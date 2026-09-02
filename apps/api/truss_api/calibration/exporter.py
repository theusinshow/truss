from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from truss_api.calibration import repository
from truss_api.core.settings import Settings


def _json_line(item: dict[str, object]) -> str:
    return json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def export_run(run_id: str, settings: Settings) -> Path:
    snapshot = repository.export_snapshot(run_id, settings)
    run = snapshot["run"]
    report_path = settings.data_dir / str(run["artifact_path"])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    output = settings.calibration_exports_dir / f"{run['run_key']}.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{uuid4().hex}.tmp")

    manifest = {
        "schema": "truss-calibration-export-v0.1",
        "run_id": run_id,
        "analysis_key": run["analysis_key"],
        "run_key": run["run_key"],
        "corpus": report["manifest"],
        "versions": report["versions"],
        "files": [
            "manifest.json",
            "feedback.ndjson",
            "decisions.ndjson",
            "evidence.ndjson",
            "metrics.json",
        ],
        "excluded": ["pdfs", "images", "memories", "conversations", "secrets", "absolute_paths"],
    }
    evidence = snapshot["evidence"]
    feedback = snapshot["feedback"]
    decisions = [
        *({"record_kind": "rule_preference", **item} for item in snapshot["preferences"]),
        *({"record_kind": "learning_decision", **item} for item in snapshot["learning_decisions"]),
        *({"record_kind": "calibration_decision", **item} for item in snapshot["decisions"]),
    ]
    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2))
            archive.writestr("feedback.ndjson", "\n".join(_json_line(item) for item in feedback))
            archive.writestr("decisions.ndjson", "\n".join(_json_line(item) for item in decisions))
            archive.writestr("evidence.ndjson", "\n".join(_json_line(item) for item in evidence))
            archive.writestr("metrics.json", json.dumps(report["metrics"], ensure_ascii=False, sort_keys=True, indent=2))
        temporary.replace(output)
    finally:
        if temporary.exists():
            temporary.unlink()
    return output
