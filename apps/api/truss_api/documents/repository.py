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
                    str(uuid4()),
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
            FROM documents
            WHERE revision_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (revision_id,),
        ).fetchall()

    return [_row_to_dict(row) for row in rows]


def get_document(document_id: str, settings: Settings) -> dict[str, object]:
    with transaction(settings) as connection:
        document = connection.execute(
            """
            SELECT
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
            FROM documents
            WHERE id = ?
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
                d.content_hash
            FROM sheets s
            JOIN documents d ON d.id = s.document_id
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
