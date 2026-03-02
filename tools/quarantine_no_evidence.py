#!/usr/bin/env python3
"""
Quarantine Tier-0 proposals missing artifact_id.

WO-FGIP-TRIANGULATION-HYGIENE-02

This script finds proposals from Tier-0 agents (edgar, usaspending, etc.)
that lack artifact_id and sets their status to QUARANTINED.

Usage:
    python3 tools/quarantine_no_evidence.py [--days N] [--dry-run]
    python3 tools/quarantine_no_evidence.py --agents edgar,usaspending --status PENDING
    python3 tools/quarantine_no_evidence.py --all-agents  # Apply to all agents, not just Tier-0
"""

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path

# Tier-0 agents that MUST have artifact_id for proposals
TIER0_AGENTS = [
    'edgar', 'usaspending', 'federal_register', 'congress',
    'nuclear_smr', 'tic', 'fec', 'scotus', 'gao', 'fara', 'chips-facility'
]


def quarantine_violations(
    db_path: str = "fgip.db",
    days: int = 30,
    dry_run: bool = False,
    agents: list = None,
    source_status: str = "PENDING",
):
    """
    Find and quarantine proposals missing artifact_id.

    Args:
        db_path: Path to FGIP database
        days: Look back N days for violations
        dry_run: If True, don't actually update rows
        agents: List of agent names to check (default: TIER0_AGENTS)
        source_status: Status to match for quarantine (default: PENDING)

    Returns:
        Receipt dict with quarantine details
    """
    target_agents = agents if agents else TIER0_AGENTS

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    placeholders = ','.join('?' * len(target_agents))

    # Build SQL predicates for receipt (reproducibility)
    edge_predicate = f"""
        SELECT proposal_id, agent_name, from_node, to_node, created_at
        FROM proposed_edges
        WHERE agent_name IN ({','.join(repr(a) for a in target_agents)})
        AND (artifact_id IS NULL OR artifact_id = '')
        AND status = '{source_status}'
        AND created_at >= datetime('now', '-{days} days')
    """.strip()

    claim_predicate = f"""
        SELECT proposal_id, agent_name, claim_text, created_at
        FROM proposed_claims
        WHERE agent_name IN ({','.join(repr(a) for a in target_agents)})
        AND (artifact_id IS NULL OR artifact_id = '')
        AND status = '{source_status}'
        AND created_at >= datetime('now', '-{days} days')
    """.strip()

    receipt = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "dry_run": dry_run,
        "days_lookback": days,
        "target_agents": target_agents,
        "source_status": source_status,
        "sql_predicates": {
            "edges": edge_predicate,
            "claims": claim_predicate,
        },
        "quarantined_edges": [],
        "quarantined_claims": [],
        "edge_count": 0,
        "claim_count": 0,
    }

    # Find violating edges
    rows = conn.execute(f"""
        SELECT proposal_id, agent_name, from_node, to_node, created_at
        FROM proposed_edges
        WHERE agent_name IN ({placeholders})
        AND (artifact_id IS NULL OR artifact_id = '')
        AND status = ?
        AND created_at >= datetime('now', '-{days} days')
    """, (*target_agents, source_status)).fetchall()

    for row in rows:
        if not dry_run:
            # Update status to QUARANTINED
            conn.execute("""
                UPDATE proposed_edges
                SET status = 'QUARANTINED',
                    reviewer_notes = COALESCE(reviewer_notes, '') ||
                        ' [HYGIENE-02] Missing artifact_id - quarantined ' || datetime('now')
                WHERE proposal_id = ?
            """, (row['proposal_id'],))

        receipt["quarantined_edges"].append({
            "proposal_id": row['proposal_id'],
            "agent_name": row['agent_name'],
            "from_node": row['from_node'],
            "to_node": row['to_node'],
            "created_at": row['created_at'],
        })

    receipt["edge_count"] = len(receipt["quarantined_edges"])

    # Find violating claims
    rows = conn.execute(f"""
        SELECT proposal_id, agent_name, claim_text, created_at
        FROM proposed_claims
        WHERE agent_name IN ({placeholders})
        AND (artifact_id IS NULL OR artifact_id = '')
        AND status = ?
        AND created_at >= datetime('now', '-{days} days')
    """, (*target_agents, source_status)).fetchall()

    for row in rows:
        if not dry_run:
            conn.execute("""
                UPDATE proposed_claims
                SET status = 'QUARANTINED',
                    reviewer_notes = COALESCE(reviewer_notes, '') ||
                        ' [HYGIENE-02] Missing artifact_id - quarantined ' || datetime('now')
                WHERE proposal_id = ?
            """, (row['proposal_id'],))

        receipt["quarantined_claims"].append({
            "proposal_id": row['proposal_id'],
            "agent_name": row['agent_name'],
            "claim_text": row['claim_text'][:100] if row['claim_text'] else None,
            "created_at": row['created_at'],
        })

    receipt["claim_count"] = len(receipt["quarantined_claims"])

    if not dry_run:
        conn.commit()
    conn.close()

    # Write receipt
    receipt_dir = Path("receipts/hygiene")
    receipt_dir.mkdir(parents=True, exist_ok=True)
    suffix = "_dryrun" if dry_run else ""
    receipt_path = receipt_dir / f"quarantine_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}{suffix}.json"
    receipt_path.write_text(json.dumps(receipt, indent=2))

    action = "Would quarantine" if dry_run else "Quarantined"
    print(f"{action}: {receipt['edge_count']} edges, {receipt['claim_count']} claims")
    print(f"Receipt: {receipt_path}")

    return receipt


def main():
    parser = argparse.ArgumentParser(
        description="Quarantine Tier-0 proposals missing artifact_id"
    )
    parser.add_argument(
        "--db", default="fgip.db",
        help="Path to FGIP database (default: fgip.db)"
    )
    parser.add_argument(
        "--days", type=int, default=30,
        help="Look back N days for violations (default: 30)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be quarantined without making changes"
    )
    parser.add_argument(
        "--agents",
        help="Comma-separated list of agents to check (default: TIER0_AGENTS)"
    )
    parser.add_argument(
        "--all-agents", action="store_true",
        help="Check ALL agents, not just Tier-0 (use with caution)"
    )
    parser.add_argument(
        "--status", default="PENDING",
        help="Status to match for quarantine (default: PENDING)"
    )

    args = parser.parse_args()

    # Determine which agents to check
    if args.all_agents:
        # Query all distinct agent names from the database
        import sqlite3
        conn = sqlite3.connect(args.db)
        agents = [row[0] for row in conn.execute(
            "SELECT DISTINCT agent_name FROM proposed_edges WHERE agent_name IS NOT NULL"
        ).fetchall()]
        conn.close()
        print(f"Checking ALL agents: {len(agents)} found")
    elif args.agents:
        agents = [a.strip() for a in args.agents.split(',')]
    else:
        agents = None  # Use default TIER0_AGENTS

    receipt = quarantine_violations(
        db_path=args.db,
        days=args.days,
        dry_run=args.dry_run,
        agents=agents,
        source_status=args.status,
    )

    # Print summary by agent
    if receipt["edge_count"] > 0 or receipt["claim_count"] > 0:
        print("\nBy agent:")
        agent_counts = {}
        for item in receipt["quarantined_edges"] + receipt["quarantined_claims"]:
            agent = item["agent_name"]
            agent_counts[agent] = agent_counts.get(agent, 0) + 1
        for agent, count in sorted(agent_counts.items(), key=lambda x: -x[1]):
            print(f"  {agent}: {count}")


if __name__ == "__main__":
    main()
