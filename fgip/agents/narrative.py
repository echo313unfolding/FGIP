"""FGIP Investigative Narrative & Divergence Agent.

Two-stream architecture detecting divergence between:
- Stream A: Investigative journalism (ProPublica, Intercept, OCCRP, etc.)
- Stream B: Lobby rhetoric (Heritage, Chamber, Cato, trade groups)

When journalism contradicts lobby narratives, that's the highest-value signal.

Tier 1 agent for investigations, Tier 2 for rhetoric tracking.
"""

import hashlib
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

from .base import FGIPAgent, Artifact, StructuredFact, ProposedClaim, ProposedEdge, ProposedNode


USER_AGENT = "FGIP Investigative Narrative (research@fgip.org)"


@dataclass
class NarrativeSource:
    """A narrative source configuration."""
    id: str
    name: str
    feed_url: str
    stream: str  # "investigative" or "rhetoric"
    tier: int
    focus: List[str]


# Stream A: Investigative Journalism Sources
INVESTIGATIVE_SOURCES = [
    NarrativeSource("propublica", "ProPublica", "https://www.propublica.org/feeds/propublica/main", "investigative", 1, ["accountability", "nonprofit", "fraud"]),
    NarrativeSource("intercept", "The Intercept", "https://theintercept.com/feed/?lang=en", "investigative", 1, ["national_security", "surveillance", "corporate"]),
    NarrativeSource("pogo", "POGO", "https://www.pogo.org/feed", "investigative", 1, ["federal_spending", "contracting", "revolving_door"]),
    NarrativeSource("occrp", "OCCRP", "https://www.occrp.org/en/rss.xml", "investigative", 1, ["money_laundering", "corruption", "offshore"]),
    NarrativeSource("lever", "The Lever", "https://www.levernews.com/rss/", "investigative", 1, ["corporate_influence", "policy"]),
    NarrativeSource("muckrack_foia", "MuckRock", "https://www.muckrock.com/news/feed/", "investigative", 1, ["foia", "government_documents"]),
    NarrativeSource("reuters_inv", "Reuters Investigations", "https://www.reuters.com/investigates/feed", "investigative", 1, ["corporate", "international"]),
    NarrativeSource("marshall", "Marshall Project", "https://www.themarshallproject.org/rss/all", "investigative", 1, ["criminal_justice"]),
]

# Stream B: Lobby/Think Tank Rhetoric Sources
RHETORIC_SOURCES = [
    NarrativeSource("heritage", "Heritage Foundation", "https://www.heritage.org/rss/all-research-and-commentary", "rhetoric", 2, ["policy", "conservative"]),
    NarrativeSource("cato", "Cato Institute", "https://www.cato.org/rss/blog", "rhetoric", 2, ["libertarian", "trade", "regulation"]),
    NarrativeSource("aei", "American Enterprise Institute", "https://www.aei.org/feed/", "rhetoric", 2, ["economics", "policy"]),
    NarrativeSource("brookings", "Brookings Institution", "https://www.brookings.edu/feed/", "rhetoric", 2, ["policy", "centrist"]),
    NarrativeSource("cfr", "Council on Foreign Relations", "https://www.cfr.org/rss/articles", "rhetoric", 2, ["foreign_policy"]),
    NarrativeSource("chamber", "US Chamber of Commerce", "https://www.uschamber.com/feed", "rhetoric", 2, ["business", "lobbying", "trade"]),
]

# Keywords for claim extraction and divergence detection
DIVERGENCE_TOPICS = {
    "trade_policy": ["tariff", "PNTR", "free trade", "protectionism", "reshoring", "offshoring"],
    "corporate_accountability": ["fraud", "embezzlement", "corruption", "indicted", "charged", "settlement"],
    "financial_system": ["bailout", "too big to fail", "Federal Reserve", "Wall Street", "Goldman", "JPMorgan"],
    "lobbying": ["lobbying", "revolving door", "PAC", "campaign finance", "K Street", "lobbyist"],
    "regulatory_capture": ["deregulation", "regulatory capture", "revolving door", "industry influence"],
    "censorship": ["censorship", "misinformation", "content moderation", "Section 230"],
}


class NarrativeAgent(FGIPAgent):
    """Investigative Narrative & Divergence Detection Agent.

    Monitors two streams and detects when:
    1. Investigative journalism makes a finding
    2. Lobby/think tank rhetoric contradicts it
    3. The divergence reveals thesis-relevant patterns
    """

    def __init__(self, db, artifact_dir: str = "data/artifacts/narrative"):
        super().__init__(
            db=db,
            name="narrative",
            description="Investigative Narrative - Two-stream divergence detection"
        )
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self._rate_limit_delay = 1.0
        self._last_request_time = 0
        self._existing_claims = None

    def _rate_limit(self):
        """Enforce rate limiting."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._rate_limit_delay:
            time.sleep(self._rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    def _fetch_url(self, url: str) -> Optional[bytes]:
        """Fetch URL with rate limiting."""
        self._rate_limit()

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            }
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()
        except Exception:
            return None

    def _get_existing_claims(self) -> List[Dict]:
        """Get existing claims for divergence detection."""
        if self._existing_claims is None:
            conn = self.db.connect()
            rows = conn.execute(
                "SELECT claim_id, claim_text, topic FROM claims LIMIT 1000"
            ).fetchall()
            self._existing_claims = [
                {"claim_id": r["claim_id"], "text": r["claim_text"], "topic": r["topic"]}
                for r in rows
            ]
        return self._existing_claims

    def collect(self) -> List[Artifact]:
        """Collect from both investigative and rhetoric streams."""
        artifacts = []

        all_sources = INVESTIGATIVE_SOURCES + RHETORIC_SOURCES

        for source in all_sources:
            content = self._fetch_url(source.feed_url)
            if not content:
                continue

            content_hash = hashlib.sha256(content).hexdigest()
            local_path = self.artifact_dir / f"feed_{source.id}.xml"

            with open(local_path, "wb") as f:
                f.write(content)

            artifact = Artifact(
                url=source.feed_url,
                artifact_type="rss",
                local_path=str(local_path),
                content_hash=content_hash,
                metadata={
                    "source_id": source.id,
                    "source_name": source.name,
                    "stream": source.stream,
                    "tier": source.tier,
                    "focus": source.focus,
                }
            )
            artifacts.append(artifact)

        return artifacts

    def extract(self, artifacts: List[Artifact]) -> List[StructuredFact]:
        """Extract claims and detect divergences between streams."""
        facts = []

        # Separate by stream
        investigative_facts = []
        rhetoric_facts = []

        for artifact in artifacts:
            stream = artifact.metadata.get("stream", "")
            articles = self._parse_rss_feed(artifact)

            for article in articles:
                # Extract claims from article
                claims = self._extract_claims_from_article(article, artifact)

                for claim in claims:
                    if stream == "investigative":
                        investigative_facts.append(claim)
                    else:
                        rhetoric_facts.append(claim)

                    facts.append(claim)

        # Detect divergences between streams
        divergences = self._detect_divergences(investigative_facts, rhetoric_facts)
        facts.extend(divergences)

        return facts

    def _parse_rss_feed(self, artifact: Artifact) -> List[Dict]:
        """Parse RSS feed and extract articles."""
        articles = []

        try:
            tree = ET.parse(artifact.local_path)
            root = tree.getroot()
        except Exception:
            return articles

        channel = root.find("channel")
        if channel is None:
            return articles

        items = channel.findall("item")

        for item in items[:10]:  # Recent 10
            title_el = item.find("title")
            desc_el = item.find("description")
            link_el = item.find("link")
            pub_date_el = item.find("pubDate")

            articles.append({
                "title": title_el.text if title_el is not None else "",
                "description": desc_el.text if desc_el is not None else "",
                "url": link_el.text if link_el is not None else "",
                "pub_date": pub_date_el.text if pub_date_el is not None else "",
                "source_name": artifact.metadata.get("source_name", ""),
                "stream": artifact.metadata.get("stream", ""),
            })

        return articles

    def _extract_claims_from_article(self, article: Dict, artifact: Artifact) -> List[StructuredFact]:
        """Extract factual claims from article."""
        facts = []
        text = f"{article.get('title', '')} {article.get('description', '')}"
        stream = article.get("stream", "")
        source_name = article.get("source_name", "")

        # Identify relevant topics
        topics_matched = []
        for topic, keywords in DIVERGENCE_TOPICS.items():
            if any(kw.lower() in text.lower() for kw in keywords):
                topics_matched.append(topic)

        if not topics_matched:
            return facts

        # Extract entities mentioned
        entities = self._extract_entities(text)

        # Create fact for article
        fact_type = "investigative_finding" if stream == "investigative" else "rhetoric_claim"

        for topic in topics_matched:
            fact = StructuredFact(
                fact_type=fact_type,
                subject=source_name,
                predicate="REPORTED" if stream == "investigative" else "ARGUED",
                object=topic,
                source_artifact=artifact,
                confidence=0.7 if stream == "investigative" else 0.5,
                date_occurred=article.get("pub_date", ""),
                raw_text=article.get("title", ""),
                metadata={
                    "article_url": article.get("url", ""),
                    "article_title": article.get("title", ""),
                    "description": article.get("description", "")[:500],
                    "stream": stream,
                    "topic": topic,
                    "entities_mentioned": entities,
                }
            )
            facts.append(fact)

        return facts

    def _extract_entities(self, text: str) -> List[str]:
        """Extract named entities from text."""
        # Simple entity extraction: capitalized multi-word phrases
        pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b'
        matches = re.findall(pattern, text)

        # Filter common non-entities
        stop_phrases = {"The New", "In The", "At The", "For The", "On The"}
        entities = [m for m in matches if m not in stop_phrases and len(m) > 3]

        return list(set(entities))[:10]

    def _detect_divergences(self, investigative: List[StructuredFact], rhetoric: List[StructuredFact]) -> List[StructuredFact]:
        """Detect divergences between investigative findings and rhetoric claims."""
        divergences = []

        # Group by topic
        inv_by_topic = {}
        for fact in investigative:
            topic = fact.metadata.get("topic", "")
            if topic not in inv_by_topic:
                inv_by_topic[topic] = []
            inv_by_topic[topic].append(fact)

        rhet_by_topic = {}
        for fact in rhetoric:
            topic = fact.metadata.get("topic", "")
            if topic not in rhet_by_topic:
                rhet_by_topic[topic] = []
            rhet_by_topic[topic].append(fact)

        # Find overlapping topics
        for topic in set(inv_by_topic.keys()) & set(rhet_by_topic.keys()):
            inv_facts = inv_by_topic[topic]
            rhet_facts = rhet_by_topic[topic]

            # Create divergence fact
            divergence = StructuredFact(
                fact_type="divergence",
                subject=topic,
                predicate="DIVERGENCE_DETECTED",
                object=f"{len(inv_facts)} investigative vs {len(rhet_facts)} rhetoric claims",
                source_artifact=inv_facts[0].source_artifact,
                confidence=0.8,
                raw_text=f"Topic '{topic}' has claims from both streams",
                metadata={
                    "topic": topic,
                    "investigative_sources": [f.subject for f in inv_facts],
                    "rhetoric_sources": [f.subject for f in rhet_facts],
                    "investigative_titles": [f.raw_text for f in inv_facts[:3]],
                    "rhetoric_titles": [f.raw_text for f in rhet_facts[:3]],
                }
            )
            divergences.append(divergence)

        return divergences

    def propose(self, facts: List[StructuredFact]) -> tuple[List[ProposedClaim], List[ProposedEdge], List[ProposedNode]]:
        """Generate proposals with divergence flagging."""
        claims = []
        edges = []
        nodes = []

        for fact in facts:
            proposal_id = self._generate_proposal_id()

            # Generate claim text
            if fact.fact_type == "divergence":
                claim_text = f"DIVERGENCE on '{fact.subject}': {fact.object}"
                topic = "SIGNAL_LAYER"
            elif fact.fact_type == "investigative_finding":
                claim_text = f"{fact.subject} investigation on {fact.object}: {fact.raw_text}"
                topic = fact.metadata.get("topic", "Accountability")
            elif fact.fact_type == "rhetoric_claim":
                claim_text = f"{fact.subject} rhetoric on {fact.object}: {fact.raw_text}"
                topic = "ThinkTank"
            else:
                claim_text = f"{fact.subject} {fact.predicate} {fact.object}"
                topic = "SIGNAL_LAYER"

            # Set promotion requirement based on stream
            if fact.fact_type == "investigative_finding":
                promo_req = "Verify investigative finding against primary source documents"
            elif fact.fact_type == "divergence":
                promo_req = "Analyze both streams; determine which has stronger evidence"
            else:
                promo_req = "Cross-reference rhetoric against investigative findings"

            claim = ProposedClaim(
                proposal_id=proposal_id,
                claim_text=claim_text,
                topic=topic,
                agent_name=self.name,
                source_url=fact.metadata.get("article_url", fact.source_artifact.url),
                artifact_path=fact.source_artifact.local_path,
                artifact_hash=fact.source_artifact.content_hash,
                reasoning=f"Stream: {fact.metadata.get('stream', 'unknown')} | {fact.fact_type}",
                promotion_requirement=promo_req,
            )
            claims.append(claim)

            # Create edge for divergences
            if fact.fact_type == "divergence":
                edge_id = self._generate_proposal_id()

                edge = ProposedEdge(
                    proposal_id=edge_id,
                    from_node="investigative-journalism",
                    to_node="lobby-rhetoric",
                    relationship="DIVERGES_FROM",
                    agent_name=self.name,
                    detail=f"Topic: {fact.subject}. {fact.object}",
                    proposed_claim_id=proposal_id,
                    confidence=fact.confidence,
                    reasoning="Divergence detected between investigative findings and lobby rhetoric",
                )
                edges.append(edge)

        return claims, edges, nodes
