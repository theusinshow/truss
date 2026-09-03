"use client";

import { FormEvent, PointerEvent, WheelEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Check,
  ChevronLeft,
  ChevronRight,
  Eye,
  EyeOff,
  LayoutGrid,
  Maximize2,
  MessageSquare,
  Minus,
  MoreHorizontal,
  Plus,
  SlidersHorizontal,
  Sparkles,
  X
} from "lucide-react";

import {
  CANVAS_NAVIGATION,
  clampViewportToSheet,
  wheelIntent,
  normalizeRect,
  offsetRect,
  Point,
  Rect,
  rectHeight,
  rectsIntersect,
  rectWidth,
  screenToWorld,
  unionRects,
  Viewport,
  viewportForBounds,
  worldToScreen,
  zoomAtScreenPoint
} from "@/lib/canvas-navigation";
import {
  AuditCoverage,
  BatchItem,
  auditCoverageSummary,
  canProposeRulePreference,
  createMessageFeedback,
  createManualFinding,
  createRulePreferenceForFinding,
  Conversation,
  DocumentDetail,
  fetchSheetMap,
  findingElementLabel,
  findingLevelTransition,
  findingLifecycleState,
  findingOverlayPresentation,
  findingSectionTransition,
  findingSheetTransition,
  findingSourceLabel,
  fetchSheetUsage,
  Finding,
  FindingSeverity,
  FindingStatus,
  FindingType,
  listConversationMessages,
  listSheetFindings,
  listSheetConversations,
  PersistedChatMessage,
  runSheetAIReview,
  revokeRulePreference,
  Sheet,
  sheetIdentityLabel,
  sheetTypeLabel,
  summarizeUsage,
  SheetMap,
  sheetTechnicalScopesLabel,
  shouldShowHypothesisNotice,
  streamChatWithSheet,
  updateFindingStatus
} from "@/lib/projects-api";
import { ChatContextItem } from "@/lib/projects-api";
import {
  ConfidenceBarsIcon,
  FocusRegionIcon,
  RegionSelectIcon,
  SheetIcon
} from "@/components/truss-icons";
import { ViewOverlays } from "@/components/canvas/view-overlays";
import { FindingsDrawer } from "@/components/findings/findings-drawer";
import { AgentActivity, ChatMode, ChatRunState, ChatTurn, ChatUsageSummary, TrussChat } from "@/components/truss-chat";
import { ConfidenceBadge, Kbd, SeverityBadge, StatusBadge, TypeBadge } from "@/components/truss-primitives";

type SheetViewerProps = {
  apiBaseUrl: string;
  documents: DocumentDetail[];
  reviewItems?: BatchItem[];
  navigationTarget?: {
    sheetId: string;
    findingId?: string;
    nonce: number;
  } | null;
};

type CanvasFinding = Finding & {
  isDraft?: boolean;
};

const INTRO_CHAT_TURN: ChatTurn = {
  id: "intro",
  role: "truss",
  text:
    "Posso explicar os achados da IA, responder sobre a prancha ativa ou ajudar a registrar uma suspeita manual."
};

type Interaction =
  | {
      type: "pan";
      pointerId: number;
      startScreen: Point;
      viewport: Viewport;
    }
  | {
      type: "marquee" | "manual";
      pointerId: number;
      startWorld: Point;
      currentWorld: Point;
    }
  | {
      type: "pinch";
      startDistance: number;
      viewport: Viewport;
    };

type HistorySnapshot = {
  findings: CanvasFinding[];
  selectedIds: string[];
  activeFindingId: string;
  viewport: Viewport;
};

type ManualDraft = {
  bbox: Rect;
};

const severityMeta: Record<FindingSeverity, { label: string; tone: string; ring: string }> = {
  low: {
    label: "LOW",
    tone: "text-truss-info",
    ring: "border-truss-info bg-truss-info/10"
  },
  medium: {
    label: "MEDIUM",
    tone: "text-truss-warning",
    ring: "border-truss-warning bg-truss-warning/10"
  },
  high: {
    label: "HIGH",
    tone: "text-truss-accent",
    ring: "border-truss-accent bg-truss-accent/10"
  },
  critical: {
    label: "CRITICAL",
    tone: "text-truss-danger",
    ring: "border-truss-danger bg-truss-danger/10"
  }
};

function shouldRunAuditFromMessage(message: string) {
  return /\b(auditar|auditoria|revisar|revisao|verificar|analisar|checar)\b/i.test(message);
}

function findingSummary(findings: Finding[]) {
  if (findings.length === 0) {
    return "Nao encontrei achados para esta prancha no pipeline atual.";
  }

  const preview = findings
    .slice(0, 4)
    .map((finding, index) => `${index + 1}. ${finding.severity.toUpperCase()}: ${finding.description}`)
    .join("\n");

  const suffix = findings.length > 4 ? `\n+ ${findings.length - 4} achado(s) adicional(is).` : "";

  return `Revisei a prancha ativa e marquei ${findings.length} achado(s) no canvas.\n${preview}${suffix}`;
}

function firstUnsuppressedFinding(findings: Finding[]): Finding | null {
  return findings.find((finding) => !finding.suppressed) ?? null;
}

function reviewStatusLabel(item?: BatchItem) {
  if (!item) return "não iniciada";
  if (item.status === "completed") return "concluída";
  if (item.status === "running") return "analisando";
  if (item.status === "failed") return "falhou";
  if (item.status === "cancelled") return "cancelada";
  return "na fila";
}

function chatTurnsFromPersistedMessages(messages: PersistedChatMessage[]): ChatTurn[] {
  if (messages.length === 0) {
    return [INTRO_CHAT_TURN];
  }

  return messages.map((message) => ({
    id: message.id,
    role: message.role === "assistant" ? "truss" : "user",
    text: message.content,
    contextItems: message.context_items,
    provider: message.provider ?? undefined,
    model: message.model ?? undefined
  }));
}

function confidenceLabel(confidence: number) {
  return `${Math.round(confidence * 100)}%`;
}

function confidenceLevel(confidence: number) {
  if (confidence >= 0.75) {
    return "high";
  }

  if (confidence >= 0.45) {
    return "medium";
  }

  return "low";
}

function formatBBox(finding: Finding) {
  return `${Math.round(finding.bbox.x0)},${Math.round(finding.bbox.y0)} -> ${Math.round(
    finding.bbox.x1
  )},${Math.round(finding.bbox.y1)} pt`;
}

function formatPoint(point: Point | null) {
  if (!point) {
    return "x -, y -";
  }

  return `x ${Math.round(point.x)} pt, y ${Math.round(point.y)} pt`;
}

function isEditableTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) {
    return false;
  }

  return Boolean(target.closest("input, textarea, select, [contenteditable='true'], [role='textbox']"));
}

function pointerDistance(a: Point, b: Point) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function pointerMidpoint(a: Point, b: Point): Point {
  return {
    x: (a.x + b.x) / 2,
    y: (a.y + b.y) / 2
  };
}

function findingRect(finding: Finding): Rect {
  return finding.bbox;
}

function clampRectToSheet(rect: Rect, sheet: Sheet): Rect {
  return {
    x0: Math.max(0, Math.min(sheet.width_pt, rect.x0)),
    y0: Math.max(0, Math.min(sheet.height_pt, rect.y0)),
    x1: Math.max(0, Math.min(sheet.width_pt, rect.x1)),
    y1: Math.max(0, Math.min(sheet.height_pt, rect.y1))
  };
}

function cloneFinding(finding: CanvasFinding, offset: Point): CanvasFinding {
  return {
    ...finding,
    id: `draft-${crypto.randomUUID()}`,
    audit_run_id: null,
    origin: "human",
    status: "pending",
    rejection_reason: null,
    description: `${finding.description} (copia local)`,
    bbox: offsetRect(finding.bbox, offset),
    evidence: [...finding.evidence, "Elemento duplicado localmente no canvas."],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    isDraft: true
  };
}

function ZoomControls({
  onFit,
  onZoomIn,
  onZoomOut,
  zoom
}: {
  onFit: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  zoom: number;
}) {
  return (
    <div
      className="absolute bottom-12 right-3 z-20 grid gap-2"
      onPointerDown={(event) => event.stopPropagation()}
      onPointerMove={(event) => event.stopPropagation()}
      onPointerUp={(event) => event.stopPropagation()}
      onWheel={(event) => event.stopPropagation()}
    >
      <div className="truss-segment shadow-truss-panel">
        <button aria-label="Reduzir zoom, Ctrl+-" className="truss-icon-button border-0" onClick={onZoomOut} title="Zoom out, Ctrl+-" type="button">
          <Minus aria-hidden="true" className="truss-icon h-4 w-4" />
        </button>
        <span
          aria-label={`Zoom atual ${Math.round(zoom * 100)}%`}
          className="flex min-w-16 items-center justify-center px-3 font-mono text-[11px] text-truss-text"
          data-testid="canvas-zoom-value"
        >
          {Math.round(zoom * 100)}%
        </span>
        <button aria-label="Ampliar zoom, Ctrl++" className="truss-icon-button border-0" onClick={onZoomIn} title="Zoom in, Ctrl++" type="button">
          <Plus aria-hidden="true" className="truss-icon h-4 w-4" />
        </button>
      </div>
      <div className="grid">
        <button aria-label="Fit View, F" className="truss-button h-[34px] min-h-[34px] px-3 font-mono text-[10.5px]" onClick={onFit} title="Fit View, F" type="button">
          Fit
        </button>
      </div>
    </div>
  );
}

function CanvasMinimap({
  bounds,
  canvasSize,
  findings,
  hidden,
  onCenter,
  onToggle,
  viewport
}: {
  bounds: Rect;
  canvasSize: { width: number; height: number };
  findings: CanvasFinding[];
  hidden: boolean;
  onCenter: (point: Point) => void;
  onToggle: () => void;
  viewport: Viewport;
}) {
  const width = 150;
  const height = 106;
  const boundsW = Math.max(1, rectWidth(bounds));
  const boundsH = Math.max(1, rectHeight(bounds));
  const scale = Math.min((width - 14) / boundsW, (height - 14) / boundsH);
  const padX = (width - boundsW * scale) / 2;
  const padY = (height - boundsH * scale) / 2;
  const visibleStart = screenToWorld({ x: 0, y: 0 }, viewport);
  const visibleEnd = screenToWorld({ x: canvasSize.width, y: canvasSize.height }, viewport);
  const visible = normalizeRect(visibleStart, visibleEnd);

  function mapX(value: number) {
    return padX + (value - bounds.x0) * scale;
  }

  function mapY(value: number) {
    return padY + (value - bounds.y0) * scale;
  }

  function centerFromPointer(event: PointerEvent<HTMLDivElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    onCenter({
      x: bounds.x0 + (event.clientX - rect.left - padX) / scale,
      y: bounds.y0 + (event.clientY - rect.top - padY) / scale
    });
  }

  if (hidden) {
    return (
      <button
        className="absolute bottom-12 left-3 z-20 border border-truss-line bg-truss-panel px-3 py-2 font-mono text-[10.5px] uppercase tracking-[0.08em] text-truss-subtle shadow-truss-panel hover:text-truss-text"
        onClick={onToggle}
        title="Mostrar minimap"
        type="button"
      >
        mapa
      </button>
    );
  }

  return (
    <div
      className="absolute bottom-12 left-3 z-20 border border-truss-line bg-truss-panel/95 p-2 shadow-truss-panel"
      onPointerDown={(event) => event.stopPropagation()}
      onPointerMove={(event) => event.stopPropagation()}
      onPointerUp={(event) => event.stopPropagation()}
      onWheel={(event) => event.stopPropagation()}
    >
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="truss-mono-label">Minimap</span>
        <button className="font-mono text-[10px] text-truss-subtle hover:text-truss-text" onClick={onToggle} title="Ocultar minimap" type="button">
          ocultar
        </button>
      </div>
      <div
        className="relative cursor-crosshair border border-truss-line bg-truss-base"
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
          centerFromPointer(event);
        }}
        onPointerMove={(event) => {
          if (event.buttons === 1) {
            centerFromPointer(event);
          }
        }}
        role="presentation"
        style={{ width, height }}
      >
        <div
          className="absolute border border-truss-subtle bg-truss-sheet/20"
          style={{
            height: boundsH * scale,
            left: padX,
            top: padY,
            width: boundsW * scale
          }}
        />
        {findings.map((finding) => (
          <div
            className="absolute bg-truss-accent"
            key={finding.id}
            style={{
              height: Math.max(2, rectHeight(finding.bbox) * scale),
              left: mapX(finding.bbox.x0),
              top: mapY(finding.bbox.y0),
              width: Math.max(2, rectWidth(finding.bbox) * scale)
            }}
          />
        ))}
        <div
          className="absolute border border-truss-success bg-truss-success/10"
          style={{
            height: Math.max(5, rectHeight(visible) * scale),
            left: mapX(visible.x0),
            top: mapY(visible.y0),
            width: Math.max(5, rectWidth(visible) * scale)
          }}
        />
      </div>
    </div>
  );
}

function CanvasRulers({
  canvasSize,
  sheet,
  viewport
}: {
  canvasSize: { width: number; height: number };
  sheet: Sheet;
  viewport: Viewport;
}) {
  const step = 100;
  const start = screenToWorld({ x: 0, y: 0 }, viewport);
  const end = screenToWorld({ x: canvasSize.width, y: canvasSize.height }, viewport);
  const xTicks: number[] = [];
  const yTicks: number[] = [];

  for (let x = Math.max(0, Math.floor(start.x / step) * step); x <= Math.min(sheet.width_pt, end.x + step); x += step) {
    xTicks.push(x);
  }

  for (let y = Math.max(0, Math.floor(start.y / step) * step); y <= Math.min(sheet.height_pt, end.y + step); y += step) {
    yTicks.push(y);
  }

  return (
    <>
      <div className="pointer-events-none absolute left-0 top-0 z-10 h-7 w-full border-b border-truss-line bg-truss-raised/88">
        {xTicks.map((x) => {
          const screen = worldToScreen({ x, y: 0 }, viewport).x;
          return (
            <div
              className="absolute top-0 h-full border-l border-truss-subtle/40 pl-1 font-mono text-[9px] leading-7 text-truss-subtle"
              key={x}
              style={{ left: screen }}
            >
              {Math.round(x)}
            </div>
          );
        })}
      </div>
      <div className="pointer-events-none absolute left-0 top-0 z-10 h-full w-7 border-r border-truss-line bg-truss-raised/88">
        {yTicks.map((y) => {
          const screen = worldToScreen({ x: 0, y }, viewport).y;
          return (
            <div
              className="absolute left-0 w-full border-t border-truss-subtle/40 pt-1 text-center font-mono text-[9px] leading-none text-truss-subtle"
              key={y}
              style={{ top: screen }}
            >
              {Math.round(y)}
            </div>
          );
        })}
      </div>
    </>
  );
}

const EVIDENCE_PREVIEW = 7;

/**
 * Evidencia bruta e o que sustenta a hipotese, entao ela nunca some: o painel
 * mostra as primeiras linhas e abre o restante sob demanda. Sem animacao, o
 * bloco ja respeita `prefers-reduced-motion` do design system. O chamador passa
 * `key={finding.id}` para que trocar de achado volte ao estado recolhido.
 */
function FindingEvidence({ finding }: { finding: Finding }) {
  const [expanded, setExpanded] = useState(false);
  const hidden = finding.evidence.length - EVIDENCE_PREVIEW;
  const visible = expanded ? finding.evidence : finding.evidence.slice(0, EVIDENCE_PREVIEW);

  if (finding.evidence.length === 0) {
    return null;
  }

  return (
    <div className="mt-3 border border-truss-line bg-truss-panel/70 p-2">
      <p className="truss-mono-label">Evidencias</p>
      <ul className="mt-2 grid gap-1 text-xs leading-5 text-truss-muted" id={`evidence-${finding.id}`}>
        {visible.map((evidence, index) => (
          <li className="break-words" key={`${finding.id}-${index}`}>{evidence}</li>
        ))}
      </ul>
      {hidden > 0 ? (
        <button
          aria-controls={`evidence-${finding.id}`}
          aria-expanded={expanded}
          className="mt-2 border border-truss-line bg-truss-raised px-2 py-1 font-mono text-[10px] uppercase tracking-[0.06em] text-truss-subtle hover:border-truss-accent/45 hover:text-truss-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-truss-accent"
          onClick={() => setExpanded((value) => !value)}
          type="button"
        >
          {expanded ? "Recolher evidencia" : `Ver evidencia completa (+${hidden})`}
        </button>
      ) : null}
    </div>
  );
}

export function SheetViewer({ apiBaseUrl, documents, navigationTarget, reviewItems = [] }: SheetViewerProps) {
  const unavailableDocuments = documents.filter(
    (document) => document.source_status === "SOURCE_UNAVAILABLE"
  );
  const sheets = useMemo(
    () =>
      documents
        .filter((document) => document.source_status !== "SOURCE_UNAVAILABLE")
        .flatMap((document) =>
        document.sheets.map((sheet) => ({
          ...sheet,
          documentName: document.original_filename
        }))
      ),
    [documents]
  );
  const [activeSheetId, setActiveSheetId] = useState("");
  const [viewport, setViewportState] = useState<Viewport>({
    x: 0,
    y: 0,
    zoom: CANVAS_NAVIGATION.defaultZoom
  });
  const [findings, setFindings] = useState<CanvasFinding[]>([]);
  const [sheetMap, setSheetMap] = useState<SheetMap | null>(null);
  const [chatUsage, setChatUsage] = useState<ChatUsageSummary | null>(null);
  const [selectedIds, setSelectedIdsState] = useState<Set<string>>(new Set());
  const [activeFindingId, setActiveFindingId] = useState("");
  const [showFindings, setShowFindings] = useState(true);
  const [showViews, setShowViews] = useState(false);
  const [showSuppressed, setShowSuppressed] = useState(false);
  const [showSupportFindings, setShowSupportFindings] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [auditCoverage, setAuditCoverage] = useState<AuditCoverage | null>(null);
  const [activeViewId, setActiveViewId] = useState<string | null>(null);
  const [showMinimap, setShowMinimap] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [isAuditing, setIsAuditing] = useState(false);
  const [manualMode, setManualMode] = useState(false);
  const [statusFilter, setStatusFilter] = useState<FindingStatus | "all">("all");
  const [severityFilter, setSeverityFilter] = useState<FindingSeverity | "all">("all");
  const [chatMessage, setChatMessage] = useState("");
  const [chatMode, setChatMode] = useState<ChatMode>("ask");
  const [conversationId, setConversationId] = useState("");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [isLoadingConversations, setIsLoadingConversations] = useState(false);
  const [isLoadingChatHistory, setIsLoadingChatHistory] = useState(false);
  const [mutedContextIds, setMutedContextIds] = useState<Set<string>>(new Set());
  const [chatTurns, setChatTurns] = useState<ChatTurn[]>([INTRO_CHAT_TURN]);
  const [isChatting, setIsChatting] = useState(false);
  const [interaction, setInteraction] = useState<Interaction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSpacePressed, setIsSpacePressed] = useState(false);
  const [isShiftPressed, setIsShiftPressed] = useState(false);
  const [canvasIsActive, setCanvasIsActive] = useState(false);
  const [cursorWorld, setCursorWorld] = useState<Point | null>(null);
  const [manualDraft, setManualDraft] = useState<ManualDraft | null>(null);
  const [manualDescription, setManualDescription] = useState("");
  const [manualType, setManualType] = useState<FindingType>("attention");
  const [manualSeverity, setManualSeverity] = useState<FindingSeverity>("medium");
  const [isCreatingManual, setIsCreatingManual] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [rejectPanelOpen, setRejectPanelOpen] = useState(false);
  const [rejectFindingId, setRejectFindingId] = useState("");
  const [isSavingFeedback, setIsSavingFeedback] = useState(false);
  const [isSavingPreference, setIsSavingPreference] = useState(false);
  const [, setHistoryState] = useState({ canRedo: false, canUndo: false });
  const [canvasSizeState, setCanvasSizeState] = useState({ height: 1, width: 1 });
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const viewportRef = useRef(viewport);
  const selectedIdsRef = useRef(selectedIds);
  const findingsRef = useRef(findings);
  const spacePressedRef = useRef(isSpacePressed);
  const interactionRef = useRef<Interaction | null>(null);
  const chatTurnIdRef = useRef(0);
  const clipboardRef = useRef<CanvasFinding[]>([]);
  const undoStackRef = useRef<HistorySnapshot[]>([]);
  const redoStackRef = useRef<HistorySnapshot[]>([]);
  const pointersRef = useRef<Map<number, Point>>(new Map());
  const rafRef = useRef<number | null>(null);
  const chatAbortRef = useRef<AbortController | null>(null);
  const handledNavigationNonceRef = useRef<number | null>(null);

  const activeSheet = sheets.find((sheet) => sheet.id === activeSheetId) ?? sheets[0] ?? null;
  const resolvedSheetId = activeSheet?.id ?? "";
  const activeIndex = activeSheet ? sheets.findIndex((sheet) => sheet.id === activeSheet.id) : -1;
  const reviewItemBySheet = useMemo(
    () => new Map(reviewItems.map((item) => [item.sheet_id, item])),
    [reviewItems]
  );
  const activeReviewItem = activeSheet ? reviewItemBySheet.get(activeSheet.id) : undefined;
  const completedReviewCount = reviewItems.filter((item) => item.status === "completed").length;
  const sheetBounds = activeSheet
    ? {
        x0: 0,
        y0: 0,
        x1: activeSheet.width_pt,
        y1: activeSheet.height_pt
      }
    : null;
  const hasAIReviewFindings = findings.some((finding) => finding.source_layer === "ai_review");
  const supportFindingCount = hasAIReviewFindings
    ? findings.filter((finding) => finding.source_layer !== "ai_review" && finding.origin !== "human").length
    : 0;
  const primaryFindings = hasAIReviewFindings && !showSupportFindings
    ? findings.filter((finding) => finding.source_layer === "ai_review" || finding.origin === "human")
    : findings;
  const suppressedCount = primaryFindings.filter((finding) => finding.suppressed).length;
  const filteredFindings = primaryFindings.filter(
    (finding) =>
      (showSuppressed || !finding.suppressed) &&
      (statusFilter === "all" || finding.status === statusFilter) &&
      (severityFilter === "all" || finding.severity === severityFilter)
  );
  const selectedFilteredFindings = filteredFindings.filter((finding) => selectedIds.has(finding.id));
  const activeFinding =
    filteredFindings.find((finding) => finding.id === activeFindingId) ??
    selectedFilteredFindings[0] ??
    filteredFindings[0] ??
    null;
  const activeFindingIndex = activeFinding
    ? filteredFindings.findIndex((finding) => finding.id === activeFinding.id)
    : -1;
  const marqueeRect =
    interaction?.type === "marquee" || interaction?.type === "manual"
      ? normalizeRect(interaction.startWorld, interaction.currentWorld)
      : null;
  const contentBounds = sheetBounds ? unionRects([sheetBounds, ...findings.map((finding) => findingRect(finding))]) ?? sheetBounds : null;
  const selectedFindingsForContext = findings.filter((finding) => selectedIds.has(finding.id));
  const chatContextItems: ChatContextItem[] = [];
  if (activeSheet) {
    chatContextItems.push({
      id: `sheet:${activeSheet.id}`,
      kind: "sheet",
      label: activeSheet.label,
      value: `${activeSheet.width_pt} x ${activeSheet.height_pt} pt`,
      metadata: {
        page: activeSheet.sheet_number,
        sheetId: activeSheet.id
      }
    });

    if ("documentName" in activeSheet) {
      chatContextItems.push({
        id: `document:${activeSheet.document_id}`,
        kind: "document",
        label: String(activeSheet.documentName),
        value: String(activeSheet.documentName),
        metadata: {
          documentId: activeSheet.document_id
        }
      });
    }

    if (selectedFindingsForContext.length > 0) {
      chatContextItems.push({
        id: "selection:findings",
        kind: "selection",
        label: `${selectedFindingsForContext.length} selecionado(s)`,
        value: selectedFindingsForContext.map((finding) => finding.description).join(" | "),
        metadata: {
          count: selectedFindingsForContext.length
        }
      });
    }

    if (activeFinding) {
      chatContextItems.push({
        id: `finding:${activeFinding.id}`,
        kind: "finding",
        label: `Achado ${activeFindingIndex + 1}`,
        value: activeFinding.description,
        metadata: {
          confidence: activeFinding.confidence,
          findingId: activeFinding.id,
          severity: activeFinding.severity,
          status: activeFinding.status
        }
      });
    }
  }
  const visibleChatContextItems = chatContextItems.filter((item) => !mutedContextIds.has(item.id));
  const lastTurn = chatTurns.at(-1) ?? null;
  const chatRunState: ChatRunState = isChatting
    ? lastTurn?.streaming
      ? "gerando"
      : "enviando"
    : lastTurn?.tone === "error"
      ? "erro"
      : lastTurn?.stopped
        ? "parado"
        : "idle";
  const chatRunDetail =
    chatRunState === "erro" && lastTurn ? lastTurn.text.split("\n")[0] : undefined;

  function retryLastChatTurn() {
    const lastUserTurn = [...chatTurns].reverse().find((turn) => turn.role === "user");
    if (!lastUserTurn) {
      return;
    }

    void sendChatMessage(
      lastUserTurn.text,
      chatMode,
      lastUserTurn.contextItems ?? visibleChatContextItems
    );
  }

  const chatActivity: AgentActivity = isAuditing
    ? {
        state: "using-tool",
        title: "Revisando prancha com IA",
        steps: [
          { id: "sheet", label: "Folha ativa carregada", state: "done" },
          { id: "audit", label: "Analisando imagem e contexto técnico", state: "active" },
          { id: "findings", label: "Atualizando achados", state: "queued" }
        ]
      }
    : isLoadingChatHistory
      ? {
          state: "using-tool",
          title: "Carregando conversa",
          steps: [
            { id: "history", label: "Buscando mensagens salvas", state: "active" },
            { id: "render", label: "Atualizando painel", state: "queued" }
          ]
        }
    : isChatting
      ? {
          state: "thinking",
          title: "Consultando Truss Agent",
          steps: [
            { id: "context", label: "Contexto preparado", state: "done" },
            { id: "provider", label: "Aguardando provider de IA", state: "active" }
          ]
        }
      : error
        ? {
            state: "error",
            title: "Falha na ultima operacao",
            steps: [{ id: "error", label: "Erro visivel no painel", state: "error" }]
          }
        : {
            state: "idle",
            title: "Pronto",
            steps: []
          };

  function beginInteraction(next: Interaction | null) {
    // Gestos leem do ref: dentro de um mesmo arrasto o estado do React pode
    // ainda nao ter re-renderizado quando o primeiro pointermove chega.
    interactionRef.current = next;
    setInteraction(next);
  }

  function setViewport(next: Viewport) {
    const rect = canvasRef.current?.getBoundingClientRect();
    viewportRef.current = activeSheet && rect && rect.width > 0
      ? clampViewportToSheet(
          next,
          { width: activeSheet.width_pt, height: activeSheet.height_pt },
          { width: rect.width, height: rect.height }
        )
      : next;

    if (rafRef.current !== null) {
      return;
    }

    rafRef.current = window.requestAnimationFrame(() => {
      rafRef.current = null;
      setViewportState(viewportRef.current);
    });
  }

  function setSelectedIds(next: Set<string>) {
    selectedIdsRef.current = next;
    setSelectedIdsState(next);
  }

  function snapshot(): HistorySnapshot {
    return {
      activeFindingId,
      findings: findingsRef.current,
      selectedIds: Array.from(selectedIdsRef.current),
      viewport: viewportRef.current
    };
  }

  function pushHistory() {
    undoStackRef.current = [...undoStackRef.current.slice(-39), snapshot()];
    redoStackRef.current = [];
    setHistoryState({ canRedo: false, canUndo: true });
  }

  function applySnapshot(next: HistorySnapshot) {
    findingsRef.current = next.findings;
    setFindings(next.findings);
    setSelectedIds(new Set(next.selectedIds));
    setActiveFindingId(next.activeFindingId);
    setViewport(next.viewport);
  }

  function undo() {
    const previous = undoStackRef.current.pop();
    if (!previous) {
      return;
    }

    redoStackRef.current.push(snapshot());
    applySnapshot(previous);
    setHistoryState({
      canRedo: redoStackRef.current.length > 0,
      canUndo: undoStackRef.current.length > 0
    });
  }

  function redo() {
    const next = redoStackRef.current.pop();
    if (!next) {
      return;
    }

    undoStackRef.current.push(snapshot());
    applySnapshot(next);
    setHistoryState({
      canRedo: redoStackRef.current.length > 0,
      canUndo: undoStackRef.current.length > 0
    });
  }

  function nextChatTurnId() {
    chatTurnIdRef.current += 1;
    return `chat-${chatTurnIdRef.current}`;
  }

  function appendTurn(turn: Omit<ChatTurn, "id"> & { id?: string }) {
    const id = turn.id ?? nextChatTurnId();
    setChatTurns((current) => [
      ...current,
      {
        ...turn,
        id
      }
    ]);
    return id;
  }

  function updateTurn(id: string, updater: (turn: ChatTurn) => Partial<ChatTurn>) {
    setChatTurns((current) =>
      current.map((turn) => (turn.id === id ? { ...turn, ...updater(turn) } : turn))
    );
  }

  async function refreshConversations(sheetId = activeSheet?.id) {
    if (!sheetId) {
      setConversations([]);
      return;
    }

    setIsLoadingConversations(true);
    try {
      const sheetConversations = await listSheetConversations(apiBaseUrl, sheetId);
      setConversations(sheetConversations);
    } catch (conversationError) {
      setError(conversationError instanceof Error ? conversationError.message : "Falha ao carregar conversas.");
    } finally {
      setIsLoadingConversations(false);
    }
  }

  function startNewConversation() {
    if (isChatting || isAuditing) {
      return;
    }

    setConversationId("");
    setChatTurns([INTRO_CHAT_TURN]);
    setChatMessage("");
    setError(null);
  }

  async function loadConversationHistory(nextConversationId: string) {
    if (isChatting || isAuditing || nextConversationId === conversationId) {
      return;
    }

    setIsLoadingChatHistory(true);
    setError(null);
    try {
      const messages = await listConversationMessages(apiBaseUrl, nextConversationId);
      setConversationId(nextConversationId);
      setChatTurns(chatTurnsFromPersistedMessages(messages));
      setChatMessage("");
    } catch (conversationError) {
      const message =
        conversationError instanceof Error ? conversationError.message : "Falha ao carregar historico da conversa.";
      setError(message);
      appendTurn({ role: "truss", tone: "error", text: message });
    } finally {
      setIsLoadingChatHistory(false);
    }
  }

  function canvasPointFromClient(clientX: number, clientY: number): Point | null {
    const canvas = canvasRef.current;
    if (!canvas) {
      return null;
    }

    const rect = canvas.getBoundingClientRect();
    return {
      x: clientX - rect.left,
      y: clientY - rect.top
    };
  }

  function viewportSize() {
    const rect = canvasRef.current?.getBoundingClientRect();
    return {
      width: rect?.width ?? 1,
      height: rect?.height ?? 1
    };
  }

  function fitView() {
    if (!contentBounds) {
      return;
    }

    setViewport(viewportForBounds(contentBounds, viewportSize(), { maxZoom: CANVAS_NAVIGATION.defaultZoom }));
  }

  function resetView() {
    if (!sheetBounds) {
      return;
    }

    const size = viewportSize();
    const sheetWidthPx = rectWidth(sheetBounds) * CANVAS_NAVIGATION.renderScale * CANVAS_NAVIGATION.defaultZoom;
    const sheetHeightPx = rectHeight(sheetBounds) * CANVAS_NAVIGATION.renderScale * CANVAS_NAVIGATION.defaultZoom;

    setViewport({
      x: (size.width - sheetWidthPx) / 2,
      y: sheetHeightPx < size.height
        ? (size.height - sheetHeightPx) / 2
        : CANVAS_NAVIGATION.fitPaddingPx,
      zoom: CANVAS_NAVIGATION.defaultZoom
    });
  }

  function zoomByFactor(factor: number, anchor?: Point) {
    const size = viewportSize();
    const screenPoint = anchor ?? { x: size.width / 2, y: size.height / 2 };
    setViewport(zoomAtScreenPoint(viewportRef.current, viewportRef.current.zoom * factor, screenPoint));
  }

  function centerOnWorld(point: Point) {
    const size = viewportSize();
    setViewport({
      x: size.width / 2 - point.x * viewportRef.current.zoom * CANVAS_NAVIGATION.renderScale,
      y: size.height / 2 - point.y * viewportRef.current.zoom * CANVAS_NAVIGATION.renderScale,
      zoom: viewportRef.current.zoom
    });
  }

  function focusFinding(finding: Finding, replaceSelection = true) {
    if (replaceSelection) {
      setSelectedIds(new Set([finding.id]));
    }

    setActiveFindingId(finding.id);
    // O achado aponta para a view onde ele foi avaliado; destaca-la da o
    // contexto sem obrigar a procurar no canvas.
    if (finding.view_id) {
      setActiveViewId(finding.view_id);
    }
    centerOnWorld({
      x: (finding.bbox.x0 + finding.bbox.x1) / 2,
      y: (finding.bbox.y0 + finding.bbox.y1) / 2
    });
  }

  function selectFinding(finding: CanvasFinding, additive: boolean) {
    const next = new Set(additive ? selectedIdsRef.current : []);

    if (additive && next.has(finding.id)) {
      next.delete(finding.id);
    } else {
      next.add(finding.id);
      setActiveFindingId(finding.id);
    }

    setSelectedIds(next);
  }

  function selectedFindings() {
    return findingsRef.current.filter((finding) => selectedIdsRef.current.has(finding.id));
  }

  function duplicateSelection() {
    const selection = selectedFindings();
    if (selection.length === 0) {
      return;
    }

    pushHistory();
    const offset = {
      x: CANVAS_NAVIGATION.duplicateOffsetPt,
      y: CANVAS_NAVIGATION.duplicateOffsetPt
    };
    const clones = selection.map((finding) => cloneFinding(finding, offset));
    const nextFindings = [...clones, ...findingsRef.current];
    findingsRef.current = nextFindings;
    setFindings(nextFindings);
    setSelectedIds(new Set(clones.map((finding) => finding.id)));
    setActiveFindingId(clones[0]?.id ?? "");
    appendTurn({
      role: "truss",
      tone: "success",
      text: `${clones.length} elemento(s) duplicado(s) localmente no canvas.`
    });
  }

  function copySelection() {
    const selection = selectedFindings();
    if (selection.length === 0) {
      return;
    }

    clipboardRef.current = selection;
    appendTurn({
      role: "truss",
      text: `${selection.length} elemento(s) copiado(s) para a area de transferencia local do canvas.`
    });
  }

  function pasteSelection() {
    if (clipboardRef.current.length === 0) {
      return;
    }

    pushHistory();
    const offset = {
      x: CANVAS_NAVIGATION.duplicateOffsetPt * 1.5,
      y: CANVAS_NAVIGATION.duplicateOffsetPt * 1.5
    };
    const clones = clipboardRef.current.map((finding) => cloneFinding(finding, offset));
    const nextFindings = [...clones, ...findingsRef.current];
    findingsRef.current = nextFindings;
    setFindings(nextFindings);
    setSelectedIds(new Set(clones.map((finding) => finding.id)));
    setActiveFindingId(clones[0]?.id ?? "");
  }

  function removeSelection() {
    if (selectedIdsRef.current.size === 0) {
      return;
    }

    pushHistory();
    const selected = selectedIdsRef.current;
    const nextFindings = findingsRef.current.filter((finding) => !selected.has(finding.id));
    findingsRef.current = nextFindings;
    setFindings(nextFindings);
    setSelectedIds(new Set());
    setActiveFindingId("");
    appendTurn({
      role: "truss",
      text:
        "Elemento(s) removido(s) desta sessao do canvas. Achados persistidos voltam ao recarregar ate existir exclusao auditavel no backend."
    });
  }

  function setActiveSheet(sheet: Sheet) {
    setActiveSheetId(sheet.id);
    setSelectedIds(new Set());
    setActiveFindingId("");
    setManualDraft(null);
    setRejectPanelOpen(false);
    setRejectReason("");
    setRejectFindingId("");
    setMutedContextIds(new Set());
    setConversationId("");
    setConversations([]);
    setChatTurns([INTRO_CHAT_TURN]);
    appendTurn({
      role: "truss",
      text: `Prancha ativa alterada para ${sheet.label}.`
    });
  }

  function moveSheet(offset: number) {
    if (activeIndex < 0 || sheets.length === 0) {
      return;
    }

    const nextIndex = (activeIndex + offset + sheets.length) % sheets.length;
    setActiveSheet(sheets[nextIndex]);
  }

  function handleWheel(event: WheelEvent<HTMLDivElement>) {
    event.preventDefault();
    event.stopPropagation();
    setCanvasIsActive(true);

    const anchor = canvasPointFromClient(event.clientX, event.clientY);
    const intent = wheelIntent(event);

    if (intent.kind === "zoom") {
      zoomByFactor(intent.factor, anchor ?? undefined);
      return;
    }

    setViewport({
      ...viewportRef.current,
      x: viewportRef.current.x + intent.deltaX,
      y: viewportRef.current.y + intent.deltaY
    });
  }

  function handlePointerDown(event: PointerEvent<HTMLDivElement>) {
    setCanvasIsActive(true);
    const canvasPoint = canvasPointFromClient(event.clientX, event.clientY);
    if (!canvasPoint) {
      return;
    }

    pointersRef.current.set(event.pointerId, canvasPoint);

    if (event.pointerType === "touch" && pointersRef.current.size >= 2) {
      const points = Array.from(pointersRef.current.values()).slice(0, 2);
      event.currentTarget.setPointerCapture(event.pointerId);
      beginInteraction({
        type: "pinch",
        startDistance: pointerDistance(points[0], points[1]),
        viewport: viewportRef.current
      });
      return;
    }

    const wantsMarquee = event.button === 0 && (event.shiftKey || manualMode);

    if (
      event.pointerType === "touch"
      || event.button === 1
      || (event.button === 0 && !wantsMarquee)
    ) {
      event.preventDefault();
      event.currentTarget.setPointerCapture(event.pointerId);
      beginInteraction({
        type: "pan",
        pointerId: event.pointerId,
        startScreen: canvasPoint,
        viewport: viewportRef.current
      });
      return;
    }

    if (event.button !== 0) {
      return;
    }

    const world = screenToWorld(canvasPoint, viewportRef.current);
    event.currentTarget.setPointerCapture(event.pointerId);
    beginInteraction({
      type: manualMode ? "manual" : "marquee",
      pointerId: event.pointerId,
      startWorld: world,
      currentWorld: world
    });
  }

  function handlePointerMove(event: PointerEvent<HTMLDivElement>) {
    const canvasPoint = canvasPointFromClient(event.clientX, event.clientY);
    if (!canvasPoint) {
      return;
    }

    pointersRef.current.set(event.pointerId, canvasPoint);
    setCursorWorld(screenToWorld(canvasPoint, viewportRef.current));

    if (interactionRef.current?.type === "pinch") {
      const points = Array.from(pointersRef.current.values()).slice(0, 2);
      if (points.length === 2) {
        const distance = pointerDistance(points[0], points[1]);
        const midpoint = pointerMidpoint(points[0], points[1]);
        setViewport(zoomAtScreenPoint(interactionRef.current.viewport, interactionRef.current.viewport.zoom * (distance / interactionRef.current.startDistance), midpoint));
      }
      return;
    }

    if (interactionRef.current?.type === "pan" && interactionRef.current.pointerId === event.pointerId) {
      setViewport({
        ...interactionRef.current.viewport,
        x: interactionRef.current.viewport.x + canvasPoint.x - interactionRef.current.startScreen.x,
        y: interactionRef.current.viewport.y + canvasPoint.y - interactionRef.current.startScreen.y
      });
      return;
    }

    if ((interactionRef.current?.type === "marquee" || interactionRef.current?.type === "manual") && interactionRef.current.pointerId === event.pointerId) {
      beginInteraction({
        ...interactionRef.current,
        currentWorld: screenToWorld(canvasPoint, viewportRef.current)
      });
    }
  }

  async function handlePointerUp(event: PointerEvent<HTMLDivElement>) {
    pointersRef.current.delete(event.pointerId);

    if (interactionRef.current?.type === "manual" && interactionRef.current.pointerId === event.pointerId && activeSheet) {
      const bbox = normalizeRect(interactionRef.current.startWorld, interactionRef.current.currentWorld);
      beginInteraction(null);

      if (rectWidth(bbox) < 4 || rectHeight(bbox) < 4) {
        return;
      }

      setManualDraft({ bbox: clampRectToSheet(bbox, activeSheet) });
      setManualDescription("");
      setManualType("attention");
      setManualSeverity("medium");
      setManualMode(false);
      setShowFindings(true);
      return;
    }

    if (interactionRef.current?.type === "marquee" && interactionRef.current.pointerId === event.pointerId) {
      const rect = normalizeRect(interactionRef.current.startWorld, interactionRef.current.currentWorld);
      beginInteraction(null);

      if (rectWidth(rect) < 3 && rectHeight(rect) < 3) {
        setSelectedIds(new Set());
        setActiveFindingId("");
        return;
      }

      const ids = filteredFindings
        .filter((finding) => rectsIntersect(rect, finding.bbox))
        .map((finding) => finding.id);
      setSelectedIds(new Set(ids));
      setActiveFindingId(ids[0] ?? "");
      return;
    }

    if (interactionRef.current?.type === "pan" || interactionRef.current?.type === "pinch") {
      beginInteraction(null);
    }
  }

  function handlePointerCancel(event: PointerEvent<HTMLDivElement>) {
    pointersRef.current.delete(event.pointerId);
    beginInteraction(null);
  }

  async function runAuditFromChat() {
    if (!activeSheet) {
      return;
    }

    setIsAuditing(true);
    setError(null);

    try {
      const auditRun = await runSheetAIReview(apiBaseUrl, activeSheet.id);
      const firstFinding = firstUnsuppressedFinding(auditRun.findings);
      findingsRef.current = auditRun.findings;
      setFindings(auditRun.findings);
      setAuditCoverage(auditRun.coverage ?? null);
      setSelectedIds(new Set());
      setActiveFindingId(firstFinding?.id ?? "");
      setShowSuppressed(false);
      setShowFindings(true);
      appendTurn({
        role: "truss",
        tone: auditRun.findings.length > 0 ? "success" : "default",
        text: ["Revisão por IA concluída.", findingSummary(auditRun.findings), auditCoverageSummary(auditRun.coverage)]
          .filter(Boolean)
          .join(" ")
      });
    } catch (auditError) {
      const message =
        auditError instanceof Error ? auditError.message : "Falha ao executar revisão por IA.";
      setError(message);
      appendTurn({ role: "truss", tone: "error", text: message });
    } finally {
      setIsAuditing(false);
    }
  }

  async function submitManualFinding(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!activeSheet || !manualDraft) {
      return;
    }

    const description = manualDescription.trim();
    if (!description) {
      return;
    }

    setIsCreatingManual(true);
    setError(null);

    try {
      const finding = await createManualFinding(apiBaseUrl, activeSheet.id, {
        category: "composition",
        type: manualType,
        description,
        severity: manualSeverity,
        confidence: 1,
        bbox: manualDraft.bbox,
        evidence: ["Regiao selecionada manualmente no viewer."]
      });
      const next = [finding, ...findingsRef.current];
      findingsRef.current = next;
      setFindings(next);
      setSelectedIds(new Set([finding.id]));
      setActiveFindingId(finding.id);
      setManualDraft(null);
      setManualDescription("");
      setShowFindings(true);
      appendTurn({
        role: "truss",
        tone: "success",
        text: `Registrei o achado manual: ${finding.description}`
      });
    } catch (manualError) {
      const message = manualError instanceof Error ? manualError.message : "Falha ao criar achado.";
      setError(message);
      appendTurn({ role: "truss", tone: "error", text: message });
    } finally {
      setIsCreatingManual(false);
    }
  }

  async function setFindingStatus(status: "confirmed" | "rejected", rejectionReason?: string, targetFinding = activeFinding) {
    if (!targetFinding) {
      return;
    }

    const cleanedReason = rejectionReason?.trim();

    if (targetFinding.isDraft) {
      const next = findingsRef.current.map((finding) =>
        finding.id === targetFinding.id
          ? {
              ...finding,
              status,
              rejection_reason: status === "rejected" ? cleanedReason || null : null,
              updated_at: new Date().toISOString()
            }
          : finding
      );
      findingsRef.current = next;
      setFindings(next);
      setRejectPanelOpen(false);
      setRejectReason("");
      setRejectFindingId("");
      return;
    }

    setIsSavingFeedback(true);

    try {
      const updated = await updateFindingStatus(
        apiBaseUrl,
        targetFinding.id,
        status,
        status === "rejected" ? cleanedReason : undefined
      );
      const next = findingsRef.current.map((finding) => (finding.id === updated.id ? updated : finding));
      findingsRef.current = next;
      setFindings(next);
      setRejectPanelOpen(false);
      setRejectReason("");
      setRejectFindingId("");
      appendTurn({
        role: "truss",
        tone: status === "confirmed" ? "success" : "default",
        text:
          status === "confirmed"
            ? "Achado confirmado e salvo."
            : "Achado rejeitado e salvo com justificativa."
      });
    } catch (feedbackError) {
      const message =
        feedbackError instanceof Error ? feedbackError.message : "Falha ao salvar feedback.";
      setError(message);
      appendTurn({ role: "truss", tone: "error", text: message });
    } finally {
      setIsSavingFeedback(false);
    }
  }

  async function applyRulePreference(finding: Finding) {
    if (!finding.rejection_reason || !finding.rule_id) {
      return;
    }

    setIsSavingPreference(true);
    setError(null);
    try {
      await createRulePreferenceForFinding(
        apiBaseUrl,
        finding.id,
        finding.rejection_reason
      );
      const refreshed = await listSheetFindings(apiBaseUrl, finding.sheet_id);
      findingsRef.current = refreshed;
      setFindings(refreshed);
      setShowSuppressed(true);
      setActiveFindingId(finding.id);
      setSelectedIds(new Set([finding.id]));
      appendTurn({
        role: "truss",
        tone: "success",
        text: `Preferencia aprovada: ${finding.rule_id} fica silenciada neste tipo de prancha.`
      });
    } catch (preferenceError) {
      const message =
        preferenceError instanceof Error
          ? preferenceError.message
          : "Falha ao aplicar preferencia de regra.";
      setError(message);
      appendTurn({ role: "truss", tone: "error", text: message });
    } finally {
      setIsSavingPreference(false);
    }
  }

  async function restoreRulePreference(finding: Finding) {
    if (!finding.suppression_preference_id) {
      return;
    }

    setIsSavingPreference(true);
    setError(null);
    try {
      await revokeRulePreference(apiBaseUrl, finding.suppression_preference_id);
      const refreshed = await listSheetFindings(apiBaseUrl, finding.sheet_id);
      findingsRef.current = refreshed;
      setFindings(refreshed);
      setActiveFindingId(finding.id);
      setSelectedIds(new Set([finding.id]));
      appendTurn({
        role: "truss",
        tone: "default",
        text: `Preferencia revogada: ${finding.rule_id ?? "regra"} volta a aparecer nas auditorias.`
      });
    } catch (preferenceError) {
      const message =
        preferenceError instanceof Error
          ? preferenceError.message
          : "Falha ao revogar preferencia de regra.";
      setError(message);
      appendTurn({ role: "truss", tone: "error", text: message });
    } finally {
      setIsSavingPreference(false);
    }
  }

  async function sendChatMessage(messageInput: string, mode: ChatMode = chatMode, contextItems = visibleChatContextItems) {
    const message = messageInput.trim();
    if (!activeSheet || !message) {
      return;
    }

    appendTurn({ role: "user", text: message, contextItems });
    setChatMessage("");
    setIsChatting(true);
    setError(null);
    const abortController = new AbortController();
    chatAbortRef.current = abortController;
    let streamingTurnId = "";

    try {
      if (mode === "audit_sheet" || shouldRunAuditFromMessage(message)) {
        await runAuditFromChat();
        return;
      }

      if (mode === "audit_selection" && selectedFindingsForContext.length === 0) {
        appendTurn({
          role: "truss",
          tone: "error",
          text: "Para auditar uma selecao, selecione um achado ou regiao no canvas primeiro."
        });
        return;
      }

      streamingTurnId = appendTurn({
        role: "truss",
        streaming: true,
        text: ""
      });

      const response = await streamChatWithSheet(apiBaseUrl, activeSheet.id, message, {
        conversationId: conversationId || undefined,
        contextItems,
        onEvent: (event) => {
          if (event.event === "meta") {
            updateTurn(streamingTurnId, () => ({
              model: event.model,
              provider: event.provider
            }));
          }

          if (event.event === "delta") {
            updateTurn(streamingTurnId, (turn) => ({
              text: `${turn.text}${event.delta}`
            }));
          }
        },
        signal: abortController.signal
      });
      setConversationId(response.conversation_id);
      void refreshConversations(activeSheet.id);
      updateTurn(streamingTurnId, () => ({
        id: response.assistant_message_id,
        model: response.model,
        provider: response.provider,
        streaming: false,
        text: response.answer
      }));
    } catch (chatError) {
      if (chatError instanceof DOMException && chatError.name === "AbortError") {
        updateTurn(streamingTurnId, (turn) => ({
          stopped: true,
          streaming: false,
          text: turn.text || "Analise interrompida pelo usuario."
        }));
        return;
      }

      const messageText =
        chatError instanceof Error ? chatError.message : "Falha ao conversar com o Truss.";
      setError(messageText);
      if (streamingTurnId) {
        updateTurn(streamingTurnId, (turn) => ({
          streaming: false,
          text: turn.text ? `${turn.text}\n\n${messageText}` : messageText,
          tone: "error"
        }));
      } else {
        appendTurn({ role: "truss", tone: "error", text: messageText });
      }
    } finally {
      setIsChatting(false);
      chatAbortRef.current = null;
    }
  }

  function handleChatSubmit(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    void sendChatMessage(chatMessage);
  }

  function stopChat() {
    chatAbortRef.current?.abort();
    setIsChatting(false);
  }

  function insertChatPrompt(prompt: string, mode: ChatMode = chatMode) {
    setChatMode(mode);
    setChatMessage(prompt);
  }

  function auditSelectionFromChatAction() {
    void sendChatMessage("Audite somente a seleção atual.", "audit_selection", visibleChatContextItems);
  }

  function explainFindingFromChatAction(finding: Finding) {
    focusFinding(finding);
    void sendChatMessage(
      `Explique este achado com evidências, hipóteses e próxima ação: ${finding.description}`,
      "explain_finding",
      visibleChatContextItems
    );
  }

  function editChatTurn(turn: ChatTurn) {
    setChatMessage(turn.text);
    setChatMode("ask");
  }

  function regenerateChatTurn(turn: ChatTurn) {
    const turnIndex = chatTurns.findIndex((item) => item.id === turn.id);
    const previousUserTurn = [...chatTurns.slice(0, turnIndex)].reverse().find((item) => item.role === "user");
    if (!previousUserTurn) {
      return;
    }

    void sendChatMessage(previousUserTurn.text, chatMode, previousUserTurn.contextItems ?? visibleChatContextItems);
  }

  function rejectFindingFromChat(finding: Finding) {
    focusFinding(finding);
    setRejectPanelOpen(true);
    setRejectFindingId(finding.id);
    setRejectReason(finding.rejection_reason ?? "");
  }

  async function submitMessageFeedback(turn: ChatTurn, feedback: "correct" | "incorrect") {
    if (turn.role !== "truss" || !turn.provider) {
      return;
    }

    try {
      await createMessageFeedback(apiBaseUrl, turn.id, { feedback });
      appendTurn({
        role: "truss",
        tone: "success",
        text: feedback === "correct" ? "Feedback registrado: resultado correto." : "Feedback registrado: resultado incorreto."
      });
    } catch (feedbackError) {
      const message =
        feedbackError instanceof Error ? feedbackError.message : "Falha ao registrar feedback da mensagem.";
      setError(message);
    }
  }

  function moveFinding(offset: number) {
    if (activeFindingIndex < 0 || filteredFindings.length === 0) {
      return;
    }

    const nextIndex = (activeFindingIndex + offset + filteredFindings.length) % filteredFindings.length;
    focusFinding(filteredFindings[nextIndex]);
  }

  useEffect(() => {
    viewportRef.current = viewport;
  }, [viewport]);

  useEffect(() => {
    selectedIdsRef.current = selectedIds;
  }, [selectedIds]);

  useEffect(() => {
    findingsRef.current = findings;
  }, [findings]);

  useEffect(() => {
    spacePressedRef.current = isSpacePressed;
  }, [isSpacePressed]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }

    const updateSize = () => {
      const rect = canvas.getBoundingClientRect();
      setCanvasSizeState({ height: rect.height, width: rect.width });
    };
    const observer = new ResizeObserver(updateSize);
    updateSize();
    observer.observe(canvas);

    return () => observer.disconnect();
  }, [activeSheetId]);

  useEffect(() => {
    let cancelled = false;

    async function loadSheetMap() {
      // activeSheetId comeca vazio e a folha exibida cai em sheets[0], entao
      // a chave aqui tem de ser a folha realmente ativa, nao o id selecionado.
      if (!resolvedSheetId) {
        return null;
      }

      try {
        return await fetchSheetMap(apiBaseUrl, resolvedSheetId);
      } catch {
        return null;
      }
    }

    loadSheetMap().then((loaded) => {
      if (!cancelled) {
        setSheetMap(loaded);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, resolvedSheetId]);

  useEffect(() => {
    let cancelled = false;

    async function loadUsage() {
      if (!resolvedSheetId) {
        return null;
      }

      try {
        return summarizeUsage(await fetchSheetUsage(apiBaseUrl, resolvedSheetId));
      } catch {
        return null;
      }
    }

    loadUsage().then((summary) => {
      if (!cancelled) {
        setChatUsage(summary);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, resolvedSheetId, chatTurns.length]);

  useEffect(() => {
    let isMounted = true;

    async function loadFindings() {
      if (!activeSheet) {
        return;
      }

      try {
        const sheetFindings = await listSheetFindings(apiBaseUrl, activeSheet.id);
        if (isMounted) {
          const firstFinding = firstUnsuppressedFinding(sheetFindings);
          findingsRef.current = sheetFindings;
          setFindings(sheetFindings);
          setSelectedIds(new Set());
          setActiveFindingId(firstFinding?.id ?? "");
          setShowSuppressed(false);
          setShowSupportFindings(false);
          setFiltersOpen(false);
          setManualDraft(null);
          setCursorWorld(null);
          setMutedContextIds(new Set());
          setConversationId("");
          window.requestAnimationFrame(() => fitView());
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
    // fitView reads current canvas refs intentionally after the sheet render has settled.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSheet, apiBaseUrl]);

  useEffect(() => {
    if (!navigationTarget) {
      return;
    }
    const targetSheet = sheets.find((sheet) => sheet.id === navigationTarget.sheetId);
    if (targetSheet && targetSheet.id !== resolvedSheetId) {
      const frame = window.requestAnimationFrame(() => setActiveSheetId(targetSheet.id));
      return () => window.cancelAnimationFrame(frame);
    }
  }, [navigationTarget, resolvedSheetId, sheets]);

  useEffect(() => {
    if (
      !navigationTarget ||
      !navigationTarget.findingId ||
      navigationTarget.sheetId !== resolvedSheetId ||
      handledNavigationNonceRef.current === navigationTarget.nonce
    ) {
      return;
    }
    const finding = findings.find((item) => item.id === navigationTarget.findingId);
    if (!finding) {
      return;
    }
    const frame = window.requestAnimationFrame(() => {
      handledNavigationNonceRef.current = navigationTarget.nonce;
      if (finding.suppressed) {
        setShowSuppressed(true);
      }
      focusFinding(finding);
    });
    return () => window.cancelAnimationFrame(frame);
    // focusFinding intentionally reads the settled canvas refs after sheet and findings load.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [findings, navigationTarget, resolvedSheetId]);

  useEffect(() => {
    let isMounted = true;

    async function loadConversations() {
      if (!activeSheet) {
        setConversations([]);
        return;
      }

      setIsLoadingConversations(true);
      try {
        const sheetConversations = await listSheetConversations(apiBaseUrl, activeSheet.id);
        if (isMounted) {
          setConversations(sheetConversations);
        }
      } catch (conversationError) {
        if (isMounted) {
          setError(conversationError instanceof Error ? conversationError.message : "Falha ao carregar conversas.");
        }
      } finally {
        if (isMounted) {
          setIsLoadingConversations(false);
        }
      }
    }

    void loadConversations();

    return () => {
      isMounted = false;
    };
  }, [activeSheet, apiBaseUrl]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (isEditableTarget(event.target)) {
        return;
      }

      if (event.key === "Shift") {
        setIsShiftPressed(true);
      }

      if (event.code === "Space" && canvasIsActive) {
        event.preventDefault();
        setIsSpacePressed(true);
        return;
      }

      if (!canvasIsActive) {
        return;
      }

      const key = event.key.toLowerCase();
      const isModifier = event.ctrlKey || event.metaKey;

      if (event.key === "Escape") {
        event.preventDefault();
        beginInteraction(null);
        setManualDraft(null);
        setRejectPanelOpen(false);
        setRejectReason("");
        setRejectFindingId("");
        setSelectedIds(new Set());
        setActiveFindingId("");
        return;
      }

      if ((event.key === "Delete" || event.key === "Backspace") && selectedIdsRef.current.size > 0) {
        event.preventDefault();
        removeSelection();
        return;
      }

      if (key === "f") {
        event.preventDefault();
        fitView();
        return;
      }

      if (isModifier && (event.key === "0" || event.code === "Digit0")) {
        event.preventDefault();
        resetView();
        return;
      }

      if (isModifier && (event.key === "+" || event.key === "=")) {
        event.preventDefault();
        zoomByFactor(CANVAS_NAVIGATION.zoomStep);
        return;
      }

      if (isModifier && event.key === "-") {
        event.preventDefault();
        zoomByFactor(1 / CANVAS_NAVIGATION.zoomStep);
        return;
      }

      if (isModifier && key === "z" && event.shiftKey) {
        event.preventDefault();
        redo();
        return;
      }

      if (isModifier && key === "z") {
        event.preventDefault();
        undo();
        return;
      }

      if (isModifier && key === "y") {
        event.preventDefault();
        redo();
        return;
      }

      if (isModifier && key === "d") {
        event.preventDefault();
        duplicateSelection();
        return;
      }

      if (isModifier && key === "c") {
        event.preventDefault();
        copySelection();
        return;
      }

      if (isModifier && key === "v") {
        event.preventDefault();
        pasteSelection();
      }
    }

    function handleKeyUp(event: KeyboardEvent) {
      if (event.code === "Space") {
        setIsSpacePressed(false);
      }

      if (event.key === "Shift") {
        setIsShiftPressed(false);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
    };
    // Keyboard shortcuts operate on refs for current canvas state, avoiding stale closures during pointer-heavy interactions.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canvasIsActive]);

  useEffect(() => {
    return () => {
      if (rafRef.current !== null) {
        window.cancelAnimationFrame(rafRef.current);
      }
    };
  }, []);

  if (!activeSheet || !sheetBounds) {
    const hasUnavailableSource = unavailableDocuments.length > 0;
    return (
      <div className="flex min-h-[680px] items-center justify-center border border-dashed border-truss-line bg-truss-panel p-6 text-center">
        <div className="max-w-lg">
          <SheetIcon
            className={`mx-auto h-6 w-6 ${hasUnavailableSource ? "text-truss-warning" : "text-truss-accent"}`}
          />
          <p className="mt-4 text-sm font-semibold text-truss-text">
            {hasUnavailableSource ? "Fonte historica indisponivel" : "Viewer sem prancha"}
          </p>
          <p className="mt-3 max-w-md text-sm leading-6 text-truss-muted">
            {hasUnavailableSource
              ? "O registro, os achados e o feedback desta revisao foram preservados, mas o PDF original nao veio para este clone. Abra uma revisao atual para visualizar a prancha."
              : "Importe um PDF em uma revisao para liberar a visualizacao das folhas."}
          </p>
          {hasUnavailableSource ? (
            <ul className="mx-auto mt-4 grid max-w-md gap-1 text-left font-mono text-[10.5px] text-truss-subtle">
              {unavailableDocuments.map((document) => (
                <li className="truncate" key={document.id} title={document.original_filename}>
                  SOURCE_UNAVAILABLE / {document.original_filename}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden border border-truss-line bg-truss-panel">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-truss-line bg-truss-raised px-3 py-2">
        <div className="min-w-0">
          <p className="truss-mono-label">Prancha ativa</p>
          <p className="mt-1 truncate text-sm font-semibold text-truss-text">
            {sheetIdentityLabel(activeSheet, sheetMap)}
            {"documentName" in activeSheet ? ` / ${activeSheet.documentName}` : ""}
          </p>
          {sheetMap ? (
            <p className="mt-0.5 truncate font-mono text-[10.5px] uppercase tracking-[0.09em] text-truss-subtle">
              {sheetTechnicalScopesLabel(sheetMap)} &middot; {sheetMap.paper_format}
            </p>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex h-[38px] items-center gap-2 border border-truss-line bg-truss-panel px-3 font-mono text-[10px] uppercase tracking-[0.06em] text-truss-subtle">
            <Sparkles aria-hidden="true" className="h-3.5 w-3.5 text-truss-accent" />
            IA / {isAuditing ? "analisando" : reviewStatusLabel(activeReviewItem)}
          </span>
          <button className="truss-icon-button" onClick={() => moveSheet(-1)} title="Folha anterior" type="button">
            <ChevronLeft aria-hidden="true" className="truss-icon h-4 w-4" />
          </button>
          <span className="min-w-20 text-center font-mono text-[11px] text-truss-subtle">
            {activeIndex + 1}/{sheets.length}
          </span>
          <button className="truss-icon-button" onClick={() => moveSheet(1)} title="Proxima folha" type="button">
            <ChevronRight aria-hidden="true" className="truss-icon h-4 w-4" />
          </button>
          <button
            aria-label={assistantOpen ? "Voltar aos achados" : "Abrir assistente"}
            aria-pressed={assistantOpen}
            className="truss-icon-button"
            data-active={assistantOpen}
            onClick={() => setAssistantOpen((current) => !current)}
            title={assistantOpen ? "Voltar aos achados" : "Abrir assistente"}
            type="button"
          >
            <MessageSquare aria-hidden="true" className="truss-icon h-4 w-4" />
          </button>
          <details className="group relative">
            <summary className="truss-icon-button flex cursor-pointer list-none items-center justify-center" title="Ferramentas da prancha">
              <MoreHorizontal aria-hidden="true" className="truss-icon h-4 w-4" />
              <span className="sr-only">Ferramentas da prancha</span>
            </summary>
            <div className="absolute right-0 z-40 mt-2 grid min-w-56 gap-1 border border-truss-line bg-truss-raised p-2 shadow-truss-panel">
              <button
                aria-pressed={showFindings}
                className="truss-button justify-start"
                onClick={() => setShowFindings((current) => !current)}
                type="button"
              >
                {showFindings ? <Eye aria-hidden="true" className="truss-icon h-4 w-4" /> : <EyeOff aria-hidden="true" className="truss-icon h-4 w-4" />}
                {showFindings ? "Ocultar marcações" : "Mostrar marcações"}
              </button>
              <button
                aria-pressed={showViews}
                className="truss-button justify-start"
                onClick={() => setShowViews((current) => !current)}
                type="button"
              >
                <LayoutGrid aria-hidden="true" className="truss-icon h-4 w-4" />
                {showViews ? "Ocultar views" : "Mostrar views"}
              </button>
              <button
                aria-pressed={manualMode}
                className="truss-button justify-start"
                onClick={() => setManualMode((current) => !current)}
                type="button"
              >
                <RegionSelectIcon className="h-4 w-4" />
                Adicionar achado manual
              </button>
              <button
                className="truss-button justify-start"
                disabled={isAuditing}
                onClick={() => void runAuditFromChat()}
                type="button"
              >
                <Sparkles aria-hidden="true" className={`truss-icon h-4 w-4 ${isAuditing ? "animate-pulse" : ""}`} />
                Revisar esta prancha com IA
              </button>
            </div>
          </details>
        </div>
      </div>

      {error ? (
        <div
          className="border-b border-truss-danger/25 bg-truss-danger/10 px-4 py-2 text-sm text-truss-text"
          role="alert"
        >
          {error}
        </div>
      ) : null}

      <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden lg:grid-cols-[minmax(0,1fr)_340px] 2xl:grid-cols-[152px_minmax(0,1fr)_380px]">
        <aside className="hidden min-h-0 flex-col border-r border-truss-line bg-truss-raised 2xl:flex">
          <div className="border-b border-truss-line px-3 py-3">
            <p className="truss-mono-label">Pranchas</p>
            <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.06em] text-truss-subtle">
              {completedReviewCount}/{sheets.length} revisadas
            </p>
          </div>
          <nav aria-label="Pranchas da revisão" className="min-h-0 flex-1 overflow-y-auto p-1.5">
            {sheets.map((sheet, index) => {
              const reviewItem = reviewItemBySheet.get(sheet.id);
              const status = reviewItem?.status;
              return (
                <button
                  className="flex w-full items-center gap-2 border border-transparent px-2 py-2 text-left transition-colors hover:border-truss-line hover:bg-truss-panel data-[active=true]:border-truss-accent/55 data-[active=true]:bg-truss-accentSoft"
                  data-active={sheet.id === activeSheet.id}
                  key={sheet.id}
                  onClick={() => setActiveSheet(sheet)}
                  type="button"
                >
                  <span
                    aria-hidden="true"
                    className={`h-1.5 w-1.5 shrink-0 ${
                      status === "completed"
                        ? "bg-truss-success"
                        : status === "running"
                          ? "animate-pulse bg-truss-accent"
                          : status === "failed"
                            ? "bg-truss-danger"
                            : "bg-truss-subtle"
                    }`}
                  />
                  <span className="min-w-0">
                    <span className="block truncate font-mono text-[10px] uppercase tracking-[0.05em] text-truss-text">
                      {String(index + 1).padStart(2, "0")} · {sheet.label}
                    </span>
                    <span className="mt-0.5 block truncate font-mono text-[9px] uppercase tracking-[0.05em] text-truss-subtle">
                      {reviewStatusLabel(reviewItem)}
                    </span>
                  </span>
                </button>
              );
            })}
          </nav>
        </aside>
        <div className="flex min-h-0 min-w-0 flex-col">
          <div
            aria-label="Canvas da prancha. Use roda para pan, Ctrl mais roda para zoom no cursor, Espaco mais arrasto para pan e F para Fit View."
            className={`relative min-h-0 flex-1 select-none overflow-hidden bg-truss-canvas bg-[linear-gradient(to_right,rgba(121,131,138,0.12)_1px,transparent_1px),linear-gradient(to_bottom,rgba(121,131,138,0.12)_1px,transparent_1px)] bg-[size:28px_28px] outline-none ${
              interaction?.type === "pan"
                ? "cursor-grabbing"
                : manualMode || isShiftPressed
                  ? "cursor-crosshair"
                  : "cursor-grab"
            }`}
            onDoubleClick={() => {
              appendTurn({
                role: "truss",
                text: "Double click no canvas capturado. O ponto esta reservado para menu de criacao futuro."
              });
            }}
            onPointerCancel={handlePointerCancel}
            onPointerDown={handlePointerDown}
            onPointerEnter={() => setCanvasIsActive(true)}
            onPointerLeave={() => {
              pointersRef.current.clear();
              beginInteraction(null);
              setCursorWorld(null);
            }}
            onPointerMove={handlePointerMove}
            onPointerUp={(event) => void handlePointerUp(event)}
            onWheel={handleWheel}
            ref={canvasRef}
            role="application"
            style={{ touchAction: "none" }}
            tabIndex={0}
          >
            <CanvasRulers canvasSize={canvasSizeState} sheet={activeSheet} viewport={viewport} />

            <div className="absolute left-10 top-10 z-20 flex min-h-[34px] max-w-[calc(100%-3.25rem)] items-center gap-2 border border-truss-line bg-truss-panel/95 px-3 font-mono text-[11px] uppercase tracking-[0.06em] text-truss-subtle shadow-truss-panel">
              {manualMode ? (
                <RegionSelectIcon className="h-4 w-4 text-truss-accent" />
              ) : (
                <FocusRegionIcon className="h-4 w-4 text-truss-accent" />
              )}
              {manualMode
                ? "Modo achado manual"
                : (
                    <>
                      <span>{selectedIds.size} selecionado(s)</span>
                      <Kbd>Ctrl</Kbd>
                      <span>+ wheel zoom</span>
                      <Kbd>F</Kbd>
                      <span>fit</span>
                    </>
                  )}
            </div>

            {isAuditing ? (
              <div className="pointer-events-none absolute inset-y-7 left-0 z-20 w-1/2 animate-[truss-scan-sweep_1.55s_ease-in-out_infinite] truss-scan-sweep" />
            ) : null}

            <div
              className="absolute left-0 top-0 will-change-transform"
              style={{
                height: activeSheet.height_pt * CANVAS_NAVIGATION.renderScale,
                transform: `translate(${viewport.x}px, ${viewport.y}px) scale(${viewport.zoom})`,
                transformOrigin: "0 0",
                width: activeSheet.width_pt * CANVAS_NAVIGATION.renderScale
              }}
            >
              {/* eslint-disable-next-line @next/next/no-img-element -- Local rendered PDF sheets need direct transform control. */}
              <img
                alt={`Render da ${activeSheet.label}`}
                className="max-h-none max-w-none select-none border border-truss-line bg-truss-sheet shadow-[0_18px_55px_rgba(0,0,0,0.55)]"
                draggable={false}
                src={`${apiBaseUrl}/sheets/${activeSheet.id}/image`}
                style={{
                  height: activeSheet.height_pt * CANVAS_NAVIGATION.renderScale,
                  width: activeSheet.width_pt * CANVAS_NAVIGATION.renderScale
                }}
              />
              {showViews && sheetMap ? (
                <ViewOverlays
                  activeViewId={activeViewId}
                  onSelect={(view) => setActiveViewId(view.id)}
                  views={sheetMap.views ?? []}
                />
              ) : null}
              {showFindings
                  ? filteredFindings.map((finding) => {
                    const severity = severityMeta[finding.severity];
                    const isActive = selectedIds.has(finding.id);
                    const lifecycleState = findingLifecycleState(finding);
                    const presentation = findingOverlayPresentation(finding, activeSheet);
                    const isScopeMarker = presentation === "scope";

                    return (
                      <button
                        aria-label={`Selecionar achado ${severity.label}: ${finding.description}`}
                        className={
                          isScopeMarker
                            ? `absolute grid h-7 w-7 place-items-center border bg-truss-panel text-left transition-colors ${severity.ring} data-[active=true]:shadow-truss-red`
                            : `absolute border bg-truss-accent/5 text-left transition-colors ${severity.ring} data-[active=true]:bg-truss-accent/12 data-[active=true]:shadow-truss-red data-[draft=true]:border-dashed data-[status=confirmed]:border-truss-success data-[status=confirmed]:bg-truss-success/5 data-[status=rejected]:border-truss-subtle data-[status=rejected]:bg-transparent`
                        }
                        data-active={isActive}
                        data-draft={finding.isDraft}
                        data-status={finding.status}
                        key={finding.id}
                        onClick={(event) => {
                          event.stopPropagation();
                        }}
                        onPointerDown={(event) => {
                          // Sem stopPropagation: o canvas precisa ver o evento para
                          // iniciar o pan. Achados de pagina inteira cobrem todo o
                          // canvas, e engolir o pointerdown aqui trava a navegacao.
                          selectFinding(finding, event.shiftKey);
                        }}
                        style={{
                          height: isScopeMarker
                            ? undefined
                            : (finding.bbox.y1 - finding.bbox.y0) * CANVAS_NAVIGATION.renderScale,
                          left: finding.bbox.x0 * CANVAS_NAVIGATION.renderScale,
                          top: finding.bbox.y0 * CANVAS_NAVIGATION.renderScale,
                          transform: isScopeMarker ? `scale(${1 / viewport.zoom})` : undefined,
                          transformOrigin: isScopeMarker ? "0 0" : undefined,
                          width: isScopeMarker
                            ? undefined
                            : (finding.bbox.x1 - finding.bbox.x0) * CANVAS_NAVIGATION.renderScale
                        }}
                        title={`${finding.description} ${finding.isDraft ? "(draft local)" : ""}`}
                        type="button"
                      >
                        {isScopeMarker ? (
                          <AlertTriangle aria-hidden="true" className={`h-3.5 w-3.5 ${severity.tone}`} />
                        ) : (
                          <span className={`absolute -left-px -top-5 border px-1.5 py-0.5 font-mono text-[8.5px] uppercase tracking-[0.08em] ${severity.ring} ${severity.tone}`}>
                            {finding.isDraft
                              ? "DRAFT"
                              : finding.element_code
                                ? `${finding.element_code}${lifecycleState ? `/${lifecycleState.toUpperCase()}` : ""} · ${severity.label}`
                                : severity.label}
                          </span>
                        )}
                      </button>
                    );
                  })
                : null}
            </div>

            {marqueeRect ? (
              <div
                className={`pointer-events-none absolute z-10 border ${
                  interaction?.type === "manual"
                    ? "border-truss-success bg-truss-success/10"
                    : "border-truss-accent bg-truss-accent/10"
                }`}
                style={{
                  height: rectHeight(marqueeRect) * viewport.zoom * CANVAS_NAVIGATION.renderScale,
                  left: worldToScreen({ x: marqueeRect.x0, y: marqueeRect.y0 }, viewport).x,
                  top: worldToScreen({ x: marqueeRect.x0, y: marqueeRect.y0 }, viewport).y,
                  width: rectWidth(marqueeRect) * viewport.zoom * CANVAS_NAVIGATION.renderScale
                }}
              />
            ) : null}

            {manualDraft ? (
              <div
                className="pointer-events-none absolute z-10 border border-truss-success bg-truss-success/10 truss-region-focus"
                style={{
                  height: rectHeight(manualDraft.bbox) * viewport.zoom * CANVAS_NAVIGATION.renderScale,
                  left: worldToScreen({ x: manualDraft.bbox.x0, y: manualDraft.bbox.y0 }, viewport).x,
                  top: worldToScreen({ x: manualDraft.bbox.x0, y: manualDraft.bbox.y0 }, viewport).y,
                  width: rectWidth(manualDraft.bbox) * viewport.zoom * CANVAS_NAVIGATION.renderScale
                }}
              />
            ) : null}

            <ZoomControls
              onFit={fitView}
              onZoomIn={() => zoomByFactor(CANVAS_NAVIGATION.zoomStep)}
              onZoomOut={() => zoomByFactor(1 / CANVAS_NAVIGATION.zoomStep)}
              zoom={viewport.zoom}
            />

            {contentBounds ? (
              <CanvasMinimap
                bounds={contentBounds}
                canvasSize={canvasSizeState}
                findings={filteredFindings}
                hidden={!showMinimap}
                onCenter={centerOnWorld}
                onToggle={() => setShowMinimap((current) => !current)}
                viewport={viewport}
              />
            ) : null}

            <div className="absolute inset-x-0 bottom-0 z-20 flex min-h-8 flex-wrap items-center gap-x-4 gap-y-1 border-t border-truss-line bg-truss-raised/95 px-3 py-1 font-mono text-[10.5px] uppercase tracking-[0.06em] text-truss-subtle">
              <span>cursor / {formatPoint(cursorWorld)}</span>
              <span>zoom / {Math.round(viewport.zoom * 100)}%</span>
              <span>folha / {Math.round(activeSheet.width_pt)} x {Math.round(activeSheet.height_pt)} pt</span>
              <span>selecionados / {selectedIds.size}</span>
              <span className={isAuditing ? "text-truss-accent" : "text-truss-subtle"}>
                revisão IA / {isAuditing ? "analisando" : reviewStatusLabel(activeReviewItem)}
              </span>
            </div>
          </div>
        </div>

        {!assistantOpen ? (
          <FindingsDrawer
            count={filteredFindings.length}
            toolbar={(
              <button
                aria-expanded={filtersOpen}
                className="ml-auto inline-flex h-10 items-center gap-2 px-2 font-mono text-[10px] uppercase tracking-[0.07em] text-truss-subtle transition-colors hover:text-truss-text"
                onClick={() => setFiltersOpen((current) => !current)}
                type="button"
              >
                <SlidersHorizontal aria-hidden="true" className="truss-icon h-3.5 w-3.5" />
                filtros
                {statusFilter !== "all" || severityFilter !== "all" || showSuppressed || showSupportFindings ? (
                  <span className="text-truss-accent">ativos</span>
                ) : null}
              </button>
            )}
            variant="panel"
          >
            {filtersOpen ? <div className="border-b border-truss-line px-3 py-3">
              <div className="grid gap-2">
                <div className="truss-segment overflow-x-auto">
                  {(["all", "pending", "confirmed", "rejected"] as const).map((status) => (
                    <button
                      className="h-[34px] px-3 font-mono text-[10.5px] uppercase tracking-[0.06em] text-truss-subtle transition-colors hover:bg-truss-panel2 hover:text-truss-text data-[active=true]:bg-truss-accentSoft data-[active=true]:text-[#ffb3aa]"
                      data-active={statusFilter === status}
                      key={status}
                      onClick={() => setStatusFilter(status)}
                      type="button"
                    >
                      {status === "all" ? "todos" : status}
                    </button>
                  ))}
                </div>
                <div className="truss-segment overflow-x-auto">
                  {(["all", "critical", "high", "medium", "low"] as const).map((severity) => (
                    <button
                      className="h-[34px] px-3 font-mono text-[10.5px] uppercase tracking-[0.06em] text-truss-subtle transition-colors hover:bg-truss-panel2 hover:text-truss-text data-[active=true]:bg-truss-accentSoft data-[active=true]:text-[#ffb3aa]"
                      data-active={severityFilter === severity}
                      key={severity}
                      onClick={() => setSeverityFilter(severity)}
                      type="button"
                    >
                      {severity}
                    </button>
                  ))}
                </div>
                <button
                  aria-pressed={showSuppressed}
                  className="flex h-[34px] items-center justify-center gap-2 border border-truss-line bg-truss-raised px-3 font-mono text-[10.5px] uppercase tracking-[0.06em] text-truss-subtle transition-colors hover:bg-truss-panel2 hover:text-truss-text data-[active=true]:border-truss-info/55 data-[active=true]:bg-truss-info/10 data-[active=true]:text-truss-info disabled:cursor-not-allowed disabled:opacity-45"
                  data-active={showSuppressed}
                  disabled={suppressedCount === 0}
                  onClick={() => setShowSuppressed((current) => !current)}
                  type="button"
                >
                  <EyeOff aria-hidden="true" className="truss-icon h-3.5 w-3.5" />
                  Silenciados / {suppressedCount}
                </button>
                {supportFindingCount > 0 ? (
                  <button
                    aria-pressed={showSupportFindings}
                    className="flex h-10 items-center justify-center gap-2 border border-truss-line bg-truss-raised px-3 font-mono text-[10.5px] uppercase tracking-[0.06em] text-truss-subtle transition-colors hover:bg-truss-panel2 hover:text-truss-text data-[active=true]:border-truss-info/55 data-[active=true]:bg-truss-info/10 data-[active=true]:text-truss-info"
                    data-active={showSupportFindings}
                    onClick={() => setShowSupportFindings((current) => !current)}
                    type="button"
                  >
                    <Eye aria-hidden="true" className="truss-icon h-3.5 w-3.5" />
                    Regras locais / {supportFindingCount}
                  </button>
                ) : null}
              </div>
            </div> : null}

            <div className="max-h-[34vh] overflow-y-auto border-b border-truss-line">
              {filteredFindings.length === 0 ? (
                <div className="m-3 border border-dashed border-truss-line px-3 py-5 text-center text-sm text-truss-muted">
                  {findings.length === 0 && auditCoverage ? (
                    <>
                      Nenhum achado nesta folha.
                      <span className="mt-1 block font-mono text-[10px] uppercase tracking-[0.08em] text-truss-subtle">
                        {auditCoverageSummary(auditCoverage)}
                      </span>
                    </>
                  ) : (
                    suppressedCount > 0 && !showSuppressed
                      ? `${suppressedCount} achado(s) silenciado(s). Ative o filtro para revisar.`
                      : "Nenhum achado nesse filtro."
                  )}
                </div>
              ) : (
                filteredFindings.map((finding) => {
                  const severity = severityMeta[finding.severity];
                  const level = confidenceLevel(finding.confidence);

                  return (
                    <button
                      className="flex w-full gap-3 border-b border-truss-line px-3 py-3 text-left transition-colors hover:bg-truss-panel data-[active=true]:bg-truss-accentSoft data-[active=true]:shadow-[inset_2px_0_0_var(--red)] data-[suppressed=true]:bg-truss-info/5"
                      data-active={selectedIds.has(finding.id)}
                      data-suppressed={finding.suppressed}
                      key={finding.id}
                      onClick={(event) => {
                        selectFinding(finding, event.shiftKey);
                        focusFinding(finding, false);
                      }}
                      type="button"
                    >
                      <AlertTriangle aria-hidden="true" className={`truss-icon mt-0.5 h-4 w-4 shrink-0 ${severity.tone}`} />
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm leading-5 text-truss-text">
                          {finding.description}
                          {finding.isDraft ? <span className="ml-2 font-mono text-[10px] text-truss-warning">DRAFT</span> : null}
                        </span>
                        <span className="mt-2 flex flex-wrap items-center gap-2">
                          {findingElementLabel(finding) ? (
                            <span className="inline-flex h-6 items-center border border-truss-accent/45 bg-truss-accentSoft px-2 font-mono text-[10px] uppercase tracking-[0.06em] text-truss-text">
                              {findingElementLabel(finding)}
                            </span>
                          ) : null}
                          {findingSourceLabel(finding) ? (
                            <span className="inline-flex h-6 items-center border border-truss-info/50 bg-truss-info/10 px-2 font-mono text-[10px] uppercase tracking-[0.06em] text-truss-info">
                              {findingSourceLabel(finding)}
                            </span>
                          ) : null}
                          {finding.suppressed ? (
                            <span className="inline-flex h-6 items-center gap-1 border border-truss-info/50 bg-truss-info/10 px-2 font-mono text-[10px] uppercase tracking-[0.06em] text-truss-info">
                              <EyeOff aria-hidden="true" className="truss-icon h-3 w-3" />
                              Silenciado
                            </span>
                          ) : null}
                          <SeverityBadge severity={finding.severity} />
                          <StatusBadge status={finding.status} />
                          <span className="inline-flex h-6 items-center gap-1 border border-truss-line bg-truss-raised px-2 font-mono text-[10px] uppercase tracking-[0.06em] text-truss-subtle">
                            <ConfidenceBarsIcon className={`h-3.5 w-3.5 ${level === "high" ? "text-truss-muted" : level === "medium" ? "text-truss-warning" : "text-truss-subtle"}`} />
                            {confidenceLabel(finding.confidence)}
                          </span>
                        </span>
                      </span>
                    </button>
                  );
                })
              )}
            </div>

            {manualDraft ? (
              <div className="border-b border-truss-line p-3">
                <form className="border border-truss-success/40 bg-truss-success/10 p-3" onSubmit={(event) => void submitManualFinding(event)}>
                  <div className="flex items-center justify-between gap-3">
                    <p className="truss-mono-label text-truss-success">Novo achado manual</p>
                    <button
                      className="font-mono text-[10px] uppercase tracking-[0.06em] text-truss-subtle hover:text-truss-text"
                      onClick={() => setManualDraft(null)}
                      type="button"
                    >
                      cancelar
                    </button>
                  </div>
                  <p className="mt-2 font-mono text-[10.5px] uppercase tracking-[0.06em] text-truss-subtle">
                    Regiao / {Math.round(manualDraft.bbox.x0)},{Math.round(manualDraft.bbox.y0)} - {Math.round(manualDraft.bbox.x1)},{Math.round(manualDraft.bbox.y1)} pt
                  </p>
                  <div className="mt-3 grid grid-cols-2 gap-2">
                    <label className="grid gap-1">
                      <span className="truss-mono-label">Tipo</span>
                      <select
                        className="truss-field px-2 font-mono text-[11px]"
                        onChange={(event) => setManualType(event.target.value as FindingType)}
                        value={manualType}
                      >
                        <option value="attention">ATTENTION</option>
                        <option value="inconsistency">INCONSISTENCY</option>
                        <option value="missing_information">MISSING INFO</option>
                        <option value="unverifiable">NOT VERIFIABLE</option>
                      </select>
                    </label>
                    <label className="grid gap-1">
                      <span className="truss-mono-label">Severidade</span>
                      <select
                        className="truss-field px-2 font-mono text-[11px]"
                        onChange={(event) => setManualSeverity(event.target.value as FindingSeverity)}
                        value={manualSeverity}
                      >
                        <option value="low">LOW</option>
                        <option value="medium">MEDIUM</option>
                        <option value="high">HIGH</option>
                        <option value="critical">CRITICAL</option>
                      </select>
                    </label>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <TypeBadge type={manualType} />
                    <SeverityBadge severity={manualSeverity} />
                    <ConfidenceBadge confidence={1} />
                  </div>
                  <label className="mt-3 grid gap-1">
                    <span className="truss-mono-label">Descricao</span>
                    <textarea
                      className="truss-field resize-none px-3 py-2 text-sm leading-5"
                      onChange={(event) => setManualDescription(event.target.value)}
                      placeholder="Descreva a suspeita observada nessa regiao."
                      value={manualDescription}
                    />
                  </label>
                  <button
                    className="truss-button truss-button-primary mt-3 w-full disabled:opacity-50"
                    disabled={isCreatingManual || !manualDescription.trim()}
                    type="submit"
                  >
                    Registrar achado
                  </button>
                </form>
              </div>
            ) : null}

            {activeFinding ? (
              <div className="border-b border-truss-line p-3">
                <div className="border border-truss-accent/40 bg-truss-accentSoft p-3 text-sm text-truss-text">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="truss-mono-label mr-auto">
                      Achado {activeFindingIndex + 1} de {filteredFindings.length}
                    </p>
                    <StatusBadge status={activeFinding.status} />
                  </div>
                  <p className="mt-2 leading-6">{activeFinding.description}</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {findingElementLabel(activeFinding) ? (
                      <span className="inline-flex h-6 items-center border border-truss-accent/45 bg-truss-accentSoft px-2 font-mono text-[10px] uppercase tracking-[0.06em] text-truss-text">
                        {findingElementLabel(activeFinding)}
                      </span>
                    ) : null}
                    {findingSourceLabel(activeFinding) ? (
                      <span className="inline-flex h-6 items-center border border-truss-info/50 bg-truss-info/10 px-2 font-mono text-[10px] uppercase tracking-[0.06em] text-truss-info">
                        {findingSourceLabel(activeFinding)}
                      </span>
                    ) : null}
                    <TypeBadge type={activeFinding.type} />
                    <SeverityBadge severity={activeFinding.severity} />
                    <ConfidenceBadge confidence={activeFinding.confidence} />
                    {findingLevelTransition(activeFinding) ? (
                      <span className="inline-flex h-6 items-center border border-truss-line bg-truss-raised px-2 font-mono text-[10px] uppercase tracking-[0.06em] text-truss-subtle">
                        Nivel {findingLevelTransition(activeFinding)?.source} → {findingLevelTransition(activeFinding)?.target}
                      </span>
                    ) : null}
                    {findingSheetTransition(activeFinding) ? (
                      <span className="inline-flex h-6 items-center border border-truss-line bg-truss-raised px-2 font-mono text-[10px] uppercase tracking-[0.06em] text-truss-subtle">
                        Folha {findingSheetTransition(activeFinding)?.source} → {findingSheetTransition(activeFinding)?.target}
                      </span>
                    ) : null}
                    {findingSectionTransition(activeFinding) ? (
                      <span className="inline-flex h-6 items-center border border-truss-line bg-truss-raised px-2 font-mono text-[10px] uppercase tracking-[0.06em] text-truss-subtle">
                        Unidade {findingSectionTransition(activeFinding)?.unit ?? "nao declarada"}
                      </span>
                    ) : null}
                  </div>
                  {shouldShowHypothesisNotice(activeFinding) ? (
                    <div className="mt-3 border border-truss-warning/35 bg-truss-warning/10 px-3 py-2 text-xs leading-5 text-truss-text">
                      Hipotese pendente de verificacao humana. Severidade mede impacto, nao certeza.
                    </div>
                  ) : null}
                  {activeFinding.suppressed ? (
                    <div className="mt-3 border border-truss-info/40 bg-truss-info/10 p-3 text-xs leading-5 text-truss-text">
                      <div className="flex items-start gap-2">
                        <EyeOff aria-hidden="true" className="truss-icon mt-0.5 h-4 w-4 shrink-0 text-truss-info" />
                        <div className="min-w-0 flex-1">
                          <p className="font-semibold">Regra silenciada neste tipo de prancha</p>
                          <p className="mt-1 text-truss-muted">
                            {activeFinding.rule_id} nao aparece por padrao em folhas {sheetTypeLabel(activeFinding.suppression_sheet_type ?? sheetMap?.sheet_type ?? "unknown")}. O achado continua salvo e auditavel.
                          </p>
                          <button
                            className="truss-button mt-3 w-full disabled:opacity-50"
                            disabled={isSavingPreference}
                            onClick={() => void restoreRulePreference(activeFinding)}
                            type="button"
                          >
                            Reativar regra
                          </button>
                        </div>
                      </div>
                    </div>
                  ) : canProposeRulePreference(activeFinding) && activeFinding.rejection_reason ? (
                    <div className="mt-3 border border-truss-warning/40 bg-truss-warning/10 p-3 text-xs leading-5 text-truss-text">
                      <div className="flex items-start gap-2">
                        <EyeOff aria-hidden="true" className="truss-icon mt-0.5 h-4 w-4 shrink-0 text-truss-warning" />
                        <div className="min-w-0 flex-1">
                          <p className="font-semibold">Transformar esta rejeicao em preferencia?</p>
                          <p className="mt-1 text-truss-muted">
                            Silenciar {activeFinding.rule_id} apenas em folhas {sheetTypeLabel(sheetMap?.sheet_type ?? "unknown")}. Nada sera apagado e a decisao pode ser revogada.
                          </p>
                          <button
                            className="truss-button truss-button-primary mt-3 w-full disabled:opacity-50"
                            disabled={isSavingPreference}
                            onClick={() => void applyRulePreference(activeFinding)}
                            type="button"
                          >
                            Silenciar neste tipo
                          </button>
                        </div>
                      </div>
                    </div>
                  ) : null}
                  <div className="mt-3 grid gap-2 font-mono text-[10.5px] uppercase tracking-[0.06em] text-truss-subtle">
                    <span>Regiao / {formatBBox(activeFinding)}</span>
                    <span>Origem / {findingSourceLabel(activeFinding) ?? activeFinding.origin}</span>
                    {activeFinding.registry_hash ? <span>Registry / {activeFinding.registry_hash}</span> : null}
                    {activeFinding.isDraft ? <span>Persistencia / draft local</span> : null}
                    {activeFinding.rejection_reason ? <span>Rejeicao / {activeFinding.rejection_reason}</span> : null}
                  </div>
                  <FindingEvidence finding={activeFinding} key={activeFinding.id} />
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button className="truss-icon-button" onClick={() => moveFinding(-1)} title="Achado anterior" type="button">
                      <ChevronLeft aria-hidden="true" className="truss-icon h-4 w-4" />
                    </button>
                    <button className="truss-icon-button" onClick={() => moveFinding(1)} title="Proximo achado" type="button">
                      <ChevronRight aria-hidden="true" className="truss-icon h-4 w-4" />
                    </button>
                    <button
                      className="truss-icon-button hover:border-truss-success/50 hover:text-truss-success"
                      disabled={isSavingFeedback}
                      onClick={() => void setFindingStatus("confirmed")}
                      title="Confirmar achado"
                      type="button"
                    >
                      <Check aria-hidden="true" className="truss-icon h-4 w-4" />
                    </button>
                    <button
                      className="truss-icon-button hover:border-truss-danger/50 hover:text-truss-danger"
                      disabled={isSavingFeedback}
                      onClick={() => {
                        setRejectPanelOpen(true);
                        setRejectFindingId(activeFinding.id);
                        setRejectReason(activeFinding.rejection_reason ?? "");
                      }}
                      title="Rejeitar achado"
                      type="button"
                    >
                      <X aria-hidden="true" className="truss-icon h-4 w-4" />
                    </button>
                    <button
                      className="truss-icon-button"
                      onClick={() => focusFinding(activeFinding)}
                      title="Focar regiao selecionada"
                      type="button"
                    >
                      <Maximize2 aria-hidden="true" className="truss-icon h-4 w-4" />
                    </button>
                  </div>
                  {rejectPanelOpen && rejectFindingId === activeFinding.id ? (
                    <form
                      className="mt-3 border border-truss-danger/35 bg-truss-danger/10 p-3"
                      onSubmit={(event) => {
                        event.preventDefault();
                        void setFindingStatus("rejected", rejectReason);
                      }}
                    >
                      <label className="grid gap-1">
                        <span className="truss-mono-label text-truss-danger">Justificativa de rejeicao</span>
                        <textarea
                          className="truss-field resize-none px-3 py-2 text-sm leading-5"
                          onChange={(event) => setRejectReason(event.target.value)}
                          placeholder="Explique por que esse achado nao procede."
                          value={rejectReason}
                        />
                      </label>
                      <div className="mt-3 flex gap-2">
                        <button
                          className="truss-button flex-1"
                          onClick={() => {
                            setRejectPanelOpen(false);
                            setRejectReason("");
                            setRejectFindingId("");
                          }}
                          type="button"
                        >
                          Cancelar
                        </button>
                        <button
                          className="truss-button truss-button-primary flex-1 disabled:opacity-50"
                          disabled={isSavingFeedback || !rejectReason.trim()}
                          type="submit"
                        >
                          Salvar rejeicao
                        </button>
                      </div>
                    </form>
                  ) : null}
                </div>
              </div>
            ) : null}

          </FindingsDrawer>
        ) : null}

        {assistantOpen ? (
        <aside className="flex min-h-0 flex-col border-t border-truss-line bg-truss-raised lg:border-l lg:border-t-0">
          <TrussChat
            activeFinding={activeFinding}
            activeConversationId={conversationId}
            activity={chatActivity}
            conversations={conversations}
            contextItems={visibleChatContextItems}
            documentName={"documentName" in activeSheet ? String(activeSheet.documentName) : ""}
            isLoadingConversations={isLoadingConversations}
            isRunning={isChatting || isAuditing || isLoadingChatHistory}
            message={chatMessage}
            messages={chatTurns}
            mode={chatMode}
            onAuditSelection={auditSelectionFromChatAction}
            onConfirmFinding={(finding) => void setFindingStatus("confirmed", undefined, finding)}
            onEditMessage={editChatTurn}
            onExplainFinding={explainFindingFromChatAction}
            onFocusFinding={(finding) => focusFinding(finding)}
            onInsertPrompt={insertChatPrompt}
            onMessageFeedback={(turn, feedback) => void submitMessageFeedback(turn, feedback)}
            onMessageChange={setChatMessage}
            onModeChange={setChatMode}
            onNewConversation={startNewConversation}
            onRegenerate={regenerateChatTurn}
            onRejectFinding={rejectFindingFromChat}
            onRemoveContext={(id) => setMutedContextIds((current) => new Set([...current, id]))}
            onRunSheetAudit={() => void runAuditFromChat()}
            onSelectConversation={(nextConversationId) => void loadConversationHistory(nextConversationId)}
            onRetry={retryLastChatTurn}
            onStop={stopChat}
            onSubmit={(event) => handleChatSubmit(event)}
            runDetail={chatRunDetail}
            runState={chatRunState}
            usage={chatUsage}
            selectedCount={selectedIds.size}
            sheetLabel={activeSheet.label}
          />
        </aside>
        ) : null}
      </div>
    </div>
  );
}
