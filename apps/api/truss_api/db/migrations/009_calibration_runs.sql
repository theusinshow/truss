CREATE TABLE IF NOT EXISTS calibration_runs (
    id TEXT PRIMARY KEY,
    analysis_key TEXT NOT NULL,
    run_key TEXT NOT NULL UNIQUE,
    corpus_manifest_hash TEXT NOT NULL,
    sheetmap_pipeline_version TEXT NOT NULL,
    audit_pipeline_version TEXT NOT NULL,
    rule_pack_digest TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    preference_digest TEXT NOT NULL,
    document_count INTEGER NOT NULL,
    page_count INTEGER NOT NULL,
    sheet_map_count INTEGER NOT NULL,
    evaluation_count INTEGER NOT NULL,
    raw_finding_count INTEGER NOT NULL,
    suppressed_finding_count INTEGER NOT NULL,
    effective_finding_count INTEGER NOT NULL,
    artifact_path TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_calibration_runs_created
ON calibration_runs(created_at DESC);

CREATE TABLE IF NOT EXISTS calibration_proposals (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    stable_key TEXT NOT NULL,
    proposal_kind TEXT NOT NULL CHECK (
        proposal_kind IN ('rule_noise', 'checklist_candidate', 'rule_retention')
    ),
    sheet_type TEXT,
    technical_scope TEXT,
    rule_id TEXT,
    title TEXT NOT NULL,
    rationale TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES calibration_runs(id) ON DELETE RESTRICT,
    UNIQUE (run_id, stable_key)
);

CREATE INDEX IF NOT EXISTS idx_calibration_proposals_run
ON calibration_proposals(run_id, proposal_kind, stable_key);

CREATE TABLE IF NOT EXISTS calibration_proposal_evidence (
    id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL,
    evidence_key TEXT NOT NULL,
    evidence_kind TEXT NOT NULL CHECK (
        evidence_kind IN ('sample', 'counterexample', 'feedback')
    ),
    document_sha256 TEXT,
    page_index INTEGER,
    sheet_code TEXT,
    x0 REAL,
    y0 REAL,
    x1 REAL,
    y1 REAL,
    source_finding_id TEXT,
    description TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (proposal_id) REFERENCES calibration_proposals(id) ON DELETE RESTRICT,
    FOREIGN KEY (source_finding_id) REFERENCES findings(id) ON DELETE RESTRICT,
    UNIQUE (proposal_id, evidence_key)
);

CREATE INDEX IF NOT EXISTS idx_calibration_evidence_proposal
ON calibration_proposal_evidence(proposal_id, evidence_kind);

CREATE TABLE IF NOT EXISTS calibration_proposal_decisions (
    id TEXT PRIMARY KEY,
    stable_key TEXT NOT NULL,
    proposal_id TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('approved', 'dismissed')),
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    revoked_at TEXT,
    FOREIGN KEY (proposal_id) REFERENCES calibration_proposals(id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_calibration_decisions_active_key
ON calibration_proposal_decisions(stable_key)
WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_calibration_decisions_history
ON calibration_proposal_decisions(stable_key, created_at DESC);
