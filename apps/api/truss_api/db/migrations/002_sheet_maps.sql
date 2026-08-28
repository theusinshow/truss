CREATE TABLE IF NOT EXISTS sheet_maps (
    id TEXT PRIMARY KEY,
    sheet_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    pipeline_version TEXT NOT NULL,
    status TEXT NOT NULL,
    geometry_path TEXT NOT NULL,
    sheet_code TEXT,
    sheet_type TEXT NOT NULL,
    paper_format TEXT NOT NULL,
    orientation TEXT NOT NULL,
    title_block_json TEXT NOT NULL,
    built_at TEXT NOT NULL,
    FOREIGN KEY (sheet_id) REFERENCES sheets(id) ON DELETE RESTRICT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE RESTRICT,
    FOREIGN KEY (revision_id) REFERENCES revisions(id) ON DELETE RESTRICT,
    UNIQUE (sheet_id, pipeline_version)
);

CREATE INDEX IF NOT EXISTS idx_sheet_maps_revision_type
ON sheet_maps(revision_id, sheet_type);

CREATE TABLE IF NOT EXISTS sheet_regions (
    id TEXT PRIMARY KEY,
    sheet_map_id TEXT NOT NULL,
    region_kind TEXT NOT NULL,
    x0 REAL NOT NULL,
    y0 REAL NOT NULL,
    x1 REAL NOT NULL,
    y1 REAL NOT NULL,
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (sheet_map_id) REFERENCES sheet_maps(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sheet_regions_map
ON sheet_regions(sheet_map_id, region_kind);
