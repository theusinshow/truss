from dataclasses import asdict, dataclass
from hashlib import sha256
import os
from pathlib import Path
import shutil
import sqlite3
from typing import Literal

from truss_api.core.settings import Settings
from truss_api.db.migrations import available_migrations
from truss_api.recovery.sources import SOURCE_UNAVAILABLE, list_document_sources


CheckStatus = Literal["ok", "warning", "error"]


@dataclass(frozen=True)
class DiagnosticCheck:
    name: str
    status: CheckStatus
    code: str
    message: str
    action: str | None = None
    data: dict[str, object] | None = None

    def as_dict(self) -> dict[str, object]:
        return {key: value for key, value in asdict(self).items() if value is not None}


def _database_uri(path: Path) -> str:
    return f"file:{path.resolve().as_posix()}?mode=ro"


def _storage_check(settings: Settings) -> DiagnosticCheck:
    if not settings.data_dir.exists():
        return DiagnosticCheck(
            name="storage",
            status="error",
            code="STORAGE_NOT_FOUND",
            message="O diretorio de dados local ainda nao existe.",
            action="Inicie o aplicativo para criar o layout local.",
        )
    if not settings.data_dir.is_dir() or not os.access(settings.data_dir, os.R_OK | os.W_OK):
        return DiagnosticCheck(
            name="storage",
            status="error",
            code="STORAGE_NOT_WRITABLE",
            message="O diretorio de dados nao permite leitura e escrita.",
            action="Verifique as permissoes do diretorio configurado.",
        )
    usage = shutil.disk_usage(settings.data_dir)
    status: CheckStatus = "warning" if usage.free < 512 * 1024 * 1024 else "ok"
    return DiagnosticCheck(
        name="storage",
        status=status,
        code="STORAGE_LOW_SPACE" if status == "warning" else "STORAGE_OK",
        message=(
            "O espaco livre esta abaixo de 512 MiB."
            if status == "warning"
            else "O armazenamento local esta disponivel."
        ),
        action="Libere espaco antes de importar ou criar backup." if status == "warning" else None,
        data={"free_bytes": usage.free, "total_bytes": usage.total},
    )


def _database_check(settings: Settings) -> DiagnosticCheck:
    if not settings.database_path.is_file():
        return DiagnosticCheck(
            name="database",
            status="error",
            code="DATABASE_NOT_FOUND",
            message="O banco local nao foi encontrado.",
            action="Inicie o aplicativo ou restaure um backup em um novo diretorio.",
        )
    try:
        connection = sqlite3.connect(_database_uri(settings.database_path), uri=True)
        connection.row_factory = sqlite3.Row
        quick = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        foreign = connection.execute("PRAGMA foreign_key_check").fetchall()
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        applied = []
        if "schema_migrations" in tables:
            applied = [
                str(row[0])
                for row in connection.execute(
                    "SELECT version FROM schema_migrations ORDER BY version"
                )
            ]
        connection.close()
    except sqlite3.Error:
        return DiagnosticCheck(
            name="database",
            status="error",
            code="DATABASE_INTEGRITY_FAILED",
            message="O SQLite nao pode ser aberto ou verificado.",
            action="Pare as escritas e verifique um backup antes de recuperar.",
        )
    available = [version for version, _ in available_migrations()]
    if quick != "ok" or foreign:
        return DiagnosticCheck(
            name="database",
            status="error",
            code="DATABASE_INTEGRITY_FAILED",
            message="O banco local falhou na verificacao de integridade.",
            action="Pare as escritas e execute o diagnostico profundo.",
            data={"quick_check": quick, "foreign_key_violations": len(foreign)},
        )
    if applied != available[: len(applied)]:
        return DiagnosticCheck(
            name="database",
            status="error",
            code="DATABASE_SCHEMA_UNKNOWN",
            message="O banco possui migrations desconhecidas por esta versao do Truss.",
            action="Use uma versao compativel do aplicativo; nao tente migrar este banco.",
            data={"applied_migrations": applied, "known_migrations": available},
        )
    pending = [version for version in available if version not in applied]
    return DiagnosticCheck(
        name="database",
        status="warning" if pending else "ok",
        code="DATABASE_MIGRATIONS_PENDING" if pending else "DATABASE_OK",
        message=(
            "Existem migrations pendentes."
            if pending
            else "O banco local passou nas verificacoes basicas."
        ),
        data={"applied_migrations": applied, "pending_migrations": pending},
    )


def _operations_check(settings: Settings) -> DiagnosticCheck:
    if not settings.database_path.is_file():
        return DiagnosticCheck(
            name="operations",
            status="warning",
            code="OPERATIONS_UNAVAILABLE",
            message="Operacoes nao podem ser consultadas sem o banco local.",
        )
    try:
        connection = sqlite3.connect(_database_uri(settings.database_path), uri=True)
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='processing_operations'"
        ).fetchone()
        interrupted = 0
        if exists:
            interrupted = int(
                connection.execute(
                    "SELECT COUNT(*) FROM processing_operations WHERE status IN ('interrupted', 'manual_retry_required')"
                ).fetchone()[0]
            )
        connection.close()
    except sqlite3.Error:
        interrupted = 0
    return DiagnosticCheck(
        name="operations",
        status="warning" if interrupted else "ok",
        code="OPERATION_INTERRUPTED" if interrupted else "OPERATIONS_OK",
        message=(
            f"Ha {interrupted} operacao(oes) que exigem atencao."
            if interrupted
            else "Nao ha operacoes interrompidas."
        ),
        action="Revise e continue apenas as operacoes seguras." if interrupted else None,
        data={"interrupted_count": interrupted},
    )


def _batches_check(settings: Settings) -> DiagnosticCheck:
    if not settings.database_path.is_file():
        return DiagnosticCheck(
            name="batches",
            status="warning",
            code="BATCHES_UNAVAILABLE",
            message="Lotes nao podem ser consultados sem o banco local.",
        )
    try:
        connection = sqlite3.connect(_database_uri(settings.database_path), uri=True)
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='batch_runs'"
        ).fetchone()
        interrupted = 0
        if exists:
            interrupted = int(
                connection.execute(
                    "SELECT COUNT(*) FROM batch_runs WHERE status = 'interrupted'"
                ).fetchone()[0]
            )
        connection.close()
    except sqlite3.Error:
        interrupted = 0
    return DiagnosticCheck(
        name="batches",
        status="warning" if interrupted else "ok",
        code="BATCH_INTERRUPTED" if interrupted else "BATCHES_OK",
        message=(
            f"Ha {interrupted} lote(s) interrompido(s) aguardando retomada."
            if interrupted
            else "Nao ha lotes interrompidos."
        ),
        action="Revise o lote e retome apenas as falhas locais." if interrupted else None,
        data={"interrupted_count": interrupted},
    )


def _deep_originals_check(settings: Settings) -> DiagnosticCheck:
    missing = 0
    corrupt = 0
    checked = 0
    unavailable = 0
    if not settings.database_path.is_file():
        return DiagnosticCheck(
            name="originals",
            status="error",
            code="DATABASE_NOT_FOUND",
            message="Nao foi possivel conferir os PDFs sem o banco local.",
        )
    try:
        connection = sqlite3.connect(_database_uri(settings.database_path), uri=True)
        rows = list_document_sources(connection)
        connection.close()
        for document in rows:
            relative = str(document["stored_file_path"])
            expected = str(document["content_hash"])
            path = settings.data_dir / relative
            if not path.is_file():
                if document["source_status"] == SOURCE_UNAVAILABLE:
                    unavailable += 1
                    continue
                missing += 1
                continue
            checked += 1
            digest = sha256(path.read_bytes()).hexdigest()
            if digest != str(expected):
                corrupt += 1
            elif document["source_status"] == SOURCE_UNAVAILABLE:
                corrupt += 1
    except (sqlite3.Error, OSError):
        return DiagnosticCheck(
            name="originals",
            status="error",
            code="PDF_SOURCE_MISSING",
            message="A verificacao dos PDFs originais nao pode ser concluida.",
            action="Verifique o armazenamento e um backup valido.",
        )
    status: CheckStatus = "error" if missing or corrupt else "warning" if unavailable else "ok"
    if missing:
        code = "PDF_SOURCE_MISSING"
    elif corrupt:
        code = "ARTIFACT_CORRUPT"
    elif unavailable:
        code = "PDF_SOURCE_UNAVAILABLE"
    else:
        code = "ORIGINALS_OK"
    return DiagnosticCheck(
        name="originals",
        status=status,
        code=code,
        message=(
            "Ha PDFs originais ausentes ou com hash divergente."
            if status == "error"
            else f"Ha {unavailable} fonte(s) historica(s) declarada(s) como indisponivel(is)."
            if status == "warning"
            else "Todos os PDFs originais referenciados foram verificados."
        ),
        action=(
            "Restaure um backup valido em um novo diretorio."
            if status == "error"
            else "Use uma nova revisao para os PDFs atuais; o historico foi preservado."
            if status == "warning"
            else None
        ),
        data={
            "checked": checked,
            "missing": missing,
            "corrupt": corrupt,
            "unavailable": unavailable,
        },
    )


def run_diagnostics(settings: Settings, *, deep: bool = False) -> dict[str, object]:
    checks = [
        _storage_check(settings),
        _database_check(settings),
        _operations_check(settings),
        _batches_check(settings),
    ]
    if deep:
        checks.append(_deep_originals_check(settings))
    if any(check.status == "error" for check in checks):
        status = "unavailable"
    elif any(check.status == "warning" for check in checks):
        status = "degraded"
    else:
        status = "ok"
    return {
        "app": "truss-agent",
        "status": status,
        "deep": deep,
        "checks": [check.as_dict() for check in checks],
    }


def health_summary(settings: Settings) -> dict[str, object]:
    report = run_diagnostics(settings, deep=False)
    by_name = {str(item["name"]): item for item in report["checks"]}
    operations_data = by_name["operations"].get("data") or {}
    batches_data = by_name["batches"].get("data") or {}
    return {
        "app": "truss-agent",
        "status": report["status"],
        "environment": settings.environment,
        "database": by_name["database"]["status"],
        "storage": by_name["storage"]["status"],
        "interrupted_operations": int(operations_data.get("interrupted_count", 0)),
        "interrupted_batches": int(batches_data.get("interrupted_count", 0)),
    }
