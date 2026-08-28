from pathlib import Path

from truss_api.core.settings import Settings
from truss_api.db.connection import transaction
from truss_api.db.migrations import apply_migrations


def _table_names(settings: Settings) -> set[str]:
    with transaction(settings) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    return {str(row["name"]) for row in rows}


def test_apply_migrations_creates_schema_and_is_idempotent(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data")

    applied = apply_migrations(settings)

    assert "001" in applied
    assert {"projects", "revisions", "documents", "sheets", "findings"} <= _table_names(settings)
    assert apply_migrations(settings) == []


def test_apply_migrations_adopts_legacy_database_without_losing_data(tmp_path: Path) -> None:
    """Um banco criado antes das migrations nao pode ser recriado nem perder dados."""
    settings = Settings(data_dir=tmp_path / "data")
    baseline = (
        Path(__file__).resolve().parents[1]
        / "truss_api"
        / "db"
        / "migrations"
        / "001_baseline.sql"
    )
    with transaction(settings) as connection:
        connection.executescript(baseline.read_text(encoding="utf-8"))
        connection.execute(
            "INSERT INTO projects (id, name, description, created_at, updated_at)"
            " VALUES ('p1', 'Obra existente', '', '2026-01-01', '2026-01-01')"
        )

    applied = apply_migrations(settings)

    assert "001" in applied
    with transaction(settings) as connection:
        row = connection.execute("SELECT name FROM projects WHERE id = 'p1'").fetchone()
    assert row is not None and str(row["name"]) == "Obra existente"
