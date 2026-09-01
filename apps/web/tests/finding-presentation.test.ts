import { describe, expect, it } from "vitest";

import {
  canProposeRulePreference,
  Finding,
  findingElementLabel,
  findingLevelTransition,
  findingLifecycleState,
  findingSectionTransition,
  findingSheetTransition,
  findingSourceLabel,
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

  it("acrescenta o estado explicito e expoe a transicao de nivel", () => {
    const lifecycleFinding = finding({
      evidence: [
        "estado: morre",
        "nivel origem: -04",
        "alvo: folha=EST-0080 view=view-upper nivel=338"
      ]
    });

    expect(findingLifecycleState(lifecycleFinding)).toBe("morre");
    expect(findingElementLabel(lifecycleFinding)).toBe("Elemento P2 / MORRE");
    expect(findingLevelTransition(lifecycleFinding)).toEqual({ source: "-04", target: "338" });
  });

  it("ignora evidencia de ciclo de vida ausente ou malformada", () => {
    const malformed = finding({
      evidence: ["estado: talvez", "nivel origem: ausente", "alvo: nivel=ausente"]
    });

    expect(findingLifecycleState(malformed)).toBeNull();
    expect(findingElementLabel(malformed)).toBe("Elemento P2");
    expect(findingLevelTransition(malformed)).toBeNull();
  });

  it("expoe a transicao de secao e as folhas das duas pontas", () => {
    const sectionFinding = finding({
      type: "attention",
      severity: "medium",
      element_code: "P27",
      evidence: [
        "codigo: P27",
        "nivel origem: 680",
        "origem: folha=EST-0100-A view=view-lower nivel=680 secao=20x40 cm",
        "alvo: folha=EST-0200-A view=view-upper nivel=780 secao=20x20 cm",
        "unidade: cm",
        "secoes: 20x40 cm -> 20x20 cm"
      ]
    });

    expect(findingSectionTransition(sectionFinding)).toEqual({
      source: "20x40 cm",
      target: "20x20 cm",
      unit: "cm"
    });
    expect(findingSheetTransition(sectionFinding)).toEqual({
      source: "EST-0100-A",
      target: "EST-0200-A"
    });
    expect(findingLevelTransition(sectionFinding)).toEqual({ source: "680", target: "780" });
    expect(findingElementLabel(sectionFinding)).toBe("Elemento P27 / 20x40 cm -> 20x20 cm");
  });

  it("nunca completa a unidade ausente por convencao", () => {
    const withoutUnit = finding({
      element_code: "P27",
      evidence: ["unidade: ausente", "secoes: 20x40 -> 20x20"]
    });

    expect(findingSectionTransition(withoutUnit)?.unit).toBeNull();
  });

  it("ignora evidencia de secao ausente ou malformada", () => {
    const malformed = finding({
      evidence: ["secoes: 20x40", "origem: folha=ausente", "alvo: folha=ausente"]
    });

    expect(findingSectionTransition(malformed)).toBeNull();
    expect(findingSheetTransition(malformed)).toBeNull();
    expect(findingElementLabel(malformed)).toBe("Elemento P2");
  });

  it("mantem inconsistencia automatica pendente como hipotese", () => {
    expect(shouldShowHypothesisNotice(finding())).toBe(true);
    expect(shouldShowHypothesisNotice(finding({ status: "confirmed" }))).toBe(false);
    expect(shouldShowHypothesisNotice(finding({ origin: "human" }))).toBe(false);
  });

  it("distingue findings produzidos por crop visual", () => {
    expect(findingSourceLabel(finding({ source_layer: "vision" }))).toBe("VISAO / CROP");
    expect(findingSourceLabel(finding({ source_layer: "deterministic" }))).toBeNull();
  });

  it("so propoe preferencia para achado automatico rejeitado e rastreavel", () => {
    const eligible = finding({
      status: "rejected",
      rejection_reason: "Nao se aplica.",
      rule_id: "forms.sheet.has_main_view"
    });

    expect(canProposeRulePreference(eligible)).toBe(true);
    expect(canProposeRulePreference(finding({ ...eligible, status: "pending" }))).toBe(false);
    expect(canProposeRulePreference(finding({ ...eligible, origin: "human" }))).toBe(false);
    expect(canProposeRulePreference(finding({ ...eligible, rule_id: null }))).toBe(false);
    expect(canProposeRulePreference(finding({ ...eligible, suppressed: true }))).toBe(false);
  });
});
