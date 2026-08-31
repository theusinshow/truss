from pathlib import Path

import fitz
import pytest

from truss_api.calibration.spatial import (
    VALID_BBOX_SEMANTICS,
    bbox_iou,
    load_spatial_ground_truths,
)
from truss_api.core.text import normalize
from truss_api.sheetmap.geometry import geometry_from_extraction
from truss_api.sheetmap.primitives import extract_page
from truss_api.sheetmap.regions import detect_regions, extract_line_boxes
from truss_api.sheetmap.views.detector import detect_forms_views


REPO_ROOT = Path(__file__).resolve().parents[3]
LOCAL_APPROVED = REPO_ROOT / "data" / "knowledge-inbox" / "approved"


def test_bbox_iou_handles_equal_disjoint_and_partial_boxes() -> None:
    assert bbox_iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert bbox_iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    assert bbox_iou((0, 0, 10, 10), (5, 0, 15, 10)) == pytest.approx(1 / 3)


def test_spatial_batch_declares_only_verified_pdf_point_boxes() -> None:
    batches = load_spatial_ground_truths()

    assert len(batches) >= 1
    batch = next(item for item in batches if item.path.stem == "bbox-review-batch-01")
    views = [view for sheet in batch.sheets for view in sheet.views]

    assert batch.status == "human_verified"
    assert batch.coordinate_system == "pdf_points"
    assert len(batch.sheets) == 6
    assert len(views) == 17
    assert all(view.bbox_semantics in VALID_BBOX_SEMANTICS for view in views)


def test_current_detector_meets_verified_spatial_iou_when_pdfs_are_present() -> None:
    batches = load_spatial_ground_truths()
    available = 0

    for batch in batches:
        for sheet in batch.sheets:
            pdf_path = LOCAL_APPROVED / sheet.filename
            if not pdf_path.exists():
                continue

            available += 1
            document = fitz.open(pdf_path)
            try:
                page = document.load_page(sheet.page_index)
                extraction = extract_page(page)
                regions = detect_regions(
                    geometry_from_extraction(extraction), extract_line_boxes(page)
                )
                detected = {
                    normalize(view.title.raw or ""): view
                    for view in detect_forms_views(extraction, regions)
                }
            finally:
                document.close()

            for expected in sheet.views:
                actual = detected[normalize(expected.title_raw)]
                assert bbox_iou(actual.bbox, expected.bbox) >= batch.minimum_iou

    if available == 0:
        pytest.skip("PDFs locais do gabarito espacial nao estao presentes")
