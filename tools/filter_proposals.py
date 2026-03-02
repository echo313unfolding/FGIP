#!/usr/bin/env python3
"""FGIP Proposal Filter - Hughes-style triage for pending proposals.

Runs integrity checks on pending proposals and:
1. Flags manipulation markers (DEPRIORITIZE)
2. Boosts proposals with primary source evidence (FAST_TRACK)
3. Routes ambiguous proposals for HUMAN_REVIEW

Usage:
    python3 tools/filter_proposals.py fgip.db
    python3 tools/filter_proposals.py fgip.db --apply  # Actually update statuses
    python3 tools/filter_proposals.py fgip.db --agent rss  # Filter specific agent
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fgip.db import FGIPDatabase


# Tier mapping by agent
AGENT_TIERS = {
    # Tier 0 - Government primary
    'edgar': 0, 'usaspending': 0, 'federal_register': 0, 'congress': 0,
    'tic': 0, 'fec': 0, 'fara': 0, 'scotus': 0, 'gao': 0,
    'chips-facility': 0, 'nuclear-smr': 0, 'nuclear_smr': 0,
    # Tier 1 - Official secondary / journalism
    'rss': 1, 'opensecrets': 1,
    # Tier 2 - Commentary
    'promethean': 2, 'youtube': 2, 'stablecoin': 2,
    # Tier 3 - Meta-analysis
    'causal': 3, 'reasoning': 3, 'supply_chain_extractor': 3,
    'gap_detector': 3, 'coverage_analyzer': 3,
}

# Manipulation markers in reasoning/notes
MANIPULATION_PATTERNS = [
    (r'everyone knows', "APPEAL_TO_COMMON_KNOWLEDGE", -0.2),
    (r'obviously|clearly|undeniably', "FALSE_CERTAINTY", -0.1),
    (r'shocking|horrifying|disgusting', "HIGH_EMOTION", -0.15),
    (r'bombshell|explosive|breaking', "SENSATIONALISM", -0.1),
    (r'100%|guaranteed|certain', "ABSOLUTE_CERTAINTY", -0.1),
]

# Evidence quality markers in reasoning/notes
EVIDENCE_PATTERNS = [
    (r'(?:SEC|DOJ|Treasury|GAO|CBO|Fed|FDIC|OCC)\s+(?:filing|report|data)', "AGENCY_CITATION", 0.15),
    (r'(?:Form\s+)?(?:10-K|10-Q|8-K|13F|S-1)', "SEC_FILING", 0.2),
    (r'\$[\d,]+(?:\.\d+)?[BMK]?\b', "SPECIFIC_AMOUNT", 0.1),
    (r'\d+(?:\.\d+)?%', "SPECIFIC_PERCENTAGE", 0.05),
    (r'(?:H\.R\.|S\.)\s*\d+', "BILL_CITATION", 0.15),
    (r'(?:Public Law|P\.L\.)\s+\d+-\d+', "LAW_CITATION", 0.15),
    (r'usaspending\.gov|sec\.gov|congress\.gov|federalregister\.gov', "GOV_SOURCE", 0.2),
]


def analyze_proposal(proposal: dict) -> dict:
    """Analyze a single proposal for integrity signals."""
    agent = proposal.get('agent_name', '')
    reasoning = proposal.get('reasoning', '') or ''
    confidence = proposal.get('confidence', 0.5)

    tier = AGENT_TIERS.get(agent, 3)

    # Start with tier-based score
    tier_bonus = {0: 0.2, 1: 0.1, 2: 0.0, 3: -0.1}.get(tier, 0)

    # Check manipulation patterns
    manipulation_flags = []
    manipulation_penalty = 0
    for pattern, flag, penalty in MANIPULATION_PATTERNS:
        if re.search(pattern, reasoning, re.IGNORECASE):
            manipulation_flags.append(flag)
            manipulation_penalty += penalty

    # Check evidence patterns
    evidence_flags = []
    evidence_bonus = 0
    for pattern, flag, bonus in EVIDENCE_PATTERNS:
        if re.search(pattern, reasoning, re.IGNORECASE):
            evidence_flags.append(flag)
            evidence_bonus += bonus

    # Calculate adjusted score
    adjusted_confidence = confidence + tier_bonus + evidence_bonus + manipulation_penalty
    adjusted_confidence = max(0, min(1, adjusted_confidence))  # Clamp 0-1

    # Determine route
    if manipulation_flags and not evidence_flags:
        route = "DEPRIORITIZE"
    elif tier == 0 and adjusted_confidence >= 0.85:
        route = "FAST_TRACK"
    elif evidence_flags and adjusted_confidence >= 0.75:
        route = "FAST_TRACK"
    elif adjusted_confidence < 0.5 or manipulation_flags:
        route = "DEPRIORITIZE"
    else:
        route = "HUMAN_REVIEW"

    return {
        'proposal_id': proposal.get('proposal_id'),
        'agent': agent,
        'tier': tier,
        'original_confidence': confidence,
        'adjusted_confidence': round(adjusted_confidence, 3),
        'route': route,
        'manipulation_flags': manipulation_flags,
        'evidence_flags': evidence_flags,
        'edge': f"{proposal.get('from_node', '?')} --{proposal.get('relationship', '?')}--> {proposal.get('to_node', '?')}",
    }


def filter_proposals(db_path: str, agent_filter: str = None) -> dict:
    """Filter all pending proposals."""
    db = FGIPDatabase(db_path)
    conn = db.connect()

    # Get pending proposals
    query = """
        SELECT proposal_id, from_node, to_node, relationship,
               confidence, agent_name, reasoning
        FROM proposed_edges
        WHERE status = 'PENDING'
    """
    params = []
    if agent_filter:
        query += " AND agent_name = ?"
        params.append(agent_filter)

    proposals = conn.execute(query, params).fetchall()

    results = {
        'FAST_TRACK': [],
        'HUMAN_REVIEW': [],
        'DEPRIORITIZE': [],
    }

    for p in proposals:
        proposal = {
            'proposal_id': p[0],
            'from_node': p[1],
            'to_node': p[2],
            'relationship': p[3],
            'confidence': p[4],
            'agent_name': p[5],
            'reasoning': p[6],
        }
        analysis = analyze_proposal(proposal)
        results[analysis['route']].append(analysis)

    return results


def apply_filter_results(db_path: str, results: dict) -> dict:
    """Apply filter results - deprioritize flagged proposals."""
    db = FGIPDatabase(db_path)
    conn = db.connect()

    stats = {'deprioritized': 0, 'boosted': 0}

    # Mark DEPRIORITIZE proposals as REJECTED with reason
    for item in results['DEPRIORITIZE']:
        conn.execute("""
            UPDATE proposed_edges
            SET status = 'REJECTED',
                reasoning = COALESCE(reasoning, '') || ' [FILTER: ' || ? || ']'
            WHERE proposal_id = ?
        """, (','.join(item['manipulation_flags']), item['proposal_id']))
        stats['deprioritized'] += 1

    # Boost FAST_TRACK confidence (cap at 0.95 to avoid auto-approve of narrative)
    for item in results['FAST_TRACK']:
        if item['adjusted_confidence'] > item['original_confidence']:
            new_conf = min(0.95, item['adjusted_confidence'])
            conn.execute("""
                UPDATE proposed_edges
                SET confidence = ?,
                    reasoning = COALESCE(reasoning, '') || ' [FILTER: ' || ? || ']'
                WHERE proposal_id = ?
            """, (new_conf, ','.join(item['evidence_flags']), item['proposal_id']))
            stats['boosted'] += 1

    conn.commit()
    return stats


def main():
    parser = argparse.ArgumentParser(description="FGIP Proposal Filter")
    parser.add_argument("db", type=str, help="Database path")
    parser.add_argument("--agent", type=str, help="Filter specific agent")
    parser.add_argument("--apply", action="store_true", help="Apply filter decisions")
    parser.add_argument("--json", action="store_true", help="JSON output")

    args = parser.parse_args()

    results = filter_proposals(args.db, args.agent)

    if args.apply:
        stats = apply_filter_results(args.db, results)

    if args.json:
        print(json.dumps({
            'fast_track': len(results['FAST_TRACK']),
            'human_review': len(results['HUMAN_REVIEW']),
            'deprioritize': len(results['DEPRIORITIZE']),
            'applied': args.apply,
            'stats': stats if args.apply else None,
        }, indent=2))
    else:
        print("=" * 60)
        print("  FGIP PROPOSAL FILTER (Hughes-Style Triage)")
        print("=" * 60)
        print(f"  FAST_TRACK (high evidence):    {len(results['FAST_TRACK'])}")
        print(f"  HUMAN_REVIEW (ambiguous):      {len(results['HUMAN_REVIEW'])}")
        print(f"  DEPRIORITIZE (manipulation):   {len(results['DEPRIORITIZE'])}")
        print()

        if results['DEPRIORITIZE']:
            print("  DEPRIORITIZED (narrative goo):")
            for item in results['DEPRIORITIZE'][:10]:
                print(f"    [{item['agent']}] {item['edge']}")
                print(f"      Flags: {', '.join(item['manipulation_flags'])}")
            if len(results['DEPRIORITIZE']) > 10:
                print(f"    ... and {len(results['DEPRIORITIZE']) - 10} more")
            print()

        if results['FAST_TRACK']:
            print("  FAST_TRACK (high evidence):")
            for item in results['FAST_TRACK'][:5]:
                print(f"    [{item['agent']}] {item['edge']}")
                print(f"      Evidence: {', '.join(item['evidence_flags'])}")
            if len(results['FAST_TRACK']) > 5:
                print(f"    ... and {len(results['FAST_TRACK']) - 5} more")
            print()

        if args.apply:
            print(f"  APPLIED: {stats['deprioritized']} deprioritized, {stats['boosted']} boosted")
        else:
            print("  Use --apply to apply filter decisions")

        print("=" * 60)


if __name__ == "__main__":
    main()
