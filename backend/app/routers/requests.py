"""Travel requests. Phase 1 stubs — Agent A implements (CLAUDE.md §5–7, §11)."""
from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..auth import current_user
from ..db import get_session
from ..models import Employee
from ..schemas import RequestIn, RequestListItem, RequestOut, RequestValidateOut, SubmitOut

router = APIRouter(prefix="/requests", tags=["requests"])


@router.get("", response_model=list[RequestListItem])
def list_requests(user: Employee = Depends(current_user), session: Session = Depends(get_session)):
    raise NotImplementedError


@router.post("", response_model=RequestOut, status_code=201)
def create_request(body: RequestIn, user: Employee = Depends(current_user),
                   session: Session = Depends(get_session)):
    raise NotImplementedError


@router.get("/{request_id}", response_model=RequestOut)
def get_request(request_id: str, user: Employee = Depends(current_user),
                session: Session = Depends(get_session)):
    raise NotImplementedError


@router.patch("/{request_id}", response_model=RequestOut)
def patch_request(request_id: str, body: RequestIn, user: Employee = Depends(current_user),
                  session: Session = Depends(get_session)):
    raise NotImplementedError


@router.post("/{request_id}/validate", response_model=RequestValidateOut)
def validate_request(request_id: str, user: Employee = Depends(current_user),
                     session: Session = Depends(get_session)):
    raise NotImplementedError


@router.post("/{request_id}/submit", response_model=SubmitOut)
def submit_request(request_id: str, user: Employee = Depends(current_user),
                   session: Session = Depends(get_session)):
    raise NotImplementedError


@router.post("/{request_id}/resubmit", response_model=SubmitOut)
def resubmit_request(request_id: str, user: Employee = Depends(current_user),
                     session: Session = Depends(get_session)):
    raise NotImplementedError
