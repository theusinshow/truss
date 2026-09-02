from datetime import UTC, datetime
from sqlite3 import IntegrityError, Row
from uuid import uuid4

from truss_api.core.settings import Settings
from truss_api.db.connection import transaction
from truss_api.documents.importer import PreparedPdf


class DocumentNotFoundError(Exception):
    pass


class DuplicateDocumentError(Exception):
    pass


class RevisionNotFoundError(Exception):
    pass


class SheetNotFoundError(Exception):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_dict(row: Row) -> dict[str, object]:
    return dict(row)


def ensure_revision_belongs_to_project(
    project_id: str,
    revision_id: str,
    settings: Settings,
) -> None:
    with transaction(settings) as connection:
        row = connection.execute(
            "SELECT id FROM revisions WHERE id = ? AND project_id = ?",
            (revision_id, project_id),
        ).fetchone()

    if row is None:
        raise RevisionNotFoundError(revision_id)


def create_document_from_prepared_pdf(
    *,
    project_id: str,
    revision_id: str,
    prepared_pdf: PreparedPdf,
    settings: Settings,
) -> dict[str, object]:
    document_id = str(uuid4())
    created_at = _now()

    with transaction(settings) as connection:
        revision = connection.execute(
            "SELECT id FROM revisions WHERE id = ? AND project_id = ?",
            (revision_id, project_id),
        ).fetchone()

        if revision is None:
            raise RevisionNotFoundError(revision_id)

        try:
            connection.execute(
                """
                INSERT INTO documents (
                    id,
                    project_id,
                    revision_id,
                    original_filename,
                    stored_file_path,
                    content_hash,
                    mime_type,
                    file_size_bytes,
                    page_count,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    project_id,
                    revision_id,
                    prepared_pdf.original_filename,
                    prepared_pdf.stored_file_path,
                    prepared_pdf.content_hash,
                    prepared_pdf.mime_type,
                    prepared_pdf.file_size_bytes,
                    len(prepared_pdf.pages),
                    created_at,
                ),
            )
        except IntegrityError as error:
            if "UNIQUE" in str(error).upper():
                raise DuplicateDocumentError(prepared_pdf.content_hash) from error
            raise

        for page in prepared_pdf.pages:
            sheet_id = str(uuid4())
            connection.execute(
                """
                INSERT INTO sheets (
                    id,
                    document_id,
                    project_id,
                    revision_id,
                    page_index,
                    sheet_number,
                    width_pt,
                    height_pt,
                    rotation,
                    label,
                    render_path,
                    thumbnail_path,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sheet_id,
                    document_id,
                    project_id,
                    revision_id,
                    page.page_index,
                    page.sheet_number,
                    page.width_pt,
                    page.height_pt,
                    page.rotation,
                    page.label,
                    None,
                    None,
                    created_at,
                ),
            )

            for text_block in page.text_blocks:
                connection.execute(
                    """
                    INSERT INTO text_blocks (
                        id,
                        sheet_id,
                        document_id,
                        project_id,
                        revision_id,
                        block_index,
                        text,
                        x0,
                        y0,
                        x1,
                        y1,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid4()),
                        sheet_id,
                        document_id,
                        project_id,
                        revision_id,
                        text_block.block_index,
                        text_block.text,
                        text_block.x0,
                        text_block.y0,
                        text_block.x1,
                        text_block.y1,
                        created_at,
                    ),
                )

        connection.execute(
            "UPDATE projects SET updated_at = ? WHERE id = ?",
            (created_at, project_id),
        )

    return get_document(document_id, settings)


def list_documents_for_revision(
    revision_id: str,
    settings: Settings,
) -> list[dict[str, object]]:
    with transaction(settings) as connection:
        rows = connection.execute(
            """
            SELECT
                d.id,
                d.project_id,
                d.revision_id,
                d.original_filename,
                d.stored_file_path,
                d.content_hash,
                d.mime_type,
                d.file_size_bytes,
                d.page_count,
                COALESCE(source_event.status, 'AVAILABLE') AS source_status,
                source_event.reason_code AS source_reason_code,
                source_event.note AS source_status_note,
                source_event.created_at AS source_status_at,
                d.created_at
            FROM documents d
            LEFT JOIN document_source_events source_event
              ON source_event.id = (
                  SELECT candidate.id
                  FROM document_source_events candidate
                  WHERE candidate.document_id = d.id
                  ORDER BY candidate.sequence DESC
                  LIMIT 1
              )
            WHERE d.revision_id = ?
            ORDER BY d.created_at ASC, d.id ASC
            """,
            (revision_id,),
        ).fetchall()

    return [_row_to_dict(row) for row in rows]


def get_document(document_id: str, settings: Settings) -> dict[str, object]:
    with transaction(settings) as connection:
        document = connection.execute(
            """
            SELECT
                d.id,
                d.project_id,
                d.revision_id,
                d.original_filename,
                d.stored_file_path,
                d.content_hash,
                d.mime_type,
                d.file_size_bytes,
                d.page_count,
                COALESCE(source_event.status, 'AVAILABLE') AS source_status,
                source_event.reason_code AS source_reason_code,
                source_event.note AS source_status_note,
                source_event.created_at AS source_status_at,
                d.created_at
            FROM documents d
            LEFT JOIN document_source_events source_event
              ON source_event.id = (
                  SELECT candidate.id
                  FROM document_source_events candidate
                  WHERE candidate.document_id = d.id
                  ORDER BY candidate.sequence DESC
                  LIMIT 1
              )
            WHERE d.id = ?
            """,
            (document_id,),
        ).fetchone()

        if document is None:
            raise DocumentNotFoundError(document_id)

        sheets = connection.execute(
            """
            SELECT
                id,
                document_id,
                project_id,
                revision_id,
                page_index,
                sheet_number,
                width_pt,
                height_pt,
                rotation,
                label,
                render_path,
                thumbnail_path,
                created_at
            FROM sheets
            WHERE document_id = ?
            ORDER BY page_index ASC
            """,
            (document_id,),
        ).fetchall()

    result = _row_to_dict(document)
    result["sheets"] = [_row_to_dict(row) for row in sheets]
    return result


def get_document_by_revision_hash(
    revision_id: str,
    content_hash: str,
    settings: Settings,
) -> dict[str, object] | None:
    with transaction(settings) as connection:
        row = connection.execute(
            "SELECT id FROM documents WHERE revision_id = ? AND content_hash = ?",
            (revision_id, content_hash),
        ).fetchone()
    return get_document(str(row["id"]), settings) if row is not None else None


def get_sheet_render_context(sheet_id: str, settings: Settings) -> dict[str, object]:
    with transaction(settings) as connection:
        row = connection.execute(
            """
            SELECT
                s.id,
                s.document_id,
                s.project_id,
                s.revision_id,
                s.page_index,
                s.render_path,
                d.stored_file_path,
                d.content_hash,
                COALESCE(source_event.status, 'AVAILABLE') AS source_status
            FROM sheets s
            JOIN documents d ON d.id = s.document_id
            LEFT JOIN document_source_events source_event
              ON source_event.id = (
                  SELECT candidate.id
                  FROM document_source_events candidate
                  WHERE candidate.document_id = d.id
                  ORDER BY candidate.sequence DESC
                  LIMIT 1
              )
            WHERE s.id = ?
            """,
            (sheet_id,),
        ).fetchone()

    if row is None:
        raise SheetNotFoundError(sheet_id)

    return _row_to_dict(row)


def update_sheet_render_path(sheet_id: str, render_path: str, settings: Settings) -> None:
    with transaction(settings) as connection:
        connection.execute(
            "UPDATE sheets SET render_path = ? WHERE id = ?",
            (render_path, sheet_id),
        )


def list_text_blocks_for_sheet(sheet_id: str, settings: Settings) -> list[dict[str, object]]:
    with transaction(settings) as connection:
        sheet = connection.execute(
            "SELECT id FROM sheets WHERE id = ?",
            (sheet_id,),
        ).fetchone()

        if sheet is None:
            raise SheetNotFoundError(sheet_id)

        rows = connection.execute(
            """
            SELECT
                id,
                sheet_id,
                document_id,
                project_id,
                revision_id,
                block_index,
                text,
                x0,
                y0,
                x1,
                y1,
                created_at
            FROM text_blocks
            WHERE sheet_id = ?
            ORDER BY block_index ASC
            """,
            (sheet_id,),
        ).fetchall()

    return [_row_to_dict(row) for row in rows]
