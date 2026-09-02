"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  Check,
  EyeOff,
  FileSearch,
  History,
  Lightbulb,
  RotateCcw,
  ShieldCheck,
  X
} from "lucide-react";

import {
  decideLearningProposal,
  EvidenceLocator,
  LearningEvidence,
  LearningProposal,
  LearningProposalState,
  listLearningProposals,
  listRulePreferences,
  reactivateRulePreference,
  revokeLearningDecision,
  revokeRulePreference,
  RulePreference,
  sheetTypeLabel
} from "@/lib/projects-api";
import { CalibrationPanel } from "@/components/learning/calibration-panel";

type LearningCenterProps = {
  apiBaseUrl: string;
  onClose: () => void;
  onOpenEvidence: (evidence: EvidenceLocator) => void;
};

type CenterTab = "preferences" | "proposals" | "calibration";
type PreferenceFilter = "active" | "revoked" | "all";
type ProposalFilter = LearningProposalState | "all";

const proposalKindLabels = {
  suppress_rule: "Silenciar regra",
  retain_rule: "Manter regra",
  draft_rule: "Candidato a checklist"
} as const;

const proposalStateLabels = {
  insufficient: "Evidencia insuficiente",
  pending: "Pendente",
  approved: "Aprovada",
  dismissed: "Descartada"
} as const;

const DATE_FORMATTER = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "short",
  timeStyle: "short"
});

function formatDate(value: string | null) {
  if (!value) {
    return "-";
  }
  return DATE_FORMATTER.format(new Date(value));
}

function proposalTitle(proposal: LearningProposal) {
  return proposal.rule_id ?? proposal.normalized_description ?? "Padrao sem titulo";
}

function StateBadge({ state }: { state: LearningProposalState }) {
  const tones: Record<LearningProposalState, string> = {
    insufficient: "border-truss-line bg-truss-base/50 text-truss-subtle",
    pending: "border-truss-warning/45 bg-truss-warning/10 text-truss-warning",
    approved: "border-truss-success/45 bg-truss-success/10 text-truss-success",
    dismissed: "border-truss-line bg-truss-panel text-truss-muted"
  };
  return (
    <span
      className={`inline-flex h-6 items-center border px-2 font-mono text-[10px] uppercase tracking-[0.06em] ${tones[state]}`}
    >
      {proposalStateLabels[state]}
    </span>
  );
}

function EvidenceButton({
  evidence,
  onOpen
}: {
  evidence: EvidenceLocator & Partial<Pick<LearningEvidence, "signal_kind">>;
  onOpen: (evidence: EvidenceLocator) => void;
}) {
  return (
    <button
      className="flex w-full items-start gap-3 border-b border-truss-line px-3 py-3 text-left transition-colors duration-150 hover:bg-truss-panel focus-visible:bg-truss-panel"
      onClick={() => onOpen(evidence)}
      type="button"
    >
      <FileSearch aria-hidden="true" className="truss-icon mt-0.5 h-4 w-4 shrink-0 text-truss-info" />
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-truss-text">
            {evidence.sheet_code ?? evidence.sheet_label}
          </span>
          {evidence.signal_kind ? (
            <span className="font-mono text-[10px] uppercase tracking-[0.06em] text-truss-subtle">
              {evidence.signal_kind}
            </span>
          ) : null}
        </span>
        <span className="mt-1 block truncate text-xs text-truss-muted">
          {evidence.project_name} / {evidence.revision_code} / {evidence.document_name}
        </span>
        <span className="mt-2 block font-mono text-[10px] uppercase tracking-[0.06em] text-truss-subtle">
          bbox {Math.round(evidence.bbox.x0)},{Math.round(evidence.bbox.y0)} → {Math.round(evidence.bbox.x1)},{Math.round(evidence.bbox.y1)} pt
        </span>
      </span>
      <span className="font-mono text-[10px] uppercase tracking-[0.06em] text-truss-info">
        abrir
      </span>
    </button>
  );
}

export function LearningCenter({ apiBaseUrl, onClose, onOpenEvidence }: LearningCenterProps) {
  const [tab, setTab] = useState<CenterTab>("preferences");
  const [preferences, setPreferences] = useState<RulePreference[]>([]);
  const [proposals, setProposals] = useState<LearningProposal[]>([]);
  const [preferenceFilter, setPreferenceFilter] = useState<PreferenceFilter>("active");
  const [proposalFilter, setProposalFilter] = useState<ProposalFilter>("pending");
  const [selectedPreferenceId, setSelectedPreferenceId] = useState("");
  const [selectedProposalKey, setSelectedProposalKey] = useState("");
  const [decisionMode, setDecisionMode] = useState<"approved" | "dismissed" | null>(null);
  const [decisionReason, setDecisionReason] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [nextPreferences, nextProposals] = await Promise.all([
      listRulePreferences(apiBaseUrl, "all"),
      listLearningProposals(apiBaseUrl, true)
    ]);
    setPreferences(nextPreferences);
    setProposals(nextProposals);
    setSelectedPreferenceId((current) =>
      nextPreferences.some((item) => item.id === current) ? current : (nextPreferences[0]?.id ?? "")
    );
    setSelectedProposalKey((current) =>
      nextProposals.some((item) => item.stable_key === current)
        ? current
        : (nextProposals[0]?.stable_key ?? "")
    );
  }, [apiBaseUrl]);

  useEffect(() => {
    let mounted = true;
    const frame = window.requestAnimationFrame(() => {
      void refresh()
        .catch((loadError) => {
          if (mounted) {
            setError(
              loadError instanceof Error ? loadError.message : "Falha ao carregar aprendizado."
            );
          }
        })
        .finally(() => {
          if (mounted) {
            setIsLoading(false);
          }
        });
    });
    return () => {
      mounted = false;
      window.cancelAnimationFrame(frame);
    };
  }, [refresh]);

  const filteredPreferences = useMemo(
    () =>
      preferences.filter((preference) => {
        if (preferenceFilter === "active") return preference.active;
        if (preferenceFilter === "revoked") return !preference.active;
        return true;
      }),
    [preferenceFilter, preferences]
  );
  const filteredProposals = useMemo(
    () =>
      proposals.filter(
        (proposal) => proposalFilter === "all" || proposal.state === proposalFilter
      ),
    [proposalFilter, proposals]
  );
  const selectedPreference =
    filteredPreferences.find((item) => item.id === selectedPreferenceId) ??
    filteredPreferences[0] ??
    null;
  const selectedProposal =
    filteredProposals.find((item) => item.stable_key === selectedProposalKey) ??
    filteredProposals[0] ??
    null;

  async function mutate(action: () => Promise<unknown>, onSuccess?: () => void) {
    setIsSaving(true);
    setError(null);
    try {
      await action();
      await refresh();
      onSuccess?.();
      setDecisionMode(null);
      setDecisionReason("");
    } catch (mutationError) {
      setError(
        mutationError instanceof Error ? mutationError.message : "Falha ao salvar decisao."
      );
    } finally {
      setIsSaving(false);
    }
  }

  function submitDecision(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProposal || !decisionMode || !decisionReason.trim()) {
      return;
    }
    const completedState = decisionMode;
    void mutate(
      () =>
        decideLearningProposal(
          apiBaseUrl,
          selectedProposal.stable_key,
          completedState,
          decisionReason.trim()
        ),
      () => setProposalFilter(completedState)
    );
  }

  return (
    <section className="relative flex min-h-0 flex-1 flex-col overflow-hidden border border-truss-line bg-truss-raised">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-truss-line bg-truss-panel px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <ShieldCheck aria-hidden="true" className="truss-icon h-5 w-5 shrink-0 text-truss-accent" />
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-truss-text">Aprendizado local</h3>
            <p className="mt-1 truncate text-xs text-truss-muted">
              Decisoes explicitas, evidencias localizadas e nenhum comportamento oculto.
            </p>
          </div>
        </div>
        <button className="truss-button" onClick={onClose} type="button">
          <ArrowLeft aria-hidden="true" className="truss-icon h-4 w-4" />
          Voltar ao PDF
        </button>
      </header>

      <div className="flex border-b border-truss-line bg-truss-base/40" role="tablist" aria-label="Areas de aprendizado">
        <button
          aria-selected={tab === "preferences"}
          aria-controls="learning-preferences-panel"
          className="min-w-40 border-r border-truss-line px-4 py-2.5 text-sm font-semibold text-truss-muted transition-colors data-[active=true]:bg-truss-accentSoft data-[active=true]:text-truss-text"
          data-active={tab === "preferences"}
          id="learning-preferences-tab"
          onClick={() => setTab("preferences")}
          role="tab"
          type="button"
        >
          Preferencias / {preferences.length}
        </button>
        <button
          aria-selected={tab === "proposals"}
          aria-controls="learning-proposals-panel"
          className="min-w-40 border-r border-truss-line px-4 py-2.5 text-sm font-semibold text-truss-muted transition-colors data-[active=true]:bg-truss-accentSoft data-[active=true]:text-truss-text"
          data-active={tab === "proposals"}
          id="learning-proposals-tab"
          onClick={() => setTab("proposals")}
          role="tab"
          type="button"
        >
          Propostas / {proposals.filter((item) => item.state === "pending").length}
        </button>
        <button
          aria-selected={tab === "calibration"}
          aria-controls="learning-calibration-panel"
          className="min-w-40 border-r border-truss-line px-4 py-2.5 text-sm font-semibold text-truss-muted transition-colors data-[active=true]:bg-truss-accentSoft data-[active=true]:text-truss-text"
          data-active={tab === "calibration"}
          id="learning-calibration-tab"
          onClick={() => setTab("calibration")}
          role="tab"
          type="button"
        >
          Calibracao
        </button>
      </div>

      {error ? (
        <div className="border-b border-truss-danger/30 bg-truss-danger/10 px-4 py-3 text-sm text-truss-text" role="alert">
          {error}
        </div>
      ) : null}

      {isLoading ? (
        <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[360px_minmax(0,1fr)]" aria-label="Carregando aprendizado">
          <div className="space-y-2 border-r border-truss-line p-3">
            <div className="h-10 animate-pulse bg-truss-panel" />
            <div className="h-20 animate-pulse bg-truss-panel" />
            <div className="h-20 animate-pulse bg-truss-panel" />
          </div>
          <div className="space-y-3 p-5">
            <div className="h-8 w-1/3 animate-pulse bg-truss-panel" />
            <div className="h-28 animate-pulse bg-truss-panel" />
          </div>
        </div>
      ) : tab === "calibration" ? (
        <CalibrationPanel apiBaseUrl={apiBaseUrl} />
      ) : tab === "preferences" ? (
        <div
          aria-labelledby="learning-preferences-tab"
          className="grid min-h-0 flex-1 grid-cols-1 grid-rows-[minmax(240px,40vh)_minmax(0,1fr)] overflow-hidden lg:grid-cols-[360px_minmax(0,1fr)] lg:grid-rows-1"
          id="learning-preferences-panel"
          role="tabpanel"
        >
          <div className="flex min-h-0 flex-col border-b border-truss-line lg:border-b-0 lg:border-r">
            <div className="grid grid-cols-3 gap-2 border-b border-truss-line p-3">
              {(["active", "revoked", "all"] as const).map((filter) => (
                <button
                  className="truss-button px-2 data-[active=true]:border-truss-accent/55 data-[active=true]:bg-truss-accentSoft data-[active=true]:text-truss-text"
                  data-active={preferenceFilter === filter}
                  key={filter}
                  onClick={() => setPreferenceFilter(filter)}
                  type="button"
                >
                  {filter === "active" ? "Ativas" : filter === "revoked" ? "Revogadas" : "Todas"}
                </button>
              ))}
            </div>
            <div className="min-h-0 overflow-y-auto">
              {filteredPreferences.length === 0 ? (
                <p className="m-3 border border-dashed border-truss-line p-4 text-sm leading-6 text-truss-muted">
                  Nenhuma preferencia neste filtro. Rejeitar um finding nao cria comportamento sozinho.
                </p>
              ) : (
                filteredPreferences.map((preference) => (
                  <button
                    className="w-full border-b border-truss-line px-3 py-3 text-left transition-colors hover:bg-truss-panel data-[active=true]:bg-truss-accentSoft"
                    data-active={preference.id === selectedPreference?.id}
                    key={preference.id}
                    onClick={() => setSelectedPreferenceId(preference.id)}
                    type="button"
                  >
                    <span className="flex items-start gap-3">
                      {preference.active ? (
                        <EyeOff aria-hidden="true" className="truss-icon mt-0.5 h-4 w-4 shrink-0 text-truss-accent" />
                      ) : (
                        <History aria-hidden="true" className="truss-icon mt-0.5 h-4 w-4 shrink-0 text-truss-subtle" />
                      )}
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-mono text-xs font-semibold text-truss-text">
                          {preference.rule_id}
                        </span>
                        <span className="mt-1 block text-xs text-truss-muted">
                          {sheetTypeLabel(preference.sheet_type)}
                        </span>
                        <span className="mt-2 block font-mono text-[10px] uppercase tracking-[0.06em] text-truss-subtle">
                          {preference.active ? "ativa" : "revogada"} / {formatDate(preference.created_at)}
                        </span>
                      </span>
                    </span>
                  </button>
                ))
              )}
            </div>
          </div>

          <div className="min-h-0 overflow-y-auto p-4 sm:p-5">
            {selectedPreference ? (
              <div className="mx-auto max-w-4xl">
                <div className="flex flex-wrap items-start justify-between gap-3 border-b border-truss-line pb-4">
                  <div>
                    <p className="font-mono text-xs text-truss-subtle">{selectedPreference.rule_id}</p>
                    <h4 className="mt-2 text-lg font-semibold text-truss-text">
                      Supressao em {sheetTypeLabel(selectedPreference.sheet_type)}
                    </h4>
                  </div>
                  <span className={`inline-flex h-6 items-center border px-2 font-mono text-[10px] uppercase tracking-[0.06em] ${selectedPreference.active ? "border-truss-success/45 bg-truss-success/10 text-truss-success" : "border-truss-line text-truss-subtle"}`}>
                    {selectedPreference.active ? "Ativa" : "Revogada"}
                  </span>
                </div>

                <dl className="grid gap-px border border-truss-line bg-truss-line sm:grid-cols-2">
                  <div className="bg-truss-panel p-3">
                    <dt className="truss-mono-label">Efeito no runtime</dt>
                    <dd className="mt-2 text-sm text-truss-text">Oculta por padrao; findings permanecem salvos.</dd>
                  </div>
                  <div className="bg-truss-panel p-3">
                    <dt className="truss-mono-label">Historico</dt>
                    <dd className="mt-2 text-sm text-truss-text">
                      Criada {formatDate(selectedPreference.created_at)}
                      {selectedPreference.revoked_at ? ` / revogada ${formatDate(selectedPreference.revoked_at)}` : ""}
                    </dd>
                  </div>
                </dl>

                <div className="mt-4 border border-truss-line bg-truss-panel p-4">
                  <p className="truss-mono-label">Justificativa aprovada</p>
                  <p className="mt-2 max-w-[72ch] text-sm leading-6 text-truss-text">{selectedPreference.reason}</p>
                </div>

                {selectedPreference.source ? (
                  <div className="mt-4 border border-truss-line bg-truss-base/30">
                    <div className="border-b border-truss-line px-3 py-2">
                      <p className="truss-mono-label">Finding de origem</p>
                    </div>
                    <EvidenceButton evidence={selectedPreference.source} onOpen={onOpenEvidence} />
                    <p className="px-3 py-3 text-sm leading-6 text-truss-muted">
                      {selectedPreference.source.description}
                    </p>
                  </div>
                ) : null}

                <div className="mt-4 flex flex-wrap gap-2 border-t border-truss-line pt-4">
                  {selectedPreference.active ? (
                    <button
                      className="truss-button hover:border-truss-danger/50 hover:text-truss-danger disabled:opacity-50"
                      disabled={isSaving}
                      onClick={() => void mutate(() => revokeRulePreference(apiBaseUrl, selectedPreference.id))}
                      type="button"
                    >
                      <X aria-hidden="true" className="truss-icon h-4 w-4" />
                      Revogar preferencia
                    </button>
                  ) : (
                    <button
                      className="truss-button truss-button-primary disabled:opacity-50"
                      disabled={isSaving}
                      onClick={() => void mutate(() => reactivateRulePreference(apiBaseUrl, selectedPreference.id))}
                      type="button"
                    >
                      <RotateCcw aria-hidden="true" className="truss-icon h-4 w-4" />
                      Reativar preferencia
                    </button>
                  )}
                </div>
              </div>
            ) : null}
          </div>
        </div>
      ) : (
        <div
          aria-labelledby="learning-proposals-tab"
          className="grid min-h-0 flex-1 grid-cols-1 grid-rows-[minmax(240px,40vh)_minmax(0,1fr)] overflow-hidden lg:grid-cols-[380px_minmax(0,1fr)] lg:grid-rows-1"
          id="learning-proposals-panel"
          role="tabpanel"
        >
          <div className="flex min-h-0 flex-col border-b border-truss-line lg:border-b-0 lg:border-r">
            <label className="border-b border-truss-line p-3">
              <span className="truss-mono-label">Estado da proposta</span>
              <select
                className="truss-field mt-2 w-full px-3 text-sm"
                onChange={(event) => setProposalFilter(event.target.value as ProposalFilter)}
                value={proposalFilter}
              >
                <option value="pending">Pendentes</option>
                <option value="approved">Aprovadas</option>
                <option value="dismissed">Descartadas</option>
                <option value="insufficient">Evidencia insuficiente</option>
                <option value="all">Todas</option>
              </select>
            </label>
            <div className="min-h-0 overflow-y-auto">
              {filteredProposals.length === 0 ? (
                <p className="m-3 border border-dashed border-truss-line p-4 text-sm leading-6 text-truss-muted">
                  Nenhuma proposta neste estado. O Truss so pergunta quando a politica versionada e atingida.
                </p>
              ) : (
                filteredProposals.map((proposal) => (
                  <button
                    className="w-full border-b border-truss-line px-3 py-3 text-left transition-colors hover:bg-truss-panel data-[active=true]:bg-truss-accentSoft"
                    data-active={proposal.stable_key === selectedProposal?.stable_key}
                    key={proposal.stable_key}
                    onClick={() => {
                      setSelectedProposalKey(proposal.stable_key);
                      setDecisionMode(null);
                      setDecisionReason("");
                    }}
                    type="button"
                  >
                    <span className="flex items-start gap-3">
                      <Lightbulb aria-hidden="true" className="truss-icon mt-0.5 h-4 w-4 shrink-0 text-truss-warning" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-semibold text-truss-text">{proposalTitle(proposal)}</span>
                        <span className="mt-1 block text-xs text-truss-muted">{proposalKindLabels[proposal.proposal_kind]} / {sheetTypeLabel(proposal.sheet_type)}</span>
                        <span className="mt-2 flex flex-wrap items-center gap-2">
                          <StateBadge state={proposal.state} />
                          <span className="font-mono text-[10px] uppercase tracking-[0.06em] text-truss-subtle">{proposal.evidence_count} sinais / {proposal.distinct_sheet_count} folhas</span>
                        </span>
                      </span>
                    </span>
                  </button>
                ))
              )}
            </div>
          </div>

          <div className="min-h-0 overflow-y-auto p-4 sm:p-5">
            {selectedProposal ? (
              <div className="mx-auto max-w-5xl">
                <div className="flex flex-wrap items-start justify-between gap-3 border-b border-truss-line pb-4">
                  <div>
                    <p className="font-mono text-xs text-truss-subtle">{proposalKindLabels[selectedProposal.proposal_kind]}</p>
                    <h4 className="mt-2 text-lg font-semibold text-truss-text">{proposalTitle(selectedProposal)}</h4>
                    <p className="mt-2 text-sm text-truss-muted">{sheetTypeLabel(selectedProposal.sheet_type)} / {selectedProposal.policy_version}</p>
                  </div>
                  <StateBadge state={selectedProposal.state} />
                </div>

                <dl className="grid gap-px border border-truss-line bg-truss-line sm:grid-cols-2 xl:grid-cols-4">
                  <div className="bg-truss-panel p-3"><dt className="truss-mono-label">Sinais</dt><dd className="mt-2 font-mono text-sm text-truss-text">{selectedProposal.evidence_count}</dd></div>
                  <div className="bg-truss-panel p-3"><dt className="truss-mono-label">Folhas</dt><dd className="mt-2 font-mono text-sm text-truss-text">{selectedProposal.distinct_sheet_count}</dd></div>
                  <div className="bg-truss-panel p-3"><dt className="truss-mono-label">Revisoes</dt><dd className="mt-2 font-mono text-sm text-truss-text">{selectedProposal.distinct_revision_count}</dd></div>
                  <div className="bg-truss-panel p-3"><dt className="truss-mono-label">Razao observada</dt><dd className="mt-2 font-mono text-sm text-truss-text">{selectedProposal.observed_ratio === null ? "n/a" : `${Math.round(selectedProposal.observed_ratio * 100)}%`}</dd></div>
                </dl>

                <div className="mt-4 border border-truss-line bg-truss-panel p-4">
                  <p className="truss-mono-label">Efeito se aprovada</p>
                  <p className="mt-2 max-w-[72ch] text-sm leading-6 text-truss-text">
                    {selectedProposal.effect === "suppresses_findings"
                      ? "Cria uma preferencia explicita para ocultar esta regra por padrao neste tipo de prancha. Nenhum finding e apagado."
                      : "Registra a decisao para calibracao futura. Nao altera confianca, severidade, findings ou arquivos de regra nesta fase."}
                  </p>
                  <p className="mt-3 font-mono text-[10px] uppercase tracking-[0.06em] text-truss-subtle">
                    limiar / {selectedProposal.threshold.minimum_evidence} sinais / {selectedProposal.threshold.minimum_sheets} folhas{selectedProposal.threshold.minimum_ratio === null ? "" : ` / ${Math.round(selectedProposal.threshold.minimum_ratio * 100)}%`}
                  </p>
                </div>

                {selectedProposal.decision ? (
                  <div className="mt-4 border border-truss-success/35 bg-truss-success/10 p-4">
                    <p className="text-sm font-semibold text-truss-text">Decisao {selectedProposal.decision.decision === "approved" ? "aprovada" : "descartada"}</p>
                    <p className="mt-2 text-sm leading-6 text-truss-muted">{selectedProposal.decision.reason}</p>
                    <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.06em] text-truss-subtle">{selectedProposal.decision.evidence_count} evidencias congeladas / {formatDate(selectedProposal.decision.created_at)}</p>
                    <button
                      className="truss-button mt-3 disabled:opacity-50"
                      disabled={isSaving}
                      onClick={() => void mutate(() => revokeLearningDecision(apiBaseUrl, selectedProposal.decision!.id))}
                      type="button"
                    >
                      <RotateCcw aria-hidden="true" className="truss-icon h-4 w-4" />
                      Reabrir proposta
                    </button>
                  </div>
                ) : selectedProposal.active_preference_id ? (
                  <div className="mt-4 border border-truss-info/35 bg-truss-info/10 p-4">
                    <p className="text-sm font-semibold text-truss-text">Preferencia ja ativa</p>
                    <p className="mt-2 text-sm leading-6 text-truss-muted">
                      Esta supressao foi aprovada no viewer antes da central. O comportamento e o
                      finding de origem permanecem inspecionaveis na aba Preferencias.
                    </p>
                  </div>
                ) : selectedProposal.state === "pending" ? (
                  <div className="mt-4 border border-truss-warning/35 bg-truss-warning/10 p-4">
                    {decisionMode ? (
                      <form onSubmit={submitDecision}>
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="text-sm font-semibold text-truss-text">{decisionMode === "approved" ? "Aprovar proposta" : "Descartar proposta"}</p>
                            <p className="mt-1 text-xs leading-5 text-truss-muted">A justificativa fica vinculada ao snapshot das evidencias.</p>
                          </div>
                          <button className="truss-icon-button shrink-0" onClick={() => setDecisionMode(null)} title="Cancelar decisao" type="button"><X aria-hidden="true" className="truss-icon h-4 w-4" /></button>
                        </div>
                        <label className="mt-3 block">
                          <span className="truss-mono-label">Justificativa</span>
                          <textarea className="truss-field mt-2 w-full resize-none px-3 py-2 text-sm" maxLength={1000} onChange={(event) => setDecisionReason(event.target.value)} placeholder="Explique por que esta decisao deve ser mantida." required value={decisionReason} />
                        </label>
                        <button className="truss-button truss-button-primary mt-3 disabled:opacity-50" disabled={isSaving || !decisionReason.trim()} type="submit"><Check aria-hidden="true" className="truss-icon h-4 w-4" />Salvar decisao</button>
                      </form>
                    ) : (
                      <div className="flex flex-wrap gap-2">
                        <button className="truss-button truss-button-primary" onClick={() => setDecisionMode("approved")} type="button"><Check aria-hidden="true" className="truss-icon h-4 w-4" />Aprovar</button>
                        <button className="truss-button" onClick={() => setDecisionMode("dismissed")} type="button"><X aria-hidden="true" className="truss-icon h-4 w-4" />Descartar</button>
                      </div>
                    )}
                  </div>
                ) : null}

                <div className="mt-4 border border-truss-line bg-truss-base/30">
                  <div className="flex items-center justify-between gap-3 border-b border-truss-line px-3 py-2">
                    <p className="truss-mono-label">Evidencias localizaveis</p>
                    <span className="font-mono text-[10px] text-truss-subtle">{selectedProposal.evidence.length}</span>
                  </div>
                  {selectedProposal.evidence.map((evidence) => (
                    <EvidenceButton evidence={evidence} key={evidence.finding_id} onOpen={onOpenEvidence} />
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}
    </section>
  );
}
