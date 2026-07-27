from datetime import UTC, datetime
from sqlite3 import IntegrityError, Row
from uuid import uuid4

from truss_api.ai.provider import ProviderResponse
from truss_api.assistant.models import ChatRequest, MemoryCreate
from truss_api.core.settings import Settings
from truss_api.db.connection import transaction
from truss_api.documents.repository import SheetNotFoundError


class MemoryNotFoundError(Exception):
    pass


class DuplicateMemoryError(Exception):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_dict(row: Row) -> dict[str, object]:
    return dict(row)


def sheet_context(sheet_id: str, settings: Settings) -> dict[str, object]:
    with transaction(settings) as connection:
        sheet = connection.execute(
            """
            SELECT
                s.id,
                s.label,
                s.project_id,
                s.revision_id,
                (
                    SELECT COUNT(*)
                    FROM findings f
                    WHERE f.sheet_id = s.id
                ) AS findings_count,
                (
                    SELECT COUNT(*)
                    FROM findings f
                    WHERE f.sheet_id = s.id AND f.status = 'pending'
                ) AS pending_findings_count,
                (
                    SELECT COUNT(*)
                    FROM memories m
                ) AS memory_count
            FROM sheets s
            WHERE s.id = ?
            """,
            (sheet_id,),
        ).fetchone()

    if sheet is None:
        raise SheetNotFoundError(sheet_id)

    data = _row_to_dict(sheet)
    data["sheet_label"] = data.pop("label")
    return data


def persist_chat_turn(
    *,
    sheet_id: str,
    request: ChatRequest,
    response: ProviderResponse,
    settings: Settings,
) -> None:
    context = sheet_context(sheet_id, settings)
    now = _now()

    with transaction(settings) as connection:
        for role, content in (("user", request.message), ("assistant", response.answer)):
            connection.execute(
                """
                INSERT INTO chat_messages (
                    id,
                    sheet_id,
                    project_id,
                    revision_id,
                    role,
                    content,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    sheet_id,
                    context["project_id"],
                    context["revision_id"],
                    role,
                    content,
                    now,
                ),
            )

        connection.execute(
            """
            INSERT INTO ai_usage_events (
                id,
                provider,
                model,
                operation,
                project_id,
                revision_id,
                sheet_id,
                input_tokens,
                output_tokens,
                estimated_cost_usd,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                response.provider,
                response.model,
                "sheet_chat",
                context["project_id"],
                context["revision_id"],
                sheet_id,
                response.input_tokens,
                response.output_tokens,
                response.estimated_cost_usd,
                now,
            ),
        )


def list_memories(settings: Settings) -> list[dict[str, object]]:
    with transaction(settings) as connection:
        rows = connection.execute(
            """
            SELECT id, scope, key, text, created_at
            FROM memories
            ORDER BY created_at DESC, key ASC
            """
        ).fetchall()

    return [_row_to_dict(row) for row in rows]


def create_memory(payload: MemoryCreate, settings: Settings) -> dict[str, object]:
    memory_id = str(uuid4())
    created_at = _now()

    with transaction(settings) as connection:
        try:
            connection.execute(
                """
                INSERT INTO memories (id, scope, key, text, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    payload.scope.strip(),
                    payload.key.strip(),
                    payload.text.strip(),
                    created_at,
                ),
            )
        except IntegrityError as error:
            if "UNIQUE" in str(error).upper():
                raise DuplicateMemoryError(payload.key) from error
            raise

        row = connection.execute(
            "SELECT id, scope, key, text, created_at FROM memories WHERE id = ?",
            (memory_id,),
        ).fetchone()

    return _row_to_dict(row)


def delete_memory(memory_id: str, settings: Settings) -> None:
    with transaction(settings) as connection:
        cursor = connection.execute("DELETE FROM memories WHERE id = ?", (memory_id,))

    if cursor.rowcount == 0:
        raise MemoryNotFoundError(memory_id)


def list_usage_events(settings: Settings) -> list[dict[str, object]]:
    with transaction(settings) as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                provider,
                model,
                operation,
                project_id,
                revision_id,
                sheet_id,
                input_tokens,
                output_tokens,
                estimated_cost_usd,
                created_at
            FROM ai_usage_events
            ORDER BY created_at DESC
            """
        ).fetchall()

    return [_row_to_dict(row) for row in rows]
