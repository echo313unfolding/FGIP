#!/usr/bin/env python3
"""FGIP NLPAgent - Structured Extraction from Text.

This agent extracts structured facts from text content:
- Named entities (organizations, persons, legislation, etc.)
- Relations between entities
- Evidence spans (verbatim quotes supporting claims)
- Counter-evidence (negations, denials, hedging)

Output is used to create reviewable proposals with "why" explanations.

Dependencies:
- spacy (optional, falls back to regex if not installed)
- rapidfuzz (for entity normalization)
"""

import json
import re
import sqlite3
import hashlib
from datetime import datetime
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set
import sys

# Add project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Try to import optional dependencies
try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False

try:
    from rapidfuzz import fuzz, process
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False


@dataclass
class EntityCandidate:
    """A candidate entity extracted from text."""
    text: str                        # Original text
    entity_type: str                 # ORG, PERSON, LAW, MONEY, etc.
    start_offset: int
    end_offset: int
    node_id_guess: Optional[str]     # Normalized to existing graph node
    confidence: float                # 0-1
    why: List[str]                   # Reasons for confidence


@dataclass
class RelationCandidate:
    """A candidate relation between entities."""
    from_entity: str
    to_entity: str
    relation_type: str               # FUNDED_BY, AWARDED_GRANT, etc.
    evidence_span: str               # Verbatim supporting text
    evidence_offset: int
    confidence: float
    pattern_name: str                # Which pattern matched
    why: List[str]


@dataclass
class ClaimCandidate:
    """A candidate claim extracted from text."""
    claim_text: str                  # The claim itself
    evidence_span: str               # Supporting quote
    evidence_offset: int
    topic: str                       # Inferred topic
    entities: List[str]              # Entities mentioned
    confidence: float
    counter_evidence: List[str]      # Detected negations/hedging
    why: List[str]


@dataclass
class ExtractionResult:
    """Result of NLP extraction from content."""
    artifact_id: str
    entities: List[EntityCandidate]
    relations: List[RelationCandidate]
    claims: List[ClaimCandidate]
    counter_evidence_flags: List[str]
    extraction_time_ms: int


# FGIP entity types (map from spaCy types)
ENTITY_TYPE_MAP = {
    "ORG": "ORGANIZATION",
    "PERSON": "PERSON",
    "GPE": "LOCATION",
    "LAW": "LEGISLATION",
    "MONEY": "FINANCIAL",
    "DATE": "DATE",
    "PERCENT": "METRIC",
    "CARDINAL": "METRIC",
    "PRODUCT": "PROGRAM",
    "FAC": "FACILITY",
}

# Relation extraction patterns
# Format: (pattern, relation_type, from_group, to_group)
RELATION_PATTERNS = [
    # Funding/Investment
    (r'(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b)\s+(?:invested|invested in|acquired stake in)\s+(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b)',
     "INVESTED_IN", 1, 2),
    (r'(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b)\s+(?:funded|financed|backed)\s+(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b)',
     "FUNDED_BY", 2, 1),

    # Awards/Grants
    (r'(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b)\s+(?:awarded|granted|allocated)\s+\$[\d,\.]+[BMK]?\s+(?:to|for)\s+(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b)',
     "AWARDED_GRANT", 1, 2),
    (r'(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b)\s+(?:received|was awarded|got)\s+(?:a\s+)?\$[\d,\.]+[BMK]?\s+(?:grant|award|funding)',
     "AWARDED_GRANT", None, 1),

    # Ownership
    (r'(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b)\s+(?:owns|acquired|purchased)\s+(?:\d+%?\s+(?:of|stake in)\s+)?(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b)',
     "OWNS", 1, 2),
    (r'(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b)\s+(?:holds?|has)\s+\$[\d,\.]+[BMK]?\s+(?:in|of)\s+(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b)',
     "HOLDS", 1, 2),

    # Lobbying
    (r'(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b)\s+(?:lobbied for|lobbied against|advocated for)\s+(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b)',
     "LOBBIED_FOR", 1, 2),

    # Employment/Leadership
    (r'(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b)\s+(?:CEO|president|chairman|director)\s+(?:of|at)\s+(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b)',
     "LEADS", 1, 2),
    (r'(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b)\s+(?:joined|hired by|works at|employed by)\s+(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b)',
     "EMPLOYED_BY", 1, 2),

    # Regulatory
    (r'(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b)\s+(?:fined|penalized|sanctioned)\s+(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b)',
     "SANCTIONED", 1, 2),
    (r'(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b)\s+(?:approved|authorized|permitted)\s+(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b)',
     "AUTHORIZED", 1, 2),

    # Legislative
    (r'(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b)\s+(?:signed|enacted|passed)\s+(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b)',
     "ENACTED", 1, 2),
    (r'(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b)\s+(?:sponsored|introduced|proposed)\s+(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b)',
     "SPONSORED", 1, 2),

    # Construction/Building
    (r'(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b)\s+(?:built|constructed|building|constructing)\s+(?:a\s+)?(?:new\s+)?(?:facility|plant|factory|fab)\s+in\s+(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b)',
     "BUILT_IN", 1, 2),
]

# Counter-evidence patterns (negations, hedging, denials)
# Format: (pattern, flag_type, severity)
# Severity: 'fatal', 'serious', 'manageable', 'weak'
COUNTER_EVIDENCE_PATTERNS = [
    (r'retracted|withdrawn|corrected', "RETRACTED", "fatal"),
    (r'false|incorrect|inaccurate|fabricated', "DISPUTED", "fatal"),
    (r'denied|denies|refuted|disputed', "DENIAL", "serious"),
    (r'no evidence|unconfirmed|unverified|unsubstantiated', "NO_EVIDENCE", "serious"),
    (r'failed to confirm|could not verify|unable to confirm', "VERIFICATION_FAILED", "serious"),
    (r'allegedly|reportedly|purportedly|supposedly', "HEDGING", "manageable"),
    (r'sources say|according to sources|anonymous sources', "ANONYMOUS_SOURCE", "manageable"),
    (r'may|might|could|possibly|potentially', "UNCERTAINTY", "weak"),
    (r'unclear|unknown|uncertain', "AMBIGUOUS", "weak"),
]

# Topic inference patterns
TOPIC_PATTERNS = [
    (r'CHIPS\s+Act|semiconductor|fab|foundry', "semiconductors"),
    (r'stablecoin|cryptocurrency|CBDC|digital currency', "stablecoins"),
    (r'treasury|T-bill|bond|debt', "treasury"),
    (r'tariff|trade|import|export', "trade"),
    (r'reshoring|onshoring|domestic manufacturing', "reshoring"),
    (r'lobbying|PAC|campaign|donation', "political_influence"),
    (r'SEC|filing|13F|disclosure', "securities"),
    (r'Fed|interest rate|monetary policy', "monetary_policy"),
    (r'China|Taiwan|TSMC', "geopolitics"),
]


class NLPAgent:
    """NLP extraction agent for structured fact extraction."""

    def __init__(self, db_path: str = "fgip.db"):
        self.db_path = db_path
        self.conn = None
        self.existing_nodes = {}  # name -> node_id mapping
        self.nlp = None

        # Load spaCy if available
        if SPACY_AVAILABLE:
            try:
                self.nlp = spacy.load("en_core_web_sm")
            except OSError:
                print("spaCy model not found. Install with: python -m spacy download en_core_web_sm")
                self.nlp = None

    def connect(self):
        """Get database connection."""
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
            self._load_existing_nodes()
        return self.conn

    def _load_existing_nodes(self):
        """Load existing nodes for entity normalization."""
        rows = self.conn.execute("""
            SELECT node_id, LOWER(name) as name, node_type FROM nodes
        """).fetchall()

        for row in rows:
            self.existing_nodes[row["name"]] = {
                "node_id": row["node_id"],
                "node_type": row["node_type"],
            }

    def _normalize_entity(self, text: str) -> Tuple[Optional[str], float]:
        """
        Normalize entity text to existing graph node.

        Returns (node_id, confidence) or (None, 0) if no match.
        """
        text_lower = text.lower()

        # Exact match
        if text_lower in self.existing_nodes:
            return self.existing_nodes[text_lower]["node_id"], 0.99

        # Fuzzy match if rapidfuzz available
        if RAPIDFUZZ_AVAILABLE and self.existing_nodes:
            matches = process.extract(
                text_lower,
                self.existing_nodes.keys(),
                scorer=fuzz.token_sort_ratio,
                limit=1
            )
            if matches and matches[0][1] >= 85:
                matched_name = matches[0][0]
                confidence = matches[0][1] / 100
                return self.existing_nodes[matched_name]["node_id"], confidence

        return None, 0.0

    def extract_entities(self, content: str) -> List[EntityCandidate]:
        """Extract named entities from content."""
        entities = []

        if self.nlp:
            # Use spaCy for NER
            doc = self.nlp(content)
            for ent in doc.ents:
                if ent.label_ in ENTITY_TYPE_MAP:
                    node_id, confidence = self._normalize_entity(ent.text)
                    why = ["spacy_ner"]
                    if node_id:
                        why.append("matched_existing_node")

                    entities.append(EntityCandidate(
                        text=ent.text,
                        entity_type=ENTITY_TYPE_MAP.get(ent.label_, "OTHER"),
                        start_offset=ent.start_char,
                        end_offset=ent.end_char,
                        node_id_guess=node_id,
                        confidence=confidence if node_id else 0.5,
                        why=why,
                    ))
        else:
            # Fallback to regex-based extraction
            # Find proper noun sequences (capitalized words)
            pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b'
            for match in re.finditer(pattern, content):
                text = match.group(1)
                node_id, confidence = self._normalize_entity(text)
                why = ["regex_proper_noun"]
                if node_id:
                    why.append("matched_existing_node")

                entities.append(EntityCandidate(
                    text=text,
                    entity_type="ORGANIZATION",  # Default guess
                    start_offset=match.start(),
                    end_offset=match.end(),
                    node_id_guess=node_id,
                    confidence=confidence if node_id else 0.3,
                    why=why,
                ))

            # Find money amounts
            money_pattern = r'\$[\d,]+(?:\.\d{2})?(?:\s*[BMK](?:illion)?)?'
            for match in re.finditer(money_pattern, content):
                entities.append(EntityCandidate(
                    text=match.group(),
                    entity_type="FINANCIAL",
                    start_offset=match.start(),
                    end_offset=match.end(),
                    node_id_guess=None,
                    confidence=0.9,
                    why=["regex_money_amount"],
                ))

        return entities

    def extract_relations(self, content: str,
                          entities: List[EntityCandidate]) -> List[RelationCandidate]:
        """Extract relations between entities."""
        relations = []
        entity_texts = {e.text.lower() for e in entities}

        for pattern, rel_type, from_group, to_group in RELATION_PATTERNS:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                # Get context window for evidence span
                start = max(0, match.start() - 20)
                end = min(len(content), match.end() + 20)
                evidence_span = content[start:end]

                # Extract entity names from groups
                if from_group and to_group:
                    from_entity = match.group(from_group)
                    to_entity = match.group(to_group)
                elif from_group:
                    from_entity = match.group(from_group)
                    to_entity = None
                else:
                    from_entity = None
                    to_entity = match.group(to_group) if to_group else None

                if from_entity or to_entity:
                    # Calculate confidence based on entity matching
                    confidence = 0.5
                    why = [f"pattern:{pattern[:30]}"]

                    if from_entity and from_entity.lower() in entity_texts:
                        confidence += 0.2
                        why.append("from_entity_confirmed")
                    if to_entity and to_entity.lower() in entity_texts:
                        confidence += 0.2
                        why.append("to_entity_confirmed")

                    relations.append(RelationCandidate(
                        from_entity=from_entity or "UNKNOWN",
                        to_entity=to_entity or "UNKNOWN",
                        relation_type=rel_type,
                        evidence_span=evidence_span.strip(),
                        evidence_offset=match.start(),
                        confidence=min(1.0, confidence),
                        pattern_name=rel_type,
                        why=why,
                    ))

        return relations

    def extract_claims(self, content: str,
                       entities: List[EntityCandidate],
                       relations: List[RelationCandidate]) -> List[ClaimCandidate]:
        """Extract claim candidates from content."""
        claims = []

        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', content)

        for i, sentence in enumerate(sentences):
            if len(sentence) < 20:
                continue

            # Check if sentence has claim-worthy content
            has_entity = any(e.text.lower() in sentence.lower() for e in entities)
            has_money = bool(re.search(r'\$[\d,]+', sentence))
            has_action = bool(re.search(r'awarded|invested|funded|signed|enacted|built|purchased', sentence, re.IGNORECASE))

            if not (has_entity or has_money or has_action):
                continue

            # Infer topic
            topic = "general"
            for pattern, topic_name in TOPIC_PATTERNS:
                if re.search(pattern, sentence, re.IGNORECASE):
                    topic = topic_name
                    break

            # Detect counter-evidence with severity
            counter = []
            counter_severity = "weak"  # Default
            for pattern, flag, severity in COUNTER_EVIDENCE_PATTERNS:
                if re.search(pattern, sentence, re.IGNORECASE):
                    counter.append(flag)
                    # Track worst severity
                    severity_order = {"fatal": 0, "serious": 1, "manageable": 2, "weak": 3}
                    if severity_order.get(severity, 3) < severity_order.get(counter_severity, 3):
                        counter_severity = severity

            # Calculate confidence
            confidence = 0.5
            why = []

            if has_entity:
                confidence += 0.15
                why.append("has_entity")
            if has_money:
                confidence += 0.15
                why.append("has_money")
            if has_action:
                confidence += 0.1
                why.append("has_action")
            if topic != "general":
                confidence += 0.05
                why.append(f"topic:{topic}")
            if counter:
                confidence -= 0.2
                why.append("has_counter_evidence")

            # Find evidence offset
            offset = content.find(sentence)

            # Get entities mentioned in this sentence
            mentioned_entities = [
                e.text for e in entities
                if e.text.lower() in sentence.lower()
            ]

            claims.append(ClaimCandidate(
                claim_text=sentence.strip(),
                evidence_span=sentence.strip(),
                evidence_offset=offset,
                topic=topic,
                entities=mentioned_entities,
                confidence=max(0, min(1.0, confidence)),
                counter_evidence=counter,
                why=why,
            ))

        return claims

    def extract(self, content: str) -> ExtractionResult:
        """
        Run full extraction pipeline on content.

        Returns ExtractionResult with entities, relations, claims.
        """
        self.connect()
        start_time = datetime.now()

        artifact_id = hashlib.sha256(content.encode()).hexdigest()[:16]

        # Extract entities
        entities = self.extract_entities(content)

        # Extract relations
        relations = self.extract_relations(content, entities)

        # Extract claims
        claims = self.extract_claims(content, entities, relations)

        # Aggregate counter-evidence flags
        counter_flags = set()
        for claim in claims:
            counter_flags.update(claim.counter_evidence)

        elapsed_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        return ExtractionResult(
            artifact_id=artifact_id,
            entities=entities,
            relations=relations,
            claims=claims,
            counter_evidence_flags=list(counter_flags),
            extraction_time_ms=elapsed_ms,
        )

    def create_proposals(self, extraction: ExtractionResult,
                         agent_name: str = "nlp_agent",
                         source_url: str = "",
                         artifact_path: str = "",
                         artifact_id: str = None) -> Dict[str, int]:
        """
        Create proposed claims and edges from extraction result.

        Args:
            extraction: NLP extraction result
            agent_name: Name of agent creating proposals
            source_url: Original source URL
            artifact_path: Path to artifact file
            artifact_id: FK to artifact_queue (required for traceability)

        Returns:
            Counts of proposals created {"claims": N, "edges": M}
        """
        self.connect()
        from fgip.staging import get_next_proposal_id

        counts = {"claims": 0, "edges": 0}

        # Create claim proposals
        for claim in extraction.claims:
            if claim.confidence < 0.4:
                continue  # Skip low confidence claims

            proposal_id = get_next_proposal_id(
                self.conn, agent_name,
                hashlib.sha256(claim.claim_text.encode()).hexdigest()[:10]
            )

            try:
                self.conn.execute("""
                    INSERT INTO proposed_claims
                    (proposal_id, claim_text, topic, agent_name, source_url,
                     artifact_path, reasoning, status, evidence_span,
                     evidence_offset, entity_candidates, reason_codes,
                     counter_evidence, se_score, artifact_id, bypass_pipeline)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?, ?, ?, ?, ?, ?, 0)
                """, (
                    proposal_id,
                    claim.claim_text,
                    claim.topic,
                    agent_name,
                    source_url,
                    artifact_path,
                    f"NLP extraction. Why: {', '.join(claim.why)}",
                    claim.evidence_span,
                    claim.evidence_offset,
                    json.dumps([{"entity": e, "confidence": 0.7} for e in claim.entities]),
                    json.dumps(claim.why),
                    json.dumps(claim.counter_evidence),
                    claim.confidence,
                    artifact_id,  # FK to artifact_queue
                ))
                counts["claims"] += 1
            except sqlite3.IntegrityError:
                pass  # Duplicate

        # Create edge proposals
        for rel in extraction.relations:
            if rel.confidence < 0.5:
                continue

            proposal_id = get_next_proposal_id(
                self.conn, agent_name,
                hashlib.sha256(f"{rel.from_entity}{rel.relation_type}{rel.to_entity}".encode()).hexdigest()[:10]
            )

            try:
                self.conn.execute("""
                    INSERT INTO proposed_edges
                    (proposal_id, from_node, to_node, relationship, detail,
                     agent_name, confidence, reasoning, status, evidence_span,
                     evidence_offset, reason_codes, artifact_id, bypass_pipeline)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?, ?, ?, 0)
                """, (
                    proposal_id,
                    rel.from_entity,
                    rel.to_entity,
                    rel.relation_type,
                    rel.evidence_span,
                    agent_name,
                    rel.confidence,
                    f"NLP pattern: {rel.pattern_name}. Why: {', '.join(rel.why)}",
                    rel.evidence_span,
                    rel.evidence_offset,
                    json.dumps(rel.why),
                    artifact_id,  # FK to artifact_queue
                ))
                counts["edges"] += 1
            except sqlite3.IntegrityError:
                pass  # Duplicate

        self.conn.commit()
        return counts

    def process_artifact(self, artifact_id: str) -> Dict[str, Any]:
        """
        Process an artifact from the queue.

        Updates artifact status and creates proposals.
        """
        self.connect()

        # Get artifact content
        row = self.conn.execute("""
            SELECT * FROM artifact_queue WHERE artifact_id = ?
        """, (artifact_id,)).fetchone()

        if not row:
            return {"error": f"Artifact {artifact_id} not found"}

        # Read content from artifact_path or URL
        content = ""
        if row["artifact_path"]:
            try:
                with open(row["artifact_path"], "r") as f:
                    content = f.read()
            except:
                pass

        if not content:
            return {"error": "Could not read artifact content"}

        # Update status to EXTRACTING
        self.conn.execute("""
            UPDATE artifact_queue SET status = 'EXTRACTING' WHERE artifact_id = ?
        """, (artifact_id,))
        self.conn.commit()

        try:
            # Run extraction
            result = self.extract(content)

            # Create proposals with artifact_id FK for traceability
            counts = self.create_proposals(
                result,
                source_url=row["url"] or "",
                artifact_path=row["artifact_path"] or "",
                artifact_id=artifact_id,  # FK to artifact_queue
            )

            # Update status to EXTRACTED
            self.conn.execute("""
                UPDATE artifact_queue
                SET status = 'EXTRACTED', extracted_at = ?
                WHERE artifact_id = ?
            """, (datetime.utcnow().isoformat() + "Z", artifact_id))
            self.conn.commit()

            return {
                "artifact_id": artifact_id,
                "entities": len(result.entities),
                "relations": len(result.relations),
                "claims": len(result.claims),
                "proposals_created": counts,
                "extraction_time_ms": result.extraction_time_ms,
            }

        except Exception as e:
            self.conn.execute("""
                UPDATE artifact_queue
                SET status = 'FAILED', error_message = ?
                WHERE artifact_id = ?
            """, (str(e), artifact_id))
            self.conn.commit()
            return {"error": str(e)}


def main():
    """Test the NLP agent."""
    import argparse

    parser = argparse.ArgumentParser(description="FGIP NLPAgent")
    parser.add_argument("--test", action="store_true", help="Run test extraction")
    parser.add_argument("--file", type=str, help="Extract from file")
    args = parser.parse_args()

    agent = NLPAgent("fgip.db")

    if args.test:
        sample = """
        According to the Treasury Department, Intel Corporation received a $4.2 billion
        CHIPS Act award for fab construction in Arizona. BlackRock increased its holdings
        in Intel by $1.8 billion during Q3 2025, according to SEC Form 13F filings.
        Senator Chuck Schumer sponsored the CHIPS and Science Act, which was signed
        by President Biden in August 2022. Critics allege the award process favored
        companies with existing lobbying relationships, though Treasury officials
        denied any impropriety.
        """

        result = agent.extract(sample)

        print(f"Extraction completed in {result.extraction_time_ms}ms")
        print(f"\nEntities ({len(result.entities)}):")
        for e in result.entities[:10]:
            print(f"  {e.text} [{e.entity_type}] -> {e.node_id_guess} (conf: {e.confidence:.2f})")

        print(f"\nRelations ({len(result.relations)}):")
        for r in result.relations:
            print(f"  {r.from_entity} --[{r.relation_type}]--> {r.to_entity}")
            print(f"    Evidence: \"{r.evidence_span[:60]}...\"")
            print(f"    Confidence: {r.confidence:.2f}")

        print(f"\nClaims ({len(result.claims)}):")
        for c in result.claims[:5]:
            print(f"  [{c.topic}] {c.claim_text[:80]}...")
            print(f"    Confidence: {c.confidence:.2f}, Counter: {c.counter_evidence}")

        print(f"\nCounter-evidence flags: {result.counter_evidence_flags}")

    elif args.file:
        with open(args.file, "r") as f:
            content = f.read()

        result = agent.extract(content)
        counts = agent.create_proposals(result)

        print(f"Extracted from {args.file}:")
        print(f"  Entities: {len(result.entities)}")
        print(f"  Relations: {len(result.relations)}")
        print(f"  Claims: {len(result.claims)}")
        print(f"  Proposals created: {counts}")


if __name__ == "__main__":
    main()
