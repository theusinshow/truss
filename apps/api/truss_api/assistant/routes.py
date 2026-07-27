from fastapi import APIRouter, Depends, HTTPException, Response, status

from truss_api.ai.provider import (
    AIProviderConfigError,
    AIProviderUnavailableError,
    build_ai_provider,
)
from truss_api.assistant import repository
from truss_api.assistant.models import ChatRequest, ChatResponse, Memory, MemoryCreate, UsageEvent
from truss_api.core.settings import Settings, get_settings
from truss_api.documents.repository import SheetNotFoundError


router = APIRouter(tags=["assistant"])


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
        context = repository.sheet_context(sheet_id, settings)
        provider_response = provider.respond(user_message=payload.message, context=context)
        repository.persist_chat_turn(
            sheet_id=sheet_id,
            request=payload,
            response=provider_response,
            settings=settings,
        )
    except SheetNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sheet not found") from error
    except AIProviderUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI provider is unavailable",
        ) from error

    return ChatResponse(
        answer=provider_response.answer,
        provider=provider_response.provider,
        model=provider_response.model,
    )


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
def list_usage(settings: Settings = Depends(get_settings)) -> list[dict[str, object]]:
    return repository.list_usage_events(settings)
