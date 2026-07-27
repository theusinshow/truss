"use client";

import { PointerEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Crosshair,
  Eye,
  EyeOff,
  LocateFixed,
  Maximize2,
  Minus,
  Plus,
  ScanSearch,
  SquareMousePointer,
  X
} from "lucide-react";

import {
  createManualFinding,
  DocumentDetail,
  Finding,
  listSheetFindings,
  runSheetAudit,
  Sheet,
  updateFindingStatus
} from "@/lib/projects-api";

type SheetViewerProps = {
  apiBaseUrl: string;
  documents: DocumentDetail[];
};

type PanState = {
  x: number;
  y: number;
};

const minZoom = 0.25;
const maxZoom = 3;
const renderScale = 2;

function clampZoom(value: number) {
  return Math.min(maxZoom, Math.max(minZoom, value));
}

export function SheetViewer({ apiBaseUrl, documents }: SheetViewerProps) {
  const sheets = useMemo(
    () =>
      documents.flatMap((document) =>
        document.sheets.map((sheet) => ({
          ...sheet,
          documentName: document.original_filename
        }))
      ),
    [documents]
  );
  const [activeSheetId, setActiveSheetId] = useState("");
  const [zoom, setZoom] = useState(0.55);
  const [pan, setPan] = useState<PanState>({ x: 0, y: 0 });
  const [findings, setFindings] = useState<Finding[]>([]);
  const [activeFindingId, setActiveFindingId] = useState("");
  const [showFindings, setShowFindings] = useState(true);
  const [isAuditing, setIsAuditing] = useState(false);
  const [manualMode, setManualMode] = useState(false);
  const [manualStart, setManualStart] = useState<PanState | null>(null);
  const [manualDraft, setManualDraft] = useState<PanState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragStart, setDragStart] = useState<{
    pointerX: number;
    pointerY: number;
    pan: PanState;
  } | null>(null);
  const sheetFrameRef = useRef<HTMLDivElement | null>(null);

  const activeSheet = sheets.find((sheet) => sheet.id === activeSheetId) ?? sheets[0] ?? null;
  const activeIndex = activeSheet ? sheets.findIndex((sheet) => sheet.id === activeSheet.id) : -1;
  const activeFinding =
    findings.find((finding) => finding.id === activeFindingId) ?? findings[0] ?? null;
  const activeFindingIndex = activeFinding
    ? findings.findIndex((finding) => finding.id === activeFinding.id)
    : -1;

  function resetView(nextZoom = 0.55) {
    setZoom(nextZoom);
    setPan({ x: 0, y: 0 });
  }

  function setActiveSheet(sheet: Sheet) {
    setActiveSheetId(sheet.id);
    setActiveFindingId("");
    resetView();
  }

  function moveSheet(offset: number) {
    if (activeIndex < 0 || sheets.length === 0) {
      return;
    }

    const nextIndex = (activeIndex + offset + sheets.length) % sheets.length;
    setActiveSheet(sheets[nextIndex]);
  }

  function handlePointerDown(event: PointerEvent<HTMLDivElement>) {
    if (manualMode) {
      const point = toPdfPoint(event);
      if (point) {
        setManualStart(point);
        setManualDraft(point);
      }
      return;
    }

    event.currentTarget.setPointerCapture(event.pointerId);
    setDragStart({
      pointerX: event.clientX,
      pointerY: event.clientY,
      pan
    });
  }

  function handlePointerMove(event: PointerEvent<HTMLDivElement>) {
    if (manualMode && manualStart) {
      setManualDraft(toPdfPoint(event));
      return;
    }

    if (!dragStart) {
      return;
    }

    setPan({
      x: dragStart.pan.x + event.clientX - dragStart.pointerX,
      y: dragStart.pan.y + event.clientY - dragStart.pointerY
    });
  }

  function toPdfPoint(event: PointerEvent<HTMLDivElement>): PanState | null {
    const frame = sheetFrameRef.current;
    if (!frame) {
      return null;
    }

    const rect = frame.getBoundingClientRect();
    return {
      x: (event.clientX - rect.left) / zoom / renderScale,
      y: (event.clientY - rect.top) / zoom / renderScale
    };
  }

  async function handlePointerUp() {
    setDragStart(null);

    if (!manualMode || !manualStart || !manualDraft || !activeSheet) {
      return;
    }

    const bbox = {
      x0: Math.max(0, Math.min(manualStart.x, manualDraft.x)),
      y0: Math.max(0, Math.min(manualStart.y, manualDraft.y)),
      x1: Math.min(activeSheet.width_pt, Math.max(manualStart.x, manualDraft.x)),
      y1: Math.min(activeSheet.height_pt, Math.max(manualStart.y, manualDraft.y))
    };

    setManualStart(null);
    setManualDraft(null);

    if (Math.abs(bbox.x1 - bbox.x0) < 4 || Math.abs(bbox.y1 - bbox.y0) < 4) {
      return;
    }

    const description = window.prompt("Descricao do achado manual:");
    if (!description) {
      return;
    }

    try {
      const finding = await createManualFinding(apiBaseUrl, activeSheet.id, {
        category: "composition",
        type: "attention",
        description,
        severity: "medium",
        confidence: 1,
        bbox,
        evidence: ["Regiao selecionada manualmente no viewer."]
      });
      setFindings((current) => [finding, ...current]);
      setActiveFindingId(finding.id);
      setManualMode(false);
      setShowFindings(true);
    } catch (manualError) {
      setError(manualError instanceof Error ? manualError.message : "Falha ao criar achado.");
    }
  }

  async function handleRunAudit() {
    if (!activeSheet) {
      return;
    }

    setIsAuditing(true);
    setError(null);

    try {
      const auditRun = await runSheetAudit(apiBaseUrl, activeSheet.id);
      setFindings(auditRun.findings);
      setActiveFindingId(auditRun.findings[0]?.id ?? "");
      setShowFindings(true);
    } catch (auditError) {
      setError(auditError instanceof Error ? auditError.message : "Falha ao executar auditoria.");
    } finally {
      setIsAuditing(false);
    }
  }

  async function setFindingStatus(status: "confirmed" | "rejected") {
    if (!activeFinding) {
      return;
    }

    const rejectionReason =
      status === "rejected" ? window.prompt("Motivo da rejeicao:") ?? undefined : undefined;

    try {
      const updated = await updateFindingStatus(
        apiBaseUrl,
        activeFinding.id,
        status,
        rejectionReason
      );
      setFindings((current) =>
        current.map((finding) => (finding.id === updated.id ? updated : finding))
      );
    } catch (feedbackError) {
      setError(feedbackError instanceof Error ? feedbackError.message : "Falha ao salvar feedback.");
    }
  }

  function moveFinding(offset: number) {
    if (activeFindingIndex < 0 || findings.length === 0) {
      return;
    }

    const nextIndex = (activeFindingIndex + offset + findings.length) % findings.length;
    const nextFinding = findings[nextIndex];
    setActiveFindingId(nextFinding.id);
    setPan({
      x: (activeSheet!.width_pt / 2 - (nextFinding.bbox.x0 + nextFinding.bbox.x1) / 2) * zoom,
      y: (activeSheet!.height_pt / 2 - (nextFinding.bbox.y0 + nextFinding.bbox.y1) / 2) * zoom
    });
  }

  useEffect(() => {
    let isMounted = true;

    async function loadFindings() {
      if (!activeSheet) {
        return;
      }

      try {
        const sheetFindings = await listSheetFindings(apiBaseUrl, activeSheet.id);
        if (isMounted) {
          setFindings(sheetFindings);
          setActiveFindingId(sheetFindings[0]?.id ?? "");
        }
      } catch (loadError) {
        if (isMounted) {
          setError(loadError instanceof Error ? loadError.message : "Falha ao carregar achados.");
        }
      }
    }

    void loadFindings();

    return () => {
      isMounted = false;
    };
  }, [activeSheet, apiBaseUrl]);

  if (!activeSheet) {
    return (
      <div className="flex min-h-[520px] items-center justify-center border border-truss-line bg-truss-base p-6 text-center">
        <div>
          <Eye aria-hidden="true" className="mx-auto h-5 w-5 text-truss-accent" />
          <p className="mt-4 font-mono text-xs uppercase tracking-[0.16em] text-truss-muted">
            Viewer sem prancha
          </p>
          <p className="mt-3 max-w-md text-sm leading-6 text-truss-muted">
            Importe um PDF em uma revisao para liberar a visualizacao das folhas.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="border border-truss-line bg-truss-base">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-truss-line px-4 py-3">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.16em] text-truss-muted">
            Prancha ativa
          </p>
          <p className="mt-1 text-sm font-semibold text-truss-text">
            {activeSheet.label}
            {"documentName" in activeSheet ? ` | ${activeSheet.documentName}` : ""}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            className="inline-flex items-center gap-2 border border-truss-accent px-3 py-2 text-sm font-semibold text-truss-text hover:bg-truss-accent hover:text-truss-base disabled:cursor-not-allowed disabled:opacity-50"
            disabled={isAuditing}
            onClick={() => void handleRunAudit()}
            type="button"
          >
            <ScanSearch aria-hidden="true" className="h-4 w-4" />
            {isAuditing ? "Auditando" : "Auditar"}
          </button>
          <button
            className="inline-flex h-9 w-9 items-center justify-center border border-truss-line text-truss-muted hover:border-truss-accent hover:text-truss-text data-[active=true]:border-truss-accent data-[active=true]:text-truss-text"
            data-active={showFindings}
            onClick={() => setShowFindings((current) => !current)}
            title="Mostrar ou ocultar achados"
            type="button"
          >
            {showFindings ? (
              <Eye aria-hidden="true" className="h-4 w-4" />
            ) : (
              <EyeOff aria-hidden="true" className="h-4 w-4" />
            )}
          </button>
          <button
            className="inline-flex h-9 w-9 items-center justify-center border border-truss-line text-truss-muted hover:border-truss-accent hover:text-truss-text data-[active=true]:border-truss-accent data-[active=true]:text-truss-text"
            data-active={manualMode}
            onClick={() => setManualMode((current) => !current)}
            title="Adicionar achado manual"
            type="button"
          >
            <SquareMousePointer aria-hidden="true" className="h-4 w-4" />
          </button>
          <button
            className="inline-flex h-9 w-9 items-center justify-center border border-truss-line text-truss-muted hover:border-truss-accent hover:text-truss-text"
            onClick={() => moveSheet(-1)}
            title="Folha anterior"
            type="button"
          >
            <ChevronLeft aria-hidden="true" className="h-4 w-4" />
          </button>
          <button
            className="inline-flex h-9 w-9 items-center justify-center border border-truss-line text-truss-muted hover:border-truss-accent hover:text-truss-text"
            onClick={() => moveSheet(1)}
            title="Proxima folha"
            type="button"
          >
            <ChevronRight aria-hidden="true" className="h-4 w-4" />
          </button>
          <button
            className="inline-flex h-9 w-9 items-center justify-center border border-truss-line text-truss-muted hover:border-truss-accent hover:text-truss-text"
            onClick={() => resetView()}
            title="Fit"
            type="button"
          >
            <Maximize2 aria-hidden="true" className="h-4 w-4" />
          </button>
          <button
            className="inline-flex h-9 w-9 items-center justify-center border border-truss-line text-truss-muted hover:border-truss-accent hover:text-truss-text"
            onClick={() => setZoom((current) => clampZoom(current - 0.15))}
            title="Reduzir zoom"
            type="button"
          >
            <Minus aria-hidden="true" className="h-4 w-4" />
          </button>
          <span className="w-14 text-center font-mono text-xs text-truss-muted">
            {Math.round(zoom * 100)}%
          </span>
          <button
            className="inline-flex h-9 w-9 items-center justify-center border border-truss-line text-truss-muted hover:border-truss-accent hover:text-truss-text"
            onClick={() => setZoom((current) => clampZoom(current + 0.15))}
            title="Ampliar zoom"
            type="button"
          >
            <Plus aria-hidden="true" className="h-4 w-4" />
          </button>
        </div>
      </div>

      {error ? (
        <div className="border-b border-truss-accent bg-truss-accent/10 px-4 py-2 text-sm text-truss-text">
          {error}
        </div>
      ) : null}

      {activeFinding ? (
        <div className="grid gap-3 border-b border-truss-line bg-truss-panel px-4 py-3 lg:grid-cols-[minmax(0,1fr)_auto]">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.14em] text-truss-muted">
              Achado {activeFindingIndex + 1} de {findings.length} | {activeFinding.severity} |{" "}
              {activeFinding.status}
            </p>
            <p className="mt-1 text-sm text-truss-text">{activeFinding.description}</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              className="inline-flex h-9 w-9 items-center justify-center border border-truss-line text-truss-muted hover:border-truss-accent hover:text-truss-text"
              onClick={() => moveFinding(-1)}
              title="Achado anterior"
              type="button"
            >
              <ChevronLeft aria-hidden="true" className="h-4 w-4" />
            </button>
            <button
              className="inline-flex h-9 w-9 items-center justify-center border border-truss-line text-truss-muted hover:border-truss-accent hover:text-truss-text"
              onClick={() => moveFinding(1)}
              title="Proximo achado"
              type="button"
            >
              <ChevronRight aria-hidden="true" className="h-4 w-4" />
            </button>
            <button
              className="inline-flex h-9 w-9 items-center justify-center border border-truss-line text-truss-muted hover:border-emerald-400 hover:text-emerald-300"
              onClick={() => void setFindingStatus("confirmed")}
              title="Confirmar achado"
              type="button"
            >
              <Check aria-hidden="true" className="h-4 w-4" />
            </button>
            <button
              className="inline-flex h-9 w-9 items-center justify-center border border-truss-line text-truss-muted hover:border-truss-accent hover:text-truss-accent"
              onClick={() => void setFindingStatus("rejected")}
              title="Rejeitar achado"
              type="button"
            >
              <X aria-hidden="true" className="h-4 w-4" />
            </button>
          </div>
        </div>
      ) : null}

      <div className="grid min-h-[620px] grid-cols-[150px_minmax(0,1fr)]">
        <aside className="border-r border-truss-line bg-truss-panel">
          <div className="border-b border-truss-line px-3 py-2 font-mono text-xs uppercase tracking-[0.14em] text-truss-muted">
            Folhas
          </div>
          <div className="max-h-[620px] overflow-y-auto">
            {sheets.map((sheet, index) => (
              <button
                className="block w-full border-b border-truss-line px-3 py-3 text-left hover:bg-truss-base data-[active=true]:bg-truss-base"
                data-active={sheet.id === activeSheet.id}
                key={sheet.id}
                onClick={() => setActiveSheet(sheet)}
                type="button"
              >
                <span className="font-mono text-xs text-truss-muted">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span className="mt-1 block text-sm font-semibold text-truss-text">
                  {sheet.label}
                </span>
                <span className="mt-1 block font-mono text-[11px] text-truss-muted">
                  {Math.round(sheet.width_pt)} x {Math.round(sheet.height_pt)} pt
                </span>
              </button>
            ))}
          </div>
        </aside>

        <div
          className="relative overflow-hidden bg-[linear-gradient(to_right,rgba(154,163,177,0.08)_1px,transparent_1px),linear-gradient(to_bottom,rgba(154,163,177,0.08)_1px,transparent_1px)] bg-[size:28px_28px]"
          onPointerDown={handlePointerDown}
          onPointerLeave={() => setDragStart(null)}
          onPointerMove={handlePointerMove}
          onPointerUp={() => void handlePointerUp()}
          role="presentation"
        >
          <div className="absolute left-3 top-3 z-10 flex items-center gap-2 border border-truss-line bg-truss-panel/95 px-3 py-2 font-mono text-xs text-truss-muted">
            <Crosshair aria-hidden="true" className="h-3.5 w-3.5 text-truss-accent" />
            {manualMode ? "Selecione uma regiao para achado manual" : "Pan por arrasto | Coordenadas PDF em pt"}
          </div>
          <div
            className="flex h-full min-h-[620px] items-center justify-center transition-transform duration-150 ease-out"
            style={{
              transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`
            }}
          >
            <div className="relative" ref={sheetFrameRef}>
              {/* eslint-disable-next-line @next/next/no-img-element -- Local rendered PDF sheets need direct transform control. */}
              <img
                alt={`Render da ${activeSheet.label}`}
                className="max-h-none max-w-none select-none border border-truss-line bg-zinc-100 shadow-[0_18px_60px_rgba(0,0,0,0.38)]"
                draggable={false}
                src={`${apiBaseUrl}/sheets/${activeSheet.id}/image`}
              />
              {showFindings
                ? findings.map((finding) => (
                    <button
                      className="absolute border-2 border-truss-accent bg-truss-accent/10 text-left shadow-[0_0_0_1px_rgba(0,0,0,0.75)] data-[active=true]:border-emerald-300 data-[status=confirmed]:border-emerald-400 data-[status=rejected]:border-zinc-500"
                      data-active={finding.id === activeFinding?.id}
                      data-status={finding.status}
                      key={finding.id}
                      onClick={(event) => {
                        event.stopPropagation();
                        setActiveFindingId(finding.id);
                      }}
                      style={{
                        left: finding.bbox.x0 * renderScale,
                        top: finding.bbox.y0 * renderScale,
                        width: (finding.bbox.x1 - finding.bbox.x0) * renderScale,
                        height: (finding.bbox.y1 - finding.bbox.y0) * renderScale
                      }}
                      title={finding.description}
                      type="button"
                    >
                      <span className="absolute -left-2 -top-2 inline-flex h-5 min-w-5 items-center justify-center border border-truss-accent bg-truss-base px-1 font-mono text-[10px] text-truss-text">
                        <LocateFixed aria-hidden="true" className="h-3 w-3" />
                      </span>
                    </button>
                  ))
                : null}
              {manualStart && manualDraft ? (
                <div
                  className="pointer-events-none absolute border-2 border-emerald-300 bg-emerald-300/10"
                  style={{
                    left: Math.min(manualStart.x, manualDraft.x) * renderScale,
                    top: Math.min(manualStart.y, manualDraft.y) * renderScale,
                    width: Math.abs(manualDraft.x - manualStart.x) * renderScale,
                    height: Math.abs(manualDraft.y - manualStart.y) * renderScale
                  }}
                />
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
