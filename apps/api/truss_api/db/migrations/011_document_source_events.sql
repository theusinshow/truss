CREATE TABLE IF NOT EXISTS document_source_events (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('SOURCE_UNAVAILABLE', 'SOURCE_RESTORED')),
    reason_code TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_document_source_events_document
ON document_source_events(document_id, created_at, id);

CREATE TRIGGER IF NOT EXISTS document_source_events_no_update
BEFORE UPDATE ON document_source_events
BEGIN
    SELECT RAISE(ABORT, 'document_source_events is append-only');
END;

CREATE TRIGGER IF NOT EXISTS document_source_events_no_delete
BEFORE DELETE ON document_source_events
BEGIN
    SELECT RAISE(ABORT, 'document_source_events is append-only');
END;
