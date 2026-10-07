import json

from sqlmodel import select

from app.models import Advance, ApprovalStep, AuditEvent, Employee, RequestCostHead, Settlement, TravelRequest


def test_seed_loads_employees_and_trip(session):
    assert len(session.exec(select(Employee)).all()) == 9
    trq = session.get(TravelRequest, "TRQ-2026-0001")
    assert trq.status == "advance_paid" and trq.emp_code == "NX-4471"
    heads = session.exec(select(RequestCostHead)).all()
    assert sum(h.estimate_paise for h in heads) == trq.estimate_total_paise == 4_350_000
    assert sum(h.estimate_paise for h in heads if h.borne_by == "Employee") * 60 // 100 == 1_980_000
    assert session.exec(select(Advance)).one().reference == "ADV/2026/0619"
    assert session.exec(select(ApprovalStep)).one().approver_code == "NX-2210"
    assert len(session.exec(select(AuditEvent)).all()) == 3
    assert len(json.loads(trq.legacy_flags_json)) == 2
    assert session.exec(select(Settlement)).one().status == "draft"


def test_seed_is_idempotent(session):
    from app.seed import seed_if_empty
    assert seed_if_empty(session) is False


def test_login_picker_and_roles(login_as):
    c = login_as("NX-2210")
    me = c.get("/api/auth/me").json()
    assert me["app_role"] == "manager"
    roles = {e["emp_code"]: e["app_role"] for e in c.get("/api/employees").json()}
    assert roles["NX-4471"] == "employee" and roles["NX-3305"] == "admin" and roles["NX-1000"] == "manager"
    c.post("/api/auth/logout")
    assert c.get("/api/auth/me").status_code == 401


def test_unknown_login_404(login_as):
    c = login_as("NX-4471")
    assert c.post("/api/auth/login", json={"emp_code": "NX-0"}).status_code == 404
