from fastapi import APIRouter, Depends, HTTPException, status

from truss_api.audit import repository
from truss_api.audit.models import AuditRun, Finding, FindingStatusUpdate, ManualFindingCreate
from truss_api.audit.orchestrator import run_deterministic_audit
from truss_api.core.settings import Settings, get_settings
from truss_api.documents.repository import SheetNotFoundError


router = APIRouter(tags=["audit"])


@router.post("/sheets/{sheet_id}/audit-runs", response_model=AuditRun, status_code=status.HTTP_201_CREATED)
def create_audit_run(sheet_id: str, settings: Settings = Depends(get_settings)) -> dict[str, object]:
    try:
        return run_deterministic_audit(sheet_id, settings)
    except SheetNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sheet not found") from error


@router.get("/sheets/{sheet_id}/findings", response_model=list[Finding])
def list_sheet_findings(
    sheet_id: str,
    settings: Settings = Depends(get_settings),
) -> list[dict[str, object]]:
    return repository.list_findings_for_sheet(sheet_id, settings)


@router.post("/sheets/{sheet_id}/findings", response_model=Finding, status_code=status.HTTP_201_CREATED)
def create_manual_finding(
    sheet_id: str,
    payload: ManualFindingCreate,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    try:
        return repository.create_manual_finding(sheet_id, payload, settings)
    except SheetNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sheet not found") from error


@router.patch("/findings/{finding_id}", response_model=Finding)
def update_finding_status(
    finding_id: str,
    payload: FindingStatusUpdate,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    try:
        return repository.update_finding_status(finding_id, payload, settings)
    except repository.FindingNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found") from error
