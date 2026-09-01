from hashlib import sha256
import json
import math

import fitz

from truss_api.core.settings import Settings
from truss_api.documents import repository as documents_repository
from truss_api.sheetmap.primitives import PageExtraction, TextSpanRecord, extract_page
from truss_api.vision.models import VisionCandidate


GRID_PT = 96.0
MIN_OVERLAP_RATIO = 0.12


def read_sheet_extraction(sheet_id: str, settings: Settings) -> PageExtraction:
    """Rele somente a pagina local; `geometry_path` guarda outro artefato vetorial."""
    context = documents_repository.get_sheet_render_context(sheet_id, settings)
    source_path = settings.data_dir / str(context["stored_file_path"])
    document = fitz.open(source_path)
    try:
        return extract_page(document.load_page(int(context["page_index"])))
    finally:
        document.close()


def _area(bbox: tuple[float, float, float, float]) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def _union(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    return (
        min(left[0], right[0]),
        min(left[1], right[1]),
        max(left[2], right[2]),
        max(left[3], right[3]),
    )


def _overlap_ratio(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    intersection = (
        max(left[0], right[0]),
        max(left[1], right[1]),
        min(left[2], right[2]),
        min(left[3], right[3]),
    )
    denominator = min(_area(left), _area(right))
    return _area(intersection) / denominator if denominator > 0 else 0.0


def _grid_keys(bbox: tuple[float, float, float, float]) -> tuple[tuple[int, int], ...]:
    x0 = math.floor(bbox[0] / GRID_PT)
    y0 = math.floor(bbox[1] / GRID_PT)
    x1 = math.floor(max(bbox[0], bbox[2] - 0.001) / GRID_PT)
    y1 = math.floor(max(bbox[1], bbox[3] - 0.001) / GRID_PT)
    return tuple((x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1))


def _candidate_id(
    kind: str,
    bbox: tuple[float, float, float, float],
    texts: tuple[str, ...],
) -> str:
    material = json.dumps(
        {
            "bbox": [round(value, 3) for value in bbox],
            "kind": kind,
            "texts": texts,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"visual-{sha256(material.encode('utf-8')).hexdigest()[:20]}"


def _view_context(
    bbox: tuple[float, float, float, float],
    views: list[dict[str, object]],
) -> tuple[str | None, str | None]:
    center = ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
    matches = [
        view
        for view in views
        if float(view["x0"]) <= center[0] <= float(view["x1"])
        and float(view["y0"]) <= center[1] <= float(view["y1"])
    ]
    if not matches:
        return None, None

    selected = min(
        matches,
        key=lambda view: (float(view["x1"]) - float(view["x0"]))
        * (float(view["y1"]) - float(view["y0"])),
    )
    return str(selected["id"]), str(selected.get("technical_scope") or "") or None


def detect_legibility_candidates(
    extraction: PageExtraction,
    sheet_map: dict[str, object],
    *,
    small_text_threshold_pt: float,
    max_candidates: int,
) -> list[VisionCandidate]:
    spans = [span for span in extraction.spans if span.text.strip() and _area(span.bbox) > 0]
    views = [item for item in sheet_map.get("views", []) if isinstance(item, dict)]
    ranked: list[VisionCandidate] = []
    overlapping_indexes: set[int] = set()

    grid: dict[tuple[int, int], list[int]] = {}
    checked_pairs: set[tuple[int, int]] = set()
    for index, span in enumerate(spans):
        neighbours: set[int] = set()
        for key in _grid_keys(span.bbox):
            neighbours.update(grid.get(key, []))

        for other_index in sorted(neighbours):
            pair = (other_index, index)
            if pair in checked_pairs:
                continue
            checked_pairs.add(pair)
            other = spans[other_index]
            ratio = _overlap_ratio(other.bbox, span.bbox)
            if ratio < MIN_OVERLAP_RATIO:
                continue

            bbox = _union(other.bbox, span.bbox)
            texts = tuple(dict.fromkeys((other.text, span.text)))
            view_id, technical_scope = _view_context(bbox, views)
            ranked.append(
                VisionCandidate(
                    candidate_id=_candidate_id("text_overlap", bbox, texts),
                    kind="text_overlap",
                    bbox_pt=bbox,
                    text_samples=texts,
                    font_sizes_pt=(other.size, span.size),
                    view_id=view_id,
                    technical_scope=technical_scope,
                    score=100.0 + ratio,
                )
            )
            overlapping_indexes.update((other_index, index))

        for key in _grid_keys(span.bbox):
            grid.setdefault(key, []).append(index)

    for index, span in enumerate(spans):
        if index in overlapping_indexes or span.size <= 0 or span.size >= small_text_threshold_pt:
            continue
        view_id, technical_scope = _view_context(span.bbox, views)
        ranked.append(
            VisionCandidate(
                candidate_id=_candidate_id("small_text", span.bbox, (span.text,)),
                kind="small_text",
                bbox_pt=span.bbox,
                text_samples=(span.text,),
                font_sizes_pt=(span.size,),
                view_id=view_id,
                technical_scope=technical_scope,
                score=small_text_threshold_pt - span.size,
            )
        )

    unique = {candidate.candidate_id: candidate for candidate in ranked}
    return sorted(
        unique.values(),
        key=lambda item: (-item.score, item.bbox_pt[1], item.bbox_pt[0], item.candidate_id),
    )[:max_candidates]
