import { FindingSeverity, FindingStatus, FindingType } from "@/lib/projects-api";

const severityMeta: Record<FindingSeverity, { label: string; tone: string; bars: number }> = {
  low: { label: "LOW", tone: "border-truss-info bg-truss-info/10 text-truss-info", bars: 1 },
  medium: { label: "MEDIUM", tone: "border-truss-warning bg-truss-warning/10 text-truss-warning", bars: 2 },
  high: { label: "HIGH", tone: "border-truss-accent bg-truss-accent/10 text-truss-accent", bars: 3 },
  critical: { label: "CRITICAL", tone: "border-truss-danger bg-truss-danger/10 text-truss-danger", bars: 4 }
};

const statusMeta: Record<FindingStatus, { label: string; tone: string; dot: string }> = {
  pending: {
    label: "PENDING",
    tone: "border-truss-warning/45 bg-truss-warning/10 text-truss-warning",
    dot: "bg-truss-warning"
  },
  confirmed: {
    label: "CONFIRMED",
    tone: "border-truss-success/45 bg-truss-success/10 text-truss-success",
    dot: "bg-truss-success"
  },
  rejected: {
    label: "REJECTED",
    tone: "border-truss-line bg-truss-base/40 text-truss-subtle",
    dot: "bg-truss-subtle"
  }
};

const typeLabels: Record<FindingType, string> = {
  attention: "ATTENTION",
  inconsistency: "INCONSISTENCY",
  missing_information: "MISSING INFO",
  unverifiable: "NOT VERIFIABLE"
};

function clampConfidence(confidence: number) {
  return Math.max(0, Math.min(1, confidence));
}

export function SeverityBadge({ severity }: { severity: FindingSeverity }) {
  const meta = severityMeta[severity];

  return (
    <span className={`inline-flex h-6 items-center gap-2 border px-2 font-mono text-[10px] uppercase tracking-[0.06em] ${meta.tone}`}>
      <span>{meta.label}</span>
      <span className="inline-grid grid-cols-4 gap-0.5" aria-hidden="true">
        {[0, 1, 2, 3].map((index) => (
          <span
            className={`h-2.5 w-1 ${index < meta.bars ? "bg-current" : "bg-current/20"}`}
            key={index}
          />
        ))}
      </span>
    </span>
  );
}

export function ConfidenceBadge({ confidence }: { confidence: number }) {
  const normalized = clampConfidence(confidence);

  return (
    <span className="inline-flex h-6 min-w-24 items-center gap-2 border border-truss-line bg-truss-raised px-2 font-mono text-[10px] uppercase tracking-[0.06em] text-truss-subtle">
      <span className="h-1.5 w-10 bg-truss-line" aria-hidden="true">
        <span
          className="block h-full bg-truss-muted"
          style={{ width: `${Math.round(normalized * 100)}%` }}
        />
      </span>
      {Math.round(normalized * 100)}%
    </span>
  );
}

export function StatusBadge({ status }: { status: FindingStatus }) {
  const meta = statusMeta[status];

  return (
    <span className={`inline-flex h-6 items-center gap-2 border px-2 font-mono text-[10px] uppercase tracking-[0.06em] ${meta.tone}`}>
      <span className={`h-1.5 w-1.5 ${meta.dot}`} aria-hidden="true" />
      {meta.label}
    </span>
  );
}

export function TypeBadge({ type }: { type: FindingType }) {
  return (
    <span className="inline-flex h-6 items-center border border-truss-line bg-truss-panel px-2 font-mono text-[10px] uppercase tracking-[0.06em] text-truss-subtle">
      {typeLabels[type]}
    </span>
  );
}

export function Kbd({ children }: { children: string }) {
  return (
    <kbd className="inline-flex h-5 min-w-5 items-center justify-center border border-truss-line bg-truss-base px-1.5 font-mono text-[10px] uppercase text-truss-muted">
      {children}
    </kbd>
  );
}
