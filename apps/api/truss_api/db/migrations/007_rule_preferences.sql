CREATE TABLE IF NOT EXISTS rule_preferences (
    id TEXT PRIMARY KEY,
    scope TEXT NOT NULL CHECK (scope = 'sheet_type'),
    sheet_type TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action = 'suppress'),
    reason TEXT NOT NULL,
    source_finding_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    revoked_at TEXT,
    FOREIGN KEY (source_finding_id) REFERENCES findings(id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_rule_preferences_active
ON rule_preferences(sheet_type, rule_id, action)
WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_rule_preferences_source
ON rule_preferences(source_finding_id, created_at);
