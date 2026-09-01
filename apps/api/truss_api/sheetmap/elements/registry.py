from hashlib import sha256
import json

from truss_api.core.settings import Settings
from truss_api.core.text import normalize
from truss_api.db.connection import transaction
from truss_api.sheetmap.elements.levels import build_form_level_registry
from truss_api.sheetmap.snapshot import SHEET_MAP_PIPELINE


def _current_maps(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(str(row["sheet_id"]), []).append(row)

    selected: list[dict[str, object]] = []
    for sheet_id in sorted(grouped):
        candidates = grouped[sheet_id]
        candidates.sort(
            key=lambda item: (
                str(item["pipeline_version"]).startswith(SHEET_MAP_PIPELINE),
                str(item["built_at"]),
                str(item["id"]),
            ),
            reverse=True,
        )
        selected.append(candidates[0])
    return selected


def _element_digest(elements: list[dict[str, object]]) -> str:
    material = [
        {
            "kind": item["element_kind"],
            "code": item["code"],
            "view_id": item["view_id"],
            "scope": item["technical_scope"],
            "bbox": [item["x0"], item["y0"], item["x1"], item["y1"]],
            "provenance": item["provenance"],
            "attributes": item.get("attributes") or {},
        }
        for item in elements
    ]
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()[:16]


def build_revision_registry(revision_id: str, settings: Settings) -> dict[str, object]:
    with transaction(settings) as connection:
        map_rows = [
            dict(row)
            for row in connection.execute(
                """
                SELECT sm.*, s.document_id, s.page_index, s.label
                FROM sheet_maps sm
                JOIN sheets s ON s.id = sm.sheet_id
                WHERE sm.revision_id = ?
                ORDER BY sm.sheet_id, sm.built_at DESC, sm.id DESC
                """,
                (revision_id,),
            ).fetchall()
        ]
        current_maps = _current_maps(map_rows)
        occurrences: list[dict[str, object]] = []
        views: list[dict[str, object]] = []
        fingerprint_parts: list[str] = []

        for sheet_map in current_maps:
            sheet_map_id = str(sheet_map["id"])
            map_views = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT id, parent_view_id, view_kind, view_role, title_raw,
                           level_raw, level, technical_scope, confidence,
                           provenance, x0, y0, x1, y1
                    FROM sheet_views WHERE sheet_map_id = ? ORDER BY y0, x0, id
                    """,
                    (sheet_map_id,),
                ).fetchall()
            ]
            for view in map_views:
                view.update(
                    {
                        "sheet_map_id": sheet_map_id,
                        "sheet_id": str(sheet_map["sheet_id"]),
                        "document_id": str(sheet_map["document_id"]),
                        "sheet_code": sheet_map.get("sheet_code"),
                        "sheet_code_raw": sheet_map.get("sheet_code_raw"),
                        "page_index": sheet_map["page_index"],
                    }
                )
                views.append(view)

            map_elements = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT id, view_id, technical_scope, element_kind, code_raw,
                           code, attributes_json, x0, y0, x1, y1, confidence, provenance
                    FROM sheet_elements WHERE sheet_map_id = ?
                    ORDER BY element_kind, code, y0, x0, id
                    """,
                    (sheet_map_id,),
                ).fetchall()
            ]
            for element in map_elements:
                element["attributes"] = json.loads(
                    str(element.pop("attributes_json") or "{}")
                )
                element.update(
                    {
                        "sheet_map_id": sheet_map_id,
                        "sheet_id": str(sheet_map["sheet_id"]),
                        "document_id": str(sheet_map["document_id"]),
                        "sheet_code": sheet_map.get("sheet_code"),
                        "sheet_code_raw": sheet_map.get("sheet_code_raw"),
                        "page_index": sheet_map["page_index"],
                    }
                )
                occurrences.append(element)

            fingerprint_parts.append(
                "|".join(
                    [
                        sheet_map_id,
                        str(sheet_map.get("snapshot_hash") or ""),
                        _element_digest(map_elements),
                    ]
                )
            )

    fingerprint_material = "\n".join(sorted(fingerprint_parts))
    registry_hash = sha256(fingerprint_material.encode("utf-8")).hexdigest()[:24]
    registry = {
        "revision_id": revision_id,
        "registry_hash": registry_hash,
        "sheet_maps": current_maps,
        "views": views,
        "occurrences": occurrences,
        "pillar_sections": build_pillar_section_registry(occurrences),
    }
    registry.update(build_form_level_registry(registry))
    return registry


def _section_evidence(occurrence: dict[str, object]) -> list[dict[str, object]]:
    attributes = occurrence.get("attributes") or {}
    common = {
        "occurrence_id": occurrence.get("id"),
        "code_raw": occurrence.get("code_raw"),
        "code_bbox_pt": [
            occurrence.get("x0"),
            occurrence.get("y0"),
            occurrence.get("x1"),
            occurrence.get("y1"),
        ],
        "page_index": occurrence.get("page_index"),
        "sheet_id": occurrence.get("sheet_id"),
        "sheet_code": occurrence.get("sheet_code"),
    }
    if attributes.get("section_association_status") == "matched":
        return [
            {
                **common,
                "status": "matched",
                "section_raw": attributes.get("section_raw"),
                "section_signature": attributes.get("section_signature"),
                "section_ordered_signature": attributes.get(
                    "section_ordered_signature"
                ),
                "section_unit_raw": attributes.get("section_unit_raw"),
                "section_bbox_pt": attributes.get("section_bbox_pt"),
                "section_provenance": attributes.get("section_provenance"),
                "section_confidence": attributes.get("section_confidence"),
            }
        ]

    result: list[dict[str, object]] = []
    for candidate in attributes.get("section_candidates") or []:
        result.append(
            {
                **common,
                "status": "ambiguous",
                "section_raw": candidate.get("raw"),
                "section_signature": candidate.get("signature"),
                "section_ordered_signature": candidate.get("ordered_signature"),
                "section_unit_raw": candidate.get("unit_raw"),
                "section_bbox_pt": candidate.get("bbox_pt"),
                "section_provenance": attributes.get("section_provenance"),
                "section_confidence": None,
            }
        )
    return result


def _unit_key(value: object) -> str | None:
    return str(value).lower() if value is not None else None


def build_pillar_section_registry(
    occurrences: list[dict[str, object]],
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
    for occurrence in occurrences:
        if occurrence.get("element_kind") != "pillar" or not occurrence.get("view_id"):
            continue
        attributes = occurrence.get("attributes") or {}
        if attributes.get("section_association_status") not in {"matched", "ambiguous"}:
            continue
        key = (str(occurrence["view_id"]), str(occurrence["code"]))
        grouped.setdefault(key, []).append(occurrence)

    result: list[dict[str, object]] = []
    for (view_id, code), group in sorted(grouped.items()):
        evidence = [
            item
            for occurrence in group
            for item in _section_evidence(occurrence)
        ]
        evidence.sort(
            key=lambda item: (
                int(item.get("page_index") or 0),
                item.get("section_bbox_pt") or [],
                str(item.get("section_raw") or ""),
            )
        )
        signatures = {
            tuple(item["section_signature"])
            for item in evidence
            if item.get("section_signature") is not None
        }
        units = {_unit_key(item.get("section_unit_raw")) for item in evidence}
        has_ambiguous_occurrence = any(
            (occurrence.get("attributes") or {}).get("section_association_status")
            == "ambiguous"
            for occurrence in group
        )
        first = group[0]
        base = {
            "view_id": view_id,
            "code": code,
            "technical_scope": first.get("technical_scope"),
            "document_id": first.get("document_id"),
            "sheet_map_id": first.get("sheet_map_id"),
            "sheet_id": first.get("sheet_id"),
            "sheet_code": first.get("sheet_code"),
            "page_index": first.get("page_index"),
            "evidence_count": len(evidence),
            "evidence": evidence,
        }

        if has_ambiguous_occurrence or len(signatures) != 1 or len(units) != 1:
            result.append(
                {
                    **base,
                    "status": "ambiguous",
                    "section_signatures": [
                        list(signature) for signature in sorted(signatures)
                    ],
                    "section_units": sorted(
                        units, key=lambda value: (value is not None, value or "")
                    ),
                }
            )
            continue

        selected = evidence[0]
        confidences = [
            float(item["section_confidence"])
            for item in evidence
            if item.get("section_confidence") is not None
        ]
        reinforced_confidence = min(
            0.99,
            (max(confidences) if confidences else 0.0)
            + min(0.04, max(0, len(evidence) - 1) * 0.02),
        )
        result.append(
            {
                **base,
                "status": "resolved",
                "resolution": "reinforced" if len(evidence) > 1 else "unique",
                "section_raw": selected.get("section_raw"),
                "section_signature": list(next(iter(signatures))),
                "section_ordered_signature": selected.get(
                    "section_ordered_signature"
                ),
                "section_unit_raw": selected.get("section_unit_raw"),
                "section_bbox_pt": selected.get("section_bbox_pt"),
                "code_bbox_pt": selected.get("code_bbox_pt"),
                "section_provenance": selected.get("section_provenance"),
                "section_confidence": round(reinforced_confidence, 3),
            }
        )
    return result


def pillar_detail_views(registry: dict[str, object]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for view in registry.get("views", []):
        title = normalize(str(view.get("title_raw") or ""))
        is_pillar_detail = "PILAR" in title and (
            "DETALHE" in title or "DETALHAMENTO" in title
        )
        # O titulo da view e evidencia mais especifica que o escopo global da
        # folha. No projeto-base, "DETALHAMENTO FUNDACOES E PILARES DE
        # ARRANQUE" e classificado como locacao por uma nota de revisao no
        # carimbo; descartar o titulo explicito cria dezenas de falsos ausentes.
        if is_pillar_detail:
            result.append(view)
    return result
