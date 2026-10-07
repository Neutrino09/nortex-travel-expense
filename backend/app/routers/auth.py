from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select

from ..auth import app_role_for, current_user
from ..db import get_session
from ..models import Employee
from .. import clock
from ..schemas import ClockOut, EmployeeOut, LoginIn

router = APIRouter(tags=["auth"])


def to_employee_out(e: Employee) -> EmployeeOut:
    return EmployeeOut(**e.model_dump(), app_role=app_role_for(e.role))


@router.post("/auth/login", response_model=EmployeeOut)
def login(body: LoginIn, request: Request, session: Session = Depends(get_session)):
    emp = session.get(Employee, body.emp_code)
    if not emp:
        raise HTTPException(404, f"Unknown employee {body.emp_code}")
    request.session["emp_code"] = emp.emp_code
    return to_employee_out(emp)


@router.get("/auth/me", response_model=EmployeeOut)
def me(user: Employee = Depends(current_user)):
    return to_employee_out(user)


@router.post("/auth/logout", status_code=204)
def logout(request: Request):
    request.session.clear()


@router.get("/employees", response_model=list[EmployeeOut])
def employees(session: Session = Depends(get_session)):
    """Login picker — no auth needed."""
    return [to_employee_out(e) for e in session.exec(select(Employee).order_by(Employee.emp_code))]


@router.get("/clock", response_model=ClockOut)
def server_clock():
    """Server 'now' (honours APP_TODAY) so relative times in the UI match the frozen demo date."""
    return ClockOut(now=clock.now())
