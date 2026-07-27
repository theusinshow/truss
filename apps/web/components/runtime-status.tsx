import { Server } from "lucide-react";

type RuntimeStatusProps = {
  apiBaseUrl: string;
};

export function RuntimeStatus({ apiBaseUrl }: RuntimeStatusProps) {
  return (
    <div className="flex items-center gap-3 border border-truss-line bg-truss-panel px-3 py-2 font-mono text-xs text-truss-muted">
      <Server aria-hidden="true" className="h-4 w-4 text-truss-accent" />
      <span className="uppercase tracking-[0.14em]">API</span>
      <span className="max-w-52 truncate text-truss-text" title={apiBaseUrl}>
        {apiBaseUrl}
      </span>
    </div>
  );
}
