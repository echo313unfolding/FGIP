#!/usr/bin/env python3
"""FGIP Coverage Analyzer - Local graph coverage analysis.

Compares our graph against expected entity sets without external API calls.
Creates sentinel nodes tracking coverage gaps for thesis-critical entities.

Expected Entity Sets (derived from thesis):
- Big Three (asset managers)
- Semiconductor majors
- Defense contractors (both-sides pattern)
- CHIPS recipients
- Debt domestication actors

Usage:
    python3 -m fgip.agents.coverage_analyzer fgip.db
"""

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set, Optional, Any

from .base import FGIPAgent, ProposedNode


@dataclass
class ExpectedEntitySet:
    """A set of entities we expect to have in the graph."""
    name: str
    description: str
    entities: List[str]
    thesis_relevance: str
    priority: int  # 1-10


@dataclass
class CoverageReport:
    """Coverage analysis for an entity set."""
    entity_set: str
    total_expected: int
    total_found: int
    coverage_ratio: float
    missing_entities: List[str]
    found_entities: List[Dict]  # node_id, edge_count
    priority: int
    thesis_impact: str


@dataclass
class RelationshipDensity:
    """Relationship density analysis for entities."""
    node_id: str
    name: str
    edge_count: int
    expected_min_edges: int
    density_status: str  # 'adequate', 'sparse', 'orphan'


# Expected entity sets derived from FGIP thesis
EXPECTED_ENTITY_SETS = [
    ExpectedEntitySet(
        name='big_three',
        description='Major index fund managers (passive capital concentration)',
        entities=['blackrock', 'vanguard', 'state-street', 'fidelity', 'schwab'],
        thesis_relevance='Both-sides pattern: same capital on problem and correction layers',
        priority=10,
    ),
    ExpectedEntitySet(
        name='semiconductor_majors',
        description='Major semiconductor companies (supply chain thesis)',
        entities=[
            'intel', 'tsmc', 'samsung', 'samsung-electronics', 'micron', 'nvidia',
            'amd', 'qualcomm', 'globalfoundries', 'texas-instruments', 'broadcom',
            'asml', 'sk-hynix', 'applied-materials', 'lam-research', 'kla-corporation',
        ],
        thesis_relevance='Supply chain vulnerability and reshoring beneficiaries',
        priority=9,
    ),
    ExpectedEntitySet(
        name='chips_recipients',
        description='CHIPS Act grant recipients (correction layer)',
        entities=[
            'intel', 'tsmc', 'samsung', 'micron', 'globalfoundries',
            'texas-instruments', 'sk-hynix', 'bae-systems', 'microchip-technology',
            'onsemi', 'polar-semiconductor',
        ],
        thesis_relevance='Government reshoring investments (correction layer)',
        priority=9,
    ),
    ExpectedEntitySet(
        name='defense_primes',
        description='Major defense contractors (both-sides pattern)',
        entities=[
            'lockheed-martin', 'raytheon', 'northrop-grumman', 'boeing',
            'general-dynamics', 'l3harris', 'bae-systems', 'huntington-ingalls',
            'leidos', 'saic',
        ],
        thesis_relevance='Defense industrial base, both-sides ownership pattern',
        priority=8,
    ),
    ExpectedEntitySet(
        name='tech_offshorers',
        description='Major tech companies with offshore supply chains (problem layer)',
        entities=[
            'apple', 'google', 'microsoft', 'amazon', 'meta',
            'alphabet', 'nvidia', 'tesla', 'hp', 'dell', 'cisco',
        ],
        thesis_relevance='Companies dependent on offshore supply chains (problem layer)',
        priority=8,
    ),
    ExpectedEntitySet(
        name='nuclear_smr',
        description='Small modular reactor companies (energy reshoring)',
        entities=[
            'nuscale', 'oklo', 'terrapower', 'x-energy', 'kairos-power',
            'westinghouse', 'ge-hitachi', 'bwxt', 'centrus-energy',
        ],
        thesis_relevance='Energy independence and nuclear renaissance thesis',
        priority=7,
    ),
    ExpectedEntitySet(
        name='stablecoin_actors',
        description='Stablecoin issuers and related (debt domestication)',
        entities=[
            'tether', 'circle', 'usdc', 'paxos', 'binance',
            'coinbase', 'kraken', 'gemini',
        ],
        thesis_relevance='GENIUS Act and debt domestication thesis',
        priority=7,
    ),
    ExpectedEntitySet(
        name='federal_agencies',
        description='Key federal agencies in thesis',
        entities=[
            'federal-reserve', 'treasury', 'sec', 'fdic', 'occ',
            'commerce', 'dod', 'doe', 'nist', 'chips-program-office',
        ],
        thesis_relevance='Government actors in monetary and industrial policy',
        priority=8,
    ),
]

# Minimum expected edges by node type
MIN_EDGES_BY_TYPE = {
    'ORGANIZATION': 3,
    'COMPANY': 5,
    'GOVERNMENT_AGENCY': 4,
    'PERSON': 2,
    'POLICY': 2,
    'EVENT': 3,
    'CONCEPT': 2,
}


class CoverageAnalyzer(FGIPAgent):
    """Analyzes graph coverage against expected entity sets.

    Creates sentinel nodes summarizing:
    - Which entity sets have good/poor coverage
    - Which priority entities are missing
    - Relationship density gaps
    """

    AGENT_NAME = "coverage-analyzer"

    def __init__(self, db):
        super().__init__(db, self.AGENT_NAME)
        self.coverage_reports: List[CoverageReport] = []
        self.density_analysis: List[RelationshipDensity] = []

    def collect(self) -> Dict:
        """Get current graph state."""
        conn = self.db.connect()

        # Get all nodes with their edge counts
        nodes_with_edges = conn.execute("""
            SELECT n.node_id, n.name, n.node_type, COALESCE(e.edge_count, 0) as edge_count
            FROM nodes n
            LEFT JOIN (
                SELECT node_id, SUM(cnt) as edge_count FROM (
                    SELECT from_node_id as node_id, COUNT(*) as cnt FROM edges GROUP BY from_node_id
                    UNION ALL
                    SELECT to_node_id as node_id, COUNT(*) as cnt FROM edges GROUP BY to_node_id
                ) GROUP BY node_id
            ) e ON n.node_id = e.node_id
        """).fetchall()

        # Build lookup
        node_data = {}
        for node_id, name, node_type, edge_count in nodes_with_edges:
            node_data[node_id] = {
                'name': name,
                'type': node_type,
                'edges': edge_count,
            }
            # Also index by normalized name
            normalized = self._normalize(name) if name else node_id
            if normalized not in node_data:
                node_data[normalized] = node_data[node_id]

        return {
            'nodes': node_data,
            'total_nodes': len(nodes_with_edges),
            'total_edges': conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0],
        }

    def _normalize(self, name: str) -> str:
        """Normalize entity name for matching."""
        name = name.lower().strip()
        for suffix in [' inc', ' inc.', ' corp', ' corp.', ' corporation',
                       ' llc', ' ltd', ' limited', ' co', ' co.', ' company']:
            if name.endswith(suffix):
                name = name[:-len(suffix)]
        return name.replace(' ', '-').replace(',', '').replace('.', '')

    def _find_node(self, entity: str, nodes: Dict) -> Optional[Dict]:
        """Find a node matching the entity name."""
        # Direct match
        if entity in nodes:
            return {'node_id': entity, **nodes[entity]}

        # Normalized match
        normalized = self._normalize(entity)
        if normalized in nodes:
            return {'node_id': normalized, **nodes[normalized]}

        # Partial match
        for node_id, info in nodes.items():
            node_normalized = self._normalize(info.get('name', node_id))
            if entity in node_normalized or normalized in node_id:
                return {'node_id': node_id, **info}

        return None

    def extract(self, collected: Dict) -> List[CoverageReport]:
        """Analyze coverage for each expected entity set."""
        nodes = collected['nodes']
        reports = []

        for entity_set in EXPECTED_ENTITY_SETS:
            found_entities = []
            missing_entities = []

            for entity in entity_set.entities:
                match = self._find_node(entity, nodes)
                if match:
                    found_entities.append({
                        'expected': entity,
                        'node_id': match['node_id'],
                        'edges': match.get('edges', 0),
                    })
                else:
                    missing_entities.append(entity)

            coverage_ratio = len(found_entities) / len(entity_set.entities) if entity_set.entities else 0

            # Determine thesis impact
            if coverage_ratio < 0.5:
                thesis_impact = 'CRITICAL: Major blind spot in thesis coverage'
            elif coverage_ratio < 0.75:
                thesis_impact = 'MODERATE: Significant entities missing'
            else:
                thesis_impact = 'ADEQUATE: Most entities covered'

            reports.append(CoverageReport(
                entity_set=entity_set.name,
                total_expected=len(entity_set.entities),
                total_found=len(found_entities),
                coverage_ratio=coverage_ratio,
                missing_entities=missing_entities,
                found_entities=found_entities,
                priority=entity_set.priority,
                thesis_impact=thesis_impact,
            ))

        # Analyze relationship density
        for node_id, info in nodes.items():
            if not isinstance(info, dict):
                continue

            node_type = info.get('type', 'UNKNOWN')
            min_edges = MIN_EDGES_BY_TYPE.get(node_type, 2)
            actual_edges = info.get('edges', 0)

            if actual_edges < min_edges:
                status = 'orphan' if actual_edges < 2 else 'sparse'
                self.density_analysis.append(RelationshipDensity(
                    node_id=node_id,
                    name=info.get('name', node_id),
                    edge_count=actual_edges,
                    expected_min_edges=min_edges,
                    density_status=status,
                ))

        self.coverage_reports = reports
        return reports

    def propose(self, reports: List[CoverageReport]) -> Dict:
        """Generate coverage sentinel nodes and gap proposals."""
        conn = self.db.connect()
        timestamp = datetime.now(timezone.utc).isoformat()

        # Create sentinel nodes for each coverage area
        sentinel_nodes_created = 0
        for report in reports:
            sentinel_id = f"sentinel:coverage:{report.entity_set}"

            # Check if exists
            existing = conn.execute(
                "SELECT node_id FROM nodes WHERE node_id = ?",
                (sentinel_id,)
            ).fetchone()

            if not existing:
                sha256 = hashlib.sha256(f"{sentinel_id}:{timestamp}".encode()).hexdigest()
                metadata = json.dumps({
                    'type': 'coverage_sentinel',
                    'entity_set': report.entity_set,
                    'coverage_ratio': report.coverage_ratio,
                    'missing_count': len(report.missing_entities),
                    'missing_entities': report.missing_entities,
                    'thesis_impact': report.thesis_impact,
                    'last_analyzed': timestamp,
                })

                conn.execute("""
                    INSERT INTO nodes (node_id, node_type, name, created_at, sha256, metadata)
                    VALUES (?, 'SENTINEL', ?, ?, ?, ?)
                """, (
                    sentinel_id,
                    f"Coverage: {report.entity_set} ({report.coverage_ratio*100:.0f}%)",
                    timestamp,
                    sha256,
                    metadata,
                ))
                sentinel_nodes_created += 1

        conn.commit()

        # Write detailed report
        full_report = {
            'timestamp': timestamp,
            'summary': {
                'total_entity_sets': len(reports),
                'critical_gaps': len([r for r in reports if r.coverage_ratio < 0.5]),
                'moderate_gaps': len([r for r in reports if 0.5 <= r.coverage_ratio < 0.75]),
                'adequate_coverage': len([r for r in reports if r.coverage_ratio >= 0.75]),
                'total_missing_entities': sum(len(r.missing_entities) for r in reports),
                'sparse_nodes': len([d for d in self.density_analysis if d.density_status == 'sparse']),
                'orphan_nodes': len([d for d in self.density_analysis if d.density_status == 'orphan']),
            },
            'coverage_by_set': [asdict(r) for r in reports],
            'density_issues': [asdict(d) for d in self.density_analysis[:50]],  # Top 50
            'recommended_actions': self._generate_recommendations(reports),
        }

        # Write receipt
        receipts_dir = Path(__file__).parent.parent.parent / "receipts" / "coverage"
        receipts_dir.mkdir(parents=True, exist_ok=True)
        receipt_path = receipts_dir / f"analysis_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        receipt_path.write_text(json.dumps(full_report, indent=2))

        return {
            'agent': self.AGENT_NAME,
            'sentinel_nodes_created': sentinel_nodes_created,
            'entity_sets_analyzed': len(reports),
            'critical_gaps': full_report['summary']['critical_gaps'],
            'total_missing_entities': full_report['summary']['total_missing_entities'],
            'receipt': str(receipt_path),
        }

    def _generate_recommendations(self, reports: List[CoverageReport]) -> List[Dict]:
        """Generate prioritized recommendations for filling gaps."""
        recommendations = []

        for report in sorted(reports, key=lambda r: (r.coverage_ratio, -r.priority)):
            if report.missing_entities:
                # Find the entity set definition
                entity_set_def = next(
                    (es for es in EXPECTED_ENTITY_SETS if es.name == report.entity_set),
                    None
                )

                recommendations.append({
                    'priority': report.priority,
                    'action': f"Add {len(report.missing_entities)} missing entities to {report.entity_set}",
                    'entities': report.missing_entities,
                    'thesis_relevance': entity_set_def.thesis_relevance if entity_set_def else '',
                    'coverage_impact': f"Would improve {report.entity_set} from {report.coverage_ratio*100:.0f}% to 100%",
                })

        return recommendations

    def run(self) -> Dict:
        """Run full coverage analysis."""
        collected = self.collect()
        reports = self.extract(collected)
        return self.propose(reports)


def main():
    """CLI for coverage analyzer."""
    import argparse
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from fgip.db import FGIPDatabase

    parser = argparse.ArgumentParser(description="FGIP Coverage Analyzer")
    parser.add_argument("db", type=str, help="Database path")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--verbose", action="store_true", help="Show all missing entities")

    args = parser.parse_args()

    db = FGIPDatabase(args.db)
    analyzer = CoverageAnalyzer(db)
    result = analyzer.run()

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("=" * 60)
        print("  FGIP COVERAGE ANALYSIS")
        print("=" * 60)
        print(f"  Entity Sets Analyzed: {result['entity_sets_analyzed']}")
        print(f"  Critical Gaps: {result['critical_gaps']}")
        print(f"  Total Missing Entities: {result['total_missing_entities']}")
        print(f"  Sentinel Nodes Created: {result['sentinel_nodes_created']}")
        print()

        # Show coverage by set
        print("  Coverage by Entity Set:")
        for report in analyzer.coverage_reports:
            status = "✓" if report.coverage_ratio >= 0.75 else "⚠" if report.coverage_ratio >= 0.5 else "✗"
            print(f"    {status} {report.entity_set}: {report.coverage_ratio*100:.0f}% ({report.total_found}/{report.total_expected})")
            if args.verbose and report.missing_entities:
                print(f"      Missing: {', '.join(report.missing_entities[:5])}")
                if len(report.missing_entities) > 5:
                    print(f"      ... and {len(report.missing_entities) - 5} more")
        print()
        print(f"  Receipt: {result['receipt']}")
        print("=" * 60)


if __name__ == "__main__":
    main()
