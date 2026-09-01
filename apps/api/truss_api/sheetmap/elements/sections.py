from dataclasses import dataclass, replace
import math
import re

from truss_api.sheetmap.elements.models import DetectedElement, ELEMENT_KIND_PILLAR
from truss_api.sheetmap.primitives import TextSpanRecord
from truss_api.sheetmap.views.models import DetectedView


SECTION_PROVENANCE = "native-text/pillar-section-v1:adjacent-label"
MAX_SECTION_GAP_PT = 2.0
MIN_NEAREST_PILLAR_MARGIN_PT = 0.5
MIN_SECTION_VALUE = 8.0
MAX_SECTION_VALUE = 300.0

_SECTION_TOKEN = re.compile(
    r"^\s*(?P<a>\d{1,3}(?:[.,]\d+)?)\s*[xX×]\s*"
    r"(?P<b>\d{1,3}(?:[.,]\d+)?)(?:\s*(?P<unit>cm))?\s*$",
    re.IGNORECASE,
)

Number = int | float
BBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class SectionCandidate:
    raw: str
    a_raw: str
    b_raw: str
    ordered_signature: tuple[Number, Number]
    signature: tuple[Number, Number]
    unit_raw: str | None
    bbox: BBox

    @property
    def normalized_unit(self) -> str | None:
        return self.unit_raw.lower() if self.unit_raw else None


def _number(raw: str) -> Number:
    value = float(raw.replace(",", "."))
    return int(value) if value.is_integer() else value


def parse_section_span(span: TextSpanRecord) -> SectionCandidate | None:
    match = _SECTION_TOKEN.fullmatch(span.text)
    if match is None:
        return None

    a = _number(match.group("a"))
    b = _number(match.group("b"))
    if not (
        MIN_SECTION_VALUE <= a <= MAX_SECTION_VALUE
        and MIN_SECTION_VALUE <= b <= MAX_SECTION_VALUE
    ):
        return None

    return SectionCandidate(
        raw=span.text,
        a_raw=match.group("a"),
        b_raw=match.group("b"),
        ordered_signature=(a, b),
        signature=tuple(sorted((a, b))),
        unit_raw=match.group("unit"),
        bbox=span.bbox,
    )


def _bbox_gap(left: BBox, right: BBox) -> float:
    dx = max(left[0] - right[2], right[0] - left[2], 0.0)
    dy = max(left[1] - right[3], right[1] - left[3], 0.0)
    return math.hypot(dx, dy)


def _center_inside(bbox: BBox, view_bbox: BBox) -> bool:
    center_x = (bbox[0] + bbox[2]) / 2
    center_y = (bbox[1] + bbox[3]) / 2
    return (
        view_bbox[0] <= center_x <= view_bbox[2]
        and view_bbox[1] <= center_y <= view_bbox[3]
    )


def _candidate_view_index(
    candidate: SectionCandidate, views: list[DetectedView]
) -> int | None:
    containing = [
        index for index, view in enumerate(views) if _center_inside(candidate.bbox, view.bbox)
    ]
    return containing[0] if len(containing) == 1 else None


def _association_confidence(gap_pt: float, element_confidence: float) -> float:
    spatial = max(0.75, 0.98 - gap_pt * 0.08)
    return round(min(element_confidence, spatial), 3)


def _ambiguous_attributes(candidates: list[SectionCandidate]) -> dict[str, object]:
    signatures = sorted({candidate.signature for candidate in candidates})
    units = {candidate.normalized_unit for candidate in candidates}
    ordered_units = sorted(units, key=lambda value: (value is not None, value or ""))
    return {
        "section_association_status": "ambiguous",
        "section_provenance": SECTION_PROVENANCE,
        "section_candidate_count": len(candidates),
        "section_candidate_signatures": [list(signature) for signature in signatures],
        "section_candidate_units": ordered_units,
        "section_candidates": [
            {
                "raw": candidate.raw,
                "ordered_signature": list(candidate.ordered_signature),
                "signature": list(candidate.signature),
                "unit_raw": candidate.unit_raw,
                "bbox_pt": list(candidate.bbox),
            }
            for candidate in sorted(
                candidates,
                key=lambda item: (item.bbox, item.raw),
            )
        ],
    }


def _matched_attributes(
    candidate: SectionCandidate,
    *,
    evidence_count: int,
    confidence: float,
) -> dict[str, object]:
    return {
        "section_association_status": "matched",
        "section_raw": candidate.raw,
        "section_a_raw": candidate.a_raw,
        "section_b_raw": candidate.b_raw,
        "section_signature": list(candidate.signature),
        "section_ordered_signature": list(candidate.ordered_signature),
        "section_unit_raw": candidate.unit_raw,
        "section_provenance": SECTION_PROVENANCE,
        "section_confidence": confidence,
        "section_bbox_pt": list(candidate.bbox),
        "section_evidence_count": evidence_count,
    }


def associate_pillar_sections(
    spans: list[TextSpanRecord],
    elements: list[DetectedElement],
    views: list[DetectedView],
) -> list[DetectedElement]:
    candidates_by_view: dict[int, list[SectionCandidate]] = {}
    for span in spans:
        candidate = parse_section_span(span)
        if candidate is None:
            continue
        view_index = _candidate_view_index(candidate, views)
        if view_index is not None:
            candidates_by_view.setdefault(view_index, []).append(candidate)

    pillar_indexes_by_view: dict[int, list[int]] = {}
    for index, element in enumerate(elements):
        if element.element_kind != ELEMENT_KIND_PILLAR or element.view_index is None:
            continue
        pillar_indexes_by_view.setdefault(element.view_index, []).append(index)

    assigned: dict[int, list[tuple[float, SectionCandidate]]] = {}
    for view_index, candidates in candidates_by_view.items():
        pillar_indexes = pillar_indexes_by_view.get(view_index, [])
        for candidate in candidates:
            nearest = sorted(
                (
                    (_bbox_gap(candidate.bbox, elements[index].bbox), index)
                    for index in pillar_indexes
                ),
                key=lambda item: (item[0], item[1]),
            )
            if not nearest or nearest[0][0] > MAX_SECTION_GAP_PT:
                continue
            if (
                len(nearest) > 1
                and nearest[1][0] - nearest[0][0]
                < MIN_NEAREST_PILLAR_MARGIN_PT
            ):
                continue
            assigned.setdefault(nearest[0][1], []).append((nearest[0][0], candidate))

    enriched: list[DetectedElement] = []
    for index, element in enumerate(elements):
        links = assigned.get(index, [])
        if not links:
            enriched.append(element)
            continue

        candidates = [candidate for _, candidate in links]
        signatures = {candidate.signature for candidate in candidates}
        units = {candidate.normalized_unit for candidate in candidates}
        attributes = dict(element.attributes)
        if len(signatures) != 1 or len(units) != 1:
            attributes.update(_ambiguous_attributes(candidates))
            enriched.append(replace(element, attributes=attributes))
            continue

        gap, selected = min(
            links,
            key=lambda item: (
                item[0],
                item[1].bbox,
                item[1].raw,
            ),
        )
        attributes.update(
            _matched_attributes(
                selected,
                evidence_count=len(candidates),
                confidence=_association_confidence(gap, element.confidence),
            )
        )
        enriched.append(replace(element, attributes=attributes))

    return enriched
