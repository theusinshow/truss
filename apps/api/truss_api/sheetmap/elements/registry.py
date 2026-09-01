from hashlib import sha256
import json

from truss_api.core.settings import Settings
from truss_api.core.text import normalize
from truss_api.db.connection import transaction
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
                           technical_scope, confidence, x0, y0, x1, y1
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
    return {
        "revision_id": revision_id,
        "registry_hash": registry_hash,
        "sheet_maps": current_maps,
        "views": views,
        "occurrences": occurrences,
    }


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
