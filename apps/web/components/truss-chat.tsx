"use client";

import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  ChevronDown,
  Clipboard,
  Copy,
  Crosshair,
  Edit3,
  FilePlus2,
  LocateFixed,
  MessageSquare,
  Paperclip,
  RefreshCw,
  Send,
  Square,
  ThumbsDown,
  ThumbsUp,
  X
} from "lucide-react";

import { ChatContextItem, Conversation, Finding } from "@/lib/projects-api";
import { ConfidenceBadge, SeverityBadge, StatusBadge, TypeBadge } from "@/components/truss-primitives";

export type ChatMode =
  | "ask"
  | "audit_sheet"
  | "audit_selection"
  | "explain_finding"
  | "check_text";

export type ChatActivityState =
  | "idle"
  | "thinking"
  | "using-tool"
  | "completed"
  | "stopped"
  | "error";

export type ChatTurn = {
  id: string;
  role: "truss" | "user";
  text: string;
  tone?: "default" | "error" | "success";
  contextItems?: ChatContextItem[];
  provider?: string;
  model?: string;
  elapsedMs?: number;
  stopped?: boolean;
  streaming?: boolean;
};

export type AgentActivity = {
  state: ChatActivityState;
  title: string;
  steps: Array<{ id: string; label: string; state: "done" | "active" | "queued" | "error" }>;
};

const modeLabels: Record<ChatMode, string> = {
  ask: "Perguntar",
  audit_sheet: "Auditar prancha",
  audit_selection: "Auditar seleção",
  explain_finding: "Explicar achado",
  check_text: "Verificar textos"
};

const commands: Array<{ command: string; label: string; mode: ChatMode; prompt: string }> = [
  { command: "/auditar", label: "Auditar prancha", mode: "audit_sheet", prompt: "Audite a prancha ativa." },
  { command: "/auditar-selecao", label: "Auditar seleção", mode: "audit_selection", prompt: "Audite somente a seleção atual." },
  { command: "/explicar", label: "Explicar achado", mode: "explain_finding", prompt: "Explique o achado selecionado." },
  { command: "/textos", label: "Verificar textos", mode: "check_text", prompt: "Verifique os textos desta prancha." },
  { command: "/resumo", label: "Resumo técnico", mode: "ask", prompt: "Resuma os pontos de atenção da prancha ativa." }
];

function elapsedLabel(elapsedMs?: number) {
  if (!elapsedMs) {
    return "";
  }

  return `${(elapsedMs / 1000).toFixed(1).replace(".", ",")}s`;
}

function roleLabel(turn: ChatTurn) {
  return turn.role === "user" ? "Você" : "Truss";
}

function compactTimestamp(value: string) {
  const [date, time = ""] = value.split("T");
  return `${date} ${time.slice(0, 5)}`.trim();
}

function ConversationHistory({
  activeConversationId,
  conversations,
  isLoading,
  onNewConversation,
  onSelectConversation
}: {
  activeConversationId: string;
  conversations: Conversation[];
  isLoading: boolean;
  onNewConversation: () => void;
  onSelectConversation: (conversationId: string) => void;
}) {
  return (
    <div className="border-b border-truss-line bg-truss-base/60 px-3 py-2">
      <div className="mb-2 flex items-center gap-2">
        <p className="truss-mono-label mr-auto">Conversas</p>
        <button
          className="truss-button h-7 min-h-7 px-2 font-mono text-[10px]"
          onClick={onNewConversation}
          type="button"
        >
          <FilePlus2 aria-hidden="true" className="truss-icon h-3.5 w-3.5" />
          Nova
        </button>
      </div>
      {isLoading ? (
        <div className="grid gap-1.5">
          <span className="h-7 animate-pulse bg-truss-panel2" />
          <span className="h-7 w-2/3 animate-pulse bg-truss-panel2" />
        </div>
      ) : conversations.length === 0 ? (
        <p className="border border-dashed border-truss-line px-2 py-2 text-xs leading-5 text-truss-subtle">
          Nenhuma conversa salva nesta prancha.
        </p>
      ) : (
        <div className="flex gap-2 overflow-x-auto pb-1">
          {conversations.map((conversation) => (
            <button
              className="min-w-[168px] max-w-[220px] border border-truss-line bg-truss-panel px-2 py-2 text-left transition-colors hover:bg-truss-panel2 data-[active=true]:border-truss-accent data-[active=true]:bg-truss-accentSoft"
              data-active={conversation.id === activeConversationId}
              key={conversation.id}
              onClick={() => onSelectConversation(conversation.id)}
              title={conversation.title}
              type="button"
            >
              <span className="block truncate text-xs font-medium text-truss-text">{conversation.title}</span>
              <span className="mt-1 block truncate font-mono text-[10px] uppercase tracking-[0.06em] text-truss-subtle">
                {conversation.id === activeConversationId ? "ativa" : compactTimestamp(conversation.updated_at)}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function ActivityPanel({ activity }: { activity: AgentActivity }) {
  const [expanded, setExpanded] = useState(activity.state !== "idle");

  if (activity.state === "idle") {
    return null;
  }

  return (
    <div className="border-b border-truss-line bg-truss-panel/70 px-3 py-2">
      <button
        className="flex w-full items-center gap-2 text-left font-mono text-[10.5px] uppercase tracking-[0.06em] text-truss-subtle hover:text-truss-text"
        onClick={() => setExpanded((current) => !current)}
        type="button"
      >
        <ChevronDown aria-hidden="true" className={`truss-icon h-3.5 w-3.5 transition-transform ${expanded ? "" : "-rotate-90"}`} />
        <span className={activity.state === "error" ? "text-truss-danger" : activity.state === "completed" ? "text-truss-success" : "text-truss-accent"}>
          {activity.title}
        </span>
      </button>
      {expanded ? (
        <div className="mt-2 grid gap-1">
          {activity.steps.map((step) => (
            <div className="flex items-center gap-2 font-mono text-[10.5px] uppercase tracking-[0.06em] text-truss-subtle" key={step.id}>
              <span
                className={`h-1.5 w-1.5 ${
                  step.state === "done"
                    ? "bg-truss-success"
                    : step.state === "active"
                      ? "bg-truss-accent"
                      : step.state === "error"
                        ? "bg-truss-danger"
                        : "bg-truss-line"
                }`}
              />
              {step.label}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ContextChips({
  contextItems,
  onRemoveContext
}: {
  contextItems: ChatContextItem[];
  onRemoveContext: (id: string) => void;
}) {
  if (contextItems.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-wrap gap-1.5">
      {contextItems.map((item) => (
        <span
          className="inline-flex h-6 max-w-full items-center gap-1 border border-truss-line bg-truss-raised px-2 font-mono text-[10px] uppercase tracking-[0.06em] text-truss-subtle"
          key={item.id}
          title={item.value}
        >
          <span className="truncate">{item.label}</span>
          {item.kind === "sheet" || item.kind === "document" ? null : (
            <button
              aria-label={`Remover contexto ${item.label}`}
              className="ml-1 text-truss-subtle hover:text-truss-text"
              onClick={() => onRemoveContext(item.id)}
              type="button"
            >
              <X aria-hidden="true" className="truss-icon h-3 w-3" />
            </button>
          )}
        </span>
      ))}
    </div>
  );
}

function ResponseActionPanel({
  disabled,
  finding,
  onAuditSelection,
  onConfirmFinding,
  onExplainFinding,
  onFocusFinding,
  onRejectFinding,
  onRunSheetAudit,
  selectedCount
}: {
  disabled: boolean;
  finding: Finding | null;
  onAuditSelection: () => void;
  onConfirmFinding: (finding: Finding) => void;
  onExplainFinding: (finding: Finding) => void;
  onFocusFinding: (finding: Finding) => void;
  onRejectFinding: (finding: Finding) => void;
  onRunSheetAudit: () => void;
  selectedCount: number;
}) {
  return (
    <div className="border border-truss-line bg-truss-panel p-3">
      <div className="flex flex-wrap items-center gap-2">
        <p className="truss-mono-label mr-auto">Ações disponíveis</p>
        {finding ? <StatusBadge status={finding.status} /> : null}
      </div>
      {finding ? (
        <>
          <p className="mt-2 text-sm leading-5 text-truss-text">{finding.description}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <TypeBadge type={finding.type} />
            <SeverityBadge severity={finding.severity} />
            <ConfidenceBadge confidence={finding.confidence} />
          </div>
        </>
      ) : null}
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          className="truss-button h-[32px] min-h-[32px] px-2 text-[11px] disabled:cursor-not-allowed disabled:opacity-45"
          disabled={disabled}
          onClick={onRunSheetAudit}
          type="button"
        >
          <RefreshCw aria-hidden="true" className="truss-icon h-3.5 w-3.5" />
          Auditar prancha
        </button>
        <button
          className="truss-button h-[32px] min-h-[32px] px-2 text-[11px] disabled:cursor-not-allowed disabled:opacity-45"
          disabled={disabled || selectedCount === 0}
          onClick={onAuditSelection}
          type="button"
        >
          <Crosshair aria-hidden="true" className="truss-icon h-3.5 w-3.5" />
          Auditar seleção
        </button>
        {finding ? (
          <>
            <button
              className="truss-button h-[32px] min-h-[32px] px-2 text-[11px] disabled:cursor-not-allowed disabled:opacity-45"
              disabled={disabled}
              onClick={() => onFocusFinding(finding)}
              type="button"
            >
              <LocateFixed aria-hidden="true" className="truss-icon h-3.5 w-3.5" />
              Localizar
            </button>
            <button
              className="truss-button h-[32px] min-h-[32px] px-2 text-[11px] disabled:cursor-not-allowed disabled:opacity-45"
              disabled={disabled}
              onClick={() => onExplainFinding(finding)}
              type="button"
            >
              <MessageSquare aria-hidden="true" className="truss-icon h-3.5 w-3.5" />
              Explicar
            </button>
            <button
              className="truss-button h-[32px] min-h-[32px] px-2 text-[11px] disabled:cursor-not-allowed disabled:opacity-45"
              disabled={disabled}
              onClick={() => onConfirmFinding(finding)}
              type="button"
            >
              <Check aria-hidden="true" className="truss-icon h-3.5 w-3.5" />
              Confirmar
            </button>
            <button
              className="truss-button h-[32px] min-h-[32px] px-2 text-[11px] disabled:cursor-not-allowed disabled:opacity-45"
              disabled={disabled}
              onClick={() => onRejectFinding(finding)}
              type="button"
            >
              <X aria-hidden="true" className="truss-icon h-3.5 w-3.5" />
              Rejeitar
            </button>
          </>
        ) : null}
      </div>
    </div>
  );
}

function MessageActions({
  onFeedback,
  onEdit,
  onRegenerate,
  text,
  turn
}: {
  onFeedback: (turn: ChatTurn, feedback: "correct" | "incorrect") => void;
  onEdit: (turn: ChatTurn) => void;
  onRegenerate: (turn: ChatTurn) => void;
  text: string;
  turn: ChatTurn;
}) {
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null);

  async function copyText() {
    await navigator.clipboard.writeText(text);
  }

  return (
    <div className="mt-2 flex items-center gap-1 opacity-70 transition-opacity group-hover:opacity-100">
      <button className="truss-icon-button h-7 min-h-7 w-7 border-truss-line" onClick={() => void copyText()} title="Copiar" type="button">
        <Copy aria-hidden="true" className="truss-icon h-3.5 w-3.5" />
      </button>
      {turn.role === "truss" ? (
        <button
          className="truss-icon-button h-7 min-h-7 w-7 border-truss-line"
          disabled={turn.streaming}
          onClick={() => onRegenerate(turn)}
          title="Analisar novamente"
          type="button"
        >
          <RefreshCw aria-hidden="true" className="truss-icon h-3.5 w-3.5" />
        </button>
      ) : (
        <button className="truss-icon-button h-7 min-h-7 w-7 border-truss-line" onClick={() => onEdit(turn)} title="Editar pergunta" type="button">
          <Edit3 aria-hidden="true" className="truss-icon h-3.5 w-3.5" />
        </button>
      )}
      {turn.role === "truss" ? (
        <>
          <button
            aria-pressed={feedback === "up"}
            className="truss-icon-button h-7 min-h-7 w-7 border-truss-line"
            data-active={feedback === "up"}
            disabled={turn.streaming}
            onClick={() => {
              setFeedback((current) => (current === "up" ? null : "up"));
              onFeedback(turn, "correct");
            }}
            title="Resultado correto"
            type="button"
          >
            <ThumbsUp aria-hidden="true" className="truss-icon h-3.5 w-3.5" />
          </button>
          <button
            aria-pressed={feedback === "down"}
            className="truss-icon-button h-7 min-h-7 w-7 border-truss-line"
            data-active={feedback === "down"}
            disabled={turn.streaming}
            onClick={() => {
              setFeedback((current) => (current === "down" ? null : "down"));
              onFeedback(turn, "incorrect");
            }}
            title="Resultado incorreto"
            type="button"
          >
            <ThumbsDown aria-hidden="true" className="truss-icon h-3.5 w-3.5" />
          </button>
        </>
      ) : null}
    </div>
  );
}

function MessageList({
  activeFinding,
  isRunning,
  messages,
  onAuditSelection,
  onConfirmFinding,
  onEditMessage,
  onExplainFinding,
  onMessageFeedback,
  onFocusFinding,
  onRegenerate,
  onRejectFinding,
  onRunSheetAudit,
  selectedCount
}: {
  activeFinding: Finding | null;
  isRunning: boolean;
  messages: ChatTurn[];
  onAuditSelection: () => void;
  onConfirmFinding: (finding: Finding) => void;
  onEditMessage: (turn: ChatTurn) => void;
  onExplainFinding: (finding: Finding) => void;
  onMessageFeedback: (turn: ChatTurn, feedback: "correct" | "incorrect") => void;
  onFocusFinding: (finding: Finding) => void;
  onRegenerate: (turn: ChatTurn) => void;
  onRejectFinding: (finding: Finding) => void;
  onRunSheetAudit: () => void;
  selectedCount: number;
}) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [pinnedToBottom, setPinnedToBottom] = useState(true);
  const [hasUnread, setHasUnread] = useState(false);

  function isNearBottom(element: HTMLDivElement) {
    return element.scrollHeight - element.scrollTop - element.clientHeight < 48;
  }

  useEffect(() => {
    const element = scrollRef.current;
    if (!element) {
      return;
    }

    // Puxar para o fim so quando o usuario ja esta la. Rolar por baixo de quem
    // subiu para ler e um dos comportamentos mais irritantes de um chat.
    if (pinnedToBottom) {
      element.scrollTo({ top: element.scrollHeight, behavior: "smooth" });
      return;
    }

    const frame = window.requestAnimationFrame(() => setHasUnread(true));
    return () => window.cancelAnimationFrame(frame);
  }, [messages, pinnedToBottom]);

  const lastTrussIndex = messages.reduce(
    (last, turn, index) => (turn.role === "truss" ? index : last),
    -1
  );

  function scrollToBottom() {
    const element = scrollRef.current;
    if (!element) {
      return;
    }

    element.scrollTo({ top: element.scrollHeight, behavior: "smooth" });
    setPinnedToBottom(true);
    setHasUnread(false);
  }

  if (messages.length === 0) {
    const suggestions: Array<{ label: string; run: () => void }> = [
      { label: "Auditar esta prancha", run: onRunSheetAudit },
      ...(activeFinding
        ? [{ label: "Explicar o achado selecionado", run: () => onExplainFinding(activeFinding) }]
        : []),
      ...(selectedCount > 0
        ? [{ label: `Auditar ${selectedCount} selecionado(s)`, run: onAuditSelection }]
        : [])
    ];

    return (
      <div className="flex min-h-0 flex-1 flex-col justify-center px-4 py-6 text-center">
        <p className="text-lg font-semibold text-truss-text">O que vamos verificar?</p>
        <p className="mt-2 text-sm leading-6 text-truss-muted">
          Use a prancha, uma seleção ou um achado como contexto técnico.
        </p>
        <div className="mt-5 grid gap-2">
          {suggestions.map((suggestion) => (
            <button
              className="truss-button h-9 justify-start px-3 text-left text-xs"
              disabled={isRunning}
              key={suggestion.label}
              onClick={suggestion.run}
              type="button"
            >
              {suggestion.label}
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      {hasUnread ? (
        <button
          className="absolute inset-x-0 top-2 z-20 mx-auto w-fit border border-truss-accent bg-truss-panel px-3 py-1 font-mono text-[10.5px] uppercase tracking-[0.06em] text-truss-accent shadow-truss-panel"
          onClick={scrollToBottom}
          type="button"
        >
          novas mensagens
        </button>
      ) : null}
      <div
        aria-live="polite"
        className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-3"
        onScroll={(event) => {
          const nearBottom = isNearBottom(event.currentTarget);
          setPinnedToBottom(nearBottom);
          if (nearBottom) {
            setHasUnread(false);
          }
        }}
        ref={scrollRef}
      >
      {messages.map((turn, index) => {
        // Confirmacoes de operacao no canvas usam tone "success". Sao registro,
        // nao conversa: viram linha fina em vez de bolha.
        const isSystemEvent = turn.role === "truss" && turn.tone === "success";

        if (isSystemEvent) {
          return (
            <p
              className="flex items-start gap-2 px-1 font-mono text-[10.5px] leading-5 text-truss-subtle"
              key={turn.id}
            >
              <span aria-hidden="true" className="mt-1.5 h-px w-3 shrink-0 bg-truss-line" />
              <span className="min-w-0 flex-1">{turn.text}</span>
            </p>
          );
        }

        return (
        <div className={`group ${turn.role === "user" ? "ml-auto max-w-[92%]" : "max-w-[96%]"}`} key={turn.id}>
          <div className="mb-1 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.06em] text-truss-subtle">
            <span>{roleLabel(turn)}</span>
            {turn.provider ? <span>{turn.provider} / {turn.model}</span> : null}
            {turn.elapsedMs ? <span>{elapsedLabel(turn.elapsedMs)}</span> : null}
          </div>
          <div
            className={`whitespace-pre-wrap border px-3 py-2 text-sm leading-6 ${
              turn.role === "user"
                ? "border-truss-accent bg-truss-accent text-truss-text"
                : turn.tone === "error"
                  ? "border-truss-danger/30 bg-truss-danger/10 text-truss-text"
                  : turn.tone === "success"
                    ? "border-truss-success/30 bg-truss-success/10 text-truss-text"
                    : "border-truss-line bg-truss-panel text-truss-text"
            }`}
          >
            {turn.contextItems && turn.contextItems.length > 0 ? (
              <div className="mb-2">
                <ContextChips contextItems={turn.contextItems} onRemoveContext={() => undefined} />
              </div>
            ) : null}
            {turn.text || (turn.streaming ? "Processando resposta..." : "")}
            {turn.streaming ? <span className="ml-1 animate-pulse text-truss-accent">|</span> : null}
          </div>
          {turn.role === "truss"
          && turn.id !== "intro"
          && index === lastTrussIndex
          && !turn.text.startsWith("Feedback registrado:") ? (
            <div className="mt-2">
              <ResponseActionPanel
                disabled={isRunning || Boolean(turn.streaming)}
                finding={activeFinding}
                onAuditSelection={onAuditSelection}
                onConfirmFinding={onConfirmFinding}
                onExplainFinding={onExplainFinding}
                onFocusFinding={onFocusFinding}
                onRejectFinding={onRejectFinding}
                onRunSheetAudit={onRunSheetAudit}
                selectedCount={selectedCount}
              />
            </div>
          ) : null}
          <MessageActions
            onEdit={onEditMessage}
            onFeedback={onMessageFeedback}
            onRegenerate={onRegenerate}
            text={turn.text}
            turn={turn}
          />
        </div>
        );
      })}
      </div>
    </div>
  );
}

export type ChatRunState = "idle" | "enviando" | "gerando" | "parado" | "erro";

const CHAT_STATE_LABEL: Record<Exclude<ChatRunState, "idle">, string> = {
  enviando: "enviando",
  gerando: "gerando resposta",
  parado: "interrompido por voce",
  erro: "falhou"
};

function ChatStatusBar({
  state,
  detail,
  onStop,
  onRetry
}: {
  state: ChatRunState;
  detail?: string;
  onStop: () => void;
  onRetry: () => void;
}) {
  if (state === "idle") {
    return null;
  }

  const isBusy = state === "enviando" || state === "gerando";
  const tone =
    state === "erro"
      ? "border-truss-danger/50 bg-truss-danger/10 text-truss-danger"
      : state === "parado"
        ? "border-truss-line bg-truss-panel text-truss-muted"
        : "border-truss-accent/40 bg-truss-accentSoft text-truss-accent";

  return (
    <div
      className={`flex items-center gap-2 border-t px-3 py-2 font-mono text-[10.5px] uppercase tracking-[0.06em] ${tone}`}
      role="status"
    >
      {isBusy ? (
        <span className="h-1.5 w-1.5 shrink-0 animate-pulse bg-current motion-reduce:animate-none" />
      ) : null}
      <span className="min-w-0 flex-1 truncate normal-case tracking-normal">
        {CHAT_STATE_LABEL[state]}
        {detail ? `: ${detail}` : ""}
      </span>
      {isBusy ? (
        <button className="truss-button h-6 min-h-6 px-2 text-[10px]" onClick={onStop} type="button">
          parar
        </button>
      ) : null}
      {state === "erro" || state === "parado" ? (
        <button className="truss-button h-6 min-h-6 px-2 text-[10px]" onClick={onRetry} type="button">
          {state === "erro" ? "tentar de novo" : "continuar"}
        </button>
      ) : null}
    </div>
  );
}

function AttachmentMenu({ hasSelection }: { hasSelection: boolean }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      <button
        aria-expanded={open}
        aria-label="Abrir anexos"
        className="truss-icon-button h-8 min-h-8 w-8"
        onClick={() => setOpen((current) => !current)}
        title="Anexos"
        type="button"
      >
        <Paperclip aria-hidden="true" className="truss-icon h-4 w-4" />
      </button>
      {open ? (
        <div className="absolute bottom-10 left-0 z-30 w-64 border border-truss-line bg-truss-panel p-2 shadow-truss-panel">
          <button className="flex w-full items-center gap-2 px-2 py-2 text-left text-sm text-truss-muted" disabled type="button">
            <FilePlus2 aria-hidden="true" className="truss-icon h-4 w-4" />
            Anexar arquivo, use a área principal
          </button>
          <button className="flex w-full items-center gap-2 px-2 py-2 text-left text-sm text-truss-muted" disabled={!hasSelection} type="button">
            <Crosshair aria-hidden="true" className="truss-icon h-4 w-4" />
            Capturar seleção atual
          </button>
          <p className="mt-2 border-t border-truss-line px-2 pt-2 font-mono text-[10px] uppercase tracking-[0.06em] text-truss-subtle">
            Upload pelo chat depende de endpoint dedicado.
          </p>
        </div>
      ) : null}
    </div>
  );
}

function CommandMenu({
  query,
  onPick
}: {
  query: string;
  onPick: (command: { mode: ChatMode; prompt: string }) => void;
}) {
  const filtered = commands.filter((item) => item.command.includes(query.toLowerCase()) || item.label.toLowerCase().includes(query.toLowerCase()));

  if (!query.startsWith("/")) {
    return null;
  }

  return (
    <div className="absolute bottom-[calc(100%+8px)] left-0 right-0 z-30 border border-truss-line bg-truss-panel p-2 shadow-truss-panel">
      {filtered.map((item) => (
        <button
          className="flex w-full items-center justify-between gap-3 px-2 py-2 text-left hover:bg-truss-panel2"
          key={item.command}
          onClick={() => onPick(item)}
          type="button"
        >
          <span className="text-sm text-truss-text">{item.label}</span>
          <span className="font-mono text-[10px] uppercase tracking-[0.06em] text-truss-subtle">{item.command}</span>
        </button>
      ))}
    </div>
  );
}

export function TrussChat({
  activeFinding,
  activeConversationId,
  activity,
  conversations,
  contextItems,
  documentName,
  isLoadingConversations,
  isRunning,
  message,
  messages,
  mode,
  onConfirmFinding,
  onEditMessage,
  onAuditSelection,
  onExplainFinding,
  onMessageFeedback,
  onFocusFinding,
  onInsertPrompt,
  onMessageChange,
  onModeChange,
  onNewConversation,
  onRegenerate,
  onRejectFinding,
  onRemoveContext,
  onRunSheetAudit,
  onSelectConversation,
  onStop,
  onSubmit,
  runState,
  runDetail,
  onRetry,
  selectedCount,
  sheetLabel
}: {
  activeFinding: Finding | null;
  activeConversationId: string;
  activity: AgentActivity;
  conversations: Conversation[];
  contextItems: ChatContextItem[];
  documentName: string;
  isLoadingConversations: boolean;
  isRunning: boolean;
  message: string;
  messages: ChatTurn[];
  mode: ChatMode;
  onConfirmFinding: (finding: Finding) => void;
  onEditMessage: (turn: ChatTurn) => void;
  onAuditSelection: () => void;
  onExplainFinding: (finding: Finding) => void;
  onMessageFeedback: (turn: ChatTurn, feedback: "correct" | "incorrect") => void;
  onFocusFinding: (finding: Finding) => void;
  onInsertPrompt: (prompt: string, mode?: ChatMode) => void;
  onMessageChange: (message: string) => void;
  onModeChange: (mode: ChatMode) => void;
  onNewConversation: () => void;
  onRegenerate: (turn: ChatTurn) => void;
  onRejectFinding: (finding: Finding) => void;
  onRemoveContext: (id: string) => void;
  onRunSheetAudit: () => void;
  onSelectConversation: (conversationId: string) => void;
  onStop: () => void;
  onSubmit: (event?: FormEvent<HTMLFormElement>) => void;
  runState: ChatRunState;
  runDetail?: string;
  onRetry: () => void;
  selectedCount: number;
  sheetLabel: string;
}) {
  const [dragging, setDragging] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const showCommands = message.startsWith("/");
  const headerContext = useMemo(() => `${documentName || "Documento"} / ${sheetLabel}`, [documentName, sheetLabel]);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }

    textarea.style.height = "0px";
    textarea.style.height = `${Math.min(180, Math.max(54, textarea.scrollHeight))}px`;
  }, [message]);

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      onSubmit();
    }

    if (event.key === "Escape" && isRunning) {
      event.preventDefault();
      onStop();
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="shrink-0 border-b border-truss-line px-3 py-2">
        <div className="flex items-center gap-2">
          <MessageSquare aria-hidden="true" className="truss-icon h-4 w-4 text-truss-info" />
          <div className="min-w-0">
            <p className="truss-mono-label">Truss Agent</p>
            <p className="mt-0.5 truncate font-mono text-[10.5px] uppercase tracking-[0.06em] text-truss-subtle">
              {headerContext}
            </p>
          </div>
          <span className={`ml-auto h-1.5 w-1.5 ${isRunning ? "bg-truss-accent" : "bg-truss-success"}`} />
        </div>
      </div>

      <ActivityPanel activity={activity} />

      <ConversationHistory
        activeConversationId={activeConversationId}
        conversations={conversations}
        isLoading={isLoadingConversations}
        onNewConversation={onNewConversation}
        onSelectConversation={onSelectConversation}
      />

      <MessageList
        activeFinding={activeFinding}
        isRunning={isRunning}
        messages={messages}
        onAuditSelection={onAuditSelection}
        onConfirmFinding={onConfirmFinding}
        onEditMessage={onEditMessage}
        onExplainFinding={onExplainFinding}
        onMessageFeedback={onMessageFeedback}
        onFocusFinding={onFocusFinding}
        onRegenerate={onRegenerate}
        onRejectFinding={onRejectFinding}
        onRunSheetAudit={onRunSheetAudit}
        selectedCount={selectedCount}
      />

      <ChatStatusBar detail={runDetail} onRetry={onRetry} onStop={onStop} state={runState} />

      <div
        className="relative border-t border-truss-line p-3"
        onDragEnter={(event) => {
          if (event.dataTransfer.types.includes("Files")) {
            setDragging(true);
          }
        }}
        onDragLeave={() => setDragging(false)}
        onDragOver={(event) => {
          if (event.dataTransfer.types.includes("Files")) {
            event.preventDefault();
          }
        }}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
        }}
      >
        {dragging ? (
          <div className="absolute inset-3 z-20 flex items-center justify-center border border-dashed border-truss-warning bg-truss-panel/95 text-center">
            <div>
              <Clipboard aria-hidden="true" className="mx-auto h-5 w-5 text-truss-warning" />
              <p className="mt-2 text-sm font-semibold text-truss-text">Upload pelo chat ainda indisponível</p>
              <p className="mt-1 text-xs text-truss-muted">Solte PDFs na área principal do projeto.</p>
            </div>
          </div>
        ) : null}

        <form className="relative border border-truss-line bg-truss-panel p-2" onSubmit={onSubmit}>
          <div className="mb-2 flex items-center justify-between gap-2 font-mono text-[10px] uppercase tracking-[0.06em] text-truss-subtle">
            <span className="truncate">{headerContext}</span>
            <span>{selectedCount > 0 ? `${selectedCount} selecionado(s)` : "sem seleção"}</span>
          </div>
          <ContextChips contextItems={contextItems} onRemoveContext={onRemoveContext} />
          <div className="relative mt-2">
            <CommandMenu
              query={message}
              onPick={(command) => {
                onModeChange(command.mode);
                onMessageChange(command.prompt);
              }}
            />
            <textarea
              aria-label="Mensagem para o Truss Agent"
              className="truss-field max-h-44 min-h-[54px] w-full resize-none px-3 py-2 text-sm leading-5"
              onChange={(event) => onMessageChange(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Pergunte algo sobre esta prancha..."
              ref={textareaRef}
              value={message}
            />
          </div>
          <div className="mt-2 flex items-center gap-2">
            <AttachmentMenu hasSelection={selectedCount > 0} />
            <select
              aria-label="Modo do Truss Agent"
              className="truss-field h-8 min-h-8 px-2 font-mono text-[10.5px] uppercase tracking-[0.06em] text-truss-subtle"
              onChange={(event) => onModeChange(event.target.value as ChatMode)}
              value={mode}
            >
              {Object.entries(modeLabels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
            <button
              className="truss-button h-8 min-h-8 px-2 font-mono text-[10.5px]"
              onClick={() => onInsertPrompt("Audite a prancha ativa.", "audit_sheet")}
              type="button"
            >
              Auditar
            </button>
            <button
              aria-label={isRunning ? "Interromper" : "Enviar"}
              className="truss-icon-button ml-auto h-8 min-h-8 w-8 border-truss-accent bg-truss-accent text-truss-text hover:bg-truss-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!isRunning && !message.trim()}
              onClick={isRunning ? onStop : undefined}
              title={isRunning ? "Interromper" : "Enviar"}
              type={isRunning ? "button" : "submit"}
            >
              {isRunning ? (
                <Square aria-hidden="true" className="truss-icon h-3.5 w-3.5" />
              ) : (
                <Send aria-hidden="true" className="truss-icon h-4 w-4" />
              )}
            </button>
          </div>
          {showCommands ? (
            <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.06em] text-truss-subtle">
              Use setas futuramente; nesta versão clique no comando desejado.
            </p>
          ) : null}
        </form>
      </div>
    </div>
  );
}
