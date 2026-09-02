ALTER TABLE schema_migrations ADD COLUMN sql_sha256 TEXT;

CREATE TABLE IF NOT EXISTS processing_operations (
    id TEXT PRIMARY KEY,
    identity_key TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK (
        kind IN ('document_import', 'sheet_map_build', 'deterministic_audit', 'vision_audit')
    ),
    project_id TEXT,
    revision_id TEXT,
    document_id TEXT,
    sheet_id TEXT,
    input_hash TEXT NOT NULL,
    pipeline_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'pending', 'running', 'completed', 'failed', 'interrupted',
            'manual_retry_required'
        )
    ),
    checkpoint TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL DEFAULT '{}',
    error_code TEXT,
    error_message TEXT,
    error_context_json TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    heartbeat_at TEXT,
    completed_at TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id),
    FOREIGN KEY(revision_id) REFERENCES revisions(id),
    FOREIGN KEY(document_id) REFERENCES documents(id),
    FOREIGN KEY(sheet_id) REFERENCES sheets(id)
);

CREATE INDEX IF NOT EXISTS idx_processing_operations_status
ON processing_operations(status, updated_at);

CREATE INDEX IF NOT EXISTS idx_processing_operations_revision
ON processing_operations(revision_id, created_at);

CREATE INDEX IF NOT EXISTS idx_processing_operations_sheet
ON processing_operations(sheet_id, created_at);

CREATE TABLE IF NOT EXISTS processing_operation_events (
    id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    event_kind TEXT NOT NULL CHECK (
        event_kind IN ('created', 'started', 'checkpoint', 'completed', 'failed', 'interrupted', 'resumed')
    ),
    checkpoint TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(operation_id) REFERENCES processing_operations(id),
    UNIQUE(operation_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_processing_operation_events_operation
ON processing_operation_events(operation_id, sequence);

