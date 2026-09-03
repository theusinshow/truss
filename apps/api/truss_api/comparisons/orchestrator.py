from hashlib import sha256
import json
from typing import Any

from truss_api.comparisons import repository
from truss_api.comparisons.diff import RasterReadError, compare_rasters, full_page_region
from truss_api.comparisons.matcher import match_sheets
from truss_api.core.settings import Settings


COMPARISON_PIPELINE_VERSION = "revision-comparison-v0.1"
PAIR_STATUSES = ("identical", "changed", "added", "removed", "ambiguous", "unavailable")


def _sheet_fingerprint(sheet: dict[str, Any]) -> dict[str, object]:
    return {
        "id": str(sheet["id"]),
        "document_hash": str(sheet["document_hash"]),
        "page_index": int(sheet["page_index"]),
        "width_pt": float(sheet["width_pt"]),
        "height_pt": float(sheet["height_pt"]),
        "rotation": int(sheet["rotation"]),
        "source_status": str(sheet["source_status"]),
        "source_exists": bool(sheet["source_exists"]),
        "sheet_map_id": sheet.get("sheet_map_id"),
        "snapshot_hash": sheet.get("snapshot_hash"),
        "sheet_code": sheet.get("sheet_code"),
    }


def _fingerprint(
    project_id: str,
    base_revision_id: str,
    target_revision_id: str,
    base_sheets: list[dict[str, Any]],
    target_sheets: list[dict[str, Any]],
    overrides: list[dict[str, Any]],
) -> str:
    payload = {
        "pipeline_version": COMPARISON_PIPELINE_VERSION,
        "project_id": project_id,
        "base_revision_id": base_revision_id,
        "target_revision_id": target_revision_id,
        "base_sheets": [_sheet_fingerprint(sheet) for sheet in base_sheets],
        "target_sheets": [_sheet_fingerprint(sheet) for sheet in target_sheets],
        "pairings": [
            {
                "id": str(item["id"]),
                "base_sheet_id": str(item["base_sheet_id"]),
                "target_sheet_id": str(item["target_sheet_id"]),
            }
            for item in overrides
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def _public_sheet(sheet: dict[str, Any] | None) -> dict[str, object] | None:
    if sheet is None:
        return None
    return {
        "id": str(sheet["id"]),
        "document_id": str(sheet["document_id"]),
        "revision_id": str(sheet["revision_id"]),
        "sheet_number": int(sheet["sheet_number"]),
        "page_index": int(sheet["page_index"]),
        "label": str(sheet["label"]),
        "sheet_code": sheet.get("sheet_code"),
        "sheet_code_raw": sheet.get("sheet_code_raw"),
        "width_pt": float(sheet["width_pt"]),
        "height_pt": float(sheet["height_pt"]),
        "rotation": int(sheet["rotation"]),
        "source_status": str(sheet["source_status"]),
    }


def _same_geometry(base: dict[str, Any], target: dict[str, Any]) -> bool:
    return (
        abs(float(base["width_pt"]) - float(target["width_pt"])) < 0.01
        and abs(float(base["height_pt"]) - float(target["height_pt"])) < 0.01
        and int(base["rotation"]) == int(target["rotation"])
    )


def _source_available(sheet: dict[str, Any]) -> bool:
    return str(sheet["source_status"]) != "SOURCE_UNAVAILABLE" and bool(
        sheet["source_exists"]
    )


def _evaluate_pair(candidate: dict[str, Any], settings: Settings) -> dict[str, Any]:
    base = candidate.get("base")
    target = candidate.get("target")
    result = {
        "base_sheet_id": str(base["id"]) if base is not None else None,
        "target_sheet_id": str(target["id"]) if target is not None else None,
        "match_method": candidate["match_method"],
        "match_confidence": candidate["match_confidence"],
        "pairing_override_id": candidate.get("pairing_override_id"),
        "base_identity": _public_sheet(base),
        "target_identity": _public_sheet(target),
        "changed_ratio": 0.0,
        "regions": [],
    }
    if base is None or target is None:
        status = str(candidate["unmatched_status"])
        identity = base or target
        code = identity.get("sheet_code") if identity is not None else None
        if status == "added":
            summary = f"Folha {code} existe somente na revisao-alvo."
        elif status == "removed":
            summary = f"Folha {code} existe somente na revisao-base."
        else:
            summary = "Identidade da folha inconclusiva; escolha o par manualmente."
        return {**result, "status": status, "summary": summary}

    if not _source_available(base) or not _source_available(target):
        return {
            **result,
            "status": "unavailable",
            "summary": "A fonte PDF de um dos lados nao esta disponivel para comparacao grafica.",
        }

    if not _same_geometry(base, target):
        return {
            **result,
            "status": "changed",
            "summary": "Formato ou rotacao da pagina mudou; o registro pixel a pixel foi omitido.",
            "changed_ratio": 1.0,
            "regions": [full_page_region(base, target)],
        }

    if (
        str(base["document_hash"]) == str(target["document_hash"])
        and int(base["page_index"]) == int(target["page_index"])
    ):
        return {
            **result,
            "status": "identical",
            "summary": "Conteudo PDF identico pelos hashes e indice da pagina.",
        }

    try:
        diff = compare_rasters(base, target, settings.data_dir)
    except RasterReadError:
        return {
            **result,
            "status": "unavailable",
            "summary": "A rasterizacao local de um dos lados falhou; nenhuma igualdade foi presumida.",
        }
    if not diff.regions:
        return {
            **result,
            "status": "identical",
            "summary": "Nenhuma alteracao grafica acima do limiar deterministico foi localizada.",
            "changed_ratio": diff.changed_ratio,
        }
    return {
        **result,
        "status": "changed",
        "summary": f"{len(diff.regions)} regiao(oes) graficamente alterada(s) localizada(s).",
        "changed_ratio": diff.changed_ratio,
        "regions": diff.regions,
    }


def create_comparison(
    *,
    project_id: str,
    base_revision_id: str,
    target_revision_id: str,
    settings: Settings,
) -> dict[str, Any]:
    repository.ensure_revision_pair(
        project_id, base_revision_id, target_revision_id, settings
    )
    base_sheets = repository.list_revision_sheets(base_revision_id, settings)
    target_sheets = repository.list_revision_sheets(target_revision_id, settings)
    overrides = repository.list_active_pairings(
        project_id, base_revision_id, target_revision_id, settings
    )
    fingerprint = _fingerprint(
        project_id,
        base_revision_id,
        target_revision_id,
        base_sheets,
        target_sheets,
        overrides,
    )
    existing = repository.get_by_fingerprint(fingerprint, settings)
    if existing is not None:
        return existing

    candidates = match_sheets(base_sheets, target_sheets, overrides)
    pairs = [_evaluate_pair(candidate, settings) for candidate in candidates]
    counts = {status: 0 for status in PAIR_STATUSES}
    for pair in pairs:
        counts[str(pair["status"])] += 1
    counts["total"] = len(pairs)
    status = (
        "completed_with_limits"
        if counts["ambiguous"] > 0 or counts["unavailable"] > 0
        else "completed"
    )
    return repository.save_comparison(
        project_id=project_id,
        base_revision_id=base_revision_id,
        target_revision_id=target_revision_id,
        input_fingerprint=fingerprint,
        pipeline_version=COMPARISON_PIPELINE_VERSION,
        status=status,
        counts=counts,
        pairs=pairs,
        settings=settings,
    )
