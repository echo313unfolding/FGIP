"""FGIP Promethean Action Agent - Independent Media Signal Layer.

Monitors Promethean Action newsletter (Ghost platform) for policy analysis
relevant to reshoring thesis, American System economics, and industrial policy.

Tier 2 agent - uses independent media/think tank sources.

Promethean Action covers:
- Trade policy (tariffs, reshoring, decoupling)
- Industrial policy (CHIPS Act, infrastructure)
- American System economics (Hamilton, Clay, Lincoln tradition)
- Anti-globalist economic analysis

Safety rules:
- Uses public RSS feeds only
- Stores only article metadata and excerpts
- Respects rate limits
- Artifacts saved locally with SHA256 hash
"""

import hashlib
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
import urllib.request
import urllib.error

try:
    from .base import FGIPAgent, Artifact, StructuredFact, ProposedClaim, ProposedEdge, ProposedNode
except ImportError:
    from base import FGIPAgent, Artifact, StructuredFact, ProposedClaim, ProposedEdge, ProposedNode


# Promethean Action RSS feed (Ghost platform)
PROMETHEAN_FEEDS = {
    "promethean_main": {
        "url": "https://www.prometheanaction.com/latest/rss",
        "tier": 2,
        "name": "Promethean Action",
        "signal_type": "policy_analysis",
    },
}

# Keywords specific to Promethean Action's focus areas
PROMETHEAN_KEYWORDS = [
    # American System economics
    "american system", "hamilton", "hamiltonian", "national bank",
    "internal improvements", "tariff", "protective tariff",
    "henry clay", "lincoln", "american school",

    # Trade/Industrial policy
    "reshoring", "onshoring", "nearshoring", "friend-shoring",
    "chips act", "industrial policy", "manufacturing",
    "supply chain", "decoupling", "deglobalization",

    # China/Geopolitics
    "china trade", "ccp", "belt and road", "made in china 2025",
    "trade war", "tariffs", "wto", "pntr",

    # Infrastructure
    "infrastructure", "rail", "high-speed rail", "nuclear",
    "energy independence", "grid",

    # Finance/Monetary
    "federal reserve", "central bank", "credit system",
    "wall street", "speculation", "glass-steagall",

    # Defense
    "defense industrial base", "national security",
    "military industrial", "shipbuilding",
]

# Entities to track for edge creation
PROMETHEAN_ENTITIES = {
    # Legislation
    "chips act": "chips-act",
    "chips and science act": "chips-act",
    "pntr": "pntr-2000",
    "permanent normal trade relations": "pntr-2000",
    "inflation reduction act": "inflation-reduction-act",
    "infrastructure investment": "infrastructure-investment-jobs-act",

    # Companies (reshoring focus)
    "intel": "intel-corp",
    "tsmc": "tsmc",
    "samsung semiconductor": "samsung-semiconductor",
    "micron": "micron-technology",
    "globalfoundries": "globalfoundries",

    # Institutions
    "chamber of commerce": "us-chamber-of-commerce",
    "business roundtable": "business-roundtable",
    "federal reserve": "federal-reserve",
    "treasury": "us-treasury",

    # Investors
    "blackrock": "blackrock-inc",
    "vanguard": "vanguard-group",
    "state street": "state-street-corp",

    # Countries
    "china": "china-prc",
    "taiwan": "taiwan-roc",
}

USER_AGENT = "FGIP Research Agent (contact@example.com)"


class PrometheanAgent(FGIPAgent):
    """Promethean Action newsletter monitoring agent.

    Monitors the Promethean Action Ghost newsletter for:
    - Policy analysis relevant to reshoring thesis
    - American System economics commentary
    - Trade/industrial policy coverage
    - China/geopolitics analysis

    Proposes ANALYZES and REPORTS_ON edges linking analysis to entities.
    """

    def __init__(self, db, artifact_dir: str = "data/artifacts/promethean"):
        super().__init__(
            db=db,
            name="promethean",
            description="Promethean Action newsletter - American System policy analysis"
        )
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self._rate_limit_delay = 3.0  # 3 seconds between requests
        self._last_request_time = 0
        self._seen_urls = set()

    def _rate_limit(self):
        """Enforce rate limiting."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._rate_limit_delay:
            time.sleep(self._rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    def _fetch_url(self, url: str) -> Optional[bytes]:
        """Fetch URL with proper headers and rate limiting."""
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
        except urllib.error.HTTPError as e:
            print(f"HTTP error fetching {url}: {e.code}")
            return None
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None

    def _load_seen_urls(self):
        """Load previously seen URLs to avoid re-processing."""
        seen_file = self.artifact_dir / "seen_urls.json"
        if seen_file.exists():
            try:
                with open(seen_file) as f:
                    self._seen_urls = set(json.load(f))
            except Exception:
                self._seen_urls = set()

    def _save_seen_urls(self):
        """Save seen URLs for persistence."""
        seen_file = self.artifact_dir / "seen_urls.json"
        recent = list(self._seen_urls)[-1000:]  # Keep last 1000
        with open(seen_file, "w") as f:
            json.dump(recent, f)

    def _parse_ghost_rss(self, content: bytes, feed_id: str) -> List[Dict[str, Any]]:
        """Parse Ghost platform RSS feed.

        Ghost RSS typically includes:
        - title, link, description
        - content:encoded (full article HTML)
        - dc:creator (author)
        - pubDate
        - category tags
        """
        items = []

        try:
            root = ET.fromstring(content)
        except ET.ParseError as e:
            print(f"XML parse error: {e}")
            return items

        feed_info = PROMETHEAN_FEEDS.get(feed_id, {})

        # Define namespaces Ghost uses
        namespaces = {
            "content": "http://purl.org/rss/1.0/modules/content/",
            "dc": "http://purl.org/dc/elements/1.1/",
            "atom": "http://www.w3.org/2005/Atom",
        }

        # Find channel items
        for item in root.iter("item"):
            try:
                title = item.find("title")
                link = item.find("link")
                description = item.find("description")
                pub_date = item.find("pubDate")

                # Ghost includes full content in content:encoded
                content_encoded = item.find("content:encoded", namespaces)

                # Get author from dc:creator
                creator = item.find("dc:creator", namespaces)

                # Get categories/tags
                categories = [cat.text for cat in item.findall("category") if cat.text]

                if title is not None and link is not None:
                    # Extract text content, stripping HTML from content:encoded
                    full_text = ""
                    if content_encoded is not None and content_encoded.text:
                        # Strip HTML tags for text analysis
                        full_text = re.sub(r'<[^>]+>', ' ', content_encoded.text)
                        full_text = re.sub(r'\s+', ' ', full_text).strip()

                    items.append({
                        "title": title.text or "",
                        "link": link.text or "",
                        "description": (description.text or "")[:500] if description is not None else "",
                        "full_text": full_text[:5000],  # Limit to 5000 chars
                        "pub_date": pub_date.text if pub_date is not None else "",
                        "author": creator.text if creator is not None else "",
                        "categories": categories,
                        "feed_id": feed_id,
                        "feed_name": feed_info.get("name", feed_id),
                        "tier": feed_info.get("tier", 2),
                        "signal_type": feed_info.get("signal_type", "policy_analysis"),
                    })
            except Exception as e:
                print(f"Error parsing item: {e}")
                continue

        return items

    def _matches_keywords(self, text: str) -> List[str]:
        """Check if text matches any tracked keywords."""
        text_lower = text.lower()
        matched = []
        for keyword in PROMETHEAN_KEYWORDS:
            if keyword in text_lower:
                matched.append(keyword)
        return matched

    def _matches_entities(self, text: str) -> List[Dict[str, str]]:
        """Check if text mentions any tracked entities."""
        text_lower = text.lower()
        matched = []

        for entity_name, node_id in PROMETHEAN_ENTITIES.items():
            if entity_name in text_lower:
                matched.append({
                    "name": entity_name,
                    "node_id": node_id,
                })

        return matched

    def _extract_policy_positions(self, text: str) -> List[str]:
        """Extract policy position indicators from text.

        Looks for stance indicators like "supports", "opposes", "calls for", etc.
        """
        positions = []
        text_lower = text.lower()

        # Positive stance patterns
        positive_patterns = [
            r"supports?\s+(?:the\s+)?(\w+(?:\s+\w+){0,3})",
            r"calls?\s+for\s+(?:the\s+)?(\w+(?:\s+\w+){0,3})",
            r"advocates?\s+(?:for\s+)?(?:the\s+)?(\w+(?:\s+\w+){0,3})",
            r"endorses?\s+(?:the\s+)?(\w+(?:\s+\w+){0,3})",
        ]

        # Negative stance patterns
        negative_patterns = [
            r"opposes?\s+(?:the\s+)?(\w+(?:\s+\w+){0,3})",
            r"criticizes?\s+(?:the\s+)?(\w+(?:\s+\w+){0,3})",
            r"rejects?\s+(?:the\s+)?(\w+(?:\s+\w+){0,3})",
            r"warns?\s+against\s+(?:the\s+)?(\w+(?:\s+\w+){0,3})",
        ]

        for pattern in positive_patterns:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                positions.append(f"SUPPORTS: {match}")

        for pattern in negative_patterns:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                positions.append(f"OPPOSES: {match}")

        return positions[:5]  # Limit to 5 positions

    def collect(self) -> List[Artifact]:
        """Fetch Promethean Action RSS feed and filter for relevant articles."""
        artifacts = []
        self._load_seen_urls()

        for feed_id, feed_info in PROMETHEAN_FEEDS.items():
            url = feed_info["url"]
            print(f"Fetching {feed_info['name']} from {url}...")

            content = self._fetch_url(url)
            if not content:
                print(f"  Failed to fetch feed")
                continue

            # Save raw feed
            content_hash = hashlib.sha256(content).hexdigest()
            feed_path = self.artifact_dir / f"feed_{feed_id}_{datetime.utcnow().strftime('%Y%m%d')}.xml"

            with open(feed_path, "wb") as f:
                f.write(content)

            # Parse feed
            items = self._parse_ghost_rss(content, feed_id)
            print(f"  Parsed {len(items)} items")

            for item in items:
                article_url = item["link"]

                # Skip already seen
                if article_url in self._seen_urls:
                    continue

                # Check for keyword or entity match
                combined_text = f"{item['title']} {item['description']} {item['full_text']}"
                keywords = self._matches_keywords(combined_text)
                entity_matches = self._matches_entities(combined_text)

                # Extract policy positions
                positions = self._extract_policy_positions(combined_text)

                # For Promethean Action, we're interested in ALL articles (they're all policy-focused)
                # But we'll score relevance by keyword/entity matches
                relevance_score = len(keywords) * 0.1 + len(entity_matches) * 0.2 + len(positions) * 0.1

                if relevance_score < 0.1 and not keywords and not entity_matches:
                    # Very low relevance, skip
                    continue

                self._seen_urls.add(article_url)

                # Create artifact
                article_data = {
                    "title": item["title"],
                    "url": article_url,
                    "description": item["description"],
                    "full_text": item["full_text"][:2000],  # Limit stored text
                    "pub_date": item["pub_date"],
                    "author": item["author"],
                    "categories": item["categories"],
                    "feed_id": item["feed_id"],
                    "feed_name": item["feed_name"],
                    "tier": item["tier"],
                    "signal_type": item["signal_type"],
                    "matched_keywords": keywords,
                    "matched_entities": [e["node_id"] for e in entity_matches],
                    "matched_entity_names": [e["name"] for e in entity_matches],
                    "policy_positions": positions,
                    "relevance_score": relevance_score,
                }

                article_hash = hashlib.sha256(json.dumps(article_data).encode()).hexdigest()
                article_path = self.artifact_dir / f"article_{article_hash[:16]}.json"

                with open(article_path, "w") as f:
                    json.dump(article_data, f, indent=2)

                artifact = Artifact(
                    url=article_url,
                    artifact_type="json",
                    local_path=str(article_path),
                    content_hash=article_hash,
                    metadata=article_data,
                )
                artifacts.append(artifact)
                print(f"  + {item['title'][:60]}... (relevance: {relevance_score:.2f})")

        self._save_seen_urls()
        print(f"Collected {len(artifacts)} articles")
        return artifacts

    def extract(self, artifacts: List[Artifact]) -> List[StructuredFact]:
        """Extract facts from collected articles."""
        facts = []

        for artifact in artifacts:
            metadata = artifact.metadata

            # Create fact for each matched entity
            for i, entity_id in enumerate(metadata.get("matched_entities", [])):
                entity_name = metadata["matched_entity_names"][i] if i < len(metadata.get("matched_entity_names", [])) else entity_id

                facts.append(StructuredFact(
                    fact_type="policy_analysis",
                    subject="Promethean Action",
                    predicate="ANALYZES",
                    object=entity_name,
                    source_artifact=artifact,
                    confidence=0.6 + min(0.3, metadata.get("relevance_score", 0)),
                    date_occurred=metadata.get("pub_date", ""),
                    raw_text=f"{metadata.get('title', '')} - {metadata.get('description', '')[:200]}",
                    metadata={
                        "entity_node_id": entity_id,
                        "article_title": metadata.get("title"),
                        "feed_name": metadata.get("feed_name"),
                        "feed_tier": metadata.get("tier"),
                        "matched_keywords": metadata.get("matched_keywords", []),
                        "policy_positions": metadata.get("policy_positions", []),
                        "author": metadata.get("author"),
                    }
                ))

            # Create fact for policy positions
            for position in metadata.get("policy_positions", []):
                facts.append(StructuredFact(
                    fact_type="policy_stance",
                    subject="Promethean Action",
                    predicate="TAKES_POSITION",
                    object=position,
                    source_artifact=artifact,
                    confidence=0.5,
                    date_occurred=metadata.get("pub_date", ""),
                    raw_text=f"{metadata.get('title', '')}",
                    metadata={
                        "article_title": metadata.get("title"),
                        "feed_name": metadata.get("feed_name"),
                    }
                ))

            # Create fact for keyword coverage (signal layer)
            if metadata.get("matched_keywords") and not metadata.get("matched_entities"):
                facts.append(StructuredFact(
                    fact_type="topic_signal",
                    subject="Promethean Action",
                    predicate="COVERS_TOPIC",
                    object=", ".join(metadata["matched_keywords"][:5]),
                    source_artifact=artifact,
                    confidence=0.5,
                    date_occurred=metadata.get("pub_date", ""),
                    raw_text=f"{metadata.get('title', '')}",
                    metadata={
                        "article_title": metadata.get("title"),
                        "feed_name": metadata.get("feed_name"),
                    }
                ))

        return facts

    def propose(self, facts: List[StructuredFact]) -> tuple[List[ProposedClaim], List[ProposedEdge]]:
        """Generate HYPOTHESIS claims and edges from facts."""
        claims = []
        edges = []

        for fact in facts:
            proposal_id = self._generate_proposal_id()

            if fact.fact_type == "policy_analysis":
                entity_id = fact.metadata.get("entity_node_id")
                entity_name = fact.object
                article_title = fact.metadata.get("article_title", "")

                claim_text = f"Promethean Action analyzes {entity_name}: {article_title[:100]}"

                claim = ProposedClaim(
                    proposal_id=proposal_id,
                    claim_text=claim_text,
                    topic="SIGNAL_LAYER",
                    agent_name=self.name,
                    source_url=fact.source_artifact.url,
                    artifact_path=fact.source_artifact.local_path,
                    artifact_hash=fact.source_artifact.content_hash,
                    reasoning=f"Matched keywords: {', '.join(fact.metadata.get('matched_keywords', []))}",
                    promotion_requirement="Verify article substantively covers entity (not just mentions)",
                )
                claims.append(claim)

                # Create ANALYZES edge
                edge_proposal_id = self._generate_proposal_id()

                edge = ProposedEdge(
                    proposal_id=edge_proposal_id,
                    from_node="media_promethean_action",
                    to_node=entity_id,
                    relationship="ANALYZES",
                    agent_name=self.name,
                    detail=article_title[:200],
                    proposed_claim_id=proposal_id,
                    confidence=fact.confidence,
                    reasoning=f"Tier 2 policy analysis; keywords: {', '.join(fact.metadata.get('matched_keywords', [])[:5])}",
                    promotion_requirement="Confirm substantive policy analysis (not just news coverage)",
                )
                edges.append(edge)

            elif fact.fact_type == "policy_stance":
                # Create claim for policy stance
                claim_text = f"Promethean Action position: {fact.object}"

                claim = ProposedClaim(
                    proposal_id=proposal_id,
                    claim_text=claim_text,
                    topic="SIGNAL_LAYER",
                    agent_name=self.name,
                    source_url=fact.source_artifact.url,
                    artifact_path=fact.source_artifact.local_path,
                    artifact_hash=fact.source_artifact.content_hash,
                    reasoning="Policy stance extracted from article text",
                    promotion_requirement="Verify stance accurately represents article content",
                )
                claims.append(claim)

            elif fact.fact_type == "topic_signal":
                # Create claim for topic coverage
                claim_text = f"Promethean Action covers topics: {fact.object}"

                claim = ProposedClaim(
                    proposal_id=proposal_id,
                    claim_text=claim_text,
                    topic="SIGNAL_LAYER",
                    agent_name=self.name,
                    source_url=fact.source_artifact.url,
                    artifact_path=fact.source_artifact.local_path,
                    artifact_hash=fact.source_artifact.content_hash,
                    reasoning="Topic keywords detected in article",
                    promotion_requirement="Link to specific entity for edge creation",
                )
                claims.append(claim)

        return claims, edges


# CLI entry point
if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    from fgip.db import FGIPDatabase

    if len(sys.argv) < 2:
        print("Usage: python promethean.py <database_path>")
        print("Example: python promethean.py fgip.db")
        sys.exit(1)

    db_path = sys.argv[1]
    db = FGIPDatabase(db_path)

    agent = PrometheanAgent(db)

    print(f"\n{'='*60}")
    print(f"Promethean Action Newsletter Agent")
    print(f"{'='*60}")

    results = agent.run()

    print(f"\n{'='*60}")
    print(f"Results:")
    print(f"  Artifacts collected: {results['artifacts_collected']}")
    print(f"  Facts extracted: {results['facts_extracted']}")
    print(f"  Claims proposed: {results['claims_proposed']}")
    print(f"  Edges proposed: {results['edges_proposed']}")

    if results['errors']:
        print(f"\nErrors:")
        for error in results['errors']:
            print(f"  - {error}")

    # Show status
    status = agent.get_status()
    print(f"\nAgent Status:")
    print(f"  Pending claims: {status['pending_claims']}")
    print(f"  Pending edges: {status['pending_edges']}")
    print(f"  Approved claims: {status['approved_claims']}")
    print(f"  Approved edges: {status['approved_edges']}")
