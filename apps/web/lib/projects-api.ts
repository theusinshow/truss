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
