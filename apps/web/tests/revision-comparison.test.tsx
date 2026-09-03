import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RevisionComparisonPanel } from "@/components/comparisons/revision-comparison";
import type {
  ComparisonSheet,
  Revision,
  RevisionComparison,
} from "@/lib/projects-api";


const revisions: Revision[] = [
  {
    id: "revision-base",
    project_id: "project-1",
    revision_code: "R01",
    notes: "",
    source_type: "manual",
    original_filename: null,
    original_file_path: null,
    content_hash: null,
    created_at: "2026-09-01T00:00:00Z",
  },
  {
    id: "revision-target",
    project_id: "project-1",
    revision_code: "R02",
    notes: "",
    source_type: "manual",
    original_filename: null,
    original_file_path: null,
    content_hash: null,
    created_at: "2026-09-02T00:00:00Z",
  },
];

function sheet(id: string, revisionId: string, code: string | null): ComparisonSheet {
  return {
    id,
    document_id: `document-${id}`,
    revision_id: revisionId,
    sheet_number: 1,
    page_index: 0,
    label: "Folha 1",
    sheet_code: code,
    sheet_code_raw: code,
    width_pt: 1000,
    height_pt: 800,
    rotation: 0,
    source_status: "AVAILABLE",
  };
}

const baseSheet = sheet("sheet-base", "revision-base", "EST-0010-A");
const targetSheet = sheet("sheet-target", "revision-target", "EST-0010-A");

function comparison(overrides: Partial<RevisionComparison> = {}): RevisionComparison {
  return {
    id: "comparison-1",
    project_id: "project-1",
    base_revision_id: "revision-base",
    target_revision_id: "revision-target",
    base_revision_code: "R01",
    target_revision_code: "R02",
    input_fingerprint: "abcdef1234567890",
    pipeline_version: "revision-comparison-v0.2",
    status: "completed",
    counts: {
      total: 1,
      changed: 1,
      identical: 0,
      added: 0,
      removed: 0,
      ambiguous: 0,
      unavailable: 0,
    },
    created_at: "2026-09-02T12:00:00Z",
    pairs: [
      {
        id: "pair-1",
        sequence: 0,
        base_sheet: baseSheet,
        target_sheet: targetSheet,
        status: "changed",
        match_method: "sheet_code",
        match_confidence: 1,
        pairing_override_id: null,
        summary: "1 região graficamente alterada localizada.",
        changed_ratio: 0.012,
        regions: [
          {
            id: "region-1",
            region_index: 0,
            base_bbox: { x0: 100, y0: 120, x1: 240, y1: 260 },
            target_bbox: { x0: 100, y0: 120, x1: 240, y1: 260 },
            changed_pixel_count: 120,
            changed_ratio: 0.25,
          },
        ],
        delta_status: "completed",
        delta_counts: {
          total: 2,
          text: { total: 1, added: 0, removed: 0, modified: 1, moved: 0 },
          vector: { total: 1, added: 0, removed: 0, modified: 0, moved: 1 },
        },
        delta_truncated: false,
        delta_summary: "1 delta de texto e 1 delta vetorial.",
        deltas: [
          {
            id: "delta-text-1",
            delta_index: 0,
            layer: "text",
            change_type: "modified",
            match_evidence: "mutual_spatial_text_similarity",
            similarity: 0.94,
            before_value: "VIGA V1 20x40",
            after_value: "VIGA V1 20x45",
            base_bbox: { x0: 300, y0: 200, x1: 390, y1: 215 },
            target_bbox: { x0: 300, y0: 200, x1: 390, y1: 215 },
            details: {},
          },
          {
            id: "delta-vector-1",
            delta_index: 1,
            layer: "vector",
            change_type: "moved",
            match_evidence: "unique_vector_geometry_and_style",
            similarity: 1,
            before_value: "linha · 1.00 pt",
            after_value: "linha · 1.00 pt",
            base_bbox: { x0: 420, y0: 300, x1: 520, y1: 301 },
            target_bbox: { x0: 440, y0: 300, x1: 540, y1: 301 },
            details: {},
          },
        ],
      },
    ],
    ...overrides,
  };
}

function jsonResponse(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
    }
  );
  vi.stubGlobal("matchMedia", () => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("RevisionComparisonPanel", () => {
  it("keeps the PDF central and exposes split, overlay and blink modes", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(comparison(), 201)));

    render(
      <RevisionComparisonPanel
        apiBaseUrl="http://api"
        initialTargetRevisionId="revision-target"
        projectId="project-1"
        revisions={revisions}
      />
    );

    expect(await screen.findByText("R01 → R02")).toBeInTheDocument();
    expect(screen.getByText("Alterada 1")).toBeInTheDocument();
    expect(screen.getAllByAltText(/Antes|Depois/)).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "Alteração 1" })).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: "Sobrepor revisões" }));
    expect(screen.getByText("Sobreposição · antes + depois")).toBeInTheDocument();
    expect(screen.getAllByAltText(/Sobreposição/)).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: "Alternar antes e depois" }));
    expect(screen.getByRole("button", { name: "Mostrar depois" })).toBeInTheDocument();
  });

  it("promotes a selected graphic change only after an explicit action", async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      if (String(input).includes("/sheets/sheet-target/findings") && init?.method === "POST") {
        return jsonResponse({ id: "finding-1" }, 201);
      }
      return jsonResponse(comparison(), 201);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <RevisionComparisonPanel
        apiBaseUrl="http://api"
        initialTargetRevisionId="revision-target"
        projectId="project-1"
        revisions={revisions}
      />
    );

    fireEvent.click((await screen.findAllByRole("button", { name: "Alteração 1" }))[0]);
    const createButton = await screen.findByRole("button", { name: "Criar achado manual" });
    await waitFor(() => expect(createButton).toBeEnabled());
    fireEvent.click(createButton);
    expect(await screen.findByText("Achado manual criado na revisão-alvo.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "http://api/sheets/sheet-target/findings",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining('"category":"revision_comparison"'),
      })
    );
  });

  it("filters native layers and shows before/after evidence", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(comparison(), 201)));

    render(
      <RevisionComparisonPanel
        apiBaseUrl="http://api"
        initialTargetRevisionId="revision-target"
        projectId="project-1"
        revisions={revisions}
      />
    );

    expect(await screen.findByText("VIGA V1 20x40")).toBeInTheDocument();
    expect(screen.getByText("VIGA V1 20x45")).toBeInTheDocument();
    expect(screen.getByText("Texto / Modificado")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Texto" })).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(screen.getByRole("button", { name: "Texto" }));
    expect(screen.queryByRole("button", { name: /Inspecionar Texto modificado/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Texto" })).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(screen.getByRole("button", { name: /Inspecionar Vetor movido/ }));
    expect(screen.getByText("Vetor / Movido")).toBeInTheDocument();
  });

  it("does not render missing sources or register incompatible page geometry", async () => {
    const unavailable = comparison({
      counts: { total: 1, changed: 0, identical: 0, added: 0, removed: 0, ambiguous: 0, unavailable: 1 },
      pairs: [
        {
          ...comparison().pairs[0],
          status: "unavailable",
          summary: "A fonte PDF de um dos lados não está disponível.",
          regions: [],
        },
      ],
    });
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(unavailable, 201)));

    const { unmount } = render(
      <RevisionComparisonPanel
        apiBaseUrl="http://api"
        initialTargetRevisionId="revision-target"
        projectId="project-1"
        revisions={revisions}
      />
    );

    expect(await screen.findByText("Fonte PDF indisponível")).toBeInTheDocument();
    expect(screen.queryByAltText(/Antes|Depois/)).not.toBeInTheDocument();
    unmount();

    const geometryChange = comparison({
      pairs: [
        {
          ...comparison().pairs[0],
          target_sheet: { ...targetSheet, width_pt: 1100 },
        },
      ],
    });
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(geometryChange, 201)));
    render(
      <RevisionComparisonPanel
        apiBaseUrl="http://api"
        initialTargetRevisionId="revision-target"
        projectId="project-1"
        revisions={revisions}
      />
    );

    expect(await screen.findByRole("button", { name: "Sobrepor revisões" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Alternar antes e depois" })).toBeDisabled();
  });

  it("keeps blink manual when reduced motion is requested", async () => {
    vi.stubGlobal("matchMedia", () => ({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    const intervalSpy = vi.spyOn(window, "setInterval");
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(comparison(), 201)));

    render(
      <RevisionComparisonPanel
        apiBaseUrl="http://api"
        initialTargetRevisionId="revision-target"
        projectId="project-1"
        revisions={revisions}
      />
    );

    fireEvent.click(await screen.findByRole("button", { name: "Alternar antes e depois" }));
    expect(await screen.findByRole("button", { name: "Mostrar depois" })).toBeInTheDocument();
    expect(intervalSpy).not.toHaveBeenCalledWith(expect.any(Function), 850);
    fireEvent.click(screen.getByRole("button", { name: "Mostrar depois" }));
    expect(screen.getByRole("button", { name: "Mostrar antes" })).toBeInTheDocument();
  });

  it("turns an ambiguous pair into a manual, revocable pairing", async () => {
    const ambiguous = comparison({
      status: "completed_with_limits",
      counts: {
        total: 2,
        changed: 0,
        identical: 0,
        added: 0,
        removed: 0,
        ambiguous: 2,
        unavailable: 0,
      },
      pairs: [
        {
          id: "base-only",
          sequence: 0,
          base_sheet: { ...baseSheet, sheet_code: null, sheet_code_raw: null },
          target_sheet: null,
          status: "ambiguous",
          match_method: "unmatched",
          match_confidence: 0,
          pairing_override_id: null,
          summary: "Identidade inconclusiva.",
          changed_ratio: 0,
          regions: [],
          delta_status: "not_applicable",
          delta_counts: {},
          delta_truncated: false,
          delta_summary: "Sem par confiável.",
          deltas: [],
        },
        {
          id: "target-only",
          sequence: 1,
          base_sheet: null,
          target_sheet: { ...targetSheet, sheet_code: null, sheet_code_raw: null },
          status: "ambiguous",
          match_method: "unmatched",
          match_confidence: 0,
          pairing_override_id: null,
          summary: "Identidade inconclusiva.",
          changed_ratio: 0,
          regions: [],
          delta_status: "not_applicable",
          delta_counts: {},
          delta_truncated: false,
          delta_summary: "Sem par confiável.",
          deltas: [],
        },
      ],
    });
    const paired = comparison({
      id: "comparison-2",
      pairs: [
        {
          ...comparison().pairs[0],
          match_method: "manual",
          pairing_override_id: "override-1",
        },
      ],
    });
    let pairingSaved = false;
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/comparison-pairings") && init?.method === "POST") {
        pairingSaved = true;
        return jsonResponse({ id: "override-1", active: true }, 201);
      }
      return jsonResponse(pairingSaved ? paired : ambiguous, 201);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <RevisionComparisonPanel
        apiBaseUrl="http://api"
        initialTargetRevisionId="revision-target"
        projectId="project-1"
        revisions={revisions}
      />
    );

    const pairButton = await screen.findByRole("button", { name: "Vincular folhas" });
    await waitFor(() => expect(pairButton).toBeEnabled());
    fireEvent.click(pairButton);
    expect(await screen.findByText(/pareamento \/ vínculo manual/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Revogar vínculo atual" })).toBeInTheDocument();
  });
});
