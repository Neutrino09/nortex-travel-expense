"""The two import endpoints (CLAUDE.md §9). main.py mounts this under /api."""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session

from .auth import current_user
from .db import get_session
from .ingest.importer import SUPPORTED, import_files, sample_files
from .models import Employee, Settlement
from .schemas import ImportResult
from pathlib import Path

router = APIRouter(tags=["import"])
EDITABLE = {"draft", "returned"}


def _own_editable_settlement(session: Session, settlement_id: int, user: Employee) -> Settlement:
    s = session.get(Settlement, settlement_id)
    if s is None:
        raise HTTPException(404, "Settlement not found")
    if s.emp_code != user.emp_code:  # only the claimant imports evidence
        raise HTTPException(403, "Only the claimant can import evidence")
    if s.status not in EDITABLE:
        raise HTTPException(409, f"Settlement is {s.status}; evidence can only be imported while draft or returned")
    return s


@router.post("/settlements/{settlement_id}/import", response_model=ImportResult)
def import_upload(settlement_id: int, files: list[UploadFile] = File(...),
                  user: Employee = Depends(current_user), session: Session = Depends(get_session)):
    s = _own_editable_settlement(session, settlement_id, user)
    bad = [f.filename for f in files if Path(f.filename or "").suffix.lower() not in SUPPORTED]
    if bad:
        raise HTTPException(400, f"Unsupported file type: {', '.join(bad)} (use .eml, .png, .jpg)")
    return import_files(session, s, [(f.filename, f.file.read()) for f in files])


@router.post("/settlements/{settlement_id}/import-sample", response_model=ImportResult)
def import_sample(settlement_id: int, user: Employee = Depends(current_user),
                  session: Session = Depends(get_session)):
    s = _own_editable_settlement(session, settlement_id, user)
    return import_files(session, s, sample_files())
