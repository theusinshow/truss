import { AlertTriangle, RotateCcw } from "lucide-react";

import { TrussApiError } from "@/lib/projects-api";

type OperationalErrorProps = {
  error: Error;
  isResuming?: boolean;
  onResume?: (operationId: string) => void;
};

export function OperationalError({ error, isResuming = false, onResume }: OperationalErrorProps) {
  const detail = error instanceof TrussApiError ? error.detail : null;
  return (
    <div
      className="mb-4 border border-truss-danger/40 bg-truss-danger/10 px-4 py-3"
      role="alert"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <AlertTriangle
            aria-hidden="true"
            className="truss-icon mt-0.5 h-4 w-4 shrink-0 text-truss-danger"
          />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-truss-text">{error.message}</p>
            {detail?.action ? (
              <p className="mt-1 max-w-3xl text-sm leading-5 text-truss-muted">{detail.action}</p>
            ) : null}
            {detail?.code ? (
              <p className="mt-2 font-mono text-[11px] text-truss-subtle">{detail.code}</p>
            ) : null}
          </div>
        </div>
        {detail?.retryable && detail.operation_id && onResume ? (
          <button
            className="truss-button shrink-0"
            disabled={isResuming}
            onClick={() => onResume(detail.operation_id as string)}
            type="button"
          >
            <RotateCcw aria-hidden="true" className="truss-icon h-4 w-4" />
            {isResuming ? "Continuando..." : "Continuar"}
          </button>
        ) : null}
      </div>
    </div>
  );
}

