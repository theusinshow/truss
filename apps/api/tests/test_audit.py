from collections.abc import Iterator
from io import BytesIO
from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient

from truss_api.core.settings import Settings, get_settings
from truss_api.db.schema import initialize_database
from truss_api.main import app
from truss_api.projects import repository
from truss_api.projects.models import ProjectCreate, RevisionCreate


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


def make_pdf_bytes(text: str = "FORMA PAVIMENTO 1") -> bytes:
    document = fitz.open()
    page = document.new_page(width=842, height=595)
    page.insert_text((72, 72), text)
    buffer = BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def create_imported_sheet(client: TestClient, settings: Settings) -> str:
    project = repository.create_project(ProjectCreate(name="Audit Project"), settings)
    revision = repository.create_revision(
        str(project["id"]),
        RevisionCreate(notes="Audit revision"),
        settings,
    )
    response = client.post(
        f"/projects/{project['id']}/revisions/{revision['id']}/documents",
        files={"file": ("forma.pdf", make_pdf_bytes(), "application/pdf")},
    )
    return str(response.json()["sheets"][0]["id"])


def test_deterministic_audit_creates_structured_findings(
    client: TestClient,
    settings: Settings,
) -> None:
    sheet_id = create_imported_sheet(client, settings)

    response = client.post(f"/sheets/{sheet_id}/audit-runs")

    assert response.status_code == 201
    audit_run = response.json()
    assert audit_run["status"] == "completed"
    assert audit_run["pipeline_version"] == "deterministic-v0.1"
    assert len(audit_run["findings"]) >= 1
    finding = audit_run["findings"][0]
    assert finding["bbox"]["x0"] < finding["bbox"]["x1"]
    assert finding["bbox"]["y0"] < finding["bbox"]["y1"]
    assert finding["status"] == "pending"
    assert finding["origin"] == "ai"


def test_deterministic_audit_uses_cache_for_same_sheet(
    client: TestClient,
    settings: Settings,
) -> None:
    sheet_id = create_imported_sheet(client, settings)

    first_response = client.post(f"/sheets/{sheet_id}/audit-runs")
    second_response = client.post(f"/sheets/{sheet_id}/audit-runs")

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert second_response.json()["id"] == first_response.json()["id"]


def test_finding_feedback_is_persisted(client: TestClient, settings: Settings) -> None:
    sheet_id = create_imported_sheet(client, settings)
    audit_run = client.post(f"/sheets/{sheet_id}/audit-runs").json()
    finding_id = audit_run["findings"][0]["id"]

    response = client.patch(
        f"/findings/{finding_id}",
        json={"status": "rejected", "rejection_reason": "Nao se aplica a este padrao."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "rejected"
    assert payload["rejection_reason"] == "Nao se aplica a este padrao."


def test_manual_finding_is_persisted_with_human_origin(
    client: TestClient,
    settings: Settings,
) -> None:
    sheet_id = create_imported_sheet(client, settings)

    response = client.post(
        f"/sheets/{sheet_id}/findings",
        json={
            "category": "composition",
            "type": "attention",
            "description": "Texto sobreposto a uma linha de cota.",
            "severity": "high",
            "confidence": 1,
            "bbox": {"x0": 10, "y0": 20, "x1": 120, "y1": 160},
            "evidence": ["Marcado manualmente no viewer."],
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["origin"] == "human"
    assert payload["bbox"] == {"x0": 10.0, "y0": 20.0, "x1": 120.0, "y1": 160.0}

    findings = client.get(f"/sheets/{sheet_id}/findings").json()
    assert any(finding["id"] == payload["id"] for finding in findings)
