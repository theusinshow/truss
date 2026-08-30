"""Rascunho de gabarito a partir de um PDF.

Escrever a mao o gabarito de um projeto de 29 folhas e o que impede a
calibracao de crescer. O rascunho carrega o que o pipeline detectou para o
humano **corrigir**, nao para o pipeline se medir contra a propria saida: nada
aqui sai marcado como confirmado, e nenhuma folha declara zero achados
esperados.
"""

from hashlib import sha256
from pathlib import Path

import fitz
import yaml

from truss_api.calibration.catalog import STATUS_DRAFT
from truss_api.sheetmap.classifier import classify_sheet_type
from truss_api.sheetmap.geometry import geometry_from_extraction
from truss_api.sheetmap.primitives import extract_page
from truss_api.sheetmap.regions import (
    REGION_TITLE_BLOCK,
    detect_regions,
    extract_line_boxes,
)
from truss_api.sheetmap.title_block import TitleBlockFields, parse_title_block
from truss_api.sheetmap.views.detector import detect_forms_views
from truss_api.sheetmap.views.models import DetectedView


DEFAULT_THRESHOLDS = {
    "content_block_recall": 0.85,
    "content_block_iou": 0.50,
    "view_attribute_accuracy": 0.90,
    "finding_coverage": 0.60,
    "finding_precision": 0.70,
}


def _document_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _view_entry(ordinal: int, view: DetectedView) -> dict:
    return {
        "ordinal": ordinal,
        "view_kind": view.view_kind,
        "role": view.view_role,
        "identifier": view.identifier,
        "title": {"raw": view.title.raw},
        "scale": {
            "raw": view.declared_scale.raw,
            "normalized": view.declared_scale.normalized,
        },
        # Normalizar nivel exige a tabela confirmada pelo proprietario.
        "level": {
            "raw": view.level.raw,
            "normalized": None,
            "needs_human_confirmation": True,
        },
        "bbox": [round(value, 1) for value in view.bbox],
        "bbox_status": STATUS_DRAFT,
        "human_confirmed": False,
    }


def draft_ground_truth(pdf_path: Path) -> dict:
    document = fitz.open(pdf_path)
    page_count = document.page_count
    sheets: list[dict] = []

    try:
        for page_index in range(page_count):
            page = document.load_page(page_index)
            extraction = extract_page(page)
            text_boxes = extract_line_boxes(page)
            regions = detect_regions(geometry_from_extraction(extraction), text_boxes)

            views = detect_forms_views(extraction, regions)
            if not views:
                # Folha sem escala declarada nao vira linha de gabarito vazia.
                continue

            title_block_region = next(
                (r for r in regions if r.region_kind == REGION_TITLE_BLOCK), None
            )
            fields = (
                parse_title_block(title_block_region, text_boxes)
                if title_block_region
                else TitleBlockFields(None, None, None, None)
            )
            classification = classify_sheet_type(
                fields, " ".join(box.text for box in text_boxes)
            )

            sheets.append(
                {
                    "page_index": page_index,
                    "sheet_code": fields.sheet_code,
                    "sheet_role": classification.sheet_type,
                    "approval": "unreviewed",
                    "views": [
                        _view_entry(index + 1, view) for index, view in enumerate(views)
                    ],
                    # Um projeto aprovado nao e um projeto sem achados esperados.
                    # Declarar `confirmed_zero` aqui faria o gabarito medir o
                    # pipeline contra a saida do proprio pipeline.
                    "expected_findings": {
                        "status": "not_provided",
                        "note": "folha ainda nao revisada por humano",
                    },
                }
            )
    finally:
        document.close()

    return {
        "version": 3,
        "status": STATUS_DRAFT,
        "source": {
            "generated_from": "pipeline",
            "note": (
                "Rascunho gerado pelo pipeline para revisao humana. Enquanto o status "
                "for draft_unverified, este arquivo mede regressao, nao correcao."
            ),
        },
        "document": {
            "filename": pdf_path.name,
            "sha256": _document_hash(pdf_path),
            "page_count": page_count,
        },
        "thresholds": dict(DEFAULT_THRESHOLDS),
        "sheets": sheets,
    }


def write_draft(pdf_path: Path, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        yaml.safe_dump(draft_ground_truth(pdf_path), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return target
