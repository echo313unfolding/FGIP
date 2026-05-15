#!/usr/bin/env python3
"""
FGIP Claim Deduplication
Date: 2026-05-14

For each group of claims with identical text:
1. Keep the earliest claim_id (lowest FGIP-NNNNNN number)
2. Merge all claim_sources from duplicates into the keeper
3. If any duplicate has higher status, promote the keeper
4. Delete duplicate claims and their orphaned claim_sources
5. Rebuild FTS index

Safe: no edges reference duplicate claims (verified pre-run).
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
SESSION_ID = "claim-dedup-20260514"

STATUS_RANK = {"VERIFIED": 4, "EVIDENCED": 3, "PARTIAL": 2, "MISSING": 1}


def main():
    t_start = time.time()
    cpu_start = time.process_time()
    start_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = OFF")  # We handle FK integrity manually

    # Find all duplicate groups
    groups = db.execute("""
        SELECT claim_text, COUNT(*) as cnt
        FROM claims
        GROUP BY claim_text
        HAVING cnt > 1
        ORDER BY cnt DESC
    """).fetchall()

    print(f"Duplicate groups: {len(groups)}")
    total_before = db.execute("SELECT COUNT(*) FROM claims").fetchone()[0]

    claims_deleted = 0
    sources_merged = 0
    status_promoted = 0
    edges_repointed = 0

    for group in groups:
        text = group["claim_text"]

        # Get all claims with this text, ordered by claim_id
        members = db.execute(
            "SELECT claim_id, status, topic, notes FROM claims WHERE claim_text = ? ORDER BY claim_id",
            (text,)
        ).fetchall()

        keeper_id = members[0]["claim_id"]
        keeper_status = members[0]["status"]
        remove_ids = [m["claim_id"] for m in members[1:]]

        # Find best status across all duplicates
        best_status = keeper_status
        for m in members:
            if STATUS_RANK.get(m["status"], 0) > STATUS_RANK.get(best_status, 0):
                best_status = m["status"]

        # Promote keeper status if a duplicate had higher
        if best_status != keeper_status:
            db.execute("UPDATE claims SET status = ? WHERE claim_id = ?",
                       (best_status, keeper_id))
            status_promoted += 1

        # Re-point edges from duplicates to keeper
        for rid in remove_ids:
            updated = db.execute(
                "UPDATE edges SET claim_id = ? WHERE claim_id = ?",
                (keeper_id, rid)
            ).rowcount
            edges_repointed += updated

        # Merge sources: move all claim_sources from duplicates to keeper
        for rid in remove_ids:
            sources = db.execute(
                "SELECT source_id FROM claim_sources WHERE claim_id = ?", (rid,)
            ).fetchall()
            for s in sources:
                try:
                    db.execute(
                        "INSERT OR IGNORE INTO claim_sources (claim_id, source_id) VALUES (?, ?)",
                        (keeper_id, s["source_id"])
                    )
                    sources_merged += 1
                except sqlite3.IntegrityError:
                    pass

            # Delete claim_sources for this duplicate
            db.execute("DELETE FROM claim_sources WHERE claim_id = ?", (rid,))

        # Delete duplicate claims
        placeholders = ",".join("?" * len(remove_ids))
        db.execute(f"DELETE FROM claims WHERE claim_id IN ({placeholders})", remove_ids)
        claims_deleted += len(remove_ids)

    db.commit()

    # Rebuild FTS index
    print("Rebuilding claims FTS index...")
    try:
        db.execute("INSERT INTO claims_fts(claims_fts) VALUES('rebuild')")
        db.commit()
        fts_ok = True
    except Exception as e:
        print(f"FTS rebuild warning: {e}")
        fts_ok = False

    total_after = db.execute("SELECT COUNT(*) FROM claims").fetchone()[0]

    # Verify no orphaned claim_sources
    orphaned = db.execute("""
        SELECT COUNT(*) FROM claim_sources cs
        WHERE NOT EXISTS (SELECT 1 FROM claims c WHERE c.claim_id = cs.claim_id)
    """).fetchone()[0]

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
        "operation": "claim_dedup",
        "session_date": "2026-05-14",
        "results": {
            "duplicate_groups": len(groups),
            "claims_before": total_before,
            "claims_deleted": claims_deleted,
            "claims_after": total_after,
            "sources_merged": sources_merged,
            "status_promoted": status_promoted,
            "orphaned_claim_sources": orphaned,
            "fts_rebuilt": fts_ok,
            "edges_repointed": edges_repointed,
        },
        "cost": cost,
    }

    RECEIPT_DIR.mkdir(exist_ok=True)
    receipt_path = RECEIPT_DIR / f"{SESSION_ID}.json"
    with open(receipt_path, "w") as f:
        json.dump(receipt, f, indent=2)

    print(f"\n{'='*60}")
    print(f"DEDUP COMPLETE")
    print(f"  Claims: {total_before} → {total_after} (-{claims_deleted})")
    print(f"  Sources merged: {sources_merged}")
    print(f"  Status promotions: {status_promoted}")
    print(f"  Edges repointed: {edges_repointed}")
    print(f"  Orphaned claim_sources: {orphaned}")
    print(f"  FTS rebuilt: {fts_ok}")
    print(f"  Receipt: {receipt_path}")
    print(f"  Wall time: {cost['wall_time_s']}s")
    print(f"{'='*60}")

    db.close()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
