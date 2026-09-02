ALTER TABLE document_source_events
ADD COLUMN sequence INTEGER NOT NULL DEFAULT 1;

CREATE UNIQUE INDEX IF NOT EXISTS idx_document_source_events_sequence
ON document_source_events(document_id, sequence);
