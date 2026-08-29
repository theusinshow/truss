from dataclasses import dataclass
import re

import fitz

from truss_api.core.text import normalize
from truss_api.sheetmap.geometry import PageGeometry


REGION_FRAME = "moldura"
REGION_TITLE_BLOCK = "carimbo"
REGION_DRAWING = "area_desenho"
# Regioes de conteudo previstas pela F2. Ainda sem detector: as tabelas do
# material real sao desenhadas como segmentos de linha, nao como retangulos de
# celula, entao nao ha o que agrupar. Ver docs/DECISIONS.md.
REGION_TABLE = "table"
REGION_NOTE_BLOCK = "note_block"
REGION_LEGEND = "legend"

# Uma faixa mais estreita que isso nao comporta uma view; sobra de subtracao.
MIN_ZONE_SIDE_PT = 60.0

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
    parent_kind: str | None = None


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


def drawing_zones(
    frame: DetectedRegion,
    occupied: list[DetectedRegion],
) -> list[DetectedRegion]:
    """Zona de desenho como faixas disjuntas: moldura menos regioes ocupadas.

    Corta em faixas horizontais definidas pelas bordas verticais das regioes
    ocupadas, e dentro de cada faixa remove os intervalos horizontais cobertos.
    Evita a truncagem anterior, que descartava tudo abaixo do topo do carimbo -
    inclusive a faixa lateral onde ficam views reais.
    """
    if not occupied:
        return [
            DetectedRegion(
                REGION_DRAWING,
                frame.x0,
                frame.y0,
                frame.x1,
                frame.y1,
                frame.confidence,
                parent_kind=REGION_FRAME,
            )
        ]

    edges = sorted(
        {frame.y0, frame.y1}
        | {edge for region in occupied for edge in (region.y0, region.y1)}
    )
    zones: list[DetectedRegion] = []

    for top, bottom in zip(edges, edges[1:]):
        if bottom - top < MIN_ZONE_SIDE_PT:
            continue

        blockers = sorted(
            (region for region in occupied if region.y0 < bottom and region.y1 > top),
            key=lambda region: region.x0,
        )

        cursor = frame.x0
        for blocker in blockers:
            if blocker.x0 - cursor >= MIN_ZONE_SIDE_PT:
                zones.append(
                    DetectedRegion(
                        REGION_DRAWING,
                        cursor,
                        top,
                        blocker.x0,
                        bottom,
                        frame.confidence,
                        parent_kind=REGION_FRAME,
                    )
                )
            cursor = max(cursor, blocker.x1)

        if frame.x1 - cursor >= MIN_ZONE_SIDE_PT:
            zones.append(
                DetectedRegion(
                    REGION_DRAWING,
                    cursor,
                    top,
                    frame.x1,
                    bottom,
                    frame.confidence,
                    parent_kind=REGION_FRAME,
                )
            )

    return zones


def detect_regions(
    geometry: PageGeometry,
    text_boxes: list[TextBox],
) -> list[DetectedRegion]:
    frame = detect_frame(geometry)
    regions = [frame]

    title_block = detect_title_block(text_boxes, geometry, frame)
    if title_block is not None:
        regions.append(title_block)

    occupied = [region for region in regions if region.region_kind != REGION_FRAME]
    regions.extend(drawing_zones(frame, occupied))

    return regions
