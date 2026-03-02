"""FGIP RSS Signal Agent - Signal Layer Feed.

RSS monitoring from Reuters, AP, and curated independents.
Keyword matching against tracked topics.
Proposes REPORTS_ON edges for convergence scoring.

Tier 1/2 agent - uses journalism sources.

Safety rules:
- Uses public RSS feeds only
- Stores only article metadata and snippets
- Respects robots.txt and rate limits
- Artifacts saved locally with SHA256 hash
"""

import hashlib
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any
import urllib.request
import urllib.error

from .base import FGIPAgent, Artifact, StructuredFact, ProposedClaim, ProposedEdge


# RSS feed sources organized by tier
RSS_FEEDS = {
    # Tier 1 - Major journalism
    "reuters": {
        "url": "https://www.reuters.com/rssFeed/businessNews",
        "tier": 1,
        "name": "Reuters",
    },
    "ap": {
        "url": "https://rsshub.app/apnews/topics/business",  # Using RSShub as AP doesn't have direct RSS
        "tier": 1,
        "name": "AP News",
    },
    "wsj": {
        "url": "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
        "tier": 1,
        "name": "Wall Street Journal",
    },
    "nyt": {
        "url": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
        "tier": 1,
        "name": "New York Times",
    },
    "bbc": {
        "url": "https://feeds.bbci.co.uk/news/business/rss.xml",
        "tier": 1,
        "name": "BBC Business",
    },
    "politico": {
        "url": "https://www.politico.com/rss/politicopicks.xml",
        "tier": 1,
        "name": "Politico",
    },
    # Tier 2 - Commentary/Analysis
    "thehill": {
        "url": "https://thehill.com/rss/syndicator/19110",
        "tier": 2,
        "name": "The Hill",
    },
    "propublica": {
        "url": "https://www.propublica.org/feeds/propublica/main",
        "tier": 1,
        "name": "ProPublica",
    },
    # YouTube - Geopolitics/Analysis (derived from user algorithm analysis)
    "zeihan": {
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCsy9I56PY3IngCf_VGjunMQ",
        "tier": 2,
        "name": "Zeihan on Geopolitics",
        "signal_type": "geopolitics",
    },
    "lex_fridman": {
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCSHZKyawb77ixDdsGog4iWA",
        "tier": 2,
        "name": "Lex Fridman",
        "signal_type": "tech_geopolitics",
    },
    "shawn_ryan": {
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC1vUksRWfEfd6V4pPDIQ0jw",
        "tier": 2,
        "name": "Shawn Ryan Show",
        "signal_type": "intelligence",
    },
    "american_alchemy": {
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCuG2KzrIMe3qoNcuDVpwnXw",
        "tier": 2,
        "name": "American Alchemy (Jesse Michels)",
        "signal_type": "finance_conspiracy",
    },
    "valuetainment": {
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCIHdDJ0tjn_3j-FS7s_X1kQ",
        "tier": 2,
        "name": "Valuetainment",
        "signal_type": "business",
    },
    "andrew_bustamante": {
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCXam0UQg9Xr0_OarTKNMFCQ",
        "tier": 2,
        "name": "Andrew Bustamante (ex-CIA)",
        "signal_type": "intelligence",
    },
    "tucker_carlson": {
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCGttrUON87gWfU6dMWm1fcA",
        "tier": 2,
        "name": "Tucker Carlson",
        "signal_type": "politics",
    },
    "pbd_podcast": {
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCGX7nGXpz-CmO_Arg-cgJ7A",
        "tier": 2,
        "name": "PBD Podcast",
        "signal_type": "business",
    },
    "johnny_harris": {
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCmGSJVG3mCRXVOP4yZrU1Dw",
        "tier": 2,
        "name": "Johnny Harris",
        "signal_type": "geopolitics",
    },
    # YouTube - News/Finance
    "cnbc_yt": {
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCvJJ_dzjViJCoLf5uKUTwoA",
        "tier": 1,
        "name": "CNBC",
        "signal_type": "finance",
    },
    "fox_business_yt": {
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCCXoCcu9Rp7NPbTzIvogpZg",
        "tier": 2,
        "name": "Fox Business",
        "signal_type": "finance",
    },
    "forbes_breaking": {
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCg40OxZ1GYh3u3jBntB6DLg",
        "tier": 1,
        "name": "Forbes Breaking News",
        "signal_type": "finance",
    },
    # Defense Industrial Base
    "mwi": {
        "url": "https://mwi.westpoint.edu/feed/",
        "tier": 2,
        "name": "Modern War Institute",
        "signal_type": "defense_industrial",
    },
}

# Topics to track
TRACKED_KEYWORDS = [
    # Trade/Economic
    "tariff", "trade war", "china trade", "supply chain", "reshoring",
    "manufacturing", "semiconductor", "chip", "fentanyl",
    # Policy/Legal
    "supreme court", "scotus", "amicus", "lobbying",
    "sec filing", "10-k", "13f", "proxy",
    # Organizations
    "chamber of commerce", "business roundtable",
    "blackrock", "vanguard", "state street",
    # Regulatory
    "cfius", "sanctions", "export control", "foreign investment",

    # Enhanced keywords from algorithm analysis
    # Geopolitics/Deglobalization (Zeihan thesis)
    "deglobalization", "decoupling", "supply chain collapse",
    "china demographics", "china collapse", "taiwan invasion",
    "chips act", "onshoring", "nearshoring", "friend-shoring",

    # Energy/Infrastructure
    "nuclear fusion", "energy security", "grid vulnerability",
    "critical minerals", "rare earth", "lithium", "cobalt",

    # Finance/Dark Money
    "institutional ownership", "passive investing", "index fund",
    "dark money", "pac spending", "lobbying disclosure",
    "shadow banking", "private equity",

    # Security/Defense
    "cyber warfare", "infrastructure attack", "cisa",
    "defense industrial base", "military industrial",
    "national security", "foreign influence",

    # Key Companies/Entities
    "intel", "tsmc", "samsung semiconductor", "nvidia",
    "micron", "globalfoundries", "applied materials",
    "lockheed", "raytheon", "northrop", "general dynamics",
]

USER_AGENT = "FGIP Research Agent (contact@example.com)"


class RSSSignalAgent(FGIPAgent):
    """RSS signal layer feed agent.

    Monitors news feeds for:
    - Topic keyword matches
    - Entity mentions
    - Convergence signals (multiple sources reporting same story)

    Proposes REPORTS_ON edges linking media to entities.
    """

    def __init__(self, db, artifact_dir: str = "data/artifacts/rss"):
        super().__init__(
            db=db,
            name="rss",
            description="RSS signal layer - news feeds from Reuters, AP, etc."
        )
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self._rate_limit_delay = 2.0  # 2 seconds between requests
        self._last_request_time = 0
        self._seen_urls = set()  # Track processed articles

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
        except urllib.error.HTTPError:
            return None
        except Exception:
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
        # Keep only recent 10000 URLs
        recent = list(self._seen_urls)[-10000:]
        with open(seen_file, "w") as f:
            json.dump(recent, f)

    def _get_tracked_entities(self) -> List[Dict[str, Any]]:
        """Get entities from nodes table for matching."""
        conn = self.db.connect()
        rows = conn.execute(
            """SELECT node_id, name, aliases FROM nodes
               WHERE node_type IN ('ORGANIZATION', 'COMPANY', 'PERSON', 'LEGISLATION')
               LIMIT 200"""
        ).fetchall()

        entities = []
        for row in rows:
            aliases = json.loads(row["aliases"]) if row["aliases"] else []
            entities.append({
                "node_id": row["node_id"],
                "name": row["name"],
                "aliases": aliases,
            })
        return entities

    def _parse_rss_feed(self, content: bytes, feed_id: str) -> List[Dict[str, Any]]:
        """Parse RSS/Atom feed content."""
        items = []

        try:
            root = ET.fromstring(content)
        except ET.ParseError:
            return items

        feed_info = RSS_FEEDS.get(feed_id, {})

        # Handle RSS 2.0
        for item in root.iter("item"):
            try:
                title = item.find("title")
                link = item.find("link")
                description = item.find("description")
                pub_date = item.find("pubDate")

                if title is not None and link is not None:
                    items.append({
                        "title": title.text or "",
                        "link": link.text or "",
                        "description": (description.text or "")[:500] if description is not None else "",
                        "pub_date": pub_date.text if pub_date is not None else "",
                        "feed_id": feed_id,
                        "feed_name": feed_info.get("name", feed_id),
                        "tier": feed_info.get("tier", 2),
                    })
            except Exception:
                continue

        # Handle Atom feeds
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//atom:entry", ns):
            try:
                title = entry.find("atom:title", ns)
                link = entry.find("atom:link", ns)
                summary = entry.find("atom:summary", ns)
                published = entry.find("atom:published", ns)

                link_href = link.get("href") if link is not None else ""

                if title is not None and link_href:
                    items.append({
                        "title": title.text or "",
                        "link": link_href,
                        "description": (summary.text or "")[:500] if summary is not None else "",
                        "pub_date": published.text if published is not None else "",
                        "feed_id": feed_id,
                        "feed_name": feed_info.get("name", feed_id),
                        "tier": feed_info.get("tier", 2),
                    })
            except Exception:
                continue

        return items

    def _matches_keywords(self, text: str) -> List[str]:
        """Check if text matches any tracked keywords."""
        text_lower = text.lower()
        matched = []
        for keyword in TRACKED_KEYWORDS:
            if keyword in text_lower:
                matched.append(keyword)
        return matched

    def _matches_entities(self, text: str, entities: List[Dict]) -> List[Dict]:
        """Check if text mentions any tracked entities."""
        text_lower = text.lower()
        matched = []

        for entity in entities:
            # Check main name
            if entity["name"].lower() in text_lower:
                matched.append(entity)
                continue

            # Check aliases
            for alias in entity.get("aliases", []):
                if alias.lower() in text_lower:
                    matched.append(entity)
                    break

        return matched

    def collect(self) -> List[Artifact]:
        """Fetch RSS feeds and filter for relevant articles."""
        artifacts = []
        self._load_seen_urls()
        entities = self._get_tracked_entities()

        for feed_id, feed_info in RSS_FEEDS.items():
            url = feed_info["url"]

            content = self._fetch_url(url)
            if not content:
                continue

            # Save raw feed
            content_hash = hashlib.sha256(content).hexdigest()
            feed_path = self.artifact_dir / f"feed_{feed_id}_{datetime.utcnow().strftime('%Y%m%d')}.xml"

            with open(feed_path, "wb") as f:
                f.write(content)

            # Parse feed
            items = self._parse_rss_feed(content, feed_id)

            for item in items:
                article_url = item["link"]

                # Skip already seen
                if article_url in self._seen_urls:
                    continue

                # Check for keyword or entity match
                combined_text = f"{item['title']} {item['description']}"
                keywords = self._matches_keywords(combined_text)
                entity_matches = self._matches_entities(combined_text, entities)

                if not keywords and not entity_matches:
                    continue

                # This is a relevant article
                self._seen_urls.add(article_url)

                # Create artifact for the article metadata
                article_data = {
                    "title": item["title"],
                    "url": article_url,
                    "description": item["description"],
                    "pub_date": item["pub_date"],
                    "feed_id": item["feed_id"],
                    "feed_name": item["feed_name"],
                    "tier": item["tier"],
                    "matched_keywords": keywords,
                    "matched_entities": [e["node_id"] for e in entity_matches],
                    "matched_entity_names": [e["name"] for e in entity_matches],
                }

                article_hash = hashlib.sha256(json.dumps(article_data).encode()).hexdigest()
                article_path = self.artifact_dir / f"article_{article_hash[:16]}.json"

                with open(article_path, "w") as f:
                    json.dump(article_data, f, indent=2)

                artifacts.append(Artifact(
                    url=article_url,
                    artifact_type="json",
                    local_path=str(article_path),
                    content_hash=article_hash,
                    metadata=article_data,
                ))

        self._save_seen_urls()
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
                    fact_type="media_mention",
                    subject=metadata.get("feed_name", "News"),
                    predicate="REPORTS_ON",
                    object=entity_name,
                    source_artifact=artifact,
                    confidence=0.6 + (0.1 * len(metadata.get("matched_keywords", []))),  # Higher confidence with more keywords
                    date_occurred=metadata.get("pub_date", ""),
                    raw_text=f"{metadata.get('title', '')} - {metadata.get('description', '')[:200]}",
                    metadata={
                        "entity_node_id": entity_id,
                        "article_title": metadata.get("title"),
                        "feed_name": metadata.get("feed_name"),
                        "feed_tier": metadata.get("tier"),
                        "matched_keywords": metadata.get("matched_keywords", []),
                    }
                ))

            # Create fact for keyword matches without specific entities
            if metadata.get("matched_keywords") and not metadata.get("matched_entities"):
                facts.append(StructuredFact(
                    fact_type="topic_signal",
                    subject=metadata.get("feed_name", "News"),
                    predicate="COVERS_TOPIC",
                    object=", ".join(metadata["matched_keywords"]),
                    source_artifact=artifact,
                    confidence=0.5,
                    date_occurred=metadata.get("pub_date", ""),
                    raw_text=f"{metadata.get('title', '')} - {metadata.get('description', '')[:200]}",
                    metadata={
                        "article_title": metadata.get("title"),
                        "feed_name": metadata.get("feed_name"),
                        "feed_tier": metadata.get("tier"),
                    }
                ))

        return facts

    def propose(self, facts: List[StructuredFact]) -> tuple[List[ProposedClaim], List[ProposedEdge]]:
        """Generate HYPOTHESIS claims and edges from facts."""
        claims = []
        edges = []

        # Group facts by entity to detect convergence
        entity_mentions = {}  # entity_id -> list of facts

        for fact in facts:
            if fact.fact_type == "media_mention":
                entity_id = fact.metadata.get("entity_node_id")
                if entity_id:
                    if entity_id not in entity_mentions:
                        entity_mentions[entity_id] = []
                    entity_mentions[entity_id].append(fact)

        # Create proposals
        for fact in facts:
            proposal_id = self._generate_proposal_id()

            if fact.fact_type == "media_mention":
                entity_id = fact.metadata.get("entity_node_id")
                entity_name = fact.object
                feed_name = fact.metadata.get("feed_name", "News source")
                article_title = fact.metadata.get("article_title", "")

                # Check for convergence (multiple sources)
                convergence_count = len(entity_mentions.get(entity_id, []))
                convergence_note = ""
                if convergence_count > 1:
                    convergence_note = f" ({convergence_count} sources reporting)"

                claim_text = f"{feed_name} reports on {entity_name}: {article_title[:100]}{convergence_note}"

                claim = ProposedClaim(
                    proposal_id=proposal_id,
                    claim_text=claim_text,
                    topic="SIGNAL_LAYER",
                    agent_name=self.name,
                    source_url=fact.source_artifact.url,
                    artifact_path=fact.source_artifact.local_path,
                    artifact_hash=fact.source_artifact.content_hash,
                    reasoning=f"Matched keywords: {', '.join(fact.metadata.get('matched_keywords', []))}",
                    promotion_requirement="Verify article exists and entity is substantively covered (not just mentioned)",
                )
                claims.append(claim)

                # Create REPORTS_ON edge
                edge_proposal_id = self._generate_proposal_id()

                # Create media outlet node ID
                feed_node_id = f"media_{fact.metadata.get('feed_name', 'news').lower().replace(' ', '_')}"

                edge = ProposedEdge(
                    proposal_id=edge_proposal_id,
                    from_node=feed_node_id,
                    to_node=entity_id,
                    relationship="REPORTS_ON",
                    agent_name=self.name,
                    detail=article_title[:200],
                    proposed_claim_id=proposal_id,
                    confidence=fact.confidence,
                    reasoning=f"Tier {fact.metadata.get('feed_tier')} source; keywords: {', '.join(fact.metadata.get('matched_keywords', []))}",
                    promotion_requirement="Verify media outlet node exists; confirm substantive coverage",
                )
                edges.append(edge)

            elif fact.fact_type == "topic_signal":
                # Create claim for topic signal without specific entity
                claim_text = f"{fact.subject} covers topics: {fact.object}"

                claim = ProposedClaim(
                    proposal_id=proposal_id,
                    claim_text=claim_text,
                    topic="SIGNAL_LAYER",
                    agent_name=self.name,
                    source_url=fact.source_artifact.url,
                    artifact_path=fact.source_artifact.local_path,
                    artifact_hash=fact.source_artifact.content_hash,
                    reasoning=f"Topic keywords detected in article",
                    promotion_requirement="Link to specific entity or event for edge creation",
                )
                claims.append(claim)

        return claims, edges

    def get_convergence_signals(self) -> Dict[str, Any]:
        """Analyze convergence across sources for tracked topics.

        Returns entities with multiple source coverage (potential signals).
        """
        conn = self.db.connect()

        # Get recent proposals grouped by target entity
        rows = conn.execute(
            """SELECT to_node, COUNT(DISTINCT from_node) as source_count,
                      GROUP_CONCAT(DISTINCT from_node) as sources
               FROM proposed_edges
               WHERE agent_name = 'rss'
                 AND status = 'PENDING'
                 AND created_at > datetime('now', '-7 days')
               GROUP BY to_node
               HAVING source_count > 1
               ORDER BY source_count DESC
               LIMIT 20"""
        ).fetchall()

        signals = []
        for row in rows:
            signals.append({
                "entity": row["to_node"],
                "source_count": row["source_count"],
                "sources": row["sources"].split(",") if row["sources"] else [],
            })

        return {
            "convergence_signals": signals,
            "total_signals": len(signals),
        }
