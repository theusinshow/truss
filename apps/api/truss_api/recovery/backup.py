from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import tempfile
from typing import BinaryIO
from uuid import uuid4
import zipfile

from truss_api.core.settings import Settings
from truss_api.db.migrations import available_migrations
from truss_api.recovery.atomic import atomic_output_path
from truss_api.recovery.errors import TrussError, storage_error
from truss_api.recovery.sources import (
    SOURCE_UNAVAILABLE,
    list_document_sources,
    unavailable_manifest_entry,
)


BACKUP_SCHEMA = "truss-backup-v0.1"
MAX_ARCHIVE_FILES = 100_000
MAX_RESTORED_BYTES = 100 * 1024 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _raise_invalid(message: str) -> None:
    raise TrussError(
        code="BACKUP_INVALID",
        message=message,
        action="Nao restaure este arquivo; crie ou selecione um backup valido.",
        status_code=400,
    )


def _safe_relative(value: str) -> PurePosixPath:
    if "\\" in value or ":" in value:
        _raise_invalid("O backup contem um caminho de arquivo inseguro.")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        _raise_invalid("O backup contem um caminho de arquivo inseguro.")
    return path


def _confined(root: Path, relative: str) -> Path:
    safe = _safe_relative(relative)
    target = (root / Path(*safe.parts)).resolve()
    if not target.is_relative_to(root.resolve()):
        _raise_invalid("Um arquivo escaparia do diretorio de dados.")
    return target


def _hash_stream(stream: BinaryIO) -> tuple[str, int]:
    digest = sha256()
    size = 0
    while chunk := stream.read(CHUNK_SIZE):
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def _hash_file(path: Path) -> tuple[str, int]:
    with path.open("rb") as stream:
        return _hash_stream(stream)


def _sqlite_integrity(path: Path) -> tuple[list[str], dict[str, int]]:
    try:
        connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
        result = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        foreign = connection.execute("PRAGMA foreign_key_check").fetchall()
        if result != "ok" or foreign:
            _raise_invalid("O snapshot SQLite do backup falhou na verificacao de integridade.")
        migrations = [
            str(row[0])
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ]
        known = [version for version, _ in available_migrations()]
        if migrations != known[: len(migrations)]:
            _raise_invalid("O snapshot possui migrations desconhecidas ou fora de ordem.")
        counts: dict[str, int] = {}
        for table in (
            "projects",
            "revisions",
            "documents",
            "sheets",
            "sheet_maps",
            "audit_runs",
            "findings",
            "rule_preferences",
            "learning_proposal_decisions",
            "calibration_runs",
            "calibration_proposal_decisions",
            "processing_operations",
            "document_source_events",
        ):
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            if exists:
                counts[table] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        connection.close()
    except TrussError:
        raise
    except sqlite3.Error as error:
        raise TrussError(
            code="DATABASE_INTEGRITY_FAILED",
            message="O SQLite nao pode ser aberto para criar ou verificar o backup.",
            action="Pare as escritas e execute o diagnostico local.",
            status_code=503,
        ) from error
    return migrations, counts


def _snapshot_database(source: Path, target: Path) -> None:
    try:
        source_connection = sqlite3.connect(source)
        target_connection = sqlite3.connect(target)
        try:
            source_connection.backup(target_connection)
        finally:
            target_connection.close()
            source_connection.close()
    except sqlite3.Error as error:
        raise TrussError(
            code="DATABASE_INTEGRITY_FAILED",
            message="Nao foi possivel criar um snapshot consistente do SQLite.",
            action="Execute o diagnostico local antes de tentar novamente.",
            status_code=503,
            retryable=True,
        ) from error


def _source_files(
    settings: Settings,
    snapshot: Path,
) -> tuple[list[tuple[Path, str, str, bool]], list[dict[str, object]]]:
    connection = sqlite3.connect(f"file:{snapshot.resolve().as_posix()}?mode=ro", uri=True)
    documents = list_document_sources(connection)
    connection.close()
    selected: dict[str, tuple[Path, str, str, bool]] = {}
    unavailable: list[dict[str, object]] = []
    for document in documents:
        relative = str(document["stored_file_path"])
        expected_hash = str(document["content_hash"])
        # Caminhos historicos foram persistidos com separador nativo do Windows.
        relative_posix = PurePosixPath(str(relative).replace("\\", "/")).as_posix()
        path = _confined(settings.data_dir, relative_posix)
        declared_unavailable = document["source_status"] == SOURCE_UNAVAILABLE
        if not path.is_file():
            if declared_unavailable:
                unavailable.append(unavailable_manifest_entry(document))
                continue
            raise TrussError(
                code="PDF_SOURCE_MISSING",
                message="Um PDF original referenciado pelo banco nao foi encontrado.",
                action=(
                    "Restaure um backup valido ou declare explicitamente a fonte historica "
                    "como indisponivel."
                ),
                status_code=500,
            )
        digest, _ = _hash_file(path)
        if digest != str(expected_hash):
            raise TrussError(
                code="ARTIFACT_CORRUPT",
                message="Um PDF original diverge do hash registrado no banco.",
                action="Restaure um backup valido em um novo diretorio.",
                status_code=500,
            )
        if declared_unavailable:
            raise TrussError(
                code="SOURCE_DECLARATION_CONFLICT",
                message="Um PDF declarado indisponivel esta novamente presente e integro.",
                action="Registre a restauracao da fonte antes de criar o backup.",
                status_code=409,
            )
        archive_path = f"files/{relative_posix}"
        selected[archive_path] = (path, archive_path, "original", True)

    roots = (
        (settings.geometry_dir, "geometry"),
        (settings.calibration_analyses_dir, "calibration_analysis"),
        (settings.calibration_runs_dir, "calibration_run"),
        (settings.data_dir / "knowledge-inbox", "knowledge_inbox"),
    )
    for root, role in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                _raise_invalid("O diretorio de dados contem link simbolico nao suportado.")
            if not path.is_file() or path.name.endswith(".partial"):
                continue
            relative = path.relative_to(settings.data_dir).as_posix()
            archive_path = f"files/{relative}"
            selected.setdefault(archive_path, (path, archive_path, role, False))
    return [selected[key] for key in sorted(selected)], sorted(
        unavailable,
        key=lambda item: (str(item["stored_file_path"]), str(item["document_id"])),
    )


def _write_entry(
    archive: zipfile.ZipFile,
    source: Path,
    archive_path: str,
    *,
    role: str,
    critical: bool,
) -> dict[str, object]:
    before = source.stat()
    digest = sha256()
    size = 0
    info = zipfile.ZipInfo(archive_path, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    with source.open("rb") as input_stream, archive.open(info, "w") as output_stream:
        while chunk := input_stream.read(CHUNK_SIZE):
            output_stream.write(chunk)
            digest.update(chunk)
            size += len(chunk)
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise TrussError(
            code="BACKUP_SOURCE_CHANGED",
            message="Um arquivo local mudou durante a criacao do backup.",
            action="Tente criar o backup novamente quando a importacao estiver concluida.",
            status_code=409,
            retryable=True,
        )
    return {
        "relative_path": archive_path,
        "role": role,
        "critical": critical,
        "size_bytes": size,
        "sha256": digest.hexdigest(),
    }


def create_backup(settings: Settings, output_dir: Path | None = None) -> Path:
    if not settings.database_path.is_file():
        raise TrussError(
            code="DATABASE_NOT_FOUND",
            message="O banco local nao foi encontrado para backup.",
            action="Inicie o Truss e execute o diagnostico local.",
            status_code=404,
        )
    output = (output_dir or settings.backup_dir).resolve()
    if output == settings.data_dir.resolve() or output.is_relative_to(settings.data_dir.resolve()):
        raise TrussError(
            code="BACKUP_DESTINATION_INVALID",
            message="O backup nao pode ser gravado dentro do diretorio de dados.",
            action="Escolha um destino fora de data/.",
            status_code=400,
        )
    try:
        output.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise storage_error(error) from error
    target = output / f"truss-{_stamp()}-{uuid4().hex[:8]}.zip"

    with tempfile.TemporaryDirectory(prefix="truss-backup-") as temporary:
        snapshot = Path(temporary) / "truss.sqlite"
        _snapshot_database(settings.database_path, snapshot)
        migrations, logical_counts = _sqlite_integrity(snapshot)
        sources, unavailable_sources = _source_files(settings, snapshot)
        required = snapshot.stat().st_size + sum(item[0].stat().st_size for item in sources)
        free = shutil.disk_usage(output).free
        if free < required + max(64 * 1024 * 1024, required // 10):
            raise TrussError(
                code="STORAGE_FULL",
                message="Nao ha espaco suficiente para criar o backup.",
                action="Libere espaco ou escolha outro disco.",
                status_code=507,
                retryable=True,
            )

        def validate(path: Path) -> None:
            verify_backup(path)

        with atomic_output_path(target, validator=validate) as partial:
            entries: list[dict[str, object]] = []
            with zipfile.ZipFile(partial, "w", allowZip64=True) as archive:
                entries.append(
                    _write_entry(
                        archive,
                        snapshot,
                        "db/truss.sqlite",
                        role="database",
                        critical=True,
                    )
                )
                for source, archive_path, role, critical in sources:
                    entries.append(
                        _write_entry(
                            archive,
                            source,
                            archive_path,
                            role=role,
                            critical=critical,
                        )
                    )
                manifest = {
                    "schema": BACKUP_SCHEMA,
                    "backup_id": str(uuid4()),
                    "created_at": _now(),
                    "app_version": "0.0.0",
                    "database_sha256": entries[0]["sha256"],
                    "schema_migrations": migrations,
                    "logical_counts": logical_counts,
                    "unavailable_sources": unavailable_sources,
                    "files": entries,
                    "total_size_bytes": sum(int(item["size_bytes"]) for item in entries),
                    "excluded_roles": [
                        "renders",
                        "cache",
                        "calibration_previews",
                        "calibration_exports",
                        "secrets",
                        "logs",
                        "pre_migration_snapshots",
                        "backups",
                    ],
                    "warnings": [
                        "Este backup contem PDFs e nao possui criptografia.",
                        *(
                            [
                                f"{len(unavailable_sources)} fonte(s) historica(s) estao "
                                "explicitamente indisponiveis."
                            ]
                            if unavailable_sources
                            else []
                        ),
                    ],
                }
                info = zipfile.ZipInfo("manifest.json", date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o600 << 16
                archive.writestr(
                    info,
                    json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":")),
                )
    return target


def _read_manifest(archive: zipfile.ZipFile) -> dict[str, object]:
    try:
        raw = archive.read("manifest.json")
        manifest = json.loads(raw.decode("utf-8"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as error:
        _raise_invalid("O manifesto do backup esta ausente ou corrompido.")
        raise AssertionError from error
    if not isinstance(manifest, dict) or manifest.get("schema") != BACKUP_SCHEMA:
        _raise_invalid("A versao do formato de backup nao e suportada.")
    return manifest


def verify_backup(path: Path) -> dict[str, object]:
    if not path.is_file():
        _raise_invalid("O arquivo de backup nao foi encontrado.")
    try:
        with zipfile.ZipFile(path, "r") as archive:
            manifest = _read_manifest(archive)
            declared = manifest.get("files")
            if not isinstance(declared, list) or len(declared) > MAX_ARCHIVE_FILES:
                _raise_invalid("A lista de arquivos do backup e invalida.")
            expected_names = {"manifest.json"}
            total = 0
            entries_by_name: dict[str, dict[str, object]] = {}
            for item in declared:
                if not isinstance(item, dict):
                    _raise_invalid("Uma entrada do manifesto e invalida.")
                name = str(item.get("relative_path") or "")
                _safe_relative(name)
                if name in entries_by_name:
                    _raise_invalid("O manifesto possui caminhos duplicados.")
                size = int(item.get("size_bytes", -1))
                if size < 0:
                    _raise_invalid("O manifesto possui tamanho de arquivo invalido.")
                total += size
                entries_by_name[name] = item
                expected_names.add(name)
            if total != int(manifest.get("total_size_bytes", -1)) or total > MAX_RESTORED_BYTES:
                _raise_invalid("O tamanho total declarado pelo backup e invalido.")
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)) or set(names) != expected_names:
                _raise_invalid("O ZIP contem entradas ausentes, extras ou duplicadas.")
            for info in infos:
                _safe_relative(info.filename)
                mode = (info.external_attr >> 16) & 0o170000
                if mode == 0o120000 or info.is_dir():
                    _raise_invalid("O ZIP contem link ou diretorio nao suportado.")
                if info.filename == "manifest.json":
                    continue
                item = entries_by_name[info.filename]
                if info.file_size != int(item["size_bytes"]):
                    _raise_invalid("Um arquivo do ZIP diverge do tamanho declarado.")
                with archive.open(info, "r") as stream:
                    digest, size = _hash_stream(stream)
                if size != int(item["size_bytes"]) or digest != str(item.get("sha256")):
                    _raise_invalid("Um arquivo do backup falhou na verificacao SHA-256.")

            with tempfile.TemporaryDirectory(prefix="truss-verify-") as temporary:
                database = Path(temporary) / "truss.sqlite"
                with archive.open("db/truss.sqlite") as source, database.open("wb") as target:
                    shutil.copyfileobj(source, target, CHUNK_SIZE)
                migrations, counts = _sqlite_integrity(database)
                if migrations != manifest.get("schema_migrations") or counts != manifest.get("logical_counts"):
                    _raise_invalid("O manifesto diverge do conteudo logico do SQLite.")
                connection = sqlite3.connect(
                    f"file:{database.resolve().as_posix()}?mode=ro", uri=True
                )
                documents = list_document_sources(connection)
                connection.close()
                expected_unavailable = [
                    unavailable_manifest_entry(document)
                    for document in documents
                    if document["source_status"] == SOURCE_UNAVAILABLE
                ]
                expected_unavailable.sort(
                    key=lambda item: (str(item["stored_file_path"]), str(item["document_id"]))
                )
                declared_unavailable = manifest.get("unavailable_sources", [])
                if not isinstance(declared_unavailable, list):
                    _raise_invalid("A lista de fontes indisponiveis e invalida.")
                if declared_unavailable != expected_unavailable:
                    _raise_invalid(
                        "As fontes indisponiveis do manifesto divergem dos eventos do SQLite."
                    )
                unavailable_ids = {
                    str(item["document_id"])
                    for item in expected_unavailable
                }
                for document in documents:
                    if str(document["document_id"]) in unavailable_ids:
                        normalized = PurePosixPath(
                            str(document["stored_file_path"]).replace("\\", "/")
                        ).as_posix()
                        if f"files/{normalized}" in entries_by_name:
                            _raise_invalid(
                                "Uma fonte indisponivel foi incluída como PDF original."
                            )
                        continue
                    relative = str(document["stored_file_path"])
                    expected_hash = str(document["content_hash"])
                    normalized = PurePosixPath(str(relative).replace("\\", "/")).as_posix()
                    name = f"files/{normalized}"
                    item = entries_by_name.get(name)
                    if item is None or str(item.get("sha256")) != str(expected_hash):
                        _raise_invalid("Um PDF original referenciado nao esta integro no backup.")
            return manifest
    except TrussError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError, ValueError) as error:
        raise TrussError(
            code="BACKUP_INVALID",
            message="O arquivo nao e um backup ZIP valido do Truss.",
            action="Nao restaure este arquivo; selecione outro backup.",
            status_code=400,
        ) from error
