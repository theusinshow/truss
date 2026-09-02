from datetime import UTC, datetime
from sqlite3 import Connection, Row
from uuid import uuid4

from truss_api.core.settings import Settings
from truss_api.db.connection import transaction
from truss_api.preferences.models import RulePreferenceCreate


UNCLASSIFIED_SHEET_TYPES = {"", "unknown", "nao_classificada", "not_verifiable"}


class FindingNotEligibleForPreferenceError(Exception):
    pass


class FindingNotFoundForPreferenceError(Exception):
    pass


class RulePreferenceNotFoundError(Exception):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _preference_from_row(row: Row) -> dict[str, object]:
    data = dict(row)
    data["active"] = data["revoked_at"] is None
    return data


def _source_for_finding(connection: Connection, finding_id: str) -> dict[str, object] | None:
    row = connection.execute(
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
                    SELECT latest.sheet_code
                    FROM sheet_maps latest
                    WHERE latest.sheet_id = f.sheet_id
                    ORDER BY latest.built_at DESC
                    LIMIT 1
                )
            ) AS sheet_code,
            f.x0, f.y0, f.x1, f.y1,
            f.description,
            f.rejection_reason
        FROM findings f
        JOIN projects p ON p.id = f.project_id
        JOIN revisions r ON r.id = f.revision_id
        JOIN documents d ON d.id = f.document_id
        JOIN sheets s ON s.id = f.sheet_id
        LEFT JOIN sheet_maps sm ON sm.id = f.sheet_map_id
        WHERE f.id = ?
        """,
        (finding_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "finding_id": str(row["finding_id"]),
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
    }


def _enrich_preference(connection: Connection, row: Row) -> dict[str, object]:
    data = _preference_from_row(row)
    data["source"] = _source_for_finding(connection, str(row["source_finding_id"]))
    return data


def _sheet_type_for_finding(connection: Connection, finding: Row) -> str:
    sheet_map_id = finding["sheet_map_id"]
    if sheet_map_id:
        row = connection.execute(
            "SELECT sheet_type FROM sheet_maps WHERE id = ?",
            (str(sheet_map_id),),
        ).fetchone()
        if row is not None:
            return str(row["sheet_type"] or "").strip()

    row = connection.execute(
        """
        SELECT sheet_type
        FROM sheet_maps
        WHERE sheet_id = ?
        ORDER BY built_at DESC
        LIMIT 1
        """,
        (str(finding["sheet_id"]),),
    ).fetchone()
    return str(row["sheet_type"] or "").strip() if row is not None else ""


def _current_sheet_type(connection: Connection, sheet_id: str) -> str:
    row = connection.execute(
        """
        SELECT sheet_type
        FROM sheet_maps
        WHERE sheet_id = ?
        ORDER BY built_at DESC
        LIMIT 1
        """,
        (sheet_id,),
    ).fetchone()
    return str(row["sheet_type"] or "").strip() if row is not None else ""


def create_suppression_in_connection(
    connection: Connection,
    finding_id: str,
    reason: str,
) -> dict[str, object]:
    finding = connection.execute(
        "SELECT * FROM findings WHERE id = ?",
        (finding_id,),
    ).fetchone()
    if finding is None:
        raise FindingNotFoundForPreferenceError(finding_id)
    if finding["status"] != "rejected":
        raise FindingNotEligibleForPreferenceError(
            "Somente um achado rejeitado pode propor uma preferencia."
        )
    if finding["origin"] != "ai" or not finding["rule_id"]:
        raise FindingNotEligibleForPreferenceError(
            "O achado precisa ter origem automatica e uma regra rastreavel."
        )

    sheet_type = _sheet_type_for_finding(connection, finding)
    if sheet_type.lower() in UNCLASSIFIED_SHEET_TYPES:
        raise FindingNotEligibleForPreferenceError(
            "O tipo da prancha precisa estar classificado antes da supressao."
        )

    existing = connection.execute(
        """
        SELECT * FROM rule_preferences
        WHERE scope = 'sheet_type'
          AND sheet_type = ?
          AND rule_id = ?
          AND action = 'suppress'
          AND revoked_at IS NULL
        """,
        (sheet_type, str(finding["rule_id"])),
    ).fetchone()
    if existing is not None:
        return _enrich_preference(connection, existing)

    preference_id = str(uuid4())
    connection.execute(
        """
        INSERT INTO rule_preferences (
            id, scope, sheet_type, rule_id, action, reason,
            source_finding_id, created_at, revoked_at
        ) VALUES (?, 'sheet_type', ?, ?, 'suppress', ?, ?, ?, NULL)
        """,
        (
            preference_id,
            sheet_type,
            str(finding["rule_id"]),
            reason.strip(),
            finding_id,
            _now(),
        ),
    )
    row = connection.execute(
        "SELECT * FROM rule_preferences WHERE id = ?",
        (preference_id,),
    ).fetchone()
    return _enrich_preference(connection, row)


def create_suppression_for_finding(
    finding_id: str,
    payload: RulePreferenceCreate,
    settings: Settings,
) -> dict[str, object]:
    with transaction(settings) as connection:
        return create_suppression_in_connection(
            connection, finding_id, payload.reason
        )


def list_rule_preferences(
    settings: Settings,
    *,
    include_revoked: bool = False,
    status: str | None = None,
    sheet_type: str | None = None,
    rule_id: str | None = None,
) -> list[dict[str, object]]:
    clauses: list[str] = []
    parameters: list[str] = []
    resolved_status = status or ("all" if include_revoked else "active")
    if resolved_status == "active":
        clauses.append("revoked_at IS NULL")
    elif resolved_status == "revoked":
        clauses.append("revoked_at IS NOT NULL")
    if sheet_type:
        clauses.append("sheet_type = ?")
        parameters.append(sheet_type)
    if rule_id:
        clauses.append("rule_id = ?")
        parameters.append(rule_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with transaction(settings) as connection:
        rows = connection.execute(
            f"""
            SELECT * FROM rule_preferences
            {where}
            ORDER BY created_at DESC, id DESC
            """,
            parameters,
        ).fetchall()
        return [_enrich_preference(connection, row) for row in rows]


def revoke_rule_preference_in_connection(
    connection: Connection,
    preference_id: str,
) -> dict[str, object]:
    current = connection.execute(
        "SELECT * FROM rule_preferences WHERE id = ?",
        (preference_id,),
    ).fetchone()
    if current is None:
        raise RulePreferenceNotFoundError(preference_id)

    if current["revoked_at"] is None:
        connection.execute(
            "UPDATE rule_preferences SET revoked_at = ? WHERE id = ?",
            (_now(), preference_id),
        )
    row = connection.execute(
        "SELECT * FROM rule_preferences WHERE id = ?",
        (preference_id,),
    ).fetchone()
    return _enrich_preference(connection, row)


def revoke_rule_preference(
    preference_id: str,
    settings: Settings,
) -> dict[str, object]:
    with transaction(settings) as connection:
        return revoke_rule_preference_in_connection(connection, preference_id)


def reactivate_rule_preference(
    preference_id: str,
    settings: Settings,
) -> dict[str, object]:
    with transaction(settings) as connection:
        previous = connection.execute(
            "SELECT * FROM rule_preferences WHERE id = ?",
            (preference_id,),
        ).fetchone()
        if previous is None:
            raise RulePreferenceNotFoundError(preference_id)
        if previous["revoked_at"] is None:
            return _enrich_preference(connection, previous)
        return create_suppression_in_connection(
            connection,
            str(previous["source_finding_id"]),
            str(previous["reason"]),
        )


def annotate_findings_with_preferences(
    findings: list[dict[str, object]],
    sheet_id: str,
    settings: Settings,
) -> list[dict[str, object]]:
    with transaction(settings) as connection:
        sheet_type = _current_sheet_type(connection, sheet_id)
        rows = connection.execute(
            """
            SELECT * FROM rule_preferences
            WHERE scope = 'sheet_type'
              AND sheet_type = ?
              AND action = 'suppress'
              AND revoked_at IS NULL
            """,
            (sheet_type,),
        ).fetchall()

    active_by_rule = {str(row["rule_id"]): row for row in rows}
    annotated: list[dict[str, object]] = []
    for finding in findings:
        preference = active_by_rule.get(str(finding.get("rule_id") or ""))
        item = dict(finding)
        item["suppressed"] = preference is not None
        item["suppression_preference_id"] = (
            str(preference["id"]) if preference is not None else None
        )
        item["suppression_sheet_type"] = sheet_type if preference is not None else None
        annotated.append(item)
    return annotated
