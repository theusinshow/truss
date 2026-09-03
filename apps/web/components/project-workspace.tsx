"use client";

import { DragEvent, useCallback, useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import {
  Activity,
  BrainCircuit,
  ClipboardCheck,
  Database,
  FileUp,
  FolderOpen,
  GitCompare,
  Loader2,
  MoreHorizontal,
  RefreshCcw,
  Sparkles,
} from "lucide-react";
import {
  createProject,
  createRevision,
  BatchCapabilities,
  BatchItem,
  BatchRunSummary,
  DocumentDetail,
  getDocument,
  getBatchCapabilities,
  getProject,
  importRevisionBatch,
  listProjects,
  listRevisionDocuments,
  ProjectDetail,
  ProjectSummary,
  startRevisionAIReview,
} from "@/lib/projects-api";
import type { EvidenceLocator } from "@/lib/projects-api";
import { LearningCenter } from "@/components/learning/learning-center";
import { OperationalError } from "@/components/operations/operational-error";
import { OperationalStatus } from "@/components/operations/operational-status";
import { BatchProgress } from "@/components/operations/batch-progress";
import { SheetViewer } from "@/components/sheet-viewer";
import { resumeProcessingOperation } from "@/lib/diagnostics-api";
import { SheetIcon } from "@/components/truss-icons";

const RevisionComparisonPanel = dynamic(
  () =>
    import("@/components/comparisons/revision-comparison").then(
      (module) => module.RevisionComparisonPanel
    ),
  {
    ssr: false,
    loading: () => (
      <div className="flex min-h-[520px] items-center justify-center border border-truss-line bg-truss-panel text-sm text-truss-muted">
        Preparando comparação gráfica...
      </div>
    ),
  }
);

type ProjectWorkspaceProps = {
  apiBaseUrl: string;
};

function titleFromFileName(fileName: string) {
  return fileName
    .replace(/\.[^.]+$/, "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function ProjectWorkspace({ apiBaseUrl }: ProjectWorkspaceProps) {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [selectedProject, setSelectedProject] = useState<ProjectDetail | null>(null);
  const [selectedRevisionId, setSelectedRevisionId] = useState("");
  const [documentsByRevision, setDocumentsByRevision] = useState<Record<string, DocumentDetail[]>>(
    {}
  );
  const [isLoading, setIsLoading] = useState(true);
  const [isQuickImporting, setIsQuickImporting] = useState(false);
  const [isDraggingPdf, setIsDraggingPdf] = useState(false);
  const [quickStatus, setQuickStatus] = useState("");
  const [importedAuditVersion, setImportedAuditVersion] = useState(0);
  const [workspaceMode, setWorkspaceMode] = useState<"viewer" | "learning" | "compare">("viewer");
  const [viewerNavigationTarget, setViewerNavigationTarget] = useState<{
    sheetId: string;
    findingId?: string;
    nonce: number;
  } | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [isResumingOperation, setIsResumingOperation] = useState(false);
  const [operationsRefreshToken, setOperationsRefreshToken] = useState(0);
  const [batchByRevision, setBatchByRevision] = useState<Record<string, BatchRunSummary>>({});
  const [batchItemsByRevision, setBatchItemsByRevision] = useState<Record<string, BatchItem[]>>({});
  const [batchCapabilities, setBatchCapabilities] = useState<BatchCapabilities | null>(null);
  const [isStartingAIReview, setIsStartingAIReview] = useState(false);

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
          setError(loadError instanceof Error ? loadError : new Error("Falha ao carregar projetos."));
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

  useEffect(() => {
    let mounted = true;
    getBatchCapabilities(apiBaseUrl)
      .then((capabilities) => {
        if (mounted) setBatchCapabilities(capabilities);
      })
      .catch(() => {
        if (mounted) setBatchCapabilities(null);
      });
    return () => {
      mounted = false;
    };
  }, [apiBaseUrl]);

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
      setError(loadError instanceof Error ? loadError : new Error("Falha ao carregar documentos."));
    }
  }

  async function importPdfIntoWorkspace(file: File, options?: { createNewRevision?: boolean }) {
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      throw new Error("Selecione um arquivo PDF.");
    }

    setError(null);
    setQuickStatus("Preparando projeto e revisao...");

    let targetProject = selectedProject;
    if (!targetProject) {
      const projectName = titleFromFileName(file.name) || "Projeto importado";
      targetProject = await createProject(apiBaseUrl, {
        name: projectName,
        description: `Criado automaticamente a partir de ${file.name}.`
      });
    }

    let targetRevision =
      !options?.createNewRevision && targetProject.id === selectedProject?.id ? selectedRevision : null;

    if (!targetRevision) {
      targetRevision = await createRevision(apiBaseUrl, targetProject.id, {
        notes: `Revisao criada automaticamente na importacao de ${file.name}.`,
        source_type: "pdf_placeholder",
        original_filename: file.name
      });
    }

    setQuickStatus("Importando PDF e preparando a revisão por IA...");
    const { document: imported, batch } = await importRevisionBatch(
      apiBaseUrl,
      targetProject.id,
      targetRevision.id,
      file,
      false,
      true
    );

    setSelectedProject(await getProject(apiBaseUrl, targetProject.id));
    setSelectedRevisionId(targetRevision.id);
    setDocumentsByRevision((current) => ({
      ...current,
      [targetRevision.id]: [imported, ...(current[targetRevision.id] ?? [])]
    }));
    setBatchByRevision((current) => ({ ...current, [targetRevision.id]: batch }));

    setQuickStatus(`PDF importado. A IA vai revisar ${imported.sheets.length} folha(s).`);
    await refreshProjects(targetProject.id);
  }

  async function handleStartAIReview() {
    if (!selectedProject || !selectedRevision) return;
    setIsStartingAIReview(true);
    setError(null);
    try {
      const batch = await startRevisionAIReview(
        apiBaseUrl,
        selectedProject.id,
        selectedRevision.id
      );
      setBatchByRevision((current) => ({ ...current, [selectedRevision.id]: batch }));
      setQuickStatus(`Revisão por IA iniciada para ${batch.total_sheets} folha(s).`);
    } catch (reviewError) {
      setError(
        reviewError instanceof Error
          ? reviewError
          : new Error("Não foi possível iniciar a revisão por IA.")
      );
    } finally {
      setIsStartingAIReview(false);
    }
  }

  const handleBatchTerminal = useCallback((batch: BatchRunSummary) => {
    setBatchByRevision((current) => ({ ...current, [batch.revision_id]: batch }));
    setImportedAuditVersion((current) => current + 1);
    setQuickStatus(
      batch.status === "completed"
        ? batch.config.ai_review === true
          ? `Revisão por IA concluída em ${batch.total_sheets} folha(s).`
          : "Verificações locais concluídas."
        : batch.status === "completed_with_errors"
          ? "Revisão concluída com folhas que exigem atenção."
          : "Processamento interrompido pelo usuário."
    );
  }, []);

  const handleBatchItemsChange = useCallback(
    (items: BatchItem[]) => {
      if (!selectedRevisionId) return;
      setBatchItemsByRevision((current) => ({ ...current, [selectedRevisionId]: items }));
    },
    [selectedRevisionId]
  );

  async function handleQuickFile(file: File | null) {
    if (!file) {
      return;
    }

    setIsQuickImporting(true);
    setQuickStatus("");

    try {
      await importPdfIntoWorkspace(file, { createNewRevision: true });
    } catch (quickError) {
      setQuickStatus("");
      setError(quickError instanceof Error ? quickError : new Error("Falha ao importar e auditar PDF."));
      setOperationsRefreshToken((current) => current + 1);
    } finally {
      setIsQuickImporting(false);
      setIsDraggingPdf(false);
    }
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setIsDraggingPdf(false);
    const file = event.dataTransfer.files[0] ?? null;
    void handleQuickFile(file);
  }

  async function handleOpenEvidence(evidence: EvidenceLocator) {
    setError(null);
    try {
      const detail = await getProject(apiBaseUrl, evidence.project_id);
      const documents = await listRevisionDocuments(
        apiBaseUrl,
        evidence.project_id,
        evidence.revision_id
      );
      const documentDetails = await Promise.all(
        documents.map((document) => getDocument(apiBaseUrl, document.id))
      );
      setSelectedProject(detail);
      setSelectedRevisionId(evidence.revision_id);
      setDocumentsByRevision((current) => ({
        ...current,
        [evidence.revision_id]: documentDetails
      }));
      setViewerNavigationTarget({
        sheetId: evidence.sheet_id,
        findingId: evidence.finding_id,
        nonce: Date.now()
      });
      setWorkspaceMode("viewer");
    } catch (navigationError) {
      setError(
        navigationError instanceof Error
          ? navigationError
          : new Error("Falha ao localizar a evidencia no PDF.")
      );
    }
  }

  async function handleResumeOperation(operationId: string) {
    setIsResumingOperation(true);
    try {
      await resumeProcessingOperation(apiBaseUrl, operationId);
      setError(null);
      setOperationsRefreshToken((current) => current + 1);
      await refreshProjects();
    } catch (resumeError) {
      setError(
        resumeError instanceof Error ? resumeError : new Error("Falha ao continuar a operacao.")
      );
    } finally {
      setIsResumingOperation(false);
    }
  }

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 bg-truss-base/70 lg:grid-cols-[296px_minmax(0,1fr)]">
      <aside className="border-b border-truss-line bg-truss-raised lg:border-b-0 lg:border-r">
        <div className="border-b border-truss-line p-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="truss-mono-label">Biblioteca local</p>
              <h2 className="mt-1 text-sm font-semibold text-truss-text">Projetos e revisoes</h2>
            </div>
            <button
              className="truss-icon-button shrink-0"
              onClick={() => void refreshProjects()}
              title="Atualizar projetos"
              type="button"
            >
              <RefreshCcw aria-hidden="true" className="truss-icon h-4 w-4" />
              <span className="sr-only">Atualizar projetos</span>
            </button>
          </div>

          <p className="mt-4 text-xs leading-5 text-truss-muted">
            Estado salvo em SQLite local. PDFs originais ficam no disco e cada revisao e imutavel.
          </p>
        </div>

        <div className="max-h-[calc(100dvh-150px)] overflow-y-auto p-2">
          {isLoading ? (
            <div className="space-y-2 p-3" aria-label="Carregando projetos">
              <div className="h-16 animate-pulse bg-truss-panel" />
              <div className="h-16 animate-pulse bg-truss-panel" />
              <div className="h-16 animate-pulse bg-truss-panel" />
            </div>
          ) : projects.length === 0 ? (
            <p className="border border-dashed border-truss-line bg-truss-panel p-4 text-sm leading-6 text-truss-muted">
              Nenhum projeto local ainda. Arraste um PDF na area principal para comecar.
            </p>
          ) : (
            <ul className="space-y-1">
              {projects.map((project) => (
                <li key={project.id}>
                  <button
                    className="w-full border border-transparent px-3 py-3 text-left transition-colors hover:border-truss-line hover:bg-truss-panel data-[selected=true]:border-truss-accent/60 data-[selected=true]:bg-truss-accentSoft data-[selected=true]:shadow-[inset_2px_0_0_var(--red)]"
                    data-selected={project.id === selectedProject?.id}
                    onClick={() => void handleSelectProject(project.id)}
                    type="button"
                  >
                    <span className="flex items-start gap-3">
                      <FolderOpen aria-hidden="true" className="truss-icon mt-0.5 h-4 w-4 shrink-0 text-truss-subtle" />
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-semibold text-truss-text">
                          {project.name}
                        </span>
                        <span className="mt-2 block font-mono text-[11px] uppercase tracking-[0.06em] text-truss-subtle">
                          {project.revisions_count} revisoes
                          {project.latest_revision_code ? ` / ${project.latest_revision_code}` : ""}
                        </span>
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>

      <section className="flex min-h-0 flex-col p-3 sm:p-4">
        <OperationalStatus
          apiBaseUrl={apiBaseUrl}
          onRecovered={() => void refreshProjects()}
          refreshToken={operationsRefreshToken}
        />
        {error ? (
          <OperationalError
            error={error}
            isResuming={isResumingOperation}
            onResume={(operationId) => void handleResumeOperation(operationId)}
          />
        ) : null}

        <label
          className="mb-4 block cursor-pointer border border-dashed border-truss-line bg-truss-panel p-4 transition-colors hover:border-truss-accent hover:bg-truss-accentSoft data-[dragging=true]:border-truss-accent data-[dragging=true]:bg-truss-accentSoft data-[dragging=true]:shadow-truss-red data-[busy=true]:cursor-wait data-[busy=true]:opacity-80"
          data-busy={isQuickImporting}
          data-dragging={isDraggingPdf}
          onDragLeave={() => setIsDraggingPdf(false)}
          onDragOver={(event) => {
            event.preventDefault();
            setIsDraggingPdf(true);
          }}
          onDrop={handleDrop}
        >
          <input
            accept="application/pdf"
            className="sr-only"
            disabled={isQuickImporting}
            onChange={(event) => void handleQuickFile(event.target.files?.[0] ?? null)}
            type="file"
          />
          <span className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <span className="flex items-start gap-4">
              <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center border border-truss-accent bg-truss-accentSoft text-truss-accent">
                {isQuickImporting ? (
                  <Loader2 aria-hidden="true" className="truss-icon h-5 w-5 animate-spin" />
                ) : (
                  <FileUp aria-hidden="true" className="truss-icon h-5 w-5" />
                )}
              </span>
              <span>
                <span className="block text-sm font-semibold text-truss-text">
                  Importe um PDF para revisar com IA
                </span>
                <span className="mt-1 block max-w-2xl text-sm leading-6 text-truss-muted">
                  O Truss cria uma revisão imutável e envia cada prancha à IA dentro do teto
                  configurado. O PDF original permanece no disco local.
                </span>
                {quickStatus ? (
                  <span className="mt-3 inline-flex items-center gap-2 border border-truss-line bg-truss-raised px-3 py-2 font-mono text-[11px] text-truss-muted">
                    <ClipboardCheck aria-hidden="true" className="truss-icon h-4 w-4 text-truss-accent" />
                    {quickStatus}
                  </span>
                ) : null}
              </span>
            </span>
            <span className="truss-button">
              Escolher PDF e revisar
            </span>
          </span>
        </label>

        {batchCapabilities ? (
          <div
            className={`mb-3 flex items-center justify-between gap-3 border px-3 py-2 text-xs ${
              batchCapabilities.ai_review_available
                ? "border-truss-success/35 bg-truss-success/5 text-truss-muted"
                : "border-truss-warning/40 bg-truss-warning/10 text-truss-warning"
            }`}
          >
            <span className="flex items-center gap-2">
              <Sparkles aria-hidden="true" className="h-4 w-4 shrink-0" />
              {batchCapabilities.ai_review_available
                ? `IA pronta: ${batchCapabilities.provider} / ${batchCapabilities.model}`
                : "IA indisponível. Configure OpenAI e habilite a revisão visual."}
            </span>
            <span className="shrink-0 font-mono text-[10px] uppercase tracking-[0.06em]">
              teto US$ {batchCapabilities.vision_budget_usd_per_revision.toFixed(2)} / revisão
            </span>
          </div>
        ) : null}

        {selectedProject ? (
          <div className="flex min-h-0 flex-1 flex-col">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3 border border-truss-line bg-truss-panel px-4 py-3">
              <div className="min-w-0">
                <p className="truss-mono-label">Projeto ativo</p>
                <h2 className="mt-1 truncate text-lg font-semibold text-truss-text">
                  {selectedProject.name}
                </h2>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <button
                  className="truss-button truss-button-primary"
                  disabled={
                    isStartingAIReview
                    || !selectedRevision
                    || selectedDocuments.length === 0
                    || !batchCapabilities?.ai_review_available
                  }
                  onClick={() => void handleStartAIReview()}
                  type="button"
                >
                  {isStartingAIReview ? (
                    <Loader2 aria-hidden="true" className="truss-icon h-4 w-4 animate-spin" />
                  ) : (
                    <Sparkles aria-hidden="true" className="truss-icon h-4 w-4" />
                  )}
                  Revisar projeto com IA
                </button>
                <details className="group relative">
                  <summary className="truss-icon-button flex cursor-pointer list-none items-center justify-center" title="Mais ferramentas">
                    <MoreHorizontal aria-hidden="true" className="truss-icon h-4 w-4" />
                    <span className="sr-only">Mais ferramentas</span>
                  </summary>
                  <div className="absolute right-0 z-40 mt-2 grid min-w-52 gap-1 border border-truss-line bg-truss-raised p-2 shadow-truss-panel">
                    <button
                      className="truss-button justify-start"
                      onClick={() => setWorkspaceMode(workspaceMode === "learning" ? "viewer" : "learning")}
                      type="button"
                    >
                      <BrainCircuit aria-hidden="true" className="truss-icon h-4 w-4" />
                      {workspaceMode === "learning" ? "Voltar ao PDF" : "Aprendizado local"}
                    </button>
                    <button
                      className="truss-button justify-start"
                      disabled={selectedProject.revisions.length < 2}
                      onClick={() => setWorkspaceMode(workspaceMode === "compare" ? "viewer" : "compare")}
                      type="button"
                    >
                      <GitCompare aria-hidden="true" className="truss-icon h-4 w-4" />
                      {workspaceMode === "compare" ? "Voltar ao PDF" : "Comparar revisões"}
                    </button>
                  </div>
                </details>
                <span className="inline-flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.06em] text-truss-subtle">
                  <Database aria-hidden="true" className="truss-icon h-4 w-4 text-truss-accent" />
                  {selectedSummary?.latest_revision_code ?? "Sem revisao"}
                </span>
                <span className="inline-flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.06em] text-truss-subtle">
                  <SheetIcon className="h-4 w-4 text-truss-info" />
                  {selectedDocuments.reduce((count, document) => count + document.sheets.length, 0)} folhas
                </span>
                <select
                  className="truss-field px-3 font-mono text-sm"
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
              </div>
            </div>

            {workspaceMode === "learning" ? (
              <LearningCenter
                apiBaseUrl={apiBaseUrl}
                onClose={() => setWorkspaceMode("viewer")}
                onOpenEvidence={(evidence) => void handleOpenEvidence(evidence)}
              />
            ) : workspaceMode === "compare" && selectedRevision ? (
              <RevisionComparisonPanel
                apiBaseUrl={apiBaseUrl}
                initialTargetRevisionId={selectedRevision.id}
                key={`${selectedProject.id}:${selectedRevision.id}`}
                projectId={selectedProject.id}
                revisions={selectedProject.revisions}
              />
            ) : (
              <>
                {selectedRevision ? (
                  <BatchProgress
                    apiBaseUrl={apiBaseUrl}
                    initialBatch={batchByRevision[selectedRevision.id] ?? null}
                    key={`${selectedRevision.id}:${batchByRevision[selectedRevision.id]?.id ?? "latest"}`}
                    onOpenSheet={(sheetId) =>
                      setViewerNavigationTarget({ sheetId, nonce: Date.now() })
                    }
                    onItemsChange={handleBatchItemsChange}
                    onTerminal={handleBatchTerminal}
                    revisionId={selectedRevision.id}
                  />
                ) : null}
                <SheetViewer
                  apiBaseUrl={apiBaseUrl}
                  documents={selectedDocuments}
                  key={importedAuditVersion}
                  navigationTarget={viewerNavigationTarget}
                  reviewItems={
                    selectedRevision
                      ? batchItemsByRevision[selectedRevision.id]?.filter(
                          (item) => item.phase === "visual_audit"
                        ) ?? []
                      : []
                  }
                />
              </>
            )}
          </div>
        ) : (
          <div className="flex min-h-[520px] items-center justify-center border border-dashed border-truss-line bg-truss-panel p-6 text-center">
            <div>
              <Activity aria-hidden="true" className="truss-icon mx-auto h-5 w-5 text-truss-accent" />
              <p className="mt-4 text-sm font-semibold text-truss-text">
                Comece pelo PDF
              </p>
              <p className="mt-3 max-w-md text-sm leading-6 text-truss-muted">
                Arraste uma prancha estrutural na area acima. O Truss cria o projeto, registra a
                revisao e executa as verificacoes iniciais.
              </p>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
