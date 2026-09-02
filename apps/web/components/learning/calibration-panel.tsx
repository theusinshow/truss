"use client";

import Image from "next/image";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Activity, Archive, Check, Eye, RotateCcw, X } from "lucide-react";

import {
  calibrationEvidencePreviewUrl,
  CalibrationEvidence,
  CalibrationProposal,
  CalibrationRun,
  CalibrationRunDetail,
  decideCalibrationProposal,
  downloadCalibrationExport,
  getCalibrationRun,
  listCalibrationRuns,
  revokeCalibrationDecision,
  sheetTypeLabel
} from "@/lib/projects-api";

type CalibrationPanelProps = { apiBaseUrl: string };
type ProposalState = "pending" | "approved" | "dismissed";

const kindLabel = {
  rule_noise: "Ruido de regra",
  checklist_candidate: "Candidato a checklist",
  rule_retention: "Retencao de regra"
} as const;

const dateFormatter = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" });

function proposalState(proposal: CalibrationProposal): ProposalState {
  return proposal.state === "ready_for_implementation" ? "approved" : proposal.state;
}

function shortHash(value: string) {
  return value.slice(0, 10);
}

export function CalibrationPanel({ apiBaseUrl }: CalibrationPanelProps) {
  const [runs, setRuns] = useState<CalibrationRun[]>([]);
  const [run, setRun] = useState<CalibrationRunDetail | null>(null);
  const [selectedProposalId, setSelectedProposalId] = useState("");
  const [filter, setFilter] = useState<ProposalState | "all">("pending");
  const [decisionMode, setDecisionMode] = useState<"approved" | "dismissed" | null>(null);
  const [reason, setReason] = useState("");
  const [preview, setPreview] = useState<CalibrationEvidence | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadRun = useCallback(async (runId: string) => {
    const detail = await getCalibrationRun(apiBaseUrl, runId);
    setRun(detail);
    setSelectedProposalId((current) =>
      detail.proposals.some((proposal) => proposal.id === current)
        ? current
        : (detail.proposals[0]?.id ?? "")
    );
  }, [apiBaseUrl]);

  const refresh = useCallback(async (preferredRunId?: string) => {
    const nextRuns = await listCalibrationRuns(apiBaseUrl);
    setRuns(nextRuns);
    const nextId = preferredRunId && nextRuns.some((item) => item.id === preferredRunId)
      ? preferredRunId
      : (nextRuns[0]?.id ?? "");
    if (nextId) {
      await loadRun(nextId);
    } else {
      setRun(null);
    }
  }, [apiBaseUrl, loadRun]);

  useEffect(() => {
    let active = true;
    const frame = window.requestAnimationFrame(() => {
      void refresh()
        .catch((loadError) => {
          if (active) setError(loadError instanceof Error ? loadError.message : "Falha ao carregar calibracao.");
        })
        .finally(() => {
          if (active) setIsLoading(false);
        });
    });
    return () => {
      active = false;
      window.cancelAnimationFrame(frame);
    };
  }, [refresh]);

  const filteredProposals = useMemo(
    () => run?.proposals.filter((proposal) => filter === "all" || proposalState(proposal) === filter) ?? [],
    [filter, run]
  );
  const selectedProposal = filteredProposals.find((proposal) => proposal.id === selectedProposalId)
    ?? filteredProposals[0]
    ?? null;

  async function mutate(action: () => Promise<unknown>) {
    if (!run) return;
    setIsSaving(true);
    setError(null);
    try {
      await action();
      await refresh(run.id);
      setDecisionMode(null);
      setReason("");
    } catch (mutationError) {
      setError(mutationError instanceof Error ? mutationError.message : "Falha ao salvar decisao.");
    } finally {
      setIsSaving(false);
    }
  }

  function submitDecision(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProposal || !decisionMode || !reason.trim()) return;
    void mutate(() => decideCalibrationProposal(apiBaseUrl, selectedProposal.id, decisionMode, reason.trim()));
  }

  if (isLoading) {
    return (
      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[380px_minmax(0,1fr)]" aria-label="Carregando calibracao">
        <div className="space-y-2 border-r border-truss-line p-3"><div className="h-10 animate-pulse bg-truss-panel" /><div className="h-20 animate-pulse bg-truss-panel" /></div>
        <div className="space-y-3 p-5"><div className="h-8 w-1/3 animate-pulse bg-truss-panel" /><div className="h-28 animate-pulse bg-truss-panel" /></div>
      </div>
    );
  }

  if (runs.length === 0 || !run) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center p-6" role="tabpanel" id="learning-calibration-panel" aria-labelledby="learning-calibration-tab">
        <div className="max-w-xl border border-dashed border-truss-line bg-truss-base/30 p-6">
          <Activity aria-hidden="true" className="truss-icon h-5 w-5 text-truss-accent" />
          <h4 className="mt-3 text-base font-semibold text-truss-text">Nenhuma medicao registrada</h4>
          <p className="mt-2 text-sm leading-6 text-truss-muted">A calibracao e iniciada explicitamente no terminal e nunca durante uma requisicao da interface.</p>
          <code className="mt-4 block overflow-x-auto border border-truss-line bg-truss-panel px-3 py-2 font-mono text-xs text-truss-text">.venv\Scripts\python -m truss_api.calibration.runner measure-approved</code>
          {error ? <p className="mt-3 text-sm text-truss-danger" role="alert">{error}</p> : null}
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col" role="tabpanel" id="learning-calibration-panel" aria-labelledby="learning-calibration-tab">
      {error ? <div className="border-b border-truss-danger/30 bg-truss-danger/10 px-4 py-3 text-sm text-truss-text" role="alert">{error}</div> : null}
      <div className="grid gap-px border-b border-truss-line bg-truss-line sm:grid-cols-3 lg:grid-cols-6">
        <label className="bg-truss-panel p-3 sm:col-span-2">
          <span className="truss-mono-label">Execucao medida</span>
          <select className="truss-field mt-2 w-full px-3 text-sm" value={run.id} onChange={(event) => void loadRun(event.target.value)}>
            {runs.map((item) => <option key={item.id} value={item.id}>{dateFormatter.format(new Date(item.created_at))} / {shortHash(item.run_key)}</option>)}
          </select>
        </label>
        {[
          ["Corpus", `${run.document_count} PDF / ${run.page_count} pag.`],
          ["Achados brutos", run.raw_finding_count],
          ["Suprimidos", run.suppressed_finding_count],
          ["Efetivos", run.effective_finding_count]
        ].map(([label, value]) => (
          <dl className="bg-truss-panel p-3" key={label}><dt className="truss-mono-label">{label}</dt><dd className="mt-2 font-mono text-sm text-truss-text">{value}</dd></dl>
        ))}
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 grid-rows-[minmax(250px,42vh)_minmax(0,1fr)] overflow-hidden lg:grid-cols-[380px_minmax(0,1fr)] lg:grid-rows-1">
        <div className="flex min-h-0 flex-col border-b border-truss-line lg:border-b-0 lg:border-r">
          <div className="grid grid-cols-4 gap-1 border-b border-truss-line p-2">
            {(["pending", "approved", "dismissed", "all"] as const).map((state) => (
              <button className="truss-button px-1 data-[active=true]:border-truss-accent/55 data-[active=true]:bg-truss-accentSoft" data-active={filter === state} key={state} onClick={() => setFilter(state)} type="button">
                {state === "pending" ? "Pend." : state === "approved" ? "Aprov." : state === "dismissed" ? "Desc." : "Todas"}
              </button>
            ))}
          </div>
          <div className="min-h-0 overflow-y-auto">
            {filteredProposals.length === 0 ? (
              <p className="m-3 border border-dashed border-truss-line p-4 text-sm leading-6 text-truss-muted">Nenhuma proposta neste estado. Zero propostas e um resultado valido da medicao.</p>
            ) : filteredProposals.map((proposal) => (
              <button className="w-full border-b border-truss-line px-3 py-3 text-left transition-colors hover:bg-truss-panel data-[active=true]:bg-truss-accentSoft" data-active={proposal.id === selectedProposal?.id} key={proposal.id} onClick={() => { setSelectedProposalId(proposal.id); setDecisionMode(null); setReason(""); }} type="button">
                <span className="block text-sm font-semibold text-truss-text">{proposal.title}</span>
                <span className="mt-1 block text-xs text-truss-muted">{kindLabel[proposal.proposal_kind]} / {proposal.sheet_type ? sheetTypeLabel(proposal.sheet_type) : "escopo geral"}</span>
                <span className="mt-2 block font-mono text-[10px] uppercase tracking-[0.06em] text-truss-subtle">{proposalState(proposal)} / {proposal.evidence.length} evidencias</span>
              </button>
            ))}
          </div>
        </div>

        <div className="min-h-0 overflow-y-auto p-4 sm:p-5">
          {selectedProposal ? (
            <div className="mx-auto max-w-5xl">
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-truss-line pb-4">
                <div><p className="font-mono text-xs text-truss-subtle">{kindLabel[selectedProposal.proposal_kind]}</p><h4 className="mt-2 text-lg font-semibold text-truss-text">{selectedProposal.title}</h4><p className="mt-2 text-sm text-truss-muted">{selectedProposal.policy_version} / {selectedProposal.rule_id ?? "sem regra executavel"}</p></div>
                <button className="truss-button" onClick={() => void downloadCalibrationExport(apiBaseUrl, run.id).catch((exportError) => setError(exportError instanceof Error ? exportError.message : "Falha ao exportar."))} type="button"><Archive aria-hidden="true" className="truss-icon h-4 w-4" />Exportar dataset</button>
              </div>
              <div className="mt-4 border border-truss-line bg-truss-panel p-4"><p className="truss-mono-label">Leitura da medicao</p><p className="mt-2 max-w-[76ch] text-sm leading-6 text-truss-text">{selectedProposal.rationale}</p>{selectedProposal.payload.rule_spec_status === "needs_design" ? <p className="mt-3 border-l-2 border-truss-warning pl-3 text-xs leading-5 text-truss-muted">Requer desenho tecnico antes de virar regra. Aprovar nao altera o rule pack.</p> : null}</div>

              {selectedProposal.decision ? (
                <div className="mt-4 border border-truss-success/35 bg-truss-success/10 p-4"><p className="text-sm font-semibold text-truss-text">Decisao {selectedProposal.decision.decision === "approved" ? "aprovada" : "descartada"}</p><p className="mt-2 text-sm leading-6 text-truss-muted">{selectedProposal.decision.reason}</p><button className="truss-button mt-3" disabled={isSaving} onClick={() => void mutate(() => revokeCalibrationDecision(apiBaseUrl, selectedProposal.decision!.id))} type="button"><RotateCcw aria-hidden="true" className="truss-icon h-4 w-4" />Reabrir</button></div>
              ) : decisionMode ? (
                <form className="mt-4 border border-truss-warning/35 bg-truss-warning/10 p-4" onSubmit={submitDecision}><div className="flex items-start justify-between gap-3"><p className="text-sm font-semibold text-truss-text">{decisionMode === "approved" ? "Aprovar proposta" : "Descartar proposta"}</p><button className="truss-icon-button" onClick={() => setDecisionMode(null)} title="Cancelar" type="button"><X aria-hidden="true" className="truss-icon h-4 w-4" /></button></div><label className="mt-3 block"><span className="truss-mono-label">Justificativa</span><textarea className="truss-field mt-2 w-full resize-none px-3 py-2 text-sm" maxLength={1000} onChange={(event) => setReason(event.target.value)} required value={reason} /></label><button className="truss-button truss-button-primary mt-3" disabled={isSaving || !reason.trim()} type="submit"><Check aria-hidden="true" className="truss-icon h-4 w-4" />Salvar decisao</button></form>
              ) : (
                <div className="mt-4 flex flex-wrap gap-2 border-t border-truss-line pt-4"><button className="truss-button truss-button-primary" onClick={() => setDecisionMode("approved")} type="button"><Check aria-hidden="true" className="truss-icon h-4 w-4" />Aprovar</button><button className="truss-button" onClick={() => setDecisionMode("dismissed")} type="button"><X aria-hidden="true" className="truss-icon h-4 w-4" />Descartar</button></div>
              )}

              <div className="mt-4 border border-truss-line bg-truss-base/30"><div className="flex items-center justify-between border-b border-truss-line px-3 py-2"><p className="truss-mono-label">Amostras e contraexemplos</p><span className="font-mono text-[10px] text-truss-subtle">{selectedProposal.evidence.length}</span></div>{selectedProposal.evidence.length === 0 ? <p className="p-3 text-sm text-truss-muted">A proposta herda apenas a decisao humana de origem.</p> : selectedProposal.evidence.map((evidence) => <button className="flex w-full items-start gap-3 border-b border-truss-line px-3 py-3 text-left hover:bg-truss-panel disabled:cursor-not-allowed disabled:opacity-60" disabled={evidence.page_index === null} key={evidence.id} onClick={() => setPreview(evidence)} type="button"><Eye aria-hidden="true" className="truss-icon mt-0.5 h-4 w-4 shrink-0 text-truss-info" /><span className="min-w-0 flex-1"><span className="text-sm font-semibold text-truss-text">{evidence.sheet_code ?? `Pagina ${(evidence.page_index ?? 0) + 1}`}</span><span className="ml-2 font-mono text-[10px] uppercase text-truss-subtle">{evidence.evidence_kind}</span><span className="mt-1 block truncate text-xs text-truss-muted">{evidence.description || shortHash(evidence.document_sha256 ?? "")}</span></span><span className="font-mono text-[10px] uppercase text-truss-info">preview</span></button>)}</div>
            </div>
          ) : null}
        </div>
      </div>

      {preview ? (
        <div className="absolute inset-4 z-30 flex flex-col border border-truss-line bg-truss-base shadow-2xl" role="dialog" aria-modal="true" aria-label="Preview da evidencia"><div className="flex items-center justify-between border-b border-truss-line bg-truss-panel px-3 py-2"><div><p className="text-sm font-semibold text-truss-text">{preview.sheet_code ?? `Pagina ${(preview.page_index ?? 0) + 1}`}</p><p className="font-mono text-[10px] text-truss-subtle">{shortHash(preview.document_sha256 ?? "")}</p></div><button className="truss-icon-button" onClick={() => setPreview(null)} title="Fechar preview" type="button"><X aria-hidden="true" className="truss-icon h-4 w-4" /></button></div><div className="relative min-h-0 flex-1 bg-black"><Image alt={`Preview da evidencia ${preview.sheet_code ?? ""}`} className="object-contain" fill sizes="90vw" src={calibrationEvidencePreviewUrl(apiBaseUrl, preview.id)} unoptimized /></div></div>
      ) : null}
    </div>
  );
}
