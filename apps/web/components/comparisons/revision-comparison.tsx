"use client";

import {
  Crosshair,
  Columns2,
  Eye,
  Layers,
  Link2,
  Loader2,
  Plus,
  RefreshCcw,
  Unlink,
} from "lucide-react";
import {
  PointerEvent as ReactPointerEvent,
  WheelEvent as ReactWheelEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  ComparisonRegion,
  ComparisonSheet,
  ComparisonSheetPair,
  ComparisonStatus,
  createComparisonPairing,
  createManualFinding,
  createRevisionComparison,
  FindingSeverity,
  Revision,
  RevisionComparison,
  revokeComparisonPairing,
} from "@/lib/projects-api";
import {
  CANVAS_NAVIGATION,
  clampViewportToSheet,
  viewportForBounds,
  wheelIntent,
  zoomAtScreenPoint,
  type Viewport,
} from "@/lib/canvas-navigation";

type RevisionComparisonProps = {
  apiBaseUrl: string;
  projectId: string;
  revisions: Revision[];
  initialTargetRevisionId: string;
};

type DisplayMode = "split" | "overlay" | "blink";

const STATUS: Record<ComparisonStatus, { label: string; className: string }> = {
  changed: { label: "Alterada", className: "text-truss-danger" },
  identical: { label: "Idêntica", className: "text-truss-success" },
  added: { label: "Adicionada", className: "text-truss-info" },
  removed: { label: "Removida", className: "text-truss-warning" },
  ambiguous: { label: "Ambígua", className: "text-truss-warning" },
  unavailable: { label: "Indisponível", className: "text-truss-subtle" },
};

const MATCH_METHOD = {
  manual: "vínculo manual",
  sheet_code: "código canônico",
  exact_content: "conteúdo idêntico",
  unmatched: "sem pareamento",
} as const;

function sheetName(sheet: ComparisonSheet | null) {
  if (!sheet) return "—";
  return sheet.sheet_code ?? `Folha ${sheet.sheet_number}`;
}

function uniqueSheets(sheets: Array<ComparisonSheet | null>) {
  const found = new Map<string, ComparisonSheet>();
  for (const sheet of sheets) {
    if (sheet) found.set(sheet.id, sheet);
  }
  return [...found.values()].sort((a, b) => a.sheet_number - b.sheet_number);
}

function hasCompatibleGeometry(pair: ComparisonSheetPair | null) {
  const base = pair?.base_sheet;
  const target = pair?.target_sheet;
  return Boolean(
    base &&
      target &&
      Math.abs(base.width_pt - target.width_pt) < 0.01 &&
      Math.abs(base.height_pt - target.height_pt) < 0.01 &&
      base.rotation === target.rotation
  );
}

function defaultFindingDescription(
  pair: ComparisonSheetPair | null,
  comparison: RevisionComparison | null
) {
  if (!pair?.target_sheet || !pair.regions.length) return "";
  return `Alteração gráfica entre ${comparison?.base_revision_code ?? "a revisão-base"} e ${comparison?.target_revision_code ?? "a revisão-alvo"} em ${sheetName(pair.target_sheet)}.`;
}

function ComparisonCanvas({
  apiBaseUrl,
  label,
  layers,
  regions,
  regionSide,
  selectedRegionId,
  viewport,
  onViewportChange,
  onCanvasSize,
  onSelectRegion,
}: {
  apiBaseUrl: string;
  label: string;
  layers: Array<{ sheet: ComparisonSheet; opacity: number; className?: string }>;
  regions: ComparisonRegion[];
  regionSide: "base" | "target";
  selectedRegionId: string | null;
  viewport: Viewport;
  onViewportChange: (viewport: Viewport) => void;
  onCanvasSize: (size: { width: number; height: number }) => void;
  onSelectRegion: (region: ComparisonRegion) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ pointerId: number; x: number; y: number; viewport: Viewport } | null>(null);
  const primarySheet = layers[0]?.sheet;

  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;
    const update = () => onCanvasSize({ width: node.clientWidth, height: node.clientHeight });
    update();
    const observer = new ResizeObserver(update);
    observer.observe(node);
    return () => observer.disconnect();
  }, [onCanvasSize]);

  function handleWheel(event: ReactWheelEvent<HTMLDivElement>) {
    if (!primarySheet) return;
    event.preventDefault();
    const intent = wheelIntent(event);
    const rect = event.currentTarget.getBoundingClientRect();
    const size = { width: rect.width, height: rect.height };
    if (intent.kind === "zoom") {
      const next = zoomAtScreenPoint(viewport, viewport.zoom * intent.factor, {
        x: event.clientX - rect.left,
        y: event.clientY - rect.top,
      });
      onViewportChange(
        clampViewportToSheet(next, { width: primarySheet.width_pt, height: primarySheet.height_pt }, size)
      );
      return;
    }
    onViewportChange(
      clampViewportToSheet(
        { ...viewport, x: viewport.x + intent.deltaX, y: viewport.y + intent.deltaY },
        { width: primarySheet.width_pt, height: primarySheet.height_pt },
        size
      )
    );
  }

  function handlePointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = {
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      viewport,
    };
  }

  function handlePointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId || !primarySheet) return;
    const rect = event.currentTarget.getBoundingClientRect();
    onViewportChange(
      clampViewportToSheet(
        {
          ...drag.viewport,
          x: drag.viewport.x + event.clientX - drag.x,
          y: drag.viewport.y + event.clientY - drag.y,
        },
        { width: primarySheet.width_pt, height: primarySheet.height_pt },
        { width: rect.width, height: rect.height }
      )
    );
  }

  return (
    <div
      aria-label={`${label}. Arraste para mover; use a roda para zoom.`}
      className="relative min-h-[420px] flex-1 touch-none overflow-hidden bg-truss-canvas"
      onPointerCancel={() => (dragRef.current = null)}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={() => (dragRef.current = null)}
      onWheel={handleWheel}
      ref={containerRef}
    >
      <span className="absolute left-3 top-3 z-20 border border-truss-line bg-truss-panel/95 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.06em] text-truss-muted">
        {label}
      </span>
      {layers.map(({ sheet, opacity, className }, index) => (
        <div
          className="absolute left-0 top-0 origin-top-left"
          key={`${sheet.id}:${index}`}
          style={{
            height: sheet.height_pt * CANVAS_NAVIGATION.renderScale,
            transform: `translate(${viewport.x}px, ${viewport.y}px) scale(${viewport.zoom})`,
            width: sheet.width_pt * CANVAS_NAVIGATION.renderScale,
          }}
        >
          {/* eslint-disable-next-line @next/next/no-img-element -- local PDF render needs direct canvas transforms */}
          <img
            alt={`${label}: ${sheetName(sheet)}`}
            className={`absolute inset-0 max-h-none max-w-none select-none bg-truss-sheet ${className ?? ""}`}
            draggable={false}
            src={`${apiBaseUrl}/sheets/${sheet.id}/image`}
            style={{
              height: sheet.height_pt * CANVAS_NAVIGATION.renderScale,
              opacity,
              width: sheet.width_pt * CANVAS_NAVIGATION.renderScale,
            }}
          />
          {index === layers.length - 1
            ? regions.map((region) => {
                const bbox = regionSide === "base" ? region.base_bbox : region.target_bbox;
                const selected = selectedRegionId === region.id;
                return (
                  <button
                    aria-label={`Alteração ${region.region_index + 1}`}
                    className="absolute border border-truss-danger bg-truss-accent/10 transition-colors hover:bg-truss-accent/20 data-[selected=true]:bg-truss-accent/25 data-[selected=true]:shadow-[inset_0_0_0_1px_var(--red)]"
                    data-selected={selected}
                    key={region.id}
                    onPointerDown={(event) => event.stopPropagation()}
                    onClick={(event) => {
                      event.stopPropagation();
                      onSelectRegion(region);
                    }}
                    style={{
                      height: (bbox.y1 - bbox.y0) * CANVAS_NAVIGATION.renderScale,
                      left: bbox.x0 * CANVAS_NAVIGATION.renderScale,
                      top: bbox.y0 * CANVAS_NAVIGATION.renderScale,
                      width: (bbox.x1 - bbox.x0) * CANVAS_NAVIGATION.renderScale,
                    }}
                    type="button"
                  >
                    <span className="absolute -left-px -top-5 bg-truss-accent px-1.5 py-0.5 font-mono text-[9px] text-white">
                      Δ{region.region_index + 1}
                    </span>
                  </button>
                );
              })
            : null}
        </div>
      ))}
    </div>
  );
}

export function RevisionComparisonPanel({
  apiBaseUrl,
  projectId,
  revisions,
  initialTargetRevisionId,
}: RevisionComparisonProps) {
  const targetIndex = Math.max(0, revisions.findIndex((item) => item.id === initialTargetRevisionId));
  const initialBase = revisions[Math.max(0, targetIndex - 1)]?.id ?? "";
  const [baseRevisionId, setBaseRevisionId] = useState(
    initialBase === initialTargetRevisionId ? revisions.find((item) => item.id !== initialTargetRevisionId)?.id ?? "" : initialBase
  );
  const [targetRevisionId, setTargetRevisionId] = useState(initialTargetRevisionId);
  const [comparison, setComparison] = useState<RevisionComparison | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [statusFilter, setStatusFilter] = useState<ComparisonStatus | "all">("all");
  const [selectedPairId, setSelectedPairId] = useState<string | null>(null);
  const [selectedRegionId, setSelectedRegionId] = useState<string | null>(null);
  const [displayMode, setDisplayMode] = useState<DisplayMode>("split");
  const [blinkTarget, setBlinkTarget] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [viewport, setViewport] = useState<Viewport>({ x: 24, y: 24, zoom: 0.2 });
  const [canvasSize, setCanvasSize] = useState({ width: 900, height: 520 });
  const [manualBaseSheetId, setManualBaseSheetId] = useState("");
  const [manualTargetSheetId, setManualTargetSheetId] = useState("");
  const [isPairing, setIsPairing] = useState(false);
  const [findingDescription, setFindingDescription] = useState("");
  const [findingSeverity, setFindingSeverity] = useState<FindingSeverity>("medium");
  const [findingStatus, setFindingStatus] = useState("");

  const applyComparison = useCallback((result: RevisionComparison) => {
    const nextPair =
      result.pairs.find((pair) => pair.status === "changed") ?? result.pairs[0] ?? null;
    setComparison(result);
    setSelectedPairId(nextPair?.id ?? null);
    setSelectedRegionId(nextPair?.regions[0]?.id ?? null);
    setFindingDescription(defaultFindingDescription(nextPair, result));
    setFindingStatus("");
    setDisplayMode("split");
  }, []);

  const loadComparison = useCallback(async () => {
    if (!baseRevisionId || !targetRevisionId || baseRevisionId === targetRevisionId) return;
    setIsLoading(true);
    setError("");
    try {
      const result = await createRevisionComparison(
        apiBaseUrl,
        projectId,
        baseRevisionId,
        targetRevisionId
      );
      applyComparison(result);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Falha ao comparar revisões.");
    } finally {
      setIsLoading(false);
    }
  }, [apiBaseUrl, applyComparison, baseRevisionId, projectId, targetRevisionId]);

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (!baseRevisionId || !targetRevisionId || baseRevisionId === targetRevisionId) return;
    let cancelled = false;
    createRevisionComparison(apiBaseUrl, projectId, baseRevisionId, targetRevisionId)
      .then((result) => {
        if (!cancelled) applyComparison(result);
      })
      .catch((loadError: unknown) => {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Falha ao comparar revisões.");
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, applyComparison, baseRevisionId, projectId, targetRevisionId]);

  useEffect(() => {
    if (displayMode !== "blink" || reducedMotion) return;
    const timer = window.setInterval(() => setBlinkTarget((current) => !current), 850);
    return () => window.clearInterval(timer);
  }, [displayMode, reducedMotion]);

  const filteredPairs = useMemo(
    () => comparison?.pairs.filter((pair) => statusFilter === "all" || pair.status === statusFilter) ?? [],
    [comparison, statusFilter]
  );
  const selectedPair =
    comparison?.pairs.find((pair) => pair.id === selectedPairId) ?? comparison?.pairs[0] ?? null;
  const selectedRegion =
    selectedPair?.regions.find((region) => region.id === selectedRegionId) ?? selectedPair?.regions[0] ?? null;
  const geometryCompatible = hasCompatibleGeometry(selectedPair);
  const baseSheets = useMemo(
    () => uniqueSheets(comparison?.pairs.map((pair) => pair.base_sheet) ?? []),
    [comparison]
  );
  const targetSheets = useMemo(
    () => uniqueSheets(comparison?.pairs.map((pair) => pair.target_sheet) ?? []),
    [comparison]
  );

  const resolvedManualBaseSheetId = baseSheets.some((sheet) => sheet.id === manualBaseSheetId)
    ? manualBaseSheetId
    : baseSheets[0]?.id ?? "";
  const resolvedManualTargetSheetId = targetSheets.some((sheet) => sheet.id === manualTargetSheetId)
    ? manualTargetSheetId
    : targetSheets[0]?.id ?? "";

  async function handlePair() {
    if (!resolvedManualBaseSheetId || !resolvedManualTargetSheetId) return;
    setIsPairing(true);
    setError("");
    try {
      await createComparisonPairing(apiBaseUrl, projectId, {
        base_revision_id: baseRevisionId,
        target_revision_id: targetRevisionId,
        base_sheet_id: resolvedManualBaseSheetId,
        target_sheet_id: resolvedManualTargetSheetId,
      });
      await loadComparison();
    } catch (pairError) {
      setError(pairError instanceof Error ? pairError.message : "Falha ao salvar o pareamento.");
    } finally {
      setIsPairing(false);
    }
  }

  async function handleRevokePairing(pair: ComparisonSheetPair) {
    if (!pair.pairing_override_id) return;
    setIsPairing(true);
    try {
      await revokeComparisonPairing(apiBaseUrl, pair.pairing_override_id);
      await loadComparison();
    } catch (pairError) {
      setError(pairError instanceof Error ? pairError.message : "Falha ao revogar o pareamento.");
    } finally {
      setIsPairing(false);
    }
  }

  function focusRegion(region: ComparisonRegion) {
    const bbox = region.base_bbox;
    setSelectedRegionId(region.id);
    setViewport(viewportForBounds(bbox, canvasSize, { paddingPx: 72, maxZoom: 1.6 }));
  }

  function handleSelectPair(pair: ComparisonSheetPair) {
    const sheet = pair.base_sheet ?? pair.target_sheet;
    setSelectedPairId(pair.id);
    setSelectedRegionId(pair.regions[0]?.id ?? null);
    setFindingDescription(defaultFindingDescription(pair, comparison));
    setFindingStatus("");
    if (!hasCompatibleGeometry(pair)) setDisplayMode("split");
    if (sheet) {
      setViewport(
        viewportForBounds(
          { x0: 0, y0: 0, x1: sheet.width_pt, y1: sheet.height_pt },
          canvasSize,
          { maxZoom: 1 }
        )
      );
    }
  }

  async function handleCreateFinding() {
    if (!selectedPair?.target_sheet || !selectedRegion || !findingDescription.trim()) return;
    setFindingStatus("Salvando achado manual...");
    try {
      await createManualFinding(apiBaseUrl, selectedPair.target_sheet.id, {
        category: "revision_comparison",
        type: "attention",
        description: findingDescription.trim(),
        severity: findingSeverity,
        confidence: 1,
        bbox: selectedRegion.target_bbox,
        evidence: [
          `Comparação ${comparison?.base_revision_code} → ${comparison?.target_revision_code}.`,
          `Região Δ${selectedRegion.region_index + 1} detectada por ${comparison?.pipeline_version}.`,
          "Diferença gráfica promovida manualmente; não representa erro confirmado.",
        ],
      });
      setFindingStatus("Achado manual criado na revisão-alvo.");
    } catch (findingError) {
      setFindingStatus(
        findingError instanceof Error ? findingError.message : "Falha ao criar o achado manual."
      );
    }
  }

  const updateCanvasSize = useCallback(
    (size: { width: number; height: number }) => {
      setCanvasSize((current) =>
        current.width === size.width && current.height === size.height ? current : size
      );
      const sheet = selectedPair?.base_sheet ?? selectedPair?.target_sheet;
      if (sheet && size.width > 0 && size.height > 0) {
        setViewport(
          viewportForBounds(
            { x0: 0, y0: 0, x1: sheet.width_pt, y1: sheet.height_pt },
            size,
            { maxZoom: 1 }
          )
        );
      }
    },
    [selectedPair]
  );

  if (revisions.length < 2) {
    return (
      <div className="flex min-h-[520px] items-center justify-center border border-dashed border-truss-line bg-truss-panel p-8 text-center">
        <div className="max-w-md">
          <Layers aria-hidden="true" className="truss-icon mx-auto h-5 w-5 text-truss-accent" />
          <p className="mt-4 text-sm font-semibold text-truss-text">Duas revisões são necessárias</p>
          <p className="mt-2 text-sm leading-6 text-truss-muted">
            Importe uma nova exportação como revisão imutável para iniciar a comparação gráfica.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col border border-truss-line bg-truss-panel">
      <div className="flex flex-wrap items-end gap-3 border-b border-truss-line bg-truss-raised p-3">
        <label className="min-w-40 flex-1">
          <span className="truss-mono-label">Revisão-base</span>
          <select
            className="truss-field mt-1 w-full px-3 font-mono text-sm"
            onChange={(event) => {
              setBaseRevisionId(event.target.value);
              setComparison(null);
              setIsLoading(true);
              setError("");
            }}
            value={baseRevisionId}
          >
            {revisions.map((revision) => (
              <option disabled={revision.id === targetRevisionId} key={revision.id} value={revision.id}>
                {revision.revision_code}
              </option>
            ))}
          </select>
        </label>
        <span className="pb-2 font-mono text-sm text-truss-subtle">→</span>
        <label className="min-w-40 flex-1">
          <span className="truss-mono-label">Revisão-alvo</span>
          <select
            className="truss-field mt-1 w-full px-3 font-mono text-sm"
            onChange={(event) => {
              setTargetRevisionId(event.target.value);
              setComparison(null);
              setIsLoading(true);
              setError("");
            }}
            value={targetRevisionId}
          >
            {revisions.map((revision) => (
              <option disabled={revision.id === baseRevisionId} key={revision.id} value={revision.id}>
                {revision.revision_code}
              </option>
            ))}
          </select>
        </label>
        <button className="truss-button" disabled={isLoading} onClick={() => void loadComparison()} type="button">
          {isLoading ? <Loader2 aria-hidden="true" className="truss-icon h-4 w-4 animate-spin" /> : <RefreshCcw aria-hidden="true" className="truss-icon h-4 w-4" />}
          {isLoading ? "Comparando" : "Atualizar"}
        </button>
      </div>

      {error ? (
        <p className="border-b border-truss-danger/45 bg-truss-accentSoft px-4 py-3 text-sm text-[#ffb3aa]" role="alert">
          {error}
        </p>
      ) : null}

      {comparison ? (
        <>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-b border-truss-line px-3 py-2" aria-live="polite">
            <span className="font-mono text-[11px] text-truss-muted">
              {comparison.base_revision_code} → {comparison.target_revision_code}
            </span>
            {(["changed", "identical", "added", "removed", "ambiguous", "unavailable"] as ComparisonStatus[]).map((status) => (
              <button
                className={`font-mono text-[10px] uppercase tracking-[0.05em] ${STATUS[status].className}`}
                key={status}
                onClick={() => setStatusFilter(statusFilter === status ? "all" : status)}
                type="button"
              >
                {STATUS[status].label} {comparison.counts[status] ?? 0}
              </button>
            ))}
            <span className="ml-auto font-mono text-[10px] uppercase tracking-[0.05em] text-truss-subtle">
              {comparison.pipeline_version} · cache {comparison.input_fingerprint.slice(0, 8)}
            </span>
          </div>

          <div className="grid min-h-0 flex-1 grid-cols-1 xl:grid-cols-[260px_minmax(0,1fr)_286px]">
            <aside className="max-h-[720px] overflow-y-auto border-b border-truss-line xl:border-b-0 xl:border-r">
              <div className="sticky top-0 z-10 border-b border-truss-line bg-truss-raised p-2">
                <select
                  aria-label="Filtrar folhas por estado"
                  className="truss-field w-full px-2 font-mono text-xs"
                  onChange={(event) => setStatusFilter(event.target.value as ComparisonStatus | "all")}
                  value={statusFilter}
                >
                  <option value="all">Todas as folhas</option>
                  {Object.entries(STATUS).map(([value, item]) => (
                    <option key={value} value={value}>{item.label}</option>
                  ))}
                </select>
              </div>
              {filteredPairs.length ? (
                <ul>
                  {filteredPairs.map((pair) => (
                    <li className="border-b border-truss-line" key={pair.id}>
                      <button
                        className="w-full px-3 py-3 text-left transition-colors hover:bg-truss-panel2 data-[selected=true]:bg-truss-accentSoft data-[selected=true]:shadow-[inset_2px_0_0_var(--red)]"
                        data-selected={pair.id === selectedPair?.id}
                        onClick={() => handleSelectPair(pair)}
                        type="button"
                      >
                        <span className="flex items-center justify-between gap-2">
                          <span className="truncate font-mono text-[11px] text-truss-text">
                            {sheetName(pair.base_sheet)} → {sheetName(pair.target_sheet)}
                          </span>
                          <span className={`shrink-0 font-mono text-[9px] uppercase ${STATUS[pair.status].className}`}>
                            {STATUS[pair.status].label}
                          </span>
                        </span>
                        <span className="mt-1 block text-[11px] leading-4 text-truss-subtle">
                          {pair.summary}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="p-4 text-sm leading-6 text-truss-muted">Nenhuma folha neste filtro.</p>
              )}
            </aside>

            <main className="flex min-h-[520px] min-w-0 flex-col bg-truss-canvas">
              {selectedPair?.base_sheet && selectedPair.target_sheet && selectedPair.status !== "unavailable" ? (
                <>
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-truss-line bg-truss-raised p-2">
                    <div className="truss-segment">
                      <button aria-pressed={displayMode === "split"} className="truss-icon-button border-0" onClick={() => setDisplayMode("split")} title="Lado a lado" type="button">
                        <Columns2 aria-hidden="true" className="truss-icon h-4 w-4" />
                        <span className="sr-only">Lado a lado</span>
                      </button>
                      <button aria-pressed={displayMode === "overlay"} className="truss-icon-button border-0" disabled={!geometryCompatible} onClick={() => setDisplayMode("overlay")} title={geometryCompatible ? "Sobrepor revisões" : "Sobreposição indisponível: formato ou rotação diferente"} type="button">
                        <Layers aria-hidden="true" className="truss-icon h-4 w-4" />
                        <span className="sr-only">Sobrepor revisões</span>
                      </button>
                      <button aria-pressed={displayMode === "blink"} className="truss-icon-button border-0" disabled={!geometryCompatible} onClick={() => setDisplayMode("blink")} title={geometryCompatible ? "Alternar antes e depois" : "Alternância indisponível: formato ou rotação diferente"} type="button">
                        <Eye aria-hidden="true" className="truss-icon h-4 w-4" />
                        <span className="sr-only">Alternar antes e depois</span>
                      </button>
                    </div>
                    <div className="flex items-center gap-2">
                      {displayMode === "blink" ? (
                        <button className="truss-button" onClick={() => setBlinkTarget((current) => !current)} type="button">
                          Mostrar {blinkTarget ? "antes" : "depois"}
                        </button>
                      ) : null}
                      <button
                        className="truss-button"
                        onClick={() => {
                          const sheet = selectedPair.base_sheet ?? selectedPair.target_sheet;
                          if (sheet) setViewport(viewportForBounds({ x0: 0, y0: 0, x1: sheet.width_pt, y1: sheet.height_pt }, canvasSize, { maxZoom: 1 }));
                        }}
                        type="button"
                      >
                        Fit
                      </button>
                      <span className="min-w-14 text-right font-mono text-[11px] text-truss-subtle">{Math.round(viewport.zoom * 100)}%</span>
                    </div>
                  </div>
                  <div className={`flex min-h-0 flex-1 ${displayMode === "split" ? "divide-x divide-truss-line" : ""}`}>
                    {displayMode === "split" ? (
                      <>
                        <ComparisonCanvas apiBaseUrl={apiBaseUrl} label={`Antes · ${comparison.base_revision_code}`} layers={[{ sheet: selectedPair.base_sheet, opacity: 1 }]} onCanvasSize={updateCanvasSize} onSelectRegion={focusRegion} onViewportChange={setViewport} regionSide="base" regions={selectedPair.regions} selectedRegionId={selectedRegionId} viewport={viewport} />
                        <ComparisonCanvas apiBaseUrl={apiBaseUrl} label={`Depois · ${comparison.target_revision_code}`} layers={[{ sheet: selectedPair.target_sheet, opacity: 1 }]} onCanvasSize={updateCanvasSize} onSelectRegion={focusRegion} onViewportChange={setViewport} regionSide="target" regions={selectedPair.regions} selectedRegionId={selectedRegionId} viewport={viewport} />
                      </>
                    ) : displayMode === "overlay" ? (
                      <ComparisonCanvas apiBaseUrl={apiBaseUrl} label="Sobreposição · antes + depois" layers={[{ sheet: selectedPair.base_sheet, opacity: 1 }, { sheet: selectedPair.target_sheet, opacity: 0.5, className: "mix-blend-multiply" }]} onCanvasSize={updateCanvasSize} onSelectRegion={focusRegion} onViewportChange={setViewport} regionSide="target" regions={selectedPair.regions} selectedRegionId={selectedRegionId} viewport={viewport} />
                    ) : (
                      <ComparisonCanvas apiBaseUrl={apiBaseUrl} label={blinkTarget ? `Depois · ${comparison.target_revision_code}` : `Antes · ${comparison.base_revision_code}`} layers={[{ sheet: blinkTarget ? selectedPair.target_sheet : selectedPair.base_sheet, opacity: 1 }]} onCanvasSize={updateCanvasSize} onSelectRegion={focusRegion} onViewportChange={setViewport} regionSide={blinkTarget ? "target" : "base"} regions={selectedPair.regions} selectedRegionId={selectedRegionId} viewport={viewport} />
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-4 border-t border-truss-line bg-truss-raised px-3 py-2 font-mono text-[10px] uppercase tracking-[0.05em] text-truss-subtle">
                    <span>pareamento / {MATCH_METHOD[selectedPair.match_method]}</span>
                    <span>diferença / {(selectedPair.changed_ratio * 100).toFixed(3)}%</span>
                    <span>regiões / {selectedPair.regions.length}</span>
                    <span className={STATUS[selectedPair.status].className}>estado / {STATUS[selectedPair.status].label}</span>
                  </div>
                </>
              ) : (
                <div className="flex flex-1 items-center justify-center p-8 text-center">
                  <div className="max-w-md">
                    <Link2 aria-hidden="true" className="truss-icon mx-auto h-5 w-5 text-truss-warning" />
                    <p className="mt-4 text-sm font-semibold text-truss-text">
                      {selectedPair?.status === "unavailable" ? "Fonte PDF indisponível" : "Folha sem par verificável"}
                    </p>
                    <p className="mt-2 text-sm leading-6 text-truss-muted">
                      {selectedPair?.summary ?? "Selecione uma folha para inspecionar."}
                      {selectedPair?.status === "unavailable"
                        ? " Restaure a fonte local antes de inspecionar a diferença gráfica."
                        : " Use o pareamento manual ao lado somente quando você reconhecer a mesma prancha."}
                    </p>
                  </div>
                </div>
              )}
            </main>

            <aside className="max-h-[720px] overflow-y-auto border-t border-truss-line bg-truss-raised xl:border-l xl:border-t-0">
              <section className="border-b border-truss-line p-3">
                <h3 className="text-sm font-semibold text-truss-text">Pareamento de folhas</h3>
                <p className="mt-1 text-xs leading-5 text-truss-muted">
                  Confirme manualmente apenas quando os dois lados representam a mesma prancha.
                </p>
                <label className="mt-3 block">
                  <span className="truss-mono-label">Base</span>
                  <select className="truss-field mt-1 w-full px-2 font-mono text-xs" onChange={(event) => setManualBaseSheetId(event.target.value)} value={resolvedManualBaseSheetId}>
                    {baseSheets.map((sheet) => <option key={sheet.id} value={sheet.id}>{sheetName(sheet)}</option>)}
                  </select>
                </label>
                <label className="mt-2 block">
                  <span className="truss-mono-label">Alvo</span>
                  <select className="truss-field mt-1 w-full px-2 font-mono text-xs" onChange={(event) => setManualTargetSheetId(event.target.value)} value={resolvedManualTargetSheetId}>
                    {targetSheets.map((sheet) => <option key={sheet.id} value={sheet.id}>{sheetName(sheet)}</option>)}
                  </select>
                </label>
                <button className="truss-button mt-3 w-full" disabled={isPairing || !resolvedManualBaseSheetId || !resolvedManualTargetSheetId} onClick={() => void handlePair()} type="button">
                  {isPairing ? <Loader2 aria-hidden="true" className="truss-icon h-4 w-4 animate-spin" /> : <Link2 aria-hidden="true" className="truss-icon h-4 w-4" />}
                  Vincular folhas
                </button>
                {selectedPair?.pairing_override_id ? (
                  <button className="truss-button mt-2 w-full" disabled={isPairing} onClick={() => void handleRevokePairing(selectedPair)} type="button">
                    <Unlink aria-hidden="true" className="truss-icon h-4 w-4" />
                    Revogar vínculo atual
                  </button>
                ) : null}
              </section>

              <section className="border-b border-truss-line p-3">
                <h3 className="text-sm font-semibold text-truss-text">Regiões alteradas</h3>
                {selectedPair?.regions.length ? (
                  <ul className="mt-2 space-y-1">
                    {selectedPair.regions.map((region) => (
                      <li key={region.id}>
                        <button className="flex w-full items-center justify-between border border-transparent px-2 py-2 text-left hover:border-truss-line hover:bg-truss-panel data-[selected=true]:border-truss-accent/55 data-[selected=true]:bg-truss-accentSoft" data-selected={region.id === selectedRegion?.id} onClick={() => focusRegion(region)} type="button">
                          <span className="font-mono text-[11px] text-truss-text">Δ{region.region_index + 1}</span>
                          <span className="font-mono text-[9px] text-truss-subtle">{Math.round(region.base_bbox.x0)},{Math.round(region.base_bbox.y0)} → {Math.round(region.base_bbox.x1)},{Math.round(region.base_bbox.y1)} pt</span>
                          <Crosshair aria-hidden="true" className="truss-icon h-3.5 w-3.5 text-truss-accent" />
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-2 text-xs leading-5 text-truss-muted">Nenhuma região gráfica localizada para este par.</p>
                )}
              </section>

              {selectedPair?.target_sheet && selectedRegion ? (
                <section className="p-3">
                  <h3 className="text-sm font-semibold text-truss-text">Promover para achado</h3>
                  <p className="mt-1 text-xs leading-5 text-truss-muted">A diferença só vira hipótese após sua ação explícita.</p>
                  <label className="mt-3 block">
                    <span className="truss-mono-label">Descrição</span>
                    <textarea className="truss-field mt-1 w-full resize-y p-2 text-sm leading-5" onChange={(event) => setFindingDescription(event.target.value)} value={findingDescription} />
                  </label>
                  <label className="mt-2 block">
                    <span className="truss-mono-label">Severidade potencial</span>
                    <select className="truss-field mt-1 w-full px-2 font-mono text-xs" onChange={(event) => setFindingSeverity(event.target.value as FindingSeverity)} value={findingSeverity}>
                      <option value="low">LOW</option><option value="medium">MEDIUM</option><option value="high">HIGH</option><option value="critical">CRITICAL</option>
                    </select>
                  </label>
                  <button className="truss-button truss-button-primary mt-3 w-full" disabled={!findingDescription.trim()} onClick={() => void handleCreateFinding()} type="button">
                    <Plus aria-hidden="true" className="truss-icon h-4 w-4" /> Criar achado manual
                  </button>
                  {findingStatus ? <p className="mt-2 text-xs leading-5 text-truss-muted" role="status">{findingStatus}</p> : null}
                </section>
              ) : null}
            </aside>
          </div>
        </>
      ) : (
        <div className="flex min-h-[520px] items-center justify-center p-8 text-sm text-truss-muted">
          {isLoading ? "Construindo comparação local..." : "Escolha duas revisões para comparar."}
        </div>
      )}
    </div>
  );
}
