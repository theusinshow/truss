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


def make_pdf_bytes() -> bytes:
    document = fitz.open()
    page = document.new_page(width=842, height=595)
    page.insert_text((72, 72), "FORMA PAVIMENTO 1")
    buffer = BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def create_sheet(client: TestClient, settings: Settings) -> str:
    project = repository.create_project(ProjectCreate(name="Assistant Project"), settings)
    revision = repository.create_revision(
        str(project["id"]),
        RevisionCreate(notes="Assistant revision"),
        settings,
    )
    response = client.post(
        f"/projects/{project['id']}/revisions/{revision['id']}/documents",
        files={"file": ("forma.pdf", make_pdf_bytes(), "application/pdf")},
    )
    return str(response.json()["sheets"][0]["id"])


def test_sheet_chat_uses_local_provider_and_records_usage(
    client: TestClient,
    settings: Settings,
) -> None:
    sheet_id = create_sheet(client, settings)
    client.post(f"/sheets/{sheet_id}/audit-runs")

    response = client.post(f"/sheets/{sheet_id}/chat", json={"message": "E a escala?"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "local"
    assert "escala" in payload["answer"].lower()

    usage = client.get("/usage").json()
    assert usage[0]["provider"] == "local"
    assert usage[0]["estimated_cost_usd"] == 0


def test_memory_crud(client: TestClient) -> None:
    create_response = client.post(
        "/memories",
        json={"scope": "global", "key": "escala", "text": "Sempre cobrar escala grafica."},
    )

    assert create_response.status_code == 201
    memory_id = create_response.json()["id"]
    assert client.get("/memories").json()[0]["key"] == "escala"

    delete_response = client.delete(f"/memories/{memory_id}")

    assert delete_response.status_code == 204
    assert client.get("/memories").json() == []
