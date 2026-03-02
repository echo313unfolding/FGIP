"""
FGIP Kalshi Signal Agent - Prediction market probabilities.

Kalshi is a regulated prediction market for real-world events.
This agent tracks prediction market prices as probability signals.

Use cases:
- "Will CHIPS funding be approved by X date?" -> market probability
- "Will Fed cut rates in Q2?" -> market probability
- Compare narrative claims to betting market consensus

Safety rules:
- Read-only (no trading)
- Probabilities are market-implied, not recommendations
- Markets can be wrong (but are usually calibrated)
"""

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False



# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class PredictionMarket:
    """A prediction market contract."""
    market_id: str
    title: str
    category: str
    yes_price: float  # 0-100 (probability %)
    no_price: float
    volume: int
    expires_at: Optional[str]
    status: str  # OPEN, CLOSED, RESOLVED
    resolution: Optional[str]  # YES, NO, None


@dataclass
class MarketSignal:
    """Signal derived from prediction market."""
    market_id: str
    thesis_relevance: str  # Description of how this relates to thesis
    implied_probability: float  # 0-1
    confidence: float  # How liquid/reliable is this market
    direction: str  # BULLISH, BEARISH, NEUTRAL for thesis
    timestamp: str


# =============================================================================
# KALSHI API (Stub - implement with actual API key)
# =============================================================================

KALSHI_CATEGORY_MAPPING = {
    "fed": ["fed-rate", "fomc", "interest-rate"],
    "inflation": ["cpi", "inflation", "pce"],
    "politics": ["election", "president", "congress", "bill"],
    "tech": ["tech", "ai", "semiconductor", "chips"],
    "economy": ["gdp", "recession", "employment", "jobs"],
    "crypto": ["bitcoin", "ethereum", "crypto"],
}


def search_kalshi_markets(
    query: str,
    category: Optional[str] = None
) -> List[PredictionMarket]:
    """
    Search Kalshi markets.

    Note: This is a stub. Real implementation requires Kalshi API key.
    For demo, returns mock markets based on query.
    """
    # Mock markets for common queries
    mock_markets = {
        "fed": [
            PredictionMarket(
                market_id="fed-rate-cut-q2-2026",
                title="Fed to cut rates by end of Q2 2026",
                category="Economy",
                yes_price=42.0,
                no_price=58.0,
                volume=125000,
                expires_at="2026-06-30",
                status="OPEN",
                resolution=None
            ),
            PredictionMarket(
                market_id="fed-rate-pause-mar-2026",
                title="Fed to pause rate changes in March 2026 FOMC",
                category="Economy",
                yes_price=68.0,
                no_price=32.0,
                volume=89000,
                expires_at="2026-03-20",
                status="OPEN",
                resolution=None
            ),
        ],
        "chips": [
            PredictionMarket(
                market_id="chips-intel-fab-2026",
                title="Intel to begin CHIPS-funded fab construction in 2026",
                category="Tech",
                yes_price=78.0,
                no_price=22.0,
                volume=45000,
                expires_at="2026-12-31",
                status="OPEN",
                resolution=None
            ),
        ],
        "recession": [
            PredictionMarket(
                market_id="us-recession-2026",
                title="US to enter recession in 2026",
                category="Economy",
                yes_price=25.0,
                no_price=75.0,
                volume=230000,
                expires_at="2026-12-31",
                status="OPEN",
                resolution=None
            ),
        ],
        "inflation": [
            PredictionMarket(
                market_id="cpi-below-3-q2-2026",
                title="CPI YoY below 3% by Q2 2026",
                category="Economy",
                yes_price=55.0,
                no_price=45.0,
                volume=112000,
                expires_at="2026-06-30",
                status="OPEN",
                resolution=None
            ),
        ],
        "tariff": [
            PredictionMarket(
                market_id="china-tariff-increase-2026",
                title="US to increase China tariffs in 2026",
                category="Politics",
                yes_price=72.0,
                no_price=28.0,
                volume=67000,
                expires_at="2026-12-31",
                status="OPEN",
                resolution=None
            ),
        ],
    }

    # Search by query keywords
    query_lower = query.lower()
    results = []

    for key, markets in mock_markets.items():
        if key in query_lower:
            results.extend(markets)

    # Also search by title
    for markets in mock_markets.values():
        for market in markets:
            if query_lower in market.title.lower() and market not in results:
                results.append(market)

    return results


# =============================================================================
# KALSHI SIGNAL AGENT
# =============================================================================

class KalshiSignalAgent:
    """
    Track prediction market probabilities as signals.

    Answers: "What does the betting market think?"
    """

    AGENT_NAME = "kalshi-signal"
    TIER = 2  # Market consensus

    def __init__(self, db_path: str = "fgip.db"):
        """Initialize with database path."""
        self.db_path = Path(db_path)
        self._cache: Dict[str, Tuple[List[PredictionMarket], datetime]] = {}
        self._cache_ttl = timedelta(minutes=15)
        self._ensure_tables()

    def _get_db(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self):
        """Create prediction market tables if needed."""
        conn = self._get_db()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS prediction_markets (
                    market_id TEXT PRIMARY KEY,
                    title TEXT,
                    category TEXT,
                    yes_price REAL,
                    no_price REAL,
                    volume INTEGER,
                    expires_at TEXT,
                    status TEXT,
                    resolution TEXT,
                    last_updated TEXT
                );

                CREATE TABLE IF NOT EXISTS market_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    market_id TEXT,
                    thesis_id TEXT,
                    thesis_relevance TEXT,
                    implied_probability REAL,
                    direction TEXT,
                    created_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_signals_thesis ON market_signals(thesis_id);
            """)
            conn.commit()
        finally:
            conn.close()

    def search_markets(
        self,
        query: str,
        category: Optional[str] = None,
        force_refresh: bool = False
    ) -> List[PredictionMarket]:
        """
        Search for relevant prediction markets.

        Args:
            query: Search query (e.g., "fed rate cut", "chips act")
            category: Optional category filter
            force_refresh: Bypass cache

        Returns:
            List of matching PredictionMarket objects
        """
        cache_key = f"{query}:{category or ''}"

        # Check cache
        if not force_refresh and cache_key in self._cache:
            cached, cached_at = self._cache[cache_key]
            if datetime.now() - cached_at < self._cache_ttl:
                return cached

        # Search markets
        markets = search_kalshi_markets(query, category)

        # Store results
        self._store_markets(markets)

        # Cache
        self._cache[cache_key] = (markets, datetime.now())

        return markets

    def _store_markets(self, markets: List[PredictionMarket]):
        """Store markets in database."""
        conn = self._get_db()
        try:
            now = datetime.now().isoformat()
            for m in markets:
                conn.execute("""
                    INSERT OR REPLACE INTO prediction_markets (
                        market_id, title, category, yes_price, no_price,
                        volume, expires_at, status, resolution, last_updated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    m.market_id, m.title, m.category, m.yes_price, m.no_price,
                    m.volume, m.expires_at, m.status, m.resolution, now
                ))
            conn.commit()
        finally:
            conn.close()

    def get_thesis_signal(
        self,
        thesis_id: str,
        thesis_keywords: List[str],
        thesis_direction: str = "BULLISH"
    ) -> Optional[MarketSignal]:
        """
        Get prediction market signal for a thesis.

        Args:
            thesis_id: ID of the thesis
            thesis_keywords: Keywords to search (e.g., ["fed", "rate cut"])
            thesis_direction: What direction supports the thesis

        Returns:
            MarketSignal with aggregated probability
        """
        all_markets = []

        # Search for each keyword
        for keyword in thesis_keywords:
            markets = self.search_markets(keyword)
            all_markets.extend(markets)

        if not all_markets:
            return None

        # Deduplicate
        seen = set()
        unique_markets = []
        for m in all_markets:
            if m.market_id not in seen:
                seen.add(m.market_id)
                unique_markets.append(m)

        # Weight by volume for aggregate probability
        total_volume = sum(m.volume for m in unique_markets)
        if total_volume == 0:
            return None

        weighted_prob = sum(
            (m.yes_price / 100) * (m.volume / total_volume)
            for m in unique_markets
        )

        # Determine direction based on weighted probability
        if weighted_prob > 0.6:
            direction = "BULLISH" if thesis_direction == "BULLISH" else "BEARISH"
        elif weighted_prob < 0.4:
            direction = "BEARISH" if thesis_direction == "BULLISH" else "BULLISH"
        else:
            direction = "NEUTRAL"

        # Confidence based on volume
        confidence = min(total_volume / 100000, 1.0)  # Max out at 100k volume

        # Create relevance summary
        relevance = f"Based on {len(unique_markets)} markets: " + ", ".join(
            f"{m.title} ({m.yes_price:.0f}%)"
            for m in unique_markets[:3]
        )

        signal = MarketSignal(
            market_id=unique_markets[0].market_id,  # Primary market
            thesis_relevance=relevance,
            implied_probability=round(weighted_prob, 2),
            confidence=round(confidence, 2),
            direction=direction,
            timestamp=datetime.now().isoformat()
        )

        # Store signal
        self._store_signal(thesis_id, signal)

        return signal

    def _store_signal(self, thesis_id: str, signal: MarketSignal):
        """Store signal in database."""
        conn = self._get_db()
        try:
            conn.execute("""
                INSERT INTO market_signals (
                    market_id, thesis_id, thesis_relevance,
                    implied_probability, direction, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                signal.market_id, thesis_id, signal.thesis_relevance,
                signal.implied_probability, signal.direction, signal.timestamp
            ))
            conn.commit()
        finally:
            conn.close()

    def compare_to_narrative(
        self,
        claim: str,
        claim_confidence: float
    ) -> Dict[str, Any]:
        """
        Compare a narrative claim to prediction market consensus.

        Args:
            claim: The claim text (e.g., "Fed will cut rates")
            claim_confidence: Confidence in the claim (0-1)

        Returns:
            Comparison with market probability and divergence
        """
        # Extract keywords from claim
        keywords = self._extract_keywords(claim)

        if not keywords:
            return {
                "has_market": False,
                "explanation": "No relevant prediction markets found"
            }

        # Search markets
        markets = []
        for kw in keywords:
            markets.extend(self.search_markets(kw))

        if not markets:
            return {
                "has_market": False,
                "explanation": f"No markets for keywords: {', '.join(keywords)}"
            }

        # Get most relevant market
        best_market = max(markets, key=lambda m: m.volume)
        market_prob = best_market.yes_price / 100

        # Compare
        divergence = claim_confidence - market_prob

        if abs(divergence) < 0.15:
            alignment = "ALIGNED"
            explanation = f"Claim confidence ({claim_confidence:.0%}) aligns with market ({market_prob:.0%})"
        elif divergence > 0:
            alignment = "MORE_BULLISH"
            explanation = f"Claim ({claim_confidence:.0%}) more bullish than market ({market_prob:.0%})"
        else:
            alignment = "MORE_BEARISH"
            explanation = f"Claim ({claim_confidence:.0%}) more bearish than market ({market_prob:.0%})"

        return {
            "has_market": True,
            "market": {
                "id": best_market.market_id,
                "title": best_market.title,
                "probability": market_prob,
                "volume": best_market.volume
            },
            "claim_confidence": claim_confidence,
            "market_probability": market_prob,
            "divergence": round(divergence, 2),
            "alignment": alignment,
            "explanation": explanation
        }

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract searchable keywords from text."""
        keywords = []

        # Check for known categories
        text_lower = text.lower()

        if "fed" in text_lower or "rate" in text_lower or "fomc" in text_lower:
            keywords.append("fed")
        if "chips" in text_lower or "semiconductor" in text_lower:
            keywords.append("chips")
        if "inflation" in text_lower or "cpi" in text_lower:
            keywords.append("inflation")
        if "recession" in text_lower or "gdp" in text_lower:
            keywords.append("recession")
        if "tariff" in text_lower or "china" in text_lower:
            keywords.append("tariff")

        return keywords

# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import sys

    agent = KalshiSignalAgent()

    if len(sys.argv) > 1:
        cmd = sys.argv[1]

        if cmd == "search":
            # Example: python -m fgip.agents.kalshi_signal search "fed rate"
            query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "fed"
            markets = agent.search_markets(query)

            print(f"\n=== Kalshi Markets: '{query}' ===")
            if markets:
                for m in markets:
                    print(f"\n[{m.market_id}]")
                    print(f"  {m.title}")
                    print(f"  YES: {m.yes_price:.0f}% | NO: {m.no_price:.0f}%")
                    print(f"  Volume: {m.volume:,}")
                    print(f"  Expires: {m.expires_at}")
            else:
                print("No markets found")

        elif cmd == "signal":
            # Example: python -m fgip.agents.kalshi_signal signal test-thesis fed,rate
            thesis_id = sys.argv[2] if len(sys.argv) > 2 else "test-thesis"
            keywords = sys.argv[3].split(",") if len(sys.argv) > 3 else ["fed"]

            signal = agent.get_thesis_signal(thesis_id, keywords)

            if signal:
                print(f"\n=== Market Signal for {thesis_id} ===")
                print(f"Implied Probability: {signal.implied_probability:.0%}")
                print(f"Direction: {signal.direction}")
                print(f"Confidence: {signal.confidence:.0%}")
                print(f"Relevance: {signal.thesis_relevance}")
            else:
                print("No relevant markets found")

        elif cmd == "compare":
            # Example: python -m fgip.agents.kalshi_signal compare "Fed will cut rates" 0.7
            claim = sys.argv[2] if len(sys.argv) > 2 else "Fed will cut rates"
            confidence = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5

            result = agent.compare_to_narrative(claim, confidence)

            print(f"\n=== Narrative vs Market ===")
            print(f"Claim: {claim}")
            print(f"Claim Confidence: {confidence:.0%}")
            if result["has_market"]:
                print(f"Market: {result['market']['title']}")
                print(f"Market Probability: {result['market_probability']:.0%}")
                print(f"Divergence: {result['divergence']:+.0%}")
                print(f"Alignment: {result['alignment']}")
            print(f"Explanation: {result['explanation']}")

        else:
            print(f"Unknown command: {cmd}")

    else:
        print("Usage:")
        print("  python -m fgip.agents.kalshi_signal search [query]")
        print("  python -m fgip.agents.kalshi_signal signal [thesis_id] [keywords]")
        print("  python -m fgip.agents.kalshi_signal compare [claim] [confidence]")
