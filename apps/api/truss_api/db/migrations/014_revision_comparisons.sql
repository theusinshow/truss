CREATE TABLE revision_comparisons (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    base_revision_id TEXT NOT NULL,
    target_revision_id TEXT NOT NULL,
    input_fingerprint TEXT NOT NULL UNIQUE,
    pipeline_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('completed', 'completed_with_limits')),
    counts_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE RESTRICT,
    FOREIGN KEY (base_revision_id) REFERENCES revisions(id) ON DELETE RESTRICT,
    FOREIGN KEY (target_revision_id) REFERENCES revisions(id) ON DELETE RESTRICT,
    CHECK (base_revision_id <> target_revision_id)
);

CREATE INDEX idx_revision_comparisons_project_created
ON revision_comparisons(project_id, created_at);

CREATE INDEX idx_revision_comparisons_revisions
ON revision_comparisons(base_revision_id, target_revision_id, created_at);

CREATE TABLE comparison_pair_overrides (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    base_revision_id TEXT NOT NULL,
    target_revision_id TEXT NOT NULL,
    base_sheet_id TEXT NOT NULL,
    target_sheet_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    revoked_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE RESTRICT,
    FOREIGN KEY (base_revision_id) REFERENCES revisions(id) ON DELETE RESTRICT,
    FOREIGN KEY (target_revision_id) REFERENCES revisions(id) ON DELETE RESTRICT,
    FOREIGN KEY (base_sheet_id) REFERENCES sheets(id) ON DELETE RESTRICT,
    FOREIGN KEY (target_sheet_id) REFERENCES sheets(id) ON DELETE RESTRICT,
    CHECK (base_revision_id <> target_revision_id),
    CHECK (base_sheet_id <> target_sheet_id)
);

CREATE INDEX idx_comparison_pair_overrides_active
ON comparison_pair_overrides(
    project_id, base_revision_id, target_revision_id, revoked_at, created_at
);

CREATE TABLE revision_comparison_pairs (
    id TEXT PRIMARY KEY,
    comparison_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    base_sheet_id TEXT,
    target_sheet_id TEXT,
    status TEXT NOT NULL CHECK (
        status IN ('identical', 'changed', 'added', 'removed', 'ambiguous', 'unavailable')
    ),
    match_method TEXT NOT NULL CHECK (
        match_method IN ('manual', 'sheet_code', 'exact_content', 'unmatched')
    ),
    match_confidence REAL NOT NULL CHECK (match_confidence >= 0 AND match_confidence <= 1),
    pairing_override_id TEXT,
    summary TEXT NOT NULL,
    changed_ratio REAL NOT NULL DEFAULT 0 CHECK (changed_ratio >= 0 AND changed_ratio <= 1),
    base_identity_json TEXT,
    target_identity_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (comparison_id) REFERENCES revision_comparisons(id) ON DELETE RESTRICT,
    FOREIGN KEY (base_sheet_id) REFERENCES sheets(id) ON DELETE RESTRICT,
    FOREIGN KEY (target_sheet_id) REFERENCES sheets(id) ON DELETE RESTRICT,
    FOREIGN KEY (pairing_override_id) REFERENCES comparison_pair_overrides(id) ON DELETE RESTRICT,
    UNIQUE (comparison_id, sequence)
);

CREATE INDEX idx_revision_comparison_pairs_comparison_status
ON revision_comparison_pairs(comparison_id, status, sequence);

CREATE TABLE revision_comparison_regions (
    id TEXT PRIMARY KEY,
    pair_id TEXT NOT NULL,
    region_index INTEGER NOT NULL,
    base_x0 REAL NOT NULL,
    base_y0 REAL NOT NULL,
    base_x1 REAL NOT NULL,
    base_y1 REAL NOT NULL,
    target_x0 REAL NOT NULL,
    target_y0 REAL NOT NULL,
    target_x1 REAL NOT NULL,
    target_y1 REAL NOT NULL,
    changed_pixel_count INTEGER NOT NULL CHECK (changed_pixel_count >= 0),
    changed_ratio REAL NOT NULL CHECK (changed_ratio >= 0 AND changed_ratio <= 1),
    created_at TEXT NOT NULL,
    FOREIGN KEY (pair_id) REFERENCES revision_comparison_pairs(id) ON DELETE RESTRICT,
    UNIQUE (pair_id, region_index),
    CHECK (base_x0 <= base_x1 AND base_y0 <= base_y1),
    CHECK (target_x0 <= target_x1 AND target_y0 <= target_y1)
);

CREATE INDEX idx_revision_comparison_regions_pair
ON revision_comparison_regions(pair_id, region_index);

CREATE TRIGGER revision_comparisons_no_update
BEFORE UPDATE ON revision_comparisons
BEGIN
    SELECT RAISE(ABORT, 'revision comparisons are immutable');
END;

CREATE TRIGGER revision_comparisons_no_delete
BEFORE DELETE ON revision_comparisons
BEGIN
    SELECT RAISE(ABORT, 'revision comparisons are immutable');
END;

CREATE TRIGGER revision_comparison_pairs_no_update
BEFORE UPDATE ON revision_comparison_pairs
BEGIN
    SELECT RAISE(ABORT, 'revision comparison pairs are immutable');
END;

CREATE TRIGGER revision_comparison_pairs_no_delete
BEFORE DELETE ON revision_comparison_pairs
BEGIN
    SELECT RAISE(ABORT, 'revision comparison pairs are immutable');
END;

CREATE TRIGGER revision_comparison_regions_no_update
BEFORE UPDATE ON revision_comparison_regions
BEGIN
    SELECT RAISE(ABORT, 'revision comparison regions are immutable');
END;

CREATE TRIGGER revision_comparison_regions_no_delete
BEFORE DELETE ON revision_comparison_regions
BEGIN
    SELECT RAISE(ABORT, 'revision comparison regions are immutable');
END;

CREATE TRIGGER comparison_pair_overrides_no_delete
BEFORE DELETE ON comparison_pair_overrides
BEGIN
    SELECT RAISE(ABORT, 'comparison pairing history cannot be deleted');
END;
