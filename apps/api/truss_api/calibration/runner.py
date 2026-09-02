from __future__ import annotations

import argparse
from collections import Counter
from datetime import UTC, datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable
from uuid import uuid4

from truss_api.audit.orchestrator import AUDIT_PIPELINE_VERSION, run_deterministic_audit
from truss_api.calibration.contracts import (
    POLICY_VERSION,
    CorpusDocument,
    analysis_key,
    build_corpus_manifest,
    preference_digest,
    rule_pack_digest,
    run_key,
)
from truss_api.calibration.proposals import generate_proposals
from truss_api.calibration.exporter import export_run
from truss_api.calibration import repository
from truss_api.core.settings import REPO_ROOT, Settings
from truss_api.db.connection import transaction
from truss_api.db.schema import initialize_database
from truss_api.documents import repository as documents_repository
from truss_api.documents.importer import prepare_pdf_storage
from truss_api.projects import repository as projects_repository
from truss_api.projects.models import ProjectCreate, RevisionCreate
from truss_api.sheetmap.builder import build_sheet_map_for_document
from truss_api.sheetmap.snapshot import SHEET_MAP_PIPELINE


APPROVED_DIR = REPO_ROOT / "data" / "knowledge-inbox" / "approved"
CATALOG_PATH = REPO_ROOT / "data" / "knowledge-inbox" / ".truss" / "catalog.json"
GROUND_TRUTH_DIR = REPO_ROOT / "calibration"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def analyze_documents(documents: list[CorpusDocument]) -> dict[str, Any]:
    evaluations: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    sheet_map_count = 0
    frequencies: dict[str, Counter[str]] = {
        "sheet_types": Counter(),
        "technical_scopes": Counter(),
        "view_kinds": Counter(),
        "element_kinds": Counter(),
    }

    for corpus_document in documents:
        with TemporaryDirectory(prefix="truss-f53-") as temporary:
            isolated = Settings(data_dir=Path(temporary) / "data")
            initialize_database(isolated)
            project = projects_repository.create_project(
                ProjectCreate(name=f"F5.3 {corpus_document.sha256[:12]}"), isolated
            )
            revision = projects_repository.create_revision(
                str(project["id"]), RevisionCreate(notes="F5.3 disposable corpus measurement"), isolated
            )
            prepared = prepare_pdf_storage(
                content=corpus_document.path.read_bytes(),
                filename=corpus_document.filename,
                project_id=str(project["id"]),
                revision_id=str(revision["id"]),
                settings=isolated,
            )
            document = documents_repository.create_document_from_prepared_pdf(
                project_id=str(project["id"]),
                revision_id=str(revision["id"]),
                prepared_pdf=prepared,
                settings=isolated,
            )
            maps = build_sheet_map_for_document(str(document["id"]), isolated)
            sheet_map_count += len(maps)
            for sheet in document["sheets"]:
                run_deterministic_audit(str(sheet["id"]), isolated)

            with transaction(isolated) as connection:
                evaluation_rows = connection.execute(
                    """
                    SELECT e.rule_id, e.rule_version, e.rule_scope, e.technical_scope,
                           e.target_kind, e.target_id,
                           e.outcome, e.confidence, e.reason, s.page_index,
                           s.width_pt, s.height_pt, sm.sheet_code, sm.sheet_type
                    FROM rule_evaluations e
                    JOIN sheets s ON s.id = e.sheet_id
                    JOIN sheet_maps sm ON sm.id = e.sheet_map_id
                    ORDER BY s.page_index, e.rule_id, e.id
                    """
                ).fetchall()
                finding_rows = connection.execute(
                    """
                    SELECT f.rule_id, f.rule_version, f.rule_scope, f.technical_scope,
                           f.view_id, f.element_code,
                           f.description, f.severity, f.confidence,
                           f.x0, f.y0, f.x1, f.y1, s.page_index,
                           sm.sheet_code, sm.sheet_type
                    FROM findings f
                    JOIN sheets s ON s.id = f.sheet_id
                    LEFT JOIN sheet_maps sm ON sm.id = f.sheet_map_id
                    WHERE f.source_layer = 'deterministic'
                    ORDER BY s.page_index, f.rule_id, f.id
                    """
                ).fetchall()
                frequency_queries = {
                    "sheet_types": "SELECT sheet_type AS value, COUNT(*) AS total FROM sheet_maps GROUP BY sheet_type",
                    "technical_scopes": "SELECT technical_scope AS value, COUNT(*) AS total FROM sheet_map_scopes GROUP BY technical_scope",
                    "view_kinds": "SELECT view_kind AS value, COUNT(*) AS total FROM sheet_views GROUP BY view_kind",
                    "element_kinds": "SELECT element_kind AS value, COUNT(*) AS total FROM sheet_elements GROUP BY element_kind",
                }
                for dimension, query in frequency_queries.items():
                    for row in connection.execute(query).fetchall():
                        frequencies[dimension][str(row["value"] or "unknown")] += int(row["total"])

            for row in evaluation_rows:
                item = dict(row)
                item.update(
                    {
                        "document_sha256": corpus_document.sha256,
                        "authority": corpus_document.authority,
                        "bbox": {
                            "x0": 0.0,
                            "y0": 0.0,
                            "x1": float(item.pop("width_pt")),
                            "y1": float(item.pop("height_pt")),
                        },
                    }
                )
                evaluations.append(item)
            for row in finding_rows:
                item = dict(row)
                item.update(
                    {
                        "document_sha256": corpus_document.sha256,
                        "authority": corpus_document.authority,
                        "bbox": {key: float(item.pop(key)) for key in ("x0", "y0", "x1", "y1")},
                    }
                )
                findings.append(item)

    return {
        "sheet_maps": sheet_map_count,
        "evaluations": evaluations,
        "findings": findings,
        "frequencies": {
            dimension: dict(sorted(values.items())) for dimension, values in frequencies.items()
        },
    }


def _rule_metrics(evaluations: list[dict[str, Any]], findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    outcome_counts: dict[tuple[str, str], Counter[str]] = {}
    for item in evaluations:
        key = (str(item.get("sheet_type") or ""), str(item.get("rule_id") or ""))
        outcome_counts.setdefault(key, Counter())[str(item.get("outcome"))] += 1
    finding_counts = Counter(
        (str(item.get("sheet_type") or ""), str(item.get("rule_id") or "")) for item in findings
    )
    return [
        {
            "sheet_type": key[0],
            "rule_id": key[1],
            "outcomes": dict(sorted(counts.items())),
            "raw_findings": finding_counts[key],
        }
        for key, counts in sorted(outcome_counts.items())
    ]


def partition_findings(
    findings: list[dict[str, Any]],
    preferences: list[dict[str, object]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    suppressed_keys = {
        (str(item["sheet_type"]), str(item["rule_id"]))
        for item in preferences
        if item["action"] == "suppress"
    }
    suppressed = [
        item for item in findings
        if (str(item.get("sheet_type") or ""), str(item.get("rule_id") or "")) in suppressed_keys
    ]
    effective = [item for item in findings if item not in suppressed]
    return suppressed, effective


def measure_approved(
    settings: Settings,
    *,
    approved_dir: Path = APPROVED_DIR,
    catalog_path: Path = CATALOG_PATH,
    ground_truth_dir: Path = GROUND_TRUTH_DIR,
    analyzer: Callable[[list[CorpusDocument]], dict[str, Any]] = analyze_documents,
) -> dict[str, Any]:
    initialize_database(settings)
    manifest, documents = build_corpus_manifest(
        approved_dir=approved_dir,
        catalog_path=catalog_path,
        ground_truth_dir=ground_truth_dir,
    )
    pack_digest = rule_pack_digest()
    raw_key = analysis_key(str(manifest["hash"]), pack_digest)
    preferences = repository.active_preferences(settings)
    preferences_hash = preference_digest(preferences)
    derived_key = run_key(raw_key, preferences_hash)

    existing = repository.find_run_by_key(derived_key, settings)
    if existing:
        report_path = settings.data_dir / str(existing["artifact_path"])
        if report_path.exists():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["cache"] = {"analysis": True, "run": True}
            return report

    raw_path = settings.calibration_analyses_dir / raw_key / "raw.json"
    analysis_cache_hit = raw_path.exists()
    if analysis_cache_hit:
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
    else:
        measured = analyzer(documents)
        raw = {
            "analysis_key": raw_key,
            "manifest": manifest,
            "versions": {
                "sheetmap": SHEET_MAP_PIPELINE,
                "audit": AUDIT_PIPELINE_VERSION,
                "rule_packs": pack_digest,
                "policy": POLICY_VERSION,
            },
            "sheet_maps": int(measured["sheet_maps"]),
            "evaluations": measured["evaluations"],
            "findings": measured["findings"],
            "frequencies": measured.get(
                "frequencies",
                {"sheet_types": {}, "technical_scopes": {}, "view_kinds": {}, "element_kinds": {}},
            ),
            "created_at": _now(),
        }
        _write_json_atomic(raw_path, raw)

    raw_findings = list(raw["findings"])
    suppressed, effective = partition_findings(raw_findings, preferences)
    feedback = repository.feedback_snapshot(settings)
    learning = repository.approved_learning_snapshot(settings)
    proposals = generate_proposals(raw, feedback, learning)
    report = {
        "schema": "calibration-report-v0.1",
        "analysis_key": raw_key,
        "run_key": derived_key,
        "manifest": manifest,
        "versions": raw["versions"],
        "preference_digest": preferences_hash,
        "metrics": {
            "sheet_maps": int(raw["sheet_maps"]),
            "evaluations": len(raw["evaluations"]),
            "raw_findings": len(raw_findings),
            "suppressed_findings": len(suppressed),
            "effective_findings": len(effective),
            "outcomes": dict(sorted(Counter(str(item["outcome"]) for item in raw["evaluations"]).items())),
            "frequencies": raw.get("frequencies", {}),
            "rules": _rule_metrics(raw["evaluations"], raw_findings),
        },
        "proposal_count": len(proposals),
        "created_at": _now(),
        "cache": {"analysis": analysis_cache_hit, "run": False},
    }
    relative_path = Path("calibration") / "runs" / derived_key / "report.json"
    report_path = settings.data_dir / relative_path
    _write_json_atomic(report_path, report)
    repository.persist_run(report, proposals, relative_path, settings)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Truss deterministic corpus calibration")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("measure-approved", help="Measure the approved local PDF corpus")
    export_parser = subcommands.add_parser("export-feedback", help="Export one immutable calibration run")
    export_parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if args.command == "measure-approved":
        report = measure_approved(Settings())
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "export-feedback":
        settings = Settings()
        initialize_database(settings)
        print(export_run(args.run_id, settings))


if __name__ == "__main__":
    main()
