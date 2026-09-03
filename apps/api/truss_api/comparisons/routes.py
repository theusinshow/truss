from fastapi import APIRouter, Depends, status

from truss_api.comparisons import orchestrator, repository
from truss_api.comparisons.models import (
    ComparisonPairing,
    ComparisonPairingCreate,
    RevisionComparison,
    RevisionComparisonCreate,
)
from truss_api.core.settings import Settings, get_settings


router = APIRouter(tags=["comparisons"])


@router.post(
    "/projects/{project_id}/revision-comparisons",
    response_model=RevisionComparison,
    status_code=status.HTTP_201_CREATED,
)
def create_revision_comparison(
    project_id: str,
    payload: RevisionComparisonCreate,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    return orchestrator.create_comparison(
        project_id=project_id,
        base_revision_id=payload.base_revision_id,
        target_revision_id=payload.target_revision_id,
        settings=settings,
    )


@router.get(
    "/revision-comparisons/{comparison_id}", response_model=RevisionComparison
)
def get_revision_comparison(
    comparison_id: str, settings: Settings = Depends(get_settings)
) -> dict[str, object]:
    return repository.get_comparison(comparison_id, settings)


@router.post(
    "/projects/{project_id}/comparison-pairings",
    response_model=ComparisonPairing,
    status_code=status.HTTP_201_CREATED,
)
def create_comparison_pairing(
    project_id: str,
    payload: ComparisonPairingCreate,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    return repository.create_pairing(
        project_id=project_id,
        base_revision_id=payload.base_revision_id,
        target_revision_id=payload.target_revision_id,
        base_sheet_id=payload.base_sheet_id,
        target_sheet_id=payload.target_sheet_id,
        settings=settings,
    )


@router.delete(
    "/comparison-pairings/{pairing_id}", response_model=ComparisonPairing
)
def revoke_comparison_pairing(
    pairing_id: str, settings: Settings = Depends(get_settings)
) -> dict[str, object]:
    return repository.revoke_pairing(pairing_id, settings)
