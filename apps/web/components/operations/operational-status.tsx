"use client";

import { Activity, AlertTriangle, ChevronDown, ChevronUp, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";

import {
  getDiagnostics,
  getHealth,
  listAttentionOperations,
  ProcessingOperation,
  resumeProcessingOperation
} from "@/lib/diagnostics-api";

type OperationalStatusProps = {
  apiBaseUrl: string;
  refreshToken?: number;
  onRecovered?: () => void;
};

const KIND_LABELS: Record<ProcessingOperation["kind"], string> = {
  document_import: "Importacao de PDF",
  sheet_map_build: "Construcao do Sheet Map",
  deterministic_audit: "Auditoria deterministica",
  vision_audit: "Analise visual"
};

async function loadOperationalState(apiBaseUrl: string) {
  const [health, attention] = await Promise.all([
    getHealth(apiBaseUrl),
    listAttentionOperations(apiBaseUrl)
  ]);
  const report = health.status !== "ok" ? await getDiagnostics(apiBaseUrl) : null;
  return {
    status: health.status,
    operations: attention,
    checks:
      report?.checks
        .filter((check) => check.status !== "ok")
        .map((check) => check.action ?? check.message) ?? []
  };
}

export function OperationalStatus({
  apiBaseUrl,
  refreshToken = 0,
  onRecovered
}: OperationalStatusProps) {
  const [operations, setOperations] = useState<ProcessingOperation[]>([]);
  const [status, setStatus] = useState<"ok" | "degraded" | "unavailable">("ok");
  const [checks, setChecks] = useState<string[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [resumingId, setResumingId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadOperationalState(apiBaseUrl)
      .then((next) => {
        if (cancelled) return;
        setStatus(next.status);
        setOperations(next.operations);
        setChecks(next.checks);
      })
      .catch(() => {
        if (cancelled) return;
        setStatus("unavailable");
        setChecks(["A API local nao respondeu ao diagnostico."]);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, refreshToken]);

  async function handleResume(operationId: string) {
    setResumingId(operationId);
    try {
      await resumeProcessingOperation(apiBaseUrl, operationId);
      const next = await loadOperationalState(apiBaseUrl);
      setStatus(next.status);
      setOperations(next.operations);
      setChecks(next.checks);
      onRecovered?.();
    } catch (error) {
      setStatus("degraded");
      setChecks([
        error instanceof Error ? error.message : "A operacao nao pode ser retomada."
      ]);
    } finally {
      setResumingId(null);
    }
  }

  if (isLoading || (status === "ok" && operations.length === 0)) {
    return null;
  }

  const unavailable = status === "unavailable";
  return (
    <div className="mb-4 border border-truss-line bg-truss-raised" data-testid="operational-status">
      <button
        aria-expanded={isOpen}
        className="flex min-h-11 w-full items-center justify-between gap-4 px-4 py-2 text-left hover:bg-truss-panel"
        onClick={() => setIsOpen((current) => !current)}
        type="button"
      >
        <span className="flex min-w-0 items-center gap-3">
          {unavailable ? (
            <AlertTriangle aria-hidden="true" className="truss-icon h-4 w-4 shrink-0 text-truss-danger" />
          ) : (
            <Activity aria-hidden="true" className="truss-icon h-4 w-4 shrink-0 text-truss-warning" />
          )}
          <span>
            <span className="block text-xs font-semibold text-truss-text">
              {unavailable ? "Operacao local indisponivel" : "Operacao local requer atencao"}
            </span>
            <span className="mt-0.5 block font-mono text-[10.5px] text-truss-subtle">
              {operations.length} interrompida(s) / estado {status}
            </span>
          </span>
        </span>
        {isOpen ? (
          <ChevronUp aria-hidden="true" className="truss-icon h-4 w-4 text-truss-subtle" />
        ) : (
          <ChevronDown aria-hidden="true" className="truss-icon h-4 w-4 text-truss-subtle" />
        )}
      </button>

      {isOpen ? (
        <div className="border-t border-truss-line px-4 py-3">
          {checks.length > 0 ? (
            <ul className="mb-3 space-y-1 text-xs leading-5 text-truss-muted">
              {checks.map((check) => (
                <li key={check}>{check}</li>
              ))}
            </ul>
          ) : null}
          {operations.length > 0 ? (
            <ul className="divide-y divide-truss-line border-y border-truss-line">
              {operations.map((operation) => (
                <li
                  className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between"
                  key={operation.id}
                >
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-truss-text">
                      {KIND_LABELS[operation.kind]}
                    </p>
                    <p className="mt-1 font-mono text-[10.5px] text-truss-subtle">
                      {operation.error_code ?? operation.status} / {operation.checkpoint}
                    </p>
                  </div>
                  {operation.resumable ? (
                    <button
                      className="truss-button shrink-0"
                      disabled={resumingId === operation.id}
                      onClick={() => void handleResume(operation.id)}
                      type="button"
                    >
                      <RotateCcw aria-hidden="true" className="truss-icon h-4 w-4" />
                      {resumingId === operation.id ? "Continuando..." : "Continuar"}
                    </button>
                  ) : (
                    <span className="max-w-sm text-xs leading-5 text-truss-muted">
                      {operation.kind === "vision_audit"
                        ? "Nova chamada exige confirmacao manual."
                        : "Importe novamente o mesmo arquivo."}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
