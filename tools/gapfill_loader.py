#!/usr/bin/env python3
"""Gap Fill Loader - Process GAP manifest through staging pipeline.

Routes documented gaps through the same staging → prelint → review workflow
as auto-discovered edges. No handwaving. Everything routes through staging.

Usage:
    python3 tools/gapfill_loader.py                    # List pending gaps
    python3 tools/gapfill_loader.py --batch 5          # Load first 5 pending
    python3 tools/gapfill_loader.py --id GAP-001       # Load specific gap
    python3 tools/gapfill_loader.py --skip GAP-003     # Mark as skipped
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from fgip.db import FGIPDatabase
from fgip.agents.base import ProposedClaim, ProposedEdge, ProposedNode
from fgip.staging_prelint import prelint_edge, prelint_node_id, LintIssue


MANIFEST_PATH = Path(__file__).parent.parent / "receipts" / "gapfill" / "GAP_95_manifest.jsonl"


def load_manifest() -> list:
    """Load the gap manifest."""
    if not MANIFEST_PATH.exists():
        print(f"Manifest not found: {MANIFEST_PATH}", file=sys.stderr)
        sys.exit(1)

    entries = []
    with open(MANIFEST_PATH) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                entry['_line'] = line_num
                entries.append(entry)
            except json.JSONDecodeError as e:
                print(f"JSON error on line {line_num}: {e}", file=sys.stderr)

    return entries


def save_manifest(entries: list):
    """Save updated manifest."""
    with open(MANIFEST_PATH, 'w') as f:
        for entry in entries:
            # Remove internal fields
            clean = {k: v for k, v in entry.items() if not k.startswith('_')}
            f.write(json.dumps(clean) + '\n')


def list_pending(entries: list):
    """List pending gaps."""
    pending = [e for e in entries if e.get('status') == 'PENDING']

    print(f"\n=== Pending Gaps ({len(pending)}) ===\n")

    for e in pending:
        gap_id = e.get('id', '?')
        from_node = e.get('from_node_id', '?')
        edge_type = e.get('edge_type', '?')
        to_node = e.get('to_node_id', '?')
        skip_reason = e.get('reason_if_skipped', '')

        # Check for prelint issues
        issues = prelint_edge(from_node, to_node, edge_type)
        has_errors = any(i.severity == LintIssue.SEVERITY_ERROR for i in issues)
        has_warnings = any(i.severity == LintIssue.SEVERITY_WARNING for i in issues)

        if has_errors:
            marker = "✗"
        elif has_warnings:
            marker = "⚠"
        else:
            marker = "○"

        print(f"{marker} {gap_id}: {from_node} --{edge_type}--> {to_node}")
        if skip_reason:
            print(f"    Note: {skip_reason}")
        for issue in issues:
            icon = "✗" if issue.severity == "ERROR" else "⚠"
            print(f"    {icon} {issue.message}")


def check_node_exists(db, node_id: str) -> bool:
    """Check if a node exists in the database."""
    node = db.get_node(node_id)
    return node is not None


def load_gap(db, entry: dict, dry_run: bool = False) -> dict:
    """Load a single gap entry through staging.

    Returns:
        Dict with result status
    """
    gap_id = entry.get('id')
    from_node = entry.get('from_node_id')
    to_node = entry.get('to_node_id')
    edge_type = entry.get('edge_type')

    result = {
        'gap_id': gap_id,
        'status': 'unknown',
        'proposal_id': None,
        'issues': [],
        'missing_nodes': [],
    }

    # Check prelint
    issues = prelint_edge(from_node, to_node, edge_type)
    errors = [i for i in issues if i.severity == LintIssue.SEVERITY_ERROR]

    if errors:
        result['status'] = 'prelint_failed'
        result['issues'] = [str(i) for i in errors]
        return result

    # Check if nodes exist
    missing_nodes = []
    if not check_node_exists(db, from_node):
        missing_nodes.append(from_node)
    if not check_node_exists(db, to_node):
        missing_nodes.append(to_node)

    if missing_nodes:
        result['status'] = 'missing_nodes'
        result['missing_nodes'] = missing_nodes
        return result

    # Generate proposal
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    proposal_id = f"FGIP-PROPOSED-GAPFILL-{timestamp}-{gap_id}"

    # Create claim first
    claim_id = f"FGIP-PROPOSED-GAPFILL-CLAIM-{timestamp}-{gap_id}"

    claim = ProposedClaim(
        proposal_id=claim_id,
        claim_text=entry.get('claim_text', ''),
        topic='GapFill',
        agent_name='gapfill_loader',
        source_url=entry.get('source_url'),
        reasoning=f"Gap fill from manifest: {gap_id}",
        promotion_requirement=entry.get('promotion_requirement'),
    )

    edge = ProposedEdge(
        proposal_id=proposal_id,
        from_node=from_node,
        to_node=to_node,
        relationship=edge_type,
        agent_name='gapfill_loader',
        detail=entry.get('claim_text'),
        proposed_claim_id=claim_id,
        confidence=0.8,  # Human-curated from manifest
        reasoning=f"From GAP manifest: {gap_id}. Assertion level: {entry.get('assertion_level', 'HYPOTHESIS')}",
        promotion_requirement=entry.get('promotion_requirement'),
    )

    if dry_run:
        result['status'] = 'would_propose'
        result['proposal_id'] = proposal_id
        return result

    # Write to staging
    conn = db.connect()

    conn.execute(
        """INSERT INTO proposed_claims
           (proposal_id, claim_text, topic, agent_name, source_url,
            reasoning, promotion_requirement, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)""",
        (claim.proposal_id, claim.claim_text, claim.topic, claim.agent_name,
         claim.source_url, claim.reasoning, claim.promotion_requirement,
         claim.created_at)
    )

    conn.execute(
        """INSERT INTO proposed_edges
           (proposal_id, from_node, to_node, relationship, detail,
            proposed_claim_id, agent_name, confidence, reasoning,
            promotion_requirement, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)""",
        (edge.proposal_id, edge.from_node, edge.to_node, edge.relationship,
         edge.detail, edge.proposed_claim_id, edge.agent_name, edge.confidence,
         edge.reasoning, edge.promotion_requirement, edge.created_at)
    )

    conn.commit()

    result['status'] = 'proposed'
    result['proposal_id'] = proposal_id
    return result


def main():
    parser = argparse.ArgumentParser(description='Gap Fill Loader')
    parser.add_argument('--batch', type=int, help='Load first N pending gaps')
    parser.add_argument('--id', dest='gap_id', help='Load specific gap by ID')
    parser.add_argument('--skip', help='Mark gap as skipped with reason')
    parser.add_argument('--skip-reason', default='Manually skipped', help='Reason for skipping')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done')
    parser.add_argument('--db', default='fgip.db', help='Database path')
    args = parser.parse_args()

    entries = load_manifest()
    db = FGIPDatabase(args.db)

    # Skip mode
    if args.skip:
        for entry in entries:
            if entry.get('id') == args.skip:
                entry['status'] = 'SKIPPED'
                entry['reason_if_skipped'] = args.skip_reason
                save_manifest(entries)
                print(f"✓ Marked {args.skip} as SKIPPED: {args.skip_reason}")
                return
        print(f"Gap not found: {args.skip}", file=sys.stderr)
        sys.exit(1)

    # Load specific gap
    if args.gap_id:
        for entry in entries:
            if entry.get('id') == args.gap_id:
                if entry.get('status') != 'PENDING':
                    print(f"Gap {args.gap_id} is not PENDING (status: {entry.get('status')})")
                    return

                result = load_gap(db, entry, dry_run=args.dry_run)

                if result['status'] == 'proposed':
                    print(f"✓ Proposed: {result['proposal_id']}")
                    entry['status'] = 'STAGED'
                    save_manifest(entries)
                elif result['status'] == 'would_propose':
                    print(f"Would propose: {result['proposal_id']}")
                elif result['status'] == 'missing_nodes':
                    print(f"✗ Missing nodes: {', '.join(result['missing_nodes'])}")
                elif result['status'] == 'prelint_failed':
                    print(f"✗ Prelint failed:")
                    for issue in result['issues']:
                        print(f"    {issue}")
                return

        print(f"Gap not found: {args.gap_id}", file=sys.stderr)
        sys.exit(1)

    # Batch mode
    if args.batch:
        pending = [e for e in entries if e.get('status') == 'PENDING'][:args.batch]

        if not pending:
            print("No pending gaps to load.")
            return

        print(f"\n=== Loading {len(pending)} gaps ===\n")

        proposed = 0
        failed = 0
        missing = 0

        for entry in pending:
            gap_id = entry.get('id')
            result = load_gap(db, entry, dry_run=args.dry_run)

            if result['status'] == 'proposed':
                print(f"✓ {gap_id}: Proposed as {result['proposal_id']}")
                entry['status'] = 'STAGED'
                proposed += 1
            elif result['status'] == 'would_propose':
                print(f"○ {gap_id}: Would propose")
                proposed += 1
            elif result['status'] == 'missing_nodes':
                print(f"⚠ {gap_id}: Missing nodes - {', '.join(result['missing_nodes'])}")
                missing += 1
            elif result['status'] == 'prelint_failed':
                print(f"✗ {gap_id}: Prelint failed - {result['issues'][0]}")
                failed += 1

        if not args.dry_run:
            save_manifest(entries)

        print(f"\nSummary: {proposed} proposed, {missing} missing nodes, {failed} failed")
        return

    # Default: list pending
    list_pending(entries)


if __name__ == '__main__':
    main()
