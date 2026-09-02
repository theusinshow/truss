CREATE TABLE IF NOT EXISTS learning_proposal_decisions (
    id TEXT PRIMARY KEY,
    stable_key TEXT NOT NULL,
    proposal_kind TEXT NOT NULL CHECK (
        proposal_kind IN ('suppress_rule', 'retain_rule', 'draft_rule')
    ),
    decision TEXT NOT NULL CHECK (decision IN ('approved', 'dismissed')),
    reason TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    preference_id TEXT,
    created_at TEXT NOT NULL,
    revoked_at TEXT,
    FOREIGN KEY (preference_id) REFERENCES rule_preferences(id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_learning_decisions_active_key
ON learning_proposal_decisions(stable_key)
WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_learning_decisions_history
ON learning_proposal_decisions(stable_key, created_at);

CREATE TABLE IF NOT EXISTS learning_proposal_evidence (
    decision_id TEXT NOT NULL,
    finding_id TEXT NOT NULL,
    signal_kind TEXT NOT NULL CHECK (
        signal_kind IN ('confirmed', 'rejected', 'manual')
    ),
    created_at TEXT NOT NULL,
    PRIMARY KEY (decision_id, finding_id),
    FOREIGN KEY (decision_id) REFERENCES learning_proposal_decisions(id) ON DELETE RESTRICT,
    FOREIGN KEY (finding_id) REFERENCES findings(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_learning_evidence_finding
ON learning_proposal_evidence(finding_id, created_at);
