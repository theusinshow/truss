from pathlib import Path

import pytest

from truss_api.core.settings import Settings
from truss_api.db.connection import transaction
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
from truss_api.sheetmap.elements.models import DetectedElement
from truss_api.sheetmap.technical_scopes import DetectedTechnicalScope
from truss_api.sheetmap.views.models import (
    VIEW_KIND_DETAIL,
    VIEW_KIND_SECTION,
    VIEW_ROLE_GROUPING,
    VIEW_ROLE_SUBVIEW,
    DetectedView,
    MeasuredValue,
)
from tests.factories import make_forms_sheet_pdf_bytes, make_structural_pdf_bytes


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
    assert sheet_map["sheet_code_raw"] == "EST-0010-A"
    assert sheet_map["sheet_type"] == "planta_locacao"
    assert (settings.data_dir / str(sheet_map["geometry_path"])).exists()
    assert any(r["region_kind"] == "carimbo" for r in sheet_map["regions"])


def test_build_is_idempotent_and_does_not_duplicate_regions(
    settings: Settings, document: dict[str, object]
) -> None:
    build_sheet_map_for_document(str(document["id"]), settings)
    once = sheetmap_repository.get_sheet_map(
        str(document["sheets"][0]["id"]), settings
    )

    build_sheet_map_for_document(str(document["id"]), settings)
    twice = sheetmap_repository.get_sheet_map(
        str(document["sheets"][0]["id"]), settings
    )

    # O numero de zonas de desenho depende do que ocupa a moldura, entao o que
    # importa e a estabilidade entre construcoes, nao uma contagem fixa.
    assert len(twice["regions"]) == len(once["regions"])
    assert [region["region_kind"] for region in twice["regions"]] == [
        region["region_kind"] for region in once["regions"]
    ]
    assert any(region["region_kind"] == "moldura" for region in once["regions"])
    assert any(region["region_kind"] == "area_desenho" for region in once["regions"])


def test_get_sheet_map_raises_when_missing(settings: Settings) -> None:
    with pytest.raises(sheetmap_repository.SheetMapNotFoundError):
        sheetmap_repository.get_sheet_map("missing-sheet", settings)


def test_rebuilding_the_same_input_reuses_the_snapshot(
    settings: Settings, document: dict[str, object]
) -> None:
    first = build_sheet_map_for_document(str(document["id"]), settings)
    second = build_sheet_map_for_document(str(document["id"]), settings)

    assert [item["id"] for item in first] == [item["id"] for item in second]

    with transaction(settings) as connection:
        total = connection.execute("SELECT COUNT(*) FROM sheet_maps").fetchone()[0]
    assert total == len(first), "reprocessar entrada identica nao pode criar snapshot novo"


def test_previous_snapshot_survives_a_pipeline_change(
    settings: Settings, document: dict[str, object]
) -> None:
    """Um Sheet Map referenciado por auditoria nunca pode ser apagado."""
    built = build_sheet_map_for_document(str(document["id"]), settings)
    original_id = str(built[0]["id"])

    sheet = document["sheets"][0]
    sheetmap_repository.save_sheet_map(
        sheet_id=str(sheet["id"]),
        project_id=str(sheet["project_id"]),
        revision_id=str(sheet["revision_id"]),
        geometry_path="geometry/p/r/s.other.json.gz",
        sheet_code="EST-0010-A",
        sheet_type="planta_formas",
        paper_format="A1",
        orientation="paisagem",
        title_block={},
        regions=[],
        views=[],
        snapshot_hash="0000000000000001",
        extractor_version="extract-v0.2",
        document_hash="abc",
        settings=settings,
    )

    with transaction(settings) as connection:
        rows = connection.execute(
            "SELECT id FROM sheet_maps WHERE sheet_id = ?", (str(sheet["id"]),)
        ).fetchall()

    assert original_id in {str(row["id"]) for row in rows}
    assert len(rows) == 2


def test_current_sheet_map_is_the_most_recent_snapshot(
    settings: Settings, document: dict[str, object]
) -> None:
    build_sheet_map_for_document(str(document["id"]), settings)
    sheet = document["sheets"][0]

    newer = sheetmap_repository.save_sheet_map(
        sheet_id=str(sheet["id"]),
        project_id=str(sheet["project_id"]),
        revision_id=str(sheet["revision_id"]),
        geometry_path="geometry/p/r/s.other.json.gz",
        sheet_code="EST-0010-Z",
        sheet_type="planta_formas",
        paper_format="A1",
        orientation="paisagem",
        title_block={},
        regions=[],
        views=[],
        snapshot_hash="0000000000000002",
        extractor_version="extract-v0.2",
        document_hash="abc",
        settings=settings,
    )

    current = sheetmap_repository.get_sheet_map(str(sheet["id"]), settings)

    assert current["id"] == newer["id"]
    assert current["sheet_code"] == "EST-0010-Z"


def test_snapshot_persists_views_keeping_raw_and_normalized_apart(
    settings: Settings, document: dict[str, object]
) -> None:
    """O nivel bruto "-650" nunca vira "-6.50 m" sem confirmacao humana."""
    sheet = document["sheets"][0]
    view = DetectedView(
        view_kind=VIEW_KIND_SECTION,
        identifier="1",
        title=MeasuredValue(raw="CORTE A-A"),
        declared_scale=MeasuredValue(raw="ESCALA 1:50", normalized="1:50"),
        level=MeasuredValue(raw="-650"),
        bbox=(10.0, 20.0, 30.0, 40.0),
        confidence=0.8,
        provenance="anchor",
    )

    saved = sheetmap_repository.save_sheet_map(
        sheet_id=str(sheet["id"]),
        project_id=str(sheet["project_id"]),
        revision_id=str(sheet["revision_id"]),
        geometry_path="geometry/p/r/s.views.json.gz",
        sheet_code="EST-0010-A",
        sheet_type="planta_formas",
        paper_format="A1",
        orientation="paisagem",
        title_block={},
        regions=[],
        views=[view],
        snapshot_hash="0000000000000003",
        extractor_version="extract-v0.2",
        document_hash="abc",
        settings=settings,
    )

    stored = saved["views"][0]

    assert stored["view_kind"] == VIEW_KIND_SECTION
    assert stored["identifier"] == "1"
    assert stored["title_raw"] == "CORTE A-A"
    assert stored["declared_scale_raw"] == "ESCALA 1:50"
    assert stored["declared_scale"] == "1:50"
    assert stored["level_raw"] == "-650"
    assert stored["level"] is None, "nivel nao pode ser normalizado sem confirmacao humana"


def test_snapshot_persists_element_occurrence_linked_to_its_view(
    settings: Settings, document: dict[str, object]
) -> None:
    sheet = document["sheets"][0]
    view = DetectedView(
        view_kind=VIEW_KIND_DETAIL,
        identifier=None,
        title=MeasuredValue(raw="DETALHAMENTO PILARES"),
        declared_scale=MeasuredValue(raw="ESCALA 1:20", normalized="1:20"),
        level=MeasuredValue(raw=None),
        bbox=(0.0, 0.0, 100.0, 100.0),
        confidence=0.9,
        provenance="test",
        technical_scope="armaduras",
    )
    element = DetectedElement(
        element_kind="pillar",
        code_raw="P 12",
        code="P12",
        bbox=(10.0, 20.0, 30.0, 40.0),
        confidence=0.95,
        provenance="native-text/pillar-code-v1",
        attributes={"source_text": "P 12", "association_status": "view_matched"},
        view_index=0,
        technical_scope="armaduras",
    )

    saved = sheetmap_repository.save_sheet_map(
        sheet_id=str(sheet["id"]),
        project_id=str(sheet["project_id"]),
        revision_id=str(sheet["revision_id"]),
        geometry_path="geometry/p/r/s.elements.json.gz",
        sheet_code="EST-0010-A",
        sheet_type="planta_armaduras",
        paper_format="A1",
        orientation="paisagem",
        title_block={},
        regions=[],
        views=[view],
        elements=[element],
        snapshot_hash="0000000000000006",
        extractor_version="extract-v0.2",
        document_hash="abc",
        settings=settings,
    )

    stored = saved["elements"][0]
    assert stored["code_raw"] == "P 12"
    assert stored["code"] == "P12"
    assert stored["view_id"] == saved["views"][0]["id"]
    assert stored["technical_scope"] == "armaduras"
    assert stored["attributes"]["association_status"] == "view_matched"


def test_snapshot_persists_multiple_scopes_and_view_scope(
    settings: Settings, document: dict[str, object]
) -> None:
    sheet = document["sheets"][0]
    view = DetectedView(
        view_kind=VIEW_KIND_DETAIL,
        identifier="1",
        title=MeasuredValue(raw="ARMACAO POSITIVA DA LAJE"),
        declared_scale=MeasuredValue(raw="ESCALA 1:20", normalized="1:20"),
        level=MeasuredValue(raw=None),
        bbox=(10.0, 20.0, 30.0, 40.0),
        confidence=0.9,
        provenance="anchor",
        technical_scope="armaduras",
    )

    saved = sheetmap_repository.save_sheet_map(
        sheet_id=str(sheet["id"]),
        project_id=str(sheet["project_id"]),
        revision_id=str(sheet["revision_id"]),
        geometry_path="geometry/p/r/s.multiscope.json.gz",
        sheet_code="EST-0010-A",
        sheet_type="desconhecido",
        paper_format="A1",
        orientation="paisagem",
        title_block={},
        technical_scopes=[
            DetectedTechnicalScope("formas", 0.92, "titulo_ou_carimbo"),
            DetectedTechnicalScope("armaduras", 0.92, "titulo_ou_carimbo"),
        ],
        regions=[],
        views=[view],
        snapshot_hash="0000000000000005",
        extractor_version="extract-v0.2",
        document_hash="abc",
        settings=settings,
    )

    assert [item["technical_scope"] for item in saved["technical_scopes"]] == [
        "formas",
        "armaduras",
    ]
    assert saved["views"][0]["technical_scope"] == "armaduras"


def test_snapshot_persists_subviews_under_their_grouping_detail(
    settings: Settings, document: dict[str, object]
) -> None:
    sheet = document["sheets"][0]
    grouping = DetectedView(
        view_kind=VIEW_KIND_DETAIL,
        identifier="01",
        title=MeasuredValue(raw="DETALHE 01/02 LAJE PRE-FABRICADA"),
        declared_scale=MeasuredValue(raw="ESCALA 1:20", normalized="1:20"),
        level=MeasuredValue(raw=None),
        bbox=(0.0, 0.0, 100.0, 100.0),
        confidence=0.7,
        provenance="anchor",
        view_role=VIEW_ROLE_GROUPING,
        subviews=[
            DetectedView(
                view_kind=VIEW_KIND_DETAIL,
                identifier="02",
                title=MeasuredValue(raw=None),
                declared_scale=MeasuredValue(raw=None),
                level=MeasuredValue(raw=None),
                bbox=(10.0, 10.0, 40.0, 40.0),
                confidence=0.6,
                provenance="subview",
                view_role=VIEW_ROLE_SUBVIEW,
            )
        ],
    )

    saved = sheetmap_repository.save_sheet_map(
        sheet_id=str(sheet["id"]),
        project_id=str(sheet["project_id"]),
        revision_id=str(sheet["revision_id"]),
        geometry_path="geometry/p/r/s.sub.json.gz",
        sheet_code="EST-0010-A",
        sheet_type="planta_formas",
        paper_format="A1",
        orientation="paisagem",
        title_block={},
        regions=[],
        views=[grouping],
        snapshot_hash="0000000000000004",
        extractor_version="extract-v0.2",
        document_hash="abc",
        settings=settings,
    )

    parent = next(v for v in saved["views"] if v["view_role"] == VIEW_ROLE_GROUPING)
    child = next(v for v in saved["views"] if v["view_role"] == VIEW_ROLE_SUBVIEW)

    assert child["parent_view_id"] == parent["id"]
    assert parent["parent_view_id"] is None


def test_sheet_without_a_scale_declaration_yields_no_views(
    settings: Settings, document: dict[str, object]
) -> None:
    """Propriedade de seguranca que substitui o gate por sheet_type.

    O detector so constroi view a partir de uma ancora ESCALA explicita, entao
    uma folha que nao declara escala nao produz view - independente de como ela
    foi classificada.
    """
    built = build_sheet_map_for_document(str(document["id"]), settings)

    assert all(sheet_map["views"] == [] for sheet_map in built)


def test_forms_sheet_persists_its_detected_views_end_to_end(settings: Settings) -> None:
    project = projects_repository.create_project(ProjectCreate(name="F"), settings)
    revision = projects_repository.create_revision(
        str(project["id"]), RevisionCreate(notes="R"), settings
    )
    prepared = prepare_pdf_storage(
        content=make_forms_sheet_pdf_bytes(),
        filename="formas.pdf",
        project_id=str(project["id"]),
        revision_id=str(revision["id"]),
        settings=settings,
    )
    document = documents_repository.create_document_from_prepared_pdf(
        project_id=str(project["id"]),
        revision_id=str(revision["id"]),
        prepared_pdf=prepared,
        settings=settings,
    )

    built = build_sheet_map_for_document(str(document["id"]), settings)
    views = {view["title_raw"]: view for view in built[0]["views"]}

    assert set(views) == {
        "PLANTA DE FORMAS - TERREO",
        "CORTE A-A",
        "DETALHE 01 LAJE",
    }
    assert views["PLANTA DE FORMAS - TERREO"]["view_kind"] == "plan"
    assert views["CORTE A-A"]["view_kind"] == "section"
    assert views["DETALHE 01 LAJE"]["view_kind"] == "detail"
    assert views["PLANTA DE FORMAS - TERREO"]["declared_scale"] == "1:50"
    assert views["CORTE A-A"]["declared_scale"] == "1:50"
    assert views["DETALHE 01 LAJE"]["declared_scale"] == "1:20"
    assert all(view["provenance"] for view in views.values())
