import { afterEach, describe, expect, it, vi } from "vitest";

import { runSheetVisionAudit, TrussApiError } from "@/lib/projects-api";

describe("projects API errors", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("presents FastAPI detail without exposing raw JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: "Analise visual desabilitada. Configure um teto de custo."
          }),
          { status: 409, headers: { "Content-Type": "application/json" } }
        )
      )
    );

    await expect(runSheetVisionAudit("http://localhost:8000", "sheet-1")).rejects.toThrow(
      "Analise visual desabilitada. Configure um teto de custo."
    );
  });

  it("preserves typed recovery detail for actionable errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: {
              code: "OPERATION_INTERRUPTED",
              message: "O processamento foi interrompido.",
              action: "Continue a partir do checkpoint seguro.",
              retryable: true,
              operation_id: "operation-1"
            }
          }),
          { status: 500, headers: { "Content-Type": "application/json" } }
        )
      )
    );

    try {
      await runSheetVisionAudit("http://localhost:8000", "sheet-1");
      throw new Error("expected rejection");
    } catch (error) {
      expect(error).toBeInstanceOf(TrussApiError);
      expect((error as TrussApiError).detail.operation_id).toBe("operation-1");
      expect((error as TrussApiError).detail.retryable).toBe(true);
    }
  });
});
