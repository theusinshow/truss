"use client";

import { Cpu, KeyRound, PlugZap, Server } from "lucide-react";
import { useEffect, useState } from "react";

import { AIStatus, getAIStatus } from "@/lib/projects-api";

type RuntimeStatusProps = {
  apiBaseUrl: string;
};

export function RuntimeStatus({ apiBaseUrl }: RuntimeStatusProps) {
  const [aiStatus, setAiStatus] = useState<AIStatus | null>(null);
  const aiStatusTitle = aiStatus
    ? [
        aiStatus.message,
        aiStatus.openai_key_source
          ? `Chave: ${aiStatus.openai_key_source} ...${aiStatus.openai_key_last4 ?? "----"} (${aiStatus.openai_key_fingerprint ?? "sem fingerprint"})`
          : null,
        aiStatus.openai_org_id_configured ? "Org configurada" : null,
        aiStatus.openai_project_id_configured ? "Projeto configurado" : null
      ]
        .filter(Boolean)
        .join(" | ")
    : "Status de IA indisponivel";

  useEffect(() => {
    let isMounted = true;

    getAIStatus(apiBaseUrl)
      .then((status) => {
        if (isMounted) {
          setAiStatus(status);
        }
      })
      .catch(() => {
        if (isMounted) {
          setAiStatus(null);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [apiBaseUrl]);

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="inline-flex min-h-[38px] items-center gap-3 border border-truss-line bg-truss-raised px-3 text-xs text-truss-muted">
        <span className="relative inline-flex h-6 w-6 items-center justify-center text-truss-info">
          <Server aria-hidden="true" className="truss-icon h-4 w-4" />
          <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-truss-success shadow-[0_0_0_3px_rgba(63,168,96,0.14)]" />
        </span>
        <span className="truss-mono-label text-truss-muted">API</span>
        <span className="max-w-52 truncate font-mono text-[11px] text-truss-subtle" title={apiBaseUrl}>
          {apiBaseUrl}
        </span>
      </div>
      <div
        className="inline-flex min-h-[38px] items-center gap-3 border border-truss-line bg-truss-raised px-3 text-xs text-truss-muted"
        title={aiStatusTitle}
      >
        <span className="relative inline-flex h-6 w-6 items-center justify-center text-truss-accent">
          {aiStatus?.external_calls_enabled ? (
            <PlugZap aria-hidden="true" className="truss-icon h-4 w-4" />
          ) : (
            <Cpu aria-hidden="true" className="truss-icon h-4 w-4" />
          )}
          <span
            className={`absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full ${
              aiStatus?.external_calls_enabled ? "bg-truss-success" : "bg-truss-subtle"
            }`}
          />
        </span>
        <span className="truss-mono-label text-truss-muted">IA</span>
        <span className="font-mono text-[11px] text-truss-subtle">
          {aiStatus ? `${aiStatus.resolved_provider} | ${aiStatus.model}` : "indisponivel"}
        </span>
        {aiStatus?.openai_api_key_configured ? (
          <KeyRound aria-label="Chave configurada" className="truss-icon h-3.5 w-3.5 text-truss-success" />
        ) : null}
      </div>
    </div>
  );
}
