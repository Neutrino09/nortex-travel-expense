"""Seed on startup only when the DB is empty (CLAUDE.md §10)."""
import csv
import json
from datetime import datetime

from sqlmodel import Session, select

from .config import get_settings
from .models import (Advance, ApprovalStep, AuditEvent, Employee, RequestCostHead, Settlement,
                     TravelRequest)

TRQ_ID = "TRQ-2026-0001"
LEGACY_FLAGS = [
    "Advance ₹20,000 exceeds the 60% cap of ₹19,800 (§1.2).",
    "Estimate above ₹25,000 needed Head of Department approval (§2); only the Reporting Manager "
    "approved by email. The email also states ₹48,000 while the form totals ₹43,500.",
]


def seed_if_empty(session: Session) -> bool:
    if session.exec(select(Employee)).first():
        return False
    _seed_employees(session)
    _seed_chaitanya_trip(session)
    session.commit()
    return True


def _seed_employees(session: Session) -> None:
    path = get_settings().pack_dir / "employee_master.csv"
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            row["reporting_manager_code"] = row["reporting_manager_code"] or None
            session.add(Employee(**row))
    session.commit()  # employees first so FKs resolve


def _seed_chaitanya_trip(session: Session) -> None:
    from datetime import date
    # Assumption §17.4: lodging is Employee-borne (voucher says Pay at Hotel; folio on personal card).
    heads = [
        ("air_rail", "Flights BLR return (booked via travel desk)", 1_050_000, "Company"),
        ("lodging", "Keys Prime, 4 nights (pay at hotel)", 2_300_000, "Employee"),
        ("conveyance", "Local cabs", 400_000, "Employee"),
        ("meals", "Meals", 600_000, "Employee"),
    ]
    session.add(TravelRequest(
        id=TRQ_ID, emp_code="NX-4471", purpose="Customer meeting + site visit",
        visiting_place="Bengaluru", visiting_company="Vertex Technologies",
        from_date=date(2026, 6, 16), to_date=date(2026, 6, 20), destination_city="Bengaluru",
        city_tier=1, category="domestic", mode="Flight",
        estimate_total_paise=sum(h[2] for h in heads), advance_requested_paise=2_000_000,
        status="advance_paid", created_at=datetime(2026, 6, 8, 9, 0),
        submitted_at=datetime(2026, 6, 8, 9, 30), revision=1,
        legacy_flags_json=json.dumps(LEGACY_FLAGS)))
    for head, basis, paise, borne in heads:
        session.add(RequestCostHead(request_id=TRQ_ID, head=head, basis=basis,
                                    estimate_paise=paise, borne_by=borne))
    session.add(Advance(request_id=TRQ_ID, amount_paise=2_000_000, reference="ADV/2026/0619",
                        disbursed_at=datetime(2026, 6, 10, 11, 0), disbursed_by="NX-3305"))
    session.add(ApprovalStep(entity_type="request", entity_id=TRQ_ID, revision=1, seq=1,
                             level="RM", approver_code="NX-2210", status="approved",
                             acted_at=datetime(2026, 6, 8, 16, 0),
                             remarks="Approved. Keep hotel within 6000/night."))
    for actor, action, frm, to, remarks, at in [
        ("NX-4471", "submit", "draft", "pending_approval", None, datetime(2026, 6, 8, 9, 30)),
        ("NX-2210", "approve", "pending_approval", "approved",
         "Approved. Keep hotel within 6000/night.", datetime(2026, 6, 8, 16, 0)),
        ("NX-3305", "disburse_advance", "approved", "advance_paid",
         "ADV/2026/0619", datetime(2026, 6, 10, 11, 0)),
    ]:
        session.add(AuditEvent(entity_type="request", entity_id=TRQ_ID, actor_code=actor,
                               action=action, from_status=frm, to_status=to,
                               remarks=remarks, at=at))
    session.add(Settlement(request_id=TRQ_ID, emp_code="NX-4471", status="draft"))
