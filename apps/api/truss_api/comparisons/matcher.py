from collections import defaultdict
from typing import Any


SheetRow = dict[str, Any]
PairCandidate = dict[str, Any]


def _unique_index(sheets: list[SheetRow], key_name: str) -> dict[object, SheetRow]:
    grouped: dict[object, list[SheetRow]] = defaultdict(list)
    for sheet in sheets:
        value = sheet.get(key_name)
        if value not in (None, ""):
            grouped[value].append(sheet)
    return {key: values[0] for key, values in grouped.items() if len(values) == 1}


def match_sheets(
    base_sheets: list[SheetRow],
    target_sheets: list[SheetRow],
    overrides: list[dict[str, Any]],
) -> list[PairCandidate]:
    """Pair sheets only when identity has explicit, auditable evidence."""
    base_by_id = {str(sheet["id"]): sheet for sheet in base_sheets}
    target_by_id = {str(sheet["id"]): sheet for sheet in target_sheets}
    used_base: set[str] = set()
    used_target: set[str] = set()
    pairs: list[PairCandidate] = []

    for override in overrides:
        base_id = str(override["base_sheet_id"])
        target_id = str(override["target_sheet_id"])
        if base_id not in base_by_id or target_id not in target_by_id:
            continue
        used_base.add(base_id)
        used_target.add(target_id)
        pairs.append(
            {
                "base": base_by_id[base_id],
                "target": target_by_id[target_id],
                "match_method": "manual",
                "match_confidence": 1.0,
                "pairing_override_id": str(override["id"]),
            }
        )

    remaining_base = [sheet for sheet in base_sheets if str(sheet["id"]) not in used_base]
    remaining_target = [sheet for sheet in target_sheets if str(sheet["id"]) not in used_target]
    base_codes = _unique_index(remaining_base, "sheet_code")
    target_codes = _unique_index(remaining_target, "sheet_code")
    for code in sorted(set(base_codes) & set(target_codes), key=str):
        base = base_codes[code]
        target = target_codes[code]
        base_id = str(base["id"])
        target_id = str(target["id"])
        used_base.add(base_id)
        used_target.add(target_id)
        pairs.append(
            {
                "base": base,
                "target": target,
                "match_method": "sheet_code",
                "match_confidence": 1.0,
                "pairing_override_id": None,
            }
        )

    remaining_base = [sheet for sheet in base_sheets if str(sheet["id"]) not in used_base]
    remaining_target = [sheet for sheet in target_sheets if str(sheet["id"]) not in used_target]
    base_content: dict[tuple[str, int], list[SheetRow]] = defaultdict(list)
    target_content: dict[tuple[str, int], list[SheetRow]] = defaultdict(list)
    for sheet in remaining_base:
        base_content[(str(sheet["document_hash"]), int(sheet["page_index"]))].append(sheet)
    for sheet in remaining_target:
        target_content[(str(sheet["document_hash"]), int(sheet["page_index"]))].append(sheet)
    for key in sorted(set(base_content) & set(target_content)):
        if len(base_content[key]) != 1 or len(target_content[key]) != 1:
            continue
        base = base_content[key][0]
        target = target_content[key][0]
        base_id = str(base["id"])
        target_id = str(target["id"])
        used_base.add(base_id)
        used_target.add(target_id)
        pairs.append(
            {
                "base": base,
                "target": target,
                "match_method": "exact_content",
                "match_confidence": 1.0,
                "pairing_override_id": None,
            }
        )

    remaining_base_codes = {
        sheet.get("sheet_code") for sheet in base_sheets if str(sheet["id"]) not in used_base
    }
    remaining_target_codes = {
        sheet.get("sheet_code") for sheet in target_sheets if str(sheet["id"]) not in used_target
    }
    ambiguous_codes = (remaining_base_codes & remaining_target_codes) - {None, ""}

    for sheet in base_sheets:
        if str(sheet["id"]) in used_base:
            continue
        pairs.append(
            {
                "base": sheet,
                "target": None,
                "match_method": "unmatched",
                "match_confidence": 0.0,
                "pairing_override_id": None,
                "unmatched_status": (
                    "removed"
                    if sheet.get("sheet_code") and sheet.get("sheet_code") not in ambiguous_codes
                    else "ambiguous"
                ),
            }
        )
    for sheet in target_sheets:
        if str(sheet["id"]) in used_target:
            continue
        pairs.append(
            {
                "base": None,
                "target": sheet,
                "match_method": "unmatched",
                "match_confidence": 0.0,
                "pairing_override_id": None,
                "unmatched_status": (
                    "added"
                    if sheet.get("sheet_code") and sheet.get("sheet_code") not in ambiguous_codes
                    else "ambiguous"
                ),
            }
        )

    pairs.sort(
        key=lambda pair: (
            int((pair.get("base") or pair.get("target"))["sheet_number"]),
            0 if pair.get("base") else 1,
            str((pair.get("base") or pair.get("target"))["id"]),
        )
    )
    return pairs
