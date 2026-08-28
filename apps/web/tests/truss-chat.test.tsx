import { fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { describe, expect, it, vi } from "vitest";

import { TrussChat } from "@/components/truss-chat";
import { Finding } from "@/lib/projects-api";

const finding: Finding = {
  id: "finding-1",
  audit_run_id: "audit-1",
  sheet_id: "sheet-1",
  document_id: "document-1",
  project_id: "project-1",
  revision_id: "revision-1",
  category: "text",
  type: "attention",
  description: "Texto de escala ausente na prancha.",
  severity: "medium",
  confidence: 0.68,
  bbox: { x0: 10, y0: 20, x1: 120, y1: 80 },
  evidence: ["Texto nativo sem ESCALA."],
  origin: "ai",
  status: "pending",
  rejection_reason: null,
  created_at: "2026-07-29T12:00:00Z",
  updated_at: "2026-07-29T12:00:00Z"
};

function renderChat(overrides: Partial<Parameters<typeof TrussChat>[0]> = {}) {
  Element.prototype.scrollTo = vi.fn();

  const props: Parameters<typeof TrussChat>[0] = {
    activeFinding: finding,
    activeConversationId: "",
    activity: {
      state: "idle",
      title: "Pronto",
      steps: []
    },
    conversations: [],
    contextItems: [
      {
        id: "sheet:sheet-1",
        kind: "sheet",
        label: "Folha 01",
        value: "842 x 595 pt"
      },
      {
        id: "selection:findings",
        kind: "selection",
        label: "1 selecionado",
        value: "Texto de escala ausente"
      }
    ],
    documentName: "forma.pdf",
    isLoadingConversations: false,
    isRunning: false,
    message: "",
    messages: [],
    mode: "ask",
    onAuditSelection: vi.fn(),
    onConfirmFinding: vi.fn(),
    onEditMessage: vi.fn(),
    onExplainFinding: vi.fn(),
    onFocusFinding: vi.fn(),
    onInsertPrompt: vi.fn(),
    onMessageFeedback: vi.fn(),
    onMessageChange: vi.fn(),
    onModeChange: vi.fn(),
    onNewConversation: vi.fn(),
    onRegenerate: vi.fn(),
    onRejectFinding: vi.fn(),
    onRemoveContext: vi.fn(),
    onRunSheetAudit: vi.fn(),
    onSelectConversation: vi.fn(),
    onRetry: vi.fn(),
    onStop: vi.fn(),
    runState: "idle" as const,
    usage: null,
    onSubmit: vi.fn(),
    selectedCount: 1,
    sheetLabel: "Folha 01",
    ...overrides
  };

  render(<TrussChat {...props} />);
  return props;
}

describe("TrussChat", () => {
  it("renders explicit context chips and removes removable context", () => {
    const props = renderChat();

    expect(screen.getByText("Folha 01")).toBeInTheDocument();
    expect(screen.getByText("1 selecionado")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Remover contexto 1 selecionado"));

    expect(props.onRemoveContext).toHaveBeenCalledWith("selection:findings");
  });

  it("submits with Enter and keeps Shift Enter for multiline editing", () => {
    const props = renderChat({ message: "Verifique a seleção" });
    const textarea = screen.getByLabelText("Mensagem para o Truss Agent");

    fireEvent.keyDown(textarea, { key: "Enter" });
    expect(props.onSubmit).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true });
    expect(props.onSubmit).toHaveBeenCalledTimes(1);
  });

  it("exposes command menu entries without executing fake tools", () => {
    const props = renderChat({ message: "/aud" });

    fireEvent.click(screen.getAllByText("Auditar prancha")[0]);

    expect(props.onModeChange).toHaveBeenCalledWith("audit_sheet");
    expect(props.onMessageChange).toHaveBeenCalledWith("Audite a prancha ativa.");
  });

  it("shows Stop while running", () => {
    const props = renderChat({ isRunning: true, message: "Pergunta em andamento" });

    fireEvent.click(screen.getByLabelText("Interromper"));

    expect(props.onStop).toHaveBeenCalled();
  });

  it("renders saved conversations and switches history inline", () => {
    const props = renderChat({
      activeConversationId: "conversation-2",
      conversations: [
        {
          id: "conversation-1",
          sheet_id: "sheet-1",
          project_id: "project-1",
          revision_id: "revision-1",
          title: "Verifique os textos.",
          status: "active",
          created_at: "2026-07-29T12:00:00Z",
          updated_at: "2026-07-29T12:01:00Z"
        },
        {
          id: "conversation-2",
          sheet_id: "sheet-1",
          project_id: "project-1",
          revision_id: "revision-1",
          title: "E a escala?",
          status: "active",
          created_at: "2026-07-29T12:02:00Z",
          updated_at: "2026-07-29T12:03:00Z"
        }
      ]
    });

    fireEvent.click(screen.getByText("Verifique os textos."));
    fireEvent.click(screen.getByText("Nova"));

    expect(props.onSelectConversation).toHaveBeenCalledWith("conversation-1");
    expect(props.onNewConversation).toHaveBeenCalled();
    expect(screen.getByText("ativa")).toBeInTheDocument();
  });

  it("exposes concrete response actions for sheet, selection and active finding", () => {
    const props = renderChat({
      messages: [
        {
          id: "assistant-1",
          role: "truss",
          text: "Resumo\nHá um ponto de atenção na escala."
        }
      ]
    });

    fireEvent.click(screen.getByRole("button", { name: "Auditar prancha" }));
    fireEvent.click(screen.getByRole("button", { name: "Auditar seleção" }));
    fireEvent.click(screen.getByRole("button", { name: "Localizar" }));
    fireEvent.click(screen.getByRole("button", { name: "Explicar" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirmar" }));
    fireEvent.click(screen.getByRole("button", { name: "Rejeitar" }));

    expect(props.onRunSheetAudit).toHaveBeenCalledTimes(1);
    expect(props.onAuditSelection).toHaveBeenCalledTimes(1);
    expect(props.onFocusFinding).toHaveBeenCalledWith(finding);
    expect(props.onExplainFinding).toHaveBeenCalledWith(finding);
    expect(props.onConfirmFinding).toHaveBeenCalledWith(finding);
    expect(props.onRejectFinding).toHaveBeenCalledWith(finding);
  });
});
