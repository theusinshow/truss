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

CREATE TABLE IF NOT EXISTS text_blocks (
    id TEXT PRIMARY KEY,
    sheet_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    block_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    x0 REAL NOT NULL,
    y0 REAL NOT NULL,
    x1 REAL NOT NULL,
    y1 REAL NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (sheet_id) REFERENCES sheets(id) ON DELETE RESTRICT,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE RESTRICT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE RESTRICT,
    FOREIGN KEY (revision_id) REFERENCES revisions(id) ON DELETE RESTRICT,
    UNIQUE (sheet_id, block_index)
);

CREATE INDEX IF NOT EXISTS idx_text_blocks_sheet
ON text_blocks(sheet_id, block_index);

CREATE TABLE IF NOT EXISTS audit_runs (
    id TEXT PRIMARY KEY,
    sheet_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    pipeline_version TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    FOREIGN KEY (sheet_id) REFERENCES sheets(id) ON DELETE RESTRICT,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE RESTRICT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE RESTRICT,
    FOREIGN KEY (revision_id) REFERENCES revisions(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_audit_runs_sheet_completed
ON audit_runs(sheet_id, completed_at);

CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY,
    audit_run_id TEXT,
    sheet_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    category TEXT NOT NULL,
    type TEXT NOT NULL,
    description TEXT NOT NULL,
    severity TEXT NOT NULL,
    confidence REAL NOT NULL,
    x0 REAL NOT NULL,
    y0 REAL NOT NULL,
    x1 REAL NOT NULL,
    y1 REAL NOT NULL,
    evidence_json TEXT NOT NULL,
    origin TEXT NOT NULL,
    status TEXT NOT NULL,
    rejection_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (audit_run_id) REFERENCES audit_runs(id) ON DELETE RESTRICT,
    FOREIGN KEY (sheet_id) REFERENCES sheets(id) ON DELETE RESTRICT,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE RESTRICT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE RESTRICT,
    FOREIGN KEY (revision_id) REFERENCES revisions(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_findings_sheet_status
ON findings(sheet_id, status, severity);

CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    scope TEXT NOT NULL,
    key TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (scope, key)
);

CREATE INDEX IF NOT EXISTS idx_memories_scope
ON memories(scope, created_at);

CREATE TABLE IF NOT EXISTS chat_conversations (
    id TEXT PRIMARY KEY,
    sheet_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (sheet_id) REFERENCES sheets(id) ON DELETE RESTRICT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE RESTRICT,
    FOREIGN KEY (revision_id) REFERENCES revisions(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_chat_conversations_sheet_updated
ON chat_conversations(sheet_id, updated_at);

CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT,
    sheet_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'completed',
    provider TEXT,
    model TEXT,
    parent_message_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (conversation_id) REFERENCES chat_conversations(id) ON DELETE RESTRICT,
    FOREIGN KEY (parent_message_id) REFERENCES chat_messages(id) ON DELETE RESTRICT,
    FOREIGN KEY (sheet_id) REFERENCES sheets(id) ON DELETE RESTRICT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE RESTRICT,
    FOREIGN KEY (revision_id) REFERENCES revisions(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_sheet
ON chat_messages(sheet_id, created_at);

CREATE TABLE IF NOT EXISTS chat_message_context_items (
    id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL,
    item_order INTEGER NOT NULL,
    source_id TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL,
    label TEXT NOT NULL,
    value TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (message_id) REFERENCES chat_messages(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_chat_message_context_message
ON chat_message_context_items(message_id, item_order);

CREATE TABLE IF NOT EXISTS chat_message_feedback (
    id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL,
    feedback TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (message_id) REFERENCES chat_messages(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_chat_message_feedback_message
ON chat_message_feedback(message_id, created_at);

CREATE TABLE IF NOT EXISTS ai_usage_events (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    operation TEXT NOT NULL,
    project_id TEXT,
    revision_id TEXT,
    sheet_id TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    estimated_cost_usd REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ai_usage_project
ON ai_usage_events(project_id, created_at);

CREATE TABLE IF NOT EXISTS cache_entries (
    id TEXT PRIMARY KEY,
    cache_key TEXT NOT NULL UNIQUE,
    namespace TEXT NOT NULL,
    value TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cache_entries_namespace
ON cache_entries(namespace, created_at);
"""


CHAT_MESSAGE_COLUMNS = {
    "conversation_id": "TEXT",
    "status": "TEXT NOT NULL DEFAULT 'completed'",
    "provider": "TEXT",
    "model": "TEXT",
    "parent_message_id": "TEXT",
    "updated_at": "TEXT NOT NULL DEFAULT ''",
}

CHAT_MESSAGE_CONTEXT_COLUMNS = {
    "source_id": "TEXT NOT NULL DEFAULT ''",
}


def _ensure_column(connection: object, table: str, column: str, definition: str) -> None:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    columns = {str(row["name"]) for row in rows}

    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def initialize_database(settings: Settings | None = None) -> None:
    resolved = settings or get_settings()

    with transaction(resolved) as connection:
        connection.executescript(SCHEMA_SQL)
        for column, definition in CHAT_MESSAGE_COLUMNS.items():
            _ensure_column(connection, "chat_messages", column, definition)
        for column, definition in CHAT_MESSAGE_CONTEXT_COLUMNS.items():
            _ensure_column(connection, "chat_message_context_items", column, definition)
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation
            ON chat_messages(conversation_id, created_at)
            """
        )
        connection.execute(
            """
            UPDATE chat_messages
            SET updated_at = created_at
            WHERE updated_at = ''
            """
        )
