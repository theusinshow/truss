from collections.abc import Iterator
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient

from truss_api.core.settings import Settings, get_settings
from truss_api.db.schema import initialize_database
from truss_api.main import app
from truss_api.recovery.sources import declare_source_unavailable


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    resolved = Settings(data_dir=tmp_path / "data")
    initialize_database(resolved)
    return resolved


@pytest.fixture()
def client(settings: Settings) -> Iterator[TestClient]:
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_root_returns_ok(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"app": "truss-agent", "status": "ok"}


def test_health_returns_safe_summary(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["app"] == "truss-agent"
    assert payload["status"] == "ok"
    assert payload["database"] == "ok"
    assert payload["storage"] == "ok"
    assert payload["interrupted_operations"] == 0
    assert "data" not in payload


def test_diagnostics_can_verify_originals_without_exposing_paths(client: TestClient) -> None:
    response = client.get("/diagnostics?deep=true")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert {item["name"] for item in payload["checks"]} == {
        "storage",
        "database",
        "operations",
        "originals",
    }
    assert "data_dir" not in response.text


def test_deep_diagnostics_reports_missing_original(
    client: TestClient,
    settings: Settings,
) -> None:
    with sqlite3.connect(settings.database_path) as connection:
        connection.execute(
            """
            INSERT INTO projects VALUES ('p', 'P', '', '2026-01-01', '2026-01-01');
            """
        )
        connection.execute(
            """
            INSERT INTO revisions (
                id, project_id, revision_code, notes, source_type, original_filename,
                original_file_path, content_hash, created_at
            ) VALUES ('r', 'p', 'R01', '', 'manual', NULL, NULL, NULL, '2026-01-01')
            """
        )
        connection.execute(
            """
            INSERT INTO documents (
                id, project_id, revision_id, original_filename, stored_file_path,
                content_hash, mime_type, file_size_bytes, page_count, created_at
            ) VALUES ('d', 'p', 'r', 'missing.pdf', 'originals/missing.pdf',
                      'abc', 'application/pdf', 3, 1, '2026-01-01')
            """
        )

    response = client.get("/diagnostics?deep=true")

    assert response.json()["status"] == "unavailable"
    originals = next(item for item in response.json()["checks"] if item["name"] == "originals")
    assert originals["code"] == "PDF_SOURCE_MISSING"


def test_deep_diagnostics_distinguishes_declared_historical_source(
    client: TestClient,
    settings: Settings,
) -> None:
    with sqlite3.connect(settings.database_path) as connection:
        connection.execute(
            "INSERT INTO projects VALUES ('p', 'P', '', '2026-01-01', '2026-01-01')"
        )
        connection.execute(
            """
            INSERT INTO revisions (
                id, project_id, revision_code, notes, source_type, original_filename,
                original_file_path, content_hash, created_at
            ) VALUES ('r', 'p', 'R01', '', 'manual', NULL, NULL, NULL, '2026-01-01')
            """
        )
        connection.execute(
            """
            INSERT INTO documents (
                id, project_id, revision_id, original_filename, stored_file_path,
                content_hash, mime_type, file_size_bytes, page_count, created_at
            ) VALUES ('d', 'p', 'r', 'legacy.pdf', 'originals/legacy.pdf',
                      'abc', 'application/pdf', 3, 1, '2026-01-01')
            """
        )
    declare_source_unavailable(
        "d",
        reason_code="clone_migration_missing",
        note="",
        settings=settings,
    )

    payload = client.get("/diagnostics?deep=true").json()

    assert payload["status"] == "degraded"
    originals = next(item for item in payload["checks"] if item["name"] == "originals")
    assert originals["code"] == "PDF_SOURCE_UNAVAILABLE"
    assert originals["data"] == {
        "checked": 0,
        "missing": 0,
        "corrupt": 0,
        "unavailable": 1,
    }
