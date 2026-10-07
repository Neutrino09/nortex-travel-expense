"""Deterministic validation (policy §1–§5). The LLM never decides any of this.
Pure functions (request_findings, evaluate_lines, summarize) + thin DB wrappers."""
import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlmodel import Session, select

from ..clock import today
from ..models import Advance, ClaimLine, Employee, RequestCostHead, Settlement, TravelRequest
from ..money import format_inr
from ..schemas import Finding, SettlementSummary, ValidationResult
from . import chain as chain_mod
from .config import (ADVANCE_PERCENT, ALCOHOL_RE, ENTERTAINMENT_HOD_ABOVE_PAISE, LATE_AFTER_DAYS,
                     NON_REIMBURSABLE_RE, WINDOW_DAYS, lodging_cap_paise, meal_cap_paise,
                     tier_for_city)
from .payments import expected_payout

SETTLEMENT_RULE_IDS = ["R-PROOF", "R-DUP", "R-LODGE", "R-NONREIMB", "R-ALCOHOL", "R-MEAL",
                       "R-AIR", "R-COMPANY", "R-ENT-ATT", "R-ENT-HOD", "R-WINDOW", "R-LATE",
                       "R-EMPTY"]


def find(rule_id, severity, message, ref=None, line=None, amount=None) -> Finding:
    return Finding(rule_id=rule_id, severity=severity, message=message, policy_ref=ref,
                   line_id=line.id if line else None, amount_paise=amount)


# ------------------------------------------------------------------ requests

def advance_cap_paise(heads) -> int:
    """policy §1.2: advance <= 60% of the employee-borne heads."""
    employee_total = sum(h.estimate_paise for h in heads if h.borne_by == "Employee")
    return employee_total * ADVANCE_PERCENT // 100


def request_days(from_date: date | None, to_date: date | None) -> int | None:
    return (to_date - from_date).days + 1 if from_date and to_date and from_date <= to_date else None


def resolve_tier(city: str, chosen: int | None) -> int | None:
    """policy §3.1: Tier 1 is automatic; any other city needs the user to pick Tier 2 or 3."""
    return tier_for_city(city) or (chosen if chosen in (2, 3) else None)


def request_findings(req, heads) -> list[Finding]:
    out: list[Finding] = []
    cap = advance_cap_paise(heads)
    if req.advance_requested_paise > cap:  # RQ-ADV, policy §1.2
        out.append(find("RQ-ADV", "BLOCK",
                        f"Advance {format_inr(req.advance_requested_paise)} exceeds the "
                        f"{ADVANCE_PERCENT}% cap of {format_inr(cap)}", "§1.2"))
    if not (req.from_date and req.to_date) or req.from_date > req.to_date:  # RQ-DATES
        out.append(find("RQ-DATES", "BLOCK", "Travel dates are required and From must not be after To"))
    if resolve_tier(req.destination_city, req.city_tier) is None:  # RQ-TIER, policy §3.1
        out.append(find("RQ-TIER", "BLOCK",
                        "City is not Tier 1 — choose Tier 2 or Tier 3 for the destination", "§3.1"))
    if not heads or any(h.estimate_paise < 0 for h in heads):  # RQ-HEADS
        out.append(find("RQ-HEADS", "BLOCK", "Add at least one cost head (estimates cannot be negative)"))
    return out


def _all_employees(session: Session) -> dict[str, Employee]:
    return {e.emp_code: e for e in session.exec(select(Employee))}


def request_heads(session: Session, req: TravelRequest) -> list[RequestCostHead]:
    return list(session.exec(select(RequestCostHead).where(RequestCostHead.request_id == req.id)))


def request_chain_preview(session: Session, req: TravelRequest):
    """Business approvers only, valued on the full estimate (§2; no Finance step on requests)."""
    emps = _all_employees(session)
    specs = chain_mod.build_chain(emps[req.emp_code], req.estimate_total_paise,
                                  req.category == "international", False, False, emps)
    return chain_mod.to_out(specs, emps)


# ------------------------------------------------------------------ settlement lines

@dataclass
class LineContext:
    tier: int | None
    from_date: date | None
    to_date: date | None
    ref_date: date  # today(), or the submit date once submitted
    external_fingerprints: set[str] = field(default_factory=set)  # other non-rejected settlements


def fingerprint(merchant: str, bill_no: str | None, date, time: str | None, amount_paise: int) -> str:
    """policy §5.3. norm(merchant)+bill_no, else norm(merchant)+date+time+amount (Uber has no bill no)."""
    def norm(s):
        return re.sub(r"[^a-z0-9]", "", (s or "").lower())
    if bill_no and bill_no.strip():
        return f"{norm(merchant)}|{norm(bill_no)}"
    return f"{norm(merchant)}|{date.isoformat() if date else ''}|{norm(time)}|{amount_paise}"


def line_fingerprint(line: ClaimLine) -> str:
    return fingerprint(line.merchant, line.bill_no, line.date, line.time, line.amount_paise)


def _disallow(line: ClaimLine, paise: int, reason: str, ref: str) -> Finding | None:
    """Record a disallowance on the line (never deletes it), capped at what is still allowed."""
    paise = min(paise, line.amount_paise - line.disallowed_paise)
    if paise <= 0:
        return None
    line.disallowed_paise += paise
    line.disallow_reason = f"{line.disallow_reason}; {reason}" if line.disallow_reason else reason
    line.policy_ref = ref
    return find("DISALLOW", "DISALLOW", f"{reason}: {format_inr(paise)} disallowed", ref, line, paise)


def _named(rule_id: str, f: Finding | None) -> list[Finding]:
    if f:
        f.rule_id = rule_id
    return [f] if f else []


def _nights(line: ClaimLine) -> int | None:
    if line.nights:
        return line.nights
    if line.check_in and line.check_out and line.check_out > line.check_in:
        return (line.check_out - line.check_in).days
    return None


def _full_disallowance(line: ClaimLine) -> list[Finding]:
    """Rules that disallow 100% of an employee-paid line; first match wins."""
    if line.head == "air":  # R-AIR, policy §3.2
        return _named("R-AIR", _disallow(line, line.amount_paise,
                      "Flights are booked and billed through the travel desk", "§3.2"))
    if NON_REIMBURSABLE_RE.search(line.description or ""):  # R-NONREIMB, policy §4
        return _named("R-NONREIMB", _disallow(line, line.amount_paise,
                      "Non-reimbursable item (policy §4)", "§4"))
    if ALCOHOL_RE.search(line.description or "") and line.head != "business_entertainment":
        return _named("R-ALCOHOL", _disallow(line, line.amount_paise,  # R-ALCOHOL, policy §4
                      "Alcohol is not reimbursable outside business entertainment", "§4"))
    return []


def _lodging_cap(line: ClaimLine, tier: int | None) -> list[Finding]:
    """R-LODGE, policy §3.1: disallow (tariff - cap) x nights on the base; tax is reimbursed in full."""
    if line.head != "lodging" or line.disallowed_paise:
        return []
    nights = _nights(line)
    if not nights:
        return [find("R-LODGE", "WARN", "Nights missing — lodging cap not checked", "§3.1", line)]
    cap = lodging_cap_paise(tier)
    tariff = line.base_paise // nights
    if tariff <= cap:
        return []
    excess = line.base_paise - cap * nights
    return _named("R-LODGE", _disallow(
        line, excess, f"Room tariff {format_inr(tariff)}/night above Tier {tier or 3} cap "
                      f"{format_inr(cap)}/night (taxes reimbursed)", "§3.1"))


def _meal_cap(lines: list[ClaimLine], tier: int | None) -> list[Finding]:
    """R-MEAL, policy §3.3: per-date cap; excess disallowed on the last line(s) of that date."""
    cap, out = meal_cap_paise(tier), []
    by_date: dict[date, list[ClaimLine]] = {}
    for ln in lines:
        if ln.head == "meals" and ln.paid_by == "Employee" and ln.date:
            by_date.setdefault(ln.date, []).append(ln)
    for day, day_lines in by_date.items():
        excess = sum(ln.amount_paise - ln.disallowed_paise for ln in day_lines) - cap
        for ln in reversed(day_lines):
            if excess <= 0:
                break
            taken = min(excess, ln.amount_paise - ln.disallowed_paise)
            out += _named("R-MEAL", _disallow(
                ln, taken, f"Meals on {day:%d %b} above the {format_inr(cap)} daily cap", "§3.3"))
            excess -= taken
    return out


def _entertainment(line: ClaimLine) -> list[Finding]:
    out = []
    people = json.loads(line.attendees_json) if line.attendees_json else []
    if not any((p.get("name") or "").strip() and (p.get("organisation") or "").strip() for p in people):
        out.append(find("R-ENT-ATT", "BLOCK",  # policy §3.5
                        "Business entertainment needs at least one attendee with name and organisation",
                        "§3.5", line))
    if line.amount_paise > ENTERTAINMENT_HOD_ABOVE_PAISE:  # R-ENT-HOD, policy §3.5
        msg = "Entertainment above ₹2,000 needs Head of Department approval"
        if not (line.prior_approval_ref or "").strip():
            out.append(find("R-ENT-HOD", "WARN", msg + "; no prior approval reference given", "§3.5", line))
        else:
            out.append(find("R-ENT-HOD", "INFO", msg, "§3.5", line))
    return out


def _duplicates(lines: list[ClaimLine], external: set[str]) -> list[Finding]:
    """R-DUP, policy §5.3. Lines from the same document (same evidence) never duplicate each other."""
    out, seen = [], {}
    for ln in lines:
        fp = ln.fingerprint
        if not fp or not (ln.merchant or ln.bill_no):
            continue
        earlier = [o for o in seen.get(fp, []) if o.evidence_id is None or o.evidence_id != ln.evidence_id]
        if fp in external or earlier:
            out.append(find("R-DUP", "BLOCK", "Duplicate of another claimed bill", "§5.3", ln))
        seen.setdefault(fp, []).append(ln)
    return out


def _per_line(line: ClaimLine, ctx: LineContext) -> list[Finding]:
    out = []
    if not line.evidence_id:  # R-PROOF, policy §5.2
        out.append(find("R-PROOF", "BLOCK", "Attach proof (a bill or receipt) to this line", "§5.2", line))
    if ctx.from_date and ctx.to_date and line.date and not (
            ctx.from_date - timedelta(days=WINDOW_DAYS) <= line.date <= ctx.to_date + timedelta(days=WINDOW_DAYS)):
        out.append(find("R-WINDOW", "WARN", "Line date is outside the trip dates", None, line))  # R-WINDOW
    if line.paid_by == "Company":  # R-COMPANY: memo only, never reimbursed
        return out + [find("R-COMPANY", "INFO", "Paid by company — memo only, not reimbursed",
                           "template legend", line)]
    if line.head == "business_entertainment":
        out += _entertainment(line)
    return out + _full_disallowance(line) + _lodging_cap(line, ctx.tier)


def evaluate_lines(lines: list[ClaimLine], ctx: LineContext) -> list[Finding]:
    """Runs every settlement rule; sets disallowed_paise / reason / policy_ref on the lines."""
    for ln in lines:
        ln.disallowed_paise, ln.disallow_reason, ln.policy_ref = 0, None, None
        ln.amount_paise = ln.base_paise + ln.tax_paise
        ln.fingerprint = ln.fingerprint or line_fingerprint(ln)
    findings: list[Finding] = []
    if not lines:  # R-EMPTY
        findings.append(find("R-EMPTY", "BLOCK", "The settlement has no lines"))
    for ln in lines:
        findings += _per_line(ln, ctx)
    findings += _meal_cap([ln for ln in lines if ln.paid_by == "Employee"], ctx.tier)
    findings += _duplicates(lines, ctx.external_fingerprints)
    if ctx.to_date and ctx.ref_date > ctx.to_date + timedelta(days=LATE_AFTER_DAYS):  # R-LATE §5.1
        findings.append(find("R-LATE", "WARN",
                             f"Submitted more than {LATE_AFTER_DAYS} days after the trip ended", "§5.1"))
    return findings


def summarize(lines, advance_paise: int) -> SettlementSummary:
    """Mirrors rows 44–50 of the xlsx. Exactly one of payable / recoverable is non-zero."""
    emp = [ln for ln in lines if ln.paid_by == "Employee"]
    gross = sum(ln.amount_paise for ln in emp)
    disallowed = sum(ln.disallowed_paise for ln in emp)
    net = gross - disallowed
    return SettlementSummary(
        gross_employee_paise=gross,
        company_memo_paise=sum(ln.amount_paise for ln in lines if ln.paid_by == "Company"),
        disallowed_paise=disallowed, net_paise=net, advance_paise=advance_paise,
        payable_paise=max(net - advance_paise, 0), recoverable_paise=max(advance_paise - net, 0))


# ------------------------------------------------------------------ settlement (DB)

def settlement_lines(session: Session, settlement: Settlement) -> list[ClaimLine]:
    return list(session.exec(select(ClaimLine).where(ClaimLine.settlement_id == settlement.id)
                             .order_by(ClaimLine.id)))


def advance_paise_for(session: Session, request_id: str) -> int:
    return sum(a.amount_paise for a in session.exec(select(Advance).where(Advance.request_id == request_id)))


def current_summary(session: Session, settlement: Settlement) -> SettlementSummary:
    """Summary from the SAVED disallowed amounts (no re-run)."""
    return summarize(settlement_lines(session, settlement), advance_paise_for(session, settlement.request_id))


def _external_fingerprints(session: Session, settlement: Settlement, fps: set[str]) -> set[str]:
    if not fps:
        return set()
    rows = session.exec(select(ClaimLine.fingerprint).join(Settlement, Settlement.id == ClaimLine.settlement_id)
                        .where(Settlement.id != settlement.id, Settlement.status != "rejected",
                               ClaimLine.fingerprint.in_(fps)))
    return set(rows)


def _forces_hod(lines: list[ClaimLine]) -> bool:
    """policy §3.5: an employee-paid entertainment line above ₹2,000 forces HoD into the chain."""
    return any(ln.head == "business_entertainment" and ln.paid_by == "Employee"
               and ln.amount_paise > ENTERTAINMENT_HOD_ABOVE_PAISE for ln in lines)


def validate_settlement(session: Session, settlement: Settlement, save: bool = True) -> ValidationResult:
    """Re-runs every rule; saves disallowed amounts on the lines (flush, caller commits).
    save=False is a read-only dry run (used for submitted settlements and the approver inbox)."""
    if save:
        return _validate(session, settlement, True)
    with session.no_autoflush:
        return _validate(session, settlement, False)


def _validate(session: Session, settlement: Settlement, save: bool) -> ValidationResult:
    req = session.get(TravelRequest, settlement.request_id)
    lines = settlement_lines(session, settlement)
    for ln in lines:
        ln.fingerprint = ln.fingerprint or line_fingerprint(ln)
    ref = settlement.submitted_at.date() if settlement.submitted_at else today()
    ctx = LineContext(req.city_tier, req.from_date, req.to_date, ref,
                      _external_fingerprints(session, settlement, {ln.fingerprint for ln in lines}))
    findings = evaluate_lines(lines, ctx)
    summary = summarize(lines, advance_paise_for(session, req.id))
    emps = _all_employees(session)
    specs = chain_mod.build_chain(emps[settlement.emp_code], summary.net_paise,
                                  req.category == "international", _forces_hod(lines), True, emps)
    if save:
        for ln in lines:
            session.add(ln)
        session.flush()
    else:
        session.expire_all()  # do not leak the in-memory recomputation into a later commit
    verified = settlement.status in ("verified", "paid")
    return ValidationResult(findings=findings, summary=summary,
                            chain_preview=chain_mod.to_out(specs, emps),
                            rules_checked=len(SETTLEMENT_RULE_IDS),
                            expected_payout=expected_payout(summary, today(), verified))
