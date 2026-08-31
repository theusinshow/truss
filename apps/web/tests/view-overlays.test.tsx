import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ViewOverlays } from "@/components/canvas/view-overlays";
import type { SheetView } from "@/lib/projects-api";

function view(overrides: Partial<SheetView> = {}): SheetView {
  return {
    id: "v1",
    parent_view_id: null,
    view_kind: "plan",
    view_role: null,
    identifier: "1",
    title_raw: "PLANTA DE FORMAS - TÉRREO",
    title: null,
    declared_scale_raw: "ESCALA 1:50",
    declared_scale: "1:50",
    level_raw: "-04",
    level: null,
    x0: 10,
    y0: 20,
    x1: 210,
    y1: 220,
    confidence: 0.9,
    provenance: "deterministic/forms-view-v1",
    technical_scope: "formas",
    ...overrides,
  };
}

describe("ViewOverlays", () => {
  it("renders one inspectable overlay per view with its label", () => {
    render(<ViewOverlays activeViewId={null} onSelect={vi.fn()} views={[view()]} />);

    const overlay = screen.getByRole("button", { name: /PLANTA DE FORMAS - TÉRREO/ });
    expect(overlay).toBeTruthy();
    expect(overlay.textContent).toContain("1:50");
  });

  it("marks the active view so the finding can be located in it", () => {
    render(<ViewOverlays activeViewId="v1" onSelect={vi.fn()} views={[view()]} />);

    expect(screen.getByRole("button", { name: /PLANTA/ }).dataset.active).toBe("true");
  });

  it("labels a view without title by its kind instead of showing nothing", () => {
    render(
      <ViewOverlays activeViewId={null} onSelect={vi.fn()} views={[view({ title_raw: null })]} />,
    );

    expect(screen.getByRole("button", { name: /planta/i })).toBeTruthy();
  });

  it("shows the sheet's own wording when the scale is not numeric", () => {
    render(
      <ViewOverlays
        activeViewId={null}
        onSelect={vi.fn()}
        views={[
          view({
            view_kind: "perspective",
            title_raw: "PERSPECTIVA",
            declared_scale_raw: "ESCALA REPRESENTATIVA",
            declared_scale: null,
          }),
        ]}
      />,
    );

    expect(screen.getByRole("button", { name: /PERSPECTIVA/ }).textContent).toContain(
      "ESCALA REPRESENTATIVA",
    );
  });

  it("shows the raw level, never a normalized guess", () => {
    render(<ViewOverlays activeViewId={null} onSelect={vi.fn()} views={[view()]} />);

    expect(screen.getByRole("button", { name: /PLANTA/ }).textContent).toContain("-04");
  });

  it("positions the overlay from the pdf points of the view", () => {
    render(<ViewOverlays activeViewId={null} onSelect={vi.fn()} views={[view()]} />);

    const overlay = screen.getByRole("button", { name: /PLANTA/ });

    expect(overlay.style.left).toBe("20px");
    expect(overlay.style.top).toBe("40px");
    expect(overlay.style.width).toBe("400px");
    expect(overlay.style.height).toBe("400px");
  });

  it("renders nothing when the sheet map has no views", () => {
    const { container } = render(
      <ViewOverlays activeViewId={null} onSelect={vi.fn()} views={[]} />,
    );

    expect(container.querySelectorAll("button")).toHaveLength(0);
  });
});
