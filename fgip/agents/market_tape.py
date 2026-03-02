"""
FGIP Market Tape Agent - Price data, technicals, volume signals.

The "Market Confirmation" layer in the trade memo system.
Answers: "Does the tape agree with the thesis?"

Data sources:
- yfinance for price/volume (free, rate-limited)
- Calculated technicals (SMA, RSI, volume ratios)
- Event detection (breakouts, volume spikes)

Safety rules:
- Read-only (no trading)
- Rate limiting to respect API terms
- All signals are informational, not recommendations
"""

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fgip.analysis.provenance import DataProvenance

try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False



# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class PriceSnapshot:
    """Current price state for a symbol."""
    symbol: str
    price: float
    prev_close: float
    volume: int
    avg_volume: int
    day_change_pct: float
    fifty_two_week_high: float
    fifty_two_week_low: float
    pct_from_high: float
    pct_from_low: float
    timestamp: str


@dataclass
class TechnicalSignals:
    """Technical indicators for trend analysis."""
    symbol: str
    sma_20: float
    sma_50: float
    sma_200: float
    rsi_14: float
    volume_ratio: float  # Current vs avg
    trend: str  # BULLISH, BEARISH, NEUTRAL
    signals: List[str]  # Human-readable signals


@dataclass
class TapeEvent:
    """Significant tape event (breakout, spike, etc)."""
    symbol: str
    event_type: str  # BREAKOUT, BREAKDOWN, VOLUME_SPIKE, GAP
    description: str
    magnitude: float
    timestamp: str


@dataclass
class TapeAnalysis:
    """Complete tape analysis for a symbol."""
    symbol: str
    snapshot: PriceSnapshot
    technicals: TechnicalSignals
    events: List[TapeEvent]
    tape_verdict: str  # CONFIRMING, NEUTRAL, DIVERGING
    confidence: float
    analysis_time: str
    provenance: Optional[DataProvenance] = None  # Data source verification


# =============================================================================
# TECHNICAL CALCULATIONS
# =============================================================================

def calculate_sma(prices: List[float], period: int) -> Optional[float]:
    """Simple moving average."""
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def calculate_rsi(prices: List[float], period: int = 14) -> Optional[float]:
    """Relative Strength Index."""
    if len(prices) < period + 1:
        return None

    gains = []
    losses = []

    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    if len(gains) < period:
        return None

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def detect_trend(price: float, sma_20: float, sma_50: float, sma_200: float) -> str:
    """Detect trend from SMA alignment."""
    if sma_20 is None or sma_50 is None or sma_200 is None:
        return "NEUTRAL"

    # Bullish: Price > SMA20 > SMA50 > SMA200
    if price > sma_20 > sma_50 > sma_200:
        return "BULLISH"

    # Bearish: Price < SMA20 < SMA50 < SMA200
    if price < sma_20 < sma_50 < sma_200:
        return "BEARISH"

    return "NEUTRAL"


# =============================================================================
# MARKET TAPE AGENT
# =============================================================================

class MarketTapeAgent:
    """
    Price/volume data layer for trade confirmation.

    Answers: "Does the tape agree with the thesis?"
    """

    AGENT_NAME = "market-tape"
    TIER = 2  # Market data is secondary to fundamentals

    def __init__(self, db_path: str = "fgip.db"):
        """Initialize with database path."""
        self.db_path = Path(db_path)
        self._cache: Dict[str, Tuple[TapeAnalysis, datetime]] = {}
        self._cache_ttl = timedelta(minutes=5)

    def _get_db(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def fetch_tape(self, symbol: str, force_refresh: bool = False) -> Optional[TapeAnalysis]:
        """
        Fetch and analyze tape for a symbol.

        Args:
            symbol: Stock ticker (e.g., "INTC")
            force_refresh: Bypass cache

        Returns:
            TapeAnalysis or None if unavailable
        """
        if not HAS_YFINANCE:
            return self._mock_tape(symbol)

        # Check cache
        if not force_refresh and symbol in self._cache:
            cached, cached_at = self._cache[symbol]
            if datetime.now() - cached_at < self._cache_ttl:
                return cached

        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1y")
            info = ticker.info

            if hist.empty:
                return None

            # Compute content hash for provenance
            content_hash = hashlib.sha256(
                hist.to_json().encode()
            ).hexdigest()[:16]

            provenance = DataProvenance(
                source_type="yfinance",
                source_ref=symbol,
                retrieved_at=datetime.now().isoformat(),
                content_hash=content_hash,
                notes="Live market data"
            )

            # Get price data
            current_price = hist['Close'].iloc[-1]
            prev_close = hist['Close'].iloc[-2] if len(hist) > 1 else current_price
            current_volume = int(hist['Volume'].iloc[-1])
            avg_volume = int(hist['Volume'].mean())

            # 52-week range
            high_52w = hist['High'].max()
            low_52w = hist['Low'].min()

            snapshot = PriceSnapshot(
                symbol=symbol,
                price=round(current_price, 2),
                prev_close=round(prev_close, 2),
                volume=current_volume,
                avg_volume=avg_volume,
                day_change_pct=round((current_price - prev_close) / prev_close * 100, 2),
                fifty_two_week_high=round(high_52w, 2),
                fifty_two_week_low=round(low_52w, 2),
                pct_from_high=round((current_price - high_52w) / high_52w * 100, 2),
                pct_from_low=round((current_price - low_52w) / low_52w * 100, 2),
                timestamp=datetime.now().isoformat()
            )

            # Calculate technicals
            prices = hist['Close'].tolist()
            sma_20 = calculate_sma(prices, 20)
            sma_50 = calculate_sma(prices, 50)
            sma_200 = calculate_sma(prices, 200)
            rsi = calculate_rsi(prices, 14)

            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
            trend = detect_trend(current_price, sma_20, sma_50, sma_200)

            # Generate signals
            signals = []
            if sma_20 and current_price > sma_20:
                signals.append("Above SMA20")
            if sma_50 and current_price > sma_50:
                signals.append("Above SMA50")
            if sma_200 and current_price > sma_200:
                signals.append("Above SMA200")
            if rsi and rsi > 70:
                signals.append("RSI Overbought")
            if rsi and rsi < 30:
                signals.append("RSI Oversold")
            if volume_ratio > 2.0:
                signals.append(f"High Volume ({volume_ratio:.1f}x)")

            technicals = TechnicalSignals(
                symbol=symbol,
                sma_20=round(sma_20, 2) if sma_20 else 0,
                sma_50=round(sma_50, 2) if sma_50 else 0,
                sma_200=round(sma_200, 2) if sma_200 else 0,
                rsi_14=round(rsi, 2) if rsi else 50,
                volume_ratio=round(volume_ratio, 2),
                trend=trend,
                signals=signals
            )

            # Detect events
            events = self._detect_events(symbol, hist, snapshot, technicals)

            # Determine tape verdict
            tape_verdict, confidence = self._tape_verdict(snapshot, technicals, events)

            analysis = TapeAnalysis(
                symbol=symbol,
                snapshot=snapshot,
                technicals=technicals,
                events=events,
                tape_verdict=tape_verdict,
                confidence=confidence,
                analysis_time=datetime.now().isoformat(),
                provenance=provenance
            )

            # Cache it
            self._cache[symbol] = (analysis, datetime.now())

            return analysis

        except Exception as e:
            print(f"[MarketTape] Error fetching {symbol}: {e}")
            return None

    def _detect_events(
        self,
        symbol: str,
        hist,
        snapshot: PriceSnapshot,
        technicals: TechnicalSignals
    ) -> List[TapeEvent]:
        """Detect significant tape events."""
        events = []
        now = datetime.now().isoformat()

        # Volume spike
        if technicals.volume_ratio > 3.0:
            events.append(TapeEvent(
                symbol=symbol,
                event_type="VOLUME_SPIKE",
                description=f"Volume {technicals.volume_ratio:.1f}x average",
                magnitude=technicals.volume_ratio,
                timestamp=now
            ))

        # Breakout detection (new 20-day high)
        recent_high = hist['High'].tail(20).max()
        if snapshot.price >= recent_high * 0.98:  # Within 2% of 20-day high
            events.append(TapeEvent(
                symbol=symbol,
                event_type="BREAKOUT",
                description="Testing 20-day high",
                magnitude=(snapshot.price / recent_high) * 100,
                timestamp=now
            ))

        # Breakdown detection (new 20-day low)
        recent_low = hist['Low'].tail(20).min()
        if snapshot.price <= recent_low * 1.02:  # Within 2% of 20-day low
            events.append(TapeEvent(
                symbol=symbol,
                event_type="BREAKDOWN",
                description="Testing 20-day low",
                magnitude=(snapshot.price / recent_low) * 100,
                timestamp=now
            ))

        # Gap detection
        if abs(snapshot.day_change_pct) > 5:
            events.append(TapeEvent(
                symbol=symbol,
                event_type="GAP",
                description=f"Gap {'up' if snapshot.day_change_pct > 0 else 'down'} {abs(snapshot.day_change_pct):.1f}%",
                magnitude=abs(snapshot.day_change_pct),
                timestamp=now
            ))

        return events

    def _tape_verdict(
        self,
        snapshot: PriceSnapshot,
        technicals: TechnicalSignals,
        events: List[TapeEvent]
    ) -> Tuple[str, float]:
        """
        Determine if tape confirms or diverges from bullish thesis.

        Returns:
            (verdict, confidence)
        """
        score = 0.0

        # Trend component (40%)
        if technicals.trend == "BULLISH":
            score += 0.40
        elif technicals.trend == "BEARISH":
            score -= 0.40

        # RSI component (20%)
        if technicals.rsi_14 > 50:
            score += 0.20 * ((technicals.rsi_14 - 50) / 50)
        else:
            score -= 0.20 * ((50 - technicals.rsi_14) / 50)

        # Price position (20%)
        if snapshot.pct_from_high > -10:  # Within 10% of high
            score += 0.20
        elif snapshot.pct_from_low < 10:  # Within 10% of low
            score -= 0.20

        # Volume confirmation (20%)
        if technicals.volume_ratio > 1.5 and snapshot.day_change_pct > 0:
            score += 0.20  # Bullish volume
        elif technicals.volume_ratio > 1.5 and snapshot.day_change_pct < 0:
            score -= 0.20  # Bearish volume

        # Convert to verdict
        if score > 0.3:
            return "CONFIRMING", min(0.95, 0.5 + score)
        elif score < -0.3:
            return "DIVERGING", min(0.95, 0.5 + abs(score))
        else:
            return "NEUTRAL", 0.5

    def _mock_tape(self, symbol: str) -> TapeAnalysis:
        """Return mock data when yfinance unavailable."""
        now = datetime.now().isoformat()

        # Mock provenance - NOT verifiable
        provenance = DataProvenance(
            source_type="mock",
            source_ref=symbol,
            retrieved_at=now,
            content_hash=None,
            notes="PLACEHOLDER - yfinance unavailable"
        )

        snapshot = PriceSnapshot(
            symbol=symbol,
            price=100.0,
            prev_close=99.0,
            volume=1000000,
            avg_volume=800000,
            day_change_pct=1.01,
            fifty_two_week_high=120.0,
            fifty_two_week_low=80.0,
            pct_from_high=-16.67,
            pct_from_low=25.0,
            timestamp=now
        )

        technicals = TechnicalSignals(
            symbol=symbol,
            sma_20=98.0,
            sma_50=95.0,
            sma_200=90.0,
            rsi_14=55.0,
            volume_ratio=1.25,
            trend="NEUTRAL",
            signals=["Above SMA20", "Above SMA200"]
        )

        return TapeAnalysis(
            symbol=symbol,
            snapshot=snapshot,
            technicals=technicals,
            events=[],
            tape_verdict="NEUTRAL",
            confidence=0.5,
            analysis_time=now,
            provenance=provenance
        )

    def confirm_thesis(
        self,
        symbol: str,
        thesis_direction: str  # BULLISH or BEARISH
    ) -> Dict[str, Any]:
        """
        Check if tape confirms a thesis direction.

        Returns:
            {
                "confirms": bool,
                "confidence": float,
                "explanation": str,
                "tape_analysis": TapeAnalysis
            }
        """
        tape = self.fetch_tape(symbol)
        if not tape:
            return {
                "confirms": False,
                "confidence": 0.0,
                "explanation": f"Unable to fetch tape for {symbol}",
                "tape_analysis": None
            }

        # Check alignment
        if thesis_direction == "BULLISH":
            confirms = tape.tape_verdict == "CONFIRMING"
            diverges = tape.tape_verdict == "DIVERGING"
        else:  # BEARISH
            confirms = tape.tape_verdict == "DIVERGING"
            diverges = tape.tape_verdict == "CONFIRMING"

        if confirms:
            explanation = f"Tape confirms {thesis_direction} thesis: {tape.technicals.trend} trend, RSI {tape.technicals.rsi_14:.0f}"
        elif diverges:
            explanation = f"Tape diverges from {thesis_direction} thesis: {tape.technicals.trend} trend"
        else:
            explanation = f"Tape neutral: {tape.technicals.trend} trend, RSI {tape.technicals.rsi_14:.0f}"

        return {
            "confirms": confirms,
            "confidence": tape.confidence,
            "explanation": explanation,
            "tape_analysis": tape
        }

# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import sys

    agent = MarketTapeAgent()

    if len(sys.argv) > 1:
        symbol = sys.argv[1].upper()
        tape = agent.fetch_tape(symbol)

        if tape:
            print(f"\n=== Market Tape: {symbol} ===")
            print(f"Price: ${tape.snapshot.price} ({tape.snapshot.day_change_pct:+.2f}%)")
            print(f"Volume: {tape.snapshot.volume:,} ({tape.technicals.volume_ratio:.1f}x avg)")
            print(f"52W Range: ${tape.snapshot.fifty_two_week_low} - ${tape.snapshot.fifty_two_week_high}")
            print(f"\nTechnicals:")
            print(f"  SMA 20/50/200: {tape.technicals.sma_20}/{tape.technicals.sma_50}/{tape.technicals.sma_200}")
            print(f"  RSI(14): {tape.technicals.rsi_14}")
            print(f"  Trend: {tape.technicals.trend}")
            print(f"  Signals: {', '.join(tape.technicals.signals) or 'None'}")
            print(f"\nVerdict: {tape.tape_verdict} (confidence: {tape.confidence:.0%})")

            if tape.events:
                print(f"\nEvents:")
                for e in tape.events:
                    print(f"  - [{e.event_type}] {e.description}")
        else:
            print(f"Could not fetch tape for {symbol}")
    else:
        print("Usage: python -m fgip.agents.market_tape SYMBOL")
        print("Example: python -m fgip.agents.market_tape INTC")
