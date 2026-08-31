import { describe, expect, it } from "vitest";

import { sheetIdentityLabel, sheetTechnicalScopesLabel, sheetTypeLabel } from "@/lib/projects-api";
import type { Sheet, SheetMap } from "@/lib/projects-api";

const sheet = { label: "Folha 13" } as Sheet;

function sheetMap(sheetCode: string | null): SheetMap {
  return {
    id: "map-1",
    sheet_id: "sheet-1",
    project_id: "p",
    revision_id: "r",
    pipeline_version: "sheetmap-v0.1",
    status: "completed",
    geometry_path: "geometry/p/r/s.json",
    sheet_code: sheetCode,
    sheet_code_raw: sheetCode,
    sheet_type: "planta_armaduras",
    paper_format: "A1",
    orientation: "paisagem",
    title_block: {},
    built_at: "2026-08-28T00:00:00+00:00",
    technical_scopes: [],
    regions: [],
    views: [],
  };
}

describe("sheetIdentityLabel", () => {
  it("prefere o codigo real do carimbo e volta ao rotulo generico sem ele", () => {
    expect(sheetIdentityLabel(sheet, sheetMap("EST-0130-A"))).toBe("EST-0130-A");
    const rawOnly = sheetMap(null);
    rawOnly.sheet_code_raw = "SES-ETE-EST-0020";
    expect(sheetIdentityLabel(sheet, rawOnly)).toBe("SES-ETE-EST-0020");
    rawOnly.sheet_code_raw = null;
    expect(sheetIdentityLabel(sheet, rawOnly)).toBe("Folha 13");
    expect(sheetIdentityLabel(sheet, null)).toBe("Folha 13");
  });
});

describe("sheetTypeLabel", () => {
  it("traduz tipos conhecidos e usa travessao para o desconhecido", () => {
    expect(sheetTypeLabel("planta_formas")).toBe("Planta de formas");
    expect(sheetTypeLabel("planta_locacao")).toBe("Planta de locação");
    expect(sheetTypeLabel("desconhecido")).toBe("—");
  });
});

describe("sheetTechnicalScopesLabel", () => {
  it("mostra todos os escopos de uma prancha mista sem esconder o tipo legado", () => {
    const mixed = sheetMap("EST-0300-A");
    mixed.technical_scopes = [
      { technical_scope: "formas", confidence: 0.92, provenance: "titulo_ou_carimbo" },
      { technical_scope: "armaduras", confidence: 0.92, provenance: "titulo_ou_carimbo" }
    ];

    expect(sheetTechnicalScopesLabel(mixed)).toBe("Formas + Armaduras");
    expect(sheetTechnicalScopesLabel(sheetMap("EST-0010-A"))).toBe("Planta de armaduras");
  });
});
