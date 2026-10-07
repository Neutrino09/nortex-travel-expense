from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..auth import require_admin
from ..db import get_session
from ..models import Employee
from ..schemas import DisburseIn, FinanceQueue, PaymentOut, RequestOut

router = APIRouter(prefix="/finance", tags=["finance"])


@router.get("/queue", response_model=FinanceQueue)
def queue(user: Employee = Depends(require_admin), session: Session = Depends(get_session)):
    raise NotImplementedError


@router.post("/requests/{request_id}/disburse-advance", response_model=RequestOut)
def disburse_advance(request_id: str, body: DisburseIn, user: Employee = Depends(require_admin),
                     session: Session = Depends(get_session)):
    raise NotImplementedError


@router.post("/payments/{payment_id}/mark-paid", response_model=PaymentOut)
def mark_paid(payment_id: int, user: Employee = Depends(require_admin),
              session: Session = Depends(get_session)):
    raise NotImplementedError
