import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LearningCenter } from "@/components/learning/learning-center";
import type { LearningProposal, RulePreference } from "@/lib/projects-api";


const source = {
  finding_id: "finding-1",
  project_id: "project-1",
  project_name: "Edificio Centro",
  revision_id: "revision-1",
  revision_code: "R03",
  document_id: "document-1",
  document_name: "formas.pdf",
  sheet_id: "sheet-1",
  sheet_label: "Folha 1",
  sheet_number: 1,
  sheet_code: "EST-0010-A",
  bbox: { x0: 10, y0: 20, x1: 110, y1: 120 },
  description: "Vista principal ausente.",
  rejection_reason: "Padrao do escritorio."
};

const preferences: RulePreference[] = [
  {
    id: "preference-active",
    scope: "sheet_type",
    sheet_type: "formas",
    rule_id: "forms.sheet.has_main_view",
    action: "suppress",
    reason: "Esta familia nao usa vista principal.",
    source_finding_id: "finding-1",
    created_at: "2026-09-01T12:00:00Z",
    revoked_at: null,
    active: true,
    source
  },
  {
    id: "preference-revoked",
    scope: "sheet_type",
    sheet_type: "locacao",
    rule_id: "location.sheet.has_axis",
    action: "suppress",
    reason: "Decisao antiga.",
    source_finding_id: "finding-2",
    created_at: "2026-08-30T12:00:00Z",
    revoked_at: "2026-09-01T10:00:00Z",
    active: false,
    source: { ...source, finding_id: "finding-2", sheet_id: "sheet-2" }
  }
];

function proposal(overrides: Partial<LearningProposal> = {}): LearningProposal {
  return {
    stable_key: "a".repeat(64),
    proposal_kind: "suppress_rule",
    state: "pending",
    effect: "suppresses_findings",
    policy_version: "learning-policy-v0.1",
    sheet_type: "formas",
    rule_id: "forms.sheet.has_main_view",
    normalized_description: null,
    evidence_count: 2,
    confirmed_count: 0,
    rejected_count: 2,
    manual_count: 0,
    distinct_sheet_count: 2,
    distinct_revision_count: 2,
    distinct_project_count: 1,
    observed_ratio: 1,
    threshold: { minimum_evidence: 2, minimum_sheets: 2, minimum_ratio: 0.75 },
    threshold_reached: true,
    active_preference_id: null,
    evidence: [
      {
        ...source,
        signal_kind: "rejected",
        sheet_type: "formas",
        rule_id: "forms.sheet.has_main_view",
        finding_status: "rejected",
        created_at: "2026-09-01T12:00:00Z"
      }
    ],
    decision: null,
    ...overrides
  };
}

function jsonResponse(value: unknown) {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { "Content-Type": "application/json" }
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("LearningCenter", () => {
  it("shows loading, empty and error states explicitly", async () => {
    const requestResolvers: Array<(response: Response) => void> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            requestResolvers.push(resolve);
          })
      )
    );

    const { unmount } = render(
      <LearningCenter apiBaseUrl="http://api" onClose={vi.fn()} onOpenEvidence={vi.fn()} />
    );
    expect(await screen.findByLabelText("Carregando aprendizado")).toBeInTheDocument();
    await waitFor(() => expect(requestResolvers).toHaveLength(2));
    requestResolvers.forEach((resolve) => resolve(jsonResponse([])));
    await waitFor(() =>
      expect(screen.getByText(/Nenhuma preferencia neste filtro/)).toBeInTheDocument()
    );
    unmount();

    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new Error("API indisponivel"))));
    render(
      <LearningCenter apiBaseUrl="http://api" onClose={vi.fn()} onOpenEvidence={vi.fn()} />
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("API indisponivel");
  });

  it("filters preference history and opens the exact PDF evidence", async () => {
    const onOpenEvidence = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const url = String(input);
        return url.includes("/rule-preferences")
          ? jsonResponse(preferences)
          : jsonResponse([proposal()]);
      })
    );

    render(
      <LearningCenter
        apiBaseUrl="http://api"
        onClose={vi.fn()}
        onOpenEvidence={onOpenEvidence}
      />
    );

    expect((await screen.findAllByText("forms.sheet.has_main_view")).length).toBeGreaterThan(0);
    expect(screen.queryByText("location.sheet.has_axis")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Revogadas" }));
    expect((await screen.findAllByText("location.sheet.has_axis")).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: /EST-0010-A/ }));
    expect(onOpenEvidence).toHaveBeenCalledWith(
      expect.objectContaining({ finding_id: "finding-2", sheet_id: "sheet-2" })
    );
  });

  it("revokes an active preference and refreshes its visible history", async () => {
    let currentPreferences = [preferences[0]];
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/rule-preferences") && init?.method === "DELETE") {
        currentPreferences = [{ ...preferences[0], active: false, revoked_at: "2026-09-01T14:00:00Z" }];
        return jsonResponse(currentPreferences[0]);
      }
      return url.includes("/rule-preferences")
        ? jsonResponse(currentPreferences)
        : jsonResponse([]);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <LearningCenter apiBaseUrl="http://api" onClose={vi.fn()} onOpenEvidence={vi.fn()} />
    );
    fireEvent.click(await screen.findByRole("button", { name: "Revogar preferencia" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "http://api/rule-preferences/preference-active",
        expect.objectContaining({ method: "DELETE" })
      )
    );
    expect(await screen.findByText(/Nenhuma preferencia neste filtro/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Revogadas" }));
    expect(await screen.findByRole("button", { name: "Reativar preferencia" })).toBeInTheDocument();
  });

  it("requires an explicit reason before approving a proposal", async () => {
    let currentProposal = proposal();
    const fetchMock = vi.fn(
      async (input: string | URL | Request, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("/rule-preferences")) {
          return jsonResponse([]);
        }
        if (init?.method === "POST") {
          currentProposal = proposal({
            state: "approved",
            decision: {
              id: "decision-1",
              stable_key: currentProposal.stable_key,
              proposal_kind: "suppress_rule",
              decision: "approved",
              reason: "Padrao confirmado pelo proprietario.",
              policy_version: "learning-policy-v0.1",
              preference_id: "preference-1",
              preference_active: true,
              evidence_count: 2,
              created_at: "2026-09-01T13:00:00Z",
              revoked_at: null,
              active: true
            }
          });
          return jsonResponse(currentProposal);
        }
        return jsonResponse([currentProposal]);
      }
    );
    vi.stubGlobal("fetch", fetchMock);

    render(
      <LearningCenter apiBaseUrl="http://api" onClose={vi.fn()} onOpenEvidence={vi.fn()} />
    );

    fireEvent.click(await screen.findByRole("tab", { name: /Propostas/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Aprovar" }));
    const save = screen.getByRole("button", { name: "Salvar decisao" });
    expect(save).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Justificativa"), {
      target: { value: "Padrao confirmado pelo proprietario." }
    });
    fireEvent.click(save);

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/learning/proposals/"),
        expect.objectContaining({ method: "POST" })
      )
    );
    expect(await screen.findByText("Decisao aprovada")).toBeInTheDocument();
  });
});
