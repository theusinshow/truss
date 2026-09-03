from datetime import UTC, datetime
from hashlib import sha256
import json
import sqlite3
from uuid import uuid4

from truss_api.core.settings import Settings
from truss_api.db.connection import transaction
from truss_api.recovery.errors import TrussError


BATCH_PIPELINE_VERSION = "batch-v0.1"
ACTIVE_STATUSES = ("queued", "running", "cancel_requested", "interrupted")
TERMINAL_ITEM_STATUSES = (
    "completed",
    "failed",
    "skipped_dependency",
    "cancelled",
    "manual_retry_required",
)
PHASES = ("sheet_map", "deterministic_audit", "visual_audit")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _event(
    connection: sqlite3.Connection,
    batch_run_id: str,
    event_kind: str,
    phase: str,
    detail: dict[str, object] | None = None,
) -> None:
    row = connection.execute(
        "SELECT COALESCE(MAX(sequence), 0) + 1 FROM batch_run_events WHERE batch_run_id = ?",
        (batch_run_id,),
    ).fetchone()
    connection.execute(
        """
        INSERT INTO batch_run_events (
            id, batch_run_id, sequence, event_kind, phase, detail_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid4()),
            batch_run_id,
            int(row[0]),
            event_kind,
            phase,
            json.dumps(detail or {}, ensure_ascii=False, sort_keys=True),
            _now(),
        ),
    )


def _run_dict(row: sqlite3.Row) -> dict[str, object]:
    value = dict(row)
    value["config"] = json.loads(str(value.pop("config_json") or "{}"))
    return value


def _item_dict(row: sqlite3.Row) -> dict[str, object]:
    value = dict(row)
    value.pop("run_token", None)
    return value


def list_sheet_ids_for_revision(revision_id: str, settings: Settings) -> list[str]:
    with transaction(settings) as connection:
        rows = connection.execute(
            """
            SELECT s.id
            FROM sheets s
            JOIN documents d ON d.id = s.document_id
            WHERE s.revision_id = ?
            ORDER BY d.created_at, s.page_index, s.id
            """,
            (revision_id,),
        ).fetchall()
    return [str(row["id"]) for row in rows]


def batch_fingerprint(
    revision_id: str,
    sheet_ids: list[str],
    mode: str,
    config: dict[str, object],
) -> str:
    material = json.dumps(
        {
            "revision_id": revision_id,
            "sheet_ids": sheet_ids,
            "mode": mode,
            "config": config,
            "pipeline": BATCH_PIPELINE_VERSION,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(material.encode("utf-8")).hexdigest()


def create_batch_run(
    *,
    project_id: str,
    revision_id: str,
    mode: str,
    config: dict[str, object],
    settings: Settings,
) -> dict[str, object]:
    sheet_ids = list_sheet_ids_for_revision(revision_id, settings)
    if not sheet_ids:
        raise TrussError(
            code="BATCH_EMPTY",
            message="A revisao nao possui folhas para processar.",
            action="Importe um PDF antes de iniciar o lote.",
            status_code=409,
        )
    fingerprint = batch_fingerprint(revision_id, sheet_ids, mode, config)
    batch_id = str(uuid4())
    now = _now()
    if mode == "with_visual" and config.get("ai_review") is True:
        phases = ["sheet_map", "visual_audit"]
    else:
        phases = ["sheet_map", "deterministic_audit"]
        if mode == "with_visual":
            phases.append("visual_audit")

    with transaction(settings) as connection:
        revision = connection.execute(
            "SELECT id FROM revisions WHERE id = ? AND project_id = ?",
            (revision_id, project_id),
        ).fetchone()
        if revision is None:
            raise TrussError(
                code="REVISION_NOT_FOUND",
                message="A revisao informada nao existe neste projeto.",
                action="Atualize o projeto e selecione uma revisao valida.",
                status_code=404,
            )
        try:
            connection.execute(
                """
                INSERT INTO batch_runs (
                    id, project_id, revision_id, mode, status, phase, config_json,
                    input_fingerprint, pipeline_version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'queued', 'sheet_map', ?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    project_id,
                    revision_id,
                    mode,
                    json.dumps(config, ensure_ascii=False, sort_keys=True),
                    fingerprint,
                    BATCH_PIPELINE_VERSION,
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError:
            existing = connection.execute(
                """
                SELECT id FROM batch_runs
                WHERE revision_id = ? AND mode = ?
                  AND status IN ('queued', 'running', 'cancel_requested', 'interrupted')
                ORDER BY created_at DESC LIMIT 1
                """,
                (revision_id, mode),
            ).fetchone()
            if existing is None:
                raise
            raise TrussError(
                code="BATCH_ALREADY_ACTIVE",
                message="Esta revisao ja possui um lote ativo neste modo.",
                action="Acompanhe ou encerre o lote atual antes de iniciar outro.",
                status_code=409,
            )
        else:
            for phase in phases:
                for sequence, sheet_id in enumerate(sheet_ids, start=1):
                    connection.execute(
                        """
                        INSERT INTO batch_items (
                            id, batch_run_id, sheet_id, phase, sequence, status,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, 'queued', ?, ?)
                        """,
                        (str(uuid4()), batch_id, sheet_id, phase, sequence, now, now),
                    )
            _event(connection, batch_id, "created", "sheet_map", {"sheets": len(sheet_ids)})
    return get_batch_run(batch_id, settings)


def get_batch_run(batch_run_id: str, settings: Settings) -> dict[str, object]:
    with transaction(settings) as connection:
        row = connection.execute(
            "SELECT * FROM batch_runs WHERE id = ?", (batch_run_id,)
        ).fetchone()
        if row is None:
            raise TrussError(
                code="BATCH_NOT_FOUND",
                message="O lote local nao foi encontrado.",
                action="Atualize a revisao ativa.",
                status_code=404,
            )
        phase_rows = connection.execute(
            """
            SELECT phase, status, COUNT(*) AS count
            FROM batch_items WHERE batch_run_id = ?
            GROUP BY phase, status
            """,
            (batch_run_id,),
        ).fetchall()
        total = int(
            connection.execute(
                "SELECT COUNT(DISTINCT sheet_id) FROM batch_items WHERE batch_run_id = ?",
                (batch_run_id,),
            ).fetchone()[0]
        )
    value = _run_dict(row)
    phase_counts: dict[str, dict[str, int]] = {}
    for item in phase_rows:
        phase_counts.setdefault(str(item["phase"]), {})[str(item["status"])] = int(
            item["count"]
        )
    value["total_sheets"] = total
    value["phase_counts"] = phase_counts
    value["counts"] = phase_counts.get(str(value["phase"]), {})
    return value


def list_revision_batch_runs(
    revision_id: str,
    settings: Settings,
    *,
    active_only: bool = False,
) -> list[dict[str, object]]:
    with transaction(settings) as connection:
        sql = "SELECT id FROM batch_runs WHERE revision_id = ?"
        params: list[object] = [revision_id]
        if active_only:
            sql += " AND status IN (?, ?, ?, ?)"
            params.extend(ACTIVE_STATUSES)
        sql += " ORDER BY created_at DESC"
        rows = connection.execute(sql, params).fetchall()
    return [get_batch_run(str(row["id"]), settings) for row in rows]


def list_batch_items(
    batch_run_id: str,
    settings: Settings,
    *,
    status: str | None = None,
    phase: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, object]]:
    get_batch_run(batch_run_id, settings)
    clauses = ["batch_run_id = ?"]
    params: list[object] = [batch_run_id]
    if status:
        clauses.append("status = ?")
        params.append(status)
    if phase:
        clauses.append("phase = ?")
        params.append(phase)
    params.extend([limit, offset])
    with transaction(settings) as connection:
        rows = connection.execute(
            f"""
            SELECT batch_items.*, sheets.label AS sheet_label,
                   sheets.sheet_number AS sheet_number
            FROM batch_items
            JOIN sheets ON sheets.id = batch_items.sheet_id
            WHERE {' AND '.join(clauses)}
            ORDER BY phase, sequence LIMIT ? OFFSET ?
            """,
            params,
        ).fetchall()
    return [_item_dict(row) for row in rows]


def _phase_order(mode: str, config: dict[str, object] | None = None) -> list[str]:
    if mode == "with_visual" and (config or {}).get("ai_review") is True:
        return ["sheet_map", "visual_audit"]
    if mode == "with_visual":
        return ["sheet_map", "deterministic_audit", "visual_audit"]
    return ["sheet_map", "deterministic_audit"]


def _advance_run(connection: sqlite3.Connection, batch_id: str) -> None:
    run = connection.execute("SELECT * FROM batch_runs WHERE id = ?", (batch_id,)).fetchone()
    if run is None or str(run["status"]) in {"completed", "completed_with_errors", "cancelled"}:
        return
    now = _now()
    if str(run["status"]) == "cancel_requested":
        connection.execute(
            """
            UPDATE batch_items SET status = 'cancelled', completed_at = ?, updated_at = ?
            WHERE batch_run_id = ? AND status = 'queued'
            """,
            (now, now, batch_id),
        )
        running = int(
            connection.execute(
                "SELECT COUNT(*) FROM batch_items WHERE batch_run_id = ? AND status = 'running'",
                (batch_id,),
            ).fetchone()[0]
        )
        if running == 0:
            connection.execute(
                """
                UPDATE batch_runs SET status = 'cancelled', phase = 'completed',
                    completed_at = ?, updated_at = ? WHERE id = ?
                """,
                (now, now, batch_id),
            )
            _event(connection, batch_id, "cancelled", "completed")
        return

    phase = str(run["phase"])
    active = int(
        connection.execute(
            """
            SELECT COUNT(*) FROM batch_items
            WHERE batch_run_id = ? AND phase = ? AND status IN ('queued', 'running')
            """,
            (batch_id, phase),
        ).fetchone()[0]
    )
    if active:
        return

    phases = _phase_order(
        str(run["mode"]),
        json.loads(str(run["config_json"] or "{}")),
    )
    current_index = phases.index(phase)
    if current_index + 1 < len(phases):
        next_phase = phases[current_index + 1]
        if phase == "sheet_map":
            connection.execute(
                """
                UPDATE batch_items
                SET status = 'skipped_dependency', error_code = 'SHEET_MAP_UNAVAILABLE',
                    error_message = 'O Sheet Map desta folha nao foi concluido.',
                    completed_at = ?, updated_at = ?
                WHERE batch_run_id = ? AND phase IN ('deterministic_audit', 'visual_audit')
                  AND status = 'queued'
                  AND sheet_id IN (
                      SELECT sheet_id FROM batch_items
                      WHERE batch_run_id = ? AND phase = 'sheet_map'
                        AND status != 'completed'
                  )
                """,
                (now, now, batch_id, batch_id),
            )
        connection.execute(
            "UPDATE batch_runs SET phase = ?, updated_at = ? WHERE id = ?",
            (next_phase, now, batch_id),
        )
        _event(connection, batch_id, "phase_changed", next_phase, {"from": phase})
        _advance_run(connection, batch_id)
        return

    errors = int(
        connection.execute(
            """
            SELECT COUNT(*) FROM batch_items
            WHERE batch_run_id = ? AND status IN ('failed', 'skipped_dependency', 'manual_retry_required')
            """,
            (batch_id,),
        ).fetchone()[0]
    )
    status = "completed_with_errors" if errors else "completed"
    connection.execute(
        """
        UPDATE batch_runs SET status = ?, phase = 'completed', completed_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (status, now, now, batch_id),
    )
    _event(connection, batch_id, "completed", "completed", {"errors": errors})


def claim_next_item(settings: Settings) -> dict[str, object] | None:
    with transaction(settings) as connection:
        connection.execute("BEGIN IMMEDIATE")
        running_items = int(
            connection.execute(
                "SELECT COUNT(*) FROM batch_items WHERE status = 'running'"
            ).fetchone()[0]
        )
        if running_items:
            return None
        runs = connection.execute(
            """
            SELECT id FROM batch_runs
            WHERE status IN ('queued', 'running', 'cancel_requested')
            ORDER BY created_at, id
            """
        ).fetchall()
        for run_row in runs:
            batch_id = str(run_row["id"])
            _advance_run(connection, batch_id)
            run = connection.execute(
                "SELECT * FROM batch_runs WHERE id = ?", (batch_id,)
            ).fetchone()
            if run is None or str(run["status"]) not in {"queued", "running"}:
                continue
            item = connection.execute(
                """
                SELECT * FROM batch_items
                WHERE batch_run_id = ? AND phase = ? AND status = 'queued'
                ORDER BY sequence LIMIT 1
                """,
                (batch_id, str(run["phase"])),
            ).fetchone()
            if item is None:
                continue
            token = str(uuid4())
            now = _now()
            updated = connection.execute(
                """
                UPDATE batch_items
                SET status = 'running', run_token = ?, attempt_count = attempt_count + 1,
                    started_at = COALESCE(started_at, ?), updated_at = ?,
                    error_code = NULL, error_message = NULL
                WHERE id = ? AND status = 'queued'
                """,
                (token, now, now, str(item["id"])),
            )
            if updated.rowcount != 1:
                continue
            if str(run["status"]) == "queued":
                connection.execute(
                    """
                    UPDATE batch_runs SET status = 'running', started_at = COALESCE(started_at, ?),
                        updated_at = ? WHERE id = ?
                    """,
                    (now, now, batch_id),
                )
                _event(connection, batch_id, "started", str(run["phase"]))
            claimed = connection.execute(
                "SELECT * FROM batch_items WHERE id = ?", (str(item["id"]),)
            ).fetchone()
            result = dict(claimed)
            result["run_token"] = token
            result["batch"] = _run_dict(
                connection.execute("SELECT * FROM batch_runs WHERE id = ?", (batch_id,)).fetchone()
            )
            return result
    return None


def complete_item(
    item_id: str,
    run_token: str,
    settings: Settings,
    *,
    operation_id: str | None = None,
) -> None:
    now = _now()
    with transaction(settings) as connection:
        connection.execute("BEGIN IMMEDIATE")
        item = connection.execute(
            "SELECT batch_run_id FROM batch_items WHERE id = ?", (item_id,)
        ).fetchone()
        updated = connection.execute(
            """
            UPDATE batch_items SET status = 'completed', operation_id = COALESCE(?, operation_id),
                run_token = NULL, completed_at = ?, updated_at = ?
            WHERE id = ? AND status = 'running' AND run_token = ?
            """,
            (operation_id, now, now, item_id, run_token),
        )
        if item is None or updated.rowcount != 1:
            raise TrussError(
                code="BATCH_CLAIM_LOST",
                message="A posse da etapa do lote mudou durante o processamento.",
                action="Atualize o lote antes de continuar.",
                status_code=409,
            )
        _advance_run(connection, str(item["batch_run_id"]))


def fail_item(
    item_id: str,
    run_token: str,
    settings: Settings,
    *,
    code: str,
    message: str,
    manual_retry: bool = False,
    operation_id: str | None = None,
) -> None:
    now = _now()
    status = "manual_retry_required" if manual_retry else "failed"
    with transaction(settings) as connection:
        connection.execute("BEGIN IMMEDIATE")
        item = connection.execute(
            "SELECT batch_run_id FROM batch_items WHERE id = ?", (item_id,)
        ).fetchone()
        updated = connection.execute(
            """
            UPDATE batch_items SET status = ?, operation_id = COALESCE(?, operation_id),
                run_token = NULL, error_code = ?, error_message = ?, completed_at = ?, updated_at = ?
            WHERE id = ? AND status = 'running' AND run_token = ?
            """,
            (status, operation_id, code, message, now, now, item_id, run_token),
        )
        if item is not None and updated.rowcount == 1:
            _advance_run(connection, str(item["batch_run_id"]))


def requeue_transient_item(
    item_id: str,
    run_token: str,
    settings: Settings,
    *,
    code: str,
    message: str,
) -> bool:
    """Schedule the single automatic retry allowed for a typed local failure."""
    now = _now()
    with transaction(settings) as connection:
        connection.execute("BEGIN IMMEDIATE")
        item = connection.execute(
            """
            SELECT batch_run_id, phase, attempt_count
            FROM batch_items WHERE id = ?
            """,
            (item_id,),
        ).fetchone()
        if (
            item is None
            or str(item["phase"]) == "visual_audit"
            or int(item["attempt_count"]) >= 2
        ):
            return False
        updated = connection.execute(
            """
            UPDATE batch_items
            SET status = 'queued', run_token = NULL, error_code = ?, error_message = ?,
                completed_at = NULL, updated_at = ?
            WHERE id = ? AND status = 'running' AND run_token = ?
            """,
            (code, message, now, item_id, run_token),
        )
        if updated.rowcount != 1:
            return False
        batch_id = str(item["batch_run_id"])
        _event(
            connection,
            batch_id,
            "item_retry_scheduled",
            str(item["phase"]),
            {"item_id": item_id, "error_code": code, "attempt": 2},
        )
        return True


def request_cancel(batch_run_id: str, settings: Settings) -> dict[str, object]:
    now = _now()
    with transaction(settings) as connection:
        connection.execute("BEGIN IMMEDIATE")
        run = connection.execute(
            "SELECT status, phase FROM batch_runs WHERE id = ?", (batch_run_id,)
        ).fetchone()
        if run is None:
            raise TrussError(
                code="BATCH_NOT_FOUND",
                message="O lote local nao foi encontrado.",
                action="Atualize a revisao ativa.",
                status_code=404,
            )
        if str(run["status"]) not in {"completed", "completed_with_errors", "cancelled"}:
            connection.execute(
                """
                UPDATE batch_runs SET status = 'cancel_requested', cancel_requested_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, now, batch_run_id),
            )
            _event(connection, batch_run_id, "cancel_requested", str(run["phase"]))
            _advance_run(connection, batch_run_id)
    return get_batch_run(batch_run_id, settings)


def retry_failures(batch_run_id: str, settings: Settings) -> dict[str, object]:
    now = _now()
    with transaction(settings) as connection:
        connection.execute("BEGIN IMMEDIATE")
        run = connection.execute(
            "SELECT * FROM batch_runs WHERE id = ?", (batch_run_id,)
        ).fetchone()
        if run is None:
            raise TrussError(
                code="BATCH_NOT_FOUND",
                message="O lote local nao foi encontrado.",
                action="Atualize a revisao ativa.",
                status_code=404,
            )
        if str(run["status"]) not in {"interrupted", "completed_with_errors"}:
            raise TrussError(
                code="BATCH_NOT_RETRYABLE",
                message="Este lote nao esta em um estado que aceite retomada.",
                action="Atualize o lote e revise seu estado atual.",
                status_code=409,
            )
        failed = connection.execute(
            """
            SELECT phase FROM batch_items
            WHERE batch_run_id = ? AND status = 'failed'
            ORDER BY CASE phase WHEN 'sheet_map' THEN 0 ELSE 1 END, sequence LIMIT 1
            """,
            (batch_run_id,),
        ).fetchone()
        if failed is None:
            raise TrussError(
                code="BATCH_NO_SAFE_FAILURES",
                message="O lote nao possui falhas locais seguras para repetir.",
                action="Falhas visuais exigem uma nova confirmacao explicita.",
                status_code=409,
            )
        phase = str(failed["phase"])
        connection.execute(
            """
            UPDATE batch_items SET status = 'queued', completed_at = NULL, updated_at = ?
            WHERE batch_run_id = ? AND status = 'failed' AND phase = ?
            """,
            (now, batch_run_id, phase),
        )
        if phase == "sheet_map":
            connection.execute(
                """
                UPDATE batch_items SET status = 'queued', completed_at = NULL,
                    error_code = NULL, error_message = NULL, updated_at = ?
                WHERE batch_run_id = ? AND phase IN ('deterministic_audit', 'visual_audit')
                  AND status = 'skipped_dependency'
                """,
                (now, batch_run_id),
            )
            connection.execute(
                """
                UPDATE batch_items SET status = 'queued', completed_at = NULL,
                    error_code = NULL, error_message = NULL, updated_at = ?
                WHERE batch_run_id = ? AND phase = 'deterministic_audit'
                  AND status = 'completed'
                """,
                (now, batch_run_id),
            )
        connection.execute(
            """
            UPDATE batch_runs SET status = 'queued', phase = ?, completed_at = NULL,
                cancel_requested_at = NULL, updated_at = ? WHERE id = ?
            """,
            (phase, now, batch_run_id),
        )
        _event(connection, batch_run_id, "resumed", phase, {"retry_failures": True})
    return get_batch_run(batch_run_id, settings)


def mark_running_batches_interrupted(settings: Settings) -> int:
    now = _now()
    with transaction(settings) as connection:
        connection.execute("BEGIN IMMEDIATE")
        runs = connection.execute(
            """
            SELECT id, phase, status FROM batch_runs
            WHERE status IN ('running', 'cancel_requested')
            """
        ).fetchall()
        for run in runs:
            batch_id = str(run["id"])
            connection.execute(
                """
                UPDATE batch_items SET status = 'failed', run_token = NULL,
                    error_code = 'WORKER_INTERRUPTED',
                    error_message = 'O worker terminou antes de concluir esta etapa.',
                    completed_at = ?, updated_at = ?
                WHERE batch_run_id = ? AND status = 'running'
                """,
                (now, now, batch_id),
            )
            _event(connection, batch_id, "interrupted", str(run["phase"]))
            if str(run["status"]) == "cancel_requested":
                _advance_run(connection, batch_id)
            else:
                connection.execute(
                    "UPDATE batch_runs SET status = 'interrupted', updated_at = ? WHERE id = ?",
                    (now, batch_id),
                )
    return len(runs)
