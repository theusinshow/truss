from dataclasses import dataclass
from typing import Literal

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
