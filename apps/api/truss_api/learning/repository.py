from collections import defaultdict
from datetime import UTC, datetime
from sqlite3 import Connection, Row
from typing import Any
from uuid import uuid4

from truss_api.core.settings import Settings
from truss_api.db.connection import transaction
from truss_api.learning.models import LearningDecisionCreate
from truss_api.learning.policy import (
    POLICY_VERSION,
    automatic_key,
    is_classified_sheet_type,
    manual_key,
)


class LearningProposalNotFoundError(Exception):
    pass


class LearningProposalNotEligibleError(Exception):
    pass


class LearningDecisionConflictError(Exception):
    pass


class LearningDecisionNotFoundError(Exception):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _finding_rows(connection: Connection) -> list[Row]:
    return connection.execute(
        """
        SELECT
            f.id AS finding_id,
            f.project_id,
            p.name AS project_name,
            f.revision_id,
            r.revision_code,
            f.document_id,
            d.original_filename AS document_name,
            f.sheet_id,
            s.label AS sheet_label,
            s.sheet_number,
            COALESCE(
                sm.sheet_code,
                (
                    SELECT latest_code.sheet_code
                    FROM sheet_maps latest_code
                    WHERE latest_code.sheet_id = f.sheet_id
                    ORDER BY latest_code.built_at DESC
                    LIMIT 1
                )
            ) AS sheet_code,
            COALESCE(
                NULLIF(sm.sheet_type, ''),
                (
                    SELECT latest_type.sheet_type
                    FROM sheet_maps latest_type
                    WHERE latest_type.sheet_id = f.sheet_id
                    ORDER BY latest_type.built_at DESC
                    LIMIT 1
                ),
                ''
            ) AS sheet_type,
            f.category,
            f.type AS finding_type,
            f.description,
            f.origin,
            f.status AS finding_status,
            f.rejection_reason,
            f.rule_id,
            f.x0,
            f.y0,
            f.x1,
            f.y1,
            f.created_at
        FROM findings f
        JOIN projects p ON p.id = f.project_id
        JOIN revisions r ON r.id = f.revision_id
        JOIN documents d ON d.id = f.document_id
        JOIN sheets s ON s.id = f.sheet_id
        LEFT JOIN sheet_maps sm ON sm.id = f.sheet_map_id
        ORDER BY f.created_at DESC, f.id DESC
        """
    ).fetchall()


def _evidence_from_row(row: Row, signal_kind: str) -> dict[str, object]:
    return {
        "finding_id": str(row["finding_id"]),
        "signal_kind": signal_kind,
        "project_id": str(row["project_id"]),
        "project_name": str(row["project_name"]),
        "revision_id": str(row["revision_id"]),
        "revision_code": str(row["revision_code"]),
        "document_id": str(row["document_id"]),
        "document_name": str(row["document_name"]),
        "sheet_id": str(row["sheet_id"]),
        "sheet_label": str(row["sheet_label"]),
        "sheet_number": int(row["sheet_number"]),
        "sheet_code": str(row["sheet_code"]) if row["sheet_code"] else None,
        "sheet_type": str(row["sheet_type"]),
        "bbox": {
            "x0": float(row["x0"]),
            "y0": float(row["y0"]),
            "x1": float(row["x1"]),
            "y1": float(row["y1"]),
        },
        "description": str(row["description"]),
        "rejection_reason": (
            str(row["rejection_reason"]) if row["rejection_reason"] else None
        ),
        "rule_id": str(row["rule_id"]) if row["rule_id"] else None,
        "finding_status": str(row["finding_status"]),
        "created_at": str(row["created_at"]),
    }


def _active_decisions(connection: Connection) -> dict[str, dict[str, object]]:
    rows = connection.execute(
        """
        SELECT
            decision.*,
            preference.id AS linked_preference_id,
            preference.revoked_at AS preference_revoked_at,
            COUNT(evidence.finding_id) AS evidence_count
        FROM learning_proposal_decisions decision
        LEFT JOIN rule_preferences preference ON preference.id = decision.preference_id
        LEFT JOIN learning_proposal_evidence evidence ON evidence.decision_id = decision.id
        WHERE decision.revoked_at IS NULL
        GROUP BY decision.id
        ORDER BY decision.created_at DESC
        """
    ).fetchall()

    decisions: dict[str, dict[str, object]] = {}
    for row in rows:
        preference_id = (
            str(row["linked_preference_id"]) if row["linked_preference_id"] else None
        )
        decisions[str(row["stable_key"])] = {
            "id": str(row["id"]),
            "stable_key": str(row["stable_key"]),
            "proposal_kind": str(row["proposal_kind"]),
            "decision": str(row["decision"]),
            "reason": str(row["reason"]),
            "policy_version": str(row["policy_version"]),
            "preference_id": preference_id,
            "preference_active": (
                preference_id is not None and row["preference_revoked_at"] is None
            ),
            "evidence_count": int(row["evidence_count"]),
            "created_at": str(row["created_at"]),
            "revoked_at": None,
            "active": True,
        }
    return decisions


def _active_preferences(connection: Connection) -> dict[str, str]:
    rows = connection.execute(
        """
        SELECT id, sheet_type, rule_id
        FROM rule_preferences
        WHERE action = 'suppress' AND revoked_at IS NULL
        """
    ).fetchall()
    return {
        automatic_key(str(row["sheet_type"]), str(row["rule_id"])): str(row["id"])
        for row in rows
    }


def _active_decision_evidence(
    connection: Connection,
    finding_rows: list[Row],
) -> dict[str, list[dict[str, object]]]:
    findings_by_id = {str(row["finding_id"]): row for row in finding_rows}
    rows = connection.execute(
        """
        SELECT decision.stable_key, evidence.finding_id, evidence.signal_kind
        FROM learning_proposal_decisions decision
        JOIN learning_proposal_evidence evidence ON evidence.decision_id = decision.id
        WHERE decision.revoked_at IS NULL
        ORDER BY evidence.created_at, evidence.finding_id
        """
    ).fetchall()
    snapshots: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        finding = findings_by_id.get(str(row["finding_id"]))
        if finding is None:
            continue
        snapshots[str(row["stable_key"])].append(
            _evidence_from_row(finding, str(row["signal_kind"]))
        )
    return snapshots


def _proposal(
    *,
    stable_key: str,
    proposal_kind: str,
    sheet_type: str,
    rule_id: str | None,
    normalized_description: str | None,
    evidence: list[dict[str, object]],
    decisions: dict[str, dict[str, object]],
    active_preferences: dict[str, str],
) -> dict[str, object]:
    confirmed_count = sum(1 for item in evidence if item["signal_kind"] == "confirmed")
    rejected_count = sum(1 for item in evidence if item["signal_kind"] == "rejected")
    manual_count = sum(1 for item in evidence if item["signal_kind"] == "manual")
    sheet_count = len({str(item["sheet_id"]) for item in evidence})
    revision_count = len({str(item["revision_id"]) for item in evidence})
    project_count = len({str(item["project_id"]) for item in evidence})

    observed_ratio: float | None = None
    minimum_ratio: float | None = None
    if proposal_kind in {"suppress_rule", "retain_rule"}:
        total = confirmed_count + rejected_count
        relevant = rejected_count if proposal_kind == "suppress_rule" else confirmed_count
        observed_ratio = relevant / total if total else 0.0
        minimum_ratio = 0.75

    if proposal_kind == "suppress_rule":
        minimum_evidence = 2
        threshold_reached = (
            rejected_count >= minimum_evidence
            and sheet_count >= 2
            and (observed_ratio or 0.0) >= 0.75
        )
        effect = "suppresses_findings"
    elif proposal_kind == "retain_rule":
        minimum_evidence = 3
        threshold_reached = (
            confirmed_count >= minimum_evidence
            and sheet_count >= 2
            and (observed_ratio or 0.0) >= 0.75
        )
        effect = "calibration_only"
    else:
        minimum_evidence = 3
        threshold_reached = manual_count >= minimum_evidence and sheet_count >= 2
        effect = "calibration_only"

    decision = decisions.get(stable_key)
    active_preference_id = active_preferences.get(stable_key)
    state = (
        str(decision["decision"])
        if decision is not None
        else (
            "approved"
            if proposal_kind == "suppress_rule" and active_preference_id is not None
            else ("pending" if threshold_reached else "insufficient")
        )
    )
    return {
        "stable_key": stable_key,
        "proposal_kind": proposal_kind,
        "state": state,
        "effect": effect,
        "policy_version": POLICY_VERSION,
        "sheet_type": sheet_type,
        "rule_id": rule_id,
        "normalized_description": normalized_description,
        "evidence_count": len(evidence),
        "confirmed_count": confirmed_count,
        "rejected_count": rejected_count,
        "manual_count": manual_count,
        "distinct_sheet_count": sheet_count,
        "distinct_revision_count": revision_count,
        "distinct_project_count": project_count,
        "observed_ratio": observed_ratio,
        "threshold": {
            "minimum_evidence": minimum_evidence,
            "minimum_sheets": 2,
            "minimum_ratio": minimum_ratio,
        },
        "threshold_reached": threshold_reached,
        "active_preference_id": active_preference_id,
        "evidence": evidence,
        "decision": decision,
    }


def _build_proposals(
    connection: Connection,
    *,
    include_insufficient: bool,
) -> list[dict[str, object]]:
    auto_groups: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"evidence": [], "sheet_type": "", "rule_id": ""}
    )
    manual_groups: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "evidence": [],
            "sheet_type": "",
            "normalized_description": "",
        }
    )

    finding_rows = _finding_rows(connection)
    for row in finding_rows:
        sheet_type = str(row["sheet_type"] or "").strip()
        if not is_classified_sheet_type(sheet_type):
            continue

        origin = str(row["origin"])
        status = str(row["finding_status"])
        rule_id = str(row["rule_id"] or "").strip()
        has_rejection_reason = bool(str(row["rejection_reason"] or "").strip())
        if (
            origin == "ai"
            and rule_id
            and status in {"confirmed", "rejected"}
            and (status != "rejected" or has_rejection_reason)
        ):
            key = automatic_key(sheet_type, rule_id)
            auto_groups[key]["sheet_type"] = sheet_type
            auto_groups[key]["rule_id"] = rule_id
            auto_groups[key]["evidence"].append(_evidence_from_row(row, status))
            continue

        if origin == "human":
            key, normalized = manual_key(
                sheet_type,
                str(row["category"]),
                str(row["finding_type"]),
                str(row["description"]),
            )
            manual_groups[key]["sheet_type"] = sheet_type
            manual_groups[key]["normalized_description"] = normalized
            manual_groups[key]["evidence"].append(_evidence_from_row(row, "manual"))

    decisions = _active_decisions(connection)
    decision_evidence = _active_decision_evidence(connection, finding_rows)
    active_preferences = _active_preferences(connection)
    proposals: list[dict[str, object]] = []
    for key, group in auto_groups.items():
        evidence = decision_evidence.get(key, list(group["evidence"]))
        confirmed = sum(1 for item in evidence if item["signal_kind"] == "confirmed")
        rejected = sum(1 for item in evidence if item["signal_kind"] == "rejected")
        proposal_kind = (
            str(decisions[key]["proposal_kind"])
            if key in decisions
            else ("suppress_rule" if rejected >= confirmed else "retain_rule")
        )
        proposals.append(
            _proposal(
                stable_key=key,
                proposal_kind=proposal_kind,
                sheet_type=str(group["sheet_type"]),
                rule_id=str(group["rule_id"]),
                normalized_description=None,
                evidence=evidence,
                decisions=decisions,
                active_preferences=active_preferences,
            )
        )

    for key, group in manual_groups.items():
        proposals.append(
            _proposal(
                stable_key=key,
                proposal_kind="draft_rule",
                sheet_type=str(group["sheet_type"]),
                rule_id=None,
                normalized_description=str(group["normalized_description"]),
                evidence=decision_evidence.get(key, list(group["evidence"])),
                decisions=decisions,
                active_preferences=active_preferences,
            )
        )

    represented_keys = {str(item["stable_key"]) for item in proposals}
    rows_by_finding_id = {str(row["finding_id"]): row for row in finding_rows}
    for key, decision in decisions.items():
        if key in represented_keys:
            continue
        evidence = decision_evidence.get(key, [])
        if not evidence:
            continue
        first_row = rows_by_finding_id[str(evidence[0]["finding_id"])]
        proposal_kind = str(decision["proposal_kind"])
        normalized_description = None
        rule_id = str(first_row["rule_id"]) if first_row["rule_id"] else None
        if proposal_kind == "draft_rule":
            _, normalized_description = manual_key(
                str(first_row["sheet_type"]),
                str(first_row["category"]),
                str(first_row["finding_type"]),
                str(first_row["description"]),
            )
            rule_id = None
        proposals.append(
            _proposal(
                stable_key=key,
                proposal_kind=proposal_kind,
                sheet_type=str(first_row["sheet_type"]),
                rule_id=rule_id,
                normalized_description=normalized_description,
                evidence=evidence,
                decisions=decisions,
                active_preferences=active_preferences,
            )
        )

    if not include_insufficient:
        proposals = [item for item in proposals if item["state"] != "insufficient"]
    state_order = {"pending": 0, "approved": 1, "dismissed": 2, "insufficient": 3}
    proposals.sort(
        key=lambda item: (
            state_order[str(item["state"])],
            -int(item["evidence_count"]),
            str(item["stable_key"]),
        )
    )
    return proposals


def list_learning_proposals(
    settings: Settings,
    *,
    include_insufficient: bool = False,
) -> list[dict[str, object]]:
    with transaction(settings) as connection:
        return _build_proposals(connection, include_insufficient=include_insufficient)


def get_learning_proposal(stable_key: str, settings: Settings) -> dict[str, object]:
    with transaction(settings) as connection:
        proposals = _build_proposals(connection, include_insufficient=True)
    proposal = next((item for item in proposals if item["stable_key"] == stable_key), None)
    if proposal is None:
        raise LearningProposalNotFoundError(stable_key)
    return proposal


def decide_learning_proposal(
    stable_key: str,
    payload: LearningDecisionCreate,
    settings: Settings,
) -> dict[str, object]:
    from truss_api.preferences import repository as preferences_repository

    now = _now()
    with transaction(settings) as connection:
        proposals = _build_proposals(connection, include_insufficient=True)
        proposal = next((item for item in proposals if item["stable_key"] == stable_key), None)
        if proposal is None:
            raise LearningProposalNotFoundError(stable_key)
        if not bool(proposal["threshold_reached"]):
            raise LearningProposalNotEligibleError(
                "A proposta ainda nao atingiu a politica minima de evidencia."
            )

        current = connection.execute(
            """
            SELECT * FROM learning_proposal_decisions
            WHERE stable_key = ? AND revoked_at IS NULL
            """,
            (stable_key,),
        ).fetchone()
        if current is not None:
            if (
                str(current["decision"]) == payload.decision
                and str(current["proposal_kind"]) == str(proposal["proposal_kind"])
            ):
                return proposal
            raise LearningDecisionConflictError(
                "Ja existe uma decisao ativa para esta chave de evidencia."
            )

        preference_id: str | None = None
        if payload.decision == "approved" and proposal["proposal_kind"] == "suppress_rule":
            source = next(
                item
                for item in proposal["evidence"]
                if item["signal_kind"] == "rejected"
            )
            preference = preferences_repository.create_suppression_in_connection(
                connection,
                str(source["finding_id"]),
                payload.reason.strip(),
            )
            preference_id = str(preference["id"])

        decision_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO learning_proposal_decisions (
                id, stable_key, proposal_kind, decision, reason,
                policy_version, preference_id, created_at, revoked_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                decision_id,
                stable_key,
                proposal["proposal_kind"],
                payload.decision,
                payload.reason.strip(),
                POLICY_VERSION,
                preference_id,
                now,
            ),
        )
        for evidence in proposal["evidence"]:
            connection.execute(
                """
                INSERT INTO learning_proposal_evidence (
                    decision_id, finding_id, signal_kind, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    decision_id,
                    evidence["finding_id"],
                    evidence["signal_kind"],
                    now,
                ),
            )

        refreshed = _build_proposals(connection, include_insufficient=True)
        return next(item for item in refreshed if item["stable_key"] == stable_key)


def revoke_learning_decision(
    decision_id: str,
    settings: Settings,
) -> dict[str, object]:
    from truss_api.preferences import repository as preferences_repository

    now = _now()
    with transaction(settings) as connection:
        decision = connection.execute(
            "SELECT * FROM learning_proposal_decisions WHERE id = ?",
            (decision_id,),
        ).fetchone()
        if decision is None:
            raise LearningDecisionNotFoundError(decision_id)

        if decision["revoked_at"] is None:
            if decision["preference_id"]:
                preferences_repository.revoke_rule_preference_in_connection(
                    connection, str(decision["preference_id"])
                )
            connection.execute(
                "UPDATE learning_proposal_decisions SET revoked_at = ? WHERE id = ?",
                (now, decision_id),
            )

        stable_key = str(decision["stable_key"])
        refreshed = _build_proposals(connection, include_insufficient=True)
        proposal = next(
            (item for item in refreshed if item["stable_key"] == stable_key), None
        )
        if proposal is None:
            raise LearningProposalNotFoundError(stable_key)
        return proposal
