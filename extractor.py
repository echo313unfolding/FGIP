"""
FGIP Entity Extractor - Build nodes and edges from claims.

Step 4 & 5 in the build order:
- Extract unique entities from claims
- Create edges referencing claim_ids
"""

import re
import json
import sqlite3
from typing import List, Dict, Tuple, Optional


# Known entities with their types (seed data)
KNOWN_ENTITIES = {
    # Organizations
    'US Chamber of Commerce': ('ORGANIZATION', 'us-chamber-of-commerce'),
    'Chamber of Commerce': ('ORGANIZATION', 'us-chamber-of-commerce'),
    'BlackRock': ('ORGANIZATION', 'blackrock'),
    'Vanguard': ('ORGANIZATION', 'vanguard'),
    'State Street': ('ORGANIZATION', 'state-street'),
    'Heritage Foundation': ('ORGANIZATION', 'heritage-foundation'),
    'Cato Institute': ('ORGANIZATION', 'cato-institute'),
    'Federalist Society': ('ORGANIZATION', 'federalist-society'),
    'Business Roundtable': ('ORGANIZATION', 'business-roundtable'),
    'OpenSecrets': ('ORGANIZATION', 'opensecrets'),
    'ProPublica': ('ORGANIZATION', 'propublica'),

    # Financial institutions
    'NY Fed': ('FINANCIAL_INST', 'ny-fed'),
    'New York Fed': ('FINANCIAL_INST', 'ny-fed'),
    'Federal Reserve': ('FINANCIAL_INST', 'federal-reserve'),
    'BIS': ('FINANCIAL_INST', 'bis'),
    'Bank for International Settlements': ('FINANCIAL_INST', 'bis'),
    'Citibank': ('FINANCIAL_INST', 'citibank'),
    'JPMorgan': ('FINANCIAL_INST', 'jpmorgan'),
    'JPMorgan Chase': ('FINANCIAL_INST', 'jpmorgan'),
    'Goldman Sachs': ('FINANCIAL_INST', 'goldman-sachs'),
    'HSBC': ('FINANCIAL_INST', 'hsbc'),
    'HSBC Bank USA': ('FINANCIAL_INST', 'hsbc'),
    'Deutsche Bank': ('FINANCIAL_INST', 'deutsche-bank'),
    'Bank of NY Mellon': ('FINANCIAL_INST', 'bank-of-ny-mellon'),

    # People
    'Ginni Thomas': ('PERSON', 'ginni-thomas'),
    'Virginia Lamp': ('PERSON', 'ginni-thomas'),
    'Clarence Thomas': ('PERSON', 'clarence-thomas'),
    'Harlan Crow': ('PERSON', 'harlan-crow'),
    'Larry Fink': ('PERSON', 'larry-fink'),
    'Bill Archer': ('PERSON', 'bill-archer'),
    'Frances Haugen': ('PERSON', 'frances-haugen'),
    'Marco Rubio': ('PERSON', 'marco-rubio'),
    'John Danforth': ('PERSON', 'john-danforth'),

    # Legislation
    'PNTR': ('LEGISLATION', 'pntr-2000'),
    'Permanent Normal Trade Relations': ('LEGISLATION', 'pntr-2000'),
    'H.R. 4444': ('LEGISLATION', 'pntr-2000'),
    'CHIPS Act': ('LEGISLATION', 'chips-act'),
    'OBBBA': ('LEGISLATION', 'obbba'),
    'GENIUS Act': ('LEGISLATION', 'genius-act'),
    'Anti-CBDC Act': ('LEGISLATION', 'anti-cbdc-act'),

    # Court cases
    'Learning Resources v. Trump': ('COURT_CASE', 'learning-resources-v-trump'),
    'V.O.S. Selections v. Trump': ('COURT_CASE', 'vos-selections-v-trump'),
    'Citizens United': ('COURT_CASE', 'citizens-united'),

    # Companies
    'Caterpillar': ('COMPANY', 'caterpillar'),
    'Intel': ('COMPANY', 'intel'),
    'Nucor': ('COMPANY', 'nucor'),
    'Eaton': ('COMPANY', 'eaton'),
    'Constellation Energy': ('COMPANY', 'constellation-energy'),
    'Freeport-McMoRan': ('COMPANY', 'freeport-mcmoran'),
    'GE Aerospace': ('COMPANY', 'ge-aerospace'),
    'Oracle': ('COMPANY', 'oracle'),
    'Whirlpool': ('COMPANY', 'whirlpool'),
    'MP Materials': ('COMPANY', 'mp-materials'),
    'Cleveland-Cliffs': ('COMPANY', 'cleveland-cliffs'),
    'US Steel': ('COMPANY', 'us-steel'),
    'Gannett': ('COMPANY', 'gannett'),
    'Sinclair': ('COMPANY', 'sinclair'),
    'Graham Media': ('COMPANY', 'graham-media'),
    'Bloomberg': ('COMPANY', 'bloomberg'),
    'Anduril': ('COMPANY', 'anduril'),

    # Economic events
    'China Shock': ('ECONOMIC_EVENT', 'china-shock'),
    'Great Rotation': ('ECONOMIC_EVENT', 'great-rotation-2026'),
    'Reshoring': ('ECONOMIC_EVENT', 'reshoring-2025'),

    # Media
    'Facebook': ('MEDIA_OUTLET', 'facebook'),
    'Twitter': ('MEDIA_OUTLET', 'twitter'),

    # Government bodies
    'Supreme Court': ('ORGANIZATION', 'supreme-court'),
    'House Select Committee on CCP': ('ORGANIZATION', 'house-ccp-committee'),
    'CISA': ('ORGANIZATION', 'cisa'),
    'DHS': ('ORGANIZATION', 'dhs'),
}

# Relationship patterns to extract from claims
RELATIONSHIP_PATTERNS = [
    (r'(\w+)\s+owns?\s+([\d.]+%)', 'OWNS_SHARES', lambda m: m.group(2)),
    (r'(\w+)\s+lobbied\s+for', 'LOBBIED_FOR', None),
    (r'(\w+)\s+lobbied\s+against', 'LOBBIED_AGAINST', None),
    (r'(\w+)\s+filed\s+amicus', 'FILED_AMICUS', None),
    (r'(\w+)\s+married\s+to', 'MARRIED_TO', None),
    (r'(\w+)\s+donated\s+to', 'DONATED_TO', None),
    (r'(\w+)\s+employs?', 'EMPLOYS', None),
    (r'(\w+)\s+ruled\s+on', 'RULED_ON', None),
    (r'(\w+)\s+passed', 'ENACTED', None),
    (r'(\w+)\s+caused', 'CAUSED', None),
    (r'(\w+)\s+invested\s+in', 'INVESTED_IN', None),
]


def slugify(name: str) -> str:
    """Convert name to node_id slug."""
    slug = name.lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug


def extract_entities(conn: sqlite3.Connection) -> int:
    """
    Extract entities from claims and create nodes.

    Returns number of nodes created.
    """
    cursor = conn.cursor()
    nodes_created = 0

    # Get all claims
    cursor.execute("SELECT claim_id, claim_text, topic FROM claims")
    claims = cursor.fetchall()

    # First pass: add all known entities
    for name, (node_type, node_id) in KNOWN_ENTITIES.items():
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO nodes (node_id, name, node_type)
                VALUES (?, ?, ?)
            """, (node_id, name, node_type))
            if cursor.rowcount > 0:
                nodes_created += 1
        except sqlite3.IntegrityError:
            pass

    # Second pass: find entities mentioned in claims
    for claim in claims:
        claim_text = claim['claim_text']

        for name, (node_type, node_id) in KNOWN_ENTITIES.items():
            if name.lower() in claim_text.lower():
                # Entity mentioned - ensure it exists
                cursor.execute("""
                    INSERT OR IGNORE INTO nodes (node_id, name, node_type)
                    VALUES (?, ?, ?)
                """, (node_id, name, node_type))
                if cursor.rowcount > 0:
                    nodes_created += 1

    conn.commit()
    return nodes_created


def extract_edges_from_seed_data(conn: sqlite3.Connection) -> int:
    """
    Create edges from the known seed data relationships.

    Each edge references a claim_id from the claims table.
    """
    cursor = conn.cursor()
    edges_created = 0

    # Seed edges - these are the relationships from the spec
    seed_edges = [
        # Ownership Layer - Fed
        ('citibank', 'ny-fed', 'OWNS_SHARES', '42.8% (87.9M shares, 2018)', 'Ownership'),
        ('jpmorgan', 'ny-fed', 'OWNS_SHARES', '29.5% (60.6M shares)', 'Ownership'),
        ('goldman-sachs', 'ny-fed', 'OWNS_SHARES', '4.0% (8.3M shares)', 'Ownership'),
        ('hsbc', 'ny-fed', 'OWNS_SHARES', '6.1% (12.6M shares)', 'Ownership'),
        ('deutsche-bank', 'ny-fed', 'OWNS_SHARES', '0.87% combined', 'Ownership'),
        ('bank-of-ny-mellon', 'ny-fed', 'OWNS_SHARES', '3.5% (7.2M shares)', 'Ownership'),

        # Ownership Layer - Cross-holdings
        ('vanguard', 'jpmorgan', 'OWNS_SHARES', '9.84% (270.7M shares)', 'Ownership'),
        ('blackrock', 'jpmorgan', 'OWNS_SHARES', '4.82% (132.6M shares)', 'Ownership'),
        ('state-street', 'jpmorgan', 'OWNS_SHARES', '4.56% (125.3M shares)', 'Ownership'),
        ('vanguard', 'blackrock', 'OWNS_SHARES', '~9.04% (13.9M shares)', 'Ownership'),

        # Lobbying Layer
        ('us-chamber-of-commerce', 'pntr-2000', 'LOBBIED_FOR', '$1.8B+ total lobbying', 'Lobbying'),

        # Judicial Pipeline
        ('ginni-thomas', 'clarence-thomas', 'MARRIED_TO', None, 'Judicial'),
        ('harlan-crow', 'clarence-thomas', 'DONATED_TO', 'Undisclosed financial benefits', 'Judicial'),
        ('harlan-crow', 'heritage-foundation', 'DONATED_TO', None, 'Judicial'),

        # Court cases
        ('us-chamber-of-commerce', 'learning-resources-v-trump', 'FILED_AMICUS', 'Against tariffs', 'Judicial'),
    ]

    for from_node, to_node, relationship, detail, topic in seed_edges:
        # Find a matching claim
        cursor.execute("""
            SELECT claim_id FROM claims
            WHERE topic = ?
            AND (
                LOWER(claim_text) LIKE LOWER(?)
                OR LOWER(claim_text) LIKE LOWER(?)
            )
            LIMIT 1
        """, (topic, f'%{from_node.replace("-", " ")}%', f'%{to_node.replace("-", " ")}%'))

        row = cursor.fetchone()
        claim_id = row['claim_id'] if row else None

        # If no matching claim, create a placeholder
        if not claim_id:
            cursor.execute("SELECT MAX(CAST(SUBSTR(claim_id, 6) AS INTEGER)) FROM claims")
            max_num = cursor.fetchone()[0] or 0
            claim_id = f"FGIP-{max_num + 1:06d}"

            claim_text = f"{from_node} {relationship} {to_node}"
            if detail:
                claim_text += f" ({detail})"

            cursor.execute("""
                INSERT INTO claims (claim_id, claim_text, topic, status, required_tier)
                VALUES (?, ?, ?, 'MISSING', 0)
            """, (claim_id, claim_text, topic))

        # Create edge
        try:
            cursor.execute("""
                INSERT INTO edges (from_node, to_node, relationship, detail, claim_id, confidence)
                VALUES (?, ?, ?, ?, ?, 'high')
            """, (from_node, to_node, relationship, detail, claim_id))
            edges_created += 1
        except sqlite3.IntegrityError:
            pass

    conn.commit()
    return edges_created


def build_graph(conn: sqlite3.Connection) -> Dict:
    """
    Build the full graph from claims.

    Returns summary of nodes and edges created.
    """
    print("Extracting entities...")
    nodes = extract_entities(conn)
    print(f"  Created {nodes} nodes")

    print("Creating edges from seed data...")
    edges = extract_edges_from_seed_data(conn)
    print(f"  Created {edges} edges")

    # Get stats
    cursor = conn.cursor()

    cursor.execute("SELECT node_type, COUNT(*) FROM nodes GROUP BY node_type")
    nodes_by_type = dict(cursor.fetchall())

    cursor.execute("SELECT relationship, COUNT(*) FROM edges GROUP BY relationship")
    edges_by_rel = dict(cursor.fetchall())

    return {
        'nodes_created': nodes,
        'edges_created': edges,
        'nodes_by_type': nodes_by_type,
        'edges_by_relationship': edges_by_rel,
    }


def add_node(
    conn: sqlite3.Connection,
    name: str,
    node_type: str,
    node_id: Optional[str] = None,
    metadata: Optional[Dict] = None,
) -> str:
    """Add a new node to the graph."""
    if node_id is None:
        node_id = slugify(name)

    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO nodes (node_id, name, node_type, metadata)
        VALUES (?, ?, ?, ?)
    """, (node_id, name, node_type, json.dumps(metadata) if metadata else None))
    conn.commit()

    return node_id


def add_edge(
    conn: sqlite3.Connection,
    from_node: str,
    to_node: str,
    relationship: str,
    claim_id: str,
    detail: Optional[str] = None,
    date_occurred: Optional[str] = None,
    confidence: str = 'medium',
) -> int:
    """
    Add a new edge to the graph.

    EVERY edge must reference a claim_id.
    """
    cursor = conn.cursor()

    # Verify claim exists
    cursor.execute("SELECT claim_id FROM claims WHERE claim_id = ?", (claim_id,))
    if not cursor.fetchone():
        raise ValueError(f"Claim not found: {claim_id}")

    # Verify nodes exist
    cursor.execute("SELECT node_id FROM nodes WHERE node_id = ?", (from_node,))
    if not cursor.fetchone():
        raise ValueError(f"From node not found: {from_node}")

    cursor.execute("SELECT node_id FROM nodes WHERE node_id = ?", (to_node,))
    if not cursor.fetchone():
        raise ValueError(f"To node not found: {to_node}")

    cursor.execute("""
        INSERT INTO edges (from_node, to_node, relationship, detail, claim_id, date_occurred, confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (from_node, to_node, relationship, detail, claim_id, date_occurred, confidence))
    conn.commit()

    return cursor.lastrowid


def add_claim(
    conn: sqlite3.Connection,
    claim_text: str,
    topic: str,
    source_url: Optional[str] = None,
    required_tier: int = 1,
) -> str:
    """Add a new claim with optional source URL."""
    from schema import source_id_from_url, get_domain, get_tier

    cursor = conn.cursor()

    # Generate claim_id
    cursor.execute("SELECT MAX(CAST(SUBSTR(claim_id, 6) AS INTEGER)) FROM claims")
    max_num = cursor.fetchone()[0] or 0
    claim_id = f"FGIP-{max_num + 1:06d}"

    # Determine status
    status = 'PARTIAL' if source_url else 'MISSING'

    cursor.execute("""
        INSERT INTO claims (claim_id, claim_text, topic, status, required_tier)
        VALUES (?, ?, ?, ?, ?)
    """, (claim_id, claim_text, topic, status, required_tier))

    # Add source if provided
    if source_url:
        source_id = source_id_from_url(source_url)
        cursor.execute("""
            INSERT OR IGNORE INTO sources (source_id, url, domain, tier, retrieved_at)
            VALUES (?, ?, ?, ?, datetime('now'))
        """, (source_id, source_url, get_domain(source_url), get_tier(source_url)))

        cursor.execute("""
            INSERT OR IGNORE INTO claim_sources (claim_id, source_id)
            VALUES (?, ?)
        """, (claim_id, source_id))

    conn.commit()
    return claim_id
