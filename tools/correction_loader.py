#!/usr/bin/env python3
"""Correction Layer Loader - Process correction manifest through staging pipeline.

Routes correction layer edges (GENIUS Act, CHIPS Act, etc.) through the same
staging → prelint → review workflow as problem layer edges.

Usage:
    python3 tools/correction_loader.py                    # List pending corrections
    python3 tools/correction_loader.py --batch 5          # Load first 5 pending
    python3 tools/correction_loader.py --id CORR-001      # Load specific correction
    python3 tools/correction_loader.py --skip CORR-003    # Mark as skipped
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


MANIFEST_PATH = Path(__file__).parent.parent / "manifests" / "correction_layer_v0.jsonl"


def load_manifest() -> list:
    """Load the correction manifest."""
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
    """List pending corrections."""
    pending = [e for e in entries if e.get('status') == 'PENDING']

    print(f"\n=== Pending Corrections ({len(pending)}) ===\n")

    for e in pending:
        corr_id = e.get('id', '?')
        from_node = e.get('from_node_id', '?')
        edge_type = e.get('edge_type', '?')
        to_node = e.get('to_node_id', '?')
        tier = e.get('tier_hint', '?')
        assertion = e.get('assertion_level', '?')

        # Check for prelint issues
        issues = prelint_edge(from_node, to_node, edge_type)
        has_errors = any(i.severity == LintIssue.SEVERITY_ERROR for i in issues)
        has_warnings = any(i.severity == LintIssue.SEVERITY_WARNING for i in issues)

        if has_errors:
            marker = "X"
        elif has_warnings:
            marker = "!"
        else:
            marker = "o"

        print(f"{marker} {corr_id}: {from_node} --{edge_type}--> {to_node} [T{tier}/{assertion}]")
        if e.get('claim_text'):
            # Truncate long claims
            claim = e['claim_text'][:60] + "..." if len(e.get('claim_text', '')) > 60 else e['claim_text']
            print(f"    {claim}")
        for issue in issues:
            icon = "X" if issue.severity == "ERROR" else "!"
            print(f"    {icon} {issue.message}")


def check_node_exists(db, node_id: str) -> bool:
    """Check if a node exists in the database."""
    node = db.get_node(node_id)
    return node is not None


def load_correction(db, entry: dict, dry_run: bool = False) -> dict:
    """Load a single correction entry through staging.

    Returns:
        Dict with result status
    """
    corr_id = entry.get('id')
    from_node = entry.get('from_node_id')
    to_node = entry.get('to_node_id')
    edge_type = entry.get('edge_type')

    result = {
        'corr_id': corr_id,
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

    # Check if nodes exist (just record, don't fail - we'll propose them)
    missing_nodes = []
    if not check_node_exists(db, from_node):
        missing_nodes.append(from_node)
    if not check_node_exists(db, to_node):
        missing_nodes.append(to_node)

    result['missing_nodes'] = missing_nodes

    # Generate proposal
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    proposal_id = f"FGIP-PROPOSED-CORRECTION-{timestamp}-{corr_id}"

    # Create claim first
    claim_id = f"FGIP-PROPOSED-CORRECTION-CLAIM-{timestamp}-{corr_id}"

    claim = ProposedClaim(
        proposal_id=claim_id,
        claim_text=entry.get('claim_text', ''),
        topic='CorrectionLayer',
        agent_name='correction_loader',
        source_url=entry.get('source_url'),
        reasoning=f"Correction layer manifest: {corr_id}. Tier {entry.get('tier_hint', '?')}.",
        promotion_requirement=entry.get('promotion_requirement'),
    )

    edge = ProposedEdge(
        proposal_id=proposal_id,
        from_node=from_node,
        to_node=to_node,
        relationship=edge_type,
        agent_name='correction_loader',
        detail=entry.get('claim_text'),
        proposed_claim_id=claim_id,
        confidence=0.9 if entry.get('tier_hint') == 0 else 0.8,
        reasoning=f"From correction manifest: {corr_id}. Assertion level: {entry.get('assertion_level', 'FACT')}",
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

    # Propose missing nodes (skip if already proposed in this session)
    global _proposed_nodes
    actually_proposed = []
    for node_id in missing_nodes:
        if node_id in _proposed_nodes:
            continue  # Already proposed in this session

        node_proposal_id = f"FGIP-PROPOSED-CORRECTION-NODE-{timestamp}-{node_id[:20]}"
        node_type = infer_node_type(node_id, edge_type)
        node_name = node_id.replace('-', ' ').title()

        # Check if already in proposed_nodes table
        existing = conn.execute(
            "SELECT 1 FROM proposed_nodes WHERE node_id = ? AND status = 'PENDING'",
            (node_id,)
        ).fetchone()
        if existing:
            _proposed_nodes.add(node_id)
            continue

        conn.execute(
            """INSERT INTO proposed_nodes
               (proposal_id, node_id, node_type, name, agent_name,
                reasoning, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?)""",
            (node_proposal_id, node_id, node_type, node_name,
             'correction_loader', f'Node from correction manifest: {corr_id}',
             datetime.utcnow().isoformat() + 'Z')
        )
        _proposed_nodes.add(node_id)
        actually_proposed.append(node_id)

    result['missing_nodes'] = actually_proposed  # Only report newly proposed

    conn.commit()

    result['status'] = 'proposed'
    result['proposal_id'] = proposal_id
    return result


def infer_node_type(node_id: str, edge_type: str) -> str:
    """Infer node type from node_id and edge context."""
    node_lower = node_id.lower()

    # Agency indicators
    if any(agency in node_lower for agency in ['fdic', 'sec', 'treasury', 'commerce']):
        return "AGENCY"

    # Legislation/Act indicators
    if 'act' in node_lower:
        return "LEGISLATION"

    # Location indicators
    if any(loc in node_lower for loc in ['ohio', 'texas', 'arizona', 'georgia', 'indiana']):
        return "LOCATION"

    # Company indicators
    if any(co in node_lower for co in ['intel', 'tsmc', 'samsung', 'micron']):
        return "COMPANY"

    # Policy indicators
    if any(pol in node_lower for pol in ['framework', 'stablecoin', 'cbdc']):
        return "POLICY"

    # Default based on edge type
    if edge_type in ('AWARDED_GRANT', 'AWARDED_CONTRACT'):
        return "COMPANY"
    elif edge_type in ('RULEMAKING_FOR', 'IMPLEMENTED_BY'):
        return "AGENCY"
    elif edge_type == 'BUILT_IN':
        return "LOCATION"

    return "ORGANIZATION"


# Track proposed nodes globally to avoid duplicates
_proposed_nodes = set()


def main():
    global _proposed_nodes
    _proposed_nodes = set()  # Reset at start

    parser = argparse.ArgumentParser(description='Correction Layer Loader')
    parser.add_argument('--batch', type=int, help='Load first N pending corrections')
    parser.add_argument('--id', dest='corr_id', help='Load specific correction by ID')
    parser.add_argument('--skip', help='Mark correction as skipped with reason')
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
                print(f"Marked {args.skip} as SKIPPED: {args.skip_reason}")
                return
        print(f"Correction not found: {args.skip}", file=sys.stderr)
        sys.exit(1)

    # Load specific correction
    if args.corr_id:
        for entry in entries:
            if entry.get('id') == args.corr_id:
                if entry.get('status') != 'PENDING':
                    print(f"Correction {args.corr_id} is not PENDING (status: {entry.get('status')})")
                    return

                result = load_correction(db, entry, dry_run=args.dry_run)

                if result['status'] == 'proposed':
                    print(f"Proposed: {result['proposal_id']}")
                    if result['missing_nodes']:
                        print(f"  Also proposed nodes: {', '.join(result['missing_nodes'])}")
                    entry['status'] = 'STAGED'
                    save_manifest(entries)
                elif result['status'] == 'would_propose':
                    print(f"Would propose: {result['proposal_id']}")
                    if result['missing_nodes']:
                        print(f"  Would also propose nodes: {', '.join(result['missing_nodes'])}")
                elif result['status'] == 'prelint_failed':
                    print(f"X Prelint failed:")
                    for issue in result['issues']:
                        print(f"    {issue}")
                return

        print(f"Correction not found: {args.corr_id}", file=sys.stderr)
        sys.exit(1)

    # Batch mode
    if args.batch:
        pending = [e for e in entries if e.get('status') == 'PENDING'][:args.batch]

        if not pending:
            print("No pending corrections to load.")
            return

        print(f"\n=== Loading {len(pending)} corrections ===\n")

        proposed = 0
        failed = 0

        for entry in pending:
            corr_id = entry.get('id')
            result = load_correction(db, entry, dry_run=args.dry_run)

            if result['status'] == 'proposed':
                print(f"o {corr_id}: Proposed as {result['proposal_id']}")
                if result['missing_nodes']:
                    print(f"    + nodes: {', '.join(result['missing_nodes'])}")
                entry['status'] = 'STAGED'
                proposed += 1
            elif result['status'] == 'would_propose':
                print(f"o {corr_id}: Would propose")
                proposed += 1
            elif result['status'] == 'prelint_failed':
                print(f"X {corr_id}: Prelint failed - {result['issues'][0]}")
                failed += 1

        if not args.dry_run:
            save_manifest(entries)

        print(f"\nSummary: {proposed} proposed, {failed} failed")
        return

    # Default: list pending
    list_pending(entries)


if __name__ == '__main__':
    main()
