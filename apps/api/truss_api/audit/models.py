from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


FindingType = Literal["inconsistency", "attention", "missing_information", "unverifiable"]
FindingSeverity = Literal["low", "medium", "high", "critical"]
FindingOrigin = Literal["ai", "human"]
FindingStatus = Literal["pending", "confirmed", "rejected"]


class BoundingBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float


class Finding(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    audit_run_id: str | None
    sheet_id: str
    document_id: str
    project_id: str
    revision_id: str
    category: str
    type: FindingType
    description: str
    severity: FindingSeverity
    confidence: float
    bbox: BoundingBox
    evidence: list[str]
    origin: FindingOrigin
    status: FindingStatus
    rejection_reason: str | None
    created_at: datetime
    updated_at: datetime


class AuditRun(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sheet_id: str
    document_id: str
    project_id: str
    revision_id: str
    mode: str
    pipeline_version: str
    status: str
    summary: str
    started_at: datetime
    completed_at: datetime
    findings: list[Finding]


class FindingStatusUpdate(BaseModel):
    status: FindingStatus
    rejection_reason: str | None = Field(default=None, max_length=1000)


class ManualFindingCreate(BaseModel):
    category: str = Field(min_length=1, max_length=80)
    type: FindingType = "attention"
    description: str = Field(min_length=1, max_length=1200)
    severity: FindingSeverity = "medium"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    bbox: BoundingBox
    evidence: list[str] = Field(default_factory=list, max_length=10)
