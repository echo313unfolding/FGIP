"""
FGIP Price Manager - Fetch and cache historical OHLCV data.

Provides persistent caching of price data to:
1. Avoid repeated API calls
2. Enable reproducible backtests
3. Support offline operation after initial fetch

Data source: yfinance (Yahoo Finance)

Usage:
    from fgip.data.price_manager import PriceManager
    from fgip.db import FGIPDatabase

    db = FGIPDatabase("fgip.db")
    pm = PriceManager(db)

    # Fetch historical data
    df = pm.get_history("VRT", "2024-01-01", "2025-12-31")

    # Get specific price
    price = pm.get_price_at("VRT", "2024-06-15")

    # Calculate returns
    returns = pm.get_returns("VRT", "2024-01-01", "2024-12-31")
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False


# Price history table schema (for migration)
PRICE_HISTORY_SCHEMA = """
-- Historical OHLCV price data
CREATE TABLE IF NOT EXISTS price_history (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    adj_close REAL,
    volume INTEGER,
    source TEXT DEFAULT 'yfinance',
    fetched_at TEXT,
    PRIMARY KEY (symbol, date)
);
CREATE INDEX IF NOT EXISTS idx_price_symbol ON price_history(symbol);
CREATE INDEX IF NOT EXISTS idx_price_date ON price_history(date);
"""


@dataclass
class PriceBar:
    """Single OHLCV bar."""
    symbol: str
    date: str
    open: float
    high: float
    low: float
    close: float
    adj_close: float
    volume: int
    source: str = "yfinance"

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "date": self.date,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "adj_close": self.adj_close,
            "volume": self.volume,
            "source": self.source,
        }


class PriceManager:
    """
    Fetch and cache historical OHLCV data.

    Features:
    - Persistent SQLite caching
    - Automatic gap detection and filling
    - Bulk fetch for efficiency
    - Returns calculation
    """

    def __init__(self, db, cache_ttl_days: int = 1):
        """
        Initialize PriceManager.

        Args:
            db: FGIPDatabase instance
            cache_ttl_days: How long cached data is considered fresh (default 1 day)
        """
        self.db = db
        self.cache_ttl_days = cache_ttl_days
        self._ensure_schema()

    def _ensure_schema(self):
        """Ensure price_history table exists."""
        conn = self.db.connect()
        try:
            conn.executescript(PRICE_HISTORY_SCHEMA)
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Table already exists

    def get_history(
        self,
        symbol: str,
        start: str,
        end: str,
        force_refresh: bool = False
    ) -> "pd.DataFrame":
        """
        Get OHLCV data for a symbol, fetching from yfinance if not cached.

        Args:
            symbol: Stock ticker (e.g., "VRT")
            start: Start date (YYYY-MM-DD)
            end: End date (YYYY-MM-DD)
            force_refresh: Bypass cache and re-fetch

        Returns:
            DataFrame with columns: open, high, low, close, adj_close, volume
            Index: date
        """
        if not HAS_PANDAS:
            raise ImportError("pandas is required for get_history()")

        symbol = symbol.upper()

        # Check cache first
        if not force_refresh:
            cached = self._get_from_cache(symbol, start, end)
            if cached is not None and len(cached) > 0:
                # Check if we have data for the date range
                expected_days = self._trading_days_between(start, end)
                if len(cached) >= expected_days * 0.9:  # 90% coverage
                    return cached

        # Fetch from yfinance
        if not HAS_YFINANCE:
            raise ImportError("yfinance is required to fetch new data")

        try:
            df = self._fetch_from_yfinance(symbol, start, end)
            if df is not None and len(df) > 0:
                self._save_to_cache(symbol, df)
                return df
        except Exception as e:
            print(f"[PriceManager] Error fetching {symbol}: {e}")

        # Return cached data even if incomplete
        return self._get_from_cache(symbol, start, end) or pd.DataFrame()

    def bulk_fetch(
        self,
        symbols: List[str],
        start: str,
        end: str,
        verbose: bool = False
    ):
        """
        Fetch multiple symbols efficiently.

        Args:
            symbols: List of tickers
            start: Start date
            end: End date
            verbose: Print progress
        """
        for i, symbol in enumerate(symbols):
            if verbose:
                print(f"[{i+1}/{len(symbols)}] Fetching {symbol}...")
            try:
                self.get_history(symbol, start, end)
            except Exception as e:
                if verbose:
                    print(f"  Error: {e}")

    def get_price_at(self, symbol: str, date: str) -> Optional[float]:
        """
        Get closing price on a specific date.

        Args:
            symbol: Stock ticker
            date: Date (YYYY-MM-DD)

        Returns:
            Closing price or None if not available
        """
        symbol = symbol.upper()
        conn = self.db.connect()

        # Try exact date first
        row = conn.execute(
            "SELECT adj_close FROM price_history WHERE symbol = ? AND date = ?",
            (symbol, date)
        ).fetchone()

        if row:
            return row[0]

        # Try finding nearest previous trading day (up to 5 days back)
        for days_back in range(1, 6):
            prev_date = (datetime.fromisoformat(date) - timedelta(days=days_back)).strftime("%Y-%m-%d")
            row = conn.execute(
                "SELECT adj_close FROM price_history WHERE symbol = ? AND date = ?",
                (symbol, prev_date)
            ).fetchone()
            if row:
                return row[0]

        return None

    def get_returns(
        self,
        symbol: str,
        start: str,
        end: str
    ) -> "pd.Series":
        """
        Calculate daily returns for a symbol.

        Args:
            symbol: Stock ticker
            start: Start date
            end: End date

        Returns:
            Series of daily percentage returns
        """
        if not HAS_PANDAS:
            raise ImportError("pandas is required for get_returns()")

        df = self.get_history(symbol, start, end)
        if df.empty:
            return pd.Series(dtype=float)

        returns = df["adj_close"].pct_change().dropna()
        return returns

    def get_prices_for_date(
        self,
        symbols: List[str],
        date: str
    ) -> Dict[str, float]:
        """
        Get closing prices for multiple symbols on a specific date.

        Args:
            symbols: List of tickers
            date: Date (YYYY-MM-DD)

        Returns:
            Dict mapping symbol to price
        """
        prices = {}
        for symbol in symbols:
            price = self.get_price_at(symbol, date)
            if price is not None:
                prices[symbol.upper()] = price
        return prices

    def get_available_range(self, symbol: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Get the date range available in cache for a symbol.

        Returns:
            (start_date, end_date) or (None, None) if no data
        """
        symbol = symbol.upper()
        conn = self.db.connect()

        row = conn.execute(
            "SELECT MIN(date), MAX(date) FROM price_history WHERE symbol = ?",
            (symbol,)
        ).fetchone()

        if row and row[0]:
            return (row[0], row[1])
        return (None, None)

    def get_cached_symbols(self) -> List[str]:
        """Get list of symbols with cached data."""
        conn = self.db.connect()
        rows = conn.execute(
            "SELECT DISTINCT symbol FROM price_history ORDER BY symbol"
        ).fetchall()
        return [row[0] for row in rows]

    def _fetch_from_yfinance(
        self,
        symbol: str,
        start: str,
        end: str
    ) -> "pd.DataFrame":
        """Fetch data from yfinance."""
        ticker = yf.Ticker(symbol)

        # Add a day to end date to include it
        end_dt = datetime.fromisoformat(end) + timedelta(days=1)
        end_str = end_dt.strftime("%Y-%m-%d")

        hist = ticker.history(start=start, end=end_str, auto_adjust=False)

        if hist.empty:
            return pd.DataFrame()

        # Normalize column names
        hist.columns = [c.lower().replace(" ", "_") for c in hist.columns]

        # Ensure we have required columns
        required = ["open", "high", "low", "close", "volume"]
        for col in required:
            if col not in hist.columns:
                return pd.DataFrame()

        # Use Adj Close if available, otherwise Close
        if "adj_close" in hist.columns:
            pass
        elif "adj close" in hist.columns:
            hist["adj_close"] = hist["adj close"]
        else:
            hist["adj_close"] = hist["close"]

        # Reset index to get date as column
        hist = hist.reset_index()
        hist["date"] = hist["Date"].dt.strftime("%Y-%m-%d")
        hist = hist.set_index("date")

        # Select columns
        result = hist[["open", "high", "low", "close", "adj_close", "volume"]].copy()
        return result

    def _get_from_cache(
        self,
        symbol: str,
        start: str,
        end: str
    ) -> Optional["pd.DataFrame"]:
        """Get data from SQLite cache."""
        if not HAS_PANDAS:
            return None

        conn = self.db.connect()
        rows = conn.execute(
            """SELECT date, open, high, low, close, adj_close, volume
               FROM price_history
               WHERE symbol = ? AND date >= ? AND date <= ?
               ORDER BY date""",
            (symbol, start, end)
        ).fetchall()

        if not rows:
            return None

        df = pd.DataFrame(
            rows,
            columns=["date", "open", "high", "low", "close", "adj_close", "volume"]
        )
        df = df.set_index("date")
        return df

    def _save_to_cache(self, symbol: str, df: "pd.DataFrame"):
        """Save data to SQLite cache."""
        conn = self.db.connect()
        now = datetime.utcnow().isoformat() + "Z"

        for date, row in df.iterrows():
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO price_history
                       (symbol, date, open, high, low, close, adj_close, volume, source, fetched_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        symbol,
                        date,
                        float(row["open"]),
                        float(row["high"]),
                        float(row["low"]),
                        float(row["close"]),
                        float(row["adj_close"]),
                        int(row["volume"]),
                        "yfinance",
                        now,
                    )
                )
            except Exception:
                pass  # Skip invalid rows

        conn.commit()

    def _trading_days_between(self, start: str, end: str) -> int:
        """Estimate trading days between two dates (rough approximation)."""
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        total_days = (end_dt - start_dt).days
        # Roughly 252 trading days per 365 calendar days
        return int(total_days * 252 / 365)

    def clear_cache(self, symbol: Optional[str] = None):
        """
        Clear cached price data.

        Args:
            symbol: Specific symbol to clear, or None for all
        """
        conn = self.db.connect()
        if symbol:
            conn.execute(
                "DELETE FROM price_history WHERE symbol = ?",
                (symbol.upper(),)
            )
        else:
            conn.execute("DELETE FROM price_history")
        conn.commit()


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from fgip.db import FGIPDatabase

    import argparse
    parser = argparse.ArgumentParser(description="FGIP Price Manager")
    parser.add_argument("db_path", help="Path to FGIP database")
    parser.add_argument("--symbol", "-s", help="Symbol to fetch")
    parser.add_argument("--symbols", nargs="+", help="Multiple symbols to fetch")
    parser.add_argument("--start", default="2020-01-01", help="Start date")
    parser.add_argument("--end", default=None, help="End date (default: today)")
    parser.add_argument("--list", "-l", action="store_true", help="List cached symbols")
    parser.add_argument("--clear", action="store_true", help="Clear cache")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    if args.end is None:
        args.end = datetime.now().strftime("%Y-%m-%d")

    db = FGIPDatabase(args.db_path)
    pm = PriceManager(db)

    if args.clear:
        pm.clear_cache(args.symbol)
        print("Cache cleared")
    elif args.list:
        symbols = pm.get_cached_symbols()
        print(f"Cached symbols ({len(symbols)}):")
        for sym in symbols:
            start, end = pm.get_available_range(sym)
            print(f"  {sym}: {start} to {end}")
    elif args.symbols:
        print(f"Fetching {len(args.symbols)} symbols from {args.start} to {args.end}...")
        pm.bulk_fetch(args.symbols, args.start, args.end, verbose=args.verbose)
        print("Done")
    elif args.symbol:
        print(f"Fetching {args.symbol} from {args.start} to {args.end}...")
        df = pm.get_history(args.symbol, args.start, args.end)
        print(f"Got {len(df)} rows")
        if args.verbose and len(df) > 0:
            print(df.tail(10))
    else:
        parser.print_help()
