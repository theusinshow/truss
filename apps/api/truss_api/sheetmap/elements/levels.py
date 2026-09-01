from collections import defaultdict
from decimal import Decimal, InvalidOperation
import re

from truss_api.core.text import normalize


MIN_VIEW_CONFIDENCE = 0.6
MIN_ELEMENT_CONFIDENCE = 0.6
CROSS_SHEET_MIN_SHARED_CODES = 3
CROSS_SHEET_MIN_OVERLAP = 0.5

LEVEL_VALUE = re.compile(r"^[+-]?\d+(?:[.,]\d+)?$")
LEVEL_DECLARATION = re.compile(
    r"\(?\s*(?:NIVEL|N\.A\.|EL\.)\s*[:=]?\s*[+-]?\d+(?:[.,]\d+)?\s*\)?"
)
FLOOR_TERMS = re.compile(
    r"\b(?:PLANTA|DE|FORMAS?|BAIXA|FUNDACAO|FUNDO|PISCINA|INTERMEDIARIA|"
    r"TERREO|PAVIMENTO|COBERTURA|RESERVATORIO|TOPO|NIVEL)\b"
)


def parse_level_ordinal(raw: str | None) -> dict[str, object] | None:
    """Interpreta somente ordem relativa; nunca converte a unidade da cota."""
    if raw is None:
        return None

    value = raw.strip().replace(" ", "")
    if not LEVEL_VALUE.fullmatch(value):
        return None

    family = "decimal" if "." in value or "," in value else "integer"
    try:
        ordinal = Decimal(value.replace(",", "."))
    except InvalidOperation:
        return None

    return {
        "raw": raw,
        "ordinal": ordinal,
        "notation_family": family,
        "provenance": "numeric-relative-level-v1",
    }


def context_signature(title_raw: str | None) -> str:
    title = normalize(str(title_raw or ""))
    title = LEVEL_DECLARATION.sub(" ", title)
    title = FLOOR_TERMS.sub(" ", title)
    title = re.sub(r"\b\d+(?:O|A)?\b", " ", title)
    title = re.sub(r"[^A-Z0-9]+", " ", title)
    return " ".join(title.split()) or "ESTRUTURA"


def _pair(
    lower: dict[str, object],
    upper: dict[str, object],
    *,
    provenance: str,
    confidence: float,
    shared_codes: set[str],
) -> dict[str, object]:
    return {
        "lower_view_id": lower["view_id"],
        "upper_view_id": upper["view_id"],
        "lower_sheet_id": lower["sheet_id"],
        "upper_sheet_id": upper["sheet_id"],
        "lower_sheet_code": lower.get("sheet_code") or lower.get("sheet_code_raw"),
        "upper_sheet_code": upper.get("sheet_code") or upper.get("sheet_code_raw"),
        "lower_level_raw": lower["level_raw"],
        "upper_level_raw": upper["level_raw"],
        "provenance": provenance,
        "confidence": round(confidence, 4),
        "shared_codes": sorted(shared_codes),
    }


def _compatible_notation(lower: dict[str, object], upper: dict[str, object]) -> bool:
    return lower["notation_family"] == upper["notation_family"]


def build_form_level_registry(registry: dict[str, object]) -> dict[str, object]:
    occurrences_by_view: dict[str, list[dict[str, object]]] = defaultdict(list)
    for occurrence in registry.get("occurrences", []):
        view_id = str(occurrence.get("view_id") or "")
        if (
            view_id
            and occurrence.get("element_kind") == "pillar"
            and occurrence.get("technical_scope") == "formas"
            and float(occurrence.get("confidence") or 0.0) >= MIN_ELEMENT_CONFIDENCE
        ):
            occurrences_by_view[view_id].append(occurrence)

    levels: list[dict[str, object]] = []
    for view in registry.get("views", []):
        parsed = parse_level_ordinal(view.get("level_raw"))
        if (
            parsed is None
            or view.get("view_kind") != "plan"
            or view.get("technical_scope") != "formas"
            or float(view.get("confidence") or 0.0) < MIN_VIEW_CONFIDENCE
        ):
            continue

        view_id = str(view["id"])
        occurrences = occurrences_by_view.get(view_id, [])
        levels.append(
            {
                "view_id": view_id,
                "sheet_map_id": view.get("sheet_map_id"),
                "sheet_id": view.get("sheet_id"),
                "document_id": view.get("document_id"),
                "sheet_code": view.get("sheet_code"),
                "sheet_code_raw": view.get("sheet_code_raw"),
                "page_index": int(view.get("page_index") or 0),
                "title_raw": view.get("title_raw"),
                "level_raw": parsed["raw"],
                "level_ordinal": str(parsed["ordinal"]),
                "notation_family": parsed["notation_family"],
                "level_provenance": parsed["provenance"],
                "context_signature": context_signature(view.get("title_raw")),
                "confidence": float(view.get("confidence") or 0.0),
                "pillar_codes": sorted({str(item["code"]) for item in occurrences}),
                "pillar_occurrences": len(occurrences),
            }
        )

    by_document: dict[str, list[dict[str, object]]] = defaultdict(list)
    for level in levels:
        by_document[str(level.get("document_id") or "")].append(level)

    pairs: list[dict[str, object]] = []
    ambiguities: list[dict[str, object]] = []
    paired_next: set[str] = set()
    paired_previous: set[str] = set()

    for document_id, document_levels in sorted(by_document.items()):
        by_page: dict[int, list[dict[str, object]]] = defaultdict(list)
        for level in document_levels:
            by_page[int(level["page_index"])].append(level)

        ordered_pages = sorted(by_page)
        for page_index in ordered_pages:
            page_levels = by_page[page_index]
            by_ordinal: dict[Decimal, list[dict[str, object]]] = defaultdict(list)
            for level in page_levels:
                by_ordinal[Decimal(str(level["level_ordinal"]))].append(level)

            duplicated = {ordinal for ordinal, items in by_ordinal.items() if len(items) > 1}
            for ordinal in sorted(duplicated):
                ambiguities.append(
                    {
                        "document_id": document_id,
                        "page_index": page_index,
                        "reason": "duplicate_level",
                        "level_raw": [item["level_raw"] for item in by_ordinal[ordinal]],
                        "view_ids": [item["view_id"] for item in by_ordinal[ordinal]],
                    }
                )

            unique = [
                items[0]
                for ordinal, items in sorted(by_ordinal.items())
                if ordinal not in duplicated
            ]
            for lower, upper in zip(unique, unique[1:]):
                if not _compatible_notation(lower, upper):
                    ambiguities.append(
                        {
                            "document_id": document_id,
                            "page_index": page_index,
                            "reason": "incompatible_level_notation",
                            "view_ids": [lower["view_id"], upper["view_id"]],
                        }
                    )
                    continue

                shared = set(lower["pillar_codes"]) & set(upper["pillar_codes"])
                pairs.append(
                    _pair(
                        lower,
                        upper,
                        provenance="same-sheet-level-order-v1",
                        confidence=min(float(lower["confidence"]), float(upper["confidence"])),
                        shared_codes=shared,
                    )
                )
                paired_next.add(str(lower["view_id"]))
                paired_previous.add(str(upper["view_id"]))

        # Entre folhas, apenas as bordas de paginas consecutivas podem se
        # ligar, e somente quando varios pilares independentes sustentam a
        # continuidade. Isso impede ordenar globalmente estruturas distintas.
        for lower_page, upper_page in zip(ordered_pages, ordered_pages[1:]):
            if upper_page != lower_page + 1:
                continue

            lower_candidates = [
                item for item in by_page[lower_page]
                if str(item["view_id"]) not in paired_next
            ]
            upper_candidates = [
                item for item in by_page[upper_page]
                if str(item["view_id"]) not in paired_previous
            ]
            if not lower_candidates or not upper_candidates:
                continue

            max_ordinal = max(Decimal(str(item["level_ordinal"])) for item in lower_candidates)
            min_ordinal = min(Decimal(str(item["level_ordinal"])) for item in upper_candidates)
            lowers = [
                item for item in lower_candidates
                if Decimal(str(item["level_ordinal"])) == max_ordinal
            ]
            uppers = [
                item for item in upper_candidates
                if Decimal(str(item["level_ordinal"])) == min_ordinal
            ]
            if len(lowers) != 1 or len(uppers) != 1:
                continue

            lower, upper = lowers[0], uppers[0]
            if (
                Decimal(str(upper["level_ordinal"])) <= Decimal(str(lower["level_ordinal"]))
                or not _compatible_notation(lower, upper)
                or lower["context_signature"] != upper["context_signature"]
            ):
                continue

            lower_codes = set(lower["pillar_codes"])
            upper_codes = set(upper["pillar_codes"])
            shared = lower_codes & upper_codes
            denominator = min(len(lower_codes), len(upper_codes))
            overlap = len(shared) / denominator if denominator else 0.0
            if (
                len(shared) < CROSS_SHEET_MIN_SHARED_CODES
                or overlap < CROSS_SHEET_MIN_OVERLAP
            ):
                continue

            pairs.append(
                _pair(
                    lower,
                    upper,
                    provenance="adjacent-sheet-code-overlap-v1",
                    confidence=(
                        min(float(lower["confidence"]), float(upper["confidence"]))
                        * overlap
                    ),
                    shared_codes=shared,
                )
            )
            paired_next.add(str(lower["view_id"]))
            paired_previous.add(str(upper["view_id"]))

    return {
        "form_levels": sorted(
            levels,
            key=lambda item: (
                str(item.get("document_id") or ""),
                int(item["page_index"]),
                Decimal(str(item["level_ordinal"])),
                str(item["view_id"]),
            ),
        ),
        "form_level_pairs": sorted(
            pairs,
            key=lambda item: (
                str(item.get("lower_sheet_id") or ""),
                str(item.get("lower_level_raw") or ""),
                str(item.get("lower_view_id") or ""),
            ),
        ),
        "form_level_ambiguities": ambiguities,
    }
