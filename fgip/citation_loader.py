"""FGIP Citation Loader - Claims-first unification (Square-Two).

This module loads the full citation database from:
1. fgip_all_source_urls.txt (~698 sources with auto-tiering)
2. fgip_citation_database.md (~200+ claims)

Build order:
1. Load all source URLs with auto-tiering
2. Parse claims from markdown tables
3. Link claims to sources via claim_sources
4. Extract nodes from known entities
5. Create edges backed by claims (Square-One compliant)
"""

import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional, Dict

from .db import FGIPDatabase
from .schema import (
    Source, Claim, ClaimStatus, Node, Edge, NodeType, EdgeType,
    Receipt, compute_sha256, extract_domain, auto_tier_domain
)


# Topic mapping from section headers in citation database
TOPIC_MAP = {
    'I': 'Lobbying',
    'II': 'Judicial',
    'III': 'Ownership',
    'IV': 'Downstream',
    'V': 'Censorship',
    'VI': 'Reshoring',
    'VII': 'ThinkTank',
    'VIII': 'IndependentMedia',
    'IX': 'Fraud',
    'X': 'Stablecoin',
    'XI': 'ForeignPolicy',
}

# Known entities with their types (seed data)
KNOWN_ENTITIES: Dict[str, Tuple[str, str]] = {
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
    'GAO': ('ORGANIZATION', 'gao'),
    'SEC': ('ORGANIZATION', 'sec'),
}

# Seed edges - core relationships with claim patterns
SEED_EDGES = [
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


class CitationLoader:
    """Load sources and claims from citation database (Square-Two)."""

    def __init__(self, db: FGIPDatabase):
        self.db = db
        self._claim_num = 1

    def _get_next_claim_id(self) -> str:
        """Get next sequential claim ID."""
        claim_id = f"FGIP-{self._claim_num:06d}"
        self._claim_num += 1
        return claim_id

    def _extract_urls(self, text: str) -> List[str]:
        """Extract all URLs from text."""
        url_pattern = r'https?://[^\s<>"\')\]]+[^\s<>"\')\],.]'
        urls = re.findall(url_pattern, text)

        cleaned = []
        for url in urls:
            while url and url[-1] in '.,;:)]':
                url = url[:-1]
            if url:
                cleaned.append(url)

        return cleaned

    def _determine_required_tier(self, claim_text: str) -> int:
        """
        Determine required source tier based on claim content.

        Tier 0 required for:
        - Ownership percentages
        - Dollar amounts (lobbying spend, fines)
        - Legislative outcomes
        - Court rulings

        Tier 1 required for:
        - Market performance claims

        Tier 2 acceptable for:
        - Interpretive/analytical claims
        """
        text_lower = claim_text.lower()

        # Tier 0 indicators
        tier_0_patterns = [
            r'\d+\.?\d*\s*%',  # Percentages
            r'\$[\d,]+[mb]?',  # Dollar amounts
            r'owns?\s+\d+',  # Ownership claims
            r'(passed|signed|enacted|ruled|decided)',  # Legislative/judicial
            r'(congress|senate|house|supreme court)',  # Government bodies
            r'(sec\s+fil|13f|edgar)',  # SEC filings
            r'(foia|gao|audit)',  # Government documents
        ]

        for pattern in tier_0_patterns:
            if re.search(pattern, text_lower):
                return 0

        # Tier 1 indicators
        tier_1_patterns = [
            r'\+\d+%\s+(ytd|yoy)',  # Market performance
            r'(backlog|revenue|earnings)',  # Financial claims
            r'(jobs? (lost|created|added))',  # Employment claims
        ]

        for pattern in tier_1_patterns:
            if re.search(pattern, text_lower):
                return 1

        # Default to Tier 2
        return 2

    def load_source_urls(self, filepath: str) -> Receipt:
        """
        Load source URLs from text file with auto-tiering.

        Args:
            filepath: Path to fgip_all_source_urls.txt

        Returns:
            Receipt with load statistics
        """
        input_hash = compute_sha256({"filepath": filepath})
        path = Path(filepath)

        if not path.exists():
            return Receipt(
                receipt_id=str(uuid.uuid4()),
                operation="load_source_urls",
                timestamp=datetime.utcnow().isoformat() + "Z",
                input_hash=input_hash,
                output_hash=compute_sha256({"error": "file not found"}),
                success=False,
                details={"error": f"File not found: {filepath}"}
            )

        loaded = 0
        skipped = 0
        tier_counts = {0: 0, 1: 0, 2: 0}
        errors = []

        with open(path) as f:
            for line_num, line in enumerate(f, 1):
                url = line.strip()
                if not url or url.startswith('#'):
                    continue

                try:
                    source = Source.from_url(url)
                    if self.db.insert_source(source):
                        loaded += 1
                        tier_counts[source.tier] = tier_counts.get(source.tier, 0) + 1
                    else:
                        skipped += 1
                except Exception as e:
                    errors.append({"line": line_num, "url": url[:50], "error": str(e)})

        details = {
            "loaded": loaded,
            "skipped": skipped,
            "tier_0": tier_counts.get(0, 0),
            "tier_1": tier_counts.get(1, 0),
            "tier_2": tier_counts.get(2, 0),
            "errors": errors[:10],
        }

        receipt = Receipt(
            receipt_id=str(uuid.uuid4()),
            operation="load_source_urls",
            timestamp=datetime.utcnow().isoformat() + "Z",
            input_hash=input_hash,
            output_hash=compute_sha256(details),
            success=True,
            details=details,
        )

        return receipt

    def parse_citation_database(self, filepath: str) -> Receipt:
        """
        Parse claims from citation database markdown file.

        Args:
            filepath: Path to fgip_citation_database.md

        Returns:
            Receipt with parse statistics
        """
        input_hash = compute_sha256({"filepath": filepath})
        path = Path(filepath)

        if not path.exists():
            return Receipt(
                receipt_id=str(uuid.uuid4()),
                operation="parse_citation_database",
                timestamp=datetime.utcnow().isoformat() + "Z",
                input_hash=input_hash,
                output_hash=compute_sha256({"error": "file not found"}),
                success=False,
                details={"error": f"File not found: {filepath}"}
            )

        content = path.read_text()
        lines = content.split('\n')

        claims_loaded = 0
        links_created = 0
        current_topic = 'General'
        topic_counts = {}
        status_counts = {"PARTIAL": 0, "MISSING": 0}
        errors = []

        # Initialize claim counter from database
        conn = self.db.connect()
        row = conn.execute("SELECT next_claim_num FROM claim_counter WHERE id = 1").fetchone()
        self._claim_num = row[0] if row else 1

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Detect section headers like "# I. LOBBYING NETWORK"
            section_match = re.match(r'^#\s+(I+|IV|V|VI+|IX|X|XI)\.?\s+', line)
            if section_match:
                roman = section_match.group(1)
                current_topic = TOPIC_MAP.get(roman, 'General')
                i += 1
                continue

            # Detect table rows: | Claim | Source |
            if line.startswith('|') and '|' in line[1:]:
                parts = [p.strip() for p in line.split('|')]
                parts = [p for p in parts if p]  # Remove empty parts

                # Skip header rows
                if len(parts) >= 2 and parts[0].lower() in ['claim', 'company', 'event', 'entity', 'from']:
                    i += 1
                    continue

                # Skip separator rows
                if len(parts) >= 1 and all(c in '-|:' for c in parts[0]):
                    i += 1
                    continue

                # Parse claim row
                if len(parts) >= 2:
                    claim_text = parts[0]
                    source_text = parts[-1]  # Last column is source

                    # Handle 3-column tables (Company | Claim | Source)
                    if len(parts) >= 3:
                        # Check if first column looks like a company name
                        if not any(c in parts[0].lower() for c in ['%', '$', 'billion', 'million', 'passed', 'signed']):
                            claim_text = f"{parts[0]}: {parts[1]}"
                            source_text = parts[-1]

                    # Skip if claim text is too short
                    if len(claim_text) < 10:
                        i += 1
                        continue

                    # Generate claim_id
                    claim_id = self._get_next_claim_id()

                    # Extract URLs from source text
                    urls = self._extract_urls(source_text)
                    status = ClaimStatus.PARTIAL if urls else ClaimStatus.MISSING

                    # Determine required_tier based on claim content
                    required_tier = self._determine_required_tier(claim_text)

                    # Create claim
                    claim = Claim(
                        claim_id=claim_id,
                        claim_text=claim_text,
                        topic=current_topic,
                        status=status,
                        required_tier=required_tier,
                    )

                    try:
                        if self.db.insert_claim(claim):
                            claims_loaded += 1
                            topic_counts[current_topic] = topic_counts.get(current_topic, 0) + 1
                            status_counts[status.value] = status_counts.get(status.value, 0) + 1

                            # Link to sources
                            for url in urls:
                                source = Source.from_url(url)
                                self.db.insert_source(source)  # Ensure source exists
                                if self.db.link_claim_source(claim_id, source.source_id):
                                    links_created += 1
                    except Exception as e:
                        errors.append({"claim_id": claim_id, "error": str(e)})

            i += 1

        # Update claim counter
        conn.execute("UPDATE claim_counter SET next_claim_num = ? WHERE id = 1", (self._claim_num,))
        conn.commit()

        details = {
            "claims_loaded": claims_loaded,
            "links_created": links_created,
            "by_topic": topic_counts,
            "by_status": status_counts,
            "errors": errors[:10],
        }

        receipt = Receipt(
            receipt_id=str(uuid.uuid4()),
            operation="parse_citation_database",
            timestamp=datetime.utcnow().isoformat() + "Z",
            input_hash=input_hash,
            output_hash=compute_sha256(details),
            success=True,
            details=details,
        )

        return receipt

    def extract_nodes_from_claims(self) -> Receipt:
        """
        Extract entity nodes from loaded claims using KNOWN_ENTITIES patterns.

        Returns:
            Receipt with extraction statistics
        """
        input_hash = compute_sha256({"operation": "extract_nodes"})
        nodes_created = 0
        nodes_by_type = {}
        errors = []

        # First pass: add all known entities
        for name, (node_type_str, node_id) in KNOWN_ENTITIES.items():
            # Use canonical name (first occurrence for each node_id)
            existing = self.db.get_node(node_id)
            if existing:
                continue

            try:
                node_type = NodeType(node_type_str)
                node = Node(
                    node_id=node_id,
                    node_type=node_type,
                    name=name,
                    aliases=[],
                )
                receipt = self.db.insert_node(node)
                if receipt.success:
                    nodes_created += 1
                    nodes_by_type[node_type_str] = nodes_by_type.get(node_type_str, 0) + 1
            except Exception as e:
                errors.append({"node_id": node_id, "error": str(e)})

        details = {
            "nodes_created": nodes_created,
            "by_type": nodes_by_type,
            "errors": errors[:10],
        }

        return Receipt(
            receipt_id=str(uuid.uuid4()),
            operation="extract_nodes_from_claims",
            timestamp=datetime.utcnow().isoformat() + "Z",
            input_hash=input_hash,
            output_hash=compute_sha256(details),
            success=True,
            details=details,
        )

    def create_edges_from_claims(self) -> Receipt:
        """
        Create edges backed by claim_ids from seed edge patterns.

        Returns:
            Receipt with edge creation statistics
        """
        input_hash = compute_sha256({"operation": "create_edges"})
        edges_created = 0
        edges_by_type = {}
        errors = []

        conn = self.db.connect()

        for from_node, to_node, relationship, detail, topic in SEED_EDGES:
            # Find a matching claim
            cursor = conn.execute("""
                SELECT claim_id FROM claims
                WHERE topic = ?
                AND (
                    LOWER(claim_text) LIKE LOWER(?)
                    OR LOWER(claim_text) LIKE LOWER(?)
                )
                LIMIT 1
            """, (topic, f'%{from_node.replace("-", " ")}%', f'%{to_node.replace("-", " ")}%'))

            row = cursor.fetchone()
            claim_id = row[0] if row else None

            # If no matching claim, create a placeholder claim
            if not claim_id:
                claim_id = self.db.get_next_claim_id()
                claim_text = f"{from_node.replace('-', ' ').title()} {relationship.replace('_', ' ').lower()} {to_node.replace('-', ' ').title()}"
                if detail:
                    claim_text += f" ({detail})"

                claim = Claim(
                    claim_id=claim_id,
                    claim_text=claim_text,
                    topic=topic,
                    status=ClaimStatus.MISSING,
                    required_tier=0,
                )
                self.db.insert_claim(claim)

            # Create edge
            try:
                edge_type = EdgeType(relationship)
                edge_id = f"{edge_type.value.lower()}_{from_node}_{to_node}"

                edge = Edge(
                    edge_id=edge_id,
                    edge_type=edge_type,
                    from_node_id=from_node,
                    to_node_id=to_node,
                    claim_id=claim_id,
                    notes=detail,
                )

                receipt = self.db.insert_edge(edge)
                if receipt.success:
                    edges_created += 1
                    edges_by_type[relationship] = edges_by_type.get(relationship, 0) + 1
            except Exception as e:
                errors.append({
                    "from": from_node,
                    "to": to_node,
                    "relationship": relationship,
                    "error": str(e)
                })

        details = {
            "edges_created": edges_created,
            "by_type": edges_by_type,
            "errors": errors[:10],
        }

        return Receipt(
            receipt_id=str(uuid.uuid4()),
            operation="create_edges_from_claims",
            timestamp=datetime.utcnow().isoformat() + "Z",
            input_hash=input_hash,
            output_hash=compute_sha256(details),
            success=True,
            details=details,
        )

    def load_all(self, sources_file: str, citations_file: str) -> Receipt:
        """
        Full pipeline orchestrator: load sources, claims, nodes, and edges.

        Args:
            sources_file: Path to fgip_all_source_urls.txt
            citations_file: Path to fgip_citation_database.md

        Returns:
            Receipt with complete load statistics
        """
        input_hash = compute_sha256({
            "sources_file": sources_file,
            "citations_file": citations_file,
        })

        results = {}

        # Step 1: Load source URLs
        sources_receipt = self.load_source_urls(sources_file)
        results["sources"] = sources_receipt.details

        # Step 2: Parse citation database
        claims_receipt = self.parse_citation_database(citations_file)
        results["claims"] = claims_receipt.details

        # Step 3: Extract nodes
        nodes_receipt = self.extract_nodes_from_claims()
        results["nodes"] = nodes_receipt.details

        # Step 4: Create edges
        edges_receipt = self.create_edges_from_claims()
        results["edges"] = edges_receipt.details

        # Get final statistics
        stats = self.db.get_stats()
        evidence = self.db.get_evidence_status()

        results["final_stats"] = {
            "total_sources": stats["sources"],
            "total_claims": stats["claims"],
            "total_nodes": stats["nodes"],
            "total_edges": stats["edges"],
            "evidence_coverage_pct": evidence["evidence_coverage_pct"],
            "tier_01_coverage_pct": evidence["tier_01_coverage_pct"],
        }

        return Receipt(
            receipt_id=str(uuid.uuid4()),
            operation="load_all",
            timestamp=datetime.utcnow().isoformat() + "Z",
            input_hash=input_hash,
            output_hash=compute_sha256(results),
            success=True,
            details=results,
        )
