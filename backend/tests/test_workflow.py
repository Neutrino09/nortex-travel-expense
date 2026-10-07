"""State machines and invariants (§3, §5), exercised through the HTTP API."""
import hashlib
from datetime import date

from sqlmodel import Session, select

from app import db
from app.models import (ApprovalStep, AuditEvent, Evidence, Payment, Settlement, TravelRequest)
from app.workflow import transition

CHAITANYA, SURESH, MEERA, RAVI, KAVITHA = "NX-4471", "NX-2210", "NX-1108", "NX-3305", "NX-3300"
SETTLEMENT_ID = 1  # seeded draft settlement of TRQ-2026-0001 (advance ₹20,000)


def make_evidence(owner=CHAITANYA, name="bill.png"):
    with Session(db.engine) as s:
        ev = Evidence(owner_emp_code=owner, filename=name, kind="image", storage_path="/nonexistent",
                      sha256=hashlib.sha256(name.encode()).hexdigest(), triage="used")
        s.add(ev)
        s.commit()
        return ev.id


def lodging_payload(base_paise, evidence_id, bill="B1"):
    return dict(section="lodging", head="lodging", date="2026-06-17", merchant="Keys Prime", bill_no=bill,
                description="Room", nights=5, base_paise=base_paise, tax_paise=0, evidence_id=evidence_id)


def add_claim(login_as, base_paise=2_900_000):
    c = login_as(CHAITANYA)
    r = c.post(f"/api/settlements/{SETTLEMENT_ID}/lines", json=lodging_payload(base_paise, make_evidence()))
    assert r.status_code == 201, r.text
    return c, r.json()["id"]


def submit_claim(login_as, base_paise=2_900_000):
    c, line_id = add_claim(login_as, base_paise)
    r = c.post(f"/api/settlements/{SETTLEMENT_ID}/submit")
    assert r.status_code == 200, r.text
    return c, line_id, r.json()


def act(client, action, remarks=None, etype="settlement", eid=str(SETTLEMENT_ID)):
    return client.post(f"/api/approvals/{etype}/{eid}/act", json={"action": action, "remarks": remarks})


def status_of(client):
    return client.get(f"/api/settlements/{SETTLEMENT_ID}").json()["status"]


def test_happy_path_chain_and_payout(login_as):
    c, _, out = submit_claim(login_as)  # ₹29,000 net -> Suresh, Meera, Ravi
    assert [s["approver_code"] for s in out["chain"]] == [SURESH, MEERA, RAVI]
    assert act(login_as(SURESH), "approve").status_code == 200
    assert act(login_as(MEERA), "approve").json()["status"] == "finance_review"
    assert act(login_as(RAVI), "approve").json()["status"] == "verified"
    pay = c.get(f"/api/settlements/{SETTLEMENT_ID}").json()["payments"]
    assert [(p["kind"], p["amount_paise"], p["run_date"]) for p in pay] == [("payout", 900_000, "2026-06-25")]
    assert login_as(RAVI).post(f"/api/finance/payments/{pay[0]['id']}/mark-paid").status_code == 200
    assert status_of(c) == "paid"


def test_illegal_transition_is_409(login_as):
    c = login_as(CHAITANYA)
    assert c.post("/api/requests/TRQ-2026-0001/submit").status_code == 409  # already advance_paid
    assert act(login_as(SURESH), "approve").status_code == 409  # settlement is still a draft
    assert login_as(RAVI).post("/api/finance/requests/TRQ-2026-0001/disburse-advance",
                               json={"amount_paise": 100}).status_code == 409


def test_only_current_pending_approver_can_act(login_as):
    submit_claim(login_as)
    assert act(login_as(MEERA), "approve").status_code == 403  # waiting, not pending
    assert act(login_as(RAVI), "approve").status_code == 403
    assert act(login_as("NX-5182"), "approve").status_code == 403  # unrelated employee


def test_nobody_acts_on_own_request_or_claim(login_as, session):
    c, _, _ = submit_claim(login_as)
    assert act(c, "approve").status_code == 403  # Chaitanya on his own claim
    # Suresh's own request: even though he is a manager, he cannot approve it
    s = login_as(SURESH)
    body = {"purpose": "x", "destination_city": "Pune", "from_date": "2026-07-01", "to_date": "2026-07-02",
            "heads": [{"head": "lodging", "estimate_paise": 100_000, "borne_by": "Employee"}]}
    trq = s.post("/api/requests", json=body).json()["id"]
    assert s.post(f"/api/requests/{trq}/submit").status_code == 200
    assert act(s, "approve", etype="request", eid=trq).status_code == 403


def test_finance_never_verifies_own_claim(session):
    ravi = session.get(__import__("app.models", fromlist=["Employee"]).Employee, RAVI)
    st = Settlement(request_id="TRQ-2026-0001", emp_code=RAVI, status="finance_review")
    session.add(st)
    session.flush()
    session.add(ApprovalStep(entity_type="settlement", entity_id=str(st.id), revision=1, seq=1,
                             level="FINANCE", approver_code=RAVI, status="pending"))
    session.flush()
    try:
        transition(session, st, "approve", ravi)
        raise AssertionError("expected 403")
    except Exception as e:  # HTTPException
        assert e.status_code == 403


def test_return_then_resubmit_keeps_id_bumps_revision_rebuilds_chain(login_as):
    c, line_id, out = submit_claim(login_as)  # ₹29,000 -> three approvers
    s = login_as(SURESH)
    assert act(s, "return", "").status_code == 400  # remarks required
    assert act(s, "return", "Please reduce the lodging").status_code == 200
    assert status_of(c) == "returned"
    # edit the line down to ₹5,000 and resubmit: same settlement id, revision 2, shorter chain
    assert c.patch(f"/api/settlements/{SETTLEMENT_ID}/lines/{line_id}",
                   json={"base_paise": 500_000, "nights": 4}).status_code == 200
    out = c.post(f"/api/settlements/{SETTLEMENT_ID}/resubmit").json()
    assert [x["approver_code"] for x in out["chain"]] == [SURESH, RAVI]
    detail = c.get(f"/api/settlements/{SETTLEMENT_ID}").json()
    assert detail["id"] == SETTLEMENT_ID and detail["revision"] == 2 and detail["status"] == "pending_approval"
    assert act(s, "approve").json()["status"] == "finance_review"


def test_reject_creates_full_advance_recovery(login_as, session):
    submit_claim(login_as)
    assert act(login_as(SURESH), "reject", None).status_code == 400
    assert act(login_as(SURESH), "reject", "Not a business trip").json()["status"] == "rejected"
    pays = session.exec(select(Payment)).all()
    assert [(p.kind, p.amount_paise, p.status) for p in pays] == [("recovery", 2_000_000, "payroll_deduction")]
    assert act(login_as(SURESH), "approve").status_code == 409  # terminal


def test_verify_with_recovery(login_as, session):
    submit_claim(login_as, base_paise=1_500_000)  # net ₹15,000 vs ₹20,000 advance
    act(login_as(SURESH), "approve")
    assert act(login_as(RAVI), "approve").json()["status"] == "verified"
    pays = session.exec(select(Payment)).all()
    assert [(p.kind, p.amount_paise, p.status) for p in pays] == [("recovery", 500_000, "payroll_deduction")]


def test_submit_blocked_while_block_finding_exists(login_as):
    c = login_as(CHAITANYA)
    assert c.post(f"/api/settlements/{SETTLEMENT_ID}/submit").status_code == 400  # R-EMPTY
    payload = lodging_payload(2_900_000, None)
    c.post(f"/api/settlements/{SETTLEMENT_ID}/lines", json=payload)  # no proof -> R-PROOF
    r = c.post(f"/api/settlements/{SETTLEMENT_ID}/submit")
    assert r.status_code == 400 and "proof" in r.json()["detail"].lower()
    assert status_of(c) == "draft"
    v = c.post(f"/api/settlements/{SETTLEMENT_ID}/validate").json()
    assert v["rules_checked"] == 13 and any(f["severity"] == "BLOCK" for f in v["findings"])


def test_request_flow_submit_approve_disburse(login_as):
    c = login_as("NX-4490")  # Imran
    body = {"purpose": "Client visit", "destination_city": "Mumbai", "from_date": "2026-07-01",
            "to_date": "2026-07-03", "advance_requested_paise": 1_000_000,
            "heads": [{"head": "lodging", "estimate_paise": 2_000_000, "borne_by": "Employee"}]}
    r = c.post("/api/requests", json=body)
    trq = r.json()["id"]
    assert trq == "TRQ-2026-0002" and r.json()["advance_cap_paise"] == 1_200_000
    assert c.post(f"/api/requests/{trq}/submit").json()["status"] == "pending_approval"
    assert act(login_as(SURESH), "approve", etype="request", eid=trq).json()["status"] == "approved"
    ravi = login_as(RAVI)
    assert ravi.post(f"/api/finance/requests/{trq}/disburse-advance", json={"amount_paise": 1_000_000}).status_code == 200
    assert c.get(f"/api/requests/{trq}").json()["status"] == "advance_paid"


def test_request_advance_over_cap_blocks_submit_and_edit_rules(login_as):
    c = login_as("NX-4490")
    body = {"purpose": "x", "destination_city": "Mumbai", "from_date": "2026-07-01", "to_date": "2026-07-03",
            "advance_requested_paise": 1_300_000,
            "heads": [{"head": "lodging", "estimate_paise": 2_000_000, "borne_by": "Employee"}]}
    trq = c.post("/api/requests", json=body).json()["id"]
    assert c.post(f"/api/requests/{trq}/submit").status_code == 400
    v = c.post(f"/api/requests/{trq}/validate").json()
    assert v["advance_cap_paise"] == 1_200_000 and v["findings"][0]["rule_id"] == "RQ-ADV"
    body["advance_requested_paise"] = 1_200_000
    assert c.patch(f"/api/requests/{trq}", json=body).status_code == 200
    assert c.post(f"/api/requests/{trq}/submit").status_code == 200
    assert c.patch(f"/api/requests/{trq}", json=body).status_code == 409  # locked once submitted


def test_authorization_scoping(login_as):
    submit_claim(login_as)
    other = login_as("NX-5182")  # Deepa cannot see Chaitanya's items
    assert other.get(f"/api/settlements/{SETTLEMENT_ID}").status_code == 404
    assert other.get("/api/requests/TRQ-2026-0001").status_code == 404
    assert other.get("/api/finance/queue").status_code == 403
    assert login_as(SURESH).get(f"/api/settlements/{SETTLEMENT_ID}").status_code == 200
    inbox = login_as(SURESH).get("/api/approvals/inbox").json()
    assert [(i["entity_type"], i["amount_paise"]) for i in inbox] == [("settlement", 2_900_000)]
    assert login_as(RAVI).get("/api/audit").status_code == 200
    assert other.get("/api/audit?entity_type=request&entity_id=TRQ-2026-0001").status_code == 403


def test_every_transition_writes_audit(login_as, session):
    submit_claim(login_as)
    act(login_as(SURESH), "approve")
    actions = [e.action for e in session.exec(select(AuditEvent).where(AuditEvent.entity_type == "settlement"))]
    assert actions == ["submit", "approve"]
