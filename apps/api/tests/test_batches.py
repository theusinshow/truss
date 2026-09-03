from collections.abc import Iterator
from io import BytesIO
from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from truss_api.batch import repository as batch_repository
from truss_api.batch.worker import process_next_item
from truss_api.core.settings import Settings, get_settings
from truss_api.db.connection import transaction
from truss_api.db.schema import initialize_database
from truss_api.main import app
from truss_api.projects import repository as projects_repository
from truss_api.projects.models import ProjectCreate, RevisionCreate
from truss_api.sheetmap.elements.registry import build_revision_registry


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    resolved = Settings(data_dir=tmp_path / "data", ai_provider="local")
    initialize_database(resolved)
    return resolved


@pytest.fixture()
def client(settings: Settings) -> Iterator[TestClient]:
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def revision(settings: Settings) -> tuple[str, str]:
    project = projects_repository.create_project(ProjectCreate(name="Lote local"), settings)
    revision = projects_repository.create_revision(
        str(project["id"]), RevisionCreate(notes="F6.2"), settings
    )
    return str(project["id"]), str(revision["id"])


def make_pdf(page_count: int = 2) -> bytes:
    document = fitz.open()
    for index in range(page_count):
        page = document.new_page(width=842, height=595)
        page.insert_text((72, 72), f"FORMA PAVIMENTO {index + 1}")
        page.insert_text((620, 540), f"EST-{index + 1:04d}")
    buffer = BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def create_batch(client: TestClient, revision: tuple[str, str], pages: int = 2) -> dict:
    project_id, revision_id = revision
    response = client.post(
        f"/projects/{project_id}/revisions/{revision_id}/batch-imports",
        files={"file": ("lote.pdf", make_pdf(pages), "application/pdf")},
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_batch_import_persists_queue_and_worker_completes_both_phases(
    client: TestClient,
    settings: Settings,
    revision: tuple[str, str],
) -> None:
    payload = create_batch(client, revision, pages=2)
    batch_id = payload["batch"]["id"]

    assert payload["batch"]["total_sheets"] == 2
    assert payload["batch"]["phase"] == "sheet_map"
    assert payload["batch"]["phase_counts"]["sheet_map"]["queued"] == 2
    with transaction(settings) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sheet_maps").fetchone()[0] == 0

    assert process_next_item(settings)
    assert process_next_item(settings)
    after_maps = batch_repository.get_batch_run(batch_id, settings)
    assert after_maps["phase"] == "deterministic_audit"
    assert process_next_item(settings)
    assert process_next_item(settings)
    assert not process_next_item(settings)

    completed = batch_repository.get_batch_run(batch_id, settings)
    assert completed["status"] == "completed"
    assert completed["phase"] == "completed"
    with transaction(settings) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sheet_maps").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM audit_runs").fetchone()[0] == 2


def test_batch_claim_is_single_worker_and_cancel_is_cooperative(
    client: TestClient,
    settings: Settings,
    revision: tuple[str, str],
) -> None:
    payload = create_batch(client, revision, pages=2)
    batch_id = payload["batch"]["id"]
    claimed = batch_repository.claim_next_item(settings)
    assert claimed is not None
    assert batch_repository.claim_next_item(settings) is None

    requested = batch_repository.request_cancel(batch_id, settings)
    assert requested["status"] == "cancel_requested"
    batch_repository.complete_item(str(claimed["id"]), str(claimed["run_token"]), settings)

    cancelled = batch_repository.get_batch_run(batch_id, settings)
    assert cancelled["status"] == "cancelled"
    items = batch_repository.list_batch_items(batch_id, settings)
    assert sum(item["status"] == "completed" for item in items) == 1
    assert all(item["status"] in {"completed", "cancelled"} for item in items)


def test_worker_restart_finishes_a_pending_cancellation(
    client: TestClient,
    settings: Settings,
    revision: tuple[str, str],
) -> None:
    payload = create_batch(client, revision, pages=2)
    batch_id = payload["batch"]["id"]
    claimed = batch_repository.claim_next_item(settings)
    assert claimed is not None
    batch_repository.request_cancel(batch_id, settings)

    assert batch_repository.mark_running_batches_interrupted(settings) == 1
    recovered = batch_repository.get_batch_run(batch_id, settings)
    assert recovered["status"] == "cancelled"
    assert batch_repository.claim_next_item(settings) is None


def test_running_batch_cannot_be_retried(
    client: TestClient,
    revision: tuple[str, str],
) -> None:
    payload = create_batch(client, revision, pages=1)

    response = client.post(f"/batch-runs/{payload['batch']['id']}/resume")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "BATCH_NOT_RETRYABLE"


def test_sheet_map_failure_is_isolated_and_registry_reports_incomplete_coverage(
    client: TestClient,
    settings: Settings,
    revision: tuple[str, str],
) -> None:
    payload = create_batch(client, revision, pages=2)
    batch_id = payload["batch"]["id"]
    first = batch_repository.claim_next_item(settings)
    assert first is not None
    batch_repository.fail_item(
        str(first["id"]),
        str(first["run_token"]),
        settings,
        code="FIXTURE_FAILURE",
        message="Falha controlada.",
    )
    assert process_next_item(settings)

    current = batch_repository.get_batch_run(batch_id, settings)
    assert current["phase"] == "deterministic_audit"
    items = batch_repository.list_batch_items(batch_id, settings)
    skipped = [item for item in items if item["status"] == "skipped_dependency"]
    assert len(skipped) == 1

    registry = build_revision_registry(revision[1], settings)
    assert registry["coverage_complete"] is False
    assert registry["mapped_sheet_count"] == 1
    assert registry["expected_sheet_count"] == 2

    assert process_next_item(settings)
    finished = batch_repository.get_batch_run(batch_id, settings)
    assert finished["status"] == "completed_with_errors"

    resumed = batch_repository.retry_failures(batch_id, settings)
    assert resumed["phase"] == "sheet_map"
    assert process_next_item(settings)
    after_retry_map = batch_repository.get_batch_run(batch_id, settings)
    assert after_retry_map["phase"] == "deterministic_audit"
    assert after_retry_map["phase_counts"]["deterministic_audit"]["queued"] == 2
    assert process_next_item(settings)
    assert process_next_item(settings)
    assert batch_repository.get_batch_run(batch_id, settings)["status"] == "completed"
    assert build_revision_registry(revision[1], settings)["coverage_complete"] is True


def test_batch_events_are_append_only(
    client: TestClient,
    settings: Settings,
    revision: tuple[str, str],
) -> None:
    payload = create_batch(client, revision, pages=1)
    batch_id = payload["batch"]["id"]
    with transaction(settings) as connection:
        event_id = str(
            connection.execute(
                "SELECT id FROM batch_run_events WHERE batch_run_id = ?", (batch_id,)
            ).fetchone()["id"]
        )
        with pytest.raises(Exception):
            connection.execute(
                "UPDATE batch_run_events SET event_kind = 'started' WHERE id = ?", (event_id,)
            )


def test_local_transient_item_has_only_one_automatic_retry(
    client: TestClient,
    settings: Settings,
    revision: tuple[str, str],
) -> None:
    payload = create_batch(client, revision, pages=1)
    batch_id = payload["batch"]["id"]
    first = batch_repository.claim_next_item(settings)
    assert first is not None

    assert batch_repository.requeue_transient_item(
        str(first["id"]),
        str(first["run_token"]),
        settings,
        code="STORAGE_IO_ERROR",
        message="Falha transitoria.",
    )
    second = batch_repository.claim_next_item(settings)
    assert second is not None
    assert second["id"] == first["id"]
    assert second["attempt_count"] == 2
    assert not batch_repository.requeue_transient_item(
        str(second["id"]),
        str(second["run_token"]),
        settings,
        code="STORAGE_IO_ERROR",
        message="Falha repetida.",
    )
    batch_repository.fail_item(
        str(second["id"]),
        str(second["run_token"]),
        settings,
        code="STORAGE_IO_ERROR",
        message="Falha repetida.",
    )
    assert batch_repository.get_batch_run(batch_id, settings)["status"] == "completed_with_errors"


def test_visual_batch_requires_explicitly_enabled_vision(
    client: TestClient,
    revision: tuple[str, str],
) -> None:
    project_id, revision_id = revision
    response = client.post(
        f"/projects/{project_id}/revisions/{revision_id}/batch-imports",
        files={"file": ("lote.pdf", make_pdf(1), "application/pdf")},
        data={"include_visual": "true"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "VISION_DISABLED"


def test_ai_review_import_creates_only_sheet_map_and_ai_review_phases(
    client: TestClient,
    settings: Settings,
    revision: tuple[str, str],
) -> None:
    settings.ai_provider = "openai"
    settings.openai_api_key = SecretStr("sk-test")
    settings.vision_enabled = True
    project_id, revision_id = revision

    response = client.post(
        f"/projects/{project_id}/revisions/{revision_id}/batch-imports",
        files={"file": ("ai-review.pdf", make_pdf(2), "application/pdf")},
        data={"ai_review": "true"},
    )

    assert response.status_code == 202, response.text
    batch = response.json()["batch"]
    assert batch["mode"] == "with_visual"
    assert set(batch["phase_counts"]) == {"sheet_map", "visual_audit"}
    assert batch["config"]["ai_review"] is True
    assert batch["config"]["vision_budget_usd_per_revision"] == 1.0
    assert batch["config"]["vision_cost_reserve_usd_per_call"] == 0.25
    assert batch["config"]["vision_max_output_tokens"] == 3000
    assert batch["config"]["openai_reasoning_effort"] == "low"


def test_batch_capabilities_publish_frozen_local_limits(client: TestClient) -> None:
    response = client.get("/batch-capabilities")

    assert response.status_code == 200
    assert response.json() == {
        "visual_enabled": False,
        "ai_review_available": False,
        "external_calls_enabled": False,
        "provider": "local",
        "model": "gpt-5.6-sol",
        "vision_budget_usd_per_revision": 1.0,
        "vision_max_calls_per_revision": 30,
        "vision_max_candidates_per_sheet": 8,
        "worker_concurrency": 1,
        "visual_concurrency": 1,
    }


def test_second_active_batch_is_rejected_without_duplicate_items(
    client: TestClient,
    settings: Settings,
    revision: tuple[str, str],
) -> None:
    payload = create_batch(client, revision, pages=2)
    project_id, revision_id = revision
    response = client.post(
        f"/projects/{project_id}/revisions/{revision_id}/batch-runs",
        json={"include_visual": False},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "BATCH_ALREADY_ACTIVE"
    with transaction(settings) as connection:
        assert connection.execute("SELECT COUNT(*) FROM batch_runs").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM batch_items").fetchone()[0] == 4
    assert payload["batch"]["total_sheets"] == 2


def test_worker_restart_requires_explicit_resume_and_reuses_audit_identity(
    client: TestClient,
    settings: Settings,
    revision: tuple[str, str],
) -> None:
    payload = create_batch(client, revision, pages=1)
    batch_id = payload["batch"]["id"]
    assert process_next_item(settings)
    abandoned = batch_repository.claim_next_item(settings)
    assert abandoned is not None
    assert abandoned["phase"] == "deterministic_audit"

    assert batch_repository.mark_running_batches_interrupted(settings) == 1
    interrupted = batch_repository.get_batch_run(batch_id, settings)
    assert interrupted["status"] == "interrupted"
    assert batch_repository.claim_next_item(settings) is None

    resumed = client.post(f"/batch-runs/{batch_id}/resume")
    assert resumed.status_code == 200
    assert process_next_item(settings)
    assert batch_repository.get_batch_run(batch_id, settings)["status"] == "completed"
    with transaction(settings) as connection:
        assert connection.execute("SELECT COUNT(*) FROM audit_runs").fetchone()[0] == 1


def test_visual_worker_uses_configuration_frozen_on_batch_creation(
    client: TestClient,
    settings: Settings,
    revision: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_batch(client, revision, pages=1)
    assert process_next_item(settings)
    assert process_next_item(settings)
    visual = batch_repository.create_batch_run(
        project_id=revision[0],
        revision_id=revision[1],
        mode="with_visual",
        config={
            "include_visual": True,
            "provider": "openai",
            "model": "frozen-model",
            "vision_budget_usd_per_revision": 0.12,
            "vision_max_calls_per_revision": 7,
            "vision_max_candidates_per_sheet": 3,
        },
        settings=settings,
    )
    assert process_next_item(settings)
    assert process_next_item(settings)
    captured: dict[str, object] = {}

    def fake_visual(_sheet_id: str, operation_settings: Settings) -> dict[str, object]:
        captured.update(
            provider=operation_settings.ai_provider,
            model=operation_settings.openai_model,
            budget=operation_settings.vision_budget_usd_per_revision,
            calls=operation_settings.vision_max_calls_per_revision,
            candidates=operation_settings.vision_max_candidates_per_sheet,
        )
        return {"id": "visual-result"}

    monkeypatch.setattr("truss_api.batch.worker.run_visual_audit_operation", fake_visual)
    assert process_next_item(settings)

    assert captured == {
        "provider": "openai",
        "model": "frozen-model",
        "budget": 0.12,
        "calls": 7,
        "candidates": 3,
    }
    assert batch_repository.get_batch_run(str(visual["id"]), settings)["status"] == "completed"


def test_ai_review_batch_skips_deterministic_phase_and_reviews_every_sheet(
    client: TestClient,
    settings: Settings,
    revision: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported = create_batch(client, revision, pages=2)
    while process_next_item(settings):
        pass
    assert batch_repository.get_batch_run(imported["batch"]["id"], settings)["status"] == "completed"

    review = batch_repository.create_batch_run(
        project_id=revision[0],
        revision_id=revision[1],
        mode="with_visual",
        config={
            "ai_review": True,
            "provider": "openai",
            "model": "frozen-ai-review",
            "vision_budget_usd_per_revision": 1.0,
            "vision_max_calls_per_revision": 20,
            "vision_cost_reserve_usd_per_call": 0.18,
            "vision_max_output_tokens": 2800,
            "openai_reasoning_effort": "none",
            "ai_review_global_max_pixels": 1500,
            "ai_review_tile_max_pixels": 1200,
            "ai_review_tile_overlap_ratio": 0.03,
        },
        settings=settings,
    )
    assert set(review["phase_counts"]) == {"sheet_map", "visual_audit"}
    assert process_next_item(settings)
    assert process_next_item(settings)
    captured: list[tuple[str, str, float, float, int, str]] = []

    def fake_review(sheet_id: str, operation_settings: Settings) -> dict[str, object]:
        captured.append(
            (
                sheet_id,
                operation_settings.openai_model,
                operation_settings.vision_budget_usd_per_revision,
                operation_settings.vision_cost_reserve_usd_per_call,
                operation_settings.vision_max_output_tokens,
                operation_settings.openai_reasoning_effort,
            )
        )
        return {"id": f"review-{sheet_id}"}

    monkeypatch.setattr("truss_api.batch.worker.run_ai_sheet_review_operation", fake_review)
    assert process_next_item(settings)
    assert process_next_item(settings)
    assert not process_next_item(settings)

    completed = batch_repository.get_batch_run(str(review["id"]), settings)
    assert completed["status"] == "completed"
    assert len(captured) == 2
    assert {model for _, model, _, _, _, _ in captured} == {"frozen-ai-review"}
    assert {budget for _, _, budget, _, _, _ in captured} == {1.0}
    assert {reserve for _, _, _, reserve, _, _ in captured} == {0.18}
    assert {tokens for _, _, _, _, tokens, _ in captured} == {2800}
    assert {effort for _, _, _, _, _, effort in captured} == {"none"}
