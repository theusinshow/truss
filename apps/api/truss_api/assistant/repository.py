import json
from datetime import UTC, datetime
from sqlite3 import IntegrityError, Row
from uuid import uuid4

from truss_api.ai.provider import ProviderResponse
from truss_api.assistant.models import ChatRequest, MessageFeedbackCreate, MemoryCreate
from truss_api.core.settings import Settings
from truss_api.db.connection import transaction
from truss_api.documents.repository import SheetNotFoundError

TECHNICAL_CONTEXT_VERSION = "sheet-chat-v0.2"


class MemoryNotFoundError(Exception):
    pass


class DuplicateMemoryError(Exception):
    pass


class ConversationNotFoundError(Exception):
    pass


class ChatMessageNotFoundError(Exception):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_dict(row: Row) -> dict[str, object]:
    return dict(row)


def _conversation_title(message: str) -> str:
    title = " ".join(message.strip().split())
    if len(title) > 76:
        return f"{title[:73]}..."
    return title or "Nova conversa"


def _safe_json_list(value: object) -> list[object]:
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return []

    return parsed if isinstance(parsed, list) else []


def _finding_certainty(finding: dict[str, object]) -> str:
    status = str(finding.get("status", "pending"))
    confidence = float(finding.get("confidence", 0) or 0)

    if status == "confirmed":
        return "confirmed_by_human"
    if status == "rejected":
        return "rejected_by_human"
    if confidence >= 0.75:
        return "hypothesis_high_confidence"
    if confidence >= 0.45:
        return "hypothesis_medium_confidence"
    return "hypothesis_low_confidence"


def _normalize_finding_for_context(finding: dict[str, object]) -> dict[str, object]:
    evidence = _safe_json_list(finding.get("evidence_json", "[]"))
    return {
        "id": finding["id"],
        "category": finding["category"],
        "type": finding["type"],
        "description": finding["description"],
        "severity": finding["severity"],
        "confidence": finding["confidence"],
        "certainty": _finding_certainty(finding),
        "status": finding["status"],
        "origin": finding["origin"],
        "rejection_reason": finding.get("rejection_reason"),
        "bbox": {
            "x0": finding["x0"],
            "y0": finding["y0"],
            "x1": finding["x1"],
            "y1": finding["y1"],
            "unit": "pt",
        },
        "evidence": evidence[:4],
    }


def _selected_finding_ids(context_items: list[dict[str, object]]) -> list[str]:
    selected: list[str] = []
    for item in context_items:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        finding_id = metadata.get("findingId") if isinstance(metadata, dict) else None
        if isinstance(finding_id, str) and finding_id:
            selected.append(finding_id)
            continue

        item_id = str(item.get("id", ""))
        if item_id.startswith("finding:"):
            selected.append(item_id.removeprefix("finding:"))

    return list(dict.fromkeys(selected))


def build_technical_context(context: dict[str, object]) -> dict[str, object]:
    findings = [
        _normalize_finding_for_context(finding)
        for finding in context.get("recent_findings", [])
        if isinstance(finding, dict)
    ]
    context_items = [
        item for item in context.get("ui_context_items", [])
        if isinstance(item, dict)
    ]
    selected_ids = _selected_finding_ids(context_items)
    selected_findings = [finding for finding in findings if str(finding["id"]) in selected_ids]

    status_counts = {
        "pending": sum(1 for finding in findings if finding["status"] == "pending"),
        "confirmed": sum(1 for finding in findings if finding["status"] == "confirmed"),
        "rejected": sum(1 for finding in findings if finding["status"] == "rejected"),
    }
    severity_counts = {
        severity: sum(1 for finding in findings if finding["severity"] == severity)
        for severity in ("critical", "high", "medium", "low")
    }

    native_text_excerpt = str(context.get("native_text_excerpt", "") or "")
    memories = [
        {
            "scope": memory.get("scope"),
            "key": memory.get("key"),
            "text": memory.get("text"),
        }
        for memory in context.get("memories", [])
        if isinstance(memory, dict)
    ]

    return {
        "version": TECHNICAL_CONTEXT_VERSION,
        "sheet": {
            "id": context.get("id"),
            "label": context.get("sheet_label"),
            "width_pt": context.get("width_pt"),
            "height_pt": context.get("height_pt"),
            "rotation": context.get("rotation"),
        },
        "summary": {
            "total_findings": context.get("findings_count", len(findings)),
            "status_counts": status_counts,
            "severity_counts": severity_counts,
            "native_text_available": bool(native_text_excerpt.strip()),
            "memory_count": context.get("memory_count", len(memories)),
            "conversation_history_count": context.get("conversation_history_count", 0),
        },
        "focus": {
            "selected_finding_ids": selected_ids,
            "selected_findings": selected_findings,
            "context_items": [
                {
                    "kind": item.get("kind"),
                    "label": item.get("label"),
                    "value": item.get("value"),
                    "metadata": item.get("metadata", {}),
                }
                for item in context_items
            ],
        },
        "findings": findings[:10],
        "native_text": {
            "excerpt": native_text_excerpt[:3000],
            "is_truncated": len(native_text_excerpt) > 3000,
        },
        "memories": memories[:10],
        "answer_policy": {
            "pdf_is_primary": True,
            "severity_is_not_certainty": True,
            "must_separate_hypothesis_from_confirmed_error": True,
            "must_not_approve_issue": True,
            "must_say_unavailable_when_context_is_missing": True,
            "coordinate_unit": "pt",
        },
    }


def sheet_context(sheet_id: str, settings: Settings) -> dict[str, object]:
    with transaction(settings) as connection:
        sheet = connection.execute(
            """
            SELECT
                s.id,
                s.label,
                s.project_id,
                s.revision_id,
                s.width_pt,
                s.height_pt,
                s.rotation,
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

        findings = connection.execute(
            """
            SELECT
                id,
                category,
                type,
                description,
                severity,
                confidence,
                x0,
                y0,
                x1,
                y1,
                status,
                origin,
                rejection_reason,
                evidence_json
            FROM findings
            WHERE sheet_id = ?
            ORDER BY
                CASE severity
                    WHEN 'critical' THEN 0
                    WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2
                    WHEN 'low' THEN 3
                    ELSE 4
                END,
                created_at DESC
            LIMIT 12
            """,
            (sheet_id,),
        ).fetchall()

        text_blocks = connection.execute(
            """
            SELECT text
            FROM text_blocks
            WHERE sheet_id = ?
            ORDER BY block_index ASC
            LIMIT 80
            """,
            (sheet_id,),
        ).fetchall()

        memories = connection.execute(
            """
            SELECT scope, key, text
            FROM memories
            ORDER BY created_at DESC, key ASC
            LIMIT 20
            """
        ).fetchall()

    if sheet is None:
        raise SheetNotFoundError(sheet_id)

    data = _row_to_dict(sheet)
    data["sheet_label"] = data.pop("label")
    native_text = "\n".join(str(row["text"]).strip() for row in text_blocks if str(row["text"]).strip())
    data["native_text_excerpt"] = native_text[:6000]
    data["recent_findings"] = [_row_to_dict(row) for row in findings]
    data["memories"] = [_row_to_dict(row) for row in memories]
    return data


def _get_or_create_conversation(
    *,
    sheet_id: str,
    request: ChatRequest,
    context: dict[str, object],
    connection: object,
    now: str,
) -> str:
    if request.conversation_id:
        row = connection.execute(
            """
            SELECT id
            FROM chat_conversations
            WHERE id = ? AND sheet_id = ?
            """,
            (request.conversation_id, sheet_id),
        ).fetchone()

        if row is None:
            raise ConversationNotFoundError(request.conversation_id)

        connection.execute(
            """
            UPDATE chat_conversations
            SET updated_at = ?
            WHERE id = ?
            """,
            (now, request.conversation_id),
        )
        return str(request.conversation_id)

    conversation_id = str(uuid4())
    connection.execute(
        """
        INSERT INTO chat_conversations (
            id,
            sheet_id,
            project_id,
            revision_id,
            title,
            status,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            conversation_id,
            sheet_id,
            context["project_id"],
            context["revision_id"],
            _conversation_title(request.message),
            "active",
            now,
            now,
        ),
    )
    return conversation_id


def _persist_context_items(
    *,
    connection: object,
    message_id: str,
    request: ChatRequest,
    now: str,
) -> None:
    for index, item in enumerate(request.context_items):
        connection.execute(
            """
            INSERT INTO chat_message_context_items (
                id,
                message_id,
                item_order,
                source_id,
                kind,
                label,
                value,
                metadata_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                message_id,
                index,
                item.id,
                item.kind,
                item.label,
                item.value,
                json.dumps(item.metadata, ensure_ascii=False, default=str),
                now,
            ),
        )


def persist_chat_turn(
    *,
    sheet_id: str,
    request: ChatRequest,
    response: ProviderResponse,
    settings: Settings,
) -> dict[str, str]:
    context = sheet_context(sheet_id, settings)
    now = _now()

    with transaction(settings) as connection:
        conversation_id = _get_or_create_conversation(
            sheet_id=sheet_id,
            request=request,
            context=context,
            connection=connection,
            now=now,
        )
        user_message_id = str(uuid4())
        assistant_message_id = str(uuid4())

        for role, content, message_id, provider, model in (
            ("user", request.message, user_message_id, None, None),
            ("assistant", response.answer, assistant_message_id, response.provider, response.model),
        ):
            connection.execute(
                """
                INSERT INTO chat_messages (
                    id,
                    conversation_id,
                    sheet_id,
                    project_id,
                    revision_id,
                    role,
                    content,
                    status,
                    provider,
                    model,
                    parent_message_id,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    conversation_id,
                    sheet_id,
                    context["project_id"],
                    context["revision_id"],
                    role,
                    content,
                    "completed",
                    provider,
                    model,
                    user_message_id if role == "assistant" else None,
                    now,
                    now,
                ),
            )

        _persist_context_items(
            connection=connection,
            message_id=user_message_id,
            request=request,
            now=now,
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

    return {
        "conversation_id": conversation_id,
        "user_message_id": user_message_id,
        "assistant_message_id": assistant_message_id,
    }


def ensure_conversation_for_sheet(conversation_id: str, sheet_id: str, settings: Settings) -> None:
    with transaction(settings) as connection:
        row = connection.execute(
            """
            SELECT id
            FROM chat_conversations
            WHERE id = ? AND sheet_id = ?
            """,
            (conversation_id, sheet_id),
        ).fetchone()

    if row is None:
        raise ConversationNotFoundError(conversation_id)


def conversation_history_context(
    conversation_id: str,
    sheet_id: str,
    settings: Settings,
    *,
    limit: int = 12,
) -> list[dict[str, object]]:
    with transaction(settings) as connection:
        conversation = connection.execute(
            """
            SELECT id
            FROM chat_conversations
            WHERE id = ? AND sheet_id = ?
            """,
            (conversation_id, sheet_id),
        ).fetchone()
        if conversation is None:
            raise ConversationNotFoundError(conversation_id)

        rows = connection.execute(
            """
            SELECT
                id,
                role,
                content,
                provider,
                model,
                created_at
            FROM chat_messages
            WHERE conversation_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (conversation_id, limit),
        ).fetchall()

    history: list[dict[str, object]] = []
    for row in reversed(rows):
        content = str(row["content"])
        history.append(
            {
                "id": row["id"],
                "role": row["role"],
                "content": content[:1200],
                "provider": row["provider"],
                "model": row["model"],
                "created_at": row["created_at"],
            }
        )

    return history


def list_conversations(sheet_id: str, settings: Settings) -> list[dict[str, object]]:
    with transaction(settings) as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                sheet_id,
                project_id,
                revision_id,
                title,
                status,
                created_at,
                updated_at
            FROM chat_conversations
            WHERE sheet_id = ?
            ORDER BY updated_at DESC
            """,
            (sheet_id,),
        ).fetchall()

    return [_row_to_dict(row) for row in rows]


def list_conversation_messages(conversation_id: str, settings: Settings) -> list[dict[str, object]]:
    with transaction(settings) as connection:
        messages = connection.execute(
            """
            SELECT
                id,
                conversation_id,
                sheet_id,
                project_id,
                revision_id,
                role,
                content,
                status,
                provider,
                model,
                parent_message_id,
                created_at,
                CASE WHEN updated_at = '' THEN created_at ELSE updated_at END AS updated_at
            FROM chat_messages
            WHERE conversation_id = ?
            ORDER BY created_at ASC
            """,
            (conversation_id,),
        ).fetchall()

        if not messages:
            conversation = connection.execute(
                "SELECT id FROM chat_conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if conversation is None:
                raise ConversationNotFoundError(conversation_id)

        context_rows = connection.execute(
            """
            SELECT
                message_id,
                id,
                source_id,
                kind,
                label,
                value,
                metadata_json
            FROM chat_message_context_items
            WHERE message_id IN (
                SELECT id FROM chat_messages WHERE conversation_id = ?
            )
            ORDER BY item_order ASC
            """,
            (conversation_id,),
        ).fetchall()

    contexts_by_message: dict[str, list[dict[str, object]]] = {}
    for row in context_rows:
        message_id = str(row["message_id"])
        contexts_by_message.setdefault(message_id, []).append(
            {
                "id": row["source_id"] or row["id"],
                "kind": row["kind"],
                "label": row["label"],
                "value": row["value"],
                "metadata": json.loads(str(row["metadata_json"])),
            }
        )

    result = []
    for row in messages:
        data = _row_to_dict(row)
        data["context_items"] = contexts_by_message.get(str(row["id"]), [])
        result.append(data)

    return result


def create_message_feedback(message_id: str, payload: MessageFeedbackCreate, settings: Settings) -> dict[str, object]:
    feedback_id = str(uuid4())
    created_at = _now()

    with transaction(settings) as connection:
        message = connection.execute(
            "SELECT id FROM chat_messages WHERE id = ?",
            (message_id,),
        ).fetchone()
        if message is None:
            raise ChatMessageNotFoundError(message_id)

        connection.execute(
            """
            INSERT INTO chat_message_feedback (
                id,
                message_id,
                feedback,
                reason,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                feedback_id,
                message_id,
                payload.feedback,
                payload.reason.strip(),
                created_at,
            ),
        )

        row = connection.execute(
            """
            SELECT id, message_id, feedback, reason, created_at
            FROM chat_message_feedback
            WHERE id = ?
            """,
            (feedback_id,),
        ).fetchone()

    return _row_to_dict(row)


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
