#!/usr/bin/env python3
"""Backfill Square-One claims for legacy unsourced edges.

Creates claims from edge metadata (type, nodes, source text, notes) and
links them to edges that were created before Square-One compliance was enforced.

Three modes:
  --dry-run     Show what would be created (default)
  --source-text Backfill only edges that have source text (143 edges)
  --bulk        Backfill all unsourced edges grouped by type+source pattern

Usage:
  python3 tools/backfill_claims.py --dry-run          # Preview
  python3 tools/backfill_claims.py --source-text      # Safe: only edges with source text
  python3 tools/backfill_claims.py --bulk              # All unsourced edges
  python3 tools/backfill_claims.py --bulk --type VOTED_FOR  # Single edge type
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fgip.db import FGIPDatabase
from fgip.schema import Claim, ClaimStatus, Source, compute_sha256


# Map edge types to claim topics and source descriptions
EDGE_TYPE_METADATA = {
    "VOTED_FOR": {"topic": "congressional_voting", "source_desc": "Congress.gov voting records", "tier": 0},
    "VOTED_AGAINST": {"topic": "congressional_voting", "source_desc": "Congress.gov voting records", "tier": 0},
    "DONATED_TO": {"topic": "campaign_finance", "source_desc": "FEC/OpenSecrets campaign finance records", "tier": 0},
    "SUPPLIES_TO": {"topic": "supply_chain", "source_desc": "SEC 10-K filing", "tier": 0},
    "CUSTOMER_OF": {"topic": "supply_chain", "source_desc": "SEC 10-K filing", "tier": 0},
    "DEPENDS_ON": {"topic": "supply_chain", "source_desc": "Supply chain analysis", "tier": 1},
    "IMPLEMENTED_BY": {"topic": "policy_implementation", "source_desc": "Federal Register / agency action", "tier": 0},
    "COMPETES_WITH": {"topic": "market_structure", "source_desc": "SEC 10-K Risk Factors", "tier": 0},
    "RULEMAKING_FOR": {"topic": "policy_implementation", "source_desc": "Federal Register rulemaking", "tier": 0},
    "AWARDED_GRANT": {"topic": "government_funding", "source_desc": "USAspending.gov / agency announcement", "tier": 0},
    "ACQUIRED": {"topic": "corporate_actions", "source_desc": "SEC 8-K/10-K filing", "tier": 0},
    "OPENED_FACILITY": {"topic": "industrial_base", "source_desc": "SEC 8-K Properties / press release", "tier": 1},
    "BUILT_IN": {"topic": "industrial_base", "source_desc": "Facility records", "tier": 1},
    "LOBBIED_FOR": {"topic": "lobbying", "source_desc": "FARA/LDA registration", "tier": 0},
    "LOBBIED_AGAINST": {"topic": "lobbying", "source_desc": "FARA/LDA registration", "tier": 0},
    "REPORTS_ON": {"topic": "media_coverage", "source_desc": "Publication record", "tier": 1},
    "CAPACITY_AT": {"topic": "industrial_base", "source_desc": "Facility capacity data", "tier": 1},
    "REGISTERED_AS_AGENT": {"topic": "lobbying", "source_desc": "FARA Registration Act filing", "tier": 0},
    "FUNDED_PROJECT": {"topic": "government_funding", "source_desc": "Project funding records", "tier": 0},
}

DEFAULT_META = {"topic": "general", "source_desc": "Graph ingestion (pre-Square-One)", "tier": 2}


def backfill_with_source_text(db: FGIPDatabase, dry_run: bool = True) -> dict:
    """Backfill edges that have source text but no claim_id."""
    conn = db.connect()
    rows = conn.execute(
        """SELECT edge_id, edge_type, from_node_id, to_node_id, source, notes
           FROM edges
           WHERE claim_id IS NULL
             AND source IS NOT NULL AND source != ''
           ORDER BY edge_type"""
    ).fetchall()

    created = 0
    skipped = 0

    for r in rows:
        edge_id, edge_type, from_id, to_id, source, notes = r

        # Build claim text from edge metadata
        claim_text = f"{from_id} {edge_type.lower().replace('_', ' ')} {to_id}"
        if notes:
            claim_text = notes[:200]

        meta = EDGE_TYPE_METADATA.get(edge_type, DEFAULT_META)

        if dry_run:
            print(f"  [DRY] {edge_id}: claim from source=\"{source[:50]}\" topic={meta['topic']}")
            created += 1
            continue

        # Create claim
        claim_id = db.get_next_claim_id()
        claim = Claim(
            claim_id=claim_id,
            claim_text=claim_text,
            topic=meta["topic"],
            status=ClaimStatus.PARTIAL,
            required_tier=meta["tier"],
            notes=f"Backfilled from edge {edge_id}. Original source: {source}",
        )
        db.insert_claim(claim)

        # Link edge to claim
        db.update_edge_claim(edge_id, claim_id)
        created += 1

    conn.commit()
    return {"created": created, "skipped": skipped, "mode": "source_text", "dry_run": dry_run}


def backfill_bulk(db: FGIPDatabase, edge_type_filter: str = None,
                  dry_run: bool = True) -> dict:
    """Backfill all unsourced edges, creating claims by type."""
    conn = db.connect()

    query = """SELECT edge_id, edge_type, from_node_id, to_node_id, notes
               FROM edges
               WHERE claim_id IS NULL
                 AND (source IS NULL OR source = '')"""
    params = []

    if edge_type_filter:
        query += " AND edge_type = ?"
        params.append(edge_type_filter)

    query += " ORDER BY edge_type, from_node_id"
    rows = conn.execute(query, params).fetchall()

    created = 0
    by_type = {}

    for r in rows:
        edge_id, edge_type, from_id, to_id, notes = r

        # Get node names for readable claim text
        try:
            from_node = db.get_node(from_id)
        except (ValueError, Exception):
            from_node = None
        try:
            to_node = db.get_node(to_id)
        except (ValueError, Exception):
            to_node = None
        from_name = from_node.name if from_node else from_id
        to_name = to_node.name if to_node else to_id

        # Build claim text
        verb = edge_type.lower().replace("_", " ")
        claim_text = f"{from_name} {verb} {to_name}"
        if notes:
            claim_text += f". {notes[:100]}"

        meta = EDGE_TYPE_METADATA.get(edge_type, DEFAULT_META)
        by_type[edge_type] = by_type.get(edge_type, 0) + 1

        if dry_run:
            if by_type[edge_type] <= 3:  # Show first 3 per type
                print(f"  [DRY] {edge_type}: \"{claim_text[:80]}\" topic={meta['topic']}")
            elif by_type[edge_type] == 4:
                print(f"  [DRY] {edge_type}: ... and more")
            created += 1
            continue

        claim_id = db.get_next_claim_id()
        claim = Claim(
            claim_id=claim_id,
            claim_text=claim_text,
            topic=meta["topic"],
            status=ClaimStatus.PARTIAL,
            required_tier=meta["tier"],
            notes=f"Backfilled from edge {edge_id} (pre-Square-One legacy)",
        )
        db.insert_claim(claim)
        db.update_edge_claim(edge_id, claim_id)
        created += 1

    conn.commit()
    return {"created": created, "by_type": by_type, "mode": "bulk", "dry_run": dry_run}


def main():
    parser = argparse.ArgumentParser(description="Backfill Square-One claims for legacy edges")
    parser.add_argument("--db", default="fgip.db", help="Database path")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Preview only (default)")
    parser.add_argument("--source-text", action="store_true",
                        help="Backfill only edges with existing source text")
    parser.add_argument("--bulk", action="store_true",
                        help="Backfill all unsourced edges")
    parser.add_argument("--type", help="Filter to single edge type (with --bulk)")
    parser.add_argument("--execute", action="store_true",
                        help="Actually write to database (removes dry-run safety)")
    args = parser.parse_args()

    db = FGIPDatabase(args.db)
    db.connect()

    dry_run = not args.execute

    if args.source_text:
        result = backfill_with_source_text(db, dry_run=dry_run)
    elif args.bulk:
        result = backfill_bulk(db, edge_type_filter=args.type, dry_run=dry_run)
    else:
        # Default: show summary
        conn = db.connect()
        total = conn.execute(
            "SELECT COUNT(*) FROM edges WHERE claim_id IS NULL AND (source IS NULL OR source = '')"
        ).fetchone()[0]
        with_source = conn.execute(
            "SELECT COUNT(*) FROM edges WHERE claim_id IS NULL AND source IS NOT NULL AND source != ''"
        ).fetchone()[0]
        print(f"Unsourced edges: {total} (no claim, no source)")
        print(f"Edges with source text: {with_source} (can auto-claim)")
        print(f"\nRun with --source-text --execute to backfill {with_source} edges")
        print(f"Run with --bulk --execute to backfill all {total + with_source} edges")
        print(f"Run with --bulk --type VOTED_FOR --execute to backfill one type")
        db.close()
        return

    if dry_run:
        print(f"\n[DRY RUN] Would create {result['created']} claims")
        print(f"Run with --execute to apply")
    else:
        print(f"\nCreated {result['created']} claims")
        if "by_type" in result:
            print("By type:")
            for t, c in sorted(result["by_type"].items(), key=lambda x: -x[1]):
                print(f"  {t:30s} {c:>5d}")

    db.close()


if __name__ == "__main__":
    main()
