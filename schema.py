"""
FGIP Schema - Claims-first knowledge graph.

Build order:
1. sources (every URL gets an entry)
2. claims (every factual claim gets an entry)
3. claim_sources (many-to-many)
4. nodes (entities extracted from claims)
5. edges (relationships, each must reference a claim_id)
"""

import hashlib
import sqlite3
from urllib.parse import urlparse

SCHEMA_SQL = """
-- Every source URL gets an entry
CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY,        -- sha256(url)
    url TEXT NOT NULL UNIQUE,
    domain TEXT,                        -- extracted from URL
    tier INTEGER DEFAULT 2,             -- 0=primary doc, 1=journalism citing primary, 2=commentary/blog/wiki
    retrieved_at TEXT,                  -- when we first found it
    artifact_path TEXT DEFAULT NULL,    -- local PDF/HTML snapshot path (null until captured)
    artifact_hash TEXT DEFAULT NULL,    -- sha256 of saved file (null until captured)
    notes TEXT DEFAULT NULL
);

-- Every factual claim gets an entry
CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY,          -- FGIP-000001, FGIP-000002, etc.
    claim_text TEXT NOT NULL,           -- the actual claim
    topic TEXT NOT NULL,                -- Lobbying, Judicial, Ownership, Downstream, Censorship, Reshoring, etc.
    status TEXT DEFAULT 'PARTIAL',      -- MISSING, PARTIAL, EVIDENCED, VERIFIED
    required_tier INTEGER DEFAULT 1,    -- what tier is needed to consider this verified
    created_at TEXT DEFAULT (datetime('now')),
    notes TEXT DEFAULT NULL
);

-- Many-to-many: which sources support which claims
CREATE TABLE IF NOT EXISTS claim_sources (
    claim_id TEXT REFERENCES claims(claim_id),
    source_id TEXT REFERENCES sources(source_id),
    PRIMARY KEY (claim_id, source_id)
);

-- Nodes: entities in the graph
CREATE TABLE IF NOT EXISTS nodes (
    node_id TEXT PRIMARY KEY,           -- slugified name: "us-chamber-of-commerce"
    name TEXT NOT NULL,                 -- "US Chamber of Commerce"
    node_type TEXT NOT NULL,            -- ORGANIZATION, PERSON, LEGISLATION, COURT_CASE, COMPANY, etc.
    metadata TEXT DEFAULT NULL,         -- JSON blob for extra fields
    created_at TEXT DEFAULT (datetime('now'))
);

-- Edges: relationships (EVERY edge must reference a claim_id)
CREATE TABLE IF NOT EXISTS edges (
    edge_id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_node TEXT REFERENCES nodes(node_id),
    to_node TEXT REFERENCES nodes(node_id),
    relationship TEXT NOT NULL,         -- LOBBIED_FOR, OWNS_SHARES, FILED_AMICUS, etc.
    detail TEXT DEFAULT NULL,           -- "42.8% (87.9M shares, 2018)"
    claim_id TEXT REFERENCES claims(claim_id),  -- which claim supports this edge
    date_occurred TEXT DEFAULT NULL,
    confidence TEXT DEFAULT 'medium',   -- high, medium, low
    created_at TEXT DEFAULT (datetime('now'))
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_claims_topic ON claims(topic);
CREATE INDEX IF NOT EXISTS idx_claims_status ON claims(status);
CREATE INDEX IF NOT EXISTS idx_sources_domain ON sources(domain);
CREATE INDEX IF NOT EXISTS idx_sources_tier ON sources(tier);
CREATE INDEX IF NOT EXISTS idx_edges_from ON edges(from_node);
CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_node);
CREATE INDEX IF NOT EXISTS idx_edges_claim ON edges(claim_id);
CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(node_type);

-- Metadata table
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);
"""

# Tier 0: Primary government/legal documents
TIER_0_DOMAINS = [
    'congress.gov', 'house.gov', 'senate.gov', 'whitehouse.gov',
    'gao.gov', 'sec.gov', 'supremecourt.gov', 'justia.com',
    'federalreserve.gov', 'treasury.gov', 'state.gov', 'commerce.gov',
    'ncua.gov', 'archives.gov', 'govtrack.us', 'crsreports.congress.gov',
    'hhs.gov', 'bis.org', 'efile.fara.gov'
]

# Tier 1: Quality journalism / academic
TIER_1_DOMAINS = [
    'reuters.com', 'npr.org', 'propublica.org', 'opensecrets.org',
    'theintercept.com', 'scotusblog.com', 'cnn.com', 'washingtonpost.com',
    'nytimes.com', 'bbc.co.uk', 'apnews.com', 'fortune.com',
    'influencewatch.org', 'brookings.edu', 'cfr.org', 'rand.org',
    'aei.org', 'harvard.edu', 'columbia.edu', 'unc.edu',
    'ucdavis.edu', 'doi.org', 'academic.oup.com', 'economics.ucdavis.edu'
]


def get_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # Remove www. prefix
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain
    except:
        return ''


def get_tier(url: str) -> int:
    """Auto-assign tier based on domain."""
    domain = get_domain(url)

    # Check Tier 0
    for t0 in TIER_0_DOMAINS:
        if t0 in domain:
            return 0

    # Check Tier 1
    for t1 in TIER_1_DOMAINS:
        if t1 in domain:
            return 1

    # Default to Tier 2
    return 2


def source_id_from_url(url: str) -> str:
    """Generate source_id as sha256 of URL."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def init_db(db_path: str) -> sqlite3.Connection:
    """Initialize the database with schema."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)

    # Set metadata
    conn.execute("""
        INSERT OR REPLACE INTO meta (key, value, updated_at)
        VALUES ('schema_version', '1.0.0', datetime('now'))
    """)
    conn.commit()

    return conn
