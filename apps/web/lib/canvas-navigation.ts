export type Viewport = {
  x: number;
  y: number;
  zoom: number;
};

export type Point = {
  x: number;
  y: number;
};

export type Rect = {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
};

export const CANVAS_NAVIGATION = {
  minZoom: 0.15,
  defaultZoom: 1,
  maxZoom: 4,
  zoomStep: 1.2,
  renderScale: 2,
  fitPaddingPx: 48,
  duplicateOffsetPt: 24
} as const;

export function clampZoom(value: number) {
  return Math.min(CANVAS_NAVIGATION.maxZoom, Math.max(CANVAS_NAVIGATION.minZoom, value));
}

export function screenToWorld(
  point: Point,
  viewport: Viewport,
  renderScale = CANVAS_NAVIGATION.renderScale
): Point {
  return {
    x: (point.x - viewport.x) / (viewport.zoom * renderScale),
    y: (point.y - viewport.y) / (viewport.zoom * renderScale)
  };
}

export function worldToScreen(
  point: Point,
  viewport: Viewport,
  renderScale = CANVAS_NAVIGATION.renderScale
): Point {
  return {
    x: point.x * viewport.zoom * renderScale + viewport.x,
    y: point.y * viewport.zoom * renderScale + viewport.y
  };
}

export function zoomAtScreenPoint(
  viewport: Viewport,
  nextZoomValue: number,
  screenPoint: Point,
  renderScale = CANVAS_NAVIGATION.renderScale
): Viewport {
  const zoom = clampZoom(nextZoomValue);
  const worldPoint = screenToWorld(screenPoint, viewport, renderScale);

  return {
    x: screenPoint.x - worldPoint.x * zoom * renderScale,
    y: screenPoint.y - worldPoint.y * zoom * renderScale,
    zoom
  };
}

export function normalizeRect(start: Point, end: Point): Rect {
  return {
    x0: Math.min(start.x, end.x),
    y0: Math.min(start.y, end.y),
    x1: Math.max(start.x, end.x),
    y1: Math.max(start.y, end.y)
  };
}

export function rectWidth(rect: Rect) {
  return rect.x1 - rect.x0;
}

export function rectHeight(rect: Rect) {
  return rect.y1 - rect.y0;
}

export function rectsIntersect(a: Rect, b: Rect) {
  return a.x0 <= b.x1 && a.x1 >= b.x0 && a.y0 <= b.y1 && a.y1 >= b.y0;
}

export function unionRects(rects: Rect[]): Rect | null {
  if (rects.length === 0) {
    return null;
  }

  return rects.reduce(
    (acc, rect) => ({
      x0: Math.min(acc.x0, rect.x0),
      y0: Math.min(acc.y0, rect.y0),
      x1: Math.max(acc.x1, rect.x1),
      y1: Math.max(acc.y1, rect.y1)
    }),
    rects[0]
  );
}

export function viewportForBounds(
  bounds: Rect,
  viewportSize: { width: number; height: number },
  options?: {
    renderScale?: number;
    paddingPx?: number;
    maxZoom?: number;
  }
): Viewport {
  const renderScale = options?.renderScale ?? CANVAS_NAVIGATION.renderScale;
  const paddingPx = options?.paddingPx ?? CANVAS_NAVIGATION.fitPaddingPx;
  const maxZoom = options?.maxZoom ?? CANVAS_NAVIGATION.maxZoom;
  const availableWidth = Math.max(1, viewportSize.width - paddingPx * 2);
  const availableHeight = Math.max(1, viewportSize.height - paddingPx * 2);
  const boundsWidth = Math.max(1, rectWidth(bounds) * renderScale);
  const boundsHeight = Math.max(1, rectHeight(bounds) * renderScale);
  const zoom = Math.min(maxZoom, clampZoom(Math.min(availableWidth / boundsWidth, availableHeight / boundsHeight)));

  return {
    x: (viewportSize.width - rectWidth(bounds) * renderScale * zoom) / 2 - bounds.x0 * renderScale * zoom,
    y: (viewportSize.height - rectHeight(bounds) * renderScale * zoom) / 2 - bounds.y0 * renderScale * zoom,
    zoom
  };
}

export function offsetRect(rect: Rect, offset: Point): Rect {
  return {
    x0: rect.x0 + offset.x,
    y0: rect.y0 + offset.y,
    x1: rect.x1 + offset.x,
    y1: rect.y1 + offset.y
  };
}

export const MIN_VISIBLE_SHEET_PX = 80;

/**
 * Impede que a prancha seja arrastada inteiramente para fora da tela.
 * Garante que o retangulo da folha sempre intersecte o viewport em pelo menos
 * MIN_VISIBLE_SHEET_PX nos dois eixos. Aplicado ao resultado de qualquer
 * operacao que mova o viewport, nao apenas ao arrasto.
 */
export function clampViewportToSheet(
  viewport: Viewport,
  sheet: { width: number; height: number },
  viewportSize: { width: number; height: number },
  renderScale = CANVAS_NAVIGATION.renderScale
): Viewport {
  const sheetWidth = sheet.width * viewport.zoom * renderScale;
  const sheetHeight = sheet.height * viewport.zoom * renderScale;
  const marginX = Math.min(MIN_VISIBLE_SHEET_PX, sheetWidth);
  const marginY = Math.min(MIN_VISIBLE_SHEET_PX, sheetHeight);

  return {
    zoom: viewport.zoom,
    x: Math.min(
      viewportSize.width - marginX,
      Math.max(marginX - sheetWidth, viewport.x)
    ),
    y: Math.min(
      viewportSize.height - marginY,
      Math.max(marginY - sheetHeight, viewport.y)
    )
  };
}

export type WheelIntent =
  | { kind: "zoom"; factor: number }
  | { kind: "pan"; deltaX: number; deltaY: number };

/**
 * Decide se um evento de roda veio de roda de mouse ou de trackpad.
 *
 * Mapear roda para zoom sem essa distincao quebra o trackpad, que emite dezenas
 * de eventos por segundo ao rolar com dois dedos.
 */
export function wheelIntent(event: {
  deltaX: number;
  deltaY: number;
  ctrlKey: boolean;
  metaKey: boolean;
  shiftKey: boolean;
}): WheelIntent {
  // O navegador marca o gesto de pinca do trackpad com ctrlKey.
  if (event.ctrlKey || event.metaKey) {
    return { kind: "zoom", factor: Math.exp(-event.deltaY * 0.0012) };
  }

  // Deslocamento horizontal so aparece em rolagem de dois dedos.
  if (event.deltaX !== 0) {
    return { kind: "pan", deltaX: -event.deltaX, deltaY: -event.deltaY };
  }

  if (event.shiftKey) {
    return { kind: "pan", deltaX: -event.deltaY, deltaY: 0 };
  }

  return { kind: "zoom", factor: Math.exp(-event.deltaY * 0.0012) };
}
