# Nortex Travel Expense Reimbursement (prototype)

Employees forward their trip emails and receipts; the app proposes a filled-in settlement claim, enforces the
expense policy on every line, routes it through the approval chain to Finance, and shows where the money is.

> **The LLM proposes, deterministic Python decides, the human confirms.**
> The model only extracts fields from a document. Every policy decision (used/excluded/ignored, disallowed
> amounts, duplicates, approval chain, payout date) is plain, unit-tested Python.

## Run it (one command)

```bash
cp .env.example .env          # optional keys; the app runs fully without them (see below)
docker compose up --build     # http://localhost:8001 (container port 8000; change the left side in docker-compose.yml)
```

Local dev without Docker:

```bash
cd backend && python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8000
cd frontend && npm install && npm run dev     # http://localhost:5173, /api proxied to :8000
```

## Demo users — "Log in as" picker (no passwords)

Pick a person on the login screen; `emp_code` is stored in a signed session cookie. Roles come from
`pack/employee_master.csv`. All authorization is enforced on the server.

| App role | People |
|---|---|
| Employee | Chaitanya Reddy NX-4471, Deepa Nair NX-5182, Imran Qureshi NX-4490 |
| Manager | Suresh Iyer NX-2210, Meera Krishnan NX-1108, Arvind Rao NX-1002, Nandita Shah NX-1000 |
| Admin (Finance) | Ravi Menon NX-3305, Kavitha Balan NX-3300 |

The demo path is in `DEMO.md`: Chaitanya → *Load sample inbox* on TRQ-2026-0001 → add attendees → submit →
Suresh / Meera approve → Ravi verifies → payout ₹6,388.44 on 25 Jun 2026.

## Environment variables (`.env.example`)

| Var | Purpose |
|---|---|
| `OPENAI_API_KEY`, `OPENAI_MODEL` | Extraction of uncached documents. If empty the app still runs: cached extractions are used and uncached files fall back to manual entry |
| `APP_TODAY` | Freezes "today" (2026-06-22) so the June 2026 demo trip isn't late |
| `SESSION_SECRET` | Signs the session cookie |
| `COOKIE_SECURE` | `true` on HTTPS hosts (Render) |
| `DATABASE_URL` | SQLite by default (`sqlite:///./data/app.db`) |
| `PACK_DIR` | Assignment pack folder (`../pack`; `/app/pack` in Docker) |

Extractions for the sample pack are committed in `backend/fixtures/extractions/` (rebuild with
`cd backend && python -m app.ingest.build_cache`, needs a key). Tests and the demo never touch the network.

## Tests

```bash
cd backend && .venv/bin/python -m pytest -q
```

Covers the approval chain table, every policy rule, payment-run dates, the state machine and its invariants,
the golden sample-pack import (offline) and the full HTTP happy path.

## Architecture in five lines

1. `backend/app/ingest/` parses `.eml`/images, extracts fields (LLM, cached by sha256), and triages deterministically.
2. `backend/app/policy/` holds every number and rule (`config.py`, `rules.py`, `chain.py`, `payments.py`).
3. `backend/app/workflow.py` is the only place statuses change; it enforces the invariants and writes the audit trail.
4. FastAPI + SQLModel/SQLite; `schemas.py` is the API contract, mirrored in `frontend/src/api/types.ts`.
5. React + Vite + Tailwind SPA renders server-side findings; no policy logic exists in TypeScript.

## Deploy on Render

Docker web service from this repo (Render sets `$PORT`; the Dockerfile binds to it and runs uvicorn with
`--proxy-headers`). Set env vars: `SESSION_SECRET`, `APP_TODAY=2026-06-22`, `COOKIE_SECURE=true`,
`PACK_DIR=/app/pack`; add `OPENAI_API_KEY`/`OPENAI_MODEL` only if you want live extraction.
**On the free plan the SQLite file resets on every redeploy and the app re-seeds on boot.**

## Known limitations

- Extraction can misread a damaged photo (the pack's folio has a fold); reconciliation catches this case, not every case. The employee is the final check.
- "Someone else's expense" uses first/full name matching; a colleague with the same first name would slip through.
- The policy has no Tier 2 city list, so non-Tier-1 cities need the user to pick Tier 2 or 3.
- Prior HoD approval for entertainment is a reference field and a warning only.
- The MD's own claims have no business approver above them; only Finance verifies. Kavitha can appear twice in Ravi's chain.
- SQLite + local files: fine for a prototype, wrong for production. One settlement per request, INR only, no real inbox connection.
