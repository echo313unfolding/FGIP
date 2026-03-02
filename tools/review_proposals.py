#!/usr/bin/env python3
"""Interactive CLI for reviewing staged proposals.

Usage:
    # List all pending proposals
    python3 tools/review_proposals.py list fgip.db

    # Show detail for specific proposal
    python3 tools/review_proposals.py show fgip.db <proposal_id>

    # Approve a single proposal
    python3 tools/review_proposals.py approve fgip.db <proposal_id>

    # Reject a proposal with reason
    python3 tools/review_proposals.py reject fgip.db <proposal_id> --reason "Invalid citation"

    # Approve all from a source file
    python3 tools/review_proposals.py approve-batch fgip.db --source genius_edge_updates.json

    # Approve all pending proposals
    python3 tools/review_proposals.py approve-batch fgip.db --all
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def list_proposals(conn: sqlite3.Connection, status: str = "PENDING",
                   proposal_type: str = None) -> None:
    """List proposals with optional filters."""

    # Build query
    queries = []
    params = []

    if proposal_type is None or proposal_type == "edge":
        query = """
            SELECT proposal_id, from_node, to_node, relationship, confidence, status,
                   detail, reasoning, created_at
            FROM proposed_edges
            WHERE status = ?
            ORDER BY created_at DESC
        """
        rows = conn.execute(query, (status,)).fetchall()

        if rows:
            print("\n" + "=" * 80)
            print("PROPOSED EDGES")
            print("=" * 80)
            print(f"{'PROPOSAL_ID':<45} {'RELATIONSHIP':<15} {'CONF':<5} {'STATUS':<10}")
            print("-" * 80)

            for row in rows:
                # Parse detail to check if this is an UPDATE
                try:
                    detail = json.loads(row["detail"]) if row["detail"] else {}
                except json.JSONDecodeError:
                    detail = {}
                if detail.get("action") == "UPDATE":
                    rel_display = f"UPDATE:{detail.get('field', '?')}"
                    target = detail.get("target_edge_id", "?")
                    print(f"{row['proposal_id']:<45} {rel_display:<15} {row['confidence']:<5.2f} {row['status']:<10}")
                    print(f"  └─ Target: {target}, {detail.get('old_value')} → {detail.get('new_value')}")
                else:
                    print(f"{row['proposal_id']:<45} {row['relationship']:<15} {row['confidence']:<5.2f} {row['status']:<10}")
                    print(f"  └─ {row['from_node']} → {row['to_node']}")

    if proposal_type is None or proposal_type == "claim":
        query = """
            SELECT proposal_id, claim_text, topic, status, source_url, created_at
            FROM proposed_claims
            WHERE status = ?
            ORDER BY created_at DESC
        """
        rows = conn.execute(query, (status,)).fetchall()

        if rows:
            print("\n" + "=" * 80)
            print("PROPOSED CLAIMS")
            print("=" * 80)
            print(f"{'PROPOSAL_ID':<45} {'TOPIC':<20} {'STATUS':<10}")
            print("-" * 80)

            for row in rows:
                print(f"{row['proposal_id']:<45} {row['topic']:<20} {row['status']:<10}")
                claim_preview = row['claim_text'][:60] + "..." if len(row['claim_text']) > 60 else row['claim_text']
                print(f"  └─ {claim_preview}")

    # Summary
    edge_count = conn.execute(
        "SELECT COUNT(*) FROM proposed_edges WHERE status = ?", (status,)
    ).fetchone()[0]
    claim_count = conn.execute(
        "SELECT COUNT(*) FROM proposed_claims WHERE status = ?", (status,)
    ).fetchone()[0]

    print("\n" + "-" * 80)
    print(f"Total {status}: {edge_count} edges, {claim_count} claims")


def show_proposal(conn: sqlite3.Connection, proposal_id: str) -> None:
    """Show detailed view of a single proposal."""

    # Try edges first
    row = conn.execute(
        "SELECT * FROM proposed_edges WHERE proposal_id = ?",
        (proposal_id,)
    ).fetchone()

    if row:
        print("\n" + "=" * 80)
        print("PROPOSED EDGE DETAIL")
        print("=" * 80)
        print(f"Proposal ID:  {row['proposal_id']}")
        print(f"Status:       {row['status']}")
        print(f"Created:      {row['created_at']}")
        print(f"Agent:        {row['agent_name']}")
        print("-" * 40)

        detail = json.loads(row["detail"]) if row["detail"] else {}

        if detail.get("action") == "UPDATE":
            print("ACTION:       UPDATE EXISTING EDGE")
            print(f"Target Edge:  {detail.get('target_edge_id')}")
            print(f"Field:        {detail.get('field')}")
            print(f"Old Value:    {detail.get('old_value')}")
            print(f"New Value:    {detail.get('new_value')}")
        else:
            print("ACTION:       CREATE NEW EDGE")
            print(f"From Node:    {row['from_node']}")
            print(f"To Node:      {row['to_node']}")
            print(f"Relationship: {row['relationship']}")
            print(f"Confidence:   {row['confidence']}")

        print("-" * 40)
        print("REASONING:")
        print(row['reasoning'] or "(none)")
        print("-" * 40)
        print("PROMOTION REQUIREMENT:")
        print(row['promotion_requirement'] or "(none)")

        if detail.get("source_file"):
            print("-" * 40)
            print(f"Source File:  {detail.get('source_file')}")
            if detail.get("tier") is not None:
                print(f"Tier:         {detail.get('tier')}")

        return

    # Try claims
    row = conn.execute(
        "SELECT * FROM proposed_claims WHERE proposal_id = ?",
        (proposal_id,)
    ).fetchone()

    if row:
        print("\n" + "=" * 80)
        print("PROPOSED CLAIM DETAIL")
        print("=" * 80)
        print(f"Proposal ID:  {row['proposal_id']}")
        print(f"Status:       {row['status']}")
        print(f"Created:      {row['created_at']}")
        print(f"Agent:        {row['agent_name']}")
        print("-" * 40)
        print(f"Topic:        {row['topic']}")
        print(f"Claim Text:   {row['claim_text']}")
        print("-" * 40)
        print("REASONING:")
        print(row['reasoning'] or "(none)")
        print("-" * 40)
        if row['source_url']:
            print(f"Source URL:   {row['source_url']}")
        return

    print(f"ERROR: Proposal not found: {proposal_id}")


def approve_proposal(conn: sqlite3.Connection, proposal_id: str,
                     reviewer: str = "cli-reviewer") -> bool:
    """Approve a single proposal."""

    # Check if it's an edge
    row = conn.execute(
        "SELECT status FROM proposed_edges WHERE proposal_id = ?",
        (proposal_id,)
    ).fetchone()

    if row:
        if row["status"] != "PENDING":
            print(f"WARNING: Proposal {proposal_id} is not PENDING (status={row['status']})")
            return False

        conn.execute(
            """UPDATE proposed_edges
               SET status = 'APPROVED', resolved_at = ?, reviewer_notes = ?
               WHERE proposal_id = ?""",
            (datetime.utcnow().isoformat() + "Z", f"Approved by {reviewer}", proposal_id)
        )

        # Record audit
        conn.execute(
            """INSERT INTO review_audit
               (proposal_type, proposal_id, decision, reviewer, notes, timestamp)
               VALUES ('edge', ?, 'APPROVED', ?, 'CLI approval', ?)""",
            (proposal_id, reviewer, datetime.utcnow().isoformat() + "Z")
        )

        print(f"✓ Approved edge proposal: {proposal_id}")
        return True

    # Check if it's a claim
    row = conn.execute(
        "SELECT status FROM proposed_claims WHERE proposal_id = ?",
        (proposal_id,)
    ).fetchone()

    if row:
        if row["status"] != "PENDING":
            print(f"WARNING: Proposal {proposal_id} is not PENDING (status={row['status']})")
            return False

        conn.execute(
            """UPDATE proposed_claims
               SET status = 'APPROVED', resolved_at = ?, reviewer_notes = ?
               WHERE proposal_id = ?""",
            (datetime.utcnow().isoformat() + "Z", f"Approved by {reviewer}", proposal_id)
        )

        # Record audit
        conn.execute(
            """INSERT INTO review_audit
               (proposal_type, proposal_id, decision, reviewer, notes, timestamp)
               VALUES ('claim', ?, 'APPROVED', ?, 'CLI approval', ?)""",
            (proposal_id, reviewer, datetime.utcnow().isoformat() + "Z")
        )

        print(f"✓ Approved claim proposal: {proposal_id}")
        return True

    print(f"ERROR: Proposal not found: {proposal_id}")
    return False


def reject_proposal(conn: sqlite3.Connection, proposal_id: str,
                    reason: str, reviewer: str = "cli-reviewer") -> bool:
    """Reject a proposal with reason."""

    # Check edges
    row = conn.execute(
        "SELECT status FROM proposed_edges WHERE proposal_id = ?",
        (proposal_id,)
    ).fetchone()

    if row:
        if row["status"] != "PENDING":
            print(f"WARNING: Proposal {proposal_id} is not PENDING (status={row['status']})")
            return False

        conn.execute(
            """UPDATE proposed_edges
               SET status = 'REJECTED', resolved_at = ?, reviewer_notes = ?
               WHERE proposal_id = ?""",
            (datetime.utcnow().isoformat() + "Z", reason, proposal_id)
        )

        # Record audit
        conn.execute(
            """INSERT INTO review_audit
               (proposal_type, proposal_id, decision, reviewer, notes, timestamp)
               VALUES ('edge', ?, 'REJECTED', ?, ?, ?)""",
            (proposal_id, reviewer, reason, datetime.utcnow().isoformat() + "Z")
        )

        print(f"✗ Rejected edge proposal: {proposal_id}")
        print(f"  Reason: {reason}")
        return True

    # Check claims
    row = conn.execute(
        "SELECT status FROM proposed_claims WHERE proposal_id = ?",
        (proposal_id,)
    ).fetchone()

    if row:
        if row["status"] != "PENDING":
            print(f"WARNING: Proposal {proposal_id} is not PENDING (status={row['status']})")
            return False

        conn.execute(
            """UPDATE proposed_claims
               SET status = 'REJECTED', resolved_at = ?, reviewer_notes = ?
               WHERE proposal_id = ?""",
            (datetime.utcnow().isoformat() + "Z", reason, proposal_id)
        )

        # Record audit
        conn.execute(
            """INSERT INTO review_audit
               (proposal_type, proposal_id, decision, reviewer, notes, timestamp)
               VALUES ('claim', ?, 'REJECTED', ?, ?, ?)""",
            (proposal_id, reviewer, reason, datetime.utcnow().isoformat() + "Z")
        )

        print(f"✗ Rejected claim proposal: {proposal_id}")
        print(f"  Reason: {reason}")
        return True

    print(f"ERROR: Proposal not found: {proposal_id}")
    return False


def approve_batch(conn: sqlite3.Connection, source: str = None,
                  approve_all: bool = False, reviewer: str = "cli-reviewer") -> int:
    """Approve multiple proposals in batch."""

    approved = 0

    # Approve edges
    if source:
        # Filter by source file in metadata
        rows = conn.execute(
            """SELECT proposal_id, detail FROM proposed_edges WHERE status = 'PENDING'"""
        ).fetchall()

        for row in rows:
            try:
                detail = json.loads(row["detail"]) if row["detail"] else {}
            except json.JSONDecodeError:
                detail = {}
            if detail.get("source_file") == source:
                if approve_proposal(conn, row["proposal_id"], reviewer):
                    approved += 1

    elif approve_all:
        rows = conn.execute(
            "SELECT proposal_id FROM proposed_edges WHERE status = 'PENDING'"
        ).fetchall()

        for row in rows:
            if approve_proposal(conn, row["proposal_id"], reviewer):
                approved += 1

        # Also approve claims
        rows = conn.execute(
            "SELECT proposal_id FROM proposed_claims WHERE status = 'PENDING'"
        ).fetchall()

        for row in rows:
            if approve_proposal(conn, row["proposal_id"], reviewer):
                approved += 1

    return approved


def main():
    parser = argparse.ArgumentParser(
        description="Review and manage staged proposals"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list command
    list_parser = subparsers.add_parser("list", help="List proposals")
    list_parser.add_argument("database", help="Path to FGIP database")
    list_parser.add_argument("--status", default="PENDING",
                            choices=["PENDING", "APPROVED", "REJECTED"],
                            help="Filter by status")
    list_parser.add_argument("--type", dest="proposal_type",
                            choices=["edge", "claim"],
                            help="Filter by type")

    # show command
    show_parser = subparsers.add_parser("show", help="Show proposal detail")
    show_parser.add_argument("database", help="Path to FGIP database")
    show_parser.add_argument("proposal_id", help="Proposal ID to show")

    # approve command
    approve_parser = subparsers.add_parser("approve", help="Approve a proposal")
    approve_parser.add_argument("database", help="Path to FGIP database")
    approve_parser.add_argument("proposal_id", help="Proposal ID to approve")
    approve_parser.add_argument("--reviewer", default="cli-reviewer",
                               help="Reviewer name")

    # reject command
    reject_parser = subparsers.add_parser("reject", help="Reject a proposal")
    reject_parser.add_argument("database", help="Path to FGIP database")
    reject_parser.add_argument("proposal_id", help="Proposal ID to reject")
    reject_parser.add_argument("--reason", required=True, help="Rejection reason")
    reject_parser.add_argument("--reviewer", default="cli-reviewer",
                              help="Reviewer name")

    # approve-batch command
    batch_parser = subparsers.add_parser("approve-batch", help="Approve multiple proposals")
    batch_parser.add_argument("database", help="Path to FGIP database")
    batch_parser.add_argument("--source", help="Approve all from source file")
    batch_parser.add_argument("--all", dest="approve_all", action="store_true",
                             help="Approve all pending proposals")
    batch_parser.add_argument("--reviewer", default="cli-reviewer",
                             help="Reviewer name")

    args = parser.parse_args()

    # Validate database path
    db_path = Path(args.database)
    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}")
        sys.exit(1)

    # Connect
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        if args.command == "list":
            list_proposals(conn, args.status, args.proposal_type)

        elif args.command == "show":
            show_proposal(conn, args.proposal_id)

        elif args.command == "approve":
            success = approve_proposal(conn, args.proposal_id, args.reviewer)
            conn.commit()
            sys.exit(0 if success else 1)

        elif args.command == "reject":
            success = reject_proposal(conn, args.proposal_id, args.reason, args.reviewer)
            conn.commit()
            sys.exit(0 if success else 1)

        elif args.command == "approve-batch":
            if not args.source and not args.approve_all:
                print("ERROR: Must specify --source or --all")
                sys.exit(1)
            count = approve_batch(conn, args.source, args.approve_all, args.reviewer)
            conn.commit()
            print(f"\nApproved {count} proposals")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
