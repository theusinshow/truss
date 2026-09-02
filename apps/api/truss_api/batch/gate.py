"""Reproducible F6.2 acceptance drill for the approved local corpus."""

from __future__ import annotations

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import tempfile
import time
import tracemalloc

import fitz

from truss_api.audit import repository as audit_repository
from truss_api.audit.models import BoundingBox, FindingStatusUpdate, ManualFindingCreate
from truss_api.batch import repository as batch_repository
from truss_api.batch.worker import process_next_item
from truss_api.core.settings import Settings
from truss_api.db.connection import transaction
from truss_api.db.schema import initialize_database
from truss_api.projects import repository as projects_repository
from truss_api.projects.models import ProjectCreate, RevisionCreate
from truss_api.recovery.backup import create_backup, verify_backup
from truss_api.recovery.operations import import_document, run_sheet_map_operation
from truss_api.recovery.restore import restore_backup
from truss_api.sheetmap.elements.registry import build_revision_registry


COUNT_TABLES = (
    "documents",
    "sheets",
    "sheet_maps",
    "audit_runs",
    "findings",
    "processing_operations",
    "batch_runs",
    "batch_items",
    "batch_run_events",
)


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _counts(settings: Settings) -> dict[str, int]:
    with transaction(settings) as connection:
        return {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in COUNT_TABLES
        }


def _drain(settings: Settings) -> int:
    processed = 0
    while process_next_item(settings):
        processed += 1
    return processed


def _fixture_pdf() -> bytes:
    document = fitz.open()
    for index in range(2):
        page = document.new_page(width=842, height=595)
        page.insert_text((72, 72), f"FIXTURE CONTROLADA {index + 1}")
        page.insert_text((650, 550), f"FX-{index + 1}")
    buffer = BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def _run_failure_fixture(root: Path) -> dict[str, object]:
    settings = Settings(data_dir=root / "data", backup_dir=root / "backups")
    initialize_database(settings)
    project = projects_repository.create_project(ProjectCreate(name="Fixture F6.2"), settings)
    revision = projects_repository.create_revision(
        str(project["id"]), RevisionCreate(notes="Falha controlada"), settings
    )
    import_document(
        project_id=str(project["id"]),
        revision_id=str(revision["id"]),
        filename="fixture-controlada.pdf",
        content=_fixture_pdf(),
        mime_type="application/pdf",
        settings=settings,
        build_sheet_maps=False,
    )
    batch = batch_repository.create_batch_run(
        project_id=str(project["id"]),
        revision_id=str(revision["id"]),
        mode="local_deterministic",
        config={"fixture": True, "worker_concurrency": 1},
        settings=settings,
    )
    failed = batch_repository.claim_next_item(settings)
    assert failed is not None
    batch_repository.fail_item(
        str(failed["id"]),
        str(failed["run_token"]),
        settings,
        code="FIXTURE_FAILURE",
        message="Falha controlada para validar isolamento.",
    )
    processed = _drain(settings)
    final = batch_repository.get_batch_run(str(batch["id"]), settings)
    registry = build_revision_registry(str(revision["id"]), settings)
    items = batch_repository.list_batch_items(str(batch["id"]), settings)
    return {
        "real_corpus_sheet_count": 0,
        "synthetic_sheet_count": 2,
        "status": final["status"],
        "processed_after_failure": processed,
        "coverage_complete": registry["coverage_complete"],
        "mapped_sheet_count": registry["mapped_sheet_count"],
        "expected_sheet_count": registry["expected_sheet_count"],
        "failed": sum(item["status"] == "failed" for item in items),
        "skipped_dependency": sum(item["status"] == "skipped_dependency" for item in items),
        "completed": sum(item["status"] == "completed" for item in items),
    }


def run_gate(corpus_dir: Path) -> dict[str, object]:
    pdfs = sorted(corpus_dir.glob("*.pdf"))
    if not pdfs:
        raise RuntimeError(f"No PDF files found in {corpus_dir}")
    corpus = []
    for path in pdfs:
        with fitz.open(path) as document:
            corpus.append(
                {
                    "filename": path.name,
                    "pages": document.page_count,
                    "size_bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
    total_sheets = sum(int(item["pages"]) for item in corpus)
    if total_sheets != 84:
        raise RuntimeError(f"The approved real corpus must contain 84 pages, found {total_sheets}")

    started = time.perf_counter()
    tracemalloc.start()
    with tempfile.TemporaryDirectory(prefix="truss-f62-gate-") as temporary:
        root = Path(temporary)
        settings = Settings(data_dir=root / "real-data", backup_dir=root / "backups")
        initialize_database(settings)
        project = projects_repository.create_project(
            ProjectCreate(name="Gate F6.2 - 84 folhas reais"), settings
        )
        revision = projects_repository.create_revision(
            str(project["id"]), RevisionCreate(notes="Corpus real aprovado"), settings
        )

        intake_started = time.perf_counter()
        for path in pdfs:
            import_document(
                project_id=str(project["id"]),
                revision_id=str(revision["id"]),
                filename=path.name,
                content=path.read_bytes(),
                mime_type="application/pdf",
                settings=settings,
                build_sheet_maps=False,
            )
        intake_seconds = time.perf_counter() - intake_started
        before = _counts(settings)

        primary = batch_repository.create_batch_run(
            project_id=str(project["id"]),
            revision_id=str(revision["id"]),
            mode="local_deterministic",
            config={"worker_concurrency": 1, "visual_concurrency": 1, "gate": "84-real"},
            settings=settings,
        )
        processing_started = time.perf_counter()
        for _ in range(5):
            assert process_next_item(settings)
        abandoned = batch_repository.claim_next_item(settings)
        assert abandoned is not None
        interrupted_count = batch_repository.mark_running_batches_interrupted(settings)
        interrupted = batch_repository.get_batch_run(str(primary["id"]), settings)
        assert interrupted["status"] == "interrupted"
        batch_repository.retry_failures(str(primary["id"]), settings)
        processed_after_resume = _drain(settings)
        primary_final = batch_repository.get_batch_run(str(primary["id"]), settings)
        processing_seconds = time.perf_counter() - processing_started
        after_primary = _counts(settings)
        primary_items = batch_repository.list_batch_items(str(primary["id"]), settings, limit=500)

        feedback_created = False
        with transaction(settings) as connection:
            finding_row = connection.execute("SELECT id FROM findings ORDER BY created_at LIMIT 1").fetchone()
            first_sheet = connection.execute(
                "SELECT id, width_pt, height_pt FROM sheets ORDER BY created_at, page_index LIMIT 1"
            ).fetchone()
        if finding_row is None:
            finding = audit_repository.create_manual_finding(
                str(first_sheet["id"]),
                ManualFindingCreate(
                    category="gate_f62",
                    type="attention",
                    description="Achado manual do gate de persistencia.",
                    severity="low",
                    confidence=1.0,
                    bbox=BoundingBox(
                        x0=0,
                        y0=0,
                        x1=min(72, float(first_sheet["width_pt"])),
                        y1=min(72, float(first_sheet["height_pt"])),
                    ),
                    evidence=["fixture de feedback persistente"],
                ),
                settings,
            )
            finding_id = str(finding["id"])
            feedback_created = True
        else:
            finding_id = str(finding_row["id"])
        audit_repository.update_finding_status(
            finding_id,
            FindingStatusUpdate(
                status="rejected",
                rejection_reason="Feedback persistido durante o gate F6.2.",
            ),
            settings,
        )
        reopened_settings = Settings(data_dir=settings.data_dir, backup_dir=settings.backup_dir)
        with transaction(reopened_settings) as connection:
            reopened_feedback = connection.execute(
                "SELECT status, rejection_reason FROM findings WHERE id = ?", (finding_id,)
            ).fetchone()

        replay = batch_repository.create_batch_run(
            project_id=str(project["id"]),
            revision_id=str(revision["id"]),
            mode="local_deterministic",
            config={"worker_concurrency": 1, "visual_concurrency": 1, "gate": "cache-replay"},
            settings=settings,
        )
        replay_before = _counts(settings)
        replay_processed = _drain(settings)
        replay_after = _counts(settings)
        replay_final = batch_repository.get_batch_run(str(replay["id"]), settings)

        cancel_run = batch_repository.create_batch_run(
            project_id=str(project["id"]),
            revision_id=str(revision["id"]),
            mode="local_deterministic",
            config={"worker_concurrency": 1, "gate": "cancel"},
            settings=settings,
        )
        current = batch_repository.claim_next_item(settings)
        assert current is not None
        batch_repository.request_cancel(str(cancel_run["id"]), settings)
        result = run_sheet_map_operation(str(current["sheet_id"]), settings)
        batch_repository.complete_item(str(current["id"]), str(current["run_token"]), settings)
        cancel_final = batch_repository.get_batch_run(str(cancel_run["id"]), settings)
        cancel_items = batch_repository.list_batch_items(str(cancel_run["id"]), settings, limit=500)

        archive = create_backup(settings)
        manifest = verify_backup(archive)
        restored_path = restore_backup(archive, root / "restored-final")
        restored = Settings(data_dir=restored_path, backup_dir=root / "restored-backups")
        restored_counts = _counts(restored)
        fixture = _run_failure_fixture(root / "failure-fixture")
        _current, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        dedupe_tables = ("sheet_maps", "audit_runs", "findings")
        duplicate_delta = {
            table: replay_after[table] - replay_before[table] for table in dedupe_tables
        }
        report = {
            "schema": "truss-f62-gate-v0.1",
            "corpus": {
                "real_sheet_count": total_sheets,
                "files": corpus,
            },
            "limits": {
                "worker_concurrency": 1,
                "visual_concurrency": 1,
                "visual_enabled": False,
            },
            "metrics": {
                "intake_seconds": round(intake_seconds, 3),
                "primary_processing_seconds": round(processing_seconds, 3),
                "total_seconds": round(time.perf_counter() - started, 3),
                "python_tracemalloc_peak_bytes": peak_bytes,
                "retried_items": sum(int(item["attempt_count"]) > 1 for item in primary_items),
                "automatic_retries": 0,
                "explicit_resume_retries": sum(
                    int(item["attempt_count"]) > 1 for item in primary_items
                ),
            },
            "primary_run": {
                "id": primary["id"],
                "status": primary_final["status"],
                "phase_counts": primary_final["phase_counts"],
                "interrupted_workers": interrupted_count,
                "processed_after_resume": processed_after_resume,
                "counts_before": before,
                "counts_after": after_primary,
            },
            "cache_replay": {
                "id": replay["id"],
                "status": replay_final["status"],
                "processed_items": replay_processed,
                "artifact_delta": duplicate_delta,
                "no_artifact_duplicates": all(value == 0 for value in duplicate_delta.values()),
            },
            "cancel_drill": {
                "id": cancel_run["id"],
                "status": cancel_final["status"],
                "current_result_reused": bool(result.get("id")),
                "completed_items": sum(item["status"] == "completed" for item in cancel_items),
                "cancelled_items": sum(item["status"] == "cancelled" for item in cancel_items),
            },
            "feedback_reopen": {
                "finding_id": finding_id,
                "manual_finding_created": feedback_created,
                "status": str(reopened_feedback["status"]),
                "reason_preserved": bool(reopened_feedback["rejection_reason"]),
            },
            "recovery": {
                "backup_schema": manifest["schema"],
                "backup_verified": True,
                "restored_integrity": restored_counts == _counts(settings),
                "restored_counts": restored_counts,
            },
            "failure_fixture": fixture,
        }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Executa o gate real da F6.2")
    parser.add_argument("--corpus", type=Path, default=Path("docs/projeto_base"))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = run_gate(args.corpus.resolve())
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
