from dataclasses import dataclass
import re

import fitz

from truss_api.core.text import normalize
from truss_api.sheetmap.geometry import PageGeometry


REGION_FRAME = "moldura"
REGION_TITLE_BLOCK = "carimbo"
REGION_DRAWING = "area_desenho"

FRAME_MIN_AREA_RATIO = 0.70
FRAME_MAX_AREA_RATIO = 0.995

TITLE_BLOCK_MIN_X_RATIO = 0.50
TITLE_BLOCK_MIN_Y_RATIO = 0.70

SHEET_CODE_PATTERN = re.compile(r"\b[A-Z]{2,5}-\d{3,5}-[A-Z0-9]{1,3}\b")
TITLE_BLOCK_ANCHORS = ("CPF", "REVISAO", "EMISSAO", "PROJETO ESTRUTURAL")


@dataclass(frozen=True)
class TextBox:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(frozen=True)
class DetectedRegion:
    region_kind: str
    x0: float
    y0: float
    x1: float
    y1: float
    confidence: float


def extract_line_boxes(page: fitz.Page) -> list[TextBox]:
    """Texto em granularidade de linha.

    Deliberadamente NAO usa page.get_text("blocks"): esse modo funde linhas
    vizinhas num unico bloco, o que colapsa o carimbo inteiro numa string so e
    torna impossivel casar a categoria por igualdade exata.
    """
    boxes: list[TextBox] = []

    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(span["text"] for span in line["spans"]).strip()
            if not text:
                continue

            x0, y0, x1, y1 = line["bbox"]
            boxes.append(
                TextBox(text=text, x0=float(x0), y0=float(y0), x1=float(x1), y1=float(y1))
            )

    return boxes


def is_title_block_anchor(text: str) -> bool:
    normalized = normalize(text)
    if SHEET_CODE_PATTERN.search(normalized):
        return True
    return any(anchor in normalized for anchor in TITLE_BLOCK_ANCHORS)


def detect_frame(geometry: PageGeometry) -> DetectedRegion:
    page_area = geometry.page_area
    candidates = [
        rect
        for rect in geometry.rects
        if FRAME_MIN_AREA_RATIO <= rect.area / page_area < FRAME_MAX_AREA_RATIO
    ]

    if not candidates:
        return DetectedRegion(
            region_kind=REGION_FRAME,
            x0=0.0,
            y0=0.0,
            x1=geometry.width_pt,
            y1=geometry.height_pt,
            confidence=0.3,
        )

    best = max(candidates, key=lambda rect: rect.area)
    return DetectedRegion(
        region_kind=REGION_FRAME,
        x0=best.x0,
        y0=best.y0,
        x1=best.x1,
        y1=best.y1,
        confidence=0.95,
    )


def detect_title_block(
    text_boxes: list[TextBox],
    geometry: PageGeometry,
    frame: DetectedRegion,
) -> DetectedRegion | None:
    minimum_x = geometry.width_pt * TITLE_BLOCK_MIN_X_RATIO
    minimum_y = geometry.height_pt * TITLE_BLOCK_MIN_Y_RATIO

    anchors = [
        box
        for box in text_boxes
        if is_title_block_anchor(box.text)
        and (box.x0 + box.x1) / 2 >= minimum_x
        and (box.y0 + box.y1) / 2 >= minimum_y
    ]

    if not anchors:
        return None

    # As ancoras dao apenas o canto superior-esquerdo confiavel. O carimbo ocupa o
    # canto da moldura, entao a regiao e estendida ate a borda - sem isso, campos
    # abaixo da ultima ancora (a categoria, por exemplo) ficam de fora.
    return DetectedRegion(
        region_kind=REGION_TITLE_BLOCK,
        x0=min(box.x0 for box in anchors),
        y0=min(box.y0 for box in anchors),
        x1=frame.x1,
        y1=frame.y1,
        confidence=0.9 if len(anchors) >= 2 else 0.6,
    )


def detect_regions(
    geometry: PageGeometry,
    text_boxes: list[TextBox],
) -> list[DetectedRegion]:
    frame = detect_frame(geometry)
    regions = [frame]

    title_block = detect_title_block(text_boxes, geometry, frame)
    if title_block is not None:
        regions.append(title_block)

    drawing_bottom = title_block.y0 if title_block is not None else frame.y1
    regions.append(
        DetectedRegion(
            region_kind=REGION_DRAWING,
            x0=frame.x0,
            y0=frame.y0,
            x1=frame.x1,
            y1=drawing_bottom,
            confidence=frame.confidence,
        )
    )

    return regions
