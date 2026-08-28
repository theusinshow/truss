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
    lines = [
        normalize(box.text)
        for box in boxes_inside(region, text_boxes)
        if normalize(box.text)
    ]

    sheet_code: str | None = None
    revision_code: str | None = None
    for line in lines:
        match = SHEET_CODE_PATTERN.search(line)
        if match:
            sheet_code = match.group(0)
            revision_code = sheet_code.rsplit("-", 1)[-1]
            break

    category = next((line for line in lines if line in SHEET_CATEGORIES), None)

    candidates = [line for line in lines if line != category and not _is_noise(line)]
    title = max(candidates, key=len) if candidates else None

    return TitleBlockFields(
        sheet_code=sheet_code,
        revision_code=revision_code,
        category=category,
        title=title,
    )
