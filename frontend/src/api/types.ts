// TS mirror of backend/app/schemas.py — THE API CONTRACT. FROZEN after phase 1.
// Money = integer paise (never floats). Dates = ISO strings ("2026-06-16" / "2026-06-16T09:00:00").

export type AppRole = 'employee' | 'manager' | 'admin'
export type Severity = 'BLOCK' | 'DISALLOW' | 'WARN' | 'INFO'
export type Level = 'RM' | 'HOD' | 'HODIV' | 'MD' | 'FINANCE'
export type StepStatus = 'waiting' | 'pending' | 'approved' | 'returned' | 'rejected'
export type EntityType = 'request' | 'settlement'
export type Triage = 'used' | 'excluded' | 'ignored'
export type Head = 'air_rail' | 'lodging' | 'conveyance' | 'meals' | 'other'
export type LineHead = 'lodging' | 'cab' | 'air' | 'meals' | 'business_entertainment' | 'misc'
export type Section = 'lodging' | 'transport' | 'other'
export type PaidBy = 'Employee' | 'Company'

export interface ErrorOut {
  detail: string
}

// ---- auth / employees ----
export interface LoginIn {
  emp_code: string
}

export interface EmployeeOut {
  emp_code: string
  name: string
  email: string
  designation: string
  department: string
  cost_centre: string
  city: string
  reporting_manager_code: string | null
  role: string // CSV value
  app_role: AppRole
}

// ---- shared building blocks ----
export interface Finding {
  rule_id: string
  severity: Severity
  message: string
  policy_ref: string | null
  line_id: number | null
  amount_paise: number | null
}

export interface ChainStepOut {
  seq: number
  level: Level
  approver_code: string
  approver_name: string
  note: string | null
  // only for persisted steps (not chain previews)
  id: number | null
  status: StepStatus | null
  acted_at: string | null
  remarks: string | null
}

export interface SettlementSummary {
  gross_employee_paise: number
  company_memo_paise: number
  disallowed_paise: number
  net_paise: number
  advance_paise: number
  payable_paise: number
  recoverable_paise: number
}

export interface TimelineEvent {
  id: number
  entity_type: EntityType
  entity_id: string
  actor_code: string
  actor_name: string
  action: string
  from_status: string | null
  to_status: string | null
  remarks: string | null
  at: string
}

export interface ExpectedPayout {
  amount_paise: number
  run_date: string
  estimated: boolean // true until the settlement is verified
  kind: 'payout' | 'recovery'
}

export interface PaymentOut {
  id: number
  settlement_id: number
  kind: 'payout' | 'recovery'
  amount_paise: number
  run_date: string
  status: 'scheduled' | 'paid' | 'payroll_deduction'
  paid_at: string | null
  request_id: string | null
  emp_code: string | null
  emp_name: string | null
}

// step_index 0..5 = Travel request, Trip approval, Advance disbursement, Trip settlement, Finance review, Payout
export interface StageInfo {
  step_index: number
  step_label: string
  waiting_on_code: string | null
  waiting_on_name: string | null
  waiting_since: string | null
}

// ---- requests ----
export interface CostHeadIn {
  head: Head
  basis?: string
  estimate_paise: number
  borne_by?: PaidBy
}

export interface CostHeadOut {
  head: Head
  basis: string
  estimate_paise: number
  borne_by: PaidBy
  id: number
}

export interface RequestIn {
  purpose?: string
  visiting_place?: string
  visiting_company?: string
  from_date?: string | null
  to_date?: string | null
  destination_city?: string
  city_tier?: number | null // only needed for non-Tier-1 cities
  category?: 'domestic' | 'international'
  mode?: string
  advance_requested_paise?: number
  heads?: CostHeadIn[]
}

export interface AdvanceOut {
  id: number
  amount_paise: number
  reference: string
  disbursed_at: string
  disbursed_by: string
  disbursed_by_name: string
}

export interface RequestListItem {
  id: string
  emp_code: string
  emp_name: string
  purpose: string
  destination_city: string
  from_date: string | null
  to_date: string | null
  status: string
  estimate_total_paise: number
  advance_requested_paise: number
  revision: number
  created_at: string
  stage: StageInfo
  settlement_id: number | null
  settlement_status: string | null
  expected_payout: ExpectedPayout | null
}

export interface RequestOut extends RequestListItem {
  visiting_place: string
  visiting_company: string
  city_tier: number | null
  category: string
  mode: string
  submitted_at: string | null
  heads: CostHeadOut[]
  days: number | null
  advance_cap_paise: number
  advance: AdvanceOut | null
  chain: ChainStepOut[]
  legacy_flags: string[] // "Migrated from email — issues found" banner
  settlement_summary: SettlementSummary | null
  timeline: TimelineEvent[]
}

export interface RequestValidateOut {
  findings: Finding[]
  advance_cap_paise: number
  chain_preview: ChainStepOut[]
  estimate_total_paise: number
  days: number | null
  city_tier: number | null // auto-detected for Tier 1 cities
}

// ---- settlements ----
export interface Attendee {
  name: string
  organisation: string
}

export interface ClaimLineIn {
  section: Section
  head: LineHead
  date?: string | null
  time?: string | null
  description?: string
  merchant?: string
  bill_no?: string | null
  from_place?: string | null
  to_place?: string | null
  city?: string | null
  check_in?: string | null
  check_out?: string | null
  nights?: number | null
  paid_by?: PaidBy
  base_paise?: number
  tax_paise?: number
  evidence_id?: number | null
  attendees?: Attendee[]
  prior_approval_ref?: string | null
}

// Every field optional; only the ones sent are changed.
export type ClaimLinePatch = Partial<ClaimLineIn>

export interface ClaimLineOut {
  id: number
  section: Section
  head: LineHead
  date: string | null
  time: string | null
  description: string
  merchant: string
  bill_no: string | null
  from_place: string | null
  to_place: string | null
  city: string | null
  check_in: string | null
  check_out: string | null
  nights: number | null
  paid_by: PaidBy
  base_paise: number
  tax_paise: number
  amount_paise: number
  disallowed_paise: number
  disallow_reason: string | null
  policy_ref: string | null
  evidence_id: number | null
  attendees: Attendee[]
  prior_approval_ref: string | null
  source: 'import' | 'manual'
}

export interface EvidenceOut {
  id: number
  filename: string
  kind: 'email' | 'image'
  parent_evidence_id: number | null
  email_date: string | null
  doc_type: string | null
  triage: Triage | null
  triage_reason: string | null
  policy_ref: string | null
  extracted: Record<string, unknown> | null
}

export interface SettlementCreate {
  request_id: string
}

export interface ValidationResult {
  findings: Finding[]
  summary: SettlementSummary
  chain_preview: ChainStepOut[]
  rules_checked: number
  expected_payout: ExpectedPayout | null
}

export interface SettlementOut {
  id: number
  request_id: string
  emp_code: string
  emp_name: string
  status: string
  revision: number
  submitted_at: string | null
  trip: RequestListItem // trip summary header + stepper
  lines: ClaimLineOut[]
  evidence: EvidenceOut[]
  findings: Finding[]
  summary: SettlementSummary
  chain: ChainStepOut[] // persisted steps once submitted, else the preview
  rules_checked: number
  expected_payout: ExpectedPayout | null
  payments: PaymentOut[]
  timeline: TimelineEvent[]
}

export interface ImportResult {
  new_documents: number
  skipped_existing: number // idempotent per sha256
  used: number
  excluded: number
  ignored: number
  lines_created: number
  evidence: EvidenceOut[]
}

// ---- approvals / finance ----
export interface ActIn {
  action: 'approve' | 'return' | 'reject'
  remarks?: string | null // required for return / reject
}

export interface ActOut {
  entity_type: EntityType
  entity_id: string
  status: string
}

export interface InboxItem {
  entity_type: EntityType
  entity_id: string // TRQ id (request) or settlement id as text
  request_id: string
  settlement_id: number | null
  emp_code: string
  emp_name: string
  purpose: string
  amount_paise: number // request estimate, or settlement net
  level: Level
  waiting_since: string | null
  flags_count: number // WARN + BLOCK findings
  revision: number
}

export interface DisburseIn {
  amount_paise: number
}

export interface FinanceQueue {
  advances_to_disburse: RequestListItem[]
  settlements_to_verify: InboxItem[]
  payments: PaymentOut[]
}

export interface SubmitOut {
  entity_type: EntityType
  entity_id: string
  status: string
  chain: ChainStepOut[]
}
