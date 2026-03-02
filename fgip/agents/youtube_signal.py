"""
YouTube Signal Layer - Parse Google Takeout watch history into signal graph.

Extracts guests, channels, and topics from video titles, cross-references against
FGIP nodes, and builds a consumption-to-thesis connection layer.

Your viewing pattern IS a signal graph. This module makes it queryable.
"""

import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from html import unescape
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import argparse


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class YouTubeVideo:
    """Parsed video from watch history."""
    video_id: str                    # YouTube video ID
    title: str                       # Video title
    channel: str                     # Channel name
    url: str                         # Full URL
    watch_time: Optional[str]        # ISO timestamp
    watch_count: int = 1             # Times watched


@dataclass
class ExtractedGuest:
    """Guest extracted from video title."""
    name: str                        # "Michael Saylor"
    normalized_name: str             # "michael-saylor"
    video_id: str                    # Source video
    confidence: float                # Extraction confidence
    matched_node_id: Optional[str] = None  # FGIP node if matched


@dataclass
class ChannelProfile:
    """Aggregated channel statistics."""
    channel_name: str
    video_count: int
    total_watches: int
    topics: List[str] = field(default_factory=list)       # Detected topics
    frequent_guests: List[str] = field(default_factory=list)  # Guest names
    fgip_relevance_score: float = 0.0  # 0-1 thesis relevance


@dataclass
class SignalLayerReport:
    """Full signal layer analysis."""
    total_videos: int
    unique_channels: int
    extracted_guests: List[ExtractedGuest]
    channel_profiles: List[ChannelProfile]
    fgip_matches: List[Dict]         # Videos matching FGIP nodes
    topic_distribution: Dict[str, int]
    timestamp: str


# =============================================================================
# FGIP Topic Classification
# =============================================================================

FGIP_TOPICS = {
    'china': ['china', 'ccp', 'beijing', 'xi jinping', 'pntr', 'chinese', 'taiwan'],
    'tariffs': ['tariff', 'trade war', 'import', 'export', 'duties', 'trade policy'],
    'reshoring': ['reshoring', 'onshoring', 'chips act', 'manufacturing', 'supply chain', 'nearshoring'],
    'stablecoin': ['stablecoin', 'tether', 'usdc', 'genius act', 'crypto', 'cbdc', 'digital dollar', 'usdt'],
    'fed': ['federal reserve', 'fed', 'inflation', 'm2', 'money supply', 'monetary policy', 'interest rate', 'jerome powell'],
    'intelligence': ['cia', 'fbi', 'intelligence', 'espionage', 'spy', 'nsa', 'covert', 'classified'],
    'geopolitics': ['geopolitics', 'zeihan', 'demographics', 'russia', 'ukraine', 'nato', 'brics', 'middle east'],
    'finance': ['blackrock', 'vanguard', 'etf', 'institutional', 'index fund', 'wall street', 'hedge fund'],
    'bitcoin': ['bitcoin', 'btc', 'saylor', 'satoshi', 'lightning network', 'hash rate'],
    'politics': ['trump', 'biden', 'congress', 'senate', 'legislation', 'policy', 'election', 'executive order'],
    'military': ['military', 'pentagon', 'defense', 'weapon', 'missile', 'drone', 'warfare'],
    'energy': ['oil', 'gas', 'energy', 'nuclear', 'renewable', 'opec', 'lng', 'uranium'],
}


# =============================================================================
# Guest Extraction Patterns
# =============================================================================

# Generic patterns for extracting guests from titles
GUEST_PATTERNS = [
    # Podcast episode formats: "#123 - Guest Name" or "Ep. 123: Guest Name"
    (r'^(?:#|Ep\.?\s*)?(\d+)\s*[-–:]\s*([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){1,3})(?:\s*[-–|:]|$)', 0.85),

    # "Guest Name | Topic" or "Guest Name - Topic"
    (r'^([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){1,3})\s*[-–|]\s*[A-Z]', 0.80),

    # "Interview with Guest Name"
    (r'(?:interview|conversation|talk)(?:ing)?\s+(?:with\s+)?([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){1,3})', 0.90),

    # "Guest Name on Topic"
    (r'^([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){1,3})\s+on\s+[A-Z]', 0.75),

    # "with Guest Name" (featuring)
    (r'(?:with|ft\.?|featuring)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){1,3})(?:\s*[-–|]|$)', 0.80),
]

# Channel-specific patterns (more reliable)
PODCAST_CHANNEL_PATTERNS = {
    'Lex Fridman': [
        (r'^#?\d+\s*[-–]\s*(.+?)(?:\s*[-–|:]|$)', 0.95),  # "#276 – Michael Saylor: ..."
        (r'^(.+?):\s*.+$', 0.85),  # "Guest Name: Topic"
    ],
    'Shawn Ryan Show': [
        (r'(?:SRS\s*)?#?\d+\s*[-–]\s*([A-Z][^|]+?)(?:\s*[-–|]|$)', 0.95),  # "SRS #280 - Sarah Adams | ..."
        (r'^([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)+)\s*[-–]\s*', 0.90),  # "Name Name - Topic"
    ],
    'Joe Rogan Experience': [
        (r'^#?\d+\s*[-–]\s*(.+?)(?:\s*[-–|:]|$)', 0.95),
    ],
    'PBD Podcast': [
        (r'(?:PBD\s*)?#?\d+\s*[-–]\s*(.+?)(?:\s*[-–|]|$)', 0.90),
    ],
    'Valuetainment': [
        (r'^(?:")?([A-Z][^"]+?)(?:"|\s*[-–])?\s*[-–]\s*', 0.85),
    ],
    'Julian Dorey Podcast': [
        (r'^(?:")?(.+?)(?:")?\s*[-–]\s*', 0.85),
    ],
    'Peter Zeihan': [
        (r'^([A-Z][^:]+?):\s*', 0.75),  # "Topic: Subtitle"
    ],
}

# Names to exclude (not actual guests)
GUEST_BLACKLIST = {
    'breaking news', 'live stream', 'full episode', 'highlight', 'clip',
    'part one', 'part two', 'part 1', 'part 2', 'interview', 'podcast',
    'reaction', 'response', 'analysis', 'breaking', 'update', 'the truth',
    'what happened', 'why did', 'how did', 'explained', 'vs', 'versus',
    'debate', 'shorts', 'short', 'reacts', 'responds', 'calls out',
}


# =============================================================================
# HTML Parsing
# =============================================================================

def parse_watch_history(html_path: str) -> List[YouTubeVideo]:
    """
    Parse Google Takeout watch-history.html into structured videos.

    Handles:
    - HTML parsing with regex (no BeautifulSoup dependency)
    - Deduplication (same video watched multiple times)
    - Timestamp extraction
    - HTML entity decoding
    """
    path = Path(html_path)
    if not path.exists():
        raise FileNotFoundError(f"Watch history file not found: {html_path}")

    content = path.read_text(encoding='utf-8')

    # Pattern to extract video entries
    # Format: "Watched <a href="URL">TITLE</a>...<a href="channel/...">CHANNEL</a>...TIMESTAMP"
    video_pattern = re.compile(
        r'content-cell[^>]*>Watched\s+<a href="([^"]+)">([^<]+)</a>'
        r'.*?<a href="[^"]*(?:channel|user)[^"]*">([^<]+)</a>'
        r'.*?(\w{3} \d{1,2}, \d{4}[^<]*)<',
        re.DOTALL
    )

    matches = video_pattern.findall(content)

    # Track videos for deduplication
    video_counts: Dict[str, int] = defaultdict(int)
    video_data: Dict[str, Tuple[str, str, str, str]] = {}

    for url, title, channel, timestamp in matches:
        # Extract video ID from URL
        video_id = extract_video_id(url)
        if not video_id:
            continue

        # Decode HTML entities
        title = unescape(title)
        channel = unescape(channel)

        # Track watch count
        video_counts[video_id] += 1

        # Keep first occurrence (most recent in reverse chronological)
        if video_id not in video_data:
            video_data[video_id] = (title, channel, url, timestamp.strip())

    # Build video list
    videos = []
    for video_id, (title, channel, url, timestamp) in video_data.items():
        watch_time = parse_timestamp(timestamp)
        videos.append(YouTubeVideo(
            video_id=video_id,
            title=title,
            channel=channel,
            url=url,
            watch_time=watch_time,
            watch_count=video_counts[video_id]
        ))

    return videos


def extract_video_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from URL."""
    # https://www.youtube.com/watch?v=VIDEO_ID
    match = re.search(r'watch\?v=([a-zA-Z0-9_-]{11})', url)
    if match:
        return match.group(1)

    # https://youtu.be/VIDEO_ID
    match = re.search(r'youtu\.be/([a-zA-Z0-9_-]{11})', url)
    if match:
        return match.group(1)

    return None


def parse_timestamp(timestamp_str: str) -> Optional[str]:
    """Parse Google Takeout timestamp to ISO format."""
    # Format: "Feb 14, 2026, 6:13:49 PM EST"
    try:
        # Remove timezone abbreviation for parsing
        ts_clean = re.sub(r'\s+[A-Z]{2,4}\s*$', '', timestamp_str)
        dt = datetime.strptime(ts_clean, "%b %d, %Y, %I:%M:%S %p")
        return dt.isoformat()
    except ValueError:
        try:
            # Try alternative format without time
            dt = datetime.strptime(timestamp_str, "%b %d, %Y")
            return dt.isoformat()
        except ValueError:
            return None


# =============================================================================
# Guest Extraction
# =============================================================================

def extract_guests_from_title(title: str, channel: str = "") -> List[Tuple[str, float]]:
    """
    Extract guest names from video title.

    Returns list of (name, confidence) tuples.
    """
    guests = []

    # Try channel-specific patterns first
    if channel:
        for channel_pattern, patterns in PODCAST_CHANNEL_PATTERNS.items():
            if channel_pattern.lower() in channel.lower():
                for pattern, confidence in patterns:
                    match = re.search(pattern, title, re.IGNORECASE)
                    if match:
                        name = match.group(1).strip()
                        if is_valid_guest_name(name):
                            guests.append((clean_guest_name(name), confidence))
                break

    # Fall back to generic patterns
    if not guests:
        for pattern, confidence in GUEST_PATTERNS:
            match = re.search(pattern, title)
            if match:
                # Get the guest name group (usually group 1 or 2)
                name = match.group(match.lastindex).strip() if match.lastindex else None
                if name and is_valid_guest_name(name):
                    guests.append((clean_guest_name(name), confidence))

    return guests


def is_valid_guest_name(name: str) -> bool:
    """Check if extracted name looks like a real guest name."""
    if not name:
        return False

    name_lower = name.lower()

    # Check blacklist
    if name_lower in GUEST_BLACKLIST:
        return False

    # Check for common invalid patterns
    if any(word in name_lower for word in GUEST_BLACKLIST):
        return False

    # Must have at least first and last name (2+ words starting with caps)
    words = name.split()
    if len(words) < 2:
        return False

    # Check that words look like names (start with capital, reasonable length)
    for word in words[:3]:  # Check first 3 words
        if len(word) < 2 or not word[0].isupper():
            return False

    # Reject if too long (probably a phrase, not a name)
    if len(words) > 4:
        return False

    return True


def clean_guest_name(name: str) -> str:
    """Clean and normalize guest name."""
    # Remove common suffixes
    name = re.sub(r'\s*[-–|:]\s*.*$', '', name)
    name = re.sub(r'\s*\(.*?\)\s*$', '', name)
    name = re.sub(r'\s*#\d+\s*$', '', name)

    # Remove quotes
    name = name.strip('"\'')

    # Normalize whitespace
    name = ' '.join(name.split())

    return name.strip()


def normalize_name(name: str) -> str:
    """Convert name to normalized ID format."""
    # "Michael Saylor" -> "michael-saylor"
    normalized = name.lower()
    normalized = re.sub(r'[^a-z0-9\s]', '', normalized)
    normalized = re.sub(r'\s+', '-', normalized)
    return normalized.strip('-')


# =============================================================================
# Topic Classification
# =============================================================================

def classify_video_topics(video: YouTubeVideo) -> List[str]:
    """Classify video into FGIP-relevant topics based on title and channel."""
    text = f"{video.title} {video.channel}".lower()
    matched_topics = []

    for topic, keywords in FGIP_TOPICS.items():
        for keyword in keywords:
            if keyword in text:
                matched_topics.append(topic)
                break

    return matched_topics


# =============================================================================
# FGIP Node Matching
# =============================================================================

def load_fgip_nodes(db_path: str) -> Dict[str, Dict]:
    """Load FGIP nodes for matching."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT node_id, name, node_type, aliases
        FROM nodes
    """)

    nodes = {}
    for node_id, name, node_type, aliases_json in cursor.fetchall():
        aliases = json.loads(aliases_json) if aliases_json else []
        nodes[node_id] = {
            'node_id': node_id,
            'name': name,
            'node_type': node_type,
            'aliases': aliases,
            'search_terms': [name.lower()] + [a.lower() for a in aliases]
        }

    conn.close()
    return nodes


def match_to_fgip_nodes(
    guests: List[ExtractedGuest],
    videos: List[YouTubeVideo],
    db_path: str
) -> List[Dict]:
    """
    Cross-reference extracted entities against FGIP graph.

    Returns matches with:
    - node_id
    - node_name
    - match_type (guest, channel, topic)
    - video_ids that reference this node
    """
    nodes = load_fgip_nodes(db_path)

    # Index for quick lookups - filter aggressively to reduce noise
    # Single-word person names like "Jones", "Forbes", "Peterson" cause too many false positives
    name_to_node: Dict[str, str] = {}
    for node_id, node_data in nodes.items():
        for term in node_data['search_terms']:
            node_type = node_data['node_type']

            # PERSON: require multi-word names (First Last) or very long names (10+ chars)
            if node_type == 'PERSON':
                is_multi_word = ' ' in term
                is_very_long = len(term) >= 10  # e.g., "washington" but not "jones"
                if not (is_multi_word or is_very_long):
                    continue

            # Non-person entities: require minimum 6 chars
            else:
                is_organization = node_type in ('COMPANY', 'FINANCIAL_INST', 'ORGANIZATION', 'LEGISLATION', 'MEDIA_OUTLET', 'AGENCY')
                is_long_enough = len(term) >= 6
                is_multi_word = ' ' in term
                if not (is_multi_word or (is_long_enough and is_organization)):
                    continue

            name_to_node[term] = node_id

    # Match guests to nodes
    guest_matches: Dict[str, Set[str]] = defaultdict(set)
    for guest in guests:
        name_lower = guest.name.lower()
        normalized = guest.normalized_name

        # Try exact match
        matched_node = name_to_node.get(name_lower) or name_to_node.get(normalized)

        # Try partial match on longer names
        if not matched_node:
            for term, node_id in name_to_node.items():
                if len(term) > 10 and (term in name_lower or name_lower in term):
                    matched_node = node_id
                    break

        if matched_node:
            guest.matched_node_id = matched_node
            guest_matches[matched_node].add(guest.video_id)

    # Match videos to nodes via title/channel content
    # Use the filtered name_to_node index (which excludes noisy single-word person names)
    topic_matches: Dict[str, Set[str]] = defaultdict(set)
    for video in videos:
        text = f"{video.title} {video.channel}".lower()
        for term, node_id in name_to_node.items():
            # Require longer terms and word boundary matching
            if len(term) >= 6:
                # Check for word boundary match (not substring of larger word)
                pattern = r'\b' + re.escape(term) + r'\b'
                if re.search(pattern, text):
                    topic_matches[node_id].add(video.video_id)
                    break

    # Build match results - deduplicate by node_id
    seen_nodes = set()
    matches = []
    all_matched_nodes = set(guest_matches.keys()) | set(topic_matches.keys())

    for node_id in all_matched_nodes:
        if node_id in seen_nodes:
            continue
        seen_nodes.add(node_id)

        node_data = nodes.get(node_id, {})
        guest_videos = guest_matches.get(node_id, set())
        topic_videos = topic_matches.get(node_id, set())
        all_videos = guest_videos | topic_videos

        if all_videos:
            matches.append({
                'node_id': node_id,
                'node_name': node_data.get('name', node_id),
                'node_type': node_data.get('node_type', 'UNKNOWN'),
                'match_type': 'guest' if guest_videos else 'topic',
                'video_count': len(all_videos),
                'video_ids': list(all_videos)[:10],  # Limit for report
                'guest_count': len(guest_videos),
                'topic_count': len(topic_videos),
            })

    # Sort by video count
    matches.sort(key=lambda x: x['video_count'], reverse=True)

    return matches


# =============================================================================
# Channel Profiles
# =============================================================================

def build_channel_profiles(
    videos: List[YouTubeVideo],
    guests: List[ExtractedGuest]
) -> List[ChannelProfile]:
    """
    Aggregate statistics by channel.

    Returns list of ChannelProfile sorted by FGIP relevance.
    """
    # Group videos by channel
    channel_videos: Dict[str, List[YouTubeVideo]] = defaultdict(list)
    for video in videos:
        channel_videos[video.channel].append(video)

    # Group guests by channel
    channel_guests: Dict[str, Set[str]] = defaultdict(set)
    for guest in guests:
        video = next((v for v in videos if v.video_id == guest.video_id), None)
        if video:
            channel_guests[video.channel].add(guest.name)

    profiles = []
    for channel_name, channel_vids in channel_videos.items():
        # Aggregate topics
        topic_counts: Dict[str, int] = defaultdict(int)
        for video in channel_vids:
            for topic in classify_video_topics(video):
                topic_counts[topic] += 1

        # Calculate FGIP relevance (proportion of videos with FGIP topics)
        videos_with_topics = sum(1 for v in channel_vids if classify_video_topics(v))
        relevance = videos_with_topics / len(channel_vids) if channel_vids else 0.0

        # Boost for known high-signal channels
        high_signal_channels = ['peter zeihan', 'shawn ryan', 'lex fridman', 'valuetainment',
                                'julian dorey', 'coin bureau', 'pbd', 'all-in podcast']
        if any(hsc in channel_name.lower() for hsc in high_signal_channels):
            relevance = min(1.0, relevance + 0.3)

        # Total watches
        total_watches = sum(v.watch_count for v in channel_vids)

        profiles.append(ChannelProfile(
            channel_name=channel_name,
            video_count=len(channel_vids),
            total_watches=total_watches,
            topics=sorted(topic_counts.keys(), key=lambda t: topic_counts[t], reverse=True),
            frequent_guests=list(channel_guests.get(channel_name, set()))[:10],
            fgip_relevance_score=round(relevance, 3)
        ))

    # Sort by relevance then video count
    profiles.sort(key=lambda p: (p.fgip_relevance_score, p.video_count), reverse=True)

    return profiles


# =============================================================================
# Main Analyzer Class
# =============================================================================

class YouTubeSignalAnalyzer:
    """
    Ingests YouTube watch history and builds signal layer.

    This is the TEMPLATE for future ingestion pipelines.
    """

    def __init__(self, db_path: str = 'fgip.db'):
        self.db_path = db_path
        self.nodes = {}
        self.videos: List[YouTubeVideo] = []
        self.guests: List[ExtractedGuest] = []
        self.channel_profiles: List[ChannelProfile] = []

    def ingest_history(self, html_path: str) -> SignalLayerReport:
        """
        Full ingestion pipeline.

        1. Parse HTML
        2. Extract guests
        3. Classify topics
        4. Match to FGIP nodes
        5. Build channel profiles
        6. Generate report
        """
        # 1. Parse HTML
        print(f"Parsing watch history from {html_path}...")
        self.videos = parse_watch_history(html_path)
        print(f"  Found {len(self.videos)} unique videos")

        # 2. Extract guests
        print("Extracting guests from titles...")
        self.guests = []
        for video in self.videos:
            extracted = extract_guests_from_title(video.title, video.channel)
            for name, confidence in extracted:
                self.guests.append(ExtractedGuest(
                    name=name,
                    normalized_name=normalize_name(name),
                    video_id=video.video_id,
                    confidence=confidence
                ))
        print(f"  Extracted {len(self.guests)} guest mentions")

        # 3. Build topic distribution
        print("Classifying topics...")
        topic_dist: Dict[str, int] = defaultdict(int)
        for video in self.videos:
            for topic in classify_video_topics(video):
                topic_dist[topic] += 1

        # 4. Match to FGIP nodes
        print("Matching to FGIP graph...")
        fgip_matches = []
        if Path(self.db_path).exists():
            fgip_matches = match_to_fgip_nodes(self.guests, self.videos, self.db_path)
            print(f"  Found {len(fgip_matches)} FGIP node matches")
        else:
            print(f"  Warning: FGIP database not found at {self.db_path}")

        # 5. Build channel profiles
        print("Building channel profiles...")
        self.channel_profiles = build_channel_profiles(self.videos, self.guests)

        # 6. Generate report
        unique_channels = len(set(v.channel for v in self.videos))

        report = SignalLayerReport(
            total_videos=len(self.videos),
            unique_channels=unique_channels,
            extracted_guests=self.guests,
            channel_profiles=self.channel_profiles,
            fgip_matches=fgip_matches,
            topic_distribution=dict(topic_dist),
            timestamp=datetime.utcnow().isoformat() + 'Z'
        )

        print(f"\nSignal layer built:")
        print(f"  Videos: {report.total_videos}")
        print(f"  Channels: {report.unique_channels}")
        print(f"  Guests: {len(report.extracted_guests)}")
        print(f"  FGIP matches: {len(report.fgip_matches)}")

        return report

    def get_videos_for_node(self, node_id: str) -> List[YouTubeVideo]:
        """Find videos that reference a specific FGIP node."""
        if not self.nodes:
            self.nodes = load_fgip_nodes(self.db_path)

        node = self.nodes.get(node_id)
        if not node:
            return []

        matching_videos = []
        search_terms = node['search_terms']

        for video in self.videos:
            text = f"{video.title} {video.channel}".lower()
            if any(term in text for term in search_terms if len(term) > 4):
                matching_videos.append(video)

        return matching_videos

    def get_high_signal_channels(self, min_relevance: float = 0.5) -> List[ChannelProfile]:
        """Get channels most relevant to FGIP thesis."""
        return [p for p in self.channel_profiles if p.fgip_relevance_score >= min_relevance]

    def to_json(self, report: SignalLayerReport) -> str:
        """Convert report to JSON format."""
        return json.dumps({
            'timestamp': report.timestamp,
            'total_videos': report.total_videos,
            'unique_channels': report.unique_channels,
            'fgip_matches': report.fgip_matches[:50],  # Top 50
            'top_channels': [
                {
                    'channel': p.channel_name,
                    'videos': p.video_count,
                    'total_watches': p.total_watches,
                    'fgip_relevance': p.fgip_relevance_score,
                    'topics': p.topics[:5],
                    'guests': p.frequent_guests[:5],
                }
                for p in report.channel_profiles[:30]  # Top 30
            ],
            'topic_distribution': report.topic_distribution,
            'extracted_guests_sample': [
                {
                    'name': g.name,
                    'confidence': g.confidence,
                    'matched_node': g.matched_node_id,
                }
                for g in report.extracted_guests[:100]  # Sample
            ],
        }, indent=2)


# =============================================================================
# CLI Entry Point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Parse YouTube watch history and build FGIP signal layer'
    )
    parser.add_argument(
        'html_path',
        help='Path to watch-history.html from Google Takeout'
    )
    parser.add_argument(
        '--db', '-d',
        default='fgip.db',
        help='Path to FGIP database (default: fgip.db)'
    )
    parser.add_argument(
        '--output', '-o',
        help='Output JSON file path'
    )
    parser.add_argument(
        '--min-relevance', '-r',
        type=float,
        default=0.3,
        help='Minimum relevance score for channel profiles (default: 0.3)'
    )

    args = parser.parse_args()

    analyzer = YouTubeSignalAnalyzer(db_path=args.db)
    report = analyzer.ingest_history(args.html_path)

    # Output results
    json_output = analyzer.to_json(report)

    if args.output:
        Path(args.output).write_text(json_output)
        print(f"\nReport saved to: {args.output}")
    else:
        print("\n" + "="*60)
        print("SIGNAL LAYER REPORT")
        print("="*60)
        print(json_output)

    # Print high-signal channels
    high_signal = analyzer.get_high_signal_channels(args.min_relevance)
    if high_signal:
        print(f"\n{'='*60}")
        print(f"HIGH-SIGNAL CHANNELS (relevance >= {args.min_relevance})")
        print("="*60)
        for profile in high_signal[:15]:
            print(f"  {profile.channel_name}")
            print(f"    Videos: {profile.video_count}, Relevance: {profile.fgip_relevance_score}")
            if profile.topics:
                print(f"    Topics: {', '.join(profile.topics[:5])}")
            print()


if __name__ == '__main__':
    main()
