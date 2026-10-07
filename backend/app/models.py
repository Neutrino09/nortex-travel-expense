"""SQLModel tables (CLAUDE.md §4). FROZEN after phase 1 — only the main agent edits this."""
import datetime as dt

from pydantic import NaiveDatetime
from sqlmodel import Field, SQLModel

# all timestamps are naive local time (single-timezone prototype, IST)


class Employee(SQLModel, table=True):
    emp_code: str = Field(primary_key=True)
    name: str
    email: str
    designation: str
    department: str
    cost_centre: str
    city: str
    reporting_manager_code: str | None = Field(default=None, foreign_key="employee.emp_code")
    role: str  # CSV value: Employee | Reporting Manager | Head of Department | ...


class TravelRequest(SQLModel, table=True):
    id: str = Field(primary_key=True)  # TRQ-YYYY-NNNN — the spine
    emp_code: str = Field(foreign_key="employee.emp_code", index=True)
    purpose: str = ""
    visiting_place: str = ""
    visiting_company: str = ""
    from_date: dt.date | None = None
    to_date: dt.date | None = None
    destination_city: str = ""
    city_tier: int | None = None  # 1|2|3
    category: str = "domestic"  # domestic | international
    mode: str = ""
    estimate_total_paise: int = 0  # computed = sum of heads; never typed by the user
    advance_requested_paise: int = 0
    status: str = "draft"
    created_at: NaiveDatetime
    submitted_at: NaiveDatetime | None = None
    revision: int = 1
    legacy_flags_json: str | None = None


class RequestCostHead(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    request_id: str = Field(foreign_key="travelrequest.id", index=True)
    head: str  # air_rail | lodging | conveyance | meals | other
    basis: str = ""
    estimate_paise: int = 0
    borne_by: str = "Employee"  # Employee | Company


class Advance(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    request_id: str = Field(foreign_key="travelrequest.id", index=True)
    amount_paise: int
    reference: str  # ADV/YYYY/NNNN
    disbursed_at: NaiveDatetime
    disbursed_by: str = Field(foreign_key="employee.emp_code")


class Settlement(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    request_id: str = Field(foreign_key="travelrequest.id", index=True)  # one active per request
    emp_code: str = Field(foreign_key="employee.emp_code", index=True)
    status: str = "draft"
    revision: int = 1
    submitted_at: NaiveDatetime | None = None


class Evidence(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    owner_emp_code: str = Field(foreign_key="employee.emp_code", index=True)
    settlement_id: int | None = Field(default=None, foreign_key="settlement.id", index=True)
    filename: str
    kind: str  # email | image
    sha256: str = Field(index=True)  # unique per owner (checked in the importer)
    storage_path: str
    parent_evidence_id: int | None = Field(default=None, foreign_key="evidence.id")
    email_date: NaiveDatetime | None = None
    extracted_json: str | None = None
    doc_type: str | None = None
    triage: str | None = None  # used | excluded | ignored
    triage_reason: str | None = None
    policy_ref: str | None = None


class ClaimLine(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    settlement_id: int = Field(foreign_key="settlement.id", index=True)
    section: str  # lodging | transport | other
    head: str  # lodging | cab | air | meals | business_entertainment | misc
    date: dt.date | None = None
    time: str | None = None
    description: str = ""
    merchant: str = ""
    bill_no: str | None = None
    from_place: str | None = None
    to_place: str | None = None
    city: str | None = None
    check_in: dt.date | None = None
    check_out: dt.date | None = None
    nights: int | None = None
    paid_by: str = "Employee"  # Employee | Company
    base_paise: int = 0
    tax_paise: int = 0
    amount_paise: int = 0  # = base + tax
    disallowed_paise: int = 0
    disallow_reason: str | None = None
    policy_ref: str | None = None
    evidence_id: int | None = Field(default=None, foreign_key="evidence.id")
    fingerprint: str | None = Field(default=None, index=True)
    attendees_json: str | None = None  # list of {name, organisation}
    prior_approval_ref: str | None = None
    source: str = "manual"  # import | manual


class ApprovalStep(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    entity_type: str  # request | settlement
    entity_id: str  # TRQ id or settlement id (as text)
    revision: int = 1
    seq: int
    level: str  # RM | HOD | HODIV | MD | FINANCE
    approver_code: str = Field(foreign_key="employee.emp_code")
    status: str = "waiting"  # waiting | pending | approved | returned | rejected
    acted_at: NaiveDatetime | None = None
    remarks: str | None = None
    note: str | None = None


class Payment(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    settlement_id: int = Field(foreign_key="settlement.id", index=True)
    kind: str  # payout | recovery
    amount_paise: int
    run_date: dt.date
    status: str  # scheduled | paid | payroll_deduction
    paid_at: NaiveDatetime | None = None


class AuditEvent(SQLModel, table=True):
    """APPEND-ONLY. Never update or delete."""
    id: int | None = Field(default=None, primary_key=True)
    entity_type: str  # request | settlement
    entity_id: str
    actor_code: str
    action: str
    from_status: str | None = None
    to_status: str | None = None
    remarks: str | None = None
    at: NaiveDatetime
