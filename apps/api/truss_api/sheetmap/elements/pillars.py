import re

from truss_api.sheetmap.elements.models import DetectedElement, ELEMENT_KIND_PILLAR
from truss_api.sheetmap.primitives import TextSpanRecord


PROVENANCE = "native-text/pillar-code-v1"

# Delimitadores impedem que CP1, XP2 ou palavras sejam lidos como pilar. O
# separador nao aceita "=", logo P=10 continua sendo uma nota, nao um codigo.
PILLAR_CODE = re.compile(
    r"(?<![A-Z0-9])P[\s.\-]*(?P<suffix>\d{1,3}[A-Z]?)(?![A-Z0-9])",
    re.IGNORECASE,
)


def _union_bbox(spans: tuple[TextSpanRecord, ...]) -> tuple[float, float, float, float]:
    return (
        min(span.bbox[0] for span in spans),
        min(span.bbox[1] for span in spans),
        max(span.bbox[2] for span in spans),
        max(span.bbox[3] for span in spans),
    )


def _same_line(left: TextSpanRecord, right: TextSpanRecord) -> bool:
    left_center = (left.bbox[1] + left.bbox[3]) / 2
    right_center = (right.bbox[1] + right.bbox[3]) / 2
    tolerance = max(left.size, right.size) * 0.45
    gap = right.bbox[0] - left.bbox[2]
    max_gap = max(4.0, max(left.size, right.size) * 1.2)
    horizontal = abs(left.dir[1]) < 0.2 and abs(right.dir[1]) < 0.2
    return horizontal and abs(left_center - right_center) <= tolerance and -1.0 <= gap <= max_gap


def _candidates(spans: list[TextSpanRecord]) -> list[tuple[str, tuple[TextSpanRecord, ...]]]:
    candidates = [(span.text, (span,)) for span in spans]

    for index, left in enumerate(spans[:-1]):
        right = spans[index + 1]
        if _same_line(left, right):
            candidates.append((f"{left.text} {right.text}", (left, right)))

    return candidates


def extract_pillars(spans: list[TextSpanRecord]) -> list[DetectedElement]:
    found: list[DetectedElement] = []
    seen: set[tuple[str, tuple[float, float, float, float]]] = set()

    for source_text, source_spans in _candidates(spans):
        bbox = _union_bbox(source_spans)
        for match in PILLAR_CODE.finditer(source_text):
            raw = match.group(0)
            code = f"P{match.group('suffix').upper()}"
            key = (code, bbox)
            if key in seen:
                continue
            seen.add(key)
            found.append(
                DetectedElement(
                    element_kind=ELEMENT_KIND_PILLAR,
                    code_raw=raw,
                    code=code,
                    bbox=bbox,
                    confidence=0.95 if len(source_spans) == 1 else 0.85,
                    provenance=PROVENANCE,
                    attributes={
                        "source_text": source_text,
                        "span_count": len(source_spans),
                        "association_status": "not_evaluated",
                    },
                )
            )

    return found
