from pathlib import Path
import json
import sqlite3
import zipfile

import pytest

from factories import make_structural_pdf_bytes
from truss_api.core.settings import Settings
from truss_api.db.schema import initialize_database
from truss_api.projects import repository as projects_repository
from truss_api.projects.models import ProjectCreate, RevisionCreate
from truss_api.recovery.backup import BACKUP_SCHEMA, create_backup, verify_backup
from truss_api.recovery.errors import TrussError
from truss_api.recovery.operations import import_document
from truss_api.recovery.restore import restore_backup
from truss_api.recovery.sources import declare_source_unavailable


@pytest.fixture()
def populated(tmp_path: Path) -> tuple[Settings, dict[str, object]]:
    settings = Settings(data_dir=tmp_path / "data", backup_dir=tmp_path / "backups")
    initialize_database(settings)
    project = projects_repository.create_project(ProjectCreate(name="Backup"), settings)
    revision = projects_repository.create_revision(
        str(project["id"]),
        RevisionCreate(notes="R01"),
        settings,
    )
    document = import_document(
        project_id=str(project["id"]),
        revision_id=str(revision["id"]),
        filename="estrutura.pdf",
        content=make_structural_pdf_bytes(page_count=2),
        mime_type="application/pdf",
        settings=settings,
    )
    inbox = settings.data_dir / "knowledge-inbox" / "approved"
    inbox.mkdir(parents=True)
    (inbox / "notes.json").write_text('{"authority":"delivered_reference"}', encoding="utf-8")
    settings.renders_dir.mkdir(parents=True, exist_ok=True)
    (settings.renders_dir / "rebuildable.png").write_bytes(b"render")
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    (settings.cache_dir / "cache.bin").write_bytes(b"cache")
    return settings, document


def test_backup_manifest_verifies_durable_data_and_excludes_derivatives(
    populated: tuple[Settings, dict[str, object]],
) -> None:
    settings, document = populated

    archive = create_backup(settings)
    manifest = verify_backup(archive)

    assert manifest["schema"] == BACKUP_SCHEMA
    assert manifest["logical_counts"]["documents"] == 1
    names = {item["relative_path"] for item in manifest["files"]}
    assert "db/truss.sqlite" in names
    assert f"files/{str(document['stored_file_path']).replace(chr(92), '/')}" in names
    assert "files/knowledge-inbox/approved/notes.json" in names
    assert not any("renders/" in name or "cache/" in name for name in names)
    assert archive.parent == settings.backup_dir


def test_restore_publishes_new_data_dir_without_mutating_source(
    populated: tuple[Settings, dict[str, object]],
    tmp_path: Path,
) -> None:
    settings, document = populated
    archive = create_backup(settings)
    source_database_hash = settings.database_path.read_bytes()
    target = tmp_path / "restored-data"

    restored = restore_backup(archive, target)

    assert restored == target.resolve()
    assert settings.database_path.read_bytes() == source_database_hash
    assert (restored / str(document["stored_file_path"])).is_file()
    connection = sqlite3.connect(restored / "db" / "truss.sqlite")
    assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
    connection.close()
    assert (restored / "recovery" / "restore-manifest.json").is_file()
    assert not (restored / "renders").exists()


def test_restore_refuses_existing_target(
    populated: tuple[Settings, dict[str, object]],
    tmp_path: Path,
) -> None:
    settings, _ = populated
    archive = create_backup(settings)
    target = tmp_path / "existing"
    target.mkdir()

    with pytest.raises(TrussError) as captured:
        restore_backup(archive, target)

    assert captured.value.public.code == "RESTORE_TARGET_EXISTS"


def test_corrupt_archive_is_rejected_before_restore(
    populated: tuple[Settings, dict[str, object]],
    tmp_path: Path,
) -> None:
    settings, _ = populated
    archive = create_backup(settings)
    corrupt = tmp_path / "corrupt.zip"
    content = archive.read_bytes()
    corrupt.write_bytes(content[: len(content) // 2])
    target = tmp_path / "must-not-exist"

    with pytest.raises(TrussError) as captured:
        restore_backup(corrupt, target)

    assert captured.value.public.code == "BACKUP_INVALID"
    assert not target.exists()


def test_backup_refuses_missing_original_and_destination_inside_data(
    populated: tuple[Settings, dict[str, object]],
) -> None:
    settings, document = populated
    (settings.data_dir / str(document["stored_file_path"])).unlink()

    with pytest.raises(TrussError) as missing:
        create_backup(settings)
    assert missing.value.public.code == "PDF_SOURCE_MISSING"

    with pytest.raises(TrussError) as destination:
        create_backup(settings, settings.data_dir / "backups")
    assert destination.value.public.code == "BACKUP_DESTINATION_INVALID"


def test_backup_preserves_explicit_unavailable_source(
    populated: tuple[Settings, dict[str, object]],
    tmp_path: Path,
) -> None:
    settings, document = populated
    (settings.data_dir / str(document["stored_file_path"])).unlink()
    declare_source_unavailable(
        str(document["id"]),
        reason_code="clone_migration_missing",
        note="Estado local anterior nao transferido.",
        settings=settings,
    )

    archive = create_backup(settings)
    manifest = verify_backup(archive)

    assert manifest["logical_counts"]["document_source_events"] == 1
    assert manifest["unavailable_sources"] == [
        {
            "document_id": document["id"],
            "revision_id": document["revision_id"],
            "original_filename": document["original_filename"],
            "stored_file_path": str(document["stored_file_path"]).replace("\\", "/"),
            "content_hash": document["content_hash"],
            "file_size_bytes": document["file_size_bytes"],
            "page_count": document["page_count"],
            "status": "SOURCE_UNAVAILABLE",
            "reason_code": "clone_migration_missing",
            "note": "Estado local anterior nao transferido.",
            "declared_at": manifest["unavailable_sources"][0]["declared_at"],
        }
    ]
    unavailable_path = f"files/{str(document['stored_file_path']).replace(chr(92), '/')}"
    assert unavailable_path not in {item["relative_path"] for item in manifest["files"]}

    restored = restore_backup(archive, tmp_path / "restored-with-declaration")
    with sqlite3.connect(restored / "db" / "truss.sqlite") as connection:
        assert connection.execute("SELECT COUNT(*) FROM document_source_events").fetchone()[0] == 1


def test_verify_rejects_path_traversal_before_extraction(tmp_path: Path) -> None:
    archive = tmp_path / "traversal.zip"
    manifest = {
        "schema": BACKUP_SCHEMA,
        "files": [
            {
                "relative_path": "../escape.txt",
                "role": "original",
                "critical": True,
                "size_bytes": 1,
                "sha256": "0" * 64,
            }
        ],
        "total_size_bytes": 1,
    }
    with zipfile.ZipFile(archive, "w") as target:
        target.writestr("manifest.json", json.dumps(manifest))
        target.writestr("../escape.txt", b"x")

    with pytest.raises(TrussError) as captured:
        verify_backup(archive)

    assert captured.value.public.code == "BACKUP_INVALID"
    assert not (tmp_path.parent / "escape.txt").exists()
