"""Evidence graph database — domain-agnostic SQLite layer.

Provides CRUD for nodes, edges, claims, sources, and receipts.
Uses a DomainRegistry for type validation and ID formatting.
No domain-specific tables (facility_capacity, supply_chain_scores, etc.)
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
import uuid

from .schema import (
    Node, Edge, Receipt, Source, Claim, ClaimStatus,
    AssertionLevel, compute_sha256, extract_domain,
)
from .registry import DomainRegistry


# Core schema — nodes, edges, claims, sources, receipts, staging
CORE_SCHEMA_SQL = """
-- Sources table
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

-- Claims table
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

-- Entities
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

-- Relationships with claim references
CREATE TABLE IF NOT EXISTS edges (
    edge_id TEXT PRIMARY KEY,
    edge_type TEXT NOT NULL,
    from_node_id TEXT NOT NULL,
    to_node_id TEXT NOT NULL,
    claim_id TEXT REFERENCES claims(claim_id),
    assertion_level TEXT DEFAULT 'FACT',
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

-- Receipts table
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

-- Proposed claims awaiting review
CREATE TABLE IF NOT EXISTS proposed_claims (
    proposal_id TEXT PRIMARY KEY,
    claim_text TEXT NOT NULL,
    topic TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    source_url TEXT,
    artifact_path TEXT,
    artifact_hash TEXT,
    reasoning TEXT,
    promotion_requirement TEXT,
    status TEXT DEFAULT 'PENDING',
    resolved_claim_id TEXT,
    reviewer_notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    resolved_at TEXT
);

-- Proposed edges awaiting review
CREATE TABLE IF NOT EXISTS proposed_edges (
    proposal_id TEXT PRIMARY KEY,
    from_node TEXT NOT NULL,
    to_node TEXT NOT NULL,
    relationship TEXT NOT NULL,
    detail TEXT,
    proposed_claim_id TEXT,
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

-- Proposed nodes awaiting review
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
    status TEXT DEFAULT 'PENDING',
    resolved_node_id TEXT,
    reviewer_notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    resolved_at TEXT
);

-- Proposal counter
CREATE TABLE IF NOT EXISTS proposal_counter (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    next_proposal_num INTEGER DEFAULT 1
);
INSERT OR IGNORE INTO proposal_counter (id, next_proposal_num) VALUES (1, 1);

-- Correlation metrics
CREATE TABLE IF NOT EXISTS correlation_metrics (
    metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id TEXT,
    metric_type TEXT NOT NULL,
    metric_value REAL,
    details TEXT,
    computed_at TEXT DEFAULT (datetime('now'))
);

-- Review audit trail
CREATE TABLE IF NOT EXISTS review_audit (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_type TEXT NOT NULL,
    proposal_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    reviewer TEXT,
    notes TEXT,
    timestamp TEXT DEFAULT (datetime('now'))
);

-- Ingest run tracking
CREATE TABLE IF NOT EXISTS ingest_runs (
    run_id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT DEFAULT 'RUNNING',
    proposals_count INTEGER DEFAULT 0,
    delta_hash TEXT,
    previous_run_id TEXT,
    metadata TEXT
);

-- Domain registry metadata
CREATE TABLE IF NOT EXISTS _meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Staging indexes
CREATE INDEX IF NOT EXISTS idx_proposed_claims_status ON proposed_claims(status);
CREATE INDEX IF NOT EXISTS idx_proposed_edges_status ON proposed_edges(status);
CREATE INDEX IF NOT EXISTS idx_proposed_claims_agent ON proposed_claims(agent_name);
CREATE INDEX IF NOT EXISTS idx_proposed_edges_agent ON proposed_edges(agent_name);
CREATE INDEX IF NOT EXISTS idx_proposed_nodes_status ON proposed_nodes(status);
CREATE INDEX IF NOT EXISTS idx_proposed_nodes_agent ON proposed_nodes(agent_name);
CREATE INDEX IF NOT EXISTS idx_correlation_metrics_proposal ON correlation_metrics(proposal_id);
CREATE INDEX IF NOT EXISTS idx_ingest_runs_agent ON ingest_runs(agent_name);
CREATE INDEX IF NOT EXISTS idx_ingest_runs_status ON ingest_runs(status);
"""

FTS_SCHEMA_SQL = """
-- Full-text search for nodes
CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
    node_id, name, description,
    content='nodes', content_rowid='rowid'
);

-- Full-text search for edges
CREATE VIRTUAL TABLE IF NOT EXISTS edges_fts USING fts5(
    edge_id, notes, source,
    content='edges', content_rowid='rowid'
);

-- Full-text search for claims
CREATE VIRTUAL TABLE IF NOT EXISTS claims_fts USING fts5(
    claim_id, claim_text, topic,
    content='claims', content_rowid='rowid'
);

-- Sync triggers
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


class EvidenceGraphDB:
    """Domain-agnostic evidence graph database."""

    def __init__(self, db_path: str = "evidence.db", registry: DomainRegistry = None):
        self.db_path = Path(db_path)
        self.registry = registry
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
        """Initialize database schema and store registry in _meta."""
        conn = self.connect()
        input_hash = compute_sha256({"schema": "core_v1"})

        try:
            conn.executescript(CORE_SCHEMA_SQL)
            conn.executescript(FTS_SCHEMA_SQL)
            # Store registry manifest in _meta
            if self.registry:
                conn.execute(
                    "INSERT OR REPLACE INTO _meta (key, value) VALUES (?, ?)",
                    ("domain_registry", self.registry.to_json()),
                )
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

    def load_registry_from_db(self) -> Optional[DomainRegistry]:
        """Load the domain registry from the _meta table."""
        conn = self.connect()
        try:
            row = conn.execute(
                "SELECT value FROM _meta WHERE key = 'domain_registry'"
            ).fetchone()
            if row:
                self.registry = DomainRegistry.from_dict(json.loads(row[0]))
                return self.registry
        except Exception:
            pass
        return None

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

    # ========== Claim ID generation ==========

    def get_next_claim_id(self) -> str:
        """Get next sequential claim ID using registry prefix."""
        conn = self.connect()
        row = conn.execute(
            "SELECT next_claim_num FROM claim_counter WHERE id = 1"
        ).fetchone()
        num = row[0] if row else 1
        conn.execute(
            "UPDATE claim_counter SET next_claim_num = ? WHERE id = 1",
            (num + 1,),
        )
        conn.commit()
        if self.registry:
            return self.registry.format_claim_id(num)
        return f"EG-{num:06d}"

    # ========== Source Operations ==========

    def insert_source(self, source: Source) -> bool:
        conn = self.connect()
        # Auto-tier via registry if source has default tier
        if self.registry and source.tier == 2 and source.domain:
            source.tier = self.registry.auto_tier_domain(source.domain)
        try:
            conn.execute(
                """INSERT OR REPLACE INTO sources
                   (source_id, url, domain, tier, retrieved_at,
                    artifact_path, artifact_hash, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (source.source_id, source.url, source.domain, source.tier,
                 source.retrieved_at, source.artifact_path,
                 source.artifact_hash, source.notes),
            )
            conn.commit()
            return True
        except Exception:
            return False

    def get_source(self, source_id: str) -> Optional[Source]:
        conn = self.connect()
        row = conn.execute(
            "SELECT * FROM sources WHERE source_id = ?", (source_id,)
        ).fetchone()
        if row is None:
            return None
        return Source(
            source_id=row["source_id"], url=row["url"],
            domain=row["domain"], tier=row["tier"],
            retrieved_at=row["retrieved_at"],
            artifact_path=row["artifact_path"],
            artifact_hash=row["artifact_hash"], notes=row["notes"],
        )

    def get_source_by_url(self, url: str) -> Optional[Source]:
        return self.get_source(compute_sha256(url))

    def list_sources(self, tier: Optional[int] = None,
                     limit: int = 100) -> list[Source]:
        conn = self.connect()
        if tier is not None:
            rows = conn.execute(
                "SELECT * FROM sources WHERE tier = ? LIMIT ?",
                (tier, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM sources LIMIT ?", (limit,)
            ).fetchall()
        return [Source(
            source_id=r["source_id"], url=r["url"], domain=r["domain"],
            tier=r["tier"], retrieved_at=r["retrieved_at"],
            artifact_path=r["artifact_path"],
            artifact_hash=r["artifact_hash"], notes=r["notes"],
        ) for r in rows]

    # ========== Claim Operations ==========

    def insert_claim(self, claim: Claim) -> bool:
        conn = self.connect()
        try:
            conn.execute(
                """INSERT INTO claims
                   (claim_id, claim_text, topic, status, required_tier,
                    created_at, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (claim.claim_id, claim.claim_text, claim.topic,
                 claim.status.value, claim.required_tier,
                 claim.created_at, claim.notes),
            )
            conn.commit()
            return True
        except Exception:
            return False

    def get_claim(self, claim_id: str) -> Optional[Claim]:
        conn = self.connect()
        row = conn.execute(
            "SELECT * FROM claims WHERE claim_id = ?", (claim_id,)
        ).fetchone()
        if row is None:
            return None
        return Claim(
            claim_id=row["claim_id"], claim_text=row["claim_text"],
            topic=row["topic"], status=ClaimStatus(row["status"]),
            required_tier=row["required_tier"],
            created_at=row["created_at"], notes=row["notes"],
        )

    def list_claims(self, status: Optional[str] = None,
                    topic: Optional[str] = None,
                    limit: int = 100) -> list[Claim]:
        conn = self.connect()
        query = "SELECT * FROM claims WHERE 1=1"
        params: list = []
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
            claim_id=r["claim_id"], claim_text=r["claim_text"],
            topic=r["topic"], status=ClaimStatus(r["status"]),
            required_tier=r["required_tier"],
            created_at=r["created_at"], notes=r["notes"],
        ) for r in rows]

    def update_claim_status(self, claim_id: str,
                            status: ClaimStatus) -> bool:
        conn = self.connect()
        try:
            conn.execute(
                "UPDATE claims SET status = ? WHERE claim_id = ?",
                (status.value, claim_id),
            )
            conn.commit()
            return True
        except Exception:
            return False

    def link_claim_source(self, claim_id: str, source_id: str) -> bool:
        conn = self.connect()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO claim_sources (claim_id, source_id) "
                "VALUES (?, ?)",
                (claim_id, source_id),
            )
            conn.commit()
            return True
        except Exception:
            return False

    def get_claim_sources(self, claim_id: str) -> list[Source]:
        conn = self.connect()
        rows = conn.execute(
            """SELECT s.* FROM sources s
               JOIN claim_sources cs ON s.source_id = cs.source_id
               WHERE cs.claim_id = ?""",
            (claim_id,),
        ).fetchall()
        return [Source(
            source_id=r["source_id"], url=r["url"], domain=r["domain"],
            tier=r["tier"], retrieved_at=r["retrieved_at"],
            artifact_path=r["artifact_path"],
            artifact_hash=r["artifact_hash"], notes=r["notes"],
        ) for r in rows]

    def get_claim_for_edge(self, edge_id: str) -> Optional[Claim]:
        conn = self.connect()
        row = conn.execute(
            """SELECT c.* FROM claims c
               JOIN edges e ON e.claim_id = c.claim_id
               WHERE e.edge_id = ?""",
            (edge_id,),
        ).fetchone()
        if row is None:
            return None
        return Claim(
            claim_id=row["claim_id"], claim_text=row["claim_text"],
            topic=row["topic"], status=ClaimStatus(row["status"]),
            required_tier=row["required_tier"],
            created_at=row["created_at"], notes=row["notes"],
        )

    # ========== Node Operations ==========

    def insert_node(self, node: Node) -> Receipt:
        errors = node.validate()
        if errors:
            raise ValueError(f"Invalid node: {errors}")

        # Validate node type against registry
        if self.registry:
            self.registry.validate_node_type(node.node_type)

        conn = self.connect()
        input_hash = node.sha256

        try:
            conn.execute(
                """INSERT INTO nodes
                   (node_id, node_type, name, aliases, description,
                    metadata, created_at, sha256)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (node.node_id, node.node_type, node.name,
                 json.dumps(node.aliases), node.description,
                 json.dumps(node.metadata), node.created_at, node.sha256),
            )
            conn.commit()
            success = True
            output_hash = compute_sha256({
                "node_id": node.node_id, "inserted": True,
            })
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
            details={"node_id": node.node_id, "node_type": node.node_type},
        )
        self._save_receipt(receipt)
        return receipt

    def get_node(self, node_id: str) -> Optional[Node]:
        conn = self.connect()
        row = conn.execute(
            "SELECT * FROM nodes WHERE node_id = ?", (node_id,)
        ).fetchone()
        if row is None:
            return None
        return Node(
            node_id=row["node_id"], node_type=row["node_type"],
            name=row["name"],
            aliases=json.loads(row["aliases"]) if row["aliases"] else [],
            description=row["description"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=row["created_at"], sha256=row["sha256"],
        )

    def list_nodes(self, node_type: Optional[str] = None,
                   limit: int = 100) -> list[Node]:
        conn = self.connect()
        if node_type:
            rows = conn.execute(
                "SELECT * FROM nodes WHERE node_type = ? LIMIT ?",
                (node_type, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM nodes LIMIT ?", (limit,)
            ).fetchall()
        return [Node(
            node_id=r["node_id"], node_type=r["node_type"],
            name=r["name"],
            aliases=json.loads(r["aliases"]) if r["aliases"] else [],
            description=r["description"],
            metadata=json.loads(r["metadata"]) if r["metadata"] else {},
            created_at=r["created_at"], sha256=r["sha256"],
        ) for r in rows]

    def search_nodes(self, query: str, limit: int = 50) -> list[Node]:
        conn = self.connect()
        rows = conn.execute(
            """SELECT n.* FROM nodes n
               JOIN nodes_fts fts ON n.node_id = fts.node_id
               WHERE nodes_fts MATCH ? LIMIT ?""",
            (query, limit),
        ).fetchall()
        return [Node(
            node_id=r["node_id"], node_type=r["node_type"],
            name=r["name"],
            aliases=json.loads(r["aliases"]) if r["aliases"] else [],
            description=r["description"],
            metadata=json.loads(r["metadata"]) if r["metadata"] else {},
            created_at=r["created_at"], sha256=r["sha256"],
        ) for r in rows]

    # ========== Edge Operations ==========

    def insert_edge(self, edge: Edge) -> Receipt:
        errors = edge.validate()
        if errors:
            raise ValueError(f"Invalid edge: {errors}")

        # Validate edge type and auto-set assertion level via registry
        if self.registry:
            self.registry.validate_edge_type(edge.edge_type)
            if edge.assertion_level is None:
                if self.registry.is_inferential(edge.edge_type):
                    edge.assertion_level = AssertionLevel.INFERENCE.value
                else:
                    edge.assertion_level = AssertionLevel.FACT.value

        conn = self.connect()
        input_hash = edge.sha256

        try:
            conn.execute(
                """INSERT INTO edges
                   (edge_id, edge_type, from_node_id, to_node_id,
                    claim_id, assertion_level, source, source_url,
                    source_type, date_documented, date_occurred,
                    date_ended, confidence, notes, metadata,
                    created_at, sha256)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (edge.edge_id, edge.edge_type, edge.from_node_id,
                 edge.to_node_id, edge.claim_id, edge.assertion_level,
                 edge.source, edge.source_url, None,
                 edge.date_documented, edge.date_occurred,
                 edge.date_ended, edge.confidence, edge.notes,
                 json.dumps(edge.metadata), edge.created_at, edge.sha256),
            )
            conn.commit()
            success = True
            output_hash = compute_sha256({
                "edge_id": edge.edge_id, "inserted": True,
            })
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
            details={
                "edge_id": edge.edge_id, "edge_type": edge.edge_type,
                "from": edge.from_node_id, "to": edge.to_node_id,
                "claim_id": edge.claim_id,
            },
        )
        self._save_receipt(receipt)
        return receipt

    def get_edge(self, edge_id: str) -> Optional[Edge]:
        conn = self.connect()
        row = conn.execute(
            "SELECT * FROM edges WHERE edge_id = ?", (edge_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_edge(row)

    def _row_to_edge(self, row) -> Edge:
        return Edge(
            edge_id=row["edge_id"], edge_type=row["edge_type"],
            from_node_id=row["from_node_id"],
            to_node_id=row["to_node_id"],
            claim_id=row["claim_id"],
            assertion_level=row["assertion_level"]
            if "assertion_level" in row.keys() else "FACT",
            source=row["source"], source_url=row["source_url"],
            date_documented=row["date_documented"],
            date_occurred=row["date_occurred"],
            date_ended=row["date_ended"],
            confidence=row["confidence"], notes=row["notes"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=row["created_at"], sha256=row["sha256"],
        )

    def list_edges(self, from_node_id: Optional[str] = None,
                   to_node_id: Optional[str] = None,
                   edge_type: Optional[str] = None,
                   limit: int = 100) -> list[Edge]:
        conn = self.connect()
        query = "SELECT * FROM edges WHERE 1=1"
        params: list = []
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
            (query, limit),
        ).fetchall()
        return [self._row_to_edge(r) for r in rows]

    def get_neighbors(self, node_id: str,
                      direction: str = "both") -> list[tuple[Edge, Node]]:
        conn = self.connect()
        results = []

        if direction in ("outgoing", "both"):
            rows = conn.execute(
                """SELECT e.* FROM edges e
                   WHERE e.from_node_id = ?""",
                (node_id,),
            ).fetchall()
            for row in rows:
                edge = self._row_to_edge(row)
                node = self.get_node(row["to_node_id"])
                if node:
                    results.append((edge, node))

        if direction in ("incoming", "both"):
            rows = conn.execute(
                """SELECT e.* FROM edges e
                   WHERE e.to_node_id = ?""",
                (node_id,),
            ).fetchall()
            for row in rows:
                edge = self._row_to_edge(row)
                node = self.get_node(row["from_node_id"])
                if node:
                    results.append((edge, node))

        return results

    def update_edge_claim(self, edge_id: str, claim_id: str) -> bool:
        conn = self.connect()
        try:
            conn.execute(
                "UPDATE edges SET claim_id = ? WHERE edge_id = ?",
                (claim_id, edge_id),
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
        receipt_count = conn.execute(
            "SELECT COUNT(*) FROM receipts"
        ).fetchone()[0]
        source_count = conn.execute(
            "SELECT COUNT(*) FROM sources"
        ).fetchone()[0]
        claim_count = conn.execute(
            "SELECT COUNT(*) FROM claims"
        ).fetchone()[0]

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

        edges_with_claims = conn.execute(
            "SELECT COUNT(*) FROM edges WHERE claim_id IS NOT NULL"
        ).fetchone()[0]

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
            "source_tiers": {
                f"tier_{row[0]}": row[1] for row in source_tiers
            },
            "edges_with_claims": edges_with_claims,
            "evidence_coverage": (
                edges_with_claims / edge_count if edge_count > 0 else 0
            ),
            "tier_01_claims": tier_01_claims,
        }

    def get_evidence_status(self) -> dict:
        conn = self.connect()
        total_claims = conn.execute(
            "SELECT COUNT(*) FROM claims"
        ).fetchone()[0]
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
        total_edges = conn.execute(
            "SELECT COUNT(*) FROM edges"
        ).fetchone()[0]
        edges_with_claims = conn.execute(
            "SELECT COUNT(*) FROM edges WHERE claim_id IS NOT NULL"
        ).fetchone()[0]

        return {
            "total_claims": total_claims,
            "verified": verified,
            "evidenced": evidenced,
            "partial": partial,
            "missing": missing,
            "total_edges": total_edges,
            "edges_with_claims": edges_with_claims,
            "orphan_edges": total_edges - edges_with_claims,
            "evidence_coverage_pct": (
                edges_with_claims / total_edges * 100
                if total_edges > 0 else 0
            ),
        }
