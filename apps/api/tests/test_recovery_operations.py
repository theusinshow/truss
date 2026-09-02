from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from truss_api.core.settings import Settings, get_settings
from truss_api.db.connection import transaction
from truss_api.db.schema import initialize_database
from truss_api.documents.importer import hash_bytes, prepare_pdf_storage
from truss_api.main import app
from truss_api.projects import repository as projects_repository
from truss_api.projects.models import ProjectCreate, RevisionCreate
from truss_api.recovery import repository
from truss_api.recovery.errors import TrussError
from truss_api.recovery.operations import IMPORT_PIPELINE_VERSION, operation_identity
from truss_api.recovery.operations import _vision_identity_context

from factories import make_structural_pdf_bytes


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    resolved = Settings(data_dir=tmp_path / "data")
    initialize_database(resolved)
    return resolved


@pytest.fixture()
def client(settings: Settings) -> Iterator[TestClient]:
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _revision(settings: Settings) -> tuple[str, str]:
    project = projects_repository.create_project(ProjectCreate(name="Recovery"), settings)
    revision = projects_repository.create_revision(
        str(project["id"]),
        RevisionCreate(notes="R01"),
        settings,
    )
    return str(project["id"]), str(revision["id"])


def test_claim_is_compare_and_swap_and_startup_marks_interrupted(settings: Settings) -> None:
    project_id, revision_id = _revision(settings)
    operation = repository.create_operation(
        identity_key="one-operation",
        kind="document_import",
        project_id=project_id,
        revision_id=revision_id,
        input_hash="hash",
        pipeline_version=IMPORT_PIPELINE_VERSION,
        checkpoint="validated",
        settings=settings,
    )
    repository.claim_operation(str(operation["id"]), settings)

    with pytest.raises(TrussError) as captured:
        repository.claim_operation(str(operation["id"]), settings)
    assert captured.value.public.code == "OPERATION_ALREADY_RUNNING"

    assert repository.mark_running_as_interrupted(settings) == 1
    interrupted = repository.get_operation(str(operation["id"]), settings)
    assert interrupted["status"] == "interrupted"
    assert interrupted["resumable"] is False  # o PDF ainda nao foi armazenado
    assert [event["event_kind"] for event in repository.list_events(str(operation["id"]), settings)] == [
        "created",
        "started",
        "interrupted",
    ]


def test_interrupted_import_resumes_once_from_stored_original(
    client: TestClient,
    settings: Settings,
) -> None:
    project_id, revision_id = _revision(settings)
    content = make_structural_pdf_bytes(page_count=1)
    digest = hash_bytes(content)
    prepared = prepare_pdf_storage(
        content=content,
        filename="recovery.pdf",
        project_id=project_id,
        revision_id=revision_id,
        settings=settings,
    )
    operation = repository.create_operation(
        identity_key=operation_identity(
            "document_import",
            revision_id=revision_id,
            content_hash=digest,
            pipeline=IMPORT_PIPELINE_VERSION,
        ),
        kind="document_import",
        project_id=project_id,
        revision_id=revision_id,
        input_hash=digest,
        pipeline_version=IMPORT_PIPELINE_VERSION,
        checkpoint="validated",
        payload={"original_filename": "recovery.pdf", "mime_type": "application/pdf"},
        settings=settings,
    )
    repository.claim_operation(str(operation["id"]), settings)
    repository.save_checkpoint(
        str(operation["id"]),
        "original_stored",
        settings,
        payload={"stored_file_path": prepared.stored_file_path},
    )
    repository.mark_running_as_interrupted(settings)

    response = client.post(f"/operations/{operation['id']}/resume")
    replay = client.post(f"/operations/{operation['id']}/resume")

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert replay.status_code == 200
    assert replay.json()["status"] == "completed"
    with transaction(settings) as connection:
        assert connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM sheet_maps").fetchone()[0] == 1


def test_visual_operation_is_never_automatically_resumable(settings: Settings) -> None:
    operation = repository.create_operation(
        identity_key="vision-operation",
        kind="vision_audit",
        input_hash="hash",
        pipeline_version="vision-v0.1",
        checkpoint="ready",
        settings=settings,
    )
    repository.claim_operation(str(operation["id"]), settings)
    repository.mark_running_as_interrupted(settings)

    restored = repository.get_operation(str(operation["id"]), settings)
    assert restored["status"] == "manual_retry_required"
    assert restored["resumable"] is False


def test_operation_creation_is_idempotent_by_identity(settings: Settings) -> None:
    first = repository.create_operation(
        identity_key="stable-identity",
        kind="deterministic_audit",
        input_hash="snapshot",
        pipeline_version="audit-v0.5",
        checkpoint="ready",
        settings=settings,
    )
    second = repository.create_operation(
        identity_key="stable-identity",
        kind="deterministic_audit",
        input_hash="snapshot",
        pipeline_version="audit-v0.5",
        checkpoint="ready",
        settings=settings,
    )

    assert second["id"] == first["id"]
    assert len(repository.list_events(str(first["id"]), settings)) == 1


def test_vision_identity_context_changes_with_result_settings(settings: Settings) -> None:
    baseline = _vision_identity_context(settings)
    changed = Settings(
        data_dir=settings.data_dir,
        vision_crop_padding_pt=settings.vision_crop_padding_pt + 1,
    )

    assert _vision_identity_context(changed) != baseline
