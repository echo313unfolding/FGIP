#!/usr/bin/env python3
"""FGIP Proposal Promoter - Batch promote high-confidence proposals to production graph.

Usage:
    python3 tools/promote_proposals.py fgip.db --type DEPENDS_ON --min-confidence 0.8
    python3 tools/promote_proposals.py fgip.db --supply-chain --min-confidence 0.7
    python3 tools/promote_proposals.py fgip.db --dry-run
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fgip.db import FGIPDatabase


def promote_edges(db, edge_types: list, min_confidence: float = 0.7, dry_run: bool = False) -> dict:
    """Promote pending edge proposals to production graph.

    Args:
        db: FGIPDatabase instance
        edge_types: List of edge types to promote
        min_confidence: Minimum confidence threshold
        dry_run: If True, don't actually promote

    Returns:
        Dict with promotion statistics
    """
    conn = db.connect()

    # Find qualifying proposals
    placeholders = ','.join('?' * len(edge_types))
    proposals = conn.execute(f"""
        SELECT proposal_id, from_node, to_node, relationship, detail,
               confidence, reasoning, agent_name, created_at
        FROM proposed_edges
        WHERE relationship IN ({placeholders})
        AND status = 'PENDING'
        AND confidence >= ?
        ORDER BY confidence DESC
    """, (*edge_types, min_confidence)).fetchall()

    stats = {
        'edge_types': edge_types,
        'min_confidence': min_confidence,
        'dry_run': dry_run,
        'found': len(proposals),
        'promoted': 0,
        'skipped': 0,
        'errors': [],
    }

    if dry_run:
        print(f"\n[DRY RUN] Would promote {len(proposals)} edges")
        for p in proposals[:10]:
            print(f"  {p[1]} --{p[3]}--> {p[2]} (conf={p[5]:.2f})")
        if len(proposals) > 10:
            print(f"  ... and {len(proposals) - 10} more")
        return stats

    # Promote each proposal
    for p in proposals:
        proposal_id, from_node, to_node, relationship, detail, confidence, reasoning, agent_name, created_at = p

        try:
            # Check if edge already exists
            existing = conn.execute("""
                SELECT edge_id FROM edges
                WHERE from_node_id = ? AND to_node_id = ? AND edge_type = ?
            """, (from_node, to_node, relationship)).fetchone()

            if existing:
                # Update status to SKIPPED
                conn.execute("""
                    UPDATE proposed_edges SET status = 'SKIPPED'
                    WHERE proposal_id = ?
                """, (proposal_id,))
                stats['skipped'] += 1
                continue

            # Ensure nodes exist (create if needed)
            for node_id in [from_node, to_node]:
                existing_node = conn.execute(
                    "SELECT node_id FROM nodes WHERE node_id = ?", (node_id,)
                ).fetchone()
                if not existing_node:
                    # Create placeholder node
                    node_name = node_id.replace('-', ' ').title()
                    created_at = datetime.now(timezone.utc).isoformat()
                    sha256 = hashlib.sha256(f"{node_id}:{node_name}:{created_at}".encode()).hexdigest()
                    conn.execute("""
                        INSERT INTO nodes (node_id, node_type, name, created_at, sha256)
                        VALUES (?, 'ORGANIZATION', ?, ?, ?)
                    """, (node_id, node_name, created_at, sha256))

            # Insert edge into production
            created_at = datetime.now(timezone.utc).isoformat()
            edge_id = f"{from_node}_{relationship}_{to_node}"[:100]
            edge_sha256 = hashlib.sha256(f"{edge_id}:{created_at}".encode()).hexdigest()

            edge_metadata = json.dumps({
                'proposal_id': proposal_id,
                'agent_name': agent_name,
                'promoted_at': created_at,
            })

            conn.execute("""
                INSERT INTO edges (edge_id, from_node_id, to_node_id, edge_type, notes,
                                   confidence, assertion_level, metadata, created_at, sha256)
                VALUES (?, ?, ?, ?, ?, ?, 'INFERENCE', ?, ?, ?)
            """, (edge_id, from_node, to_node, relationship, detail, confidence,
                  edge_metadata, created_at, edge_sha256))

            # Update proposal status
            conn.execute("""
                UPDATE proposed_edges SET status = 'APPLIED'
                WHERE proposal_id = ?
            """, (proposal_id,))

            stats['promoted'] += 1

        except Exception as e:
            stats['errors'].append(f"{proposal_id}: {str(e)}")

    conn.commit()
    return stats


def main():
    parser = argparse.ArgumentParser(description="FGIP Proposal Promoter")
    parser.add_argument("db", type=str, help="Database path")
    parser.add_argument("--type", type=str, action="append", dest="types",
                       help="Edge type to promote (can specify multiple)")
    parser.add_argument("--supply-chain", action="store_true",
                       help="Promote supply chain edges (DEPENDS_ON, SUPPLIES_TO, CUSTOMER_OF)")
    parser.add_argument("--min-confidence", type=float, default=0.7,
                       help="Minimum confidence threshold (default: 0.7)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be promoted without doing it")

    args = parser.parse_args()

    # Determine edge types
    edge_types = []
    if args.supply_chain:
        edge_types.extend(['DEPENDS_ON', 'SUPPLIES_TO', 'CUSTOMER_OF', 'BOTTLENECK_AT'])
    if args.types:
        edge_types.extend(args.types)

    if not edge_types:
        print("Error: Specify --type or --supply-chain")
        parser.print_help()
        return

    # Connect to database
    db = FGIPDatabase(args.db)
    db.connect()

    # Run promotion
    print(f"Promoting edges: {', '.join(edge_types)}")
    print(f"Min confidence: {args.min_confidence}")

    stats = promote_edges(db, edge_types, args.min_confidence, args.dry_run)

    # Summary
    print()
    print("=" * 50)
    print(f"  Found: {stats['found']}")
    print(f"  Promoted: {stats['promoted']}")
    print(f"  Skipped (already exists): {stats['skipped']}")
    if stats['errors']:
        print(f"  Errors: {len(stats['errors'])}")
        for e in stats['errors'][:5]:
            print(f"    {e}")
    print("=" * 50)


if __name__ == "__main__":
    main()
