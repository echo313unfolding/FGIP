#!/usr/bin/env python3
"""
FGIP Portfolio Backtest Runner

Run portfolio backtest for FGIP theses to prove the strategy would have made money historically.

Usage:
    python3 scripts/run_backtest.py --thesis infrastructure-picks-shovels --start 2024-01-01 --end 2025-12-31
    python3 scripts/run_backtest.py --all-theses --start 2023-01-01
    python3 scripts/run_backtest.py --thesis nuclear-smr-thesis --start 2024-01-01 --plot

Examples:
    # Backtest infrastructure thesis for 2024
    python3 scripts/run_backtest.py --thesis infrastructure-picks-shovels --start 2024-01-01 --end 2024-12-31

    # Backtest multiple theses
    python3 scripts/run_backtest.py --thesis infrastructure-picks-shovels nuclear-smr-thesis --start 2024-01-01

    # List available theses
    python3 scripts/run_backtest.py --list

    # Generate JSON output
    python3 scripts/run_backtest.py --thesis infrastructure-picks-shovels --start 2024-01-01 --format json

Exit Codes:
    0: Success
    1: Backtest completed but strategy had negative returns
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


def list_theses():
    """List available investment theses."""
    from fgip.agents.conviction_engine import INVESTMENT_THESES

    print("Available Investment Theses:")
    print("=" * 70)
    for thesis in INVESTMENT_THESES:
        print(f"\n  ID: {thesis['thesis_id']}")
        tickers = [t for t in thesis['tickers'] if t.isupper()]
        print(f"  Tickers: {', '.join(tickers[:8])}{'...' if len(tickers) > 8 else ''}")
        print(f"  Sector: {thesis['sector']}")
        statement = thesis['thesis_statement'][:80] + "..." if len(thesis['thesis_statement']) > 80 else thesis['thesis_statement']
        print(f"  Statement: {statement}")
    print()


def plot_equity_curve(result, output_path: str = None):
    """Generate equity curve plot."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("WARNING: matplotlib not installed, skipping plot")
        return

    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

    # Equity curve
    ax1 = axes[0]
    result.equity_curve["portfolio_value"].plot(ax=ax1, label="Portfolio", linewidth=2)
    result.equity_curve["benchmark_value"].plot(ax=ax1, label=result.config.benchmark_symbol, linewidth=1, alpha=0.7)
    ax1.set_ylabel("Value ($)")
    ax1.set_title(f"Backtest: {result.config.start_date} to {result.config.end_date}")
    ax1.legend(loc="upper left")
    ax1.grid(True, alpha=0.3)

    # Drawdown
    ax2 = axes[1]
    (result.drawdown_series * 100).plot(ax=ax2, color="red", alpha=0.5)
    ax2.fill_between(result.drawdown_series.index, result.drawdown_series * 100, 0, color="red", alpha=0.3)
    ax2.set_ylabel("Drawdown (%)")
    ax2.set_xlabel("Date")
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()

    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        print(f"Plot saved to: {output_path}")
    else:
        plt.show()


def print_summary(result):
    """Print backtest summary."""
    result.print_report()


def save_receipt(result, output_path: Path):
    """Save backtest receipt."""
    import hashlib

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    receipt_path = output_path / f"backtest_{timestamp}.json"

    # Create hash of inputs
    inputs = {
        "config": result.config.to_dict(),
        "timestamp": timestamp,
    }
    inputs_str = json.dumps(inputs, sort_keys=True)
    inputs_hash = hashlib.sha256(inputs_str.encode()).hexdigest()[:16]

    # Create hash of outputs
    outputs = {
        "total_return": result.total_return,
        "sharpe": result.sharpe_ratio,
        "alpha": result.alpha,
    }
    outputs_str = json.dumps(outputs, sort_keys=True)
    outputs_hash = hashlib.sha256(outputs_str.encode()).hexdigest()[:16]

    receipt = {
        "timestamp": timestamp,
        "inputs_hash": inputs_hash,
        "outputs_hash": outputs_hash,
        **result.to_dict(),
    }

    output_path.mkdir(parents=True, exist_ok=True)
    with open(receipt_path, "w") as f:
        json.dump(receipt, f, indent=2, default=str)

    return receipt_path


def main():
    parser = argparse.ArgumentParser(
        description="Run portfolio backtest for FGIP theses",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s --thesis infrastructure-picks-shovels --start 2024-01-01
    %(prog)s --all-theses --start 2023-01-01 --end 2024-12-31
    %(prog)s --list
        """
    )

    # Thesis selection
    parser.add_argument(
        "--thesis", "-t",
        nargs="+",
        help="Thesis ID(s) to backtest"
    )
    parser.add_argument(
        "--all-theses",
        action="store_true",
        help="Backtest all defined theses"
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List available theses and exit"
    )

    # Date range
    parser.add_argument(
        "--start",
        type=str,
        help="Start date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end",
        type=str,
        default=None,
        help="End date (YYYY-MM-DD, default: today)"
    )

    # Configuration
    parser.add_argument(
        "--capital",
        type=float,
        default=100_000,
        help="Initial capital (default: 100000)"
    )
    parser.add_argument(
        "--max-position",
        type=float,
        default=0.20,
        help="Maximum position size as decimal (default: 0.20 = 20%%)"
    )
    parser.add_argument(
        "--rebalance",
        choices=["daily", "weekly", "monthly", "on_signal"],
        default="weekly",
        help="Rebalance frequency (default: weekly)"
    )
    parser.add_argument(
        "--slippage",
        type=float,
        default=10,
        help="Slippage in basis points (default: 10)"
    )
    parser.add_argument(
        "--benchmark",
        type=str,
        default="SPY",
        help="Benchmark symbol (default: SPY)"
    )
    parser.add_argument(
        "--min-conviction",
        type=int,
        default=3,
        choices=[1, 2, 3, 4, 5],
        help="Minimum conviction level to trade (default: 3)"
    )
    parser.add_argument(
        "--stop-loss",
        type=float,
        default=0.15,
        help="Stop loss percentage (default: 0.15 = 15%%)"
    )

    # Output
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("receipts/backtest"),
        help="Output directory for receipts"
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)"
    )
    parser.add_argument(
        "--plot",
        action="store_true",
        help="Generate equity curve plot"
    )
    parser.add_argument(
        "--plot-output",
        type=str,
        default=None,
        help="Save plot to file instead of displaying"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )

    # Database
    parser.add_argument(
        "--db",
        type=str,
        default="fgip.db",
        help="Path to FGIP database (default: fgip.db)"
    )

    args = parser.parse_args()

    # Handle --list
    if args.list:
        list_theses()
        sys.exit(0)

    # Validate required arguments
    if not args.thesis and not args.all_theses:
        parser.error("Either --thesis or --all-theses is required")

    if not args.start:
        parser.error("--start is required")

    # Set default end date
    if args.end is None:
        args.end = datetime.now().strftime("%Y-%m-%d")

    # Check database exists
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}", file=sys.stderr)
        sys.exit(2)

    # Get thesis IDs
    if args.all_theses:
        from fgip.agents.conviction_engine import INVESTMENT_THESES
        thesis_ids = [t["thesis_id"] for t in INVESTMENT_THESES]
    else:
        thesis_ids = args.thesis

    # Validate thesis IDs
    from fgip.agents.conviction_engine import INVESTMENT_THESES
    valid_ids = {t["thesis_id"] for t in INVESTMENT_THESES}
    for tid in thesis_ids:
        if tid not in valid_ids:
            print(f"ERROR: Unknown thesis ID: {tid}", file=sys.stderr)
            print(f"Use --list to see available theses", file=sys.stderr)
            sys.exit(2)

    # Initialize
    from fgip.db import FGIPDatabase
    from fgip.backtest import BacktestConfig, PortfolioBacktest

    try:
        db = FGIPDatabase(str(db_path))
        db.connect()
        db.run_migrations()
    except Exception as e:
        print(f"ERROR: Failed to connect to database: {e}", file=sys.stderr)
        sys.exit(2)

    # Create config
    config = BacktestConfig(
        start_date=args.start,
        end_date=args.end,
        initial_capital=args.capital,
        max_position_pct=args.max_position,
        rebalance_frequency=args.rebalance,
        slippage_bps=args.slippage,
        benchmark_symbol=args.benchmark,
        min_conviction_to_trade=args.min_conviction,
        stop_loss_pct=args.stop_loss if args.stop_loss > 0 else None,
    )

    # Print header
    if args.format == "text":
        print()
        print("=" * 60)
        print("FGIP PORTFOLIO BACKTEST")
        print("=" * 60)
        print(f"Theses: {', '.join(thesis_ids)}")
        print(f"Period: {args.start} to {args.end}")
        print(f"Capital: ${args.capital:,.0f}")
        print(f"Max Position: {args.max_position*100:.0f}%")
        print(f"Rebalance: {args.rebalance}")
        print(f"Benchmark: {args.benchmark}")
        print()

    # Run backtest
    try:
        backtest = PortfolioBacktest(db, config)
        result = backtest.run(thesis_ids)
    except Exception as e:
        print(f"ERROR: Backtest failed: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(2)

    # Output results
    if args.format == "json":
        print(json.dumps(result.to_dict(), indent=2, default=str))
    else:
        print_summary(result)

    # Save receipt
    try:
        receipt_path = save_receipt(result, args.output)
        if args.format == "text":
            print(f"\nReceipt: {receipt_path}")
    except Exception as e:
        print(f"WARNING: Failed to save receipt: {e}", file=sys.stderr)

    # Generate plot
    if args.plot:
        plot_equity_curve(result, args.plot_output)

    # Summary verdict
    if args.format == "text":
        print()
        if result.total_return > 0 and result.alpha > 0:
            if result.sharpe_ratio > 1.0:
                print(f"VERDICT: Strategy OUTPERFORMED {args.benchmark} with {result.alpha*100:.1f}% alpha and {result.sharpe_ratio:.2f} Sharpe")
            else:
                print(f"VERDICT: Strategy beat {args.benchmark} by {result.alpha*100:.1f}% but Sharpe < 1.0")
        elif result.total_return > 0:
            print(f"VERDICT: Strategy had positive returns but UNDERPERFORMED {args.benchmark}")
        else:
            print(f"VERDICT: Strategy had NEGATIVE returns")

    # Exit code
    if result.total_return >= 0:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
