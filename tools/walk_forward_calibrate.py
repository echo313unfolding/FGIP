#!/usr/bin/env python3
"""Walk-Forward Calibration CLI.

Runs anti-lookahead backtests to verify forecast calibration.

Usage:
    python3 tools/walk_forward_calibrate.py fgip.db --start 2024-01-01 --end 2025-02-01
    python3 tools/walk_forward_calibrate.py fgip.db --thesis uranium-thesis --step 30d
    python3 tools/walk_forward_calibrate.py fgip.db --check-lookahead-only

Key Features:
- Anti-lookahead validation: No future data in forecasts
- Calibration curves: Predicted vs actual probability frequencies
- Brier/log scoring: Quantitative forecast accuracy

Exit Codes:
    0: Success (no lookahead violations, Brier < 0.35)
    1: Calibration issues (Brier >= 0.35 or lookahead violations)
    2: Configuration or runtime error
"""

import argparse
import json
import hashlib
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fgip.db import FGIPDatabase
from fgip.calibration.backtest import WalkForwardBacktest, BacktestResult


def write_receipt(
    result: BacktestResult,
    params: Dict[str, Any],
    output_dir: Path,
    strict_mode: bool
) -> Path:
    """Write calibration receipt to file."""
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    receipt_path = output_dir / f"walk_forward_{timestamp}.json"

    # Hash inputs for reproducibility
    inputs_str = json.dumps(params, sort_keys=True)
    inputs_hash = hashlib.sha256(inputs_str.encode()).hexdigest()[:16]

    # Hash outputs
    outputs_str = json.dumps({
        "avg_brier_score": result.avg_brier_score,
        "avg_log_score": result.avg_log_score,
        "total_steps": result.total_steps,
        "lookahead_violations": result.lookahead_violations,
    }, sort_keys=True)
    outputs_hash = hashlib.sha256(outputs_str.encode()).hexdigest()[:16]

    receipt = {
        "timestamp": timestamp,
        "parameters": params,
        "results": {
            "total_steps": result.total_steps,
            "avg_brier_score": result.avg_brier_score,
            "avg_log_score": result.avg_log_score,
            "calibration_curve": result.calibration_curve,
        },
        "anti_lookahead": {
            "violations": result.lookahead_violations,
            "violation_details": result.violation_details[:10],  # Limit to 10
            "strict_mode": strict_mode,
        },
        "inputs_hash": inputs_hash,
        "outputs_hash": outputs_hash,
    }

    with open(receipt_path, "w") as f:
        json.dump(receipt, f, indent=2)

    return receipt_path


def update_calibration_metrics(
    db: FGIPDatabase,
    result: BacktestResult,
    agent_name: str = "forecast-agent"
):
    """Update calibration_metrics table with results."""
    conn = db.connect()

    timestamp = datetime.utcnow().isoformat() + "Z"

    # Calculate overconfidence ratio
    # Compare mean predicted to actual hit rate
    mean_pred = 0.0
    hit_rate = 0.0
    total_count = 0

    for bin_name, bin_data in result.calibration_curve.items():
        if bin_data.get("count", 0) > 0:
            mean_pred += bin_data.get("mean_predicted", 0) * bin_data["count"]
            hit_rate += bin_data.get("actual_frequency", 0) * bin_data["count"]
            total_count += bin_data["count"]

    if total_count > 0:
        mean_pred /= total_count
        hit_rate /= total_count
        overconfidence = mean_pred / max(hit_rate, 0.01) if hit_rate > 0 else 1.0
    else:
        overconfidence = 1.0

    # Insert for different time windows
    for window in ["all_time"]:
        conn.execute("""
            INSERT OR REPLACE INTO calibration_metrics
            (agent_name, time_window, brier_score, log_score, overconfidence_ratio,
             underconfidence_ratio, sample_size, mean_confidence, hit_rate,
             calibration_error, computed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            agent_name,
            window,
            result.avg_brier_score,
            result.avg_log_score,
            overconfidence,
            1.0 / overconfidence if overconfidence > 0 else 1.0,
            result.total_steps,
            mean_pred,
            hit_rate,
            abs(mean_pred - hit_rate),
            timestamp,
        ))

    conn.commit()


def print_summary(result: BacktestResult, strict_mode: bool):
    """Print calibration summary."""
    print("\n" + "=" * 60)
    print("Walk-Forward Calibration Results")
    print("=" * 60)
    print(f"Period:     {result.start_date} to {result.end_date}")
    print(f"Step Size:  {result.step_size}")
    print(f"Total Steps: {result.total_steps}")
    print()

    print("-" * 60)
    print("Calibration Scores:")
    print("-" * 60)
    print(f"  Brier Score:    {result.avg_brier_score:.4f}")
    print(f"  Log Score:      {result.avg_log_score:.4f}")
    print()

    # Brier interpretation
    if result.avg_brier_score < 0.15:
        print("  📊 Excellent calibration (Brier < 0.15)")
    elif result.avg_brier_score < 0.25:
        print("  📊 Good calibration (Brier < 0.25)")
    elif result.avg_brier_score < 0.35:
        print("  📊 Acceptable calibration (Brier < 0.35)")
    else:
        print("  ⚠️  Poor calibration (Brier >= 0.35)")

    print()
    print("-" * 60)
    print("Calibration Curve:")
    print("-" * 60)
    print(f"  {'Bin':<12} {'Predicted':>10} {'Actual':>10} {'Count':>8} {'Error':>10}")
    print("  " + "-" * 50)

    for bin_name, data in sorted(result.calibration_curve.items()):
        if data.get("count", 0) > 0:
            pred = data.get("mean_predicted", 0) or 0
            actual = data.get("actual_frequency", 0) or 0
            error = data.get("error", 0) or 0
            count = data.get("count", 0)
            print(f"  {bin_name:<12} {pred:>10.3f} {actual:>10.3f} {count:>8} {error:>+10.3f}")

    print()
    print("-" * 60)
    print("Anti-Lookahead Check:")
    print("-" * 60)
    if result.lookahead_violations == 0:
        print("  ✅ No lookahead violations detected")
    else:
        print(f"  ❌ {result.lookahead_violations} lookahead violations!")
        if strict_mode:
            print("     (Strict mode: this is a failure)")
        for detail in result.violation_details[:5]:
            print(f"     - {detail}")

    print()

    # Overall verdict
    passed = (
        result.avg_brier_score < 0.35 and
        result.lookahead_violations == 0
    )

    if passed:
        print("✅ CALIBRATION PASSED - Forecasts are well-calibrated")
    else:
        print("❌ CALIBRATION ISSUES DETECTED")
        if result.avg_brier_score >= 0.35:
            print("   - Brier score too high (forecasts are poorly calibrated)")
        if result.lookahead_violations > 0:
            print("   - Lookahead bias detected (using future data)")


def main():
    parser = argparse.ArgumentParser(
        description="Run walk-forward calibration backtest"
    )
    parser.add_argument(
        "db_path",
        nargs="?",
        default="fgip.db",
        help="Path to FGIP database (default: fgip.db)"
    )
    parser.add_argument(
        "--start",
        type=str,
        default="2024-01-01",
        help="Start date (ISO format, default: 2024-01-01)"
    )
    parser.add_argument(
        "--end",
        type=str,
        default=None,
        help="End date (ISO format, default: today)"
    )
    parser.add_argument(
        "--step",
        type=str,
        default="7d",
        choices=["1d", "7d", "14d", "30d"],
        help="Step size (default: 7d)"
    )
    parser.add_argument(
        "--thesis",
        type=str,
        action="append",
        dest="thesis_ids",
        help="Specific thesis ID(s) to test (can repeat)"
    )
    parser.add_argument(
        "--check-lookahead-only",
        action="store_true",
        help="Only check for lookahead violations, don't score"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=True,
        help="Fail on any lookahead violation (default: True)"
    )
    parser.add_argument(
        "--no-strict",
        action="store_false",
        dest="strict",
        help="Don't fail on lookahead violations"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("receipts/calibration"),
        help="Output directory for receipts"
    )
    parser.add_argument(
        "--update-metrics",
        action="store_true",
        help="Update calibration_metrics table"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    # Check database exists
    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}", file=sys.stderr)
        sys.exit(2)

    # Set default end date
    end_date = args.end
    if end_date is None:
        end_date = datetime.utcnow().strftime("%Y-%m-%d")

    # Initialize database
    try:
        db = FGIPDatabase(str(db_path))
        db.connect()
    except Exception as e:
        print(f"ERROR: Failed to connect to database: {e}", file=sys.stderr)
        sys.exit(2)

    # Initialize backtest
    backtest = WalkForwardBacktest(db)

    # Run backtest
    try:
        if args.verbose:
            print(f"Running walk-forward backtest...")
            print(f"  Period: {args.start} to {end_date}")
            print(f"  Step: {args.step}")
            if args.thesis_ids:
                print(f"  Theses: {args.thesis_ids}")
            print()

        result = backtest.run(
            start_date=args.start,
            end_date=end_date,
            step=args.step,
            thesis_ids=args.thesis_ids,
        )
    except Exception as e:
        print(f"ERROR: Backtest failed: {e}", file=sys.stderr)
        sys.exit(2)

    # Prepare params for receipt
    params = {
        "start_date": args.start,
        "end_date": end_date,
        "step": args.step,
        "thesis_ids": args.thesis_ids or "all",
    }

    # Write receipt
    try:
        receipt_path = write_receipt(result, params, args.output, args.strict)
    except Exception as e:
        print(f"WARNING: Failed to write receipt: {e}", file=sys.stderr)
        receipt_path = None

    # Update metrics if requested
    if args.update_metrics:
        try:
            update_calibration_metrics(db, result)
            if args.verbose:
                print("Updated calibration_metrics table")
        except Exception as e:
            print(f"WARNING: Failed to update metrics: {e}", file=sys.stderr)

    # Output
    if args.json:
        output = {
            "parameters": params,
            "results": result.to_dict(),
            "receipt_path": str(receipt_path) if receipt_path else None,
        }
        print(json.dumps(output, indent=2))
    else:
        print_summary(result, args.strict)
        if receipt_path:
            print(f"\nReceipt: {receipt_path}")

    # Exit code
    passed = (
        result.avg_brier_score < 0.35 and
        (not args.strict or result.lookahead_violations == 0)
    )

    if passed:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
