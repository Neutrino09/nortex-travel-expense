# Nortex Travel Expense Reimbursement: note

Run it with `./run.sh` (Docker only, no keys needed). Details are in the README.

## What I understood the problem to be
Travel claims cost Nortex in three ways. Employees spend 25–30 minutes copying bookings and bills from email into Excel. That copying causes the errors: duplicates, personal items, other people's bills, wrong categories. Then the claim goes up an approval chain and the employee spends two weeks chasing Finance. So the app has to do three things: propose the claim from the inbox, enforce the policy on every line (and show what was disallowed and why), and show every item's stage, who it is waiting on, and the expected payout.

The principle I built around: **the LLM proposes, deterministic Python decides, the human confirms.** The model only extracts fields from a document. Used/excluded/ignored, disallowed amounts, duplicates, the approval chain and the payout date are plain unit-tested code. The employee edits every line before submitting, and all validation lives on the server.

## Assumptions and decisions
- Approval levels depend on value. A request uses the total estimate; a settlement uses net reimbursable (employee-paid minus disallowed). A higher level brings in every level below it.
- If a role is missing in the reporting line (Finance staff have no HoD), I escalate to the next higher role and record a note. Finance always comes last, as the policy says, even though the Excel template lists it earlier.
- Chaitanya's lodging is Employee-borne: the voucher says "Pay at Hotel" and the folio was on his personal card. That makes the advance cap ₹19,800.
- A returned item is resubmitted under the same TRQ id with the revision bumped and the chain rebuilt from level 1.
- Payment run is the first 10th or 25th on or after verification. Tax on a room tariff above the cap is still reimbursed (§3.1 read literally); tax on a disallowed item goes with it.
- Duplicates match on merchant plus bill number, or merchant plus date, time and amount when there is no bill number (Uber), across all employees.
- Late submission (more than 7 days) is a warning to approvers, not a block. Tier 2 is a user choice because the policy lists no Tier 2 cities. In-room dining counts as a meal.
- Sample-pack extractions are cached, so tests and the demo are deterministic and work offline. Login is a "log in as" picker; authorization is fully server-side.

## What I built
- FastAPI + SQLModel backend, React frontend, one Docker image.
- Import of `.eml` files and receipt images with deterministic triage. Every document gets a reason and a policy clause, and the hotel folio is split into lines with laundry and minibar disallowed rather than dropped.
- A policy engine (rules, approval chain, payment runs) and a single state machine that is the only place statuses change, with an append-only audit trail.
- Employee, Manager and Finance screens, including a light/dark toggle.
- 71 tests, including a golden test that imports the whole sample pack offline and checks net ₹26,388.44.

## What I deliberately left out
A real mailbox connection, passwords or SSO, notifications, a policy-editing UI, multi-currency, payroll or bank integration, Postgres and migrations, OCR without an LLM, PDF export, mobile polish, global search, a pre-trip HoD approval workflow for entertainment (a reference field and a warning only), and multiple settlements per request.

## Where it breaks
- **Extraction.** A model can misread a damaged photo. The pack's folio has a fold; checking the items against the invoice total and the booking voucher catches that case, not every case. The employee is the final check.
- **Name matching** for "someone else's expense" uses first and full name, so a colleague with the same first name would slip through.
- **No Tier 2 list**, so the tier for non-Tier-1 cities depends on the user's choice.
- **The top of the chain.** The MD's own claims have no business approver above them, so only Finance verifies (a request with no approver auto-approves, which I added). Kavitha can appear twice in Ravi's chain; separation of duties only means "not yourself".
- **Calls that go beyond the spec:** a corporate-card booking confirmation is treated as a paid ticket, and lines from the same document are not flagged as duplicates of each other.
- **Storage.** SQLite and local files are fine for a prototype; on Render's free tier they reset on redeploy. Production needs Postgres and object storage.
