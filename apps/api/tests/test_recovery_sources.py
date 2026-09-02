from pathlib import Path
import sqlite3

import pytest

from truss_api.core.settings import Settings
from truss_api.db.connection import transaction
from truss_api.db.schema import initialize_database
from truss_api.documents.repository import create_document_from_prepared_pdf
from truss_api.documents.importer import prepare_pdf_storage
from truss_api.projects import repository as projects_repository
from truss_api.projects.models import ProjectCreate, RevisionCreate
from truss_api.recovery.errors import TrussError
from truss_api.recovery.sources import (
    SOURCE_RESTORED,
    SOURCE_UNAVAILABLE,
    declare_source_restored,
    declare_source_unavailable,
    list_document_sources,
)

from factories import make_structural_pdf_bytes


@pytest.fixture()
def missing_document(tmp_path: Path) -> tuple[Settings, dict[str, object], bytes]:
    settings = Settings(data_dir=tmp_path / "data")
    initialize_database(settings)
    project = projects_repository.create_project(ProjectCreate(name="Legacy"), settings)
    revision = projects_repository.create_revision(
        str(project["id"]),
        RevisionCreate(revision_code="R01"),
        settings,
    )
    content = make_structural_pdf_bytes(page_count=1)
    prepared = prepare_pdf_storage(
        content=content,
        filename="legacy.pdf",
        project_id=str(project["id"]),
        revision_id=str(revision["id"]),
        settings=settings,
        mime_type="application/pdf",
    )
    document = create_document_from_prepared_pdf(
        project_id=str(project["id"]),
        revision_id=str(revision["id"]),
        prepared_pdf=prepared,
        settings=settings,
    )
    (settings.data_dir / str(document["stored_file_path"])).unlink()
    return settings, document, content


def test_unavailable_declaration_is_append_only_and_idempotent(
    missing_document: tuple[Settings, dict[str, object], bytes],
) -> None:
    settings, document, _ = missing_document
    first = declare_source_unavailable(
        str(document["id"]),
        reason_code="clone_migration_missing",
        note="Banco transferido sem os arquivos locais.",
        settings=settings,
    )
    second = declare_source_unavailable(
        str(document["id"]),
        reason_code="clone_migration_missing",
        note="Repeticao segura.",
        settings=settings,
    )

    assert first["id"] == second["id"]
    with transaction(settings) as connection:
        sources = list_document_sources(connection)
        assert sources[0]["source_status"] == SOURCE_UNAVAILABLE
        assert sources[0]["reason_code"] == "clone_migration_missing"
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE document_source_events SET note='alterado' WHERE id=?",
                (first["id"],),
            )


def test_declaring_available_or_corrupt_source_unavailable_is_refused(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data")
    initialize_database(settings)
    project = projects_repository.create_project(ProjectCreate(name="Available"), settings)
    revision = projects_repository.create_revision(
        str(project["id"]), RevisionCreate(revision_code="R01"), settings
    )
    content = make_structural_pdf_bytes(page_count=1)
    prepared = prepare_pdf_storage(
        content=content,
        filename="available.pdf",
        project_id=str(project["id"]),
        revision_id=str(revision["id"]),
        settings=settings,
        mime_type="application/pdf",
    )
    document = create_document_from_prepared_pdf(
        project_id=str(project["id"]),
        revision_id=str(revision["id"]),
        prepared_pdf=prepared,
        settings=settings,
    )

    with pytest.raises(TrussError) as available:
        declare_source_unavailable(
            str(document["id"]),
            reason_code="clone_migration_missing",
            note="",
            settings=settings,
        )
    assert available.value.public.code == "PDF_SOURCE_AVAILABLE"

    (settings.data_dir / str(document["stored_file_path"])).write_bytes(b"corrupt")
    with pytest.raises(TrussError) as corrupt:
        declare_source_unavailable(
            str(document["id"]),
            reason_code="clone_migration_missing",
            note="",
            settings=settings,
        )
    assert corrupt.value.public.code == "ARTIFACT_CORRUPT"


def test_restoration_requires_and_verifies_exact_historical_bytes(
    missing_document: tuple[Settings, dict[str, object], bytes],
) -> None:
    settings, document, content = missing_document
    declare_source_unavailable(
        str(document["id"]),
        reason_code="clone_migration_missing",
        note="",
        settings=settings,
    )
    source = settings.data_dir / str(document["stored_file_path"])
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"other revision")

    with pytest.raises(TrussError) as mismatch:
        declare_source_restored(
            str(document["id"]),
            reason_code="source_recovered",
            note="",
            settings=settings,
        )
    assert mismatch.value.public.code == "ARTIFACT_CORRUPT"

    source.write_bytes(content)
    restored = declare_source_restored(
        str(document["id"]),
        reason_code="source_recovered",
        note="Hash historico confirmado.",
        settings=settings,
    )
    assert restored["status"] == SOURCE_RESTORED
    with transaction(settings) as connection:
        assert list_document_sources(connection)[0]["source_status"] == SOURCE_RESTORED
