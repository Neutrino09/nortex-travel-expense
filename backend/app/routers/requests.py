"""Travel requests + shared view helpers (CLAUDE.md §5–7, §11)."""
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from .. import workflow
from ..auth import current_user
from ..clock import now, today
from ..db import get_session
from ..models import (Advance, ApprovalStep, AuditEvent, Employee, RequestCostHead, Settlement,
                      TravelRequest)
from ..policy import rules
from ..policy.payments import expected_payout
from ..schemas import (AdvanceOut, ChainStepOut, CostHeadOut, RequestIn, RequestListItem, RequestOut,
                       RequestValidateOut, StageInfo, SubmitOut, TimelineEvent)

router = APIRouter(prefix="/requests", tags=["requests"])
STEP_LABELS = ["Travel request", "Trip approval", "Advance disbursement", "Trip settlement",
               "Finance review", "Payout"]


# ------------------------------------------------------------------ shared helpers

def is_finance(user: Employee) -> bool:
    return user.role == "Finance"


def employee_name(session: Session, code: str | None) -> str:
    emp = session.get(Employee, code) if code else None
    return emp.name if emp else (code or "")


def active_settlement(session: Session, request_id: str) -> Settlement | None:
    rows = list(session.exec(select(Settlement).where(Settlement.request_id == request_id)
                             .order_by(Settlement.id.desc())))
    return rows[0] if rows else None


def is_approver_on(session: Session, user: Employee, etype: str, eid: str) -> bool:
    return session.exec(select(ApprovalStep).where(
        ApprovalStep.entity_type == etype, ApprovalStep.entity_id == eid,
        ApprovalStep.approver_code == user.emp_code)).first() is not None


def can_view_request(session: Session, user: Employee, req: TravelRequest) -> bool:
    """Owner, Finance, or someone in the approval chain of the request / its settlement."""
    if user.emp_code == req.emp_code or is_finance(user) or is_approver_on(session, user, "request", req.id):
        return True
    st = active_settlement(session, req.id)
    return bool(st and is_approver_on(session, user, "settlement", str(st.id)))


def can_view_settlement(session: Session, user: Employee, st: Settlement) -> bool:
    return (user.emp_code == st.emp_code or is_finance(user)
            or is_approver_on(session, user, "settlement", str(st.id)))


def load_request(session: Session, request_id: str, user: Employee, owner_only: bool = False) -> TravelRequest:
    req = session.get(TravelRequest, request_id)
    if not req or not can_view_request(session, user, req):
        raise HTTPException(404, "Request not found")  # do not reveal other people's ids
    if owner_only and user.emp_code != req.emp_code:
        raise HTTPException(403, "Only the owner can do this")
    return req


def chain_out(session: Session, entity, preview) -> list[ChainStepOut]:
    """Persisted steps of the current revision if any, else the preview."""
    steps = workflow.current_steps(session, entity)
    if not steps:
        return preview
    return [ChainStepOut(seq=s.seq, level=s.level, approver_code=s.approver_code,
                         approver_name=employee_name(session, s.approver_code), note=s.note, id=s.id,
                         status=s.status, acted_at=s.acted_at, remarks=s.remarks) for s in steps]


def timeline_for(session: Session, pairs: list[tuple[str, str]]) -> list[TimelineEvent]:
    events: list[AuditEvent] = []
    for etype, eid in pairs:
        events += session.exec(select(AuditEvent).where(AuditEvent.entity_type == etype,
                                                        AuditEvent.entity_id == eid))
    events.sort(key=lambda e: (e.at, e.id))
    return [TimelineEvent(**e.model_dump(), actor_name=employee_name(session, e.actor_code)) for e in events]


def last_event_at(session: Session, etype: str, eid: str):
    e = session.exec(select(AuditEvent).where(AuditEvent.entity_type == etype, AuditEvent.entity_id == eid)
                     .order_by(AuditEvent.at.desc(), AuditEvent.id.desc())).first()
    return e.at if e else None


def stage_for(session: Session, req: TravelRequest, st: Settlement | None) -> StageInfo:
    """Stepper mapping (CLAUDE.md §5)."""
    waiting_entity, step_index = None, 3
    if req.status in ("draft", "returned", "rejected"):
        step_index = 0
    elif req.status == "pending_approval":
        step_index, waiting_entity = 1, req
    elif req.status == "approved" and req.advance_requested_paise > 0:
        step_index = 2
    elif st and st.status in ("finance_review",):
        step_index, waiting_entity = 4, st
    elif st and st.status in ("verified", "paid"):
        step_index = 5
    elif st and st.status == "pending_approval":
        step_index, waiting_entity = 3, st
    info = StageInfo(step_index=step_index, step_label=STEP_LABELS[step_index])
    if step_index == 2:
        info.waiting_on_name = "Finance (advance disbursement)"
        info.waiting_since = last_event_at(session, "request", req.id)
    step = workflow.pending_step(session, waiting_entity) if waiting_entity else None
    if step:
        etype, eid = workflow.entity_key(waiting_entity)
        info.waiting_on_code, info.waiting_on_name = step.approver_code, employee_name(session, step.approver_code)
        info.waiting_since = last_event_at(session, etype, eid)
    return info


def settlement_expected_payout(session: Session, st: Settlement | None):
    """'Expected payout: ₹X on <date>' from submit onwards; 'estimated' until verified."""
    if not st or st.status in ("draft", "returned", "rejected"):
        return None
    from ..models import Payment
    pay = session.exec(select(Payment).where(Payment.settlement_id == st.id)).first()
    return expected_payout(rules.current_summary(session, st), today(), st.status in ("verified", "paid"),
                           pay.run_date if pay else None)


def list_item(session: Session, req: TravelRequest) -> RequestListItem:
    st = active_settlement(session, req.id)
    return RequestListItem(
        id=req.id, emp_code=req.emp_code, emp_name=employee_name(session, req.emp_code),
        purpose=req.purpose, destination_city=req.destination_city, from_date=req.from_date,
        to_date=req.to_date, status=req.status, estimate_total_paise=req.estimate_total_paise,
        advance_requested_paise=req.advance_requested_paise, revision=req.revision,
        created_at=req.created_at, stage=stage_for(session, req, st),
        settlement_id=st.id if st else None, settlement_status=st.status if st else None,
        expected_payout=settlement_expected_payout(session, st))


def request_out(session: Session, req: TravelRequest) -> RequestOut:
    heads = rules.request_heads(session, req)
    adv = session.exec(select(Advance).where(Advance.request_id == req.id)).first()
    st = active_settlement(session, req.id)
    pairs = [("request", req.id)] + ([("settlement", str(st.id))] if st else [])
    return RequestOut(
        **list_item(session, req).model_dump(), visiting_place=req.visiting_place,
        visiting_company=req.visiting_company, city_tier=req.city_tier, category=req.category,
        mode=req.mode, submitted_at=req.submitted_at, heads=[CostHeadOut(**h.model_dump()) for h in heads],
        days=rules.request_days(req.from_date, req.to_date), advance_cap_paise=rules.advance_cap_paise(heads),
        advance=AdvanceOut(**adv.model_dump(), disbursed_by_name=employee_name(session, adv.disbursed_by))
        if adv else None,
        chain=chain_out(session, req, rules.request_chain_preview(session, req)),
        legacy_flags=json.loads(req.legacy_flags_json) if req.legacy_flags_json else [],
        settlement_summary=rules.current_summary(session, st) if st else None,
        timeline=timeline_for(session, pairs))


# ------------------------------------------------------------------ writes

def _next_request_id(session: Session) -> str:
    prefix = f"TRQ-{today().year}-"
    nums = [int(r.id.rsplit("-", 1)[1]) for r in session.exec(select(TravelRequest)) if r.id.startswith(prefix)]
    return f"{prefix}{max(nums, default=0) + 1:04d}"


def _apply(session: Session, req: TravelRequest, body: RequestIn) -> None:
    for f in ("purpose", "visiting_place", "visiting_company", "from_date", "to_date",
              "destination_city", "category", "mode", "advance_requested_paise"):
        setattr(req, f, getattr(body, f))
    req.city_tier = rules.resolve_tier(body.destination_city, body.city_tier)  # policy §3.1
    for old in rules.request_heads(session, req):
        session.delete(old)
    session.flush()
    for h in body.heads:
        session.add(RequestCostHead(request_id=req.id, **h.model_dump()))
    req.estimate_total_paise = sum(h.estimate_paise for h in body.heads)  # computed, never typed


@router.get("", response_model=list[RequestListItem])
def list_requests(user: Employee = Depends(current_user), session: Session = Depends(get_session)):
    query = select(TravelRequest).order_by(TravelRequest.created_at.desc(), TravelRequest.id.desc())
    if not is_finance(user):
        query = query.where(TravelRequest.emp_code == user.emp_code)
    return [list_item(session, r) for r in session.exec(query)]


@router.post("", response_model=RequestOut, status_code=201)
def create_request(body: RequestIn, user: Employee = Depends(current_user),
                   session: Session = Depends(get_session)):
    req = TravelRequest(id=_next_request_id(session), emp_code=user.emp_code, created_at=now())
    session.add(req)
    session.flush()
    _apply(session, req, body)
    session.commit()
    return request_out(session, req)


@router.get("/{request_id}", response_model=RequestOut)
def get_request(request_id: str, user: Employee = Depends(current_user),
                session: Session = Depends(get_session)):
    return request_out(session, load_request(session, request_id, user))


@router.patch("/{request_id}", response_model=RequestOut)
def patch_request(request_id: str, body: RequestIn, user: Employee = Depends(current_user),
                  session: Session = Depends(get_session)):
    req = load_request(session, request_id, user, owner_only=True)
    if req.status not in ("draft", "returned"):
        raise HTTPException(409, f"A {req.status} request cannot be edited")
    _apply(session, req, body)
    session.commit()
    return request_out(session, req)


@router.post("/{request_id}/validate", response_model=RequestValidateOut)
def validate_request(request_id: str, user: Employee = Depends(current_user),
                     session: Session = Depends(get_session)):
    req = load_request(session, request_id, user)
    heads = rules.request_heads(session, req)
    return RequestValidateOut(
        findings=rules.request_findings(req, heads), advance_cap_paise=rules.advance_cap_paise(heads),
        chain_preview=rules.request_chain_preview(session, req), estimate_total_paise=req.estimate_total_paise,
        days=rules.request_days(req.from_date, req.to_date),
        city_tier=rules.resolve_tier(req.destination_city, req.city_tier))


def _submit_out(session: Session, req: TravelRequest) -> SubmitOut:
    return SubmitOut(entity_type="request", entity_id=req.id, status=req.status,
                     chain=chain_out(session, req, []))


@router.post("/{request_id}/submit", response_model=SubmitOut)
def submit_request(request_id: str, user: Employee = Depends(current_user),
                   session: Session = Depends(get_session)):
    req = load_request(session, request_id, user, owner_only=True)
    workflow.transition(session, req, "submit", user)
    session.commit()
    return _submit_out(session, req)


@router.post("/{request_id}/resubmit", response_model=SubmitOut)
def resubmit_request(request_id: str, user: Employee = Depends(current_user),
                     session: Session = Depends(get_session)):
    req = load_request(session, request_id, user, owner_only=True)
    workflow.transition(session, req, "resubmit", user)
    session.commit()
    return _submit_out(session, req)
