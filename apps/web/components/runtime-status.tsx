import { Server } from "lucide-react";

type RuntimeStatusProps = {
  apiBaseUrl: string;
};

export function RuntimeStatus({ apiBaseUrl }: RuntimeStatusProps) {
  return (
    <div className="inline-flex min-h-11 items-center gap-3 rounded-lg border border-truss-line bg-truss-raised px-3 text-xs text-truss-muted">
      <span className="relative inline-flex h-7 w-7 items-center justify-center rounded-md bg-truss-accentSoft text-truss-accent">
        <Server aria-hidden="true" className="h-4 w-4" />
        <span className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full border-2 border-truss-raised bg-truss-success" />
      </span>
      <span className="font-medium text-truss-text">API local</span>
      <span className="max-w-52 truncate font-mono text-[11px]" title={apiBaseUrl}>
        {apiBaseUrl}
      </span>
    </div>
  );
}
