# Nortex Travel Expense Reimbursement: note

## What I understood the problem to be
Three costs: about 25 minutes of hand-copying per claim, errors from that copying (duplicates, personal items, other
people's bills, wrong categories), and two weeks of chasing Finance for status. The app imports the inbox and proposes
the claim, enforces the policy line by line, and shows each item's stage, who it waits on, and the expected payout.
The principle I built around: **the LLM proposes, deterministic Python decides, the human confirms.** The model only
extracts fields; classification, disallowed amounts, duplicates, the approval chain and the payout date are plain,
unit-tested code, and the employee reviews every line before submitting. Validation exists only on the server.

## Assumptions and decisions
1. Approval levels depend on value: a request uses the total estimate; a settlement uses net reimbursable (employee-paid minus disallowed).
2. A missing approver role (e.g. no HoD above Finance staff) escalates to the next higher role; if nobody is above, the level is skipped with a recorded note.
3. Finance comes last, as the policy says (§2.1). The xlsx template lists it before MD; I followed the policy.
4. Chaitanya's lodging is Employee-borne (voucher says Pay at Hotel; folio on his personal card), so the advance cap is ₹19,800.
5. A returned item is resubmitted under the same TRQ ID; revision goes up and the chain is rebuilt from level 1 on the new amount.
6. Payment run: first 10th or 25th on or after Finance verification.
7. Tax on a room tariff above the cap is reimbursed in full (§3.1 read literally); tax on a disallowed item goes with it.
8. Duplicates match on merchant + bill number, or merchant + date + time + amount when there is no bill number, across all employees.
9. Late submission (>7 days) is a warning to approvers, not a block.
10. The policy has no Tier 2 list, so the user picks Tier 2 or 3 for any non-Tier-1 city.
11. In-room dining on a hotel folio counts as a meal.
12. Sample-pack extractions are cached, so the demo and tests are deterministic and work offline.
13. Login is a "log in as" picker; roles come from the employee CSV; authorization is fully server-side.

## What I built
- FastAPI + SQLModel backend, React/Vite/Tailwind frontend, one Docker image.
- Ingestion: .eml and image import, cached LLM extraction, deterministic triage into used / excluded / ignored with reason and policy clause, hotel folio split with reconciliation.
- Policy engine (rules, approval chain, payment runs), a single audited state machine, and the Employee, Manager and Finance screens.
- Tests: chain table, every rule, payment dates, workflow invariants, the golden sample-pack import (offline), and the full HTTP happy path.

## What I deliberately left out
Real mailbox connection, passwords/SSO, notifications, a policy-editing UI, multi-currency, payroll or bank integration, Postgres/migrations, OCR without an LLM, PDF export, mobile polish, dark mode, global search, a pre-trip HoD approval workflow for entertainment (reference field and warning only), and multiple settlements per request.

## Where it breaks
- Extraction can misread a damaged photo. Reconciliation catches the pack's folded folio, not every case; the employee is the final check.
- "Someone else's expense" matches on first or full name, so a colleague with the same first name would slip through.
- No Tier 2 list, so city tier relies on the user's choice outside Tier 1.
- The MD's own claims have no business approver above them; only Finance verifies. Kavitha can appear twice in Ravi's chain (separation of duties is only "not yourself").
- SQLite and local files: on Render's free tier data resets on redeploy. Production needs Postgres and object storage.
- Some choices go beyond the spec and are worth stating: a corporate-card booking confirmation is treated as a paid ticket, and a request with no business approver auto-approves.
