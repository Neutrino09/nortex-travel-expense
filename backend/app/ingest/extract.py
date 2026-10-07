"""Document extraction (CLAUDE.md §9 step 2).

The LLM proposes: it only reads fields off a document, never applies policy.
Results are cached by sha256 in settings.fixtures_dir/<sha256>.json so tests and the demo are offline.
Amounts are converted to integer paise immediately (Doc), so nothing downstream sees rupee floats.
"""
import base64
import datetime as dt
import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..config import get_settings
from ..money import rupees_to_paise

DocType = Literal["receipt", "tax_invoice", "booking_confirmation", "payment_failed",
                  "travel_approval", "advance_notice", "promotional", "other"]
PaymentMethod = Literal["personal_card", "corporate_card", "pay_at_property", "cash", "unknown"]

UNAVAILABLE_REASON = "Extraction unavailable — add the line manually"

SYSTEM_PROMPT = ("Extract only what is visible. Do not apply any expense policy. "
                 "Use null when unsure. Amounts are numbers in rupees.")


# ---- raw model output (rupees) ----
class RawLineItem(BaseModel):
    date: dt.date | None = None
    description: str
    amount: float


class RawTax(BaseModel):
    label: str
    rate_pct: float | None = None
    amount: float


class Extraction(BaseModel):
    """record_document, as the model returns it. Extra keys (e.g. _source) are tolerated."""
    model_config = ConfigDict(extra="ignore")
    doc_type: DocType
    merchant: str | None = None
    bill_no: str | None = None
    date: dt.date | None = None
    time: str | None = None
    currency: str | None = None
    total: float | None = None
    payment_method: PaymentMethod = "unknown"
    person_name: str | None = None
    is_forwarded: bool = False
    forwarded_by: str | None = None
    from_place: str | None = None
    to_place: str | None = None
    check_in: dt.date | None = None
    check_out: dt.date | None = None
    nights: int | None = None
    covers: int | None = None
    line_items: list[RawLineItem] = Field(default_factory=list)
    taxes: list[RawTax] = Field(default_factory=list)
    context_note: str | None = None


# ---- normalised document (paise) ----
class ItemP(BaseModel):
    date: dt.date | None = None
    description: str
    amount_paise: int


class TaxP(BaseModel):
    label: str
    rate_pct: float | None = None
    amount_paise: int


class Doc(BaseModel):
    doc_type: str
    merchant: str | None = None
    bill_no: str | None = None
    date: dt.date | None = None
    time: str | None = None
    total_paise: int | None = None
    payment_method: str = "unknown"
    person_name: str | None = None
    is_forwarded: bool = False
    forwarded_by: str | None = None
    from_place: str | None = None
    to_place: str | None = None
    check_in: dt.date | None = None
    check_out: dt.date | None = None
    nights: int | None = None
    covers: int | None = None
    line_items: list[ItemP] = Field(default_factory=list)
    taxes: list[TaxP] = Field(default_factory=list)
    context_note: str | None = None


def to_doc(ex: Extraction) -> Doc:
    """Rupees -> paise, once, at the boundary."""
    data = ex.model_dump(exclude={"total", "line_items", "taxes", "currency"})
    return Doc(
        **data,
        total_paise=None if ex.total is None else rupees_to_paise(ex.total),
        line_items=[ItemP(date=i.date, description=i.description, amount_paise=rupees_to_paise(i.amount))
                    for i in ex.line_items],
        taxes=[TaxP(label=t.label, rate_pct=t.rate_pct, amount_paise=rupees_to_paise(t.amount)) for t in ex.taxes],
    )


# ---- JSON schema for Structured Outputs (strict: all props required, nullable for optional) ----
def _nullable(t: str, **extra) -> dict:
    return {"type": [t, "null"], **extra}


def record_document_schema() -> dict:
    props = {
        "doc_type": {"type": "string", "enum": list(DocType.__args__)},
        "merchant": _nullable("string"),
        "bill_no": _nullable("string"),
        "date": _nullable("string", description="YYYY-MM-DD"),
        "time": _nullable("string", description="HH:MM 24h"),
        "currency": _nullable("string"),
        "total": _nullable("number"),
        "payment_method": {"type": "string", "enum": list(PaymentMethod.__args__)},
        "person_name": _nullable("string", description="guest / rider / passenger the bill is for"),
        "is_forwarded": {"type": "boolean"},
        "forwarded_by": _nullable("string"),
        "from_place": _nullable("string"),
        "to_place": _nullable("string"),
        "check_in": _nullable("string", description="YYYY-MM-DD"),
        "check_out": _nullable("string", description="YYYY-MM-DD"),
        "nights": _nullable("integer"),
        "covers": _nullable("integer"),
        "line_items": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"date": _nullable("string"), "description": {"type": "string"},
                           "amount": {"type": "number"}},
            "required": ["date", "description", "amount"]}},
        "taxes": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"label": {"type": "string"}, "rate_pct": _nullable("number"),
                           "amount": {"type": "number"}},
            "required": ["label", "rate_pct", "amount"]}},
        "context_note": _nullable("string"),
    }
    return {"type": "object", "additionalProperties": False, "properties": props, "required": list(props)}


# ---- cache ----
def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cache_path(sha: str):
    return get_settings().fixtures_dir / f"{sha}.json"


def load_cached(sha: str) -> Extraction | None:
    path = cache_path(sha)
    if not path.is_file():
        return None
    return Extraction.model_validate_json(path.read_text())


def save_cached(sha: str, ex: Extraction, filename: str | None = None) -> None:
    path = cache_path(sha)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = ex.model_dump(mode="json")
    if filename:
        data["_filename"] = filename
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


# ---- the LLM call ----
def llm_available() -> bool:
    s = get_settings()
    return bool(s.openai_api_key and s.openai_model)


def _user_content(text: str | None, image: bytes | None, mime: str) -> list[dict]:
    if image is not None:
        url = f"data:{mime};base64,{base64.b64encode(image).decode()}"
        return [{"type": "text", "text": "Extract this document."},
                {"type": "image_url", "image_url": {"url": url}}]
    return [{"type": "text", "text": text or ""}]


def call_llm(text: str | None, image: bytes | None = None, mime: str = "image/png") -> Extraction:
    """One Structured Outputs call. Network happens ONLY here."""
    from openai import BadRequestError, OpenAI  # imported lazily: tests never reach this
    s = get_settings()
    client = OpenAI(api_key=s.openai_api_key)
    kwargs = dict(
        model=s.openai_model,
        messages=[{"role": "system", "content": SYSTEM_PROMPT},
                  {"role": "user", "content": _user_content(text, image, mime)}],
        response_format={"type": "json_schema", "json_schema": {
            "name": "record_document", "strict": True, "schema": record_document_schema()}},
    )
    try:
        resp = client.chat.completions.create(temperature=0, **kwargs)
    except BadRequestError as e:
        if "temperature" not in str(e).lower():
            raise
        resp = client.chat.completions.create(**kwargs)  # model rejects temperature: drop it
    return Extraction.model_validate_json(resp.choices[0].message.content)


def extract(sha: str, text: str | None = None, image: bytes | None = None, mime: str = "image/png",
            filename: str | None = None) -> Extraction | None:
    """Cache first; then the LLM if configured; else None (caller marks the document 'ignored')."""
    cached = load_cached(sha)
    if cached is not None:
        return cached
    if not llm_available():
        return None
    try:
        ex = call_llm(text, image, mime)
    except Exception:
        return None  # network/model failure degrades to manual entry, never crashes the import
    save_cached(sha, ex, filename)
    return ex
