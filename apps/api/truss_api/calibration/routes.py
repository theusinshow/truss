from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from truss_api.calibration import repository
from truss_api.calibration.exporter import export_run
from truss_api.calibration.models import (
    CalibrationDecisionCreate,
    CalibrationProposal,
    CalibrationRun,
    CalibrationRunDetail,
)
from truss_api.calibration.preview import CalibrationPreviewError, render_evidence_preview
from truss_api.core.settings import Settings, get_settings


router = APIRouter(prefix="/calibration", tags=["calibration"])


@router.get("/runs", response_model=list[CalibrationRun])
def list_runs(settings: Settings = Depends(get_settings)):
    return repository.list_runs(settings)


@router.get("/runs/{run_id}", response_model=CalibrationRunDetail)
def get_run(run_id: str, settings: Settings = Depends(get_settings)):
    try:
        return repository.get_run(run_id, settings)
    except repository.CalibrationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Calibration run not found") from error


@router.get("/proposals", response_model=list[CalibrationProposal])
def list_proposals(
    run_id: str | None = None,
    state: str | None = None,
    proposal_kind: str | None = None,
    rule_id: str | None = None,
    settings: Settings = Depends(get_settings),
):
    proposals = repository.list_proposals(settings, run_id)
    return [
        proposal for proposal in proposals
        if (state is None or proposal["state"] == state)
        and (proposal_kind is None or proposal["proposal_kind"] == proposal_kind)
        and (rule_id is None or proposal["rule_id"] == rule_id)
    ]


@router.get("/proposals/{proposal_id}", response_model=CalibrationProposal)
def get_proposal(proposal_id: str, settings: Settings = Depends(get_settings)):
    try:
        return repository.get_proposal(proposal_id, settings)
    except repository.CalibrationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Calibration proposal not found") from error


@router.post("/proposals/{proposal_id}/decisions", response_model=CalibrationProposal, status_code=status.HTTP_201_CREATED)
def decide_proposal(proposal_id: str, payload: CalibrationDecisionCreate, settings: Settings = Depends(get_settings)):
    try:
        return repository.decide(proposal_id, payload.decision, payload.reason, settings)
    except repository.CalibrationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Calibration proposal not found") from error
    except repository.CalibrationDecisionConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.delete("/proposal-decisions/{decision_id}", response_model=CalibrationProposal)
def revoke_decision(decision_id: str, settings: Settings = Depends(get_settings)):
    try:
        return repository.revoke_decision(decision_id, settings)
    except repository.CalibrationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Calibration decision not found") from error


@router.get("/evidence/{evidence_id}/preview", response_class=FileResponse)
def evidence_preview(evidence_id: str, settings: Settings = Depends(get_settings)):
    try:
        return FileResponse(render_evidence_preview(evidence_id, settings), media_type="image/png")
    except repository.CalibrationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Calibration evidence not found") from error
    except CalibrationPreviewError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/runs/{run_id}/exports", response_class=FileResponse)
def create_export(run_id: str, settings: Settings = Depends(get_settings)):
    try:
        path = export_run(run_id, settings)
    except repository.CalibrationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Calibration run not found") from error
    return FileResponse(path, media_type="application/zip", filename=path.name)
