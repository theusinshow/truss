"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  Database,
  FileArchive,
  FilePlus2,
  FolderPlus,
  Layers3,
  RefreshCcw,
  SquarePen,
  Upload
} from "lucide-react";
import {
  createProject,
  createRevision,
  DocumentDetail,
  getDocument,
  getProject,
  importRevisionDocument,
  listProjects,
  listRevisionDocuments,
  ProjectDetail,
  ProjectSummary
} from "@/lib/projects-api";
import { MemoryPanel } from "@/components/memory-panel";
import { SheetViewer } from "@/components/sheet-viewer";

type ProjectWorkspaceProps = {
  apiBaseUrl: string;
};

type FormState = {
  name: string;
  description: string;
};

type RevisionState = {
  revisionCode: string;
  notes: string;
  originalFilename: string;
};

const initialProjectForm: FormState = {
  name: "",
  description: ""
};

const initialRevisionForm: RevisionState = {
  revisionCode: "",
  notes: "",
  originalFilename: ""
};

function formatDate(value: string) {
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short"
  }).format(new Date(value));
}

export function ProjectWorkspace({ apiBaseUrl }: ProjectWorkspaceProps) {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [selectedProject, setSelectedProject] = useState<ProjectDetail | null>(null);
  const [selectedRevisionId, setSelectedRevisionId] = useState("");
  const [documentsByRevision, setDocumentsByRevision] = useState<Record<string, DocumentDetail[]>>(
    {}
  );
  const [projectForm, setProjectForm] = useState<FormState>(initialProjectForm);
  const [revisionForm, setRevisionForm] = useState<RevisionState>(initialRevisionForm);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedSummary = useMemo(
    () => projects.find((project) => project.id === selectedProject?.id),
    [projects, selectedProject]
  );

  const selectedRevision = useMemo(() => {
    if (!selectedProject) {
      return null;
    }

    return (
      selectedProject.revisions.find((revision) => revision.id === selectedRevisionId) ??
      selectedProject.revisions.at(-1) ??
      null
    );
  }, [selectedProject, selectedRevisionId]);

  const selectedDocuments = selectedRevision ? documentsByRevision[selectedRevision.id] ?? [] : [];

  async function refreshProjects(projectIdToSelect?: string) {
    setError(null);
    const nextProjects = await listProjects(apiBaseUrl);
    setProjects(nextProjects);

    const nextSelectionId = projectIdToSelect ?? selectedProject?.id ?? nextProjects[0]?.id;

    if (nextSelectionId) {
      const detail = await getProject(apiBaseUrl, nextSelectionId);
      const nextRevisionId = detail.revisions.at(-1)?.id ?? "";
      setSelectedProject(detail);
      setSelectedRevisionId(nextRevisionId);

      if (nextRevisionId) {
        await refreshDocuments(detail.id, nextRevisionId);
      }
    } else {
      setSelectedProject(null);
      setSelectedRevisionId("");
    }
  }

  async function refreshDocuments(projectId: string, revisionId: string) {
    const documents = await listRevisionDocuments(apiBaseUrl, projectId, revisionId);
    const documentDetails = await Promise.all(
      documents.map((document) => getDocument(apiBaseUrl, document.id))
    );
    setDocumentsByRevision((current) => ({
      ...current,
      [revisionId]: documentDetails
    }));
  }

  useEffect(() => {
    let isMounted = true;

    async function load() {
      try {
        const nextProjects = await listProjects(apiBaseUrl);
        if (!isMounted) {
          return;
        }

        setProjects(nextProjects);

        if (nextProjects[0]) {
          const detail = await getProject(apiBaseUrl, nextProjects[0].id);
          const nextRevisionId = detail.revisions.at(-1)?.id ?? "";
          const documents = nextRevisionId
            ? await listRevisionDocuments(apiBaseUrl, detail.id, nextRevisionId)
            : [];
          const documentDetails = await Promise.all(
            documents.map((document) => getDocument(apiBaseUrl, document.id))
          );

          if (isMounted) {
            setSelectedProject(detail);
            setSelectedRevisionId(nextRevisionId);
            if (nextRevisionId) {
              setDocumentsByRevision((current) => ({
                ...current,
                [nextRevisionId]: documentDetails
              }));
            }
          }
        }
      } catch (loadError) {
        if (isMounted) {
          setError(loadError instanceof Error ? loadError.message : "Falha ao carregar projetos.");
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }

    load();

    return () => {
      isMounted = false;
    };
  }, [apiBaseUrl]);

  async function handleCreateProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);

    try {
      const created = await createProject(apiBaseUrl, projectForm);
      setProjectForm(initialProjectForm);
      await refreshProjects(created.id);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Falha ao criar projeto.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleCreateRevision(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!selectedProject) {
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      await createRevision(apiBaseUrl, selectedProject.id, {
        revision_code: revisionForm.revisionCode || undefined,
        notes: revisionForm.notes,
        source_type: "manual",
        original_filename: revisionForm.originalFilename || undefined
      });
      setRevisionForm(initialRevisionForm);
      await refreshProjects(selectedProject.id);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Falha ao criar revisao.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleSelectProject(projectId: string) {
    setError(null);
    const detail = await getProject(apiBaseUrl, projectId);
    const nextRevisionId = detail.revisions.at(-1)?.id ?? "";
    setSelectedProject(detail);
    setSelectedRevisionId(nextRevisionId);

    if (nextRevisionId) {
      await refreshDocuments(detail.id, nextRevisionId);
    }
  }

  async function handleSelectRevision(revisionId: string) {
    setSelectedRevisionId(revisionId);

    if (!selectedProject || !revisionId || documentsByRevision[revisionId]) {
      return;
    }

    try {
      await refreshDocuments(selectedProject.id, revisionId);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Falha ao carregar documentos.");
    }
  }

  async function handleImportDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!selectedProject || !selectedRevision || !uploadFile) {
      return;
    }

    setIsUploading(true);
    setError(null);

    try {
      const imported = await importRevisionDocument(
        apiBaseUrl,
        selectedProject.id,
        selectedRevision.id,
        uploadFile
      );
      setUploadFile(null);
      setDocumentsByRevision((current) => ({
        ...current,
        [selectedRevision.id]: [imported, ...(current[selectedRevision.id] ?? [])]
      }));
      await refreshProjects(selectedProject.id);
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "Falha ao importar PDF.");
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <div className="grid flex-1 grid-cols-1 bg-truss-base lg:grid-cols-[360px_minmax(0,1fr)]">
      <aside className="border-b border-truss-line bg-truss-raised lg:border-b-0 lg:border-r">
        <div className="border-b border-truss-line p-5">
          <div className="flex items-center justify-between gap-4">
            <h2 className="text-sm font-semibold text-truss-text">
              Projetos
            </h2>
            <button
              className="inline-flex h-11 w-11 items-center justify-center border border-truss-line bg-truss-panel text-truss-muted transition-colors hover:border-truss-accent hover:bg-truss-accentSoft hover:text-truss-accent"
              onClick={() => void refreshProjects()}
              title="Atualizar projetos"
              type="button"
            >
              <RefreshCcw aria-hidden="true" className="h-4 w-4" />
              <span className="sr-only">Atualizar projetos</span>
            </button>
          </div>

          <form className="mt-5 space-y-3" onSubmit={(event) => void handleCreateProject(event)}>
            <label className="block">
              <span className="text-xs font-medium text-truss-muted">
                Nome
              </span>
              <input
                className="mt-2 w-full border border-truss-line bg-truss-panel px-3 text-sm text-truss-text outline-none transition-colors placeholder:text-truss-subtle focus:border-truss-accent"
                maxLength={160}
                onChange={(event) =>
                  setProjectForm((current) => ({ ...current, name: event.target.value }))
                }
                placeholder="Ex.: Torre A - estrutura"
                required
                value={projectForm.name}
              />
            </label>
            <label className="block">
              <span className="text-xs font-medium text-truss-muted">
                Descricao
              </span>
              <textarea
                className="mt-2 w-full resize-none border border-truss-line bg-truss-panel px-3 py-2 text-sm text-truss-text outline-none transition-colors placeholder:text-truss-subtle focus:border-truss-accent"
                maxLength={1000}
                onChange={(event) =>
                  setProjectForm((current) => ({
                    ...current,
                    description: event.target.value
                  }))
                }
                placeholder="Opcional, contexto tecnico do conjunto."
                value={projectForm.description}
              />
            </label>
            <button
              className="inline-flex w-full items-center justify-center gap-2 border border-truss-accent bg-truss-accent px-4 text-sm font-semibold text-white transition-colors hover:bg-truss-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={isSubmitting}
              type="submit"
            >
              <FolderPlus aria-hidden="true" className="h-4 w-4" />
              Criar projeto
            </button>
          </form>
        </div>

        <div className="max-h-[520px] overflow-y-auto p-2">
          {isLoading ? (
            <div className="space-y-2 p-3" aria-label="Carregando projetos">
              <div className="h-14 animate-pulse rounded-lg bg-truss-panel" />
              <div className="h-14 animate-pulse rounded-lg bg-truss-panel" />
              <div className="h-14 animate-pulse rounded-lg bg-truss-panel" />
            </div>
          ) : projects.length === 0 ? (
            <p className="rounded-lg border border-dashed border-truss-line bg-truss-panel p-4 text-sm leading-6 text-truss-muted">
              Nenhum projeto local ainda. Crie o primeiro registro para iniciar o historico.
            </p>
          ) : (
            <ul className="space-y-2">
              {projects.map((project) => (
                <li key={project.id}>
                  <button
                    className="w-full rounded-lg border border-transparent px-4 py-3 text-left transition-colors hover:border-truss-line hover:bg-truss-panel data-[selected=true]:border-truss-accent data-[selected=true]:bg-truss-accentSoft"
                    data-selected={project.id === selectedProject?.id}
                    onClick={() => void handleSelectProject(project.id)}
                    type="button"
                  >
                    <span className="block text-sm font-semibold text-truss-text">
                      {project.name}
                    </span>
                    <span className="mt-2 block font-mono text-xs text-truss-muted">
                      {project.revisions_count} revisoes
                      {project.latest_revision_code ? ` | ${project.latest_revision_code}` : ""}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>

      <section className="min-h-[620px] p-4 sm:p-5">
        {error ? (
          <div className="mb-5 rounded-lg border border-truss-danger/30 bg-truss-danger/10 px-4 py-3 text-sm text-truss-text" role="alert">
            {error}
          </div>
        ) : null}

        {selectedProject ? (
          <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
            <div>
              <div className="rounded-lg border border-truss-line bg-truss-panel p-5 shadow-[0_1px_2px_rgba(32,43,61,0.04)]">
                <p className="text-xs font-medium text-truss-muted">
                  Projeto ativo
                </p>
                <h2 className="mt-2 text-2xl font-semibold tracking-tight text-truss-text">
                  {selectedProject.name}
                </h2>
                <p className="mt-4 max-w-3xl text-sm leading-6 text-truss-muted">
                  {selectedProject.description || "Sem descricao registrada."}
                </p>
                <dl className="mt-6 grid grid-cols-1 gap-3 border-t border-truss-line pt-5 text-xs text-truss-muted sm:grid-cols-3">
                  <div>
                    <dt className="font-medium">Criado</dt>
                    <dd className="mt-1 font-mono text-truss-text">{formatDate(selectedProject.created_at)}</dd>
                  </div>
                  <div>
                    <dt className="font-medium">Atualizado</dt>
                    <dd className="mt-1 font-mono text-truss-text">{formatDate(selectedProject.updated_at)}</dd>
                  </div>
                  <div>
                    <dt className="font-medium">Ultima revisao</dt>
                    <dd className="mt-1 font-mono text-truss-text">
                      {selectedSummary?.latest_revision_code ?? "Sem revisao"}
                    </dd>
                  </div>
                </dl>
              </div>

              <div className="mt-5 overflow-hidden rounded-lg border border-truss-line bg-truss-panel shadow-[0_1px_2px_rgba(32,43,61,0.04)]">
                <div className="flex items-center gap-3 border-b border-truss-line bg-truss-raised px-5 py-4">
                  <Database aria-hidden="true" className="h-4 w-4 text-truss-accent" />
                  <h3 className="text-sm font-semibold text-truss-text">
                    Revisoes imutaveis
                  </h3>
                </div>

                {selectedProject.revisions.length === 0 ? (
                  <p className="p-5 text-sm leading-6 text-truss-muted">
                    Nenhuma revisao registrada. Crie uma revisao para importar PDFs estruturais.
                  </p>
                ) : (
                  <ol className="divide-y divide-truss-line">
                    {selectedProject.revisions.map((revision) => (
                      <li className="grid gap-3 p-5 sm:grid-cols-[160px_minmax(0,1fr)]" key={revision.id}>
                        <div>
                          <p className="font-mono text-sm font-semibold text-truss-text">
                            {revision.revision_code}
                          </p>
                          <p className="mt-2 font-mono text-xs text-truss-muted">
                            {formatDate(revision.created_at)}
                          </p>
                        </div>
                        <div>
                          <p className="text-sm text-truss-text">
                            {revision.notes || "Sem notas."}
                          </p>
                          <p className="mt-2 font-mono text-xs text-truss-muted">
                            {revision.original_filename ?? "Sem arquivo associado"}
                          </p>
                        </div>
                      </li>
                    ))}
                  </ol>
                )}
              </div>

              <div className="mt-5 overflow-hidden rounded-lg border border-truss-line bg-truss-panel shadow-[0_1px_2px_rgba(32,43,61,0.04)]">
                <div className="flex items-center gap-3 border-b border-truss-line bg-truss-raised px-5 py-4">
                  <Layers3 aria-hidden="true" className="h-4 w-4 text-truss-accent" />
                  <h3 className="text-sm font-semibold text-truss-text">
                    PDFs importados
                  </h3>
                </div>

                {!selectedRevision ? (
                  <p className="p-5 text-sm leading-6 text-truss-muted">
                    Selecione ou crie uma revisao para ver os documentos.
                  </p>
                ) : selectedDocuments.length === 0 ? (
                  <p className="p-5 text-sm leading-6 text-truss-muted">
                    Nenhum PDF importado nesta revisao.
                  </p>
                ) : (
                  <div className="divide-y divide-truss-line">
                    {selectedDocuments.map((document) => (
                      <article className="p-5" key={document.id}>
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <p className="text-sm font-semibold text-truss-text">
                              {document.original_filename}
                            </p>
                            <p className="mt-2 font-mono text-xs text-truss-muted">
                              {document.page_count} folhas | {(document.file_size_bytes / 1024).toFixed(1)} KB
                            </p>
                          </div>
                          <p className="font-mono text-xs text-truss-muted">
                            {document.content_hash.slice(0, 12)}
                          </p>
                        </div>
                        {"sheets" in document && document.sheets.length > 0 ? (
                          <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                            {document.sheets.map((sheet) => (
                              <div className="rounded-md border border-truss-line bg-truss-raised px-3 py-2" key={sheet.id}>
                                <p className="font-mono text-xs font-semibold text-truss-text">
                                  {sheet.label}
                                </p>
                                <p className="mt-1 font-mono text-xs text-truss-muted">
                                  {Math.round(sheet.width_pt)} x {Math.round(sheet.height_pt)} pt
                                </p>
                              </div>
                            ))}
                          </div>
                        ) : null}
                      </article>
                    ))}
                  </div>
                )}
              </div>

              <div className="mt-5">
                <SheetViewer apiBaseUrl={apiBaseUrl} documents={selectedDocuments} />
              </div>
            </div>

            <div className="space-y-5">
              <form
                className="h-fit rounded-lg border border-truss-line bg-truss-panel p-5 shadow-[0_1px_2px_rgba(32,43,61,0.04)]"
                onSubmit={(event) => void handleCreateRevision(event)}
              >
                <div className="flex items-center gap-3">
                  <FilePlus2 aria-hidden="true" className="h-4 w-4 text-truss-accent" />
                  <h3 className="text-sm font-semibold text-truss-text">
                    Nova revisao
                  </h3>
                </div>
                <label className="mt-5 block">
                  <span className="text-xs font-medium text-truss-muted">
                    Codigo
                  </span>
                  <input
                    className="mt-2 w-full border border-truss-line bg-truss-raised px-3 font-mono text-sm text-truss-text outline-none transition-colors placeholder:text-truss-subtle focus:border-truss-accent"
                    maxLength={40}
                    onChange={(event) =>
                      setRevisionForm((current) => ({
                        ...current,
                        revisionCode: event.target.value
                      }))
                    }
                    placeholder="Automatico: REV-001"
                    value={revisionForm.revisionCode}
                  />
                </label>
                <label className="mt-4 block">
                  <span className="text-xs font-medium text-truss-muted">
                    Arquivo
                  </span>
                  <input
                    className="mt-2 w-full border border-truss-line bg-truss-raised px-3 text-sm text-truss-text outline-none transition-colors placeholder:text-truss-subtle focus:border-truss-accent"
                    maxLength={255}
                    onChange={(event) =>
                      setRevisionForm((current) => ({
                        ...current,
                        originalFilename: event.target.value
                      }))
                    }
                    placeholder="Opcional, ex.: forma-pav01.pdf"
                    value={revisionForm.originalFilename}
                  />
                </label>
                <label className="mt-4 block">
                  <span className="text-xs font-medium text-truss-muted">
                    Notas
                  </span>
                  <textarea
                    className="mt-2 w-full resize-none border border-truss-line bg-truss-raised px-3 py-2 text-sm text-truss-text outline-none transition-colors placeholder:text-truss-subtle focus:border-truss-accent"
                    maxLength={1000}
                    onChange={(event) =>
                      setRevisionForm((current) => ({
                        ...current,
                        notes: event.target.value
                      }))
                    }
                    placeholder="Contexto manual da revisao."
                    value={revisionForm.notes}
                  />
                </label>
                <button
                  className="mt-5 inline-flex w-full items-center justify-center gap-2 border border-truss-line bg-truss-raised px-4 text-sm font-semibold text-truss-text transition-colors hover:border-truss-accent hover:bg-truss-accentSoft disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={isSubmitting}
                  type="submit"
                >
                  <SquarePen aria-hidden="true" className="h-4 w-4" />
                  Registrar revisao
                </button>
              </form>

              <form
                className="h-fit rounded-lg border border-truss-line bg-truss-panel p-5 shadow-[0_1px_2px_rgba(32,43,61,0.04)]"
                onSubmit={(event) => void handleImportDocument(event)}
              >
                <div className="flex items-center gap-3">
                  <FileArchive aria-hidden="true" className="h-4 w-4 text-truss-accent" />
                  <h3 className="text-sm font-semibold text-truss-text">
                    Importar PDF
                  </h3>
                </div>
                <label className="mt-5 block">
                  <span className="text-xs font-medium text-truss-muted">
                    Revisao
                  </span>
                  <select
                    className="mt-2 w-full border border-truss-line bg-truss-raised px-3 font-mono text-sm text-truss-text outline-none transition-colors focus:border-truss-accent"
                    disabled={selectedProject.revisions.length === 0}
                    onChange={(event) => void handleSelectRevision(event.target.value)}
                    value={selectedRevision?.id ?? ""}
                  >
                    {selectedProject.revisions.map((revision) => (
                      <option key={revision.id} value={revision.id}>
                        {revision.revision_code}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="mt-4 block">
                  <span className="text-xs font-medium text-truss-muted">
                    PDF
                  </span>
                  <input
                    accept="application/pdf"
                    className="mt-2 w-full border border-truss-line bg-truss-raised px-3 py-2 text-sm text-truss-text file:mr-3 file:rounded-md file:border-0 file:bg-truss-accentSoft file:px-3 file:py-1 file:text-sm file:font-semibold file:text-truss-accent"
                    onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
                    type="file"
                  />
                </label>
                <button
                  className="mt-5 inline-flex w-full items-center justify-center gap-2 border border-truss-accent bg-truss-accent px-4 text-sm font-semibold text-white transition-colors hover:bg-truss-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={!selectedRevision || !uploadFile || isUploading}
                  type="submit"
                >
                  <Upload aria-hidden="true" className="h-4 w-4" />
                  {isUploading ? "Importando..." : "Importar prancha"}
                </button>
              </form>

              <MemoryPanel apiBaseUrl={apiBaseUrl} />
            </div>
          </div>
        ) : (
          <div className="flex min-h-[520px] items-center justify-center rounded-lg border border-dashed border-truss-line bg-truss-panel p-6 text-center">
            <div>
              <p className="text-sm font-semibold text-truss-text">
                Sem projeto ativo
              </p>
              <p className="mt-3 max-w-md text-sm leading-6 text-truss-muted">
                Crie um projeto na lateral para liberar o registro manual de revisoes.
              </p>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
