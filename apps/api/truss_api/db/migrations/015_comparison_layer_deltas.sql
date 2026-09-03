ALTER TABLE revision_comparison_pairs
ADD COLUMN delta_status TEXT NOT NULL DEFAULT 'not_run'
CHECK (delta_status IN (
    'not_run', 'completed', 'completed_with_limits',
    'not_comparable', 'unavailable', 'not_applicable'
));

ALTER TABLE revision_comparison_pairs
ADD COLUMN delta_counts_json TEXT NOT NULL DEFAULT '{}';

ALTER TABLE revision_comparison_pairs
ADD COLUMN delta_truncated INTEGER NOT NULL DEFAULT 0
CHECK (delta_truncated IN (0, 1));

ALTER TABLE revision_comparison_pairs
ADD COLUMN delta_summary TEXT NOT NULL DEFAULT 'Camadas textuais e vetoriais nao executadas neste run.';

CREATE TABLE revision_comparison_deltas (
    id TEXT PRIMARY KEY,
    pair_id TEXT NOT NULL,
    delta_index INTEGER NOT NULL,
    layer TEXT NOT NULL CHECK (layer IN ('text', 'vector')),
    change_type TEXT NOT NULL CHECK (
        change_type IN ('added', 'removed', 'modified', 'moved')
    ),
    match_evidence TEXT NOT NULL,
    similarity REAL NOT NULL CHECK (similarity >= 0 AND similarity <= 1),
    before_value TEXT,
    after_value TEXT,
    base_x0 REAL,
    base_y0 REAL,
    base_x1 REAL,
    base_y1 REAL,
    target_x0 REAL,
    target_y0 REAL,
    target_x1 REAL,
    target_y1 REAL,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (pair_id) REFERENCES revision_comparison_pairs(id) ON DELETE RESTRICT,
    UNIQUE (pair_id, delta_index),
    CHECK (
        (base_x0 IS NULL AND base_y0 IS NULL AND base_x1 IS NULL AND base_y1 IS NULL)
        OR
        (base_x0 IS NOT NULL AND base_y0 IS NOT NULL AND base_x1 IS NOT NULL
         AND base_y1 IS NOT NULL AND base_x0 <= base_x1 AND base_y0 <= base_y1)
    ),
    CHECK (
        (target_x0 IS NULL AND target_y0 IS NULL AND target_x1 IS NULL AND target_y1 IS NULL)
        OR
        (target_x0 IS NOT NULL AND target_y0 IS NOT NULL AND target_x1 IS NOT NULL
         AND target_y1 IS NOT NULL AND target_x0 <= target_x1 AND target_y0 <= target_y1)
    )
);

CREATE INDEX idx_revision_comparison_deltas_pair_layer
ON revision_comparison_deltas(pair_id, layer, change_type, delta_index);

CREATE TRIGGER revision_comparison_deltas_no_update
BEFORE UPDATE ON revision_comparison_deltas
BEGIN
    SELECT RAISE(ABORT, 'revision comparison deltas are immutable');
END;

CREATE TRIGGER revision_comparison_deltas_no_delete
BEFORE DELETE ON revision_comparison_deltas
BEGIN
    SELECT RAISE(ABORT, 'revision comparison deltas are immutable');
END;
