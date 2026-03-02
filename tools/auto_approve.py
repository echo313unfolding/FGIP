#!/usr/bin/env python3
"""FGIP Auto-Approver - Automatically promotes high-confidence proposals.

Runs after each ingest cycle to:
1. Promote edges with confidence >= threshold
2. Flag edges with confidence < threshold for manual review
3. Veto edges that fail validation rules
4. Generate approval receipt

Usage:
    python3 tools/auto_approve.py fgip.db --threshold 0.8
    python3 tools/auto_approve.py fgip.db --dry-run
    python3 tools/auto_approve.py fgip.db --report
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


# Validation rules - edges that should be vetoed
VETO_RULES = [
    # Self-referential edges
    lambda e: e['from_node'] == e['to_node'],
    # Too short node IDs (likely extraction errors)
    lambda e: len(e['from_node']) < 3 or len(e['to_node']) < 3,
    # Known bad patterns
    lambda e: any(bad in e['from_node'].lower() for bad in ['the-', 'a-', 'an-', 'and-']),
]

# Edge types that require higher confidence
HIGH_BAR_EDGE_TYPES = ['CAUSED', 'ENABLED', 'CONTRIBUTED_TO', 'BOTTLENECK_AT']


def get_pending_proposals(conn, edge_types=None):
    """Get all pending edge proposals."""
    query = """
        SELECT proposal_id, from_node, to_node, relationship,
               confidence, agent_name, created_at, reasoning
        FROM proposed_edges
        WHERE status = 'PENDING'
    """
    if edge_types:
        placeholders = ','.join('?' * len(edge_types))
        query += f" AND relationship IN ({placeholders})"
        return conn.execute(query, edge_types).fetchall()
    return conn.execute(query).fetchall()


def should_veto(edge):
    """Check if edge should be vetoed based on rules."""
    edge_dict = {
        'from_node': edge[1],
        'to_node': edge[2],
        'relationship': edge[3],
        'confidence': edge[4],
    }
    for rule in VETO_RULES:
        if rule(edge_dict):
            return True
    return False


def get_confidence_threshold(edge_type, base_threshold):
    """Get confidence threshold for edge type."""
    if edge_type in HIGH_BAR_EDGE_TYPES:
        return max(base_threshold, 0.85)  # Higher bar for causal claims
    return base_threshold


def auto_approve(db, threshold=0.8, dry_run=False):
    """Auto-approve proposals based on confidence threshold."""
    conn = db.connect()

    proposals = get_pending_proposals(conn)

    results = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'threshold': threshold,
        'dry_run': dry_run,
        'total_pending': len(proposals),
        'approved': [],
        'flagged_review': [],
        'vetoed': [],
    }

    for p in proposals:
        proposal_id, from_node, to_node, relationship, confidence, agent_name, created_at, reasoning = p

        # Check veto rules first
        if should_veto(p):
            results['vetoed'].append({
                'proposal_id': proposal_id,
                'edge': f"{from_node} --{relationship}--> {to_node}",
                'reason': 'Failed validation rule',
            })
            if not dry_run:
                conn.execute(
                    "UPDATE proposed_edges SET status = 'REJECTED' WHERE proposal_id = ?",
                    (proposal_id,)
                )
            continue

        # Get threshold for this edge type
        edge_threshold = get_confidence_threshold(relationship, threshold)

        if confidence >= edge_threshold:
            results['approved'].append({
                'proposal_id': proposal_id,
                'edge': f"{from_node} --{relationship}--> {to_node}",
                'confidence': confidence,
                'agent': agent_name,
            })
            if not dry_run:
                # Promote to production (same logic as promote_proposals.py)
                _promote_edge(conn, p)
        else:
            results['flagged_review'].append({
                'proposal_id': proposal_id,
                'edge': f"{from_node} --{relationship}--> {to_node}",
                'confidence': confidence,
                'threshold': edge_threshold,
                'gap': round(edge_threshold - confidence, 2),
            })

    if not dry_run:
        conn.commit()

    return results


def _promote_edge(conn, proposal):
    """Promote a single edge to production."""
    proposal_id, from_node, to_node, relationship, confidence, agent_name, created_at, reasoning = proposal

    try:
        # Check if already exists
        existing = conn.execute(
            "SELECT edge_id FROM edges WHERE from_node_id = ? AND to_node_id = ? AND edge_type = ?",
            (from_node, to_node, relationship)
        ).fetchone()

        if existing:
            conn.execute("UPDATE proposed_edges SET status = 'SKIPPED' WHERE proposal_id = ?", (proposal_id,))
            return False

        # Ensure nodes exist
        created_at_now = datetime.now(timezone.utc).isoformat()
        for node_id in [from_node, to_node]:
            existing_node = conn.execute("SELECT node_id FROM nodes WHERE node_id = ?", (node_id,)).fetchone()
            if not existing_node:
                node_name = node_id.replace('-', ' ').title()
                sha256 = hashlib.sha256(f"{node_id}:{node_name}:{created_at_now}".encode()).hexdigest()
                conn.execute(
                    "INSERT INTO nodes (node_id, node_type, name, created_at, sha256) VALUES (?, 'ORGANIZATION', ?, ?, ?)",
                    (node_id, node_name, created_at_now, sha256)
                )

        # Insert edge
        edge_id = f"{from_node}_{relationship}_{to_node}"[:100]
        edge_sha256 = hashlib.sha256(f"{edge_id}:{created_at_now}".encode()).hexdigest()
        metadata = json.dumps({'proposal_id': proposal_id, 'agent_name': agent_name, 'auto_approved': True})

        conn.execute("""
            INSERT INTO edges (edge_id, from_node_id, to_node_id, edge_type, confidence,
                              assertion_level, metadata, created_at, sha256)
            VALUES (?, ?, ?, ?, ?, 'INFERENCE', ?, ?, ?)
        """, (edge_id, from_node, to_node, relationship, confidence, metadata, created_at_now, edge_sha256))

        conn.execute("UPDATE proposed_edges SET status = 'APPLIED' WHERE proposal_id = ?", (proposal_id,))
        return True

    except Exception as e:
        print(f"Error promoting {proposal_id}: {e}")
        return False


def generate_review_report(results):
    """Generate human-readable review report."""
    lines = [
        "=" * 60,
        "  FGIP AUTO-APPROVAL REPORT",
        "=" * 60,
        f"  Timestamp: {results['timestamp']}",
        f"  Threshold: {results['threshold']}",
        f"  Dry Run: {results['dry_run']}",
        "",
        f"  SUMMARY:",
        f"    Total Pending: {results['total_pending']}",
        f"    Auto-Approved: {len(results['approved'])}",
        f"    Flagged for Review: {len(results['flagged_review'])}",
        f"    Vetoed: {len(results['vetoed'])}",
        "",
    ]

    if results['flagged_review']:
        lines.append("  NEEDS MANUAL REVIEW:")
        for item in results['flagged_review'][:20]:
            lines.append(f"    [{item['confidence']:.2f}] {item['edge']}")
            lines.append(f"           needs +{item['gap']:.2f} to reach {item['threshold']}")
        if len(results['flagged_review']) > 20:
            lines.append(f"    ... and {len(results['flagged_review']) - 20} more")
        lines.append("")

    if results['vetoed']:
        lines.append("  VETOED (failed validation):")
        for item in results['vetoed'][:10]:
            lines.append(f"    {item['edge']} - {item['reason']}")
        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="FGIP Auto-Approver")
    parser.add_argument("db", type=str, help="Database path")
    parser.add_argument("--threshold", type=float, default=0.8, help="Confidence threshold for auto-approval")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be approved without doing it")
    parser.add_argument("--report", action="store_true", help="Generate review report for flagged items")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")

    args = parser.parse_args()

    db = FGIPDatabase(args.db)
    db.connect()

    results = auto_approve(db, args.threshold, args.dry_run)

    # Save receipt
    receipt_dir = PROJECT_ROOT / "receipts" / "auto_approve"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / f"approval_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    receipt_path.write_text(json.dumps(results, indent=2))

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(generate_review_report(results))
        print(f"  Receipt: {receipt_path}")


if __name__ == "__main__":
    main()
