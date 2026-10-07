"""Golden test (CLAUDE.md §9): the whole sample inbox, offline, from cached extractions.

Part 1 tests only the ingestion layer (triage + lines + our own arithmetic).
Part 2 adds the policy layer (validate_settlement: summary, findings, chain) from Agent A.
"""
import json

import pytest
from sqlmodel import select

from app.ingest.importer import import_files, sample_files
from app.models import ClaimLine, Evidence, Settlement

EXPECTED_TRIAGE = {
    "01_travel_approval_request.eml": "ignored", "02_travel_approval_granted.eml": "ignored",
    "03_advance_disbursed.eml": "ignored", "04_flight_eticket.eml": "used", "05_hotel_voucher.eml": "excluded",
    "06_uber_receipt_1.eml": "used", "07_uber_receipt_2.eml": "used", "08_uber_payment_failed.eml": "excluded",
    "09_uber_receipt_3.eml": "used", "10_uber_receipt_3_resend.eml": "excluded", "11_dinner_bill.eml": "used",
    "12_hotel_invoice.eml": "used", "13_colleague_forward.eml": "excluded", "14_promo_noise.eml": "ignored",
    "15_return_cab.eml": "used", "dinner_bill_18jun.png": "used", "hotel_invoice_1188.png": "used",
}


@pytest.fixture()
def imported(session):
    settlement = session.exec(select(Settlement)).first()
    result = import_files(session, settlement, sample_files())
    return settlement, result


def _lines(session, settlement):
    return session.exec(select(ClaimLine).where(ClaimLine.settlement_id == settlement.id)).all()


def _by_head(lines, head, **kw):
    return [ln for ln in lines if ln.head == head and all(getattr(ln, k) == v for k, v in kw.items())]


def test_triage_matches_golden_table(imported):
    _, result = imported
    got = {e.filename: e.triage for e in result.evidence}
    assert got == EXPECTED_TRIAGE
    assert result.new_documents == 17
    assert (result.used, result.excluded, result.ignored) == (9, 4, 4)
    assert all(e.triage_reason for e in result.evidence)


def test_triage_reasons(imported):
    _, result = imported
    reason = {e.filename: e.triage_reason for e in result.evidence}
    assert "Duplicate of 09_uber_receipt_3.eml" in reason["10_uber_receipt_3_resend.eml"]
    assert "Deepa" in reason["13_colleague_forward.eml"]
    assert "voucher" in reason["05_hotel_voucher.eml"].lower()
    assert "failed" in reason["08_uber_payment_failed.eml"].lower()
    assert reason["11_dinner_bill.eml"] == "Covering email for dinner_bill_18jun.png"
    assert reason["12_hotel_invoice.eml"] == "Covering email for hotel_invoice_1188.png"


def test_attachments_are_separate_evidence_linked_to_email(session, imported):
    settlement, _ = imported
    evs = {e.filename: e for e in session.exec(select(Evidence)).all()}
    assert evs["dinner_bill_18jun.png"].parent_evidence_id == evs["11_dinner_bill.eml"].id
    assert evs["hotel_invoice_1188.png"].parent_evidence_id == evs["12_hotel_invoice.eml"].id
    assert evs["hotel_invoice_1188.png"].kind == "image"
    from pathlib import Path
    assert Path(evs["hotel_invoice_1188.png"].storage_path).is_absolute()
    assert Path(evs["hotel_invoice_1188.png"].storage_path).is_file()


def test_lines_match_golden_table(session, imported):
    settlement, _ = imported
    lines = _lines(session, settlement)
    evs = {e.id: e.filename for e in session.exec(select(Evidence)).all()}

    air = _by_head(lines, "air")
    assert sorted(ln.amount_paise for ln in air) == [501_600, 554_000]
    assert all(ln.paid_by == "Company" and ln.section == "transport" for ln in air)

    cabs = {(str(ln.date), ln.amount_paise) for ln in _by_head(lines, "cab")}
    assert cabs == {("2026-06-16", 141_502), ("2026-06-16", 74_300), ("2026-06-17", 17_200),
                    ("2026-06-20", 122_902)}

    [dinner] = _by_head(lines, "business_entertainment")
    assert (dinner.bill_no, dinner.amount_paise, str(dinner.date)) == ("4471", 225_500, "2026-06-18")
    assert dinner.section == "other" and json.loads(dinner.attendees_json) == []
    assert "Vertex" in dinner.description
    assert evs[dinner.evidence_id] == "dinner_bill_18jun.png"  # the attachment is the proof

    [lodging] = _by_head(lines, "lodging")
    assert (lodging.base_paise, lodging.tax_paise, lodging.amount_paise) == (1_725_000, 207_000, 1_932_000)
    assert lodging.nights == 3 and lodging.city == "Bengaluru" and lodging.section == "lodging"
    assert evs[lodging.evidence_id] == "hotel_invoice_1188.png"
    [meal] = _by_head(lines, "meals")
    assert (meal.amount_paise, str(meal.date)) == (125_440, "2026-06-18")
    misc = {ln.description: ln.amount_paise for ln in _by_head(lines, "misc")}
    assert sorted(misc.values()) == [42_560, 50_400]  # laundry 504.00, minibar 425.60

    # folio lines add up EXACTLY to the invoice total
    folio = [ln for ln in lines if evs[ln.evidence_id] == "hotel_invoice_1188.png"]
    assert sum(ln.amount_paise for ln in folio) == 2_150_400
    assert all(ln.source == "import" and ln.fingerprint for ln in lines)
    assert all(ln.paid_by == "Employee" for ln in lines if ln.head != "air")
    assert len({ln.fingerprint for ln in lines}) == len(lines)  # no self-collisions (R-DUP safe)


def test_ingestion_arithmetic_hits_golden_summary(session, imported):
    """gross - the two non-reimbursable folio lines = golden net, using only our own arithmetic."""
    settlement, _ = imported
    lines = _lines(session, settlement)
    gross = sum(ln.amount_paise for ln in lines if ln.paid_by == "Employee")
    memo = sum(ln.amount_paise for ln in lines if ln.paid_by == "Company")
    non_reimb = sum(ln.amount_paise for ln in _by_head(lines, "misc"))
    assert gross == 2_731_804 and memo == 1_055_600
    assert non_reimb == 92_960 and gross - non_reimb == 2_638_844


def test_import_is_idempotent(session, imported):
    settlement, _ = imported
    before = len(_lines(session, settlement))
    again = import_files(session, settlement, sample_files())
    assert again.new_documents == 0 and again.skipped_existing > 0 and again.lines_created == 0
    assert len(_lines(session, settlement)) == before
    assert len(session.exec(select(Evidence)).all()) == 17


def test_damaged_folio_falls_back_to_email_body(session):
    """If the folded image's room items don't add up, the email body's figures win (and say so)."""
    from app.ingest import extract as ex
    from app.ingest.folio import split_folio
    body = ex.to_doc(ex.load_cached(_sha("12_hotel_invoice.eml", "sample_emails")))
    inv = ex.to_doc(ex.load_cached(_sha("hotel_invoice_1188.png", "receipts")))
    inv.line_items[1].amount_paise = 0  # the fold: 17-Jun room line unreadable
    lines = split_folio(inv, body, voucher_room_paise=1_725_000)
    assert sum(ln.base_paise + ln.tax_paise for ln in lines) == 2_150_400
    room = next(ln for ln in lines if ln.kind == "room")
    assert "email body" in room.description and "matches booking voucher" in room.description
    assert next(ln for ln in lines if "dining" in ln.description.lower()).date.isoformat() == "2026-06-18"


def _sha(name, folder):
    from app.config import get_settings
    from app.ingest.extract import sha256_of
    return sha256_of((get_settings().pack_dir / folder / name).read_bytes())


def test_no_key_no_cache_is_ignored_with_manual_entry_reason(session, monkeypatch, tmp_path):
    from app.config import get_settings
    settlement = session.exec(select(Settlement)).first()
    monkeypatch.setattr("app.ingest.extract.cache_path", lambda sha: tmp_path / f"{sha}.json")
    result = import_files(session, settlement, [sample_files()[5]])  # an Uber receipt, no cache, no key
    assert result.ignored == 1 and result.lines_created == 0
    assert result.evidence[0].triage_reason == "Extraction unavailable — add the line manually"
    assert get_settings().openai_api_key == ""


# ---- Part 2: needs Agent A's policy layer ----
def test_summary_and_chain_after_import(session, imported):
    rules = pytest.importorskip("app.policy.rules")
    settlement, _ = imported
    result = rules.validate_settlement(session, settlement)
    s = result.summary
    assert (s.gross_employee_paise, s.disallowed_paise, s.net_paise) == (2_731_804, 92_960, 2_638_844)
    assert (s.advance_paise, s.payable_paise, s.recoverable_paise) == (2_000_000, 638_844, 0)
    assert s.company_memo_paise == 1_055_600
    assert [c.approver_code for c in result.chain_preview] == ["NX-2210", "NX-1108", "NX-3305"]
    rules_hit = {(f.rule_id, f.severity) for f in result.findings}
    assert ("R-ENT-ATT", "BLOCK") in rules_hit
    assert ("R-ENT-HOD", "WARN") in rules_hit
    assert not any(f.rule_id == "R-DUP" for f in result.findings)
