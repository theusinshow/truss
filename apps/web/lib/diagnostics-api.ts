import { apiErrorFromResponse } from "@/lib/projects-api";

export type HealthSummary = {
  app: "truss-agent";
  status: "ok" | "degraded" | "unavailable";
  environment: string;
  database: "ok" | "warning" | "error";
  storage: "ok" | "warning" | "error";
  interrupted_operations: number;
};

export type DiagnosticCheck = {
  name: string;
  status: "ok" | "warning" | "error";
  code: string;
  message: string;
  action?: string;
  data?: Record<string, unknown>;
};

export type DiagnosticReport = {
  app: "truss-agent";
  status: HealthSummary["status"];
  deep: boolean;
  checks: DiagnosticCheck[];
};

export type ProcessingOperation = {
  id: string;
  kind: "document_import" | "sheet_map_build" | "deterministic_audit" | "vision_audit";
  status: "failed" | "interrupted" | "manual_retry_required";
  checkpoint: string;
  attempt_count: number;
  error_code: string | null;
  error_message: string | null;
  updated_at: string;
  resumable: boolean;
  payload: Record<string, unknown>;
};

async function get<T>(apiBaseUrl: string, path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, init);
  if (!response.ok) {
    throw await apiErrorFromResponse(response);
  }
  return response.json() as Promise<T>;
}

export function getHealth(apiBaseUrl: string): Promise<HealthSummary> {
  return get<HealthSummary>(apiBaseUrl, "/health");
}

export function getDiagnostics(apiBaseUrl: string): Promise<DiagnosticReport> {
  return get<DiagnosticReport>(apiBaseUrl, "/diagnostics");
}

export function listAttentionOperations(apiBaseUrl: string): Promise<ProcessingOperation[]> {
  return get<ProcessingOperation[]>(apiBaseUrl, "/operations");
}

export function resumeProcessingOperation(
  apiBaseUrl: string,
  operationId: string
): Promise<ProcessingOperation> {
  return get<ProcessingOperation>(apiBaseUrl, `/operations/${operationId}/resume`, {
    method: "POST"
  });
}

