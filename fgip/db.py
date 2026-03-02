"""FGIP Database - SQLite connection, schema creation, FTS5, Square-One compliance."""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
import uuid

from .schema import (
    Node, Edge, Receipt, Source, Claim, ClaimStatus,
    compute_sha256, extract_domain, auto_tier_domain
)


# Base schema (nodes, edges, receipts)
SCHEMA_SQL = """
-- Sources table (Square-One)
CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    domain TEXT,
    tier INTEGER DEFAULT 2,
    retrieved_at TEXT,
    artifact_path TEXT DEFAULT NULL,
    artifact_hash TEXT DEFAULT NULL,
    notes TEXT DEFAULT NULL
);

-- Claims table (Square-One)
CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY,
    claim_text TEXT NOT NULL,
    topic TEXT NOT NULL,
    status TEXT DEFAULT 'PARTIAL',
    required_tier INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    notes TEXT DEFAULT NULL
);

-- Many-to-many: claims to sources
CREATE TABLE IF NOT EXISTS claim_sources (
    claim_id TEXT REFERENCES claims(claim_id),
    source_id TEXT REFERENCES sources(source_id),
    PRIMARY KEY (claim_id, source_id)
);

-- Entities (organizations, persons, legislation, etc.)
CREATE TABLE IF NOT EXISTS nodes (
    node_id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL,
    name TEXT NOT NULL,
    aliases TEXT,
    description TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL,
    sha256 TEXT NOT NULL
);

-- Relationships with claim references (Square-One compliant)
CREATE TABLE IF NOT EXISTS edges (
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

-- Indexes
CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(edge_type);
CREATE INDEX IF NOT EXISTS idx_edges_from ON edges(from_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_claim ON edges(claim_id);
CREATE INDEX IF NOT EXISTS idx_sources_tier ON sources(tier);
CREATE INDEX IF NOT EXISTS idx_sources_domain ON sources(domain);
CREATE INDEX IF NOT EXISTS idx_claims_status ON claims(status);
CREATE INDEX IF NOT EXISTS idx_claims_topic ON claims(topic);

-- Receipts table for verification per CLAUDE.md
CREATE TABLE IF NOT EXISTS receipts (
    receipt_id TEXT PRIMARY KEY,
    operation TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    output_hash TEXT NOT NULL,
    success INTEGER NOT NULL,
    details TEXT
);

-- Claim counter for sequential IDs
CREATE TABLE IF NOT EXISTS claim_counter (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    next_claim_num INTEGER DEFAULT 1
);
INSERT OR IGNORE INTO claim_counter (id, next_claim_num) VALUES (1, 1);

-- Proposed claims awaiting human review (agent staging)
CREATE TABLE IF NOT EXISTS proposed_claims (
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

-- Proposed edges awaiting human review (agent staging)
CREATE TABLE IF NOT EXISTS proposed_edges (
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

-- Correlation metrics computed by agents
CREATE TABLE IF NOT EXISTS correlation_metrics (
    metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id TEXT,
    metric_type TEXT NOT NULL,  -- 'source_overlap', 'temporal_proximity', 'path_distance', 'convergence'
    metric_value REAL,
    details TEXT,  -- JSON with computation details
    computed_at TEXT DEFAULT (datetime('now'))
);

-- Review audit trail
CREATE TABLE IF NOT EXISTS review_audit (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_type TEXT NOT NULL,  -- 'claim' or 'edge'
    proposal_id TEXT NOT NULL,
    decision TEXT NOT NULL,  -- APPROVED, REJECTED
    reviewer TEXT,
    notes TEXT,
    timestamp TEXT DEFAULT (datetime('now'))
);

-- Proposed nodes awaiting human review (agent staging)
CREATE TABLE IF NOT EXISTS proposed_nodes (
    proposal_id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    node_type TEXT NOT NULL,
    name TEXT NOT NULL,
    aliases TEXT,
    description TEXT,
    agent_name TEXT NOT NULL,
    source_url TEXT,
    reasoning TEXT,
    status TEXT DEFAULT 'PENDING',  -- PENDING, APPROVED, REJECTED
    resolved_node_id TEXT,
    reviewer_notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    resolved_at TEXT
);

-- Proposal counter for sequential IDs
CREATE TABLE IF NOT EXISTS proposal_counter (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    next_proposal_num INTEGER DEFAULT 1
);
INSERT OR IGNORE INTO proposal_counter (id, next_proposal_num) VALUES (1, 1);

CREATE INDEX IF NOT EXISTS idx_proposed_claims_status ON proposed_claims(status);
CREATE INDEX IF NOT EXISTS idx_proposed_edges_status ON proposed_edges(status);
CREATE INDEX IF NOT EXISTS idx_proposed_claims_agent ON proposed_claims(agent_name);
CREATE INDEX IF NOT EXISTS idx_proposed_edges_agent ON proposed_edges(agent_name);
CREATE INDEX IF NOT EXISTS idx_proposed_nodes_status ON proposed_nodes(status);
CREATE INDEX IF NOT EXISTS idx_proposed_nodes_agent ON proposed_nodes(agent_name);
CREATE INDEX IF NOT EXISTS idx_correlation_metrics_proposal ON correlation_metrics(proposal_id);

-- Ingest run tracking (for delta detection in live signals)
CREATE TABLE IF NOT EXISTS ingest_runs (
    run_id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT DEFAULT 'RUNNING',  -- RUNNING, SUCCESS, FAILED
    proposals_count INTEGER DEFAULT 0,
    delta_hash TEXT,                -- SHA256 of new proposals since last run
    previous_run_id TEXT,
    metadata TEXT                   -- JSON: error_message, source_counts, etc.
);
CREATE INDEX IF NOT EXISTS idx_ingest_runs_agent ON ingest_runs(agent_name);
CREATE INDEX IF NOT EXISTS idx_ingest_runs_status ON ingest_runs(status);

-- Facility capacity tracking (enriches FACILITY nodes)
CREATE TABLE IF NOT EXISTS facility_capacity (
    facility_node_id TEXT PRIMARY KEY,
    company_node_id TEXT,
    capacity_type TEXT,             -- 'fab_wafer_starts', 'assembly_units', 'tons', etc.
    capacity_value REAL,
    capacity_unit TEXT,             -- 'wafers/month', 'units/year', 'tons/year'
    process_node TEXT,              -- For semiconductors: '3nm', '5nm', '7nm', etc.
    operational_status TEXT,        -- 'operational', 'construction', 'planned', 'announced'
    operational_date TEXT,          -- When operational or expected
    investment_usd REAL,
    last_updated TEXT
);

-- Supply chain scores (computed, auditable)
CREATE TABLE IF NOT EXISTS supply_chain_scores (
    score_id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_node_id TEXT NOT NULL,
    score_type TEXT NOT NULL,       -- 'domestic_capacity', 'supplier_concentration', 'bottleneck_risk'
    score_value REAL,               -- 0.0 to 1.0 or 0 to 100
    components TEXT,                -- JSON: breakdown of score components
    computed_at TEXT,
    methodology TEXT                -- Brief description of scoring logic
);
CREATE INDEX IF NOT EXISTS idx_sc_scores_company ON supply_chain_scores(company_node_id);
CREATE INDEX IF NOT EXISTS idx_sc_scores_type ON supply_chain_scores(score_type);

-- Artifact queue for FilterAgent content triage
CREATE TABLE IF NOT EXISTS artifact_queue (
    artifact_id TEXT PRIMARY KEY,
    source_id TEXT,
    url TEXT,
    artifact_path TEXT,
    content_hash TEXT,
    content_type TEXT,              -- 'rss', 'pdf', 'filing', 'transcript', 'html'
    fetched_at TEXT,
    -- Filter outputs (Hughes-style triage)
    filter_score REAL,              -- 0-100 priority score
    route TEXT DEFAULT 'PENDING',   -- FAST_TRACK, HUMAN_REVIEW, DEPRIORITIZE, PENDING
    reason_codes TEXT,              -- JSON array: [PRIMARY_DOC_LINKED, NO_CITATION, etc.]
    manipulation_flags TEXT,        -- JSON array: [HIGH_EMOTION, CERTAINTY_NO_CITE, etc.]
    novelty_score REAL,             -- 0-1, how novel vs existing graph
    se_score REAL,                  -- Signal Entropy: H * C * D
    -- Processing status
    status TEXT DEFAULT 'PENDING',  -- PENDING, FILTERING, FILTERED, EXTRACTING, EXTRACTED, FAILED
    extracted_at TEXT,
    error_message TEXT,
    -- Metadata
    word_count INTEGER,
    entity_density REAL,            -- entities per 100 words
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_artifact_queue_status ON artifact_queue(status);
CREATE INDEX IF NOT EXISTS idx_artifact_queue_route ON artifact_queue(route);
CREATE INDEX IF NOT EXISTS idx_artifact_queue_score ON artifact_queue(filter_score);
"""

FTS_SCHEMA_SQL = """
-- Full-text search for nodes
CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
    node_id,
    name,
    description,
    content='nodes',
    content_rowid='rowid'
);

-- Full-text search for edges
CREATE VIRTUAL TABLE IF NOT EXISTS edges_fts USING fts5(
    edge_id,
    notes,
    source,
    content='edges',
    content_rowid='rowid'
);

-- Full-text search for claims
CREATE VIRTUAL TABLE IF NOT EXISTS claims_fts USING fts5(
    claim_id,
    claim_text,
    topic,
    content='claims',
    content_rowid='rowid'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS nodes_ai AFTER INSERT ON nodes BEGIN
    INSERT INTO nodes_fts(rowid, node_id, name, description)
    VALUES (NEW.rowid, NEW.node_id, NEW.name, NEW.description);
END;

CREATE TRIGGER IF NOT EXISTS nodes_ad AFTER DELETE ON nodes BEGIN
    INSERT INTO nodes_fts(nodes_fts, rowid, node_id, name, description)
    VALUES('delete', OLD.rowid, OLD.node_id, OLD.name, OLD.description);
END;

CREATE TRIGGER IF NOT EXISTS nodes_au AFTER UPDATE ON nodes BEGIN
    INSERT INTO nodes_fts(nodes_fts, rowid, node_id, name, description)
    VALUES('delete', OLD.rowid, OLD.node_id, OLD.name, OLD.description);
    INSERT INTO nodes_fts(rowid, node_id, name, description)
    VALUES (NEW.rowid, NEW.node_id, NEW.name, NEW.description);
END;

CREATE TRIGGER IF NOT EXISTS edges_ai AFTER INSERT ON edges BEGIN
    INSERT INTO edges_fts(rowid, edge_id, notes, source)
    VALUES (NEW.rowid, NEW.edge_id, NEW.notes, NEW.source);
END;

CREATE TRIGGER IF NOT EXISTS edges_ad AFTER DELETE ON edges BEGIN
    INSERT INTO edges_fts(edges_fts, rowid, edge_id, notes, source)
    VALUES('delete', OLD.rowid, OLD.edge_id, OLD.notes, OLD.source);
END;

CREATE TRIGGER IF NOT EXISTS edges_au AFTER UPDATE ON edges BEGIN
    INSERT INTO edges_fts(edges_fts, rowid, edge_id, notes, source)
    VALUES('delete', OLD.rowid, OLD.edge_id, OLD.notes, OLD.source);
    INSERT INTO edges_fts(rowid, edge_id, notes, source)
    VALUES (NEW.rowid, NEW.edge_id, NEW.notes, NEW.source);
END;

CREATE TRIGGER IF NOT EXISTS claims_ai AFTER INSERT ON claims BEGIN
    INSERT INTO claims_fts(rowid, claim_id, claim_text, topic)
    VALUES (NEW.rowid, NEW.claim_id, NEW.claim_text, NEW.topic);
END;

CREATE TRIGGER IF NOT EXISTS claims_ad AFTER DELETE ON claims BEGIN
    INSERT INTO claims_fts(claims_fts, rowid, claim_id, claim_text, topic)
    VALUES('delete', OLD.rowid, OLD.claim_id, OLD.claim_text, OLD.topic);
END;

CREATE TRIGGER IF NOT EXISTS claims_au AFTER UPDATE ON claims BEGIN
    INSERT INTO claims_fts(claims_fts, rowid, claim_id, claim_text, topic)
    VALUES('delete', OLD.rowid, OLD.claim_id, OLD.claim_text, OLD.topic);
    INSERT INTO claims_fts(rowid, claim_id, claim_text, topic)
    VALUES (NEW.rowid, NEW.claim_id, NEW.claim_text, NEW.topic);
END;
"""


class FGIPDatabase:
    """SQLite database for the FGIP knowledge graph with Square-One compliance."""

    def __init__(self, db_path: str = "fgip.db"):
        self.db_path = Path(db_path)
        self.conn: Optional[sqlite3.Connection] = None

    def connect(self) -> sqlite3.Connection:
        if self.conn is None:
            self.conn = sqlite3.connect(str(self.db_path))
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys = ON")
        return self.conn

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def init_schema(self) -> Receipt:
        """Initialize database schema including Square-One tables."""
        conn = self.connect()
        input_hash = compute_sha256({"schema": SCHEMA_SQL, "fts": FTS_SCHEMA_SQL})

        try:
            conn.executescript(SCHEMA_SQL)
            conn.executescript(FTS_SCHEMA_SQL)
            conn.commit()
            success = True
            output_hash = compute_sha256({"tables_created": True})
        except Exception as e:
            success = False
            output_hash = compute_sha256({"error": str(e)})

        receipt = Receipt(
            receipt_id=str(uuid.uuid4()),
            operation="init_schema",
            timestamp=datetime.utcnow().isoformat() + "Z",
            input_hash=input_hash,
            output_hash=output_hash,
            success=success,
            details={"db_path": str(self.db_path)},
        )
        self._save_receipt(receipt)
        return receipt

    def _save_receipt(self, receipt: Receipt):
        conn = self.connect()
        conn.execute(
            """INSERT INTO receipts
               (receipt_id, operation, timestamp, input_hash, output_hash, success, details)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (receipt.receipt_id, receipt.operation, receipt.timestamp,
             receipt.input_hash, receipt.output_hash, 1 if receipt.success else 0,
             json.dumps(receipt.details)),
        )
        conn.commit()

    def migrate_nlp_columns(self):
        """Add NLP extraction columns to proposal tables (idempotent)."""
        conn = self.connect()

        # Columns to add to proposed_claims
        claim_columns = [
            ("evidence_span", "TEXT"),           # Exact quote snippet
            ("evidence_offset", "INTEGER"),      # Character offset in source
            ("entity_candidates", "TEXT"),       # JSON: [{node_id, confidence, why}]
            ("reason_codes", "TEXT"),            # JSON array: [PRIMARY_DOC_LINKED, etc.]
            ("counter_evidence", "TEXT"),        # Detected negations/denials
            ("se_score", "REAL"),                # Signal Entropy score
        ]

        # Columns to add to proposed_edges
        edge_columns = [
            ("evidence_span", "TEXT"),
            ("evidence_offset", "INTEGER"),
            ("entity_candidates", "TEXT"),
            ("reason_codes", "TEXT"),
            ("counter_evidence", "TEXT"),
            ("se_score", "REAL"),
            ("relation_confidence", "REAL"),     # NLP-derived confidence
        ]

        # Add columns to proposed_claims (ignore if already exists)
        for col_name, col_type in claim_columns:
            try:
                conn.execute(f"ALTER TABLE proposed_claims ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError:
                pass  # Column already exists

        # Add columns to proposed_edges
        for col_name, col_type in edge_columns:
            try:
                conn.execute(f"ALTER TABLE proposed_edges ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError:
                pass  # Column already exists

        conn.commit()

    def migrate_artifact_fk(self):
        """Add artifact_id foreign key to proposal tables (idempotent).

        This enables full traceability: proposal → artifact_queue.
        Part of the "no bypass" plumbing system.
        """
        conn = self.connect()

        # Add artifact_id to proposed_claims
        try:
            conn.execute("""
                ALTER TABLE proposed_claims
                ADD COLUMN artifact_id TEXT REFERENCES artifact_queue(artifact_id)
            """)
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Add artifact_id to proposed_edges
        try:
            conn.execute("""
                ALTER TABLE proposed_edges
                ADD COLUMN artifact_id TEXT REFERENCES artifact_queue(artifact_id)
            """)
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Add bypass_pipeline flag (for intentional legacy bypasses)
        try:
            conn.execute("""
                ALTER TABLE proposed_claims
                ADD COLUMN bypass_pipeline INTEGER DEFAULT 0
            """)
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("""
                ALTER TABLE proposed_edges
                ADD COLUMN bypass_pipeline INTEGER DEFAULT 0
            """)
        except sqlite3.OperationalError:
            pass

        # Create indexes for traceability queries
        try:
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_proposed_claims_artifact
                ON proposed_claims(artifact_id)
            """)
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_proposed_edges_artifact
                ON proposed_edges(artifact_id)
            """)
        except sqlite3.OperationalError:
            pass

        conn.commit()

    def migrate_price_history(self):
        """Add price_history table for backtest module (idempotent)."""
        conn = self.connect()

        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS price_history (
                    symbol TEXT NOT NULL,
                    date TEXT NOT NULL,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    adj_close REAL,
                    volume INTEGER,
                    source TEXT DEFAULT 'yfinance',
                    fetched_at TEXT,
                    PRIMARY KEY (symbol, date)
                )
            """)
        except sqlite3.OperationalError:
            pass  # Table already exists

        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_price_symbol ON price_history(symbol)")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_price_date ON price_history(date)")
        except sqlite3.OperationalError:
            pass

        conn.commit()

    def run_migrations(self):
        """Run all schema migrations (idempotent)."""
        self.migrate_nlp_columns()
        self.migrate_artifact_fk()
        self.migrate_price_history()

    # ========== Source Operations (Square-One) ==========

    def get_next_claim_id(self) -> str:
        """Get next sequential claim ID."""
        conn = self.connect()
        row = conn.execute("SELECT next_claim_num FROM claim_counter WHERE id = 1").fetchone()
        num = row[0] if row else 1
        conn.execute("UPDATE claim_counter SET next_claim_num = ? WHERE id = 1", (num + 1,))
        conn.commit()
        return f"FGIP-{num:06d}"

    def insert_source(self, source: Source) -> bool:
        """Insert or update a source."""
        conn = self.connect()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO sources
                   (source_id, url, domain, tier, retrieved_at, artifact_path, artifact_hash, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (source.source_id, source.url, source.domain, source.tier,
                 source.retrieved_at, source.artifact_path, source.artifact_hash, source.notes),
            )
            conn.commit()
            return True
        except Exception:
            return False

    def get_source(self, source_id: str) -> Optional[Source]:
        """Get source by ID."""
        conn = self.connect()
        row = conn.execute("SELECT * FROM sources WHERE source_id = ?", (source_id,)).fetchone()
        if row is None:
            return None
        return Source(
            source_id=row["source_id"],
            url=row["url"],
            domain=row["domain"],
            tier=row["tier"],
            retrieved_at=row["retrieved_at"],
            artifact_path=row["artifact_path"],
            artifact_hash=row["artifact_hash"],
            notes=row["notes"],
        )

    def get_source_by_url(self, url: str) -> Optional[Source]:
        """Get source by URL."""
        source_id = compute_sha256(url)
        return self.get_source(source_id)

    def list_sources(self, tier: Optional[int] = None, limit: int = 100) -> list[Source]:
        """List sources, optionally filtered by tier."""
        conn = self.connect()
        if tier is not None:
            rows = conn.execute(
                "SELECT * FROM sources WHERE tier = ? LIMIT ?", (tier, limit)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM sources LIMIT ?", (limit,)).fetchall()
        return [Source(
            source_id=r["source_id"], url=r["url"], domain=r["domain"],
            tier=r["tier"], retrieved_at=r["retrieved_at"],
            artifact_path=r["artifact_path"], artifact_hash=r["artifact_hash"],
            notes=r["notes"]
        ) for r in rows]

    # ========== Claim Operations (Square-One) ==========

    def insert_claim(self, claim: Claim) -> bool:
        """Insert a claim."""
        conn = self.connect()
        try:
            conn.execute(
                """INSERT INTO claims
                   (claim_id, claim_text, topic, status, required_tier, created_at, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (claim.claim_id, claim.claim_text, claim.topic, claim.status.value,
                 claim.required_tier, claim.created_at, claim.notes),
            )
            conn.commit()
            return True
        except Exception:
            return False

    def get_claim(self, claim_id: str) -> Optional[Claim]:
        """Get claim by ID."""
        conn = self.connect()
        row = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
        if row is None:
            return None
        return Claim(
            claim_id=row["claim_id"],
            claim_text=row["claim_text"],
            topic=row["topic"],
            status=ClaimStatus(row["status"]),
            required_tier=row["required_tier"],
            created_at=row["created_at"],
            notes=row["notes"],
        )

    def list_claims(self, status: Optional[str] = None, topic: Optional[str] = None,
                    limit: int = 100) -> list[Claim]:
        """List claims with optional filters."""
        conn = self.connect()
        query = "SELECT * FROM claims WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if topic:
            query += " AND topic = ?"
            params.append(topic)
        query += " ORDER BY claim_id LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [Claim(
            claim_id=r["claim_id"], claim_text=r["claim_text"], topic=r["topic"],
            status=ClaimStatus(r["status"]), required_tier=r["required_tier"],
            created_at=r["created_at"], notes=r["notes"]
        ) for r in rows]

    def update_claim_status(self, claim_id: str, status: ClaimStatus) -> bool:
        """Update claim status."""
        conn = self.connect()
        try:
            conn.execute(
                "UPDATE claims SET status = ? WHERE claim_id = ?",
                (status.value, claim_id)
            )
            conn.commit()
            return True
        except Exception:
            return False

    def link_claim_source(self, claim_id: str, source_id: str) -> bool:
        """Link a claim to a source."""
        conn = self.connect()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO claim_sources (claim_id, source_id) VALUES (?, ?)",
                (claim_id, source_id)
            )
            conn.commit()
            return True
        except Exception:
            return False

    def get_claim_sources(self, claim_id: str) -> list[Source]:
        """Get all sources for a claim."""
        conn = self.connect()
        rows = conn.execute(
            """SELECT s.* FROM sources s
               JOIN claim_sources cs ON s.source_id = cs.source_id
               WHERE cs.claim_id = ?""",
            (claim_id,)
        ).fetchall()
        return [Source(
            source_id=r["source_id"], url=r["url"], domain=r["domain"],
            tier=r["tier"], retrieved_at=r["retrieved_at"],
            artifact_path=r["artifact_path"], artifact_hash=r["artifact_hash"],
            notes=r["notes"]
        ) for r in rows]

    def get_claim_for_edge(self, edge_id: str) -> Optional[Claim]:
        """Get the claim backing an edge."""
        conn = self.connect()
        row = conn.execute(
            """SELECT c.* FROM claims c
               JOIN edges e ON e.claim_id = c.claim_id
               WHERE e.edge_id = ?""",
            (edge_id,)
        ).fetchone()
        if row is None:
            return None
        return Claim(
            claim_id=row["claim_id"], claim_text=row["claim_text"], topic=row["topic"],
            status=ClaimStatus(row["status"]), required_tier=row["required_tier"],
            created_at=row["created_at"], notes=row["notes"]
        )

    # ========== Node Operations ==========

    def insert_node(self, node: Node) -> Receipt:
        errors = node.validate()
        if errors:
            raise ValueError(f"Invalid node: {errors}")

        conn = self.connect()
        input_hash = node.sha256

        try:
            conn.execute(
                """INSERT INTO nodes
                   (node_id, node_type, name, aliases, description, metadata, created_at, sha256)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (node.node_id, node.node_type.value, node.name,
                 json.dumps(node.aliases), node.description,
                 json.dumps(node.metadata), node.created_at, node.sha256),
            )
            conn.commit()
            success = True
            output_hash = compute_sha256({"node_id": node.node_id, "inserted": True})
        except sqlite3.IntegrityError as e:
            success = False
            output_hash = compute_sha256({"error": str(e)})

        receipt = Receipt(
            receipt_id=str(uuid.uuid4()),
            operation="insert_node",
            timestamp=datetime.utcnow().isoformat() + "Z",
            input_hash=input_hash,
            output_hash=output_hash,
            success=success,
            details={"node_id": node.node_id, "node_type": node.node_type.value},
        )
        self._save_receipt(receipt)
        return receipt

    def get_node(self, node_id: str) -> Optional[Node]:
        conn = self.connect()
        row = conn.execute("SELECT * FROM nodes WHERE node_id = ?", (node_id,)).fetchone()
        if row is None:
            return None
        return Node(
            node_id=row["node_id"],
            node_type=row["node_type"],
            name=row["name"],
            aliases=json.loads(row["aliases"]) if row["aliases"] else [],
            description=row["description"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=row["created_at"],
            sha256=row["sha256"],
        )

    def list_nodes(self, node_type: Optional[str] = None, limit: int = 100) -> list[Node]:
        conn = self.connect()
        if node_type:
            rows = conn.execute(
                "SELECT * FROM nodes WHERE node_type = ? LIMIT ?", (node_type, limit)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM nodes LIMIT ?", (limit,)).fetchall()
        return [Node(
            node_id=r["node_id"], node_type=r["node_type"], name=r["name"],
            aliases=json.loads(r["aliases"]) if r["aliases"] else [],
            description=r["description"],
            metadata=json.loads(r["metadata"]) if r["metadata"] else {},
            created_at=r["created_at"], sha256=r["sha256"]
        ) for r in rows]

    def search_nodes(self, query: str, limit: int = 50) -> list[Node]:
        conn = self.connect()
        rows = conn.execute(
            """SELECT n.* FROM nodes n
               JOIN nodes_fts fts ON n.node_id = fts.node_id
               WHERE nodes_fts MATCH ? LIMIT ?""",
            (query, limit)
        ).fetchall()
        return [Node(
            node_id=r["node_id"], node_type=r["node_type"], name=r["name"],
            aliases=json.loads(r["aliases"]) if r["aliases"] else [],
            description=r["description"],
            metadata=json.loads(r["metadata"]) if r["metadata"] else {},
            created_at=r["created_at"], sha256=r["sha256"]
        ) for r in rows]

    # ========== Edge Operations ==========

    def insert_edge(self, edge: Edge) -> Receipt:
        errors = edge.validate()
        if errors:
            raise ValueError(f"Invalid edge: {errors}")

        conn = self.connect()
        input_hash = edge.sha256

        try:
            conn.execute(
                """INSERT INTO edges
                   (edge_id, edge_type, from_node_id, to_node_id, claim_id, assertion_level,
                    source, source_url, source_type, date_documented, date_occurred, date_ended,
                    confidence, notes, metadata, created_at, sha256)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (edge.edge_id, edge.edge_type.value, edge.from_node_id, edge.to_node_id,
                 edge.claim_id, edge.assertion_level, edge.source, edge.source_url,
                 edge.source_type.value if edge.source_type else None,
                 edge.date_documented, edge.date_occurred, edge.date_ended,
                 edge.confidence, edge.notes, json.dumps(edge.metadata),
                 edge.created_at, edge.sha256),
            )
            conn.commit()
            success = True
            output_hash = compute_sha256({"edge_id": edge.edge_id, "inserted": True})
        except sqlite3.IntegrityError as e:
            success = False
            output_hash = compute_sha256({"error": str(e)})

        receipt = Receipt(
            receipt_id=str(uuid.uuid4()),
            operation="insert_edge",
            timestamp=datetime.utcnow().isoformat() + "Z",
            input_hash=input_hash,
            output_hash=output_hash,
            success=success,
            details={"edge_id": edge.edge_id, "edge_type": edge.edge_type.value,
                     "from": edge.from_node_id, "to": edge.to_node_id,
                     "claim_id": edge.claim_id},
        )
        self._save_receipt(receipt)
        return receipt

    def get_edge(self, edge_id: str) -> Optional[Edge]:
        conn = self.connect()
        row = conn.execute("SELECT * FROM edges WHERE edge_id = ?", (edge_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_edge(row)

    def _row_to_edge(self, row) -> Edge:
        return Edge(
            edge_id=row["edge_id"],
            edge_type=row["edge_type"],
            from_node_id=row["from_node_id"],
            to_node_id=row["to_node_id"],
            claim_id=row["claim_id"],
            assertion_level=row["assertion_level"] if "assertion_level" in row.keys() else "FACT",
            source=row["source"],
            source_url=row["source_url"],
            source_type=row["source_type"],
            date_documented=row["date_documented"],
            date_occurred=row["date_occurred"],
            date_ended=row["date_ended"],
            confidence=row["confidence"],
            notes=row["notes"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=row["created_at"],
            sha256=row["sha256"],
        )

    def list_edges(self, from_node_id: Optional[str] = None, to_node_id: Optional[str] = None,
                   edge_type: Optional[str] = None, limit: int = 100) -> list[Edge]:
        conn = self.connect()
        query = "SELECT * FROM edges WHERE 1=1"
        params = []
        if from_node_id:
            query += " AND from_node_id = ?"
            params.append(from_node_id)
        if to_node_id:
            query += " AND to_node_id = ?"
            params.append(to_node_id)
        if edge_type:
            query += " AND edge_type = ?"
            params.append(edge_type)
        query += " LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_edge(r) for r in rows]

    def search_edges(self, query: str, limit: int = 50) -> list[Edge]:
        conn = self.connect()
        rows = conn.execute(
            """SELECT e.* FROM edges e
               JOIN edges_fts fts ON e.edge_id = fts.edge_id
               WHERE edges_fts MATCH ? LIMIT ?""",
            (query, limit)
        ).fetchall()
        return [self._row_to_edge(r) for r in rows]

    def get_neighbors(self, node_id: str, direction: str = "both") -> list[tuple[Edge, Node]]:
        conn = self.connect()
        results = []

        if direction in ("outgoing", "both"):
            rows = conn.execute(
                """SELECT e.*, n.* FROM edges e
                   JOIN nodes n ON e.to_node_id = n.node_id
                   WHERE e.from_node_id = ?""",
                (node_id,)
            ).fetchall()
            for row in rows:
                edge = self._row_to_edge(row)
                node = self.get_node(row["to_node_id"])
                if node:
                    results.append((edge, node))

        if direction in ("incoming", "both"):
            rows = conn.execute(
                """SELECT e.*, n.* FROM edges e
                   JOIN nodes n ON e.from_node_id = n.node_id
                   WHERE e.to_node_id = ?""",
                (node_id,)
            ).fetchall()
            for row in rows:
                edge = self._row_to_edge(row)
                node = self.get_node(row["from_node_id"])
                if node:
                    results.append((edge, node))

        return results

    def update_edge_claim(self, edge_id: str, claim_id: str) -> bool:
        """Update edge to reference a claim (Square-One migration)."""
        conn = self.connect()
        try:
            conn.execute(
                "UPDATE edges SET claim_id = ? WHERE edge_id = ?",
                (claim_id, edge_id)
            )
            conn.commit()
            return True
        except Exception:
            return False

    # ========== Statistics ==========

    def get_stats(self) -> dict:
        conn = self.connect()
        node_count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        edge_count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        receipt_count = conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]
        source_count = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        claim_count = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]

        node_types = conn.execute(
            "SELECT node_type, COUNT(*) FROM nodes GROUP BY node_type"
        ).fetchall()
        edge_types = conn.execute(
            "SELECT edge_type, COUNT(*) FROM edges GROUP BY edge_type"
        ).fetchall()
        claim_statuses = conn.execute(
            "SELECT status, COUNT(*) FROM claims GROUP BY status"
        ).fetchall()
        source_tiers = conn.execute(
            "SELECT tier, COUNT(*) FROM sources GROUP BY tier"
        ).fetchall()

        # Evidence coverage: edges with claims
        edges_with_claims = conn.execute(
            "SELECT COUNT(*) FROM edges WHERE claim_id IS NOT NULL"
        ).fetchone()[0]

        # Tier 0/1 claims
        tier_01_claims = conn.execute(
            """SELECT COUNT(DISTINCT c.claim_id) FROM claims c
               JOIN claim_sources cs ON c.claim_id = cs.claim_id
               JOIN sources s ON cs.source_id = s.source_id
               WHERE s.tier <= 1"""
        ).fetchone()[0]

        return {
            "nodes": node_count,
            "edges": edge_count,
            "sources": source_count,
            "claims": claim_count,
            "receipts": receipt_count,
            "node_types": {row[0]: row[1] for row in node_types},
            "edge_types": {row[0]: row[1] for row in edge_types},
            "claim_statuses": {row[0]: row[1] for row in claim_statuses},
            "source_tiers": {f"tier_{row[0]}": row[1] for row in source_tiers},
            "edges_with_claims": edges_with_claims,
            "evidence_coverage": edges_with_claims / edge_count if edge_count > 0 else 0,
            "tier_01_claims": tier_01_claims,
        }

    def get_evidence_status(self) -> dict:
        """Get detailed evidence status for Square-One compliance."""
        conn = self.connect()

        total_claims = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
        verified = conn.execute(
            "SELECT COUNT(*) FROM claims WHERE status = 'VERIFIED'"
        ).fetchone()[0]
        evidenced = conn.execute(
            "SELECT COUNT(*) FROM claims WHERE status = 'EVIDENCED'"
        ).fetchone()[0]
        partial = conn.execute(
            "SELECT COUNT(*) FROM claims WHERE status = 'PARTIAL'"
        ).fetchone()[0]
        missing = conn.execute(
            "SELECT COUNT(*) FROM claims WHERE status = 'MISSING'"
        ).fetchone()[0]

        total_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        edges_with_claims = conn.execute(
            "SELECT COUNT(*) FROM edges WHERE claim_id IS NOT NULL"
        ).fetchone()[0]
        orphan_edges = total_edges - edges_with_claims

        # Edges backed by Tier 0/1 sources
        tier_01_edges = conn.execute(
            """SELECT COUNT(DISTINCT e.edge_id) FROM edges e
               JOIN claims c ON e.claim_id = c.claim_id
               JOIN claim_sources cs ON c.claim_id = cs.claim_id
               JOIN sources s ON cs.source_id = s.source_id
               WHERE s.tier <= 1"""
        ).fetchone()[0]

        return {
            "total_claims": total_claims,
            "verified": verified,
            "evidenced": evidenced,
            "partial": partial,
            "missing": missing,
            "total_edges": total_edges,
            "edges_with_claims": edges_with_claims,
            "orphan_edges": orphan_edges,
            "tier_01_edges": tier_01_edges,
            "evidence_coverage_pct": (edges_with_claims / total_edges * 100) if total_edges > 0 else 0,
            "tier_01_coverage_pct": (tier_01_edges / total_edges * 100) if total_edges > 0 else 0,
        }
