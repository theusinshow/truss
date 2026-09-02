import json
import os
from pathlib import Path
import shutil
from uuid import uuid4
import zipfile

from truss_api.recovery.backup import (
    CHUNK_SIZE,
    _confined,
    _hash_file,
    _sqlite_integrity,
    verify_backup,
)
from truss_api.recovery.errors import TrussError, storage_error


def _destination_for_entry(staging: Path, archive_path: str) -> Path | None:
    if archive_path == "manifest.json":
        return staging / "recovery" / "restore-manifest.json"
    if archive_path == "db/truss.sqlite":
        return staging / "db" / "truss.sqlite"
    if archive_path.startswith("files/"):
        return _confined(staging, archive_path.removeprefix("files/"))
    return None


def restore_backup(archive_path: Path, target: Path) -> Path:
    manifest = verify_backup(archive_path)
    resolved_target = target.resolve()
    if resolved_target.exists():
        raise TrussError(
            code="RESTORE_TARGET_EXISTS",
            message="O destino da restauracao ja existe.",
            action="Escolha um novo caminho; a F6.1 nunca sobrescreve diretorios.",
            status_code=409,
        )
    parent = resolved_target.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise storage_error(error) from error
    required = int(manifest["total_size_bytes"])
    if shutil.disk_usage(parent).free < required + max(64 * 1024 * 1024, required // 10):
        raise TrussError(
            code="STORAGE_FULL",
            message="Nao ha espaco suficiente para restaurar o backup.",
            action="Libere espaco ou escolha outro disco.",
            status_code=507,
            retryable=True,
        )
    staging = parent / f".{resolved_target.name}.{uuid4().hex}.partial"
    try:
        staging.mkdir()
        with zipfile.ZipFile(archive_path, "r") as archive:
            for info in archive.infolist():
                destination = _destination_for_entry(staging, info.filename)
                if destination is None:
                    raise TrussError(
                        code="BACKUP_INVALID",
                        message="O backup contem uma entrada sem destino conhecido.",
                        action="Nao restaure este arquivo.",
                        status_code=400,
                    )
                destination.parent.mkdir(parents=True, exist_ok=True)
                if info.filename == "manifest.json":
                    destination.write_text(
                        json.dumps(manifest, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    continue
                with archive.open(info, "r") as source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output, CHUNK_SIZE)
        # Confere novamente o staging, agora no layout final, antes de publicar.
        for item in manifest["files"]:
            destination = _destination_for_entry(staging, str(item["relative_path"]))
            if destination is None or not destination.is_file():
                raise TrussError(
                    code="BACKUP_INVALID",
                    message="Um arquivo restaurado esta ausente no staging.",
                    action="Nao publique esta restauracao.",
                    status_code=400,
                )
            digest, size = _hash_file(destination)
            if digest != str(item["sha256"]) or size != int(item["size_bytes"]):
                raise TrussError(
                    code="BACKUP_INVALID",
                    message="Um arquivo restaurado diverge do manifesto.",
                    action="Nao publique esta restauracao.",
                    status_code=400,
                )
        database = staging / "db" / "truss.sqlite"
        if not database.is_file():
            raise TrussError(
                code="BACKUP_INVALID",
                message="O banco restaurado nao foi encontrado no staging.",
                action="Nao publique esta restauracao.",
                status_code=400,
            )
        _sqlite_integrity(database)
        os.replace(staging, resolved_target)
    except Exception:
        if staging.exists() and staging.parent == parent and staging.name.endswith(".partial"):
            shutil.rmtree(staging)
        raise
    return resolved_target
