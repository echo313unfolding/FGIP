"""FGIP Supply Chain Extractor - Enhanced 10-K parsing for supply chain edges.

Uses cached EDGAR 10-K artifacts for section-aware extraction of:
- SUPPLIES_TO: supplier → company
- DEPENDS_ON: company → critical supplier (sole/single source)
- CUSTOMER_OF: company → major customer (>10% revenue)
- BOTTLENECK_AT: supply chain → chokepoint

Improvements over base EDGAR extraction:
- Section-aware parsing (Item 1, 1A, 7)
- Better regex patterns for single-source dependencies
- Entity deduplication via alias lookup
- Creates DEPENDS_ON edges (not just SUPPLIES_TO)
"""

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional, Set

from .base import FGIPAgent, Artifact, StructuredFact, ProposedClaim, ProposedEdge


@dataclass
class EntityMention:
    """A detected entity mention with context."""
    raw_text: str
    normalized: str
    context: str
    section: str
    relationship_hint: str


class SupplyChainExtractor(FGIPAgent):
    """Enhanced 10-K parser for supply chain relationships.

    Focuses on extracting:
    - SUPPLIES_TO: supplier → company
    - DEPENDS_ON: company → critical supplier (single-source)
    - CUSTOMER_OF: company → major customer (>10% revenue)
    - COMPETES_WITH: company → competitor
    - BOTTLENECK_AT: supply_chain → chokepoint

    Uses cached EDGAR artifacts from data/artifacts/edgar/.
    """

    # Section markers in 10-K filings
    SECTION_PATTERNS = {
        'item_1': re.compile(
            r'(?:item\s+1\.?\s*[-–—]?\s*business|part\s+i\s+item\s+1)',
            re.I
        ),
        'item_1a': re.compile(
            r'item\s+1a\.?\s*[-–—]?\s*risk\s+factors?',
            re.I
        ),
        'item_7': re.compile(
            r'item\s+7\.?\s*[-–—]?\s*management',
            re.I
        ),
    }

    # Supply chain relationship patterns - single-source (DEPENDS_ON)
    DEPENDS_ON_PATTERNS = [
        re.compile(
            r'(?:sole|single|only|exclusive)\s+(?:source|supplier|vendor|provider)\s+'
            r'(?:of|for)\s+([A-Z][A-Za-z0-9\s,&\-\.]+?)(?:\.|,|;|\)|\sand\s)',
            re.I
        ),
        re.compile(
            r'(?:depend|relies?|reliant)\s+(?:heavily\s+)?(?:on|upon)\s+'
            r'([A-Z][A-Za-z0-9\s,&\-\.]+?)\s+(?:for|to\s+provide|as)',
            re.I
        ),
        re.compile(
            r'(?:critical|essential)\s+(?:supplier|vendor|provider|source)\s+'
            r'(?:is|includes?|such\s+as)\s+([A-Z][A-Za-z0-9\s,&\-\.]+?)(?:\.|,|;)',
            re.I
        ),
        re.compile(
            r'single[- ]source[d]?\s+(?:from|with|through)\s+'
            r'([A-Z][A-Za-z0-9\s,&\-\.]+?)(?:\.|,|;)',
            re.I
        ),
    ]

    # Supply chain relationship patterns - general suppliers (SUPPLIES_TO)
    SUPPLIES_TO_PATTERNS = [
        re.compile(
            r'(?:primary|principal|major|key|significant)\s+(?:supplier|vendor|provider)s?\s+'
            r'(?:include|are|such\s+as|:)\s+([A-Z][A-Za-z0-9\s,&\-\.]+?)(?:\.|;|\))',
            re.I
        ),
        re.compile(
            r'(?:purchase|procure|source|obtain)s?\s+(?:from|through)\s+'
            r'([A-Z][A-Za-z0-9\s,&\-\.]+?)(?:\.|,|;|and)',
            re.I
        ),
        re.compile(
            r'(?:supplied|provided)\s+(?:by|from)\s+'
            r'([A-Z][A-Za-z0-9\s,&\-\.]+?)(?:\.|,|;)',
            re.I
        ),
    ]

    # Customer concentration patterns (CUSTOMER_OF)
    CUSTOMER_PATTERNS = [
        re.compile(
            r'(\d{1,2}(?:\.\d+)?)\s*(?:%|percent)\s+'
            r'(?:of\s+)?(?:our\s+)?(?:total\s+)?(?:revenue|sales|net\s+sales).*?'
            r'(?:from|to|with|attributable\s+to)\s+([A-Z][A-Za-z0-9\s,&\-\.]+?)(?:\.|,|;)',
            re.I | re.DOTALL
        ),
        re.compile(
            r'([A-Z][A-Za-z0-9\s,&\-\.]+?)\s+'
            r'(?:accounted|represented|comprised)\s+(?:for\s+)?'
            r'(?:approximately\s+)?(\d{1,2}(?:\.\d+)?)\s*(?:%|percent)',
            re.I
        ),
        re.compile(
            r'(?:largest|major|significant|principal)\s+customer(?:s)?\s+'
            r'(?:include|are|such\s+as|:)\s+([A-Z][A-Za-z0-9\s,&\-\.]+?)(?:\.|,|;)',
            re.I
        ),
    ]

    # Known entity aliases for deduplication
    ENTITY_ALIASES = {
        'intel': ['intel corporation', 'intel corp', 'intel inc', 'intc'],
        'tsmc': ['taiwan semiconductor', 'taiwan semiconductor manufacturing', 'tsm', 'taiwan semi'],
        'samsung': ['samsung electronics', 'samsung semiconductor', 'samsung elec'],
        'micron': ['micron technology', 'micron tech', 'mu'],
        'nvidia': ['nvidia corporation', 'nvidia corp', 'nvda'],
        'apple': ['apple inc', 'apple computer', 'aapl'],
        'google': ['alphabet', 'alphabet inc', 'googl', 'goog'],
        'microsoft': ['microsoft corporation', 'microsoft corp', 'msft'],
        'amazon': ['amazon.com', 'amazon inc', 'amzn'],
        'caterpillar': ['caterpillar inc', 'cat'],
        'asml': ['asml holding', 'asml holdings'],
        'lam-research': ['lam research', 'lam research corporation'],
        'applied-materials': ['applied materials', 'amat'],
        'tokyo-electron': ['tokyo electron', 'tel'],
        'kla': ['kla corporation', 'kla-tencor'],
    }

    # Words that indicate NOT an entity
    STOP_WORDS = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'up', 'about', 'into', 'through', 'during',
        'our', 'their', 'its', 'we', 'they', 'it', 'these', 'those', 'this',
        'certain', 'various', 'other', 'many', 'some', 'such', 'each', 'all',
        'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten',
        'company', 'companies', 'supplier', 'suppliers', 'vendor', 'vendors',
        'customer', 'customers', 'competitor', 'competitors', 'manufacturer', 'manufacturers',
    }

    def __init__(self, db, artifact_dir: str = "data/artifacts/edgar"):
        super().__init__(
            db=db,
            name="supply_chain_extractor",
            description="Enhanced 10-K supply chain relationship extractor"
        )
        self.artifact_dir = Path(artifact_dir)
        self._known_nodes: Optional[Set[str]] = None

    def _get_known_nodes(self) -> Set[str]:
        """Load existing node IDs for deduplication."""
        if self._known_nodes is None:
            conn = self.db.connect()
            nodes = conn.execute("SELECT node_id FROM nodes").fetchall()
            self._known_nodes = {r[0] for r in nodes}
        return self._known_nodes

    def collect(self) -> List[Artifact]:
        """Find existing 10-K artifacts from EDGAR cache."""
        artifacts = []

        if not self.artifact_dir.exists():
            print(f"Warning: Artifact directory not found: {self.artifact_dir}")
            return artifacts

        # Find all 10-K files (htm, html)
        for path in self.artifact_dir.glob("*.htm"):
            # Check if this looks like a 10-K based on filename or content
            filename_lower = path.name.lower()
            if '10-k' in filename_lower or '10k' in filename_lower or '-20' in filename_lower:
                try:
                    content = path.read_bytes()
                    artifacts.append(Artifact(
                        url=f"file://{path}",
                        artifact_type="10-K",
                        local_path=str(path),
                        content_hash=hashlib.sha256(content).hexdigest(),
                        metadata={
                            'source': 'edgar_cache',
                            'filename': path.name,
                            'size_bytes': len(content),
                        }
                    ))
                except Exception as e:
                    print(f"Warning: Could not read {path}: {e}")

        print(f"Found {len(artifacts)} 10-K artifacts in {self.artifact_dir}")
        return artifacts

    def extract(self, artifacts: List[Artifact]) -> List[StructuredFact]:
        """Extract supply chain relationships with section awareness."""
        facts = []

        for artifact in artifacts:
            if not artifact.local_path:
                continue

            try:
                content = Path(artifact.local_path).read_text(encoding='utf-8', errors='ignore')
            except Exception as e:
                print(f"Warning: Could not read {artifact.local_path}: {e}")
                continue

            # Determine filing entity from filename
            entity_name = self._extract_filer_name(artifact, content)
            if not entity_name:
                continue

            print(f"Processing 10-K for: {entity_name}")

            # Extract sections
            sections = self._split_into_sections(content)

            for section_name, section_text in sections.items():
                # Clean HTML tags
                clean_text = self._clean_html(section_text)

                # Extract DEPENDS_ON relationships (single-source)
                depends_facts = self._extract_depends_on(clean_text, section_name, entity_name, artifact)
                facts.extend(depends_facts)

                # Extract SUPPLIES_TO relationships (general suppliers)
                supplies_facts = self._extract_supplies_to(clean_text, section_name, entity_name, artifact)
                facts.extend(supplies_facts)

                # Extract CUSTOMER_OF relationships
                customer_facts = self._extract_customers(clean_text, section_name, entity_name, artifact)
                facts.extend(customer_facts)

        # Deduplicate facts
        facts = self._deduplicate_facts(facts)

        print(f"Extracted {len(facts)} supply chain facts")
        return facts

    def _extract_filer_name(self, artifact: Artifact, content: str) -> Optional[str]:
        """Extract the filing company name."""
        filename = artifact.metadata.get('filename', '')

        # Common patterns: cat-20251231.htm, intc-20231231.htm
        # CIK_accession_filename pattern
        parts = filename.split('_')
        if len(parts) >= 3:
            # Last part is the actual filename
            actual_name = parts[-1]
            # Extract ticker from filename like "cat-20251231.htm"
            ticker_match = re.match(r'^([a-z]+)-\d{8}\.htm', actual_name, re.I)
            if ticker_match:
                ticker = ticker_match.group(1).lower()
                # Map known tickers
                ticker_map = {
                    'cat': 'caterpillar',
                    'intc': 'intel',
                    'mu': 'micron',
                    'nvda': 'nvidia',
                    'amd': 'amd',
                    'tsm': 'tsmc',
                }
                return ticker_map.get(ticker, ticker)

        # Try to extract from content
        company_pattern = re.compile(
            r'<title>([^<]+)</title>',
            re.I
        )
        match = company_pattern.search(content[:5000])
        if match:
            title = match.group(1)
            # Clean up title
            for suffix in ['10-K', '10K', 'Annual Report', 'Form']:
                title = re.sub(rf'\s*{suffix}.*', '', title, flags=re.I)
            title = title.strip()
            if title and len(title) < 50:
                return self._normalize_entity(title)

        return None

    def _split_into_sections(self, content: str) -> Dict[str, str]:
        """Split 10-K content into major sections."""
        sections = {}

        # Find section boundaries
        section_positions = []
        for section_name, pattern in self.SECTION_PATTERNS.items():
            for match in pattern.finditer(content):
                section_positions.append((match.start(), section_name))

        # Sort by position
        section_positions.sort(key=lambda x: x[0])

        # Extract each section
        for i, (start, name) in enumerate(section_positions):
            if i + 1 < len(section_positions):
                end = section_positions[i + 1][0]
            else:
                # Last section: take next 50k chars
                end = min(start + 50000, len(content))

            section_text = content[start:end]
            sections[name] = section_text

        # If no sections found, use entire content as 'full'
        if not sections:
            sections['full'] = content[:100000]

        return sections

    def _clean_html(self, text: str) -> str:
        """Remove HTML tags and normalize whitespace."""
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', text)
        # Remove HTML entities
        text = re.sub(r'&[a-z]+;', ' ', text)
        text = re.sub(r'&#\d+;', ' ', text)
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _extract_depends_on(self, text: str, section: str, company: str,
                            artifact: Artifact) -> List[StructuredFact]:
        """Extract single-source dependency relationships."""
        facts = []

        for pattern in self.DEPENDS_ON_PATTERNS:
            for match in pattern.finditer(text):
                supplier_text = match.group(1)
                suppliers = self._parse_entity_list(supplier_text)

                for supplier in suppliers:
                    normalized = self._normalize_entity(supplier)
                    if not normalized or len(normalized) < 2:
                        continue

                    # Skip if same as filing company
                    if normalized == company:
                        continue

                    facts.append(StructuredFact(
                        fact_type='supply_chain',
                        subject=company,  # Company depends on supplier
                        predicate='DEPENDS_ON',
                        object=normalized,
                        source_artifact=artifact,
                        confidence=0.85 if section in ('item_1', 'item_1a') else 0.75,
                        raw_text=match.group(0)[:200],
                        metadata={
                            'section': section,
                            'is_critical': True,
                            'relationship_type': 'single_source',
                            'original_text': supplier,
                        }
                    ))

        return facts

    def _extract_supplies_to(self, text: str, section: str, company: str,
                             artifact: Artifact) -> List[StructuredFact]:
        """Extract general supplier relationships."""
        facts = []

        for pattern in self.SUPPLIES_TO_PATTERNS:
            for match in pattern.finditer(text):
                supplier_text = match.group(1)
                suppliers = self._parse_entity_list(supplier_text)

                for supplier in suppliers:
                    normalized = self._normalize_entity(supplier)
                    if not normalized or len(normalized) < 2:
                        continue

                    # Skip if same as filing company
                    if normalized == company:
                        continue

                    facts.append(StructuredFact(
                        fact_type='supply_chain',
                        subject=normalized,  # Supplier supplies to company
                        predicate='SUPPLIES_TO',
                        object=company,
                        source_artifact=artifact,
                        confidence=0.75 if section == 'item_1' else 0.65,
                        raw_text=match.group(0)[:200],
                        metadata={
                            'section': section,
                            'is_critical': False,
                            'relationship_type': 'general_supplier',
                            'original_text': supplier,
                        }
                    ))

        return facts

    def _extract_customers(self, text: str, section: str, company: str,
                           artifact: Artifact) -> List[StructuredFact]:
        """Extract major customer relationships."""
        facts = []

        for pattern in self.CUSTOMER_PATTERNS:
            for match in pattern.finditer(text):
                groups = match.groups()

                # Different patterns capture groups differently
                if len(groups) >= 2:
                    # Try to identify percentage and customer
                    customer = None
                    pct = None

                    for g in groups:
                        if g and re.match(r'^\d+(\.\d+)?$', g):
                            pct = float(g)
                        elif g and len(g) > 2:
                            customer = g

                    if customer:
                        customers = self._parse_entity_list(customer)
                        for cust in customers:
                            normalized = self._normalize_entity(cust)
                            if not normalized or len(normalized) < 2:
                                continue

                            if normalized == company:
                                continue

                            metadata = {
                                'section': section,
                                'relationship_type': 'customer',
                                'original_text': cust,
                            }
                            if pct and pct >= 10:
                                metadata['revenue_concentration_pct'] = pct

                            facts.append(StructuredFact(
                                fact_type='supply_chain',
                                subject=company,
                                predicate='CUSTOMER_OF',
                                object=normalized,
                                source_artifact=artifact,
                                confidence=0.85 if pct and pct >= 10 else 0.70,
                                raw_text=match.group(0)[:200],
                                metadata=metadata,
                            ))

        return facts

    def _parse_entity_list(self, text: str) -> List[str]:
        """Parse comma/and separated list of entities."""
        if not text:
            return []

        # Split on common delimiters
        entities = re.split(r',\s*|\s+and\s+|\s+or\s+', text)

        result = []
        for entity in entities:
            entity = entity.strip().rstrip('.,;)')
            # Remove leading articles
            entity = re.sub(r'^(?:the|a|an)\s+', '', entity, flags=re.I)
            if entity and len(entity) > 1:
                result.append(entity)

        return result

    def _normalize_entity(self, name: str) -> str:
        """Normalize entity name for deduplication."""
        if not name:
            return ""

        # Clean up
        name = name.strip().rstrip('.,;:)')
        name = re.sub(r'\s+', ' ', name)

        # Remove corporate suffixes
        name = re.sub(
            r'\s*(?:Inc\.?|Corp\.?|Corporation|Company|Co\.?|LLC|Ltd\.?|Limited|Holdings?|Group)\.?\s*$',
            '',
            name,
            flags=re.I
        )

        name_lower = name.lower().strip()

        # Check against known aliases
        for canonical, aliases in self.ENTITY_ALIASES.items():
            if name_lower in aliases or canonical == name_lower:
                return canonical

        # Check if this looks like a valid entity name
        words = name_lower.split()
        if not words:
            return ""

        # Skip if starts with stop word or is too short
        if words[0] in self.STOP_WORDS and len(words) == 1:
            return ""

        # Skip if looks like generic text
        if all(w in self.STOP_WORDS for w in words):
            return ""

        # Generate slug
        slug = re.sub(r'[^a-z0-9]+', '-', name_lower)
        slug = slug.strip('-')

        # Skip if too short after normalization
        if len(slug) < 2:
            return ""

        return slug[:50]

    def _deduplicate_facts(self, facts: List[StructuredFact]) -> List[StructuredFact]:
        """Deduplicate facts by normalized relationship."""
        seen = {}
        deduped = []

        for fact in facts:
            key = (fact.subject, fact.predicate, fact.object)
            if key not in seen:
                seen[key] = len(deduped)
                deduped.append(fact)
            else:
                # Keep highest confidence version
                idx = seen[key]
                if fact.confidence > deduped[idx].confidence:
                    deduped[idx] = fact

        return deduped

    def propose(self, facts: List[StructuredFact]) -> Tuple[List[ProposedClaim], List[ProposedEdge]]:
        """Generate supply chain edge proposals."""
        claims = []
        edges = []

        for fact in facts:
            # Generate proposal ID
            proposal_id = self._generate_proposal_id()

            # Create claim
            claim_text = f"{fact.subject} {fact.predicate.replace('_', ' ').lower()} {fact.object}"
            if fact.metadata.get('revenue_concentration_pct'):
                claim_text += f" ({fact.metadata['revenue_concentration_pct']}% of revenue)"

            claim = ProposedClaim(
                proposal_id=f"{proposal_id}-CLAIM",
                claim_text=claim_text,
                topic="Downstream" if fact.predicate in ('SUPPLIES_TO', 'CUSTOMER_OF') else "Supply Chain Risk",
                agent_name=self.name,
                source_url=fact.source_artifact.url if fact.source_artifact else None,
                artifact_path=fact.source_artifact.local_path if fact.source_artifact else None,
                artifact_hash=fact.source_artifact.content_hash if fact.source_artifact else None,
                reasoning=f"Extracted from 10-K section: {fact.metadata.get('section', 'unknown')}",
                promotion_requirement="Verify against SEC filing at sec.gov",
            )
            claims.append(claim)

            # Create edge
            edge = ProposedEdge(
                proposal_id=proposal_id,
                from_node=fact.subject,
                to_node=fact.object,
                relationship=fact.predicate,
                agent_name=self.name,
                detail=fact.raw_text[:100] if fact.raw_text else None,
                proposed_claim_id=claim.proposal_id,
                confidence=fact.confidence,
                reasoning=f"10-K extraction: {fact.metadata.get('relationship_type', 'unknown')}",
                promotion_requirement="Verify against SEC filing",
            )
            edges.append(edge)

        # Summary
        edge_types = {}
        for e in edges:
            edge_types[e.relationship] = edge_types.get(e.relationship, 0) + 1

        print(f"\n{'='*60}")
        print(f"  SUPPLY CHAIN EXTRACTOR RESULTS")
        print(f"{'='*60}")
        print(f"  Total edges proposed: {len(edges)}")
        for etype, count in sorted(edge_types.items()):
            print(f"    {etype}: {count}")
        print(f"{'='*60}\n")

        return claims, edges


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    from fgip.db import FGIPDatabase

    db_path = sys.argv[1] if len(sys.argv) > 1 else "fgip.db"
    db = FGIPDatabase(db_path)
    db.connect()

    agent = SupplyChainExtractor(db)
    result = agent.run()

    print(f"Artifacts collected: {result['artifacts_collected']}")
    print(f"Facts extracted: {result['facts_extracted']}")
    print(f"Claims proposed: {result['claims_proposed']}")
    print(f"Edges proposed: {result['edges_proposed']}")
