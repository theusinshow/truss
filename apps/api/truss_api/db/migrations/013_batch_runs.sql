CREATE TABLE IF NOT EXISTS batch_runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('local_deterministic', 'with_visual')),
    status TEXT NOT NULL CHECK (
        status IN (
            'queued', 'running', 'completed', 'completed_with_errors',
            'cancel_requested', 'cancelled', 'interrupted'
        )
    ),
    phase TEXT NOT NULL CHECK (
        phase IN ('sheet_map', 'deterministic_audit', 'visual_audit', 'completed')
    ),
    config_json TEXT NOT NULL DEFAULT '{}',
    input_fingerprint TEXT NOT NULL,
    pipeline_version TEXT NOT NULL,
    cancel_requested_at TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE RESTRICT,
    FOREIGN KEY(revision_id) REFERENCES revisions(id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_batch_runs_active_revision_mode
ON batch_runs(revision_id, mode)
WHERE status IN ('queued', 'running', 'cancel_requested', 'interrupted');

CREATE INDEX IF NOT EXISTS idx_batch_runs_revision
ON batch_runs(revision_id, created_at DESC);

CREATE TABLE IF NOT EXISTS batch_items (
    id TEXT PRIMARY KEY,
    batch_run_id TEXT NOT NULL,
    sheet_id TEXT NOT NULL,
    phase TEXT NOT NULL CHECK (
        phase IN ('sheet_map', 'deterministic_audit', 'visual_audit')
    ),
    sequence INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'queued', 'running', 'completed', 'failed', 'skipped_dependency',
            'cancelled', 'manual_retry_required'
        )
    ),
    operation_id TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    run_token TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(batch_run_id) REFERENCES batch_runs(id) ON DELETE RESTRICT,
    FOREIGN KEY(sheet_id) REFERENCES sheets(id) ON DELETE RESTRICT,
    FOREIGN KEY(operation_id) REFERENCES processing_operations(id) ON DELETE RESTRICT,
    UNIQUE(batch_run_id, sheet_id, phase)
);

CREATE INDEX IF NOT EXISTS idx_batch_items_claim
ON batch_items(batch_run_id, phase, status, sequence);

CREATE INDEX IF NOT EXISTS idx_batch_items_sheet
ON batch_items(sheet_id, created_at DESC);

CREATE TABLE IF NOT EXISTS batch_run_events (
    id TEXT PRIMARY KEY,
    batch_run_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    event_kind TEXT NOT NULL CHECK (
        event_kind IN (
            'created', 'started', 'phase_changed', 'cancel_requested',
            'cancelled', 'interrupted', 'resumed', 'item_retry_scheduled', 'completed'
        )
    ),
    phase TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(batch_run_id) REFERENCES batch_runs(id) ON DELETE RESTRICT,
    UNIQUE(batch_run_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_batch_run_events_run
ON batch_run_events(batch_run_id, sequence);

CREATE TRIGGER IF NOT EXISTS batch_run_events_no_update
BEFORE UPDATE ON batch_run_events
BEGIN
    SELECT RAISE(ABORT, 'batch_run_events is append-only');
END;

CREATE TRIGGER IF NOT EXISTS batch_run_events_no_delete
BEFORE DELETE ON batch_run_events
BEGIN
    SELECT RAISE(ABORT, 'batch_run_events is append-only');
END;
