import { describe, expect, it } from "vitest";

import {
  Finding,
  findingElementLabel,
  shouldShowHypothesisNotice
} from "@/lib/projects-api";


function finding(overrides: Partial<Finding> = {}): Finding {
  return {
    id: "f1",
    audit_run_id: "a1",
    sheet_id: "s1",
    document_id: "d1",
    project_id: "p1",
    revision_id: "r1",
    category: "cross_sheet_consistency",
    type: "inconsistency",
    description: "P2 nao foi localizado nos detalhamentos.",
    severity: "high",
    confidence: 0.76,
    bbox: { x0: 10, y0: 20, x1: 30, y1: 40 },
    evidence: [],
    origin: "ai",
    status: "pending",
    rejection_reason: null,
    created_at: "2026-08-31T00:00:00Z",
    updated_at: "2026-08-31T00:00:00Z",
    element_code: "P2",
    registry_hash: "registry-123",
    ...overrides
  };
}


describe("apresentacao de findings F3", () => {
  it("mostra o codigo tecnico como referencia compacta", () => {
    expect(findingElementLabel(finding())).toBe("Elemento P2");
    expect(findingElementLabel(finding({ element_code: null }))).toBeNull();
  });

  it("mantem inconsistencia automatica pendente como hipotese", () => {
    expect(shouldShowHypothesisNotice(finding())).toBe(true);
    expect(shouldShowHypothesisNotice(finding({ status: "confirmed" }))).toBe(false);
    expect(shouldShowHypothesisNotice(finding({ origin: "human" }))).toBe(false);
  });
});
