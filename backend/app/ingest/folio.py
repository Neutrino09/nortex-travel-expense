"""Split a hotel tax invoice (folio) into claim lines (CLAUDE.md §9 step 4).

Rooms -> one lodging line; in-room dining -> meals line; laundry/minibar/... -> one line each
(R-NONREIMB later disallows them in full: shown, never dropped, policy §4).
Tax is spread on every item at the invoice rate; the rounding difference goes on the lodging line
so the lines add up EXACTLY to the invoice total.
"""
import datetime as dt
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from ..money import format_inr
from .extract import Doc, ItemP

DINING_WORDS = ("dining", "restaurant", "room service", "food", "breakfast", "lunch", "dinner", "meal")
ROOM_WORDS = ("room charge", "room rent", "room tariff", "tariff", "accommodation", "room")


@dataclass
class FolioLine:
    kind: str  # room | meals | other
    description: str
    base_paise: int
    tax_paise: int = 0
    date: dt.date | None = None
    nights: int | None = None
    check_in: dt.date | None = None
    check_out: dt.date | None = None


def categorise(description: str) -> str:
    d = description.lower()
    if any(w in d for w in DINING_WORDS):  # checked first: "In Room Dining" is not a room charge
        return "meals"
    if any(w in d for w in ROOM_WORDS):
        return "room"
    return "other"


def _room_total(items: list[ItemP]) -> int:
    return sum(i.amount_paise for i in items if categorise(i.description) == "room")


def _taxes_total(doc: Doc) -> int:
    return sum(t.amount_paise for t in doc.taxes)


def reconciles(items: list[ItemP], doc: Doc) -> bool:
    """Do the items add up to the invoice subtotal (total - taxes)?"""
    if not items or doc.total_paise is None:
        return False
    return sum(i.amount_paise for i in items) == doc.total_paise - _taxes_total(doc)


def _pick_source(invoice: Doc, body: Doc | None, voucher_room_paise: int | None):
    """Image first; if its room items are damaged (fold) fall back to the email body's figures."""
    body_for_check = None
    if body is not None:
        body_for_check = body.model_copy(update={
            "total_paise": body.total_paise if body.total_paise is not None else invoice.total_paise,
            "taxes": body.taxes or invoice.taxes})
    candidates = [("invoice image", invoice.line_items, invoice)]
    if body_for_check is not None and body.line_items:
        candidates.append(("email body", body.line_items, body_for_check))
    for name, items, doc in candidates:  # best: reconciles AND matches the booking voucher tariff
        if reconciles(items, doc) and (voucher_room_paise is None or _room_total(items) == voucher_room_paise):
            return name, items
    for name, items, doc in candidates:
        if reconciles(items, doc):
            return name, items
    return "invoice image (unreconciled)", invoice.line_items


def _norm(text: str) -> str:
    return "".join(c for c in text.lower() if c.isalnum())


def _fill_dates(items: list[ItemP], reference: list[ItemP]) -> list[ItemP]:
    """Body figures are aggregated and undated; borrow the date from the matching image item."""
    out = []
    for it in items:
        date = it.date
        if date is None:
            same = [r for r in reference if r.date and _norm(r.description) == _norm(it.description)]
            date = same[0].date if same else None
        out.append(it.model_copy(update={"date": date}))
    return out


def _tax_rate(invoice: Doc, subtotal: int) -> Decimal:
    rates = [t.rate_pct for t in invoice.taxes]
    if rates and all(r is not None for r in rates) and sum(rates) > 0:
        return Decimal(str(sum(rates))) / 100  # CGST + SGST
    tax = _taxes_total(invoice)
    return Decimal(tax) / Decimal(subtotal) if subtotal else Decimal(0)


def _tax_on(base_paise: int, rate: Decimal) -> int:
    return int((Decimal(base_paise) * rate).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _nights(invoice: Doc, body: Doc | None) -> int | None:
    for d in (invoice, body):
        if d is None:
            continue
        if d.nights:
            return d.nights
        if d.check_in and d.check_out:
            return (d.check_out - d.check_in).days
    return None


def split_folio(invoice: Doc, body: Doc | None = None, voucher_room_paise: int | None = None) -> list[FolioLine]:
    source, items = _pick_source(invoice, body, voucher_room_paise)
    items = _fill_dates(items, invoice.line_items)
    subtotal = sum(i.amount_paise for i in items)
    rate = _tax_rate(invoice, subtotal)
    tax_actual = _taxes_total(invoice) or (_taxes_total(body) if body else 0)

    room_base = _room_total(items)
    src_note = f"source: {source}"
    if voucher_room_paise is not None:
        ok = "matches" if room_base == voucher_room_paise else "DIFFERS from"
        src_note += f"; {ok} booking voucher tariff {format_inr(voucher_room_paise)}"

    ci = invoice.check_in or (body.check_in if body else None)
    co = invoice.check_out or (body.check_out if body else None)
    nights = _nights(invoice, body)
    lines: list[FolioLine] = []
    if room_base:
        lines.append(FolioLine("room", f"Room charges, {nights or '?'} nights ({src_note})", room_base,
                               date=ci, nights=nights, check_in=ci, check_out=co))
    for it in items:
        kind = categorise(it.description)
        if kind != "room":
            lines.append(FolioLine(kind, it.description, it.amount_paise, date=it.date or co or ci))
    for ln in lines:
        ln.tax_paise = _tax_on(ln.base_paise, rate)
    if tax_actual and lines:  # rounding difference lands on the lodging line (or the first line)
        diff = tax_actual - sum(ln.tax_paise for ln in lines)
        lines[0].tax_paise += diff
    return lines
