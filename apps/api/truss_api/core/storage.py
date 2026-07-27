from pathlib import Path

from truss_api.core.settings import Settings, get_settings


def storage_directories(settings: Settings | None = None) -> tuple[Path, ...]:
    resolved = settings or get_settings()
    return (
        resolved.data_dir,
        resolved.db_dir,
        resolved.originals_dir,
        resolved.renders_dir,
        resolved.cache_dir,
    )


def ensure_storage_layout(settings: Settings | None = None) -> None:
    for directory in storage_directories(settings):
        directory.mkdir(parents=True, exist_ok=True)
