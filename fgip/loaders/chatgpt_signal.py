"""
ChatGPT Signal Loader - Merge ChatGPT's pre-tagged YouTube analysis with FGIP.

Loads youtube_signal_layer.json (4,181 FGIP-relevant videos) and merges:
1. Channel classifications (tier/layer/role)
2. Category distribution (intelligence_espionage, defense_industrial, etc.)
3. Guest frequency weights
4. Signal entries for provenance linking
"""

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


@dataclass
class ChannelClassification:
    """Channel tier/layer/role from ChatGPT analysis."""
    channel_name: str
    tier: str                    # T1, T2, T3
    layer: str                   # intelligence_military, geopolitical_intelligence, etc.
    role: str                    # primary_interview_source, counter_thesis_stress_test, etc.


@dataclass
class SignalEntry:
    """Individual video entry from ChatGPT signal layer."""
    index: int
    title: str
    channel: str
    url: str
    fgip_relevant: bool
    channel_meta: Dict[str, str]
    keyword_tags: List[str]
    guest_matches: List[str]


@dataclass
class ChatGPTSignalReport:
    """Full report from loading ChatGPT signal layer."""
    total_videos: int
    fgip_relevant: int
    relevance_pct: float
    channels_classified: int
    categories: Dict[str, int]
    top_guests: List[tuple]
    top_channels: List[tuple]
    signal_entries_loaded: int
    timestamp: str


# =============================================================================
# CATEGORY MAPPING (ChatGPT → FGIP Topics)
# =============================================================================

CATEGORY_TO_FGIP_TOPIC = {
    "intelligence_espionage": "intelligence",
    "defense_industrial": "military",
    "fentanyl_cartel": "fentanyl",
    "geopolitical": "geopolitics",
    "china_threat": "china",
    "judicial_capture": "politics",
    "trade_reshoring": "reshoring",
    "monetary_thesis": "fed",
    "correction_layer": "politics",
    "ownership_capture": "finance",
}


# =============================================================================
# MAIN LOADER
# =============================================================================

def load_chatgpt_signal(
    json_path: str,
    db_path: Optional[str] = None,
    merge_with_existing: bool = True
) -> ChatGPTSignalReport:
    """
    Load ChatGPT's youtube_signal_layer.json and optionally merge with FGIP.

    Args:
        json_path: Path to youtube_signal_layer.json
        db_path: Optional path to FGIP database for merging
        merge_with_existing: Whether to update existing youtube_signal report

    Returns:
        ChatGPTSignalReport with loading statistics
    """
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"ChatGPT signal file not found: {json_path}")

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Parse metadata
    metadata = data.get("metadata", {})
    total_videos = metadata.get("total_videos", 0)
    fgip_relevant = metadata.get("fgip_relevant", 0)
    relevance_pct = metadata.get("relevance_pct", 0.0)

    # Parse channel classifications
    channel_classifications = metadata.get("channel_classifications", {})
    channels_classified = len(channel_classifications)

    # Parse category distribution
    categories = data.get("category_distribution", {})

    # Parse guest frequency
    guest_freq = data.get("guest_frequency", {})
    top_guests = sorted(guest_freq.items(), key=lambda x: -x[1])[:20]

    # Parse channel frequency
    channel_freq = data.get("channel_frequency", {})
    top_channels = sorted(channel_freq.items(), key=lambda x: -x[1])[:20]

    # Parse signal entries
    signal_entries = data.get("signal_entries", [])
    entries_loaded = len(signal_entries)

    print(f"Loaded ChatGPT signal layer:")
    print(f"  Total videos: {total_videos}")
    print(f"  FGIP-relevant: {fgip_relevant} ({relevance_pct}%)")
    print(f"  Channels classified: {channels_classified}")
    print(f"  Categories: {len(categories)}")
    print(f"  Signal entries: {entries_loaded}")

    # Store parsed data for later access
    _LOADED_DATA["metadata"] = metadata
    _LOADED_DATA["channel_classifications"] = channel_classifications
    _LOADED_DATA["categories"] = categories
    _LOADED_DATA["guest_frequency"] = guest_freq
    _LOADED_DATA["channel_frequency"] = channel_freq
    _LOADED_DATA["signal_entries"] = signal_entries

    # Merge with FGIP database if requested
    if db_path and merge_with_existing:
        merge_with_fgip(db_path, data)

    return ChatGPTSignalReport(
        total_videos=total_videos,
        fgip_relevant=fgip_relevant,
        relevance_pct=relevance_pct,
        channels_classified=channels_classified,
        categories=categories,
        top_guests=top_guests,
        top_channels=top_channels,
        signal_entries_loaded=entries_loaded,
        timestamp=datetime.utcnow().isoformat() + "Z"
    )


# Module-level storage for loaded data
_LOADED_DATA: Dict[str, Any] = {}


def get_channel_classification(channel_name: str) -> Optional[ChannelClassification]:
    """Get ChatGPT classification for a channel."""
    classifications = _LOADED_DATA.get("channel_classifications", {})
    if channel_name in classifications:
        c = classifications[channel_name]
        return ChannelClassification(
            channel_name=channel_name,
            tier=c.get("tier", "T3"),
            layer=c.get("layer", "unknown"),
            role=c.get("role", "unknown")
        )
    return None


def get_guest_weight(guest_name: str) -> int:
    """Get frequency weight for a guest from ChatGPT analysis."""
    guest_freq = _LOADED_DATA.get("guest_frequency", {})
    return guest_freq.get(guest_name, 0)


def get_category_distribution() -> Dict[str, int]:
    """Get category distribution from ChatGPT analysis."""
    return _LOADED_DATA.get("categories", {})


def get_signal_entries_for_guest(guest_name: str) -> List[SignalEntry]:
    """Find all signal entries mentioning a specific guest."""
    entries = _LOADED_DATA.get("signal_entries", [])
    matching = []

    guest_lower = guest_name.lower()
    for entry in entries:
        # Check guest_matches field
        if any(guest_lower in g.lower() for g in entry.get("guest_matches", [])):
            matching.append(SignalEntry(
                index=entry.get("index", 0),
                title=entry.get("title", ""),
                channel=entry.get("channel", ""),
                url=entry.get("url", ""),
                fgip_relevant=entry.get("fgip_relevant", False),
                channel_meta=entry.get("channel_meta", {}),
                keyword_tags=entry.get("keyword_tags", []),
                guest_matches=entry.get("guest_matches", [])
            ))

    return matching


def get_signal_entries_for_channel(channel_name: str) -> List[SignalEntry]:
    """Find all signal entries from a specific channel."""
    entries = _LOADED_DATA.get("signal_entries", [])
    matching = []

    channel_lower = channel_name.lower()
    for entry in entries:
        if channel_lower in entry.get("channel", "").lower():
            matching.append(SignalEntry(
                index=entry.get("index", 0),
                title=entry.get("title", ""),
                channel=entry.get("channel", ""),
                url=entry.get("url", ""),
                fgip_relevant=entry.get("fgip_relevant", False),
                channel_meta=entry.get("channel_meta", {}),
                keyword_tags=entry.get("keyword_tags", []),
                guest_matches=entry.get("guest_matches", [])
            ))

    return matching


# =============================================================================
# FGIP MERGE
# =============================================================================

def merge_with_fgip(db_path: str, chatgpt_data: dict) -> dict:
    """
    Merge ChatGPT signal data with FGIP graph.

    Creates provenance links between YouTube videos and FGIP nodes
    based on guest matches and keyword tags.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Load existing nodes for matching
    cursor.execute("SELECT node_id, name, node_type FROM nodes")
    nodes = {row["name"].lower(): row["node_id"] for row in cursor.fetchall()}

    # Also index by node_id
    cursor.execute("SELECT node_id, name FROM nodes")
    for row in cursor.fetchall():
        nodes[row["node_id"]] = row["node_id"]

    merged_count = 0
    guest_matches = 0
    channel_matches = 0

    # Match guests to nodes
    guest_freq = chatgpt_data.get("guest_frequency", {})
    for guest_name, count in guest_freq.items():
        guest_lower = guest_name.lower()
        normalized = guest_lower.replace(" ", "-")

        # Try exact match
        node_id = nodes.get(guest_lower) or nodes.get(normalized)

        if node_id:
            guest_matches += 1
            print(f"  Guest match: {guest_name} -> {node_id} ({count} videos)")

    # Match channels to media outlet nodes
    channel_freq = chatgpt_data.get("channel_frequency", {})
    for channel_name, count in list(channel_freq.items())[:50]:
        channel_lower = channel_name.lower()
        normalized = channel_lower.replace(" ", "-")

        node_id = nodes.get(channel_lower) or nodes.get(normalized)
        if node_id:
            channel_matches += 1
            print(f"  Channel match: {channel_name} -> {node_id} ({count} videos)")

    conn.close()

    print(f"\nMerge summary:")
    print(f"  Guest matches to FGIP nodes: {guest_matches}")
    print(f"  Channel matches to FGIP nodes: {channel_matches}")

    return {
        "guest_matches": guest_matches,
        "channel_matches": channel_matches,
        "total_merged": guest_matches + channel_matches
    }


# =============================================================================
# EXPORT MERGED REPORT
# =============================================================================

def export_merged_report(output_path: str) -> None:
    """Export merged signal layer report combining my youtube_signal + ChatGPT."""
    if not _LOADED_DATA:
        raise RuntimeError("No ChatGPT data loaded. Call load_chatgpt_signal first.")

    report = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "source": "chatgpt_youtube_signal_layer",
        "total_videos": _LOADED_DATA["metadata"].get("total_videos", 0),
        "fgip_relevant": _LOADED_DATA["metadata"].get("fgip_relevant", 0),
        "relevance_pct": _LOADED_DATA["metadata"].get("relevance_pct", 0),
        "category_distribution": _LOADED_DATA.get("categories", {}),
        "top_guests": sorted(
            _LOADED_DATA.get("guest_frequency", {}).items(),
            key=lambda x: -x[1]
        )[:30],
        "top_channels": sorted(
            _LOADED_DATA.get("channel_frequency", {}).items(),
            key=lambda x: -x[1]
        )[:30],
        "channel_classifications": _LOADED_DATA.get("channel_classifications", {}),
    }

    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)

    print(f"Merged report exported to: {output_path}")


# =============================================================================
# CLI
# =============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Load ChatGPT YouTube signal layer")
    parser.add_argument("json_path", help="Path to youtube_signal_layer.json")
    parser.add_argument("--db", "-d", help="FGIP database path for merging")
    parser.add_argument("--output", "-o", help="Output path for merged report")
    args = parser.parse_args()

    report = load_chatgpt_signal(
        args.json_path,
        db_path=args.db,
        merge_with_existing=bool(args.db)
    )

    print(f"\n{'='*60}")
    print("CHATGPT SIGNAL LAYER LOADED")
    print("="*60)
    print(f"Videos: {report.total_videos}")
    print(f"FGIP-relevant: {report.fgip_relevant} ({report.relevance_pct}%)")
    print(f"Channels classified: {report.channels_classified}")

    print(f"\nCategory distribution:")
    for cat, count in sorted(report.categories.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")

    print(f"\nTop guests:")
    for guest, count in report.top_guests[:10]:
        print(f"  {guest}: {count}")

    print(f"\nTop channels:")
    for channel, count in report.top_channels[:10]:
        print(f"  {channel}: {count}")

    if args.output:
        export_merged_report(args.output)


if __name__ == "__main__":
    main()
