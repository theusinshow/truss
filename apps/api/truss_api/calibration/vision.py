from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import fitz

from truss_api.sheetmap.primitives import extract_page
from truss_api.vision.candidates import detect_legibility_candidates


@dataclass(frozen=True)
class VisualCandidatePageMeasurement:
    page_index: int
    text_span_count: int
    small_text_count: int
    overlap_count: int
    selected_count: int


@dataclass(frozen=True)
class VisualCandidateDocumentMeasurement:
    path: Path
    page_count: int
    pages_with_candidates: int
    text_span_count: int
    small_text_count: int
    overlap_count: int
    selected_count: int
    elapsed_seconds: float
    pages: tuple[VisualCandidatePageMeasurement, ...]


def measure_visual_candidates(
    pdf_path: Path,
    *,
    small_text_threshold_pt: float,
    max_candidates_per_page: int,
) -> VisualCandidateDocumentMeasurement:
    """Measure deterministic visual candidates without invoking an AI provider."""

    started_at = perf_counter()
    pages: list[VisualCandidatePageMeasurement] = []

    with fitz.open(pdf_path) as document:
        for page_index, page in enumerate(document):
            extraction = extract_page(page)
            candidates = detect_legibility_candidates(
                extraction,
                {"views": []},
                small_text_threshold_pt=small_text_threshold_pt,
                max_candidates=100_000,
            )
            small_text_count = sum(
                candidate.kind == "small_text" for candidate in candidates
            )
            overlap_count = sum(candidate.kind == "text_overlap" for candidate in candidates)
            pages.append(
                VisualCandidatePageMeasurement(
                    page_index=page_index,
                    text_span_count=len(extraction.spans),
                    small_text_count=small_text_count,
                    overlap_count=overlap_count,
                    selected_count=min(len(candidates), max_candidates_per_page),
                )
            )

    return VisualCandidateDocumentMeasurement(
        path=pdf_path,
        page_count=len(pages),
        pages_with_candidates=sum(
            page.small_text_count + page.overlap_count > 0 for page in pages
        ),
        text_span_count=sum(page.text_span_count for page in pages),
        small_text_count=sum(page.small_text_count for page in pages),
        overlap_count=sum(page.overlap_count for page in pages),
        selected_count=sum(page.selected_count for page in pages),
        elapsed_seconds=perf_counter() - started_at,
        pages=tuple(pages),
    )
