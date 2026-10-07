"""Settlements. Phase 1 stubs — Agent A implements everything except the two import endpoints
(those stay stubs here until Agent B's import_router.py is mounted in phase 3)."""
from fastapi import APIRouter, Depends, File, UploadFile
from sqlmodel import Session

from ..auth import current_user
from ..db import get_session
from ..models import Employee
from ..schemas import (ClaimLineIn, ClaimLineOut, ClaimLinePatch, ImportResult, SettlementCreate,
                       SettlementOut, SubmitOut, ValidationResult)

router = APIRouter(prefix="/settlements", tags=["settlements"])


@router.post("", response_model=SettlementOut, status_code=201)
def create_settlement(body: SettlementCreate, user: Employee = Depends(current_user),
                      session: Session = Depends(get_session)):
    raise NotImplementedError


@router.get("/{settlement_id}", response_model=SettlementOut)
def get_settlement(settlement_id: int, user: Employee = Depends(current_user),
                   session: Session = Depends(get_session)):
    raise NotImplementedError


@router.post("/{settlement_id}/lines", response_model=ClaimLineOut, status_code=201)
def add_line(settlement_id: int, body: ClaimLineIn, user: Employee = Depends(current_user),
             session: Session = Depends(get_session)):
    raise NotImplementedError


@router.patch("/{settlement_id}/lines/{line_id}", response_model=ClaimLineOut)
def patch_line(settlement_id: int, line_id: int, body: ClaimLinePatch,
               user: Employee = Depends(current_user), session: Session = Depends(get_session)):
    raise NotImplementedError


@router.delete("/{settlement_id}/lines/{line_id}", status_code=204)
def delete_line(settlement_id: int, line_id: int, user: Employee = Depends(current_user),
                session: Session = Depends(get_session)):
    raise NotImplementedError


@router.post("/{settlement_id}/import", response_model=ImportResult)
def import_files(settlement_id: int, files: list[UploadFile] = File(...),
                 user: Employee = Depends(current_user), session: Session = Depends(get_session)):
    raise NotImplementedError  # Agent B (ingest)


@router.post("/{settlement_id}/import-sample", response_model=ImportResult)
def import_sample(settlement_id: int, user: Employee = Depends(current_user),
                  session: Session = Depends(get_session)):
    raise NotImplementedError  # Agent B (ingest)


@router.post("/{settlement_id}/validate", response_model=ValidationResult)
def validate(settlement_id: int, user: Employee = Depends(current_user),
             session: Session = Depends(get_session)):
    raise NotImplementedError


@router.post("/{settlement_id}/submit", response_model=SubmitOut)
def submit(settlement_id: int, user: Employee = Depends(current_user),
           session: Session = Depends(get_session)):
    raise NotImplementedError


@router.post("/{settlement_id}/resubmit", response_model=SubmitOut)
def resubmit(settlement_id: int, user: Employee = Depends(current_user),
             session: Session = Depends(get_session)):
    raise NotImplementedError
