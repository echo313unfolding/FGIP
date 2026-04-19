#!/usr/bin/env python3
"""FGIP Wiki Index Generator — Creates human-readable wiki pages from the graph.

Generates:
  wiki/index.md     — Entity catalog by type with relationship counts
  wiki/log.md       — Append-only chronological change log
  wiki/entities/    — Per-entity pages with relationships and claims
  wiki/topics/      — Per-topic claim summaries

Adapted from Karpathy's LLM Wiki pattern for FGIP's graph structure.

Usage:
  python3 tools/wiki_index.py                # Generate all
  python3 tools/wiki_index.py --index-only   # Just index.md
  python3 tools/wiki_index.py --output wiki/ # Custom output dir
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fgip.db import FGIPDatabase


def generate_index(db: FGIPDatabase) -> str:
    """Generate wiki/index.md — catalog of all entities by type."""
    conn = db.connect()
    stats = db.get_stats()

    lines = [
        "# FGIP Knowledge Graph — Index",
        "",
        f"*Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC*",
        "",
        f"**{stats['nodes']} nodes** | **{stats['edges']} edges** | "
        f"**{stats['claims']} claims** | **{stats['sources']} sources** | "
        f"**{stats['evidence_coverage']:.0%} evidence coverage**",
        "",
        "---",
        "",
    ]

    # Group nodes by type with edge counts
    for node_type in sorted(stats.get("node_types", {}).keys()):
        count = stats["node_types"][node_type]
        lines.append(f"## {node_type} ({count})")
        lines.append("")

        rows = conn.execute(
            """SELECT n.node_id, n.name, n.description,
                      COUNT(DISTINCT e_from.edge_id) + COUNT(DISTINCT e_to.edge_id) as edge_count
               FROM nodes n
               LEFT JOIN edges e_from ON n.node_id = e_from.from_node_id
               LEFT JOIN edges e_to ON n.node_id = e_to.to_node_id
               WHERE n.node_type = ?
               GROUP BY n.node_id
               ORDER BY edge_count DESC, n.name
               LIMIT 50""",
            (node_type,)
        ).fetchall()

        for r in rows:
            desc = f" — {r[2][:80]}" if r[2] else ""
            edges = f" ({r[3]} edges)" if r[3] else " (orphan)"
            lines.append(f"- **{r[1]}**{edges}{desc}")

        lines.append("")

    # Claim status summary
    lines.append("## Claims by Status")
    lines.append("")
    for status, count in sorted(stats.get("claim_statuses", {}).items()):
        lines.append(f"- **{status}**: {count}")
    lines.append("")

    # Source tier summary
    lines.append("## Sources by Tier")
    lines.append("")
    tier_names = {0: "Primary (gov/court)", 1: "Journalism", 2: "Commentary"}
    for tier_key, count in sorted(stats.get("source_tiers", {}).items()):
        tier_num = int(tier_key.split("_")[1])
        name = tier_names.get(tier_num, f"Tier {tier_num}")
        lines.append(f"- **Tier {tier_num}** ({name}): {count}")
    lines.append("")

    return "\n".join(lines)


def generate_entity_page(db: FGIPDatabase, node_id: str) -> str:
    """Generate a wiki page for a single entity."""
    node = db.get_node(node_id)
    if not node:
        return f"# Entity not found: {node_id}\n"

    conn = db.connect()
    lines = [
        f"# {node.name}",
        "",
        f"**Type:** {node.node_type.value}",
    ]
    if node.description:
        lines.append(f"**Description:** {node.description}")
    if node.aliases:
        lines.append(f"**Aliases:** {', '.join(node.aliases)}")
    lines.extend(["", "---", ""])

    # Outgoing relationships
    out_rows = conn.execute(
        """SELECT e.edge_type, e.assertion_level, e.confidence, e.notes,
                  n.name, n.node_type, e.claim_id
           FROM edges e
           JOIN nodes n ON e.to_node_id = n.node_id
           WHERE e.from_node_id = ?
           ORDER BY e.edge_type, n.name""",
        (node_id,)
    ).fetchall()

    if out_rows:
        lines.append("## Relationships (outgoing)")
        lines.append("")
        current_type = None
        for r in out_rows:
            if r[0] != current_type:
                current_type = r[0]
                lines.append(f"### {current_type}")
            assertion = f" [{r[1]}]" if r[1] != "FACT" else ""
            claim = f" (claim: {r[6]})" if r[6] else ""
            confidence = f" conf={r[2]:.0%}" if r[2] < 1.0 else ""
            lines.append(f"- → **{r[4]}** ({r[5]}){assertion}{confidence}{claim}")
        lines.append("")

    # Incoming relationships
    in_rows = conn.execute(
        """SELECT e.edge_type, e.assertion_level, e.confidence, e.notes,
                  n.name, n.node_type, e.claim_id
           FROM edges e
           JOIN nodes n ON e.from_node_id = n.node_id
           WHERE e.to_node_id = ?
           ORDER BY e.edge_type, n.name""",
        (node_id,)
    ).fetchall()

    if in_rows:
        lines.append("## Relationships (incoming)")
        lines.append("")
        current_type = None
        for r in in_rows:
            if r[0] != current_type:
                current_type = r[0]
                lines.append(f"### {current_type}")
            assertion = f" [{r[1]}]" if r[1] != "FACT" else ""
            confidence = f" conf={r[2]:.0%}" if r[2] < 1.0 else ""
            lines.append(f"- ← **{r[4]}** ({r[5]}){assertion}{confidence}")
        lines.append("")

    # Related claims
    claim_rows = conn.execute(
        """SELECT DISTINCT c.claim_id, c.claim_text, c.status, c.topic
           FROM claims c
           JOIN edges e ON e.claim_id = c.claim_id
           WHERE e.from_node_id = ? OR e.to_node_id = ?
           ORDER BY c.claim_id""",
        (node_id, node_id)
    ).fetchall()

    if claim_rows:
        lines.append("## Related Claims")
        lines.append("")
        for r in claim_rows:
            lines.append(f"- **{r[0]}** [{r[2]}] {r[1][:100]}")
        lines.append("")

    lines.append(f"*Node ID: {node_id} | Created: {node.created_at}*")
    return "\n".join(lines)


def generate_topic_page(db: FGIPDatabase, topic: str) -> str:
    """Generate a wiki page for a claim topic."""
    conn = db.connect()

    rows = conn.execute(
        """SELECT claim_id, claim_text, status, created_at, notes
           FROM claims
           WHERE topic = ?
           ORDER BY claim_id""",
        (topic,)
    ).fetchall()

    lines = [
        f"# Topic: {topic}",
        "",
        f"**{len(rows)} claims**",
        "",
        "---",
        "",
    ]

    for r in rows:
        status_icon = {"VERIFIED": "V", "EVIDENCED": "E",
                       "PARTIAL": "P", "MISSING": "?"}
        icon = status_icon.get(r[2], "?")
        lines.append(f"- [{icon}] **{r[0]}**: {r[1][:120]}")
        if r[4]:
            lines.append(f"  - *{r[4][:100]}*")

    lines.append("")
    return "\n".join(lines)


def generate_log_entry(stats: dict) -> str:
    """Generate a single log entry for the current state."""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    return (
        f"## [{now}] wiki_index | Generated\n"
        f"- Nodes: {stats['nodes']}, Edges: {stats['edges']}, "
        f"Claims: {stats['claims']}, Sources: {stats['sources']}\n"
        f"- Evidence coverage: {stats['evidence_coverage']:.0%}\n"
    )


def main():
    parser = argparse.ArgumentParser(description="FGIP Wiki Index Generator")
    parser.add_argument("--db", default="fgip.db", help="Database path")
    parser.add_argument("--output", default="wiki", help="Output directory")
    parser.add_argument("--index-only", action="store_true")
    parser.add_argument("--entities", action="store_true",
                        help="Generate entity pages (can be slow for large graphs)")
    parser.add_argument("--topics", action="store_true",
                        help="Generate topic pages")
    args = parser.parse_args()

    db = FGIPDatabase(args.db)
    db.connect()

    out = Path(args.output)
    out.mkdir(exist_ok=True)

    # Always generate index
    index_md = generate_index(db)
    (out / "index.md").write_text(index_md)
    print(f"  wrote {out}/index.md")

    if args.index_only:
        db.close()
        return

    # Append to log
    stats = db.get_stats()
    log_path = out / "log.md"
    log_entry = generate_log_entry(stats)
    if log_path.exists():
        existing = log_path.read_text()
        log_path.write_text(log_entry + "\n" + existing)
    else:
        log_path.write_text(f"# FGIP Wiki Log\n\n{log_entry}")
    print(f"  wrote {out}/log.md")

    # Entity pages (opt-in — can be large)
    if args.entities:
        ent_dir = out / "entities"
        ent_dir.mkdir(exist_ok=True)
        conn = db.connect()
        rows = conn.execute("SELECT node_id FROM nodes").fetchall()
        for r in rows:
            page = generate_entity_page(db, r[0])
            safe_id = r[0].replace("/", "_").replace(" ", "_")
            (ent_dir / f"{safe_id}.md").write_text(page)
        print(f"  wrote {len(rows)} entity pages to {ent_dir}/")

    # Topic pages (opt-in)
    if args.topics:
        topic_dir = out / "topics"
        topic_dir.mkdir(exist_ok=True)
        conn = db.connect()
        rows = conn.execute(
            "SELECT DISTINCT topic FROM claims ORDER BY topic"
        ).fetchall()
        for r in rows:
            page = generate_topic_page(db, r[0])
            safe_topic = r[0].replace("/", "_").replace(" ", "_")
            (topic_dir / f"{safe_topic}.md").write_text(page)
        print(f"  wrote {len(rows)} topic pages to {topic_dir}/")

    db.close()
    print(f"\n  Wiki generated at {out}/")


if __name__ == "__main__":
    main()
