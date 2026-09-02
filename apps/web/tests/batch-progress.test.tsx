import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BatchProgress, batchPollInterval } from "@/components/operations/batch-progress";
import type { BatchRunSummary } from "@/lib/projects-api";


function batch(overrides: Partial<BatchRunSummary> = {}): BatchRunSummary {
  return {
    id: "batch-1",
    project_id: "project-1",
    revision_id: "revision-1",
    mode: "local_deterministic",
    status: "completed",
    phase: "completed",
    config: {},
    input_fingerprint: "fingerprint",
    pipeline_version: "batch-v0.1",
    total_sheets: 84,
    counts: {},
    phase_counts: {
      sheet_map: { completed: 84 },
      deterministic_audit: { completed: 84 },
    },
    cancel_requested_at: null,
    created_at: "2026-09-02T00:00:00Z",
    started_at: "2026-09-02T00:00:01Z",
    completed_at: "2026-09-02T00:10:00Z",
    updated_at: "2026-09-02T00:10:00Z",
    ...overrides,
  };
}

describe("BatchProgress", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("slows polling while the application is in the background", () => {
    expect(batchPollInterval(false)).toBe(1000);
    expect(batchPollInterval(true)).toBe(5000);
  });

  it("keeps the 84-sheet result compact above the viewer", async () => {
    const completed = batch();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify([completed])))
    );

    render(
      <BatchProgress
        apiBaseUrl="http://localhost:8000"
        initialBatch={completed}
        revisionId="revision-1"
      />
    );

    expect(screen.getByText("Processamento concluído")).toBeInTheDocument();
    expect(screen.getByText("84/84 folhas")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "84");
  });

  it("requests cooperative cancellation without hiding progress", async () => {
    const running = batch({
      status: "running",
      phase: "sheet_map",
      completed_at: null,
      phase_counts: {
        sheet_map: { completed: 12, running: 1, queued: 71 },
        deterministic_audit: { queued: 84 },
      },
    });
    const cancelling = batch({
      ...running,
      status: "cancel_requested",
      cancel_requested_at: "2026-09-02T00:02:00Z",
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify([running])))
      .mockResolvedValueOnce(new Response(JSON.stringify(cancelling)));
    vi.stubGlobal("fetch", fetchMock);

    render(
      <BatchProgress
        apiBaseUrl="http://localhost:8000"
        initialBatch={running}
        revisionId="revision-1"
      />
    );
    fireEvent.click(screen.getByRole("button", { name: "Parar após a etapa atual" }));

    await waitFor(() => expect(screen.getByText("Parando após a etapa atual")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/batch-runs/batch-1/cancel",
      expect.objectContaining({ method: "POST" })
    );
    expect(screen.getByTestId("batch-progress")).toBeInTheDocument();
  });

  it("opens the affected sheet from an isolated failure", async () => {
    const errored = batch({
      status: "completed_with_errors",
      phase_counts: {
        sheet_map: { completed: 84 },
        deterministic_audit: { completed: 83, failed: 1 },
      },
    });
    const onOpenSheet = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(new Response(JSON.stringify([errored])))
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify([
              {
                id: "item-1",
                batch_run_id: "batch-1",
                sheet_id: "sheet-7",
                sheet_label: "Folha 07",
                sheet_number: 7,
                phase: "deterministic_audit",
                sequence: 7,
                status: "failed",
                operation_id: null,
                attempt_count: 1,
                error_code: "FIXTURE_FAILURE",
                error_message: "Falha isolada.",
                created_at: "2026-09-02T00:00:00Z",
                started_at: "2026-09-02T00:00:01Z",
                completed_at: "2026-09-02T00:00:02Z",
                updated_at: "2026-09-02T00:00:02Z",
              },
            ])
          )
        )
    );

    render(
      <BatchProgress
        apiBaseUrl="http://localhost:8000"
        initialBatch={errored}
        onOpenSheet={onOpenSheet}
        revisionId="revision-1"
      />
    );
    fireEvent.click(screen.getByRole("button", { name: "Mostrar detalhes" }));
    fireEvent.click(await screen.findByRole("button", { name: /Folha 07.*Falha isolada/i }));

    expect(onOpenSheet).toHaveBeenCalledWith("sheet-7");
  });
});
