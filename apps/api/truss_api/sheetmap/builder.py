from dataclasses import asdict

import fitz

from truss_api.core.settings import Settings
from truss_api.db.connection import transaction
from truss_api.sheetmap import repository
from truss_api.sheetmap.classifier import classify_sheet_type
from truss_api.sheetmap.geometry import extract_page_geometry, write_page_geometry
from truss_api.sheetmap.regions import (
    REGION_TITLE_BLOCK,
    detect_regions,
    extract_line_boxes,
)
from truss_api.sheetmap.title_block import TitleBlockFields, parse_title_block


PAPER_FORMATS: tuple[tuple[str, float, float], ...] = (
    ("A0", 3370.0, 2384.0),
    ("A1", 2384.0, 1684.0),
    ("A2", 1684.0, 1191.0),
    ("A3", 1191.0, 842.0),
    ("A4", 842.0, 595.0),
)

FORMAT_TOLERANCE_PT = 20.0


class DocumentNotFoundError(Exception):
    pass


def paper_format_for(width_pt: float, height_pt: float) -> str:
    longer = max(width_pt, height_pt)
    shorter = min(width_pt, height_pt)

    for name, format_long, format_short in PAPER_FORMATS:
        if (
            abs(longer - format_long) <= FORMAT_TOLERANCE_PT
            and abs(shorter - format_short) <= FORMAT_TOLERANCE_PT
        ):
            return name

    return "personalizado"


def orientation_for(width_pt: float, height_pt: float) -> str:
    return "paisagem" if width_pt >= height_pt else "retrato"


def _load_document_context(
    document_id: str,
    settings: Settings,
) -> tuple[str, list[dict[str, object]]]:
    with transaction(settings) as connection:
        document = connection.execute(
            "SELECT stored_file_path FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()

        if document is None:
            raise DocumentNotFoundError(document_id)

        sheets = connection.execute(
            """
            SELECT id, project_id, revision_id, page_index
            FROM sheets WHERE document_id = ? ORDER BY page_index
            """,
            (document_id,),
        ).fetchall()

    return str(document["stored_file_path"]), [dict(row) for row in sheets]


def build_sheet_map_for_document(
    document_id: str,
    settings: Settings,
) -> list[dict[str, object]]:
    stored_path, sheets = _load_document_context(document_id, settings)
    pdf_path = settings.data_dir / stored_path
    built: list[dict[str, object]] = []

    pdf = fitz.open(pdf_path)
    try:
        for sheet in sheets:
            page = pdf.load_page(int(sheet["page_index"]))
            geometry = extract_page_geometry(page)
            text_boxes = extract_line_boxes(page)
            regions = detect_regions(geometry, text_boxes)

            title_block_region = next(
                (r for r in regions if r.region_kind == REGION_TITLE_BLOCK), None
            )
            if title_block_region is None:
                fields = TitleBlockFields(None, None, None, None)
            else:
                fields = parse_title_block(title_block_region, text_boxes)

            sheet_text = " ".join(box.text for box in text_boxes)
            classification = classify_sheet_type(fields, sheet_text)

            geometry_path = write_page_geometry(
                geometry,
                project_id=str(sheet["project_id"]),
                revision_id=str(sheet["revision_id"]),
                sheet_id=str(sheet["id"]),
                settings=settings,
            )

            title_block_payload = dict(asdict(fields))
            title_block_payload["classification_source"] = classification.source
            title_block_payload["classification_confidence"] = classification.confidence

            built.append(
                repository.save_sheet_map(
                    sheet_id=str(sheet["id"]),
                    project_id=str(sheet["project_id"]),
                    revision_id=str(sheet["revision_id"]),
                    geometry_path=geometry_path,
                    sheet_code=fields.sheet_code,
                    sheet_type=classification.sheet_type,
                    paper_format=paper_format_for(geometry.width_pt, geometry.height_pt),
                    orientation=orientation_for(geometry.width_pt, geometry.height_pt),
                    title_block=title_block_payload,
                    regions=regions,
                    settings=settings,
                )
            )
    finally:
        pdf.close()

    return built
