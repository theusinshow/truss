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


def create_suppression_for_finding(
    finding_id: str,
    payload: RulePreferenceCreate,
    settings: Settings,
) -> dict[str, object]:
    with transaction(settings) as connection:
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
            return _preference_from_row(existing)

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
                payload.reason.strip(),
                finding_id,
                _now(),
            ),
        )
        row = connection.execute(
            "SELECT * FROM rule_preferences WHERE id = ?",
            (preference_id,),
        ).fetchone()
    return _preference_from_row(row)


def list_rule_preferences(
    settings: Settings,
    *,
    include_revoked: bool = False,
) -> list[dict[str, object]]:
    where = "" if include_revoked else "WHERE revoked_at IS NULL"
    with transaction(settings) as connection:
        rows = connection.execute(
            f"""
            SELECT * FROM rule_preferences
            {where}
            ORDER BY created_at DESC, id DESC
            """
        ).fetchall()
    return [_preference_from_row(row) for row in rows]


def revoke_rule_preference(
    preference_id: str,
    settings: Settings,
) -> dict[str, object]:
    with transaction(settings) as connection:
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
    return _preference_from_row(row)


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
