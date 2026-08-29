from math import hypot

from truss_api.sheetmap.primitives import PageExtraction
from truss_api.sheetmap.regions import (
    REGION_DRAWING,
    REGION_LEGEND,
    REGION_NOTE_BLOCK,
    REGION_TABLE,
    REGION_TITLE_BLOCK,
    DetectedRegion,
)
from truss_api.sheetmap.views.anchors import (
    find_level_in,
    find_level_near,
    find_scale_anchors,
    find_title_for,
    title_font_floor,
    view_kind_from_title,
)
from truss_api.sheetmap.views.models import (
    BBox,
    DetectedView,
    MeasuredValue,
    ScaleAnchor,
    TitleCandidate,
)
from truss_api.sheetmap.primitives import TextSpanRecord


PROVENANCE = "deterministic/forms-view-v1"

# Margem aplicada ao redor do conteudo atribuido a uma view, em pt.
VIEW_PADDING_PT = 12.0

# Duas ancoras a menos que isso de distancia horizontal contam como mesma coluna,
# entao uma encerra a view da outra.
SAME_COLUMN_TOLERANCE_PT = 400.0


def _excluded_bboxes(regions: list[DetectedRegion]) -> list[BBox]:
    """Carimbo, tabelas, notas e legendas nao sao views e nao podem gerar uma."""
    excluded_kinds = {REGION_TITLE_BLOCK, REGION_TABLE, REGION_NOTE_BLOCK, REGION_LEGEND}
    return [
        (region.x0, region.y0, region.x1, region.y1)
        for region in regions
        if region.region_kind in excluded_kinds
    ]


def _inside_any(bbox: BBox, regions: list[BBox]) -> bool:
    center_x = (bbox[0] + bbox[2]) / 2
    center_y = (bbox[1] + bbox[3]) / 2
    return any(
        region[0] <= center_x <= region[2] and region[1] <= center_y <= region[3]
        for region in regions
    )


def _zone_for(
    point: tuple[float, float],
    regions: list[DetectedRegion],
) -> DetectedRegion | None:
    for region in regions:
        if region.region_kind != REGION_DRAWING:
            continue
        if region.x0 <= point[0] <= region.x1 and region.y0 <= point[1] <= region.y1:
            return region

    return None


def _distance(anchor: ScaleAnchor, title: TitleCandidate) -> float:
    return hypot(title.bbox[0] - anchor.bbox[0], anchor.bbox[1] - title.bbox[3])


def _assign_titles(
    anchors: list[ScaleAnchor],
    spans: list[TextSpanRecord],
) -> list[TitleCandidate | None]:
    """Casa cada ancora com um titulo, um titulo por view.

    Buscar isoladamente deixa duas ancoras vizinhas escolherem o mesmo titulo -
    medido na pagina 8 do projeto-base, onde a ancora do detalhe roubava o
    titulo da planta ao lado. A atribuicao e gulosa pela menor distancia global,
    entao o par mais proximo decide primeiro e os demais reconsultam.
    """
    font_floor = title_font_floor(spans)
    assigned: list[TitleCandidate | None] = [None] * len(anchors)
    pending = set(range(len(anchors)))
    claimed: set[BBox] = set()

    while pending:
        best: tuple[float, int, TitleCandidate] | None = None

        for index in sorted(pending):
            candidate = find_title_for(anchors[index], spans, font_floor, claimed=claimed)
            if candidate is None:
                continue

            distance = _distance(anchors[index], candidate)
            if best is None or distance < best[0]:
                best = (distance, index, candidate)

        if best is None:
            break

        _, index, candidate = best
        assigned[index] = candidate
        claimed.add(candidate.bbox)
        pending.discard(index)

    return assigned


def detect_forms_views(
    extraction: PageExtraction,
    regions: list[DetectedRegion],
) -> list[DetectedView]:
    """Segmenta views usando ancoras de escala, ancoradas na zona de desenho.

    Cada ancora de escala define uma view. O limite vertical de cada view vai do
    seu titulo ate o inicio da proxima view na mesma coluna, ou ate o fim da zona
    de desenho. Deterministico e sem modelo.
    """
    excluded = _excluded_bboxes(regions)
    anchors = [
        anchor
        for anchor in find_scale_anchors(extraction.spans, exclude=None)
        if not _inside_any(anchor.bbox, excluded)
    ]
    if not anchors:
        return []

    titles = _assign_titles(anchors, extraction.spans)
    views: list[DetectedView] = []

    for index, anchor in enumerate(anchors):
        title = titles[index]
        top = (title.bbox[1] if title else anchor.bbox[1]) - VIEW_PADDING_PT
        left = min(anchor.bbox[0], title.bbox[0] if title else anchor.bbox[0]) - VIEW_PADDING_PT

        zone = _zone_for((anchor.bbox[0], anchor.bbox[1]), regions)
        right = (zone.x1 if zone else extraction.metadata.width_pt) - VIEW_PADDING_PT
        bottom_limit = zone.y1 if zone else extraction.metadata.height_pt

        # A proxima ancora na mesma coluna encerra esta view.
        following = [
            other
            for other in anchors[index + 1 :]
            if abs(other.bbox[0] - anchor.bbox[0]) < SAME_COLUMN_TOLERANCE_PT
        ]
        if following:
            following_title = titles[anchors.index(following[0])]
            bottom_limit = min(
                bottom_limit,
                (following_title.bbox[1] if following_title else following[0].bbox[1])
                - VIEW_PADDING_PT,
            )

        bbox: BBox = (
            max(0.0, left),
            max(0.0, top),
            right,
            max(top + VIEW_PADDING_PT, bottom_limit),
        )

        views.append(
            DetectedView(
                view_kind=view_kind_from_title(title.title if title else None),
                identifier=title.identifier if title else None,
                title=MeasuredValue(raw=title.raw if title else None),
                # O texto bruto da declaracao fica ao lado do valor: "ESCALA
                # REPRESENTATIVA" e uma declaracao valida sem escala numerica.
                declared_scale=MeasuredValue(raw=anchor.text, normalized=anchor.scale),
                # O titulo tem precedencia: a bbox alcanca views vizinhas e a
                # varredura espacial devolvia o nivel do vizinho. Nunca
                # normalizado aqui - normalizar exige tabela confirmada.
                level=MeasuredValue(
                    raw=find_level_in(title.raw if title else None)
                    or find_level_near(bbox, extraction.spans)
                ),
                bbox=bbox,
                confidence=0.85 if title else 0.5,
                provenance=PROVENANCE,
            )
        )

    return views
