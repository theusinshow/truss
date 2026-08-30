"""Piso de ruido do checklist sobre projetos aprovados.

Num projeto que ja foi entregue e aprovado, **todo achado e candidato a falso
positivo**. Isso nao mede cobertura - os defeitos reais nao estao rotulados -
mas mede a unica coisa que decide se a lista e utilizavel: quanto ruido ela
produz num material que passou.

Foi assim que os tres achados espurios das paginas 9, 10 e 11 do projeto-base
apareceram.
"""

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import fitz

from truss_api.rules.engine import evaluate
from truss_api.rules.loader import load_packs
from truss_api.rules.models import OUTCOME_FAIL
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


@dataclass(frozen=True)
class SheetNoise:
    page_index: int
    sheet_code: str | None
    sheet_type: str
    views: int
    findings: list[dict]


@dataclass(frozen=True)
class ProjectNoise:
    name: str
    pages: int
    sheets: list[SheetNoise] = field(default_factory=list)

    @property
    def total_findings(self) -> int:
        return sum(len(sheet.findings) for sheet in self.sheets)

    @property
    def total_views(self) -> int:
        return sum(sheet.views for sheet in self.sheets)

    @property
    def findings_per_sheet(self) -> float:
        return self.total_findings / self.pages if self.pages else 0.0

    def by_rule(self) -> Counter:
        counter: Counter = Counter()
        for sheet in self.sheets:
            for finding in sheet.findings:
                counter[(finding["scope"], finding["rule_id"])] += 1
        return counter


def _as_row(index: int, view: DetectedView) -> dict:
    return {
        "id": f"v{index}",
        "view_kind": view.view_kind,
        "view_role": view.view_role,
        "identifier": view.identifier,
        "title_raw": view.title.raw,
        "title": view.title.normalized,
        "declared_scale_raw": view.declared_scale.raw,
        "declared_scale": view.declared_scale.normalized,
        "level_raw": view.level.raw,
        "level": view.level.normalized,
        "x0": view.bbox[0],
        "y0": view.bbox[1],
        "x1": view.bbox[2],
        "y1": view.bbox[3],
        "confidence": view.confidence,
    }


def measure_project(pdf_path: Path, name: str | None = None) -> ProjectNoise:
    document = fitz.open(pdf_path)
    page_count = document.page_count
    sheets: list[SheetNoise] = []

    try:
        for page_index in range(page_count):
            page = document.load_page(page_index)
            extraction = extract_page(page)
            text_boxes = extract_line_boxes(page)
            regions = detect_regions(geometry_from_extraction(extraction), text_boxes)

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

            views = detect_forms_views(extraction, regions)
            snapshot = {
                "sheet_type": classification.sheet_type,
                "title_block": {"category": fields.category, "title": fields.title},
                "views": [_as_row(index, view) for index, view in enumerate(views)],
                "regions": [
                    {
                        "region_kind": region.region_kind,
                        "x0": region.x0,
                        "y0": region.y0,
                        "x1": region.x1,
                        "y1": region.y1,
                    }
                    for region in regions
                ],
            }

            findings = [
                {
                    "rule_id": evaluation.rule_id,
                    "scope": evaluation.scope,
                    "severity": evaluation.severity,
                    "reason": evaluation.reason,
                    "evidence": evaluation.evidence,
                }
                for pack in load_packs(classification.sheet_type)
                for evaluation in evaluate(pack, snapshot)
                if evaluation.outcome == OUTCOME_FAIL
            ]

            sheets.append(
                SheetNoise(
                    page_index=page_index,
                    sheet_code=fields.sheet_code,
                    sheet_type=classification.sheet_type,
                    views=len(views),
                    findings=findings,
                )
            )
    finally:
        document.close()

    return ProjectNoise(name=name or pdf_path.stem, pages=page_count, sheets=sheets)
