from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from sqlite3 import Connection, Row
from typing import Any
from uuid import uuid4

from truss_api.core.settings import Settings
from truss_api.db.connection import transaction


class CalibrationNotFoundError(Exception):
    pass


class CalibrationDecisionConflictError(Exception):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


def active_preferences(settings: Settings) -> list[dict[str, object]]:
    with transaction(settings) as connection:
        rows = connection.execute(
            """SELECT scope, sheet_type, rule_id, action FROM rule_preferences
               WHERE revoked_at IS NULL ORDER BY scope, sheet_type, rule_id, action"""
        ).fetchall()
    return [dict(row) for row in rows]


def feedback_snapshot(settings: Settings) -> list[dict[str, Any]]:
    with transaction(settings) as connection:
        rows = connection.execute(
            """
            SELECT f.id AS source_finding_id, f.status, f.rejection_reason,
                   f.description, f.rule_id, d.content_hash AS document_sha256,
                   s.page_index, sm.sheet_code, sm.sheet_type,
                   f.x0, f.y0, f.x1, f.y1
            FROM findings f
            JOIN documents d ON d.id = f.document_id
            JOIN sheets s ON s.id = f.sheet_id
            LEFT JOIN sheet_maps sm ON sm.id = f.sheet_map_id
            WHERE f.status IN ('confirmed', 'rejected') OR f.origin = 'manual'
            ORDER BY f.created_at, f.id
            """
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["signal_kind"] = "manual" if not item.get("rule_id") else str(item.pop("status"))
        item["bbox"] = {key: item.pop(key) for key in ("x0", "y0", "x1", "y1")}
        result.append(item)
    return result


def approved_learning_snapshot(settings: Settings) -> list[dict[str, Any]]:
    with transaction(settings) as connection:
        decisions = connection.execute(
            """SELECT * FROM learning_proposal_decisions
               WHERE decision = 'approved' AND revoked_at IS NULL
                 AND proposal_kind IN ('draft_rule', 'retain_rule')
               ORDER BY created_at, id"""
        ).fetchall()
        result = []
        for decision in decisions:
            evidence = connection.execute(
                """
                SELECT e.signal_kind, f.id AS source_finding_id, f.description, f.rule_id,
                       d.content_hash AS document_sha256, s.page_index,
                       sm.sheet_code, sm.sheet_type, f.x0, f.y0, f.x1, f.y1
                FROM learning_proposal_evidence e
                JOIN findings f ON f.id = e.finding_id
                JOIN documents d ON d.id = f.document_id
                JOIN sheets s ON s.id = f.sheet_id
                LEFT JOIN sheet_maps sm ON sm.id = f.sheet_map_id
                WHERE e.decision_id = ? ORDER BY e.created_at, f.id
                """,
                (decision["id"],),
            ).fetchall()
            snapshot = dict(decision)
            snapshot["evidence"] = []
            for row in evidence:
                item = dict(row)
                item["bbox"] = {key: item.pop(key) for key in ("x0", "y0", "x1", "y1")}
                snapshot["evidence"].append(item)
            first = snapshot["evidence"][0] if snapshot["evidence"] else {}
            snapshot["sheet_type"] = first.get("sheet_type")
            snapshot["rule_id"] = first.get("rule_id")
            result.append(snapshot)
    return result


def find_run_by_key(run_key: str, settings: Settings) -> dict[str, Any] | None:
    with transaction(settings) as connection:
        row = connection.execute("SELECT * FROM calibration_runs WHERE run_key = ?", (run_key,)).fetchone()
    return dict(row) if row else None


def persist_run(report: dict[str, Any], proposals: list[dict[str, Any]], artifact_path: Path, settings: Settings) -> str:
    run_id = str(uuid4())
    now = _now()
    metrics = report["metrics"]
    with transaction(settings) as connection:
        connection.execute(
            """INSERT INTO calibration_runs (
                id, analysis_key, run_key, corpus_manifest_hash,
                sheetmap_pipeline_version, audit_pipeline_version, rule_pack_digest,
                policy_version, preference_digest, document_count, page_count,
                sheet_map_count, evaluation_count, raw_finding_count,
                suppressed_finding_count, effective_finding_count, artifact_path, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id, report["analysis_key"], report["run_key"], report["manifest"]["hash"],
                report["versions"]["sheetmap"], report["versions"]["audit"], report["versions"]["rule_packs"],
                report["versions"]["policy"], report["preference_digest"], report["manifest"]["document_count"],
                report["manifest"]["page_count"], metrics["sheet_maps"], metrics["evaluations"],
                metrics["raw_findings"], metrics["suppressed_findings"], metrics["effective_findings"],
                artifact_path.as_posix(), now,
            ),
        )
        for proposal in proposals:
            proposal_id = str(uuid4())
            connection.execute(
                """INSERT INTO calibration_proposals (
                    id, run_id, stable_key, proposal_kind, sheet_type, technical_scope,
                    rule_id, title, rationale, payload_json, policy_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    proposal_id, run_id, proposal["stable_key"], proposal["proposal_kind"],
                    proposal.get("sheet_type"), proposal.get("technical_scope"), proposal.get("rule_id"),
                    proposal["title"], proposal["rationale"], json.dumps(proposal["payload"], ensure_ascii=False, sort_keys=True),
                    proposal["policy_version"], now,
                ),
            )
            for evidence in proposal.get("evidence", []):
                bbox = evidence.get("bbox") or {}
                connection.execute(
                    """INSERT INTO calibration_proposal_evidence (
                        id, proposal_id, evidence_key, evidence_kind, document_sha256,
                        page_index, sheet_code, x0, y0, x1, y1, source_finding_id,
                        description, payload_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(uuid4()), proposal_id, evidence["evidence_key"], evidence["evidence_kind"],
                        evidence.get("document_sha256"), evidence.get("page_index"), evidence.get("sheet_code"),
                        bbox.get("x0"), bbox.get("y0"), bbox.get("x1"), bbox.get("y1"),
                        evidence.get("source_finding_id"), evidence["description"],
                        json.dumps(evidence.get("payload", {}), ensure_ascii=False, sort_keys=True), now,
                    ),
                )
    return run_id


def _decision_for(connection: Connection, stable_key: str) -> dict[str, Any] | None:
    row = connection.execute(
        """SELECT * FROM calibration_proposal_decisions
           WHERE stable_key = ? AND revoked_at IS NULL ORDER BY created_at DESC LIMIT 1""",
        (stable_key,),
    ).fetchone()
    return dict(row) if row else None


def _evidence_for(connection: Connection, proposal_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT * FROM calibration_proposal_evidence WHERE proposal_id = ? ORDER BY evidence_kind, evidence_key",
        (proposal_id,),
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["bbox"] = (
            {key: item.pop(key) for key in ("x0", "y0", "x1", "y1")}
            if item["x0"] is not None else None
        )
        item["payload"] = json.loads(item.pop("payload_json"))
        result.append(item)
    return result


def _proposal_from_row(connection: Connection, row: Row) -> dict[str, Any]:
    item = dict(row)
    item["payload"] = json.loads(item.pop("payload_json"))
    item["evidence"] = _evidence_for(connection, str(row["id"]))
    item["decision"] = _decision_for(connection, str(row["stable_key"]))
    item["state"] = (
        "pending" if item["decision"] is None
        else "ready_for_implementation" if item["decision"]["decision"] == "approved"
        else "dismissed"
    )
    return item


def list_runs(settings: Settings) -> list[dict[str, Any]]:
    with transaction(settings) as connection:
        rows = connection.execute("SELECT * FROM calibration_runs ORDER BY created_at DESC").fetchall()
    return [dict(row) for row in rows]


def get_run(run_id: str, settings: Settings) -> dict[str, Any]:
    with transaction(settings) as connection:
        row = connection.execute("SELECT * FROM calibration_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise CalibrationNotFoundError(run_id)
        item = dict(row)
        report_path = settings.data_dir / str(item["artifact_path"])
        item["metrics"] = json.loads(report_path.read_text(encoding="utf-8"))["metrics"]
        item["proposals"] = [
            _proposal_from_row(connection, proposal)
            for proposal in connection.execute(
                "SELECT * FROM calibration_proposals WHERE run_id = ? ORDER BY proposal_kind, stable_key", (run_id,)
            ).fetchall()
        ]
    return item


def list_proposals(settings: Settings, run_id: str | None = None) -> list[dict[str, Any]]:
    with transaction(settings) as connection:
        if run_id:
            rows = connection.execute(
                "SELECT * FROM calibration_proposals WHERE run_id = ? ORDER BY proposal_kind, stable_key", (run_id,)
            ).fetchall()
        else:
            rows = connection.execute(
                """SELECT proposal.* FROM calibration_proposals proposal
                   JOIN calibration_runs run ON run.id = proposal.run_id
                   WHERE run.id = (SELECT id FROM calibration_runs ORDER BY created_at DESC LIMIT 1)
                   ORDER BY proposal.proposal_kind, proposal.stable_key"""
            ).fetchall()
        return [_proposal_from_row(connection, row) for row in rows]


def get_proposal(proposal_id: str, settings: Settings) -> dict[str, Any]:
    with transaction(settings) as connection:
        row = connection.execute("SELECT * FROM calibration_proposals WHERE id = ?", (proposal_id,)).fetchone()
        if row is None:
            raise CalibrationNotFoundError(proposal_id)
        return _proposal_from_row(connection, row)


def decide(proposal_id: str, decision: str, reason: str, settings: Settings) -> dict[str, Any]:
    with transaction(settings) as connection:
        proposal = connection.execute("SELECT * FROM calibration_proposals WHERE id = ?", (proposal_id,)).fetchone()
        if proposal is None:
            raise CalibrationNotFoundError(proposal_id)
        if _decision_for(connection, str(proposal["stable_key"])):
            raise CalibrationDecisionConflictError("A proposta ja possui decisao ativa")
        connection.execute(
            """INSERT INTO calibration_proposal_decisions
               (id, stable_key, proposal_id, decision, reason, created_at, revoked_at)
               VALUES (?, ?, ?, ?, ?, ?, NULL)""",
            (str(uuid4()), proposal["stable_key"], proposal_id, decision, reason, _now()),
        )
    return get_proposal(proposal_id, settings)


def revoke_decision(decision_id: str, settings: Settings) -> dict[str, Any]:
    with transaction(settings) as connection:
        row = connection.execute("SELECT * FROM calibration_proposal_decisions WHERE id = ?", (decision_id,)).fetchone()
        if row is None or row["revoked_at"] is not None:
            raise CalibrationNotFoundError(decision_id)
        connection.execute("UPDATE calibration_proposal_decisions SET revoked_at = ? WHERE id = ?", (_now(), decision_id))
        proposal_id = str(row["proposal_id"])
    return get_proposal(proposal_id, settings)


def export_snapshot(run_id: str, settings: Settings) -> dict[str, Any]:
    with transaction(settings) as connection:
        run = connection.execute("SELECT * FROM calibration_runs WHERE id = ?", (run_id,)).fetchone()
        if run is None:
            raise CalibrationNotFoundError(run_id)
        proposals = connection.execute(
            "SELECT * FROM calibration_proposals WHERE run_id = ? ORDER BY proposal_kind, stable_key", (run_id,)
        ).fetchall()
        proposal_ids = [str(row["id"]) for row in proposals]
        evidence: list[dict[str, Any]] = []
        decisions: list[dict[str, Any]] = []
        for proposal_id in proposal_ids:
            evidence.extend(
                dict(row) for row in connection.execute(
                    "SELECT * FROM calibration_proposal_evidence WHERE proposal_id = ? ORDER BY evidence_key", (proposal_id,)
                ).fetchall()
            )
            decisions.extend(
                dict(row) for row in connection.execute(
                    "SELECT * FROM calibration_proposal_decisions WHERE proposal_id = ? ORDER BY created_at, id", (proposal_id,)
                ).fetchall()
            )
        preferences = [
            dict(row) for row in connection.execute(
                "SELECT * FROM rule_preferences ORDER BY created_at, id"
            ).fetchall()
        ]
        learning_decisions = [
            dict(row) for row in connection.execute(
                "SELECT * FROM learning_proposal_decisions ORDER BY created_at, id"
            ).fetchall()
        ]
    return {
        "run": dict(run),
        "proposals": [dict(row) for row in proposals],
        "evidence": evidence,
        "decisions": decisions,
        "preferences": preferences,
        "learning_decisions": learning_decisions,
        "feedback": feedback_snapshot(settings),
    }


def evidence_preview_context(evidence_id: str, settings: Settings) -> dict[str, Any]:
    with transaction(settings) as connection:
        row = connection.execute(
            """
            SELECT evidence.*, run.artifact_path
            FROM calibration_proposal_evidence evidence
            JOIN calibration_proposals proposal ON proposal.id = evidence.proposal_id
            JOIN calibration_runs run ON run.id = proposal.run_id
            WHERE evidence.id = ?
            """,
            (evidence_id,),
        ).fetchone()
    if row is None:
        raise CalibrationNotFoundError(evidence_id)
    return dict(row)
