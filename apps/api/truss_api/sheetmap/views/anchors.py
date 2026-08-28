import re
import statistics

from truss_api.core.text import normalize
from truss_api.sheetmap.primitives import TextSpanRecord
from truss_api.sheetmap.views.models import (
    VIEW_KIND_DETAIL,
    VIEW_KIND_PERSPECTIVE,
    VIEW_KIND_PLAN,
    VIEW_KIND_SECTION,
    BBox,
    ScaleAnchor,
    TitleCandidate,
)


NUMERIC_SCALE_PATTERN = re.compile(r"ESCALA\s*:?\s*(\d+)\s*[:/]\s*(\d+)")

# Declaracoes de escala nao numericas aceitas pela politica humana confirmada:
# "ESCALA INDICADA" vale quando as subviews tem escalas diferentes, e
# "ESCALA REPRESENTATIVA" vale em perspectivas e representacoes auxiliares.
NON_NUMERIC_SCALE_PATTERN = re.compile(r"ESCALA\s+(INDICADA|REPRESENTATIVA|GRAFICA)")

IDENTIFIER_PATTERN = re.compile(r"^(\d{1,2})\s+(.{3,})$")
LEVEL_PATTERN = re.compile(r"(?:NIVEL|N\.A\.|EL\.)\s*[:=]?\s*([-+]?\d+[.,]?\d*)")

# Tolerancias verticais em pt, calibradas contra o material real. O titulo pode
# transbordar alguns pontos para dentro da linha da escala.
TITLE_OVERLAP_TOLERANCE_PT = 12.0
TITLE_MAX_GAP_PT = 90.0
TITLE_MAX_HORIZONTAL_OFFSET_PT = 700.0

SECTION_TERMS = ("CORTE", "SECAO")
DETAIL_TERMS = ("DETALHE", "DETALHAMENTO", "DET.", "AMPLIACAO")
PERSPECTIVE_TERMS = ("PERSPECTIVA", "VISTA 3D", "ISOMETRIC")


def _inside(bbox: BBox, region: BBox) -> bool:
    center_x = (bbox[0] + bbox[2]) / 2
    center_y = (bbox[1] + bbox[3]) / 2
    return region[0] <= center_x <= region[2] and region[1] <= center_y <= region[3]


def find_scale_anchors(
    spans: list[TextSpanRecord],
    exclude: BBox | None = None,
) -> list[ScaleAnchor]:
    anchors: list[ScaleAnchor] = []

    for span in spans:
        text = normalize(span.text)
        numeric = NUMERIC_SCALE_PATTERN.search(text)
        non_numeric = NON_NUMERIC_SCALE_PATTERN.search(text)

        if numeric is None and non_numeric is None:
            continue

        if exclude is not None and _inside(span.bbox, exclude):
            continue

        anchors.append(
            ScaleAnchor(
                text=text,
                scale=f"{numeric.group(1)}:{numeric.group(2)}" if numeric else None,
                bbox=span.bbox,
                size=span.size,
                is_numeric=numeric is not None,
            )
        )

    return sorted(anchors, key=lambda anchor: (anchor.bbox[1], anchor.bbox[0]))


def title_font_floor(spans: list[TextSpanRecord]) -> float:
    """Piso de fonte que separa titulo de texto de cota.

    Medido no material real: titulos por volta de 15,8 pt e cotas entre 5,9 e
    8,4 pt. A media entre mediana e maximo tolera folhas com poucos titulos.
    """
    sizes = [span.size for span in spans if span.size > 0]
    if not sizes:
        return 0.0

    return (statistics.median(sizes) + max(sizes)) / 2


def find_title_for(
    anchor: ScaleAnchor,
    spans: list[TextSpanRecord],
    font_floor: float,
) -> TitleCandidate | None:
    candidates: list[TextSpanRecord] = []

    for span in spans:
        if span.size < font_floor:
            continue

        gap = anchor.bbox[1] - span.bbox[3]
        if gap < -TITLE_OVERLAP_TOLERANCE_PT or gap > TITLE_MAX_GAP_PT:
            continue

        if abs(span.bbox[0] - anchor.bbox[0]) > TITLE_MAX_HORIZONTAL_OFFSET_PT:
            continue

        if NUMERIC_SCALE_PATTERN.search(normalize(span.text)):
            continue

        candidates.append(span)

    if not candidates:
        return None

    closest = min(candidates, key=lambda span: abs(anchor.bbox[1] - span.bbox[3]))
    text = normalize(closest.text)
    match = IDENTIFIER_PATTERN.match(text)

    return TitleCandidate(
        identifier=match.group(1) if match else None,
        title=match.group(2) if match else text,
        bbox=closest.bbox,
        size=closest.size,
    )


def find_level_near(bbox: BBox, spans: list[TextSpanRecord]) -> str | None:
    """Nivel declarado dentro da regiao da view.

    Devolve o texto bruto. Normalizar exige confirmacao humana: "-650" nao vira
    "-6.50 m" sem tabela aprovada.
    """
    for span in spans:
        if not _inside(span.bbox, bbox):
            continue

        match = LEVEL_PATTERN.search(normalize(span.text))
        if match:
            return match.group(1)

    return None


def view_kind_from_title(title: str | None) -> str:
    if title is None:
        return VIEW_KIND_PLAN

    normalized = normalize(title)
    if any(term in normalized for term in PERSPECTIVE_TERMS):
        return VIEW_KIND_PERSPECTIVE
    if any(term in normalized for term in SECTION_TERMS):
        return VIEW_KIND_SECTION
    if any(term in normalized for term in DETAIL_TERMS):
        return VIEW_KIND_DETAIL

    return VIEW_KIND_PLAN
