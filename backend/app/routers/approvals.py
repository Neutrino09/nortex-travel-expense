"""Approver inbox and act endpoint (CLAUDE.md §3, §11). Rules live in workflow.transition."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from .. import workflow
from ..auth import current_user
from ..db import get_session
from ..models import ApprovalStep, Employee, Settlement, TravelRequest
from ..policy import rules
from ..schemas import ActIn, ActOut, InboxItem
from .requests import employee_name, last_event_at

router = APIRouter(prefix="/approvals", tags=["approvals"])


def inbox_item(session: Session, entity, step: ApprovalStep) -> InboxItem:
    """One row: an entity where `step` is the current pending step."""
    if isinstance(entity, TravelRequest):
        flags = rules.request_findings(entity, rules.request_heads(session, entity))
        amount, req, sid = entity.estimate_total_paise, entity, None
    else:
        result = rules.validate_settlement(session, entity, save=False)
        flags, amount = result.findings, result.summary.net_paise
        req, sid = session.get(TravelRequest, entity.request_id), entity.id
    etype, eid = workflow.entity_key(entity)
    return InboxItem(entity_type=etype, entity_id=eid, request_id=req.id, settlement_id=sid,
                     emp_code=entity.emp_code, emp_name=employee_name(session, entity.emp_code),
                     purpose=req.purpose, amount_paise=amount, level=step.level,
                     waiting_since=last_event_at(session, etype, eid),
                     flags_count=sum(f.severity in ("WARN", "BLOCK") for f in flags),
                     revision=entity.revision)


def pending_items(session: Session, approver_code: str, level: str | None = None) -> list[InboxItem]:
    steps = session.exec(select(ApprovalStep).where(ApprovalStep.status == "pending",
                                                    ApprovalStep.approver_code == approver_code))
    items = []
    for step in steps:
        if level and step.level != level:
            continue
        entity = (session.get(TravelRequest, step.entity_id) if step.entity_type == "request"
                  else session.get(Settlement, int(step.entity_id)))
        if entity and entity.revision == step.revision:  # ignore steps of older revisions
            items.append(inbox_item(session, entity, step))
    return sorted(items, key=lambda i: (i.waiting_since or datetime.min, i.entity_id))


@router.get("/inbox", response_model=list[InboxItem])
def inbox(user: Employee = Depends(current_user), session: Session = Depends(get_session)):
    return pending_items(session, user.emp_code)


@router.post("/{entity_type}/{entity_id}/act", response_model=ActOut)
def act(entity_type: Literal["request", "settlement"], entity_id: str, body: ActIn,
        user: Employee = Depends(current_user), session: Session = Depends(get_session)):
    if entity_type == "request":
        entity = session.get(TravelRequest, entity_id)
    else:
        entity = session.get(Settlement, int(entity_id)) if entity_id.isdigit() else None
    if not entity:
        raise HTTPException(404, "Not found")
    workflow.transition(session, entity, body.action, user, body.remarks)
    session.commit()
    return ActOut(entity_type=entity_type, entity_id=entity_id, status=entity.status)
