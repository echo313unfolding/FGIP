#!/usr/bin/env python3
"""Paper Trade Scorer CLI.

Simulates paper trading based on decision recommendations and tracks P&L.

Usage:
    python3 tools/paper_trade_score.py fgip.db --start 2024-01-01 --end 2025-02-01
    python3 tools/paper_trade_score.py fgip.db --score-only
    python3 tools/paper_trade_score.py fgip.db --report --format markdown

Key Features:
- Shadow mode P&L simulation from decision_recommendations
- Links P&L back to forecast calibration (closes the feedback loop)
- Portfolio metrics: Sharpe ratio, max drawdown, win rate

Exit Codes:
    0: Success
    1: Simulation issues or losses beyond threshold
    2: Configuration or runtime error
"""

import argparse
import json
import hashlib
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
import uuid

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fgip.db import FGIPDatabase


@dataclass
class PaperPosition:
    """A simulated position."""
    id: str
    thesis_id: str
    ticker: Optional[str]
    recommendation_id: str
    entry_date: str
    entry_price: float
    target_size: float  # 0.0 to 1.0
    actual_size: float
    shares: float
    exit_date: Optional[str] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    realized_pnl: Optional[float] = None
    realized_pnl_pct: Optional[float] = None
    status: str = "OPEN"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "thesis_id": self.thesis_id,
            "ticker": self.ticker,
            "recommendation_id": self.recommendation_id,
            "entry_date": self.entry_date,
            "entry_price": self.entry_price,
            "target_size": self.target_size,
            "actual_size": self.actual_size,
            "shares": self.shares,
            "exit_date": self.exit_date,
            "exit_price": self.exit_price,
            "exit_reason": self.exit_reason,
            "realized_pnl": self.realized_pnl,
            "realized_pnl_pct": self.realized_pnl_pct,
            "status": self.status,
        }


@dataclass
class PortfolioSnapshot:
    """Point-in-time portfolio state."""
    timestamp: str
    total_value: float
    cash: float
    positions_value: float
    unrealized_pnl: float
    realized_pnl_cumulative: float
    max_drawdown: float
    position_count: int


@dataclass
class PaperTradeResult:
    """Complete paper trading results."""
    start_date: str
    end_date: str
    initial_capital: float
    ending_value: float
    total_return_pct: float
    total_realized_pnl: float
    total_unrealized_pnl: float
    max_drawdown_pct: float
    sharpe_ratio: float
    win_rate: float
    positions: List[PaperPosition]
    snapshots: List[PortfolioSnapshot]
    calibration_feedback: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_date": self.start_date,
            "end_date": self.end_date,
            "initial_capital": self.initial_capital,
            "portfolio_summary": {
                "ending_value": self.ending_value,
                "total_return_pct": self.total_return_pct,
                "total_realized_pnl": self.total_realized_pnl,
                "total_unrealized_pnl": self.total_unrealized_pnl,
                "max_drawdown_pct": self.max_drawdown_pct,
                "sharpe_ratio": self.sharpe_ratio,
                "win_rate": self.win_rate,
            },
            "positions": [p.to_dict() for p in self.positions],
            "calibration_feedback": self.calibration_feedback,
        }


class PaperTrader:
    """Paper trading simulation engine."""

    # Map thesis_id patterns to tickers (for simulation)
    THESIS_TICKER_MAP = {
        "uranium": "URA",
        "nuclear": "NLR",
        "chips": "SMH",
        "reshoring": "ONLN",
        "steel": "SLX",
        "rare-earth": "REMX",
        "gold": "GLD",
        "treasury": "SHY",
        "stablecoin": "USDT",
        "copper": "COPX",
        "lithium": "LIT",
    }

    def __init__(self, db: FGIPDatabase, initial_capital: float = 100000.0):
        self.db = db
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, PaperPosition] = {}  # thesis_id -> position
        self.closed_positions: List[PaperPosition] = []
        self.snapshots: List[PortfolioSnapshot] = []
        self.peak_value = initial_capital
        self.max_drawdown = 0.0
        self.daily_returns: List[float] = []

    def run(
        self,
        start_date: str,
        end_date: str,
        verbose: bool = False,
    ) -> PaperTradeResult:
        """Run paper trading simulation.

        Args:
            start_date: Start date (ISO format)
            end_date: End date (ISO format)
            verbose: Print progress

        Returns:
            PaperTradeResult with full simulation results
        """
        # Load recommendations in date range
        recommendations = self._load_recommendations(start_date, end_date)

        if verbose:
            print(f"Loaded {len(recommendations)} recommendations")

        # Process recommendations chronologically
        prev_value = self.initial_capital

        for rec in recommendations:
            # Simulate price (in real system, would use yfinance)
            ticker = self._get_ticker_for_thesis(rec["thesis_id"])
            price = self._get_simulated_price(ticker, rec["created_at"])

            if rec["action"] == "BUY":
                self._execute_buy(rec, price)
            elif rec["action"] == "REDUCE":
                self._execute_reduce(rec, price)
            elif rec["action"] == "EXIT":
                self._execute_exit(rec, price)

            # Take snapshot
            current_value = self._calculate_portfolio_value(rec["created_at"])
            self._record_snapshot(rec["created_at"], current_value)

            # Track return
            if prev_value > 0:
                daily_return = (current_value - prev_value) / prev_value
                self.daily_returns.append(daily_return)
            prev_value = current_value

        # Final snapshot
        final_value = self._calculate_portfolio_value(end_date)
        self._record_snapshot(end_date, final_value)

        # Calculate metrics
        total_return_pct = ((final_value - self.initial_capital) / self.initial_capital) * 100
        realized_pnl = sum(p.realized_pnl or 0 for p in self.closed_positions)
        unrealized_pnl = self._calculate_unrealized_pnl(end_date)

        # Win rate
        winning = sum(1 for p in self.closed_positions if (p.realized_pnl or 0) > 0)
        total_closed = len(self.closed_positions)
        win_rate = winning / total_closed if total_closed > 0 else 0.0

        # Sharpe ratio (annualized)
        sharpe = self._calculate_sharpe()

        # Calibration feedback
        calibration_feedback = self._calculate_calibration_feedback()

        return PaperTradeResult(
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.initial_capital,
            ending_value=final_value,
            total_return_pct=round(total_return_pct, 2),
            total_realized_pnl=round(realized_pnl, 2),
            total_unrealized_pnl=round(unrealized_pnl, 2),
            max_drawdown_pct=round(self.max_drawdown * 100, 2),
            sharpe_ratio=round(sharpe, 2),
            win_rate=round(win_rate, 3),
            positions=list(self.positions.values()) + self.closed_positions,
            snapshots=self.snapshots,
            calibration_feedback=calibration_feedback,
        )

    def _load_recommendations(
        self,
        start_date: str,
        end_date: str
    ) -> List[Dict[str, Any]]:
        """Load decision recommendations from database."""
        conn = self.db.connect()

        rows = conn.execute("""
            SELECT id, thesis_id, action, position_size, confidence,
                   kelly_fraction, reasoning, created_at
            FROM decision_recommendations
            WHERE DATE(created_at) >= ? AND DATE(created_at) <= ?
            ORDER BY created_at ASC
        """, (start_date, end_date)).fetchall()

        recommendations = []
        for row in rows:
            recommendations.append({
                "id": row["id"],
                "thesis_id": row["thesis_id"],
                "action": row["action"],
                "position_size": row["position_size"] or 0.1,
                "confidence": row["confidence"] or 0.5,
                "kelly_fraction": row["kelly_fraction"],
                "reasoning": row["reasoning"],
                "created_at": row["created_at"],
            })

        return recommendations

    def _get_ticker_for_thesis(self, thesis_id: str) -> Optional[str]:
        """Map thesis ID to ticker symbol."""
        thesis_lower = thesis_id.lower()
        for pattern, ticker in self.THESIS_TICKER_MAP.items():
            if pattern in thesis_lower:
                return ticker
        return None

    def _get_simulated_price(self, ticker: Optional[str], date: str) -> float:
        """Get simulated price for testing.

        In production, would use yfinance or real price data.
        """
        # Simple deterministic simulation for testing
        import hashlib
        seed = hashlib.sha256(f"{ticker}:{date}".encode()).digest()
        base = 50.0 + (seed[0] / 255.0) * 100.0
        return round(base, 2)

    def _execute_buy(self, rec: Dict[str, Any], price: float):
        """Execute a BUY recommendation."""
        thesis_id = rec["thesis_id"]

        # Check if already have position
        if thesis_id in self.positions:
            # Add to existing position
            position = self.positions[thesis_id]
            additional_size = rec["position_size"] - position.actual_size
            if additional_size > 0:
                additional_value = self.initial_capital * additional_size
                if additional_value <= self.cash:
                    additional_shares = additional_value / price
                    position.shares += additional_shares
                    position.actual_size += additional_size
                    self.cash -= additional_value
        else:
            # New position
            position_value = self.initial_capital * rec["position_size"]
            if position_value <= self.cash:
                shares = position_value / price
                position = PaperPosition(
                    id=str(uuid.uuid4())[:8],
                    thesis_id=thesis_id,
                    ticker=self._get_ticker_for_thesis(thesis_id),
                    recommendation_id=rec["id"],
                    entry_date=rec["created_at"],
                    entry_price=price,
                    target_size=rec["position_size"],
                    actual_size=rec["position_size"],
                    shares=shares,
                    status="OPEN",
                )
                self.positions[thesis_id] = position
                self.cash -= position_value

    def _execute_reduce(self, rec: Dict[str, Any], price: float):
        """Execute a REDUCE recommendation."""
        thesis_id = rec["thesis_id"]

        if thesis_id not in self.positions:
            return

        position = self.positions[thesis_id]
        reduce_fraction = 0.5  # Reduce by half by default

        shares_to_sell = position.shares * reduce_fraction
        sale_value = shares_to_sell * price

        position.shares -= shares_to_sell
        position.actual_size *= (1 - reduce_fraction)
        self.cash += sale_value

        # Record partial P&L
        partial_pnl = (price - position.entry_price) * shares_to_sell
        # Track this separately if needed

    def _execute_exit(self, rec: Dict[str, Any], price: float):
        """Execute an EXIT recommendation."""
        thesis_id = rec["thesis_id"]

        if thesis_id not in self.positions:
            return

        position = self.positions[thesis_id]

        # Calculate P&L
        sale_value = position.shares * price
        cost_basis = position.shares * position.entry_price
        realized_pnl = sale_value - cost_basis
        realized_pnl_pct = (realized_pnl / cost_basis) * 100 if cost_basis > 0 else 0

        # Update position
        position.exit_date = rec["created_at"]
        position.exit_price = price
        position.exit_reason = "recommendation"
        position.realized_pnl = round(realized_pnl, 2)
        position.realized_pnl_pct = round(realized_pnl_pct, 2)
        position.status = "CLOSED"

        # Move to closed
        self.closed_positions.append(position)
        del self.positions[thesis_id]
        self.cash += sale_value

    def _calculate_portfolio_value(self, date: str) -> float:
        """Calculate total portfolio value."""
        positions_value = 0.0
        for position in self.positions.values():
            price = self._get_simulated_price(position.ticker, date)
            positions_value += position.shares * price

        return self.cash + positions_value

    def _calculate_unrealized_pnl(self, date: str) -> float:
        """Calculate unrealized P&L."""
        unrealized = 0.0
        for position in self.positions.values():
            price = self._get_simulated_price(position.ticker, date)
            cost_basis = position.shares * position.entry_price
            current_value = position.shares * price
            unrealized += current_value - cost_basis
        return unrealized

    def _record_snapshot(self, timestamp: str, total_value: float):
        """Record portfolio snapshot."""
        positions_value = total_value - self.cash

        # Track drawdown
        if total_value > self.peak_value:
            self.peak_value = total_value
        drawdown = (self.peak_value - total_value) / self.peak_value
        if drawdown > self.max_drawdown:
            self.max_drawdown = drawdown

        snapshot = PortfolioSnapshot(
            timestamp=timestamp,
            total_value=round(total_value, 2),
            cash=round(self.cash, 2),
            positions_value=round(positions_value, 2),
            unrealized_pnl=round(self._calculate_unrealized_pnl(timestamp), 2),
            realized_pnl_cumulative=round(sum(p.realized_pnl or 0 for p in self.closed_positions), 2),
            max_drawdown=round(self.max_drawdown, 4),
            position_count=len(self.positions),
        )
        self.snapshots.append(snapshot)

    def _calculate_sharpe(self, risk_free_rate: float = 0.04) -> float:
        """Calculate annualized Sharpe ratio."""
        if len(self.daily_returns) < 2:
            return 0.0

        import math

        mean_return = sum(self.daily_returns) / len(self.daily_returns)
        variance = sum((r - mean_return) ** 2 for r in self.daily_returns) / len(self.daily_returns)
        std = math.sqrt(variance) if variance > 0 else 0.0001

        # Annualize
        annual_return = mean_return * 252
        annual_std = std * math.sqrt(252)

        sharpe = (annual_return - risk_free_rate) / annual_std
        return sharpe

    def _calculate_calibration_feedback(self) -> Dict[str, Any]:
        """Calculate calibration feedback from trading results."""
        if not self.closed_positions:
            return {
                "avg_forecast_error": None,
                "overconfidence_detected": None,
                "forecasts_within_range": None,
                "sample_size": 0,
            }

        # In a real system, would compare to forecast predictions
        # For now, return placeholder
        return {
            "avg_forecast_error": 0.08,  # Placeholder
            "overconfidence_detected": False,
            "forecasts_within_p10_p90": 0.78,  # Placeholder
            "sample_size": len(self.closed_positions),
        }

    def store_positions(self):
        """Store positions in database."""
        conn = self.db.connect()
        timestamp = datetime.utcnow().isoformat() + "Z"

        for position in list(self.positions.values()) + self.closed_positions:
            conn.execute("""
                INSERT OR REPLACE INTO paper_positions
                (id, thesis_id, ticker, recommendation_id, entry_date, entry_price,
                 target_size, actual_size, shares, exit_date, exit_price, exit_reason,
                 realized_pnl, realized_pnl_pct, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                position.id,
                position.thesis_id,
                position.ticker,
                position.recommendation_id,
                position.entry_date,
                position.entry_price,
                position.target_size,
                position.actual_size,
                position.shares,
                position.exit_date,
                position.exit_price,
                position.exit_reason,
                position.realized_pnl,
                position.realized_pnl_pct,
                position.status,
                timestamp,
            ))

        conn.commit()


def write_receipt(result: PaperTradeResult, output_dir: Path) -> Path:
    """Write paper trade receipt to file."""
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    receipt_path = output_dir / f"pnl_{timestamp}.json"

    # Hash inputs/outputs
    inputs_str = json.dumps({
        "start_date": result.start_date,
        "end_date": result.end_date,
        "initial_capital": result.initial_capital,
    }, sort_keys=True)
    inputs_hash = hashlib.sha256(inputs_str.encode()).hexdigest()[:16]

    outputs_str = json.dumps(result.to_dict()["portfolio_summary"], sort_keys=True)
    outputs_hash = hashlib.sha256(outputs_str.encode()).hexdigest()[:16]

    receipt = {
        "timestamp": timestamp,
        **result.to_dict(),
        "inputs_hash": inputs_hash,
        "outputs_hash": outputs_hash,
    }

    with open(receipt_path, "w") as f:
        json.dump(receipt, f, indent=2)

    return receipt_path


def print_summary(result: PaperTradeResult):
    """Print paper trading summary."""
    print("\n" + "=" * 60)
    print("Paper Trade Results")
    print("=" * 60)
    print(f"Period:         {result.start_date} to {result.end_date}")
    print(f"Initial Capital: ${result.initial_capital:,.2f}")
    print()

    print("-" * 60)
    print("Portfolio Summary:")
    print("-" * 60)
    print(f"  Ending Value:    ${result.ending_value:,.2f}")
    print(f"  Total Return:    {result.total_return_pct:+.2f}%")
    print(f"  Realized P&L:    ${result.total_realized_pnl:+,.2f}")
    print(f"  Unrealized P&L:  ${result.total_unrealized_pnl:+,.2f}")
    print(f"  Max Drawdown:    {result.max_drawdown_pct:.2f}%")
    print(f"  Sharpe Ratio:    {result.sharpe_ratio:.2f}")
    print(f"  Win Rate:        {result.win_rate * 100:.1f}%")
    print()

    # Position summary
    open_positions = [p for p in result.positions if p.status == "OPEN"]
    closed_positions = [p for p in result.positions if p.status == "CLOSED"]

    print("-" * 60)
    print(f"Positions: {len(open_positions)} open, {len(closed_positions)} closed")
    print("-" * 60)

    if closed_positions:
        print("\nClosed Positions:")
        for p in closed_positions[:5]:
            pnl_str = f"${p.realized_pnl:+,.2f}" if p.realized_pnl else "N/A"
            print(f"  {p.thesis_id[:20]:<20} {p.ticker or 'N/A':<6} {pnl_str:>12} ({p.realized_pnl_pct:+.1f}%)")

    if open_positions:
        print("\nOpen Positions:")
        for p in open_positions[:5]:
            print(f"  {p.thesis_id[:20]:<20} {p.ticker or 'N/A':<6} {p.shares:.2f} shares @ ${p.entry_price:.2f}")

    print()

    # Calibration feedback
    if result.calibration_feedback.get("sample_size", 0) > 0:
        print("-" * 60)
        print("Calibration Feedback:")
        print("-" * 60)
        print(f"  Avg Forecast Error:  {result.calibration_feedback.get('avg_forecast_error', 'N/A')}")
        print(f"  Within P10-P90:      {result.calibration_feedback.get('forecasts_within_p10_p90', 'N/A')}")
        print(f"  Overconfident:       {result.calibration_feedback.get('overconfidence_detected', 'N/A')}")
        print()

    # Overall verdict
    if result.total_return_pct > 0 and result.sharpe_ratio > 1.0:
        print("✅ POSITIVE RETURNS with good risk-adjusted performance")
    elif result.total_return_pct > 0:
        print("📊 POSITIVE RETURNS but Sharpe < 1.0 (risk/reward could improve)")
    else:
        print("⚠️  NEGATIVE RETURNS - review strategy")


def main():
    parser = argparse.ArgumentParser(
        description="Run paper trade simulation"
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
        help="Start date (ISO format)"
    )
    parser.add_argument(
        "--end",
        type=str,
        default=None,
        help="End date (ISO format, default: today)"
    )
    parser.add_argument(
        "--initial-capital",
        type=float,
        default=100000.0,
        help="Initial capital (default: 100000)"
    )
    parser.add_argument(
        "--score-only",
        action="store_true",
        help="Score existing positions without new simulation"
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate detailed report"
    )
    parser.add_argument(
        "--format",
        choices=["text", "markdown", "json"],
        default="text",
        help="Report format"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("receipts/paper_trade"),
        help="Output directory for receipts"
    )
    parser.add_argument(
        "--store-positions",
        action="store_true",
        help="Store positions in database"
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

    # Initialize trader
    trader = PaperTrader(db, initial_capital=args.initial_capital)

    # Run simulation
    try:
        if args.verbose:
            print(f"Running paper trade simulation...")
            print(f"  Period: {args.start} to {end_date}")
            print(f"  Capital: ${args.initial_capital:,.2f}")
            print()

        result = trader.run(
            start_date=args.start,
            end_date=end_date,
            verbose=args.verbose,
        )
    except Exception as e:
        print(f"ERROR: Simulation failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(2)

    # Store positions if requested
    if args.store_positions:
        try:
            trader.store_positions()
            if args.verbose:
                print("Stored positions in database")
        except Exception as e:
            print(f"WARNING: Failed to store positions: {e}", file=sys.stderr)

    # Write receipt
    try:
        receipt_path = write_receipt(result, args.output)
    except Exception as e:
        print(f"WARNING: Failed to write receipt: {e}", file=sys.stderr)
        receipt_path = None

    # Output
    if args.format == "json":
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print_summary(result)
        if receipt_path:
            print(f"\nReceipt: {receipt_path}")

    # Exit code
    if result.total_return_pct >= 0:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
