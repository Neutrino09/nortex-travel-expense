"""Settlements (CLAUDE.md §5–7, §11). The two import endpoints stay stubs until Agent B's router is mounted."""
import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session, select

from .. import workflow
from ..auth import current_user
from ..db import get_session
from ..models import ClaimLine, Evidence, Employee, Payment, Settlement, TravelRequest
from ..policy import rules
from ..schemas import (Attendee, ClaimLineIn, ClaimLineOut, ClaimLinePatch, ImportResult, PaymentOut,
                       SettlementCreate, SettlementOut, SubmitOut, ValidationResult)
from .evidence import evidence_out
from .requests import (active_settlement, can_view_settlement, chain_out, employee_name, is_finance,
                       list_item, settlement_expected_payout, timeline_for)

router = APIRouter(prefix="/settlements", tags=["settlements"])
EDITABLE = ("draft", "returned")


def load_settlement(session: Session, settlement_id: int, user: Employee, owner_only: bool = False) -> Settlement:
    st = session.get(Settlement, settlement_id)
    if not st or not can_view_settlement(session, user, st):
        raise HTTPException(404, "Settlement not found")
    if owner_only and user.emp_code != st.emp_code:
        raise HTTPException(403, "Only the owner can do this")
    return st


def line_out(line: ClaimLine) -> ClaimLineOut:
    people = json.loads(line.attendees_json) if line.attendees_json else []
    data = line.model_dump(exclude={"attendees_json", "settlement_id", "fingerprint"})
    return ClaimLineOut(**data, attendees=[Attendee(**p) for p in people])


def payment_out(session: Session, pay: Payment) -> PaymentOut:
    st = session.get(Settlement, pay.settlement_id)
    return PaymentOut(**pay.model_dump(), request_id=st.request_id, emp_code=st.emp_code,
                      emp_name=employee_name(session, st.emp_code))


def settlement_out(session: Session, st: Settlement) -> SettlementOut:
    req = session.get(TravelRequest, st.request_id)
    result = rules.validate_settlement(session, st, save=st.status in EDITABLE)
    session.refresh(st)
    evidence = session.exec(select(Evidence).where(Evidence.settlement_id == st.id)
                            .order_by(Evidence.email_date, Evidence.id))
    payments = list(session.exec(select(Payment).where(Payment.settlement_id == st.id)))
    return SettlementOut(
        id=st.id, request_id=st.request_id, emp_code=st.emp_code,
        emp_name=employee_name(session, st.emp_code), status=st.status, revision=st.revision,
        submitted_at=st.submitted_at, trip=list_item(session, req),
        lines=[line_out(ln) for ln in rules.settlement_lines(session, st)],
        evidence=[evidence_out(e) for e in evidence], findings=result.findings, summary=result.summary,
        chain=chain_out(session, st, result.chain_preview), rules_checked=result.rules_checked,
        expected_payout=settlement_expected_payout(session, st) or result.expected_payout,
        payments=[payment_out(session, p) for p in payments],
        timeline=timeline_for(session, [("settlement", str(st.id))]))


def _editable(st: Settlement) -> None:
    if st.status not in EDITABLE:
        raise HTTPException(409, f"A {st.status} settlement cannot be edited")


def _check_evidence(session: Session, user: Employee, evidence_id: int | None) -> None:
    if evidence_id is not None:
        ev = session.get(Evidence, evidence_id)
        if not ev or ev.owner_emp_code != user.emp_code:
            raise HTTPException(400, "Unknown evidence")


def _attendees_json(attendees) -> str | None:
    return json.dumps([Attendee(**(a if isinstance(a, dict) else a.model_dump())).model_dump()
                       for a in attendees]) if attendees else None


def _save_and_revalidate(session: Session, st: Settlement, line: ClaimLine) -> ClaimLineOut:
    line.amount_paise = line.base_paise + line.tax_paise
    session.add(line)
    session.flush()
    rules.validate_settlement(session, st)  # refresh disallowed amounts
    session.commit()
    session.refresh(line)
    return line_out(line)


@router.post("", response_model=SettlementOut, status_code=201)
def create_settlement(body: SettlementCreate, user: Employee = Depends(current_user),
                      session: Session = Depends(get_session)):
    req = session.get(TravelRequest, body.request_id)
    if not req or req.emp_code != user.emp_code:
        raise HTTPException(404, "Request not found")
    existing = active_settlement(session, req.id)
    if existing:  # one settlement per request: return it
        return settlement_out(session, existing)
    if req.status not in ("approved", "advance_paid"):
        raise HTTPException(409, "A settlement needs an approved request")
    st = Settlement(request_id=req.id, emp_code=user.emp_code)
    session.add(st)
    session.commit()
    return settlement_out(session, st)


@router.get("/{settlement_id}", response_model=SettlementOut)
def get_settlement(settlement_id: int, user: Employee = Depends(current_user),
                   session: Session = Depends(get_session)):
    return settlement_out(session, load_settlement(session, settlement_id, user))


@router.post("/{settlement_id}/lines", response_model=ClaimLineOut, status_code=201)
def add_line(settlement_id: int, body: ClaimLineIn, user: Employee = Depends(current_user),
             session: Session = Depends(get_session)):
    st = load_settlement(session, settlement_id, user, owner_only=True)
    _editable(st)
    _check_evidence(session, user, body.evidence_id)
    data = body.model_dump(exclude={"attendees"})
    line = ClaimLine(settlement_id=st.id, source="manual", attendees_json=_attendees_json(body.attendees),
                     **data)
    return _save_and_revalidate(session, st, line)


@router.patch("/{settlement_id}/lines/{line_id}", response_model=ClaimLineOut)
def patch_line(settlement_id: int, line_id: int, body: ClaimLinePatch,
               user: Employee = Depends(current_user), session: Session = Depends(get_session)):
    st = load_settlement(session, settlement_id, user, owner_only=True)
    _editable(st)
    line = session.get(ClaimLine, line_id)
    if not line or line.settlement_id != st.id:
        raise HTTPException(404, "Line not found")
    changes = body.model_dump(exclude_unset=True)
    _check_evidence(session, user, changes.get("evidence_id"))
    if "attendees" in changes:
        line.attendees_json = _attendees_json(changes.pop("attendees") or [])
    not_nullable = ("section", "head", "description", "merchant", "paid_by", "base_paise", "tax_paise")
    for field, value in changes.items():
        if value is not None or field not in not_nullable:
            setattr(line, field, value)
    line.fingerprint = None  # recomputed from the edited fields
    return _save_and_revalidate(session, st, line)


@router.delete("/{settlement_id}/lines/{line_id}", status_code=204)
def delete_line(settlement_id: int, line_id: int, user: Employee = Depends(current_user),
                session: Session = Depends(get_session)):
    st = load_settlement(session, settlement_id, user, owner_only=True)
    _editable(st)
    line = session.get(ClaimLine, line_id)
    if not line or line.settlement_id != st.id:
        raise HTTPException(404, "Line not found")
    session.delete(line)
    session.flush()
    rules.validate_settlement(session, st)
    session.commit()


@router.post("/{settlement_id}/import", response_model=ImportResult)
def import_files(settlement_id: int, files: list[UploadFile] = File(...),
                 user: Employee = Depends(current_user), session: Session = Depends(get_session)):
    raise NotImplementedError  # Agent B (ingest)


@router.post("/{settlement_id}/import-sample", response_model=ImportResult)
def import_sample(settlement_id: int, user: Employee = Depends(current_user),
                  session: Session = Depends(get_session)):
    raise NotImplementedError  # Agent B (ingest)


@router.post("/{settlement_id}/validate", response_model=ValidationResult)
def validate(settlement_id: int, user: Employee = Depends(current_user),
             session: Session = Depends(get_session)):
    st = load_settlement(session, settlement_id, user)
    result = rules.validate_settlement(session, st, save=st.status in EDITABLE)
    session.commit()
    return result


def _submit_out(session: Session, st: Settlement) -> SubmitOut:
    return SubmitOut(entity_type="settlement", entity_id=str(st.id), status=st.status,
                     chain=chain_out(session, st, []))


@router.post("/{settlement_id}/submit", response_model=SubmitOut)
def submit(settlement_id: int, user: Employee = Depends(current_user),
           session: Session = Depends(get_session)):
    st = load_settlement(session, settlement_id, user, owner_only=True)
    workflow.transition(session, st, "submit", user)
    session.commit()
    return _submit_out(session, st)


@router.post("/{settlement_id}/resubmit", response_model=SubmitOut)
def resubmit(settlement_id: int, user: Employee = Depends(current_user),
             session: Session = Depends(get_session)):
    st = load_settlement(session, settlement_id, user, owner_only=True)
    workflow.transition(session, st, "resubmit", user)
    session.commit()
    return _submit_out(session, st)
