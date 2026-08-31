from collections.abc import Iterator
from io import BytesIO
from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient

from truss_api.core.settings import Settings, get_settings
from truss_api.db.schema import initialize_database
from truss_api.main import app
from truss_api.projects import repository
from truss_api.projects.models import ProjectCreate, RevisionCreate
from tests.factories import make_structural_pdf_bytes


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


def make_pdf_bytes(text: str = "FORMA PAVIMENTO 1") -> bytes:
    document = fitz.open()
    page = document.new_page(width=842, height=595)
    page.insert_text((72, 72), text)
    buffer = BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def create_imported_sheet(client: TestClient, settings: Settings) -> str:
    """Folha de formas sem nenhuma view declarada.

    O carimbo da pagina 1 da prancha sintetica declara PLANTA DE FORMAS, entao
    os rule packs carregam; e ela nao declara escala nenhuma, entao o detector
    nao produz view e a regra de composicao tem o que apontar.
    """
    project = repository.create_project(ProjectCreate(name="Audit Project"), settings)
    revision = repository.create_revision(
        str(project["id"]),
        RevisionCreate(notes="Audit revision"),
        settings,
    )
    response = client.post(
        f"/projects/{project['id']}/revisions/{revision['id']}/documents",
        files={"file": ("forma.pdf", make_structural_pdf_bytes(), "application/pdf")},
    )
    return str(response.json()["sheets"][1]["id"])


def test_deterministic_audit_creates_structured_findings(
    client: TestClient,
    settings: Settings,
) -> None:
    """A folha nao tem view alguma, entao a regra de composicao aponta isso.

    O finding de fallback foi removido: quando nada e apontado, o resultado e
    zero findings mais a cobertura, nunca um achado artificial dizendo que a
    auditoria rodou.
    """
    sheet_id = create_imported_sheet(client, settings)

    response = client.post(f"/sheets/{sheet_id}/audit-runs")

    assert response.status_code == 201
    audit_run = response.json()
    assert audit_run["status"] == "completed"
    assert audit_run["pipeline_version"] == "deterministic-v0.2"
    assert audit_run["coverage"]["evaluated"] > 0

    finding = next(
        f for f in audit_run["findings"] if f["rule_id"] == "forms.sheet.has_main_view"
    )
    assert finding["bbox"]["x0"] < finding["bbox"]["x1"]
    assert finding["bbox"]["y0"] < finding["bbox"]["y1"]
    assert finding["status"] == "pending"
    assert finding["origin"] == "ai"
    assert finding["source_layer"] == "deterministic"
    assert finding["rule_scope"] == "general"
    assert finding["technical_scope"] == "formas"


def test_deterministic_audit_uses_cache_for_same_sheet(
    client: TestClient,
    settings: Settings,
) -> None:
    sheet_id = create_imported_sheet(client, settings)

    first_response = client.post(f"/sheets/{sheet_id}/audit-runs")
    second_response = client.post(f"/sheets/{sheet_id}/audit-runs")

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert second_response.json()["id"] == first_response.json()["id"]


def test_audit_exposes_a_technical_scope_without_rule_pack(
    client: TestClient,
    settings: Settings,
) -> None:
    project = repository.create_project(ProjectCreate(name="Armatures"), settings)
    revision = repository.create_revision(
        str(project["id"]), RevisionCreate(notes="R"), settings
    )
    imported = client.post(
        f"/projects/{project['id']}/revisions/{revision['id']}/documents",
        files={"file": ("armaduras.pdf", make_structural_pdf_bytes(), "application/pdf")},
    ).json()
    sheet_id = str(imported["sheets"][2]["id"])

    run = client.post(f"/sheets/{sheet_id}/audit-runs").json()

    assert run["coverage"]["evaluated"] == 0
    assert run["coverage"]["technical_scopes"] == ["armaduras"]
    assert run["coverage"]["covered_scopes"] == []
    assert run["coverage"]["uncovered_scopes"] == ["armaduras"]


def test_finding_feedback_is_persisted(client: TestClient, settings: Settings) -> None:
    sheet_id = create_imported_sheet(client, settings)
    audit_run = client.post(f"/sheets/{sheet_id}/audit-runs").json()
    assert audit_run["findings"], "a folha sem views precisa gerar ao menos um achado"
    finding_id = audit_run["findings"][0]["id"]

    response = client.patch(
        f"/findings/{finding_id}",
        json={"status": "rejected", "rejection_reason": "Nao se aplica a este padrao."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "rejected"
    assert payload["rejection_reason"] == "Nao se aplica a este padrao."


def test_manual_finding_is_persisted_with_human_origin(
    client: TestClient,
    settings: Settings,
) -> None:
    sheet_id = create_imported_sheet(client, settings)

    response = client.post(
        f"/sheets/{sheet_id}/findings",
        json={
            "category": "composition",
            "type": "attention",
            "description": "Texto sobreposto a uma linha de cota.",
            "severity": "high",
            "confidence": 1,
            "bbox": {"x0": 10, "y0": 20, "x1": 120, "y1": 160},
            "evidence": ["Marcado manualmente no viewer."],
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["origin"] == "human"
    assert payload["bbox"] == {"x0": 10.0, "y0": 20.0, "x1": 120.0, "y1": 160.0}

    findings = client.get(f"/sheets/{sheet_id}/findings").json()
    assert any(finding["id"] == payload["id"] for finding in findings)
