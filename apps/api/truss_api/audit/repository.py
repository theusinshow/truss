from datetime import UTC, datetime
import json
from sqlite3 import Row
from uuid import uuid4

from truss_api.audit.models import FindingStatusUpdate, ManualFindingCreate
from truss_api.core.settings import Settings
from truss_api.db.connection import transaction
from truss_api.documents.repository import SheetNotFoundError


class FindingNotFoundError(Exception):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _finding_from_row(row: Row) -> dict[str, object]:
    data = dict(row)
    data["bbox"] = {
        "x0": data.pop("x0"),
        "y0": data.pop("y0"),
        "x1": data.pop("x1"),
        "y1": data.pop("y1"),
    }
    data["evidence"] = json.loads(str(data.pop("evidence_json")))
    return data


def get_sheet_context(sheet_id: str, settings: Settings) -> dict[str, object]:
    with transaction(settings) as connection:
        row = connection.execute(
            """
            SELECT
                s.id AS sheet_id,
                s.document_id,
                s.project_id,
                s.revision_id,
                s.width_pt,
                s.height_pt,
                s.label
            FROM sheets s
            WHERE s.id = ?
            """,
            (sheet_id,),
        ).fetchone()

    if row is None:
        raise SheetNotFoundError(sheet_id)

    return dict(row)


def list_text_blocks(sheet_id: str, settings: Settings) -> list[dict[str, object]]:
    with transaction(settings) as connection:
        rows = connection.execute(
            """
            SELECT block_index, text, x0, y0, x1, y1
            FROM text_blocks
            WHERE sheet_id = ?
            ORDER BY block_index ASC
            """,
            (sheet_id,),
        ).fetchall()

    return [dict(row) for row in rows]


def create_audit_run(
    *,
    sheet_context: dict[str, object],
    findings: list[dict[str, object]],
    settings: Settings,
    cache_key: str | None = None,
    sheet_map_id: str | None = None,
    rule_pack_version: str = "",
    coverage: dict[str, object] | None = None,
    evaluations: list[object] | None = None,
) -> dict[str, object]:
    now = _now()
    audit_run_id = str(uuid4())

    with transaction(settings) as connection:
        connection.execute(
            """
            INSERT INTO audit_runs (
                id,
                sheet_id,
                document_id,
                project_id,
                revision_id,
                mode,
                pipeline_version,
                status,
                summary,
                started_at,
                completed_at,
                sheet_map_id,
                rule_pack_version,
                coverage_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                audit_run_id,
                sheet_context["sheet_id"],
                sheet_context["document_id"],
                sheet_context["project_id"],
                sheet_context["revision_id"],
                "aggressive",
                "deterministic-v0.2",
                "completed",
                f"{len(findings)} achados gerados por regras deterministicas.",
                now,
                now,
                sheet_map_id,
                rule_pack_version,
                json.dumps(coverage or {}),
            ),
        )

        for finding in findings:
            bbox = finding["bbox"]
            dedupe_key = finding.get("dedupe_key")
            existing = None

            if dedupe_key:
                existing = connection.execute(
                    """
                    SELECT id FROM findings
                    WHERE sheet_id = ? AND dedupe_key = ?
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (str(sheet_context["sheet_id"]), dedupe_key),
                ).fetchone()

            if existing is not None:
                # Achado ja conhecido: vincula a nova execucao e preserva
                # integralmente o status decidido por humano.
                connection.execute(
                    "UPDATE findings SET audit_run_id = ?, updated_at = ? WHERE id = ?",
                    (audit_run_id, now, str(existing["id"])),
                )
                continue

            connection.execute(
                """
                INSERT INTO findings (
                    id, audit_run_id, sheet_id, document_id, project_id, revision_id,
                    category, type, description, severity, confidence,
                    x0, y0, x1, y1, evidence_json, origin, status, rejection_reason,
                    created_at, updated_at,
                    rule_id, rule_version, rule_scope, technical_scope, sheet_map_id, view_id,
                    source_layer, dedupe_key
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    audit_run_id,
                    sheet_context["sheet_id"],
                    sheet_context["document_id"],
                    sheet_context["project_id"],
                    sheet_context["revision_id"],
                    finding["category"],
                    finding["type"],
                    finding["description"],
                    finding["severity"],
                    finding["confidence"],
                    bbox["x0"],
                    bbox["y0"],
                    bbox["x1"],
                    bbox["y1"],
                    json.dumps(finding["evidence"], ensure_ascii=False),
                    "ai",
                    "pending",
                    None,
                    now,
                    now,
                    finding.get("rule_id"),
                    finding.get("rule_version"),
                    finding.get("rule_scope"),
                    finding.get("technical_scope"),
                    sheet_map_id,
                    finding.get("view_id"),
                    finding.get("source_layer"),
                    dedupe_key,
                ),
            )

        for evaluation in evaluations or []:
            connection.execute(
                """
                INSERT INTO rule_evaluations (
                    id, audit_run_id, sheet_map_id, sheet_id, rule_id, rule_version,
                    rule_pack_id, rule_pack_version, rule_scope, technical_scope,
                    target_kind, target_id,
                    outcome, confidence, reason, evidence_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    audit_run_id,
                    sheet_map_id,
                    str(sheet_context["sheet_id"]),
                    evaluation.rule_id,
                    evaluation.rule_version,
                    evaluation.rule_pack_id,
                    evaluation.rule_pack_version,
                    evaluation.scope,
                    evaluation.technical_scope,
                    evaluation.target_kind,
                    evaluation.target_id,
                    evaluation.outcome,
                    evaluation.confidence,
                    evaluation.reason,
                    json.dumps(evaluation.evidence, ensure_ascii=False),
                    now,
                ),
            )

        if cache_key:
            connection.execute(
                """
                INSERT OR REPLACE INTO cache_entries (id, cache_key, namespace, value, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (str(uuid4()), cache_key, "audit", audit_run_id, now),
            )

    return get_audit_run(audit_run_id, settings)


def get_cached_audit_run(cache_key: str, settings: Settings) -> dict[str, object] | None:
    with transaction(settings) as connection:
        row = connection.execute(
            "SELECT value FROM cache_entries WHERE cache_key = ? AND namespace = 'audit'",
            (cache_key,),
        ).fetchone()

    if row is None:
        return None

    return get_audit_run(str(row["value"]), settings)


def get_audit_run(audit_run_id: str, settings: Settings) -> dict[str, object]:
    with transaction(settings) as connection:
        audit_run = connection.execute(
            """
            SELECT
                id,
                sheet_id,
                document_id,
                project_id,
                revision_id,
                mode,
                pipeline_version,
                status,
                summary,
                started_at,
                completed_at,
                coverage_json
            FROM audit_runs
            WHERE id = ?
            """,
            (audit_run_id,),
        ).fetchone()

        rows = connection.execute(
            """
            SELECT *
            FROM findings
            WHERE audit_run_id = ?
            ORDER BY severity DESC, created_at ASC
            """,
            (audit_run_id,),
        ).fetchall()

    data = dict(audit_run)
    data["coverage"] = json.loads(str(data.pop("coverage_json") or "{}"))
    data["findings"] = [_finding_from_row(row) for row in rows]
    return data


def clear_audit_cache(settings: Settings) -> None:
    with transaction(settings) as connection:
        connection.execute("DELETE FROM cache_entries WHERE namespace = 'audit'")


def list_findings_for_sheet(sheet_id: str, settings: Settings) -> list[dict[str, object]]:
    with transaction(settings) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM findings
            WHERE sheet_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (sheet_id,),
        ).fetchall()

    return [_finding_from_row(row) for row in rows]


def update_finding_status(
    finding_id: str,
    payload: FindingStatusUpdate,
    settings: Settings,
) -> dict[str, object]:
    now = _now()

    with transaction(settings) as connection:
        current = connection.execute(
            "SELECT id FROM findings WHERE id = ?",
            (finding_id,),
        ).fetchone()

        if current is None:
            raise FindingNotFoundError(finding_id)

        rejection_reason = payload.rejection_reason if payload.status == "rejected" else None
        connection.execute(
            """
            UPDATE findings
            SET status = ?, rejection_reason = ?, updated_at = ?
            WHERE id = ?
            """,
            (payload.status, rejection_reason, now, finding_id),
        )

        row = connection.execute("SELECT * FROM findings WHERE id = ?", (finding_id,)).fetchone()

    return _finding_from_row(row)


def create_manual_finding(
    sheet_id: str,
    payload: ManualFindingCreate,
    settings: Settings,
) -> dict[str, object]:
    context = get_sheet_context(sheet_id, settings)
    now = _now()
    finding_id = str(uuid4())

    with transaction(settings) as connection:
        connection.execute(
            """
            INSERT INTO findings (
                id,
                audit_run_id,
                sheet_id,
                document_id,
                project_id,
                revision_id,
                category,
                type,
                description,
                severity,
                confidence,
                x0,
                y0,
                x1,
                y1,
                evidence_json,
                origin,
                status,
                rejection_reason,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                finding_id,
                None,
                context["sheet_id"],
                context["document_id"],
                context["project_id"],
                context["revision_id"],
                payload.category,
                payload.type,
                payload.description,
                payload.severity,
                payload.confidence,
                payload.bbox.x0,
                payload.bbox.y0,
                payload.bbox.x1,
                payload.bbox.y1,
                json.dumps(payload.evidence, ensure_ascii=False),
                "human",
                "pending",
                None,
                now,
                now,
            ),
        )

        row = connection.execute("SELECT * FROM findings WHERE id = ?", (finding_id,)).fetchone()

    return _finding_from_row(row)
