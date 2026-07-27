import json
from dataclasses import dataclass
from typing import Any, Protocol

from truss_api.core.settings import Settings


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


class AIProviderConfigError(Exception):
    pass


class AIProviderUnavailableError(Exception):
    pass


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


OPENAI_MODEL_PRICING_PER_MILLION: dict[str, tuple[float, float]] = {
    "gpt-5.6": (5.0, 30.0),
    "gpt-5.6-sol": (5.0, 30.0),
    "gpt-5.6-terra": (2.5, 15.0),
    "gpt-5.6-luna": (1.0, 6.0),
}


def _extract_value(source: Any, key: str) -> Any:
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)


def _extract_output_text(response: Any) -> str:
    output_text = _extract_value(response, "output_text")
    if output_text:
        return str(output_text).strip()

    output = _extract_value(response, "output") or []
    for item in output:
        content = _extract_value(item, "content") or []
        for part in content:
            if _extract_value(part, "type") == "output_text":
                text = _extract_value(part, "text")
                if text:
                    return str(text).strip()

    raise AIProviderUnavailableError("OpenAI response did not include output text.")


def _estimate_openai_cost(model: str, input_tokens: int | None, output_tokens: int | None) -> float:
    pricing = OPENAI_MODEL_PRICING_PER_MILLION.get(model)
    if pricing is None or input_tokens is None or output_tokens is None:
        return 0.0

    input_price, output_price = pricing
    cost = (input_tokens / 1_000_000 * input_price) + (output_tokens / 1_000_000 * output_price)
    return round(cost, 8)


class OpenAIProvider:
    provider = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        reasoning_effort: str,
        max_output_tokens: int,
        client: Any | None = None,
    ) -> None:
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens
        self._api_key = api_key
        self._client = client

    @classmethod
    def from_settings(cls, settings: Settings) -> "OpenAIProvider":
        if settings.openai_api_key is None:
            raise AIProviderConfigError("OpenAI API key is not configured.")

        return cls(
            api_key=settings.openai_api_key.get_secret_value(),
            model=settings.openai_model,
            reasoning_effort=settings.openai_reasoning_effort,
            max_output_tokens=settings.openai_max_output_tokens,
        )

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        try:
            from openai import OpenAI
        except ModuleNotFoundError as error:
            raise AIProviderUnavailableError("OpenAI SDK is not installed.") from error

        self._client = OpenAI(api_key=self._api_key)
        return self._client

    def respond(self, *, user_message: str, context: dict[str, object]) -> ProviderResponse:
        client = self._get_client()

        try:
            response = client.responses.create(
                model=self.model,
                reasoning={"effort": self.reasoning_effort},
                max_output_tokens=self.max_output_tokens,
                input=[
                    {
                        "role": "developer",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    "Voce e o Truss Agent, assistente tecnico de revisao grafica "
                                    "de projetos estruturais em PDF. Responda em pt-BR, seja direto "
                                    "e use apenas o contexto fornecido. Quando uma informacao nao "
                                    "estiver disponivel, diga que esta indisponivel. Nao aprove "
                                    "emissao de projeto e nao substitua a validacao profissional."
                                ),
                            }
                        ],
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    f"Pergunta do usuario: {user_message}\n\n"
                                    "Contexto estruturado da folha:\n"
                                    f"{json.dumps(context, ensure_ascii=False, default=str)}"
                                ),
                            }
                        ],
                    },
                ],
            )
        except Exception as error:
            raise AIProviderUnavailableError("OpenAI request failed.") from error

        usage = _extract_value(response, "usage")
        input_tokens = _extract_value(usage, "input_tokens")
        output_tokens = _extract_value(usage, "output_tokens")

        return ProviderResponse(
            provider=self.provider,
            model=self.model,
            answer=_extract_output_text(response),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=_estimate_openai_cost(self.model, input_tokens, output_tokens),
        )


def build_ai_provider(settings: Settings) -> AIProvider:
    if settings.ai_provider == "local":
        return LocalHeuristicProvider()

    if settings.ai_provider == "openai":
        return OpenAIProvider.from_settings(settings)

    if settings.openai_api_key is not None:
        return OpenAIProvider.from_settings(settings)

    return LocalHeuristicProvider()
