"""
WO-K Completion Tests — Backtest Runtime Verification

Tests that the conviction → sizing → trade plan → backtest path is fully live.

Acceptance criteria:
- No declared-but-disconnected sizing path remains
- No declared-but-disconnected stop path remains
- One end-to-end receipt proves live usage of sizing + stops
- Tests fail if sizing is bypassed
- Tests fail if stop logic is bypassed
"""

import json
import os
import sqlite3
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from fgip.backtest.portfolio_backtest import (
    BacktestConfig,
    BacktestResult,
    PortfolioBacktest,
    Position,
    Trade,
)
from fgip.backtest.position_sizing import (
    conviction_based_size,
    equal_weight_size,
    kelly_fraction,
    liquidity_adjusted_size,
    position_sizer,
    volatility_adjusted_size,
)
from fgip.backtest.risk_metrics import sharpe_ratio, max_drawdown, win_rate


# =============================================================================
# Unit Tests: Position Sizing
# =============================================================================


class TestConvictionBasedSize(unittest.TestCase):
    """Verify conviction_based_size maps levels correctly."""

    def test_level_5_gets_max(self):
        self.assertAlmostEqual(conviction_based_size(5, 0.20), 0.20)

    def test_level_4_gets_75pct(self):
        self.assertAlmostEqual(conviction_based_size(4, 0.20), 0.15)

    def test_level_3_gets_50pct(self):
        self.assertAlmostEqual(conviction_based_size(3, 0.20), 0.10)

    def test_level_2_gets_25pct(self):
        self.assertAlmostEqual(conviction_based_size(2, 0.20), 0.05)

    def test_level_1_gets_zero(self):
        self.assertAlmostEqual(conviction_based_size(1, 0.20), 0.00)

    def test_below_min_conviction_gets_zero(self):
        self.assertAlmostEqual(conviction_based_size(2, 0.20, min_conviction_to_trade=3), 0.00)

    def test_different_max_scales(self):
        self.assertAlmostEqual(conviction_based_size(5, 0.10), 0.10)
        self.assertAlmostEqual(conviction_based_size(4, 0.10), 0.075)


class TestKellyFraction(unittest.TestCase):
    """Verify Kelly criterion sizing."""

    def test_positive_edge_gives_position(self):
        size = kelly_fraction(0.6, 2.0, fractional=1.0)
        self.assertGreater(size, 0.0)

    def test_no_edge_gives_zero(self):
        # p=0.5, b=1.0: (0.5*1-0.5)/1 = 0 → no edge
        size = kelly_fraction(0.5, 1.0)
        self.assertAlmostEqual(size, 0.0)

    def test_negative_edge_gives_zero(self):
        size = kelly_fraction(0.3, 1.0)
        self.assertAlmostEqual(size, 0.0)

    def test_fractional_kelly_reduces(self):
        full = kelly_fraction(0.6, 2.0, fractional=1.0)
        quarter = kelly_fraction(0.6, 2.0, fractional=0.25)
        self.assertAlmostEqual(quarter, full * 0.25, places=6)

    def test_invalid_inputs_give_zero(self):
        self.assertAlmostEqual(kelly_fraction(0.0, 2.0), 0.0)
        self.assertAlmostEqual(kelly_fraction(1.0, 2.0), 0.0)
        self.assertAlmostEqual(kelly_fraction(0.6, 0.0), 0.0)


class TestVolatilityAdjustedSize(unittest.TestCase):
    """Verify volatility adjustment scales correctly."""

    def test_high_vol_reduces_size(self):
        adjusted = volatility_adjusted_size(0.10, current_vol=0.30, target_vol=0.15)
        self.assertLess(adjusted, 0.10)

    def test_low_vol_increases_size(self):
        adjusted = volatility_adjusted_size(0.10, current_vol=0.10, target_vol=0.15)
        self.assertGreater(adjusted, 0.10)

    def test_equal_vol_no_change(self):
        adjusted = volatility_adjusted_size(0.10, current_vol=0.15, target_vol=0.15)
        self.assertAlmostEqual(adjusted, 0.10)

    def test_zero_vol_no_change(self):
        adjusted = volatility_adjusted_size(0.10, current_vol=0.0, target_vol=0.15)
        self.assertAlmostEqual(adjusted, 0.10)

    def test_capped_at_2x(self):
        adjusted = volatility_adjusted_size(0.10, current_vol=0.01, target_vol=0.15)
        self.assertLessEqual(adjusted, 0.20)  # 2x base


class TestPositionSizer(unittest.TestCase):
    """Verify the comprehensive position_sizer routes correctly."""

    def test_conviction_method(self):
        result = position_sizer(conviction_level=4, method="conviction", max_position_pct=0.20)
        self.assertAlmostEqual(result["base_size"], 0.15)
        self.assertEqual(result["final_size"], result["base_size"])  # No vol/liq adjustment
        self.assertIn("conviction(level=4)", result["adjustments"])

    def test_kelly_method_with_data(self):
        result = position_sizer(
            conviction_level=3,
            win_prob=0.6,
            win_loss_ratio=2.0,
            method="kelly",
            max_position_pct=0.20,
        )
        self.assertGreater(result["base_size"], 0.0)
        self.assertTrue(any("kelly" in a for a in result["adjustments"]))

    def test_kelly_without_data_falls_through(self):
        result = position_sizer(
            conviction_level=3,
            win_prob=None,
            win_loss_ratio=None,
            method="kelly",
            max_position_pct=0.20,
        )
        # Falls through to fixed sizing
        self.assertEqual(result["base_size"], 0.20)

    def test_vol_adjustment_applied(self):
        without_vol = position_sizer(conviction_level=4, method="conviction", max_position_pct=0.20)
        with_high_vol = position_sizer(
            conviction_level=4,
            asset_volatility=0.60,
            method="conviction",
            max_position_pct=0.20,
        )
        self.assertLess(with_high_vol["final_size"], without_vol["final_size"])

    def test_liquidity_adjustment_applied(self):
        # Small ADV should reduce position
        result = position_sizer(
            conviction_level=5,
            portfolio_value=1_000_000,
            avg_daily_volume=1000,
            avg_price=50.0,
            method="conviction",
            max_position_pct=0.20,
        )
        # Max ADV = 1000 * 0.01 = 10 shares = $500 = 0.05% of portfolio
        self.assertLess(result["final_size"], 0.20)


# =============================================================================
# Unit Tests: Stop Losses
# =============================================================================


class TestStopLossLogic(unittest.TestCase):
    """Verify stop loss checks are live, not stubs."""

    def _make_backtest(self, stop_loss_pct=None, trailing_stop_pct=None):
        """Create a PortfolioBacktest with mock DB for stop loss testing."""
        db = MagicMock()
        db.connect.return_value = MagicMock()
        config = BacktestConfig(
            start_date="2024-01-01",
            end_date="2024-12-31",
            stop_loss_pct=stop_loss_pct,
            trailing_stop_pct=trailing_stop_pct,
        )
        bt = PortfolioBacktest.__new__(PortfolioBacktest)
        bt.db = db
        bt.config = config
        bt.cash = 100_000
        bt.positions = {}
        bt.trade_log = []
        bt._trade_counter = 0
        bt.price_manager = MagicMock()
        return bt

    def test_fixed_stop_triggers(self):
        """Fixed stop loss triggers when unrealized loss exceeds threshold."""
        bt = self._make_backtest(stop_loss_pct=0.10)
        bt.positions["AAPL"] = Position(
            symbol="AAPL",
            thesis_id="test",
            shares=100,
            avg_cost=100.0,
            entry_date="2024-01-01",
            entry_conviction=4,
            current_price=85.0,  # -15% loss, exceeds 10% stop
            high_water_mark=110.0,
        )
        bt.price_manager.get_price_at.return_value = 85.0
        bt._check_stop_losses("2024-06-01")
        # Position should be closed
        self.assertNotIn("AAPL", bt.positions)
        # Should have a SELL trade with reason "stop_loss"
        sells = [t for t in bt.trade_log if t.side == "SELL"]
        self.assertEqual(len(sells), 1)
        self.assertEqual(sells[0].reason, "stop_loss")

    def test_fixed_stop_does_not_trigger_below_threshold(self):
        """Fixed stop does NOT trigger when loss is within threshold."""
        bt = self._make_backtest(stop_loss_pct=0.10)
        bt.positions["AAPL"] = Position(
            symbol="AAPL",
            thesis_id="test",
            shares=100,
            avg_cost=100.0,
            entry_date="2024-01-01",
            entry_conviction=4,
            current_price=95.0,  # -5% loss, within 10% stop
            high_water_mark=100.0,
        )
        bt._check_stop_losses("2024-06-01")
        self.assertIn("AAPL", bt.positions)

    def test_trailing_stop_triggers(self):
        """Trailing stop triggers when drop from high water mark exceeds threshold."""
        bt = self._make_backtest(trailing_stop_pct=0.10)
        bt.positions["AAPL"] = Position(
            symbol="AAPL",
            thesis_id="test",
            shares=100,
            avg_cost=80.0,
            entry_date="2024-01-01",
            entry_conviction=4,
            current_price=95.0,  # Still profitable from entry...
            high_water_mark=110.0,  # ...but dropped 13.6% from high
        )
        bt.price_manager.get_price_at.return_value = 95.0
        bt._check_stop_losses("2024-06-01")
        self.assertNotIn("AAPL", bt.positions)
        sells = [t for t in bt.trade_log if t.side == "SELL"]
        self.assertEqual(len(sells), 1)
        self.assertEqual(sells[0].reason, "trailing_stop")

    def test_trailing_stop_does_not_trigger_below_threshold(self):
        """Trailing stop does NOT trigger when drop is within threshold."""
        bt = self._make_backtest(trailing_stop_pct=0.10)
        bt.positions["AAPL"] = Position(
            symbol="AAPL",
            thesis_id="test",
            shares=100,
            avg_cost=80.0,
            entry_date="2024-01-01",
            entry_conviction=4,
            current_price=105.0,  # Only 4.5% from high
            high_water_mark=110.0,
        )
        bt._check_stop_losses("2024-06-01")
        self.assertIn("AAPL", bt.positions)

    def test_no_stops_configured_no_action(self):
        """If both stop types are None, no positions are closed."""
        bt = self._make_backtest(stop_loss_pct=None, trailing_stop_pct=None)
        bt.positions["AAPL"] = Position(
            symbol="AAPL",
            thesis_id="test",
            shares=100,
            avg_cost=100.0,
            entry_date="2024-01-01",
            entry_conviction=4,
            current_price=50.0,  # -50% loss but no stops configured
            high_water_mark=100.0,
        )
        bt._check_stop_losses("2024-06-01")
        self.assertIn("AAPL", bt.positions)

    def test_fixed_stop_takes_priority_over_trailing(self):
        """When both stops configured, fixed triggers first (continue skips trailing check)."""
        bt = self._make_backtest(stop_loss_pct=0.10, trailing_stop_pct=0.05)
        bt.positions["AAPL"] = Position(
            symbol="AAPL",
            thesis_id="test",
            shares=100,
            avg_cost=100.0,
            entry_date="2024-01-01",
            entry_conviction=4,
            current_price=85.0,  # -15% from cost, triggers fixed stop
            high_water_mark=110.0,
        )
        bt.price_manager.get_price_at.return_value = 85.0
        bt._check_stop_losses("2024-06-01")
        self.assertNotIn("AAPL", bt.positions)
        sells = [t for t in bt.trade_log if t.side == "SELL"]
        self.assertEqual(sells[0].reason, "stop_loss")  # Fixed, not trailing


# =============================================================================
# Unit Tests: Sizing Method Routing
# =============================================================================


class TestSizingMethodRouting(unittest.TestCase):
    """Verify position_size_method in config actually routes through position_sizer."""

    def _make_backtest_with_prices(self, method="conviction"):
        """Create a PortfolioBacktest with in-memory price DB for sizing tests."""
        # Create in-memory SQLite with price data
        conn = sqlite3.connect(":memory:")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS price_history (
                symbol TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL, high REAL, low REAL, close REAL,
                adj_close REAL, volume INTEGER,
                source TEXT DEFAULT 'test', fetched_at TEXT,
                PRIMARY KEY (symbol, date)
            );
        """)
        # Insert price data for AAPL: 100 days of prices
        import random
        random.seed(42)
        price = 150.0
        for i in range(200):
            date = (datetime(2024, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d")
            price *= (1 + random.gauss(0.0005, 0.015))
            conn.execute(
                "INSERT INTO price_history VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("AAPL", date, price, price*1.01, price*0.99, price, price, 1_000_000, "test", "2024-01-01")
            )
        conn.commit()

        db = MagicMock()
        db.connect.return_value = conn

        config = BacktestConfig(
            start_date="2024-01-01",
            end_date="2024-07-01",
            position_size_method=method,
            max_position_pct=0.20,
        )
        bt = PortfolioBacktest.__new__(PortfolioBacktest)
        bt.db = db
        bt.config = config
        bt.cash = 100_000
        bt.positions = {}
        bt.trade_log = []
        bt._trade_counter = 0

        # Mock price_manager
        pm = MagicMock()
        pm.get_price_at.return_value = 150.0
        bt.price_manager = pm

        return bt

    def test_conviction_method_uses_conviction_sizing(self):
        """When method='conviction', size scales with conviction level."""
        bt = self._make_backtest_with_prices(method="conviction")
        signals = [{
            "thesis_id": "test-thesis",
            "conviction_level": 5,
            "tickers": ["AAPL"],
            "recommendation": "BUY",
            "position_size": 0.20,
            "conviction_score": 0.95,
        }]
        targets = bt._calculate_target_positions(signals, "2024-06-01")
        self.assertIn("AAPL", targets)
        # Level 5 conviction with 20% max → should be close to 20% (may be vol-adjusted)
        self.assertGreater(targets["AAPL"]["target_pct"], 0.05)
        self.assertEqual(targets["AAPL"]["sizing_method"], "conviction")

    def test_conviction_level_affects_size(self):
        """Higher conviction should produce larger position."""
        bt = self._make_backtest_with_prices(method="conviction")

        signals_high = [{
            "thesis_id": "test", "conviction_level": 5,
            "tickers": ["AAPL"], "recommendation": "BUY",
            "position_size": 0.20, "conviction_score": 0.95,
        }]
        signals_low = [{
            "thesis_id": "test", "conviction_level": 3,
            "tickers": ["AAPL"], "recommendation": "BUY",
            "position_size": 0.10, "conviction_score": 0.60,
        }]

        targets_high = bt._calculate_target_positions(signals_high, "2024-06-01")
        # Reset state
        bt.positions = {}
        bt.trade_log = []
        targets_low = bt._calculate_target_positions(signals_low, "2024-06-01")

        self.assertGreater(
            targets_high["AAPL"]["target_pct"],
            targets_low["AAPL"]["target_pct"],
            "Higher conviction should produce larger position size"
        )

    def test_kelly_method_recorded_in_target(self):
        """When method='kelly', sizing_method is recorded."""
        bt = self._make_backtest_with_prices(method="kelly")
        signals = [{
            "thesis_id": "test", "conviction_level": 4,
            "tickers": ["AAPL"], "recommendation": "BUY",
            "position_size": 0.15, "conviction_score": 0.80,
        }]
        targets = bt._calculate_target_positions(signals, "2024-06-01")
        self.assertIn("AAPL", targets)
        self.assertEqual(targets["AAPL"]["sizing_method"], "kelly")

    def test_sizing_adjustments_recorded(self):
        """Target should include sizing_adjustments list."""
        bt = self._make_backtest_with_prices(method="conviction")
        signals = [{
            "thesis_id": "test", "conviction_level": 4,
            "tickers": ["AAPL"], "recommendation": "BUY",
            "position_size": 0.15, "conviction_score": 0.80,
        }]
        targets = bt._calculate_target_positions(signals, "2024-06-01")
        self.assertIn("sizing_adjustments", targets["AAPL"])
        self.assertIsInstance(targets["AAPL"]["sizing_adjustments"], list)


# =============================================================================
# Unit Tests: Trade Receipt Contains Sizing
# =============================================================================


class TestTradeReceiptSizing(unittest.TestCase):
    """Verify Trade.to_dict() includes sizing_method for receipt auditability."""

    def test_trade_has_sizing_method_field(self):
        trade = Trade(
            trade_id="T00001",
            date="2024-06-01",
            symbol="AAPL",
            thesis_id="test",
            side="BUY",
            shares=100,
            price=150.0,
            slippage=0.15,
            commission=0.0,
            conviction_level=4,
            reason="new_position",
            sizing_method="kelly",
        )
        d = trade.to_dict()
        self.assertEqual(d["sizing_method"], "kelly")

    def test_trade_default_sizing_is_conviction(self):
        trade = Trade(
            trade_id="T00001",
            date="2024-06-01",
            symbol="AAPL",
            thesis_id="test",
            side="BUY",
            shares=100,
            price=150.0,
            slippage=0.15,
            commission=0.0,
            conviction_level=4,
            reason="new_position",
        )
        self.assertEqual(trade.sizing_method, "conviction")
        self.assertIn("sizing_method", trade.to_dict())


# =============================================================================
# Unit Tests: Helper Methods
# =============================================================================


class TestHelperMethods(unittest.TestCase):
    """Verify the helper methods for volatility, volume, win stats."""

    def _make_bt_with_db(self):
        """Create backtest with in-memory price DB."""
        conn = sqlite3.connect(":memory:")
        conn.executescript("""
            CREATE TABLE price_history (
                symbol TEXT, date TEXT, open REAL, high REAL, low REAL,
                close REAL, adj_close REAL, volume INTEGER,
                source TEXT, fetched_at TEXT,
                PRIMARY KEY (symbol, date)
            );
        """)
        # 100 days of AAPL prices
        import random
        random.seed(123)
        price = 150.0
        for i in range(100):
            date = (datetime(2024, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d")
            if datetime(2024, 1, 1).weekday() < 5:  # weekdays only
                price *= (1 + random.gauss(0.0005, 0.02))
                vol = random.randint(500_000, 2_000_000)
                conn.execute(
                    "INSERT OR IGNORE INTO price_history VALUES (?,?,?,?,?,?,?,?,?,?)",
                    ("AAPL", date, price, price, price, price, price, vol, "test", "now")
                )
        conn.commit()

        db = MagicMock()
        db.connect.return_value = conn
        config = BacktestConfig(start_date="2024-01-01", end_date="2024-12-31")
        bt = PortfolioBacktest.__new__(PortfolioBacktest)
        bt.db = db
        bt.config = config
        bt.trade_log = []
        bt.positions = {}
        bt.cash = 100_000
        bt._trade_counter = 0
        bt.price_manager = MagicMock()
        return bt

    def test_trailing_volatility_returns_float(self):
        bt = self._make_bt_with_db()
        vol = bt._get_trailing_volatility("AAPL", "2024-03-01")
        self.assertIsNotNone(vol)
        self.assertIsInstance(vol, float)
        self.assertGreater(vol, 0.0)

    def test_trailing_volatility_none_if_insufficient_data(self):
        bt = self._make_bt_with_db()
        vol = bt._get_trailing_volatility("AAPL", "2024-01-02")  # Only ~2 days of data
        self.assertIsNone(vol)

    def test_avg_volume_returns_int(self):
        bt = self._make_bt_with_db()
        avg_vol = bt._get_avg_volume("AAPL", "2024-03-01")
        self.assertIsNotNone(avg_vol)
        self.assertIsInstance(avg_vol, int)
        self.assertGreater(avg_vol, 0)

    def test_running_win_stats_none_with_few_trades(self):
        bt = self._make_bt_with_db()
        # No trades yet
        wp, wlr = bt._get_running_win_stats()
        self.assertIsNone(wp)
        self.assertIsNone(wlr)

    def test_running_win_stats_computes_with_enough_trades(self):
        bt = self._make_bt_with_db()
        # Add 10 completed trade pairs
        for i in range(10):
            bt.trade_log.append(Trade(
                f"T{i*2}", "2024-01-01", f"SYM{i}", "t", "BUY",
                10, 100.0, 0, 0, 3, "test",
            ))
            # 6 winners, 4 losers
            sell_price = 110.0 if i < 6 else 90.0
            bt.trade_log.append(Trade(
                f"T{i*2+1}", "2024-02-01", f"SYM{i}", "t", "SELL",
                10, sell_price, 0, 0, 3, "test",
            ))
        wp, wlr = bt._get_running_win_stats()
        self.assertIsNotNone(wp)
        self.assertAlmostEqual(wp, 0.6, places=2)
        self.assertIsNotNone(wlr)
        self.assertGreater(wlr, 0)


# =============================================================================
# Integration Test: End-to-End Sizing Through Backtest
# =============================================================================


class TestEndToEndSizingPath(unittest.TestCase):
    """
    Integration test: prove that conviction → sizing → trade is live.

    This is the key acceptance test. If sizing is bypassed,
    different conviction levels would produce identical positions.
    """

    def _make_integrated_backtest(self, method="conviction"):
        """Build a backtest with real price data in SQLite."""
        conn = sqlite3.connect(":memory:")
        conn.executescript("""
            CREATE TABLE price_history (
                symbol TEXT, date TEXT, open REAL, high REAL, low REAL,
                close REAL, adj_close REAL, volume INTEGER,
                source TEXT, fetched_at TEXT,
                PRIMARY KEY (symbol, date)
            );
        """)
        import random
        random.seed(42)

        # Two stocks with different volatilities
        for symbol, base_price, base_vol, daily_std in [
            ("LOW_VOL", 100.0, 500_000, 0.005),
            ("HIGH_VOL", 100.0, 50_000, 0.03),
        ]:
            price = base_price
            for i in range(200):
                dt = datetime(2024, 1, 1) + timedelta(days=i)
                if dt.weekday() < 5:
                    date = dt.strftime("%Y-%m-%d")
                    price *= (1 + random.gauss(0.0003, daily_std))
                    conn.execute(
                        "INSERT OR IGNORE INTO price_history VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (symbol, date, price, price*1.01, price*0.99, price, price,
                         base_vol + random.randint(-10000, 10000), "test", "now")
                    )
            conn.commit()

        db = MagicMock()
        db.connect.return_value = conn

        config = BacktestConfig(
            start_date="2024-01-01",
            end_date="2024-07-01",
            position_size_method=method,
            max_position_pct=0.20,
            min_conviction_to_trade=2,
        )
        bt = PortfolioBacktest.__new__(PortfolioBacktest)
        bt.db = db
        bt.config = config
        bt.cash = 100_000
        bt.positions = {}
        bt.trade_log = []
        bt._trade_counter = 0

        pm = MagicMock()
        pm.get_price_at.return_value = 100.0
        bt.price_manager = pm

        return bt

    def test_conviction_level_produces_different_sizes(self):
        """
        CRITICAL: Different conviction levels MUST produce different position sizes.
        If this test passes, sizing is live (not bypassed).
        """
        bt = self._make_integrated_backtest(method="conviction")

        for level in [3, 4, 5]:
            bt.positions = {}
            bt.trade_log = []
            signals = [{
                "thesis_id": "test",
                "conviction_level": level,
                "tickers": ["LOW_VOL"],
                "recommendation": "BUY",
                "position_size": 0.10,
                "conviction_score": level * 0.2,
            }]
            targets = bt._calculate_target_positions(signals, "2024-06-01")
            self.assertIn("LOW_VOL", targets, f"No target for conviction {level}")

        # Verify sizes are different
        sizes = {}
        for level in [3, 4, 5]:
            bt.positions = {}
            bt.trade_log = []
            signals = [{
                "thesis_id": "test",
                "conviction_level": level,
                "tickers": ["LOW_VOL"],
                "recommendation": "BUY",
                "position_size": 0.10,
                "conviction_score": level * 0.2,
            }]
            targets = bt._calculate_target_positions(signals, "2024-06-01")
            sizes[level] = targets["LOW_VOL"]["target_pct"]

        # Level 5 > Level 4 > Level 3
        self.assertGreater(sizes[5], sizes[4], "Level 5 should be larger than Level 4")
        self.assertGreater(sizes[4], sizes[3], "Level 4 should be larger than Level 3")

    def test_sizing_method_recorded_in_trade(self):
        """When a trade is executed, sizing_method is recorded."""
        bt = self._make_integrated_backtest(method="kelly")
        target = {
            "symbol": "LOW_VOL",
            "thesis_id": "test",
            "target_pct": 0.10,
            "conviction_level": 4,
            "sizing_method": "kelly",
            "sizing_adjustments": ["kelly(p=0.60, b=2.00)"],
        }
        bt._execute_buy(
            "LOW_VOL", "2024-06-01", 100, 100.0, "test", 4,
            "new_position", sizing_method="kelly"
        )
        self.assertEqual(len(bt.trade_log), 1)
        self.assertEqual(bt.trade_log[0].sizing_method, "kelly")
        receipt = bt.trade_log[0].to_dict()
        self.assertEqual(receipt["sizing_method"], "kelly")


# =============================================================================
# Integration Test: Trailing Stop Path
# =============================================================================


class TestTrailingStopIntegration(unittest.TestCase):
    """
    Integration test: prove trailing stop path is live.

    If trailing stop is stubbed, positions that drop from their high
    water mark would NOT be closed.
    """

    def _make_bt(self):
        db = MagicMock()
        db.connect.return_value = MagicMock()
        config = BacktestConfig(
            start_date="2024-01-01",
            end_date="2024-12-31",
            stop_loss_pct=None,  # No fixed stop
            trailing_stop_pct=0.10,  # 10% trailing stop
        )
        bt = PortfolioBacktest.__new__(PortfolioBacktest)
        bt.db = db
        bt.config = config
        bt.cash = 100_000
        bt.positions = {}
        bt.trade_log = []
        bt._trade_counter = 0
        bt.price_manager = MagicMock()
        return bt

    def test_profitable_position_closed_by_trailing_stop(self):
        """
        CRITICAL: A position that is PROFITABLE from entry but has dropped
        significantly from its HIGH should be closed by trailing stop.

        This proves trailing stop uses high_water_mark, not cost basis.
        """
        bt = self._make_bt()
        bt.positions["NVDA"] = Position(
            symbol="NVDA",
            thesis_id="ai-thesis",
            shares=50,
            avg_cost=100.0,       # Bought at $100
            entry_date="2024-01-01",
            entry_conviction=5,
            current_price=125.0,   # Now at $125 (still profitable!)
            high_water_mark=150.0, # Was at $150 (dropped 16.7% from high)
        )
        bt.price_manager.get_price_at.return_value = 125.0
        bt._check_stop_losses("2024-06-01")

        # Position should be closed despite being profitable
        self.assertNotIn("NVDA", bt.positions,
                         "Trailing stop should close position that dropped 16.7% from high")
        self.assertEqual(bt.trade_log[0].reason, "trailing_stop")

    def test_position_near_high_not_closed(self):
        """Position close to its high water mark should NOT be closed."""
        bt = self._make_bt()
        bt.positions["NVDA"] = Position(
            symbol="NVDA",
            thesis_id="ai-thesis",
            shares=50,
            avg_cost=100.0,
            entry_date="2024-01-01",
            entry_conviction=5,
            current_price=145.0,   # Only 3.3% below high
            high_water_mark=150.0,
        )
        bt._check_stop_losses("2024-06-01")
        self.assertIn("NVDA", bt.positions,
                      "Position 3.3% below high should NOT trigger 10% trailing stop")


if __name__ == "__main__":
    unittest.main()
