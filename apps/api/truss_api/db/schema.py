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

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    stored_file_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    page_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE RESTRICT,
    FOREIGN KEY (revision_id) REFERENCES revisions(id) ON DELETE RESTRICT,
    UNIQUE (revision_id, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_documents_revision_created
ON documents(revision_id, created_at);

CREATE TABLE IF NOT EXISTS sheets (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    page_index INTEGER NOT NULL,
    sheet_number INTEGER NOT NULL,
    width_pt REAL NOT NULL,
    height_pt REAL NOT NULL,
    rotation INTEGER NOT NULL,
    label TEXT NOT NULL,
    render_path TEXT,
    thumbnail_path TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE RESTRICT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE RESTRICT,
    FOREIGN KEY (revision_id) REFERENCES revisions(id) ON DELETE RESTRICT,
    UNIQUE (document_id, page_index)
);

CREATE INDEX IF NOT EXISTS idx_sheets_revision_page
ON sheets(revision_id, sheet_number);
"""


def initialize_database(settings: Settings | None = None) -> None:
    resolved = settings or get_settings()

    with transaction(resolved) as connection:
        connection.executescript(SCHEMA_SQL)
