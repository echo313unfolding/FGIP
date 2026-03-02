#!/usr/bin/env python3
"""Deduplicate edges by (edge_type, from_node_id, to_node_id).

Picks winner per duplicate-set using priority order:
1. assertion_level: FACT > INFERENCE > HYPOTHESIS
2. claim strength: VERIFIED > EVIDENCED > PARTIAL > MISSING > None
3. best source tier: Tier 0/1 beats Tier 2 (lower is better)
4. has artifact_hash
5. confidence (higher wins)
6. tie-break: created_at older wins, then edge_id lexical

Losers are deleted but their claim_ids and edge_ids are merged into
winner metadata for provenance.

Usage:
    python3 tools/dedupe_edges.py --db fgip.db --dry-run  # Preview
    python3 tools/dedupe_edges.py --db fgip.db            # Execute
"""

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

ASSERT_RANK = {"HYPOTHESIS": 0, "INFERENCE": 1, "FACT": 2}
CLAIM_RANK = {"MISSING": 0, "PARTIAL": 1, "EVIDENCED": 2, "VERIFIED": 3}


def sha256_file(path: str) -> str:
    """Compute SHA256 of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(s: Optional[str]) -> Dict[str, Any]:
    """Safely load JSON string."""
    if not s:
        return {}
    try:
        return json.loads(s)
    except Exception:
        return {}


def dump_json(d: Dict[str, Any]) -> str:
    """Dump dict to canonical JSON."""
    return json.dumps(d, sort_keys=True)


def best_source_tier_and_artifact(
    conn: sqlite3.Connection, claim_id: str
) -> Tuple[int, bool]:
    """Get best source tier and whether any source has artifact for a claim."""
    rows = conn.execute(
        """
        SELECT s.tier, s.artifact_hash
        FROM claim_sources cs
        JOIN sources s ON s.source_id = cs.source_id
        WHERE cs.claim_id = ?
    """,
        (claim_id,),
    ).fetchall()

    if not rows:
        return (99, False)

    best_tier = min(int(r[0]) for r in rows if r[0] is not None) if rows else 99
    has_art = any(bool(r[1]) for r in rows)
    return (best_tier, has_art)


def claim_strength(
    conn: sqlite3.Connection, claim_id: Optional[str]
) -> Tuple[int, int, bool]:
    """Get claim strength metrics: (status_rank, best_tier, has_artifact)."""
    if not claim_id:
        return (-1, 99, False)

    row = conn.execute(
        "SELECT status FROM claims WHERE claim_id = ?", (claim_id,)
    ).fetchone()
    status = row[0] if row else None
    rank = CLAIM_RANK.get(status, -1) if status else -1

    best_tier, has_art = best_source_tier_and_artifact(conn, claim_id)
    return (rank, best_tier, has_art)


def edge_score(conn: sqlite3.Connection, e: Dict[str, Any]) -> Tuple:
    """Compute sortable score tuple for an edge. Higher is better."""
    a = (e.get("assertion_level") or "FACT").upper()
    ar = ASSERT_RANK.get(a, 0)

    cr, best_tier, has_art = claim_strength(conn, e.get("claim_id"))
    conf = float(e.get("confidence") or 0.0)

    created = e.get("created_at") or ""
    edge_id = e.get("edge_id") or ""

    # Return tuple for comparison
    # Higher is better for ar, cr, has_art, conf
    # Lower is better for tier (invert via negative)
    # For ties: prefer older created_at, then lexical edge_id
    return (
        ar,
        cr,
        -best_tier,  # negative so lower tier = higher score
        1 if has_art else 0,
        conf,
        created,
        edge_id,
    )


def select_winner(
    conn: sqlite3.Connection, items: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Select winner from duplicate set using priority rules."""
    scored = [(edge_score(conn, it), it) for it in items]

    # Find best by first 5 components (descending)
    best5 = None
    for sc, _ in scored:
        head5 = sc[:5]
        if best5 is None or head5 > best5:
            best5 = head5

    # Among ties on first 5, pick oldest created_at, then lexical edge_id
    tied = [(sc, it) for (sc, it) in scored if sc[:5] == best5]
    tied_sorted = sorted(tied, key=lambda t: (t[0][5], t[0][6]))

    return tied_sorted[0][1]


def main():
    ap = argparse.ArgumentParser(description="Deduplicate edges by (type, from, to)")
    ap.add_argument("--db", default="fgip.db", help="Database path")
    ap.add_argument(
        "--dry-run", action="store_true", help="Preview without modifying"
    )
    ap.add_argument(
        "--backup-dir", default="receipts/dedupe", help="Where to store backups"
    )
    args = ap.parse_args()

    db_path = args.db
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    os.makedirs(args.backup_dir, exist_ok=True)

    # Backup DB first
    backup_path = os.path.join(args.backup_dir, f"fgip_{ts}.db.bak")
    shutil.copy2(db_path, backup_path)
    print(f"BACKUP: {backup_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Pull all edges
    edges = conn.execute(
        """
        SELECT edge_id, edge_type, from_node_id, to_node_id, claim_id,
               assertion_level, confidence, metadata, created_at
        FROM edges
    """
    ).fetchall()

    # Group by (edge_type, from_node_id, to_node_id)
    groups: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}
    for r in edges:
        key = (r["edge_type"], r["from_node_id"], r["to_node_id"])
        groups.setdefault(key, []).append(dict(r))

    # Find duplicate groups (more than 1 edge per key)
    dup_groups = {k: v for k, v in groups.items() if len(v) > 1}

    report = {
        "ts": ts,
        "db": os.path.abspath(db_path),
        "db_sha256_before": sha256_file(db_path),
        "backup": os.path.abspath(backup_path),
        "duplicate_groups": len(dup_groups),
        "edges_before": len(edges),
        "actions": [],
        "dry_run": bool(args.dry_run),
    }

    losers_to_delete: List[str] = []
    updates: List[Tuple[str, str]] = []  # (edge_id, new_metadata_json)

    for key, items in sorted(dup_groups.items()):
        winner = select_winner(conn, items)
        winner_id = winner["edge_id"]

        # Prepare winner metadata with merged info
        winner_meta = load_json(winner.get("metadata"))
        winner_meta.setdefault("dedupe", {})
        winner_meta["dedupe"]["group_key"] = {
            "edge_type": key[0],
            "from": key[1],
            "to": key[2],
        }
        winner_meta["dedupe"].setdefault("merged_edge_ids", [])
        winner_meta["dedupe"].setdefault("merged_claim_ids", [])
        winner_meta["dedupe"]["dedupe_ts"] = ts

        losers = [it for it in items if it["edge_id"] != winner_id]

        for lo in losers:
            losers_to_delete.append(lo["edge_id"])

            # Merge loser edge_id
            if lo.get("edge_id") not in winner_meta["dedupe"]["merged_edge_ids"]:
                winner_meta["dedupe"]["merged_edge_ids"].append(lo.get("edge_id"))

            # Merge loser claim_id (if different from winner's)
            if (
                lo.get("claim_id")
                and lo.get("claim_id") != winner.get("claim_id")
                and lo.get("claim_id") not in winner_meta["dedupe"]["merged_claim_ids"]
            ):
                winner_meta["dedupe"]["merged_claim_ids"].append(lo.get("claim_id"))

        updates.append((winner_id, dump_json(winner_meta)))

        report["actions"].append(
            {
                "group": {"edge_type": key[0], "from": key[1], "to": key[2]},
                "winner": winner_id,
                "winner_assertion": winner.get("assertion_level"),
                "winner_claim": winner.get("claim_id"),
                "deleted": [lo["edge_id"] for lo in losers],
                "merged_claims": winner_meta["dedupe"]["merged_claim_ids"],
            }
        )

    # Execute changes (unless dry-run)
    if not args.dry_run and (updates or losers_to_delete):
        conn.execute("BEGIN")

        for edge_id, meta_json in updates:
            conn.execute(
                "UPDATE edges SET metadata = ? WHERE edge_id = ?", (meta_json, edge_id)
            )

        for edge_id in losers_to_delete:
            conn.execute("DELETE FROM edges WHERE edge_id = ?", (edge_id,))

        conn.commit()
        print(f"COMMITTED: {len(updates)} updates, {len(losers_to_delete)} deletes")
    elif args.dry_run:
        print(f"DRY-RUN: would update {len(updates)}, delete {len(losers_to_delete)}")

    # Final counts
    edges_after = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    report["edges_after"] = int(edges_after)
    report["deleted_edges"] = len(losers_to_delete)
    report["updated_winners"] = len(updates)

    if not args.dry_run:
        report["db_sha256_after"] = sha256_file(db_path)

    conn.close()

    # Write receipt
    receipt_path = os.path.join(args.backup_dir, f"dedupe_edges_{ts}.json")
    with open(receipt_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True)

    print(f"\nRECEIPT: {receipt_path}")
    print(f"DB SHA256 BEFORE: {report['db_sha256_before']}")
    print(f"DUPLICATE GROUPS: {report['duplicate_groups']}")
    print(f"EDGES: {report['edges_before']} → {report['edges_after']}")
    print(f"DELETED: {report['deleted_edges']}")

    if report["actions"]:
        print(f"\n=== Sample Actions (first 5) ===")
        for action in report["actions"][:5]:
            g = action["group"]
            print(f"  {g['from']} --{g['edge_type']}--> {g['to']}")
            print(f"    winner: {action['winner']} [{action['winner_assertion']}]")
            print(f"    deleted: {action['deleted']}")
            if action["merged_claims"]:
                print(f"    merged_claims: {action['merged_claims']}")


if __name__ == "__main__":
    main()
