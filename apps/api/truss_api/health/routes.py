from fastapi import APIRouter, Depends

from truss_api.core.settings import Settings, get_settings
from truss_api.recovery.diagnostics import health_summary

router = APIRouter(tags=["health"])


@router.get("/")
def root() -> dict[str, str]:
    return {"app": "truss-agent", "status": "ok"}


@router.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    return health_summary(settings)
