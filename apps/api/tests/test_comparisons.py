import sqlite3
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient

from truss_api.core.settings import Settings, get_settings
from truss_api.db.connection import transaction
from truss_api.db.schema import initialize_database
from truss_api.main import app
from truss_api.recovery.sources import declare_source_unavailable
from truss_api.comparisons.matcher import match_sheets


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


def _pdf(*, code: str | None, marker: str, width: float = 1000, height: float = 800) -> bytes:
    document = fitz.open()
    page = document.new_page(width=width, height=height)
    page.draw_rect(fitz.Rect(20, 10, width - 30, height - 30))
    page.insert_text((120, 200), "PLANTA DE FORMAS")
    page.insert_text((120, 250), marker, fontsize=18)
    if code:
        page.insert_text((width - 290, height - 94), code)
    page.insert_text((width - 290, height - 74), "CPF: 951.770.276-00")
    page.insert_text((width - 290, height - 44), "PROJETO ESTRUTURAL")
    page.insert_text((width - 290, height - 24), "PLANTA DE FORMAS")
    buffer = BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def _project(client: TestClient, name: str = "Comparacao") -> str:
    return str(client.post("/projects", json={"name": name, "description": ""}).json()["id"])


def _revision(client: TestClient, project_id: str, code: str, pdf: bytes) -> dict[str, object]:
    revision = client.post(
        f"/projects/{project_id}/revisions",
        json={"revision_code": code, "notes": "", "source_type": "manual"},
    ).json()
    document = client.post(
        f"/projects/{project_id}/revisions/{revision['id']}/documents",
        files={"file": (f"{code}.pdf", pdf, "application/pdf")},
    ).json()
    return {"revision": revision, "document": document, "sheet": document["sheets"][0]}


def _compare(client: TestClient, project_id: str, base_id: str, target_id: str):
    return client.post(
        f"/projects/{project_id}/revision-comparisons",
        json={"base_revision_id": base_id, "target_revision_id": target_id},
    )


def test_identical_comparison_is_cached_without_duplicate_regions(
    client: TestClient, settings: Settings
) -> None:
    project_id = _project(client)
    content = _pdf(code=None, marker="MESMO CONTEUDO")
    base = _revision(client, project_id, "R01", content)
    target = _revision(client, project_id, "R02", content)

    first = _compare(
        client, project_id, str(base["revision"]["id"]), str(target["revision"]["id"])
    )
    second = _compare(
        client, project_id, str(base["revision"]["id"]), str(target["revision"]["id"])
    )

    assert first.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert first.json()["counts"]["identical"] == 1
    assert first.json()["pairs"][0]["match_method"] == "exact_content"
    assert first.json()["pairs"][0]["regions"] == []
    assert first.json()["pairs"][0]["delta_status"] == "completed"
    assert first.json()["pairs"][0]["delta_counts"]["total"] == 0
    assert first.json()["pairs"][0]["deltas"] == []
    with transaction(settings) as connection:
        assert connection.execute("SELECT COUNT(*) FROM revision_comparisons").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM revision_comparison_pairs").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM revision_comparison_deltas").fetchone()[0] == 0


def test_legacy_f71_comparison_reads_as_not_run_without_mutation(
    client: TestClient, settings: Settings
) -> None:
    project_id = _project(client)
    content = _pdf(code=None, marker="LEGADO")
    base = _revision(client, project_id, "R01", content)
    target = _revision(client, project_id, "R02", content)
    comparison_id = "comparison-f71"
    with transaction(settings) as connection:
        connection.execute(
            """
            INSERT INTO revision_comparisons (
                id, project_id, base_revision_id, target_revision_id,
                input_fingerprint, pipeline_version, status, counts_json, created_at
            ) VALUES (?, ?, ?, ?, ?, 'revision-comparison-v0.1', 'completed', ?, ?)
            """,
            (
                comparison_id,
                project_id,
                base["revision"]["id"],
                target["revision"]["id"],
                "legacy-fingerprint",
                '{"total": 1, "identical": 1}',
                "2026-09-01T00:00:00+00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO revision_comparison_pairs (
                id, comparison_id, sequence, base_sheet_id, target_sheet_id,
                status, match_method, match_confidence, summary, changed_ratio,
                created_at
            ) VALUES (?, ?, 0, ?, ?, 'identical', 'exact_content', 1, ?, 0, ?)
            """,
            (
                "pair-f71",
                comparison_id,
                base["sheet"]["id"],
                target["sheet"]["id"],
                "Conteúdo idêntico no pipeline F7.1.",
                "2026-09-01T00:00:00+00:00",
            ),
        )

    response = client.get(f"/revision-comparisons/{comparison_id}")

    assert response.status_code == 200
    pair = response.json()["pairs"][0]
    assert pair["delta_status"] == "not_run"
    assert pair["delta_counts"] == {}
    assert pair["deltas"] == []


def test_localized_graphic_change_keeps_pdf_point_bboxes(client: TestClient) -> None:
    project_id = _project(client)
    base = _revision(client, project_id, "R01", _pdf(code="EST-0010-A", marker="ANTES"))
    target = _revision(client, project_id, "R02", _pdf(code="EST-0010-A", marker="DEPOIS ALTERADO"))

    response = _compare(
        client, project_id, str(base["revision"]["id"]), str(target["revision"]["id"])
    )

    assert response.status_code == 201
    pair = response.json()["pairs"][0]
    assert pair["match_method"] == "sheet_code"
    assert pair["status"] == "changed"
    assert pair["regions"]
    assert pair["delta_status"] == "completed"
    assert pair["delta_counts"]["text"]["total"] > 0
    assert pair["deltas"]
    region = pair["regions"][0]
    assert 0 <= region["base_bbox"]["x0"] < region["base_bbox"]["x1"] <= 1000
    assert 0 <= region["base_bbox"]["y0"] < region["base_bbox"]["y1"] <= 800
    assert region["base_bbox"] == region["target_bbox"]
    text_delta = next(delta for delta in pair["deltas"] if delta["layer"] == "text")
    for bbox in (text_delta["base_bbox"], text_delta["target_bbox"]):
        if bbox is not None:
            assert 0 <= bbox["x0"] <= bbox["x1"] <= 1000
            assert 0 <= bbox["y0"] <= bbox["y1"] <= 800


def test_manual_pairing_creates_new_immutable_run_and_can_be_revoked(
    client: TestClient, settings: Settings
) -> None:
    project_id = _project(client)
    base = _revision(client, project_id, "R01", _pdf(code=None, marker="BASE"))
    target = _revision(client, project_id, "R02", _pdf(code=None, marker="ALVO"))
    base_revision_id = str(base["revision"]["id"])
    target_revision_id = str(target["revision"]["id"])

    initial = _compare(client, project_id, base_revision_id, target_revision_id).json()
    assert initial["counts"]["ambiguous"] == 2

    pairing = client.post(
        f"/projects/{project_id}/comparison-pairings",
        json={
            "base_revision_id": base_revision_id,
            "target_revision_id": target_revision_id,
            "base_sheet_id": base["sheet"]["id"],
            "target_sheet_id": target["sheet"]["id"],
        },
    )
    assert pairing.status_code == 201
    paired = _compare(client, project_id, base_revision_id, target_revision_id).json()
    assert paired["id"] != initial["id"]
    assert paired["pairs"][0]["match_method"] == "manual"
    assert paired["pairs"][0]["pairing_override_id"] == pairing.json()["id"]

    revoked = client.delete(f"/comparison-pairings/{pairing.json()['id']}")
    assert revoked.status_code == 200
    assert revoked.json()["active"] is False
    after_revoke = _compare(client, project_id, base_revision_id, target_revision_id).json()
    assert after_revoke["id"] == initial["id"]
    with transaction(settings) as connection:
        assert connection.execute("SELECT COUNT(*) FROM revision_comparisons").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM comparison_pair_overrides").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE revision_comparisons SET status = 'failed' WHERE id = ?",
                (paired["id"],),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE revision_comparison_pairs SET summary = 'mutated' WHERE comparison_id = ?",
                (paired["id"],),
            )
        delta_id = connection.execute(
            """
            SELECT delta.id
            FROM revision_comparison_deltas delta
            JOIN revision_comparison_pairs pair ON pair.id = delta.pair_id
            WHERE pair.comparison_id = ?
            LIMIT 1
            """,
            (paired["id"],),
        ).fetchone()["id"]
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE revision_comparison_deltas SET similarity = 0 WHERE id = ?",
                (delta_id,),
            )


def test_unavailable_source_is_not_reported_as_identical(
    client: TestClient, settings: Settings
) -> None:
    project_id = _project(client)
    content = _pdf(code="EST-0010-A", marker="MESMO")
    base = _revision(client, project_id, "R01", content)
    target = _revision(client, project_id, "R02", content)
    base_document = base["document"]
    (settings.data_dir / str(base_document["stored_file_path"])).unlink()
    declare_source_unavailable(
        str(base_document["id"]),
        reason_code="fixture_missing",
        note="Fonte removida no teste.",
        settings=settings,
    )

    response = _compare(
        client, project_id, str(base["revision"]["id"]), str(target["revision"]["id"])
    )

    assert response.status_code == 201
    assert response.json()["status"] == "completed_with_limits"
    assert response.json()["pairs"][0]["status"] == "unavailable"
    assert response.json()["pairs"][0]["delta_status"] == "unavailable"


def test_page_geometry_change_is_a_full_page_change(client: TestClient) -> None:
    project_id = _project(client)
    base = _revision(client, project_id, "R01", _pdf(code="EST-0010-A", marker="BASE"))
    target = _revision(
        client,
        project_id,
        "R02",
        _pdf(code="EST-0010-A", marker="ALVO", width=1100, height=800),
    )

    pair = _compare(
        client, project_id, str(base["revision"]["id"]), str(target["revision"]["id"])
    ).json()["pairs"][0]

    assert pair["status"] == "changed"
    assert pair["changed_ratio"] == 1
    assert pair["regions"][0]["base_bbox"]["x1"] == 1000
    assert pair["regions"][0]["target_bbox"]["x1"] == 1100
    assert pair["delta_status"] == "not_comparable"
    assert pair["deltas"] == []


def test_comparison_rejects_equal_or_cross_project_revisions(client: TestClient) -> None:
    first_project = _project(client, "Primeiro")
    second_project = _project(client, "Segundo")
    first = _revision(client, first_project, "R01", _pdf(code=None, marker="A"))
    second = _revision(client, second_project, "R01", _pdf(code=None, marker="B"))
    first_revision_id = str(first["revision"]["id"])

    equal = _compare(client, first_project, first_revision_id, first_revision_id)
    cross_project = _compare(
        client, first_project, first_revision_id, str(second["revision"]["id"])
    )

    assert equal.status_code == 422
    assert cross_project.status_code == 409
    assert cross_project.json()["detail"]["code"] == "COMPARISON_PROJECT_MISMATCH"


def test_matcher_marks_coded_additions_removals_and_duplicate_codes_honestly() -> None:
    def item(sheet_id: str, code: str | None, number: int, digest: str) -> dict[str, object]:
        return {
            "id": sheet_id,
            "sheet_code": code,
            "sheet_number": number,
            "document_hash": digest,
            "page_index": number - 1,
        }

    base = [
        item("base-common", "EST-0010-A", 1, "base"),
        item("base-removed", "EST-0020-A", 2, "base"),
        item("base-duplicate-a", "EST-0040-A", 4, "base"),
        item("base-duplicate-b", "EST-0040-A", 5, "base"),
    ]
    target = [
        item("target-common", "EST-0010-A", 1, "target"),
        item("target-added", "EST-0030-A", 3, "target"),
        item("target-duplicate", "EST-0040-A", 4, "target"),
    ]

    pairs = match_sheets(base, target, [])

    common = next(pair for pair in pairs if (pair.get("base") or {}).get("id") == "base-common")
    assert common["target"]["id"] == "target-common"
    assert common["match_method"] == "sheet_code"
    assert next(
        pair["unmatched_status"]
        for pair in pairs
        if (pair.get("base") or {}).get("id") == "base-removed"
    ) == "removed"
    assert next(
        pair["unmatched_status"]
        for pair in pairs
        if (pair.get("target") or {}).get("id") == "target-added"
    ) == "added"
    duplicate_pairs = [
        pair
        for pair in pairs
        if (pair.get("base") or pair.get("target") or {}).get("sheet_code") == "EST-0040-A"
    ]
    assert len(duplicate_pairs) == 3
    assert all(pair["match_method"] == "unmatched" for pair in duplicate_pairs)
    assert all(pair["unmatched_status"] == "ambiguous" for pair in duplicate_pairs)
