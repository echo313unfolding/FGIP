#!/usr/bin/env python3
"""FGIP Wiki Lint — Graph health checks adapted from Karpathy's LLM Wiki pattern.

Checks:
  1. Orphan nodes (no edges)
  2. Unsourced edges (no claim_id and no source)
  3. Stale claims (not verified within decay window)
  4. Superseded chains (show what replaced what)
  5. Contradictions (CONTRADICTS / INVALIDATES edges)
  6. Dangling references (edges pointing to nonexistent nodes)
  7. Assertion level audit (inferential edges marked as FACT)

Usage:
  python3 tools/wiki_lint.py                    # Full lint
  python3 tools/wiki_lint.py --check orphans    # Single check
  python3 tools/wiki_lint.py --json             # Machine-readable output
  python3 tools/wiki_lint.py --fix-staleness    # Run supersession migration
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fgip.db import FGIPDatabase
from fgip.schema import INFERENTIAL_EDGE_TYPES
from fgip.supersession import (
    migrate_supersession,
    get_stale_claims,
    DEFAULT_STALENESS_DAYS,
)


def check_orphan_nodes(db: FGIPDatabase) -> list[dict]:
    """Find nodes with no edges (neither from nor to)."""
    conn = db.connect()
    rows = conn.execute(
        """SELECT n.node_id, n.node_type, n.name
           FROM nodes n
           LEFT JOIN edges e_from ON n.node_id = e_from.from_node_id
           LEFT JOIN edges e_to ON n.node_id = e_to.to_node_id
           WHERE e_from.edge_id IS NULL AND e_to.edge_id IS NULL
           ORDER BY n.node_type, n.name"""
    ).fetchall()
    return [{"node_id": r[0], "node_type": r[1], "name": r[2]} for r in rows]


def check_unsourced_edges(db: FGIPDatabase) -> list[dict]:
    """Find edges with neither claim_id nor source."""
    conn = db.connect()
    rows = conn.execute(
        """SELECT edge_id, edge_type, from_node_id, to_node_id, assertion_level
           FROM edges
           WHERE claim_id IS NULL AND (source IS NULL OR source = '')
           ORDER BY edge_type"""
    ).fetchall()
    return [
        {"edge_id": r[0], "edge_type": r[1], "from": r[2], "to": r[3],
         "assertion_level": r[4]}
        for r in rows
    ]


def check_contradictions(db: FGIPDatabase) -> list[dict]:
    """Find active CONTRADICTS and INVALIDATES edges."""
    conn = db.connect()
    rows = conn.execute(
        """SELECT e.edge_id, e.edge_type, e.from_node_id, e.to_node_id,
                  e.confidence, e.notes
           FROM edges e
           WHERE e.edge_type IN ('CONTRADICTS', 'INVALIDATES', 'WEAKENS',
                                  'FALSIFIED_BY', 'DID_NOT_MATERIALIZE')
           ORDER BY e.edge_type"""
    ).fetchall()
    return [
        {"edge_id": r[0], "type": r[1], "from": r[2], "to": r[3],
         "confidence": r[4], "notes": (r[5] or "")[:100]}
        for r in rows
    ]


def check_dangling_refs(db: FGIPDatabase) -> list[dict]:
    """Find edges pointing to nonexistent nodes."""
    conn = db.connect()
    rows = conn.execute(
        """SELECT e.edge_id, e.edge_type, e.from_node_id, e.to_node_id
           FROM edges e
           LEFT JOIN nodes n_from ON e.from_node_id = n_from.node_id
           LEFT JOIN nodes n_to ON e.to_node_id = n_to.node_id
           WHERE n_from.node_id IS NULL OR n_to.node_id IS NULL"""
    ).fetchall()
    results = []
    for r in rows:
        missing = []
        from_exists = db.get_node(r[2])
        to_exists = db.get_node(r[3])
        if not from_exists:
            missing.append(f"from:{r[2]}")
        if not to_exists:
            missing.append(f"to:{r[3]}")
        results.append({
            "edge_id": r[0], "edge_type": r[1],
            "missing_nodes": missing,
        })
    return results


def check_assertion_mismatches(db: FGIPDatabase) -> list[dict]:
    """Find inferential edges incorrectly marked as FACT."""
    conn = db.connect()
    placeholders = ",".join(f"'{t}'" for t in INFERENTIAL_EDGE_TYPES)
    rows = conn.execute(
        f"""SELECT edge_id, edge_type, assertion_level, from_node_id, to_node_id
           FROM edges
           WHERE edge_type IN ({placeholders})
             AND assertion_level = 'FACT'"""
    ).fetchall()
    return [
        {"edge_id": r[0], "edge_type": r[1], "assertion_level": r[2],
         "expected": "INFERENCE or HYPOTHESIS", "from": r[3], "to": r[4]}
        for r in rows
    ]


def check_superseded_claims(db: FGIPDatabase) -> list[dict]:
    """Find claims that have been superseded (for audit trail)."""
    conn = db.connect()
    try:
        rows = conn.execute(
            """SELECT claim_id, claim_text, superseded_by, topic
               FROM claims
               WHERE superseded_by IS NOT NULL
               ORDER BY claim_id"""
        ).fetchall()
    except Exception:
        return []  # Column doesn't exist yet
    return [
        {"claim_id": r[0], "claim_text": r[1][:100], "superseded_by": r[2],
         "topic": r[3]}
        for r in rows
    ]


def run_lint(db: FGIPDatabase, checks: list[str] | None = None,
             staleness_days: int = DEFAULT_STALENESS_DAYS) -> dict:
    """Run all or selected lint checks. Returns structured report."""
    all_checks = {
        "orphans": ("Orphan nodes (no edges)", check_orphan_nodes),
        "unsourced": ("Unsourced edges (no claim/source)", check_unsourced_edges),
        "stale": ("Stale claims (not re-verified)", None),  # Special handling
        "contradictions": ("Active contradictions/invalidations", check_contradictions),
        "dangling": ("Dangling edge references", check_dangling_refs),
        "assertions": ("Assertion level mismatches", check_assertion_mismatches),
        "superseded": ("Superseded claims (audit trail)", check_superseded_claims),
    }

    if checks:
        selected = {k: v for k, v in all_checks.items() if k in checks}
    else:
        selected = all_checks

    report = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "checks_run": list(selected.keys()),
        "results": {},
        "summary": {},
    }

    total_issues = 0
    for check_name, (description, check_fn) in selected.items():
        if check_name == "stale":
            results = get_stale_claims(db, staleness_days)
        else:
            results = check_fn(db)

        report["results"][check_name] = {
            "description": description,
            "count": len(results),
            "items": results,
        }
        total_issues += len(results)

    # Graph stats for context
    stats = db.get_stats()
    report["summary"] = {
        "total_issues": total_issues,
        "nodes": stats["nodes"],
        "edges": stats["edges"],
        "claims": stats["claims"],
        "sources": stats["sources"],
        "evidence_coverage": f"{stats['evidence_coverage']:.1%}",
    }

    return report


def print_report(report: dict):
    """Pretty-print lint report."""
    print(f"\n{'='*60}")
    print(f"  FGIP Wiki Lint Report — {report['timestamp'][:19]}")
    print(f"{'='*60}")
    print(f"  Graph: {report['summary']['nodes']} nodes, "
          f"{report['summary']['edges']} edges, "
          f"{report['summary']['claims']} claims, "
          f"{report['summary']['sources']} sources")
    print(f"  Evidence coverage: {report['summary']['evidence_coverage']}")
    print(f"{'='*60}\n")

    for check_name, result in report["results"].items():
        count = result["count"]
        icon = "PASS" if count == 0 else f"WARN ({count})"
        print(f"  [{icon}] {result['description']}")

        if count > 0 and count <= 10:
            for item in result["items"]:
                # Format based on check type
                if "node_id" in item:
                    print(f"    - {item['node_type']}: {item['name']} ({item['node_id']})")
                elif "claim_id" in item and "days_stale" in item:
                    print(f"    - {item['claim_id']}: {item['claim_text']} "
                          f"(stale {item['days_stale']}d)")
                elif "edge_id" in item:
                    detail = item.get("edge_type", item.get("type", ""))
                    print(f"    - {item['edge_id']}: {detail}")
        elif count > 10:
            for item in result["items"][:5]:
                if "node_id" in item:
                    print(f"    - {item['node_type']}: {item['name']}")
                elif "claim_id" in item:
                    print(f"    - {item['claim_id']}: {item.get('claim_text', '')[:80]}")
                elif "edge_id" in item:
                    print(f"    - {item['edge_id']}")
            print(f"    ... and {count - 5} more")
        print()

    total = report["summary"]["total_issues"]
    if total == 0:
        print(f"  CLEAN — no issues found.\n")
    else:
        print(f"  TOTAL: {total} issues across {len(report['results'])} checks.\n")


def main():
    parser = argparse.ArgumentParser(description="FGIP Wiki Lint")
    parser.add_argument("--db", default="fgip.db", help="Database path")
    parser.add_argument("--check", help="Run single check (orphans|unsourced|stale|contradictions|dangling|assertions|superseded)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--staleness-days", type=int, default=DEFAULT_STALENESS_DAYS,
                        help=f"Days before a claim is stale (default: {DEFAULT_STALENESS_DAYS})")
    parser.add_argument("--fix-staleness", action="store_true",
                        help="Run supersession migration (adds staleness columns)")
    args = parser.parse_args()

    db = FGIPDatabase(args.db)
    db.connect()

    if args.fix_staleness:
        migrate_supersession(db)
        print("Supersession migration complete.")
        return

    checks = [args.check] if args.check else None
    report = run_lint(db, checks, args.staleness_days)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report)

    db.close()

    # Exit with non-zero if issues found
    sys.exit(1 if report["summary"]["total_issues"] > 0 else 0)


if __name__ == "__main__":
    main()
