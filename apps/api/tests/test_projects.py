from collections.abc import Iterator
from pathlib import Path

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


def test_repository_creates_project_and_immutable_revisions(settings: Settings) -> None:
    project = repository.create_project(
        ProjectCreate(name="Torre Norte", description="Formas e locacao"),
        settings,
    )

    first_revision = repository.create_revision(
        str(project["id"]),
        RevisionCreate(notes="Exportacao inicial"),
        settings,
    )
    second_revision = repository.create_revision(
        str(project["id"]),
        RevisionCreate(notes="Nova emissao"),
        settings,
    )

    persisted = repository.get_project(str(project["id"]), settings)

    assert persisted["name"] == "Torre Norte"
    assert [revision["revision_code"] for revision in persisted["revisions"]] == [
        "REV-001",
        "REV-002",
    ]
    assert first_revision["id"] != second_revision["id"]


def test_repository_rejects_duplicate_revision_code(settings: Settings) -> None:
    project = repository.create_project(ProjectCreate(name="Galpao"), settings)

    repository.create_revision(
        str(project["id"]),
        RevisionCreate(revision_code="R00"),
        settings,
    )

    with pytest.raises(repository.DuplicateRevisionError):
        repository.create_revision(
            str(project["id"]),
            RevisionCreate(revision_code="R00"),
            settings,
        )


def test_projects_api_round_trip(client: TestClient) -> None:
    create_response = client.post(
        "/projects",
        json={"name": "Edificio Alba", "description": "Analise piloto"},
    )

    assert create_response.status_code == 201
    created = create_response.json()
    project_id = created["id"]
    assert created["revisions"] == []

    revision_response = client.post(
        f"/projects/{project_id}/revisions",
        json={"notes": "Revisao cadastrada manualmente"},
    )

    assert revision_response.status_code == 201
    assert revision_response.json()["revision_code"] == "REV-001"

    detail_response = client.get(f"/projects/{project_id}")

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["id"] == project_id
    assert len(detail["revisions"]) == 1

    list_response = client.get("/projects")

    assert list_response.status_code == 200
    assert list_response.json()[0]["latest_revision_code"] == "REV-001"


def test_projects_api_handles_missing_project(client: TestClient) -> None:
    response = client.get("/projects/missing")

    assert response.status_code == 404
