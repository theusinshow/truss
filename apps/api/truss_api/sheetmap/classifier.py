from dataclasses import dataclass

from truss_api.core.text import normalize
from truss_api.sheetmap.title_block import TitleBlockFields


SHEET_TYPE_UNKNOWN = "desconhecido"

CATEGORY_TO_SHEET_TYPE: dict[str, str] = {
    "PLANTA DE LOCACAO": "planta_locacao",
    "PLANTA DE FORMAS": "planta_formas",
    "PLANTA DE ARMADURAS": "planta_armaduras",
    "PLANTA DE COBERTURA": "planta_cobertura",
    "PLANTA DE FUNDACOES": "planta_fundacoes",
}


@dataclass(frozen=True)
class SheetTypeResult:
    sheet_type: str
    confidence: float
    source: str


def classify_sheet_type(fields: TitleBlockFields, sheet_text: str) -> SheetTypeResult:
    if fields.category and fields.category in CATEGORY_TO_SHEET_TYPE:
        return SheetTypeResult(
            sheet_type=CATEGORY_TO_SHEET_TYPE[fields.category],
            confidence=0.97,
            source="carimbo",
        )

    normalized_text = normalize(sheet_text)
    for category, sheet_type in CATEGORY_TO_SHEET_TYPE.items():
        if category in normalized_text:
            return SheetTypeResult(
                sheet_type=sheet_type,
                confidence=0.6,
                source="texto",
            )

    return SheetTypeResult(
        sheet_type=SHEET_TYPE_UNKNOWN,
        confidence=0.2,
        source="nenhum",
    )
