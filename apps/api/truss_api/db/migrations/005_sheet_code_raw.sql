ALTER TABLE sheet_maps ADD COLUMN sheet_code_raw TEXT;

CREATE INDEX IF NOT EXISTS idx_sheet_maps_sheet_code_raw
ON sheet_maps(sheet_code_raw);
