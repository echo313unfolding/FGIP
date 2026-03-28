"""
CLI entry point for Decision Node management.

Usage:
    python3 -m fgip.decisions --create-condo
    python3 -m fgip.decisions --status CONDO_DECISION_2026
    python3 -m fgip.decisions --check-gate CONDO_DECISION_2026 location_score GREEN
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .node import DecisionNode, DecisionStatus, DecisionPhase, create_condo_decision_2026
from .gate import GateStatus
from .community import CommunityStatus
from .evidence import create_evidence, EvidenceType


def main():
    parser = argparse.ArgumentParser(
        description="FGIP Decision Node Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python3 -m fgip.decisions --create-condo
    python3 -m fgip.decisions --status CONDO_DECISION_2026
    python3 -m fgip.decisions --gates CONDO_DECISION_2026
    python3 -m fgip.decisions --communities CONDO_DECISION_2026
    python3 -m fgip.decisions --check-gate CONDO_DECISION_2026 insurance_verified PENDING "Awaiting quotes"
        """
    )

    # Mode selection
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--create-condo", action="store_true",
                      help="Create CONDO_DECISION_2026 node")
    mode.add_argument("--status", type=str, metavar="ID",
                      help="Show decision status")
    mode.add_argument("--gates", type=str, metavar="ID",
                      help="Show gate status")
    mode.add_argument("--communities", type=str, metavar="ID",
                      help="Show communities")
    mode.add_argument("--check-gate", nargs=4, metavar=("ID", "GATE", "STATUS", "EVIDENCE"),
                      help="Check a gate: decision_id gate_id status evidence")
    mode.add_argument("--update-community", nargs=4, metavar=("ID", "COMMUNITY", "STATUS", "REASON"),
                      help="Update community status")
    mode.add_argument("--add-evidence", nargs=5, metavar=("ID", "TYPE", "DESC", "SOURCE", "SUMMARY"),
                      help="Add evidence to decision")
    mode.add_argument("--list", action="store_true",
                      help="List all decisions")

    # Options
    parser.add_argument("--json", action="store_true",
                        help="Output JSON")
    parser.add_argument("--output", type=str, default="receipts/decisions",
                        help="Output directory")

    args = parser.parse_args()

    if args.create_condo:
        _create_condo(args)
    elif args.status:
        _show_status(args)
    elif args.gates:
        _show_gates(args)
    elif args.communities:
        _show_communities(args)
    elif args.check_gate:
        _check_gate(args)
    elif args.update_community:
        _update_community(args)
    elif args.add_evidence:
        _add_evidence(args)
    elif args.list:
        _list_decisions(args)


def _create_condo(args):
    """Create CONDO_DECISION_2026 node."""
    node = create_condo_decision_2026()
    json_path, md_path = node.save(args.output)

    if args.json:
        print(json.dumps(node.to_dict(), indent=2))
    else:
        print(f"Created decision node: {node.decision_id}")
        print(f"  JSON: {json_path}")
        print(f"  Report: {md_path}")
        print()
        print(f"Status: {node.status.value}")
        print(f"Phase: {node.phase.value}")
        print(f"Gates: {len(node.gates)} ({node.get_gate_summary()})")
        print(f"Communities: {len(node.communities)}")
        print()
        print("Gate 4 (Location Score) auto-checked GREEN from scorer data.")


def _show_status(args):
    """Show decision status."""
    node = DecisionNode.load(args.status, args.output)
    if not node:
        print(f"Decision not found: {args.status}")
        return

    if args.json:
        print(json.dumps(node.to_dict(), indent=2))
    else:
        print(node.generate_status_report())


def _show_gates(args):
    """Show gate status."""
    node = DecisionNode.load(args.gates, args.output)
    if not node:
        print(f"Decision not found: {args.gates}")
        return

    if args.json:
        print(json.dumps([g.to_dict() for g in node.gates], indent=2))
    else:
        print(f"# Gates for {node.decision_id}")
        print()
        print(f"Summary: {node.get_gate_summary()}")
        print()

        for gate in sorted(node.gates, key=lambda g: g.gate_number):
            status_icon = {
                GateStatus.GREEN: "[PASS]",
                GateStatus.RED: "[FAIL]",
                GateStatus.AMBER: "[WARN]",
                GateStatus.PENDING: "[....]",
                GateStatus.NOT_STARTED: "[    ]",
            }.get(gate.status, "[????]")

            print(f"{status_icon} Gate {gate.gate_number}: {gate.name}")
            print(f"        Criteria: {gate.criteria}")

            last = gate.latest_check()
            if last:
                print(f"        Last check: {last.checked_at[:10]} - {last.evidence[:60]}...")
            print()


def _show_communities(args):
    """Show communities."""
    node = DecisionNode.load(args.communities, args.output)
    if not node:
        print(f"Decision not found: {args.communities}")
        return

    if args.json:
        print(json.dumps([c.to_dict() for c in node.communities], indent=2))
    else:
        print(f"# Communities for {node.decision_id}")
        print()

        by_status = {}
        for c in node.communities:
            if c.status.value not in by_status:
                by_status[c.status.value] = []
            by_status[c.status.value].append(c)

        for status, communities in by_status.items():
            print(f"## {status} ({len(communities)})")
            print()
            for c in communities:
                gated = "Gated" if c.is_gated else "Open"
                age = "55+" if c.is_55_plus else "All ages"
                print(f"  - **{c.name}** ({c.area}, {c.county})")
                print(f"    ${c.price_range_low/1000:.0f}K-${c.price_range_high/1000:.0f}K | {gated} | {age}")
                if c.red_flags:
                    print(f"    Red flags: {', '.join(c.red_flags)}")
                print()


def _check_gate(args):
    """Check a gate."""
    decision_id, gate_id, status_str, evidence = args.check_gate

    node = DecisionNode.load(decision_id, args.output)
    if not node:
        print(f"Decision not found: {decision_id}")
        return

    try:
        status = GateStatus(status_str)
    except ValueError:
        print(f"Invalid status: {status_str}")
        print(f"Valid values: {[s.value for s in GateStatus]}")
        return

    check = node.check_gate(gate_id, status, evidence, "CLI", checked_by="user")
    if not check:
        print(f"Gate not found: {gate_id}")
        return

    node.save(args.output)

    print(f"Gate {gate_id} checked: {status.value}")
    print(f"Evidence: {evidence}")
    print()
    print(f"Current gate summary: {node.get_gate_summary()}")


def _update_community(args):
    """Update community status."""
    decision_id, community_id, status_str, reason = args.update_community

    node = DecisionNode.load(decision_id, args.output)
    if not node:
        print(f"Decision not found: {decision_id}")
        return

    try:
        status = CommunityStatus(status_str)
    except ValueError:
        print(f"Invalid status: {status_str}")
        print(f"Valid values: {[s.value for s in CommunityStatus]}")
        return

    community = node.get_community(community_id)
    if not community:
        print(f"Community not found: {community_id}")
        return

    node.update_community_status(community_id, status, reason)
    node.save(args.output)

    print(f"Community {community_id} updated: {status.value}")
    print(f"Reason: {reason}")


def _add_evidence(args):
    """Add evidence to decision."""
    decision_id, type_str, description, source, summary = args.add_evidence

    node = DecisionNode.load(decision_id, args.output)
    if not node:
        print(f"Decision not found: {decision_id}")
        return

    try:
        ev_type = EvidenceType(type_str)
    except ValueError:
        print(f"Invalid type: {type_str}")
        print(f"Valid values: {[t.value for t in EvidenceType]}")
        return

    ev = create_evidence(ev_type, description, source, summary, collected_by="user")
    node.add_evidence(ev)
    node.save(args.output)

    print(f"Evidence added: {ev.evidence_id}")
    print(f"Type: {ev_type.value}")
    print(f"Summary: {summary}")


def _list_decisions(args):
    """List all decisions."""
    decisions_dir = Path(args.output)
    if not decisions_dir.exists():
        print("No decisions found.")
        return

    decisions = []
    for d in decisions_dir.iterdir():
        if d.is_dir():
            json_path = d / "DECISION_NODE.json"
            if json_path.exists():
                with json_path.open() as f:
                    data = json.load(f)
                    decisions.append({
                        "id": data["decision_id"],
                        "title": data["title"],
                        "status": data["status"],
                        "phase": data["phase"],
                        "updated_at": data["updated_at"],
                    })

    if args.json:
        print(json.dumps(decisions, indent=2))
    else:
        print("# Decisions")
        print()
        for d in decisions:
            print(f"- **{d['id']}**: {d['title']}")
            print(f"  Status: {d['status']} | Phase: {d['phase']}")
            print(f"  Updated: {d['updated_at'][:10]}")
            print()


if __name__ == "__main__":
    main()
