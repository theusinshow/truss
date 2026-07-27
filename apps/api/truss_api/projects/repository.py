from datetime import UTC, datetime
from sqlite3 import IntegrityError, Row
from uuid import uuid4

from truss_api.core.settings import Settings
from truss_api.db.connection import transaction
from truss_api.projects.models import ProjectCreate, RevisionCreate


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_dict(row: Row) -> dict[str, object]:
    return dict(row)


def _next_revision_code(project_id: str, settings: Settings | None = None) -> str:
    with transaction(settings) as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS total FROM revisions WHERE project_id = ?",
            (project_id,),
        ).fetchone()

    total = int(row["total"]) if row else 0
    return f"REV-{total + 1:03d}"


class ProjectNotFoundError(Exception):
    pass


class DuplicateRevisionError(Exception):
    pass


def list_projects(settings: Settings | None = None) -> list[dict[str, object]]:
    with transaction(settings) as connection:
        rows = connection.execute(
            """
            SELECT
                p.id,
                p.name,
                p.description,
                p.created_at,
                p.updated_at,
                COUNT(r.id) AS revisions_count,
                (
                    SELECT r2.revision_code
                    FROM revisions r2
                    WHERE r2.project_id = p.id
                    ORDER BY r2.created_at DESC, r2.id DESC
                    LIMIT 1
                ) AS latest_revision_code
            FROM projects p
            LEFT JOIN revisions r ON r.project_id = p.id
            GROUP BY p.id
            ORDER BY p.updated_at DESC, p.name ASC
            """
        ).fetchall()

    return [_row_to_dict(row) for row in rows]


def create_project(payload: ProjectCreate, settings: Settings | None = None) -> dict[str, object]:
    project_id = str(uuid4())
    created_at = _now()

    with transaction(settings) as connection:
        connection.execute(
            """
            INSERT INTO projects (id, name, description, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                project_id,
                payload.name.strip(),
                payload.description.strip(),
                created_at,
                created_at,
            ),
        )

    return get_project(project_id, settings)


def get_project(project_id: str, settings: Settings | None = None) -> dict[str, object]:
    with transaction(settings) as connection:
        project = connection.execute(
            """
            SELECT id, name, description, created_at, updated_at
            FROM projects
            WHERE id = ?
            """,
            (project_id,),
        ).fetchone()

        if project is None:
            raise ProjectNotFoundError(project_id)

        revisions = connection.execute(
            """
            SELECT
                id,
                project_id,
                revision_code,
                notes,
                source_type,
                original_filename,
                original_file_path,
                content_hash,
                created_at
            FROM revisions
            WHERE project_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (project_id,),
        ).fetchall()

    project_data = _row_to_dict(project)
    project_data["revisions"] = [_row_to_dict(row) for row in revisions]
    return project_data


def create_revision(
    project_id: str,
    payload: RevisionCreate,
    settings: Settings | None = None,
) -> dict[str, object]:
    revision_code = (payload.revision_code or _next_revision_code(project_id, settings)).strip()
    revision_id = str(uuid4())
    created_at = _now()

    with transaction(settings) as connection:
        project = connection.execute(
            "SELECT id FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()

        if project is None:
            raise ProjectNotFoundError(project_id)

        try:
            connection.execute(
                """
                INSERT INTO revisions (
                    id,
                    project_id,
                    revision_code,
                    notes,
                    source_type,
                    original_filename,
                    original_file_path,
                    content_hash,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revision_id,
                    project_id,
                    revision_code,
                    payload.notes.strip(),
                    payload.source_type,
                    payload.original_filename,
                    payload.original_file_path,
                    payload.content_hash,
                    created_at,
                ),
            )
        except IntegrityError as error:
            if "UNIQUE" in str(error).upper():
                raise DuplicateRevisionError(revision_code) from error
            raise

        connection.execute(
            "UPDATE projects SET updated_at = ? WHERE id = ?",
            (created_at, project_id),
        )

        revision = connection.execute(
            """
            SELECT
                id,
                project_id,
                revision_code,
                notes,
                source_type,
                original_filename,
                original_file_path,
                content_hash,
                created_at
            FROM revisions
            WHERE id = ?
            """,
            (revision_id,),
        ).fetchone()

    return _row_to_dict(revision)
