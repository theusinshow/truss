"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { Database, FilePlus2, FolderPlus, RefreshCcw, SquarePen } from "lucide-react";
import {
  createProject,
  createRevision,
  getProject,
  listProjects,
  ProjectDetail,
  ProjectSummary
} from "@/lib/projects-api";

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
  const [projectForm, setProjectForm] = useState<FormState>(initialProjectForm);
  const [revisionForm, setRevisionForm] = useState<RevisionState>(initialRevisionForm);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedSummary = useMemo(
    () => projects.find((project) => project.id === selectedProject?.id),
    [projects, selectedProject]
  );

  async function refreshProjects(projectIdToSelect?: string) {
    setError(null);
    const nextProjects = await listProjects(apiBaseUrl);
    setProjects(nextProjects);

    const nextSelectionId = projectIdToSelect ?? selectedProject?.id ?? nextProjects[0]?.id;

    if (nextSelectionId) {
      const detail = await getProject(apiBaseUrl, nextSelectionId);
      setSelectedProject(detail);
    } else {
      setSelectedProject(null);
    }
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
          if (isMounted) {
            setSelectedProject(detail);
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
    setSelectedProject(detail);
  }

  return (
    <div className="grid flex-1 grid-cols-1 lg:grid-cols-[380px_minmax(0,1fr)]">
      <aside className="border-b border-truss-line bg-truss-panel lg:border-b-0 lg:border-r">
        <div className="border-b border-truss-line p-5">
          <div className="flex items-center justify-between gap-4">
            <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-truss-muted">
              Projetos
            </h2>
            <button
              className="inline-flex h-9 w-9 items-center justify-center border border-truss-line text-truss-muted transition-colors hover:border-truss-accent hover:text-truss-text"
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
              <span className="font-mono text-xs uppercase tracking-[0.14em] text-truss-muted">
                Nome
              </span>
              <input
                className="mt-2 w-full border border-truss-line bg-truss-base px-3 py-2 text-sm text-truss-text outline-none transition-colors placeholder:text-truss-muted/60 focus:border-truss-accent"
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
              <span className="font-mono text-xs uppercase tracking-[0.14em] text-truss-muted">
                Descricao
              </span>
              <textarea
                className="mt-2 min-h-20 w-full resize-none border border-truss-line bg-truss-base px-3 py-2 text-sm text-truss-text outline-none transition-colors placeholder:text-truss-muted/60 focus:border-truss-accent"
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
              className="inline-flex w-full items-center justify-center gap-2 border border-truss-accent bg-truss-accent px-3 py-2 text-sm font-semibold text-truss-base transition-opacity disabled:cursor-not-allowed disabled:opacity-50"
              disabled={isSubmitting}
              type="submit"
            >
              <FolderPlus aria-hidden="true" className="h-4 w-4" />
              Criar projeto
            </button>
          </form>
        </div>

        <div className="max-h-[520px] overflow-y-auto">
          {isLoading ? (
            <p className="p-5 font-mono text-sm text-truss-muted">Carregando projetos...</p>
          ) : projects.length === 0 ? (
            <p className="p-5 text-sm leading-6 text-truss-muted">
              Nenhum projeto local ainda. Crie o primeiro registro para iniciar o historico.
            </p>
          ) : (
            <ul className="divide-y divide-truss-line">
              {projects.map((project) => (
                <li key={project.id}>
                  <button
                    className="w-full px-5 py-4 text-left transition-colors hover:bg-truss-base/60 data-[selected=true]:bg-truss-base"
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

      <section className="min-h-[620px] p-5">
        {error ? (
          <div className="mb-5 border border-truss-accent bg-truss-accent/10 px-4 py-3 text-sm text-truss-text">
            {error}
          </div>
        ) : null}

        {selectedProject ? (
          <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
            <div>
              <div className="border border-truss-line p-5">
                <p className="font-mono text-xs uppercase tracking-[0.16em] text-truss-muted">
                  Projeto ativo
                </p>
                <h2 className="mt-3 text-2xl font-semibold text-truss-text">
                  {selectedProject.name}
                </h2>
                <p className="mt-4 max-w-3xl text-sm leading-6 text-truss-muted">
                  {selectedProject.description || "Sem descricao registrada."}
                </p>
                <dl className="mt-6 grid grid-cols-1 gap-4 border-t border-truss-line pt-5 font-mono text-xs text-truss-muted sm:grid-cols-3">
                  <div>
                    <dt>Criado</dt>
                    <dd className="mt-1 text-truss-text">{formatDate(selectedProject.created_at)}</dd>
                  </div>
                  <div>
                    <dt>Atualizado</dt>
                    <dd className="mt-1 text-truss-text">{formatDate(selectedProject.updated_at)}</dd>
                  </div>
                  <div>
                    <dt>Ultima revisao</dt>
                    <dd className="mt-1 text-truss-text">
                      {selectedSummary?.latest_revision_code ?? "Sem revisao"}
                    </dd>
                  </div>
                </dl>
              </div>

              <div className="mt-5 border border-truss-line">
                <div className="flex items-center gap-3 border-b border-truss-line px-5 py-4">
                  <Database aria-hidden="true" className="h-4 w-4 text-truss-accent" />
                  <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-truss-muted">
                    Revisoes imutaveis
                  </h3>
                </div>

                {selectedProject.revisions.length === 0 ? (
                  <p className="p-5 text-sm leading-6 text-truss-muted">
                    Nenhuma revisao registrada. M1 permite cadastrar apenas metadados manuais,
                    sem importar PDF.
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
            </div>

            <form
              className="h-fit border border-truss-line bg-truss-panel p-5"
              onSubmit={(event) => void handleCreateRevision(event)}
            >
              <div className="flex items-center gap-3">
                <FilePlus2 aria-hidden="true" className="h-4 w-4 text-truss-accent" />
                <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-truss-muted">
                  Nova revisao
                </h3>
              </div>
              <label className="mt-5 block">
                <span className="font-mono text-xs uppercase tracking-[0.14em] text-truss-muted">
                  Codigo
                </span>
                <input
                  className="mt-2 w-full border border-truss-line bg-truss-base px-3 py-2 font-mono text-sm text-truss-text outline-none transition-colors placeholder:text-truss-muted/60 focus:border-truss-accent"
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
                <span className="font-mono text-xs uppercase tracking-[0.14em] text-truss-muted">
                  Arquivo
                </span>
                <input
                  className="mt-2 w-full border border-truss-line bg-truss-base px-3 py-2 text-sm text-truss-text outline-none transition-colors placeholder:text-truss-muted/60 focus:border-truss-accent"
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
                <span className="font-mono text-xs uppercase tracking-[0.14em] text-truss-muted">
                  Notas
                </span>
                <textarea
                  className="mt-2 min-h-24 w-full resize-none border border-truss-line bg-truss-base px-3 py-2 text-sm text-truss-text outline-none transition-colors placeholder:text-truss-muted/60 focus:border-truss-accent"
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
                className="mt-5 inline-flex w-full items-center justify-center gap-2 border border-truss-accent px-3 py-2 text-sm font-semibold text-truss-text transition-colors hover:bg-truss-accent hover:text-truss-base disabled:cursor-not-allowed disabled:opacity-50"
                disabled={isSubmitting}
                type="submit"
              >
                <SquarePen aria-hidden="true" className="h-4 w-4" />
                Registrar revisao
              </button>
            </form>
          </div>
        ) : (
          <div className="flex min-h-[520px] items-center justify-center border border-truss-line p-6 text-center">
            <div>
              <p className="font-mono text-xs uppercase tracking-[0.16em] text-truss-muted">
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
