"""'Log in as' picker. emp_code lives in the signed session cookie. All authz is server-side."""
from fastapi import Depends, HTTPException, Request
from sqlmodel import Session

from .db import get_session
from .models import Employee

ADMIN_ROLES = {"Finance"}
MANAGER_ROLES = {"Reporting Manager", "Head of Department", "Head of Division", "MD"}


def app_role_for(csv_role: str) -> str:
    """CSV role -> UI role: employee | manager | admin (CLAUDE.md §3)."""
    if csv_role in ADMIN_ROLES:
        return "admin"
    if csv_role in MANAGER_ROLES:
        return "manager"
    return "employee"


def current_user(request: Request, session: Session = Depends(get_session)) -> Employee:
    code = request.session.get("emp_code")
    user = session.get(Employee, code) if code else None
    if not user:
        raise HTTPException(401, "Not logged in")
    return user


def require_admin(user: Employee = Depends(current_user)) -> Employee:
    if app_role_for(user.role) != "admin":
        raise HTTPException(403, "Finance (admin) access required")
    return user


def require_manager(user: Employee = Depends(current_user)) -> Employee:
    if app_role_for(user.role) != "manager":
        raise HTTPException(403, "Manager access required")
    return user
