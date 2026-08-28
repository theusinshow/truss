from pathlib import Path

import fitz

from truss_api.core.settings import Settings
from truss_api.sheetmap.geometry import (
    extract_page_geometry,
    read_page_geometry,
    write_page_geometry,
)


def _page_with_rects() -> fitz.Page:
    document = fitz.open()
    page = document.new_page(width=1000, height=800)
    page.draw_rect(fitz.Rect(20, 20, 980, 780))
    page.draw_rect(fitz.Rect(700, 650, 970, 770))
    page.draw_line(fitz.Point(100, 100), fitz.Point(400, 400))
    return page


def test_extract_page_geometry_reads_size_rects_and_line_count() -> None:
    geometry = extract_page_geometry(_page_with_rects())

    assert (geometry.width_pt, geometry.height_pt) == (1000, 800)
    areas = sorted(round(rect.area) for rect in geometry.rects)
    assert 960 * 760 in areas
    assert 270 * 120 in areas
    assert geometry.line_count >= 1


def test_write_and_read_page_geometry_roundtrip(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data")
    geometry = extract_page_geometry(_page_with_rects())

    relative = write_page_geometry(
        geometry,
        project_id="project-1",
        revision_id="revision-1",
        sheet_id="sheet-1",
        settings=settings,
    )
    restored = read_page_geometry(relative, settings)

    assert relative == "geometry/project-1/revision-1/sheet-1.json"
    assert (settings.data_dir / relative).exists()
    assert restored.width_pt == geometry.width_pt
    assert len(restored.rects) == len(geometry.rects)
