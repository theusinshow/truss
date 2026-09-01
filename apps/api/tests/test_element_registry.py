from pathlib import Path

import pytest

from truss_api.core.settings import Settings
from truss_api.db.schema import initialize_database
from truss_api.documents import repository as documents_repository
from truss_api.documents.importer import prepare_pdf_storage
from truss_api.projects import repository as projects_repository
from truss_api.projects.models import ProjectCreate, RevisionCreate
from truss_api.sheetmap import repository as sheetmap_repository
from truss_api.sheetmap.elements.models import DetectedElement
from truss_api.sheetmap.elements.registry import build_revision_registry, pillar_detail_views
from truss_api.sheetmap.views.models import DetectedView, MeasuredValue
from tests.factories import make_structural_pdf_bytes


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    resolved = Settings(data_dir=tmp_path / "data")
    initialize_database(resolved)
    return resolved


def _document(settings: Settings, name="Registry") -> dict[str, object]:
    project = projects_repository.create_project(ProjectCreate(name=name), settings)
    revision = projects_repository.create_revision(
        str(project["id"]), RevisionCreate(notes="R"), settings
    )
    prepared = prepare_pdf_storage(
        content=make_structural_pdf_bytes(),
        filename=f"{name}.pdf",
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


def _view(title: str, scope: str) -> DetectedView:
    return DetectedView(
        view_kind="detail" if scope == "armaduras" else "plan",
        identifier=None,
        title=MeasuredValue(raw=title),
        declared_scale=MeasuredValue(raw="ESCALA 1:50", normalized="1:50"),
        level=MeasuredValue(raw=None),
        bbox=(0.0, 0.0, 500.0, 500.0),
        confidence=0.9,
        provenance="test",
        technical_scope=scope,
    )


def _element(code: str, scope: str) -> DetectedElement:
    return DetectedElement(
        element_kind="pillar",
        code_raw=code,
        code=code,
        bbox=(10.0, 10.0, 30.0, 30.0),
        confidence=0.95,
        provenance="test",
        attributes={"association_status": "view_matched"},
        view_index=0,
        technical_scope=scope,
    )


def _save(sheet: dict, *, view: DetectedView, elements, snapshot_hash: str, settings: Settings):
    return sheetmap_repository.save_sheet_map(
        sheet_id=str(sheet["id"]),
        project_id=str(sheet["project_id"]),
        revision_id=str(sheet["revision_id"]),
        geometry_path="geometry/test.json.gz",
        sheet_code=str(sheet["label"]),
        sheet_type="planta_armaduras" if view.technical_scope == "armaduras" else "planta_formas",
        paper_format="A1",
        orientation="paisagem",
        title_block={},
        regions=[],
        views=[view],
        elements=elements,
        snapshot_hash=snapshot_hash,
        extractor_version="test",
        document_hash="doc",
        settings=settings,
    )


def test_registry_groups_current_occurrences_and_recognizes_pillar_target(settings: Settings):
    document = _document(settings)
    source, target = document["sheets"][:2]
    _save(
        source,
        view=_view("PLANTA DE FORMAS", "formas"),
        elements=[_element("P1", "formas")],
        snapshot_hash="source-1",
        settings=settings,
    )
    _save(
        target,
        view=_view("DETALHAMENTO PILARES", "armaduras"),
        elements=[_element("P1", "armaduras")],
        snapshot_hash="target-1",
        settings=settings,
    )

    registry = build_revision_registry(str(source["revision_id"]), settings)

    assert [item["code"] for item in registry["occurrences"]] == ["P1", "P1"]
    assert len(pillar_detail_views(registry)) == 1
    assert len(registry["registry_hash"]) == 24


def test_new_target_snapshot_changes_fingerprint_and_hides_historical_occurrence(settings: Settings):
    document = _document(settings)
    source, target = document["sheets"][:2]
    _save(
        source,
        view=_view("PLANTA DE FORMAS", "formas"),
        elements=[_element("P1", "formas")],
        snapshot_hash="source-1",
        settings=settings,
    )
    _save(
        target,
        view=_view("DETALHAMENTO PILARES", "armaduras"),
        elements=[_element("P1", "armaduras")],
        snapshot_hash="target-1",
        settings=settings,
    )
    first = build_revision_registry(str(source["revision_id"]), settings)

    _save(
        target,
        view=_view("DETALHAMENTO PILARES", "armaduras"),
        elements=[_element("P2", "armaduras")],
        snapshot_hash="target-2",
        settings=settings,
    )
    second = build_revision_registry(str(source["revision_id"]), settings)

    target_codes = [
        item["code"]
        for item in second["occurrences"]
        if item["technical_scope"] == "armaduras"
    ]
    assert target_codes == ["P2"]
    assert second["registry_hash"] != first["registry_hash"]


def test_registry_never_mixes_revisions(settings: Settings):
    first = _document(settings, "First")
    second = _document(settings, "Second")
    _save(
        first["sheets"][0],
        view=_view("PLANTA DE FORMAS", "formas"),
        elements=[_element("P1", "formas")],
        snapshot_hash="first",
        settings=settings,
    )
    _save(
        second["sheets"][0],
        view=_view("PLANTA DE FORMAS", "formas"),
        elements=[_element("P99", "formas")],
        snapshot_hash="second",
        settings=settings,
    )

    registry = build_revision_registry(str(first["revision_id"]), settings)

    assert {item["code"] for item in registry["occurrences"]} == {"P1"}

