from fastapi import APIRouter, Depends, HTTPException, status

from truss_api.core.settings import Settings, get_settings
from truss_api.learning import repository
from truss_api.learning.models import (
    LearningDecisionCreate,
    LearningProposal,
)


router = APIRouter(prefix="/learning", tags=["learning"])


@router.get("/proposals", response_model=list[LearningProposal])
def list_learning_proposals(
    include_insufficient: bool = False,
    settings: Settings = Depends(get_settings),
) -> list[dict[str, object]]:
    return repository.list_learning_proposals(
        settings,
        include_insufficient=include_insufficient,
    )


@router.get("/proposals/{stable_key}", response_model=LearningProposal)
def get_learning_proposal(
    stable_key: str,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    try:
        return repository.get_learning_proposal(stable_key, settings)
    except repository.LearningProposalNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Learning proposal not found",
        ) from error


@router.post(
    "/proposals/{stable_key}/decisions",
    response_model=LearningProposal,
    status_code=status.HTTP_201_CREATED,
)
def decide_learning_proposal(
    stable_key: str,
    payload: LearningDecisionCreate,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    try:
        return repository.decide_learning_proposal(stable_key, payload, settings)
    except repository.LearningProposalNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Learning proposal not found",
        ) from error
    except (
        repository.LearningProposalNotEligibleError,
        repository.LearningDecisionConflictError,
    ) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.delete(
    "/proposal-decisions/{decision_id}",
    response_model=LearningProposal,
)
def revoke_learning_decision(
    decision_id: str,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    try:
        return repository.revoke_learning_decision(decision_id, settings)
    except repository.LearningDecisionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Learning decision not found",
        ) from error
    except repository.LearningProposalNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Learning evidence is no longer available",
        ) from error
