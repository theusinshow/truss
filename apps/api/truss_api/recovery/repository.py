from datetime import UTC, datetime
import json
from sqlite3 import Row
from uuid import uuid4

from truss_api.core.settings import Settings
from truss_api.db.connection import transaction
from truss_api.recovery.errors import TrussError


ATTENTION_STATUSES = ("failed", "interrupted", "manual_retry_required")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _decode(row: Row) -> dict[str, object]:
    value = dict(row)
    value["payload"] = json.loads(str(value.pop("payload_json") or "{}"))
    raw_error = value.pop("error_context_json")
    value["error_context"] = json.loads(str(raw_error)) if raw_error else None
    value["resumable"] = (
        value["status"] in {"failed", "interrupted"}
        and value["kind"] != "vision_audit"
        and not (
            value["kind"] == "document_import"
            and value["checkpoint"] == "validated"
        )
    )
    return value


def _event(
    connection,
    *,
    operation_id: str,
    event_kind: str,
    checkpoint: str,
    detail: dict[str, object] | None = None,
) -> None:
    row = connection.execute(
        "SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence FROM processing_operation_events WHERE operation_id = ?",
        (operation_id,),
    ).fetchone()
    connection.execute(
        """
        INSERT INTO processing_operation_events (
            id, operation_id, sequence, event_kind, checkpoint, detail_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid4()),
            operation_id,
            int(row["sequence"]),
            event_kind,
            checkpoint,
            json.dumps(detail or {}, ensure_ascii=False),
            _now(),
        ),
    )


def get_operation(operation_id: str, settings: Settings) -> dict[str, object]:
    with transaction(settings) as connection:
        row = connection.execute(
            "SELECT * FROM processing_operations WHERE id = ?",
            (operation_id,),
        ).fetchone()
    if row is None:
        raise TrussError(
            code="OPERATION_NOT_FOUND",
            message="A operacao local nao foi encontrada.",
            action="Atualize o estado operacional.",
            status_code=404,
        )
    return _decode(row)


def find_by_identity(identity_key: str, settings: Settings) -> dict[str, object] | None:
    with transaction(settings) as connection:
        row = connection.execute(
            "SELECT * FROM processing_operations WHERE identity_key = ?",
            (identity_key,),
        ).fetchone()
    return _decode(row) if row is not None else None


def create_operation(
    *,
    identity_key: str,
    kind: str,
    input_hash: str,
    pipeline_version: str,
    checkpoint: str,
    settings: Settings,
    project_id: str | None = None,
    revision_id: str | None = None,
    document_id: str | None = None,
    sheet_id: str | None = None,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    operation_id = str(uuid4())
    now = _now()
    with transaction(settings) as connection:
        inserted = connection.execute(
            """
            INSERT OR IGNORE INTO processing_operations (
                id, identity_key, kind, project_id, revision_id, document_id, sheet_id,
                input_hash, pipeline_version, status, checkpoint, attempt_count,
                payload_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, 0, ?, ?, ?)
            """,
            (
                operation_id,
                identity_key,
                kind,
                project_id,
                revision_id,
                document_id,
                sheet_id,
                input_hash,
                pipeline_version,
                checkpoint,
                json.dumps(payload or {}, ensure_ascii=False),
                now,
                now,
            ),
        )
        if inserted.rowcount == 1:
            _event(
                connection,
                operation_id=operation_id,
                event_kind="created",
                checkpoint=checkpoint,
            )
    operation = find_by_identity(identity_key, settings)
    if operation is None:
        raise RuntimeError("operation identity was not persisted")
    return operation


def claim_operation(operation_id: str, settings: Settings) -> dict[str, object]:
    now = _now()
    with transaction(settings) as connection:
        current = connection.execute(
            "SELECT status, checkpoint FROM processing_operations WHERE id = ?",
            (operation_id,),
        ).fetchone()
        if current is None:
            raise TrussError(
                code="OPERATION_NOT_FOUND",
                message="A operacao local nao foi encontrada.",
                action="Atualize o estado operacional.",
                status_code=404,
            )
        if str(current["status"]) == "running":
            raise TrussError(
                code="OPERATION_ALREADY_RUNNING",
                message="Esta operacao ja esta em execucao.",
                action="Aguarde a conclusao antes de tentar novamente.",
                status_code=409,
                operation_id=operation_id,
            )
        if str(current["status"]) == "completed":
            pass
        else:
            updated = connection.execute(
                """
                UPDATE processing_operations
                SET status = 'running', attempt_count = attempt_count + 1,
                    started_at = COALESCE(started_at, ?), heartbeat_at = ?, updated_at = ?,
                    error_code = NULL, error_message = NULL, error_context_json = NULL
                WHERE id = ? AND status IN ('pending', 'failed', 'interrupted')
                """,
                (now, now, now, operation_id),
            )
            if updated.rowcount != 1:
                raise TrussError(
                    code="EXTERNAL_RETRY_REQUIRES_CONFIRMATION",
                    message="Esta operacao nao pode ser repetida automaticamente.",
                    action="Inicie novamente a analise externa se aceitar uma nova chamada.",
                    status_code=409,
                    operation_id=operation_id,
                )
            _event(
                connection,
                operation_id=operation_id,
                event_kind=(
                    "started" if str(current["status"]) == "pending" else "resumed"
                ),
                checkpoint=str(current["checkpoint"]),
            )
    return get_operation(operation_id, settings)


def save_checkpoint(
    operation_id: str,
    checkpoint: str,
    settings: Settings,
    *,
    payload: dict[str, object] | None = None,
    document_id: str | None = None,
) -> dict[str, object]:
    now = _now()
    with transaction(settings) as connection:
        current = connection.execute(
            "SELECT payload_json FROM processing_operations WHERE id = ? AND status = 'running'",
            (operation_id,),
        ).fetchone()
        if current is None:
            raise TrussError(
                code="OPERATION_STATE_CONFLICT",
                message="A operacao mudou de estado durante o processamento.",
                action="Atualize o estado antes de continuar.",
                status_code=409,
                operation_id=operation_id,
            )
        merged = json.loads(str(current["payload_json"] or "{}"))
        merged.update(payload or {})
        connection.execute(
            """
            UPDATE processing_operations
            SET checkpoint = ?, payload_json = ?, document_id = COALESCE(?, document_id),
                heartbeat_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (checkpoint, json.dumps(merged, ensure_ascii=False), document_id, now, now, operation_id),
        )
        _event(
            connection,
            operation_id=operation_id,
            event_kind="checkpoint",
            checkpoint=checkpoint,
        )
    return get_operation(operation_id, settings)


def complete_operation(
    operation_id: str,
    settings: Settings,
    *,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    save_checkpoint(operation_id, "completed", settings, payload=payload)
    now = _now()
    with transaction(settings) as connection:
        connection.execute(
            """
            UPDATE processing_operations
            SET status = 'completed', completed_at = ?, heartbeat_at = ?, updated_at = ?
            WHERE id = ? AND status = 'running'
            """,
            (now, now, now, operation_id),
        )
        _event(
            connection,
            operation_id=operation_id,
            event_kind="completed",
            checkpoint="completed",
        )
    return get_operation(operation_id, settings)


def fail_operation(
    operation_id: str,
    settings: Settings,
    *,
    code: str,
    message: str,
    retryable: bool,
    manual_retry: bool = False,
) -> dict[str, object]:
    status = "manual_retry_required" if manual_retry else "interrupted" if retryable else "failed"
    now = _now()
    with transaction(settings) as connection:
        current = connection.execute(
            "SELECT checkpoint FROM processing_operations WHERE id = ?",
            (operation_id,),
        ).fetchone()
        if current is None:
            return {}
        connection.execute(
            """
            UPDATE processing_operations
            SET status = ?, error_code = ?, error_message = ?, heartbeat_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, code, message, now, now, operation_id),
        )
        _event(
            connection,
            operation_id=operation_id,
            event_kind="interrupted" if status != "failed" else "failed",
            checkpoint=str(current["checkpoint"]),
            detail={"code": code},
        )
    return get_operation(operation_id, settings)


def mark_running_as_interrupted(settings: Settings) -> int:
    now = _now()
    with transaction(settings) as connection:
        rows = connection.execute(
            "SELECT id, kind, checkpoint FROM processing_operations WHERE status = 'running'"
        ).fetchall()
        for row in rows:
            status = "manual_retry_required" if str(row["kind"]) == "vision_audit" else "interrupted"
            connection.execute(
                """
                UPDATE processing_operations
                SET status = ?, error_code = 'OPERATION_INTERRUPTED',
                    error_message = 'O processo terminou antes da conclusao.', updated_at = ?
                WHERE id = ?
                """,
                (status, now, str(row["id"])),
            )
            _event(
                connection,
                operation_id=str(row["id"]),
                event_kind="interrupted",
                checkpoint=str(row["checkpoint"]),
            )
    return len(rows)


def list_attention_operations(settings: Settings) -> list[dict[str, object]]:
    placeholders = ",".join("?" for _ in ATTENTION_STATUSES)
    with transaction(settings) as connection:
        rows = connection.execute(
            f"SELECT * FROM processing_operations WHERE status IN ({placeholders}) ORDER BY updated_at DESC",
            ATTENTION_STATUSES,
        ).fetchall()
    return [_decode(row) for row in rows]


def list_events(operation_id: str, settings: Settings) -> list[dict[str, object]]:
    with transaction(settings) as connection:
        rows = connection.execute(
            "SELECT * FROM processing_operation_events WHERE operation_id = ? ORDER BY sequence",
            (operation_id,),
        ).fetchall()
    return [dict(row) | {"detail": json.loads(str(row["detail_json"] or "{}"))} for row in rows]
