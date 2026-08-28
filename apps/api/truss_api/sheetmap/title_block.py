from dataclasses import dataclass

from truss_api.core.text import normalize
from truss_api.sheetmap.regions import SHEET_CODE_PATTERN, DetectedRegion, TextBox


SHEET_CATEGORIES: tuple[str, ...] = (
    "PLANTA DE LOCACAO",
    "PLANTA DE FORMAS",
    "PLANTA DE ARMADURAS",
    "PLANTA DE COBERTURA",
    "PLANTA DE FUNDACOES",
)

CONSTANT_LINES: tuple[str, ...] = (
    "PROJETO ESTRUTURAL",
    "REVISAO",
    "DATA",
    "EMISSAO INICIAL",
)


@dataclass(frozen=True)
class TitleBlockFields:
    sheet_code: str | None
    revision_code: str | None
    category: str | None
    title: str | None


def boxes_inside(region: DetectedRegion, text_boxes: list[TextBox]) -> list[TextBox]:
    return [
        box
        for box in text_boxes
        if box.x0 >= region.x0
        and box.y0 >= region.y0
        and box.x1 <= region.x1
        and box.y1 <= region.y1
    ]


def _is_noise(line: str) -> bool:
    if len(line) < 8:
        return True
    if any(constant in line for constant in CONSTANT_LINES):
        return True
    if SHEET_CODE_PATTERN.search(line):
        return True
    return "CPF" in line


def parse_title_block(
    region: DetectedRegion,
    text_boxes: list[TextBox],
) -> TitleBlockFields:
    inside = [box for box in boxes_inside(region, text_boxes) if normalize(box.text)]
    lines = [normalize(box.text) for box in inside]

    sheet_code: str | None = None
    revision_code: str | None = None
    for line in lines:
        match = SHEET_CODE_PATTERN.search(line)
        if match:
            sheet_code = match.group(0)
            revision_code = sheet_code.rsplit("-", 1)[-1]
            break

    category_box = next(
        (box for box in inside if normalize(box.text) in SHEET_CATEGORIES), None
    )
    category = normalize(category_box.text) if category_box else None

    # O titulo e a linha mais proxima da categoria no carimbo. Escolher o candidato
    # mais longo nao funciona: o nome da obra costuma ser maior que o titulo.
    candidates = [
        box
        for box in inside
        if box is not category_box and not _is_noise(normalize(box.text))
    ]

    if not candidates:
        title = None
    elif category_box is None:
        title = normalize(max(candidates, key=lambda box: len(box.text)).text)
    else:
        category_center = (category_box.y0 + category_box.y1) / 2
        nearest = min(
            candidates,
            key=lambda box: abs((box.y0 + box.y1) / 2 - category_center),
        )
        title = normalize(nearest.text)

    return TitleBlockFields(
        sheet_code=sheet_code,
        revision_code=revision_code,
        category=category,
        title=title,
    )
