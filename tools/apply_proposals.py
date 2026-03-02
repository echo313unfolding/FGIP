#!/usr/bin/env python3
"""Apply approved proposals to the production edges/claims tables.

Usage:
    python3 tools/apply_proposals.py fgip.db

This script:
1. Creates a timestamped backup of the database
2. Processes all APPROVED proposals in a transaction
3. For CREATE proposals: inserts new edges
4. For UPDATE proposals: modifies existing edges
5. Marks proposals as APPLIED
6. Records audit trail

The backup is stored in receipts/db_backups/ with timestamp.
"""

import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from fgip.schema import compute_sha256


def create_backup(db_path: Path, backup_dir: Path) -> Path:
    """Create timestamped backup of database."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_dir / f"fgip.db.{timestamp}"
    shutil.copy2(db_path, backup_path)
    return backup_path


def apply_create_edge(conn: sqlite3.Connection, proposal: dict) -> dict:
    """Apply a CREATE edge proposal to production edges table."""

    try:
        detail = json.loads(proposal["detail"]) if proposal["detail"] else {}
    except json.JSONDecodeError:
        detail = {}

    # Generate edge ID
    edge_id = detail.get("original_edge_id")
    if not edge_id:
        edge_id = f"edge_{proposal['relationship'].lower()}_{proposal['from_node'][:15]}_{proposal['to_node'][:15]}"

    # Check if edge already exists
    existing = conn.execute(
        "SELECT edge_id FROM edges WHERE edge_id = ?", (edge_id,)
    ).fetchone()

    if existing:
        return {
            "status": "SKIPPED",
            "reason": f"Edge {edge_id} already exists",
            "edge_id": edge_id,
        }

    # Determine assertion level based on relationship type
    # For Tier 0 evidence, we can use INFERENCE; otherwise HYPOTHESIS
    tier = detail.get("tier", 2)
    if tier == 0:
        assertion_level = "INFERENCE"
    else:
        assertion_level = "HYPOTHESIS"

    # Build metadata
    metadata = {
        "proposal_id": proposal["proposal_id"],
        "agent": proposal["agent_name"],
        "source_file": detail.get("source_file"),
        "tier": tier,
    }

    # Insert edge
    sha256 = compute_sha256(edge_id + proposal["from_node"] + proposal["to_node"])

    conn.execute(
        """INSERT INTO edges
           (edge_id, edge_type, from_node_id, to_node_id, assertion_level,
            confidence, notes, metadata, created_at, sha256)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            edge_id,
            proposal["relationship"],
            proposal["from_node"],
            proposal["to_node"],
            assertion_level,
            proposal["confidence"],
            f"Applied from proposal {proposal['proposal_id']}. {proposal['reasoning'] or ''}",
            json.dumps(metadata),
            datetime.utcnow().isoformat() + "Z",
            sha256,
        )
    )

    return {
        "status": "APPLIED",
        "edge_id": edge_id,
        "action": "CREATE",
    }


def apply_create_edge_from_update(conn: sqlite3.Connection, proposal: dict,
                                   detail: dict, original_target: str) -> dict:
    """UPDATE target missing - do not synthesize fake edges."""
    return {
        "status": "SKIPPED",
        "reason": f"UPDATE target missing: {original_target}. Not safe to synthesize edge.",
    }


def apply_update_edge(conn: sqlite3.Connection, proposal: dict) -> dict:
    """Apply an UPDATE edge proposal to existing edge."""

    try:
        detail = json.loads(proposal["detail"]) if proposal["detail"] else {}
    except json.JSONDecodeError:
        detail = {}

    target_edge_id = detail.get("target_edge_id")
    if not target_edge_id:
        return {
            "status": "ERROR",
            "reason": "No target_edge_id in proposal detail",
        }

    field = detail.get("field")
    new_value = detail.get("new_value")

    # Check if target edge exists
    existing = conn.execute(
        "SELECT * FROM edges WHERE edge_id = ?", (target_edge_id,)
    ).fetchone()

    if not existing:
        # Target edge doesn't exist - fall back to CREATE with annotation
        return apply_create_edge_from_update(conn, proposal, detail, target_edge_id)

    # Apply the update based on field
    if field == "confidence":
        conn.execute(
            """UPDATE edges
               SET confidence = ?,
                   notes = COALESCE(notes, '') || '\n[UPDATE ' || ? || '] confidence: ' || ? || ' → ' || ?
               WHERE edge_id = ?""",
            (new_value, datetime.utcnow().strftime("%Y-%m-%d"),
             detail.get("old_value"), new_value, target_edge_id)
        )

    elif field == "status":
        # Status updates go into notes since edges don't have a status field
        conn.execute(
            """UPDATE edges
               SET notes = COALESCE(notes, '') || '\n[UPDATE ' || ? || '] status: ' || ? || ' → ' || ?
               WHERE edge_id = ?""",
            (datetime.utcnow().strftime("%Y-%m-%d"),
             detail.get("old_value"), new_value, target_edge_id)
        )

    elif field == "assertion_level":
        conn.execute(
            """UPDATE edges
               SET assertion_level = ?,
                   notes = COALESCE(notes, '') || '\n[UPDATE ' || ? || '] assertion_level: ' || ? || ' → ' || ?
               WHERE edge_id = ?""",
            (new_value, datetime.utcnow().strftime("%Y-%m-%d"),
             detail.get("old_value"), new_value, target_edge_id)
        )

    else:
        # Generic metadata update
        conn.execute(
            """UPDATE edges
               SET notes = COALESCE(notes, '') || '\n[UPDATE ' || ? || '] ' || ? || ': ' || ? || ' → ' || ?
               WHERE edge_id = ?""",
            (datetime.utcnow().strftime("%Y-%m-%d"), field,
             detail.get("old_value"), new_value, target_edge_id)
        )

    return {
        "status": "APPLIED",
        "edge_id": target_edge_id,
        "action": "UPDATE",
        "field": field,
    }


def mark_proposal_applied(conn: sqlite3.Connection, proposal_id: str,
                          resolved_edge_id: str = None) -> None:
    """Mark a proposal as APPLIED."""
    conn.execute(
        """UPDATE proposed_edges
           SET status = 'APPLIED', resolved_edge_id = ?, resolved_at = ?
           WHERE proposal_id = ?""",
        (resolved_edge_id, datetime.utcnow().isoformat() + "Z", proposal_id)
    )

    # Record audit
    conn.execute(
        """INSERT INTO review_audit
           (proposal_type, proposal_id, decision, reviewer, notes, timestamp)
           VALUES ('edge', ?, 'APPLIED', 'apply_proposals.py', ?, ?)""",
        (proposal_id, f"Applied to edge {resolved_edge_id}",
         datetime.utcnow().isoformat() + "Z")
    )


def main():
    parser = argparse.ArgumentParser(
        description="Apply approved proposals to production tables"
    )
    parser.add_argument("database", help="Path to FGIP database")
    parser.add_argument("--no-backup", action="store_true",
                       help="Skip creating backup (dangerous)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be applied without committing")
    args = parser.parse_args()

    # Validate path
    db_path = Path(args.database)
    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}")
        sys.exit(1)

    # Create backup
    if not args.no_backup and not args.dry_run:
        backup_dir = db_path.parent / "receipts" / "db_backups"
        backup_path = create_backup(db_path, backup_dir)
        print(f"✓ Created backup: {backup_path}")

    # Connect
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Get all approved edge proposals
    rows = conn.execute(
        """SELECT * FROM proposed_edges
           WHERE status = 'APPROVED'
           ORDER BY created_at"""
    ).fetchall()

    if not rows:
        print("No approved proposals to apply.")
        conn.close()
        return

    print(f"\nFound {len(rows)} approved proposals to apply")
    print("=" * 60)

    # Process in transaction
    results = {
        "APPLIED": [],
        "SKIPPED": [],
        "ERROR": [],
    }

    try:
        for row in rows:
            proposal = dict(row)
            try:
                detail = json.loads(proposal["detail"]) if proposal["detail"] else {}
            except json.JSONDecodeError:
                detail = {}

            if args.dry_run:
                if detail.get("action") == "UPDATE":
                    print(f"[DRY-RUN] Would UPDATE {detail.get('target_edge_id')}.{detail.get('field')}")
                else:
                    print(f"[DRY-RUN] Would CREATE {proposal['from_node']} → {proposal['to_node']}")
                continue

            # Determine if CREATE or UPDATE
            if detail.get("action") == "UPDATE":
                result = apply_update_edge(conn, proposal)
            else:
                result = apply_create_edge(conn, proposal)

            results[result["status"]].append({
                "proposal_id": proposal["proposal_id"],
                **result,
            })

            if result["status"] == "APPLIED":
                mark_proposal_applied(conn, proposal["proposal_id"], result.get("edge_id"))
                print(f"✓ {result.get('action', 'APPLY')}: {result.get('edge_id')}")
            elif result["status"] == "SKIPPED":
                print(f"⊘ SKIP: {result.get('reason')}")
            else:
                print(f"✗ ERROR: {result.get('reason')}")

        # Commit transaction
        if not args.dry_run:
            conn.commit()
            print("\n✓ Transaction committed")

    except Exception as e:
        conn.rollback()
        print(f"\n✗ Transaction rolled back due to error: {e}")
        sys.exit(1)

    finally:
        conn.close()

    # Summary
    print("\n" + "=" * 60)
    print("APPLY SUMMARY")
    print("=" * 60)
    print(f"  Applied:  {len(results['APPLIED'])}")
    print(f"  Skipped:  {len(results['SKIPPED'])}")
    print(f"  Errors:   {len(results['ERROR'])}")

    if results["ERROR"]:
        print("\nErrors:")
        for err in results["ERROR"]:
            print(f"  - {err['proposal_id']}: {err.get('reason')}")

    # Verification commands
    if not args.dry_run and results["APPLIED"]:
        print("\n" + "-" * 60)
        print("Verify with:")
        print(f'  sqlite3 {db_path} "SELECT COUNT(*) FROM proposed_edges WHERE status=\'APPLIED\';"')
        print(f'  sqlite3 {db_path} "SELECT edge_id, edge_type, confidence FROM edges ORDER BY created_at DESC LIMIT 10;"')


if __name__ == "__main__":
    main()
