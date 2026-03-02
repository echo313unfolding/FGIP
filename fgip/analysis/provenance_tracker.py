"""
FGIP Provenance Tracker
=======================
Maps knowledge graph edges back to their originating signals:
- YouTube watch history (videos that led to entity discovery)
- RSS article consumption (news that triggered edge creation)
- Search history (research patterns)

This is a READ-ONLY analysis module, not an agent.
It answers: "Where did this knowledge come from?"
"""

import re
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


# ─── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class YouTubeWatch:
    """A single YouTube video watch event."""
    video_id: str
    title: str
    channel: Optional[str]
    watched_at: datetime
    url: str

    def matches_entity(self, entity_name: str) -> bool:
        """Check if video title/channel mentions the entity."""
        name_lower = entity_name.lower()
        title_lower = self.title.lower()
        channel_lower = (self.channel or "").lower()
        # Direct match
        if name_lower in title_lower or name_lower in channel_lower:
            return True
        # Word-boundary match for multi-word entities
        words = name_lower.split()
        if len(words) > 1 and all(w in title_lower for w in words):
            return True
        return False


@dataclass
class RSSArticle:
    """A single RSS article from the artifacts."""
    article_id: str
    title: str
    url: str
    pub_date: datetime
    feed_id: str
    feed_name: str
    tier: int
    matched_entities: List[str]
    matched_keywords: List[str]

    def matches_entity(self, entity_name: str) -> bool:
        """Check if article mentions the entity."""
        name_lower = entity_name.lower()
        # Check matched entities
        for ent in self.matched_entities:
            if name_lower in ent.lower() or ent.lower() in name_lower:
                return True
        # Check title
        if name_lower in self.title.lower():
            return True
        return False


@dataclass
class SearchQuery:
    """A YouTube search query."""
    query: str
    searched_at: datetime


@dataclass
class EdgeProvenance:
    """Provenance information for a single edge."""
    edge_id: str
    from_node: str
    to_node: str
    edge_type: str
    created_at: Optional[datetime]

    # Signals that preceded this edge
    youtube_watches: List[YouTubeWatch] = field(default_factory=list)
    rss_articles: List[RSSArticle] = field(default_factory=list)
    search_queries: List[SearchQuery] = field(default_factory=list)

    # Analysis
    earliest_signal: Optional[datetime] = None
    knowledge_gap_days: Optional[int] = None  # Days from first signal to edge
    primary_source: Optional[str] = None  # "youtube", "rss", "search"


@dataclass
class KnowledgeTimelineEvent:
    """A single event in the knowledge timeline."""
    timestamp: datetime
    event_type: str  # "youtube_watch", "rss_article", "search_query", "edge_created"
    title: str
    detail: str
    url: Optional[str] = None
    entity_mentions: List[str] = field(default_factory=list)


@dataclass
class KnowledgeTimeline:
    """Interleaved timeline of consumption and graph growth."""
    events: List[KnowledgeTimelineEvent]
    start_date: datetime
    end_date: datetime

    # Aggregations
    youtube_count: int = 0
    rss_count: int = 0
    search_count: int = 0
    edges_created: int = 0


# ─── Provenance Tracker ───────────────────────────────────────────────────────

class ProvenanceTracker:
    """
    Tracks where knowledge graph data originated from.

    Maps edges back to YouTube watches, RSS articles, and search queries
    that may have led to the discovery of that information.
    """

    # Default paths relative to base_path
    YOUTUBE_HISTORY = "data/artifacts/youtube_takeout/Takeout/YouTube and YouTube Music/history/watch-history.html"
    YOUTUBE_SEARCH = "data/artifacts/youtube_takeout/Takeout/YouTube and YouTube Music/history/search-history.html"
    RSS_ARTIFACTS = "data/artifacts/rss"

    def __init__(self, db_path: str = "fgip.db", base_path: str = "."):
        self.db_path = db_path
        self.base_path = Path(base_path)
        self.conn: Optional[sqlite3.Connection] = None

        # Cached data
        self._youtube_watches: Optional[List[YouTubeWatch]] = None
        self._rss_articles: Optional[List[RSSArticle]] = None
        self._search_queries: Optional[List[SearchQuery]] = None
        self._nodes: Dict[str, Dict] = {}
        self._edges: List[Dict] = []

    def connect(self):
        """Connect to the database and load graph data."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._load_graph()

    def _load_graph(self):
        """Load nodes and edges from database."""
        # Load nodes
        for row in self.conn.execute("SELECT * FROM nodes"):
            d = dict(row)
            self._nodes[d["node_id"]] = d

        # Load edges
        for row in self.conn.execute("SELECT * FROM edges"):
            self._edges.append(dict(row))

        print(f"Loaded: {len(self._nodes)} nodes, {len(self._edges)} edges")

    # ─── YouTube Parsing ──────────────────────────────────────────────

    def _parse_youtube_history(self) -> List[YouTubeWatch]:
        """Parse YouTube watch history HTML."""
        if self._youtube_watches is not None:
            return self._youtube_watches

        path = self.base_path / self.YOUTUBE_HISTORY
        if not path.exists():
            print(f"Warning: YouTube history not found at {path}")
            return []

        watches = []

        if HAS_BS4:
            with open(path, "r", encoding="utf-8") as f:
                soup = BeautifulSoup(f.read(), "html.parser")

            # Find all video links
            for link in soup.find_all("a", href=re.compile(r"youtube\.com/watch\?v=")):
                href = link.get("href", "")
                title = link.get_text(strip=True)

                # Extract video ID
                video_id_match = re.search(r"v=([a-zA-Z0-9_-]+)", href)
                if not video_id_match:
                    continue
                video_id = video_id_match.group(1)

                # Find timestamp (sibling or parent text)
                parent = link.find_parent("div", class_="content-cell")
                date_str = None
                if parent:
                    text = parent.get_text()
                    # Look for date pattern
                    date_match = re.search(
                        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+,\s+\d{4}",
                        text
                    )
                    if date_match:
                        date_str = date_match.group(0)

                # Parse date
                watched_at = datetime.now(timezone.utc)  # Default
                if date_str:
                    try:
                        watched_at = datetime.strptime(date_str, "%b %d, %Y")
                        watched_at = watched_at.replace(tzinfo=timezone.utc)
                    except ValueError:
                        pass

                # Try to find channel name (usually another link nearby)
                channel = None
                if parent:
                    channel_link = parent.find("a", href=re.compile(r"youtube\.com/channel/"))
                    if channel_link:
                        channel = channel_link.get_text(strip=True)

                watches.append(YouTubeWatch(
                    video_id=video_id,
                    title=title,
                    channel=channel,
                    watched_at=watched_at,
                    url=href,
                ))
        else:
            # Fallback: regex-based parsing without BeautifulSoup
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            # Find video links with titles
            pattern = r'<a href="(https://www\.youtube\.com/watch\?v=([a-zA-Z0-9_-]+))"[^>]*>([^<]+)</a>'
            for match in re.finditer(pattern, content):
                url, video_id, title = match.groups()

                # Try to find nearby date
                start = max(0, match.start() - 500)
                end = min(len(content), match.end() + 500)
                context = content[start:end]

                date_match = re.search(
                    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+,\s+\d{4}",
                    context
                )

                watched_at = datetime.now(timezone.utc)
                if date_match:
                    try:
                        watched_at = datetime.strptime(date_match.group(0), "%b %d, %Y")
                        watched_at = watched_at.replace(tzinfo=timezone.utc)
                    except ValueError:
                        pass

                watches.append(YouTubeWatch(
                    video_id=video_id,
                    title=title,
                    channel=None,
                    watched_at=watched_at,
                    url=url,
                ))

        # Sort by date (most recent first)
        watches.sort(key=lambda w: w.watched_at, reverse=True)
        self._youtube_watches = watches
        print(f"Parsed {len(watches)} YouTube watches")
        return watches

    def _parse_search_history(self) -> List[SearchQuery]:
        """Parse YouTube search history HTML."""
        if self._search_queries is not None:
            return self._search_queries

        path = self.base_path / self.YOUTUBE_SEARCH
        if not path.exists():
            print(f"Warning: Search history not found at {path}")
            return []

        queries = []

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        # Pattern: "Searched for <a ...>query</a>"
        pattern = r'Searched for <a[^>]*>([^<]+)</a>'

        for match in re.finditer(pattern, content):
            query = match.group(1)

            # Find nearby date
            start = max(0, match.start() - 500)
            end = min(len(content), match.end() + 500)
            context = content[start:end]

            date_match = re.search(
                r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+,\s+\d{4}",
                context
            )

            searched_at = datetime.now(timezone.utc)
            if date_match:
                try:
                    searched_at = datetime.strptime(date_match.group(0), "%b %d, %Y")
                    searched_at = searched_at.replace(tzinfo=timezone.utc)
                except ValueError:
                    pass

            queries.append(SearchQuery(query=query, searched_at=searched_at))

        queries.sort(key=lambda q: q.searched_at, reverse=True)
        self._search_queries = queries
        print(f"Parsed {len(queries)} search queries")
        return queries

    # ─── RSS Parsing ──────────────────────────────────────────────────

    def _parse_rss_artifacts(self) -> List[RSSArticle]:
        """Parse RSS article artifacts."""
        if self._rss_articles is not None:
            return self._rss_articles

        path = self.base_path / self.RSS_ARTIFACTS
        if not path.exists():
            print(f"Warning: RSS artifacts not found at {path}")
            return []

        articles = []

        for json_file in path.glob("article_*.json"):
            try:
                with open(json_file, "r") as f:
                    data = json.load(f)

                # Parse pub_date
                pub_date = datetime.now(timezone.utc)
                if data.get("pub_date"):
                    # Try common formats
                    for fmt in [
                        "%a, %d %b %Y %H:%M:%S %z",
                        "%Y-%m-%dT%H:%M:%S%z",
                        "%Y-%m-%d %H:%M:%S",
                    ]:
                        try:
                            pub_date = datetime.strptime(data["pub_date"], fmt)
                            if pub_date.tzinfo is None:
                                pub_date = pub_date.replace(tzinfo=timezone.utc)
                            break
                        except ValueError:
                            continue

                articles.append(RSSArticle(
                    article_id=json_file.stem,
                    title=data.get("title", ""),
                    url=data.get("url", ""),
                    pub_date=pub_date,
                    feed_id=data.get("feed_id", ""),
                    feed_name=data.get("feed_name", ""),
                    tier=data.get("tier", 2),
                    matched_entities=data.get("matched_entities", []),
                    matched_keywords=data.get("matched_keywords", []),
                ))
            except Exception as e:
                print(f"Warning: Failed to parse {json_file}: {e}")

        articles.sort(key=lambda a: a.pub_date, reverse=True)
        self._rss_articles = articles
        print(f"Parsed {len(articles)} RSS articles")
        return articles

    # ─── Provenance Queries ───────────────────────────────────────────

    def get_edge_provenance(self, edge_id: str, window_days: int = 30) -> EdgeProvenance:
        """
        Get provenance for a specific edge.

        Finds YouTube watches, RSS articles, and searches that mention
        the from/to entities and occurred before the edge was created.

        Args:
            edge_id: The edge ID to look up
            window_days: How far back to search for signals (default 30 days)

        Returns:
            EdgeProvenance with all relevant signals
        """
        if not self.conn:
            self.connect()

        # Find the edge
        row = self.conn.execute(
            "SELECT * FROM edges WHERE edge_id = ?", (edge_id,)
        ).fetchone()

        if not row:
            raise ValueError(f"Edge not found: {edge_id}")

        edge = dict(row)
        from_node = edge.get("from_node_id", "")
        to_node = edge.get("to_node_id", "")
        edge_type = edge.get("edge_type", "")

        # Parse created_at
        created_at = None
        if edge.get("created_at"):
            try:
                created_at = datetime.fromisoformat(edge["created_at"].replace("Z", "+00:00"))
            except ValueError:
                pass

        # Get entity names
        from_name = self._nodes.get(from_node, {}).get("name", from_node)
        to_name = self._nodes.get(to_node, {}).get("name", to_node)

        # Load signals
        youtube = self._parse_youtube_history()
        rss = self._parse_rss_artifacts()
        searches = self._parse_search_history()

        # Filter by time window
        cutoff = created_at - timedelta(days=window_days) if created_at else None

        # Find matching YouTube watches
        matching_youtube = []
        for watch in youtube:
            if cutoff and watch.watched_at < cutoff:
                continue
            if created_at and watch.watched_at > created_at:
                continue
            if watch.matches_entity(from_name) or watch.matches_entity(to_name):
                matching_youtube.append(watch)

        # Find matching RSS articles
        matching_rss = []
        for article in rss:
            if cutoff and article.pub_date < cutoff:
                continue
            if created_at and article.pub_date > created_at:
                continue
            if article.matches_entity(from_name) or article.matches_entity(to_name):
                matching_rss.append(article)

        # Find matching searches
        matching_searches = []
        for query in searches:
            if cutoff and query.searched_at < cutoff:
                continue
            if created_at and query.searched_at > created_at:
                continue
            query_lower = query.query.lower()
            if from_name.lower() in query_lower or to_name.lower() in query_lower:
                matching_searches.append(query)

        # Calculate earliest signal and knowledge gap
        all_dates = []
        if matching_youtube:
            all_dates.extend(w.watched_at for w in matching_youtube)
        if matching_rss:
            all_dates.extend(a.pub_date for a in matching_rss)
        if matching_searches:
            all_dates.extend(s.searched_at for s in matching_searches)

        earliest_signal = min(all_dates) if all_dates else None
        knowledge_gap = None
        if earliest_signal and created_at:
            knowledge_gap = (created_at - earliest_signal).days

        # Determine primary source
        primary_source = None
        if matching_youtube and (not matching_rss or matching_youtube[0].watched_at > matching_rss[0].pub_date):
            primary_source = "youtube"
        elif matching_rss:
            primary_source = "rss"
        elif matching_searches:
            primary_source = "search"

        return EdgeProvenance(
            edge_id=edge_id,
            from_node=from_node,
            to_node=to_node,
            edge_type=edge_type,
            created_at=created_at,
            youtube_watches=matching_youtube,
            rss_articles=matching_rss,
            search_queries=matching_searches,
            earliest_signal=earliest_signal,
            knowledge_gap_days=knowledge_gap,
            primary_source=primary_source,
        )

    def query_provenance(self, entity_name: str, window_days: int = 90) -> Dict[str, Any]:
        """
        Query all provenance for a given entity.

        Answers: "Where did knowledge about Intel originate?"

        Args:
            entity_name: Entity name to search for
            window_days: How far back to search

        Returns:
            Dict with provenance information
        """
        if not self.conn:
            self.connect()

        # Load signals
        youtube = self._parse_youtube_history()
        rss = self._parse_rss_artifacts()
        searches = self._parse_search_history()

        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

        # Find matching YouTube watches
        matching_youtube = [
            w for w in youtube
            if w.watched_at >= cutoff and w.matches_entity(entity_name)
        ]

        # Find matching RSS articles
        matching_rss = [
            a for a in rss
            if a.pub_date >= cutoff and a.matches_entity(entity_name)
        ]

        # Find matching searches
        entity_lower = entity_name.lower()
        matching_searches = [
            s for s in searches
            if s.searched_at >= cutoff and entity_lower in s.query.lower()
        ]

        # Find edges involving this entity
        matching_edges = []
        for edge in self._edges:
            from_id = edge.get("from_node_id", "")
            to_id = edge.get("to_node_id", "")
            from_name = self._nodes.get(from_id, {}).get("name", from_id)
            to_name = self._nodes.get(to_id, {}).get("name", to_id)

            if (entity_lower in from_id.lower() or entity_lower in to_id.lower() or
                entity_lower in from_name.lower() or entity_lower in to_name.lower()):
                matching_edges.append(edge)

        # Calculate earliest signal
        all_dates = []
        if matching_youtube:
            all_dates.extend(w.watched_at for w in matching_youtube)
        if matching_rss:
            all_dates.extend(a.pub_date for a in matching_rss)
        if matching_searches:
            all_dates.extend(s.searched_at for s in matching_searches)

        earliest_signal = min(all_dates) if all_dates else None

        return {
            "entity": entity_name,
            "youtube_watches": len(matching_youtube),
            "rss_articles": len(matching_rss),
            "search_queries": len(matching_searches),
            "edges": len(matching_edges),
            "earliest_signal": earliest_signal.isoformat() if earliest_signal else None,
            "provenance": [
                {
                    "type": "youtube",
                    "title": w.title[:100],
                    "date": w.watched_at.isoformat(),
                    "url": w.url,
                }
                for w in matching_youtube[:10]
            ] + [
                {
                    "type": "rss",
                    "title": a.title[:100],
                    "date": a.pub_date.isoformat(),
                    "url": a.url,
                    "feed": a.feed_name,
                }
                for a in matching_rss[:10]
            ] + [
                {
                    "type": "search",
                    "query": s.query,
                    "date": s.searched_at.isoformat(),
                }
                for s in matching_searches[:10]
            ],
        }

    def build_timeline(self, days: int = 30) -> KnowledgeTimeline:
        """
        Build an interleaved timeline of consumption and graph growth.

        Shows YouTube watches, RSS articles, and edge creation events
        in chronological order.

        Args:
            days: Number of days to include

        Returns:
            KnowledgeTimeline with all events
        """
        if not self.conn:
            self.connect()

        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        events: List[KnowledgeTimelineEvent] = []

        # Load signals
        youtube = self._parse_youtube_history()
        rss = self._parse_rss_artifacts()
        searches = self._parse_search_history()

        youtube_count = 0
        rss_count = 0
        search_count = 0
        edges_count = 0

        # Add YouTube watches
        for watch in youtube:
            if start_date <= watch.watched_at <= end_date:
                youtube_count += 1
                events.append(KnowledgeTimelineEvent(
                    timestamp=watch.watched_at,
                    event_type="youtube_watch",
                    title=watch.title[:80],
                    detail=f"Channel: {watch.channel or 'Unknown'}",
                    url=watch.url,
                ))

        # Add RSS articles
        for article in rss:
            if start_date <= article.pub_date <= end_date:
                rss_count += 1
                events.append(KnowledgeTimelineEvent(
                    timestamp=article.pub_date,
                    event_type="rss_article",
                    title=article.title[:80],
                    detail=f"Feed: {article.feed_name} (Tier {article.tier})",
                    url=article.url,
                    entity_mentions=article.matched_entities,
                ))

        # Add search queries
        for query in searches:
            if start_date <= query.searched_at <= end_date:
                search_count += 1
                events.append(KnowledgeTimelineEvent(
                    timestamp=query.searched_at,
                    event_type="search_query",
                    title=f"Searched: {query.query}",
                    detail="YouTube search",
                ))

        # Add edge creation events
        for edge in self._edges:
            if edge.get("created_at"):
                try:
                    created = datetime.fromisoformat(edge["created_at"].replace("Z", "+00:00"))
                    if start_date <= created <= end_date:
                        edges_count += 1
                        from_id = edge.get("from_node_id", "?")
                        to_id = edge.get("to_node_id", "?")
                        from_name = self._nodes.get(from_id, {}).get("name", from_id)
                        to_name = self._nodes.get(to_id, {}).get("name", to_id)

                        events.append(KnowledgeTimelineEvent(
                            timestamp=created,
                            event_type="edge_created",
                            title=f"{from_name} → {edge.get('edge_type', '?')} → {to_name}",
                            detail=f"Edge: {edge.get('edge_id', '')}",
                            entity_mentions=[from_id, to_id],
                        ))
                except (ValueError, TypeError):
                    pass

        # Sort by timestamp
        events.sort(key=lambda e: e.timestamp, reverse=True)

        return KnowledgeTimeline(
            events=events,
            start_date=start_date,
            end_date=end_date,
            youtube_count=youtube_count,
            rss_count=rss_count,
            search_count=search_count,
            edges_created=edges_count,
        )

    def get_signal_summary(self) -> Dict[str, Any]:
        """Get a summary of all available signal data."""
        youtube = self._parse_youtube_history()
        rss = self._parse_rss_artifacts()
        searches = self._parse_search_history()

        # Count by source
        youtube_channels = defaultdict(int)
        for w in youtube:
            if w.channel:
                youtube_channels[w.channel] += 1

        rss_feeds = defaultdict(int)
        for a in rss:
            rss_feeds[a.feed_name] += 1

        return {
            "youtube": {
                "total_watches": len(youtube),
                "top_channels": sorted(
                    youtube_channels.items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:10],
                "date_range": {
                    "earliest": min(w.watched_at for w in youtube).isoformat() if youtube else None,
                    "latest": max(w.watched_at for w in youtube).isoformat() if youtube else None,
                },
            },
            "rss": {
                "total_articles": len(rss),
                "feeds": sorted(
                    rss_feeds.items(),
                    key=lambda x: x[1],
                    reverse=True
                ),
                "date_range": {
                    "earliest": min(a.pub_date for a in rss).isoformat() if rss else None,
                    "latest": max(a.pub_date for a in rss).isoformat() if rss else None,
                },
            },
            "search": {
                "total_queries": len(searches),
                "date_range": {
                    "earliest": min(s.searched_at for s in searches).isoformat() if searches else None,
                    "latest": max(s.searched_at for s in searches).isoformat() if searches else None,
                },
            },
            "graph": {
                "nodes": len(self._nodes),
                "edges": len(self._edges),
            },
        }


# ─── CLI Entry Point ──────────────────────────────────────────────────────────

def main():
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="FGIP Provenance Tracker")
    parser.add_argument("--db", default="fgip.db", help="Database path")
    parser.add_argument("--base", default=".", help="Base path for artifacts")
    parser.add_argument("--edge", help="Get provenance for specific edge ID")
    parser.add_argument("--entity", help="Query provenance for entity")
    parser.add_argument("--timeline", type=int, help="Build timeline for N days")
    parser.add_argument("--summary", action="store_true", help="Show signal summary")

    args = parser.parse_args()

    tracker = ProvenanceTracker(db_path=args.db, base_path=args.base)
    tracker.connect()

    if args.edge:
        prov = tracker.get_edge_provenance(args.edge)
        print(f"\n=== Provenance for Edge: {args.edge} ===")
        print(f"From: {prov.from_node}")
        print(f"To: {prov.to_node}")
        print(f"Type: {prov.edge_type}")
        print(f"Created: {prov.created_at}")
        print(f"\nYouTube Watches: {len(prov.youtube_watches)}")
        for w in prov.youtube_watches[:5]:
            print(f"  - {w.watched_at.strftime('%Y-%m-%d')}: {w.title[:60]}")
        print(f"\nRSS Articles: {len(prov.rss_articles)}")
        for a in prov.rss_articles[:5]:
            print(f"  - {a.pub_date.strftime('%Y-%m-%d')}: {a.title[:60]}")
        print(f"\nEarliest Signal: {prov.earliest_signal}")
        print(f"Knowledge Gap: {prov.knowledge_gap_days} days")
        print(f"Primary Source: {prov.primary_source}")

    elif args.entity:
        result = tracker.query_provenance(args.entity)
        print(f"\n=== Provenance for Entity: {args.entity} ===")
        print(f"YouTube Watches: {result['youtube_watches']}")
        print(f"RSS Articles: {result['rss_articles']}")
        print(f"Search Queries: {result['search_queries']}")
        print(f"Graph Edges: {result['edges']}")
        print(f"Earliest Signal: {result['earliest_signal']}")
        print("\nTop Provenance Sources:")
        for p in result["provenance"][:10]:
            print(f"  [{p['type']}] {p.get('date', '')[:10]}: {p.get('title', p.get('query', ''))[:50]}")

    elif args.timeline:
        timeline = tracker.build_timeline(days=args.timeline)
        print(f"\n=== Knowledge Timeline ({args.timeline} days) ===")
        print(f"YouTube Watches: {timeline.youtube_count}")
        print(f"RSS Articles: {timeline.rss_count}")
        print(f"Search Queries: {timeline.search_count}")
        print(f"Edges Created: {timeline.edges_created}")
        print("\nRecent Events:")
        for event in timeline.events[:20]:
            icon = {
                "youtube_watch": "[YT]",
                "rss_article": "[RSS]",
                "search_query": "[Q]",
                "edge_created": "[EDGE]",
            }.get(event.event_type, "[?]")
            print(f"  {event.timestamp.strftime('%Y-%m-%d %H:%M')} {icon} {event.title[:60]}")

    elif args.summary:
        summary = tracker.get_signal_summary()
        print("\n=== Signal Summary ===")
        print(f"\nYouTube: {summary['youtube']['total_watches']} watches")
        if summary['youtube']['top_channels']:
            print("  Top Channels:")
            for channel, count in summary['youtube']['top_channels'][:5]:
                print(f"    - {channel}: {count}")

        print(f"\nRSS: {summary['rss']['total_articles']} articles")
        if summary['rss']['feeds']:
            print("  Feeds:")
            for feed, count in summary['rss']['feeds'][:5]:
                print(f"    - {feed}: {count}")

        print(f"\nSearch: {summary['search']['total_queries']} queries")
        print(f"\nGraph: {summary['graph']['nodes']} nodes, {summary['graph']['edges']} edges")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
