import { describe, expect, it } from "vitest";

import {
  CANVAS_NAVIGATION,
  normalizeRect,
  rectsIntersect,
  screenToWorld,
  viewportForBounds,
  worldToScreen,
  zoomAtScreenPoint
} from "@/lib/canvas-navigation";

describe("canvas navigation math", () => {
  it("round-trips screen and world coordinates", () => {
    const viewport = { x: 120, y: -40, zoom: 1.5 };
    const screen = worldToScreen({ x: 30, y: 50 }, viewport);

    expect(screenToWorld(screen, viewport)).toEqual({ x: 30, y: 50 });
  });

  it("keeps the cursor anchored while zooming", () => {
    const viewport = { x: 100, y: 80, zoom: 1 };
    const cursor = { x: 320, y: 240 };
    const before = screenToWorld(cursor, viewport);
    const next = zoomAtScreenPoint(viewport, 2, cursor);
    const after = screenToWorld(cursor, next);

    expect(after.x).toBeCloseTo(before.x, 5);
    expect(after.y).toBeCloseTo(before.y, 5);
  });

  it("computes a fit viewport with padding", () => {
    const viewport = viewportForBounds(
      { x0: 0, y0: 0, x1: 200, y1: 100 },
      { width: 1000, height: 700 }
    );

    expect(viewport.zoom).toBeGreaterThan(CANVAS_NAVIGATION.defaultZoom);
    expect(viewport.x).toBeGreaterThan(0);
    expect(viewport.y).toBeGreaterThan(0);
  });

  it("normalizes marquee rectangles and detects intersections", () => {
    const marquee = normalizeRect({ x: 100, y: 100 }, { x: 20, y: 10 });

    expect(marquee).toEqual({ x0: 20, y0: 10, x1: 100, y1: 100 });
    expect(rectsIntersect(marquee, { x0: 90, y0: 90, x1: 120, y1: 120 })).toBe(true);
    expect(rectsIntersect(marquee, { x0: 110, y0: 110, x1: 120, y1: 120 })).toBe(false);
  });
});
