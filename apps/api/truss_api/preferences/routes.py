from fastapi import APIRouter, Depends, HTTPException, status

from truss_api.core.settings import Settings, get_settings
from truss_api.preferences import repository
from truss_api.preferences.models import RulePreference, RulePreferenceCreate


router = APIRouter(tags=["learning"])


@router.post(
    "/findings/{finding_id}/rule-preferences",
    response_model=RulePreference,
    status_code=status.HTTP_201_CREATED,
)
def create_rule_preference(
    finding_id: str,
    payload: RulePreferenceCreate,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    try:
        return repository.create_suppression_for_finding(finding_id, payload, settings)
    except repository.FindingNotFoundForPreferenceError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Finding not found",
        ) from error
    except repository.FindingNotEligibleForPreferenceError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.get("/rule-preferences", response_model=list[RulePreference])
def list_rule_preferences(
    include_revoked: bool = False,
    settings: Settings = Depends(get_settings),
) -> list[dict[str, object]]:
    return repository.list_rule_preferences(settings, include_revoked=include_revoked)


@router.delete("/rule-preferences/{preference_id}", response_model=RulePreference)
def revoke_rule_preference(
    preference_id: str,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    try:
        return repository.revoke_rule_preference(preference_id, settings)
    except repository.RulePreferenceNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule preference not found",
        ) from error
