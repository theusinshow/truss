from typing import Literal

from pydantic import BaseModel, Field, model_validator


ComparisonStatus = Literal[
    "identical", "changed", "added", "removed", "ambiguous", "unavailable"
]
MatchMethod = Literal["manual", "sheet_code", "exact_content", "unmatched"]
DeltaLayer = Literal["text", "vector"]
DeltaChangeType = Literal["added", "removed", "modified", "moved"]
DeltaStatus = Literal[
    "not_run",
    "completed",
    "completed_with_limits",
    "not_comparable",
    "unavailable",
    "not_applicable",
]


class RevisionComparisonCreate(BaseModel):
    base_revision_id: str = Field(min_length=1)
    target_revision_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def revisions_must_differ(self) -> "RevisionComparisonCreate":
        if self.base_revision_id == self.target_revision_id:
            raise ValueError("Base and target revisions must differ")
        return self


class ComparisonPairingCreate(RevisionComparisonCreate):
    base_sheet_id: str = Field(min_length=1)
    target_sheet_id: str = Field(min_length=1)


class ComparisonPairing(BaseModel):
    id: str
    project_id: str
    base_revision_id: str
    target_revision_id: str
    base_sheet_id: str
    target_sheet_id: str
    created_at: str
    revoked_at: str | None
    active: bool


class ComparisonSheet(BaseModel):
    id: str
    document_id: str
    revision_id: str
    sheet_number: int
    page_index: int
    label: str
    sheet_code: str | None
    sheet_code_raw: str | None
    width_pt: float
    height_pt: float
    rotation: int
    source_status: str


class ComparisonRegion(BaseModel):
    id: str
    region_index: int
    base_bbox: dict[str, float]
    target_bbox: dict[str, float]
    changed_pixel_count: int
    changed_ratio: float


class ComparisonDelta(BaseModel):
    id: str
    delta_index: int
    layer: DeltaLayer
    change_type: DeltaChangeType
    match_evidence: str
    similarity: float
    before_value: str | None
    after_value: str | None
    base_bbox: dict[str, float] | None
    target_bbox: dict[str, float] | None
    details: dict[str, object]


class ComparisonSheetPair(BaseModel):
    id: str
    sequence: int
    base_sheet: ComparisonSheet | None
    target_sheet: ComparisonSheet | None
    status: ComparisonStatus
    match_method: MatchMethod
    match_confidence: float
    pairing_override_id: str | None
    summary: str
    changed_ratio: float
    regions: list[ComparisonRegion]
    delta_status: DeltaStatus
    delta_counts: dict[str, object]
    delta_truncated: bool
    delta_summary: str
    deltas: list[ComparisonDelta]


class RevisionComparison(BaseModel):
    id: str
    project_id: str
    base_revision_id: str
    target_revision_id: str
    base_revision_code: str
    target_revision_code: str
    input_fingerprint: str
    pipeline_version: str
    status: Literal["completed", "completed_with_limits"]
    counts: dict[str, int]
    created_at: str
    pairs: list[ComparisonSheetPair]
