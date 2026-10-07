"""Policy rules as pure functions over unsaved ClaimLine objects (§13)."""
import json
from datetime import date

import pytest

from app.models import ClaimLine, RequestCostHead, TravelRequest
from app.policy.config import tier_for_city
from app.policy.rules import (LineContext, advance_cap_paise, evaluate_lines, fingerprint,
                              line_fingerprint, request_findings, summarize)

TRIP = dict(from_date=date(2026, 6, 16), to_date=date(2026, 6, 20))


def ctx(tier=1, ref=date(2026, 6, 22), external=None):
    return LineContext(tier, TRIP["from_date"], TRIP["to_date"], ref, external or set())


_next_id = iter(range(1, 1000))


def line(head="misc", base=100_000, tax=0, **kw):
    section = {"lodging": "lodging", "cab": "transport", "air": "transport"}.get(head, "other")
    kw.setdefault("evidence_id", 1)
    kw.setdefault("date", date(2026, 6, 17))
    kw.setdefault("merchant", f"Shop{next(_next_id)}")
    return ClaimLine(id=next(_next_id), settlement_id=1, section=section, head=head, base_paise=base,
                     tax_paise=tax, amount_paise=base + tax, **kw)


def ids(findings, rule):
    return [f for f in findings if f.rule_id == rule]


# ---- request rules ----
def heads(*pairs):
    return [RequestCostHead(request_id="T", head=h, estimate_paise=p, borne_by=b) for h, p, b in pairs]


EMP_HEADS = heads(("lodging", 2_300_000, "Employee"), ("conveyance", 400_000, "Employee"),
                  ("meals", 600_000, "Employee"), ("air_rail", 1_050_000, "Company"))


def make_req(advance, city="Bengaluru", tier=None):
    return TravelRequest(id="T", emp_code="NX-4471", created_at=date(2026, 6, 1), advance_requested_paise=advance,
                         destination_city=city, city_tier=tier, **TRIP)


def test_advance_cap_is_60_percent_of_employee_heads():
    assert advance_cap_paise(EMP_HEADS) == 1_980_000


def test_advance_over_cap_blocks():
    f = ids(request_findings(make_req(2_000_000), EMP_HEADS), "RQ-ADV")
    assert f and f[0].severity == "BLOCK"


def test_advance_at_cap_ok():
    assert not ids(request_findings(make_req(1_980_000), EMP_HEADS), "RQ-ADV")


def test_tier_one_city_automatic_other_city_needs_choice():
    assert tier_for_city("Gurugram") == 1 and tier_for_city("Jaipur") is None
    assert ids(request_findings(make_req(0, city="Jaipur"), EMP_HEADS), "RQ-TIER")
    assert not ids(request_findings(make_req(0, city="Jaipur", tier=2), EMP_HEADS), "RQ-TIER")


def test_request_dates_and_heads_block():
    req = make_req(0)
    req.from_date, req.to_date = date(2026, 6, 20), date(2026, 6, 16)
    f = request_findings(req, [])
    assert ids(f, "RQ-DATES") and ids(f, "RQ-HEADS")


# ---- lodging ----
def test_lodging_over_cap_disallows_tariff_excess_only_tax_untouched():
    # Tier 2: cap 4000; 4500 x 2 nights = 9000 base, tax 1080 -> disallow 1000, tax untouched
    lodge = line("lodging", base=900_000, tax=108_000, nights=2)
    evaluate_lines([lodge], ctx(tier=2))
    assert lodge.disallowed_paise == 100_000
    assert lodge.amount_paise - lodge.disallowed_paise == 908_000


def test_lodging_within_cap_untouched():
    lodge = line("lodging", base=1_725_000, tax=207_000, nights=3)  # 5750/night, Tier 1 cap 6000
    evaluate_lines([lodge], ctx(tier=1))
    assert lodge.disallowed_paise == 0


# ---- meals ----
def test_meals_per_day_cap_on_last_line_of_the_date():
    a, b = line("meals", base=100_000), line("meals", base=90_000)  # 1900 total vs 1500 cap
    other_day = line("meals", base=80_000, date=date(2026, 6, 18))
    evaluate_lines([a, b, other_day], ctx(tier=1))
    assert (a.disallowed_paise, b.disallowed_paise, other_day.disallowed_paise) == (0, 40_000, 0)


def test_meal_cap_other_tier_and_entertainment_not_a_meal():
    meal = line("meals", base=120_000)
    ent = line("business_entertainment", base=300_000, attendees_json=json.dumps(
        [{"name": "A", "organisation": "Vertex"}]))
    evaluate_lines([meal, ent], ctx(tier=2))
    assert meal.disallowed_paise == 20_000 and ent.disallowed_paise == 0


# ---- non-reimbursable / alcohol ----
def test_non_reimbursable_disallows_base_and_prorated_tax():
    laundry = line("misc", base=480_00, tax=24_00, description="Laundry charges")
    mini = line("misc", base=400_00, tax=25_60, description="Minibar")
    evaluate_lines([laundry, mini], ctx())
    assert laundry.disallowed_paise == 50_400 and mini.disallowed_paise == 42_560
    assert laundry.policy_ref == "§4" and laundry.disallow_reason


def test_alcohol_disallowed_unless_business_entertainment():
    beer = line("meals", base=50_000, description="Beer with dinner")
    ent = line("business_entertainment", base=50_000, description="Wine for client dinner",
               attendees_json=json.dumps([{"name": "A", "organisation": "Vertex"}]))
    evaluate_lines([beer, ent], ctx())
    assert beer.disallowed_paise == 50_000 and ent.disallowed_paise == 0


def test_keyword_match_is_whole_word():
    cab = line("cab", base=100_000, description="Cab Baner to airport", from_place="Baner")
    evaluate_lines([cab], ctx())
    assert cab.disallowed_paise == 0


def test_employee_paid_air_disallowed_company_air_is_memo():
    mine, theirs = line("air", base=500_000), line("air", base=500_000, paid_by="Company")
    f = evaluate_lines([mine, theirs], ctx())
    assert mine.disallowed_paise == 500_000 and theirs.disallowed_paise == 0
    assert ids(f, "R-AIR") and [x.severity for x in ids(f, "R-COMPANY")] == ["INFO"]


# ---- duplicates ----
def test_fingerprint_with_and_without_bill_no():
    assert fingerprint("Spice Terrace!", "4471", None, None, 1) == fingerprint("spice terrace", "4471", None, None, 99)
    uber = fingerprint("Uber", None, date(2026, 6, 17), "10:15", 17200)
    assert uber != fingerprint("Uber", None, date(2026, 6, 17), "10:16", 17200)


def test_duplicate_without_bill_number_blocks_the_second_line():
    kw = dict(merchant="Uber", date=date(2026, 6, 17), time="10:15", base=17200)
    first, second = line("cab", evidence_id=1, **kw), line("cab", evidence_id=2, **kw)
    f = evaluate_lines([first, second], ctx())
    dup = ids(f, "R-DUP")
    assert [d.line_id for d in dup] == [second.id] and dup[0].severity == "BLOCK"


def test_lines_from_same_document_are_not_duplicates_and_external_collision_blocks():
    a = line("lodging", merchant="Keys Prime", bill_no="1188", evidence_id=7, nights=1)
    b = line("meals", merchant="Keys Prime", bill_no="1188", evidence_id=7)
    assert not ids(evaluate_lines([a, b], ctx()), "R-DUP")
    c = line("cab", merchant="Uber", date=date(2026, 6, 17), time="09:00", base=10_000)
    ext = {line_fingerprint(c)}
    assert ids(evaluate_lines([c], ctx(external=ext)), "R-DUP")


# ---- proof / entertainment / window / late / empty ----
def test_missing_proof_and_empty_block():
    assert ids(evaluate_lines([line("cab", evidence_id=None)], ctx()), "R-PROOF")
    assert ids(evaluate_lines([], ctx()), "R-EMPTY")


def test_entertainment_needs_named_attendee_with_organisation():
    ent = line("business_entertainment", base=225_500)
    f = evaluate_lines([ent], ctx())
    assert ids(f, "R-ENT-ATT")[0].severity == "BLOCK"
    assert ids(f, "R-ENT-HOD")[0].severity == "WARN"  # > ₹2,000, no prior approval ref
    ent.attendees_json = json.dumps([{"name": "Ravi", "organisation": ""}])
    assert ids(evaluate_lines([ent], ctx()), "R-ENT-ATT")
    ent.attendees_json = json.dumps([{"name": "Ravi", "organisation": "Vertex"}])
    ent.prior_approval_ref = "HOD-OK"
    f = evaluate_lines([ent], ctx())
    assert not ids(f, "R-ENT-ATT") and ids(f, "R-ENT-HOD")[0].severity == "INFO"


def test_window_warning():
    assert ids(evaluate_lines([line("cab", date=date(2026, 6, 30))], ctx()), "R-WINDOW")
    assert not ids(evaluate_lines([line("cab", date=date(2026, 6, 21))], ctx()), "R-WINDOW")


def test_late_warning_driven_by_today():
    ln = line("cab")
    assert not ids(evaluate_lines([ln], ctx(ref=date(2026, 6, 27))), "R-LATE")  # exactly +7
    assert ids(evaluate_lines([ln], ctx(ref=date(2026, 6, 28))), "R-LATE")


def test_late_uses_app_today(session, monkeypatch):
    """validate_settlement reads app.clock.today() (APP_TODAY=2026-06-22 -> on time)."""
    from app.models import Settlement
    from app.policy.rules import validate_settlement
    st = session.get(Settlement, 1)
    assert not ids(validate_settlement(session, st, save=False).findings, "R-LATE")
    monkeypatch.setenv("APP_TODAY", "2026-07-15")
    assert ids(validate_settlement(session, st, save=False).findings, "R-LATE")


# ---- summary ----
def test_summary_payable_case():
    lines = [line("lodging", base=1_000_000, nights=1), line("air", base=500_000, paid_by="Company")]
    lines[0].disallowed_paise = 100_000
    s = summarize(lines, 500_000)
    assert (s.gross_employee_paise, s.company_memo_paise, s.disallowed_paise, s.net_paise) == (
        1_000_000, 500_000, 100_000, 900_000)
    assert (s.payable_paise, s.recoverable_paise) == (400_000, 0)


def test_summary_recovery_case():
    s = summarize([line("misc", base=1_500_000)], 2_000_000)
    assert s.net_paise == 1_500_000 and s.recoverable_paise == 500_000 and s.payable_paise == 0
