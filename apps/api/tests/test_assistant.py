import json
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import fitz
import pytest
from fastapi.testclient import TestClient

from truss_api.ai.provider import (
    AIProviderUnavailableError,
    OpenAIProvider,
    ProviderResponse,
    ProviderStreamDelta,
    ProviderStreamResult,
    build_ai_provider,
    get_ai_provider_status,
)
from truss_api.assistant import routes as assistant_routes
from truss_api.core import settings as settings_module
from truss_api.core.settings import Settings, get_settings
from truss_api.db.schema import initialize_database
from truss_api.main import app
from truss_api.projects import repository
from truss_api.projects.models import ProjectCreate, RevisionCreate
from tests.factories import make_structural_pdf_bytes


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    resolved = Settings(data_dir=tmp_path / "data", ai_provider="local", openai_api_key=None)
    initialize_database(resolved)
    return resolved


@pytest.fixture()
def client(settings: Settings) -> Iterator[TestClient]:
    app.dependency_overrides[get_settings] = lambda: settings

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def make_pdf_bytes() -> bytes:
    document = fitz.open()
    page = document.new_page(width=842, height=595)
    page.insert_text((72, 72), "FORMA PAVIMENTO 1")
    buffer = BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def create_sheet(client: TestClient, settings: Settings) -> str:
    project = repository.create_project(ProjectCreate(name="Assistant Project"), settings)
    revision = repository.create_revision(
        str(project["id"]),
        RevisionCreate(notes="Assistant revision"),
        settings,
    )
    response = client.post(
        f"/projects/{project['id']}/revisions/{revision['id']}/documents",
        files={"file": ("forma.pdf", make_structural_pdf_bytes(), "application/pdf")},
    )
    # Pagina 1: carimbo declara PLANTA DE FORMAS e a folha nao declara escala,
    # entao a auditoria tem uma regra para apontar e o chat tem contexto real.
    return str(response.json()["sheets"][1]["id"])


def test_sheet_chat_uses_local_provider_and_records_usage(
    client: TestClient,
    settings: Settings,
) -> None:
    sheet_id = create_sheet(client, settings)
    client.post(f"/sheets/{sheet_id}/audit-runs")

    response = client.post(f"/sheets/{sheet_id}/chat", json={"message": "E a escala?"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "local"
    assert "escala" in payload["answer"].lower()
    assert "Resumo" in payload["answer"]
    assert "Evidencias" in payload["answer"]
    assert "Hipoteses e limites" in payload["answer"]
    assert "Proxima acao" in payload["answer"]

    usage = client.get("/usage").json()
    assert usage[0]["provider"] == "local"
    assert usage[0]["estimated_cost_usd"] == 0

    filtered = client.get("/usage", params={"sheet_id": sheet_id}).json()
    assert len(filtered) == len(usage)
    assert client.get("/usage", params={"sheet_id": "outra-folha"}).json() == []


def test_sheet_chat_passes_ui_context_items_to_provider(
    client: TestClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sheet_id = create_sheet(client, settings)
    captured_context: dict[str, object] = {}

    class CapturingProvider:
        provider = "test"
        model = "context-capture"

        def respond(self, *, user_message: str, context: dict[str, object]) -> ProviderResponse:
            captured_context.update(context)
            return ProviderResponse(provider=self.provider, model=self.model, answer=user_message)

    monkeypatch.setattr(assistant_routes, "build_ai_provider", lambda _: CapturingProvider())

    response = client.post(
        f"/sheets/{sheet_id}/chat",
        json={
            "message": "Verifique a seleção.",
            "context_items": [
                {
                    "id": "selection:findings",
                    "kind": "selection",
                    "label": "1 selecionado",
                    "value": "Texto de escala ausente",
                    "metadata": {"count": 1},
                }
            ],
        },
    )

    assert response.status_code == 200
    assert captured_context["ui_context_items"] == [
        {
            "id": "selection:findings",
            "kind": "selection",
            "label": "1 selecionado",
            "value": "Texto de escala ausente",
            "metadata": {"count": 1},
        }
    ]


def test_sheet_chat_builds_technical_context_for_provider(
    client: TestClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sheet_id = create_sheet(client, settings)
    audit_response = client.post(f"/sheets/{sheet_id}/audit-runs")
    finding = audit_response.json()["findings"][0]
    captured_context: dict[str, object] = {}

    class CapturingProvider:
        provider = "test"
        model = "technical-context-capture"

        def respond(self, *, user_message: str, context: dict[str, object]) -> ProviderResponse:
            captured_context.update(context)
            return ProviderResponse(provider=self.provider, model=self.model, answer=user_message)

    monkeypatch.setattr(assistant_routes, "build_ai_provider", lambda _: CapturingProvider())

    response = client.post(
        f"/sheets/{sheet_id}/chat",
        json={
            "message": "Explique o achado selecionado.",
            "context_items": [
                {
                    "id": f"finding:{finding['id']}",
                    "kind": "finding",
                    "label": "Achado 1",
                    "value": finding["description"],
                    "metadata": {"findingId": finding["id"], "severity": finding["severity"]},
                }
            ],
        },
    )

    assert response.status_code == 200
    technical_context = captured_context["technical_context"]
    assert technical_context["answer_policy"]["severity_is_not_certainty"] is True
    assert technical_context["answer_policy"]["must_not_approve_issue"] is True
    assert technical_context["sheet"]["label"] == "Folha 02"
    assert technical_context["summary"]["total_findings"] >= 1
    assert technical_context["focus"]["selected_finding_ids"] == [finding["id"]]
    assert technical_context["findings"][0]["bbox"]["x0"] <= technical_context["findings"][0]["bbox"]["x1"]
    assert "certainty" in technical_context["findings"][0]
    assert captured_context["technical_context_version"] == "sheet-chat-v0.2"


def test_sheet_chat_creates_conversation_and_lists_messages(client: TestClient, settings: Settings) -> None:
    sheet_id = create_sheet(client, settings)

    first_response = client.post(
        f"/sheets/{sheet_id}/chat",
        json={
            "message": "Verifique os textos.",
            "context_items": [
                {
                    "id": "sheet:test",
                    "kind": "sheet",
                    "label": "Folha 01",
                    "value": "842 x 595 pt",
                    "metadata": {"page": 1},
                }
            ],
        },
    )

    assert first_response.status_code == 200
    first_payload = first_response.json()
    conversation_id = first_payload["conversation_id"]
    assert first_payload["user_message_id"]
    assert first_payload["assistant_message_id"]

    second_response = client.post(
        f"/sheets/{sheet_id}/chat",
        json={
            "message": "E a escala?",
            "conversation_id": conversation_id,
            "context_items": [],
        },
    )

    assert second_response.status_code == 200
    assert second_response.json()["conversation_id"] == conversation_id

    conversations = client.get(f"/sheets/{sheet_id}/conversations").json()
    assert conversations[0]["id"] == conversation_id
    assert conversations[0]["title"] == "Verifique os textos."

    messages = client.get(f"/chat/conversations/{conversation_id}/messages").json()
    assert [message["role"] for message in messages] == ["user", "assistant", "user", "assistant"]
    assert messages[0]["context_items"] == [
        {
            "id": "sheet:test",
            "kind": "sheet",
            "label": "Folha 01",
            "value": "842 x 595 pt",
            "metadata": {"page": 1},
        }
    ]
    assert messages[1]["provider"] == "local"


def test_sheet_chat_passes_conversation_history_to_provider(
    client: TestClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sheet_id = create_sheet(client, settings)
    first_response = client.post(f"/sheets/{sheet_id}/chat", json={"message": "Primeira pergunta."})
    conversation_id = first_response.json()["conversation_id"]
    captured_context: dict[str, object] = {}

    class CapturingProvider:
        provider = "test"
        model = "history-capture"

        def respond(self, *, user_message: str, context: dict[str, object]) -> ProviderResponse:
            captured_context.update(context)
            return ProviderResponse(provider=self.provider, model=self.model, answer=user_message)

    monkeypatch.setattr(assistant_routes, "build_ai_provider", lambda _: CapturingProvider())

    response = client.post(
        f"/sheets/{sheet_id}/chat",
        json={"message": "Continue.", "conversation_id": conversation_id},
    )

    assert response.status_code == 200
    history = captured_context["conversation_history"]
    assert captured_context["conversation_history_count"] == 2
    assert [message["role"] for message in history] == ["user", "assistant"]
    assert history[0]["content"] == "Primeira pergunta."
    assert history[1]["provider"] == "local"


def test_sheet_chat_streams_and_persists_turn(client: TestClient, settings: Settings) -> None:
    sheet_id = create_sheet(client, settings)

    with client.stream(
        "POST",
        f"/sheets/{sheet_id}/chat/stream",
        json={
            "message": "E a escala?",
            "context_items": [
                {
                    "id": "sheet:test",
                    "kind": "sheet",
                    "label": "Folha 01",
                    "value": "842 x 595 pt",
                }
            ],
        },
    ) as response:
        assert response.status_code == 200
        events = [json.loads(line) for line in response.iter_lines() if line]

    assert events[0] == {"event": "meta", "provider": "local", "model": "deterministic-context-v0.1"}
    assert any(event["event"] == "delta" and event["delta"] for event in events)
    done = events[-1]
    assert done["event"] == "done"
    assert done["conversation_id"]
    assert done["assistant_message_id"]
    assert "escala" in done["answer"].lower()

    messages = client.get(f"/chat/conversations/{done['conversation_id']}/messages").json()
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[0]["context_items"][0]["id"] == "sheet:test"
    assert messages[1]["id"] == done["assistant_message_id"]


def test_sheet_chat_stream_passes_conversation_history_to_provider(
    client: TestClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sheet_id = create_sheet(client, settings)
    first_response = client.post(f"/sheets/{sheet_id}/chat", json={"message": "Memorize este contexto."})
    conversation_id = first_response.json()["conversation_id"]
    captured_context: dict[str, object] = {}

    class CapturingStreamProvider:
        provider = "test"
        model = "stream-history-capture"

        def stream_respond(self, *, user_message: str, context: dict[str, object]) -> Iterator[object]:
            captured_context.update(context)
            yield ProviderStreamDelta("ok")
            yield ProviderStreamResult(ProviderResponse(provider=self.provider, model=self.model, answer="ok"))

    monkeypatch.setattr(assistant_routes, "build_ai_provider", lambda _: CapturingStreamProvider())

    with client.stream(
        "POST",
        f"/sheets/{sheet_id}/chat/stream",
        json={"message": "Continue no stream.", "conversation_id": conversation_id},
    ) as response:
        events = [json.loads(line) for line in response.iter_lines() if line]

    assert response.status_code == 200
    assert events[-1]["event"] == "done"
    assert captured_context["conversation_history_count"] == 2
    assert captured_context["conversation_history"][0]["content"] == "Memorize este contexto."


def test_message_feedback_is_persisted(client: TestClient, settings: Settings) -> None:
    sheet_id = create_sheet(client, settings)
    chat_response = client.post(f"/sheets/{sheet_id}/chat", json={"message": "Resuma a folha."}).json()

    response = client.post(
        f"/chat/messages/{chat_response['assistant_message_id']}/feedback",
        json={"feedback": "correct", "reason": "Resposta coerente."},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["message_id"] == chat_response["assistant_message_id"]
    assert payload["feedback"] == "correct"
    assert payload["reason"] == "Resposta coerente."


def test_ai_status_reports_local_provider_even_when_key_exists(tmp_path: Path) -> None:
    isolated_settings = Settings(
        data_dir=tmp_path / "data",
        ai_provider="local",
        openai_api_key="sk-test",
    )
    app.dependency_overrides[get_settings] = lambda: isolated_settings

    with TestClient(app) as test_client:
        response = test_client.get("/ai/status")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured_provider"] == "local"
    assert payload["resolved_provider"] == "local"
    assert payload["openai_api_key_configured"] is True
    assert payload["external_calls_enabled"] is False
    assert "ignorada" in payload["message"]


def test_auto_provider_uses_local_when_openai_key_is_missing(tmp_path: Path) -> None:
    isolated_settings = Settings(
        data_dir=tmp_path / "data",
        ai_provider="auto",
        openai_api_key=None,
    )

    provider = build_ai_provider(isolated_settings)

    assert provider.provider == "local"


def test_ai_status_reports_auto_openai_when_key_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRUSS_OPENAI_API_KEY", "sk-test-1234")
    isolated_settings = Settings(
        data_dir=tmp_path / "data",
        ai_provider="auto",
        openai_api_key="sk-test-1234",
        openai_org_id="org-test",
        openai_project_id="proj-test",
    )
    app.dependency_overrides[get_settings] = lambda: isolated_settings

    with TestClient(app) as test_client:
        response = test_client.get("/ai/status")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured_provider"] == "auto"
    assert payload["resolved_provider"] == "openai"
    assert payload["model"] == "gpt-5.6-sol"
    assert payload["external_calls_enabled"] is True
    assert payload["openai_key_source"] == "TRUSS_OPENAI_API_KEY"
    assert payload["openai_key_last4"] == "1234"
    assert payload["openai_key_fingerprint"]
    assert payload["openai_org_id_configured"] is True
    assert payload["openai_project_id_configured"] is True


def test_root_truss_openai_key_overrides_ambient_openai_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings_module, "REPO_ROOT", tmp_path)
    monkeypatch.delenv("TRUSS_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-old-gP8A")
    (tmp_path / ".env").write_text("TRUSS_OPENAI_API_KEY=sk-new-P7EA\n", encoding="utf-8")

    isolated_settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        ai_provider="auto",
    )
    status = get_ai_provider_status(isolated_settings)

    assert isolated_settings.openai_api_key is not None
    assert isolated_settings.openai_api_key.get_secret_value() == "sk-new-P7EA"
    assert status.openai_key_source == ".env:TRUSS_OPENAI_API_KEY"
    assert status.openai_key_last4 == "P7EA"


def test_openai_provider_keeps_org_and_project_from_settings(tmp_path: Path) -> None:
    isolated_settings = Settings(
        data_dir=tmp_path / "data",
        ai_provider="openai",
        openai_api_key="sk-test",
        openai_org_id="org-test",
        openai_project_id="proj-test",
    )

    provider = OpenAIProvider.from_settings(isolated_settings)

    assert provider._organization == "org-test"
    assert provider._project == "proj-test"


def test_openai_provider_uses_responses_api_and_estimates_cost() -> None:
    class FakeResponses:
        def __init__(self) -> None:
            self.request: dict[str, object] | None = None

        def create(self, **kwargs: object) -> SimpleNamespace:
            self.request = kwargs
            return SimpleNamespace(
                output_text="A escala esta indicada como 1:50 no texto nativo.",
                usage=SimpleNamespace(input_tokens=100, output_tokens=10),
            )

    class FakeClient:
        def __init__(self) -> None:
            self.responses = FakeResponses()

    fake_client = FakeClient()
    provider = OpenAIProvider(
        api_key="sk-test",
        model="gpt-5.6-sol",
        reasoning_effort="low",
        max_output_tokens=400,
        client=fake_client,
    )

    response = provider.respond(
        user_message="Qual e a escala?",
        context={
            "sheet_label": "Folha 1",
            "native_text_excerpt": "FORMA PAVIMENTO 1\nESCALA 1:50",
            "recent_findings": [],
            "memories": [],
        },
    )

    assert response.provider == "openai"
    assert response.model == "gpt-5.6-sol"
    assert response.input_tokens == 100
    assert response.output_tokens == 10
    assert response.estimated_cost_usd == 0.0006
    assert fake_client.responses.request is not None
    assert fake_client.responses.request["model"] == "gpt-5.6-sol"
    assert fake_client.responses.request["reasoning"] == {"effort": "low"}
    assert fake_client.responses.request["max_output_tokens"] == 400
    developer_text = fake_client.responses.request["input"][0]["content"][0]["text"]
    assert "Formato obrigatorio da resposta" in developer_text
    assert "Resumo" in developer_text
    assert "Evidencias" in developer_text
    assert "Hipoteses e limites" in developer_text
    assert "Proxima acao" in developer_text
    assert "Indisponivel" in developer_text


def test_openai_provider_surfaces_insufficient_quota() -> None:
    class FakeResponses:
        def create(self, **kwargs: object) -> SimpleNamespace:
            raise RuntimeErrorWithBody(
                body={
                    "error": {
                        "message": "You exceeded your current quota.",
                        "type": "insufficient_quota",
                        "code": "insufficient_quota",
                    }
                },
                status_code=429,
            )

    class FakeClient:
        def __init__(self) -> None:
            self.responses = FakeResponses()

    class RuntimeErrorWithBody(RuntimeError):
        def __init__(self, *, body: dict[str, object], status_code: int) -> None:
            super().__init__("simulated OpenAI error")
            self.body = body
            self.status_code = status_code

    provider = OpenAIProvider(
        api_key="sk-test",
        model="gpt-5.6-sol",
        reasoning_effort="low",
        max_output_tokens=400,
        client=FakeClient(),
    )

    with pytest.raises(AIProviderUnavailableError) as error:
        provider.respond(user_message="Teste", context={"sheet_label": "Folha 1"})

    assert error.value.provider_code == "insufficient_quota"
    assert "quota" in error.value.public_message.lower()


def test_memory_crud(client: TestClient) -> None:
    create_response = client.post(
        "/memories",
        json={"scope": "global", "key": "escala", "text": "Sempre cobrar escala grafica."},
    )

    assert create_response.status_code == 201
    memory_id = create_response.json()["id"]
    assert client.get("/memories").json()[0]["key"] == "escala"

    delete_response = client.delete(f"/memories/{memory_id}")

    assert delete_response.status_code == 204
    assert client.get("/memories").json() == []
