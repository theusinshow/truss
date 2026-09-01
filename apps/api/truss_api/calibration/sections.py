"""Medicao descartavel das secoes explicitas de pilares da F3.3."""

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import fitz

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
from truss_api.sheetmap.elements.sections import parse_section_span
from truss_api.sheetmap.primitives import extract_page


RULE_ID = "cross_sheet.pillar_section_transition"


@dataclass(frozen=True)
class SectionMeasurement:
    name: str
    pages: int
    # Spans que o extrator aceitaria como notacao `a x b`, antes de qualquer
    # associacao espacial. E o denominador que mostra quanto o contrato recusa.
    section_candidates: int
    associated_sections: int
    ambiguous_associations: int
    resolved_view_codes: int
    ambiguous_view_codes: int
    sections_by_provenance: dict[str, int]
    form_level_pairs: int
    outcomes: dict[str, int]
    attention_points: tuple[dict[str, object], ...]
    artifact_bytes: int
    elapsed_seconds: float


def count_section_candidates(pdf_path: Path) -> int:
    document = fitz.open(pdf_path)
    try:
        return sum(
            1
            for page in document
            for span in extract_page(page).spans
            if parse_section_span(span) is not None
        )
    finally:
        document.close()


def measure_sections(pdf_path: Path) -> SectionMeasurement:
    started = perf_counter()
    candidates = count_section_candidates(pdf_path)

    with TemporaryDirectory(prefix="truss-f33-") as temporary:
        settings = Settings(data_dir=Path(temporary) / "data")
        initialize_database(settings)
        project = projects_repository.create_project(
            ProjectCreate(name=f"F3.3 Calibration {pdf_path.stem}"), settings
        )
        revision = projects_repository.create_revision(
            str(project["id"]),
            RevisionCreate(notes="F3.3 disposable measurement"),
            settings,
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
                WHERE rule_id = ?
                  AND sheet_id IN (SELECT id FROM sheets WHERE revision_id = ?)
                GROUP BY outcome
                """,
                (RULE_ID, str(revision["id"])),
            ).fetchall()
            findings = connection.execute(
                """
                SELECT element_code, description, confidence, sheet_id, evidence_json
                FROM findings
                WHERE revision_id = ?
                  AND rule_id = ?
                ORDER BY element_code, sheet_id
                """,
                (str(revision["id"]), RULE_ID),
            ).fetchall()

        associated = 0
        ambiguous = 0
        provenance = Counter()
        for occurrence in registry["occurrences"]:
            attributes = occurrence.get("attributes") or {}
            status = str(attributes.get("section_association_status") or "")
            if status == "matched":
                associated += 1
                raw = str(attributes.get("section_provenance") or "")
                provenance[raw.rsplit(":", 1)[-1] or "desconhecida"] += 1
            elif status == "ambiguous":
                ambiguous += 1

        sections = registry["pillar_sections"]
        artifact_bytes = sum(
            path.stat().st_size
            for path in settings.geometry_dir.rglob("*")
            if path.is_file()
        )

    return SectionMeasurement(
        name=pdf_path.name,
        pages=len(maps),
        section_candidates=candidates,
        associated_sections=associated,
        ambiguous_associations=ambiguous,
        resolved_view_codes=sum(
            1 for item in sections if item.get("status") == "resolved"
        ),
        ambiguous_view_codes=sum(
            1 for item in sections if item.get("status") == "ambiguous"
        ),
        sections_by_provenance=dict(sorted(provenance.items())),
        form_level_pairs=len(registry["form_level_pairs"]),
        outcomes={str(row["outcome"]): int(row["total"]) for row in outcomes},
        attention_points=tuple(dict(row) for row in findings),
        artifact_bytes=artifact_bytes,
        elapsed_seconds=perf_counter() - started,
    )
