#!/usr/bin/env python3
"""FGIP Coverage Gap Filler - Add missing entities from coverage analysis.

Reads the latest coverage analysis receipt and adds missing entities
to the graph with appropriate node types and metadata.

Usage:
    python3 tools/fill_coverage_gaps.py fgip.db
    python3 tools/fill_coverage_gaps.py fgip.db --entity-set defense_primes
    python3 tools/fill_coverage_gaps.py fgip.db --min-priority 8
    python3 tools/fill_coverage_gaps.py fgip.db --dry-run
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


# Entity metadata for proper node creation
ENTITY_METADATA = {
    # Defense primes
    'lockheed-martin': {'type': 'COMPANY', 'sector': 'defense', 'ticker': 'LMT'},
    'raytheon': {'type': 'COMPANY', 'sector': 'defense', 'ticker': 'RTX'},
    'northrop-grumman': {'type': 'COMPANY', 'sector': 'defense', 'ticker': 'NOC'},
    'boeing': {'type': 'COMPANY', 'sector': 'defense', 'ticker': 'BA'},
    'general-dynamics': {'type': 'COMPANY', 'sector': 'defense', 'ticker': 'GD'},
    'l3harris': {'type': 'COMPANY', 'sector': 'defense', 'ticker': 'LHX'},
    'bae-systems': {'type': 'COMPANY', 'sector': 'defense', 'ticker': 'BA.L'},
    'huntington-ingalls': {'type': 'COMPANY', 'sector': 'defense', 'ticker': 'HII'},
    'leidos': {'type': 'COMPANY', 'sector': 'defense', 'ticker': 'LDOS'},
    'saic': {'type': 'COMPANY', 'sector': 'defense', 'ticker': 'SAIC'},

    # Semiconductor majors
    'nvidia': {'type': 'COMPANY', 'sector': 'semiconductor', 'ticker': 'NVDA'},
    'amd': {'type': 'COMPANY', 'sector': 'semiconductor', 'ticker': 'AMD'},
    'qualcomm': {'type': 'COMPANY', 'sector': 'semiconductor', 'ticker': 'QCOM'},
    'texas-instruments': {'type': 'COMPANY', 'sector': 'semiconductor', 'ticker': 'TXN'},
    'broadcom': {'type': 'COMPANY', 'sector': 'semiconductor', 'ticker': 'AVGO'},
    'asml': {'type': 'COMPANY', 'sector': 'semiconductor', 'ticker': 'ASML'},
    'sk-hynix': {'type': 'COMPANY', 'sector': 'semiconductor', 'ticker': '000660.KS'},
    'samsung-electronics': {'type': 'COMPANY', 'sector': 'semiconductor', 'ticker': '005930.KS'},
    'applied-materials': {'type': 'COMPANY', 'sector': 'semiconductor', 'ticker': 'AMAT'},
    'lam-research': {'type': 'COMPANY', 'sector': 'semiconductor', 'ticker': 'LRCX'},
    'kla-corporation': {'type': 'COMPANY', 'sector': 'semiconductor', 'ticker': 'KLAC'},
    'microchip-technology': {'type': 'COMPANY', 'sector': 'semiconductor', 'ticker': 'MCHP'},
    'onsemi': {'type': 'COMPANY', 'sector': 'semiconductor', 'ticker': 'ON'},
    'polar-semiconductor': {'type': 'COMPANY', 'sector': 'semiconductor', 'ticker': None},

    # Tech offshorers
    'meta': {'type': 'COMPANY', 'sector': 'tech', 'ticker': 'META'},
    'alphabet': {'type': 'COMPANY', 'sector': 'tech', 'ticker': 'GOOGL'},
    'tesla': {'type': 'COMPANY', 'sector': 'tech', 'ticker': 'TSLA'},
    'hp': {'type': 'COMPANY', 'sector': 'tech', 'ticker': 'HPQ'},
    'dell': {'type': 'COMPANY', 'sector': 'tech', 'ticker': 'DELL'},
    'cisco': {'type': 'COMPANY', 'sector': 'tech', 'ticker': 'CSCO'},

    # Asset managers
    'fidelity': {'type': 'COMPANY', 'sector': 'finance', 'ticker': None},
    'schwab': {'type': 'COMPANY', 'sector': 'finance', 'ticker': 'SCHW'},

    # Nuclear SMR
    'westinghouse': {'type': 'COMPANY', 'sector': 'nuclear', 'ticker': None},
    'ge-hitachi': {'type': 'COMPANY', 'sector': 'nuclear', 'ticker': None},

    # Stablecoin
    'binance': {'type': 'COMPANY', 'sector': 'crypto', 'ticker': None},
    'coinbase': {'type': 'COMPANY', 'sector': 'crypto', 'ticker': 'COIN'},
    'kraken': {'type': 'COMPANY', 'sector': 'crypto', 'ticker': None},

    # Federal agencies
    'occ': {'type': 'GOVERNMENT_AGENCY', 'sector': 'government', 'full_name': 'Office of the Comptroller of the Currency'},
    'chips-program-office': {'type': 'GOVERNMENT_AGENCY', 'sector': 'government', 'full_name': 'CHIPS Program Office'},
}


def get_latest_coverage_report():
    """Get the latest coverage analysis receipt."""
    receipts_dir = PROJECT_ROOT / "receipts" / "coverage"
    if not receipts_dir.exists():
        return None

    report_files = sorted(receipts_dir.glob("analysis_*.json"), reverse=True)
    if not report_files:
        return None

    with open(report_files[0]) as f:
        return json.load(f)


def add_entity(conn, entity_id: str, entity_set: str, dry_run: bool = False) -> bool:
    """Add a missing entity to the graph."""
    # Check if already exists
    existing = conn.execute(
        "SELECT node_id FROM nodes WHERE node_id = ?",
        (entity_id,)
    ).fetchone()

    if existing:
        return False

    # Get metadata
    meta = ENTITY_METADATA.get(entity_id, {'type': 'ORGANIZATION', 'sector': 'unknown'})
    node_type = meta.get('type', 'ORGANIZATION')
    name = meta.get('full_name', entity_id.replace('-', ' ').title())
    timestamp = datetime.now(timezone.utc).isoformat()
    sha256 = hashlib.sha256(f"{entity_id}:{name}:{timestamp}".encode()).hexdigest()

    metadata = json.dumps({
        'sector': meta.get('sector'),
        'ticker': meta.get('ticker'),
        'entity_set': entity_set,
        'added_by': 'fill_coverage_gaps',
        'added_at': timestamp,
    })

    if not dry_run:
        conn.execute("""
            INSERT INTO nodes (node_id, node_type, name, created_at, sha256, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (entity_id, node_type, name, timestamp, sha256, metadata))

    return True


def main():
    parser = argparse.ArgumentParser(description="FGIP Coverage Gap Filler")
    parser.add_argument("db", type=str, help="Database path")
    parser.add_argument("--entity-set", type=str, help="Only fill specific entity set")
    parser.add_argument("--min-priority", type=int, default=5, help="Minimum priority to fill (default: 5)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be added without doing it")
    parser.add_argument("--json", action="store_true", help="JSON output")

    args = parser.parse_args()

    # Get latest coverage report
    report = get_latest_coverage_report()
    if not report:
        print("No coverage report found. Run coverage_analyzer first.")
        sys.exit(1)

    db = FGIPDatabase(args.db)
    conn = db.connect()

    added = []
    skipped = []

    for recommendation in report.get('recommended_actions', []):
        priority = recommendation.get('priority', 0)
        entity_set = recommendation.get('action', '').split(' to ')[-1] if ' to ' in recommendation.get('action', '') else 'unknown'

        # Filter by entity set if specified
        if args.entity_set and entity_set != args.entity_set:
            continue

        # Filter by priority
        if priority < args.min_priority:
            continue

        for entity in recommendation.get('entities', []):
            if add_entity(conn, entity, entity_set, args.dry_run):
                added.append({'entity': entity, 'entity_set': entity_set, 'priority': priority})
            else:
                skipped.append({'entity': entity, 'reason': 'already exists'})

    if not args.dry_run:
        conn.commit()

    # Write receipt
    receipt = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'dry_run': args.dry_run,
        'entities_added': len(added),
        'entities_skipped': len(skipped),
        'added': added,
        'skipped': skipped,
    }

    if not args.dry_run:
        receipts_dir = PROJECT_ROOT / "receipts" / "coverage"
        receipts_dir.mkdir(parents=True, exist_ok=True)
        receipt_path = receipts_dir / f"fill_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        receipt_path.write_text(json.dumps(receipt, indent=2))

    if args.json:
        print(json.dumps(receipt, indent=2))
    else:
        print("=" * 60)
        print("  COVERAGE GAP FILLER")
        print("=" * 60)
        print(f"  Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
        print(f"  Entities Added: {len(added)}")
        print(f"  Entities Skipped: {len(skipped)}")
        print()

        if added:
            print("  Added:")
            by_set = {}
            for item in added:
                entity_set = item['entity_set']
                if entity_set not in by_set:
                    by_set[entity_set] = []
                by_set[entity_set].append(item['entity'])

            for entity_set, entities in by_set.items():
                print(f"    {entity_set}:")
                for e in entities[:5]:
                    print(f"      + {e}")
                if len(entities) > 5:
                    print(f"      ... and {len(entities) - 5} more")
        print()
        if not args.dry_run:
            print(f"  Receipt: {receipt_path}")
        print("=" * 60)


if __name__ == "__main__":
    main()
