"""FilterAgent - Hughes-style Integrity Triage.

NOT "vibes moderation" but **source-tier enforcement**.

This agent scores artifacts by:
1. Source tier (Tier 0 government primary = 1.0, Tier 3 social = 0.5)
2. Manipulation markers (urgency language, no citations, etc.)
3. Integrity boosters (primary documents, named officials, legal filings)

Output: integrity_score per artifact that propagates to downstream claims.

Usage:
    from fgip.agents.filter_agent import FilterAgent
    from fgip.db import FGIPDatabase

    db = FGIPDatabase("fgip.db")
    agent = FilterAgent(db)
    score = agent.score_artifact(artifact)
    print(f"Integrity: {score.final_score}, Flags: {score.flags}")
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import json
import re
import hashlib
import uuid

from .base import FGIPAgent, Artifact, StructuredFact, ProposedClaim, ProposedEdge
from fgip.text.normalize import normalize_text


@dataclass
class IntegrityAdjustment:
    """A single adjustment to integrity score."""
    marker: str
    adjustment: float
    reason: str
    evidence: Optional[str] = None  # Text snippet that triggered this


@dataclass
class IntegrityScore:
    """Complete integrity assessment for an artifact."""
    artifact_id: str
    source_url: str
    source_tier: str
    base_score: float
    adjustments: List[IntegrityAdjustment]
    final_score: float
    flags: List[str]  # Red flags that may block propagation
    manipulation_markers: List[str]
    integrity_boosters: List[str]
    novelty_score: float = 0.5
    se_score: float = 0.0  # Signal Entropy: H * C * D
    word_count: int = 0
    entity_density: float = 0.0
    scored_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "source_url": self.source_url,
            "source_tier": self.source_tier,
            "base_score": self.base_score,
            "adjustments": [
                {"marker": a.marker, "adjustment": a.adjustment, "reason": a.reason}
                for a in self.adjustments
            ],
            "final_score": self.final_score,
            "flags": self.flags,
            "manipulation_markers": self.manipulation_markers,
            "integrity_boosters": self.integrity_boosters,
            "novelty_score": self.novelty_score,
            "se_score": self.se_score,
            "scored_at": self.scored_at,
        }

    def should_block(self) -> bool:
        """Check if artifact should be blocked from propagation."""
        return len(self.flags) > 0 or self.final_score < 0.3

    def get_route(self) -> str:
        """Determine routing based on score."""
        if self.should_block():
            return "DEPRIORITIZE"
        elif self.final_score >= 0.8:
            return "FAST_TRACK"
        else:
            return "HUMAN_REVIEW"


class FilterAgent(FGIPAgent):
    """Chris-Hughes-style integrity triage.

    NOT: Vibes moderation
    IS: Distribution control - boost primary docs, penalize manipulation markers

    Output: integrity_score per artifact, propagates to downstream claims
    """

    # Source tier weights (cumulative, not replacement)
    SOURCE_WEIGHTS = {
        "TIER_0": 1.0,    # Government primary (EDGAR, USASpending, NRC, Congress.gov)
        "TIER_1": 0.85,   # Journalism with named sources (Reuters, AP, WSJ)
        "TIER_2": 0.70,   # Commentary/analysis (podcasts, substacks)
        "TIER_3": 0.50,   # Social media, anonymous sources
    }

    # Domain to tier mapping
    DOMAIN_TIERS = {
        # Tier 0 - Government Primary
        "sec.gov": "TIER_0",
        "edgar.sec.gov": "TIER_0",
        "efts.sec.gov": "TIER_0",
        "data.sec.gov": "TIER_0",
        "usaspending.gov": "TIER_0",
        "congress.gov": "TIER_0",
        "gao.gov": "TIER_0",
        "federalregister.gov": "TIER_0",
        "treasury.gov": "TIER_0",
        "nrc.gov": "TIER_0",
        "eia.gov": "TIER_0",
        "bls.gov": "TIER_0",
        "fred.stlouisfed.org": "TIER_0",
        "fec.gov": "TIER_0",
        "justice.gov": "TIER_0",
        "fara.gov": "TIER_0",
        "supremecourt.gov": "TIER_0",
        "uscourts.gov": "TIER_0",
        "energy.gov": "TIER_0",
        "commerce.gov": "TIER_0",
        "trade.gov": "TIER_0",

        # Tier 1 - Journalism
        "reuters.com": "TIER_1",
        "apnews.com": "TIER_1",
        "wsj.com": "TIER_1",
        "nytimes.com": "TIER_1",
        "washingtonpost.com": "TIER_1",
        "ft.com": "TIER_1",
        "bloomberg.com": "TIER_1",
        "bbc.com": "TIER_1",
        "politico.com": "TIER_1",
        "propublica.org": "TIER_1",
        "opensecrets.org": "TIER_1",

        # Tier 2 - Analysis/Commentary
        "substack.com": "TIER_2",
        "medium.com": "TIER_2",
        "seekingalpha.com": "TIER_2",
        "zerohedge.com": "TIER_2",
        "youtube.com": "TIER_2",

        # Tier 3 - Social/Anonymous
        "twitter.com": "TIER_3",
        "x.com": "TIER_3",
        "reddit.com": "TIER_3",
        "4chan.org": "TIER_3",
    }

    # Manipulation markers (penalize)
    MANIPULATION_MARKERS = {
        "urgency_language": {
            "adjustment": -0.15,
            "patterns": [
                r"\bACT\s+NOW\b", r"\bURGENT\b", r"\bLIMITED\s+TIME\b",
                r"\bDON'?T\s+MISS\b", r"\bBREAKING\b", r"\bEXCLUSIVE\b",
                r"\bMUST\s+SEE\b", r"\bSHOCKING\b", r"\bLAST\s+CHANCE\b",
                r"\bBEFORE\s+IT'?S?\s+TOO\s+LATE\b", r"\bLOAD\s+UP\b",
                r"\bTO\s+THE\s+MOON\b",
            ],
        },
        "excessive_caps": {
            "adjustment": -0.10,
            "patterns": [],  # Detected by ratio check in score_artifact()
        },
        "no_citations": {
            "adjustment": -0.20,
            "patterns": [],  # Detected by absence check in score_artifact()
        },
        "circular_sourcing": {
            "adjustment": -0.25,
            "patterns": [
                r"according to reports", r"it is believed",
                r"many experts", r"some say",
                r"which cites.*who references",  # Circular reference chain
                r"earlier report",  # Self-referential
            ],
        },
        "deleted_original": {
            "adjustment": -0.30,
            "patterns": [
                r"now[- ]deleted", r"deleted\s+tweet", r"link\s+no\s+longer",
                r"account\s+suspended", r"removed\s+post",
                r"page\s+not\s+found", r"unavailable\s+(?:link|source|content)",
            ],
        },
        "anonymous_source": {
            "adjustment": -0.15,
            "patterns": [
                r"anonymous\s+source", r"sources?\s+familiar",
                r"people\s+(?:close\s+to|familiar\s+with)", r"insiders?\s+say",
                r"sources?\s+say", r"someone\s+with\s+knowledge",
                r"person\s+(?:close\s+to|familiar\s+with)",
            ],
        },
        "prediction_without_range": {
            "adjustment": -0.10,
            "patterns": [
                r"(?:price\s+)?target\s+(?:is\s+)?(?:exactly\s+)?\$[\d,.]+(?!\s*[-–to]\s*\$)",
                r"\$[\d,.]+\s+(?:price\s+)?target(?!\s*[-–to]\s*\$)",
                r"will\s+(?:definitely|certainly)\s+reach",
                r"(?:by|at)\s+\w+\s+\d+(?:st|nd|rd|th)?\s+at\s+\d+:\d+",  # Precise timing
            ],
        },
        "emotional_language": {
            "adjustment": -0.10,
            "patterns": [
                r"\b(?:incredible|amazing|unbelievable|insane|crazy)\b",
                r"\b(?:disaster|catastrophe|collapse|crash)\b",
            ],
        },
        "clickbait_pattern": {
            "adjustment": -0.15,
            "patterns": [
                r"you won't believe", r"what happens next",
                r"this one trick", r"doctors hate",
            ],
        },
        "conspiratorial_framing": {
            "adjustment": -0.20,
            "patterns": [
                r"wake up", r"sheeple", r"masses",
                r"they don't want you to know",
            ],
        },
        "absolute_certainty": {
            "adjustment": -0.10,
            "patterns": [
                r"\b100%\b", r"\bguaranteed\b", r"\bcertain\b",
                r"\balways\b", r"\bnever\b",
            ],
        },
    }

    # Integrity boosters
    INTEGRITY_BOOSTERS = {
        "primary_document": {
            "adjustment": +0.20,
            "patterns": [
                r"SEC\s+Form\s+\d+", r"10-K", r"10-Q", r"8-K", r"13F",
                r"Congressional\s+Record", r"Federal\s+Register",
                r"Docket\s+No\.", r"Case\s+No\.",
            ],
        },
        "named_official": {
            "adjustment": +0.15,
            "patterns": [
                r"Secretary\s+\w+", r"Director\s+\w+", r"Commissioner\s+\w+",
                r"Chairman\s+\w+", r"Senator\s+\w+", r"Representative\s+\w+",
                r"CEO\s+\w+", r"CFO\s+\w+",
            ],
        },
        "legal_filing": {
            "adjustment": +0.20,
            "patterns": [
                r"filed\s+with\s+(?:the\s+)?(?:SEC|FTC|DOJ|court)",
                r"regulatory\s+filing", r"court\s+document",
                r"complaint\s+filed", r"motion\s+to",
            ],
        },
        "audit_verified": {
            "adjustment": +0.25,
            "patterns": [
                r"audited\s+financial", r"independent\s+audit",
                r"certified\s+public\s+accountant", r"Big\s+Four\s+audit",
            ],
        },
        "multiple_independent": {
            "adjustment": +0.15,
            "patterns": [
                r"confirmed\s+by\s+(?:multiple|several|two)",
                r"independently\s+verified",
            ],
        },
        "direct_quote": {
            "adjustment": +0.10,
            "patterns": [
                r'"[^"]{20,}"',  # Direct quote 20+ chars
                r"stated\s+that\s+\"",
            ],
        },
        "data_citation": {
            "adjustment": +0.10,
            "patterns": [
                r"according\s+to\s+(?:data|statistics)\s+from",
                r"Bureau\s+of\s+(?:Labor\s+)?Statistics",
                r"Federal\s+Reserve\s+data",
            ],
        },
        "specific_numbers": {
            "adjustment": +0.10,
            "patterns": [
                r'\$[\d,]+(?:\.\d{1,2})?[BMK]?',  # Money amounts
                r'\d+(?:\.\d+)?%',  # Percentages
            ],
        },
        "agency_citation": {
            "adjustment": +0.15,
            "patterns": [
                r'(?:SEC|DOJ|Treasury|GAO|CBO|Fed|FDIC|OCC)\s+(?:report|filing|statement|data)',
                r'(?:Form\s+)?(?:10-K|10-Q|8-K|13F|S-1|DEF 14A)',
                r'(?:Public Law|P\.L\.)\s+\d+-\d+',
                r'(?:H\.R\.|S\.)\s*\d+',
            ],
        },
    }

    # Red flags that block propagation
    RED_FLAGS = {
        "satire_disclaimer": [r"satire", r"parody", r"not real news"],
        "retracted": [r"correction:", r"editor's note:", r"this article has been updated"],
        "sponsored_content": [r"sponsored\s+(?:content|post)", r"paid\s+(?:promotion|advertisement)"],
        "ai_generated": [r"generated\s+by\s+AI", r"written\s+by\s+ChatGPT"],
    }

    def __init__(self, db, name: str = "filter-agent"):
        super().__init__(
            db, name,
            "Hughes-style integrity triage for source distribution control"
        )
        self._existing_entities = None
        self._existing_claim_hashes = None

    def _load_existing_data(self):
        """Load existing entities and claim hashes for novelty detection."""
        if self._existing_entities is not None:
            return

        conn = self.db.connect()

        # Load entity names for novelty detection
        rows = conn.execute("SELECT LOWER(name) as name FROM nodes").fetchall()
        self._existing_entities = {row["name"] for row in rows}

        # Load claim hashes for duplicate detection
        self._existing_claim_hashes = set()
        rows = conn.execute("SELECT claim_text FROM claims").fetchall()
        for row in rows:
            h = hashlib.sha256(row["claim_text"].lower().encode()).hexdigest()[:16]
            self._existing_claim_hashes.add(h)

        # Also load from proposed_claims
        rows = conn.execute("SELECT claim_text FROM proposed_claims").fetchall()
        for row in rows:
            h = hashlib.sha256(row["claim_text"].lower().encode()).hexdigest()[:16]
            self._existing_claim_hashes.add(h)

    def collect(self) -> List[Artifact]:
        """Collect artifacts from queue needing filtering."""
        conn = self.db.connect()

        # Get unfiltered artifacts from queue
        rows = conn.execute(
            """SELECT artifact_id, source_id, url, artifact_path, content_type
               FROM artifact_queue
               WHERE status = 'PENDING'
               ORDER BY created_at DESC
               LIMIT 100"""
        ).fetchall()

        artifacts = []
        for row in rows:
            artifact = Artifact(
                url=row["url"] or "",
                artifact_type=row["content_type"] or "html",
                local_path=row["artifact_path"],
                metadata={
                    "artifact_id": row["artifact_id"],
                    "source_id": row["source_id"],
                },
            )
            artifacts.append(artifact)

        return artifacts

    def extract(self, artifacts: List[Artifact]) -> List[StructuredFact]:
        """Extract is not used - scoring happens in propose()."""
        return []

    def propose(
        self, facts: List[StructuredFact]
    ) -> Tuple[List[ProposedClaim], List[ProposedEdge]]:
        """Not used for FilterAgent - use score_artifact instead."""
        return ([], [])

    def run(self) -> Dict[str, Any]:
        """Run filter agent on queued artifacts."""
        results = {
            "agent": self.name,
            "artifacts_scored": 0,
            "high_integrity": 0,  # >= 0.8
            "medium_integrity": 0,  # 0.5-0.8
            "low_integrity": 0,  # < 0.5
            "blocked": 0,  # Has red flags
            "errors": [],
        }

        try:
            artifacts = self.collect()

            for artifact in artifacts:
                try:
                    content = self._read_artifact_content(artifact)
                    score = self.score_artifact(artifact, content)

                    # Categorize
                    if score.should_block():
                        results["blocked"] += 1
                    elif score.final_score >= 0.8:
                        results["high_integrity"] += 1
                    elif score.final_score >= 0.5:
                        results["medium_integrity"] += 1
                    else:
                        results["low_integrity"] += 1

                    # Save to database
                    self._save_integrity_score(score)
                    results["artifacts_scored"] += 1

                except Exception as e:
                    results["errors"].append(f"{artifact.url}: {str(e)}")

        except Exception as e:
            results["errors"].append(str(e))

        return results

    def _read_artifact_content(self, artifact: Artifact) -> str:
        """Read artifact content from local path."""
        if artifact.local_path:
            try:
                with open(artifact.local_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
            except Exception:
                pass
        return ""

    def get_tier_from_url(self, url: str) -> str:
        """Determine source tier from URL domain."""
        if not url:
            return "TIER_3"

        # Extract domain
        import urllib.parse
        try:
            parsed = urllib.parse.urlparse(url)
            domain = parsed.netloc.lower()

            # Remove www prefix
            if domain.startswith("www."):
                domain = domain[4:]

            # Check exact match first
            if domain in self.DOMAIN_TIERS:
                return self.DOMAIN_TIERS[domain]

            # Check if subdomain of known domain
            for known_domain, tier in self.DOMAIN_TIERS.items():
                if domain.endswith("." + known_domain):
                    return tier

            # Default based on TLD
            if domain.endswith(".gov"):
                return "TIER_0"
            elif domain.endswith(".edu"):
                return "TIER_1"
            elif domain.endswith(".org"):
                return "TIER_2"

        except Exception:
            pass

        return "TIER_3"

    def _calculate_novelty(self, content: str) -> Tuple[float, str]:
        """Calculate novelty score based on overlap with existing graph."""
        self._load_existing_data()

        content_lower = content.lower()

        # Check for duplicate claim
        content_hash = hashlib.sha256(content_lower.encode()).hexdigest()[:16]
        if content_hash in self._existing_claim_hashes:
            return 0.0, "DUPLICATE_CLAIM"

        # Check entity overlap with existing graph
        words = set(content_lower.split())
        overlap = len(words & self._existing_entities)

        if not self._existing_entities:
            return 1.0, "NO_EXISTING_DATA"

        # More overlap = less novel (but not necessarily bad)
        overlap_ratio = overlap / min(len(words), 100) if words else 0

        # Novelty is inverse of overlap, but penalize if TOO novel (no connection)
        if overlap == 0:
            return 0.3, "NO_ENTITY_OVERLAP"  # Suspicious - no connection to graph
        elif overlap_ratio > 0.5:
            return 0.4, "HIGH_OVERLAP"
        else:
            return 0.8, "GOOD_NOVELTY"

    def _calculate_signal_entropy(
        self,
        content: str,
        url: str,
        novelty_score: float,
        attribution_codes: List[str]
    ) -> float:
        """Calculate Signal Entropy: Se = H * C * D"""
        # H = novelty/entropy
        H = novelty_score

        # C = coherence from attribution quality (0-1)
        C = min(1.0, len(attribution_codes) * 0.15)

        # D = dimensional depth
        D = self._dimensional_depth(content, url, attribution_codes)

        return H * C * D

    def _dimensional_depth(
        self,
        content: str,
        url: str,
        attr_codes: List[str]
    ) -> float:
        """
        Calculate dimensional depth (D in Se = H * C * D).

        D = (has_primary_doc + has_numbers + has_named_entities + has_citations) / 4
        """
        scores = []
        combined = url + " " + content

        # Has primary doc?
        primary_patterns = [r'\.gov/', r'sec\.gov', r'treasury\.gov', r'\.pdf$']
        has_primary = any(
            re.search(p, combined, re.IGNORECASE)
            for p in primary_patterns
        )
        scores.append(1.0 if has_primary else 0.0)

        # Has specific numbers?
        has_numbers = bool(re.search(r'\$[\d,]+|\d+(?:\.\d+)?%', content))
        scores.append(1.0 if has_numbers else 0.0)

        # Has named entities?
        has_named = any(c in attr_codes for c in [
            "named_official", "direct_quote"
        ])
        scores.append(1.0 if has_named else 0.0)

        # Has agency/filing citations?
        has_citations = any(c in attr_codes for c in [
            "agency_citation", "legal_filing", "primary_document"
        ])
        scores.append(1.0 if has_citations else 0.0)

        return sum(scores) / len(scores) if scores else 0.0

    def score_artifact(
        self,
        artifact: Artifact,
        content: Optional[str] = None
    ) -> IntegrityScore:
        """Score an artifact for integrity.

        Args:
            artifact: The artifact to score
            content: Optional pre-loaded content (if None, will try to load)

        Returns:
            IntegrityScore with full assessment
        """
        # Generate artifact ID
        artifact_id = artifact.metadata.get("artifact_id") or hashlib.sha256(
            artifact.url.encode()
        ).hexdigest()[:16]

        # Get source tier
        source_tier = self.get_tier_from_url(artifact.url)
        base_score = self.SOURCE_WEIGHTS.get(source_tier, 0.5)

        # Load content if needed
        if content is None:
            content = self._read_artifact_content(artifact)

        # Normalize content for pattern detection (neutralizes obfuscation)
        # Keep original for word count and entity density calculations
        normalized = normalize_text(content) if content else ""

        # Apply adjustments
        adjustments = []
        manipulation_markers = []
        integrity_boosters = []
        flags = []

        # Check manipulation markers (use normalized content)
        for marker_name, marker_info in self.MANIPULATION_MARKERS.items():
            for pattern in marker_info["patterns"]:
                if re.search(pattern, normalized, re.IGNORECASE):
                    adjustments.append(IntegrityAdjustment(
                        marker=marker_name,
                        adjustment=marker_info["adjustment"],
                        reason=f"Detected pattern: {pattern}",
                    ))
                    manipulation_markers.append(marker_name)
                    break

        # Check excessive_caps via ratio (special case - not pattern-based)
        # Use normalized content for consistent detection
        if normalized and "excessive_caps" not in manipulation_markers:
            words = normalized.split()
            if len(words) >= 5:
                # Count words that are all caps (3+ characters)
                all_caps_words = sum(1 for w in words if len(w) >= 3 and w.isupper())
                caps_ratio = all_caps_words / len(words) if words else 0
                # Trigger if >= 35% caps OR >= 4 all-caps words
                if caps_ratio >= 0.35 or all_caps_words >= 4:
                    adjustments.append(IntegrityAdjustment(
                        marker="excessive_caps",
                        adjustment=-0.10,
                        reason=f"Excessive caps: {all_caps_words} all-caps words ({caps_ratio:.0%})",
                    ))
                    manipulation_markers.append("excessive_caps")

        # Check no citations (special case)
        # Trigger if: contains claim-y verbs AND no evidence patterns
        # Use normalized content for pattern matching
        if normalized and "no_citations" not in manipulation_markers:
            # Claim-y language patterns
            has_claims = bool(re.search(
                r"\b(?:will\s+(?:triple|double|skyrocket|moon)|guaranteed|confirmed|\d{2,4}%\s*gains?|certain|to\s+the\s+moon)\b",
                normalized, re.IGNORECASE
            ))
            # Evidence patterns (citations, URLs, document references)
            has_evidence = bool(re.search(
                r"(?:according\s+to|source:|citation:|ref\.|see\s+also|\[\d+\]|https?://|"
                r"Form\s+(?:10-K|10-Q|8-K|13F)|SEC\s+Form|Federal\s+Register|Docket\s+No\.?|"
                r"CIK\s+\d|\.gov\b)",
                normalized, re.IGNORECASE
            ))
            # Flag if has claims but no evidence (OR substantial content with no evidence)
            # Use original content length for size check
            if (has_claims and not has_evidence) or (len(content or "") > 500 and not has_evidence):
                adjustments.append(IntegrityAdjustment(
                    marker="no_citations",
                    adjustment=-0.20,
                    reason="Claims without citations or evidence",
                ))
                manipulation_markers.append("no_citations")

        # Check integrity boosters (use normalized content)
        for booster_name, booster_info in self.INTEGRITY_BOOSTERS.items():
            for pattern in booster_info["patterns"]:
                if re.search(pattern, normalized, re.IGNORECASE):
                    adjustments.append(IntegrityAdjustment(
                        marker=booster_name,
                        adjustment=booster_info["adjustment"],
                        reason=f"Positive signal: {pattern}",
                    ))
                    integrity_boosters.append(booster_name)
                    break

        # Check red flags (use normalized content)
        for flag_name, patterns in self.RED_FLAGS.items():
            for pattern in patterns:
                if re.search(pattern, normalized, re.IGNORECASE):
                    flags.append(flag_name)
                    break

        # Calculate final score
        total_adjustment = sum(a.adjustment for a in adjustments)
        final_score = max(0.0, min(1.0, base_score + total_adjustment))

        # Calculate novelty and signal entropy
        novelty_score, _ = self._calculate_novelty(content)
        se_score = self._calculate_signal_entropy(
            content, artifact.url, novelty_score, integrity_boosters
        )

        # Word count and entity density
        word_count = len(content.split()) if content else 0
        entity_patterns = [
            r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b',  # Proper noun phrases
            r'\b(?:Inc\.|Corp\.|LLC|Ltd\.|Co\.)\b',  # Company suffixes
        ]
        entity_count = sum(
            len(re.findall(pattern, content))
            for pattern in entity_patterns
        )
        entity_density = (entity_count / max(word_count, 1)) * 100

        return IntegrityScore(
            artifact_id=artifact_id,
            source_url=artifact.url,
            source_tier=source_tier,
            base_score=base_score,
            adjustments=adjustments,
            final_score=final_score,
            flags=flags,
            manipulation_markers=manipulation_markers,
            integrity_boosters=integrity_boosters,
            novelty_score=novelty_score,
            se_score=se_score,
            word_count=word_count,
            entity_density=entity_density,
        )

    def score_artifact_by_id(self, artifact_id: str) -> Optional[IntegrityScore]:
        """Score an artifact by its ID in the queue."""
        conn = self.db.connect()

        row = conn.execute(
            """SELECT url, artifact_path, content_type
               FROM artifact_queue WHERE artifact_id = ?""",
            (artifact_id,)
        ).fetchone()

        if not row:
            return None

        artifact = Artifact(
            url=row["url"] or "",
            artifact_type=row["content_type"] or "html",
            local_path=row["artifact_path"],
            metadata={"artifact_id": artifact_id},
        )

        return self.score_artifact(artifact)

    def _save_integrity_score(self, score: IntegrityScore):
        """Save integrity score to database."""
        conn = self.db.connect()

        conn.execute(
            """INSERT OR REPLACE INTO integrity_scores
               (artifact_id, source_url, source_tier, base_score, adjustments,
                final_score, flags, manipulation_markers, integrity_boosters,
                scored_at, agent_name)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                score.artifact_id,
                score.source_url,
                score.source_tier,
                score.base_score,
                json.dumps([a.__dict__ for a in score.adjustments]),
                score.final_score,
                json.dumps(score.flags),
                json.dumps(score.manipulation_markers),
                json.dumps(score.integrity_boosters),
                score.scored_at,
                self.agent_name,
            )
        )

        # Update artifact_queue status
        route = score.get_route()

        conn.execute(
            """UPDATE artifact_queue SET
               status = 'FILTERED',
               filter_score = ?,
               route = ?,
               manipulation_flags = ?,
               reason_codes = ?,
               novelty_score = ?,
               se_score = ?
               WHERE artifact_id = ?""",
            (
                score.final_score * 100,  # 0-100 scale
                route,
                json.dumps(score.manipulation_markers),
                json.dumps(score.integrity_boosters),
                score.novelty_score,
                score.se_score,
                score.artifact_id,
            )
        )

        conn.commit()

    def get_integrity_score(self, artifact_id: str) -> Optional[IntegrityScore]:
        """Get previously computed integrity score."""
        conn = self.db.connect()

        row = conn.execute(
            """SELECT * FROM integrity_scores WHERE artifact_id = ?""",
            (artifact_id,)
        ).fetchone()

        if not row:
            return None

        adjustments = [
            IntegrityAdjustment(**adj)
            for adj in json.loads(row["adjustments"] or "[]")
        ]

        return IntegrityScore(
            artifact_id=row["artifact_id"],
            source_url=row["source_url"],
            source_tier=row["source_tier"],
            base_score=row["base_score"],
            adjustments=adjustments,
            final_score=row["final_score"],
            flags=json.loads(row["flags"] or "[]"),
            manipulation_markers=json.loads(row["manipulation_markers"] or "[]"),
            integrity_boosters=json.loads(row["integrity_boosters"] or "[]"),
            scored_at=row["scored_at"],
        )

    def score_text(self, text: str, source_url: str = "") -> IntegrityScore:
        """Score raw text without an artifact.

        Useful for testing or scoring inline content.
        """
        artifact = Artifact(
            url=source_url,
            artifact_type="text",
            metadata={"artifact_id": hashlib.sha256(text.encode()).hexdigest()[:16]},
        )
        return self.score_artifact(artifact, content=text)

    def get_queue_stats(self) -> Dict[str, Any]:
        """Get statistics about the artifact queue."""
        conn = self.db.connect()

        stats = {
            "by_route": {},
            "by_status": {},
            "avg_score": 0,
            "total": 0,
        }

        # By route
        rows = conn.execute(
            "SELECT route, COUNT(*) as cnt FROM artifact_queue GROUP BY route"
        ).fetchall()
        stats["by_route"] = {row["route"]: row["cnt"] for row in rows}

        # By status
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM artifact_queue GROUP BY status"
        ).fetchall()
        stats["by_status"] = {row["status"]: row["cnt"] for row in rows}

        # Average score
        row = conn.execute(
            "SELECT AVG(filter_score) as avg, COUNT(*) as cnt FROM artifact_queue"
        ).fetchone()
        stats["avg_score"] = row["avg"] or 0
        stats["total"] = row["cnt"]

        return stats
