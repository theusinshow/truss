import json
from pathlib import Path

import pytest

from truss_api.audit import repository as audit_repository
from truss_api.audit.models import FindingStatusUpdate
from truss_api.audit.orchestrator import audit_cache_key, run_deterministic_audit
from truss_api.core.settings import Settings
from truss_api.db.connection import transaction
from truss_api.db.schema import initialize_database
from truss_api.documents import repository as documents_repository
from truss_api.documents.importer import prepare_pdf_storage
from truss_api.projects import repository as projects_repository
from truss_api.projects.models import ProjectCreate, RevisionCreate
from truss_api.rules.models import SCOPE_GENERAL, SCOPE_PERSONAL
from truss_api.sheetmap.builder import build_sheet_map_for_document
from tests.factories import make_forms_sheet_pdf_bytes


GOLDEN = Path(__file__).parent / "golden" / "forms_sheet_evaluations.json"


@pytest.fixture()
def sheet(tmp_path: Path) -> tuple[Settings, str]:
    settings = Settings(data_dir=tmp_path / "data")
    initialize_database(settings)
    project = projects_repository.create_project(ProjectCreate(name="P"), settings)
    revision = projects_repository.create_revision(
        str(project["id"]), RevisionCreate(notes="R"), settings
    )
    prepared = prepare_pdf_storage(
        content=make_forms_sheet_pdf_bytes(),
        filename="formas.pdf",
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
    build_sheet_map_for_document(str(document["id"]), settings)
    return settings, str(document["sheets"][0]["id"])


def _break_scale(settings: Settings) -> None:
    with transaction(settings) as connection:
        connection.execute("UPDATE sheet_views SET declared_scale = NULL")


def test_clean_sheet_produces_zero_findings_and_a_coverage_summary(
    sheet: tuple[Settings, str],
) -> None:
    """A folha sintetica esta completa: nada deve ser apontado, e o fallback sumiu."""
    settings, sheet_id = sheet

    run = run_deterministic_audit(sheet_id, settings)

    assert run["findings"] == []
    assert run["coverage"]["evaluated"] > 0
    assert run["coverage"]["passed"] > 0
    assert run["coverage"]["failed"] == 0


def test_every_automatic_finding_carries_full_traceability(
    sheet: tuple[Settings, str],
) -> None:
    settings, sheet_id = sheet
    _break_scale(settings)

    run = run_deterministic_audit(sheet_id, settings)

    assert run["findings"]
    for finding in run["findings"]:
        assert finding["rule_id"]
        assert finding["rule_version"]
        assert finding["rule_scope"] in {SCOPE_GENERAL, SCOPE_PERSONAL}
        assert finding["view_id"]
        assert finding["source_layer"] == "deterministic"
        assert finding["dedupe_key"]
        assert finding["evidence"]
        assert finding["bbox"]["x1"] > finding["bbox"]["x0"]


def test_general_and_personal_findings_do_not_collapse_into_one(
    sheet: tuple[Settings, str],
) -> None:
    """Os dois packs tem `forms.view.level_declared` sobre o mesmo alvo.

    Sem o escopo na chave de deduplicacao, a preferencia pessoal seria engolida
    pela regra geral e o proprietario nunca veria a sua propria exigencia.
    """
    settings, sheet_id = sheet
    with transaction(settings) as connection:
        connection.execute("UPDATE sheet_views SET level_raw = NULL")

    run = run_deterministic_audit(sheet_id, settings)

    levels = [f for f in run["findings"] if f["rule_id"] == "forms.view.level_declared"]
    assert {f["rule_scope"] for f in levels} == {SCOPE_GENERAL, SCOPE_PERSONAL}
    assert len({f["dedupe_key"] for f in levels}) == len(levels)

    general = next(f for f in levels if f["rule_scope"] == SCOPE_GENERAL)
    personal = next(f for f in levels if f["rule_scope"] == SCOPE_PERSONAL)
    assert general["severity"] == "low" and general["type"] == "attention"
    assert personal["severity"] == "high" and personal["type"] == "missing_information"


def test_rerunning_the_audit_does_not_duplicate_findings(
    sheet: tuple[Settings, str],
) -> None:
    settings, sheet_id = sheet
    _break_scale(settings)

    first = run_deterministic_audit(sheet_id, settings)
    audit_repository.clear_audit_cache(settings)
    second = run_deterministic_audit(sheet_id, settings)

    assert len(second["findings"]) == len(first["findings"])
    with transaction(settings) as connection:
        total = connection.execute(
            "SELECT COUNT(*) FROM findings WHERE sheet_id = ? AND origin = 'ai'",
            (sheet_id,),
        ).fetchone()[0]
    assert total == len(first["findings"])


def test_cache_key_changes_when_the_rule_pack_changes() -> None:
    base = dict(
        document_hash="d",
        extractor_version="extract-v0.2",
        pipeline_version="audit-v0.2",
        snapshot_hash="s",
        rule_pack_id="formas_geral+formas_pessoal",
        rule_pack_version="1.0.0+1.0.0",
    )

    assert audit_cache_key(**base) != audit_cache_key(**{**base, "rule_pack_version": "1.0.1"})
    assert audit_cache_key(**base) != audit_cache_key(**{**base, "snapshot_hash": "other"})
    assert audit_cache_key(**base) != audit_cache_key(**{**base, "registry_hash": "other"})
    assert audit_cache_key(**base) == audit_cache_key(**base)


def test_human_validated_findings_are_never_replaced(sheet: tuple[Settings, str]) -> None:
    settings, sheet_id = sheet
    _break_scale(settings)

    first = run_deterministic_audit(sheet_id, settings)
    finding_id = str(first["findings"][0]["id"])
    audit_repository.update_finding_status(
        finding_id,
        FindingStatusUpdate(status="confirmed"),
        settings,
    )
    audit_repository.clear_audit_cache(settings)

    run_deterministic_audit(sheet_id, settings)

    with transaction(settings) as connection:
        row = connection.execute(
            "SELECT status FROM findings WHERE id = ?", (finding_id,)
        ).fetchone()
    assert str(row["status"]) == "confirmed"


def test_rule_evaluations_match_the_golden_file(sheet: tuple[Settings, str]) -> None:
    """Congela outcome e alvo por regra. Regenerar so com mudanca intencional."""
    settings, sheet_id = sheet
    _break_scale(settings)

    run_deterministic_audit(sheet_id, settings)

    with transaction(settings) as connection:
        rows = connection.execute(
            """
            SELECT rule_id, rule_version, rule_pack_id, rule_scope, target_kind, outcome
            FROM rule_evaluations
            ORDER BY rule_pack_id, rule_id, target_kind, outcome
            """
        ).fetchall()

    actual = [
        {
            "rule_id": str(row["rule_id"]),
            "rule_version": str(row["rule_version"]),
            "rule_pack_id": str(row["rule_pack_id"]),
            "rule_scope": str(row["rule_scope"]),
            "target_kind": str(row["target_kind"]),
            "outcome": str(row["outcome"]),
        }
        for row in rows
    ]

    if not GOLDEN.exists():
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(actual, indent=2), encoding="utf-8")
        pytest.skip("golden gerado; rodar de novo para comparar")

    assert actual == json.loads(GOLDEN.read_text(encoding="utf-8"))
