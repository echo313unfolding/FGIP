"""
FGIP Query Functions - Graph analysis and causality tracing.

All queries return evidence quality metrics.
"""

import sqlite3
from collections import deque
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set


@dataclass
class PathResult:
    """Result of a causality trace."""
    hops: int
    evidence_score: float  # Percentage of edges with Tier 0/1 sources
    path: List[Dict]  # List of edge details
    weakest_link: Optional[Dict] = None


@dataclass
class ClaimStatus:
    """Summary of a claim's evidence status."""
    claim_id: str
    claim_text: str
    topic: str
    status: str
    required_tier: int
    sources: List[Dict]
    best_tier: Optional[int]


def trace_causality(
    conn: sqlite3.Connection,
    start_node: str,
    end_node: str,
    max_depth: int = 10,
) -> List[PathResult]:
    """
    Find all paths between two nodes with evidence quality scoring.

    Returns list of PathResult sorted by evidence score (highest first).
    """
    cursor = conn.cursor()

    # Normalize node IDs (try both as-is and slugified)
    start = normalize_node_id(cursor, start_node)
    end = normalize_node_id(cursor, end_node)

    if not start or not end:
        return []

    # BFS to find all paths
    paths = []
    queue = deque([(start, [start], [])])  # (current, node_path, edge_ids)
    visited_paths = set()

    while queue:
        current, node_path, edge_ids = queue.popleft()

        if len(node_path) > max_depth + 1:
            continue

        # Get outgoing edges
        cursor.execute("""
            SELECT e.edge_id, e.to_node, e.relationship, e.detail, e.claim_id,
                   e.confidence, c.status, c.claim_text
            FROM edges e
            LEFT JOIN claims c ON e.claim_id = c.claim_id
            WHERE e.from_node = ?
        """, (current,))

        for row in cursor.fetchall():
            next_node = row['to_node']
            edge_id = row['edge_id']

            # Avoid cycles
            if next_node in node_path:
                continue

            new_node_path = node_path + [next_node]
            new_edge_ids = edge_ids + [edge_id]

            # Path signature
            path_sig = tuple(new_edge_ids)
            if path_sig in visited_paths:
                continue
            visited_paths.add(path_sig)

            if next_node == end:
                # Found a path - compute evidence score
                path_result = compute_path_evidence(cursor, new_edge_ids)
                paths.append(path_result)
            else:
                queue.append((next_node, new_node_path, new_edge_ids))

    # Sort by evidence score
    paths.sort(key=lambda p: p.evidence_score, reverse=True)
    return paths


def compute_path_evidence(cursor: sqlite3.Cursor, edge_ids: List[int]) -> PathResult:
    """Compute evidence quality for a path."""
    path_details = []
    tier_01_count = 0
    total_count = len(edge_ids)
    weakest = None
    weakest_tier = -1

    for edge_id in edge_ids:
        cursor.execute("""
            SELECT e.edge_id, e.from_node, e.to_node, e.relationship, e.detail,
                   e.claim_id, e.confidence, c.status, c.claim_text,
                   fn.name as from_name, tn.name as to_name
            FROM edges e
            LEFT JOIN claims c ON e.claim_id = c.claim_id
            LEFT JOIN nodes fn ON e.from_node = fn.node_id
            LEFT JOIN nodes tn ON e.to_node = tn.node_id
            WHERE e.edge_id = ?
        """, (edge_id,))
        edge = dict(cursor.fetchone())

        # Get best source tier for this edge's claim
        if edge['claim_id']:
            cursor.execute("""
                SELECT MIN(s.tier) as best_tier
                FROM claim_sources cs
                JOIN sources s ON cs.source_id = s.source_id
                WHERE cs.claim_id = ?
            """, (edge['claim_id'],))
            tier_row = cursor.fetchone()
            best_tier = tier_row['best_tier'] if tier_row else None
        else:
            best_tier = None

        edge['best_tier'] = best_tier

        if best_tier is not None and best_tier <= 1:
            tier_01_count += 1

        # Track weakest link
        if best_tier is None or best_tier > weakest_tier:
            weakest_tier = best_tier if best_tier is not None else 999
            weakest = edge

        path_details.append(edge)

    evidence_score = (tier_01_count / total_count * 100) if total_count > 0 else 0

    return PathResult(
        hops=total_count,
        evidence_score=evidence_score,
        path=path_details,
        weakest_link=weakest,
    )


def ownership_loop(conn: sqlite3.Connection, entity: str) -> Optional[List[Dict]]:
    """
    Detect ownership cycles involving an entity.

    Returns the cycle path if found, None otherwise.
    """
    cursor = conn.cursor()
    start = normalize_node_id(cursor, entity)

    if not start:
        return None

    ownership_rels = ['OWNS_SHARES', 'INVESTED_IN', 'MEMBER_OF', 'CONTROLS']

    # DFS for cycle detection
    visited = set()
    path = []

    def dfs(node: str) -> Optional[List[str]]:
        if node in visited:
            # Found cycle
            try:
                cycle_start = path.index(node)
                return path[cycle_start:] + [node]
            except ValueError:
                return None

        visited.add(node)
        path.append(node)

        # Get outgoing ownership edges
        placeholders = ','.join('?' * len(ownership_rels))
        cursor.execute(f"""
            SELECT e.to_node, e.relationship, e.detail, e.claim_id, n.name
            FROM edges e
            JOIN nodes n ON e.to_node = n.node_id
            WHERE e.from_node = ? AND e.relationship IN ({placeholders})
        """, [node] + ownership_rels)

        for row in cursor.fetchall():
            result = dfs(row['to_node'])
            if result:
                return result

        path.pop()
        return None

    cycle = dfs(start)
    if not cycle:
        return None

    # Build detailed cycle info
    result = []
    for i in range(len(cycle) - 1):
        from_node = cycle[i]
        to_node = cycle[i + 1]

        cursor.execute("""
            SELECT e.*, fn.name as from_name, tn.name as to_name
            FROM edges e
            JOIN nodes fn ON e.from_node = fn.node_id
            JOIN nodes tn ON e.to_node = tn.node_id
            WHERE e.from_node = ? AND e.to_node = ?
        """, (from_node, to_node))
        edge = cursor.fetchone()
        if edge:
            result.append(dict(edge))

    return result


def contradiction_check(conn: sqlite3.Connection, entity: str) -> List[Dict]:
    """
    Find contradictions involving an entity.

    Example: Filed anti-tariff amicus BUT announced reshoring.
    """
    cursor = conn.cursor()
    node_id = normalize_node_id(cursor, entity)

    if not node_id:
        return []

    contradictions = []

    # Get all edges involving this entity
    cursor.execute("""
        SELECT e.*, c.claim_text, c.topic,
               fn.name as from_name, tn.name as to_name
        FROM edges e
        LEFT JOIN claims c ON e.claim_id = c.claim_id
        LEFT JOIN nodes fn ON e.from_node = fn.node_id
        LEFT JOIN nodes tn ON e.to_node = tn.node_id
        WHERE e.from_node = ? OR e.to_node = ?
        ORDER BY e.created_at
    """, (node_id, node_id))

    edges = [dict(row) for row in cursor.fetchall()]

    # Check for contradiction patterns
    anti_tariff_briefs = [e for e in edges if e['relationship'] == 'FILED_AMICUS'
                         and 'tariff' in (e.get('claim_text') or '').lower()
                         and 'against' in (e.get('claim_text') or '').lower()]

    reshoring = [e for e in edges if e['relationship'] in ['INVESTED_IN', 'ANNOUNCED', 'BUILT']
                 and any(w in (e.get('claim_text') or '').lower()
                         for w in ['domestic', 'reshoring', 'factory', 'manufacturing', 'jobs'])]

    if anti_tariff_briefs and reshoring:
        contradictions.append({
            'type': 'AMICUS_VS_RESHORING',
            'description': f"Entity filed anti-tariff amicus briefs but also announced reshoring investments",
            'anti_tariff': anti_tariff_briefs,
            'reshoring': reshoring,
        })

    # Check for lobbying against correction while benefiting
    lobbied_against = [e for e in edges if e['relationship'] == 'LOBBIED_AGAINST']
    correction_benefit = [e for e in edges if e.get('topic') == 'Reshoring']

    if lobbied_against and correction_benefit:
        contradictions.append({
            'type': 'LOBBYING_VS_BENEFIT',
            'description': f"Entity lobbied against correction while benefiting from it",
            'lobbying': lobbied_against,
            'benefit': correction_benefit,
        })

    return contradictions


def correction_score(conn: sqlite3.Connection, company: str) -> Dict:
    """
    Score how directly a company benefits from the reshoring correction.

    Based on:
    - Direct reshoring edges (investments, jobs, factories)
    - Position in supply chain
    - Counter-position (amicus against correction)
    """
    cursor = conn.cursor()
    node_id = normalize_node_id(cursor, company)

    if not node_id:
        return {'error': f"Company not found: {company}"}

    # Get all edges
    cursor.execute("""
        SELECT e.*, c.claim_text, c.topic, c.status,
               fn.name as from_name, tn.name as to_name
        FROM edges e
        LEFT JOIN claims c ON e.claim_id = c.claim_id
        LEFT JOIN nodes fn ON e.from_node = fn.node_id
        LEFT JOIN nodes tn ON e.to_node = tn.node_id
        WHERE e.from_node = ? OR e.to_node = ?
    """, (node_id, node_id))

    edges = [dict(row) for row in cursor.fetchall()]

    # Score components
    reshoring_direct = 0
    supply_chain = 0
    counter_position = 0

    for edge in edges:
        topic = edge.get('topic', '')
        rel = edge.get('relationship', '')
        claim = (edge.get('claim_text') or '').lower()

        # Direct reshoring benefit
        if topic == 'Reshoring':
            reshoring_direct += 2

        # Supply chain position
        if rel in ['SUPPLIES', 'INVESTED_IN'] and edge['from_node'] == node_id:
            supply_chain += 1

        # Counter-position (negative)
        if rel == 'FILED_AMICUS' and 'against' in claim and 'tariff' in claim:
            counter_position -= 3
        if rel == 'LOBBIED_AGAINST':
            counter_position -= 2

    total_score = reshoring_direct + supply_chain + counter_position

    # Get company info
    cursor.execute("SELECT * FROM nodes WHERE node_id = ?", (node_id,))
    node = dict(cursor.fetchone())

    return {
        'company': node['name'],
        'node_id': node_id,
        'total_score': total_score,
        'components': {
            'reshoring_direct': reshoring_direct,
            'supply_chain': supply_chain,
            'counter_position': counter_position,
        },
        'edge_count': len(edges),
        'edges': edges,
    }


def normalize_node_id(cursor: sqlite3.Cursor, query: str) -> Optional[str]:
    """
    Find a node by ID or name (fuzzy match).
    """
    # Try exact node_id match
    cursor.execute("SELECT node_id FROM nodes WHERE node_id = ?", (query,))
    row = cursor.fetchone()
    if row:
        return row['node_id']

    # Try slugified version
    slug = slugify(query)
    cursor.execute("SELECT node_id FROM nodes WHERE node_id = ?", (slug,))
    row = cursor.fetchone()
    if row:
        return row['node_id']

    # Try name match (case-insensitive)
    cursor.execute("SELECT node_id FROM nodes WHERE LOWER(name) = LOWER(?)", (query,))
    row = cursor.fetchone()
    if row:
        return row['node_id']

    # Try partial name match
    cursor.execute("SELECT node_id FROM nodes WHERE LOWER(name) LIKE LOWER(?)", (f'%{query}%',))
    row = cursor.fetchone()
    if row:
        return row['node_id']

    return None


def slugify(name: str) -> str:
    """Convert name to node_id slug."""
    import re
    slug = name.lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug


def get_claim_status(conn: sqlite3.Connection, claim_id: str) -> Optional[ClaimStatus]:
    """Get full status of a claim including all sources."""
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM claims WHERE claim_id = ?
    """, (claim_id,))
    claim = cursor.fetchone()

    if not claim:
        return None

    # Get sources
    cursor.execute("""
        SELECT s.* FROM sources s
        JOIN claim_sources cs ON s.source_id = cs.source_id
        WHERE cs.claim_id = ?
    """, (claim_id,))
    sources = [dict(row) for row in cursor.fetchall()]

    # Best tier
    best_tier = min((s['tier'] for s in sources), default=None)

    return ClaimStatus(
        claim_id=claim['claim_id'],
        claim_text=claim['claim_text'],
        topic=claim['topic'],
        status=claim['status'],
        required_tier=claim['required_tier'],
        sources=sources,
        best_tier=best_tier,
    )


def get_status_summary(conn: sqlite3.Connection) -> Dict:
    """Get overall database status summary."""
    cursor = conn.cursor()

    # Claim counts by status
    cursor.execute("""
        SELECT status, COUNT(*) as count FROM claims GROUP BY status
    """)
    claims_by_status = {row['status']: row['count'] for row in cursor.fetchall()}

    # Total claims
    total_claims = sum(claims_by_status.values())

    # Edge coverage (edges with Tier 0/1 sources)
    cursor.execute("""
        SELECT COUNT(DISTINCT e.edge_id) as count
        FROM edges e
        JOIN claims c ON e.claim_id = c.claim_id
        JOIN claim_sources cs ON c.claim_id = cs.claim_id
        JOIN sources s ON cs.source_id = s.source_id
        WHERE s.tier <= 1
    """)
    edges_with_tier01 = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(*) as count FROM edges")
    total_edges = cursor.fetchone()['count']

    coverage = (edges_with_tier01 / total_edges * 100) if total_edges > 0 else 0

    return {
        'total_claims': total_claims,
        'claims_by_status': claims_by_status,
        'total_edges': total_edges,
        'edges_with_tier01': edges_with_tier01,
        'evidence_coverage': round(coverage, 1),
    }
