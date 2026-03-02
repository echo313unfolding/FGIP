"""
FGIP Options Flow Agent - Track unusual options activity as conviction signal.

Options flow is a TIER 1 signal that shows where smart money is positioning.

Key signals:
- Large call buying = Bullish positioning
- Large put buying = Bearish positioning/hedging
- Unusual volume = Smart money knows something
- Sweep orders = Urgent accumulation

Data sources:
- CBOE (official but requires subscription)
- Unusual Whales API (retail-friendly)
- TDAmeritrade API (free tier)
- Yahoo Finance options chains (free, delayed)

What we track:
- Call/Put ratio for thesis tickers
- Unusual volume (>2x average)
- Large premium transactions (>$100K)
- Near-expiry vs LEAPS (conviction indicator)
"""

import hashlib
import json
import re
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base import (
    FGIPAgent,
    Artifact,
    StructuredFact,
    ProposedClaim,
    ProposedEdge,
)


# =============================================================================
# OPTIONS DATA STRUCTURES
# =============================================================================

@dataclass
class OptionsFlow:
    """Unusual options activity for a ticker."""
    ticker: str
    flow_type: str  # 'call', 'put', 'spread'
    direction: str  # 'bullish', 'bearish', 'neutral'
    volume: int
    open_interest: int
    volume_oi_ratio: float
    premium_usd: float
    strike: float
    expiry: str
    days_to_expiry: int
    is_unusual: bool
    detected_at: str
    source: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OptionsSignal:
    """Aggregated options signal for conviction scoring."""
    ticker: str
    signal_direction: str  # 'bullish', 'bearish', 'neutral'
    signal_strength: float  # 0-1
    call_put_ratio: float
    unusual_activity_count: int
    total_premium_usd: float
    avg_days_to_expiry: float
    is_leaps: bool  # >180 days = high conviction
    flows: List[OptionsFlow]
    computed_at: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["flows"] = [f.to_dict() for f in self.flows]
        return d


# =============================================================================
# TRACKED TICKERS (from conviction theses)
# =============================================================================

CONVICTION_TICKERS: Dict[str, str] = {
    # Nuclear
    "SMR": "nuclear",
    "OKLO": "nuclear",
    "CEG": "nuclear",
    "BWXT": "nuclear",
    "LEU": "nuclear",
    # Uranium
    "CCJ": "nuclear_fuel",
    "URA": "nuclear_fuel",
    "UUUU": "critical_minerals",
    "NXE": "nuclear_fuel",
    # Steel/Reshoring
    "NUE": "steel",
    "STLD": "steel",
    "X": "steel",
    "CLF": "steel",
    # Defense
    "PLTR": "defense",
    "LHX": "defense",
    "RTX": "defense",
    # Critical Minerals
    "MP": "critical_minerals",
    # Copper (infrastructure proxy)
    "FCX": "copper",
    "COPX": "copper",
}

# Unusual activity thresholds
UNUSUAL_VOLUME_MULTIPLIER = 2.0  # 2x average volume = unusual
LARGE_PREMIUM_THRESHOLD = 100_000  # $100K+ premium = institutional
LEAPS_DAYS_THRESHOLD = 180  # >180 days = high conviction position


# =============================================================================
# YAHOO FINANCE OPTIONS (FREE, NO API KEY)
# =============================================================================

YAHOO_OPTIONS_URL = "https://query1.finance.yahoo.com/v7/finance/options/{ticker}"
USER_AGENT = "FGIP Options Flow Agent (research@example.com)"


def fetch_yahoo_options(ticker: str) -> Optional[Dict[str, Any]]:
    """Fetch options chain from Yahoo Finance (free, no API key needed)."""
    url = YAHOO_OPTIONS_URL.format(ticker=ticker)

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode())
            return data.get("optionChain", {}).get("result", [{}])[0]
    except Exception as e:
        print(f"  Error fetching options for {ticker}: {e}")
        return None


def parse_yahoo_options(ticker: str, data: Dict[str, Any]) -> List[OptionsFlow]:
    """Parse Yahoo options data into OptionsFlow objects."""
    flows = []

    if not data:
        return flows

    quote = data.get("quote", {})
    underlying_price = quote.get("regularMarketPrice", 0)

    for chain in data.get("options", []):
        expiry_ts = chain.get("expirationDate", 0)
        expiry_date = datetime.fromtimestamp(expiry_ts).strftime("%Y-%m-%d") if expiry_ts else ""
        days_to_expiry = (datetime.fromtimestamp(expiry_ts) - datetime.now()).days if expiry_ts else 0

        # Process calls
        for call in chain.get("calls", []):
            vol = call.get("volume", 0) or 0
            oi = call.get("openInterest", 0) or 0
            last_price = call.get("lastPrice", 0) or 0
            strike = call.get("strike", 0) or 0

            # Skip low volume
            if vol < 100:
                continue

            vol_oi_ratio = vol / max(oi, 1)
            premium = vol * last_price * 100  # 100 shares per contract

            is_unusual = vol_oi_ratio > UNUSUAL_VOLUME_MULTIPLIER or premium > LARGE_PREMIUM_THRESHOLD

            flows.append(OptionsFlow(
                ticker=ticker,
                flow_type="call",
                direction="bullish",
                volume=vol,
                open_interest=oi,
                volume_oi_ratio=vol_oi_ratio,
                premium_usd=premium,
                strike=strike,
                expiry=expiry_date,
                days_to_expiry=days_to_expiry,
                is_unusual=is_unusual,
                detected_at=datetime.utcnow().isoformat() + "Z",
                source="yahoo_finance",
                metadata={"underlying_price": underlying_price},
            ))

        # Process puts
        for put in chain.get("puts", []):
            vol = put.get("volume", 0) or 0
            oi = put.get("openInterest", 0) or 0
            last_price = put.get("lastPrice", 0) or 0
            strike = put.get("strike", 0) or 0

            if vol < 100:
                continue

            vol_oi_ratio = vol / max(oi, 1)
            premium = vol * last_price * 100

            is_unusual = vol_oi_ratio > UNUSUAL_VOLUME_MULTIPLIER or premium > LARGE_PREMIUM_THRESHOLD

            flows.append(OptionsFlow(
                ticker=ticker,
                flow_type="put",
                direction="bearish",
                volume=vol,
                open_interest=oi,
                volume_oi_ratio=vol_oi_ratio,
                premium_usd=premium,
                strike=strike,
                expiry=expiry_date,
                days_to_expiry=days_to_expiry,
                is_unusual=is_unusual,
                detected_at=datetime.utcnow().isoformat() + "Z",
                source="yahoo_finance",
                metadata={"underlying_price": underlying_price},
            ))

    return flows


def compute_options_signal(ticker: str, flows: List[OptionsFlow]) -> OptionsSignal:
    """Compute aggregated options signal from individual flows."""
    if not flows:
        return OptionsSignal(
            ticker=ticker,
            signal_direction="neutral",
            signal_strength=0.0,
            call_put_ratio=1.0,
            unusual_activity_count=0,
            total_premium_usd=0,
            avg_days_to_expiry=0,
            is_leaps=False,
            flows=[],
            computed_at=datetime.utcnow().isoformat() + "Z",
        )

    # Calculate call/put ratio
    call_volume = sum(f.volume for f in flows if f.flow_type == "call")
    put_volume = sum(f.volume for f in flows if f.flow_type == "put")
    call_put_ratio = call_volume / max(put_volume, 1)

    # Count unusual activity
    unusual_count = sum(1 for f in flows if f.is_unusual)

    # Total premium
    total_premium = sum(f.premium_usd for f in flows)

    # Average days to expiry
    avg_dte = sum(f.days_to_expiry for f in flows) / len(flows)

    # Check for LEAPS (>180 days = high conviction)
    is_leaps = any(f.days_to_expiry > LEAPS_DAYS_THRESHOLD for f in flows if f.is_unusual)

    # Determine direction
    if call_put_ratio > 1.5:
        direction = "bullish"
    elif call_put_ratio < 0.67:
        direction = "bearish"
    else:
        direction = "neutral"

    # Compute signal strength (0-1)
    strength = 0.0

    # Call/put ratio contribution
    if direction == "bullish":
        strength += min(0.3, (call_put_ratio - 1) * 0.1)
    elif direction == "bearish":
        strength += min(0.3, (1 / call_put_ratio - 1) * 0.1)

    # Unusual activity contribution
    strength += min(0.3, unusual_count * 0.05)

    # Premium contribution (institutional size)
    if total_premium > 1_000_000:
        strength += 0.2
    elif total_premium > 500_000:
        strength += 0.1
    elif total_premium > 100_000:
        strength += 0.05

    # LEAPS bonus (high conviction)
    if is_leaps:
        strength += 0.2

    strength = min(1.0, strength)

    return OptionsSignal(
        ticker=ticker,
        signal_direction=direction,
        signal_strength=strength,
        call_put_ratio=call_put_ratio,
        unusual_activity_count=unusual_count,
        total_premium_usd=total_premium,
        avg_days_to_expiry=avg_dte,
        is_leaps=is_leaps,
        flows=[f for f in flows if f.is_unusual],  # Only keep unusual flows
        computed_at=datetime.utcnow().isoformat() + "Z",
    )


# =============================================================================
# OPTIONS FLOW AGENT
# =============================================================================

class OptionsFlowAgent(FGIPAgent):
    """
    Options Flow Agent - Track unusual options activity as conviction signal.

    This is a TIER 1 signal source for the Conviction Engine.

    Monitors:
    - Call/put ratios for thesis tickers
    - Unusual volume (>2x average)
    - Large premium transactions (>$100K)
    - LEAPS positioning (>180 days = high conviction)

    Proposes:
    - BULLISH_OPTIONS_FLOW edges when call/put ratio > 1.5
    - BEARISH_OPTIONS_FLOW edges when call/put ratio < 0.67
    - UNUSUAL_OPTIONS_ACTIVITY claims for large transactions
    """

    def __init__(self, db, artifact_dir: str = "data/artifacts/options"):
        super().__init__(
            db=db,
            name="options_flow",
            description="Unusual options activity tracker - smart money positioning"
        )
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.tickers = CONVICTION_TICKERS.copy()
        self._signals: Dict[str, OptionsSignal] = {}

    def add_ticker(self, ticker: str, sector: str):
        """Add a ticker to monitor."""
        self.tickers[ticker] = sector

    def collect(self) -> List[Artifact]:
        """Fetch options chains for all tracked tickers."""
        artifacts = []

        print(f"  Fetching options data for {len(self.tickers)} tickers...")

        all_flows = {}
        for ticker, sector in self.tickers.items():
            time.sleep(0.5)  # Rate limiting

            data = fetch_yahoo_options(ticker)
            if data:
                flows = parse_yahoo_options(ticker, data)
                signal = compute_options_signal(ticker, flows)
                self._signals[ticker] = signal
                all_flows[ticker] = signal.to_dict()

                if signal.unusual_activity_count > 0:
                    print(f"    {ticker}: {signal.signal_direction} ({signal.unusual_activity_count} unusual)")

        # Create artifact
        artifact_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "tickers_scanned": len(self.tickers),
            "signals": all_flows,
        }

        content = json.dumps(artifact_data, indent=2).encode()
        content_hash = hashlib.sha256(content).hexdigest()

        local_path = self.artifact_dir / f"options_flow_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        local_path.write_bytes(content)

        artifacts.append(Artifact(
            url="internal://options_flow",
            artifact_type="json",
            local_path=str(local_path),
            content_hash=content_hash,
            metadata={
                "tickers_scanned": len(self.tickers),
                "unusual_signals": sum(1 for s in self._signals.values() if s.unusual_activity_count > 0),
                "bullish_signals": sum(1 for s in self._signals.values() if s.signal_direction == "bullish"),
                "bearish_signals": sum(1 for s in self._signals.values() if s.signal_direction == "bearish"),
            }
        ))

        return artifacts

    def extract(self, artifacts: List[Artifact]) -> List[StructuredFact]:
        """Extract facts from options signals."""
        facts = []

        for ticker, signal in self._signals.items():
            if signal.unusual_activity_count == 0:
                continue

            sector = self.tickers.get(ticker, "unknown")

            facts.append(StructuredFact(
                fact_type="options_flow",
                subject=ticker,
                predicate=f"{signal.signal_direction.upper()}_OPTIONS_FLOW",
                object=sector,
                source_artifact=artifacts[0] if artifacts else Artifact(
                    url="internal://options_flow",
                    artifact_type="json"
                ),
                confidence=signal.signal_strength,
                raw_text=(
                    f"{ticker}: {signal.signal_direction} flow, "
                    f"C/P ratio {signal.call_put_ratio:.2f}, "
                    f"{signal.unusual_activity_count} unusual, "
                    f"${signal.total_premium_usd:,.0f} premium"
                ),
                metadata={
                    "call_put_ratio": signal.call_put_ratio,
                    "unusual_count": signal.unusual_activity_count,
                    "total_premium": signal.total_premium_usd,
                    "avg_dte": signal.avg_days_to_expiry,
                    "is_leaps": signal.is_leaps,
                }
            ))

        print(f"  Extracted {len(facts)} unusual options signals")
        return facts

    def propose(self, facts: List[StructuredFact]) -> Tuple[List[ProposedClaim], List[ProposedEdge]]:
        """Propose claims and edges for unusual options activity."""
        claims = []
        edges = []

        for fact in facts:
            proposal_id = self._generate_proposal_id()
            meta = fact.metadata

            # Create claim
            claim_text = (
                f"Unusual {fact.predicate.replace('_', ' ').lower()} detected for {fact.subject}: "
                f"C/P ratio {meta['call_put_ratio']:.2f}, "
                f"${meta['total_premium']:,.0f} premium, "
                f"avg {meta['avg_dte']:.0f} DTE"
            )

            if meta.get("is_leaps"):
                claim_text += " (includes LEAPS - high conviction)"

            claims.append(ProposedClaim(
                proposal_id=proposal_id,
                claim_text=claim_text,
                topic="options_flow",
                agent_name=self.name,
                source_url="https://finance.yahoo.com",
                reasoning=(
                    f"Smart money signal: "
                    f"{'LEAPS' if meta.get('is_leaps') else 'Near-term'} positioning, "
                    f"signal strength {fact.confidence:.2f}"
                ),
                promotion_requirement="Cross-reference with EDGAR Form 4 (insider buys) for confirmation",
            ))

            # Create edge (ticker -> sector with options flow type)
            edge_proposal_id = self._generate_proposal_id()
            edges.append(ProposedEdge(
                proposal_id=edge_proposal_id,
                from_node=fact.subject.lower(),
                to_node=fact.object,
                relationship=fact.predicate,
                agent_name=self.name,
                detail=f"Options flow signal: C/P {meta['call_put_ratio']:.2f}",
                proposed_claim_id=proposal_id,
                confidence=fact.confidence,
                reasoning="Smart money positioning detected via options flow",
                promotion_requirement="Monitor for continuation or reversal in next 2 weeks",
            ))

        return claims, edges

    def get_signal(self, ticker: str) -> Optional[OptionsSignal]:
        """Get computed options signal for a ticker."""
        return self._signals.get(ticker)

    def get_all_signals(self) -> Dict[str, OptionsSignal]:
        """Get all computed signals."""
        return self._signals.copy()


# =============================================================================
# STANDALONE EXECUTION
# =============================================================================

def main():
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from fgip.db import FGIPDatabase

    import argparse
    parser = argparse.ArgumentParser(description="FGIP Options Flow Agent")
    parser.add_argument("db_path", help="Path to FGIP database")
    parser.add_argument("--ticker", "-t", help="Specific ticker to check")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to database")
    args = parser.parse_args()

    db = FGIPDatabase(args.db_path)
    agent = OptionsFlowAgent(db)

    print("=" * 60)
    print("FGIP OPTIONS FLOW AGENT")
    print("Smart money positioning via unusual options activity")
    print("=" * 60)

    if args.ticker:
        # Single ticker check
        print(f"\nChecking {args.ticker}...")
        data = fetch_yahoo_options(args.ticker)
        if data:
            flows = parse_yahoo_options(args.ticker, data)
            signal = compute_options_signal(args.ticker, flows)

            print(f"\n{args.ticker} Options Signal:")
            print(f"  Direction: {signal.signal_direction}")
            print(f"  Strength: {signal.signal_strength:.2f}")
            print(f"  Call/Put Ratio: {signal.call_put_ratio:.2f}")
            print(f"  Unusual Activity: {signal.unusual_activity_count}")
            print(f"  Total Premium: ${signal.total_premium_usd:,.0f}")
            print(f"  Avg DTE: {signal.avg_days_to_expiry:.0f} days")
            print(f"  Has LEAPS: {signal.is_leaps}")

            if signal.flows:
                print(f"\n  Top Unusual Flows:")
                for flow in sorted(signal.flows, key=lambda f: -f.premium_usd)[:5]:
                    print(f"    {flow.flow_type.upper()} ${flow.strike} exp {flow.expiry}")
                    print(f"      Vol: {flow.volume}, Premium: ${flow.premium_usd:,.0f}")
        else:
            print(f"  No options data available for {args.ticker}")
    else:
        # Full agent run
        if args.dry_run:
            artifacts = agent.collect()
            facts = agent.extract(artifacts)
            claims, edges = agent.propose(facts)

            print(f"\nDry Run Results:")
            print(f"  Tickers scanned: {len(agent.tickers)}")
            print(f"  Unusual signals: {len(facts)}")
            print(f"  Claims would propose: {len(claims)}")
            print(f"  Edges would propose: {len(edges)}")

            for signal in agent.get_all_signals().values():
                if signal.unusual_activity_count > 0:
                    print(f"\n  {signal.ticker}: {signal.signal_direction}")
                    print(f"    C/P: {signal.call_put_ratio:.2f}, Premium: ${signal.total_premium_usd:,.0f}")
        else:
            result = agent.run()
            print(f"\nResults:")
            print(f"  Artifacts collected: {result['artifacts_collected']}")
            print(f"  Facts extracted: {result['facts_extracted']}")
            print(f"  Claims proposed: {result['claims_proposed']}")
            print(f"  Edges proposed: {result['edges_proposed']}")


if __name__ == "__main__":
    main()
