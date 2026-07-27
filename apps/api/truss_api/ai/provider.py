from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProviderResponse:
    provider: str
    model: str
    answer: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float = 0.0


class AIProvider(Protocol):
    provider: str
    model: str

    def respond(self, *, user_message: str, context: dict[str, object]) -> ProviderResponse:
        ...


class LocalHeuristicProvider:
    provider = "local"
    model = "deterministic-context-v0.1"

    def respond(self, *, user_message: str, context: dict[str, object]) -> ProviderResponse:
        findings_count = int(context.get("findings_count", 0))
        pending_count = int(context.get("pending_findings_count", 0))
        sheet_label = str(context.get("sheet_label", "folha atual"))
        memory_count = int(context.get("memory_count", 0))

        answer = (
            f"Contexto da {sheet_label}: existem {findings_count} achados registrados, "
            f"{pending_count} pendentes para validacao humana e {memory_count} memorias ativas. "
            "Nesta versao local eu respondo com base nos dados estruturados ja extraidos; "
            "para duvidas tecnicas finas, execute a auditoria da folha e valide os achados no viewer."
        )

        if "escala" in user_message.lower():
            answer += " A regra deterministica atual marca falta de escala quando o texto nativo nao contem 'ESCALA'."

        return ProviderResponse(provider=self.provider, model=self.model, answer=answer)
