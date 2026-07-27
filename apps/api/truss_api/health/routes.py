from fastapi import APIRouter

from truss_api.core.settings import get_settings
from truss_api.core.storage import ensure_storage_layout

router = APIRouter(tags=["health"])


@router.get("/")
def root() -> dict[str, str]:
    return {"app": "truss-agent", "status": "ok"}


@router.get("/health")
def health() -> dict[str, object]:
    settings = get_settings()
    ensure_storage_layout(settings)

    return {
        "app": "truss-agent",
        "status": "ok",
        "environment": settings.environment,
        "storage": {
            "data": str(settings.data_dir),
            "db": str(settings.db_dir),
            "originals": str(settings.originals_dir),
            "renders": str(settings.renders_dir),
            "cache": str(settings.cache_dir),
        },
    }
