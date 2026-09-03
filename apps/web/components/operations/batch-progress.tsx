"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  CircleStop,
  Loader2,
  RotateCcw,
} from "lucide-react";

import {
  BatchItem,
  BatchPhase,
  BatchRunSummary,
  cancelBatchRun,
  getBatchRun,
  listBatchItems,
  listRevisionBatchRuns,
  resumeBatchRun,
} from "@/lib/projects-api";

type BatchProgressProps = {
  apiBaseUrl: string;
  revisionId: string;
  initialBatch?: BatchRunSummary | null;
  refreshToken?: number;
  onTerminal?: (batch: BatchRunSummary) => void;
  onOpenSheet?: (sheetId: string) => void;
  onItemsChange?: (items: BatchItem[]) => void;
};

const TERMINAL_BATCH = new Set(["completed", "completed_with_errors", "cancelled"]);
const TERMINAL_ITEM = new Set([
  "completed",
  "failed",
  "skipped_dependency",
  "cancelled",
  "manual_retry_required",
]);

const PHASE_LABELS: Record<BatchPhase, string> = {
  sheet_map: "Mapeando pranchas",
  deterministic_audit: "Verificações locais",
  visual_audit: "Análise visual",
  completed: "Processamento concluído",
};

const STATUS_LABELS: Record<string, string> = {
  queued: "Na fila",
  running: "Em processamento",
  cancel_requested: "Parando após a etapa atual",
  interrupted: "Interrompido",
  completed: "Concluído",
  completed_with_errors: "Concluído com atenção",
  cancelled: "Interrompido pelo usuário",
};
const PHASE_ORDER: Exclude<BatchPhase, "completed">[] = [
  "sheet_map",
  "deterministic_audit",
  "visual_audit",
];

export function batchPollInterval(isHidden: boolean) {
  return isHidden ? 5000 : 1000;
}

function countFinished(counts: Record<string, number>) {
  return Object.entries(counts).reduce(
    (total, [status, count]) => total + (TERMINAL_ITEM.has(status) ? count : 0),
    0
  );
}

function countErrors(batch: BatchRunSummary) {
  return Object.values(batch.phase_counts).reduce(
    (total, counts) =>
      total +
      (counts.failed ?? 0) +
      (counts.skipped_dependency ?? 0) +
      (counts.manual_retry_required ?? 0),
    0
  );
}

function displayPhase(batch: BatchRunSummary): Exclude<BatchPhase, "completed"> {
  if (batch.phase !== "completed") {
    return batch.phase;
  }
  return batch.mode === "with_visual" ? "visual_audit" : "deterministic_audit";
}

export function BatchProgress({
  apiBaseUrl,
  revisionId,
  initialBatch = null,
  refreshToken = 0,
  onTerminal,
  onOpenSheet,
  onItemsChange,
}: BatchProgressProps) {
  const [batch, setBatch] = useState<BatchRunSummary | null>(initialBatch);
  const [items, setItems] = useState<BatchItem[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [actionPending, setActionPending] = useState(false);
  const [loadError, setLoadError] = useState("");
  const terminalReported = useRef<string | null>(null);
  const batchId = batch?.id;
  const batchStatus = batch?.status;
  const batchUpdatedAt = batch?.updated_at;

  useEffect(() => {
    let mounted = true;
    async function load() {
      try {
        const runs = await listRevisionBatchRuns(apiBaseUrl, revisionId);
        if (mounted) setBatch(runs[0] ?? null);
      } catch {
        if (mounted) setLoadError("Não foi possível atualizar o lote local.");
      }
    }
    void load();
    return () => {
      mounted = false;
    };
  }, [apiBaseUrl, revisionId, refreshToken]);

  useEffect(() => {
    if (!batchId || !batchStatus || TERMINAL_BATCH.has(batchStatus)) {
      return;
    }
    const currentBatchId = batchId;
    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      try {
        const next = await getBatchRun(apiBaseUrl, currentBatchId);
        if (!cancelled) {
          setBatch((current) => (current?.updated_at === next.updated_at ? current : next));
          setLoadError("");
        }
      } catch {
        if (!cancelled) {
          setLoadError("O andamento está temporariamente indisponível.");
        }
      }
      if (!cancelled) {
        timeoutId = setTimeout(poll, batchPollInterval(document.hidden));
      }
    }

    timeoutId = setTimeout(poll, batchPollInterval(document.hidden));
    return () => {
      cancelled = true;
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [apiBaseUrl, batchId, batchStatus]);

  useEffect(() => {
    if (!batch || !TERMINAL_BATCH.has(batch.status) || terminalReported.current === batch.id) {
      return;
    }
    terminalReported.current = batch.id;
    onTerminal?.(batch);
  }, [batch, onTerminal]);

  useEffect(() => {
    if (!batchId || (!expanded && !onItemsChange)) {
      return;
    }
    void listBatchItems(apiBaseUrl, batchId)
      .then((nextItems) => {
        setItems(nextItems);
        onItemsChange?.(nextItems);
      })
      .catch(() => setLoadError("Não foi possível abrir os detalhes do lote."));
  }, [apiBaseUrl, batchId, batchUpdatedAt, expanded, onItemsChange]);

  const phase = batch ? displayPhase(batch) : "sheet_map";
  const phaseCounts = batch?.phase_counts[phase] ?? {};
  const finished = countFinished(phaseCounts);
  const total = batch?.total_sheets ?? 0;
  const progress = total ? Math.min(100, Math.round((finished / total) * 100)) : 0;
  const errors = batch ? countErrors(batch) : 0;
  const failedItems = useMemo(
    () => items.filter((item) => ["failed", "skipped_dependency", "manual_retry_required"].includes(item.status)),
    [items]
  );

  if (!batch && !loadError) {
    return null;
  }

  async function runAction(action: "cancel" | "resume") {
    if (!batch) return;
    setActionPending(true);
    setLoadError("");
    try {
      const next =
        action === "cancel"
          ? await cancelBatchRun(apiBaseUrl, batch.id)
          : await resumeBatchRun(apiBaseUrl, batch.id);
      setBatch(next);
    } catch {
      setLoadError("A ação não pôde ser concluída. Atualize o lote e tente novamente.");
    } finally {
      setActionPending(false);
    }
  }

  const active = batch && ["queued", "running", "cancel_requested"].includes(batch.status);
  const canResume = batch?.status === "interrupted" || (
    batch?.status === "completed_with_errors" &&
    Object.values(batch.phase_counts).some((counts) => (counts.failed ?? 0) > 0)
  );

  return (
    <section
      aria-live="polite"
      className="mb-3 border border-truss-line bg-truss-panel shadow-[inset_2px_0_0_var(--red)]"
      data-testid="batch-progress"
    >
      {batch ? (
        <div className="flex min-h-[84px] flex-col gap-3 px-4 py-3 xl:flex-row xl:items-center">
          <div className="flex min-w-[210px] items-center gap-3">
            <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center border border-truss-line bg-truss-raised">
              {TERMINAL_BATCH.has(batch.status) ? (
                errors ? (
                  <AlertTriangle aria-hidden="true" className="h-4 w-4 text-truss-warning" />
                ) : (
                  <CheckCircle2 aria-hidden="true" className="h-4 w-4 text-truss-success" />
                )
              ) : (
                <Loader2 aria-hidden="true" className="h-4 w-4 motion-safe:animate-spin text-truss-accent" />
              )}
            </span>
            <span className="min-w-0">
              <span className="truss-mono-label block">
                {batch.config.ai_review === true ? "Revisão do projeto" : "Processamento local"}
              </span>
              <span className="mt-1 block truncate text-sm font-semibold text-truss-text">
                {batch.phase === "visual_audit" && batch.config.ai_review === true
                  ? "Revisão por IA"
                  : PHASE_LABELS[batch.phase]}
              </span>
            </span>
          </div>

          <div className="min-w-0 flex-1">
            <div className="mb-2 flex items-center justify-between gap-3 font-mono text-[11px] uppercase tracking-[0.06em] text-truss-subtle">
              <span>{STATUS_LABELS[batch.status]}</span>
              <span>{finished}/{total} folhas</span>
            </div>
            <div
              aria-label={`${finished} de ${total} folhas concluídas nesta etapa`}
              aria-valuemax={total}
              aria-valuemin={0}
              aria-valuenow={finished}
              className="h-1.5 overflow-hidden bg-truss-raised"
              role="progressbar"
            >
              <div
                className="h-full bg-truss-accent motion-safe:transition-[width] motion-safe:duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>

          <div className="flex shrink-0 flex-wrap items-center gap-2">
            {errors ? (
              <span className="font-mono text-[11px] uppercase tracking-[0.06em] text-truss-warning">
                {errors} com atenção
              </span>
            ) : null}
            {active && batch.status !== "cancel_requested" ? (
              <button
                className="truss-button"
                disabled={actionPending}
                onClick={() => void runAction("cancel")}
                type="button"
              >
                <CircleStop aria-hidden="true" className="h-4 w-4" />
                Parar após a etapa atual
              </button>
            ) : null}
            {canResume ? (
              <button
                className="truss-button"
                disabled={actionPending}
                onClick={() => void runAction("resume")}
                type="button"
              >
                <RotateCcw aria-hidden="true" className="h-4 w-4" />
                Tentar falhas locais
              </button>
            ) : null}
            <button
              aria-expanded={expanded}
              className="truss-icon-button"
              onClick={() => setExpanded((current) => !current)}
              title={expanded ? "Ocultar detalhes" : "Mostrar detalhes"}
              type="button"
            >
              <ChevronDown
                aria-hidden="true"
                className="h-4 w-4 motion-safe:transition-transform"
                data-expanded={expanded}
                style={{ transform: expanded ? "rotate(180deg)" : undefined }}
              />
              <span className="sr-only">{expanded ? "Ocultar detalhes" : "Mostrar detalhes"}</span>
            </button>
          </div>
        </div>
      ) : null}

      {loadError ? (
        <p className="border-t border-truss-line px-4 py-2 text-xs text-truss-warning">{loadError}</p>
      ) : null}

      {expanded && batch ? (
        <div className="grid gap-4 border-t border-truss-line bg-truss-raised/55 px-4 py-3 lg:grid-cols-[minmax(0,1fr)_minmax(260px,0.7fr)]">
          <div>
            <p className="truss-mono-label">Etapas</p>
            <div className="mt-2 grid gap-px bg-truss-line sm:grid-cols-3">
              {PHASE_ORDER.filter((itemPhase) => batch.phase_counts[itemPhase]).map((itemPhase) => {
                const counts = batch.phase_counts[itemPhase] ?? {};
                return (
                  <div className="bg-truss-panel px-3 py-2" key={itemPhase}>
                    <p className="text-xs font-medium text-truss-text">{PHASE_LABELS[itemPhase]}</p>
                    <p className="mt-1 font-mono text-[11px] text-truss-subtle">
                      {countFinished(counts)}/{total} concluídas
                    </p>
                  </div>
                );
              })}
            </div>
          </div>
          <div>
            <p className="truss-mono-label">Ocorrências</p>
            {failedItems.length ? (
              <ul className="mt-2 max-h-28 space-y-1 overflow-y-auto text-xs text-truss-muted">
                {failedItems.map((item) => (
                  <li className="border-l-2 border-truss-warning/70 pl-2" key={item.id}>
                    <button
                      className="text-left hover:text-truss-text focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-truss-accent"
                      onClick={() => onOpenSheet?.(item.sheet_id)}
                      type="button"
                    >
                      <span className="font-mono text-truss-text">{item.sheet_label}</span>
                      {` · ${item.error_message ?? item.error_code ?? "Etapa não concluída"}`}
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-xs text-truss-muted">
                {items.length ? "Nenhuma falha registrada." : "Carregando detalhes…"}
              </p>
            )}
          </div>
        </div>
      ) : null}
    </section>
  );
}
