"""Entrada de um projeto novo na calibracao.

Escrever o gabarito de um projeto de 29 folhas a mao e o que impede a
calibracao de crescer. O rascunho e gerado a partir do PDF e o humano corrige,
em vez de digitar - mas nada no rascunho pode se apresentar como confirmado.
"""

from pathlib import Path

import fitz
import pytest
import yaml

from truss_api.calibration.catalog import STATUS_DRAFT, load_ground_truths
from truss_api.calibration.intake import draft_ground_truth, write_draft
from tests.factories import make_forms_sheet_pdf_bytes


@pytest.fixture()
def forms_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "obra-nova.pdf"
    path.write_bytes(make_forms_sheet_pdf_bytes())
    return path


def test_draft_records_the_document_identity_by_hash(forms_pdf: Path) -> None:
    draft = draft_ground_truth(forms_pdf)

    assert draft["document"]["filename"] == "obra-nova.pdf"
    assert len(draft["document"]["sha256"]) == 64
    assert draft["document"]["page_count"] == 1


def test_draft_is_never_presented_as_human_verified(forms_pdf: Path) -> None:
    draft = draft_ground_truth(forms_pdf)

    assert draft["status"] == STATUS_DRAFT
    assert draft["version"] == 4
    for sheet in draft["sheets"]:
        for view in sheet["views"]:
            assert view["human_confirmed"] is False


def test_draft_carries_the_detected_views_for_the_human_to_correct(
    forms_pdf: Path,
) -> None:
    draft = draft_ground_truth(forms_pdf)
    views = draft["sheets"][0]["views"]

    assert [view["title"]["raw"] for view in views] == [
        "PLANTA DE FORMAS - TERREO",
        "CORTE A-A",
        "DETALHE 01 LAJE",
    ]
    assert [view["scale"]["normalized"] for view in views] == ["1:50", "1:50", "1:20"]
    assert [view["view_kind"] for view in views] == ["plan", "section", "detail"]


def test_draft_never_normalizes_a_level_on_its_own(forms_pdf: Path) -> None:
    """Normalizar nivel exige tabela confirmada pelo proprietario."""
    view = draft_ground_truth(forms_pdf)["sheets"][0]["views"][0]

    assert view["level"]["raw"] == "-0.05"
    assert view["level"]["normalized"] is None
    assert view["level"]["needs_human_confirmation"] is True


def test_draft_records_the_bbox_in_pdf_points_as_unverified(forms_pdf: Path) -> None:
    view = draft_ground_truth(forms_pdf)["sheets"][0]["views"][0]

    assert len(view["bbox"]) == 4
    assert view["bbox"][2] > view["bbox"][0]
    assert view["bbox_status"] == STATUS_DRAFT


def test_draft_leaves_expected_findings_open_instead_of_claiming_zero(
    forms_pdf: Path,
) -> None:
    """Um projeto aprovado nao e um projeto sem achados esperados.

    Declarar `confirmed_zero` sozinho faria o gabarito medir o pipeline contra
    a propria saida dele.
    """
    sheet = draft_ground_truth(forms_pdf)["sheets"][0]

    assert sheet["expected_findings"]["status"] == "not_provided"
    assert sheet["approval"] == "unreviewed"


def test_written_draft_is_discovered_by_the_catalog(forms_pdf: Path, tmp_path: Path) -> None:
    target = write_draft(forms_pdf, tmp_path / "obra-nova.yml")

    truth = load_ground_truths(tmp_path)[0]

    assert target.exists()
    assert truth.is_human_verified is False
    assert truth.page_count == 1
    assert yaml.safe_load(target.read_text(encoding="utf-8"))["status"] == STATUS_DRAFT


def test_draft_keeps_pages_where_no_view_was_detected(tmp_path: Path) -> None:
    """Toda página aparece no intake, mesmo quando a segmentação falha."""
    document = fitz.open()
    document.new_page(width=842, height=595).insert_text((72, 72), "SEM ESCALA AQUI")
    path = tmp_path / "vazio.pdf"
    document.save(path)
    document.close()

    draft = draft_ground_truth(path)

    assert len(draft["sheets"]) == 1
    sheet = draft["sheets"][0]
    assert sheet["page_index"] == 0
    assert sheet["views"] == []
    assert sheet["view_detection_status"] == "no_views_detected"
    assert sheet["sheet_code"] is None
    assert sheet["sheet_code_raw"] is None
    assert sheet["sheet_code_status"] == "not_verifiable"
    assert draft["document"]["page_count"] == 1
