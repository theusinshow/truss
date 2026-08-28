from datetime import UTC, datetime
import json
from uuid import uuid4

from truss_api.core.settings import Settings
from truss_api.db.connection import transaction
from truss_api.sheetmap.regions import DetectedRegion


PIPELINE_VERSION = "sheetmap-v0.1"


class SheetMapNotFoundError(Exception):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


def save_sheet_map(
    *,
    sheet_id: str,
    project_id: str,
    revision_id: str,
    geometry_path: str,
    sheet_code: str | None,
    sheet_type: str,
    paper_format: str,
    orientation: str,
    title_block: dict[str, object],
    regions: list[DetectedRegion],
    settings: Settings,
) -> dict[str, object]:
    sheet_map_id = str(uuid4())
    built_at = _now()

    with transaction(settings) as connection:
        connection.execute(
            "DELETE FROM sheet_regions WHERE sheet_map_id IN ("
            "  SELECT id FROM sheet_maps WHERE sheet_id = ? AND pipeline_version = ?"
            ")",
            (sheet_id, PIPELINE_VERSION),
        )
        connection.execute(
            "DELETE FROM sheet_maps WHERE sheet_id = ? AND pipeline_version = ?",
            (sheet_id, PIPELINE_VERSION),
        )
        connection.execute(
            """
            INSERT INTO sheet_maps (
                id, sheet_id, project_id, revision_id, pipeline_version, status,
                geometry_path, sheet_code, sheet_type, paper_format, orientation,
                title_block_json, built_at
            ) VALUES (?, ?, ?, ?, ?, 'completed', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sheet_map_id,
                sheet_id,
                project_id,
                revision_id,
                PIPELINE_VERSION,
                geometry_path,
                sheet_code,
                sheet_type,
                paper_format,
                orientation,
                json.dumps(title_block),
                built_at,
            ),
        )

        for region in regions:
            connection.execute(
                """
                INSERT INTO sheet_regions (
                    id, sheet_map_id, region_kind, x0, y0, x1, y1, confidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    sheet_map_id,
                    region.region_kind,
                    region.x0,
                    region.y0,
                    region.x1,
                    region.y1,
                    region.confidence,
                    built_at,
                ),
            )

    return get_sheet_map(sheet_id, settings)


def get_sheet_map(sheet_id: str, settings: Settings) -> dict[str, object]:
    with transaction(settings) as connection:
        row = connection.execute(
            "SELECT * FROM sheet_maps WHERE sheet_id = ? AND pipeline_version = ?",
            (sheet_id, PIPELINE_VERSION),
        ).fetchone()

        if row is None:
            raise SheetMapNotFoundError(sheet_id)

        regions = connection.execute(
            """
            SELECT id, region_kind, x0, y0, x1, y1, confidence
            FROM sheet_regions WHERE sheet_map_id = ?
            ORDER BY region_kind
            """,
            (str(row["id"]),),
        ).fetchall()

    sheet_map = dict(row)
    sheet_map["title_block"] = json.loads(str(row["title_block_json"]))
    sheet_map["regions"] = [dict(region) for region in regions]
    return sheet_map
