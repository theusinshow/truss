import json
import os
import hashlib
from dataclasses import dataclass
from typing import Any, Iterator, Protocol

from truss_api.core.settings import Settings, _read_root_env


@dataclass(frozen=True)
class ProviderResponse:
    provider: str
    model: str
    answer: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float = 0.0


@dataclass(frozen=True)
class ProviderStreamDelta:
    delta: str


@dataclass(frozen=True)
class ProviderStreamResult:
    response: ProviderResponse


ProviderStreamEvent = ProviderStreamDelta | ProviderStreamResult

RESPONSE_FORMAT_INSTRUCTIONS = (
    "Formato obrigatorio da resposta, em pt-BR e em texto curto:\n"
    "Resumo\n"
    "- Sintese direta do que pode ser afirmado pelo contexto.\n\n"
    "Evidencias\n"
    "- Evidencias concretas usadas, com coordenadas em pt quando existirem. "
    "Se nao houver evidencia suficiente, escreva Indisponivel.\n\n"
    "Hipoteses e limites\n"
    "- Separe achados confirmados, rejeitados e hipoteses. Explique que severidade mede impacto, nao certeza.\n\n"
    "Proxima acao\n"
    "- Uma acao operacional curta no viewer, auditoria ou validacao humana."
)


@dataclass(frozen=True)
class ProviderStatus:
    configured_provider: str
    resolved_provider: str
    model: str
    openai_api_key_configured: bool
    openai_key_source: str | None
    openai_key_last4: str | None
    openai_key_fingerprint: str | None
    openai_org_id_configured: bool
    openai_project_id_configured: bool
    external_calls_enabled: bool
    message: str


class AIProvider(Protocol):
    provider: str
    model: str

    def respond(self, *, user_message: str, context: dict[str, object]) -> ProviderResponse:
        ...

    def stream_respond(self, *, user_message: str, context: dict[str, object]) -> Iterator[ProviderStreamEvent]:
        ...


class AIProviderConfigError(Exception):
    pass


class AIProviderUnavailableError(Exception):
    def __init__(self, message: str, *, public_message: str | None = None, provider_code: str | None = None) -> None:
        super().__init__(message)
        self.public_message = public_message or message
        self.provider_code = provider_code


class LocalHeuristicProvider:
    provider = "local"
    model = "deterministic-context-v0.1"

    def respond(self, *, user_message: str, context: dict[str, object]) -> ProviderResponse:
        findings_count = int(context.get("findings_count", 0))
        pending_count = int(context.get("pending_findings_count", 0))
        sheet_label = str(context.get("sheet_label", "folha atual"))
        memory_count = int(context.get("memory_count", 0))
        history_count = int(context.get("conversation_history_count", 0))
        technical_context = context.get("technical_context")
        technical_summary = technical_context.get("summary", {}) if isinstance(technical_context, dict) else {}
        technical_focus = technical_context.get("focus", {}) if isinstance(technical_context, dict) else {}
        selected_finding_ids = technical_focus.get("selected_finding_ids", []) if isinstance(technical_focus, dict) else []
        status_counts = technical_summary.get("status_counts", {}) if isinstance(technical_summary, dict) else {}
        findings = technical_context.get("findings", []) if isinstance(technical_context, dict) else []
        selected_findings = technical_focus.get("selected_findings", []) if isinstance(technical_focus, dict) else []
        native_text = technical_context.get("native_text", {}) if isinstance(technical_context, dict) else {}
        native_excerpt = str(native_text.get("excerpt", "") if isinstance(native_text, dict) else "")

        summary_line = (
            f"Folha {sheet_label}: {findings_count} achado(s), "
            f"{pending_count} pendente(s), {memory_count} memoria(s) ativa(s)."
        )

        evidence_lines: list[str] = []
        focus_findings = selected_findings if isinstance(selected_findings, list) and selected_findings else findings[:2] if isinstance(findings, list) else []
        for finding in focus_findings[:3]:
            if not isinstance(finding, dict):
                continue
            bbox = finding.get("bbox", {})
            if isinstance(bbox, dict):
                bbox_label = (
                    f"{round(float(bbox.get('x0', 0)))},"
                    f"{round(float(bbox.get('y0', 0)))} -> "
                    f"{round(float(bbox.get('x1', 0)))},"
                    f"{round(float(bbox.get('y1', 0)))} pt"
                )
            else:
                bbox_label = "coordenada indisponivel"
            evidence_lines.append(
                f"- {finding.get('severity', 'sem severidade')} / {finding.get('status', 'sem status')}: "
                f"{finding.get('description', 'descricao indisponivel')} ({bbox_label})."
            )

        if not evidence_lines and native_excerpt.strip():
            evidence_lines.append("- Texto nativo disponivel para consulta nesta folha.")

        if not evidence_lines:
            evidence_lines.append("- Indisponivel: execute a auditoria ou selecione um achado no viewer.")

        limits = [
            "- Severidade mede impacto, nao certeza; achados pendentes continuam como hipotese ate validacao humana."
        ]

        if isinstance(status_counts, dict) and status_counts:
            limits.append(
                f"- Status atual: {status_counts.get('pending', 0)} pendente(s), "
                f"{status_counts.get('confirmed', 0)} confirmado(s), "
                f"{status_counts.get('rejected', 0)} rejeitado(s)."
            )

        if isinstance(selected_finding_ids, list) and selected_finding_ids:
            limits.append(f"- Ha {len(selected_finding_ids)} achado(s) em foco no contexto enviado.")

        if history_count > 0:
            limits.append(f"- Considerei {history_count} turno(s) anterior(es) apenas como continuidade da conversa.")

        next_action = "Execute a auditoria da folha e valide os achados no viewer."
        if "escala" in user_message.lower():
            next_action = "Confira no texto nativo e no carimbo se a escala esta declarada; a regra local marca ausencia quando nao encontra ESCALA."

        answer = (
            "Resumo\n"
            f"- {summary_line}\n\n"
            "Evidencias\n"
            f"{chr(10).join(evidence_lines)}\n\n"
            "Hipoteses e limites\n"
            f"{chr(10).join(limits)}\n\n"
            "Proxima acao\n"
            f"- {next_action}"
        )

        return ProviderResponse(provider=self.provider, model=self.model, answer=answer)

    def stream_respond(self, *, user_message: str, context: dict[str, object]) -> Iterator[ProviderStreamEvent]:
        response = self.respond(user_message=user_message, context=context)
        for chunk in _chunk_text(response.answer):
            yield ProviderStreamDelta(chunk)
        yield ProviderStreamResult(response)


OPENAI_MODEL_PRICING_PER_MILLION: dict[str, tuple[float, float]] = {
    "gpt-5.6": (5.0, 30.0),
    "gpt-5.6-sol": (5.0, 30.0),
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


def _chunk_text(text: str, *, max_chars: int = 42) -> Iterator[str]:
    chunk = ""
    for part in text.split(" "):
        candidate = part if not chunk else f"{chunk} {part}"
        if len(candidate) > max_chars and chunk:
            yield f"{chunk} "
            chunk = part
        else:
            chunk = candidate

    if chunk:
        yield chunk


def _estimate_openai_cost(model: str, input_tokens: int | None, output_tokens: int | None) -> float:
    pricing = OPENAI_MODEL_PRICING_PER_MILLION.get(model)
    if pricing is None or input_tokens is None or output_tokens is None:
        return 0.0

    input_price, output_price = pricing
    cost = (input_tokens / 1_000_000 * input_price) + (output_tokens / 1_000_000 * output_price)
    return round(cost, 8)


def _openai_key_metadata(settings: Settings) -> tuple[str | None, str | None, str | None]:
    if settings.openai_api_key is None:
        return None, None, None

    secret = settings.openai_api_key.get_secret_value()
    root_env = _read_root_env()
    source = "settings"
    if os.getenv("TRUSS_OPENAI_API_KEY") == secret:
        source = "TRUSS_OPENAI_API_KEY"
    elif root_env.get("TRUSS_OPENAI_API_KEY") == secret:
        source = ".env:TRUSS_OPENAI_API_KEY"
    elif os.getenv("OPENAI_API_KEY") == secret:
        source = "OPENAI_API_KEY"
    elif root_env.get("OPENAI_API_KEY") == secret:
        source = ".env:OPENAI_API_KEY"

    return source, secret[-4:], hashlib.sha256(secret.encode("utf-8")).hexdigest()[:12]


def _openai_public_error(error: Exception) -> tuple[str, str | None]:
    raw_error = str(error)
    body = getattr(error, "body", None)
    status_code = getattr(error, "status_code", None)
    provider_error = body.get("error") if isinstance(body, dict) else None
    provider_code = provider_error.get("code") if isinstance(provider_error, dict) else None
    provider_type = provider_error.get("type") if isinstance(provider_error, dict) else None

    if provider_code == "insufficient_quota" or "insufficient_quota" in raw_error:
        return (
            "OpenAI sem quota disponivel para esta chave/projeto. Verifique billing, limite de uso ou troque a chave.",
            provider_code or "insufficient_quota",
        )

    if status_code == 401:
        return "Chave OpenAI invalida ou sem permissao. Atualize OPENAI_API_KEY ou TRUSS_OPENAI_API_KEY.", provider_code

    if status_code == 403:
        return f"Sem acesso ao modelo OpenAI configurado ({provider_code or provider_type or 'forbidden'}).", provider_code

    if status_code == 404 or provider_code in {"model_not_found", "model_not_available"}:
        return "Modelo OpenAI configurado indisponivel para esta chave/projeto.", provider_code

    if status_code == 429:
        return "Limite de uso da OpenAI atingido. Aguarde ou ajuste quota/billing do projeto.", provider_code

    return "Falha na chamada OpenAI. Verifique conectividade, chave, modelo e billing.", provider_code


class OpenAIProvider:
    provider = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        reasoning_effort: str,
        max_output_tokens: int,
        organization: str | None = None,
        project: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens
        self._api_key = api_key
        self._organization = organization
        self._project = project
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
            organization=settings.openai_org_id,
            project=settings.openai_project_id,
        )

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        try:
            from openai import OpenAI
        except ModuleNotFoundError as error:
            raise AIProviderUnavailableError("OpenAI SDK is not installed.") from error

        self._client = OpenAI(
            api_key=self._api_key,
            organization=self._organization,
            project=self._project,
        )
        return self._client

    def _response_input(self, *, user_message: str, context: dict[str, object]) -> list[dict[str, object]]:
        return [
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
                            "emissao de projeto e nao substitua a validacao profissional. "
                            "Use conversation_history apenas como continuidade da conversa atual; "
                            "nao trate esses turnos como evidencias tecnicas novas sem suporte no contexto da folha. "
                            "Use technical_context como fonte principal para achados, selecao ativa, texto nativo, "
                            "severidade, confianca, status humano e coordenadas PDF. Separe sempre severidade de certeza. "
                            f"{RESPONSE_FORMAT_INSTRUCTIONS}"
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
                            "Contexto estruturado da folha, com technical_context priorizado:\n"
                            f"{json.dumps(context, ensure_ascii=False, default=str)}"
                        ),
                    }
                ],
            },
        ]

    def _provider_response_from_openai(self, response: Any, *, fallback_answer: str = "") -> ProviderResponse:
        usage = _extract_value(response, "usage")
        input_tokens = _extract_value(usage, "input_tokens")
        output_tokens = _extract_value(usage, "output_tokens")
        answer = fallback_answer.strip() or _extract_output_text(response)

        return ProviderResponse(
            provider=self.provider,
            model=self.model,
            answer=answer,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=_estimate_openai_cost(self.model, input_tokens, output_tokens),
        )

    def respond(self, *, user_message: str, context: dict[str, object]) -> ProviderResponse:
        client = self._get_client()

        try:
            response = client.responses.create(
                model=self.model,
                reasoning={"effort": self.reasoning_effort},
                max_output_tokens=self.max_output_tokens,
                input=self._response_input(user_message=user_message, context=context),
            )
        except Exception as error:
            public_message, provider_code = _openai_public_error(error)
            raise AIProviderUnavailableError(
                "OpenAI request failed.",
                public_message=public_message,
                provider_code=provider_code,
            ) from error

        return self._provider_response_from_openai(response)

    def stream_respond(self, *, user_message: str, context: dict[str, object]) -> Iterator[ProviderStreamEvent]:
        client = self._get_client()
        answer_parts: list[str] = []

        try:
            with client.responses.stream(
                model=self.model,
                reasoning={"effort": self.reasoning_effort},
                max_output_tokens=self.max_output_tokens,
                input=self._response_input(user_message=user_message, context=context),
            ) as stream:
                for event in stream:
                    event_type = str(_extract_value(event, "type") or "")
                    if event_type == "response.output_text.delta":
                        delta = str(_extract_value(event, "delta") or "")
                        if delta:
                            answer_parts.append(delta)
                            yield ProviderStreamDelta(delta)

                final_response = stream.get_final_response()
        except Exception as error:
            public_message, provider_code = _openai_public_error(error)
            raise AIProviderUnavailableError(
                "OpenAI stream failed.",
                public_message=public_message,
                provider_code=provider_code,
            ) from error

        yield ProviderStreamResult(
            self._provider_response_from_openai(final_response, fallback_answer="".join(answer_parts))
        )


def build_ai_provider(settings: Settings) -> AIProvider:
    if settings.ai_provider == "local":
        return LocalHeuristicProvider()

    if settings.ai_provider == "openai":
        return OpenAIProvider.from_settings(settings)

    if settings.openai_api_key is not None:
        return OpenAIProvider.from_settings(settings)

    return LocalHeuristicProvider()


def get_ai_provider_status(settings: Settings) -> ProviderStatus:
    has_openai_key = settings.openai_api_key is not None
    key_source, key_last4, key_fingerprint = _openai_key_metadata(settings)

    if settings.ai_provider == "local":
        suffix = (
            " Chave OpenAI detectada, mas ignorada porque o provider local esta fixado."
            if has_openai_key
            else ""
        )
        return ProviderStatus(
            configured_provider=settings.ai_provider,
            resolved_provider="local",
            model=LocalHeuristicProvider.model,
            openai_api_key_configured=has_openai_key,
            openai_key_source=key_source,
            openai_key_last4=key_last4,
            openai_key_fingerprint=key_fingerprint,
            openai_org_id_configured=settings.openai_org_id is not None,
            openai_project_id_configured=settings.openai_project_id is not None,
            external_calls_enabled=False,
            message=f"Chamadas externas desativadas. Usando provider local deterministico.{suffix}",
        )

    if settings.ai_provider == "openai":
        if not has_openai_key:
            return ProviderStatus(
                configured_provider=settings.ai_provider,
                resolved_provider="unavailable",
                model=settings.openai_model,
                openai_api_key_configured=False,
                openai_key_source=None,
                openai_key_last4=None,
                openai_key_fingerprint=None,
                openai_org_id_configured=settings.openai_org_id is not None,
                openai_project_id_configured=settings.openai_project_id is not None,
                external_calls_enabled=False,
                message="TRUSS_AI_PROVIDER=openai exige OPENAI_API_KEY ou TRUSS_OPENAI_API_KEY.",
            )

        return ProviderStatus(
            configured_provider=settings.ai_provider,
            resolved_provider="openai",
            model=settings.openai_model,
            openai_api_key_configured=True,
            openai_key_source=key_source,
            openai_key_last4=key_last4,
            openai_key_fingerprint=key_fingerprint,
            openai_org_id_configured=settings.openai_org_id is not None,
            openai_project_id_configured=settings.openai_project_id is not None,
            external_calls_enabled=True,
            message="OpenAI habilitada explicitamente para o chat contextual.",
        )

    if has_openai_key:
        return ProviderStatus(
            configured_provider=settings.ai_provider,
            resolved_provider="openai",
            model=settings.openai_model,
            openai_api_key_configured=True,
            openai_key_source=key_source,
            openai_key_last4=key_last4,
            openai_key_fingerprint=key_fingerprint,
            openai_org_id_configured=settings.openai_org_id is not None,
            openai_project_id_configured=settings.openai_project_id is not None,
            external_calls_enabled=True,
            message="Modo auto resolveu para OpenAI porque uma chave foi detectada.",
        )

    return ProviderStatus(
        configured_provider=settings.ai_provider,
        resolved_provider="local",
        model=LocalHeuristicProvider.model,
        openai_api_key_configured=False,
        openai_key_source=None,
        openai_key_last4=None,
        openai_key_fingerprint=None,
        openai_org_id_configured=settings.openai_org_id is not None,
        openai_project_id_configured=settings.openai_project_id is not None,
        external_calls_enabled=False,
        message="Modo auto sem chave OpenAI: usando provider local deterministico.",
    )
