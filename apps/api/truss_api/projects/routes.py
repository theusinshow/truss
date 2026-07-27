from fastapi import APIRouter, Depends, HTTPException, status

from truss_api.core.settings import Settings, get_settings
from truss_api.projects import repository
from truss_api.projects.models import (
    ProjectCreate,
    ProjectDetail,
    ProjectSummary,
    Revision,
    RevisionCreate,
)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectSummary])
def list_projects(settings: Settings = Depends(get_settings)) -> list[dict[str, object]]:
    return repository.list_projects(settings)


@router.post("", response_model=ProjectDetail, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    return repository.create_project(payload, settings)


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(
    project_id: str,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    try:
        return repository.get_project(project_id, settings)
    except repository.ProjectNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found") from error


@router.post(
    "/{project_id}/revisions",
    response_model=Revision,
    status_code=status.HTTP_201_CREATED,
)
def create_revision(
    project_id: str,
    payload: RevisionCreate,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    try:
        return repository.create_revision(project_id, payload, settings)
    except repository.ProjectNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found") from error
    except repository.DuplicateRevisionError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Revision code already exists for this project",
        ) from error
