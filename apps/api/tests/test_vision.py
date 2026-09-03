import json
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import fitz
from fastapi.testclient import TestClient
import pytest

from truss_api.ai.provider import OpenAIProvider
from truss_api.calibration.vision import measure_visual_candidates
from truss_api.core.settings import Settings, get_settings
from truss_api.db.connection import transaction
from truss_api.db.schema import initialize_database
from truss_api.main import app
from truss_api.sheetmap import repository as sheetmap_repository
from truss_api.sheetmap.primitives import PageExtraction, PageMetadata, TextSpanRecord
from truss_api.vision.candidates import detect_legibility_candidates, read_sheet_extraction
from truss_api.vision.crops import render_vision_crop
from truss_api.vision.models import (
    VisionAnalysis,
    VisionCandidate,
    VisionCropInput,
    VisionProviderResponse,
)
from truss_api.vision.orchestrator import run_visual_audit


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    resolved = Settings(
        data_dir=tmp_path / "data",
        ai_provider="local",
        openai_api_key=None,
        vision_enabled=True,
        vision_budget_usd_per_revision=1.0,
        vision_max_candidates_per_sheet=1,
    )
    initialize_database(resolved)
    return resolved


@pytest.fixture()
def client(settings: Settings) -> Iterator[TestClient]:
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _metadata() -> PageMetadata:
    return PageMetadata(
        width_pt=842,
        height_pt=595,
        rotation=0,
        mediabox=(0, 0, 842, 595),
        cropbox=(0, 0, 842, 595),
        rotation_matrix=(1, 0, 0, 1, 0, 0),
    )


def _legibility_pdf_bytes() -> bytes:
    document = fitz.open()
    page = document.new_page(width=842, height=595)
    page.insert_text((72, 72), "PLANTA DE FORMAS - NIVEL 100", fontsize=12)
    page.insert_text((72, 90), "ESCALA 1:50", fontsize=8)
    page.insert_text((180, 170), "P1 20x40", fontsize=4)
    page.insert_text((300, 240), "TEXTO A", fontsize=8)
    page.insert_text((300, 240), "TEXTO B", fontsize=8)
    buffer = BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def _create_sheet(client: TestClient) -> str:
    project = client.post("/projects", json={"name": "Vision fixture"}).json()
    revision = client.post(
        f"/projects/{project['id']}/revisions", json={"notes": "R01"}
    ).json()
    imported = client.post(
        f"/projects/{project['id']}/revisions/{revision['id']}/documents",
        files={"file": ("vision.pdf", _legibility_pdf_bytes(), "application/pdf")},
    ).json()
    return str(imported["sheets"][0]["id"])


def test_candidates_are_deterministic_and_keep_pdf_coordinates() -> None:
    extraction = PageExtraction(
        metadata=_metadata(),
        spans=[
            TextSpanRecord("NORMAL", (10, 10, 60, 20), "Arial", 8, (1, 0)),
            TextSpanRecord("MINIMO", (10, 40, 45, 46), "Arial", 4, (1, 0)),
            TextSpanRecord("SOBRE A", (100, 100, 160, 112), "Arial", 8, (1, 0)),
            TextSpanRecord("SOBRE B", (120, 102, 180, 114), "Arial", 8, (1, 0)),
        ],
    )
    sheet_map = {
        "views": [
            {
                "id": "view-1",
                "x0": 0,
                "y0": 0,
                "x1": 200,
                "y1": 200,
                "technical_scope": "formas",
            }
        ]
    }

    first = detect_legibility_candidates(
        extraction, sheet_map, small_text_threshold_pt=5.5, max_candidates=8
    )
    second = detect_legibility_candidates(
        extraction, sheet_map, small_text_threshold_pt=5.5, max_candidates=8
    )

    assert [item.candidate_id for item in first] == [item.candidate_id for item in second]
    assert [item.kind for item in first] == ["text_overlap", "small_text"]
    assert first[0].bbox_pt == (100, 100, 180, 114)
    assert first[0].view_id == "view-1"
    assert first[0].technical_scope == "formas"
    assert all("NORMAL" not in item.text_samples for item in first)


def test_crop_is_local_content_addressed_and_clipped_to_page(
    client: TestClient, settings: Settings
) -> None:
    sheet_id = _create_sheet(client)
    sheet_map = sheetmap_repository.get_sheet_map(sheet_id, settings)
    extraction = read_sheet_extraction(sheet_id, settings)
    candidate = detect_legibility_candidates(
        extraction, sheet_map, small_text_threshold_pt=5.5, max_candidates=1
    )[0]

    first = render_vision_crop(sheet_id, candidate, settings)
    second = render_vision_crop(sheet_id, candidate, settings)

    assert first.crop_hash == second.crop_hash
    assert first.image_bytes.startswith(b"\x89PNG")
    assert first.width_px <= settings.vision_max_crop_pixels
    assert first.height_px <= settings.vision_max_crop_pixels
    assert (settings.data_dir / first.path).exists()
    assert first.crop_bbox_pt[0] >= 0 and first.crop_bbox_pt[1] >= 0
    assert first.crop_bbox_pt[2] <= 842 and first.crop_bbox_pt[3] <= 595


def test_visual_audit_uses_fake_provider_cache_and_persists_traceability(
    client: TestClient, settings: Settings
) -> None:
    sheet_id = _create_sheet(client)

    class FakeVisionProvider:
        provider = "fake"
        model = "fake-vision-v1"

        def __init__(self) -> None:
            self.calls = 0

        def analyze_crop(self, *, crop: VisionCropInput) -> VisionProviderResponse:
            self.calls += 1
            return VisionProviderResponse(
                provider=self.provider,
                model=self.model,
                analysis=VisionAnalysis(
                    candidate_id=crop.candidate.candidate_id,
                    outcome="attention",
                    issue="text_overlap",
                    confidence=0.91,
                    description="Textos aparentam estar sobrepostos; revise a legibilidade.",
                    evidence=["Os contornos dos dois textos ocupam a mesma regiao visual."],
                ),
                input_tokens=120,
                output_tokens=30,
                estimated_cost_usd=0.002,
            )

    provider = FakeVisionProvider()
    first = run_visual_audit(sheet_id, settings, provider=provider)
    second = run_visual_audit(sheet_id, settings, provider=provider)

    assert provider.calls == 1
    assert second["id"] == first["id"]
    settings.openai_reasoning_effort = "medium"
    third = run_visual_audit(sheet_id, settings, provider=provider)
    assert provider.calls == 2
    assert third["id"] != first["id"]
    assert first["pipeline_version"] == "vision-v0.1"
    assert first["mode"] == "vision"
    assert first["coverage"]["failed"] == 1
    finding = first["findings"][0]
    assert finding["source_layer"] == "vision"
    assert finding["rule_id"] == "vision.text_legibility"
    assert finding["type"] == "attention"
    assert finding["severity"] == "medium"
    assert finding["bbox"]["x0"] < finding["bbox"]["x1"]
    assert any(item.startswith("crop: hash=") for item in finding["evidence"])

    with transaction(settings) as connection:
        usage = connection.execute(
            "SELECT COUNT(*) FROM ai_usage_events WHERE operation = 'vision.legibility'"
        ).fetchone()[0]
        cache = connection.execute(
            "SELECT COUNT(*) FROM cache_entries WHERE namespace = 'vision'"
        ).fetchone()[0]
    assert usage == 2
    assert cache == 2


def test_budget_blocks_before_provider_call(client: TestClient, settings: Settings) -> None:
    sheet_id = _create_sheet(client)
    settings.vision_budget_usd_per_revision = 0.04
    settings.vision_cost_reserve_usd_per_call = 0.05

    class NeverCalledProvider:
        provider = "fake"
        model = "fake-vision-v1"
        calls = 0

        def analyze_crop(self, *, crop: VisionCropInput) -> VisionProviderResponse:
            self.calls += 1
            raise AssertionError("budget gate must run before the provider")

    provider = NeverCalledProvider()
    run = run_visual_audit(sheet_id, settings, provider=provider)

    assert provider.calls == 0
    assert run["coverage"]["evaluated"] == 0
    assert run["coverage"]["skipped"] == 1
    assert run["findings"] == []


def test_route_is_explicitly_disabled_by_default(tmp_path: Path) -> None:
    disabled = Settings(
        data_dir=tmp_path / "disabled-data",
        ai_provider="local",
        openai_api_key=None,
        vision_enabled=False,
    )
    initialize_database(disabled)
    app.dependency_overrides[get_settings] = lambda: disabled
    with TestClient(app) as disabled_client:
        response = disabled_client.post("/sheets/missing/vision-audit-runs")
    app.dependency_overrides.clear()

    assert response.status_code == 409
    assert "desabilitada" in response.json()["detail"].lower()


def test_openai_vision_uses_image_input_and_strict_structured_output() -> None:
    candidate = VisionCandidate(
        candidate_id="visual-123",
        kind="small_text",
        bbox_pt=(10, 20, 40, 30),
        text_samples=("P1",),
        font_sizes_pt=(4.0,),
        view_id="view-1",
        technical_scope="formas",
        score=1.5,
    )

    class FakeResponses:
        def __init__(self) -> None:
            self.request: dict[str, object] | None = None

        def create(self, **kwargs: object) -> SimpleNamespace:
            self.request = kwargs
            return SimpleNamespace(
                output_text=json.dumps(
                    {
                        "candidate_id": "visual-123",
                        "outcome": "pass",
                        "issue": "none",
                        "confidence": 0.88,
                        "description": "O texto permanece legivel no recorte.",
                        "evidence": ["Caracteres distinguiveis."],
                    }
                ),
                usage=SimpleNamespace(input_tokens=100, output_tokens=10),
            )

    fake_responses = FakeResponses()
    provider = OpenAIProvider(
        api_key="sk-test",
        model="gpt-5.6-sol",
        reasoning_effort="low",
        max_output_tokens=900,
        client=SimpleNamespace(responses=fake_responses),
        vision_image_detail="high",
        vision_max_output_tokens=600,
    )
    response = provider.analyze_crop(
        crop=VisionCropInput(
            candidate=candidate,
            image_bytes=b"png-test",
            image_detail="high",
            crop_hash="crop-123",
            crop_bbox_pt=(0, 10, 50, 40),
            width_px=150,
            height_px=90,
        )
    )

    assert response.analysis.outcome == "pass"
    assert response.estimated_cost_usd == 0.0006
    request = fake_responses.request
    assert request is not None
    assert request["store"] is False
    assert request["reasoning"] == {"effort": "low"}
    assert request["max_output_tokens"] == 600
    image = request["input"][1]["content"][1]
    assert image["type"] == "input_image"
    assert image["detail"] == "high"
    assert image["image_url"].startswith("data:image/png;base64,")
    schema = request["text"]["format"]["schema"]
    assert schema["properties"]["candidate_id"]["const"] == "visual-123"
    assert "bbox" not in schema["properties"]
    assert "bbox" not in request["input"][1]["content"][0]["text"]


def test_visual_candidate_measurement_never_calls_provider(tmp_path: Path) -> None:
    pdf_path = tmp_path / "measurement.pdf"
    pdf_path.write_bytes(_legibility_pdf_bytes())

    measurement = measure_visual_candidates(
        pdf_path,
        small_text_threshold_pt=5.5,
        max_candidates_per_page=8,
    )

    assert measurement.page_count == 1
    assert measurement.pages_with_candidates == 1
    assert measurement.text_span_count > 0
    assert measurement.small_text_count > 0
    assert measurement.overlap_count > 0
    assert 0 < measurement.selected_count <= 8
