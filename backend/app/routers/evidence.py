"""Evidence viewing and the audit trail (CLAUDE.md §11). Owner, current approver, or Finance only."""
import json
import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from ..auth import current_user
from ..db import get_session
from ..models import AuditEvent, Employee, Evidence, Settlement, TravelRequest
from ..schemas import EvidenceOut, TimelineEvent
from .requests import (can_view_request, can_view_settlement, employee_name, is_finance)

router = APIRouter(tags=["evidence"])


def evidence_out(ev: Evidence) -> EvidenceOut:
    data = ev.model_dump(exclude={"extracted_json"})
    return EvidenceOut(**data, extracted=json.loads(ev.extracted_json) if ev.extracted_json else None)


def load_evidence(session: Session, evidence_id: int, user: Employee) -> Evidence:
    ev = session.get(Evidence, evidence_id)
    st = session.get(Settlement, ev.settlement_id) if ev and ev.settlement_id else None
    ok = ev and (user.emp_code == ev.owner_emp_code or is_finance(user)
                 or (st and can_view_settlement(session, user, st)))
    if not ok:
        raise HTTPException(404, "Evidence not found")
    return ev


@router.get("/evidence/{evidence_id}", response_model=EvidenceOut)
def get_evidence(evidence_id: int, user: Employee = Depends(current_user),
                 session: Session = Depends(get_session)):
    return evidence_out(load_evidence(session, evidence_id, user))


@router.get("/evidence/{evidence_id}/file")
def get_evidence_file(evidence_id: int, user: Employee = Depends(current_user),
                      session: Session = Depends(get_session)) -> FileResponse:
    ev = load_evidence(session, evidence_id, user)
    path = Path(ev.storage_path)
    if not path.is_file():
        raise HTTPException(404, "File is missing from storage")
    media = mimetypes.guess_type(ev.filename)[0] or "application/octet-stream"
    if ev.kind == "email":
        media = "text/plain; charset=utf-8"
    return FileResponse(path, media_type=media)


def _can_view_entity(session: Session, user: Employee, etype: str, eid: str) -> bool:
    if etype == "request":
        req = session.get(TravelRequest, eid)
        return bool(req and can_view_request(session, user, req))
    st = session.get(Settlement, int(eid)) if eid.isdigit() else None
    return bool(st and can_view_settlement(session, user, st))


@router.get("/audit", response_model=list[TimelineEvent])
def audit(entity_type: str | None = None, entity_id: str | None = None,
          user: Employee = Depends(current_user), session: Session = Depends(get_session)):
    if not is_finance(user):  # Finance reads any; others only entities they can see
        if not (entity_type and entity_id):
            raise HTTPException(400, "entity_type and entity_id are required")
        if not _can_view_entity(session, user, entity_type, entity_id):
            raise HTTPException(403, "Not allowed to read this audit trail")
    query = select(AuditEvent).order_by(AuditEvent.at, AuditEvent.id)
    if entity_type:
        query = query.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        query = query.where(AuditEvent.entity_id == entity_id)
    return [TimelineEvent(**e.model_dump(), actor_name=employee_name(session, e.actor_code))
            for e in session.exec(query)]
