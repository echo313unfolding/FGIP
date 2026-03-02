#!/usr/bin/env python3
"""Stage edge updates from JSON into proposed_edges table.

Usage:
    python3 tools/stage_edge_updates.py fgip.db docs/genius_edge_updates.json

Loads edge update definitions from JSON and stages them as pending proposals
for human review before applying to the graph.

JSON format supports:
- action=CREATE: New edge proposals
- action=UPDATE: Modifications to existing edges (staged as new proposals with update_target)
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from fgip.schema import compute_sha256


def get_next_proposal_id(conn: sqlite3.Connection, agent_name: str, content_hash: str) -> str:
    """Generate deterministic proposal ID."""
    date_str = datetime.utcnow().strftime("%Y%m%d")
    short_sha = content_hash[:10]
    return f"FGIP-PROPOSED-{agent_name.upper()}-{date_str}-{short_sha}"


def check_duplicate(conn: sqlite3.Connection, proposal_id: str) -> bool:
    """Check if proposal already exists."""
    row = conn.execute(
        "SELECT 1 FROM proposed_edges WHERE proposal_id = ?",
        (proposal_id,)
    ).fetchone()
    return row is not None


def stage_create_edge(conn: sqlite3.Connection, edge_def: dict, source_file: str) -> dict:
    """Stage a CREATE edge action as a proposed_edge."""
    # Compute content hash for deterministic ID
    content = {
        "action": "CREATE",
        "from_node": edge_def["from_node"],
        "to_node": edge_def["to_node"],
        "edge_type": edge_def["edge_type"],
    }
    content_hash = compute_sha256(content)

    proposal_id = get_next_proposal_id(conn, "GENIUS-STAGING", content_hash)

    # Check for duplicate
    if check_duplicate(conn, proposal_id):
        return {"status": "DUPLICATE", "proposal_id": proposal_id}

    # Build reasoning from evidence
    reasoning = f"Source: {edge_def.get('evidence_citation', 'N/A')}"
    if edge_def.get("evidence_text"):
        reasoning += f"\nEvidence: {edge_def['evidence_text']}"

    # Build metadata
    metadata = {
        "tier": edge_def.get("tier", 2),
        "source_file": source_file,
        "original_edge_id": edge_def.get("edge_id"),
    }

    # Insert into proposed_edges
    conn.execute(
        """INSERT INTO proposed_edges
           (proposal_id, from_node, to_node, relationship, detail,
            agent_name, confidence, reasoning, promotion_requirement,
            status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)""",
        (
            proposal_id,
            edge_def["from_node"],
            edge_def["to_node"],
            edge_def["edge_type"],
            json.dumps(metadata),
            "genius-edge-stager",
            edge_def.get("confidence", 0.5),
            reasoning,
            f"Tier 0 citation: {edge_def.get('evidence_citation', 'pending')}",
            datetime.utcnow().isoformat() + "Z",
        )
    )

    return {"status": "STAGED", "proposal_id": proposal_id}


def stage_update_edge(conn: sqlite3.Connection, edge_def: dict, source_file: str) -> dict:
    """Stage an UPDATE edge action as a proposed_edge modification.

    Updates are staged as special proposals that reference the target edge.
    When applied, they update the existing edge rather than create new.
    """
    # Compute content hash for deterministic ID
    content = {
        "action": "UPDATE",
        "edge_id": edge_def["edge_id"],
        "field": edge_def["field"],
        "new_value": edge_def["new_value"],
    }
    content_hash = compute_sha256(content)

    proposal_id = get_next_proposal_id(conn, "GENIUS-UPDATE", content_hash)

    # Check for duplicate
    if check_duplicate(conn, proposal_id):
        return {"status": "DUPLICATE", "proposal_id": proposal_id}

    # Build reasoning
    reasoning = f"UPDATE {edge_def['edge_id']}.{edge_def['field']}: {edge_def.get('old_value')} → {edge_def['new_value']}"
    reasoning += f"\nReason: {edge_def.get('reason', 'N/A')}"
    reasoning += f"\nCitation: {edge_def.get('evidence_citation', 'N/A')}"

    # Build metadata with update details
    metadata = {
        "action": "UPDATE",
        "target_edge_id": edge_def["edge_id"],
        "field": edge_def["field"],
        "old_value": edge_def.get("old_value"),
        "new_value": edge_def["new_value"],
        "source_file": source_file,
    }

    # For UPDATE, we stage with dummy from/to nodes (the actual edge exists)
    # The applier will use target_edge_id from metadata
    conn.execute(
        """INSERT INTO proposed_edges
           (proposal_id, from_node, to_node, relationship, detail,
            agent_name, confidence, reasoning, promotion_requirement,
            status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)""",
        (
            proposal_id,
            f"[UPDATE:{edge_def['edge_id']}]",  # Marker for update
            f"[FIELD:{edge_def['field']}]",      # Marker for field
            "UPDATE",  # Special relationship type
            json.dumps(metadata),
            "genius-edge-stager",
            edge_def.get("new_value") if edge_def["field"] == "confidence" else 0.5,
            reasoning,
            f"Tier 0 citation: {edge_def.get('evidence_citation', 'pending')}",
            datetime.utcnow().isoformat() + "Z",
        )
    )

    return {"status": "STAGED", "proposal_id": proposal_id}


def main():
    parser = argparse.ArgumentParser(
        description="Stage edge updates from JSON into proposed_edges table"
    )
    parser.add_argument("database", help="Path to FGIP database")
    parser.add_argument("json_file", help="Path to edge updates JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be staged without writing")
    args = parser.parse_args()

    # Validate paths
    db_path = Path(args.database)
    json_path = Path(args.json_file)

    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}")
        sys.exit(1)

    if not json_path.exists():
        print(f"ERROR: JSON file not found: {json_path}")
        sys.exit(1)

    # Load JSON
    with open(json_path) as f:
        edge_updates = json.load(f)

    print(f"Loaded {len(edge_updates)} edge updates from {json_path.name}")

    # Connect to database
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Process each edge update
    results = {
        "STAGED": [],
        "DUPLICATE": [],
        "ERROR": [],
    }

    for edge_def in edge_updates:
        action = edge_def.get("action", "CREATE")

        try:
            if args.dry_run:
                print(f"  [DRY-RUN] Would stage {action}: {edge_def.get('edge_id', edge_def.get('from_node', 'unknown'))}")
                continue

            if action == "CREATE":
                result = stage_create_edge(conn, edge_def, json_path.name)
            elif action == "UPDATE":
                result = stage_update_edge(conn, edge_def, json_path.name)
            else:
                print(f"  WARNING: Unknown action '{action}', skipping")
                continue

            results[result["status"]].append(result["proposal_id"])

        except Exception as e:
            results["ERROR"].append(f"{edge_def.get('edge_id', 'unknown')}: {e}")

    # Commit changes
    if not args.dry_run:
        conn.commit()

    conn.close()

    # Print summary
    print("\n" + "=" * 50)
    print("STAGING SUMMARY")
    print("=" * 50)
    print(f"  Staged:     {len(results['STAGED'])}")
    print(f"  Duplicates: {len(results['DUPLICATE'])}")
    print(f"  Errors:     {len(results['ERROR'])}")

    if results["STAGED"]:
        print("\nStaged proposals:")
        for pid in results["STAGED"]:
            print(f"  - {pid}")

    if results["DUPLICATE"]:
        print("\nSkipped duplicates:")
        for pid in results["DUPLICATE"]:
            print(f"  - {pid}")

    if results["ERROR"]:
        print("\nErrors:")
        for err in results["ERROR"]:
            print(f"  - {err}")

    # Show verification command
    if not args.dry_run and results["STAGED"]:
        print("\n" + "-" * 50)
        print("Verify with:")
        print(f'  sqlite3 {db_path} "SELECT status, COUNT(*) FROM proposed_edges GROUP BY status;"')
        print(f"  python3 tools/review_proposals.py list {db_path}")


if __name__ == "__main__":
    main()
