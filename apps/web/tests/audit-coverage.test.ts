import { describe, expect, it } from "vitest";

import { auditCoverageSummary } from "@/lib/projects-api";
import type { AuditCoverage } from "@/lib/projects-api";

function coverage(overrides: Partial<AuditCoverage> = {}): AuditCoverage {
  return {
    evaluated: 15,
    passed: 13,
    failed: 0,
    unknown: 0,
    not_applicable: 2,
    skipped: 0,
    technical_scopes: ["formas"],
    covered_scopes: ["formas"],
    uncovered_scopes: [],
    ...overrides,
  };
}

describe("auditCoverageSummary", () => {
  it("says what was checked so an empty result is not read as untested", () => {
    const summary = auditCoverageSummary(coverage());

    expect(summary).toContain("15");
    expect(summary).toContain("13");
  });

  it("reports that nothing was checked instead of implying conformity", () => {
    const summary = auditCoverageSummary(coverage({ evaluated: 0, passed: 0, not_applicable: 0 }));

    expect(summary).toMatch(/nenhuma regra/i);
    expect(summary).not.toMatch(/conforme|aprovad/i);
  });

  it("surfaces what could not be verified rather than hiding it", () => {
    const summary = auditCoverageSummary(coverage({ unknown: 3 }));

    expect(summary).toMatch(/3 nao verificavel/i);
  });

  it("surfaces technical scopes that have no rule pack", () => {
    const summary = auditCoverageSummary(
      coverage({
        technical_scopes: ["formas", "armaduras"],
        covered_scopes: ["formas"],
        uncovered_scopes: ["armaduras"],
      }),
    );

    expect(summary).toMatch(/sem regras para armaduras/i);
  });

  it("returns nothing when there is no coverage to report", () => {
    expect(auditCoverageSummary(null)).toBe("");
  });
});
