"""Import orchestration: files -> Evidence rows -> extraction -> triage -> ClaimLines (CLAUDE.md §9).

Idempotent per (owner, sha256): re-importing a file creates nothing new.
"""
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlmodel import Session, select

from ..config import get_settings
from ..models import ClaimLine, Employee, Evidence, Settlement, TravelRequest
from ..schemas import EvidenceOut, ImportResult
from . import extract as ex
from .eml import IMAGE_EXTS, ParsedEmail, parse_eml
from .triage import Context, LineDraft, Outcome, remember_voucher, triage_document

SUPPORTED = {".eml", *IMAGE_EXTS}


@dataclass
class Unit:
    """One uploaded file: an email (with attachments) or a standalone image."""
    filename: str
    raw: bytes
    email: ParsedEmail | None = None

    @property
    def date(self) -> datetime | None:
        return self.email.date if self.email else None


def _units(files: list[tuple[str, bytes]]) -> list[Unit]:
    units = []
    for name, raw in files:
        ext = Path(name).suffix.lower()
        if ext == ".eml":
            units.append(Unit(Path(name).name, raw, parse_eml(raw)))
        elif ext in IMAGE_EXTS:
            units.append(Unit(Path(name).name, raw))
    # §9: sort by email Date so the original is processed before a resend (undated images go last)
    return sorted(units, key=lambda u: (u.date is None, u.date or datetime.min))


def _find_existing(session: Session, owner: str, sha: str) -> Evidence | None:
    return session.exec(select(Evidence).where(Evidence.owner_emp_code == owner, Evidence.sha256 == sha)).first()


def _store_file(owner: str, sha: str, filename: str, raw: bytes) -> str:
    path = get_settings().storage_dir / owner / f"{sha}{Path(filename).suffix.lower()}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return str(path.resolve())


def _new_evidence(session: Session, settlement: Settlement, filename: str, raw: bytes, kind: str,
                  email_date: datetime | None = None, parent_id: int | None = None) -> Evidence:
    sha = ex.sha256_of(raw)
    ev = Evidence(owner_emp_code=settlement.emp_code, settlement_id=settlement.id, filename=filename, kind=kind,
                  sha256=sha, storage_path=_store_file(settlement.emp_code, sha, filename, raw),
                  parent_evidence_id=parent_id, email_date=email_date)
    session.add(ev)
    session.flush()
    return ev


def _extract_doc(ev: Evidence, text: str | None = None, image: bytes | None = None, mime: str = "image/png"):
    """Cached/LLM extraction -> Doc in paise, or None when unavailable."""
    raw = ex.extract(ev.sha256, text=text, image=image, mime=mime, filename=ev.filename)
    return ex.to_doc(raw) if raw is not None else None


def _apply(ev: Evidence, doc: ex.Doc | None, out: Outcome) -> None:
    ev.extracted_json = doc.model_dump_json() if doc else None
    ev.doc_type = doc.doc_type if doc else None
    ev.triage, ev.triage_reason, ev.policy_ref = out.triage, out.reason, out.policy_ref


UNAVAILABLE = Outcome("ignored", ex.UNAVAILABLE_REASON)


def _make_context(session: Session, settlement: Settlement) -> Context:
    claimant = session.get(Employee, settlement.emp_code)
    request = session.get(TravelRequest, settlement.request_id)
    others = [e.name for e in session.exec(select(Employee)).all() if e.emp_code != claimant.emp_code]
    ctx = Context(claimant_name=claimant.name, other_employee_names=others,
                  destination_city=request.destination_city if request else None)
    # documents already imported earlier: fingerprints seen, and any booking voucher tariff
    rows = session.exec(select(ClaimLine, Evidence).where(
        ClaimLine.settlement_id == settlement.id, ClaimLine.evidence_id == Evidence.id)).all()
    for line, ev in rows:
        if line.fingerprint:
            ctx.seen[line.fingerprint] = ev.filename
    vouchers = session.exec(select(Evidence).where(Evidence.settlement_id == settlement.id,
                                                   Evidence.doc_type == "booking_confirmation")).all()
    for ev in vouchers:
        if ev.extracted_json:
            remember_voucher(ex.Doc.model_validate_json(ev.extracted_json), ctx)
    return ctx


def _save_lines(session: Session, settlement: Settlement, drafts: list[LineDraft], evidence_id: int) -> int:
    for d in drafts:
        session.add(ClaimLine(
            settlement_id=settlement.id, section=d.section, head=d.head, date=d.date, time=d.time,
            description=d.description, merchant=d.merchant, bill_no=d.bill_no, from_place=d.from_place,
            to_place=d.to_place, city=d.city, check_in=d.check_in, check_out=d.check_out, nights=d.nights,
            paid_by=d.paid_by, base_paise=d.base_paise, tax_paise=d.tax_paise, amount_paise=d.amount_paise,
            evidence_id=evidence_id, fingerprint=d.fingerprint, attendees_json=d.attendees_json, source="import"))
    return len(drafts)


def _process_standalone(session, settlement, ctx, ev: Evidence, doc, mime) -> int:
    out = UNAVAILABLE if doc is None else triage_document(doc, ctx)
    _apply(ev, doc, out)
    return _save_lines(session, settlement, out.lines, ev.id)


def _process_email_with_attachments(session, settlement, ctx, body_ev, body_doc, atts) -> int:
    """§9 pairs: the attachment is the primary proof; the body is context and 'used' as the cover."""
    ctx.cover_note = body_doc.context_note if body_doc else None
    ctx.cover_doc = body_doc
    created, primary_out, primary_name = 0, None, None
    for att_ev, att_doc in atts:
        ctx.filename = att_ev.filename
        out = UNAVAILABLE if att_doc is None else triage_document(att_doc, ctx)
        _apply(att_ev, att_doc, out)
        created += _save_lines(session, settlement, out.lines, att_ev.id)
        if primary_out is None or (out.triage == "used" and primary_out.triage != "used"):
            primary_out, primary_name = out, att_ev.filename
    if primary_out.triage == "used":
        _apply(body_ev, body_doc, Outcome("used", f"Covering email for {primary_name}", primary_out.policy_ref))
    else:
        _apply(body_ev, body_doc, Outcome(primary_out.triage, primary_out.reason, primary_out.policy_ref))
    return created


def _import_email(session, settlement, ctx, unit: Unit) -> tuple[int, int, int]:
    """Returns (new_documents, skipped, lines_created)."""
    if _find_existing(session, settlement.emp_code, ex.sha256_of(unit.raw)):
        return 0, 1 + len(unit.email.attachments), 0
    body_ev = _new_evidence(session, settlement, unit.filename, unit.raw, "email", unit.email.date)
    body_doc = _extract_doc(body_ev, text=unit.email.as_text())
    atts = []
    for a in unit.email.attachments:
        a_ev = _find_existing(session, settlement.emp_code, ex.sha256_of(a.content))
        if a_ev is None:
            a_ev = _new_evidence(session, settlement, a.filename, a.content, "image", unit.email.date, body_ev.id)
            atts.append((a_ev, _extract_doc(a_ev, image=a.content, mime=a.mime)))
    new_docs = 1 + len(atts)
    ctx.filename = unit.filename
    if atts and any(d is not None for _, d in atts):
        return new_docs, 0, _process_email_with_attachments(session, settlement, ctx, body_ev, body_doc, atts)
    ctx.cover_note, ctx.cover_doc = None, None
    lines = _process_standalone(session, settlement, ctx, body_ev, body_doc, None)
    for a_ev, _ in atts:  # attachments we could not read stay visible as ignored
        _apply(a_ev, None, UNAVAILABLE)
    return new_docs, 0, lines


def import_files(session: Session, settlement: Settlement, files: list[tuple[str, bytes]]) -> ImportResult:
    ctx = _make_context(session, settlement)
    new_docs = skipped = lines = 0
    for unit in _units(files):
        ctx.cover_note, ctx.cover_doc, ctx.filename = None, None, unit.filename
        if unit.email:
            n, s, l = _import_email(session, settlement, ctx, unit)
        elif _find_existing(session, settlement.emp_code, ex.sha256_of(unit.raw)):
            n, s, l = 0, 1, 0
        else:
            ev = _new_evidence(session, settlement, unit.filename, unit.raw, "image")
            mime = IMAGE_EXTS[Path(unit.filename).suffix.lower()]
            n, s, l = 1, 0, _process_standalone(session, settlement, ctx, ev, _extract_doc(ev, image=unit.raw, mime=mime), mime)
        new_docs, skipped, lines = new_docs + n, skipped + s, lines + l
    session.commit()
    return _result(session, settlement, new_docs, skipped, lines)


def _result(session: Session, settlement: Settlement, new_docs: int, skipped: int, lines: int) -> ImportResult:
    rows = session.exec(select(Evidence).where(Evidence.settlement_id == settlement.id)).all()
    rows.sort(key=lambda e: (e.email_date is None, e.email_date or datetime.min, e.id))
    counts = {k: sum(1 for e in rows if e.triage == k) for k in ("used", "excluded", "ignored")}
    return ImportResult(new_documents=new_docs, skipped_existing=skipped, lines_created=lines,
                        evidence=[evidence_out(e) for e in rows], **counts)


def evidence_out(e: Evidence) -> EvidenceOut:
    return EvidenceOut(id=e.id, filename=e.filename, kind=e.kind, parent_evidence_id=e.parent_evidence_id,
                       email_date=e.email_date, doc_type=e.doc_type, triage=e.triage,
                       triage_reason=e.triage_reason, policy_ref=e.policy_ref,
                       extracted=json.loads(e.extracted_json) if e.extracted_json else None)


def sample_files() -> list[tuple[str, bytes]]:
    """Every .eml in pack/sample_emails (attachments are resolved from pack/receipts by eml.py)."""
    folder = get_settings().pack_dir / "sample_emails"
    return [(p.name, p.read_bytes()) for p in sorted(folder.glob("*.eml"))]
