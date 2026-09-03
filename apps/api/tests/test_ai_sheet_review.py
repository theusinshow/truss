from collections.abc import Iterator
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace

import fitz
import pytest
from fastapi.testclient import TestClient

from truss_api.ai.provider import AIProviderUnavailableError, OpenAIProvider
from truss_api.core.settings import Settings, get_settings
from truss_api.db.connection import transaction
from truss_api.db.schema import initialize_database
from truss_api.main import app
from truss_api.recovery.errors import TrussError
from truss_api.vision.models import (
    NormalizedBoundingBox,
    SheetReviewAnalysis,
    SheetReviewFinding,
    SheetReviewImage,
    SheetReviewInput,
    SheetReviewProviderResponse,
)
from truss_api.vision.sheet_review import run_ai_sheet_review


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    resolved = Settings(
        data_dir=tmp_path / "data",
        ai_provider="local",
        vision_enabled=True,
        vision_budget_usd_per_revision=1.0,
        vision_max_calls_per_revision=20,
    )
    initialize_database(resolved)
    return resolved


@pytest.fixture()
def client(settings: Settings) -> Iterator[TestClient]:
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _pdf() -> bytes:
    document = fitz.open()
    page = document.new_page(width=600, height=800)
    page.insert_text((40, 60), "PLANTA DE FORMAS")
    page.insert_text((40, 90), "ESCALA 1:50")
    page.insert_text((420, 760), "EST-001")
    buffer = BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def _sheet(client: TestClient) -> str:
    project = client.post("/projects", json={"name": "AI review fixture"}).json()
    revision = client.post(
        f"/projects/{project['id']}/revisions", json={"notes": "R01"}
    ).json()
    document = client.post(
        f"/projects/{project['id']}/revisions/{revision['id']}/documents",
        files={"file": ("review.pdf", _pdf(), "application/pdf")},
    ).json()
    return str(document["sheets"][0]["id"])


def test_ai_sheet_review_uses_global_and_tiles_and_caches_result(
    client: TestClient,
    settings: Settings,
) -> None:
    sheet_id = _sheet(client)

    class FakeProvider:
        provider = "openai"
        model = "fake-sheet-review-v1"
        calls = 0
        review: SheetReviewInput | None = None

        def analyze_sheet(self, *, review: SheetReviewInput) -> SheetReviewProviderResponse:
            self.calls += 1
            self.review = review
            return SheetReviewProviderResponse(
                provider=self.provider,
                model=self.model,
                analysis=SheetReviewAnalysis(
                    sheet_id=review.sheet_id,
                    summary="A prancha foi revisada integralmente.",
                    findings=[
                        SheetReviewFinding(
                            category="identification",
                            type="attention",
                            severity="medium",
                            confidence=0.87,
                            description="Identificacao exige conferencia no detalhe indicado.",
                            scope="localized",
                            bbox=NormalizedBoundingBox(x0=100, y0=200, x1=300, y1=400),
                            evidence=["Texto e chamada ocupam a mesma regiao."],
                        )
                    ],
                ),
                input_tokens=900,
                output_tokens=120,
                estimated_cost_usd=0.0081,
            )

    provider = FakeProvider()
    first = run_ai_sheet_review(sheet_id, settings, provider=provider)
    replay = run_ai_sheet_review(sheet_id, settings, provider=provider)

    assert provider.calls == 1
    assert provider.review is not None
    assert len(provider.review.images) == 5
    assert provider.review.images[0].role == "global"
    assert all(image.image_bytes.startswith(b"\x89PNG") for image in provider.review.images)
    assert replay["id"] == first["id"]
    assert first["mode"] == "ai_review"
    assert first["pipeline_version"] == "ai-sheet-review-v0.1"
    finding = first["findings"][0]
    assert finding["source_layer"] == "ai_review"
    assert finding["rule_scope"] == "localized"
    assert finding["bbox"] == {"x0": 60.0, "y0": 160.0, "x1": 180.0, "y1": 320.0}
    assert any(item.startswith("ia: provider=openai") for item in finding["evidence"])

    with transaction(settings) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM ai_usage_events WHERE operation = 'ai.sheet_review'"
        ).fetchone()[0] == 1


def test_ai_sheet_review_budget_blocks_before_render_or_provider(
    client: TestClient,
    settings: Settings,
) -> None:
    sheet_id = _sheet(client)
    settings.vision_budget_usd_per_revision = 0.04
    settings.vision_cost_reserve_usd_per_call = 0.05

    class NeverCalledProvider:
        provider = "openai"
        model = "fake-sheet-review-v1"
        calls = 0

        def analyze_sheet(self, *, review: SheetReviewInput) -> SheetReviewProviderResponse:
            self.calls += 1
            raise AssertionError("provider must not run after the budget gate")

    provider = NeverCalledProvider()
    with pytest.raises(TrussError) as captured:
        run_ai_sheet_review(sheet_id, settings, provider=provider)

    assert captured.value.public.code == "AI_BUDGET_EXHAUSTED"
    assert provider.calls == 0


def test_ai_sheet_review_records_failed_external_attempt(
    client: TestClient,
    settings: Settings,
) -> None:
    sheet_id = _sheet(client)

    class FailingProvider:
        provider = "openai"
        model = "fake-sheet-review-v1"

        def analyze_sheet(self, *, review: SheetReviewInput) -> SheetReviewProviderResponse:
            raise AIProviderUnavailableError(
                "truncated response",
                provider_code="sheet_review_schema_invalid",
                provider=self.provider,
                model=self.model,
                input_tokens=1400,
                output_tokens=1200,
                estimated_cost_usd=0.0296,
            )

    with pytest.raises(AIProviderUnavailableError):
        run_ai_sheet_review(sheet_id, settings, provider=FailingProvider())

    with transaction(settings) as connection:
        usage = connection.execute(
            """
            SELECT provider, model, input_tokens, output_tokens, estimated_cost_usd
            FROM ai_usage_events
            WHERE operation = 'ai.sheet_review'
            """
        ).fetchone()
    assert dict(usage) == {
        "provider": "openai",
        "model": "fake-sheet-review-v1",
        "input_tokens": 1400,
        "output_tokens": 1200,
        "estimated_cost_usd": 0.0296,
    }


def test_openai_sheet_review_sends_five_images_and_requires_normalized_bbox() -> None:
    class FakeResponses:
        def __init__(self) -> None:
            self.request: dict[str, object] | None = None

        def create(self, **kwargs: object) -> SimpleNamespace:
            self.request = kwargs
            return SimpleNamespace(
                output_text=json.dumps(
                    {
                        "sheet_id": "sheet-1",
                        "summary": "Revisao concluida.",
                        "findings": [
                            {
                                "category": "dimensions",
                                "type": "unverifiable",
                                "severity": "low",
                                "confidence": 0.55,
                                "description": "Cota parcialmente encoberta.",
                                "scope": "localized",
                                "bbox": {"x0": 10, "y0": 20, "x1": 40, "y1": 60},
                                "evidence": ["O texto nao esta completamente visivel."],
                            }
                        ],
                    }
                ),
                usage=SimpleNamespace(input_tokens=1000, output_tokens=100),
            )

    fake = FakeResponses()
    provider = OpenAIProvider(
        api_key="sk-test",
        model="gpt-5.6-sol",
        reasoning_effort="low",
        max_output_tokens=900,
        client=SimpleNamespace(responses=fake),
        vision_image_detail="high",
        vision_max_output_tokens=1200,
    )
    images = tuple(
        SheetReviewImage(
            role="global" if index == 0 else "tile",
            image_bytes=b"png-test",
            image_hash=f"hash-{index}",
            bbox_pt=(0, 0, 600, 800),
            width_px=800,
            height_px=1000,
            detail="low" if index == 0 else "high",
        )
        for index in range(5)
    )
    response = provider.analyze_sheet(
        review=SheetReviewInput(
            sheet_id="sheet-1",
            width_pt=600,
            height_pt=800,
            images=images,
            context={"sheet": {"label": "Folha 01"}},
        )
    )

    assert response.analysis.findings[0].bbox.x1 == 40
    assert fake.request is not None
    assert fake.request["store"] is False
    user_content = fake.request["input"][1]["content"]
    assert sum(item["type"] == "input_image" for item in user_content) == 5
    schema = fake.request["text"]["format"]["schema"]
    bbox = schema["properties"]["findings"]["items"]["properties"]["bbox"]
    assert bbox["properties"]["x0"]["minimum"] == 0
    assert bbox["properties"]["x1"]["maximum"] == 1000


def test_openai_sheet_review_preserves_usage_when_structured_output_is_truncated() -> None:
    class FakeResponses:
        def create(self, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(
                output_text='{"sheet_id":"sheet-1","summary":"incomplete',
                status="incomplete",
                incomplete_details=SimpleNamespace(reason="max_output_tokens"),
                usage=SimpleNamespace(input_tokens=2500, output_tokens=1200),
            )

    provider = OpenAIProvider(
        api_key="sk-test",
        model="gpt-5.6-sol",
        reasoning_effort="low",
        max_output_tokens=900,
        client=SimpleNamespace(responses=FakeResponses()),
        vision_image_detail="high",
        vision_max_output_tokens=1200,
    )

    with pytest.raises(AIProviderUnavailableError) as captured:
        provider.analyze_sheet(
            review=SheetReviewInput(
                sheet_id="sheet-1",
                width_pt=600,
                height_pt=800,
                images=(),
                context={},
            )
        )

    error = captured.value
    assert error.provider_code == "sheet_review_schema_invalid"
    assert error.provider == "openai"
    assert error.model == "gpt-5.6-sol"
    assert error.input_tokens == 2500
    assert error.output_tokens == 1200
    assert error.estimated_cost_usd == 0.034
