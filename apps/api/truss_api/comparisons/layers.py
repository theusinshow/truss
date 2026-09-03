from collections import defaultdict, deque
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
import re
import unicodedata
from typing import Any, Callable, Iterable, Sequence, TypeVar

import fitz

from truss_api.core.settings import Settings
from truss_api.sheetmap.primitives import (
    PageExtraction,
    TextSpanRecord,
    VectorPrimitive,
    extract_page,
)


LAYER_DELTA_LIMIT = 500
POSITION_EPSILON_PT = 1.0
MOVE_MAX_DISTANCE_PT = 144.0
TEXT_MODIFY_MAX_DISTANCE_PT = 48.0
VECTOR_MODIFY_MAX_DISTANCE_PT = 16.0
GRID_SIZE_PT = 64.0

BBox = tuple[float, float, float, float]
T = TypeVar("T")


class LayerExtractionError(RuntimeError):
    """Expected failure while extracting a local PDF page."""


@dataclass(frozen=True)
class LayerDiff:
    counts: dict[str, Any]
    deltas: list[dict[str, Any]]
    truncated: bool


def extract_sheet(sheet: dict[str, Any], settings: Settings) -> PageExtraction:
    path = Path(settings.data_dir / str(sheet["stored_file_path"]))
    try:
        document = fitz.open(path)
        try:
            return extract_page(document.load_page(int(sheet["page_index"])))
        finally:
            document.close()
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as error:
        raise LayerExtractionError(str(error)) from error


def _normalized_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return re.sub(r"\s+", " ", normalized).strip().casefold()


def _quantized(value: float, step: float = 0.5) -> float:
    return round(value / step) * step


def _bbox_key(bbox: BBox, step: float = 0.5) -> tuple[float, ...]:
    return tuple(_quantized(value, step) for value in bbox)


def _center(bbox: BBox) -> tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)


def _distance(left: BBox, right: BBox) -> float:
    left_x, left_y = _center(left)
    right_x, right_y = _center(right)
    return ((left_x - right_x) ** 2 + (left_y - right_y) ** 2) ** 0.5


def _bbox_payload(bbox: BBox | None) -> dict[str, float] | None:
    if bbox is None:
        return None
    return {"x0": bbox[0], "y0": bbox[1], "x1": bbox[2], "y1": bbox[3]}


def _consume_exact(
    base: Sequence[T],
    target: Sequence[T],
    signature: Callable[[T], object],
) -> tuple[set[int], set[int]]:
    targets: dict[object, deque[int]] = defaultdict(deque)
    for index, item in enumerate(target):
        targets[signature(item)].append(index)
    used_base: set[int] = set()
    used_target: set[int] = set()
    for index, item in enumerate(base):
        candidates = targets.get(signature(item))
        if candidates:
            used_base.add(index)
            used_target.add(candidates.popleft())
    return used_base, used_target


def _unique_groups(
    items: Sequence[T], indexes: Iterable[int], signature: Callable[[T], object]
) -> dict[object, int]:
    grouped: dict[object, list[int]] = defaultdict(list)
    for index in indexes:
        grouped[signature(items[index])].append(index)
    return {key: values[0] for key, values in grouped.items() if len(values) == 1}


def _grid_key(bbox: BBox) -> tuple[int, int]:
    x, y = _center(bbox)
    return (int(x // GRID_SIZE_PT), int(y // GRID_SIZE_PT))


def _neighbor_indexes(
    grid: dict[tuple[int, int], list[int]], bbox: BBox
) -> Iterable[int]:
    cell_x, cell_y = _grid_key(bbox)
    for y in range(cell_y - 1, cell_y + 2):
        for x in range(cell_x - 1, cell_x + 2):
            yield from grid.get((x, y), ())


def _mutual_unique_matches(
    base_indexes: set[int],
    target_indexes: set[int],
    base_items: Sequence[T],
    target_items: Sequence[T],
    bbox: Callable[[T], BBox],
    score: Callable[[T, T], float | None],
) -> list[tuple[int, int, float]]:
    target_grid: dict[tuple[int, int], list[int]] = defaultdict(list)
    for target_index in target_indexes:
        target_grid[_grid_key(bbox(target_items[target_index]))].append(target_index)

    candidates: list[tuple[float, int, int]] = []
    for base_index in base_indexes:
        for target_index in _neighbor_indexes(target_grid, bbox(base_items[base_index])):
            value = score(base_items[base_index], target_items[target_index])
            if value is not None:
                candidates.append((float(value), base_index, target_index))

    by_base: dict[int, list[tuple[float, int]]] = defaultdict(list)
    by_target: dict[int, list[tuple[float, int]]] = defaultdict(list)
    for value, base_index, target_index in candidates:
        by_base[base_index].append((value, target_index))
        by_target[target_index].append((value, base_index))

    result: list[tuple[int, int, float]] = []
    for base_index, base_candidates in by_base.items():
        base_candidates.sort(reverse=True)
        best_value, target_index = base_candidates[0]
        target_candidates = sorted(by_target[target_index], reverse=True)
        if target_candidates[0][1] != base_index:
            continue
        base_gap = best_value - base_candidates[1][0] if len(base_candidates) > 1 else 1.0
        target_gap = (
            best_value - target_candidates[1][0] if len(target_candidates) > 1 else 1.0
        )
        if base_gap < 0.08 or target_gap < 0.08:
            continue
        result.append((base_index, target_index, best_value))
    return result


def _text_content_signature(span: TextSpanRecord) -> tuple[object, ...]:
    return (
        _normalized_text(span.text),
        span.font.casefold(),
        round(span.size, 2),
        tuple(round(value, 4) for value in span.dir),
    )


def _text_exact_signature(span: TextSpanRecord) -> tuple[object, ...]:
    return (*_text_content_signature(span), _bbox_key(span.bbox))


def _text_delta(
    change_type: str,
    base: TextSpanRecord | None,
    target: TextSpanRecord | None,
    evidence: str,
    similarity: float,
) -> dict[str, Any]:
    return {
        "layer": "text",
        "change_type": change_type,
        "match_evidence": evidence,
        "similarity": similarity,
        "before_value": base.text if base else None,
        "after_value": target.text if target else None,
        "base_bbox": _bbox_payload(base.bbox if base else None),
        "target_bbox": _bbox_payload(target.bbox if target else None),
        "details": {
            "base_font": base.font if base else None,
            "base_size_pt": base.size if base else None,
            "target_font": target.font if target else None,
            "target_size_pt": target.size if target else None,
        },
    }


def diff_text(
    base: Sequence[TextSpanRecord], target: Sequence[TextSpanRecord]
) -> list[dict[str, Any]]:
    used_base, used_target = _consume_exact(base, target, _text_exact_signature)
    remaining_base = set(range(len(base))) - used_base
    remaining_target = set(range(len(target))) - used_target
    deltas: list[dict[str, Any]] = []

    base_unique = _unique_groups(base, remaining_base, _text_content_signature)
    target_unique = _unique_groups(target, remaining_target, _text_content_signature)
    for key in sorted(set(base_unique) & set(target_unique), key=str):
        base_index = base_unique[key]
        target_index = target_unique[key]
        distance = _distance(base[base_index].bbox, target[target_index].bbox)
        if distance <= MOVE_MAX_DISTANCE_PT:
            if distance > POSITION_EPSILON_PT:
                deltas.append(
                    _text_delta(
                        "moved",
                        base[base_index],
                        target[target_index],
                        "unique_text_and_style",
                        1.0,
                    )
                )
            remaining_base.remove(base_index)
            remaining_target.remove(target_index)

    def modification_score(left: TextSpanRecord, right: TextSpanRecord) -> float | None:
        if _text_content_signature(left) == _text_content_signature(right):
            # Conteudo duplicado em posicoes diferentes continua ambiguo: nao
            # inventamos uma correspondencia apenas pela proximidade.
            return None
        distance = _distance(left.bbox, right.bbox)
        if distance > TEXT_MODIFY_MAX_DISTANCE_PT:
            return None
        text_similarity = SequenceMatcher(
            None, _normalized_text(left.text), _normalized_text(right.text)
        ).ratio()
        if text_similarity < 0.55:
            return None
        proximity = 1 - distance / TEXT_MODIFY_MAX_DISTANCE_PT
        return 0.8 * text_similarity + 0.2 * proximity

    for base_index, target_index, similarity in _mutual_unique_matches(
        remaining_base,
        remaining_target,
        base,
        target,
        lambda item: item.bbox,
        modification_score,
    ):
        deltas.append(
            _text_delta(
                "modified",
                base[base_index],
                target[target_index],
                "mutual_spatial_text_similarity",
                similarity,
            )
        )
        remaining_base.remove(base_index)
        remaining_target.remove(target_index)

    deltas.extend(
        _text_delta("removed", base[index], None, "unmatched_base_span", 1.0)
        for index in sorted(remaining_base)
    )
    deltas.extend(
        _text_delta("added", None, target[index], "unmatched_target_span", 1.0)
        for index in sorted(remaining_target)
    )
    return deltas


def _vector_style(primitive: VectorPrimitive) -> tuple[object, ...]:
    return (
        primitive.kind,
        round(primitive.width or 0.0, 3),
        tuple(round(value, 3) for value in primitive.color or ()),
        primitive.dashes or "",
    )


def _relative_points(primitive: VectorPrimitive) -> tuple[tuple[float, float], ...]:
    x0, y0, _, _ = primitive.rect
    return tuple(
        (round(point[0] - x0, 2), round(point[1] - y0, 2))
        for point in primitive.points
    )


def _vector_content_signature(primitive: VectorPrimitive) -> tuple[object, ...]:
    width = primitive.rect[2] - primitive.rect[0]
    height = primitive.rect[3] - primitive.rect[1]
    return (
        *_vector_style(primitive),
        round(width, 2),
        round(height, 2),
        _relative_points(primitive),
    )


def _vector_exact_signature(primitive: VectorPrimitive) -> tuple[object, ...]:
    return (
        *_vector_content_signature(primitive),
        _bbox_key(primitive.rect, 0.25),
        tuple((round(x, 2), round(y, 2)) for x, y in primitive.points),
    )


def _vector_value(primitive: VectorPrimitive | None) -> str | None:
    if primitive is None:
        return None
    kind = {"l": "linha", "re": "retangulo", "c": "curva", "qu": "quadrilatero"}.get(
        primitive.kind, primitive.kind
    )
    width = f" · {primitive.width:.2f} pt" if primitive.width is not None else ""
    return f"{kind}{width}"


def _vector_delta(
    change_type: str,
    base: VectorPrimitive | None,
    target: VectorPrimitive | None,
    evidence: str,
    similarity: float,
) -> dict[str, Any]:
    return {
        "layer": "vector",
        "change_type": change_type,
        "match_evidence": evidence,
        "similarity": similarity,
        "before_value": _vector_value(base),
        "after_value": _vector_value(target),
        "base_bbox": _bbox_payload(base.rect if base else None),
        "target_bbox": _bbox_payload(target.rect if target else None),
        "details": {
            "base_kind": base.kind if base else None,
            "target_kind": target.kind if target else None,
            "base_point_count": len(base.points) if base else None,
            "target_point_count": len(target.points) if target else None,
        },
    }


def diff_vectors(
    base: Sequence[VectorPrimitive], target: Sequence[VectorPrimitive]
) -> list[dict[str, Any]]:
    used_base, used_target = _consume_exact(base, target, _vector_exact_signature)
    remaining_base = set(range(len(base))) - used_base
    remaining_target = set(range(len(target))) - used_target
    deltas: list[dict[str, Any]] = []

    base_unique = _unique_groups(base, remaining_base, _vector_content_signature)
    target_unique = _unique_groups(target, remaining_target, _vector_content_signature)
    for key in sorted(set(base_unique) & set(target_unique), key=str):
        base_index = base_unique[key]
        target_index = target_unique[key]
        distance = _distance(base[base_index].rect, target[target_index].rect)
        if distance <= MOVE_MAX_DISTANCE_PT:
            if distance > POSITION_EPSILON_PT:
                deltas.append(
                    _vector_delta(
                        "moved",
                        base[base_index],
                        target[target_index],
                        "unique_vector_geometry_and_style",
                        1.0,
                    )
                )
            remaining_base.remove(base_index)
            remaining_target.remove(target_index)

    def modification_score(left: VectorPrimitive, right: VectorPrimitive) -> float | None:
        if _vector_content_signature(left) == _vector_content_signature(right):
            return None
        if left.kind != right.kind:
            return None
        distance = _distance(left.rect, right.rect)
        if distance > VECTOR_MODIFY_MAX_DISTANCE_PT:
            return None
        proximity = 1 - distance / VECTOR_MODIFY_MAX_DISTANCE_PT
        same_style = 1.0 if _vector_style(left) == _vector_style(right) else 0.6
        return 0.75 * proximity + 0.25 * same_style

    for base_index, target_index, similarity in _mutual_unique_matches(
        remaining_base,
        remaining_target,
        base,
        target,
        lambda item: item.rect,
        modification_score,
    ):
        deltas.append(
            _vector_delta(
                "modified",
                base[base_index],
                target[target_index],
                "mutual_spatial_vector_match",
                similarity,
            )
        )
        remaining_base.remove(base_index)
        remaining_target.remove(target_index)

    deltas.extend(
        _vector_delta("removed", base[index], None, "unmatched_base_primitive", 1.0)
        for index in sorted(remaining_base)
    )
    deltas.extend(
        _vector_delta("added", None, target[index], "unmatched_target_primitive", 1.0)
        for index in sorted(remaining_target)
    )
    return deltas


def _counts(deltas: Sequence[dict[str, Any]]) -> dict[str, int]:
    result = {
        "total": len(deltas),
        "added": 0,
        "removed": 0,
        "modified": 0,
        "moved": 0,
    }
    for delta in deltas:
        result[str(delta["change_type"])] += 1
    return result


def diff_layers(base: PageExtraction, target: PageExtraction) -> LayerDiff:
    text_deltas = diff_text(base.spans, target.spans)
    vector_deltas = diff_vectors(base.primitives, target.primitives)
    counts = {
        "total": len(text_deltas) + len(vector_deltas),
        "text": _counts(text_deltas),
        "vector": _counts(vector_deltas),
    }
    truncated = (
        len(text_deltas) > LAYER_DELTA_LIMIT or len(vector_deltas) > LAYER_DELTA_LIMIT
    )
    return LayerDiff(
        counts=counts,
        deltas=text_deltas[:LAYER_DELTA_LIMIT] + vector_deltas[:LAYER_DELTA_LIMIT],
        truncated=truncated,
    )
