"""Finance: advances, verification queue, payment runs (CLAUDE.md §3, §8, §11). Admin only."""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from .. import workflow
from ..auth import require_admin
from ..db import get_session
from ..models import Employee, Payment, TravelRequest
from ..schemas import DisburseIn, FinanceQueue, PaymentOut, RequestOut
from .approvals import pending_items
from .requests import list_item, request_out
from .settlements import payment_out

router = APIRouter(prefix="/finance", tags=["finance"])


@router.get("/queue", response_model=FinanceQueue)
def queue(user: Employee = Depends(require_admin), session: Session = Depends(get_session)):
    to_disburse = session.exec(select(TravelRequest).where(
        TravelRequest.status == "approved", TravelRequest.advance_requested_paise > 0,
        TravelRequest.emp_code != user.emp_code))  # not your own request
    payments = session.exec(select(Payment).order_by(Payment.run_date, Payment.id))
    return FinanceQueue(
        advances_to_disburse=[list_item(session, r) for r in to_disburse],
        settlements_to_verify=pending_items(session, user.emp_code, level="FINANCE"),
        payments=[payment_out(session, p) for p in payments])


@router.post("/requests/{request_id}/disburse-advance", response_model=RequestOut)
def disburse_advance(request_id: str, body: DisburseIn, user: Employee = Depends(require_admin),
                     session: Session = Depends(get_session)):
    req = session.get(TravelRequest, request_id)
    if not req:
        raise HTTPException(404, "Request not found")
    workflow.disburse_advance(session, req, user, body.amount_paise)
    session.commit()
    return request_out(session, req)


@router.post("/payments/{payment_id}/mark-paid", response_model=PaymentOut)
def mark_paid(payment_id: int, user: Employee = Depends(require_admin),
              session: Session = Depends(get_session)):
    pay = session.get(Payment, payment_id)
    if not pay:
        raise HTTPException(404, "Payment not found")
    workflow.mark_paid(session, pay, user)
    session.commit()
    return payment_out(session, pay)
