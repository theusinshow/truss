export type RevisionSource = "manual" | "registered_external" | "pdf_placeholder";

export type Revision = {
  id: string;
  project_id: string;
  revision_code: string;
  notes: string;
  source_type: RevisionSource;
  original_filename: string | null;
  original_file_path: string | null;
  content_hash: string | null;
  created_at: string;
};

export type ProjectSummary = {
  id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  revisions_count: number;
  latest_revision_code: string | null;
};

export type ProjectDetail = Omit<ProjectSummary, "revisions_count" | "latest_revision_code"> & {
  revisions: Revision[];
};

export type Sheet = {
  id: string;
  document_id: string;
  project_id: string;
  revision_id: string;
  page_index: number;
  sheet_number: number;
  width_pt: number;
  height_pt: number;
  rotation: number;
  label: string;
  render_path: string | null;
  thumbnail_path: string | null;
  created_at: string;
};

export type ImportedDocument = {
  id: string;
  project_id: string;
  revision_id: string;
  original_filename: string;
  stored_file_path: string;
  content_hash: string;
  mime_type: string;
  file_size_bytes: number;
  page_count: number;
  created_at: string;
};

export type DocumentDetail = ImportedDocument & {
  sheets: Sheet[];
};

export type FindingStatus = "pending" | "confirmed" | "rejected";
export type FindingSeverity = "low" | "medium" | "high" | "critical";
export type FindingType = "inconsistency" | "attention" | "missing_information" | "unverifiable";

export type BoundingBox = {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
};

export type Finding = {
  id: string;
  audit_run_id: string | null;
  sheet_id: string;
  document_id: string;
  project_id: string;
  revision_id: string;
  category: string;
  type: FindingType;
  description: string;
  severity: FindingSeverity;
  confidence: number;
  bbox: BoundingBox;
  evidence: string[];
  origin: "ai" | "human";
  status: FindingStatus;
  rejection_reason: string | null;
  created_at: string;
  updated_at: string;
  // Rastreabilidade da F2. Opcionais porque findings legados nao tem regra por
  // tras: eles vieram das heuristicas anteriores ao motor de rule packs.
  rule_id?: string | null;
  rule_version?: string | null;
  rule_scope?: string | null;
  technical_scope?: string | null;
  view_id?: string | null;
  source_layer?: string | null;
  dedupe_key?: string | null;
  element_code?: string | null;
  registry_hash?: string | null;
};

export type PillarLifecycleState = "morre" | "nasce" | "passa";

export function findingLifecycleState(finding: Finding): PillarLifecycleState | null {
  const rawState = finding.evidence
    .find((item) => item.startsWith("estado: "))
    ?.slice("estado: ".length)
    .trim()
    .toLowerCase();

  return rawState === "morre" || rawState === "nasce" || rawState === "passa"
    ? rawState
    : null;
}

export function findingLevelTransition(
  finding: Finding
): { source: string; target: string } | null {
  const source = finding.evidence
    .find((item) => item.startsWith("nivel origem: "))
    ?.slice("nivel origem: ".length)
    .trim();
  const targetEvidence = finding.evidence.find((item) => item.startsWith("alvo: "));
  const target = targetEvidence?.match(/(?:^|\s)nivel=([^\s]+)/)?.[1];

  if (!source || source === "ausente" || !target || target === "ausente") {
    return null;
  }

  return { source, target };
}

export function findingElementLabel(finding: Finding): string | null {
  if (!finding.element_code) {
    return null;
  }

  const lifecycleState = findingLifecycleState(finding);
  return lifecycleState
    ? `Elemento ${finding.element_code} / ${lifecycleState.toUpperCase()}`
    : `Elemento ${finding.element_code}`;
}

export function shouldShowHypothesisNotice(finding: Finding): boolean {
  return finding.origin === "ai" && finding.status === "pending";
}

export type AuditCoverage = {
  evaluated: number;
  passed: number;
  failed: number;
  unknown: number;
  not_applicable: number;
  skipped: number;
  technical_scopes: string[];
  covered_scopes: string[];
  uncovered_scopes: string[];
};

/**
 * Uma auditoria sem achados nao e a mesma coisa que uma auditoria que nao
 * rodou, e a diferenca precisa aparecer na tela. O motor nao emite mais um
 * achado artificial dizendo "nada encontrado", entao e a cobertura que sustenta
 * a leitura de um resultado vazio.
 */
export function auditCoverageSummary(coverage: AuditCoverage | null | undefined): string {
  if (!coverage) {
    return "";
  }

  if (coverage.evaluated === 0) {
    const uncovered = coverage.uncovered_scopes ?? [];
    return uncovered.length > 0
      ? `Nenhuma regra se aplica aos escopos ${uncovered.map(technicalScopeLabel).join(" + ")}; nada foi verificado.`
      : "Nenhuma regra se aplica a esta folha, entao nada foi verificado.";
  }

  const parts = [`${coverage.evaluated} verificacoes`, `${coverage.passed} conformes`];

  if (coverage.unknown > 0) {
    parts.push(`${coverage.unknown} nao verificavel(is)`);
  }

  if (coverage.not_applicable > 0) {
    parts.push(`${coverage.not_applicable} nao aplicavel(is)`);
  }

  if ((coverage.uncovered_scopes ?? []).length > 0) {
    parts.push(`sem regras para ${(coverage.uncovered_scopes ?? []).map(technicalScopeLabel).join(" + ")}`);
  }

  return `${parts.join(" · ")}.`;
}

export type AuditRun = {
  id: string;
  sheet_id: string;
  document_id: string;
  project_id: string;
  revision_id: string;
  mode: string;
  pipeline_version: string;
  status: string;
  summary: string;
  started_at: string;
  completed_at: string;
  coverage: AuditCoverage;
  registry_hash: string | null;
  findings: Finding[];
};

export type ChatResponse = {
  answer: string;
  provider: string;
  model: string;
  conversation_id: string;
  user_message_id: string;
  assistant_message_id: string;
};

export type ChatStreamEvent =
  | { event: "meta"; provider: string; model: string }
  | { event: "delta"; delta: string }
  | { event: "done" } & ChatResponse
  | { event: "error"; detail: string; provider_code?: string | null };

export type ChatContextItem = {
  id: string;
  kind: "sheet" | "document" | "selection" | "finding" | "audit" | "page";
  label: string;
  value: string;
  metadata?: Record<string, string | number | boolean | null>;
};

export type Conversation = {
  id: string;
  sheet_id: string;
  project_id: string;
  revision_id: string;
  title: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export type PersistedChatMessage = {
  id: string;
  conversation_id: string | null;
  sheet_id: string;
  project_id: string;
  revision_id: string;
  role: "user" | "assistant";
  content: string;
  status: string;
  provider: string | null;
  model: string | null;
  parent_message_id: string | null;
  created_at: string;
  updated_at: string;
  context_items: ChatContextItem[];
};

export type MessageFeedback = {
  id: string;
  message_id: string;
  feedback: "correct" | "incorrect";
  reason: string;
  created_at: string;
};

export type AIStatus = {
  configured_provider: string;
  resolved_provider: string;
  model: string;
  openai_api_key_configured: boolean;
  openai_key_source: string | null;
  openai_key_last4: string | null;
  openai_key_fingerprint: string | null;
  openai_org_id_configured: boolean;
  openai_project_id_configured: boolean;
  external_calls_enabled: boolean;
  message: string;
};

export type Memory = {
  id: string;
  scope: string;
  key: string;
  text: string;
  created_at: string;
};

export type CreateProjectInput = {
  name: string;
  description: string;
};

export type CreateRevisionInput = {
  revision_code?: string;
  notes: string;
  source_type: RevisionSource;
  original_filename?: string;
};

async function request<T>(apiBaseUrl: string, path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers
    }
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Request failed with status ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function listProjects(apiBaseUrl: string): Promise<ProjectSummary[]> {
  return request<ProjectSummary[]>(apiBaseUrl, "/projects");
}

export function getProject(apiBaseUrl: string, projectId: string): Promise<ProjectDetail> {
  return request<ProjectDetail>(apiBaseUrl, `/projects/${projectId}`);
}

export function createProject(
  apiBaseUrl: string,
  input: CreateProjectInput
): Promise<ProjectDetail> {
  return request<ProjectDetail>(apiBaseUrl, "/projects", {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export function createRevision(
  apiBaseUrl: string,
  projectId: string,
  input: CreateRevisionInput
): Promise<Revision> {
  return request<Revision>(apiBaseUrl, `/projects/${projectId}/revisions`, {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export function listRevisionDocuments(
  apiBaseUrl: string,
  projectId: string,
  revisionId: string
): Promise<ImportedDocument[]> {
  return request<ImportedDocument[]>(
    apiBaseUrl,
    `/projects/${projectId}/revisions/${revisionId}/documents`
  );
}

export function getDocument(apiBaseUrl: string, documentId: string): Promise<DocumentDetail> {
  return request<DocumentDetail>(apiBaseUrl, `/documents/${documentId}`);
}

export async function importRevisionDocument(
  apiBaseUrl: string,
  projectId: string,
  revisionId: string,
  file: File
): Promise<DocumentDetail> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(
    `${apiBaseUrl}/projects/${projectId}/revisions/${revisionId}/documents`,
    {
      method: "POST",
      body: formData
    }
  );

  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Request failed with status ${response.status}`);
  }

  return response.json() as Promise<DocumentDetail>;
}

export function runSheetAudit(apiBaseUrl: string, sheetId: string): Promise<AuditRun> {
  return request<AuditRun>(apiBaseUrl, `/sheets/${sheetId}/audit-runs`, {
    method: "POST"
  });
}

export function listSheetFindings(apiBaseUrl: string, sheetId: string): Promise<Finding[]> {
  return request<Finding[]>(apiBaseUrl, `/sheets/${sheetId}/findings`);
}

export function updateFindingStatus(
  apiBaseUrl: string,
  findingId: string,
  status: FindingStatus,
  rejectionReason?: string
): Promise<Finding> {
  return request<Finding>(apiBaseUrl, `/findings/${findingId}`, {
    method: "PATCH",
    body: JSON.stringify({
      status,
      rejection_reason: rejectionReason
    })
  });
}

export function createManualFinding(
  apiBaseUrl: string,
  sheetId: string,
  input: {
    category: string;
    type: FindingType;
    description: string;
    severity: FindingSeverity;
    confidence: number;
    bbox: BoundingBox;
    evidence: string[];
  }
): Promise<Finding> {
  return request<Finding>(apiBaseUrl, `/sheets/${sheetId}/findings`, {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export function chatWithSheet(
  apiBaseUrl: string,
  sheetId: string,
  message: string,
  options?: { contextItems?: ChatContextItem[]; conversationId?: string; signal?: AbortSignal }
): Promise<ChatResponse> {
  return request<ChatResponse>(apiBaseUrl, `/sheets/${sheetId}/chat`, {
    method: "POST",
    body: JSON.stringify({
      message,
      conversation_id: options?.conversationId,
      context_items: options?.contextItems ?? []
    }),
    signal: options?.signal
  });
}

export async function streamChatWithSheet(
  apiBaseUrl: string,
  sheetId: string,
  message: string,
  options?: {
    contextItems?: ChatContextItem[];
    conversationId?: string;
    onEvent?: (event: ChatStreamEvent) => void;
    signal?: AbortSignal;
  }
): Promise<ChatResponse> {
  const response = await fetch(`${apiBaseUrl}/sheets/${sheetId}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      conversation_id: options?.conversationId,
      context_items: options?.contextItems ?? []
    }),
    signal: options?.signal
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Request failed with status ${response.status}`);
  }

  if (!response.body) {
    const fallback = await chatWithSheet(apiBaseUrl, sheetId, message, options);
    options?.onEvent?.({ event: "done", ...fallback });
    return fallback;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalPayload: ChatResponse | null = null;

  async function consumeLine(line: string) {
    const trimmed = line.trim();
    if (!trimmed) {
      return;
    }

    const event = JSON.parse(trimmed) as ChatStreamEvent;
    options?.onEvent?.(event);

    if (event.event === "error") {
      throw new Error(event.detail);
    }

    if (event.event === "done") {
      finalPayload = event;
    }
  }

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      await consumeLine(line);
    }

    if (done) {
      break;
    }
  }

  await consumeLine(buffer);

  if (!finalPayload) {
    throw new Error("Stream do Truss terminou sem resposta final.");
  }

  return finalPayload;
}

export function listSheetConversations(apiBaseUrl: string, sheetId: string): Promise<Conversation[]> {
  return request<Conversation[]>(apiBaseUrl, `/sheets/${sheetId}/conversations`);
}

export function listConversationMessages(apiBaseUrl: string, conversationId: string): Promise<PersistedChatMessage[]> {
  return request<PersistedChatMessage[]>(apiBaseUrl, `/chat/conversations/${conversationId}/messages`);
}

export function createMessageFeedback(
  apiBaseUrl: string,
  messageId: string,
  input: { feedback: "correct" | "incorrect"; reason?: string }
): Promise<MessageFeedback> {
  return request<MessageFeedback>(apiBaseUrl, `/chat/messages/${messageId}/feedback`, {
    method: "POST",
    body: JSON.stringify({
      feedback: input.feedback,
      reason: input.reason ?? ""
    })
  });
}

export function getAIStatus(apiBaseUrl: string): Promise<AIStatus> {
  return request<AIStatus>(apiBaseUrl, "/ai/status");
}

export function listMemories(apiBaseUrl: string): Promise<Memory[]> {
  return request<Memory[]>(apiBaseUrl, "/memories");
}

export function createMemory(
  apiBaseUrl: string,
  input: { scope: string; key: string; text: string }
): Promise<Memory> {
  return request<Memory>(apiBaseUrl, "/memories", {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export async function deleteMemory(apiBaseUrl: string, memoryId: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/memories/${memoryId}`, {
    method: "DELETE"
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Request failed with status ${response.status}`);
  }
}

export type SheetRegion = {
  id: string;
  region_kind: string;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  confidence: number;
};

export type SheetView = {
  id: string;
  parent_view_id: string | null;
  view_kind: string;
  view_role: string | null;
  identifier: string | null;
  // Bruto e normalizado seguem separados ate a tela: o viewer mostra o que
  // esta escrito na folha, nao uma interpretacao nao confirmada.
  title_raw: string | null;
  title: string | null;
  declared_scale_raw: string | null;
  declared_scale: string | null;
  level_raw: string | null;
  level: string | null;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  confidence: number;
  provenance: string;
  technical_scope: string | null;
};

export type SheetTechnicalScope = {
  technical_scope: string;
  confidence: number;
  provenance: string;
};

export type SheetElement = {
  id: string;
  view_id: string | null;
  technical_scope: string | null;
  element_kind: string;
  code_raw: string;
  code: string;
  attributes: Record<string, unknown>;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  confidence: number;
  provenance: string;
};

export type SheetMap = {
  id: string;
  sheet_id: string;
  project_id: string;
  revision_id: string;
  pipeline_version: string;
  status: string;
  geometry_path: string;
  sheet_code: string | null;
  sheet_code_raw: string | null;
  sheet_type: string;
  paper_format: string;
  orientation: string;
  title_block: Record<string, unknown>;
  built_at: string;
  technical_scopes: SheetTechnicalScope[];
  regions: SheetRegion[];
  views: SheetView[];
  elements?: SheetElement[];
};

const SHEET_TYPE_LABELS: Record<string, string> = {
  planta_locacao: "Planta de locação",
  planta_formas: "Planta de formas",
  planta_armaduras: "Planta de armaduras",
  planta_cobertura: "Planta de cobertura",
  planta_fundacoes: "Planta de fundações",
};

export function sheetTypeLabel(sheetType: string): string {
  return SHEET_TYPE_LABELS[sheetType] ?? "—";
}

const TECHNICAL_SCOPE_LABELS: Record<string, string> = {
  locacao: "Locação",
  fundacoes: "Fundações",
  formas: "Formas",
  armaduras: "Armaduras",
  cobertura: "Cobertura"
};

function technicalScopeLabel(technicalScope: string): string {
  return TECHNICAL_SCOPE_LABELS[technicalScope] ?? technicalScope;
}

export function sheetTechnicalScopesLabel(sheetMap: SheetMap): string {
  const labels = sheetMap.technical_scopes
    .map(({ technical_scope }) => technicalScopeLabel(technical_scope))
    .filter((label, index, items) => items.indexOf(label) === index);

  return labels.length > 0 ? labels.join(" + ") : sheetTypeLabel(sheetMap.sheet_type);
}

export function sheetIdentityLabel(sheet: Sheet, sheetMap: SheetMap | null): string {
  return sheetMap?.sheet_code ?? sheetMap?.sheet_code_raw ?? sheet.label;
}

export async function fetchSheetMap(
  apiBaseUrl: string,
  sheetId: string,
): Promise<SheetMap | null> {
  const response = await fetch(`${apiBaseUrl}/sheets/${sheetId}/sheet-map`);

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    throw new Error(`Falha ao carregar o sheet map (${response.status})`);
  }

  return (await response.json()) as SheetMap;
}

export type UsageEvent = {
  id: string;
  provider: string;
  model: string;
  operation: string;
  sheet_id: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  estimated_cost_usd: number;
  created_at: string;
};

export async function fetchSheetUsage(
  apiBaseUrl: string,
  sheetId: string,
): Promise<UsageEvent[]> {
  const response = await fetch(
    `${apiBaseUrl}/usage?sheet_id=${encodeURIComponent(sheetId)}`,
  );

  if (!response.ok) {
    throw new Error(`Falha ao carregar o uso de IA (${response.status})`);
  }

  return (await response.json()) as UsageEvent[];
}

export function summarizeUsage(events: UsageEvent[]) {
  return events.reduce(
    (total, event) => ({
      costUsd: total.costUsd + event.estimated_cost_usd,
      inputTokens: total.inputTokens + (event.input_tokens ?? 0),
      outputTokens: total.outputTokens + (event.output_tokens ?? 0),
      calls: total.calls + 1
    }),
    { costUsd: 0, inputTokens: 0, outputTokens: 0, calls: 0 }
  );
}
