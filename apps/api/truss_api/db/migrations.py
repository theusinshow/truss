from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
import sqlite3
from sqlite3 import Connection

from truss_api.core.settings import Settings, get_settings
from truss_api.core.storage import ensure_storage_layout
from truss_api.recovery.atomic import atomic_output_path
from truss_api.recovery.errors import TrussError


MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

SCHEMA_MIGRATIONS_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def available_migrations(directory: Path | None = None) -> list[tuple[str, Path]]:
    resolved = directory or MIGRATIONS_DIR
    return [
        (path.name.split("_", 1)[0], path)
        for path in sorted(resolved.glob("*.sql"))
    ]


def applied_versions(connection: Connection) -> set[str]:
    rows = connection.execute("SELECT version FROM schema_migrations").fetchall()
    return {str(row["version"]) for row in rows}


class MigrationSafetyError(TrussError):
    pass


def _migration_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _integrity(connection: Connection) -> None:
    result = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
    foreign = connection.execute("PRAGMA foreign_key_check").fetchall()
    if result != "ok" or foreign:
        raise MigrationSafetyError(
            code="DATABASE_INTEGRITY_FAILED",
            message="O banco local falhou na verificacao de integridade.",
            action="Nao aplique migrations; verifique um backup valido.",
            status_code=503,
        )


def _validate_applied_migrations(
    connection: Connection,
    migrations: list[tuple[str, Path]],
) -> list[str]:
    rows = connection.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()
    applied = [str(row["version"]) for row in rows]
    available = [version for version, _ in migrations]
    if applied != available[: len(applied)]:
        raise MigrationSafetyError(
            code="DATABASE_SCHEMA_UNKNOWN",
            message="A sequencia de migrations do banco e desconhecida por esta versao.",
            action="Use uma versao compativel do Truss e nao altere este banco.",
            status_code=503,
        )
    columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(schema_migrations)")
    }
    if "sql_sha256" in columns:
        hashed = connection.execute(
            "SELECT version, sql_sha256 FROM schema_migrations WHERE sql_sha256 IS NOT NULL"
        ).fetchall()
        paths = dict(migrations)
        for row in hashed:
            version = str(row["version"])
            if version not in paths or str(row["sql_sha256"]) != _migration_hash(paths[version]):
                raise MigrationSafetyError(
                    code="DATABASE_SCHEMA_UNKNOWN",
                    message="Uma migration aplicada diverge do arquivo conhecido.",
                    action="Restaure o arquivo de migration correto antes de iniciar.",
                    status_code=503,
                )
    return applied


def _create_pre_migration_snapshot(settings: Settings, connection: Connection) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    target = settings.database_recovery_dir / f"pre-migration-{stamp}.sqlite"

    def validate(path: Path) -> None:
        snapshot = sqlite3.connect(path)
        snapshot.row_factory = sqlite3.Row
        try:
            _integrity(snapshot)
        finally:
            snapshot.close()

    with atomic_output_path(target, validator=validate) as partial:
        snapshot = sqlite3.connect(partial)
        try:
            connection.backup(snapshot)
        finally:
            snapshot.close()
    return target


def apply_migrations(
    settings: Settings | None = None,
    directory: Path | None = None,
) -> list[str]:
    resolved = settings or get_settings()
    ensure_storage_layout(resolved)
    existed_before = resolved.database_path.exists() and resolved.database_path.stat().st_size > 0
    migrations = available_migrations(directory)
    versions = [version for version, _ in migrations]
    if len(versions) != len(set(versions)):
        raise MigrationSafetyError(
            code="DATABASE_SCHEMA_UNKNOWN",
            message="Ha migrations com versao duplicada.",
            action="Corrija os arquivos de migration antes de iniciar.",
            status_code=503,
        )

    connection = sqlite3.connect(resolved.database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    applied_now: list[str] = []
    try:
        connection.executescript(SCHEMA_MIGRATIONS_SQL)
        connection.commit()
        _integrity(connection)
        already_applied = _validate_applied_migrations(connection, migrations)
        pending = [(version, path) for version, path in migrations if version not in already_applied]
        if existed_before and pending:
            _create_pre_migration_snapshot(resolved, connection)

        for version, path in pending:
            sql = path.read_text(encoding="utf-8")
            try:
                connection.executescript(f"BEGIN IMMEDIATE;\n{sql}\n")
                columns = {
                    str(row["name"])
                    for row in connection.execute("PRAGMA table_info(schema_migrations)")
                }
                if "sql_sha256" in columns:
                    connection.execute(
                        "INSERT INTO schema_migrations (version, applied_at, sql_sha256) VALUES (?, ?, ?)",
                        (version, _now(), _migration_hash(path)),
                    )
                else:
                    connection.execute(
                        "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                        (version, _now()),
                    )
                connection.commit()
            except Exception as error:
                connection.rollback()
                if isinstance(error, TrussError):
                    raise
                raise MigrationSafetyError(
                    code="DATABASE_MIGRATION_FAILED",
                    message=f"A migration {version} nao pode ser concluida.",
                    action="Preserve o snapshot pre-migration e execute o diagnostico.",
                    status_code=503,
                ) from error
            applied_now.append(version)
        _integrity(connection)
    finally:
        connection.close()

    return applied_now
