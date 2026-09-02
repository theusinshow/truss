from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RulePreferenceCreate(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class PreferenceBBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float


class PreferenceSource(BaseModel):
    finding_id: str
    project_id: str
    project_name: str
    revision_id: str
    revision_code: str
    document_id: str
    document_name: str
    sheet_id: str
    sheet_label: str
    sheet_number: int
    sheet_code: str | None
    bbox: PreferenceBBox
    description: str
    rejection_reason: str | None


class RulePreference(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    scope: Literal["sheet_type"]
    sheet_type: str
    rule_id: str
    action: Literal["suppress"]
    reason: str
    source_finding_id: str
    created_at: datetime
    revoked_at: datetime | None
    active: bool
    source: PreferenceSource | None = None
