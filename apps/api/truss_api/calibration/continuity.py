"""Medicao descartavel da continuidade explicita de pilares da F3.2."""

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from truss_api.audit.orchestrator import run_deterministic_audit
from truss_api.core.settings import Settings
from truss_api.db.connection import transaction
from truss_api.db.schema import initialize_database
from truss_api.documents import repository as documents_repository
from truss_api.documents.importer import prepare_pdf_storage
from truss_api.projects import repository as projects_repository
from truss_api.projects.models import ProjectCreate, RevisionCreate
from truss_api.sheetmap.builder import build_sheet_map_for_document
from truss_api.sheetmap.elements.registry import build_revision_registry


@dataclass(frozen=True)
class ContinuityMeasurement:
    name: str
    pages: int
    lifecycle_by_state: dict[str, int]
    associated_lifecycle_by_state: dict[str, int]
    form_levels: int
    level_pairs_by_provenance: dict[str, int]
    ambiguities: int
    outcomes: dict[str, int]
    candidate_findings: tuple[dict[str, object], ...]
    artifact_bytes: int
    elapsed_seconds: float


def measure_continuity(pdf_path: Path) -> ContinuityMeasurement:
    started = perf_counter()
    with TemporaryDirectory(prefix="truss-f32-") as temporary:
        settings = Settings(data_dir=Path(temporary) / "data")
        initialize_database(settings)
        project = projects_repository.create_project(
            ProjectCreate(name=f"F3.2 Calibration {pdf_path.stem}"), settings
        )
        revision = projects_repository.create_revision(
            str(project["id"]), RevisionCreate(notes="F3.2 disposable measurement"), settings
        )
        prepared = prepare_pdf_storage(
            content=pdf_path.read_bytes(),
            filename=pdf_path.name,
            project_id=str(project["id"]),
            revision_id=str(revision["id"]),
            settings=settings,
        )
        document = documents_repository.create_document_from_prepared_pdf(
            project_id=str(project["id"]),
            revision_id=str(revision["id"]),
            prepared_pdf=prepared,
            settings=settings,
        )
        maps = build_sheet_map_for_document(str(document["id"]), settings)
        registry = build_revision_registry(str(revision["id"]), settings)

        for sheet in document["sheets"]:
            run_deterministic_audit(str(sheet["id"]), settings)

        with transaction(settings) as connection:
            outcomes = connection.execute(
                """
                SELECT outcome, COUNT(*) AS total
                FROM rule_evaluations
                WHERE rule_id = 'cross_sheet.pillar_lifecycle_continuity'
                  AND sheet_id IN (SELECT id FROM sheets WHERE revision_id = ?)
                GROUP BY outcome
                """,
                (str(revision["id"]),),
            ).fetchall()
            findings = connection.execute(
                """
                SELECT element_code, description, confidence, sheet_id, evidence_json
                FROM findings
                WHERE revision_id = ?
                  AND rule_id = 'cross_sheet.pillar_lifecycle_continuity'
                ORDER BY element_code, sheet_id
                """,
                (str(revision["id"]),),
            ).fetchall()

        lifecycle = Counter()
        associated = Counter()
        for occurrence in registry["occurrences"]:
            state = str((occurrence.get("attributes") or {}).get("lifecycle_state") or "")
            if not state:
                continue
            lifecycle[state] += 1
            if occurrence.get("view_id") and occurrence.get("technical_scope") == "formas":
                associated[state] += 1

        pair_provenance = Counter(
            str(pair["provenance"]) for pair in registry["form_level_pairs"]
        )
        artifact_bytes = sum(
            path.stat().st_size
            for path in settings.geometry_dir.rglob("*")
            if path.is_file()
        )

    return ContinuityMeasurement(
        name=pdf_path.name,
        pages=len(maps),
        lifecycle_by_state=dict(sorted(lifecycle.items())),
        associated_lifecycle_by_state=dict(sorted(associated.items())),
        form_levels=len(registry["form_levels"]),
        level_pairs_by_provenance=dict(sorted(pair_provenance.items())),
        ambiguities=len(registry["form_level_ambiguities"]),
        outcomes={str(row["outcome"]): int(row["total"]) for row in outcomes},
        candidate_findings=tuple(dict(row) for row in findings),
        artifact_bytes=artifact_bytes,
        elapsed_seconds=perf_counter() - started,
    )

