#!/usr/bin/env python3
"""
FGIP Partial Claim Audit
Date: 2026-05-14

Audits the 5,789 PARTIAL claims:
1. Which have sources linked in claim_sources? → promote to EVIDENCED
2. Which have tier-0/1 sources? → promote to VERIFIED
3. Which are truly orphaned (no sources at all)?

Also checks for claims referenced by edges but with no sources.
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
SESSION_ID = "partial-claim-audit-20260514"


def main():
    t_start = time.time()
    cpu_start = time.process_time()
    start_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row

    # Count PARTIAL claims
    partial_count = db.execute(
        "SELECT COUNT(*) FROM claims WHERE status = 'PARTIAL'"
    ).fetchone()[0]
    print(f"PARTIAL claims: {partial_count}")

    # Find PARTIAL claims that have tier-0 or tier-1 sources → VERIFIED
    tier01_upgrades = db.execute("""
        SELECT DISTINCT c.claim_id
        FROM claims c
        JOIN claim_sources cs ON c.claim_id = cs.claim_id
        JOIN sources s ON cs.source_id = s.source_id
        WHERE c.status = 'PARTIAL'
          AND s.tier <= 1
    """).fetchall()

    tier01_ids = [r["claim_id"] for r in tier01_upgrades]
    if tier01_ids:
        placeholders = ",".join("?" * len(tier01_ids))
        db.execute(
            f"UPDATE claims SET status = 'VERIFIED' WHERE claim_id IN ({placeholders})",
            tier01_ids
        )
        print(f"  Promoted to VERIFIED (tier-0/1 sources): {len(tier01_ids)}")

    # Find remaining PARTIAL claims that have ANY sources → EVIDENCED
    evidenced_upgrades = db.execute("""
        SELECT DISTINCT c.claim_id
        FROM claims c
        JOIN claim_sources cs ON c.claim_id = cs.claim_id
        WHERE c.status = 'PARTIAL'
    """).fetchall()

    evidenced_ids = [r["claim_id"] for r in evidenced_upgrades]
    if evidenced_ids:
        placeholders = ",".join("?" * len(evidenced_ids))
        db.execute(
            f"UPDATE claims SET status = 'EVIDENCED' WHERE claim_id IN ({placeholders})",
            evidenced_ids
        )
        print(f"  Promoted to EVIDENCED (have sources): {len(evidenced_ids)}")

    # Count remaining PARTIAL (no sources at all)
    still_partial = db.execute(
        "SELECT COUNT(*) FROM claims WHERE status = 'PARTIAL'"
    ).fetchone()[0]
    print(f"  Still PARTIAL (no sources): {still_partial}")

    # Check for claims referenced by edges but missing sources
    edge_claims_no_sources = db.execute("""
        SELECT DISTINCT e.claim_id, c.status
        FROM edges e
        JOIN claims c ON e.claim_id = c.claim_id
        WHERE e.claim_id IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM claim_sources cs WHERE cs.claim_id = e.claim_id
          )
    """).fetchall()
    print(f"  Claims used by edges but no sources: {len(edge_claims_no_sources)}")

    # Check for edges referencing non-existent claims
    orphan_edges = db.execute("""
        SELECT COUNT(*) FROM edges e
        WHERE e.claim_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM claims c WHERE c.claim_id = e.claim_id)
    """).fetchone()[0]
    print(f"  Edges referencing non-existent claims: {orphan_edges}")

    db.commit()

    # Rebuild FTS
    print("Rebuilding claims FTS index...")
    try:
        db.execute("INSERT INTO claims_fts(claims_fts) VALUES('rebuild')")
        db.commit()
        fts_ok = True
    except Exception as e:
        print(f"  FTS rebuild warning: {e}")
        fts_ok = False

    # Final status distribution
    statuses = db.execute("""
        SELECT status, COUNT(*) as cnt FROM claims GROUP BY status ORDER BY cnt DESC
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
        "operation": "partial_claim_audit",
        "session_date": "2026-05-14",
        "results": {
            "partial_before": partial_count,
            "promoted_to_verified": len(tier01_ids),
            "promoted_to_evidenced": len(evidenced_ids),
            "still_partial": still_partial,
            "edge_claims_no_sources": len(edge_claims_no_sources),
            "orphan_edges": orphan_edges,
            "fts_rebuilt": fts_ok,
            "final_statuses": {r["status"]: r["cnt"] for r in statuses},
        },
        "cost": cost,
    }

    RECEIPT_DIR.mkdir(exist_ok=True)
    receipt_path = RECEIPT_DIR / f"{SESSION_ID}.json"
    with open(receipt_path, "w") as f:
        json.dump(receipt, f, indent=2)

    print(f"\n{'='*60}")
    print(f"AUDIT COMPLETE")
    for s in statuses:
        print(f"  {s['status']}: {s['cnt']}")
    print(f"Receipt: {receipt_path}")
    print(f"{'='*60}")

    db.close()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
