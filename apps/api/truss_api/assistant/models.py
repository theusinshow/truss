from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    answer: str
    provider: str
    model: str


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
