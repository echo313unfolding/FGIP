#!/usr/bin/env python3
"""Clean up garbage edges created by EDGAR agent before content filter.

Run with --dry-run (default) to preview, or --execute to actually delete.

Examples:
    python3 scripts/cleanup_garbage_edges.py              # Dry run
    python3 scripts/cleanup_garbage_edges.py --execute    # Actually delete
"""

import sqlite3
import re
import sys
from pathlib import Path

# Patterns that indicate garbage edges from 10-K boilerplate parsing
GARBAGE_PATTERNS = [
    r'^among-other-things$',
    r'^prevent$',
    r'^other-financial-institutions$',
    r'^financial-institutions$',
    r'^third-part(y|ies)$',
    r'^related-parties$',
    r'^other-companies$',
    r'^other-entities$',
    r'^government-agencies$',
    r'^regulatory-authorities$',
    r'^market-conditions$',
    r'^economic-conditions$',
    r'^business-operations$',
    r'^other-things$',
    r'^such-as$',
    r'^as-well-as$',
    r'^including$',
    r'^various$',
    r'^certain$',
    r'^several$',
    r'^others$',
    r'^etc$',
    r'^among$',
    r'-conditions$',
    r'-operations$',
    r'^other-[a-z-]+$',  # any "other-X" pattern
]


def is_garbage_node_id(node_id: str) -> bool:
    """Check if a node_id matches garbage patterns."""
    if not node_id:
        return False
    for pattern in GARBAGE_PATTERNS:
        if re.search(pattern, node_id):
            return True
    return False


def cleanup_garbage_edges(db_path: str, dry_run: bool = True) -> dict:
    """Find and optionally delete garbage edges.

    Returns dict with stats about what was found/deleted.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Find garbage edges
    cursor = conn.execute("""
        SELECT edge_id, from_node_id, to_node_id, edge_type, confidence
        FROM edges
    """)

    to_delete = []
    for row in cursor:
        edge_id = row["edge_id"]
        from_node = row["from_node_id"]
        to_node = row["to_node_id"]

        if is_garbage_node_id(to_node) or is_garbage_node_id(from_node):
            to_delete.append({
                "edge_id": edge_id,
                "from_node": from_node,
                "to_node": to_node,
                "edge_type": row["edge_type"],
            })

    stats = {
        "garbage_edges_found": len(to_delete),
        "dry_run": dry_run,
        "deleted": 0,
    }

    print(f"\n{'='*60}")
    print("FGIP Garbage Edge Cleanup")
    print(f"{'='*60}")
    print(f"Database: {db_path}")
    print(f"Mode: {'DRY RUN (preview only)' if dry_run else 'EXECUTE (will delete)'}")
    print(f"\nFound {len(to_delete)} garbage edges")

    if to_delete:
        print("\nSample garbage edges:")
        for edge in to_delete[:20]:
            print(f"  {edge['from_node']} --[{edge['edge_type']}]--> {edge['to_node']}")

        if len(to_delete) > 20:
            print(f"  ... and {len(to_delete) - 20} more")

    if not dry_run and to_delete:
        print(f"\nDeleting {len(to_delete)} edges...")
        for edge in to_delete:
            conn.execute("DELETE FROM edges WHERE edge_id = ?", (edge["edge_id"],))
        conn.commit()
        stats["deleted"] = len(to_delete)
        print(f"Deleted {len(to_delete)} garbage edges")

    # Show remaining edge count
    remaining = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    print(f"\nEdges remaining in database: {remaining}")

    conn.close()

    if dry_run and to_delete:
        print(f"\nTo actually delete these edges, run:")
        print(f"  python3 {sys.argv[0]} --execute")

    return stats


def main():
    db_path = Path(__file__).parent.parent / "fgip.db"

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)

    dry_run = "--execute" not in sys.argv

    stats = cleanup_garbage_edges(str(db_path), dry_run=dry_run)

    print(f"\n{'='*60}")
    print("Summary:")
    print(f"  Garbage edges found: {stats['garbage_edges_found']}")
    print(f"  Edges deleted: {stats['deleted']}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
