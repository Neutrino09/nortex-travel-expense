"""Parse .eml files with the stdlib (CLAUDE.md §9 step 1). No LLM here."""
import email
import email.policy
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

from ..config import get_settings

IMAGE_EXTS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


@dataclass
class Attachment:
    filename: str
    content: bytes
    mime: str


@dataclass
class ParsedEmail:
    sender: str
    to: str
    subject: str
    date: datetime | None  # naive local wall-clock time from the Date header
    body: str
    attachments: list[Attachment] = field(default_factory=list)

    def as_text(self) -> str:
        """What the extractor sees for the email body."""
        return f"From: {self.sender}\nTo: {self.to}\nSubject: {self.subject}\nDate: {self.date}\n\n{self.body}"


def _is_image_bytes(data: bytes) -> bool:
    return data.startswith(b"\x89PNG\r\n\x1a\n") or data.startswith(b"\xff\xd8\xff")


def _mime_for(filename: str) -> str:
    return IMAGE_EXTS.get(Path(filename).suffix.lower(), "image/png")


def _resolve_attachment(part) -> Attachment | None:
    filename = part.get_filename()
    if not filename:
        return None
    try:
        data = part.get_payload(decode=True) or b""
    except Exception:
        data = b""
    if not _is_image_bytes(data):
        # The pack's parts only hold a placeholder; load the real image from PACK_DIR/receipts.
        path = get_settings().pack_dir / "receipts" / Path(filename).name
        if not path.is_file():
            return None
        data = path.read_bytes()
    return Attachment(filename=Path(filename).name, content=data, mime=_mime_for(filename))


def _parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def parse_eml(raw: bytes) -> ParsedEmail:
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    body_part = msg.get_body(preferencelist=("plain",))
    body = body_part.get_content() if body_part is not None else ""
    attachments = []
    for part in msg.iter_attachments():
        att = _resolve_attachment(part)
        if att is not None:
            attachments.append(att)
    return ParsedEmail(
        sender=str(msg["From"] or ""), to=str(msg["To"] or ""), subject=str(msg["Subject"] or ""),
        date=_parse_date(msg["Date"]), body=body.strip(), attachments=attachments,
    )
