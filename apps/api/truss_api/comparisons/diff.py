from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fitz


DIFF_SCALE = 0.5
PIXEL_THRESHOLD = 28
TILE_SIZE = 16
MIN_CHANGED_PIXELS_PER_TILE = 8
REGION_PADDING_PT = 4.0


@dataclass(frozen=True)
class RasterDiff:
    changed_ratio: float
    regions: list[dict[str, object]]


class RasterReadError(RuntimeError):
    """Expected failure while opening or rendering a local PDF source."""


def _render_gray(path: Path, page_index: int) -> tuple[int, int, bytes]:
    try:
        document = fitz.open(path)
        try:
            page = document.load_page(page_index)
            pixmap = page.get_pixmap(
                matrix=fitz.Matrix(DIFF_SCALE, DIFF_SCALE),
                colorspace=fitz.csGRAY,
                alpha=False,
            )
            return pixmap.width, pixmap.height, bytes(pixmap.samples)
        finally:
            document.close()
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as error:
        raise RasterReadError(str(error)) from error


def _components(active: set[tuple[int, int]]) -> list[list[tuple[int, int]]]:
    pending = set(active)
    result: list[list[tuple[int, int]]] = []
    while pending:
        seed = pending.pop()
        stack = [seed]
        component = [seed]
        while stack:
            x, y = stack.pop()
            for next_y in range(y - 1, y + 2):
                for next_x in range(x - 1, x + 2):
                    candidate = (next_x, next_y)
                    if candidate in pending:
                        pending.remove(candidate)
                        stack.append(candidate)
                        component.append(candidate)
        result.append(component)
    return result


def compare_rasters(base: dict[str, Any], target: dict[str, Any], data_dir: Path) -> RasterDiff:
    base_width, base_height, base_samples = _render_gray(
        data_dir / str(base["stored_file_path"]), int(base["page_index"])
    )
    target_width, target_height, target_samples = _render_gray(
        data_dir / str(target["stored_file_path"]), int(target["page_index"])
    )
    if (base_width, base_height) != (target_width, target_height):
        raise ValueError("Raster dimensions differ")

    tile_counts: dict[tuple[int, int], int] = {}
    changed_pixels = 0
    for index, (base_value, target_value) in enumerate(zip(base_samples, target_samples, strict=True)):
        if abs(base_value - target_value) < PIXEL_THRESHOLD:
            continue
        changed_pixels += 1
        x = index % base_width
        y = index // base_width
        key = (x // TILE_SIZE, y // TILE_SIZE)
        tile_counts[key] = tile_counts.get(key, 0) + 1

    active = {
        tile for tile, count in tile_counts.items() if count >= MIN_CHANGED_PIXELS_PER_TILE
    }
    regions: list[dict[str, object]] = []
    for component in _components(active):
        min_tile_x = min(tile[0] for tile in component)
        min_tile_y = min(tile[1] for tile in component)
        max_tile_x = max(tile[0] for tile in component)
        max_tile_y = max(tile[1] for tile in component)
        x0 = max(0.0, min_tile_x * TILE_SIZE / DIFF_SCALE - REGION_PADDING_PT)
        y0 = max(0.0, min_tile_y * TILE_SIZE / DIFF_SCALE - REGION_PADDING_PT)
        x1 = min(
            float(base["width_pt"]),
            (max_tile_x + 1) * TILE_SIZE / DIFF_SCALE + REGION_PADDING_PT,
        )
        y1 = min(
            float(base["height_pt"]),
            (max_tile_y + 1) * TILE_SIZE / DIFF_SCALE + REGION_PADDING_PT,
        )
        component_pixels = sum(tile_counts[tile] for tile in component)
        component_area = max(1, len(component) * TILE_SIZE * TILE_SIZE)
        regions.append(
            {
                "base_bbox": {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
                "target_bbox": {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
                "changed_pixel_count": component_pixels,
                "changed_ratio": min(1.0, component_pixels / component_area),
            }
        )
    regions.sort(
        key=lambda region: (
            -int(region["changed_pixel_count"]),
            float(region["base_bbox"]["y0"]),  # type: ignore[index]
            float(region["base_bbox"]["x0"]),  # type: ignore[index]
        )
    )
    return RasterDiff(
        changed_ratio=changed_pixels / max(1, base_width * base_height),
        regions=regions,
    )


def full_page_region(base: dict[str, Any], target: dict[str, Any]) -> dict[str, object]:
    return {
        "base_bbox": {
            "x0": 0.0,
            "y0": 0.0,
            "x1": float(base["width_pt"]),
            "y1": float(base["height_pt"]),
        },
        "target_bbox": {
            "x0": 0.0,
            "y0": 0.0,
            "x1": float(target["width_pt"]),
            "y1": float(target["height_pt"]),
        },
        "changed_pixel_count": 0,
        "changed_ratio": 1.0,
    }
