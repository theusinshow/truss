from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from truss_api.core.settings import Settings, get_settings
from truss_api.db.schema import initialize_database
from truss_api.main import app
from tests.factories import make_structural_pdf_bytes


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


def test_import_builds_sheet_map_and_endpoint_serves_it(client: TestClient) -> None:
    project = client.post("/projects", json={"name": "Obra"}).json()
    revision = client.post(
        f"/projects/{project['id']}/revisions", json={"notes": "R01"}
    ).json()
    imported = client.post(
        f"/projects/{project['id']}/revisions/{revision['id']}/documents",
        files={"file": ("obra.pdf", make_structural_pdf_bytes(), "application/pdf")},
    ).json()

    response = client.get(f"/sheets/{imported['sheets'][0]['id']}/sheet-map")

    assert response.status_code == 200
    payload = response.json()
    assert payload["sheet_code"] == "EST-0010-A"
    assert payload["sheet_type"] == "planta_locacao"
    assert payload["technical_scopes"] == [
        {
            "technical_scope": "locacao",
            "confidence": 0.97,
            "provenance": "sheet_type",
        }
    ]
    assert any(region["region_kind"] == "carimbo" for region in payload["regions"])
    # As views chegam vazias ate a Task 7, mas o contrato ja as expoe: sem o
    # campo no response_model o pydantic descartaria silenciosamente o snapshot.
    assert payload["views"] == []
    assert payload["pipeline_version"].startswith("sheetmap-v0.8+")
    assert payload["sheet_code_raw"] == payload["sheet_code"]
    assert payload["elements"] == []


def test_sheet_map_endpoint_returns_404_for_unknown_sheet(client: TestClient) -> None:
    assert client.get("/sheets/does-not-exist/sheet-map").status_code == 404
