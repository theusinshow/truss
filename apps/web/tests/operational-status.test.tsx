import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OperationalStatus } from "@/components/operations/operational-status";


describe("OperationalStatus", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("stays out of the interface when local operation is healthy", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn()
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({
              app: "truss-agent",
              status: "ok",
              environment: "local",
              database: "ok",
              storage: "ok",
              interrupted_operations: 0
            })
          )
        )
        .mockResolvedValueOnce(new Response(JSON.stringify([])))
    );

    render(<OperationalStatus apiBaseUrl="http://localhost:8000" />);

    await waitFor(() => expect(screen.queryByTestId("operational-status")).not.toBeInTheDocument());
  });

  it("shows an interrupted deterministic operation and resumes it explicitly", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            app: "truss-agent",
            status: "degraded",
            environment: "local",
            database: "ok",
            storage: "ok",
            interrupted_operations: 1
          })
        )
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify([
            {
              id: "operation-1",
              kind: "deterministic_audit",
              status: "interrupted",
              checkpoint: "ready",
              attempt_count: 1,
              error_code: "OPERATION_INTERRUPTED",
              error_message: "interrupted",
              updated_at: "2026-09-02T00:00:00Z",
              resumable: true,
              payload: {}
            }
          ])
        )
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            app: "truss-agent",
            status: "degraded",
            deep: false,
            checks: [
              {
                name: "operations",
                status: "warning",
                code: "OPERATION_INTERRUPTED",
                message: "Uma operacao requer atencao.",
                action: "Continue a operacao segura."
              }
            ]
          })
        )
      )
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "operation-1", status: "completed" })))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            app: "truss-agent",
            status: "ok",
            environment: "local",
            database: "ok",
            storage: "ok",
            interrupted_operations: 0
          })
        )
      )
      .mockResolvedValueOnce(new Response(JSON.stringify([])));
    vi.stubGlobal("fetch", fetchMock);

    render(<OperationalStatus apiBaseUrl="http://localhost:8000" />);
    fireEvent.click(await screen.findByRole("button", { name: /operacao local requer atencao/i }));
    fireEvent.click(await screen.findByRole("button", { name: "Continuar" }));

    await waitFor(() => expect(screen.queryByTestId("operational-status")).not.toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/operations/operation-1/resume",
      { method: "POST" }
    );
  });
});
