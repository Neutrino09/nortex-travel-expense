from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlmodel import Session

from ..auth import current_user
from ..db import get_session
from ..models import Employee
from ..schemas import EvidenceOut, TimelineEvent

router = APIRouter(tags=["evidence"])


@router.get("/evidence/{evidence_id}", response_model=EvidenceOut)
def get_evidence(evidence_id: int, user: Employee = Depends(current_user),
                 session: Session = Depends(get_session)):
    raise NotImplementedError  # owner, current approver, or Finance only


@router.get("/evidence/{evidence_id}/file")
def get_evidence_file(evidence_id: int, user: Employee = Depends(current_user),
                      session: Session = Depends(get_session)) -> FileResponse:
    raise NotImplementedError  # owner, current approver, or Finance only


@router.get("/audit", response_model=list[TimelineEvent])
def audit(entity_type: str | None = None, entity_id: str | None = None,
          user: Employee = Depends(current_user), session: Session = Depends(get_session)):
    raise NotImplementedError  # Finance reads any; others only their own entities
