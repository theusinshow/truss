from dataclasses import dataclass
import json
from pathlib import Path

import fitz

from truss_api.core.settings import Settings


@dataclass(frozen=True)
class GeometryRect:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)


@dataclass(frozen=True)
class PageGeometry:
    width_pt: float
    height_pt: float
    rects: list[GeometryRect]
    line_count: int
    curve_count: int

    @property
    def page_area(self) -> float:
        return self.width_pt * self.height_pt


def extract_page_geometry(page: fitz.Page, min_area_ratio: float = 0.0002) -> PageGeometry:
    rect = page.rect
    page_area = rect.width * rect.height
    minimum_area = page_area * min_area_ratio

    rects: list[GeometryRect] = []
    line_count = 0
    curve_count = 0

    for drawing in page.get_drawings():
        for item in drawing["items"]:
            if item[0] == "l":
                line_count += 1
            elif item[0] == "c":
                curve_count += 1

        bounds = drawing["rect"]
        if bounds.width * bounds.height < minimum_area:
            continue

        rects.append(
            GeometryRect(
                x0=float(bounds.x0),
                y0=float(bounds.y0),
                x1=float(bounds.x1),
                y1=float(bounds.y1),
            )
        )

    return PageGeometry(
        width_pt=float(rect.width),
        height_pt=float(rect.height),
        rects=rects,
        line_count=line_count,
        curve_count=curve_count,
    )


def geometry_relative_path(project_id: str, revision_id: str, sheet_id: str) -> str:
    return f"geometry/{project_id}/{revision_id}/{sheet_id}.json"


def write_page_geometry(
    geometry: PageGeometry,
    *,
    project_id: str,
    revision_id: str,
    sheet_id: str,
    settings: Settings,
) -> str:
    relative = geometry_relative_path(project_id, revision_id, sheet_id)
    target = settings.data_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "width_pt": geometry.width_pt,
        "height_pt": geometry.height_pt,
        "line_count": geometry.line_count,
        "curve_count": geometry.curve_count,
        "rects": [[rect.x0, rect.y0, rect.x1, rect.y1] for rect in geometry.rects],
    }
    target.write_text(json.dumps(payload), encoding="utf-8")
    return relative


def read_page_geometry(relative_path: str, settings: Settings) -> PageGeometry:
    source = Path(settings.data_dir / relative_path)
    payload = json.loads(source.read_text(encoding="utf-8"))

    return PageGeometry(
        width_pt=float(payload["width_pt"]),
        height_pt=float(payload["height_pt"]),
        rects=[
            GeometryRect(x0=values[0], y0=values[1], x1=values[2], y1=values[3])
            for values in payload["rects"]
        ],
        line_count=int(payload["line_count"]),
        curve_count=int(payload["curve_count"]),
    )
