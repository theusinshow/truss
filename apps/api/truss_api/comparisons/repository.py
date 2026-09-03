from datetime import UTC, datetime
import json
import sqlite3
from typing import Any
from uuid import uuid4

from truss_api.core.settings import Settings
from truss_api.db.connection import transaction
from truss_api.recovery.errors import TrussError


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _not_found(message: str, action: str) -> TrussError:
    return TrussError(
        code="COMPARISON_NOT_FOUND",
        message=message,
        action=action,
        status_code=404,
    )


def ensure_revision_pair(
    project_id: str,
    base_revision_id: str,
    target_revision_id: str,
    settings: Settings,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if base_revision_id == target_revision_id:
        raise TrussError(
            code="COMPARISON_REVISIONS_EQUAL",
            message="A revisao-base e a revisao-alvo precisam ser diferentes.",
            action="Escolha duas revisoes imutaveis do mesmo projeto.",
            status_code=409,
        )
    with transaction(settings) as connection:
        rows = connection.execute(
            """
            SELECT id, project_id, revision_code, created_at
            FROM revisions
            WHERE id IN (?, ?)
            """,
            (base_revision_id, target_revision_id),
        ).fetchall()
    revisions = {str(row["id"]): dict(row) for row in rows}
    if base_revision_id not in revisions or target_revision_id not in revisions:
        raise _not_found(
            "Uma das revisoes da comparacao nao foi encontrada.",
            "Atualize o projeto e selecione revisoes existentes.",
        )
    if any(str(item["project_id"]) != project_id for item in revisions.values()):
        raise TrussError(
            code="COMPARISON_PROJECT_MISMATCH",
            message="As revisoes selecionadas nao pertencem ao mesmo projeto.",
            action="Escolha duas revisoes dentro do projeto ativo.",
            status_code=409,
        )
    return revisions[base_revision_id], revisions[target_revision_id]


def list_revision_sheets(revision_id: str, settings: Settings) -> list[dict[str, Any]]:
    with transaction(settings) as connection:
        rows = connection.execute(
            """
            SELECT
                s.id, s.document_id, s.project_id, s.revision_id, s.page_index,
                s.sheet_number, s.width_pt, s.height_pt, s.rotation, s.label,
                d.content_hash AS document_hash, d.stored_file_path,
                COALESCE(source_event.status, 'AVAILABLE') AS source_status,
                sm.id AS sheet_map_id, sm.snapshot_hash, sm.extractor_version,
                sm.sheet_code, sm.sheet_code_raw
            FROM sheets s
            JOIN documents d ON d.id = s.document_id
            LEFT JOIN document_source_events source_event
              ON source_event.id = (
                  SELECT candidate.id
                  FROM document_source_events candidate
                  WHERE candidate.document_id = d.id
                  ORDER BY candidate.sequence DESC
                  LIMIT 1
              )
            LEFT JOIN sheet_maps sm
              ON sm.id = (
                  SELECT candidate.id
                  FROM sheet_maps candidate
                  WHERE candidate.sheet_id = s.id
                  ORDER BY candidate.built_at DESC, candidate.id DESC
                  LIMIT 1
              )
            WHERE s.revision_id = ?
            ORDER BY s.sheet_number, s.document_id, s.page_index
            """,
            (revision_id,),
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["source_exists"] = (settings.data_dir / str(item["stored_file_path"])).exists()
        result.append(item)
    return result


def list_active_pairings(
    project_id: str,
    base_revision_id: str,
    target_revision_id: str,
    settings: Settings,
) -> list[dict[str, Any]]:
    with transaction(settings) as connection:
        rows = connection.execute(
            """
            SELECT * FROM comparison_pair_overrides
            WHERE project_id = ? AND base_revision_id = ? AND target_revision_id = ?
              AND revoked_at IS NULL
            ORDER BY created_at, id
            """,
            (project_id, base_revision_id, target_revision_id),
        ).fetchall()
    return [dict(row) for row in rows]


def get_by_fingerprint(fingerprint: str, settings: Settings) -> dict[str, Any] | None:
    with transaction(settings) as connection:
        row = connection.execute(
            "SELECT id FROM revision_comparisons WHERE input_fingerprint = ?",
            (fingerprint,),
        ).fetchone()
    return get_comparison(str(row["id"]), settings) if row is not None else None


def save_comparison(
    *,
    project_id: str,
    base_revision_id: str,
    target_revision_id: str,
    input_fingerprint: str,
    pipeline_version: str,
    status: str,
    counts: dict[str, int],
    pairs: list[dict[str, Any]],
    settings: Settings,
) -> dict[str, Any]:
    comparison_id = str(uuid4())
    created_at = _now()
    try:
        with transaction(settings) as connection:
            connection.execute(
                """
                INSERT INTO revision_comparisons (
                    id, project_id, base_revision_id, target_revision_id,
                    input_fingerprint, pipeline_version, status, counts_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    comparison_id,
                    project_id,
                    base_revision_id,
                    target_revision_id,
                    input_fingerprint,
                    pipeline_version,
                    status,
                    json.dumps(counts, sort_keys=True),
                    created_at,
                ),
            )
            for sequence, pair in enumerate(pairs):
                pair_id = str(uuid4())
                connection.execute(
                    """
                    INSERT INTO revision_comparison_pairs (
                        id, comparison_id, sequence, base_sheet_id, target_sheet_id,
                        status, match_method, match_confidence, pairing_override_id,
                        summary, changed_ratio, base_identity_json, target_identity_json,
                        delta_status, delta_counts_json, delta_truncated, delta_summary,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pair_id,
                        comparison_id,
                        sequence,
                        pair["base_sheet_id"],
                        pair["target_sheet_id"],
                        pair["status"],
                        pair["match_method"],
                        pair["match_confidence"],
                        pair["pairing_override_id"],
                        pair["summary"],
                        pair["changed_ratio"],
                        json.dumps(pair["base_identity"], sort_keys=True)
                        if pair["base_identity"] is not None
                        else None,
                        json.dumps(pair["target_identity"], sort_keys=True)
                        if pair["target_identity"] is not None
                        else None,
                        pair["delta_status"],
                        json.dumps(pair["delta_counts"], sort_keys=True),
                        int(pair["delta_truncated"]),
                        pair["delta_summary"],
                        created_at,
                    ),
                )
                for region_index, region in enumerate(pair["regions"]):
                    base_bbox = region["base_bbox"]
                    target_bbox = region["target_bbox"]
                    connection.execute(
                        """
                        INSERT INTO revision_comparison_regions (
                            id, pair_id, region_index,
                            base_x0, base_y0, base_x1, base_y1,
                            target_x0, target_y0, target_x1, target_y1,
                            changed_pixel_count, changed_ratio, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(uuid4()),
                            pair_id,
                            region_index,
                            base_bbox["x0"],
                            base_bbox["y0"],
                            base_bbox["x1"],
                            base_bbox["y1"],
                            target_bbox["x0"],
                            target_bbox["y0"],
                            target_bbox["x1"],
                            target_bbox["y1"],
                            region["changed_pixel_count"],
                            region["changed_ratio"],
                            created_at,
                        ),
                    )
                for delta_index, delta in enumerate(pair["deltas"]):
                    base_bbox = delta["base_bbox"]
                    target_bbox = delta["target_bbox"]
                    connection.execute(
                        """
                        INSERT INTO revision_comparison_deltas (
                            id, pair_id, delta_index, layer, change_type,
                            match_evidence, similarity, before_value, after_value,
                            base_x0, base_y0, base_x1, base_y1,
                            target_x0, target_y0, target_x1, target_y1,
                            details_json, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(uuid4()),
                            pair_id,
                            delta_index,
                            delta["layer"],
                            delta["change_type"],
                            delta["match_evidence"],
                            delta["similarity"],
                            delta["before_value"],
                            delta["after_value"],
                            base_bbox["x0"] if base_bbox else None,
                            base_bbox["y0"] if base_bbox else None,
                            base_bbox["x1"] if base_bbox else None,
                            base_bbox["y1"] if base_bbox else None,
                            target_bbox["x0"] if target_bbox else None,
                            target_bbox["y0"] if target_bbox else None,
                            target_bbox["x1"] if target_bbox else None,
                            target_bbox["y1"] if target_bbox else None,
                            json.dumps(delta["details"], ensure_ascii=False, sort_keys=True),
                            created_at,
                        ),
                    )
    except sqlite3.IntegrityError:
        existing = get_by_fingerprint(input_fingerprint, settings)
        if existing is not None:
            return existing
        raise
    return get_comparison(comparison_id, settings)


def _region_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "region_index": int(row["region_index"]),
        "base_bbox": {
            "x0": float(row["base_x0"]),
            "y0": float(row["base_y0"]),
            "x1": float(row["base_x1"]),
            "y1": float(row["base_y1"]),
        },
        "target_bbox": {
            "x0": float(row["target_x0"]),
            "y0": float(row["target_y0"]),
            "x1": float(row["target_x1"]),
            "y1": float(row["target_y1"]),
        },
        "changed_pixel_count": int(row["changed_pixel_count"]),
        "changed_ratio": float(row["changed_ratio"]),
    }


def _nullable_bbox_payload(row: sqlite3.Row, prefix: str) -> dict[str, float] | None:
    if row[f"{prefix}_x0"] is None:
        return None
    return {
        "x0": float(row[f"{prefix}_x0"]),
        "y0": float(row[f"{prefix}_y0"]),
        "x1": float(row[f"{prefix}_x1"]),
        "y1": float(row[f"{prefix}_y1"]),
    }


def _delta_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "delta_index": int(row["delta_index"]),
        "layer": str(row["layer"]),
        "change_type": str(row["change_type"]),
        "match_evidence": str(row["match_evidence"]),
        "similarity": float(row["similarity"]),
        "before_value": row["before_value"],
        "after_value": row["after_value"],
        "base_bbox": _nullable_bbox_payload(row, "base"),
        "target_bbox": _nullable_bbox_payload(row, "target"),
        "details": json.loads(str(row["details_json"])),
    }


def get_comparison(comparison_id: str, settings: Settings) -> dict[str, Any]:
    with transaction(settings) as connection:
        row = connection.execute(
            """
            SELECT c.*, base.revision_code AS base_revision_code,
                   target.revision_code AS target_revision_code
            FROM revision_comparisons c
            JOIN revisions base ON base.id = c.base_revision_id
            JOIN revisions target ON target.id = c.target_revision_id
            WHERE c.id = ?
            """,
            (comparison_id,),
        ).fetchone()
        if row is None:
            raise _not_found(
                "A comparacao solicitada nao foi encontrada.",
                "Crie novamente a comparacao a partir do projeto.",
            )
        pair_rows = connection.execute(
            "SELECT * FROM revision_comparison_pairs WHERE comparison_id = ? ORDER BY sequence",
            (comparison_id,),
        ).fetchall()
        pairs: list[dict[str, Any]] = []
        for pair_row in pair_rows:
            region_rows = connection.execute(
                "SELECT * FROM revision_comparison_regions WHERE pair_id = ? ORDER BY region_index",
                (pair_row["id"],),
            ).fetchall()
            delta_rows = connection.execute(
                "SELECT * FROM revision_comparison_deltas WHERE pair_id = ? ORDER BY delta_index",
                (pair_row["id"],),
            ).fetchall()
            pairs.append(
                {
                    "id": str(pair_row["id"]),
                    "sequence": int(pair_row["sequence"]),
                    "base_sheet": json.loads(str(pair_row["base_identity_json"]))
                    if pair_row["base_identity_json"] is not None
                    else None,
                    "target_sheet": json.loads(str(pair_row["target_identity_json"]))
                    if pair_row["target_identity_json"] is not None
                    else None,
                    "status": str(pair_row["status"]),
                    "match_method": str(pair_row["match_method"]),
                    "match_confidence": float(pair_row["match_confidence"]),
                    "pairing_override_id": pair_row["pairing_override_id"],
                    "summary": str(pair_row["summary"]),
                    "changed_ratio": float(pair_row["changed_ratio"]),
                    "regions": [_region_payload(region) for region in region_rows],
                    "delta_status": str(pair_row["delta_status"]),
                    "delta_counts": json.loads(str(pair_row["delta_counts_json"])),
                    "delta_truncated": bool(pair_row["delta_truncated"]),
                    "delta_summary": str(pair_row["delta_summary"]),
                    "deltas": [_delta_payload(delta) for delta in delta_rows],
                }
            )
    return {
        "id": str(row["id"]),
        "project_id": str(row["project_id"]),
        "base_revision_id": str(row["base_revision_id"]),
        "target_revision_id": str(row["target_revision_id"]),
        "base_revision_code": str(row["base_revision_code"]),
        "target_revision_code": str(row["target_revision_code"]),
        "input_fingerprint": str(row["input_fingerprint"]),
        "pipeline_version": str(row["pipeline_version"]),
        "status": str(row["status"]),
        "counts": json.loads(str(row["counts_json"])),
        "created_at": str(row["created_at"]),
        "pairs": pairs,
    }


def _pairing_payload(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["active"] = row["revoked_at"] is None
    return result


def create_pairing(
    *,
    project_id: str,
    base_revision_id: str,
    target_revision_id: str,
    base_sheet_id: str,
    target_sheet_id: str,
    settings: Settings,
) -> dict[str, Any]:
    ensure_revision_pair(project_id, base_revision_id, target_revision_id, settings)
    created_at = _now()
    with transaction(settings) as connection:
        base_sheet = connection.execute(
            "SELECT id FROM sheets WHERE id = ? AND revision_id = ? AND project_id = ?",
            (base_sheet_id, base_revision_id, project_id),
        ).fetchone()
        target_sheet = connection.execute(
            "SELECT id FROM sheets WHERE id = ? AND revision_id = ? AND project_id = ?",
            (target_sheet_id, target_revision_id, project_id),
        ).fetchone()
        if base_sheet is None or target_sheet is None:
            raise _not_found(
                "Uma das folhas do pareamento nao pertence as revisoes selecionadas.",
                "Selecione uma folha-base e uma folha-alvo validas.",
            )
        existing = connection.execute(
            """
            SELECT * FROM comparison_pair_overrides
            WHERE project_id = ? AND base_revision_id = ? AND target_revision_id = ?
              AND base_sheet_id = ? AND target_sheet_id = ? AND revoked_at IS NULL
            """,
            (
                project_id,
                base_revision_id,
                target_revision_id,
                base_sheet_id,
                target_sheet_id,
            ),
        ).fetchone()
        if existing is not None:
            return _pairing_payload(existing)
        connection.execute(
            """
            UPDATE comparison_pair_overrides SET revoked_at = ?
            WHERE project_id = ? AND base_revision_id = ? AND target_revision_id = ?
              AND revoked_at IS NULL AND (base_sheet_id = ? OR target_sheet_id = ?)
            """,
            (
                created_at,
                project_id,
                base_revision_id,
                target_revision_id,
                base_sheet_id,
                target_sheet_id,
            ),
        )
        pairing_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO comparison_pair_overrides (
                id, project_id, base_revision_id, target_revision_id,
                base_sheet_id, target_sheet_id, created_at, revoked_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                pairing_id,
                project_id,
                base_revision_id,
                target_revision_id,
                base_sheet_id,
                target_sheet_id,
                created_at,
            ),
        )
        row = connection.execute(
            "SELECT * FROM comparison_pair_overrides WHERE id = ?", (pairing_id,)
        ).fetchone()
    return _pairing_payload(row)


def revoke_pairing(pairing_id: str, settings: Settings) -> dict[str, Any]:
    revoked_at = _now()
    with transaction(settings) as connection:
        row = connection.execute(
            "SELECT * FROM comparison_pair_overrides WHERE id = ?", (pairing_id,)
        ).fetchone()
        if row is None:
            raise _not_found(
                "O pareamento manual nao foi encontrado.",
                "Atualize a comparacao antes de tentar novamente.",
            )
        if row["revoked_at"] is None:
            connection.execute(
                "UPDATE comparison_pair_overrides SET revoked_at = ? WHERE id = ?",
                (revoked_at, pairing_id),
            )
        updated = connection.execute(
            "SELECT * FROM comparison_pair_overrides WHERE id = ?", (pairing_id,)
        ).fetchone()
    return _pairing_payload(updated)
