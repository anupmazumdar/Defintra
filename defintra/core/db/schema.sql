-- Defintra Core SQLite Schema
-- Layered Relational + Graph Storage (§45)

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    objective TEXT NOT NULL,
    domain TEXT DEFAULT 'GENERAL',
    source_type TEXT DEFAULT 'idea', -- 'idea' or 'repo' (brownfield ready)
    spec_entropy REAL DEFAULT 1.0,
    spec_health_score REAL DEFAULT 0.0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS requirements (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    ears_pattern TEXT NOT NULL,
    priority TEXT DEFAULT 'MEDIUM',
    status TEXT DEFAULT 'PROPOSED',
    category TEXT DEFAULT 'FUNCTIONAL',
    affected_components_json TEXT DEFAULT '[]',
    constraints_json TEXT DEFAULT '[]',
    acceptance_criteria_json TEXT DEFAULT '[]',
    provenance_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT NOT NULL,
    rejected_alternatives_json TEXT DEFAULT '[]',
    status TEXT DEFAULT 'PROPOSED',
    approval_level TEXT DEFAULT 'USER',
    change_risk TEXT DEFAULT 'MEDIUM',
    superseded_by TEXT,
    affected_components_json TEXT DEFAULT '[]',
    provenance_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assumptions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    statement TEXT NOT NULL,
    category TEXT DEFAULT 'GENERAL',
    confidence REAL DEFAULT 0.6,
    status TEXT DEFAULT 'ACTIVE',
    provenance_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS unknowns (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    impact TEXT DEFAULT 'HIGH',
    category TEXT DEFAULT 'ARCHITECTURE',
    status TEXT DEFAULT 'OPEN',
    resolution TEXT,
    priority_order INTEGER DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    target_entity_type TEXT NOT NULL,
    target_entity_id TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    description TEXT NOT NULL,
    confidence REAL DEFAULT 0.8,
    source TEXT NOT NULL,
    approved_by TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS components (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    component_type TEXT NOT NULL,
    description TEXT DEFAULT '',
    stability_state TEXT DEFAULT 'PROPOSED',
    blast_radius_json TEXT DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contracts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    contract_type TEXT NOT NULL,
    version TEXT DEFAULT '1.0.0',
    specification_json TEXT DEFAULT '{}',
    status TEXT DEFAULT 'PROPOSED',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conflicts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    entity_a_ref TEXT NOT NULL,
    entity_b_ref TEXT NOT NULL,
    severity TEXT DEFAULT 'HIGH',
    status TEXT DEFAULT 'OPEN',
    resolution TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS discovery_audit_log (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    silent_assumption TEXT NOT NULL,
    reason_skipped TEXT NOT NULL,
    risk_level TEXT DEFAULT 'LOW',
    category TEXT DEFAULT 'GENERAL',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dependencies (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    dependency_kind TEXT DEFAULT 'REQUIRES',
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- Indexes for efficient graph and entity lookups
CREATE INDEX IF NOT EXISTS idx_req_project ON requirements(project_id);
CREATE INDEX IF NOT EXISTS idx_dec_project ON decisions(project_id);
CREATE INDEX IF NOT EXISTS idx_asm_project ON assumptions(project_id);
CREATE INDEX IF NOT EXISTS idx_unk_project ON unknowns(project_id);
CREATE INDEX IF NOT EXISTS idx_evi_target ON evidence(target_entity_type, target_entity_id);
CREATE INDEX IF NOT EXISTS idx_dep_src ON dependencies(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_dep_tgt ON dependencies(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_dep_proj ON dependencies(project_id);
