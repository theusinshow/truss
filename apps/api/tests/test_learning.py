from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from truss_api.core.settings import Settings, get_settings
from truss_api.db.connection import transaction
from truss_api.db.schema import initialize_database
from truss_api.main import app


NOW = "2026-09-01T12:00:00+00:00"


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


def seed_sheet(settings: Settings, index: int, *, sheet_type: str = "formas") -> dict[str, str]:
    ids = {
        "project_id": f"project-{index}",
        "revision_id": f"revision-{index}",
        "document_id": f"document-{index}",
        "sheet_id": f"sheet-{index}",
        "sheet_map_id": f"sheet-map-{index}",
    }
    with transaction(settings) as connection:
        connection.execute(
            "INSERT INTO projects VALUES (?, ?, '', ?, ?)",
            (ids["project_id"], f"Projeto {index}", NOW, NOW),
        )
        connection.execute(
            """
            INSERT INTO revisions (
                id, project_id, revision_code, notes, source_type, created_at
            ) VALUES (?, ?, ?, '', 'manual', ?)
            """,
            (ids["revision_id"], ids["project_id"], f"R{index:02d}", NOW),
        )
        connection.execute(
            """
            INSERT INTO documents (
                id, project_id, revision_id, original_filename, stored_file_path,
                content_hash, mime_type, file_size_bytes, page_count, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'application/pdf', 100, 1, ?)
            """,
            (
                ids["document_id"],
                ids["project_id"],
                ids["revision_id"],
                f"estrutura-{index}.pdf",
                f"originals/{index}.pdf",
                f"hash-{index}",
                NOW,
            ),
        )
        connection.execute(
            """
            INSERT INTO sheets (
                id, document_id, project_id, revision_id, page_index, sheet_number,
                width_pt, height_pt, rotation, label, created_at
            ) VALUES (?, ?, ?, ?, 0, ?, 1000, 800, 0, ?, ?)
            """,
            (
                ids["sheet_id"],
                ids["document_id"],
                ids["project_id"],
                ids["revision_id"],
                index,
                f"Folha {index}",
                NOW,
            ),
        )
        connection.execute(
            """
            INSERT INTO sheet_maps (
                id, sheet_id, project_id, revision_id, pipeline_version, status,
                geometry_path, sheet_code, sheet_type, paper_format, orientation,
                title_block_json, built_at
            ) VALUES (?, ?, ?, ?, 'sheetmap-test', 'completed', ?, ?, ?, 'A1',
                      'landscape', '{}', ?)
            """,
            (
                ids["sheet_map_id"],
                ids["sheet_id"],
                ids["project_id"],
                ids["revision_id"],
                f"geometry/{index}.json",
                f"EST-{index:04d}-A",
                sheet_type,
                NOW,
            ),
        )
    return ids


def seed_finding(
    settings: Settings,
    context: dict[str, str],
    finding_id: str,
    *,
    origin: str = "ai",
    status: str = "rejected",
    rule_id: str | None = "forms.sheet.has_main_view",
    description: str = "Vista principal ausente.",
    category: str = "composition",
    finding_type: str = "attention",
) -> None:
    with transaction(settings) as connection:
        connection.execute(
            """
            INSERT INTO findings (
                id, audit_run_id, sheet_id, document_id, project_id, revision_id,
                category, type, description, severity, confidence,
                x0, y0, x1, y1, evidence_json, origin, status, rejection_reason,
                created_at, updated_at, rule_id, rule_version, rule_scope,
                sheet_map_id, source_layer, dedupe_key, technical_scope
            ) VALUES (
                ?, NULL, ?, ?, ?, ?, ?, ?, ?, 'medium', 0.9,
                10, 20, 110, 120, '[]', ?, ?, ?, ?, ?, ?, '1.0', 'general',
                ?, ?, ?, 'formas'
            )
            """,
            (
                finding_id,
                context["sheet_id"],
                context["document_id"],
                context["project_id"],
                context["revision_id"],
                category,
                finding_type,
                description,
                origin,
                status,
                "Padrao do proprietario." if status == "rejected" else None,
                NOW,
                NOW,
                rule_id,
                context["sheet_map_id"],
                "deterministic" if origin == "ai" else "human",
                f"dedupe-{finding_id}" if origin == "ai" else None,
            ),
        )


def test_rejection_proposal_is_derived_without_writing(client: TestClient, settings: Settings) -> None:
    first = seed_sheet(settings, 1)
    second = seed_sheet(settings, 2)
    seed_finding(settings, first, "finding-1")
    seed_finding(settings, second, "finding-2")

    with transaction(settings) as connection:
        before = connection.execute(
            "SELECT COUNT(*) AS count FROM learning_proposal_decisions"
        ).fetchone()["count"]

    response = client.get("/learning/proposals")

    assert response.status_code == 200
    proposals = response.json()
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal["proposal_kind"] == "suppress_rule"
    assert proposal["state"] == "pending"
    assert proposal["threshold_reached"] is True
    assert proposal["rejected_count"] == 2
    assert proposal["distinct_sheet_count"] == 2
    assert proposal["observed_ratio"] == 1
    assert proposal["evidence"][0]["bbox"] == {
        "x0": 10,
        "y0": 20,
        "x1": 110,
        "y1": 120,
    }
    assert proposal["evidence"][0]["project_name"].startswith("Projeto")

    with transaction(settings) as connection:
        after = connection.execute(
            "SELECT COUNT(*) AS count FROM learning_proposal_decisions"
        ).fetchone()["count"]
    assert before == after == 0


def test_conflicting_feedback_stays_below_ratio(client: TestClient, settings: Settings) -> None:
    contexts = [seed_sheet(settings, index) for index in (1, 2, 3)]
    seed_finding(settings, contexts[0], "finding-1", status="rejected")
    seed_finding(settings, contexts[1], "finding-2", status="rejected")
    seed_finding(settings, contexts[2], "finding-3", status="confirmed")

    assert client.get("/learning/proposals").json() == []
    proposal = client.get("/learning/proposals?include_insufficient=true").json()[0]
    assert proposal["proposal_kind"] == "suppress_rule"
    assert proposal["state"] == "insufficient"
    assert proposal["observed_ratio"] == pytest.approx(2 / 3)


def test_sheet_types_never_share_a_learning_key(
    client: TestClient,
    settings: Settings,
) -> None:
    forms = [seed_sheet(settings, index, sheet_type="formas") for index in (1, 2)]
    locations = [seed_sheet(settings, index, sheet_type="locacao") for index in (3, 4)]
    for index, context in enumerate([*forms, *locations], start=1):
        seed_finding(settings, context, f"finding-{index}")

    proposals = client.get("/learning/proposals").json()

    assert len(proposals) == 2
    assert {item["sheet_type"] for item in proposals} == {"formas", "locacao"}
    assert len({item["stable_key"] for item in proposals}) == 2


def test_existing_inline_preference_is_not_proposed_again(
    client: TestClient,
    settings: Settings,
) -> None:
    first = seed_sheet(settings, 1)
    second = seed_sheet(settings, 2)
    seed_finding(settings, first, "finding-1")
    seed_finding(settings, second, "finding-2")
    preference = client.post(
        "/findings/finding-1/rule-preferences",
        json={"reason": "Aprovada diretamente no viewer."},
    ).json()

    proposal = client.get("/learning/proposals").json()[0]

    assert proposal["state"] == "approved"
    assert proposal["decision"] is None
    assert proposal["active_preference_id"] == preference["id"]


def test_approved_suppression_is_atomic_locatable_and_revocable(
    client: TestClient,
    settings: Settings,
) -> None:
    first = seed_sheet(settings, 1)
    second = seed_sheet(settings, 2)
    seed_finding(settings, first, "finding-1")
    seed_finding(settings, second, "finding-2")
    proposal = client.get("/learning/proposals").json()[0]

    approved = client.post(
        f"/learning/proposals/{proposal['stable_key']}/decisions",
        json={"decision": "approved", "reason": "Regra nao se aplica a estas formas."},
    )

    assert approved.status_code == 201
    payload = approved.json()
    assert payload["state"] == "approved"
    assert payload["decision"]["evidence_count"] == 2
    assert payload["decision"]["preference_active"] is True
    preference_id = payload["decision"]["preference_id"]
    preferences = client.get("/rule-preferences").json()
    assert [item["id"] for item in preferences] == [preference_id]
    assert preferences[0]["source"]["finding_id"] in {"finding-1", "finding-2"}
    assert preferences[0]["source"]["sheet_code"].startswith("EST-")
    assert client.get(f"/sheets/{first['sheet_id']}/findings").json()[0]["suppressed"] is True

    with transaction(settings) as connection:
        snapshot_count = connection.execute(
            "SELECT COUNT(*) AS count FROM learning_proposal_evidence"
        ).fetchone()["count"]
    assert snapshot_count == 2

    revoked = client.delete(
        f"/learning/proposal-decisions/{payload['decision']['id']}"
    )
    assert revoked.status_code == 200
    assert revoked.json()["state"] == "pending"
    assert client.get(f"/sheets/{first['sheet_id']}/findings").json()[0]["suppressed"] is False
    history = client.get("/rule-preferences?status=revoked").json()
    assert history[0]["id"] == preference_id
    assert history[0]["source"]["bbox"]["x0"] == 10


def test_confirmed_rule_proposal_has_no_runtime_effect(client: TestClient, settings: Settings) -> None:
    first = seed_sheet(settings, 1)
    second = seed_sheet(settings, 2)
    seed_finding(settings, first, "finding-1", status="confirmed")
    seed_finding(settings, first, "finding-2", status="confirmed")
    seed_finding(settings, second, "finding-3", status="confirmed")

    proposal = client.get("/learning/proposals").json()[0]
    assert proposal["proposal_kind"] == "retain_rule"
    approved = client.post(
        f"/learning/proposals/{proposal['stable_key']}/decisions",
        json={"decision": "approved", "reason": "Regra confirmada no uso diario."},
    ).json()

    assert approved["effect"] == "calibration_only"
    assert approved["decision"]["preference_id"] is None
    assert client.get("/rule-preferences").json() == []


def test_active_decision_keeps_its_evidence_snapshot_visible(
    client: TestClient,
    settings: Settings,
) -> None:
    first = seed_sheet(settings, 1)
    second = seed_sheet(settings, 2)
    seed_finding(settings, first, "finding-1")
    seed_finding(settings, second, "finding-2")
    proposal = client.get("/learning/proposals").json()[0]
    approved = client.post(
        f"/learning/proposals/{proposal['stable_key']}/decisions",
        json={"decision": "approved", "reason": "Manter a decisao auditavel."},
    ).json()

    with transaction(settings) as connection:
        connection.execute(
            "UPDATE findings SET status = 'pending', rejection_reason = NULL"
        )

    proposals = client.get("/learning/proposals").json()

    assert len(proposals) == 1
    assert proposals[0]["state"] == "approved"
    assert proposals[0]["decision"]["id"] == approved["decision"]["id"]
    assert proposals[0]["decision"]["evidence_count"] == 2
    assert {item["signal_kind"] for item in proposals[0]["evidence"]} == {"rejected"}


def test_duplicate_decision_is_idempotent_and_conflicting_decision_is_rejected(
    client: TestClient,
    settings: Settings,
) -> None:
    first = seed_sheet(settings, 1)
    second = seed_sheet(settings, 2)
    seed_finding(settings, first, "finding-1")
    seed_finding(settings, second, "finding-2")
    proposal = client.get("/learning/proposals").json()[0]
    url = f"/learning/proposals/{proposal['stable_key']}/decisions"

    approved = client.post(
        url,
        json={"decision": "approved", "reason": "Preferencia explicita."},
    )
    repeated = client.post(
        url,
        json={"decision": "approved", "reason": "Preferencia explicita."},
    )
    conflict = client.post(
        url,
        json={"decision": "dismissed", "reason": "Tentativa conflitante."},
    )

    assert repeated.status_code == 201
    assert repeated.json()["decision"]["id"] == approved.json()["decision"]["id"]
    assert conflict.status_code == 409
    with transaction(settings) as connection:
        count = connection.execute(
            "SELECT COUNT(*) AS count FROM learning_proposal_decisions"
        ).fetchone()["count"]
    assert count == 1


def test_manual_signature_is_exact_and_calibration_only(
    client: TestClient,
    settings: Settings,
) -> None:
    first = seed_sheet(settings, 1)
    second = seed_sheet(settings, 2)
    seed_finding(
        settings,
        first,
        "manual-1",
        origin="human",
        status="pending",
        rule_id=None,
        description=" Texto sobreposto. ",
    )
    seed_finding(
        settings,
        first,
        "manual-2",
        origin="human",
        status="pending",
        rule_id=None,
        description="texto   sobreposto",
    )
    seed_finding(
        settings,
        second,
        "manual-3",
        origin="human",
        status="pending",
        rule_id=None,
        description="TEXTO SOBREPOSTO!",
    )
    seed_finding(
        settings,
        second,
        "manual-other",
        origin="human",
        status="pending",
        rule_id=None,
        description="Texto sobreposto em cota",
    )

    proposals = client.get("/learning/proposals?include_insufficient=true").json()
    pending = next(item for item in proposals if item["state"] == "pending")
    insufficient = next(item for item in proposals if item["state"] == "insufficient")
    assert pending["proposal_kind"] == "draft_rule"
    assert pending["normalized_description"] == "texto sobreposto"
    assert pending["manual_count"] == 3
    assert insufficient["manual_count"] == 1

    approved = client.post(
        f"/learning/proposals/{pending['stable_key']}/decisions",
        json={"decision": "approved", "reason": "Levar para a calibracao do checklist."},
    ).json()
    assert approved["state"] == "approved"
    assert approved["effect"] == "calibration_only"
    assert client.get("/rule-preferences").json() == []


def test_preference_history_can_be_filtered_and_reactivated(
    client: TestClient,
    settings: Settings,
) -> None:
    first = seed_sheet(settings, 1)
    second = seed_sheet(settings, 2)
    seed_finding(settings, first, "finding-1")
    seed_finding(settings, second, "finding-2")
    proposal = client.get("/learning/proposals").json()[0]
    approved = client.post(
        f"/learning/proposals/{proposal['stable_key']}/decisions",
        json={"decision": "approved", "reason": "Preferencia local."},
    ).json()
    preference_id = approved["decision"]["preference_id"]

    client.delete(f"/rule-preferences/{preference_id}")
    assert client.get("/rule-preferences?status=active").json() == []
    revoked = client.get(
        "/rule-preferences?status=revoked&sheet_type=formas&rule_id=forms.sheet.has_main_view"
    ).json()
    assert [item["id"] for item in revoked] == [preference_id]

    reactivated = client.post(f"/rule-preferences/{preference_id}/reactivate")
    assert reactivated.status_code == 201
    assert reactivated.json()["id"] != preference_id
    assert reactivated.json()["active"] is True
