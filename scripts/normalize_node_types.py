#!/usr/bin/env python3
"""
FGIP Node Type Normalization
Date: 2026-05-14

Fixes lowercase/inconsistent node_type values:
  - company → COMPANY (merge with 162 existing)
  - infrastructure → INFRASTRUCTURE (merge with 3 existing)
  - regulator → REGULATOR (merge with 14 existing)
  - risk → RISK_FACTOR (merge with 1 existing)
  - central_bank → FINANCIAL_INST (merge with 22 existing)
  - asset_class, concept, market, market_mechanism, market_participant,
    regulatory_category, regulatory_requirement → UPPERCASED
"""

import sqlite3
import json
import time
import resource
import platform
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "fgip.db"
RECEIPT_DIR = Path(__file__).parent.parent / "receipts"
SESSION_ID = "node-type-normalize-20260514"

# Mapping: old_type → new_type
TYPE_MAP = {
    "company": "COMPANY",
    "infrastructure": "INFRASTRUCTURE",
    "regulator": "REGULATOR",
    "risk": "RISK_FACTOR",
    "central_bank": "FINANCIAL_INST",
    "asset_class": "ASSET_CLASS",
    "concept": "CONCEPT",
    "market": "MARKET",
    "market_mechanism": "MARKET_MECHANISM",
    "market_participant": "MARKET_PARTICIPANT",
    "regulatory_category": "REGULATORY_CATEGORY",
    "regulatory_requirement": "REGULATORY_REQUIREMENT",
}


def main():
    t_start = time.time()
    cpu_start = time.process_time()
    start_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row

    updates = {}
    total_updated = 0

    for old_type, new_type in TYPE_MAP.items():
        # Find nodes with this type
        count = db.execute(
            "SELECT COUNT(*) FROM nodes WHERE node_type = ?", (old_type,)
        ).fetchone()[0]

        if count > 0:
            # Get the node IDs for the receipt
            nodes = db.execute(
                "SELECT node_id, name FROM nodes WHERE node_type = ?", (old_type,)
            ).fetchall()

            db.execute(
                "UPDATE nodes SET node_type = ? WHERE node_type = ?",
                (new_type, old_type)
            )

            updates[old_type] = {
                "new_type": new_type,
                "count": count,
                "nodes": [{"id": n["node_id"], "name": n["name"]} for n in nodes],
            }
            total_updated += count
            print(f"  {old_type} → {new_type}: {count} nodes")

    db.commit()

    # Verify no lowercase types remain
    remaining = db.execute("""
        SELECT node_type, COUNT(*) as cnt FROM nodes
        WHERE node_type != UPPER(node_type)
        GROUP BY node_type
    """).fetchall()

    # Get final type distribution
    final_types = db.execute("""
        SELECT node_type, COUNT(*) as cnt FROM nodes
        GROUP BY node_type ORDER BY cnt DESC
    """).fetchall()

    cost = {
        "wall_time_s": round(time.time() - t_start, 3),
        "cpu_time_s": round(time.process_time() - cpu_start, 3),
        "peak_memory_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        "python_version": platform.python_version(),
        "hostname": platform.node(),
        "timestamp_start": start_iso,
        "timestamp_end": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
    }

    receipt = {
        "receipt_id": SESSION_ID,
        "operation": "node_type_normalize",
        "session_date": "2026-05-14",
        "results": {
            "total_updated": total_updated,
            "mappings": updates,
            "remaining_lowercase": [dict(r) for r in remaining],
            "final_type_counts": {r["node_type"]: r["cnt"] for r in final_types},
        },
        "cost": cost,
    }

    RECEIPT_DIR.mkdir(exist_ok=True)
    receipt_path = RECEIPT_DIR / f"{SESSION_ID}.json"
    with open(receipt_path, "w") as f:
        json.dump(receipt, f, indent=2)

    print(f"\n{'='*60}")
    print(f"NORMALIZE COMPLETE: {total_updated} nodes updated")
    print(f"Remaining lowercase: {len(remaining)}")
    print(f"Distinct types: {len(final_types)}")
    print(f"Receipt: {receipt_path}")
    print(f"{'='*60}")

    db.close()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
