#!/usr/bin/env python3
"""FilterAgent Tuning Verification Receipt.

Runs before/after comparison to verify tuning changes improve adversarial detection
without regressing easter egg or positive filter tests.

Usage:
    python3 tools/filter_tune_receipt.py fgip.db
    python3 tools/filter_tune_receipt.py fgip.db --json
    python3 tools/filter_tune_receipt.py fgip.db --baseline receipts/kat/BASELINE.json

Exit Codes:
    0: All targets met (adversarial >= 7/7, easter_eggs >= 11/11, positive >= 2/2)
    1: Some targets not met
    2: Runtime error
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fgip.db import FGIPDatabase
from fgip.tests.kat.runner import KATHarness


def main():
    parser = argparse.ArgumentParser(description="FilterAgent Tuning Receipt")
    parser.add_argument("db", nargs="?", default="fgip.db", help="Database path")
    parser.add_argument("--json", action="store_true", help="JSON output only")
    parser.add_argument("--baseline", type=Path, help="Compare against baseline receipt")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "receipts" / "filter_tune")

    args = parser.parse_args()

    db = FGIPDatabase(args.db)
    harness = KATHarness(db)

    # Run all KAT tests
    result = harness.run_all()

    # Categorize results
    easter_eggs = [r for r in result.results if r.test_type == "must_exist"]
    adversarial = [r for r in result.results if r.test_id.startswith("adversarial-")]
    positive = [r for r in result.results if r.test_id.startswith("good-")]

    # Calculate scores
    easter_score = sum(1 for r in easter_eggs if r.passed)
    adversarial_score = sum(1 for r in adversarial if r.passed)
    positive_score = sum(1 for r in positive if r.passed)

    targets = {
        "easter_eggs": {
            "target": 11,
            "actual": easter_score,
            "total": len(easter_eggs),
            "pass": easter_score >= 11
        },
        "adversarial": {
            "target": 7,
            "actual": adversarial_score,
            "total": len(adversarial),
            "pass": adversarial_score >= 7
        },
        "positive_filter": {
            "target": 2,
            "actual": positive_score,
            "total": len(positive),
            "pass": positive_score >= 2
        },
    }

    all_pass = all(t["pass"] for t in targets.values())

    # Load baseline for delta comparison
    delta = None
    baseline_summary = None
    if args.baseline and args.baseline.exists():
        try:
            baseline_data = json.loads(args.baseline.read_text())
            baseline_passed = baseline_data.get("passed", 0)
            delta = result.passed - baseline_passed
            baseline_summary = {
                "file": str(args.baseline),
                "passed": baseline_passed,
                "total": baseline_data.get("total", 0),
            }
        except Exception as e:
            baseline_summary = {"error": str(e)}

    # Build receipt
    receipt = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "targets": targets,
        "all_pass": all_pass,
        "total_tests": result.total,
        "total_passed": result.passed,
        "pass_rate": result.pass_rate,
        "delta_from_baseline": delta,
        "baseline": baseline_summary,
        "failed_tests": [
            {
                "id": r.test_id,
                "type": r.test_type,
                "details": r.details
            }
            for r in result.results if not r.passed
        ],
        "inputs_hash": result.inputs_hash,
    }

    # Output
    if args.json:
        print(json.dumps(receipt, indent=2))
    else:
        print("=" * 60)
        print("  FILTERAGENT TUNING VERIFICATION")
        print("=" * 60)
        print()
        for name, t in targets.items():
            icon = "PASS" if t["pass"] else "FAIL"
            print(f"  {name:20} {t['actual']:2}/{t['target']:2}  [{icon}]")
        print()
        print(f"  Overall pass rate: {result.pass_rate:.1%} ({result.passed}/{result.total})")
        if delta is not None:
            sign = "+" if delta > 0 else ""
            print(f"  Delta from baseline: {sign}{delta} tests")
        print()
        print(f"  Result: {'ALL TARGETS MET' if all_pass else 'TARGETS NOT MET'}")
        print("=" * 60)

        if not all_pass:
            print("\nFailed tests:")
            for r in result.results:
                if not r.passed:
                    print(f"  - {r.test_id}: {r.details}")

    # Write receipt
    args.output.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    receipt_path = args.output / f"tune_{ts}.json"
    receipt_path.write_text(json.dumps(receipt, indent=2))

    if not args.json:
        print(f"\nReceipt: {receipt_path}")

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
