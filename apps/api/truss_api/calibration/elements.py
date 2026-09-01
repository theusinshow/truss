"""Medicao F3 em uma revisao isolada e descartavel.

Cada PDF e tratado como uma revisao completa em banco temporario. Isso exercita
o mesmo import, snapshots, registry, cache e auditoria usados pelo produto sem
alterar o banco de trabalho nem os PDFs do acervo aprovado.
"""

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


@dataclass(frozen=True)
class ElementMeasurement:
    name: str
    pages: int
    elements_by_kind: dict[str, int]
    elements_by_scope: dict[str, int]
    ambiguous_elements: int
    cross_sheet_outcomes: dict[str, int]
    candidate_findings: tuple[dict[str, object], ...]
    artifact_bytes: int
    elapsed_seconds: float


def measure_pdf(pdf_path: Path) -> ElementMeasurement:
    started = perf_counter()
    with TemporaryDirectory(prefix="truss-f3-") as temporary:
        settings = Settings(data_dir=Path(temporary) / "data")
        initialize_database(settings)
        project = projects_repository.create_project(
            ProjectCreate(name=f"Calibration {pdf_path.stem}"), settings
        )
        revision = projects_repository.create_revision(
            str(project["id"]), RevisionCreate(notes="F3 disposable measurement"), settings
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

        for sheet in document["sheets"]:
            run_deterministic_audit(str(sheet["id"]), settings)

        with transaction(settings) as connection:
            elements = connection.execute(
                """
                SELECT element_kind, COALESCE(technical_scope, 'ambiguous') AS scope,
                       attributes_json
                FROM sheet_elements
                WHERE sheet_map_id IN (
                    SELECT id FROM sheet_maps WHERE revision_id = ?
                )
                """,
                (str(revision["id"]),),
            ).fetchall()
            outcomes = connection.execute(
                """
                SELECT outcome, COUNT(*) AS total
                FROM rule_evaluations
                WHERE rule_id = 'cross_sheet.pillar_has_detail'
                  AND sheet_id IN (SELECT id FROM sheets WHERE revision_id = ?)
                GROUP BY outcome
                """,
                (str(revision["id"]),),
            ).fetchall()
            findings = connection.execute(
                """
                SELECT f.element_code, f.description, f.confidence, f.sheet_id,
                       sm.sheet_code, sm.sheet_code_raw
                FROM findings f
                LEFT JOIN sheet_maps sm ON sm.id = f.sheet_map_id
                WHERE f.revision_id = ?
                  AND f.rule_id = 'cross_sheet.pillar_has_detail'
                ORDER BY COALESCE(sm.sheet_code, sm.sheet_code_raw), f.element_code
                """,
                (str(revision["id"]),),
            ).fetchall()

        by_kind = Counter(str(row["element_kind"]) for row in elements)
        by_scope = Counter(str(row["scope"]) for row in elements)
        ambiguous = by_scope.get("ambiguous", 0)
        artifact_bytes = sum(
            path.stat().st_size
            for path in settings.geometry_dir.rglob("*")
            if path.is_file()
        )

    return ElementMeasurement(
        name=pdf_path.name,
        pages=len(maps),
        elements_by_kind=dict(sorted(by_kind.items())),
        elements_by_scope=dict(sorted(by_scope.items())),
        ambiguous_elements=ambiguous,
        cross_sheet_outcomes={str(row["outcome"]): int(row["total"]) for row in outcomes},
        candidate_findings=tuple(dict(row) for row in findings),
        artifact_bytes=artifact_bytes,
        elapsed_seconds=perf_counter() - started,
    )

