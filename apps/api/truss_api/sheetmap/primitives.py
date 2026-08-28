from dataclasses import dataclass, field

import fitz


EXTRACTOR_VERSION = "extract-v0.2"


@dataclass(frozen=True)
class VectorPrimitive:
    kind: str
    points: list[tuple[float, float]]
    rect: tuple[float, float, float, float]
    width: float | None = None
    color: tuple[float, ...] | None = None
    dashes: str | None = None


@dataclass(frozen=True)
class TextSpanRecord:
    text: str
    bbox: tuple[float, float, float, float]
    font: str
    size: float
    dir: tuple[float, float]


@dataclass(frozen=True)
class PageMetadata:
    width_pt: float
    height_pt: float
    rotation: int
    mediabox: tuple[float, float, float, float]
    cropbox: tuple[float, float, float, float]
    rotation_matrix: tuple[float, ...]


@dataclass(frozen=True)
class PageExtraction:
    metadata: PageMetadata
    primitives: list[VectorPrimitive] = field(default_factory=list)
    spans: list[TextSpanRecord] = field(default_factory=list)


def _rect_tuple(rect: fitz.Rect) -> tuple[float, float, float, float]:
    return (float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1))


def _page_metadata(page: fitz.Page) -> PageMetadata:
    rect = page.rect
    return PageMetadata(
        width_pt=float(rect.width),
        height_pt=float(rect.height),
        rotation=int(page.rotation),
        mediabox=_rect_tuple(page.mediabox),
        cropbox=_rect_tuple(page.cropbox),
        rotation_matrix=tuple(round(float(value), 6) for value in page.rotation_matrix),
    )


def _primitives(page: fitz.Page) -> list[VectorPrimitive]:
    primitives: list[VectorPrimitive] = []

    for drawing in page.get_drawings():
        bounds = _rect_tuple(drawing["rect"])
        width = drawing.get("width")
        color = drawing.get("color")
        dashes = drawing.get("dashes")

        for item in drawing["items"]:
            points = [
                (round(float(value.x), 3), round(float(value.y), 3))
                for value in item[1:]
                if hasattr(value, "x")
            ]
            primitives.append(
                VectorPrimitive(
                    kind=str(item[0]),
                    points=points,
                    rect=bounds,
                    width=float(width) if width is not None else None,
                    color=tuple(float(channel) for channel in color) if color else None,
                    dashes=str(dashes) if dashes else None,
                )
            )

    return primitives


def _spans(page: fitz.Page) -> list[TextSpanRecord]:
    records: list[TextSpanRecord] = []

    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            direction = line.get("dir", (1.0, 0.0))
            for span in line["spans"]:
                text = str(span["text"]).strip()
                if not text:
                    continue

                x0, y0, x1, y1 = span["bbox"]
                records.append(
                    TextSpanRecord(
                        text=text,
                        bbox=(float(x0), float(y0), float(x1), float(y1)),
                        font=str(span.get("font", "")),
                        size=round(float(span.get("size", 0.0)), 2),
                        dir=(float(direction[0]), float(direction[1])),
                    )
                )

    return records


def extract_page(page: fitz.Page) -> PageExtraction:
    return PageExtraction(
        metadata=_page_metadata(page),
        primitives=_primitives(page),
        spans=_spans(page),
    )
