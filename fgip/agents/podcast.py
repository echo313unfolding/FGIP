"""FGIP Podcast Intelligence Agent.

Monitors podcast RSS feeds for episodes discussing thesis-relevant topics.
Extracts claims, guest appearances, and reference chains from episode metadata.

Sources:
- Lex Fridman, Joe Rogan, All-In, PBD Podcast, Sean Ryan Show
- Finance/economics: Macro Voices, Real Vision, Peter Schiff
- Investigative: Glenn Greenwald, Matt Taibbi, Breaking Points

Tier 1/2 agent - podcasts are commentary, but reference chains lead to Tier 0.
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


USER_AGENT = "FGIP Podcast Intelligence (research@fgip.org)"


@dataclass
class PodcastEpisode:
    """A parsed podcast episode."""
    show_name: str
    episode_title: str
    description: str
    pub_date: str
    url: str
    duration: Optional[str]
    guest_names: List[str]


# Core podcast RSS feeds - Tier 0 watchlist
PODCAST_FEEDS = {
    # Interview / Investigation
    "lex_fridman": {
        "name": "Lex Fridman Podcast",
        "feed_url": "https://lexfridman.com/feed/podcast/",
        "platform": "youtube",
        "tier": 1,
    },
    "sean_ryan": {
        "name": "Sean Ryan Show",
        "feed_url": "https://feeds.simplecast.com/4T39_jAj",  # Example
        "platform": "youtube",
        "tier": 1,
    },
    "joe_rogan": {
        "name": "Joe Rogan Experience",
        "feed_url": "https://feeds.megaphone.fm/WWO3519750118",  # Spotify feed
        "platform": "spotify",
        "tier": 2,
    },
    "pbd_podcast": {
        "name": "PBD Podcast",
        "feed_url": "https://feeds.megaphone.fm/ROOSTER8556472664",
        "platform": "youtube",
        "tier": 1,
    },
    "all_in": {
        "name": "All-In Podcast",
        "feed_url": "https://feeds.megaphone.fm/all-in-with-chamath-jason-sacks-friedberg",
        "platform": "youtube",
        "tier": 1,
    },
    "breaking_points": {
        "name": "Breaking Points",
        "feed_url": "https://feeds.megaphone.fm/breakingpoints",
        "platform": "youtube",
        "tier": 1,
    },
    # Finance / Economics
    "macro_voices": {
        "name": "Macro Voices",
        "feed_url": "https://feeds.libsyn.com/100913/rss",
        "platform": "various",
        "tier": 1,
    },
    "real_vision": {
        "name": "Real Vision",
        "feed_url": "https://feeds.simplecast.com/l50iXJJb",
        "platform": "youtube",
        "tier": 1,
    },
    "odd_lots": {
        "name": "Odd Lots (Bloomberg)",
        "feed_url": "https://feeds.bloomberg.com/BLM8400515853",
        "platform": "bloomberg",
        "tier": 1,
    },
}

# Keywords that match thesis topics
THESIS_KEYWORDS = {
    "Lobbying": [
        "lobbyist", "lobbying", "chamber of commerce", "think tank", "revolving door",
        "PAC", "super PAC", "political donation", "K Street", "foreign agent", "FARA"
    ],
    "Ownership": [
        "BlackRock", "Vanguard", "State Street", "institutional ownership",
        "cross-ownership", "13F", "beneficial owner", "proxy voting", "ESG"
    ],
    "Reshoring": [
        "reshoring", "onshoring", "manufacturing", "supply chain", "CHIPS Act",
        "domestic production", "made in America", "tariff", "trade war", "PNTR"
    ],
    "Downstream": [
        "fentanyl", "opioid", "drug shortage", "pharmaceutical", "API",
        "defense industrial base", "shipbuilding", "rare earth", "critical minerals"
    ],
    "Judicial": [
        "Supreme Court", "SCOTUS", "amicus", "judicial ethics", "Federalist Society",
        "Heritage Foundation", "judicial nomination", "recusal"
    ],
    "Censorship": [
        "censorship", "content moderation", "fact check", "Twitter Files",
        "misinformation", "disinformation", "Section 230", "social media"
    ],
    "Stablecoin": [
        "stablecoin", "CBDC", "cryptocurrency", "Bitcoin", "digital dollar",
        "GENIUS Act", "crypto regulation", "Tether", "Circle"
    ],
    "ThinkTank": [
        "Cato", "Heritage", "Brookings", "CFR", "AEI", "foundation",
        "Koch", "donor", "nonprofit", "501(c)"
    ],
}


class PodcastAgent(FGIPAgent):
    """Podcast Intelligence Agent.

    Monitors podcast RSS feeds and extracts:
    - Episode metadata matching thesis topics
    - Guest names and affiliations
    - Claims and references mentioned in descriptions
    - Reference chains to follow
    """

    def __init__(self, db, artifact_dir: str = "data/artifacts/podcast"):
        super().__init__(
            db=db,
            name="podcast",
            description="Podcast Intelligence - Long-form interviews and reference chains"
        )
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self._rate_limit_delay = 1.0  # 1 second between requests
        self._last_request_time = 0
        self._graph_entities = None

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

    def _get_graph_entities(self) -> Dict[str, str]:
        """Get all entity names from nodes table."""
        if self._graph_entities is None:
            conn = self.db.connect()
            rows = conn.execute(
                "SELECT node_id, name FROM nodes"
            ).fetchall()
            self._graph_entities = {
                row["name"].lower(): row["node_id"] for row in rows
            }
        return self._graph_entities

    def collect(self) -> List[Artifact]:
        """Collect recent podcast episodes from RSS feeds."""
        artifacts = []

        for feed_id, feed_info in PODCAST_FEEDS.items():
            feed_url = feed_info.get("feed_url", "")
            if not feed_url:
                continue

            content = self._fetch_url(feed_url)
            if not content:
                continue

            content_hash = hashlib.sha256(content).hexdigest()
            local_path = self.artifact_dir / f"feed_{feed_id}.xml"

            with open(local_path, "wb") as f:
                f.write(content)

            artifact = Artifact(
                url=feed_url,
                artifact_type="rss",
                local_path=str(local_path),
                content_hash=content_hash,
                metadata={
                    "feed_id": feed_id,
                    "show_name": feed_info["name"],
                    "tier": feed_info.get("tier", 2),
                }
            )
            artifacts.append(artifact)

        return artifacts

    def extract(self, artifacts: List[Artifact]) -> List[StructuredFact]:
        """Parse RSS feeds and extract thesis-relevant episodes."""
        facts = []

        for artifact in artifacts:
            if artifact.artifact_type != "rss":
                continue

            episodes = self._parse_rss_feed(artifact)

            for episode in episodes:
                # Check if episode matches thesis topics
                matches = self._match_thesis_topics(episode)

                if matches:
                    # Create fact for each topic match
                    for topic, keywords in matches:
                        facts.append(StructuredFact(
                            fact_type="podcast_episode",
                            subject=episode.show_name,
                            predicate="DISCUSSED",
                            object=topic,
                            source_artifact=artifact,
                            confidence=0.6,
                            date_occurred=episode.pub_date,
                            raw_text=episode.episode_title,
                            metadata={
                                "episode_title": episode.episode_title,
                                "episode_url": episode.url,
                                "guest_names": episode.guest_names,
                                "matched_keywords": keywords,
                                "description": episode.description[:500],
                            }
                        ))

                # Check for guest matches against graph entities
                entity_matches = self._match_graph_entities(episode)
                for entity_name, node_id in entity_matches:
                    facts.append(StructuredFact(
                        fact_type="podcast_guest",
                        subject=entity_name,
                        predicate="APPEARED_ON",
                        object=episode.show_name,
                        source_artifact=artifact,
                        confidence=0.7,
                        date_occurred=episode.pub_date,
                        raw_text=episode.episode_title,
                        metadata={
                            "episode_title": episode.episode_title,
                            "episode_url": episode.url,
                            "graph_node_id": node_id,
                        }
                    ))

                # Extract reference chains (people/studies mentioned)
                references = self._extract_references(episode)
                for ref in references:
                    facts.append(StructuredFact(
                        fact_type="podcast_reference",
                        subject=episode.show_name,
                        predicate="REFERENCED",
                        object=ref["name"],
                        source_artifact=artifact,
                        confidence=0.5,
                        date_occurred=episode.pub_date,
                        raw_text=ref.get("context", ""),
                        metadata={
                            "reference_type": ref["type"],
                            "episode_title": episode.episode_title,
                            "episode_url": episode.url,
                        }
                    ))

        return facts

    def _parse_rss_feed(self, artifact: Artifact) -> List[PodcastEpisode]:
        """Parse RSS feed and extract episodes."""
        episodes = []

        try:
            tree = ET.parse(artifact.local_path)
            root = tree.getroot()
        except Exception:
            return episodes

        show_name = artifact.metadata.get("show_name", "Unknown")

        # Find channel/items
        channel = root.find("channel")
        if channel is None:
            return episodes

        items = channel.findall("item")

        # Only process recent episodes (last 30 days)
        cutoff = (datetime.utcnow() - timedelta(days=30)).isoformat()

        for item in items[:10]:  # Limit to 10 most recent
            title_el = item.find("title")
            desc_el = item.find("description")
            link_el = item.find("link")
            pub_date_el = item.find("pubDate")
            duration_el = item.find("{http://www.itunes.com/dtds/podcast-1.0.dtd}duration")

            title = title_el.text if title_el is not None else ""
            description = desc_el.text if desc_el is not None else ""
            link = link_el.text if link_el is not None else ""
            pub_date = pub_date_el.text if pub_date_el is not None else ""
            duration = duration_el.text if duration_el is not None else None

            # Extract guest names from title (common pattern: "Guest Name - Topic")
            guest_names = self._extract_guest_names(title, description)

            episodes.append(PodcastEpisode(
                show_name=show_name,
                episode_title=title,
                description=description or "",
                pub_date=pub_date,
                url=link,
                duration=duration,
                guest_names=guest_names,
            ))

        return episodes

    def _extract_guest_names(self, title: str, description: str) -> List[str]:
        """Extract guest names from episode title/description."""
        guests = []

        # Common patterns: "#123 - Guest Name:", "with Guest Name", "featuring Guest"
        patterns = [
            r"#\d+\s*[-–:]\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",  # #123 - John Smith
            r"(?:with|featuring|guest)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
            r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s*[-–:]",  # John Smith: Topic
        ]

        text = f"{title} {description}"

        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                # Validate: looks like a name (2-4 words, each capitalized)
                words = match.split()
                if 2 <= len(words) <= 4:
                    guests.append(match.strip())

        return list(set(guests))[:3]  # Limit to 3 unique guests

    def _match_thesis_topics(self, episode: PodcastEpisode) -> List[Tuple[str, List[str]]]:
        """Match episode content against thesis topic keywords."""
        matches = []
        text = f"{episode.episode_title} {episode.description}".lower()

        for topic, keywords in THESIS_KEYWORDS.items():
            matched_keywords = [kw for kw in keywords if kw.lower() in text]
            if matched_keywords:
                matches.append((topic, matched_keywords))

        return matches

    def _match_graph_entities(self, episode: PodcastEpisode) -> List[Tuple[str, str]]:
        """Match episode against existing graph entities."""
        matches = []
        entities = self._get_graph_entities()
        text = f"{episode.episode_title} {episode.description}".lower()

        for entity_name, node_id in entities.items():
            if entity_name in text and len(entity_name) > 3:
                matches.append((entity_name, node_id))

        return matches[:5]  # Limit matches

    def _extract_references(self, episode: PodcastEpisode) -> List[Dict[str, str]]:
        """Extract references to people, studies, datasets from description."""
        references = []
        text = episode.description

        # Look for academic/research references
        study_patterns = [
            r"(?:study|research|paper|report)\s+(?:by|from)\s+([A-Z][A-Za-z\s]+?)(?:,|\.|\s+shows|\s+found)",
            r"(?:according to)\s+([A-Z][A-Za-z\s]+?)(?:,|\.)",
        ]

        for pattern in study_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                match = match.strip()
                if 3 < len(match) < 60:
                    references.append({
                        "type": "study",
                        "name": match,
                        "context": text[:200],
                    })

        # Look for dataset/source references
        data_patterns = [
            r"(?:data from|according to the)\s+([A-Z][A-Za-z\s]+?)(?:\s+shows|\s+data|,|\.)",
        ]

        for pattern in data_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                match = match.strip()
                if 3 < len(match) < 50:
                    references.append({
                        "type": "dataset",
                        "name": match,
                        "context": text[:200],
                    })

        return references[:5]

    def propose(self, facts: List[StructuredFact]) -> tuple[List[ProposedClaim], List[ProposedEdge], List[ProposedNode]]:
        """Generate proposals from podcast facts."""
        claims = []
        edges = []
        nodes = []

        for fact in facts:
            proposal_id = self._generate_proposal_id()

            # Generate claim text
            if fact.fact_type == "podcast_episode":
                matched = fact.metadata.get("matched_keywords", [])
                claim_text = f"{fact.subject} episode discussed {fact.object} (keywords: {', '.join(matched[:3])})"
            elif fact.fact_type == "podcast_guest":
                claim_text = f"{fact.subject} appeared on {fact.object} - '{fact.raw_text}'"
            elif fact.fact_type == "podcast_reference":
                ref_type = fact.metadata.get("reference_type", "source")
                claim_text = f"{fact.subject} referenced {fact.object} ({ref_type})"
            else:
                claim_text = f"{fact.subject} {fact.predicate} {fact.object}"

            claim = ProposedClaim(
                proposal_id=proposal_id,
                claim_text=claim_text,
                topic=fact.object if fact.fact_type == "podcast_episode" else "SIGNAL_LAYER",
                agent_name=self.name,
                source_url=fact.metadata.get("episode_url", fact.source_artifact.url),
                artifact_path=fact.source_artifact.local_path,
                artifact_hash=fact.source_artifact.content_hash,
                reasoning=f"Extracted from podcast episode: {fact.metadata.get('episode_title', '')}",
                promotion_requirement="Verify claim against episode transcript; follow reference chain to Tier 0 if applicable",
            )
            claims.append(claim)

            # Create edge for guest appearances
            if fact.fact_type == "podcast_guest" and fact.metadata.get("graph_node_id"):
                edge_id = self._generate_proposal_id()

                edge = ProposedEdge(
                    proposal_id=edge_id,
                    from_node=fact.metadata["graph_node_id"],
                    to_node=self._slugify(fact.object),
                    relationship="APPEARED_ON",
                    agent_name=self.name,
                    detail=claim_text,
                    proposed_claim_id=proposal_id,
                    confidence=fact.confidence,
                    reasoning="Podcast guest appearance detected",
                )
                edges.append(edge)

        return claims, edges, nodes

    def _slugify(self, name: str) -> str:
        """Convert name to node_id slug."""
        slug = name.lower()
        slug = re.sub(r'[^a-z0-9]+', '-', slug)
        return slug.strip('-')[:50]
