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


@pytest.fixture()
def revision(settings: Settings) -> tuple[str, str]:
    project = repository.create_project(ProjectCreate(name="PDF Project"), settings)
    created_revision = repository.create_revision(
        str(project["id"]),
        RevisionCreate(notes="PDF import"),
        settings,
    )
    return str(project["id"]), str(created_revision["id"])


def make_pdf_bytes(page_count: int = 2) -> bytes:
    document = fitz.open()
    for index in range(page_count):
        page = document.new_page(width=842, height=595)
        page.insert_text((72, 72), f"FORMA PAVIMENTO {index + 1}")

    buffer = BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def test_import_pdf_creates_document_sheets_and_local_copy(
    client: TestClient,
    settings: Settings,
    revision: tuple[str, str],
) -> None:
    project_id, revision_id = revision
    pdf_bytes = make_pdf_bytes(page_count=2)

    response = client.post(
        f"/projects/{project_id}/revisions/{revision_id}/documents",
        files={"file": ("forma.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["original_filename"] == "forma.pdf"
    assert payload["page_count"] == 2
    assert len(payload["sheets"]) == 2
    assert payload["sheets"][0]["width_pt"] == 842
    assert payload["sheets"][0]["height_pt"] == 595
    assert payload["content_hash"]

    stored_file = settings.data_dir / payload["stored_file_path"]
    assert stored_file.exists()
    assert stored_file.read_bytes() == pdf_bytes


def test_sheet_image_endpoint_renders_png(
    client: TestClient,
    settings: Settings,
    revision: tuple[str, str],
) -> None:
    project_id, revision_id = revision
    pdf_bytes = make_pdf_bytes(page_count=1)

    import_response = client.post(
        f"/projects/{project_id}/revisions/{revision_id}/documents",
        files={"file": ("forma.pdf", pdf_bytes, "application/pdf")},
    )
    sheet_id = import_response.json()["sheets"][0]["id"]

    image_response = client.get(f"/sheets/{sheet_id}/image")

    assert image_response.status_code == 200
    assert image_response.headers["content-type"] == "image/png"
    assert image_response.content.startswith(b"\x89PNG")

    detail_response = client.get(f"/documents/{import_response.json()['id']}")
    render_path = detail_response.json()["sheets"][0]["render_path"]
    assert render_path is not None
    assert (settings.data_dir / render_path).exists()


def test_import_pdf_extracts_text_blocks_with_pdf_coordinates(
    client: TestClient,
    revision: tuple[str, str],
) -> None:
    project_id, revision_id = revision
    pdf_bytes = make_pdf_bytes(page_count=1)

    import_response = client.post(
        f"/projects/{project_id}/revisions/{revision_id}/documents",
        files={"file": ("forma.pdf", pdf_bytes, "application/pdf")},
    )
    sheet_id = import_response.json()["sheets"][0]["id"]

    response = client.get(f"/sheets/{sheet_id}/text-blocks")

    assert response.status_code == 200
    blocks = response.json()
    assert len(blocks) >= 1
    assert "FORMA PAVIMENTO 1" in blocks[0]["text"]
    assert blocks[0]["x0"] < blocks[0]["x1"]
    assert blocks[0]["y0"] < blocks[0]["y1"]


def test_import_pdf_rejects_duplicate_content(
    client: TestClient,
    revision: tuple[str, str],
) -> None:
    project_id, revision_id = revision
    pdf_bytes = make_pdf_bytes(page_count=1)

    first_response = client.post(
        f"/projects/{project_id}/revisions/{revision_id}/documents",
        files={"file": ("detalhe.pdf", pdf_bytes, "application/pdf")},
    )
    second_response = client.post(
        f"/projects/{project_id}/revisions/{revision_id}/documents",
        files={"file": ("detalhe.pdf", pdf_bytes, "application/pdf")},
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409


def test_import_pdf_rejects_invalid_pdf(
    client: TestClient,
    revision: tuple[str, str],
) -> None:
    project_id, revision_id = revision

    response = client.post(
        f"/projects/{project_id}/revisions/{revision_id}/documents",
        files={"file": ("not-a-pdf.pdf", b"not a pdf", "application/pdf")},
    )

    assert response.status_code == 400


def test_list_documents_requires_revision_belonging_to_project(
    client: TestClient,
    revision: tuple[str, str],
) -> None:
    _, revision_id = revision

    response = client.get(f"/projects/wrong-project/revisions/{revision_id}/documents")

    assert response.status_code == 404
