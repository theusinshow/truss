import json
from dataclasses import asdict
from typing import Iterator

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse

from truss_api.ai.provider import (
    AIProviderConfigError,
    AIProviderUnavailableError,
    ProviderResponse,
    ProviderStreamDelta,
    ProviderStreamResult,
    build_ai_provider,
    get_ai_provider_status,
)
from truss_api.assistant import repository
from truss_api.assistant.models import (
    AIStatus,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    Conversation,
    Memory,
    MemoryCreate,
    MessageFeedback,
    MessageFeedbackCreate,
    UsageEvent,
)
from truss_api.core.settings import Settings, get_settings
from truss_api.documents.repository import SheetNotFoundError


router = APIRouter(tags=["assistant"])


def _ndjson_event(event: str, **payload: object) -> str:
    return json.dumps({"event": event, **payload}, ensure_ascii=False, default=str) + "\n"


def _sheet_chat_context(sheet_id: str, payload: ChatRequest, settings: Settings) -> dict[str, object]:
    context = repository.sheet_context(sheet_id, settings)
    context["ui_context_items"] = [item.model_dump() for item in payload.context_items]

    if payload.conversation_id:
        history = repository.conversation_history_context(payload.conversation_id, sheet_id, settings)
        context["conversation_id"] = payload.conversation_id
        context["conversation_history"] = history
        context["conversation_history_count"] = len(history)
    else:
        context["conversation_history"] = []
        context["conversation_history_count"] = 0

    context["technical_context"] = repository.build_technical_context(context)
    context["technical_context_version"] = repository.TECHNICAL_CONTEXT_VERSION

    return context


@router.get("/ai/status", response_model=AIStatus)
def ai_status(settings: Settings = Depends(get_settings)) -> AIStatus:
    return AIStatus.model_validate(asdict(get_ai_provider_status(settings)))


@router.post("/sheets/{sheet_id}/chat", response_model=ChatResponse)
def chat_with_sheet(
    sheet_id: str,
    payload: ChatRequest,
    settings: Settings = Depends(get_settings),
) -> ChatResponse:
    try:
        provider = build_ai_provider(settings)
    except AIProviderConfigError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI provider is not configured",
        ) from error

    try:
        context = _sheet_chat_context(sheet_id, payload, settings)
        provider_response = provider.respond(user_message=payload.message, context=context)
        persisted = repository.persist_chat_turn(
            sheet_id=sheet_id,
            request=payload,
            response=provider_response,
            settings=settings,
        )
    except SheetNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sheet not found") from error
    except repository.ConversationNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found") from error
    except AIProviderUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=error.public_message,
        ) from error

    return ChatResponse(
        answer=provider_response.answer,
        provider=provider_response.provider,
        model=provider_response.model,
        conversation_id=persisted["conversation_id"],
        user_message_id=persisted["user_message_id"],
        assistant_message_id=persisted["assistant_message_id"],
    )


@router.post("/sheets/{sheet_id}/chat/stream")
def stream_chat_with_sheet(
    sheet_id: str,
    payload: ChatRequest,
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    try:
        provider = build_ai_provider(settings)
        context = _sheet_chat_context(sheet_id, payload, settings)
    except AIProviderConfigError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI provider is not configured",
        ) from error
    except SheetNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sheet not found") from error
    except repository.ConversationNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found") from error

    def events() -> Iterator[str]:
        answer_parts: list[str] = []
        final_response: ProviderResponse | None = None

        yield _ndjson_event("meta", provider=provider.provider, model=provider.model)

        try:
            for provider_event in provider.stream_respond(user_message=payload.message, context=context):
                if isinstance(provider_event, ProviderStreamDelta):
                    answer_parts.append(provider_event.delta)
                    yield _ndjson_event("delta", delta=provider_event.delta)
                elif isinstance(provider_event, ProviderStreamResult):
                    final_response = provider_event.response
        except AIProviderUnavailableError as error:
            yield _ndjson_event("error", detail=error.public_message, provider_code=error.provider_code)
            return

        if final_response is None:
            final_response = ProviderResponse(
                provider=provider.provider,
                model=provider.model,
                answer="".join(answer_parts),
            )

        try:
            persisted = repository.persist_chat_turn(
                sheet_id=sheet_id,
                request=payload,
                response=final_response,
                settings=settings,
            )
        except repository.ConversationNotFoundError:
            yield _ndjson_event("error", detail="Conversation not found")
            return

        yield _ndjson_event(
            "done",
            answer=final_response.answer,
            provider=final_response.provider,
            model=final_response.model,
            conversation_id=persisted["conversation_id"],
            user_message_id=persisted["user_message_id"],
            assistant_message_id=persisted["assistant_message_id"],
        )

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/sheets/{sheet_id}/conversations", response_model=list[Conversation])
def list_sheet_conversations(
    sheet_id: str,
    settings: Settings = Depends(get_settings),
) -> list[dict[str, object]]:
    return repository.list_conversations(sheet_id, settings)


@router.get("/chat/conversations/{conversation_id}/messages", response_model=list[ChatMessage])
def list_chat_messages(
    conversation_id: str,
    settings: Settings = Depends(get_settings),
) -> list[dict[str, object]]:
    try:
        return repository.list_conversation_messages(conversation_id, settings)
    except repository.ConversationNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found") from error


@router.post("/chat/messages/{message_id}/feedback", response_model=MessageFeedback, status_code=status.HTTP_201_CREATED)
def create_message_feedback(
    message_id: str,
    payload: MessageFeedbackCreate,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    try:
        return repository.create_message_feedback(message_id, payload, settings)
    except repository.ChatMessageNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found") from error


@router.get("/memories", response_model=list[Memory])
def list_memories(settings: Settings = Depends(get_settings)) -> list[dict[str, object]]:
    return repository.list_memories(settings)


@router.post("/memories", response_model=Memory, status_code=status.HTTP_201_CREATED)
def create_memory(
    payload: MemoryCreate,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    try:
        return repository.create_memory(payload, settings)
    except repository.DuplicateMemoryError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Memory already exists") from error


@router.delete("/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(memory_id: str, settings: Settings = Depends(get_settings)) -> Response:
    try:
        repository.delete_memory(memory_id, settings)
    except repository.MemoryNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found") from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/usage", response_model=list[UsageEvent])
def list_usage(
    sheet_id: str | None = None,
    settings: Settings = Depends(get_settings),
) -> list[dict[str, object]]:
    return repository.list_usage_events(settings, sheet_id)
