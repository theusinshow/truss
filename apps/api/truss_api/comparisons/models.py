from typing import Literal

from pydantic import BaseModel, Field, model_validator


ComparisonStatus = Literal[
    "identical", "changed", "added", "removed", "ambiguous", "unavailable"
]
MatchMethod = Literal["manual", "sheet_code", "exact_content", "unmatched"]


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
