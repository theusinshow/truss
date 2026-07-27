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
};

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
  findings: Finding[];
};

export type ChatResponse = {
  answer: string;
  provider: string;
  model: string;
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
  message: string
): Promise<ChatResponse> {
  return request<ChatResponse>(apiBaseUrl, `/sheets/${sheetId}/chat`, {
    method: "POST",
    body: JSON.stringify({ message })
  });
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
