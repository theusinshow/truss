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
