import { afterEach, describe, expect, it, vi } from "vitest";

import { runSheetVisionAudit } from "@/lib/projects-api";

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
});
