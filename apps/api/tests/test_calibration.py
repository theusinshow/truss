from pathlib import Path

import pytest
import yaml

from truss_api.core.settings import Settings
from truss_api.db.schema import initialize_database
from truss_api.documents import repository as documents_repository
from truss_api.documents.importer import prepare_pdf_storage
from truss_api.projects import repository as projects_repository
from truss_api.projects.models import ProjectCreate, RevisionCreate
from truss_api.sheetmap import repository as sheetmap_repository
from truss_api.sheetmap.builder import build_sheet_map_for_document


REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = REPO_ROOT / "calibration" / "rancho-queimado-r01.yml"


def _find_reference_pdf(filename: str) -> Path | None:
    matches = sorted((REPO_ROOT / "data" / "originals").rglob(f"*{filename}"))
    return matches[0] if matches else None


def test_sheet_map_matches_calibration_ground_truth(tmp_path: Path) -> None:
    expected = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    pdf_path = _find_reference_pdf(expected["document"]["filename"])

    if pdf_path is None:
        pytest.skip(
            f"PDF de referencia ausente: {expected['document']['filename']}. "
            "Importe o projeto localmente para rodar a calibracao."
        )

    settings = Settings(data_dir=tmp_path / "data")
    initialize_database(settings)

    project = projects_repository.create_project(ProjectCreate(name="Calibracao"), settings)
    revision = projects_repository.create_revision(
        str(project["id"]), RevisionCreate(notes="R01"), settings
    )
    prepared = prepare_pdf_storage(
        content=pdf_path.read_bytes(),
        filename=expected["document"]["filename"],
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
    build_sheet_map_for_document(str(document["id"]), settings)

    sheets_by_page = {
        int(sheet["page_index"]): str(sheet["id"]) for sheet in document["sheets"]
    }

    type_hits = 0
    code_hits = 0
    failures: list[str] = []

    for entry in expected["sheets"]:
        page_index = int(entry["page_index"])
        sheet_map = sheetmap_repository.get_sheet_map(sheets_by_page[page_index], settings)

        if sheet_map["sheet_code"] == entry["sheet_code"]:
            code_hits += 1
        else:
            failures.append(
                f"pagina {page_index}: codigo {sheet_map['sheet_code']} != {entry['sheet_code']}"
            )

        if sheet_map["sheet_type"] == entry["sheet_type"]:
            type_hits += 1
        else:
            failures.append(
                f"pagina {page_index}: tipo {sheet_map['sheet_type']} != {entry['sheet_type']}"
            )

    total = len(expected["sheets"])
    type_accuracy = type_hits / total
    code_coverage = code_hits / total

    print(f"\ncalibracao: tipo {type_accuracy:.1%} | codigo {code_coverage:.1%} ({total} folhas)")
    for failure in failures:
        print(f"  {failure}")

    assert type_accuracy >= expected["minimum_type_accuracy"]
    assert code_coverage >= expected["minimum_code_coverage"]


FORMS_FIXTURE = REPO_ROOT / "calibration" / "juliano-corbellini-r05.yml"
BASE_PROJECT_PDF = (
    REPO_ROOT / "docs" / "projeto_base" / "Projeto Estrutural_Juliano Corbellini_R05.pdf"
)


def _paired_with_ground_truth(detected, expected_views):
    """Casa cada view detectada com a do gabarito de mesma escala e titulo.

    O pareamento exige a escala **e** o titulo: sem a escala, uma view que
    pegasse qualquer titulo da mesma folha contaria como acerto.
    """
    from truss_api.core.text import normalize

    def scale_key(raw: str | None) -> str:
        text = normalize(str(raw or ""))
        return text if ":" in text else "NAO_NUMERICA"

    pool = [
        (scale_key(view["scale"]["raw"]), normalize(view["title"]["raw"]))
        for view in expected_views
    ]
    matched = 0

    for view in detected:
        title = normalize(view.title.raw) if view.title.raw else None
        scale = view.declared_scale.normalized or "NAO_NUMERICA"
        hit = next(
            (
                index
                for index, (expected_scale, expected_title) in enumerate(pool)
                if expected_scale == scale
                and title
                and (title.startswith(expected_title[:20]) or expected_title.startswith(title[:20]))
            ),
            None,
        )
        if hit is not None:
            matched += 1
            pool.pop(hit)

    return matched


def test_view_detection_meets_calibration_thresholds() -> None:
    """Mede a deteccao de views contra o gabarito humano do projeto-base.

    O gabarito nao tem caixa espacial, so `position_hint` em texto livre, entao
    recall por IoU **nao e computavel** e nao e afirmado aqui. O que se mede e o
    que o gabarito sustenta: quantidade de views, atributos declarados e a
    associacao correta de titulo e escala.
    """
    import fitz

    from truss_api.sheetmap.geometry import geometry_from_extraction
    from truss_api.sheetmap.primitives import extract_page
    from truss_api.sheetmap.regions import detect_regions, extract_line_boxes
    from truss_api.sheetmap.views.detector import detect_forms_views

    if not BASE_PROJECT_PDF.exists():
        pytest.skip(f"PDF do projeto-base ausente: {BASE_PROJECT_PDF.name}")

    expected = yaml.safe_load(FORMS_FIXTURE.read_text(encoding="utf-8"))
    thresholds = expected["thresholds"]
    document = fitz.open(BASE_PROJECT_PDF)

    detected_total = expected_total = attributes_ok = associated = 0

    for sheet in expected["sheets"]:
        page = document.load_page(sheet["page_index"])
        extraction = extract_page(page)
        regions = detect_regions(geometry_from_extraction(extraction), extract_line_boxes(page))
        detected = detect_forms_views(extraction, regions)

        detected_total += len(detected)
        expected_total += len(sheet.get("views", []))
        attributes_ok += sum(
            1 for view in detected if view.title.raw and view.declared_scale.raw
        )
        associated += _paired_with_ground_truth(detected, sheet.get("views", []))

    attribute_accuracy = attributes_ok / detected_total if detected_total else 0.0
    association_accuracy = associated / detected_total if detected_total else 0.0

    print(
        f"\nviews: {detected_total} detectadas / {expected_total} no gabarito"
        f" | atributos {attribute_accuracy:.1%}"
        f" | titulo+escala corretos {association_accuracy:.1%}"
    )
    if expected["status"] != "human_verified":
        print("AVISO: gabarito draft_unverified - detecta regressao, nao prova correcao.")
    print("AVISO: bboxes nao sao medidos - o gabarito nao tem caixa espacial.")

    assert detected_total == expected_total
    assert attribute_accuracy >= thresholds["view_attribute_accuracy"]
    assert association_accuracy >= thresholds["view_attribute_accuracy"]
