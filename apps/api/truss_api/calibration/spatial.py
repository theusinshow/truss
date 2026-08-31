"""Gabaritos espaciais confirmados por humano, separados dos PDFs locais."""

from dataclasses import dataclass
from pathlib import Path

import yaml

from truss_api.calibration.catalog import CALIBRATION_DIR
from truss_api.sheetmap.views.models import BBox


SPATIAL_CALIBRATION_DIR = CALIBRATION_DIR / "spatial"
VALID_BBOX_SEMANTICS = frozenset({"regular", "grouping_envelope"})


@dataclass(frozen=True)
class SpatialViewTruth:
    ordinal: int
    title_raw: str
    view_kind: str
    technical_scope: str | None
    bbox: BBox
    bbox_semantics: str


@dataclass(frozen=True)
class SpatialSheetTruth:
    filename: str
    sha256: str
    page_index: int
    sheet_code: str | None
    sheet_code_raw: str | None
    views: tuple[SpatialViewTruth, ...]


@dataclass(frozen=True)
class SpatialGroundTruth:
    path: Path
    version: int
    status: str
    coordinate_system: str
    review_source: str
    minimum_iou: float
    sheets: tuple[SpatialSheetTruth, ...]


def _bbox(value: object) -> BBox:
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError("bbox espacial deve conter quatro coordenadas")

    x0, y0, x1, y1 = (float(item) for item in value)
    if x1 <= x0 or y1 <= y0:
        raise ValueError("bbox espacial deve possuir area positiva")
    return (x0, y0, x1, y1)


def _load(path: Path) -> SpatialGroundTruth:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sheets: list[SpatialSheetTruth] = []

    for document in payload.get("documents", []):
        for sheet in document.get("sheets", []):
            views = tuple(
                SpatialViewTruth(
                    ordinal=int(view["ordinal"]),
                    title_raw=str(view["title_raw"]),
                    view_kind=str(view["view_kind"]),
                    technical_scope=view.get("technical_scope"),
                    bbox=_bbox(view["bbox"]),
                    bbox_semantics=str(view["bbox_semantics"]),
                )
                for view in sheet.get("views", [])
            )
            sheets.append(
                SpatialSheetTruth(
                    filename=str(document["filename"]),
                    sha256=str(document["sha256"]),
                    page_index=int(sheet["page_index"]),
                    sheet_code=sheet.get("sheet_code"),
                    sheet_code_raw=sheet.get("sheet_code_raw"),
                    views=views,
                )
            )

    return SpatialGroundTruth(
        path=path,
        version=int(payload.get("version", 1)),
        status=str(payload.get("status", "unverified")),
        coordinate_system=str(payload.get("coordinate_system", "")),
        review_source=str(payload.get("review_source", "")),
        minimum_iou=float(payload.get("minimum_iou", 0.0)),
        sheets=tuple(sheets),
    )


def load_spatial_ground_truths(
    directory: Path | None = None,
) -> list[SpatialGroundTruth]:
    resolved = directory or SPATIAL_CALIBRATION_DIR
    return [_load(path) for path in sorted(resolved.glob("*.yml"))]


def bbox_iou(left: BBox, right: BBox) -> float:
    intersection_width = max(0.0, min(left[2], right[2]) - max(left[0], right[0]))
    intersection_height = max(0.0, min(left[3], right[3]) - max(left[1], right[1]))
    intersection = intersection_width * intersection_height
    if intersection == 0:
        return 0.0

    left_area = (left[2] - left[0]) * (left[3] - left[1])
    right_area = (right[2] - right[0]) * (right[3] - right[1])
    return intersection / (left_area + right_area - intersection)
