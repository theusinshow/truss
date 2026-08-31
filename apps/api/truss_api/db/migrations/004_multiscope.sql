CREATE TABLE IF NOT EXISTS sheet_map_scopes (
    id TEXT PRIMARY KEY,
    sheet_map_id TEXT NOT NULL,
    technical_scope TEXT NOT NULL,
    confidence REAL NOT NULL,
    provenance TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (sheet_map_id) REFERENCES sheet_maps(id) ON DELETE CASCADE,
    UNIQUE (sheet_map_id, technical_scope)
);

CREATE INDEX IF NOT EXISTS idx_sheet_map_scopes_scope
ON sheet_map_scopes(technical_scope, sheet_map_id);

ALTER TABLE sheet_views ADD COLUMN technical_scope TEXT;
ALTER TABLE rule_evaluations ADD COLUMN technical_scope TEXT;
ALTER TABLE findings ADD COLUMN technical_scope TEXT;

CREATE INDEX IF NOT EXISTS idx_rule_evaluations_technical_scope
ON rule_evaluations(technical_scope, rule_id);

CREATE INDEX IF NOT EXISTS idx_findings_technical_scope
ON findings(technical_scope, sheet_id);
