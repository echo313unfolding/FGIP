#!/usr/bin/env python3
"""Build point-in-time evidence snapshots for walk-forward simulation.

For a given decision date, returns only sources/facts/edges whose
published_at <= decision_date. No future data leaks.

Usage:
    from build_point_in_time_snapshot import build_snapshot
    snapshot = build_snapshot("2025-07-01")
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
SOURCES_DIR = DATA_DIR / "sources"
FACTS_DIR = DATA_DIR / "extracted"
EDGES_DIR = DATA_DIR / "edges"


@dataclass
class PointInTimeSnapshot:
    """Evidence visible at a specific date."""
    as_of_date: str
    sources: list[dict] = field(default_factory=list)
    facts: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)

    @property
    def source_ids(self) -> list[str]:
        return [s["source_id"] for s in self.sources]

    @property
    def fact_ids(self) -> list[str]:
        return [f["fact_id"] for f in self.facts]

    @property
    def edge_ids(self) -> list[str]:
        return [e["edge_id"] for e in self.edges]

    @property
    def tier_0_count(self) -> int:
        return sum(1 for s in self.sources if s.get("tier", 99) == 0)

    @property
    def tier_1_count(self) -> int:
        return sum(1 for s in self.sources if s.get("tier", 99) == 1)

    @property
    def source_types(self) -> set[str]:
        return {s.get("source_type", "unknown") for s in self.sources}

    @property
    def triangulation_met(self) -> bool:
        return len(self.source_types) >= 3 and self.tier_0_count >= 1

    def to_dict(self) -> dict:
        return {
            "as_of_date": self.as_of_date,
            "source_count": len(self.sources),
            "fact_count": len(self.facts),
            "edge_count": len(self.edges),
            "tier_0_count": self.tier_0_count,
            "tier_1_count": self.tier_1_count,
            "source_types": sorted(self.source_types),
            "triangulation_met": self.triangulation_met,
            "source_ids": self.source_ids,
            "fact_ids": self.fact_ids,
            "edge_ids": self.edge_ids,
        }


def _load_jsonl_files(directory: Path) -> list[dict]:
    results = []
    if not directory.exists():
        return results
    for f in sorted(directory.glob("*.jsonl")):
        with open(f) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    results.append(json.loads(line))
    return results


def _normalize_date(date_str: str) -> str:
    """Normalize date strings to YYYY-MM-DD for comparison.
    Handles: 2024-12-23, 2024-04, 2024, 2026-05-09T00:00:00Z"""
    if not date_str:
        return "9999-12-31"
    d = date_str.strip()
    if "T" in d:
        d = d.split("T")[0]
    parts = d.split("-")
    if len(parts) == 1:
        return f"{parts[0]}-12-31"  # year only -> end of year
    if len(parts) == 2:
        return f"{parts[0]}-{parts[1]}-28"  # month only -> end of month
    return d


def build_snapshot(as_of_date: str) -> PointInTimeSnapshot:
    """Build evidence snapshot visible at as_of_date (YYYY-MM-DD).

    Only includes sources with published_at <= as_of_date,
    facts linked to those sources, and edges linked to those facts.
    """
    cutoff = _normalize_date(as_of_date)
    all_sources = _load_jsonl_files(SOURCES_DIR)
    all_facts = _load_jsonl_files(FACTS_DIR)
    all_edges = _load_jsonl_files(EDGES_DIR)

    # Filter sources by publication date
    visible_sources = []
    for src in all_sources:
        pub = _normalize_date(src.get("published_at", ""))
        if pub <= cutoff:
            visible_sources.append(src)

    visible_source_ids = {s["source_id"] for s in visible_sources}

    # Filter facts by their source being visible
    visible_facts = []
    for fact in all_facts:
        if fact.get("source_id") in visible_source_ids:
            # Also check fact date if present
            fact_date = _normalize_date(fact.get("date", ""))
            if fact_date <= cutoff:
                visible_facts.append(fact)

    visible_fact_ids = {f["fact_id"] for f in visible_facts}

    # Filter edges by their fact being visible
    visible_edges = []
    for edge in all_edges:
        if edge.get("fact_id") in visible_fact_ids:
            visible_edges.append(edge)

    return PointInTimeSnapshot(
        as_of_date=as_of_date,
        sources=visible_sources,
        facts=visible_facts,
        edges=visible_edges,
    )


if __name__ == "__main__":
    import sys
    date = sys.argv[1] if len(sys.argv) > 1 else "2026-05-09"
    snap = build_snapshot(date)
    print(json.dumps(snap.to_dict(), indent=2))
