from fastapi import APIRouter, Depends, Query

from truss_api.core.settings import Settings, get_settings
from truss_api.recovery.diagnostics import run_diagnostics
from truss_api.recovery.operations import resume_operation
from truss_api.recovery import repository


router = APIRouter(tags=["recovery"])


@router.get("/diagnostics")
def diagnostics(
    deep: bool = Query(default=False),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    return run_diagnostics(settings, deep=deep)


@router.get("/operations")
def operations(settings: Settings = Depends(get_settings)) -> list[dict[str, object]]:
    return repository.list_attention_operations(settings)


@router.get("/operations/{operation_id}")
def operation_detail(
    operation_id: str,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    operation = repository.get_operation(operation_id, settings)
    operation["events"] = repository.list_events(operation_id, settings)
    return operation


@router.post("/operations/{operation_id}/resume")
def resume(
    operation_id: str,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    return resume_operation(operation_id, settings)
