"""Citation Loader Agent - Batch loads claims from fgip_citation_database.md.

Parses the markdown citation database and proposes claims/edges through
the staging pipeline. Human reviews with `fgip accept/reject`.
"""

import re
import hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass, field

from .base import FGIPAgent, Artifact, StructuredFact, ProposedClaim, ProposedEdge, ProposedNode
from ..schema import (
    EdgeType, NodeType, extract_domain, auto_tier_domain,
    TIER_0_DOMAINS, TIER_1_DOMAINS
)


@dataclass
class ParsedClaim:
    """A claim parsed from the citation database."""
    claim_text: str
    source_url: str
    section: str
    subsection: str
    source_tier: int
    line_number: int


# Pattern definitions for extracting relationships from claim text
RELATIONSHIP_PATTERNS = [
    # LOBBIED_FOR patterns
    (r'(.+?) spent \$[\d.]+[BMK]?\+? (?:total )?lobbying', 'LOBBIED_FOR', 'entity_only'),
    (r'(.+?) lobbied for (.+)', 'LOBBIED_FOR', 'entity_pair'),
    (r'(.+?) lobbied on (.+)', 'LOBBIED_FOR', 'entity_pair'),

    # FILED_AMICUS patterns
    (r'(\d+) amicus briefs? filed', 'FILED_AMICUS', 'count_only'),
    (r'(.+?) (?:filed|submitted) amicus', 'FILED_AMICUS', 'entity_only'),

    # OWNS_SHARES patterns
    (r'(.+?) owns ([\d.]+)% of (.+)', 'OWNS_SHARES', 'ownership'),
    (r'(.+?) (?:is )?(?:the )?largest (?:share)?holder', 'OWNS_SHARES', 'entity_only'),

    # EMPLOYED patterns
    (r'(.+?) was (.+?) lobbyist', 'EMPLOYED', 'employer_role'),
    (r'(.+?) became (?:a )?lobbyist', 'EMPLOYED', 'entity_only'),

    # DONATED_TO patterns
    (r'(.+?) provided.+benefits to (.+)', 'DONATED_TO', 'entity_pair'),
    (r'(.+?) funded (.+)', 'DONATED_TO', 'entity_pair'),

    # ENABLED/CAUSED patterns
    (r'(.+?) led to (.+)', 'ENABLED', 'entity_pair'),
    (r'(.+?) caused (.+)', 'CAUSED', 'entity_pair'),

    # FOUNDED_BY patterns (map to MEMBER_OF for now)
    (r'(.+?) [Ff]ounded (?:by|with) (.+)', 'MEMBER_OF', 'founder'),

    # APPOINTED_BY patterns
    (r'(.+?) appointed (?:by )?(.+)', 'APPOINTED_BY', 'entity_pair'),

    # MARRIED_TO patterns
    (r'(.+?) (?:is )?(?:the )?(?:wife|husband|spouse) of (.+)', 'MARRIED_TO', 'entity_pair'),

    # MEMBER_OF patterns
    (r'(.+?) (?:is )?(?:a )?member of (.+)', 'MEMBER_OF', 'entity_pair'),
    (r'(\d+) (?:current )?Supreme Court justices connected', 'MEMBER_OF', 'count_scotus'),

    # INVESTED_IN patterns
    (r'(.+?) invested (?:\$[\d.]+[BMK]?\+? )?in (.+)', 'INVESTED_IN', 'entity_pair'),
]


class CitationLoaderAgent(FGIPAgent):
    """Parses citation_database.md and proposes claims/edges.

    This agent reads a markdown file containing structured citation tables
    and extracts claims and relationships for staging review.

    The citation database format expected:
    - Sections marked with # headers
    - Tables with | Claim | Source | format
    - Sources as URLs or text descriptions
    """

    def __init__(self, db, citation_file: str = None):
        """Initialize the citation loader agent.

        Args:
            db: FGIPDatabase instance
            citation_file: Path to the citation database markdown file
        """
        super().__init__(
            db=db,
            name="citation_loader",
            description="Batch loader from citation database markdown"
        )
        self.citation_file = citation_file
        self._current_section = ""
        self._current_subsection = ""
        self._existing_nodes = None  # Lazy cache

    def set_citation_file(self, path: str):
        """Set the citation file path (for CLI integration)."""
        self.citation_file = path

    def collect(self) -> List[Artifact]:
        """Read citation_database.md as single artifact.

        Returns:
            List containing a single Artifact for the markdown file
        """
        if not self.citation_file:
            raise ValueError("No citation file specified. Use --file argument.")

        path = Path(self.citation_file)
        if not path.exists():
            raise FileNotFoundError(f"Citation file not found: {self.citation_file}")

        content = path.read_text(encoding='utf-8')
        content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()

        artifact = Artifact(
            url=f"file://{path.absolute()}",
            artifact_type="markdown",
            local_path=str(path.absolute()),
            content_hash=content_hash,
            fetched_at=datetime.utcnow().isoformat() + "Z",
            metadata={
                "file_name": path.name,
                "line_count": len(content.splitlines()),
            }
        )

        return [artifact]

    def extract(self, artifacts: List[Artifact]) -> List[StructuredFact]:
        """Parse markdown tables, extract claims and relationships.

        Args:
            artifacts: List containing the markdown file artifact

        Returns:
            List of StructuredFact objects extracted from tables
        """
        if not artifacts:
            return []

        artifact = artifacts[0]
        content = Path(artifact.local_path).read_text(encoding='utf-8')

        parsed_claims = self._parse_markdown_tables(content)
        facts = []

        for pc in parsed_claims:
            # Try to extract relationship from claim text
            relationship = self._extract_relationship(pc.claim_text)

            if relationship:
                fact_type = relationship['edge_type'].lower()
                subject = relationship.get('from_entity', '')
                predicate = relationship['edge_type']
                obj = relationship.get('to_entity', pc.claim_text)
            else:
                # Generic claim without extracted relationship
                fact_type = 'claim'
                subject = pc.section
                predicate = 'STATES'
                obj = pc.claim_text

            fact = StructuredFact(
                fact_type=fact_type,
                subject=subject,
                predicate=predicate,
                object=obj,
                source_artifact=artifact,
                confidence=0.8 if pc.source_tier <= 1 else 0.6,
                raw_text=pc.claim_text,
                metadata={
                    'section': pc.section,
                    'subsection': pc.subsection,
                    'source_url': pc.source_url,
                    'source_tier': pc.source_tier,
                    'line_number': pc.line_number,
                    'relationship': relationship,
                }
            )
            facts.append(fact)

        return facts

    def propose(self, facts: List[StructuredFact]) -> Tuple[List[ProposedClaim], List[ProposedEdge], List[ProposedNode]]:
        """Generate proposals with appropriate edge types.

        Args:
            facts: List of StructuredFact objects

        Returns:
            Tuple of (proposed_claims, proposed_edges, proposed_nodes)
        """
        claims = []
        edges = []
        proposed_node_ids = {}  # Track proposed nodes to avoid duplicates
        skipped_edges = []  # Track edges skipped due to validation issues

        for fact in facts:
            meta = fact.metadata
            relationship = meta.get('relationship')

            # Create a ProposedClaim for every fact
            claim_id = self._generate_proposal_id()
            source_url = meta.get('source_url', '')

            # Determine tier from URL
            tier_text = self._tier_to_text(meta.get('source_tier', 2))

            claim = ProposedClaim(
                proposal_id=claim_id,
                claim_text=fact.raw_text,
                topic=meta.get('section', 'Unknown'),
                agent_name=self.name,
                source_url=source_url if source_url.startswith('http') else None,
                artifact_path=fact.source_artifact.local_path,
                artifact_hash=fact.source_artifact.content_hash,
                reasoning=f"Extracted from citation database section '{meta.get('subsection', meta.get('section'))}'. Source tier: {tier_text}",
                promotion_requirement=self._get_promotion_requirement(meta.get('source_tier', 2)),
            )
            claims.append(claim)

            # Create ProposedEdge if we extracted a relationship
            if relationship and relationship.get('from_entity') and relationship.get('to_entity'):
                edge_type = relationship['edge_type']

                # Convert entity names to node IDs
                from_entity = relationship['from_entity']
                to_entity = relationship['to_entity']

                # Skip Franken-nodes (multiple entities conjoined)
                if self._is_multi_entity(from_entity) or self._is_multi_entity(to_entity):
                    # Log skipped edge for manual review
                    skipped_edges.append({
                        'claim': fact.raw_text,
                        'reason': f"Multi-entity detected: '{from_entity}' or '{to_entity}' needs manual split",
                    })
                    continue

                # Try to normalize to existing node IDs first
                from_node = self._normalize_to_existing_node(from_entity) or self._slugify(from_entity)
                to_node = self._normalize_to_existing_node(to_entity) or self._slugify(to_entity)

                # Track node proposals for missing entities (only if not existing)
                for node_id, entity_name, is_from in [(from_node, from_entity, True), (to_node, to_entity, False)]:
                    if node_id and node_id not in proposed_node_ids and not self._node_exists(node_id):
                        node_type = self._infer_node_type(edge_type, is_from)
                        proposed_node_ids[node_id] = {
                            'node_id': node_id,
                            'name': entity_name,
                            'node_type': node_type,
                            'source_url': source_url if source_url.startswith('http') else None,
                        }

                # Determine confidence based on tier and edge type
                is_inferential = edge_type in {'ENABLED', 'CAUSED', 'CONTRIBUTED_TO',
                                                'FACILITATED', 'PROFITED_FROM'}
                base_conf = 0.6 if is_inferential else 0.8
                tier_modifier = 0.2 if meta.get('source_tier', 2) == 0 else (
                    0.1 if meta.get('source_tier', 2) == 1 else 0
                )

                edge = ProposedEdge(
                    proposal_id=self._generate_proposal_id(),
                    from_node=from_node,
                    to_node=to_node,
                    relationship=edge_type,
                    agent_name=self.name,
                    detail=relationship.get('detail', fact.raw_text),
                    proposed_claim_id=claim_id,
                    confidence=min(1.0, base_conf + tier_modifier),
                    reasoning=f"Relationship extracted from: \"{fact.raw_text}\"",
                    promotion_requirement=f"Verify edge with {tier_text} source" if meta.get('source_tier', 2) > 0 else None,
                )
                edges.append(edge)

        # Create ProposedNode objects for all missing nodes
        nodes = []
        for node_info in proposed_node_ids.values():
            node = ProposedNode(
                proposal_id=self._generate_proposal_id(),
                node_id=node_info['node_id'],
                node_type=node_info['node_type'],
                name=node_info['name'],
                agent_name=self.name,
                source_url=node_info.get('source_url'),
                reasoning=f"Entity referenced in edge proposal. Type inferred from relationship context.",
            )
            nodes.append(node)

        # Log skipped edges for review
        if skipped_edges:
            import sys
            print(f"\n=== Skipped {len(skipped_edges)} edges due to validation ===", file=sys.stderr)
            for skip in skipped_edges[:5]:
                print(f"  - {skip['reason']}", file=sys.stderr)
            if len(skipped_edges) > 5:
                print(f"  ... and {len(skipped_edges) - 5} more", file=sys.stderr)

        return claims, edges, nodes

    def _node_exists(self, node_id: str) -> bool:
        """Check if a node exists in the database.

        Args:
            node_id: The node ID to check

        Returns:
            True if node exists
        """
        existing = self._get_existing_nodes()
        return node_id in existing

    def _parse_markdown_tables(self, content: str) -> List[ParsedClaim]:
        """Parse markdown content and extract claims from tables.

        Args:
            content: Markdown file content

        Returns:
            List of ParsedClaim objects
        """
        claims = []
        lines = content.splitlines()
        current_section = ""
        current_subsection = ""

        # Regex for markdown tables: | text | text |
        table_row_pattern = re.compile(r'^\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|')
        header_pattern = re.compile(r'^(#{1,6})\s+(.+)$')
        separator_pattern = re.compile(r'^\|[-:| ]+\|$')

        in_table = False

        for line_num, line in enumerate(lines, 1):
            line = line.strip()

            # Track section headers
            header_match = header_pattern.match(line)
            if header_match:
                level = len(header_match.group(1))
                title = header_match.group(2).strip()
                if level <= 2:
                    current_section = title
                    current_subsection = ""
                else:
                    current_subsection = title
                in_table = False
                continue

            # Skip empty lines
            if not line:
                in_table = False
                continue

            # Skip table separators
            if separator_pattern.match(line):
                in_table = True
                continue

            # Parse table rows
            row_match = table_row_pattern.match(line)
            if row_match:
                cell1 = row_match.group(1).strip()
                cell2 = row_match.group(2).strip()

                # Skip header rows
                if cell1.lower() in ('claim', 'company', '-------', '---'):
                    in_table = True
                    continue

                # Skip if first cell looks like a separator
                if set(cell1) <= set('-|: '):
                    continue

                # Determine if cell2 is a URL or description
                source_url = cell2
                source_tier = self._detect_tier(cell2)

                # For company-specific tables (3 columns)
                three_col = re.match(r'^\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|', line)
                if three_col:
                    company = three_col.group(1).strip()
                    claim_text = three_col.group(2).strip()
                    source_url = three_col.group(3).strip()
                    source_tier = self._detect_tier(source_url)
                    # Prepend company to claim for context
                    if company.lower() not in claim_text.lower():
                        claim_text = f"{company}: {claim_text}"
                    cell1 = claim_text

                claims.append(ParsedClaim(
                    claim_text=cell1,
                    source_url=source_url,
                    section=current_section,
                    subsection=current_subsection,
                    source_tier=source_tier,
                    line_number=line_num,
                ))

        return claims

    def _detect_tier(self, source_text: str) -> int:
        """Detect source tier from URL or description.

        Args:
            source_text: URL or source description

        Returns:
            Tier number (0=Primary, 1=Journalism, 2=Commentary)
        """
        if not source_text:
            return 2

        # Extract URL from markdown link if present
        url_match = re.search(r'https?://[^\s\)]+', source_text)
        if url_match:
            url = url_match.group(0)
            domain = extract_domain(url)
            return auto_tier_domain(domain)

        # Check for tier indicators in text
        text_lower = source_text.lower()
        if any(t0 in text_lower for t0 in ['sec', 'congress', 'gao', 'federal reserve', 'court', 'government']):
            return 0
        if any(t1 in text_lower for t1 in ['opensecrets', 'propublica', 'reuters', 'academic']):
            return 1

        return 2

    def _extract_relationship(self, claim_text: str) -> Optional[Dict[str, Any]]:
        """Extract entity relationship from claim text.

        Args:
            claim_text: The claim text to analyze

        Returns:
            Dict with edge_type, from_entity, to_entity, detail or None
        """
        for pattern, edge_type, pattern_type in RELATIONSHIP_PATTERNS:
            match = re.search(pattern, claim_text, re.IGNORECASE)
            if match:
                result = {
                    'edge_type': edge_type,
                    'pattern_type': pattern_type,
                    'detail': claim_text,
                }

                if pattern_type == 'entity_pair':
                    result['from_entity'] = self._clean_entity(match.group(1))
                    result['to_entity'] = self._clean_entity(match.group(2))

                elif pattern_type == 'ownership':
                    result['from_entity'] = self._clean_entity(match.group(1))
                    result['to_entity'] = self._clean_entity(match.group(3))
                    result['detail'] = f"{match.group(2)}% ownership"

                elif pattern_type == 'entity_only':
                    result['from_entity'] = self._clean_entity(match.group(1))
                    result['to_entity'] = None  # Will need manual review

                elif pattern_type == 'employer_role':
                    result['from_entity'] = self._clean_entity(match.group(1))
                    result['to_entity'] = self._clean_entity(match.group(2))

                elif pattern_type == 'founder':
                    result['from_entity'] = self._clean_entity(match.group(2))  # Founder
                    result['to_entity'] = self._clean_entity(match.group(1))  # Organization

                elif pattern_type in ('count_only', 'count_scotus'):
                    # These are aggregate claims, not direct relationships
                    result['from_entity'] = None
                    result['to_entity'] = None

                return result

        return None

    def _clean_entity(self, entity: str) -> str:
        """Clean entity name for node matching.

        Args:
            entity: Raw entity name

        Returns:
            Cleaned entity name
        """
        if not entity:
            return ""

        # Remove common prefixes
        entity = re.sub(r'^(?:the|a|an)\s+', '', entity, flags=re.IGNORECASE)

        # Remove parenthetical notes
        entity = re.sub(r'\s*\([^)]+\)', '', entity)

        # Clean whitespace
        entity = ' '.join(entity.split())

        return entity.strip()

    def _is_multi_entity(self, entity: str) -> bool:
        """Detect if entity string contains multiple entities (Franken-node).

        Args:
            entity: Entity name to check

        Returns:
            True if entity appears to be multiple entities conjoined
        """
        if not entity:
            return False

        # Pattern: "Name1 and Name2" where both look like proper names
        multi_patterns = [
            r'^[A-Z][a-z]+\s+[A-Z]?[a-z]*\s+and\s+[A-Z][a-z]+',  # "Ed Crane and Charles"
            r'\band\b.*\band\b',  # Multiple "and"s
            r'^[A-Z][a-z]+\s+[A-Z][a-z]+,?\s+and\s+[A-Z][a-z]+\s+[A-Z][a-z]+',  # "First Last and First Last"
        ]

        for pattern in multi_patterns:
            if re.search(pattern, entity):
                return True

        return False

    def _normalize_to_existing_node(self, entity_name: str) -> Optional[str]:
        """Try to match entity name to an existing node ID.

        Uses the canonical alias map from config/node_aliases.yaml.

        Args:
            entity_name: Entity name to match

        Returns:
            Existing node_id if found, None otherwise
        """
        # Load alias map (cached)
        if not hasattr(self, '_alias_map'):
            self._alias_map = self._load_alias_map()

        # Check alias map first
        entity_lower = entity_name.lower().strip()
        if entity_lower in self._alias_map:
            return self._alias_map[entity_lower]

        # Try with common variations
        entity_normalized = entity_lower.replace('-', ' ')
        if entity_normalized in self._alias_map:
            return self._alias_map[entity_normalized]

        # Check if slugified version exists
        slug = self._slugify(entity_name)
        existing = self._get_existing_nodes()
        if slug in existing:
            return slug

        return None

    def _load_alias_map(self) -> Dict[str, str]:
        """Load node aliases from config file.

        Returns:
            Dict mapping aliases to canonical node IDs
        """
        alias_path = Path(__file__).parent.parent.parent / "config" / "node_aliases.yaml"
        if not alias_path.exists():
            return {}

        aliases = {}
        try:
            with open(alias_path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if ':' in line:
                        parts = line.split(':', 1)
                        if len(parts) == 2:
                            key = parts[0].strip().lower()
                            value = parts[1].strip()
                            if key and value:
                                aliases[key] = value
        except Exception:
            pass

        return aliases

    def _slugify(self, name: str) -> str:
        """Convert entity name to node_id slug.

        Args:
            name: Entity name

        Returns:
            Slugified node ID
        """
        if not name:
            return ""

        # Lowercase and replace spaces/special chars
        slug = name.lower()
        slug = re.sub(r'[^a-z0-9]+', '-', slug)
        slug = re.sub(r'-+', '-', slug)
        slug = slug.strip('-')

        return slug

    def _tier_to_text(self, tier: int) -> str:
        """Convert tier number to human-readable text."""
        return {
            0: "Tier 0 (Government/Primary)",
            1: "Tier 1 (Journalism)",
            2: "Tier 2 (Commentary)",
        }.get(tier, f"Tier {tier}")

    def _get_promotion_requirement(self, tier: int) -> Optional[str]:
        """Get promotion requirement based on source tier."""
        if tier == 0:
            return None  # Already Tier 0
        elif tier == 1:
            return "Verify with Tier 0 government/court document for FACT status"
        else:
            return "Requires Tier 0/1 source verification for promotion"

    def _get_existing_nodes(self) -> set:
        """Get set of existing node IDs (lazy loaded)."""
        if self._existing_nodes is None:
            conn = self.db.connect()
            rows = conn.execute("SELECT node_id FROM nodes").fetchall()
            self._existing_nodes = {row[0] for row in rows}
        return self._existing_nodes

    def get_missing_nodes(self, edges: List[ProposedEdge]) -> List[Dict[str, str]]:
        """Identify nodes referenced by edges that don't exist.

        Args:
            edges: List of proposed edges

        Returns:
            List of dicts with node_id, name, suggested_type
        """
        existing = self._get_existing_nodes()
        missing = {}

        for edge in edges:
            for node_id, is_from in [(edge.from_node, True), (edge.to_node, False)]:
                if node_id and node_id not in existing and node_id not in missing:
                    # Infer type from edge type
                    node_type = self._infer_node_type(edge.relationship, is_from)
                    missing[node_id] = {
                        'node_id': node_id,
                        'name': node_id.replace('-', ' ').title(),
                        'suggested_type': node_type,
                    }

        return list(missing.values())

    def _infer_node_type(self, edge_type: str, is_source: bool) -> str:
        """Infer node type from edge type and position.

        Args:
            edge_type: The edge type string
            is_source: True if this is the from_node

        Returns:
            Suggested NodeType value
        """
        type_hints = {
            'LOBBIED_FOR': ('ORGANIZATION', 'LEGISLATION'),
            'FILED_AMICUS': ('ORGANIZATION', 'COURT_CASE'),
            'OWNS_SHARES': ('COMPANY', 'COMPANY'),
            'EMPLOYED': ('PERSON', 'ORGANIZATION'),
            'EMPLOYS': ('ORGANIZATION', 'PERSON'),
            'DONATED_TO': ('PERSON', 'PERSON'),
            'ENABLED': ('POLICY', 'ECONOMIC_EVENT'),
            'CAUSED': ('POLICY', 'ECONOMIC_EVENT'),
            'MARRIED_TO': ('PERSON', 'PERSON'),
            'MEMBER_OF': ('PERSON', 'ORGANIZATION'),
            'APPOINTED_BY': ('PERSON', 'PERSON'),
        }

        hints = type_hints.get(edge_type, ('ORGANIZATION', 'ORGANIZATION'))
        return hints[0] if is_source else hints[1]
