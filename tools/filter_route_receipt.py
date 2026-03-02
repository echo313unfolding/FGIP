#!/usr/bin/env python3
"""FilterAgent Route Distribution Receipt.

Samples artifacts from artifact_queue and reports route distribution.
Verifies Tier-0 sources are rarely deprioritized.

Usage:
    python3 tools/filter_route_receipt.py fgip.db
    python3 tools/filter_route_receipt.py fgip.db --sample-size 200
    python3 tools/filter_route_receipt.py fgip.db --json

Exit Codes:
    0: Tier-0 deprioritization below threshold (healthy)
    1: Tier-0 deprioritization above threshold (needs attention)
    2: Runtime error
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fgip.db import FGIPDatabase

# Tier-0 sources (authoritative government/primary sources)
TIER_0_SOURCES = {
    "edgar",
    "congress",
    "federal_register",
    "tic",
    "usaspending",
    "fec",
    "fred",
    "bls",
    "census",
    "treasury",
}

# Threshold: if >5% of Tier-0 artifacts are deprioritized, flag it
TIER0_DEPRIORITIZE_THRESHOLD = 0.05


def get_git_commit() -> str:
    """Get current git commit hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        return result.stdout.strip()[:12] if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def main():
    parser = argparse.ArgumentParser(description="FilterAgent Route Distribution Receipt")
    parser.add_argument("db", nargs="?", default="fgip.db", help="Database path")
    parser.add_argument("--json", action="store_true", help="JSON output only")
    parser.add_argument("--sample-size", type=int, default=0, help="Limit sample size (0=all)")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "receipts" / "filter_route"
    )

    args = parser.parse_args()

    try:
        db = FGIPDatabase(args.db)
        conn = db.connect()
    except Exception as e:
        print(f"Error opening database: {e}", file=sys.stderr)
        sys.exit(2)

    # 1. Query overall route distribution
    overall_sql = """
        SELECT route, COUNT(*) as cnt
        FROM artifact_queue
        WHERE status IN ('FILTERED', 'EXTRACTED', 'PENDING')
        GROUP BY route
    """
    overall_rows = conn.execute(overall_sql).fetchall()
    overall_distribution = {row[0] or "NULL": row[1] for row in overall_rows}

    # 2. Distribution by source_id
    by_source_sql = """
        SELECT source_id, route, COUNT(*) as cnt
        FROM artifact_queue
        WHERE status IN ('FILTERED', 'EXTRACTED', 'PENDING')
        GROUP BY source_id, route
        ORDER BY source_id, route
    """
    by_source_rows = conn.execute(by_source_sql).fetchall()

    # Organize by source
    by_source = {}
    for row in by_source_rows:
        source_id = row[0] or "unknown"
        route = row[1] or "NULL"
        cnt = row[2]
        if source_id not in by_source:
            by_source[source_id] = {}
        by_source[source_id][route] = cnt

    # 3. Score percentiles
    percentiles_sql = """
        SELECT
            MIN(filter_score) as p0,
            AVG(filter_score) as p50,
            MAX(filter_score) as p100
        FROM artifact_queue
        WHERE filter_score IS NOT NULL
    """
    percentiles_row = conn.execute(percentiles_sql).fetchone()
    score_percentiles = {
        "min": round(percentiles_row[0], 3) if percentiles_row[0] else None,
        "avg": round(percentiles_row[1], 3) if percentiles_row[1] else None,
        "max": round(percentiles_row[2], 3) if percentiles_row[2] else None,
    }

    # 4. Check Tier-0 deprioritization (should be rare)
    tier0_list = ", ".join(f"'{s}'" for s in TIER_0_SOURCES)
    tier0_deprioritized_sql = f"""
        SELECT source_id, COUNT(*) as cnt
        FROM artifact_queue
        WHERE route = 'DEPRIORITIZE'
        AND source_id IN ({tier0_list})
        GROUP BY source_id
    """
    tier0_deprioritized_rows = conn.execute(tier0_deprioritized_sql).fetchall()
    tier0_deprioritized = {row[0]: row[1] for row in tier0_deprioritized_rows}

    # Get total Tier-0 count for percentage
    tier0_total_sql = f"""
        SELECT COUNT(*) FROM artifact_queue
        WHERE source_id IN ({tier0_list})
    """
    tier0_total = conn.execute(tier0_total_sql).fetchone()[0]

    tier0_deprioritized_total = sum(tier0_deprioritized.values())
    tier0_deprioritized_rate = (
        tier0_deprioritized_total / tier0_total if tier0_total > 0 else 0.0
    )

    # 5. Total counts
    total_sql = """
        SELECT COUNT(*) FROM artifact_queue
    """
    total_artifacts = conn.execute(total_sql).fetchone()[0]

    # 6. Build receipt
    all_pass = tier0_deprioritized_rate < TIER0_DEPRIORITIZE_THRESHOLD

    receipt = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": get_git_commit(),
        "total_artifacts": total_artifacts,
        "overall_distribution": overall_distribution,
        "by_source": by_source,
        "score_percentiles": score_percentiles,
        "tier0_summary": {
            "total": tier0_total,
            "deprioritized": tier0_deprioritized_total,
            "deprioritize_rate": round(tier0_deprioritized_rate, 4),
            "threshold": TIER0_DEPRIORITIZE_THRESHOLD,
            "breakdown": tier0_deprioritized,
        },
        "pass": all_pass,
    }

    # Output
    if args.json:
        print(json.dumps(receipt, indent=2))
    else:
        print("=" * 60)
        print("  FILTERAGENT ROUTE DISTRIBUTION RECEIPT")
        print("=" * 60)
        print()
        print(f"  Total artifacts: {total_artifacts}")
        print()
        print("  Overall Distribution:")
        for route, cnt in sorted(overall_distribution.items()):
            pct = cnt / total_artifacts * 100 if total_artifacts > 0 else 0
            print(f"    {route or 'NULL':20} {cnt:5} ({pct:5.1f}%)")
        print()
        print("  Score Percentiles:")
        print(f"    Min: {score_percentiles['min']}")
        print(f"    Avg: {score_percentiles['avg']}")
        print(f"    Max: {score_percentiles['max']}")
        print()
        print("  Tier-0 Deprioritization Check:")
        print(f"    Total Tier-0 artifacts: {tier0_total}")
        print(f"    Deprioritized: {tier0_deprioritized_total} ({tier0_deprioritized_rate:.1%})")
        print(f"    Threshold: {TIER0_DEPRIORITIZE_THRESHOLD:.0%}")
        if tier0_deprioritized:
            print("    Breakdown:")
            for source, cnt in tier0_deprioritized.items():
                print(f"      {source}: {cnt}")
        print()
        print(f"  Result: {'PASS' if all_pass else 'ATTENTION NEEDED'}")
        print("=" * 60)

    # Write receipt
    args.output.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    receipt_path = args.output / f"route_{ts}.json"
    receipt_path.write_text(json.dumps(receipt, indent=2))

    if not args.json:
        print(f"\nReceipt: {receipt_path}")

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
