import json
from pathlib import Path
from zipfile import ZipFile
from fastapi.testclient import TestClient

from truss_api.calibration.contracts import (
    analysis_key,
    build_corpus_manifest,
    preference_digest,
    run_key,
)
from truss_api.calibration.proposals import generate_proposals
from truss_api.calibration import repository
from truss_api.calibration.runner import measure_approved, partition_findings
from truss_api.calibration.exporter import export_run
from truss_api.core.settings import Settings
from truss_api.core.settings import get_settings
from truss_api.main import app


def test_manifest_requires_approved_pdf_in_catalog(tmp_path: Path) -> None:
    approved = tmp_path / "approved"
    approved.mkdir()
    (approved / "unknown.pdf").write_bytes(b"pdf")
    catalog = tmp_path / "catalog.json"
    catalog.write_text("[]", encoding="utf-8")

    try:
        build_corpus_manifest(
            approved_dir=approved,
            catalog_path=catalog,
            ground_truth_dir=tmp_path / "truth",
        )
    except ValueError as error:
        assert "absent from catalog" in str(error)
    else:
        raise AssertionError("uncatalogued PDF should be rejected")


def test_manifest_is_stable_and_declares_reference_authority(tmp_path: Path) -> None:
    approved = tmp_path / "approved"
    approved.mkdir()
    pdf = approved / "reference.pdf"
    pdf.write_bytes(b"reference")
    from truss_api.calibration.contracts import file_hash

    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps([{"filename": pdf.name, "sha256": file_hash(pdf), "pages": 3}]),
        encoding="utf-8",
    )

    first, documents = build_corpus_manifest(
        approved_dir=approved,
        catalog_path=catalog,
        ground_truth_dir=tmp_path / "truth",
    )
    second, _ = build_corpus_manifest(
        approved_dir=approved,
        catalog_path=catalog,
        ground_truth_dir=tmp_path / "truth",
    )

    assert first == second
    assert first["document_count"] == 1
    assert first["page_count"] == 3
    assert documents[0].authority == "delivered_reference"
    assert "path" not in first["documents"][0]


def test_preferences_change_run_key_but_not_analysis_key() -> None:
    raw_key = analysis_key("manifest", "packs")
    empty = preference_digest([])
    suppress = preference_digest(
        [{"scope": "sheet_type", "sheet_type": "formas", "rule_id": "F-01", "action": "suppress"}]
    )

    assert raw_key == analysis_key("manifest", "packs")
    assert empty != suppress
    assert run_key(raw_key, empty) != run_key(raw_key, suppress)

    findings = [
        {"sheet_type": "formas", "rule_id": "F-01"},
        {"sheet_type": "formas", "rule_id": "F-02"},
    ]
    suppressed_findings, effective_findings = partition_findings(
        findings,
        [{"scope": "sheet_type", "sheet_type": "formas", "rule_id": "F-01", "action": "suppress"}],
    )
    assert suppressed_findings == [findings[0]]
    assert effective_findings == [findings[1]]


def test_noise_proposal_requires_two_documents_or_rejected_feedback() -> None:
    finding = {
        "document_sha256": "a",
        "page_index": 0,
        "sheet_type": "formas",
        "rule_id": "F-01",
        "description": "sample",
        "authority": "delivered_reference",
        "bbox": {"x0": 0, "y0": 0, "x1": 10, "y1": 10},
    }
    assert generate_proposals({"findings": [finding], "evaluations": []}, [], []) == []

    second = {**finding, "document_sha256": "b", "page_index": 1}
    proposals = generate_proposals(
        {
            "findings": [finding, finding, second],
            "evaluations": [{**finding, "outcome": "PASS", "reason": "ok"}],
        },
        [],
        [],
    )

    assert len(proposals) == 1
    assert proposals[0]["proposal_kind"] == "rule_noise"
    assert {item["evidence_kind"] for item in proposals[0]["evidence"]} == {
        "sample",
        "counterexample",
    }
    assert len({item["evidence_key"] for item in proposals[0]["evidence"]}) == len(proposals[0]["evidence"])


def test_measurement_persists_immutable_run_and_replays_cache(tmp_path: Path) -> None:
    approved = tmp_path / "approved"
    approved.mkdir()
    pdfs = [approved / "a.pdf", approved / "b.pdf"]
    for index, pdf in enumerate(pdfs):
        pdf.write_bytes(f"pdf-{index}".encode())
    from truss_api.calibration.contracts import file_hash

    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            [{"filename": path.name, "sha256": file_hash(path), "pages": 1} for path in pdfs]
        ),
        encoding="utf-8",
    )
    calls = 0

    def analyzer(documents):
        nonlocal calls
        calls += 1
        findings = [
            {
                "document_sha256": item.sha256,
                "page_index": 0,
                "sheet_code": "F01",
                "sheet_type": "formas",
                "technical_scope": "formas",
                "rule_id": "F-01",
                "description": "candidate",
                "authority": "delivered_reference",
                "bbox": {"x0": 0, "y0": 0, "x1": 10, "y1": 10},
            }
            for item in documents
        ]
        return {"sheet_maps": 2, "evaluations": [], "findings": findings}

    settings = Settings(data_dir=tmp_path / "data")
    first = measure_approved(
        settings,
        approved_dir=approved,
        catalog_path=catalog,
        ground_truth_dir=tmp_path / "truth",
        analyzer=analyzer,
    )
    replay = measure_approved(
        settings,
        approved_dir=approved,
        catalog_path=catalog,
        ground_truth_dir=tmp_path / "truth",
        analyzer=analyzer,
    )

    assert calls == 1
    assert first["metrics"]["raw_findings"] == 2
    assert replay["cache"] == {"analysis": True, "run": True}
    runs = repository.list_runs(settings)
    assert len(runs) == 1
    proposals = repository.list_proposals(settings, runs[0]["id"])
    assert len(proposals) == 1
    decided = repository.decide(proposals[0]["id"], "approved", "Useful evidence", settings)
    assert decided["decision"]["decision"] == "approved"
    assert decided["state"] == "ready_for_implementation"
    revoked = repository.revoke_decision(decided["decision"]["id"], settings)
    assert revoked["decision"] is None

    archive_path = export_run(runs[0]["id"], settings)
    with ZipFile(archive_path) as archive:
        assert set(archive.namelist()) == {
            "manifest.json",
            "feedback.ndjson",
            "decisions.ndjson",
            "evidence.ndjson",
            "metrics.json",
        }
        manifest = json.loads(archive.read("manifest.json"))
        assert "absolute_paths" in manifest["excluded"]
        assert str(tmp_path) not in archive.read("manifest.json").decode()

    app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(app)
    try:
        assert client.get("/calibration/runs").status_code == 200
        response = client.get(f"/calibration/runs/{runs[0]['id']}")
        assert response.status_code == 200
        assert response.json()["proposals"][0]["stable_key"] == proposals[0]["stable_key"]
        decision_response = client.post(
            f"/calibration/proposals/{proposals[0]['id']}/decisions",
            json={"decision": "dismissed", "reason": "Not actionable"},
        )
        assert decision_response.status_code == 201
        export_response = client.post(f"/calibration/runs/{runs[0]['id']}/exports")
        assert export_response.status_code == 200
        assert export_response.headers["content-type"] == "application/zip"
    finally:
        app.dependency_overrides.clear()
