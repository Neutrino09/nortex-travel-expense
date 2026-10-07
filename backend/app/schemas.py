"""THE API CONTRACT (CLAUDE.md §11). Mirrored exactly in frontend/src/api/types.ts.
FROZEN after phase 1 — only the main agent edits this. Money = integer paise. Dates = ISO strings."""
from datetime import date as Date, datetime
from typing import Literal

from pydantic import BaseModel, Field

AppRole = Literal["employee", "manager", "admin"]
Severity = Literal["BLOCK", "DISALLOW", "WARN", "INFO"]
Level = Literal["RM", "HOD", "HODIV", "MD", "FINANCE"]
StepStatus = Literal["waiting", "pending", "approved", "returned", "rejected"]
EntityType = Literal["request", "settlement"]
Triage = Literal["used", "excluded", "ignored"]
Head = Literal["air_rail", "lodging", "conveyance", "meals", "other"]
LineHead = Literal["lodging", "cab", "air", "meals", "business_entertainment", "misc"]
Section = Literal["lodging", "transport", "other"]
PaidBy = Literal["Employee", "Company"]


class ErrorOut(BaseModel):
    detail: str


# ---- auth / employees ----
class LoginIn(BaseModel):
    emp_code: str


class EmployeeOut(BaseModel):
    emp_code: str
    name: str
    email: str
    designation: str
    department: str
    cost_centre: str
    city: str
    reporting_manager_code: str | None
    role: str  # CSV value
    app_role: AppRole


# ---- shared building blocks ----
class Finding(BaseModel):
    rule_id: str
    severity: Severity
    message: str
    policy_ref: str | None = None
    line_id: int | None = None
    amount_paise: int | None = None


class ChainStepOut(BaseModel):
    seq: int
    level: Level
    approver_code: str
    approver_name: str
    note: str | None = None
    # filled only for persisted steps (not for chain previews)
    id: int | None = None
    status: StepStatus | None = None
    acted_at: datetime | None = None
    remarks: str | None = None


class SettlementSummary(BaseModel):
    gross_employee_paise: int
    company_memo_paise: int
    disallowed_paise: int
    net_paise: int
    advance_paise: int
    payable_paise: int
    recoverable_paise: int


class TimelineEvent(BaseModel):
    id: int
    entity_type: EntityType
    entity_id: str
    actor_code: str
    actor_name: str
    action: str
    from_status: str | None
    to_status: str | None
    remarks: str | None
    at: datetime


class ExpectedPayout(BaseModel):
    amount_paise: int
    run_date: Date
    estimated: bool  # true until the settlement is verified
    kind: Literal["payout", "recovery"]


class PaymentOut(BaseModel):
    id: int
    settlement_id: int
    kind: Literal["payout", "recovery"]
    amount_paise: int
    run_date: Date
    status: Literal["scheduled", "paid", "payroll_deduction"]
    paid_at: datetime | None
    # joined for the Finance "Payment runs" tab
    request_id: str | None = None
    emp_code: str | None = None
    emp_name: str | None = None


class StageInfo(BaseModel):
    """Stepper mapping (§5). step_index 0..5 = Travel request, Trip approval, Advance disbursement,
    Trip settlement, Finance review, Payout."""
    step_index: int
    step_label: str
    waiting_on_code: str | None = None
    waiting_on_name: str | None = None
    waiting_since: datetime | None = None


# ---- requests ----
class CostHeadIn(BaseModel):
    head: Head
    basis: str = ""
    estimate_paise: int = Field(ge=0)
    borne_by: PaidBy = "Employee"


class CostHeadOut(CostHeadIn):
    id: int


class RequestIn(BaseModel):
    purpose: str = ""
    visiting_place: str = ""
    visiting_company: str = ""
    from_date: Date | None = None
    to_date: Date | None = None
    destination_city: str = ""
    city_tier: int | None = None  # only needed for non-Tier-1 cities
    category: Literal["domestic", "international"] = "domestic"
    mode: str = ""
    advance_requested_paise: int = Field(default=0, ge=0)
    heads: list[CostHeadIn] = []


class AdvanceOut(BaseModel):
    id: int
    amount_paise: int
    reference: str
    disbursed_at: datetime
    disbursed_by: str
    disbursed_by_name: str


class RequestListItem(BaseModel):
    id: str
    emp_code: str
    emp_name: str
    purpose: str
    destination_city: str
    from_date: Date | None
    to_date: Date | None
    status: str
    estimate_total_paise: int
    advance_requested_paise: int
    revision: int
    created_at: datetime
    stage: StageInfo
    settlement_id: int | None = None
    settlement_status: str | None = None
    expected_payout: ExpectedPayout | None = None


class RequestOut(RequestListItem):
    visiting_place: str
    visiting_company: str
    city_tier: int | None
    category: str
    mode: str
    submitted_at: datetime | None
    heads: list[CostHeadOut]
    days: int | None
    advance_cap_paise: int
    advance: AdvanceOut | None
    chain: list[ChainStepOut]
    legacy_flags: list[str]  # "Migrated from email — issues found" banner
    settlement_summary: SettlementSummary | None
    timeline: list[TimelineEvent]


class RequestValidateOut(BaseModel):
    findings: list[Finding]
    advance_cap_paise: int
    chain_preview: list[ChainStepOut]
    estimate_total_paise: int
    days: int | None
    city_tier: int | None  # auto-detected for Tier 1 cities


# ---- settlements ----
class Attendee(BaseModel):
    name: str
    organisation: str


class ClaimLineIn(BaseModel):
    section: Section
    head: LineHead
    date: Date | None = None
    time: str | None = None
    description: str = ""
    merchant: str = ""
    bill_no: str | None = None
    from_place: str | None = None
    to_place: str | None = None
    city: str | None = None
    check_in: Date | None = None
    check_out: Date | None = None
    nights: int | None = None
    paid_by: PaidBy = "Employee"
    base_paise: int = Field(default=0, ge=0)
    tax_paise: int = Field(default=0, ge=0)
    evidence_id: int | None = None
    attendees: list[Attendee] = []
    prior_approval_ref: str | None = None


class ClaimLinePatch(BaseModel):
    """Every field optional; only the ones sent are changed."""
    section: Section | None = None
    head: LineHead | None = None
    date: Date | None = None
    time: str | None = None
    description: str | None = None
    merchant: str | None = None
    bill_no: str | None = None
    from_place: str | None = None
    to_place: str | None = None
    city: str | None = None
    check_in: Date | None = None
    check_out: Date | None = None
    nights: int | None = None
    paid_by: PaidBy | None = None
    base_paise: int | None = Field(default=None, ge=0)
    tax_paise: int | None = Field(default=None, ge=0)
    evidence_id: int | None = None
    attendees: list[Attendee] | None = None
    prior_approval_ref: str | None = None


class ClaimLineOut(BaseModel):
    id: int
    section: Section
    head: LineHead
    date: Date | None
    time: str | None
    description: str
    merchant: str
    bill_no: str | None
    from_place: str | None
    to_place: str | None
    city: str | None
    check_in: Date | None
    check_out: Date | None
    nights: int | None
    paid_by: PaidBy
    base_paise: int
    tax_paise: int
    amount_paise: int
    disallowed_paise: int
    disallow_reason: str | None
    policy_ref: str | None
    evidence_id: int | None
    attendees: list[Attendee]
    prior_approval_ref: str | None
    source: Literal["import", "manual"]


class EvidenceOut(BaseModel):
    id: int
    filename: str
    kind: Literal["email", "image"]
    parent_evidence_id: int | None
    email_date: datetime | None
    doc_type: str | None
    triage: Triage | None
    triage_reason: str | None
    policy_ref: str | None
    extracted: dict | None = None


class SettlementCreate(BaseModel):
    request_id: str


class ValidationResult(BaseModel):
    findings: list[Finding]
    summary: SettlementSummary
    chain_preview: list[ChainStepOut]
    rules_checked: int
    expected_payout: ExpectedPayout | None = None


class SettlementOut(BaseModel):
    id: int
    request_id: str
    emp_code: str
    emp_name: str
    status: str
    revision: int
    submitted_at: datetime | None
    trip: RequestListItem  # trip summary header + stepper
    lines: list[ClaimLineOut]
    evidence: list[EvidenceOut]
    findings: list[Finding]
    summary: SettlementSummary
    chain: list[ChainStepOut]  # persisted steps once submitted, else the preview
    rules_checked: int
    expected_payout: ExpectedPayout | None
    payments: list[PaymentOut]
    timeline: list[TimelineEvent]


class ImportResult(BaseModel):
    new_documents: int
    skipped_existing: int  # idempotent per sha256
    used: int
    excluded: int
    ignored: int
    lines_created: int
    evidence: list[EvidenceOut]


# ---- approvals / finance ----
class ActIn(BaseModel):
    action: Literal["approve", "return", "reject"]
    remarks: str | None = None  # required for return / reject


class ActOut(BaseModel):
    entity_type: EntityType
    entity_id: str
    status: str


class InboxItem(BaseModel):
    entity_type: EntityType
    entity_id: str  # TRQ id (request) or settlement id as text
    request_id: str
    settlement_id: int | None
    emp_code: str
    emp_name: str
    purpose: str
    amount_paise: int  # request estimate, or settlement net
    level: Level
    waiting_since: datetime | None
    flags_count: int  # WARN + BLOCK findings
    revision: int


class DisburseIn(BaseModel):
    amount_paise: int = Field(gt=0)


class FinanceQueue(BaseModel):
    advances_to_disburse: list[RequestListItem]
    settlements_to_verify: list[InboxItem]
    payments: list[PaymentOut]


class SubmitOut(BaseModel):
    entity_type: EntityType
    entity_id: str
    status: str
    chain: list[ChainStepOut]
