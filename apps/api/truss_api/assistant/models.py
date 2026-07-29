from datetime import datetime

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatContextItem(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    kind: Literal["sheet", "document", "selection", "finding", "audit", "page"]
    label: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=500)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=120)
    context_items: list[ChatContextItem] = Field(default_factory=list, max_length=12)


class ChatResponse(BaseModel):
    answer: str
    provider: str
    model: str
    conversation_id: str
    user_message_id: str
    assistant_message_id: str


class Conversation(BaseModel):
    id: str
    sheet_id: str
    project_id: str
    revision_id: str
    title: str
    status: str
    created_at: datetime
    updated_at: datetime


class ChatMessage(BaseModel):
    id: str
    conversation_id: str | None
    sheet_id: str
    project_id: str
    revision_id: str
    role: str
    content: str
    status: str
    provider: str | None
    model: str | None
    parent_message_id: str | None
    created_at: datetime
    updated_at: datetime
    context_items: list[ChatContextItem] = Field(default_factory=list)


class MessageFeedbackCreate(BaseModel):
    feedback: Literal["correct", "incorrect"]
    reason: str = Field(default="", max_length=1200)


class MessageFeedback(BaseModel):
    id: str
    message_id: str
    feedback: str
    reason: str
    created_at: datetime


class AIStatus(BaseModel):
    configured_provider: str
    resolved_provider: str
    model: str
    openai_api_key_configured: bool
    openai_key_source: str | None
    openai_key_last4: str | None
    openai_key_fingerprint: str | None
    openai_org_id_configured: bool
    openai_project_id_configured: bool
    external_calls_enabled: bool
    message: str


class MemoryCreate(BaseModel):
    scope: str = Field(default="global", min_length=1, max_length=80)
    key: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=1200)


class Memory(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    scope: str
    key: str
    text: str
    created_at: datetime


class UsageEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: str
    model: str
    operation: str
    project_id: str | None
    revision_id: str | None
    sheet_id: str | None
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost_usd: float
    created_at: datetime
