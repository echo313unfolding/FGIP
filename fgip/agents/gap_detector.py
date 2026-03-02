"""FGIP Gap Detector Agent - Meta-analysis for self-healing graph.

Runs after tier cycles to detect structural gaps:
- Orphan nodes (<3 edges)
- Unused edge types that SHOULD exist
- Promotion bottleneck (pending/applied ratio)
- Extraction gaps (proposed but not committed)
- Stale claims (UNVERIFIED >7 days)

Outputs gaps.json receipt to receipts/gaps/.
"""

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from .base import FGIPAgent, Artifact, StructuredFact, ProposedClaim, ProposedEdge


@dataclass
class GapFinding:
    """A detected gap in the knowledge graph."""
    gap_id: str
    gap_type: str  # orphan_node, unused_edge_type, promotion_bottleneck, extraction_gap, stale_claim
    severity: int  # 1-10, higher = more urgent
    entity_id: Optional[str]
    description: str
    suggested_action: str
    suggested_agent: Optional[str]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GapReport:
    """Complete gap analysis report."""
    report_id: str
    timestamp: str
    total_nodes: int
    total_edges: int
    orphan_count: int
    orphanage_rate: float
    unused_edge_types: List[str]
    promotion_bottleneck: Dict[str, int]
    extraction_gaps: List[Dict[str, Any]]
    findings: List[GapFinding]
    priority_actions: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['findings'] = [f.to_dict() if isinstance(f, GapFinding) else f for f in self.findings]
        return d


class GapDetectorAgent(FGIPAgent):
    """Meta-agent that detects structural gaps in the FGIP graph.

    Runs after tier cycles to identify:
    - Orphan nodes (nodes with <3 edges)
    - Unused edge types (36/52 completely unused)
    - Promotion bottleneck (3,078 pending vs 56 applied)
    - Extraction gaps (SUPPLIES_TO: 241 proposed, 0 committed)
    - Stale claims (UNVERIFIED > 7 days)

    Outputs gaps.json with priority-ranked holes.
    """

    # Edge types that SHOULD exist for complete graph
    EXPECTED_EDGE_TYPES = {
        'supply_chain': ['SUPPLIES_TO', 'DEPENDS_ON', 'CUSTOMER_OF', 'BOTTLENECK_AT'],
        'governance': ['SITS_ON_BOARD', 'APPOINTED_BY', 'RELATED_PARTY_TXN'],
        'causal': ['CAUSED', 'ENABLED', 'CONTRIBUTED_TO'],
        'correction_layer': ['AWARDED_GRANT', 'AWARDED_CONTRACT', 'FUNDED_PROJECT', 'BUILT_IN'],
    }

    # Minimum edge count for a node to not be an orphan
    ORPHAN_THRESHOLD = 3

    # Days after which UNVERIFIED claims are stale
    STALE_CLAIM_DAYS = 7

    # Agent suggestions by node type
    NODE_TYPE_AGENTS = {
        'PERSON': 'edgar',  # DEF 14A for board members
        'COMPANY': 'edgar',
        'ORGANIZATION': 'fara',
        'LEGISLATION': 'congress',
        'FACILITY': 'chips_facility',
    }

    # Agent suggestions by edge type
    EDGE_TYPE_AGENTS = {
        'SUPPLIES_TO': 'supply_chain_extractor',
        'DEPENDS_ON': 'supply_chain_extractor',
        'CUSTOMER_OF': 'supply_chain_extractor',
        'BOTTLENECK_AT': 'supply_chain_extractor',
        'SITS_ON_BOARD': 'edgar',
        'OWNS_SHARES': 'edgar',
        'AWARDED_GRANT': 'usaspending',
        'FUNDED_PROJECT': 'usaspending',
        'LOBBIED_FOR': 'opensecrets',
        'REGISTERED_AS_AGENT': 'fara',
    }

    def __init__(self, db, output_dir: str = "receipts/gaps"):
        super().__init__(
            db=db,
            name="gap_detector",
            description="Meta-agent that detects structural gaps in FGIP graph"
        )
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def collect(self) -> List[Artifact]:
        """Collect graph statistics as the 'artifact'."""
        conn = self.db.connect()

        stats = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'nodes': {},
            'edges': {},
            'proposals': {},
            'claims': {},
        }

        # Node statistics
        stats['nodes']['total'] = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        node_types = conn.execute(
            "SELECT node_type, COUNT(*) FROM nodes GROUP BY node_type"
        ).fetchall()
        stats['nodes']['by_type'] = {r[0]: r[1] for r in node_types}

        # Edge statistics by type
        edge_counts = conn.execute(
            "SELECT edge_type, COUNT(*) FROM edges GROUP BY edge_type"
        ).fetchall()
        stats['edges']['total'] = sum(e[1] for e in edge_counts)
        stats['edges']['by_type'] = {r[0]: r[1] for r in edge_counts}

        # Proposal statistics (THE BOTTLENECK)
        stats['proposals']['pending_edges'] = conn.execute(
            "SELECT COUNT(*) FROM proposed_edges WHERE status = 'PENDING'"
        ).fetchone()[0]
        stats['proposals']['approved_edges'] = conn.execute(
            "SELECT COUNT(*) FROM proposed_edges WHERE status = 'APPROVED'"
        ).fetchone()[0]

        # Count edges that came from proposals (have proposal_id in metadata)
        try:
            stats['proposals']['applied_edges'] = conn.execute(
                "SELECT COUNT(*) FROM edges WHERE metadata LIKE '%proposal_id%'"
            ).fetchone()[0]
        except Exception:
            stats['proposals']['applied_edges'] = 0

        # Pending by edge type
        pending_types = conn.execute(
            "SELECT relationship, COUNT(*) FROM proposed_edges WHERE status = 'PENDING' GROUP BY relationship"
        ).fetchall()
        stats['proposals']['pending_by_type'] = {r[0]: r[1] for r in pending_types}

        # Claim statistics
        try:
            stats['claims']['total'] = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
            stats['claims']['unverified_old'] = conn.execute(
                """SELECT COUNT(*) FROM claims
                   WHERE status IN ('PARTIAL', 'MISSING', 'UNVERIFIED')
                   AND created_at < datetime('now', '-7 days')"""
            ).fetchone()[0]
        except Exception:
            stats['claims']['total'] = 0
            stats['claims']['unverified_old'] = 0

        # Create artifact
        content = json.dumps(stats, indent=2).encode('utf-8')
        artifact_path = self.output_dir / f"graph_state_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        artifact_path.write_bytes(content)

        return [Artifact(
            url="internal://gap_detector/graph_state",
            artifact_type="graph_state",
            local_path=str(artifact_path),
            content_hash=hashlib.sha256(content).hexdigest(),
            metadata=stats
        )]

    def extract(self, artifacts: List[Artifact]) -> List[StructuredFact]:
        """Extract gap findings from graph state."""
        facts = []

        for artifact in artifacts:
            stats = artifact.metadata

            # 1. Detect orphan nodes
            orphan_facts = self._detect_orphan_nodes()
            facts.extend(orphan_facts)

            # 2. Detect unused edge types
            unused_facts = self._detect_unused_edge_types(stats)
            facts.extend(unused_facts)

            # 3. Detect promotion bottleneck
            bottleneck_facts = self._detect_promotion_bottleneck(stats)
            facts.extend(bottleneck_facts)

            # 4. Detect extraction gaps (proposed but not committed)
            extraction_facts = self._detect_extraction_gaps(stats)
            facts.extend(extraction_facts)

            # 5. Detect stale claims
            stale_facts = self._detect_stale_claims()
            facts.extend(stale_facts)

        return facts

    def _detect_orphan_nodes(self) -> List[StructuredFact]:
        """Find nodes with <3 edges."""
        conn = self.db.connect()

        # Count edges per node (both directions)
        orphans = conn.execute("""
            SELECT n.node_id, n.name, n.node_type,
                   COALESCE(e_count.cnt, 0) as edge_count
            FROM nodes n
            LEFT JOIN (
                SELECT node_id, SUM(cnt) as cnt FROM (
                    SELECT from_node_id as node_id, COUNT(*) as cnt FROM edges GROUP BY from_node_id
                    UNION ALL
                    SELECT to_node_id as node_id, COUNT(*) as cnt FROM edges GROUP BY to_node_id
                ) GROUP BY node_id
            ) e_count ON n.node_id = e_count.node_id
            WHERE COALESCE(e_count.cnt, 0) < ?
            LIMIT 1000
        """, (self.ORPHAN_THRESHOLD,)).fetchall()

        facts = []
        for row in orphans:
            node_id, name, node_type, edge_count = row
            suggested_agent = self.NODE_TYPE_AGENTS.get(node_type, 'edgar')

            facts.append(StructuredFact(
                fact_type="orphan_node",
                subject=node_id,
                predicate="HAS_EDGE_COUNT",
                object=str(edge_count),
                source_artifact=None,
                confidence=1.0,
                metadata={
                    'node_name': name,
                    'node_type': node_type,
                    'edge_count': edge_count,
                    'suggested_agent': suggested_agent,
                }
            ))

        return facts

    def _detect_unused_edge_types(self, stats: Dict) -> List[StructuredFact]:
        """Find expected edge types with 0 committed edges."""
        committed_types = stats['edges'].get('by_type', {})
        pending_types = stats['proposals'].get('pending_by_type', {})
        facts = []

        for category, edge_types in self.EXPECTED_EDGE_TYPES.items():
            for edge_type in edge_types:
                committed = committed_types.get(edge_type, 0)
                pending = pending_types.get(edge_type, 0)

                if committed == 0:
                    suggested_agent = self.EDGE_TYPE_AGENTS.get(edge_type)

                    facts.append(StructuredFact(
                        fact_type="unused_edge_type",
                        subject=edge_type,
                        predicate="MISSING",
                        object=f"category={category}",
                        source_artifact=None,
                        confidence=1.0,
                        metadata={
                            'category': category,
                            'committed': committed,
                            'pending': pending,
                            'severity': 8 if pending > 0 else 6,
                            'suggested_agent': suggested_agent,
                            'has_pending': pending > 0,
                        }
                    ))

        return facts

    def _detect_promotion_bottleneck(self, stats: Dict) -> List[StructuredFact]:
        """Identify the review queue constraint."""
        pending = stats['proposals'].get('pending_edges', 0)
        applied = stats['proposals'].get('applied_edges', 0)

        if pending > 0 and applied > 0:
            ratio = pending / applied
        else:
            ratio = float(pending) if pending > 0 else 0

        # Severity based on ratio
        if ratio > 50:
            severity = 10
            action = 'auto_promote_high_confidence'
        elif ratio > 10:
            severity = 8
            action = 'batch_review'
        elif ratio > 5:
            severity = 6
            action = 'prioritize_review'
        else:
            severity = 3
            action = 'normal_review'

        return [StructuredFact(
            fact_type="promotion_bottleneck",
            subject="review_queue",
            predicate="RATIO",
            object=f"{ratio:.1f}:1",
            source_artifact=None,
            confidence=1.0,
            metadata={
                'pending_count': pending,
                'applied_count': applied,
                'ratio': ratio,
                'severity': severity,
                'suggested_action': action,
            }
        )]

    def _detect_extraction_gaps(self, stats: Dict) -> List[StructuredFact]:
        """Find edge types with proposals but no committed edges."""
        facts = []
        pending_by_type = stats['proposals'].get('pending_by_type', {})
        committed_by_type = stats['edges'].get('by_type', {})

        for edge_type, pending_count in pending_by_type.items():
            committed_count = committed_by_type.get(edge_type, 0)

            if pending_count > 0 and committed_count == 0:
                suggested_agent = self.EDGE_TYPE_AGENTS.get(edge_type)
                severity = min(10, pending_count // 20 + 5)

                facts.append(StructuredFact(
                    fact_type="extraction_gap",
                    subject=edge_type,
                    predicate="GAP",
                    object=f"{pending_count} proposed, {committed_count} committed",
                    source_artifact=None,
                    confidence=1.0,
                    metadata={
                        'pending': pending_count,
                        'committed': committed_count,
                        'severity': severity,
                        'suggested_action': 'batch_promote' if pending_count > 100 else 'review',
                        'suggested_agent': suggested_agent,
                    }
                ))

        return facts

    def _detect_stale_claims(self) -> List[StructuredFact]:
        """Find claims UNVERIFIED for more than 7 days."""
        conn = self.db.connect()
        facts = []

        try:
            stale = conn.execute("""
                SELECT claim_id, claim_text, topic, status, created_at,
                       CAST(JULIANDAY('now') - JULIANDAY(created_at) AS INTEGER) as days_old
                FROM claims
                WHERE status IN ('PARTIAL', 'MISSING', 'UNVERIFIED')
                AND created_at < datetime('now', '-7 days')
                ORDER BY created_at ASC
                LIMIT 100
            """).fetchall()

            for row in stale:
                claim_id, claim_text, topic, status, created_at, days_old = row
                facts.append(StructuredFact(
                    fact_type="stale_claim",
                    subject=claim_id,
                    predicate="UNVERIFIED_DAYS",
                    object=str(days_old),
                    source_artifact=None,
                    confidence=1.0,
                    metadata={
                        'claim_text': claim_text[:100] if claim_text else '',
                        'topic': topic,
                        'status': status,
                        'days_old': days_old,
                        'severity': min(10, days_old // 7 + 3),
                    }
                ))
        except Exception:
            pass  # claims table may not have all columns

        return facts

    def propose(self, facts: List[StructuredFact]) -> Tuple[List[ProposedClaim], List[ProposedEdge]]:
        """Generate gap report (written as receipt, not proposal)."""

        # Group facts by type
        orphans = [f for f in facts if f.fact_type == 'orphan_node']
        unused_types = [f for f in facts if f.fact_type == 'unused_edge_type']
        bottlenecks = [f for f in facts if f.fact_type == 'promotion_bottleneck']
        extraction_gaps = [f for f in facts if f.fact_type == 'extraction_gap']
        stale_claims = [f for f in facts if f.fact_type == 'stale_claim']

        # Calculate orphanage rate
        conn = self.db.connect()
        total_nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        orphanage_rate = len(orphans) / total_nodes if total_nodes > 0 else 0

        # Build priority actions
        priority_actions = []

        # #1 Priority: Promotion bottleneck
        for f in bottlenecks:
            if f.metadata['ratio'] > 10:
                priority_actions.append({
                    'priority': 1,
                    'action': 'resolve_promotion_bottleneck',
                    'description': f"Pending/Applied ratio is {f.metadata['ratio']:.0f}:1",
                    'suggested_command': 'python3 tools/apply_proposals.py fgip.db',
                    'impact': f"{f.metadata['pending_count']} edges waiting promotion",
                })

        # #2 Priority: Extraction gaps (proposed but not committed)
        for f in extraction_gaps:
            if f.metadata['pending'] > 50:
                priority_actions.append({
                    'priority': 2,
                    'action': f"promote_{f.subject.lower()}_edges",
                    'description': f"{f.subject}: {f.metadata['pending']} proposed, 0 committed",
                    'suggested_command': f"python3 tools/review_proposals.py approve-batch fgip.db --type edge --relationship {f.subject}",
                    'impact': f"Would enable {f.subject} edges for analysis",
                })

        # #3 Priority: Unused edge types with pending proposals
        for f in unused_types:
            if f.metadata.get('has_pending'):
                priority_actions.append({
                    'priority': 3,
                    'action': f"review_{f.subject.lower()}_proposals",
                    'description': f"{f.subject}: {f.metadata['pending']} pending, 0 committed",
                    'suggested_agent': f.metadata.get('suggested_agent'),
                    'impact': f"Would populate {f.metadata['category']} layer",
                })

        # #4 Priority: Missing edge types (no proposals)
        for f in unused_types:
            if not f.metadata.get('has_pending'):
                priority_actions.append({
                    'priority': 4,
                    'action': f"extract_{f.subject.lower()}_edges",
                    'description': f"{f.subject}: 0 proposed, 0 committed",
                    'suggested_agent': f.metadata.get('suggested_agent'),
                    'impact': f"Requires new extraction for {f.metadata['category']} layer",
                })

        # Build findings list
        findings = []
        for f in facts:
            findings.append(GapFinding(
                gap_id=f"{f.fact_type}_{f.subject}",
                gap_type=f.fact_type,
                severity=f.metadata.get('severity', 5),
                entity_id=f.subject if f.fact_type != 'promotion_bottleneck' else None,
                description=f"{f.predicate}: {f.object}",
                suggested_action=f.metadata.get('suggested_action', 'review'),
                suggested_agent=f.metadata.get('suggested_agent'),
                metadata=f.metadata,
            ))

        # Build report
        report = GapReport(
            report_id=f"gap-report-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_nodes=total_nodes,
            total_edges=conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0],
            orphan_count=len(orphans),
            orphanage_rate=round(orphanage_rate, 3),
            unused_edge_types=[f.subject for f in unused_types],
            promotion_bottleneck=bottlenecks[0].metadata if bottlenecks else {},
            extraction_gaps=[f.metadata for f in extraction_gaps],
            findings=findings,
            priority_actions=sorted(priority_actions, key=lambda x: x['priority']),
        )

        # Write receipt
        receipt_path = self.output_dir / f"gaps_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        receipt_path.write_text(json.dumps(report.to_dict(), indent=2))

        print(f"\n{'='*60}")
        print(f"  GAP DETECTOR REPORT")
        print(f"{'='*60}")
        print(f"  Orphan nodes: {len(orphans)} / {total_nodes} ({orphanage_rate*100:.1f}%)")
        print(f"  Unused edge types: {len(unused_types)}")
        print(f"  Extraction gaps: {len(extraction_gaps)}")
        print(f"  Stale claims: {len(stale_claims)}")
        if bottlenecks:
            b = bottlenecks[0].metadata
            print(f"  Promotion bottleneck: {b['pending_count']} pending / {b['applied_count']} applied ({b['ratio']:.0f}:1)")
        print(f"\n  Priority actions: {len(priority_actions)}")
        for action in priority_actions[:5]:
            print(f"    [{action['priority']}] {action['action']}")
        print(f"\n  Receipt: {receipt_path}")
        print(f"{'='*60}\n")

        # Meta-agent: don't create proposals, just return empty
        return [], []


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    from fgip.db import FGIPDatabase

    db_path = sys.argv[1] if len(sys.argv) > 1 else "fgip.db"
    db = FGIPDatabase(db_path)
    db.connect()

    agent = GapDetectorAgent(db)
    result = agent.run()

    print(f"Artifacts collected: {result['artifacts_collected']}")
    print(f"Facts extracted: {result['facts_extracted']}")
