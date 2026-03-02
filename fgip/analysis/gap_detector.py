"""FGIP Gap Detector - Analyzes graph for missing edges and suggests agent targets.

The Gap Detector is a meta-analysis tool that:
1. Identifies nodes without expected relationship types
2. Detects missing edges based on entity type expectations
3. Suggests prioritized agent runs to fill gaps
4. Tracks gap fill rate over time

Usage:
    from fgip.analysis.gap_detector import GapDetector

    detector = GapDetector(db)
    gaps = detector.detect_all_gaps()
    suggestions = detector.suggest_agent_runs()
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
import json


@dataclass
class Gap:
    """A detected gap in the knowledge graph."""
    gap_type: str  # missing_ownership, missing_lobbying, missing_rulemaking, etc.
    node_id: str
    node_name: str
    node_type: str
    expected_edge_type: str
    description: str
    priority: int = 5  # 1-10, higher = more important
    suggested_agent: Optional[str] = None


@dataclass
class AgentSuggestion:
    """A suggested agent run to fill gaps."""
    agent: str
    targets: List[str]  # Entity names or node IDs
    reason: str
    gap_count: int
    priority: int


@dataclass
class AgentRequest:
    """A structured request for a new agent capability."""
    request_id: str
    gap_type: str           # "missing_source", "unmonitored_entity", "new_data_type"
    description: str        # Human-readable description
    target_entities: List[str]  # Which nodes would benefit
    suggested_api: str      # What API/source would fill it
    priority: int           # 1-5 based on impact
    estimated_edges: int    # How many new edges this agent could produce
    gap_ids: List[str] = field(default_factory=list)  # Gaps this would address


@dataclass
class GapReport:
    """Complete gap analysis report."""
    timestamp: str
    total_nodes: int
    total_edges: int
    gaps: List[Gap]
    suggestions: List[AgentSuggestion]
    gap_by_type: Dict[str, int]
    coverage_stats: Dict[str, float]


class GapDetector:
    """Analyzes knowledge graph for missing edges and data gaps.

    The detector applies heuristics based on node types:
    - COMPANY nodes should have OWNS_SHARES edges (from 13F filers)
    - ORGANIZATION nodes with lobbying claims should have LOBBIED_FOR edges
    - LEGISLATION nodes should have RULEMAKING_FOR or IMPLEMENTED_BY edges
    - PERSON nodes in gov roles should have EMPLOYED edges

    The detector also tracks:
    - Correction layer coverage (CHIPS, GENIUS, IRA, IIJA)
    - Source tier distribution
    - Evidence completeness
    """

    # Expected edge types by node type
    NODE_TYPE_EXPECTATIONS = {
        "COMPANY": {
            "expected_edges": ["OWNS_SHARES", "SUPPLIES", "AWARDED_CONTRACT", "AWARDED_GRANT"],
            "agents": ["edgar", "usaspending"],
        },
        "ORGANIZATION": {
            "expected_edges": ["LOBBIED_FOR", "DONATED_TO", "MEMBER_OF"],
            "agents": ["opensecrets", "dark_money"],
        },
        "LEGISLATION": {
            "expected_edges": ["RULEMAKING_FOR", "IMPLEMENTED_BY", "AUTHORIZED_BY"],
            "agents": ["federal_register"],
        },
        "FINANCIAL_INST": {
            "expected_edges": ["OWNS_SHARES", "INVESTED_IN", "SITS_ON_BOARD"],
            "agents": ["edgar"],
        },
        "AGENCY": {
            "expected_edges": ["RULEMAKING_FOR", "IMPLEMENTED_BY", "RULED_ON"],
            "agents": ["federal_register", "gao"],
        },
        "PERSON": {
            "expected_edges": ["EMPLOYED", "SITS_ON_BOARD", "APPOINTED_BY"],
            "agents": ["edgar", "opensecrets"],
        },
        "ETF_FUND": {
            "expected_edges": ["OWNS_SHARES", "INVESTED_IN"],
            "agents": ["edgar"],
        },
    }

    # Correction layer programs to track
    CORRECTION_PROGRAMS = [
        "chips-act",
        "genius-act",
        "inflation-reduction-act",
        "ira",
        "iija",
        "infrastructure-investment",
    ]

    def __init__(self, db):
        """Initialize the Gap Detector.

        Args:
            db: FGIPDatabase instance
        """
        self.db = db
        self._conn = None

    @property
    def conn(self):
        """Lazy database connection."""
        if self._conn is None:
            self._conn = self.db.connect()
        return self._conn

    def detect_all_gaps(self, include_temporal: bool = True, include_reciprocal: bool = True) -> List[Gap]:
        """Detect all gaps in the knowledge graph.

        Args:
            include_temporal: Include temporal gap detection (can be slow)
            include_reciprocal: Include reciprocal edge detection

        Returns:
            List of Gap objects
        """
        gaps = []

        gaps.extend(self.detect_missing_ownership())
        gaps.extend(self.detect_missing_lobbying())
        gaps.extend(self.detect_missing_rulemakings())
        gaps.extend(self.detect_missing_awards())
        gaps.extend(self.detect_orphan_nodes())
        gaps.extend(self.detect_source_coverage_gaps())

        if include_temporal:
            gaps.extend(self.detect_temporal_gaps())
        if include_reciprocal:
            gaps.extend(self.detect_missing_reciprocals())

        return gaps

    def detect_missing_ownership(self) -> List[Gap]:
        """Find COMPANY/FINANCIAL_INST nodes without ownership edges.

        These should have OWNS_SHARES edges from institutional investors.

        Returns:
            List of Gap objects
        """
        gaps = []

        rows = self.conn.execute("""
            SELECT n.node_id, n.name, n.node_type FROM nodes n
            WHERE n.node_type IN ('COMPANY', 'FINANCIAL_INST', 'ETF_FUND')
            AND NOT EXISTS (
                SELECT 1 FROM edges e
                WHERE (e.to_node_id = n.node_id OR e.from_node_id = n.node_id)
                AND e.edge_type IN ('OWNS_SHARES', 'INVESTED_IN')
            )
        """).fetchall()

        for row in rows:
            gaps.append(Gap(
                gap_type="missing_ownership",
                node_id=row["node_id"],
                node_name=row["name"],
                node_type=row["node_type"],
                expected_edge_type="OWNS_SHARES",
                description=f"No ownership data for {row['name']}",
                priority=7 if row["node_type"] == "COMPANY" else 5,
                suggested_agent="edgar",
            ))

        return gaps

    def detect_missing_lobbying(self) -> List[Gap]:
        """Find ORGANIZATION nodes without lobbying edges.

        Organizations that appear in lobbying context should have
        LOBBIED_FOR or LOBBIED_AGAINST edges.

        Returns:
            List of Gap objects
        """
        gaps = []

        # Organizations without any lobbying edges
        rows = self.conn.execute("""
            SELECT n.node_id, n.name FROM nodes n
            WHERE n.node_type = 'ORGANIZATION'
            AND NOT EXISTS (
                SELECT 1 FROM edges e
                WHERE e.from_node_id = n.node_id
                AND e.edge_type IN ('LOBBIED_FOR', 'LOBBIED_AGAINST', 'DONATED_TO')
            )
        """).fetchall()

        for row in rows:
            gaps.append(Gap(
                gap_type="missing_lobbying",
                node_id=row["node_id"],
                node_name=row["name"],
                node_type="ORGANIZATION",
                expected_edge_type="LOBBIED_FOR",
                description=f"No lobbying data for {row['name']}",
                priority=6,
                suggested_agent="opensecrets",
            ))

        return gaps

    def detect_missing_rulemakings(self) -> List[Gap]:
        """Find LEGISLATION nodes without rulemaking implementation edges.

        Legislation should have RULEMAKING_FOR or IMPLEMENTED_BY edges
        showing which agencies are implementing them.

        Returns:
            List of Gap objects
        """
        gaps = []

        rows = self.conn.execute("""
            SELECT n.node_id, n.name FROM nodes n
            WHERE n.node_type IN ('LEGISLATION', 'PROGRAM')
            AND NOT EXISTS (
                SELECT 1 FROM edges e
                WHERE (e.from_node_id = n.node_id OR e.to_node_id = n.node_id)
                AND e.edge_type IN ('RULEMAKING_FOR', 'IMPLEMENTED_BY', 'AUTHORIZED_BY')
            )
        """).fetchall()

        for row in rows:
            # Higher priority for correction layer programs
            is_correction = any(p in row["node_id"].lower() for p in self.CORRECTION_PROGRAMS)

            gaps.append(Gap(
                gap_type="missing_rulemaking",
                node_id=row["node_id"],
                node_name=row["name"],
                node_type="LEGISLATION",
                expected_edge_type="RULEMAKING_FOR",
                description=f"No implementation data for {row['name']}",
                priority=9 if is_correction else 5,
                suggested_agent="federal_register",
            ))

        return gaps

    def detect_missing_awards(self) -> List[Gap]:
        """Find COMPANY nodes that might have federal awards but lack edges.

        Returns:
            List of Gap objects
        """
        gaps = []

        # Companies in correction layer context without award edges
        rows = self.conn.execute("""
            SELECT n.node_id, n.name FROM nodes n
            WHERE n.node_type = 'COMPANY'
            AND (
                n.metadata LIKE '%chips%'
                OR n.metadata LIKE '%semiconductor%'
                OR n.metadata LIKE '%manufacturing%'
                OR n.name LIKE '%Intel%'
                OR n.name LIKE '%TSMC%'
                OR n.name LIKE '%Samsung%'
                OR n.name LIKE '%Micron%'
            )
            AND NOT EXISTS (
                SELECT 1 FROM edges e
                WHERE e.to_node_id = n.node_id
                AND e.edge_type IN ('AWARDED_GRANT', 'AWARDED_CONTRACT', 'FUNDED_PROJECT')
            )
        """).fetchall()

        for row in rows:
            gaps.append(Gap(
                gap_type="missing_awards",
                node_id=row["node_id"],
                node_name=row["name"],
                node_type="COMPANY",
                expected_edge_type="AWARDED_GRANT",
                description=f"No federal award data for {row['name']} (potential CHIPS recipient)",
                priority=8,
                suggested_agent="usaspending",
            ))

        return gaps

    def detect_orphan_nodes(self) -> List[Gap]:
        """Find nodes with no edges at all.

        These are completely disconnected from the graph.

        Returns:
            List of Gap objects
        """
        gaps = []

        rows = self.conn.execute("""
            SELECT n.node_id, n.name, n.node_type FROM nodes n
            WHERE NOT EXISTS (
                SELECT 1 FROM edges e
                WHERE e.from_node_id = n.node_id OR e.to_node_id = n.node_id
            )
        """).fetchall()

        for row in rows:
            # Determine suggested agent based on node type
            agent = None
            expectations = self.NODE_TYPE_EXPECTATIONS.get(row["node_type"], {})
            if expectations.get("agents"):
                agent = expectations["agents"][0]

            expected_edge = "ANY"
            if expectations.get("expected_edges"):
                expected_edge = expectations["expected_edges"][0]

            gaps.append(Gap(
                gap_type="orphan_node",
                node_id=row["node_id"],
                node_name=row["name"],
                node_type=row["node_type"],
                expected_edge_type=expected_edge,
                description=f"Orphan node: {row['name']} has no edges",
                priority=3,
                suggested_agent=agent,
            ))

        return gaps

    def detect_source_coverage_gaps(self) -> List[Gap]:
        """Find nodes/edges with only Tier 2 sources (need Tier 0/1 upgrade).

        Nodes backed only by commentary (Tier 2) need authoritative sources.

        Returns:
            List of Gap objects
        """
        gaps = []

        # Find edges with only Tier 2 sources
        rows = self.conn.execute("""
            SELECT DISTINCT e.edge_id, e.edge_type, e.from_node_id, e.to_node_id,
                   n_from.name as from_name, n_to.name as to_name
            FROM edges e
            JOIN nodes n_from ON e.from_node_id = n_from.node_id
            JOIN nodes n_to ON e.to_node_id = n_to.node_id
            WHERE e.claim_id IS NOT NULL
            AND e.claim_id IN (
                SELECT DISTINCT c.claim_id
                FROM claims c
                JOIN claim_sources cs ON c.claim_id = cs.claim_id
                JOIN sources s ON cs.source_id = s.source_id
                WHERE s.tier = 2
            )
            AND e.claim_id NOT IN (
                SELECT DISTINCT c.claim_id
                FROM claims c
                JOIN claim_sources cs ON c.claim_id = cs.claim_id
                JOIN sources s ON cs.source_id = s.source_id
                WHERE s.tier IN (0, 1)
            )
        """).fetchall()

        for row in rows:
            gaps.append(Gap(
                gap_type="source_coverage",
                node_id=row["from_node_id"],
                node_name=f"{row['from_name']} -> {row['to_name']}",
                node_type="EDGE",
                expected_edge_type=row["edge_type"],
                description=f"Edge {row['edge_id']} has only Tier 2 sources (needs Tier 0/1)",
                priority=6,
                suggested_agent=self._suggest_agent_for_edge_type(row["edge_type"]),
            ))

        return gaps

    def _suggest_agent_for_edge_type(self, edge_type: str) -> Optional[str]:
        """Suggest which agent can upgrade source tier for an edge type."""
        edge_agent_map = {
            "OWNS_SHARES": "edgar",
            "INVESTED_IN": "edgar",
            "AWARDED_GRANT": "usaspending",
            "AWARDED_CONTRACT": "usaspending",
            "LOBBIED_FOR": "opensecrets",
            "LOBBIED_AGAINST": "opensecrets",
            "DONATED_TO": "dark_money",
            "RULEMAKING_FOR": "federal_register",
            "IMPLEMENTED_BY": "federal_register",
        }
        return edge_agent_map.get(edge_type)

    def detect_temporal_gaps(self, months: int = 6) -> List[Gap]:
        """Find nodes with no recent activity.

        Entities that haven't been updated in >X months may be stale.

        Args:
            months: Number of months to consider "recent"

        Returns:
            List of Gap objects
        """
        gaps = []

        # Find nodes where the most recent edge is older than threshold
        rows = self.conn.execute("""
            SELECT n.node_id, n.name, n.node_type,
                   MAX(e.created_at) as last_edge
            FROM nodes n
            LEFT JOIN edges e ON (e.from_node_id = n.node_id OR e.to_node_id = n.node_id)
            WHERE e.edge_id IS NOT NULL
            GROUP BY n.node_id, n.name, n.node_type
            HAVING MAX(e.created_at) < datetime('now', ?)
        """, (f'-{months} months',)).fetchall()

        for row in rows:
            expectations = self.NODE_TYPE_EXPECTATIONS.get(row["node_type"], {})
            agent = expectations["agents"][0] if expectations.get("agents") else None

            gaps.append(Gap(
                gap_type="temporal_gap",
                node_id=row["node_id"],
                node_name=row["name"],
                node_type=row["node_type"],
                expected_edge_type="ANY",
                description=f"No activity since {row['last_edge'][:10]} for {row['name']}",
                priority=4,
                suggested_agent=agent,
            ))

        return gaps

    def detect_missing_reciprocals(self) -> List[Gap]:
        """Find edges that should have reciprocal relationships.

        For example:
        - If A LOBBIED_FOR B exists, expect B BENEFITED_FROM lobbying
        - If A OWNS_SHARES B, expect B HAS_SHAREHOLDER A pattern

        Returns:
            List of Gap objects
        """
        gaps = []

        # Reciprocal patterns
        reciprocal_pairs = [
            ("LOBBIED_FOR", "BENEFITED_FROM"),
            ("SUPPLIES", "SUPPLIED_BY"),
            ("COMPETES_WITH", "COMPETES_WITH"),  # Symmetric
        ]

        for edge_type, reciprocal_type in reciprocal_pairs:
            # Find edges without reciprocals
            rows = self.conn.execute("""
                SELECT e.edge_id, e.from_node_id, e.to_node_id,
                       n_from.name as from_name, n_to.name as to_name
                FROM edges e
                JOIN nodes n_from ON e.from_node_id = n_from.node_id
                JOIN nodes n_to ON e.to_node_id = n_to.node_id
                WHERE e.edge_type = ?
                AND NOT EXISTS (
                    SELECT 1 FROM edges e2
                    WHERE e2.from_node_id = e.to_node_id
                    AND e2.to_node_id = e.from_node_id
                    AND e2.edge_type = ?
                )
            """, (edge_type, reciprocal_type)).fetchall()

            for row in rows:
                gaps.append(Gap(
                    gap_type="missing_reciprocal",
                    node_id=row["to_node_id"],
                    node_name=row["to_name"],
                    node_type="EDGE",
                    expected_edge_type=reciprocal_type,
                    description=f"Missing reciprocal: {row['to_name']} {reciprocal_type} {row['from_name']}",
                    priority=5,
                    suggested_agent=None,  # These are inferred, not fetched
                ))

        return gaps

    def get_agent_coverage_matrix(self) -> Dict[str, Dict[str, Any]]:
        """Generate a matrix of node types vs agent coverage.

        Shows which agents can cover which node types and where blind spots exist.

        Returns:
            Dict mapping node_type -> {agents: [...], coverage: float, gaps: int}
        """
        matrix = {}

        # Get all node types and their counts
        node_types = self.conn.execute("""
            SELECT node_type, COUNT(*) as count
            FROM nodes GROUP BY node_type
        """).fetchall()

        for row in node_types:
            node_type = row["node_type"]
            count = row["count"]

            expectations = self.NODE_TYPE_EXPECTATIONS.get(node_type, {})
            expected_agents = expectations.get("agents", [])
            expected_edges = expectations.get("expected_edges", [])

            # Count nodes of this type with expected edges
            if expected_edges:
                edge_placeholders = ",".join("?" for _ in expected_edges)
                covered = self.conn.execute(f"""
                    SELECT COUNT(DISTINCT n.node_id) FROM nodes n
                    WHERE n.node_type = ?
                    AND EXISTS (
                        SELECT 1 FROM edges e
                        WHERE (e.from_node_id = n.node_id OR e.to_node_id = n.node_id)
                        AND e.edge_type IN ({edge_placeholders})
                    )
                """, (node_type, *expected_edges)).fetchone()[0]
            else:
                covered = 0

            matrix[node_type] = {
                "total_nodes": count,
                "covered_nodes": covered,
                "coverage_rate": covered / count if count > 0 else 0,
                "expected_agents": expected_agents,
                "expected_edges": expected_edges,
                "gaps": count - covered,
            }

        return matrix

    def generate_agent_requests(self, limit: int = 5) -> List[AgentRequest]:
        """Generate structured agent requests based on detected gaps.

        These are actionable specs for building new agent capabilities.

        Args:
            limit: Maximum requests to generate

        Returns:
            List of AgentRequest objects
        """
        # Predefined high-value agent requests based on common gaps
        requests = []

        # Check if we need PACER/CourtListener
        crime_nodes = self.conn.execute("""
            SELECT COUNT(*) FROM nodes
            WHERE node_type IN ('CRIME', 'CASE', 'FRAUD')
            OR metadata LIKE '%indictment%' OR metadata LIKE '%settlement%'
        """).fetchone()[0]

        court_edges = self.conn.execute("""
            SELECT COUNT(*) FROM edges
            WHERE edge_type IN ('INDICTED', 'FILED_AMICUS', 'SETTLED', 'RULED_ON')
        """).fetchone()[0]

        if crime_nodes > 0 and court_edges == 0:
            requests.append(AgentRequest(
                request_id="AR-001",
                gap_type="missing_source",
                description="No court filing data despite crime/fraud nodes",
                target_entities=["crime-related nodes"],
                suggested_api="courtlistener.com/api/rest/v4/",
                priority=1,
                estimated_edges=min(30, crime_nodes * 3),
            ))

        # Check if OpenSecrets bulk would help
        lobbying_gaps = len(self.detect_missing_lobbying())
        if lobbying_gaps > 10:
            requests.append(AgentRequest(
                request_id="AR-002",
                gap_type="missing_source",
                description=f"{lobbying_gaps} organizations lack lobbying data",
                target_entities=[],
                suggested_api="opensecrets.org/api/ (needs free key)",
                priority=2,
                estimated_edges=min(60, lobbying_gaps * 2),
            ))

        # Check if FARA enhancement would help
        fara_edges = self.conn.execute("""
            SELECT COUNT(*) FROM edges WHERE edge_type = 'REGISTERED_AS_AGENT'
        """).fetchone()[0]

        foreign_org_nodes = self.conn.execute("""
            SELECT COUNT(*) FROM nodes
            WHERE metadata LIKE '%foreign%' OR metadata LIKE '%international%'
        """).fetchone()[0]

        if fara_edges < 5 and foreign_org_nodes > 10:
            requests.append(AgentRequest(
                request_id="AR-003",
                gap_type="unmonitored_entity",
                description="Foreign influence nodes lack FARA registration data",
                target_entities=["foreign organizations"],
                suggested_api="fara.gov/search (HTML scraping) or efile.fara.gov",
                priority=3,
                estimated_edges=min(40, foreign_org_nodes),
            ))

        # Check state-level campaign finance
        state_pac_edges = self.conn.execute("""
            SELECT COUNT(*) FROM edges WHERE edge_type LIKE 'STATE_%'
        """).fetchone()[0]

        if state_pac_edges == 0:
            requests.append(AgentRequest(
                request_id="AR-004",
                gap_type="new_data_type",
                description="No state-level political spending tracked",
                target_entities=["state PACs", "state campaigns"],
                suggested_api="followthemoney.org or state-specific APIs",
                priority=4,
                estimated_edges=75,
            ))

        return sorted(requests, key=lambda r: r.priority)[:limit]

    def suggest_agent_runs(self, limit: int = 10) -> List[AgentSuggestion]:
        """Generate prioritized list of agent runs to fill gaps.

        Args:
            limit: Maximum number of suggestions

        Returns:
            List of AgentSuggestion objects
        """
        gaps = self.detect_all_gaps()

        # Group gaps by suggested agent
        agent_gaps: Dict[str, List[Gap]] = {}
        for gap in gaps:
            if gap.suggested_agent:
                if gap.suggested_agent not in agent_gaps:
                    agent_gaps[gap.suggested_agent] = []
                agent_gaps[gap.suggested_agent].append(gap)

        suggestions = []
        for agent, agent_gap_list in agent_gaps.items():
            # Sort by priority
            sorted_gaps = sorted(agent_gap_list, key=lambda g: -g.priority)

            # Take top targets
            targets = [g.node_name for g in sorted_gaps[:20]]
            avg_priority = sum(g.priority for g in sorted_gaps) / len(sorted_gaps)

            # Build reason string
            gap_types = set(g.gap_type for g in sorted_gaps)
            reasons = []
            for gt in gap_types:
                count = len([g for g in sorted_gaps if g.gap_type == gt])
                reasons.append(f"{count} {gt.replace('_', ' ')}")

            suggestions.append(AgentSuggestion(
                agent=agent,
                targets=targets,
                reason="; ".join(reasons),
                gap_count=len(sorted_gaps),
                priority=int(avg_priority),
            ))

        # Sort by priority and gap count
        suggestions.sort(key=lambda s: (-s.priority, -s.gap_count))

        return suggestions[:limit]

    def get_coverage_stats(self) -> Dict[str, Any]:
        """Calculate coverage statistics for the graph.

        Returns:
            Dictionary with coverage metrics
        """
        stats = {}

        # Total counts
        stats["total_nodes"] = self.conn.execute(
            "SELECT COUNT(*) FROM nodes"
        ).fetchone()[0]

        stats["total_edges"] = self.conn.execute(
            "SELECT COUNT(*) FROM edges"
        ).fetchone()[0]

        # Nodes by type
        node_types = self.conn.execute("""
            SELECT node_type, COUNT(*) as count
            FROM nodes GROUP BY node_type ORDER BY count DESC
        """).fetchall()
        stats["nodes_by_type"] = {row["node_type"]: row["count"] for row in node_types}

        # Edges by type
        edge_types = self.conn.execute("""
            SELECT edge_type, COUNT(*) as count
            FROM edges GROUP BY edge_type ORDER BY count DESC
        """).fetchall()
        stats["edges_by_type"] = {row["edge_type"]: row["count"] for row in edge_types}

        # Nodes with edges (connected)
        connected = self.conn.execute("""
            SELECT COUNT(DISTINCT node_id) FROM (
                SELECT from_node_id as node_id FROM edges
                UNION
                SELECT to_node_id as node_id FROM edges
            )
        """).fetchone()[0]
        stats["connected_nodes"] = connected
        stats["orphan_nodes"] = stats["total_nodes"] - connected
        stats["connectivity_rate"] = connected / stats["total_nodes"] if stats["total_nodes"] > 0 else 0

        # Source tier distribution
        sources = self.conn.execute("""
            SELECT tier, COUNT(*) as count
            FROM sources GROUP BY tier ORDER BY tier
        """).fetchall()
        stats["sources_by_tier"] = {f"tier_{row['tier']}": row["count"] for row in sources}

        # Correction layer coverage
        correction_nodes = self.conn.execute("""
            SELECT COUNT(*) FROM nodes
            WHERE node_id LIKE '%chips%'
               OR node_id LIKE '%genius%'
               OR node_id LIKE '%ira%'
               OR node_id LIKE '%infrastructure%'
        """).fetchone()[0]
        stats["correction_layer_nodes"] = correction_nodes

        # Evidence completeness (edges with claims)
        evidenced_edges = self.conn.execute("""
            SELECT COUNT(*) FROM edges WHERE claim_id IS NOT NULL
        """).fetchone()[0]
        stats["evidenced_edges"] = evidenced_edges
        stats["evidence_rate"] = evidenced_edges / stats["total_edges"] if stats["total_edges"] > 0 else 0

        return stats

    def generate_report(self) -> GapReport:
        """Generate a complete gap analysis report.

        Returns:
            GapReport object
        """
        gaps = self.detect_all_gaps()
        suggestions = self.suggest_agent_runs()
        stats = self.get_coverage_stats()

        # Count gaps by type
        gap_by_type: Dict[str, int] = {}
        for gap in gaps:
            if gap.gap_type not in gap_by_type:
                gap_by_type[gap.gap_type] = 0
            gap_by_type[gap.gap_type] += 1

        return GapReport(
            timestamp=datetime.utcnow().isoformat(),
            total_nodes=stats["total_nodes"],
            total_edges=stats["total_edges"],
            gaps=gaps,
            suggestions=suggestions,
            gap_by_type=gap_by_type,
            coverage_stats=stats,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Export gap analysis as dictionary (for JSON API).

        Returns:
            Dictionary representation
        """
        report = self.generate_report()

        return {
            "timestamp": report.timestamp,
            "total_nodes": report.total_nodes,
            "total_edges": report.total_edges,
            "total_gaps": len(report.gaps),
            "gaps_by_type": report.gap_by_type,
            "gaps": [
                {
                    "gap_type": g.gap_type,
                    "node_id": g.node_id,
                    "node_name": g.node_name,
                    "node_type": g.node_type,
                    "expected_edge_type": g.expected_edge_type,
                    "description": g.description,
                    "priority": g.priority,
                    "suggested_agent": g.suggested_agent,
                }
                for g in report.gaps[:100]  # Limit for API response
            ],
            "suggestions": [
                {
                    "agent": s.agent,
                    "targets": s.targets[:10],  # Limit targets
                    "reason": s.reason,
                    "gap_count": s.gap_count,
                    "priority": s.priority,
                }
                for s in report.suggestions
            ],
            "coverage": report.coverage_stats,
        }
