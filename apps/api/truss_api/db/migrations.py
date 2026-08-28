from datetime import UTC, datetime
from pathlib import Path
from sqlite3 import Connection

from truss_api.core.settings import Settings, get_settings
from truss_api.db.connection import transaction


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


def apply_migrations(
    settings: Settings | None = None,
    directory: Path | None = None,
) -> list[str]:
    resolved = settings or get_settings()
    applied: list[str] = []

    with transaction(resolved) as connection:
        connection.executescript(SCHEMA_MIGRATIONS_SQL)
        already_applied = applied_versions(connection)

        for version, path in available_migrations(directory):
            if version in already_applied:
                continue

            connection.executescript(path.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, _now()),
            )
            applied.append(version)

    return applied
