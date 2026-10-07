"""Deterministic triage of extracted documents (CLAUDE.md §9 step 3).

The LLM proposed the fields; THIS module decides used / excluded / ignored, first match wins.
Every outcome carries a human-readable reason and a policy reference. No DB access here.
"""
import datetime as dt
import re
from dataclasses import dataclass, field

from .extract import Doc
from .folio import split_folio

AIR_WORDS = ("indigo", "air india", "vistara", "spicejet", "akasa", "airline", "airways", "flight", "pnr", "6e-")
HOTEL_WORDS = ("hotel", "inn", "resort", "suites", "lodge", "residency", "hospitality")
CAB_WORDS = ("uber", "ola", "rapido", "lyft", "meru", "taxi", "cab")
FOOD_WORDS = ("restaurant", "terrace", "cafe", "café", "dhaba", "kitchen", "grill", "bistro", "eatery",
              "swiggy", "zomato", "food", "diner", "biryani", "tandoor")
HOSTING_RE = re.compile(r"\b(customer|client|team|dinner with|lunch with|hosted)\b", re.I)
TITLES = {"mr", "mrs", "ms", "miss", "dr", "shri", "smt"}


@dataclass
class LineDraft:
    section: str
    head: str
    description: str
    merchant: str = ""
    date: dt.date | None = None
    time: str | None = None
    bill_no: str | None = None
    from_place: str | None = None
    to_place: str | None = None
    city: str | None = None
    check_in: dt.date | None = None
    check_out: dt.date | None = None
    nights: int | None = None
    paid_by: str = "Employee"
    base_paise: int = 0
    tax_paise: int = 0
    attendees_json: str | None = None
    fingerprint: str | None = None

    @property
    def amount_paise(self) -> int:
        return self.base_paise + self.tax_paise


@dataclass
class Outcome:
    triage: str  # used | excluded | ignored
    reason: str
    policy_ref: str | None = None
    lines: list[LineDraft] = field(default_factory=list)


@dataclass
class Context:
    claimant_name: str
    other_employee_names: list[str]
    destination_city: str | None = None
    filename: str = ""
    seen: dict[str, str] = field(default_factory=dict)  # fingerprint -> filename of earlier document
    cover_note: str | None = None  # text of the covering email, if any
    cover_doc: Doc | None = None  # extraction of the covering email body
    voucher_room_paise: int | None = None  # booking voucher tariff, for the folio cross-check


# ---- helpers ----
def fingerprint_of(merchant, bill_no, date, time, amount_paise) -> str:
    try:
        from ..policy.rules import fingerprint  # the shared one (policy §5.3)
        return fingerprint(merchant or "", bill_no, date, time, amount_paise)
    except ImportError:
        norm = lambda s: re.sub(r"[^a-z0-9]", "", (s or "").lower())  # noqa: E731
        if bill_no:
            return norm(merchant) + norm(bill_no)
        return f"{norm(merchant)}{date}{time or ''}{amount_paise}"


def _has(text: str | None, words) -> bool:
    t = (text or "").lower()
    return any(re.search(r"(?<![a-z])" + re.escape(w), t) for w in words)  # word start, so "ola" != "kolkata"


def _tokens(name: str | None) -> list[str]:
    return [t for t in re.findall(r"[a-z]+", (name or "").lower()) if t not in TITLES]


def name_matches(person: str | None, full_name: str) -> bool:
    """Case-insensitive match on the claimant's first or full name (known limitation: same first name)."""
    p, c = _tokens(person), _tokens(full_name)
    return bool(p and c and (c[0] in p or p == c))


def _is_air(doc: Doc) -> bool:
    return _has(doc.merchant, AIR_WORDS) or any(_has(i.description, AIR_WORDS) for i in doc.line_items)


def _is_hotel(doc: Doc) -> bool:
    from .folio import categorise
    return bool(doc.check_in or doc.nights or _has(doc.merchant, HOTEL_WORDS)
                or any(categorise(i.description) == "room" for i in doc.line_items))


def _is_food(doc: Doc) -> bool:
    return doc.covers is not None or _has(doc.merchant, FOOD_WORDS)


def _is_cab(doc: Doc) -> bool:
    return _has(doc.merchant, CAB_WORDS) or bool(doc.from_place and doc.to_place)


def _tax_split(doc: Doc) -> tuple[int, int]:
    """(base, tax) for a single-amount document: tax is what the taxes list says, base is the rest."""
    total = doc.total_paise or 0
    tax = sum(t.amount_paise for t in doc.taxes)
    return (total - tax, tax) if 0 <= tax <= total else (total, 0)


# ---- line builders ----
def _air_lines(doc: Doc) -> list[LineDraft]:
    """One memo line per sector (policy §3.2: flights are booked and billed through the travel desk)."""
    items = doc.line_items or []
    lines = []
    for it in items:
        m = re.search(r"([A-Za-z ]+?)\s*(?:-|–|→|to)\s*([A-Za-z ]+)", it.description.split(",")[0])
        frm, to = (m.group(1).strip(), m.group(2).strip()) if m else (doc.from_place, doc.to_place)
        lines.append(LineDraft("transport", "air", it.description, doc.merchant or "Airline", it.date or doc.date,
                               from_place=frm, to_place=to, base_paise=it.amount_paise))
    if not lines:
        lines.append(LineDraft("transport", "air", f"Flight {doc.from_place or ''} - {doc.to_place or ''}".strip(),
                               doc.merchant or "Airline", doc.date, from_place=doc.from_place,
                               to_place=doc.to_place, base_paise=doc.total_paise or 0))
    return lines


def _folio_lines(doc: Doc, ctx: Context) -> list[LineDraft]:
    merchant = doc.merchant or "Hotel"
    lines = []
    for fl in split_folio(doc, ctx.cover_doc, ctx.voucher_room_paise):
        suffix = {"room": "room", "meals": "dining"}.get(fl.kind, re.sub(r"\W+", "", fl.description.lower()))
        bill = f"{doc.bill_no}-{suffix}" if doc.bill_no else None  # distinct per folio line so R-DUP can't self-collide
        if fl.kind == "room":
            lines.append(LineDraft("lodging", "lodging", fl.description, merchant, fl.date, bill_no=bill,
                                   city=ctx.destination_city, check_in=fl.check_in, check_out=fl.check_out,
                                   nights=fl.nights, base_paise=fl.base_paise, tax_paise=fl.tax_paise))
        else:
            head = "meals" if fl.kind == "meals" else "misc"
            lines.append(LineDraft("other", head, fl.description, merchant, fl.date, bill_no=bill,
                                   base_paise=fl.base_paise, tax_paise=fl.tax_paise))
    return lines


def _entertainment_line(doc: Doc, ctx: Context) -> LineDraft:
    base, tax = _tax_split(doc)
    note = (ctx.cover_doc.context_note if ctx.cover_doc else None) or doc.context_note \
        or f"Business meal at {doc.merchant}"
    return LineDraft("other", "business_entertainment", note, doc.merchant or "", doc.date, doc.time,
                     bill_no=doc.bill_no, base_paise=base, tax_paise=tax,
                     attendees_json="[]")  # empty on purpose: R-ENT-ATT blocks until the employee adds them


def _cab_line(doc: Doc) -> LineDraft:
    base, tax = _tax_split(doc)
    desc = f"{doc.merchant or 'Cab'}: {doc.from_place or '?'} → {doc.to_place or '?'}"
    return LineDraft("transport", "cab", desc, doc.merchant or "", doc.date, doc.time, bill_no=doc.bill_no,
                     from_place=doc.from_place, to_place=doc.to_place, base_paise=base, tax_paise=tax)


def _simple_line(doc: Doc, section: str, head: str, desc: str) -> LineDraft:
    base, tax = _tax_split(doc)
    return LineDraft(section, head, desc, doc.merchant or "", doc.date, doc.time, bill_no=doc.bill_no,
                     base_paise=base, tax_paise=tax)


def _build_lines(doc: Doc, ctx: Context) -> tuple[list[LineDraft], str, str | None]:
    """Rules 7-11 line building. Returns (lines, reason, policy_ref)."""
    if _is_air(doc):  # policy §3.2
        return _air_lines(doc), "Airline ticket: one line per sector", "§3.2"
    if _is_hotel(doc) and (doc.doc_type == "tax_invoice" or doc.line_items):  # rule 8
        return _folio_lines(doc, ctx), "Hotel tax invoice split into folio lines", "§3.1"
    if _is_food(doc):
        context = " ".join(filter(None, [doc.context_note, ctx.cover_note]))
        if (doc.covers or 0) > 1 or HOSTING_RE.search(context):  # rule 9, policy §3.5
            return [_entertainment_line(doc, ctx)], "Hosted meal: claimed as business entertainment", "§3.5"
        return [_simple_line(doc, "other", "meals", f"Meal at {doc.merchant}")], "Meal receipt", "§3.3"
    if _is_cab(doc):  # rule 10, policy §3.4
        return [_cab_line(doc)], "Cab ride", "§3.4"
    return ([_simple_line(doc, "other", "misc", f"Review category: {doc.merchant or 'expense'}")],
            "Expense with an amount; category needs review", "§5.2")  # rule 11


# ---- the rules, in order ----
def triage_document(doc: Doc, ctx: Context) -> Outcome:
    out = _non_expense(doc) or _not_claimable(doc, ctx)
    if out:
        return out
    fp = fingerprint_of(doc.merchant, doc.bill_no, doc.date, doc.time, doc.total_paise or 0)
    if fp in ctx.seen:  # rule 6, policy §5.3
        return Outcome("excluded", f"Duplicate of {ctx.seen[fp]}", "§5.3")
    if doc.total_paise is None and not doc.line_items:
        return Outcome("ignored", "No amount found — add the line manually")
    lines, reason, ref = _build_lines(doc, ctx)
    company = doc.payment_method == "corporate_card"  # rule 7
    for ln in lines:
        if company:
            ln.paid_by = "Company"
        ln.fingerprint = fingerprint_of(ln.merchant, ln.bill_no, ln.date, ln.time, ln.amount_paise)
    ctx.seen[fp] = ctx.filename
    if company:
        return Outcome("used", f"Paid on company card: memo line(s), not reimbursed. {reason}", "§3.2", lines)
    return Outcome("used", reason, ref, lines)


def _non_expense(doc: Doc) -> Outcome | None:
    if doc.doc_type in ("promotional", "other"):  # rule 1
        return Outcome("ignored", "Not an expense document")
    if doc.doc_type in ("travel_approval", "advance_notice"):  # rule 2
        return Outcome("ignored", "Reference only — request and advance are tracked in the app")
    return None


def _not_claimable(doc: Doc, ctx: Context) -> Outcome | None:
    # rule 3: voucher, not a bill. (A corporate-card e-ticket is a paid document, handled by rule 7.)
    if doc.doc_type == "booking_confirmation" and doc.payment_method != "corporate_card":
        remember_voucher(doc, ctx)
        return Outcome("excluded", "Booking voucher, not a bill; the tax invoice is the proof", "§5.2")
    if doc.doc_type == "payment_failed":  # rule 4
        return Outcome("excluded", "Payment failed — nothing was paid", "§5.2")
    if doc.person_name and not name_matches(doc.person_name, ctx.claimant_name):  # rule 5
        return Outcome("excluded", f"Expense of another person ({doc.person_name})", "§4")
    if doc.forwarded_by and not name_matches(doc.forwarded_by, ctx.claimant_name) \
            and any(name_matches(doc.forwarded_by, n) for n in ctx.other_employee_names):
        return Outcome("excluded", f"Expense of another person ({doc.forwarded_by})", "§4")
    return None


def remember_voucher(doc: Doc, ctx: Context) -> None:
    """Keep the voucher's room tariff for the folio cross-check (never a claim line)."""
    room = [i.amount_paise for i in doc.line_items if "room" in i.description.lower() or "tariff" in i.description.lower()]
    taxes = sum(t.amount_paise for t in doc.taxes)
    ctx.voucher_room_paise = max(room) if room else (doc.total_paise - taxes if doc.total_paise else None)
