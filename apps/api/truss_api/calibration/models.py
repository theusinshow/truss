from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class CalibrationDecisionCreate(BaseModel):
    decision: Literal["approved", "dismissed"]
    reason: str = Field(min_length=1, max_length=1000)


class CalibrationDecision(BaseModel):
    id: str
    stable_key: str
    proposal_id: str
    decision: Literal["approved", "dismissed"]
    reason: str
    created_at: datetime
    revoked_at: datetime | None


class CalibrationEvidence(BaseModel):
    id: str
    proposal_id: str
    evidence_key: str
    evidence_kind: Literal["sample", "counterexample", "feedback"]
    document_sha256: str | None
    page_index: int | None
    sheet_code: str | None
    bbox: dict[str, float] | None
    source_finding_id: str | None
    description: str
    payload: dict[str, Any]
    created_at: datetime


class CalibrationProposal(BaseModel):
    id: str
    run_id: str
    stable_key: str
    proposal_kind: Literal["rule_noise", "checklist_candidate", "rule_retention"]
    sheet_type: str | None
    technical_scope: str | None
    rule_id: str | None
    title: str
    rationale: str
    payload: dict[str, Any]
    policy_version: str
    created_at: datetime
    evidence: list[CalibrationEvidence]
    decision: CalibrationDecision | None
    state: Literal["pending", "ready_for_implementation", "dismissed"]


class CalibrationRun(BaseModel):
    id: str
    analysis_key: str
    run_key: str
    corpus_manifest_hash: str
    sheetmap_pipeline_version: str
    audit_pipeline_version: str
    rule_pack_digest: str
    policy_version: str
    preference_digest: str
    document_count: int
    page_count: int
    sheet_map_count: int
    evaluation_count: int
    raw_finding_count: int
    suppressed_finding_count: int
    effective_finding_count: int
    artifact_path: str
    created_at: datetime


class CalibrationRunDetail(CalibrationRun):
    metrics: dict[str, Any]
    proposals: list[CalibrationProposal]
