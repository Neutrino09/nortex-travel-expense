"""State machines. The ONLY place statuses change (CLAUDE.md §5). Every change writes an AuditEvent.

Principle: the LLM proposes, deterministic Python decides, the human confirms.
Invariants (§3): nobody acts on their own request/claim (403); only the current pending
approver acts (403); illegal transition (409); remarks required for return/reject (400).
"""
from fastapi import HTTPException
from sqlmodel import Session, select

from .clock import now, today
from .models import Advance, ApprovalStep, AuditEvent, Employee, Payment, Settlement, TravelRequest
from .policy import rules
from .policy.config import FINANCE_ROLE
from .policy.payments import next_payment_run

# (entity_type, action) -> statuses it may start from
ALLOWED_FROM = {
    ("request", "submit"): {"draft"},
    ("request", "resubmit"): {"returned"},
    ("request", "approve"): {"pending_approval"},
    ("request", "return"): {"pending_approval"},
    ("request", "reject"): {"pending_approval"},
    ("request", "disburse_advance"): {"approved"},
    ("settlement", "submit"): {"draft"},
    ("settlement", "resubmit"): {"returned"},
    ("settlement", "approve"): {"pending_approval", "finance_review"},
    ("settlement", "return"): {"pending_approval", "finance_review"},
    ("settlement", "reject"): {"pending_approval", "finance_review"},
    ("settlement", "mark_paid"): {"verified"},
}
STEP_STATUS = {"return": "returned", "reject": "rejected"}


def entity_key(entity) -> tuple[str, str]:
    if isinstance(entity, TravelRequest):
        return "request", entity.id
    return "settlement", str(entity.id)


def current_steps(session: Session, entity) -> list[ApprovalStep]:
    """Steps of the entity's current revision, in order."""
    etype, eid = entity_key(entity)
    return list(session.exec(select(ApprovalStep).where(
        ApprovalStep.entity_type == etype, ApprovalStep.entity_id == eid,
        ApprovalStep.revision == entity.revision).order_by(ApprovalStep.seq)))


def pending_step(session: Session, entity) -> ApprovalStep | None:
    return next((s for s in current_steps(session, entity) if s.status == "pending"), None)


def write_audit(session: Session, entity, actor: Employee, action: str, from_status: str | None,
                to_status: str | None, remarks: str | None = None) -> None:
    etype, eid = entity_key(entity)
    session.add(AuditEvent(entity_type=etype, entity_id=eid, actor_code=actor.emp_code, action=action,
                           from_status=from_status, to_status=to_status, remarks=remarks, at=now()))


# ------------------------------------------------------------------ guards

def _check_actor(session: Session, entity, action: str, actor: Employee) -> ApprovalStep | None:
    if action in ("submit", "resubmit"):
        if actor.emp_code != entity.emp_code:
            raise HTTPException(403, "Only the owner can submit")
    elif action in ("disburse_advance", "mark_paid"):
        if actor.role != FINANCE_ROLE:
            raise HTTPException(403, "Finance access required")
        if actor.emp_code == entity.emp_code:  # Finance never handles their own claim
            raise HTTPException(403, "You cannot act on your own request or claim")
    else:  # approve / return / reject
        if actor.emp_code == entity.emp_code:  # §3 invariant
            raise HTTPException(403, "You cannot act on your own request or claim")
        step = pending_step(session, entity)
        if not step or step.approver_code != actor.emp_code:  # §3 invariant
            raise HTTPException(403, "You are not the current approver")
        return step
    return None


# ------------------------------------------------------------------ submit / resubmit

def _blockers(session: Session, entity):
    """Server-side validation at submit; returns the chain to persist. 400 if any BLOCK."""
    if isinstance(entity, TravelRequest):
        findings = rules.request_findings(entity, rules.request_heads(session, entity))
        chain = rules.request_chain_preview(session, entity)
    else:
        result = rules.validate_settlement(session, entity)
        findings, chain = result.findings, result.chain_preview
    blocks = [f.message for f in findings if f.severity == "BLOCK"]
    if blocks:
        raise HTTPException(400, "Cannot submit: " + "; ".join(blocks))
    return chain


def _create_steps(session: Session, entity, chain) -> list[ApprovalStep]:
    etype, eid = entity_key(entity)
    steps = [ApprovalStep(entity_type=etype, entity_id=eid, revision=entity.revision, seq=c.seq,
                          level=c.level, approver_code=c.approver_code, note=c.note,
                          status="pending" if i == 0 else "waiting") for i, c in enumerate(chain)]
    session.add_all(steps)
    return steps


def _on_submit(session: Session, entity, action: str) -> str:
    chain = _blockers(session, entity)
    if action == "resubmit":  # same id, revision+1, chain rebuilt from level 1 on the new amount
        entity.revision += 1
    entity.submitted_at = now()
    steps = _create_steps(session, entity, chain)
    return "pending_approval" if steps else "approved"  # nobody above the MD -> nothing to approve


# ------------------------------------------------------------------ approve / return / reject

def _create_payment(session: Session, settlement: Settlement) -> None:
    """policy §1.3 / CLAUDE.md §8: payout on the next run, or recovery via payroll."""
    summary = rules.current_summary(session, settlement)
    run = next_payment_run(today())
    if summary.payable_paise > 0:
        session.add(Payment(settlement_id=settlement.id, kind="payout", amount_paise=summary.payable_paise,
                            run_date=run, status="scheduled"))
    if summary.recoverable_paise > 0:
        session.add(Payment(settlement_id=settlement.id, kind="recovery",
                            amount_paise=summary.recoverable_paise, run_date=run,
                            status="payroll_deduction"))


def _on_approve(session: Session, entity, step: ApprovalStep) -> str:
    nxt = next((s for s in current_steps(session, entity) if s.status == "waiting"), None)
    if nxt:
        nxt.status = "pending"
    if isinstance(entity, TravelRequest):
        return "pending_approval" if nxt else "approved"
    if step.level == "FINANCE":  # Finance verifies -> creates the payment
        _create_payment(session, entity)
        return "verified"
    return "finance_review" if (nxt and nxt.level == "FINANCE") else "pending_approval"


def _on_reject(session: Session, entity) -> str:
    if isinstance(entity, Settlement):  # the full advance becomes recoverable
        advance = rules.advance_paise_for(session, entity.request_id)
        if advance > 0:
            session.add(Payment(settlement_id=entity.id, kind="recovery", amount_paise=advance,
                                run_date=next_payment_run(today()), status="payroll_deduction"))
    return "rejected"


# ------------------------------------------------------------------ the single entry point

def transition(session: Session, entity, action: str, actor: Employee, remarks: str | None = None):
    etype, _ = entity_key(entity)
    allowed = ALLOWED_FROM.get((etype, action))
    if allowed is None or entity.status not in allowed:
        raise HTTPException(409, f"Cannot {action} a {etype} that is {entity.status}")
    if action in ("return", "reject") and not (remarks and remarks.strip()):
        raise HTTPException(400, "Remarks are required")
    step = _check_actor(session, entity, action, actor)
    old = entity.status
    if action in ("submit", "resubmit"):
        new = _on_submit(session, entity, action)
    elif action in ("approve", "return", "reject"):
        step.status, step.acted_at, step.remarks = STEP_STATUS.get(action, "approved"), now(), remarks
        new = {"approve": _on_approve, "return": lambda *_: "returned",
               "reject": lambda s, e, _st: _on_reject(s, e)}[action](session, entity, step)
    elif action == "disburse_advance":
        if entity.advance_requested_paise <= 0:
            raise HTTPException(409, "No advance was requested")
        new = "advance_paid"
    else:  # mark_paid
        new = "paid"
    entity.status = new
    write_audit(session, entity, actor, action, old, new, remarks)
    if action in ("submit", "resubmit") and new == "approved":
        write_audit(session, entity, actor, "auto_approve", "pending_approval", "approved",
                    "No approver above the claimant")
    session.add(entity)
    session.flush()
    return entity


# ------------------------------------------------------------------ Finance helpers

def _next_advance_reference(session: Session) -> str:
    prefix = f"ADV/{today().year}/"
    nums = [int(a.reference.rsplit("/", 1)[1]) for a in session.exec(select(Advance))
            if a.reference.startswith(prefix)]
    return f"{prefix}{max(nums, default=0) + 1:04d}"


def disburse_advance(session: Session, req: TravelRequest, actor: Employee, amount_paise: int) -> Advance:
    if amount_paise > req.advance_requested_paise:
        raise HTTPException(400, "Amount exceeds the advance requested")
    reference = _next_advance_reference(session)
    transition(session, req, "disburse_advance", actor, reference)  # status, role, own-request checks
    adv = Advance(request_id=req.id, amount_paise=amount_paise, reference=reference,
                  disbursed_at=now(), disbursed_by=actor.emp_code)
    session.add(adv)
    return adv


def mark_paid(session: Session, payment: Payment, actor: Employee) -> Payment:
    if payment.status == "paid":
        raise HTTPException(409, "Payment is already marked paid")
    settlement = session.get(Settlement, payment.settlement_id)
    if actor.role != FINANCE_ROLE or actor.emp_code == settlement.emp_code:
        raise HTTPException(403, "Finance access required (not on your own claim)")
    if settlement.status == "verified":
        transition(session, settlement, "mark_paid", actor)
    payment.status, payment.paid_at = "paid", now()
    session.add(payment)
    return payment
