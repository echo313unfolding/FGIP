#!/usr/bin/env python3
"""KAT (Known Answer Test) Runner CLI.

Runs deterministic tests against the FGIP pipeline to verify correctness.

Usage:
    python3 tools/run_kat.py fgip.db
    python3 tools/run_kat.py fgip.db --verbose
    python3 tools/run_kat.py fgip.db --easter-eggs-only
    python3 tools/run_kat.py fgip.db --adversarial-only
    python3 tools/run_kat.py fgip.db --fail-fast

Exit Codes:
    0: All tests passed
    1: Some tests failed
    2: Configuration or runtime error
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fgip.db import FGIPDatabase
from fgip.tests.kat import KATResult
from fgip.tests.kat.runner import KATHarness


def write_receipt(result: KATResult, output_dir: Path) -> Path:
    """Write KAT receipt to file."""
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = result.timestamp.replace(":", "-").replace("Z", "")
    receipt_path = output_dir / f"kat_{timestamp}.json"

    with open(receipt_path, "w") as f:
        json.dump(result.to_dict(), f, indent=2)

    return receipt_path


def print_summary(result: KATResult, verbose: bool = False):
    """Print KAT run summary."""
    print("\n" + "=" * 60)
    print("FGIP KAT (Known Answer Test) Results")
    print("=" * 60)
    print(f"Timestamp: {result.timestamp}")
    print(f"Duration:  {result.duration_ms:.0f}ms")
    print()

    # Detailed results if verbose
    if verbose:
        print("-" * 60)
        print("Test Results:")
        print("-" * 60)
        for r in result.results:
            icon = "✅" if r.passed else "❌"
            print(f"  {icon} [{r.test_type:12}] {r.test_id}")
            if not r.passed and r.details:
                print(f"      Details: {r.details[:60]}")
        print()

    # Summary
    print("-" * 60)
    print("Summary:")
    print("-" * 60)
    print(f"  Total:   {result.total}")
    print(f"  Passed:  {result.passed}")
    print(f"  Failed:  {result.failed}")
    print(f"  Skipped: {result.skipped}")
    print(f"  Rate:    {result.pass_rate * 100:.1f}%")
    print()

    if result.all_passed:
        print("✅ ALL TESTS PASSED - Pipeline verified!")
    elif result.passed > 0:
        print(f"⚠️  {result.passed}/{result.total} tests passed - Pipeline partially working")
        # Show failed tests
        failed_tests = [r for r in result.results if not r.passed]
        if failed_tests:
            print("\nFailed tests:")
            for r in failed_tests[:5]:
                print(f"  - {r.test_id}: {r.details or 'No details'}")
    else:
        print("❌ ALL TESTS FAILED - Check pipeline implementation")


def main():
    parser = argparse.ArgumentParser(
        description="Run FGIP Known Answer Tests"
    )
    parser.add_argument(
        "db_path",
        nargs="?",
        default="fgip.db",
        help="Path to FGIP database (default: fgip.db)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print detailed output"
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on first failure"
    )
    parser.add_argument(
        "--easter-eggs-only",
        action="store_true",
        help="Run only easter egg tests"
    )
    parser.add_argument(
        "--adversarial-only",
        action="store_true",
        help="Run only adversarial tests"
    )
    parser.add_argument(
        "--cases-dir",
        type=Path,
        default=None,
        help="Directory containing test case JSONL files"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("receipts/kat"),
        help="Output directory for receipts"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )
    parser.add_argument(
        "--store-results",
        action="store_true",
        help="Store results in database"
    )

    args = parser.parse_args()

    # Check database exists
    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}", file=sys.stderr)
        print("Create it first with: python3 -m fgip.cli init", file=sys.stderr)
        sys.exit(2)

    # Initialize database
    try:
        db = FGIPDatabase(str(db_path))
        db.connect()
    except Exception as e:
        print(f"ERROR: Failed to connect to database: {e}", file=sys.stderr)
        sys.exit(2)

    # Initialize harness
    cases_dir = args.cases_dir
    if cases_dir is None:
        cases_dir = PROJECT_ROOT / "fgip" / "tests" / "kat"

    harness = KATHarness(db, cases_dir)

    # Run tests
    try:
        if args.easter_eggs_only:
            result = harness.run_easter_eggs(verbose=args.verbose)
        elif args.adversarial_only:
            result = harness.run_adversarial(verbose=args.verbose)
        else:
            result = harness.run_all(
                fail_fast=args.fail_fast,
                verbose=args.verbose,
            )
    except Exception as e:
        print(f"ERROR: Test execution failed: {e}", file=sys.stderr)
        sys.exit(2)

    # Store results if requested
    if args.store_results:
        try:
            run_id = harness.store_results(result)
            if args.verbose:
                print(f"Results stored with run ID: {run_id}")
        except Exception as e:
            print(f"WARNING: Failed to store results: {e}", file=sys.stderr)

    # Write receipt
    try:
        receipt_path = write_receipt(result, args.output)
    except Exception as e:
        print(f"WARNING: Failed to write receipt: {e}", file=sys.stderr)
        receipt_path = None

    # Output
    if args.json:
        print(result.to_json())
    else:
        print_summary(result, verbose=args.verbose)
        if receipt_path:
            print(f"Receipt: {receipt_path}")

    # Exit code
    if result.all_passed:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
