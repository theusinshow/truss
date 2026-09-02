from typing import Literal

from pydantic import BaseModel


BatchMode = Literal["local_deterministic", "with_visual"]


class BatchRunCreate(BaseModel):
    include_visual: bool = False


class BatchCapabilities(BaseModel):
    visual_enabled: bool
    provider: str
    model: str
    vision_budget_usd_per_revision: float
    vision_max_calls_per_revision: int
    vision_max_candidates_per_sheet: int
    worker_concurrency: int
    visual_concurrency: int


class BatchRunSummary(BaseModel):
    id: str
    project_id: str
    revision_id: str
    mode: BatchMode
    status: str
    phase: str
    config: dict[str, object]
    input_fingerprint: str
    pipeline_version: str
    total_sheets: int
    counts: dict[str, int]
    phase_counts: dict[str, dict[str, int]]
    cancel_requested_at: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None
    updated_at: str


class BatchItem(BaseModel):
    id: str
    batch_run_id: str
    sheet_id: str
    sheet_label: str
    sheet_number: int
    phase: str
    sequence: int
    status: str
    operation_id: str | None
    attempt_count: int
    error_code: str | None
    error_message: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None
    updated_at: str
