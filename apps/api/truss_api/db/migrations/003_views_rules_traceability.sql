CREATE TABLE IF NOT EXISTS sheet_views (
    id TEXT PRIMARY KEY,
    sheet_map_id TEXT NOT NULL,
    parent_view_id TEXT,
    region_id TEXT,
    view_kind TEXT NOT NULL,
    view_role TEXT,
    identifier TEXT,
    title_raw TEXT,
    title TEXT,
    declared_scale_raw TEXT,
    declared_scale TEXT,
    level_raw TEXT,
    level TEXT,
    x0 REAL NOT NULL,
    y0 REAL NOT NULL,
    x1 REAL NOT NULL,
    y1 REAL NOT NULL,
    confidence REAL NOT NULL,
    provenance TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (sheet_map_id) REFERENCES sheet_maps(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_view_id) REFERENCES sheet_views(id) ON DELETE CASCADE,
    FOREIGN KEY (region_id) REFERENCES sheet_regions(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_sheet_views_map
ON sheet_views(sheet_map_id, view_kind);

CREATE INDEX IF NOT EXISTS idx_sheet_views_parent
ON sheet_views(parent_view_id);

CREATE TABLE IF NOT EXISTS rule_evaluations (
    id TEXT PRIMARY KEY,
    audit_run_id TEXT NOT NULL,
    sheet_map_id TEXT NOT NULL,
    sheet_id TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    rule_pack_id TEXT NOT NULL DEFAULT '',
    rule_pack_version TEXT NOT NULL,
    rule_scope TEXT NOT NULL DEFAULT 'general',
    target_kind TEXT NOT NULL,
    target_id TEXT,
    outcome TEXT NOT NULL,
    confidence REAL NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY (audit_run_id) REFERENCES audit_runs(id) ON DELETE RESTRICT,
    FOREIGN KEY (sheet_map_id) REFERENCES sheet_maps(id) ON DELETE RESTRICT,
    FOREIGN KEY (sheet_id) REFERENCES sheets(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_rule_evaluations_run
ON rule_evaluations(audit_run_id, outcome);

CREATE INDEX IF NOT EXISTS idx_rule_evaluations_rule
ON rule_evaluations(rule_id, rule_version);

ALTER TABLE findings ADD COLUMN rule_id TEXT;
ALTER TABLE findings ADD COLUMN rule_version TEXT;
ALTER TABLE findings ADD COLUMN rule_scope TEXT;
ALTER TABLE findings ADD COLUMN sheet_map_id TEXT;
ALTER TABLE findings ADD COLUMN view_id TEXT;
ALTER TABLE findings ADD COLUMN source_layer TEXT;
ALTER TABLE findings ADD COLUMN dedupe_key TEXT;

CREATE INDEX IF NOT EXISTS idx_findings_dedupe
ON findings(sheet_id, dedupe_key);

ALTER TABLE sheet_maps ADD COLUMN snapshot_hash TEXT;
ALTER TABLE sheet_maps ADD COLUMN extractor_version TEXT;
ALTER TABLE sheet_maps ADD COLUMN document_hash TEXT;

ALTER TABLE audit_runs ADD COLUMN sheet_map_id TEXT;
ALTER TABLE audit_runs ADD COLUMN rule_pack_version TEXT;
ALTER TABLE audit_runs ADD COLUMN coverage_json TEXT NOT NULL DEFAULT '{}';

-- Findings anteriores a F2 nao tem rastreabilidade e nao podem ser confundidos com
-- findings de regra. O feedback humano neles e preservado integralmente: status e
-- rejection_reason nao sao tocados.
UPDATE findings SET source_layer = 'legacy' WHERE source_layer IS NULL;
