from truss_api.core.settings import Settings, get_settings
from truss_api.db.connection import transaction


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS revisions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    revision_code TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT 'manual',
    original_filename TEXT,
    original_file_path TEXT,
    content_hash TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE RESTRICT,
    UNIQUE (project_id, revision_code)
);

CREATE INDEX IF NOT EXISTS idx_revisions_project_created
ON revisions(project_id, created_at);
"""


def initialize_database(settings: Settings | None = None) -> None:
    resolved = settings or get_settings()

    with transaction(resolved) as connection:
        connection.executescript(SCHEMA_SQL)
