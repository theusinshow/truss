from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


VisionCandidateKind = Literal["small_text", "text_overlap"]
VisionOutcome = Literal["pass", "attention", "not_verifiable"]
VisionIssue = Literal["none", "text_too_small", "text_overlap", "illegible", "not_verifiable"]


@dataclass(frozen=True)
class VisionCandidate:
    candidate_id: str
    kind: VisionCandidateKind
    bbox_pt: tuple[float, float, float, float]
    text_samples: tuple[str, ...]
    font_sizes_pt: tuple[float, ...]
    view_id: str | None
    technical_scope: str | None
    score: float


@dataclass(frozen=True)
class VisionCropInput:
    candidate: VisionCandidate
    image_bytes: bytes
    image_detail: Literal["low", "high", "original"]
    crop_hash: str
    crop_bbox_pt: tuple[float, float, float, float]
    width_px: int
    height_px: int


class VisionAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    outcome: VisionOutcome
    issue: VisionIssue
    confidence: float = Field(ge=0.0, le=1.0)
    description: str = Field(min_length=1, max_length=600)
    evidence: list[str] = Field(default_factory=list, max_length=6)


@dataclass(frozen=True)
class VisionProviderResponse:
    provider: str
    model: str
    analysis: VisionAnalysis
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float = 0.0


@dataclass(frozen=True)
class RenderedVisionCrop:
    image_bytes: bytes
    path: str
    crop_hash: str
    crop_bbox_pt: tuple[float, float, float, float]
    width_px: int
    height_px: int
    scale: float


SheetReviewFindingType = Literal[
    "inconsistency",
    "attention",
    "missing_information",
    "unverifiable",
]
SheetReviewSeverity = Literal["low", "medium", "high", "critical"]
SheetReviewScope = Literal["localized", "view", "sheet"]


class NormalizedBoundingBox(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x0: float = Field(ge=0.0, le=1000.0)
    y0: float = Field(ge=0.0, le=1000.0)
    x1: float = Field(ge=0.0, le=1000.0)
    y1: float = Field(ge=0.0, le=1000.0)


class SheetReviewFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str = Field(min_length=1, max_length=80)
    type: SheetReviewFindingType
    severity: SheetReviewSeverity
    confidence: float = Field(ge=0.0, le=1.0)
    description: str = Field(min_length=1, max_length=900)
    scope: SheetReviewScope
    bbox: NormalizedBoundingBox
    evidence: list[str] = Field(default_factory=list, max_length=6)


class SheetReviewAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sheet_id: str
    summary: str = Field(min_length=1, max_length=900)
    findings: list[SheetReviewFinding] = Field(default_factory=list, max_length=10)


@dataclass(frozen=True)
class SheetReviewImage:
    role: Literal["global", "tile"]
    image_bytes: bytes
    image_hash: str
    bbox_pt: tuple[float, float, float, float]
    width_px: int
    height_px: int
    detail: Literal["low", "high", "original"]


@dataclass(frozen=True)
class SheetReviewInput:
    sheet_id: str
    width_pt: float
    height_pt: float
    images: tuple[SheetReviewImage, ...]
    context: dict[str, Any]


@dataclass(frozen=True)
class SheetReviewProviderResponse:
    provider: str
    model: str
    analysis: SheetReviewAnalysis
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float = 0.0
