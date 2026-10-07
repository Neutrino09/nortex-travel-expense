# CLAUDE.md — Nortex Travel Expense Reimbursement (take-home build)

You are building a working full-stack prototype for a take-home assignment. This file is the complete spec. Read it fully before doing anything. When this file and your own instincts disagree, this file wins. If something is truly ambiguous and blocks you, stop and ask the user. Don't invent requirements.

**Hard constraints**
- The total time budget, including the user's recording and write-up, is under 6 hours. The build gets about 3.5 hours. Prefer boring, obvious code over clever code.
- The reviewers will ask the author to explain any line. Keep functions small, name things after the policy, and add a short comment with the policy clause (e.g. `# policy §3.1`) wherever a rule is enforced.
- **Do not build anything in "Out of scope" (section 15).**
- Commit after every phase with a clear message. Run the tests before every commit.
- No skills are needed for this build. Don't load any unless you're blocked.

The reviewers said: *"We expect a basic, functional full-stack prototype with working employee, manager and admin roles and sensible validations. We're assessing critical thinking, technical foundations, how well you architect the application, review and test what you build."*

---

## 0. Repository layout and the input pack

The working directory is the assignment pack folder. When you start, it contains:

```
PROBLEM_STATEMENT.md
expense_policy.md
employee_master.csv
Travel_Expense_Forms_Template.xlsx
sample_emails/   (01_travel_approval_request.eml … 15_return_cab.eml — 15 files)
receipts/        (hotel_invoice_1188.png, dinner_bill_18jun.png)
CLAUDE.md        (this file)
```

**Phase 0 moves the pack into `pack/` with `git mv`, keeping the original file names.** The pack is read-only input: never edit those files. Target layout:

```
CLAUDE.md  README.md  NOTE.md  DEMO.md  .env.example  .gitignore
Dockerfile  docker-compose.yml
pack/                      # the original assignment files, untouched
backend/
  pyproject.toml           # or requirements.txt
  app/
    main.py                # FastAPI app, /api routers, static + SPA fallback
    config.py              # env settings (PACK_DIR, DATABASE_URL, APP_TODAY, keys)
    db.py                  # engine, session dependency, create_all
    models.py              # SQLModel tables (section 4)
    schemas.py             # Pydantic request/response models = THE API CONTRACT
    auth.py                # "log in as" session, current_user, role guards
    clock.py               # today() honours APP_TODAY
    money.py               # paise helpers, INR formatting, proration
    policy/
      config.py            # EVERY policy number/keyword lives here
      rules.py             # validation → list[Finding]; settlement summary
      chain.py             # approval chain builder
      payments.py          # payment run date, payout/recovery
    workflow.py            # state machines; the ONLY place statuses change; writes audit
    ingest/
      eml.py               # parse .eml, resolve attachments
      extract.py           # Claude extraction + sha256 cache
      triage.py            # deterministic used/excluded/ignored + line building
      folio.py             # split hotel invoice into lines
      build_cache.py       # CLI: extract the whole sample pack into fixtures
    routers/
      auth.py requests.py settlements.py approvals.py finance.py evidence.py
    seed.py
  fixtures/extractions/    # <sha256>.json cached LLM output for the pack (committed)
  tests/
    conftest.py test_chain.py test_rules.py test_payments.py
    test_workflow.py test_sample_pack.py test_api_smoke.py
frontend/
  package.json vite.config.ts index.html
  src/
    api/types.ts           # TS mirror of backend/app/schemas.py
    api/client.ts          # fetch wrapper + TanStack Query hooks
    components/            # Stepper, Timeline, FindingBadge, MoneyCell, ChainPreview, AppShell…
    pages/                 # Login, Dashboard, RequestNew, RequestDetail, SettlementEditor,
                           # ApprovalsInbox, ReviewItem, Finance
```

---

## 1. The problem

Nortex employees travel. Bookings, receipts, approvals and advance notices land in their inbox as text emails and photos of paper bills. Afterwards they spend 25–30 minutes hand-copying everything into an Excel Settlement Form. That's where the errors come from: duplicates, personal items, other people's bills, the wrong category. The form then goes up an approval chain and on to Finance, and the employee spends two weeks chasing Finance about the money.

The app must:
1. **Remove the 25 minutes:** import the inbox and propose a filled-in settlement claim.
2. **Remove the errors:** enforce the policy on every line, show exactly what was disallowed and why, and make blocking errors impossible to submit.
3. **Remove the follow-ups:** show every item's stage, who it's waiting on, and the expected payout amount and date.

### The architectural principle (repeat it in the note and the code comments)

> **The LLM proposes, deterministic Python decides, the human confirms.**

- The LLM is used **only** to extract structured fields from a document. It never decides policy.
- Every decision is plain, unit-tested Python: classification into used, excluded or ignored; allowed and disallowed amounts; duplicates; the approval chain; the payout date.
- The employee reviews and edits the proposed lines before submitting.
- Validation lives **only on the server**. The UI calls `/validate` and renders the findings. Never re-implement a rule in TypeScript.

---

## 2. Stack

- **Backend:** Python 3.12, FastAPI, SQLModel, SQLite, Starlette `SessionMiddleware` (needs `itsdangerous`), `python-multipart`, the official `openai` Python SDK, pytest and httpx.
- **Frontend:** Vite, React, TypeScript, Tailwind CSS, shadcn/ui (if the CLI prompts interactively, hand-write the few components needed: button, card, badge, table, input, select, textarea, dialog, tabs), `react-router-dom`, `@tanstack/react-query`, `lucide-react`.
- **Shipping:** one multi-stage Dockerfile. A node stage builds `frontend/dist`; the python stage copies it in, and FastAPI serves it at `/` with an SPA fallback and the API at `/api`. `docker compose up --build` must run the whole app on `http://localhost:8000`. The deploy target is Render (Docker web service, bind to `$PORT`).
- **Dev mode:** `uvicorn app.main:app --reload --port 8000` and `vite` on 5173, with a proxy from `/api` to 8000.
- **Money:** always **integer paise** (`int`). Never use floats for money, in Python or TypeScript. The UI formats it as `₹26,388.44` with Indian digit grouping (`en-IN`).
- **Dates:** ISO strings in the API; display as `16 Jun 2026`.

**Environment** (`.env.example`; never commit `.env`):

```
OPENAI_API_KEY=
OPENAI_MODEL=gpt-6-luna      # cheapest vision + structured-output model; gpt-6.1-sol if reads are poor
APP_TODAY=2026-06-22        # optional; freezes "today" so the June 2026 demo trip isn't late
SESSION_SECRET=change-me
DATABASE_URL=sqlite:///./data/app.db
PACK_DIR=../pack            # /app/pack inside Docker
```

If `OPENAI_API_KEY` or `OPENAI_MODEL` is empty, the app must still run fully. Cached extractions are used, and anything uncached falls back to manual entry.

---

## 3. Users and roles

Seed all 9 rows of `pack/employee_master.csv`. There are no passwords. Login is a **"Log in as" picker** (state this in the README and the note). Store `emp_code` in the signed session cookie. **All authorization is enforced on the server.**

| App role (UI label) | CSV `role` | People | Permissions |
|---|---|---|---|
| **Employee** | Employee | Chaitanya Reddy NX-4471, Deepa Nair NX-5182, Imran Qureshi NX-4490 | Create their own travel requests and settlements, import evidence, edit drafts and returned items, submit or resubmit, track status |
| **Manager** | Reporting Manager, Head of Department, Head of Division, MD | Suresh Iyer NX-2210, Meera Krishnan NX-1108, Arvind Rao NX-1002, Nandita Shah NX-1000 | Everything an Employee can do for themselves, plus act on items **where they are the current pending approver**: approve, return (remarks required) or reject (remarks required) |
| **Admin (Finance)** | Finance | Ravi Menon NX-3305, Kavitha Balan NX-3300 | Everything an Employee can do for themselves, plus: see all requests and claims, disburse advances, verify settlements (approve or return), manage payment runs (mark paid), read any audit trail |

**Invariants**, each enforced in `workflow.py` and each with a test:
- Nobody ever acts on their own request or claim. Return 403.
- Only the approver of the current `pending` step can act. Return 403.
- Finance never verifies their own claim.
- An illegal state transition returns 409.

---

## 4. Data model (`models.py`)

The **Travel Request ID** (`TRQ-2026-0001`, a zero-padded sequence) is the spine. Settlements, evidence, approvals, payments and audit all hang off it, and the UI always shows it.

```
Employee        emp_code PK, name, email, designation, department, cost_centre, city,
                reporting_manager_code (nullable FK), role (CSV value)

TravelRequest   id PK (TRQ-YYYY-NNNN), emp_code, purpose, visiting_place, visiting_company,
                from_date, to_date, destination_city, city_tier (1|2|3),
                category ("domestic"|"international"), mode,
                estimate_total_paise (computed = sum of heads; never typed by the user),
                advance_requested_paise, status, created_at, submitted_at,
                revision (int, default 1), legacy_flags_json (nullable)

RequestCostHead id, request_id, head ("air_rail"|"lodging"|"conveyance"|"meals"|"other"),
                basis, estimate_paise, borne_by ("Employee"|"Company")

Advance         id, request_id, amount_paise, reference (ADV/YYYY/NNNN), disbursed_at, disbursed_by

Settlement      id PK, request_id FK (one active settlement per request), emp_code, status,
                revision (int, default 1), submitted_at

ClaimLine       id, settlement_id, section ("lodging"|"transport"|"other"),
                head ("lodging"|"cab"|"air"|"meals"|"business_entertainment"|"misc"),
                date, time, description, merchant, bill_no,
                from_place, to_place, city, check_in, check_out, nights,
                paid_by ("Employee"|"Company"),
                base_paise, tax_paise, amount_paise (= base + tax),
                disallowed_paise (default 0), disallow_reason, policy_ref,
                evidence_id (FK; required to submit), fingerprint,
                attendees_json (list of {name, organisation}), prior_approval_ref,
                source ("import"|"manual")

Evidence        id, owner_emp_code, settlement_id (nullable), filename, kind ("email"|"image"),
                sha256 (unique per owner), storage_path, parent_evidence_id (attachment → email),
                email_date, extracted_json, doc_type,
                triage ("used"|"excluded"|"ignored"), triage_reason, policy_ref

ApprovalStep    id, entity_type ("request"|"settlement"), entity_id, revision, seq,
                level ("RM"|"HOD"|"HODIV"|"MD"|"FINANCE"), approver_code,
                status ("waiting"|"pending"|"approved"|"returned"|"rejected"),
                acted_at, remarks, note (e.g. "No HoD above claimant — escalated to Head of Division")

Payment         id, settlement_id, kind ("payout"|"recovery"), amount_paise, run_date,
                status ("scheduled"|"paid"|"payroll_deduction"), paid_at

AuditEvent      id, entity_type, entity_id, actor_code, action, from_status, to_status,
                remarks, at   — APPEND-ONLY. Never update or delete.
```

---

## 5. State machines (`workflow.py`)

There is a single entry point:

```
transition(session, entity, action, actor, remarks=None)
```

It checks the allowed-transitions table and the invariants in section 3, changes the status, updates the approval steps (it marks the next `waiting` step as `pending`), and writes an `AuditEvent`. Routers never assign `status` directly. Remarks are required for `return` and `reject`.

**TravelRequest**

```
draft --submit--> pending_approval
pending_approval --approve(last business step)--> approved
pending_approval --return--> returned --resubmit--> pending_approval   (same TRQ id, revision+1, chain rebuilt)
pending_approval --reject--> rejected (terminal)
approved --disburse_advance(Finance)--> advance_paid                   (only if advance > 0)
```

The approval chain for a request covers **business approvers only**: RM, HOD, HODIV and MD. Finance's role at this stage is to disburse the advance.

**Settlement**

```
draft --submit--> pending_approval              (blocked if any BLOCK finding exists)
pending_approval --approve(last business step)--> finance_review
finance_review --approve(Finance = verify)--> verified    → creates Payment (section 8)
pending_approval|finance_review --return--> returned --resubmit--> pending_approval
                                            (revision+1, chain rebuilt from level 1 on the new amount)
pending_approval|finance_review --reject--> rejected (terminal; the full advance becomes recoverable → recovery Payment)
verified --mark_paid(Finance)--> paid
```

A settlement can only be created for a request in `approved` or `advance_paid`.

**Stepper mapping (UI).** The steps are: Travel request → Trip approval → Advance disbursement → Trip settlement → Finance review → Payout. Map each status onto the step that's active:

| Status | Active step |
|---|---|
| Request `draft` / `returned` | Travel request |
| Request `pending_approval` | Trip approval |
| Request `approved` with advance > 0 | Advance disbursement |
| Request `advance_paid`, or no advance; settlement `draft` / `returned` / `pending_approval` | Trip settlement |
| Settlement `finance_review` | Finance review |
| Settlement `verified` / `paid` | Payout |

---

## 6. Approval chain (`policy/chain.py`)

```python
build_chain(claimant: Employee, value_paise: int, international: bool,
            force_hod: bool, include_finance: bool, employees: dict) -> list[StepSpec]
```

1. **Required levels** (policy §2): `RM` always; add `HOD` if value > ₹25,000; add `HODIV` if > ₹75,000; add `MD` if > ₹2,00,000 **or** international. `force_hod=True` adds `HOD` (used for a business-entertainment line above ₹2,000, §3.5).
2. `ancestors` = the claimant's reporting line, going upwards.
3. The `RM` approver is the direct reporting manager. For HOD, HODIV and MD, take the first ancestor whose CSV role matches. **If no ancestor has that role, escalate** to the first ancestor holding a higher role (rank RM < HOD < HODIV < MD) and record a `note`. If nobody is above, skip the level with a note. The claimant never appears (§2.2).
4. Collapse consecutive duplicate approvers into one step, and merge their notes.
5. If `include_finance` is set, append `FINANCE`: Ravi NX-3305, or Kavitha NX-3300 when the claimant is Ravi. Finance always comes **after** the business approvals (§2.1). Note that the xlsx template lists Finance before MD; we follow the policy, and the note says so.

**Value used:** for a request, `estimate_total_paise` (all heads, including those the company pays). For a settlement, the **net reimbursable claim** (see the summary in section 7).

**Expected chains.** Each row is a test case in `test_chain.py`:

| Claimant | Input | Chain |
|---|---|---|
| Chaitanya | settlement ₹26,388.44 | Suresh → Meera → Ravi |
| Chaitanya | settlement ₹24,133.44 | Suresh → Ravi |
| Chaitanya | settlement ₹80,000 | Suresh → Meera → Arvind → Ravi |
| Chaitanya | international, ₹10,000 | Suresh → Meera → Arvind → Nandita → Ravi |
| Chaitanya | ₹20,000 + entertainment line ₹2,255 (force_hod) | Suresh → Meera → Ravi |
| Suresh | ₹30,000 | Meera → Ravi (Meera is both RM and first HoD, collapsed) |
| Ravi | ₹30,000 | Kavitha (RM) → Arvind (no HoD above, escalated) → Kavitha (Finance) |
| Nandita | ₹5,000 | Ravi only (nobody above the MD; a known limitation in the note) |
| Chaitanya | request ₹43,500, domestic | Suresh → Meera (no Finance step on requests) |

---

## 7. Policy rules (`policy/config.py`, `policy/rules.py`)

All constants go in `policy/config.py`: tier caps, the Tier 1 city list with aliases, matrix thresholds, the 60% advance ratio, the ₹2,000 entertainment threshold, the 7-day window, payment-run days (10, 25), non-reimbursable keywords and alcohol keywords.

```python
Finding(rule_id, severity: "BLOCK"|"DISALLOW"|"WARN"|"INFO", message, policy_ref, line_id | None, amount_paise | None)
```

- **BLOCK** means you can't submit.
- **DISALLOW** sets the line's `disallowed_paise` and `disallow_reason`. The line stays visible and is never deleted (§3.1 and the template legend).
- **WARN** is shown to the employee and every approver.

### Request rules

| ID | Rule | Severity | Ref |
|---|---|---|---|
| RQ-ADV | advance ≤ 60% of the sum of `borne_by=Employee` heads. Show the cap live in the form | BLOCK | §1.2 |
| RQ-DATES | from ≤ to; days = inclusive count | BLOCK | — |
| RQ-TIER | Tier 1 is set automatically for Bengaluru/Bangalore, Mumbai, Delhi/New Delhi/Gurugram/Gurgaon/Noida (Delhi NCR), Hyderabad, Chennai, Pune, Kolkata. Any other city requires the user to pick Tier 2 or Tier 3, because the policy has no Tier 2 list | BLOCK if unset | §3.1 |
| RQ-HEADS | at least one cost head; estimates ≥ 0 | BLOCK | — |

### Settlement line rules

| ID | Rule | Severity | Ref |
|---|---|---|---|
| R-PROOF | every line has `evidence_id` | BLOCK | §5.2 |
| R-DUP | fingerprint collides with another line (any employee, any settlement that isn't rejected). Fingerprint = `norm(merchant) + bill_no` when `bill_no` exists, otherwise `norm(merchant) + date + time + amount` (**Uber receipts have no bill number**) | BLOCK | §5.3 |
| R-LODGE | `base_paise / nights` > tier cap (₹6,000 / ₹4,000 / ₹2,800): disallow `(tariff − cap) × nights`. Taxes on the room tariff are reimbursed in full | DISALLOW | §3.1 |
| R-NONREIMB | description matches laundry, mini bar/minibar, spa, gym, in-room entertainment, movie, personal phone/data, fine, penalty, challan, travel insurance: disallow 100% (base + its tax) | DISALLOW | §4 |
| R-ALCOHOL | alcohol keywords (beer, wine, whisky, vodka, rum, liquor, alcohol, bar) are 100% disallowed **unless** `head = business_entertainment` | DISALLOW | §4 |
| R-MEAL | for each date, add up the `meals` lines. Anything over the cap (Tier 1 ₹1,500; otherwise ₹1,000) is disallowed on the last line of that date. Travel days count as full days. Entertainment isn't a meal | DISALLOW | §3.3 |
| R-AIR | `head=air` with `paid_by=Employee` is disallowed 100% ("flights are booked and billed through the travel desk") | DISALLOW | §3.2 |
| R-COMPANY | `paid_by=Company` lines are memo only, never reimbursed and not counted as disallowed | INFO | template legend |
| R-ENT-ATT | `business_entertainment` needs ≥1 attendee with a name **and** an organisation | BLOCK | §3.5 |
| R-ENT-HOD | `business_entertainment` above ₹2,000 forces HoD into the chain; WARN if `prior_approval_ref` is empty | WARN | §3.5 |
| R-WINDOW | line date outside `from_date − 1` to `to_date + 1` | WARN | — |
| R-LATE | `today() > to_date + 7 days` at submit time | WARN (visible to approvers) | §5.1 |
| R-EMPTY | the settlement has no lines | BLOCK | — |

### Settlement summary

This mirrors rows 44–50 of the xlsx. Exactly one of payable or recoverable is non-zero.

```
gross_employee = Σ amount of Employee lines
company_memo   = Σ amount of Company lines
disallowed     = Σ disallowed of Employee lines
net            = gross_employee − disallowed          ← "claimed value" for the approval matrix
advance        = disbursed advance (0 if none)
payable        = max(net − advance, 0)
recoverable    = max(advance − net, 0)
```

`POST /api/settlements/{id}/validate` re-runs every rule, saves the disallowed amounts, and returns `{findings, summary, chain_preview, rules_checked: N}`. The UI shows "Checked live against N policy rules" and calls validate (debounced by 400 ms) after every edit.

---

## 8. Payments (`policy/payments.py`)

- `next_payment_run(d)` returns the first 10th or 25th **on or after** `d`, rolling into the next month or year. Tests:

| `d` | Result |
|---|---|
| 9 Jun | 10 Jun |
| 10 Jun | 10 Jun |
| 11 Jun | 25 Jun |
| 26 Jun | 10 Jul |
| 26 Dec 2026 | 10 Jan 2027 |

- On `verified`: if `payable > 0`, create a `payout` for `next_payment_run(today)` with status `scheduled`. If `recoverable > 0`, create a `recovery` with status `payroll_deduction` ("deducted in the next payroll cycle", §1.3).
- On `rejected` (settlement): create a `recovery` for the full advance.
- From submit onwards, every settlement shows **"Expected payout: ₹X on <date>"**. Before verification, label it "estimated".

---

## 9. Ingestion: the headline feature

**Endpoints**
- `POST /api/settlements/{id}/import` (multipart; accepts `.eml`, `.png`, `.jpg`, `.jpeg`)
- `POST /api/settlements/{id}/import-sample` (loads every file in `pack/sample_emails/`, resolving attachments from `pack/receipts/`)

Both endpoints are idempotent per sha256: re-importing the same file doesn't create a second evidence record.

### Step 1: `eml.py`

Parse with the stdlib `email` package (`policy=email.policy.default`). Capture From, To, Subject, Date and the plain-text body. Image attachments become **separate evidence** linked by `parent_evidence_id`. The pack's attachment parts contain the placeholder text `[ATTACHMENT: see receipts/<name> in this pack]`. When an attachment can't be decoded as an image, read `filename` from Content-Disposition and load `PACK_DIR/receipts/<filename>`. **Sort all documents by email Date**, so the original is processed before a resend.

### Step 2: `extract.py`

For each document, look up `backend/fixtures/extractions/<sha256>.json`. On a miss, call OpenAI (`OPENAI_MODEL`) with the official `openai` SDK using **Structured Outputs**: Chat Completions with `response_format={"type":"json_schema","json_schema":{"name":"record_document","strict":true,"schema":<schema below>}}` and `temperature=0` (drop `temperature` if the model rejects it). Send the email text as a text part, or the image as an `image_url` part with a `data:image/png;base64,...` URL. Strict mode requires every property to be listed in `required` and `additionalProperties: false` on every object; express optional fields as nullable types (e.g. `["string","null"]`). Parse `message.content` as JSON, validate it with a Pydantic model, and save it to the cache dir. If the installed SDK version rejects this call shape, check the current OpenAI docs and use the equivalent structured-output call. Don't fall back to free-form JSON parsing.

The `record_document` JSON schema has these fields:

| Field | Values |
|---|---|
| `doc_type` | enum: `receipt`, `tax_invoice`, `booking_confirmation`, `payment_failed`, `travel_approval`, `advance_notice`, `promotional`, `other` |
| `merchant` | string\|null |
| `bill_no` | string\|null |
| `date` | YYYY-MM-DD\|null |
| `time` | HH:MM\|null |
| `currency` | string\|null |
| `total` | number\|null |
| `payment_method` | enum: `personal_card`, `corporate_card`, `pay_at_property`, `cash`, `unknown` |
| `person_name` | string\|null (guest / rider / passenger the bill is for) |
| `is_forwarded` | bool |
| `forwarded_by` | string\|null |
| `from_place`, `to_place` | string\|null |
| `check_in`, `check_out` | YYYY-MM-DD\|null |
| `nights`, `covers` | int\|null |
| `line_items` | [{date\|null, description, amount}] |
| `taxes` | [{label, rate_pct, amount}] |
| `context_note` | string\|null (useful free text, e.g. "Dinner with Vertex procurement team, 4 people") |

The system prompt says: *"Extract only what is visible. Do not apply any expense policy. Use null when unsure. Amounts are numbers in rupees."* Convert to paise immediately after extraction.

With no key and no cache hit, set the evidence to `ignored` with the reason "Extraction unavailable — add the line manually".

`build_cache.py` (`python -m app.ingest.build_cache`) extracts every pack document into `backend/fixtures/extractions/`. **The user runs this once with a real key after phase 4, then the files are committed.** Tests and the demo then never call the network.

### Step 3: `triage.py`

The rules below are deterministic and applied in order. The **first match wins**. Every outcome stores a human-readable reason and a policy reference.

**Email + attachment pairs.** If an email has an image attachment, the **attachment is the primary proof**. The email body is used only for `context_note` and to cross-check totals, and the body evidence is marked `used` with the reason "Covering email for <attachment>". It is never a duplicate.

1. `promotional` / `other` → **ignored**: "Not an expense document".
2. `travel_approval` / `advance_notice` → **ignored**: "Reference only — request and advance are tracked in the app".
3. `booking_confirmation` → **excluded**: "Booking voucher, not a bill; the tax invoice is the proof" (§5.2). Keep its tariff for the folio cross-check.
4. `payment_failed` → **excluded**: "Payment failed — nothing was paid" (§5.2).
5. `person_name` doesn't match the claimant's first or full name (case-insensitive), **or** the document was forwarded by another employee about their own expense → **excluded**: "Expense of another person (<name>)" (§4).
6. Fingerprint already used by an earlier document → **excluded**: "Duplicate of <filename>" (§5.3).
7. `payment_method = corporate_card` → **used**. Create `paid_by=Company` memo lines; an airline ticket becomes `head=air` in the transport section, one line per sector.
8. `tax_invoice` from a hotel or lodging merchant → **used** through `folio.py`.
9. Restaurant or food receipt where `covers > 1`, or the context mentions a customer, client, team or "dinner with" → **used** as `business_entertainment` in section `other`. Attendees start empty, which triggers R-ENT-ATT. Put the context_note in the description.
10. Cab or ride receipt → **used**: `section=transport, head=cab`, with date, time, from and to.
11. Anything else with an amount → **used** as `other/misc`, with a WARN "Review category".

### Step 4: `folio.py`

Split the hotel invoice by item:
- **Room charges** become one `lodging` line, with nights, check-in/out, city and `base = Σ room charges`.
- **In-room dining or restaurant** becomes a `meals` line dated on its item date.
- **Laundry, mini bar and similar** each become their own line, and R-NONREIMB disallows them fully.

Spread the invoice tax rate (CGST + SGST %) onto every item: `tax = round(base × rate)`. Put any rounding difference on the lodging line, so the lines add up **exactly** to the invoice total.

**Reconciliation.** In the pack, the folio image has a fold across the 17-Jun room line. If the image's room items don't add up to the subtotal, use the email body's aggregated figures. Cross-check against the booking voucher's tariff (₹5,750 × 3 = ₹17,250). Record which source won in the line description.

### Golden test (`test_sample_pack.py`): this must pass

Setup: the seeded TRQ-2026-0001, with the advance of ₹20,000 disbursed, Tier 1 Bengaluru, 16–20 Jun 2026. Import the sample pack using cached extractions. Expected result:

| Email / file | Triage | Line(s) |
|---|---|---|
| 01_travel_approval_request | ignored | — |
| 02_travel_approval_granted | ignored | — |
| 03_advance_disbursed | ignored | — |
| 04_flight_eticket | used | 2 × air, **Company**: ₹5,016.00 + ₹5,540.00 = memo ₹10,556.00 |
| 05_hotel_voucher | excluded (booking, not a bill) | — |
| 06_uber_receipt_1 | used | cab 16 Jun Baner → PNQ ₹1,415.02 |
| 07_uber_receipt_2 | used | cab 16 Jun BLR → Keys Prime ₹743.00 |
| 08_uber_payment_failed | excluded (payment failed) | — |
| 09_uber_receipt_3 | used | cab 17 Jun Vertex → Keys Prime ₹172.00 |
| 10_uber_receipt_3_resend | excluded (duplicate of 09) | — |
| 11_dinner_bill + dinner_bill_18jun.png | used | business_entertainment 18 Jun, Spice Terrace bill 4471, ₹2,255.00. **BLOCK** until attendees are added; WARN for prior approval; forces HoD |
| 12_hotel_invoice + hotel_invoice_1188.png | used | lodging ₹19,320.00 (17,250 + 2,070); meals 18 Jun ₹1,254.40 (1,120 + 134.40); laundry ₹504.00 **disallowed**; minibar ₹425.60 **disallowed** |
| 13_colleague_forward | excluded (Deepa Nair's expense) | — |
| 14_promo_noise | ignored | — |
| 15_return_cab | used | cab 20 Jun PNQ → Baner ₹1,229.02 |

Expected summary: gross_employee **₹27,318.04**, disallowed **₹929.60**, net **₹26,388.44**, advance **₹20,000.00**, payable **₹6,388.44**, recoverable **₹0**, company memo **₹10,556.00**, chain **Suresh → Meera → Ravi**.

After attendees are added and the settlement is submitted, the full flow must work: Suresh approves, Meera approves, Ravi verifies, and a payout of ₹6,388.44 is created for `next_payment_run(APP_TODAY)` (with APP_TODAY = 22 Jun 2026, that's 25 Jun 2026). Cover this in `test_api_smoke.py` through the HTTP API.

---

## 10. Seed data (`seed.py`: runs at startup only when the DB is empty)

1. Seed all 9 employees from the CSV.
2. Seed **TRQ-2026-0001** for Chaitanya to match the xlsx example:
   - Bengaluru / Vertex Technologies, purpose "Customer meeting + site visit", 16–20 Jun 2026, domestic, Tier 1, mode Flight.
   - Cost heads: air_rail ₹10,500 **Company**; lodging ₹23,000 **Employee** (the voucher says "Pay at Hotel" and the folio was settled on his personal card); conveyance ₹4,000 Employee; meals ₹6,000 Employee. Total ₹43,500. Advance requested ₹20,000.
   - Status `advance_paid`. Advance `ADV/2026/0619`, ₹20,000, disbursed 10 Jun 2026 by Ravi.
   - Approval steps: Suresh approved on 8 Jun with the remark "Approved. Keep hotel within 6000/night."
   - Audit events: submitted 8 Jun; approved by Suresh 8 Jun; advance disbursed 10 Jun.
   - `legacy_flags_json` holds two findings, shown as a "Migrated from email — issues found" banner on the request page:
     - "Advance ₹20,000 exceeds the 60% cap of ₹19,800 (§1.2)."
     - "Estimate above ₹25,000 needed Head of Department approval (§2); only the Reporting Manager approved by email. The email also states ₹48,000 while the form totals ₹43,500."
3. Create an empty **draft settlement** for TRQ-2026-0001.

---

## 11. API contract (`schemas.py`, mirrored exactly in `frontend/src/api/types.ts`)

Everything lives under `/api` and speaks JSON. Errors use the shape `{detail: string}`: 400 validation, 401 not logged in, 403 not allowed, 404 not found, 409 illegal transition.

```
POST /auth/login {emp_code}       GET /auth/me        POST /auth/logout
GET  /employees                   # login picker; includes app_role: employee|manager|admin

GET  /requests                    # mine; Finance gets all
POST /requests                    # draft
GET  /requests/{id}               # request + heads + chain + advance + settlement summary + timeline
PATCH /requests/{id}              # draft/returned only
POST /requests/{id}/validate      # {findings, advance_cap_paise, chain_preview}
POST /requests/{id}/submit        POST /requests/{id}/resubmit

POST /settlements {request_id}
GET  /settlements/{id}            # lines, evidence (with triage), findings, summary, chain, payment, timeline
POST /settlements/{id}/lines      PATCH /settlements/{id}/lines/{line_id}    DELETE …/lines/{line_id}
POST /settlements/{id}/import     POST /settlements/{id}/import-sample
POST /settlements/{id}/validate   POST /settlements/{id}/submit    POST /settlements/{id}/resubmit

GET  /evidence/{id}               GET /evidence/{id}/file   # owner, current approver, or Finance only

GET  /approvals/inbox             # items where I am the current pending approver
POST /approvals/{entity_type}/{id}/act {action: approve|return|reject, remarks?}

GET  /finance/queue               # {advances_to_disburse, settlements_to_verify, payments}
POST /finance/requests/{id}/disburse-advance {amount_paise}
POST /finance/payments/{id}/mark-paid

GET  /audit?entity_type=&entity_id=
```

---

## 12. Frontend

Visual reference: the demo screenshot the user has. It shows a left sidebar, a top bar with the user's name and avatar initials, and a chip such as "● You're viewing your own claims". Pages use clean white cards, a green primary colour and a horizontal 6-step stepper headed "What happens after you submit" with "You are here" under the current step. Keep it clean; don't polish beyond that.

**AppShell**
- The sidebar shows Dashboard and Claims for everyone, plus **Approvals** (with a count badge) for managers and **Finance** for admins.
- The top bar shows the user's name, a role chip (Employee / Manager / Admin · Finance) and a "Switch user" button that goes back to the login picker.

Build the screens in this order:

1. **Login.** Cards for the 9 people, grouped as Employee / Manager / Admin. Each shows designation and department, and one click logs in.
2. **Settlement editor** (`/settlements/:id`). This is the most important screen.
   - Header: the TRQ ID, trip summary, stepper and "Checked live against N policy rules".
   - **Import panel:** a "Load sample inbox" button and a drop zone. Below it, a list of every document with a badge (Used = green, Excluded = red, Ignored = grey), the reason, the policy clause, and a click-through to view the email text or image.
   - **Lines** grouped under Lodging / Travel & Transportation / Other Expenses, using the xlsx columns: Date, Time, Description/From→To/Hotel, Head, Paid By, Amount, Disallowed (struck-through grey with the reason as a tooltip), Proof Ref (links to the evidence). Lines are editable inline, there's an "Add line" button, and the entertainment row has an attendee editor.
   - Findings appear inline on each line: red BLOCK, amber WARN.
   - A sticky **summary card** shows gross, company memo, disallowed, net, advance, and payable *or* recoverable. Below it: the chain preview with names, the expected payout date, and a Submit button that's disabled while any BLOCK exists (with a tooltip listing the blockers).
3. **Approvals inbox and review page.** The inbox is a table: TRQ, employee, amount, waiting since, flags count. The review page shows, in order: summary, findings (WARNs highlighted), lines with evidence viewer, timeline. Actions are Approve / Return / Reject; Return and Reject open a dialog where remarks are required.
4. **Finance.** Three tabs: *Advances to disburse* (one-click disburse), *Claims to verify* (opens the review page with a Verify action), and *Payment runs* (grouped by run date, showing payouts and recoveries, with Mark paid).
5. **Dashboard.** One card per TRQ showing stage, "Waiting on <name> since <n> days", and the expected payout. This is the "where's my money" answer. It also has a "New travel request" button.
6. **New travel request / request detail.**
   - The form follows the xlsx Travel Request Form: dates, auto day count, destination with auto tier, purpose, visiting company, mode, category, and a cost-heads table with Borne By.
   - The total is computed, and the advance field shows the live 60% cap.
   - A live chain preview, then Submit.
   - The detail page shows the stepper, the legacy banner, the advance, a "Start settlement" button and the timeline.
7. **Timeline component.** The audit events listed vertically: actor, action, remarks, relative time.

All server state goes through TanStack Query hooks in `api/client.ts`. Invalidate the query after every mutation. Show loading and error states (a toast on error, using the `detail` string).

---

## 13. Tests (pytest). Spend the testing effort here, not on UI tests.

- `test_chain.py`: every row of the table in section 6.
- `test_rules.py`:
  - advance cap: ₹20,000 vs a ₹19,800 cap → BLOCK; ₹19,800 → OK
  - lodging over the cap (Tier 2 at ₹4,500 × 2 nights → ₹1,000 disallowed; tax untouched)
  - meals per-day cap
  - non-reimbursable split with prorated tax
  - duplicate with no bill number (merchant + date + time + amount)
  - alcohol allowed only in entertainment
  - entertainment with no attendees → BLOCK
  - late warning driven by APP_TODAY
  - employee-paid air → disallowed
  - summary arithmetic, including the recovery case (net ₹15,000 against a ₹20,000 advance → recoverable ₹5,000, payable 0)
- `test_payments.py`: the dates in section 8.
- `test_workflow.py`:
  - illegal transition → 409
  - out-of-turn approver → 403
  - self-approval impossible
  - return then resubmit keeps the TRQ ID, bumps the revision and rebuilds the chain on the new amount
  - reject creates a full-advance recovery
  - submit blocked while a BLOCK finding exists
- `test_sample_pack.py`: the golden table in section 9, offline.
- `test_api_smoke.py`: the full happy path from section 9 over HTTP with `TestClient`, switching users through `/auth/login`.

---

## 14. Build plan: phases, parallel agents, checkpoints

Use the Agent/Task tool for parallel work exactly where marked. **Launch the parallel subagents in a single message so they run concurrently.** Each subagent owns a disjoint set of files and must not edit anything outside it. If a subagent needs a contract change in `models.py` or `schemas.py`, it reports that back instead of editing. You, the main agent, merge, run the full test suite, fix integration issues and commit.

### Phase 0: repo setup (main agent, ~5 min)

1. `git init` and create `.gitignore` (Python, Node, `.env`, `data/`, `backend/.cache/`, `node_modules/`, `frontend/dist/`).
2. `mkdir pack`, then `git mv` (or `mv`, before the first commit) PROBLEM_STATEMENT.md, expense_policy.md, employee_master.csv, Travel_Expense_Forms_Template.xlsx, sample_emails/ and receipts/ into `pack/`. Leave CLAUDE.md at the root.
3. Create `.env.example` (section 2).
4. Commit: `chore: repo layout and assignment pack`.

### Phase 1: skeleton and contract freeze (main agent, ~30 min, sequential)

1. Backend: `pyproject.toml`/`requirements.txt`, `config.py`, `db.py`, `clock.py`, `money.py`, all of `models.py`, all of `schemas.py`, `auth.py`, `seed.py` (section 10), and `main.py` with every router from section 11 mounted. Implement the auth and employees endpoints fully. Every other endpoint is a stub that raises `NotImplementedError` with its final signature and response model.
2. Frontend: scaffold Vite + React + TS + Tailwind + shadcn + router + TanStack Query, plus the dev proxy. Write `src/api/types.ts` mirroring `schemas.py` exactly, and `src/api/client.ts` with typed hooks for every endpoint.
3. Tests: `conftest.py` (temp SQLite, APP_TODAY=2026-06-22, seeded DB, a `login_as` helper) and a test that the seed loads 9 employees plus TRQ-2026-0001.
4. Checkpoint: `pytest` is green; `uvicorn` starts; `npm run build` succeeds.
5. Commit: `feat: skeleton, data model, API contract, seed`.

**`models.py`, `schemas.py` and `types.ts` are now FROZEN.** Only the main agent changes them.

### Phase 2: three parallel subagents (~60–75 min wall clock)

Launch all three in one message. Give each one: "Read CLAUDE.md sections 1–13. You own ONLY these files: … Do not modify any other file. Run your tests. Report what you built, any deviations, and any contract change you need."

- **Agent A — policy and workflow.** Owns `backend/app/policy/**`, `backend/app/workflow.py`, `backend/app/routers/{requests,settlements,approvals,finance,evidence}.py` (everything **except** the import endpoints, which stay stubs for Agent B to fill), `tests/test_chain.py`, `tests/test_rules.py`, `tests/test_payments.py`, `tests/test_workflow.py`. Implements sections 5–8 and 11.
- **Agent B — ingestion.** Owns `backend/app/ingest/**`, `backend/fixtures/extractions/**`, `tests/test_sample_pack.py`, and an `import_router.py` that `main.py` will mount for the two import endpoints. Implements section 9. Where it needs summary or rule output, it imports `app.policy.rules` by the function names defined in this file (`validate_settlement(session, settlement) -> ValidationResult`, `summarize(lines, advance_paise) -> Summary`). The golden test may stay red until Agent A lands; that's expected. It must also write a minimal set of hand-checked fixture files for the sample pack, marked with `"_source": "handwritten-fixture"`, so the golden test runs before the real cache is built. `build_cache` later overwrites them with real model output.
- **Agent C — frontend.** Owns `frontend/**` except `src/api/types.ts` (read-only). Builds the screens in section 12 in the order given, against the frozen types. Runs `npm run build` and `npx tsc --noEmit` and must keep both clean.

### Phase 3: integration (main agent, ~30 min)

1. Mount Agent B's import router. Resolve any contract requests from the agents (update `schemas.py` and `types.ts` together).
2. Write `test_api_smoke.py`. Run the **full** suite and make it green, including the golden test.
3. Run backend and frontend together. Click through the demo path in section 16 yourself (Playwright or careful manual checks via curl) and fix what's broken.
4. Commit: `feat: end-to-end flow working`.
5. **Tell the user:** "Run `python -m app.ingest.build_cache` from `backend/` with OPENAI_API_KEY and OPENAI_MODEL set, then tell me." After they do, re-run the golden test against the real cache. If the real extraction differs (e.g. the folded folio line), fix the deterministic reconciliation in `folio.py`/`triage.py`. **Never change the expected numbers.** Commit the cache.

### Phase 4: ship (main agent, ~20 min)

1. Multi-stage `Dockerfile`, then `docker-compose.yml` (port 8000, env from `.env`, a volume for `data/`). Verify that `docker compose up --build` serves the UI and that the API works.
2. `README.md`: what it is, one-command run, demo users table, env vars, how to run the tests, the architecture in five lines, and the known limitations.
3. Render deploy notes: Docker web service, set env vars including `APP_TODAY=2026-06-22`, uvicorn bound to `$PORT`. On the free plan the SQLite file resets on redeploy and the app re-seeds on boot; say so.
4. Commit: `chore: docker, readme, deploy`.

### Phase 5: write-ups (main agent, ~10 min, drafts for the user to edit)

1. **`NOTE.md`**, one page and no more, with these headings:
   - **What I understood the problem to be:** the three costs and the principle.
   - **Assumptions and decisions:** take them from section 17.
   - **What I built:** a short list.
   - **What I deliberately left out:** section 15.
   - **Where it breaks:** section 18.

   Plain, honest, first person.
2. **`DEMO.md`**: the 3–5 minute recording script from section 16, with what to click and what to say.
3. Commit: `docs: note and demo script`.

If time runs short, cut from the end of the frontend list (simplify the request form; make the timeline a plain list). **Never cut from the policy, workflow, ingestion or tests.**

---

## 15. Out of scope (do not build; the note lists these)

Real mailbox or Gmail connection (we use upload or the sample pack), passwords/SSO/JWT refresh, email/push notifications, a policy-editing UI (policy lives in `policy/config.py`), multi-currency or FX, payroll or bank integration, Postgres or migrations tooling, OCR without an LLM, a PDF export of the form, mobile polish, dark mode, global search, the HoD prior-approval workflow for entertainment (captured as a reference field and a warning only), and multiple settlements per request.

---

## 16. Demo path (what the recording shows; Phase 3 must make it work)

1. Log in as **Chaitanya** (Employee). The dashboard shows TRQ-2026-0001 at "Trip settlement", with the legacy-issues banner (the advance was over the cap and HoD approval was missing, both of which the app would have caught).
2. Open the settlement and click **Load sample inbox**. 15 emails and 2 receipts are triaged in seconds. Walk through the traps: duplicate Uber, failed payment, voucher vs invoice, Deepa's ride, the promo email, company-paid flights, and the hotel folio split with laundry and minibar disallowed rather than dropped.
3. The summary shows net ₹26,388.44, payable ₹6,388.44, and the chain Suresh → Meera → Ravi. Submit is blocked: the dinner needs attendees. Add 4 attendees from Vertex Technologies, and Submit.
4. Switch to **Suresh** (Manager). In his inbox, return the claim with a remark, to show the return loop. Switch back to Chaitanya, see the remark, and resubmit (same TRQ ID). Switch to Suresh and approve, then **Meera** approves (she's required because the claim is over ₹25k and the entertainment is over ₹2k).
5. Switch to **Ravi** (Admin/Finance). Verify the claim. A payout of ₹6,388.44 is scheduled for **25 Jun 2026**. Mark it paid.
6. Back as Chaitanya: the stepper shows Payout complete and the timeline shows every step. Optionally, as **Imran**, start a new request with an advance above 60% to show the live block.

---

## 17. Decisions and assumptions (go in the note; don't change them without asking the user)

1. **Approval levels are based on value.** A request uses the total estimate (all heads). A settlement uses the net reimbursable claim (employee-paid minus disallowed).
2. **Missing approver role** (e.g. Finance staff have no HoD): escalate to the next higher role in the reporting line. If nobody is above, skip with a recorded note.
3. **Finance comes last**, after the business approvals, as the policy says (§2.1). The xlsx template orders it differently; we follow the policy.
4. **The Chaitanya trip's lodging is Employee-borne.** The voucher says Pay at Hotel and the folio was settled on his personal card, which overrides the template's example "Company". This makes the advance cap ₹19,800.
5. **A returned item** is resubmitted under the same TRQ ID; the revision goes up and the chain is rebuilt from level 1 on the new amount.
6. **Payment run:** the first 10th or 25th on or after Finance verification.
7. **Taxes on the room tariff** are reimbursed in full even when the tariff exceeds the cap (§3.1 literally). Tax on a disallowed item is disallowed with it.
8. **Duplicates** match on bill number + merchant, or merchant + date + time + amount when there's no bill number. They're checked across all employees.
9. **Late submission** (>7 days) is a warning visible to approvers, not a block. The business can still choose to pay it.
10. **Tier 2 cities** aren't listed in the policy, so the user picks Tier 2 or 3 for any non-Tier-1 city.
11. **In-room dining** on the hotel folio is treated as a meal (not listed as non-reimbursable in §4).
12. **The LLM extracts and never decides.** Extractions for the sample pack are cached, so the demo and tests are deterministic and work offline.
13. **Authentication** is a "log in as" picker. Roles come from `employee_master.csv`. Authorization is fully server-side.

---

## 18. Where it breaks (honest limitations for the note)

- **Extraction quality.** The LLM can misread a damaged photo; the pack's folio has a fold across one line. Reconciliation against totals and the booking voucher catches this case, but not every case. The employee is the final check.
- **Name matching** for "someone else's expense" uses first and full name. A colleague with the same first name would slip through.
- **No Tier 2 list** in the policy, so the city tier relies on the user's choice for non-Tier-1 cities.
- **Prior HoD approval for entertainment** is only a reference field and a warning, not a separate pre-trip workflow.
- **The MD's own claims** have no business approver above them; only Finance verifies.
- **Kavitha** can appear twice in Ravi's chain, once as RM and once as Finance verifier. Separation of duties isn't modelled beyond "not yourself".
- **Storage.** SQLite and local file storage: on Render's free tier, data resets on redeploy. Fine for a prototype, wrong for production (it should be Postgres plus object storage).
- **One settlement per request.** INR only. No real inbox connection.
