from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RulePreferenceCreate(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


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
