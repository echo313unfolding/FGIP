"""FGIP Causal Agent - Extracts CAUSED edges from policy documents and testimony.

Establishes causal relationships from:
- GAO reports (already cached in data/artifacts/gao/)
- Congressional testimony (Congress.gov API)
- Federal Register preambles (policy rationale)

Target edge types:
- CAUSED: event/policy → outcome (e.g., "Fed printing CAUSED inflation")
- ENABLED: policy → capability (e.g., "CHIPS Act ENABLED domestic fab construction")
- CONTRIBUTED_TO: factor → outcome (weaker causal claim)

Key principle: Causal claims require higher evidence bar.
- CAUSED edges default to HYPOTHESIS
- Require explicit mechanism stated in source
- Include counter-argument consideration
"""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

from .base import FGIPAgent, Artifact, StructuredFact, ProposedClaim, ProposedEdge


@dataclass
class CausalClaim:
    """A detected causal claim with evidence."""
    cause: str
    effect: str
    mechanism: Optional[str]  # How the cause produces the effect
    strength: str  # 'strong', 'moderate', 'weak'
    source_text: str
    source_type: str  # 'gao', 'testimony', 'federal_register'


class CausalAgent(FGIPAgent):
    """Extracts causal relationships from policy documents.

    Focuses on:
    - Explicit causal language ("caused", "led to", "resulted in")
    - Policy rationale ("in order to", "to address", "because")
    - Mechanism descriptions ("by increasing", "through reduction of")

    All causal claims are HYPOTHESIS by default and require:
    - Explicit mechanism in source text
    - Counter-argument consideration
    - Human review for promotion
    """

    # Causal language patterns - strong causation
    STRONG_CAUSAL_PATTERNS = [
        # Direct causation
        re.compile(
            r'([A-Z][A-Za-z0-9\s\-]+?)\s+'
            r'(?:caused|led to|resulted in|produced|created|generated)\s+'
            r'([A-Za-z0-9\s\-]+?)(?:\.|,|;|\))',
            re.I
        ),
        # Policy impact
        re.compile(
            r'(?:as a result of|due to|because of)\s+'
            r'([A-Z][A-Za-z0-9\s\-]+?),?\s+'
            r'([A-Za-z0-9\s\-]+?)(?:\s+(?:increased|decreased|changed|occurred))',
            re.I
        ),
        # Consequence language
        re.compile(
            r'([A-Z][A-Za-z0-9\s\-]+?)\s+'
            r'(?:has|had|will have)\s+(?:a\s+)?'
            r'(?:significant|substantial|material|direct)\s+(?:effect|impact)\s+on\s+'
            r'([A-Za-z0-9\s\-]+?)(?:\.|,)',
            re.I
        ),
    ]

    # Moderate causal patterns - contribution
    MODERATE_CAUSAL_PATTERNS = [
        re.compile(
            r'([A-Z][A-Za-z0-9\s\-]+?)\s+'
            r'(?:contributed to|played a role in|was a factor in)\s+'
            r'([A-Za-z0-9\s\-]+?)(?:\.|,|;)',
            re.I
        ),
        re.compile(
            r'([A-Z][A-Za-z0-9\s\-]+?)\s+'
            r'(?:may have|could have|likely)\s+'
            r'(?:caused|led to|contributed to)\s+'
            r'([A-Za-z0-9\s\-]+?)(?:\.|,)',
            re.I
        ),
    ]

    # Enabling patterns
    ENABLING_PATTERNS = [
        re.compile(
            r'([A-Z][A-Za-z0-9\s\-]+?)\s+'
            r'(?:enabled|allowed|permitted|made possible|facilitated)\s+'
            r'([A-Za-z0-9\s\-]+?)(?:\.|,|;)',
            re.I
        ),
        re.compile(
            r'(?:through|via|by means of)\s+'
            r'([A-Z][A-Za-z0-9\s\-]+?),?\s+'
            r'([A-Za-z0-9\s\-]+?)\s+(?:was|were|became)\s+(?:possible|feasible)',
            re.I
        ),
    ]

    # Mechanism extraction patterns
    MECHANISM_PATTERNS = [
        re.compile(r'by\s+(?:increasing|decreasing|reducing|expanding|limiting)\s+([A-Za-z0-9\s\-]+)', re.I),
        re.compile(r'through\s+(?:the\s+)?([A-Za-z0-9\s\-]+?)(?:\.|,|;)', re.I),
        re.compile(r'via\s+([A-Za-z0-9\s\-]+?)(?:\.|,|;)', re.I),
    ]

    # Known causal entities for normalization
    ENTITY_ALIASES = {
        'federal-reserve': ['fed', 'federal reserve', 'the fed', 'fomc', 'federal reserve board'],
        'm2-money-supply': ['m2', 'm2 money supply', 'money supply', 'm2 growth'],
        'inflation': ['inflation', 'price increases', 'rising prices', 'cpi'],
        'chips-act': ['chips act', 'chips and science act', 'chips legislation'],
        'ira': ['inflation reduction act', 'ira'],
        'reshoring': ['reshoring', 'onshoring', 'domestic manufacturing'],
        'supply-chain': ['supply chain', 'supply chains', 'supply chain disruption'],
        'tariffs': ['tariffs', 'tariff policy', 'trade barriers'],
    }

    def __init__(self, db, artifact_dirs: List[str] = None):
        super().__init__(
            db=db,
            name="causal",
            description="Extracts causal relationships from policy documents"
        )
        self.artifact_dirs = artifact_dirs or [
            "data/artifacts/gao",
            "data/artifacts/federal_register",
            "data/artifacts/congress",
        ]

    # Well-documented causal relationships from FGIP thesis
    # These are backed by evidence in the graph (25-year backtest, USASpending, etc.)
    SEED_CAUSAL_FACTS = [
        {
            'cause': 'm2-money-supply',
            'effect': 'asset-price-inflation',
            'relationship': 'CAUSED',
            'mechanism': 'Money supply expansion increases purchasing power for assets before consumer prices adjust',
            'confidence': 0.85,
            'source': 'FRED M2SL 25-year backtest: +411% S&P, +220% housing vs +88% CPI',
            'source_type': 'fred_backtest',
        },
        {
            'cause': 'chips-act',
            'effect': 'domestic-fab-investment',
            'relationship': 'ENABLED',
            'mechanism': '$52B in subsidies and tax credits for domestic semiconductor manufacturing',
            'confidence': 0.90,
            'source': 'USASpending: Intel $8.5B, Micron $6.1B, TSMC grants',
            'source_type': 'usaspending',
        },
        {
            'cause': 'federal-reserve-policy',
            'effect': 'm2-money-supply',
            'relationship': 'CAUSED',
            'mechanism': 'Open market operations, reserve requirements, and interest rate policy',
            'confidence': 0.95,
            'source': 'Federal Reserve Act, FOMC operations',
            'source_type': 'federal_reserve',
        },
        {
            'cause': 'offshoring',
            'effect': 'supply-chain-vulnerability',
            'relationship': 'CAUSED',
            'mechanism': 'Geographic concentration of manufacturing in foreign jurisdictions',
            'confidence': 0.80,
            'source': '10-K Risk Factors: single-source dependencies, geographic concentration',
            'source_type': 'edgar_10k',
        },
        {
            'cause': 'cpi-methodology-change-1983',
            'effect': 'inflation-underreporting',
            'relationship': 'CAUSED',
            'mechanism': 'OER replaced actual home prices, reducing measured inflation',
            'confidence': 0.85,
            'source': 'BLS methodology change 1983: Owner Equivalent Rent substitution',
            'source_type': 'bls_methodology',
        },
        {
            'cause': 'passive-index-investing',
            'effect': 'ownership-concentration',
            'relationship': 'CAUSED',
            'mechanism': 'Market-cap weighting mechanically concentrates ownership in largest firms',
            'confidence': 0.80,
            'source': 'SEC 13F: Big Three (BlackRock, Vanguard, State Street) own 18-20% of S&P 500',
            'source_type': 'edgar_13f',
        },
        {
            'cause': 'ira-clean-energy-credits',
            'effect': 'ev-manufacturing-investment',
            'relationship': 'ENABLED',
            'mechanism': 'Tax credits for domestic EV and battery manufacturing',
            'confidence': 0.85,
            'source': 'Inflation Reduction Act: $369B for clean energy, domestic content requirements',
            'source_type': 'legislation',
        },
        {
            'cause': 'china-pntr-2000',
            'effect': 'manufacturing-offshoring',
            'relationship': 'ENABLED',
            'mechanism': 'Removed tariff uncertainty, enabled long-term supply chain planning in China',
            'confidence': 0.80,
            'source': 'Congress.gov: HR 4444 passed House 237-197, Senate 83-15',
            'source_type': 'congress',
        },
    ]

    def collect(self) -> List[Artifact]:
        """Find existing policy document artifacts and seed facts."""
        artifacts = []

        # Add seed causal facts as a virtual artifact
        seed_content = json.dumps(self.SEED_CAUSAL_FACTS, indent=2).encode('utf-8')
        artifacts.append(Artifact(
            url="internal://causal/seed_facts",
            artifact_type="seed_causal",
            local_path=None,
            content_hash=hashlib.sha256(seed_content).hexdigest(),
            metadata={
                'source_type': 'seed_causal',
                'seed_facts': self.SEED_CAUSAL_FACTS,
            }
        ))

        # Also collect from document directories
        for dir_path in self.artifact_dirs:
            artifact_dir = Path(dir_path)
            if not artifact_dir.exists():
                continue

            # Find PDF, HTML, TXT, JSON files
            for pattern in ['*.pdf', '*.html', '*.htm', '*.txt', '*.json']:
                for path in artifact_dir.glob(pattern):
                    try:
                        content = path.read_bytes()
                        source_type = artifact_dir.name  # gao, federal_register, congress

                        artifacts.append(Artifact(
                            url=f"file://{path}",
                            artifact_type=source_type,
                            local_path=str(path),
                            content_hash=hashlib.sha256(content).hexdigest(),
                            metadata={
                                'source_type': source_type,
                                'filename': path.name,
                                'size_bytes': len(content),
                            }
                        ))
                    except Exception as e:
                        print(f"Warning: Could not read {path}: {e}")

        print(f"Found {len(artifacts)} policy document artifacts (including seed)")
        return artifacts

    def extract(self, artifacts: List[Artifact]) -> List[StructuredFact]:
        """Extract causal claims from documents."""
        facts = []

        for artifact in artifacts:
            source_type = artifact.metadata.get('source_type', 'unknown')

            # Handle seed causal facts
            if source_type == 'seed_causal':
                seed_facts = artifact.metadata.get('seed_facts', [])
                for sf in seed_facts:
                    facts.append(StructuredFact(
                        fact_type='causal',
                        subject=sf['cause'],
                        predicate=sf['relationship'],
                        object=sf['effect'],
                        source_artifact=artifact,
                        confidence=sf['confidence'],
                        raw_text=sf['source'],
                        metadata={
                            'source_type': sf['source_type'],
                            'mechanism': sf['mechanism'],
                            'is_seed': True,
                        }
                    ))
                continue

            if not artifact.local_path:
                continue

            try:
                # Read content
                path = Path(artifact.local_path)
                if path.suffix == '.pdf':
                    # Skip PDFs for now (would need pdftotext)
                    continue

                content = path.read_text(encoding='utf-8', errors='ignore')

            except Exception as e:
                print(f"Warning: Could not read {artifact.local_path}: {e}")
                continue

            # Clean content
            clean_text = self._clean_text(content)

            # Extract CAUSED relationships (strong)
            caused_facts = self._extract_causal(
                clean_text, 'CAUSED', self.STRONG_CAUSAL_PATTERNS,
                source_type, artifact, confidence=0.75
            )
            facts.extend(caused_facts)

            # Extract CONTRIBUTED_TO relationships (moderate)
            contributed_facts = self._extract_causal(
                clean_text, 'CONTRIBUTED_TO', self.MODERATE_CAUSAL_PATTERNS,
                source_type, artifact, confidence=0.60
            )
            facts.extend(contributed_facts)

            # Extract ENABLED relationships
            enabled_facts = self._extract_causal(
                clean_text, 'ENABLED', self.ENABLING_PATTERNS,
                source_type, artifact, confidence=0.70
            )
            facts.extend(enabled_facts)

        # Deduplicate
        facts = self._deduplicate_facts(facts)

        print(f"Extracted {len(facts)} causal facts")
        return facts

    def _clean_text(self, text: str) -> str:
        """Clean HTML and normalize whitespace."""
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', text)
        # Remove HTML entities
        text = re.sub(r'&[a-z]+;', ' ', text)
        text = re.sub(r'&#\d+;', ' ', text)
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _extract_causal(self, text: str, relationship: str,
                        patterns: List[re.Pattern], source_type: str,
                        artifact: Artifact, confidence: float) -> List[StructuredFact]:
        """Extract causal relationships using patterns."""
        facts = []

        for pattern in patterns:
            for match in pattern.finditer(text):
                groups = match.groups()
                if len(groups) < 2:
                    continue

                cause_raw = groups[0].strip()
                effect_raw = groups[1].strip()

                # Normalize entities
                cause = self._normalize_entity(cause_raw)
                effect = self._normalize_entity(effect_raw)

                if not cause or not effect:
                    continue

                # Skip if cause and effect are the same
                if cause == effect:
                    continue

                # Try to extract mechanism
                context_start = max(0, match.start() - 100)
                context_end = min(len(text), match.end() + 100)
                context = text[context_start:context_end]
                mechanism = self._extract_mechanism(context)

                facts.append(StructuredFact(
                    fact_type='causal',
                    subject=cause,
                    predicate=relationship,
                    object=effect,
                    source_artifact=artifact,
                    confidence=confidence,
                    raw_text=match.group(0)[:200],
                    metadata={
                        'source_type': source_type,
                        'mechanism': mechanism,
                        'original_cause': cause_raw,
                        'original_effect': effect_raw,
                        'pattern_type': relationship.lower(),
                    }
                ))

        return facts

    def _extract_mechanism(self, context: str) -> Optional[str]:
        """Extract the mechanism by which cause produces effect."""
        for pattern in self.MECHANISM_PATTERNS:
            match = pattern.search(context)
            if match:
                mechanism = match.group(1).strip()
                if len(mechanism) > 5 and len(mechanism) < 100:
                    return mechanism
        return None

    def _normalize_entity(self, name: str) -> str:
        """Normalize entity name."""
        if not name:
            return ""

        # Clean up
        name = name.strip().rstrip('.,;:)')
        name = re.sub(r'\s+', ' ', name)

        # Skip if too short or too long
        if len(name) < 3 or len(name) > 80:
            return ""

        name_lower = name.lower()

        # Check against known aliases
        for canonical, aliases in self.ENTITY_ALIASES.items():
            for alias in aliases:
                if alias in name_lower:
                    return canonical

        # Generate slug
        slug = re.sub(r'[^a-z0-9]+', '-', name_lower)
        slug = slug.strip('-')

        # Skip common non-entities
        stop_phrases = ['the', 'this', 'that', 'these', 'those', 'which', 'what',
                        'significant', 'substantial', 'material', 'increased', 'decreased']
        if slug in stop_phrases or len(slug) < 3:
            return ""

        return slug[:50]

    def _deduplicate_facts(self, facts: List[StructuredFact]) -> List[StructuredFact]:
        """Deduplicate facts by relationship."""
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
        """Generate causal edge proposals."""
        claims = []
        edges = []

        for fact in facts:
            proposal_id = self._generate_proposal_id()

            # Create claim
            mechanism_text = f" (mechanism: {fact.metadata['mechanism']})" if fact.metadata.get('mechanism') else ""
            claim_text = f"{fact.subject} {fact.predicate.replace('_', ' ').lower()} {fact.object}{mechanism_text}"

            claim = ProposedClaim(
                proposal_id=f"{proposal_id}-CLAIM",
                claim_text=claim_text,
                topic="Causal",
                agent_name=self.name,
                source_url=fact.source_artifact.url if fact.source_artifact else None,
                artifact_path=fact.source_artifact.local_path if fact.source_artifact else None,
                artifact_hash=fact.source_artifact.content_hash if fact.source_artifact else None,
                reasoning=f"Causal extraction from {fact.metadata.get('source_type', 'policy document')}",
                promotion_requirement="Verify causal mechanism is explicitly stated. Consider counter-arguments.",
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
                reasoning=f"Causal claim: {fact.metadata.get('pattern_type', 'unknown')}",
                promotion_requirement="Causal claims require explicit mechanism and counter-argument consideration",
            )
            edges.append(edge)

        # Summary by relationship type
        edge_types = {}
        for e in edges:
            edge_types[e.relationship] = edge_types.get(e.relationship, 0) + 1

        print(f"\n{'='*60}")
        print(f"  CAUSAL AGENT RESULTS")
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

    agent = CausalAgent(db)
    result = agent.run()

    print(f"Artifacts collected: {result['artifacts_collected']}")
    print(f"Facts extracted: {result['facts_extracted']}")
    print(f"Claims proposed: {result['claims_proposed']}")
    print(f"Edges proposed: {result['edges_proposed']}")
