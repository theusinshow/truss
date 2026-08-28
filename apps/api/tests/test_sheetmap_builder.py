from pathlib import Path

import pytest

from truss_api.core.settings import Settings
from truss_api.db.schema import initialize_database
from truss_api.documents import repository as documents_repository
from truss_api.documents.importer import prepare_pdf_storage
from truss_api.projects import repository as projects_repository
from truss_api.projects.models import ProjectCreate, RevisionCreate
from truss_api.sheetmap import repository as sheetmap_repository
from truss_api.sheetmap.builder import (
    build_sheet_map_for_document,
    orientation_for,
    paper_format_for,
)
from tests.factories import make_structural_pdf_bytes


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    resolved = Settings(data_dir=tmp_path / "data")
    initialize_database(resolved)
    return resolved


@pytest.fixture()
def document(settings: Settings) -> dict[str, object]:
    project = projects_repository.create_project(ProjectCreate(name="P"), settings)
    revision = projects_repository.create_revision(
        str(project["id"]), RevisionCreate(notes="R"), settings
    )
    prepared = prepare_pdf_storage(
        content=make_structural_pdf_bytes(),
        filename="obra.pdf",
        project_id=str(project["id"]),
        revision_id=str(revision["id"]),
        settings=settings,
    )
    return documents_repository.create_document_from_prepared_pdf(
        project_id=str(project["id"]),
        revision_id=str(revision["id"]),
        prepared_pdf=prepared,
        settings=settings,
    )


def test_paper_format_and_orientation() -> None:
    assert paper_format_for(2384, 1684) == "A1"
    assert paper_format_for(3370, 2384) == "A0"
    assert paper_format_for(1000, 800) == "personalizado"
    assert orientation_for(2384, 1684) == "paisagem"


def test_build_persists_identity_type_and_geometry_per_sheet(
    settings: Settings, document: dict[str, object]
) -> None:
    built = build_sheet_map_for_document(str(document["id"]), settings)

    assert len(built) == 3

    first_sheet = document["sheets"][0]
    sheet_map = sheetmap_repository.get_sheet_map(str(first_sheet["id"]), settings)

    assert sheet_map["sheet_code"] == "EST-0010-A"
    assert sheet_map["sheet_type"] == "planta_locacao"
    assert (settings.data_dir / str(sheet_map["geometry_path"])).exists()
    assert any(r["region_kind"] == "carimbo" for r in sheet_map["regions"])


def test_build_is_idempotent_and_does_not_duplicate_regions(
    settings: Settings, document: dict[str, object]
) -> None:
    build_sheet_map_for_document(str(document["id"]), settings)
    build_sheet_map_for_document(str(document["id"]), settings)

    first_sheet = document["sheets"][0]
    sheet_map = sheetmap_repository.get_sheet_map(str(first_sheet["id"]), settings)

    assert len(sheet_map["regions"]) == 3


def test_get_sheet_map_raises_when_missing(settings: Settings) -> None:
    with pytest.raises(sheetmap_repository.SheetMapNotFoundError):
        sheetmap_repository.get_sheet_map("missing-sheet", settings)
