from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ProposalKind = Literal["suppress_rule", "retain_rule", "draft_rule"]
ProposalState = Literal["insufficient", "pending", "approved", "dismissed"]
ProposalEffect = Literal["suppresses_findings", "calibration_only"]
ProposalDecisionValue = Literal["approved", "dismissed"]
SignalKind = Literal["confirmed", "rejected", "manual"]


class EvidenceBBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float


class LearningEvidence(BaseModel):
    finding_id: str
    signal_kind: SignalKind
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
    sheet_type: str
    bbox: EvidenceBBox
    description: str
    rejection_reason: str | None
    rule_id: str | None
    finding_status: str
    created_at: datetime


class LearningDecision(BaseModel):
    id: str
    stable_key: str
    proposal_kind: ProposalKind
    decision: ProposalDecisionValue
    reason: str
    policy_version: str
    preference_id: str | None
    preference_active: bool
    evidence_count: int
    created_at: datetime
    revoked_at: datetime | None
    active: bool


class LearningThreshold(BaseModel):
    minimum_evidence: int
    minimum_sheets: int
    minimum_ratio: float | None


class LearningProposal(BaseModel):
    stable_key: str
    proposal_kind: ProposalKind
    state: ProposalState
    effect: ProposalEffect
    policy_version: str
    sheet_type: str
    rule_id: str | None
    normalized_description: str | None
    evidence_count: int
    confirmed_count: int
    rejected_count: int
    manual_count: int
    distinct_sheet_count: int
    distinct_revision_count: int
    distinct_project_count: int
    observed_ratio: float | None
    threshold: LearningThreshold
    threshold_reached: bool
    active_preference_id: str | None
    evidence: list[LearningEvidence]
    decision: LearningDecision | None


class LearningDecisionCreate(BaseModel):
    decision: ProposalDecisionValue
    reason: str = Field(min_length=1, max_length=1000)
