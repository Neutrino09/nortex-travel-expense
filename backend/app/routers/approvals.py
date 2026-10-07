from typing import Literal

from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..auth import current_user
from ..db import get_session
from ..models import Employee
from ..schemas import ActIn, ActOut, InboxItem

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("/inbox", response_model=list[InboxItem])
def inbox(user: Employee = Depends(current_user), session: Session = Depends(get_session)):
    raise NotImplementedError


@router.post("/{entity_type}/{entity_id}/act", response_model=ActOut)
def act(entity_type: Literal["request", "settlement"], entity_id: str, body: ActIn,
        user: Employee = Depends(current_user), session: Session = Depends(get_session)):
    raise NotImplementedError
