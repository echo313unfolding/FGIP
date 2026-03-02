#!/usr/bin/env python3
"""FGIP Coverage Probe Agent - Compare against external knowledge graphs.

Instead of importing billions of nodes, we:
1. Probe external graphs for OUR entities
2. Check what relationships they have that we don't
3. Create sentinel/summary nodes tracking coverage gaps
4. Detect convergence (agreement) vs divergence (disagreement/missing)

External sources:
- Wikidata (SPARQL) - General knowledge graph
- OpenCorporates - Company relationships
- SEC EDGAR full - Complete filing coverage
- USASpending - Federal contracts/grants
- Crunchbase (if available) - Investment relationships

Usage:
    from fgip.agents.coverage_probe import CoverageProbeAgent
    agent = CoverageProbeAgent(db)
    result = agent.run()
"""

import hashlib
import json
import re
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from urllib.parse import quote
import urllib.request
import urllib.error

from .base import FGIPAgent, ProposedEdge, ProposedNode


@dataclass
class CoverageGap:
    """A detected gap in our coverage vs external graph."""
    our_node_id: str
    external_source: str
    gap_type: str  # 'missing_entity', 'missing_relationship', 'divergence', 'stale'
    external_relationships: List[Dict]  # What the external graph has
    our_relationships: List[str]  # What we have
    priority: int  # 1-10, based on relevance to thesis
    details: str


@dataclass
class SentinelNode:
    """Summary node tracking coverage against external graph."""
    node_id: str  # e.g., 'coverage:wikidata:semiconductors'
    source: str  # External source name
    domain: str  # What area this covers
    our_coverage: int  # How many of our nodes are covered
    external_total: int  # How many entities exist in external
    coverage_ratio: float  # our_coverage / external_total
    missing_high_priority: List[str]  # Top entities we're missing
    divergence_count: int  # Where we disagree
    last_probed: str  # ISO timestamp
    metadata: Dict = field(default_factory=dict)


class WikidataProbe:
    """Probe Wikidata via SPARQL for coverage comparison."""

    SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"

    # Wikidata property IDs for relationships we care about
    PROPERTY_MAP = {
        'P127': 'OWNED_BY',           # owned by
        'P749': 'PARENT_ORG',         # parent organization
        'P355': 'SUBSIDIARY',         # subsidiary
        'P1830': 'OWNER_OF',          # owner of
        'P452': 'INDUSTRY',           # industry
        'P159': 'HEADQUARTERS',       # headquarters location
        'P17': 'COUNTRY',             # country
        'P112': 'FOUNDED_BY',         # founded by
        'P169': 'CEO',                # chief executive officer
        'P3320': 'BOARD_MEMBER',      # board member
        'P1128': 'EMPLOYEES',         # employees
        'P2139': 'REVENUE',           # total revenue
        'P414': 'STOCK_EXCHANGE',     # stock exchange
        'P249': 'TICKER',             # ticker symbol
    }

    # Domains we care about for FGIP
    # Using instance of (P31) and subclass queries for broader coverage
    DOMAIN_QUERIES = {
        'semiconductors': '''
            SELECT ?company ?companyLabel ?relation ?target ?targetLabel WHERE {
                {?company wdt:P31 wd:Q891723.}  # instance of: semiconductor company
                UNION
                {?company wdt:P452 wd:Q880739.}  # industry: semiconductor industry
                UNION
                {?company wdt:P452 wd:Q12772.}  # industry: semiconductor device
                ?company ?relation ?target.
                FILTER(STRSTARTS(STR(?relation), "http://www.wikidata.org/prop/direct/P"))
                SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
            } LIMIT 300
        ''',
        'defense_contractors': '''
            SELECT ?company ?companyLabel ?relation ?target ?targetLabel WHERE {
                {?company wdt:P31 wd:Q1194866.}  # instance of: arms industry company
                UNION
                {?company wdt:P452 wd:Q4830453.}  # industry: business
                ?company wdt:P17 wd:Q30.  # country: USA
                ?company ?relation ?target.
                FILTER(STRSTARTS(STR(?relation), "http://www.wikidata.org/prop/direct/P"))
                SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
            } LIMIT 300
        ''',
        'investment_managers': '''
            SELECT ?company ?companyLabel ?relation ?target ?targetLabel WHERE {
                {?company wdt:P31 wd:Q4830453.}  # instance of: business
                ?company wdt:P452 wd:Q1323314.  # industry: investment management
                ?company ?relation ?target.
                FILTER(STRSTARTS(STR(?relation), "http://www.wikidata.org/prop/direct/P"))
                SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
            } LIMIT 300
        ''',
    }

    def __init__(self, rate_limit_seconds: float = 0.5):
        self.rate_limit = rate_limit_seconds
        self.last_request = 0

    def _sparql_query(self, query: str) -> List[Dict]:
        """Execute SPARQL query against Wikidata."""
        # Rate limiting
        elapsed = time.time() - self.last_request
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)

        url = f"{self.SPARQL_ENDPOINT}?query={quote(query)}"
        headers = {
            'Accept': 'application/sparql-results+json',
            'User-Agent': 'FGIP-CoverageProbe/1.0 (https://github.com/fgip)'
        }

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as response:
                self.last_request = time.time()
                data = json.loads(response.read().decode('utf-8'))
                return data.get('results', {}).get('bindings', [])
        except Exception as e:
            print(f"Wikidata query failed: {e}")
            return []

    def probe_entity(self, entity_name: str) -> Dict:
        """Check what Wikidata knows about an entity."""
        # Search for entity
        search_query = f'''
            SELECT ?item ?itemLabel ?itemDescription WHERE {{
                ?item rdfs:label "{entity_name}"@en.
                SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
            }} LIMIT 5
        '''

        results = self._sparql_query(search_query)
        if not results:
            # Try fuzzy search
            search_query = f'''
                SELECT ?item ?itemLabel ?itemDescription WHERE {{
                    ?item ?label "{entity_name}"@en.
                    SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
                }} LIMIT 5
            '''
            results = self._sparql_query(search_query)

        if not results:
            return {'found': False, 'entity': entity_name}

        # Get relationships for found entity
        item_id = results[0]['item']['value'].split('/')[-1]
        rel_query = f'''
            SELECT ?prop ?propLabel ?value ?valueLabel WHERE {{
                wd:{item_id} ?prop ?value.
                FILTER(STRSTARTS(STR(?prop), "http://www.wikidata.org/prop/direct/"))
                SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
            }} LIMIT 100
        '''

        relationships = self._sparql_query(rel_query)

        return {
            'found': True,
            'entity': entity_name,
            'wikidata_id': item_id,
            'label': results[0].get('itemLabel', {}).get('value', ''),
            'description': results[0].get('itemDescription', {}).get('value', ''),
            'relationship_count': len(relationships),
            'relationships': relationships[:20],  # Top 20
        }

    def probe_domain(self, domain: str) -> Dict:
        """Get coverage summary for a domain."""
        if domain not in self.DOMAIN_QUERIES:
            return {'error': f'Unknown domain: {domain}'}

        results = self._sparql_query(self.DOMAIN_QUERIES[domain])

        # Extract unique companies
        companies = {}
        for r in results:
            company_id = r.get('company', {}).get('value', '').split('/')[-1]
            company_label = r.get('companyLabel', {}).get('value', '')
            if company_id and company_label:
                if company_id not in companies:
                    companies[company_id] = {
                        'id': company_id,
                        'label': company_label,
                        'relationships': []
                    }
                companies[company_id]['relationships'].append({
                    'relation': r.get('relationLabel', {}).get('value', ''),
                    'target': r.get('targetLabel', {}).get('value', ''),
                })

        return {
            'domain': domain,
            'total_entities': len(companies),
            'total_relationships': len(results),
            'entities': list(companies.values()),
        }


class OpenCorporatesProbe:
    """Probe OpenCorporates for company relationships."""

    API_BASE = "https://api.opencorporates.com/v0.4"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    def search_company(self, name: str, jurisdiction: str = "us") -> Dict:
        """Search for company in OpenCorporates."""
        url = f"{self.API_BASE}/companies/search?q={quote(name)}&jurisdiction_code={jurisdiction}"
        if self.api_key:
            url += f"&api_token={self.api_key}"

        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode('utf-8'))
                companies = data.get('results', {}).get('companies', [])
                return {
                    'found': len(companies) > 0,
                    'count': len(companies),
                    'companies': companies[:5],
                }
        except Exception as e:
            return {'found': False, 'error': str(e)}


class CoverageProbeAgent(FGIPAgent):
    """Meta-agent that probes external knowledge graphs for coverage gaps.

    Creates sentinel nodes that summarize:
    - What % of a domain we cover vs external graphs
    - Where we diverge from external data
    - High-priority entities we're missing
    """

    AGENT_NAME = "coverage-probe"

    # Domains relevant to FGIP thesis
    PROBE_DOMAINS = ['semiconductors', 'defense_contractors', 'investment_managers']

    # Priority entities we MUST have coverage for
    PRIORITY_ENTITIES = [
        # Big Three
        'blackrock', 'vanguard', 'state-street',
        # Semiconductor majors
        'intel', 'tsmc', 'samsung', 'micron', 'nvidia', 'amd', 'qualcomm',
        'globalfoundries', 'texas-instruments', 'broadcom', 'asml',
        # Defense
        'lockheed-martin', 'raytheon', 'northrop-grumman', 'boeing', 'general-dynamics',
        # CHIPS recipients
        'sk-hynix', 'samsung-electronics',
    ]

    def __init__(self, db):
        super().__init__(db, self.AGENT_NAME)
        self.wikidata = WikidataProbe()
        self.opencorporates = OpenCorporatesProbe()
        self.coverage_gaps: List[CoverageGap] = []
        self.sentinel_nodes: List[SentinelNode] = []

    def collect(self) -> Dict:
        """Get our current node/edge coverage."""
        conn = self.db.connect()

        # Get all our nodes
        nodes = conn.execute("""
            SELECT node_id, name, node_type
            FROM nodes
        """).fetchall()

        # Get edge counts per node
        edge_counts = dict(conn.execute("""
            SELECT node_id, SUM(cnt) as total FROM (
                SELECT from_node_id as node_id, COUNT(*) as cnt FROM edges GROUP BY from_node_id
                UNION ALL
                SELECT to_node_id as node_id, COUNT(*) as cnt FROM edges GROUP BY to_node_id
            ) GROUP BY node_id
        """).fetchall())

        # Get our edge types
        edge_types = [r[0] for r in conn.execute(
            "SELECT DISTINCT edge_type FROM edges"
        ).fetchall()]

        return {
            'nodes': {n[0]: {'name': n[1], 'type': n[2], 'edges': edge_counts.get(n[0], 0)}
                     for n in nodes},
            'edge_types': edge_types,
            'total_nodes': len(nodes),
            'total_edges': conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0],
        }

    def _normalize_name(self, name: str) -> str:
        """Normalize entity name for comparison."""
        name = name.lower().strip()
        # Remove common suffixes
        for suffix in [' inc', ' inc.', ' corp', ' corp.', ' corporation',
                       ' llc', ' ltd', ' limited', ' co', ' co.', ' company']:
            if name.endswith(suffix):
                name = name[:-len(suffix)]
        return name.replace(' ', '-').replace(',', '').replace('.', '')

    def _find_our_node(self, external_name: str, our_nodes: Dict) -> Optional[str]:
        """Find matching node in our graph."""
        normalized = self._normalize_name(external_name)

        # Direct match
        if normalized in our_nodes:
            return normalized

        # Fuzzy match - check if our node name contains external name
        for node_id, info in our_nodes.items():
            our_normalized = self._normalize_name(info.get('name', node_id))
            if normalized in our_normalized or our_normalized in normalized:
                return node_id

        return None

    def extract(self, collected: Dict) -> List[CoverageGap]:
        """Compare our coverage against external graphs.

        Strategy: Instead of pulling domain queries, we:
        1. Sample our high-connectivity nodes
        2. Check what Wikidata knows about them
        3. Compare relationship counts (they have vs we have)
        4. Create convergence/divergence scores
        """
        our_nodes = collected['nodes']
        gaps = []

        print(f"Probing external graphs for coverage comparison...")

        # 1. Check priority entities we MUST have
        priority_checked = 0
        priority_missing = 0
        for entity in self.PRIORITY_ENTITIES:
            entity_variants = [entity, entity.replace('-', ' '), entity.replace('-', ' ').title()]
            found_in_ours = any(v in our_nodes or self._normalize_name(v) in our_nodes
                               for v in entity_variants)

            if not found_in_ours:
                priority_missing += 1
                gaps.append(CoverageGap(
                    our_node_id=entity,
                    external_source='fgip_priority_list',
                    gap_type='missing_entity',
                    external_relationships=[],
                    our_relationships=[],
                    priority=9,
                    details=f"Priority entity missing from our graph: {entity}"
                ))
            priority_checked += 1

        # 2. Sample our nodes and compare relationship density
        # Get top 50 nodes by edge count
        sorted_nodes = sorted(
            [(k, v) for k, v in our_nodes.items()],
            key=lambda x: x[1].get('edges', 0),
            reverse=True
        )[:50]

        total_probed = 0
        total_relationship_gap = 0
        our_total_edges = 0
        external_total_rels = 0

        for node_id, info in sorted_nodes[:10]:  # Probe top 10 (rate limit)
            entity_name = info.get('name', node_id.replace('-', ' ').title())
            our_edges = info.get('edges', 0)
            our_total_edges += our_edges

            wd_result = self.wikidata.probe_entity(entity_name)
            if wd_result.get('found'):
                total_probed += 1
                ext_rels = wd_result.get('relationship_count', 0)
                external_total_rels += ext_rels

                # Check for relationship density gap
                if ext_rels > our_edges * 3 and ext_rels > 10:
                    gap_ratio = ext_rels / max(our_edges, 1)
                    gaps.append(CoverageGap(
                        our_node_id=node_id,
                        external_source='wikidata',
                        gap_type='relationship_density_gap',
                        external_relationships=[],
                        our_relationships=[],
                        priority=min(8, int(gap_ratio)),
                        details=f"Wikidata has {ext_rels} relationships, we have {our_edges} (ratio: {gap_ratio:.1f}x)"
                    ))
                    total_relationship_gap += (ext_rels - our_edges)

        # 3. Create summary sentinel node
        coverage_ratio = total_probed / len(sorted_nodes[:10]) if sorted_nodes else 0
        density_ratio = our_total_edges / max(external_total_rels, 1) if total_probed > 0 else 0

        self.sentinel_nodes.append(SentinelNode(
            node_id="coverage:wikidata:overall",
            source='wikidata',
            domain='all',
            our_coverage=total_probed,
            external_total=len(sorted_nodes[:10]),
            coverage_ratio=coverage_ratio,
            missing_high_priority=[e for e in self.PRIORITY_ENTITIES
                                   if e not in our_nodes and
                                   self._normalize_name(e) not in our_nodes][:10],
            divergence_count=len([g for g in gaps if g.gap_type == 'relationship_density_gap']),
            last_probed=datetime.now(timezone.utc).isoformat(),
            metadata={
                'priority_entities_checked': priority_checked,
                'priority_entities_missing': priority_missing,
                'relationship_density_ratio': density_ratio,
                'total_relationship_gap': total_relationship_gap,
                'our_edges_sampled': our_total_edges,
                'external_rels_sampled': external_total_rels,
            }
        ))

        # 4. Convergence/Divergence summary
        print(f"  Probed {total_probed} entities in Wikidata")
        print(f"  Priority entities missing: {priority_missing}/{priority_checked}")
        print(f"  Relationship density ratio: {density_ratio:.2f} (us/them)")
        print(f"  Total relationship gap: {total_relationship_gap}")

        self.coverage_gaps = gaps
        return gaps

    def propose(self, gaps: List[CoverageGap]) -> Dict:
        """Generate proposals for filling coverage gaps."""
        conn = self.db.connect()
        timestamp = datetime.now(timezone.utc).isoformat()

        proposed_nodes = []
        proposed_edges = []

        # 1. Propose sentinel nodes for coverage tracking
        for sentinel in self.sentinel_nodes:
            node_id = sentinel.node_id
            existing = conn.execute(
                "SELECT node_id FROM nodes WHERE node_id = ?",
                (node_id,)
            ).fetchone()

            if not existing:
                sha256 = hashlib.sha256(
                    f"{node_id}:{timestamp}".encode()
                ).hexdigest()

                conn.execute("""
                    INSERT INTO nodes (node_id, node_type, name, created_at, sha256, metadata)
                    VALUES (?, 'SENTINEL', ?, ?, ?, ?)
                """, (
                    node_id,
                    f"Coverage: {sentinel.source} {sentinel.domain}",
                    timestamp,
                    sha256,
                    json.dumps(asdict(sentinel))
                ))
                proposed_nodes.append(node_id)

        conn.commit()

        # 2. Propose edges for high-priority missing entities
        for gap in gaps:
            if gap.gap_type == 'missing_entity' and gap.priority >= 7:
                # Propose adding this node
                proposed_nodes.append({
                    'node_id': gap.our_node_id,
                    'source': gap.external_source,
                    'priority': gap.priority,
                    'details': gap.details,
                })

        # 3. Write coverage report
        report = {
            'timestamp': timestamp,
            'sentinel_nodes': [asdict(s) for s in self.sentinel_nodes],
            'coverage_gaps': [asdict(g) for g in gaps],
            'summary': {
                'total_gaps': len(gaps),
                'missing_entities': len([g for g in gaps if g.gap_type == 'missing_entity']),
                'missing_relationships': len([g for g in gaps if g.gap_type == 'missing_relationship']),
                'high_priority_gaps': len([g for g in gaps if g.priority >= 7]),
                'domains_probed': len(self.sentinel_nodes),
                'average_coverage': sum(s.coverage_ratio for s in self.sentinel_nodes) / len(self.sentinel_nodes) if self.sentinel_nodes else 0,
            },
            'proposed_nodes': proposed_nodes,
        }

        # Write receipt
        receipts_dir = Path(__file__).parent.parent.parent / "receipts" / "coverage"
        receipts_dir.mkdir(parents=True, exist_ok=True)
        receipt_path = receipts_dir / f"coverage_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        receipt_path.write_text(json.dumps(report, indent=2))

        return {
            'agent': self.AGENT_NAME,
            'sentinel_nodes_created': len([n for n in proposed_nodes if isinstance(n, str)]),
            'coverage_gaps_found': len(gaps),
            'high_priority_missing': len([g for g in gaps if g.priority >= 7]),
            'average_coverage_ratio': report['summary']['average_coverage'],
            'receipt': str(receipt_path),
        }

    def run(self) -> Dict:
        """Run full coverage probe cycle."""
        collected = self.collect()
        gaps = self.extract(collected)
        return self.propose(gaps)


def main():
    """CLI for coverage probe."""
    import argparse
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from fgip.db import FGIPDatabase

    parser = argparse.ArgumentParser(description="FGIP Coverage Probe")
    parser.add_argument("db", type=str, help="Database path")
    parser.add_argument("--entity", type=str, help="Probe specific entity")
    parser.add_argument("--domain", type=str, choices=['semiconductors', 'defense_contractors', 'investment_managers'],
                       help="Probe specific domain")
    parser.add_argument("--json", action="store_true", help="JSON output")

    args = parser.parse_args()

    db = FGIPDatabase(args.db)
    agent = CoverageProbeAgent(db)

    if args.entity:
        # Single entity probe
        result = agent.wikidata.probe_entity(args.entity)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result.get('found'):
                print(f"Found: {result['label']} ({result['wikidata_id']})")
                print(f"Description: {result.get('description', 'N/A')}")
                print(f"Relationships: {result['relationship_count']}")
            else:
                print(f"Not found: {args.entity}")
    elif args.domain:
        # Domain probe
        result = agent.wikidata.probe_domain(args.domain)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Domain: {result['domain']}")
            print(f"Entities: {result['total_entities']}")
            print(f"Relationships: {result['total_relationships']}")
    else:
        # Full probe
        result = agent.run()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Coverage Probe Results:")
            print(f"  Sentinel nodes created: {result['sentinel_nodes_created']}")
            print(f"  Coverage gaps found: {result['coverage_gaps_found']}")
            print(f"  High priority missing: {result['high_priority_missing']}")
            print(f"  Average coverage: {result['average_coverage_ratio']*100:.1f}%")
            print(f"  Receipt: {result['receipt']}")


if __name__ == "__main__":
    main()
