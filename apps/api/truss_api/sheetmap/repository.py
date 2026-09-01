from datetime import UTC, datetime
import json
import sqlite3
from uuid import uuid4

from truss_api.core.settings import Settings
from truss_api.db.connection import transaction
from truss_api.sheetmap.regions import DetectedRegion
from truss_api.sheetmap.elements.models import DetectedElement
from truss_api.sheetmap.snapshot import SHEET_MAP_PIPELINE, pipeline_version_for
from truss_api.sheetmap.technical_scopes import DetectedTechnicalScope, scope_for_sheet_type
from truss_api.sheetmap.views.models import DetectedView


class SheetMapNotFoundError(Exception):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _insert_view(
    connection: sqlite3.Connection,
    view: DetectedView,
    *,
    sheet_map_id: str,
    parent_view_id: str | None,
    built_at: str,
) -> str:
    view_id = str(uuid4())

    connection.execute(
        """
        INSERT INTO sheet_views (
            id, sheet_map_id, parent_view_id, region_id, view_kind, view_role,
            identifier, title_raw, title, declared_scale_raw, declared_scale,
            level_raw, level, x0, y0, x1, y1, confidence, provenance,
            technical_scope, created_at
        ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            view_id,
            sheet_map_id,
            parent_view_id,
            view.view_kind,
            view.view_role,
            view.identifier,
            view.title.raw,
            view.title.normalized,
            view.declared_scale.raw,
            view.declared_scale.normalized,
            view.level.raw,
            view.level.normalized,
            view.bbox[0],
            view.bbox[1],
            view.bbox[2],
            view.bbox[3],
            view.confidence,
            view.provenance,
            view.technical_scope,
            built_at,
        ),
    )

    # Subviews de um detalhe agrupador pendem do pai, nunca soltas na folha.
    for subview in view.subviews:
        _insert_view(
            connection,
            subview,
            sheet_map_id=sheet_map_id,
            parent_view_id=view_id,
            built_at=built_at,
        )

    return view_id


def save_sheet_map(
    *,
    sheet_id: str,
    project_id: str,
    revision_id: str,
    geometry_path: str,
    sheet_code: str | None,
    sheet_code_raw: str | None = None,
    sheet_type: str,
    paper_format: str,
    orientation: str,
    title_block: dict[str, object],
    technical_scopes: list[DetectedTechnicalScope] | None = None,
    regions: list[DetectedRegion],
    views: list[DetectedView],
    elements: list[DetectedElement] | None = None,
    snapshot_hash: str,
    extractor_version: str,
    document_hash: str,
    settings: Settings,
) -> dict[str, object]:
    pipeline_version = pipeline_version_for(snapshot_hash)
    sheet_map_id = str(uuid4())
    built_at = _now()
    resolved_scopes = technical_scopes
    if resolved_scopes is None:
        legacy_scope = scope_for_sheet_type(sheet_type)
        resolved_scopes = (
            [
                DetectedTechnicalScope(
                    technical_scope=legacy_scope,
                    confidence=float(title_block.get("classification_confidence") or 0.5),
                    provenance="sheet_type",
                )
            ]
            if legacy_scope
            else []
        )

    with transaction(settings) as connection:
        existing = connection.execute(
            "SELECT id FROM sheet_maps WHERE sheet_id = ? AND pipeline_version = ?",
            (sheet_id, pipeline_version),
        ).fetchone()

        # Snapshot e enderecado por conteudo: entrada identica reutiliza a linha
        # existente. Nada e apagado, porque auditorias podem referencia-la.
        if existing is not None:
            return get_sheet_map_by_id(str(existing["id"]), settings)

        connection.execute(
            """
            INSERT INTO sheet_maps (
                id, sheet_id, project_id, revision_id, pipeline_version, status,
                geometry_path, sheet_code, sheet_code_raw, sheet_type, paper_format, orientation,
                title_block_json, built_at, snapshot_hash, extractor_version, document_hash
            ) VALUES (?, ?, ?, ?, ?, 'completed', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sheet_map_id,
                sheet_id,
                project_id,
                revision_id,
                pipeline_version,
                geometry_path,
                sheet_code,
                sheet_code_raw if sheet_code_raw is not None else sheet_code,
                sheet_type,
                paper_format,
                orientation,
                json.dumps(title_block),
                built_at,
                snapshot_hash,
                extractor_version,
                document_hash,
            ),
        )

        for item in resolved_scopes:
            connection.execute(
                """
                INSERT INTO sheet_map_scopes (
                    id, sheet_map_id, technical_scope, confidence, provenance, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    sheet_map_id,
                    item.technical_scope,
                    item.confidence,
                    item.provenance,
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

        view_ids: list[str] = []
        for view in views:
            view_ids.append(_insert_view(
                connection,
                view,
                sheet_map_id=sheet_map_id,
                parent_view_id=None,
                built_at=built_at,
            ))

        for element in elements or []:
            view_id = (
                view_ids[element.view_index]
                if element.view_index is not None and 0 <= element.view_index < len(view_ids)
                else None
            )
            connection.execute(
                """
                INSERT INTO sheet_elements (
                    id, sheet_map_id, view_id, technical_scope, element_kind,
                    code_raw, code, attributes_json, x0, y0, x1, y1,
                    confidence, provenance, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    sheet_map_id,
                    view_id,
                    element.technical_scope,
                    element.element_kind,
                    element.code_raw,
                    element.code,
                    json.dumps(element.attributes, ensure_ascii=False),
                    element.bbox[0],
                    element.bbox[1],
                    element.bbox[2],
                    element.bbox[3],
                    element.confidence,
                    element.provenance,
                    built_at,
                ),
            )

    return get_sheet_map_by_id(sheet_map_id, settings)


def _load(connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, object]:
    sheet_map = dict(row)
    sheet_map["title_block"] = json.loads(str(row["title_block_json"]))
    sheet_map["technical_scopes"] = [
        dict(item)
        for item in connection.execute(
            """
            SELECT technical_scope, confidence, provenance
            FROM sheet_map_scopes WHERE sheet_map_id = ?
            ORDER BY CASE technical_scope
                WHEN 'locacao' THEN 0
                WHEN 'fundacoes' THEN 1
                WHEN 'formas' THEN 2
                WHEN 'armaduras' THEN 3
                WHEN 'cobertura' THEN 4
                ELSE 5
            END, technical_scope
            """,
            (str(row["id"]),),
        ).fetchall()
    ]
    if not sheet_map["technical_scopes"]:
        legacy_scope = scope_for_sheet_type(str(row["sheet_type"]))
        if legacy_scope:
            sheet_map["technical_scopes"] = [
                {
                    "technical_scope": legacy_scope,
                    "confidence": float(
                        sheet_map["title_block"].get("classification_confidence") or 0.5
                    ),
                    "provenance": "legacy_sheet_type",
                }
            ]
    sheet_map["regions"] = [
        dict(item)
        for item in connection.execute(
            """
            SELECT id, region_kind, x0, y0, x1, y1, confidence
            FROM sheet_regions WHERE sheet_map_id = ? ORDER BY region_kind
            """,
            (str(row["id"]),),
        ).fetchall()
    ]
    sheet_map["views"] = [
        dict(item)
        for item in connection.execute(
            """
            SELECT id, parent_view_id, view_kind, view_role, identifier,
                   title_raw, title, declared_scale_raw, declared_scale,
                   level_raw, level, x0, y0, x1, y1, confidence, provenance,
                   technical_scope
            FROM sheet_views WHERE sheet_map_id = ? ORDER BY y0, x0
            """,
            (str(row["id"]),),
        ).fetchall()
    ]
    sheet_map["elements"] = []
    for item in connection.execute(
        """
        SELECT id, view_id, technical_scope, element_kind, code_raw, code,
               attributes_json, x0, y0, x1, y1, confidence, provenance
        FROM sheet_elements WHERE sheet_map_id = ? ORDER BY y0, x0, code
        """,
        (str(row["id"]),),
    ).fetchall():
        element = dict(item)
        element["attributes"] = json.loads(str(element.pop("attributes_json") or "{}"))
        sheet_map["elements"].append(element)
    return sheet_map


def get_sheet_map_by_id(sheet_map_id: str, settings: Settings) -> dict[str, object]:
    with transaction(settings) as connection:
        row = connection.execute(
            "SELECT * FROM sheet_maps WHERE id = ?", (sheet_map_id,)
        ).fetchone()

        if row is None:
            raise SheetMapNotFoundError(sheet_map_id)

        return _load(connection, row)


def get_sheet_map(sheet_id: str, settings: Settings) -> dict[str, object]:
    """Snapshot corrente da folha: o mais recente do pipeline atual."""
    with transaction(settings) as connection:
        row = connection.execute(
            """
            SELECT * FROM sheet_maps
            WHERE sheet_id = ? AND pipeline_version LIKE ?
            ORDER BY built_at DESC LIMIT 1
            """,
            (sheet_id, f"{SHEET_MAP_PIPELINE}%"),
        ).fetchone()

        # Snapshots v0.2 continuam legiveis ate o documento ser reprocessado.
        # Eles recebem apenas o escopo derivado do sheet_type, sem mutacao da
        # linha imutavel nem alegacao de segmentacao multiescopo.
        if row is None:
            row = connection.execute(
                """
                SELECT * FROM sheet_maps
                WHERE sheet_id = ?
                ORDER BY built_at DESC LIMIT 1
                """,
                (sheet_id,),
            ).fetchone()

        if row is None:
            raise SheetMapNotFoundError(sheet_id)

        return _load(connection, row)
