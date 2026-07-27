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
