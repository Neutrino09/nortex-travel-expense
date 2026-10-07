# Nortex Travel Expense Reimbursement: note

Run it with `./run.sh` (Docker only, no keys needed); details are in the README.

## What I understood the problem to be
Travel claims cost Nortex in three ways: 25–30 minutes of copying bookings and bills from email into Excel, the errors that copying causes (duplicates, personal items, other people's bills, wrong categories), and two weeks of chasing Finance. So the app must propose the claim from the inbox, enforce the policy on every line and show what was disallowed and why, and show each item's stage, who it waits on, and the expected payout.

My principle: **the LLM proposes, deterministic Python decides, the human confirms.** The model only extracts fields. Triage, disallowed amounts, duplicates, the approval chain and the payout date are plain, unit-tested code. The employee edits every line before submitting, and all validation lives on the server.

## Assumptions and decisions
- Approval levels depend on value: a request uses the total estimate, a settlement uses net reimbursable (employee-paid minus disallowed). A higher level brings in every level below it.
- A missing role (Finance staff have no HoD) escalates to the next higher role, with a recorded note. Finance comes last, as the policy says, although the Excel template lists it earlier.
- Chaitanya's lodging is Employee-borne (voucher says "Pay at Hotel", folio on his personal card), so his advance cap is ₹19,800.
- A returned item is resubmitted under the same TRQ id: revision +1, chain rebuilt from level 1.
- Payment run is the first 10th or 25th on or after verification. Tax on a room above the cap is still reimbursed (§3.1 read literally); tax on a disallowed item goes with it.
- Duplicates match on merchant + bill number, or merchant + date + time + amount when there is no bill number (Uber), across all employees.
- Late submission is a warning, not a block. Tier 2 is the user's choice, since the policy lists no Tier 2 cities. In-room dining counts as a meal.
- Sample-pack extractions are cached, so tests and the demo work offline. Login is a "log in as" picker with fully server-side authorization.

## What I built
- FastAPI + SQLModel backend, React frontend (with a light/dark toggle), one Docker image.
- `.eml` and image import with deterministic triage. Every document gets a reason and policy clause; the hotel folio is split into lines, with laundry and minibar disallowed rather than dropped.
- A policy engine, and one state machine that is the only place statuses change, with an append-only audit trail.
- 71 tests, including a golden test that imports the whole sample pack offline and checks net ₹26,388.44.

## What I deliberately left out
Real mailbox connection, SSO, notifications, a policy-editing UI, multi-currency, payroll or bank integration, Postgres and migrations, OCR without an LLM, PDF export, mobile polish, global search, a pre-trip HoD approval workflow for entertainment (a field and a warning only), and multiple settlements per request.

## Where it breaks
- **Extraction.** A model can misread a damaged photo. Checking the folio against the invoice total and the booking voucher catches the pack's fold, not every case; the employee is the final check.
- **Name matching** for "someone else's expense" uses first and full name, so a colleague with the same first name would slip through.
- **No Tier 2 list**, so non-Tier-1 tiers depend on the user.
- **Top of the chain.** The MD's own claims have no approver above them, so only Finance verifies (a request with no approver auto-approves, which I added). Kavitha can appear twice in Ravi's chain; separation of duties only means "not yourself".
- **Beyond the spec:** a corporate-card booking confirmation is treated as a paid ticket, and lines from one document are not flagged as duplicates of each other.
- **Storage.** SQLite and local files reset on Render's free tier; production needs Postgres and object storage.
