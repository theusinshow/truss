CREATE TABLE IF NOT EXISTS sheet_elements (
    id TEXT PRIMARY KEY,
    sheet_map_id TEXT NOT NULL,
    view_id TEXT,
    technical_scope TEXT,
    element_kind TEXT NOT NULL,
    code_raw TEXT NOT NULL,
    code TEXT NOT NULL,
    attributes_json TEXT NOT NULL DEFAULT '{}',
    x0 REAL NOT NULL,
    y0 REAL NOT NULL,
    x1 REAL NOT NULL,
    y1 REAL NOT NULL,
    confidence REAL NOT NULL,
    provenance TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (sheet_map_id) REFERENCES sheet_maps(id) ON DELETE CASCADE,
    FOREIGN KEY (view_id) REFERENCES sheet_views(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_sheet_elements_map
ON sheet_elements(sheet_map_id, element_kind, code);

CREATE INDEX IF NOT EXISTS idx_sheet_elements_view
ON sheet_elements(view_id, element_kind);

ALTER TABLE findings ADD COLUMN element_code TEXT;
ALTER TABLE findings ADD COLUMN registry_hash TEXT;
ALTER TABLE audit_runs ADD COLUMN registry_hash TEXT;

CREATE INDEX IF NOT EXISTS idx_findings_element_code
ON findings(revision_id, element_code);
