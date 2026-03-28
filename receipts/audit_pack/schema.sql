CREATE TABLE sources (
    source_id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    domain TEXT,
    tier INTEGER DEFAULT 2,
    retrieved_at TEXT,
    artifact_path TEXT DEFAULT NULL,
    artifact_hash TEXT DEFAULT NULL,
    notes TEXT DEFAULT NULL
);
CREATE TABLE claims (
    claim_id TEXT PRIMARY KEY,
    claim_text TEXT NOT NULL,
    topic TEXT NOT NULL,
    status TEXT DEFAULT 'PARTIAL',
    required_tier INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    notes TEXT DEFAULT NULL
);
CREATE TABLE claim_sources (
    claim_id TEXT REFERENCES claims(claim_id),
    source_id TEXT REFERENCES sources(source_id),
    PRIMARY KEY (claim_id, source_id)
);
CREATE TABLE nodes (
    node_id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL,
    name TEXT NOT NULL,
    aliases TEXT,
    description TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL,
    sha256 TEXT NOT NULL
);
CREATE TABLE edges (
    edge_id TEXT PRIMARY KEY,
    edge_type TEXT NOT NULL,
    from_node_id TEXT NOT NULL,
    to_node_id TEXT NOT NULL,
    claim_id TEXT REFERENCES claims(claim_id),
    assertion_level TEXT DEFAULT 'FACT',  -- FACT | INFERENCE | HYPOTHESIS
    -- Legacy fields (kept for migration compatibility)
    source TEXT,
    source_url TEXT,
    source_type TEXT,
    date_documented TEXT,
    date_occurred TEXT,
    date_ended TEXT,
    confidence REAL DEFAULT 1.0,
    notes TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    FOREIGN KEY (from_node_id) REFERENCES nodes(node_id),
    FOREIGN KEY (to_node_id) REFERENCES nodes(node_id)
);
CREATE INDEX idx_nodes_type ON nodes(node_type);
CREATE INDEX idx_nodes_name ON nodes(name);
CREATE INDEX idx_edges_type ON edges(edge_type);
CREATE INDEX idx_edges_from ON edges(from_node_id);
CREATE INDEX idx_edges_to ON edges(to_node_id);
CREATE INDEX idx_edges_claim ON edges(claim_id);
CREATE INDEX idx_sources_tier ON sources(tier);
CREATE INDEX idx_sources_domain ON sources(domain);
CREATE INDEX idx_claims_status ON claims(status);
CREATE INDEX idx_claims_topic ON claims(topic);
CREATE TABLE receipts (
    receipt_id TEXT PRIMARY KEY,
    operation TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    output_hash TEXT NOT NULL,
    success INTEGER NOT NULL,
    details TEXT
);
CREATE TABLE claim_counter (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    next_claim_num INTEGER DEFAULT 1
);
CREATE TABLE proposed_claims (
    proposal_id TEXT PRIMARY KEY,
    claim_text TEXT NOT NULL,
    topic TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    source_url TEXT,
    artifact_path TEXT,
    artifact_hash TEXT,
    reasoning TEXT,
    promotion_requirement TEXT,  -- "What Tier 0/1 doc would upgrade this"
    status TEXT DEFAULT 'PENDING',  -- PENDING, APPROVED, REJECTED
    resolved_claim_id TEXT,
    reviewer_notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    resolved_at TEXT
);
CREATE TABLE proposed_edges (
    proposal_id TEXT PRIMARY KEY,
    from_node TEXT NOT NULL,
    to_node TEXT NOT NULL,
    relationship TEXT NOT NULL,
    detail TEXT,
    proposed_claim_id TEXT,  -- Links to proposed_claims
    agent_name TEXT NOT NULL,
    confidence REAL DEFAULT 0.5,
    reasoning TEXT,
    promotion_requirement TEXT,
    status TEXT DEFAULT 'PENDING',
    resolved_edge_id INTEGER,
    reviewer_notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    resolved_at TEXT
);
CREATE TABLE correlation_metrics (
    metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id TEXT,
    metric_type TEXT NOT NULL,  -- 'source_overlap', 'temporal_proximity', 'path_distance', 'convergence'
    metric_value REAL,
    details TEXT,  -- JSON with computation details
    computed_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE sqlite_sequence(name,seq);
CREATE TABLE review_audit (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_type TEXT NOT NULL,  -- 'claim' or 'edge'
    proposal_id TEXT NOT NULL,
    decision TEXT NOT NULL,  -- APPROVED, REJECTED
    reviewer TEXT,
    notes TEXT,
    timestamp TEXT DEFAULT (datetime('now'))
);
CREATE TABLE proposal_counter (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    next_proposal_num INTEGER DEFAULT 1
);
CREATE INDEX idx_proposed_claims_status ON proposed_claims(status);
CREATE INDEX idx_proposed_edges_status ON proposed_edges(status);
CREATE INDEX idx_proposed_claims_agent ON proposed_claims(agent_name);
CREATE INDEX idx_proposed_edges_agent ON proposed_edges(agent_name);
CREATE INDEX idx_correlation_metrics_proposal ON correlation_metrics(proposal_id);
CREATE VIRTUAL TABLE nodes_fts USING fts5(
    node_id,
    name,
    description,
    content='nodes',
    content_rowid='rowid'
)
/* nodes_fts(node_id,name,description) */;
CREATE TABLE IF NOT EXISTS 'nodes_fts_data'(id INTEGER PRIMARY KEY, block BLOB);
CREATE TABLE IF NOT EXISTS 'nodes_fts_idx'(segid, term, pgno, PRIMARY KEY(segid, term)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS 'nodes_fts_docsize'(id INTEGER PRIMARY KEY, sz BLOB);
CREATE TABLE IF NOT EXISTS 'nodes_fts_config'(k PRIMARY KEY, v) WITHOUT ROWID;
CREATE VIRTUAL TABLE edges_fts USING fts5(
    edge_id,
    notes,
    source,
    content='edges',
    content_rowid='rowid'
)
/* edges_fts(edge_id,notes,source) */;
CREATE TABLE IF NOT EXISTS 'edges_fts_data'(id INTEGER PRIMARY KEY, block BLOB);
CREATE TABLE IF NOT EXISTS 'edges_fts_idx'(segid, term, pgno, PRIMARY KEY(segid, term)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS 'edges_fts_docsize'(id INTEGER PRIMARY KEY, sz BLOB);
CREATE TABLE IF NOT EXISTS 'edges_fts_config'(k PRIMARY KEY, v) WITHOUT ROWID;
CREATE VIRTUAL TABLE claims_fts USING fts5(
    claim_id,
    claim_text,
    topic,
    content='claims',
    content_rowid='rowid'
)
/* claims_fts(claim_id,claim_text,topic) */;
CREATE TABLE IF NOT EXISTS 'claims_fts_data'(id INTEGER PRIMARY KEY, block BLOB);
CREATE TABLE IF NOT EXISTS 'claims_fts_idx'(segid, term, pgno, PRIMARY KEY(segid, term)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS 'claims_fts_docsize'(id INTEGER PRIMARY KEY, sz BLOB);
CREATE TABLE IF NOT EXISTS 'claims_fts_config'(k PRIMARY KEY, v) WITHOUT ROWID;
CREATE TRIGGER nodes_ai AFTER INSERT ON nodes BEGIN
    INSERT INTO nodes_fts(rowid, node_id, name, description)
    VALUES (NEW.rowid, NEW.node_id, NEW.name, NEW.description);
END;
CREATE TRIGGER nodes_ad AFTER DELETE ON nodes BEGIN
    INSERT INTO nodes_fts(nodes_fts, rowid, node_id, name, description)
    VALUES('delete', OLD.rowid, OLD.node_id, OLD.name, OLD.description);
END;
CREATE TRIGGER nodes_au AFTER UPDATE ON nodes BEGIN
    INSERT INTO nodes_fts(nodes_fts, rowid, node_id, name, description)
    VALUES('delete', OLD.rowid, OLD.node_id, OLD.name, OLD.description);
    INSERT INTO nodes_fts(rowid, node_id, name, description)
    VALUES (NEW.rowid, NEW.node_id, NEW.name, NEW.description);
END;
CREATE TRIGGER edges_ai AFTER INSERT ON edges BEGIN
    INSERT INTO edges_fts(rowid, edge_id, notes, source)
    VALUES (NEW.rowid, NEW.edge_id, NEW.notes, NEW.source);
END;
CREATE TRIGGER edges_ad AFTER DELETE ON edges BEGIN
    INSERT INTO edges_fts(edges_fts, rowid, edge_id, notes, source)
    VALUES('delete', OLD.rowid, OLD.edge_id, OLD.notes, OLD.source);
END;
CREATE TRIGGER edges_au AFTER UPDATE ON edges BEGIN
    INSERT INTO edges_fts(edges_fts, rowid, edge_id, notes, source)
    VALUES('delete', OLD.rowid, OLD.edge_id, OLD.notes, OLD.source);
    INSERT INTO edges_fts(rowid, edge_id, notes, source)
    VALUES (NEW.rowid, NEW.edge_id, NEW.notes, NEW.source);
END;
CREATE TRIGGER claims_ai AFTER INSERT ON claims BEGIN
    INSERT INTO claims_fts(rowid, claim_id, claim_text, topic)
    VALUES (NEW.rowid, NEW.claim_id, NEW.claim_text, NEW.topic);
END;
CREATE TRIGGER claims_ad AFTER DELETE ON claims BEGIN
    INSERT INTO claims_fts(claims_fts, rowid, claim_id, claim_text, topic)
    VALUES('delete', OLD.rowid, OLD.claim_id, OLD.claim_text, OLD.topic);
END;
CREATE TRIGGER claims_au AFTER UPDATE ON claims BEGIN
    INSERT INTO claims_fts(claims_fts, rowid, claim_id, claim_text, topic)
    VALUES('delete', OLD.rowid, OLD.claim_id, OLD.claim_text, OLD.topic);
    INSERT INTO claims_fts(rowid, claim_id, claim_text, topic)
    VALUES (NEW.rowid, NEW.claim_id, NEW.claim_text, NEW.topic);
END;
CREATE TABLE proposed_nodes (
    proposal_id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    node_type TEXT NOT NULL,
    name TEXT NOT NULL,
    aliases TEXT,
    description TEXT,
    agent_name TEXT NOT NULL,
    source_url TEXT,
    reasoning TEXT,
    status TEXT DEFAULT 'PENDING',
    resolved_node_id TEXT,
    reviewer_notes TEXT,
    created_at TEXT,
    resolved_at TEXT
);
CREATE INDEX idx_proposed_nodes_status ON proposed_nodes(status);
CREATE INDEX idx_proposed_nodes_agent ON proposed_nodes(agent_name);
