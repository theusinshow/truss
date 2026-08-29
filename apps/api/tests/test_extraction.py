from pathlib import Path

import fitz

from truss_api.core.settings import Settings
from truss_api.sheetmap.artifacts import (
    artifact_hash,
    read_extraction,
    write_extraction,
)
from truss_api.sheetmap.primitives import extract_page


def _page(rotation: int = 0) -> fitz.Page:
    document = fitz.open()
    page = document.new_page(width=1000, height=800)
    page.draw_rect(fitz.Rect(20, 10, 970, 770), color=(0, 0, 0), width=2)
    page.draw_line(fitz.Point(100, 100), fitz.Point(400, 400))
    page.insert_text((120, 200), "PLANTA DE FORMAS", fontsize=16)
    page.insert_text((120, 240), "ESCALA 1:50", fontsize=6)
    if rotation:
        page.set_rotation(rotation)
    return page


def test_extraction_keeps_line_primitives_not_just_bounding_boxes() -> None:
    extraction = extract_page(_page())

    line_primitives = [p for p in extraction.primitives if p.kind == "l"]
    assert line_primitives, "linhas devem ser preservadas, nao apenas bboxes"
    assert all(len(p.points) >= 2 for p in line_primitives)


def test_extraction_keeps_span_font_size_used_to_tell_title_from_dimension() -> None:
    extraction = extract_page(_page())

    sizes = {round(span.size) for span in extraction.spans}
    assert 16 in sizes
    assert 6 in sizes


def test_extraction_records_page_coordinate_system() -> None:
    metadata = extract_page(_page()).metadata

    assert metadata.rotation == 0
    assert metadata.mediabox == (0.0, 0.0, 1000.0, 800.0)
    assert metadata.cropbox == metadata.mediabox


def test_extraction_records_rotation_when_page_is_rotated() -> None:
    """O material real tem rotation=0 em todas as paginas; so fixture sintetica cobre isso."""
    metadata = extract_page(_page(rotation=90)).metadata

    assert metadata.rotation == 90
    assert metadata.width_pt == 800.0
    assert metadata.height_pt == 1000.0


def test_artifact_hash_is_stable_and_content_addressed() -> None:
    first = extract_page(_page())
    second = extract_page(_page())

    assert artifact_hash(first) == artifact_hash(second)
    assert len(artifact_hash(first)) == 16


def test_write_and_read_roundtrip_uses_gzip(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data")
    extraction = extract_page(_page())

    relative = write_extraction(
        extraction,
        project_id="p",
        revision_id="r",
        sheet_id="s",
        settings=settings,
    )
    restored = read_extraction(relative, settings)

    assert relative.endswith(".json.gz")
    assert (settings.data_dir / relative).exists()
    assert len(restored.primitives) == len(extraction.primitives)
    assert len(restored.spans) == len(extraction.spans)
    assert restored.metadata == extraction.metadata
