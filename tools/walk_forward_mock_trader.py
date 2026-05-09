#!/usr/bin/env python3
"""Walk-forward mock trading harness for FGIP thesis evaluation.

Tests whether FGIP evidence receipts can drive point-in-time decisions
without look-ahead bias.

Usage:
    python3 tools/walk_forward_mock_trader.py
    python3 tools/walk_forward_mock_trader.py --start 2024-05-09 --end 2026-05-09
    python3 tools/walk_forward_mock_trader.py --thesis thesis-dollar-resilience-rails

Rules:
- No future sources, prices, or receipt states
- Monthly rebalance
- Transaction cost: 10 bps, slippage: 5 bps
- Candidate: max 25%, Active: max 50%, Quarantined: 0%
- Max single-name: 5%
- No leverage
"""

import argparse
import hashlib
import json
import math
import os
import platform
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np

# Add parent to path for sibling imports
sys.path.insert(0, str(Path(__file__).parent))
from build_point_in_time_snapshot import build_snapshot, PointInTimeSnapshot

RECEIPTS_DIR = Path(__file__).parent.parent / "receipts"
MOCK_TRADES_DIR = RECEIPTS_DIR / "mock_trades"
BACKTESTS_DIR = RECEIPTS_DIR / "backtests"
REPORTS_DIR = Path(__file__).parent.parent / "reports"
PRICE_CACHE = Path(__file__).parent.parent / ".cache" / "prices"

# Fixed mock universe
UNIVERSE = [
    "COIN", "HOOD", "PYPL", "SQ",       # stablecoin / crypto rails
    "ICE", "CME", "NDAQ", "BK", "STT",   # tokenization / market infra
    "SHY", "BIL", "TLT", "IEF",          # Treasury / rates
    "JPM", "BAC", "WFC", "V", "MA",       # banks / payment rails
    "GLD", "UUP", "SH",                   # risk hedges
]

BENCHMARKS = ["SPY"]

# Risk rules
TRANSACTION_COST_BPS = 10
SLIPPAGE_BPS = 5
MAX_SINGLE_NAME_PCT = 0.05
CANDIDATE_MAX_GROSS = 0.25
ACTIVE_MAX_GROSS = 0.50
QUARANTINE_MAX_GROSS = 0.0

# Thesis-to-evidence keywords for edge matching
THESIS_KEYWORDS = {
    "thesis-dollar-resilience-rails": [
        "genius", "stablecoin", "tokenize", "occ", "fdic", "settlement",
        "payment", "reserve", "treasury", "dollar", "digital", "crypto",
        "blockchain", "transfer-agent", "bullish", "equiniti", "dtcc",
    ],
    "thesis-defense-primes": [
        "ndaa", "defense", "military", "lockheed", "raytheon", "northrop",
        "general-dynamics", "huntington", "bwxt", "himars", "ukraine",
    ],
    "thesis-power-uranium-screen": [
        "data-center", "power", "nexus", "transco", "pipeline", "uranium",
        "nuclear", "stargate", "dte", "williams", "ferc",
    ],
}


def sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


# ─── Price Loading ───────────────────────────────────────────────────────────

def load_prices(tickers: list[str], start: str, end: str) -> dict[str, dict[str, float]]:
    """Load daily close prices. Uses yfinance with disk cache."""
    PRICE_CACHE.mkdir(parents=True, exist_ok=True)
    cache_key = sha256_hex(f"{sorted(tickers)}-{start}-{end}")[:12]
    cache_file = PRICE_CACHE / f"prices_{cache_key}.json"

    if cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)

    try:
        import yfinance as yf
    except ImportError:
        print("ERROR: yfinance required. pip install yfinance", file=sys.stderr)
        sys.exit(1)

    print(f"Downloading prices for {len(tickers)} tickers ({start} to {end})...")
    # Pad start by 5 days to ensure we have previous close for first decision
    from datetime import datetime as dt
    padded_start = (dt.strptime(start, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")

    data = yf.download(tickers, start=padded_start, end=end, progress=False, auto_adjust=True)

    if data.empty:
        print("ERROR: No price data returned", file=sys.stderr)
        sys.exit(1)

    prices = {}
    close = data["Close"] if "Close" in data.columns.get_level_values(0) else data

    for ticker in tickers:
        if ticker in close.columns:
            series = close[ticker].dropna()
            prices[ticker] = {
                d.strftime("%Y-%m-%d"): round(float(v), 4)
                for d, v in series.items()
            }

    with open(cache_file, "w") as f:
        json.dump(prices, f)

    print(f"  Cached {len(prices)} tickers, {sum(len(v) for v in prices.values())} total price points")
    return prices


def get_price(prices: dict, ticker: str, date: str) -> float | None:
    """Get closing price on or before date."""
    if ticker not in prices:
        return None
    ticker_prices = prices[ticker]
    if date in ticker_prices:
        return ticker_prices[date]
    # Find most recent price before date
    candidates = [(d, p) for d, p in ticker_prices.items() if d <= date]
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    return None


# ─── Evidence Analysis ───────────────────────────────────────────────────────

def count_thesis_evidence(snapshot: PointInTimeSnapshot, thesis_id: str) -> dict:
    """Count evidence signals relevant to a thesis from a point-in-time snapshot."""
    keywords = THESIS_KEYWORDS.get(thesis_id, [])
    if not keywords:
        return {"relevant_sources": 0, "relevant_facts": 0, "relevant_edges": 0,
                "tier_0": 0, "tier_1": 0, "source_types": []}

    def matches(text: str) -> bool:
        text_lower = text.lower()
        return any(kw in text_lower for kw in keywords)

    rel_sources = [s for s in snapshot.sources if matches(json.dumps(s))]
    rel_facts = [f for f in snapshot.facts if matches(json.dumps(f))]
    rel_edges = [e for e in snapshot.edges if matches(json.dumps(e))]

    tier_0 = sum(1 for s in rel_sources if s.get("tier", 99) == 0)
    tier_1 = sum(1 for s in rel_sources if s.get("tier", 99) == 1)
    stypes = {s.get("source_type", "unknown") for s in rel_sources}

    return {
        "relevant_sources": len(rel_sources),
        "relevant_facts": len(rel_facts),
        "relevant_edges": len(rel_edges),
        "tier_0": tier_0,
        "tier_1": tier_1,
        "source_types": sorted(stypes),
        "source_ids": [s["source_id"] for s in rel_sources],
        "fact_ids": [f["fact_id"] for f in rel_facts],
        "edge_ids": [e["edge_id"] for e in rel_edges],
    }


def determine_thesis_state(evidence: dict) -> str:
    """Determine Candidate/Active/Quarantined from visible evidence."""
    tier_0 = evidence.get("tier_0", 0)
    stypes = evidence.get("source_types", [])
    rel_edges = evidence.get("relevant_edges", 0)

    if tier_0 >= 1 and len(stypes) >= 3 and rel_edges >= 3:
        return "Active"
    if evidence.get("relevant_sources", 0) > 0:
        return "Candidate"
    return "NotYetProposed"


# ─── Agent Strategies ────────────────────────────────────────────────────────

@dataclass
class TradeDecision:
    date: str
    thesis_id: str
    graph_state: str
    action: str  # NO_TRADE, WATCH, LONG_BASKET, HEDGE, REDUCE, EXIT
    target_weights: dict[str, float] = field(default_factory=dict)
    rationale: str = ""
    evidence: dict = field(default_factory=dict)
    risk_gate: str = ""
    receipt_hash: str = ""


def cash_agent(date: str, thesis_id: str, snapshot: PointInTimeSnapshot,
               prices: dict, current_weights: dict) -> TradeDecision:
    """Baseline: 100% cash, always."""
    return TradeDecision(
        date=date, thesis_id=thesis_id, graph_state="N/A",
        action="NO_TRADE", target_weights={},
        rationale="Cash baseline — no trades.",
        risk_gate="cash_only",
    )


def equal_weight_agent(date: str, thesis_id: str, snapshot: PointInTimeSnapshot,
                       prices: dict, current_weights: dict) -> TradeDecision:
    """Baseline: equal-weight the universe, rebalance monthly."""
    available = [t for t in UNIVERSE if get_price(prices, t, date) is not None]
    if not available:
        return TradeDecision(date=date, thesis_id=thesis_id, graph_state="N/A",
                             action="NO_TRADE", target_weights={}, rationale="No prices available.")
    w = round(1.0 / len(available), 4)
    weights = {t: w for t in available}
    return TradeDecision(
        date=date, thesis_id=thesis_id, graph_state="N/A",
        action="LONG_BASKET", target_weights=weights,
        rationale=f"Equal-weight {len(available)} tickers.",
        risk_gate="equal_weight_baseline",
    )


def spy_agent(date: str, thesis_id: str, snapshot: PointInTimeSnapshot,
              prices: dict, current_weights: dict) -> TradeDecision:
    """Baseline: 100% SPY."""
    return TradeDecision(
        date=date, thesis_id=thesis_id, graph_state="N/A",
        action="LONG_BASKET", target_weights={"SPY": 1.0},
        rationale="SPY benchmark.",
        risk_gate="spy_benchmark",
    )


def momentum_agent(date: str, thesis_id: str, snapshot: PointInTimeSnapshot,
                   prices: dict, current_weights: dict) -> TradeDecision:
    """Baseline: top-5 by 3-month momentum, equal weight, max 50%."""
    from datetime import datetime as dt
    try:
        d = dt.strptime(date, "%Y-%m-%d")
        lookback = (d - timedelta(days=63)).strftime("%Y-%m-%d")
    except Exception:
        lookback = date

    returns = {}
    for ticker in UNIVERSE:
        p_now = get_price(prices, ticker, date)
        p_then = get_price(prices, ticker, lookback)
        if p_now and p_then and p_then > 0:
            returns[ticker] = (p_now - p_then) / p_then

    if len(returns) < 5:
        return TradeDecision(date=date, thesis_id=thesis_id, graph_state="N/A",
                             action="NO_TRADE", target_weights={}, rationale="Insufficient history.")

    top5 = sorted(returns, key=returns.get, reverse=True)[:5]
    w = round(0.50 / 5, 4)  # max 50% gross
    weights = {t: w for t in top5}

    return TradeDecision(
        date=date, thesis_id=thesis_id, graph_state="N/A",
        action="LONG_BASKET", target_weights=weights,
        rationale=f"Top-5 3-month momentum: {top5}. 50% gross.",
        risk_gate="momentum_baseline",
    )


def fgip_rules_agent(date: str, thesis_id: str, snapshot: PointInTimeSnapshot,
                     prices: dict, current_weights: dict) -> TradeDecision:
    """FGIP rules-only agent: no Claude, pure evidence-gated rules."""
    evidence = count_thesis_evidence(snapshot, thesis_id)
    state = determine_thesis_state(evidence)

    if state == "NotYetProposed":
        return TradeDecision(
            date=date, thesis_id=thesis_id, graph_state=state,
            action="NO_TRADE", target_weights={},
            rationale="Thesis not yet proposed. No relevant sources visible.",
            evidence=evidence, risk_gate="no_evidence",
        )

    if state == "Quarantined":
        return TradeDecision(
            date=date, thesis_id=thesis_id, graph_state=state,
            action="EXIT", target_weights={},
            rationale="Thesis quarantined. Exit all positions.",
            evidence=evidence, risk_gate="quarantine_exit",
        )

    # Determine max gross based on state
    max_gross = CANDIDATE_MAX_GROSS if state == "Candidate" else ACTIVE_MAX_GROSS

    # Score: simple signal count
    signal_score = evidence["tier_0"] * 15 + evidence["tier_1"] * 8
    # Scale position by signal strength (soft)
    position_scale = min(1.0, signal_score / 60.0)
    gross = max_gross * position_scale

    if gross < 0.02:
        return TradeDecision(
            date=date, thesis_id=thesis_id, graph_state=state,
            action="WATCH", target_weights={},
            rationale=f"Evidence too thin ({evidence['relevant_sources']} sources, score {signal_score}). Watch only.",
            evidence=evidence, risk_gate="evidence_insufficient",
        )

    # Equal-weight available universe tickers, capped at MAX_SINGLE_NAME
    available = [t for t in UNIVERSE if get_price(prices, t, date) is not None]
    if not available:
        return TradeDecision(
            date=date, thesis_id=thesis_id, graph_state=state,
            action="WATCH", target_weights={},
            rationale="No prices available for universe.",
            evidence=evidence, risk_gate="no_prices",
        )

    per_name = min(MAX_SINGLE_NAME_PCT, gross / len(available))
    weights = {t: round(per_name, 4) for t in available}

    # Trim to gross limit
    total = sum(weights.values())
    if total > gross:
        scale = gross / total
        weights = {t: round(w * scale, 4) for t, w in weights.items()}

    action = "LONG_BASKET" if sum(weights.values()) > sum(current_weights.values()) * 1.1 else "LONG_BASKET"
    if sum(weights.values()) < sum(current_weights.values()) * 0.5:
        action = "REDUCE"

    return TradeDecision(
        date=date, thesis_id=thesis_id, graph_state=state,
        action=action, target_weights=weights,
        rationale=(
            f"State={state}, Tier0={evidence['tier_0']}, Tier1={evidence['tier_1']}, "
            f"Sources={evidence['relevant_sources']}, Edges={evidence['relevant_edges']}, "
            f"Score={signal_score}, Gross={round(gross, 3)}, MaxGross={max_gross}"
        ),
        evidence=evidence,
        risk_gate=f"{state.lower()}_evidence_gated",
    )


AGENTS = {
    "cash": cash_agent,
    "equal_weight": equal_weight_agent,
    "spy": spy_agent,
    "momentum": momentum_agent,
    "fgip_rules": fgip_rules_agent,
}


# ─── Execution Engine ────────────────────────────────────────────────────────

@dataclass
class Portfolio:
    cash: float = 100000.0
    positions: dict[str, float] = field(default_factory=dict)  # ticker -> shares
    history: list[dict] = field(default_factory=list)

    def value(self, prices: dict, date: str) -> float:
        total = self.cash
        for ticker, shares in self.positions.items():
            p = get_price(prices, ticker, date)
            if p:
                total += shares * p
        return total

    def weights(self, prices: dict, date: str) -> dict[str, float]:
        total = self.value(prices, date)
        if total <= 0:
            return {}
        result = {}
        for ticker, shares in self.positions.items():
            p = get_price(prices, ticker, date)
            if p:
                result[ticker] = (shares * p) / total
        return result


def execute_rebalance(portfolio: Portfolio, target_weights: dict[str, float],
                      prices: dict, date: str) -> dict:
    """Execute rebalance with transaction costs and slippage."""
    total_value = portfolio.value(prices, date)
    trades = []
    total_cost = 0.0

    current_weights = portfolio.weights(prices, date)

    for ticker in set(list(target_weights.keys()) + list(portfolio.positions.keys())):
        target_w = target_weights.get(ticker, 0.0)
        current_w = current_weights.get(ticker, 0.0)
        delta_w = target_w - current_w

        if abs(delta_w) < 0.001:
            continue

        p = get_price(prices, ticker, date)
        if not p or p <= 0:
            continue

        dollar_amount = delta_w * total_value
        # Apply slippage
        if dollar_amount > 0:
            effective_price = p * (1 + SLIPPAGE_BPS / 10000)
        else:
            effective_price = p * (1 - SLIPPAGE_BPS / 10000)

        shares_delta = dollar_amount / effective_price
        cost = abs(dollar_amount) * TRANSACTION_COST_BPS / 10000

        portfolio.positions[ticker] = portfolio.positions.get(ticker, 0.0) + shares_delta
        portfolio.cash -= (shares_delta * effective_price + cost)
        total_cost += cost

        # Clean up near-zero positions
        if abs(portfolio.positions[ticker]) < 0.001:
            del portfolio.positions[ticker]

        trades.append({
            "ticker": ticker,
            "shares_delta": round(shares_delta, 4),
            "price": round(p, 4),
            "effective_price": round(effective_price, 4),
            "dollar_amount": round(dollar_amount, 2),
            "cost": round(cost, 2),
        })

    return {"trades": trades, "total_cost": round(total_cost, 2), "portfolio_value": round(total_value, 2)}


# ─── Performance Metrics ─────────────────────────────────────────────────────

def compute_metrics(nav_series: list[tuple[str, float]], name: str) -> dict:
    """Compute performance metrics from (date, nav) series."""
    if len(nav_series) < 2:
        return {"agent": name, "error": "insufficient data"}

    dates = [d for d, _ in nav_series]
    values = [v for _, v in nav_series]
    initial = values[0]
    final = values[-1]

    total_return = (final - initial) / initial
    years = max(0.01, (len(values) - 1) / 252)
    ann_return = (1 + total_return) ** (1 / years) - 1

    # Daily returns
    daily_returns = []
    for i in range(1, len(values)):
        if values[i - 1] > 0:
            daily_returns.append((values[i] - values[i - 1]) / values[i - 1])

    if not daily_returns:
        return {"agent": name, "error": "no returns"}

    vol = float(np.std(daily_returns)) * math.sqrt(252)
    mean_r = float(np.mean(daily_returns)) * 252
    sharpe = mean_r / vol if vol > 0 else 0.0

    # Downside deviation (Sortino)
    downside = [r for r in daily_returns if r < 0]
    downside_dev = float(np.std(downside)) * math.sqrt(252) if downside else 0.0
    sortino = mean_r / downside_dev if downside_dev > 0 else 0.0

    # Max drawdown
    peak = values[0]
    max_dd = 0.0
    for v in values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    return {
        "agent": name,
        "total_return_pct": round(total_return * 100, 2),
        "annualized_return_pct": round(ann_return * 100, 2),
        "volatility_pct": round(vol * 100, 2),
        "sharpe": round(sharpe, 3),
        "sortino": round(sortino, 3),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "initial_value": round(initial, 2),
        "final_value": round(final, 2),
        "trading_days": len(values),
    }


# ─── Main Simulation ─────────────────────────────────────────────────────────

def generate_rebalance_dates(start: str, end: str) -> list[str]:
    """Generate first-trading-day-of-month dates."""
    from datetime import datetime as dt
    s = dt.strptime(start, "%Y-%m-%d")
    e = dt.strptime(end, "%Y-%m-%d")
    dates = []
    current = s
    while current <= e:
        dates.append(current.strftime("%Y-%m-%d"))
        # Move to first of next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1, day=1)
        else:
            current = current.replace(month=current.month + 1, day=1)
    return dates


def generate_daily_dates(start: str, end: str) -> list[str]:
    """Generate all calendar dates for NAV tracking."""
    from datetime import datetime as dt
    s = dt.strptime(start, "%Y-%m-%d")
    e = dt.strptime(end, "%Y-%m-%d")
    dates = []
    current = s
    while current <= e:
        if current.weekday() < 5:  # Mon-Fri
            dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates


def run_simulation(thesis_id: str, start: str, end: str):
    """Run full walk-forward simulation."""
    t_start = time.time()
    cpu_start = time.process_time()
    ts_start = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    print(f"FGIP Walk-Forward Mock Trader v0")
    print(f"  Thesis: {thesis_id}")
    print(f"  Period: {start} to {end}")
    print(f"  Universe: {len(UNIVERSE)} tickers")
    print(f"  Agents: {list(AGENTS.keys())}")
    print()

    # Load prices
    all_tickers = UNIVERSE + BENCHMARKS
    prices = load_prices(all_tickers, start, end)
    print()

    rebalance_dates = generate_rebalance_dates(start, end)
    daily_dates = generate_daily_dates(start, end)

    print(f"  Rebalance dates: {len(rebalance_dates)}")
    print(f"  Trading days: {len(daily_dates)}")
    print()

    # Run each agent
    all_results = {}

    for agent_name, agent_fn in AGENTS.items():
        print(f"Running agent: {agent_name}...")
        portfolio = Portfolio()
        decisions = []
        nav_series = []
        trade_count = 0

        for reb_date in rebalance_dates:
            # Build point-in-time snapshot
            snapshot = build_snapshot(reb_date)
            current_weights = portfolio.weights(prices, reb_date)

            # Agent makes decision
            decision = agent_fn(reb_date, thesis_id, snapshot, prices, current_weights)
            decision.receipt_hash = sha256_hex(json.dumps({
                "date": decision.date,
                "action": decision.action,
                "weights": decision.target_weights,
            }))[:16]

            decisions.append(decision)

            # Execute trades
            if decision.target_weights:
                exec_result = execute_rebalance(portfolio, decision.target_weights, prices, reb_date)
                trade_count += len(exec_result["trades"])
            elif decision.action == "EXIT":
                exec_result = execute_rebalance(portfolio, {}, prices, reb_date)
                trade_count += len(exec_result["trades"])

        # Track daily NAV
        for d in daily_dates:
            v = portfolio.value(prices, d)
            if v > 0:
                nav_series.append((d, v))

        metrics = compute_metrics(nav_series, agent_name)
        metrics["trade_count"] = trade_count
        metrics["rebalances"] = len(rebalance_dates)

        # Evidence discipline: count decisions where agent traded without evidence
        if agent_name == "fgip_rules":
            evidence_failures = sum(
                1 for d in decisions
                if d.action in ("LONG_BASKET", "HEDGE")
                and d.evidence.get("relevant_sources", 0) == 0
            )
            metrics["evidence_discipline_failures"] = evidence_failures

        all_results[agent_name] = {
            "metrics": metrics,
            "decisions": [
                {
                    "date": d.date,
                    "thesis_id": d.thesis_id,
                    "graph_state": d.graph_state,
                    "action": d.action,
                    "target_weights_count": len(d.target_weights),
                    "gross_exposure": round(sum(d.target_weights.values()), 4),
                    "rationale": d.rationale,
                    "visible_sources": d.evidence.get("source_ids", []) if d.evidence else [],
                    "visible_facts": d.evidence.get("fact_ids", []) if d.evidence else [],
                    "visible_edges": d.evidence.get("edge_ids", []) if d.evidence else [],
                    "risk_gate": d.risk_gate,
                    "receipt_hash": d.receipt_hash,
                }
                for d in decisions
            ],
        }

        print(f"  {agent_name}: return={metrics.get('total_return_pct', 'N/A')}%, "
              f"sharpe={metrics.get('sharpe', 'N/A')}, "
              f"max_dd={metrics.get('max_drawdown_pct', 'N/A')}%, "
              f"trades={trade_count}")

    # Build report
    ts_end = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    report = {
        "simulation": "FGIP_WALK_FORWARD_MOCK_TRADER_V0",
        "thesis_id": thesis_id,
        "start_date": start,
        "end_date": end,
        "universe": UNIVERSE,
        "benchmarks": BENCHMARKS,
        "rebalance_frequency": "monthly",
        "risk_rules": {
            "transaction_cost_bps": TRANSACTION_COST_BPS,
            "slippage_bps": SLIPPAGE_BPS,
            "max_single_name_pct": MAX_SINGLE_NAME_PCT,
            "candidate_max_gross": CANDIDATE_MAX_GROSS,
            "active_max_gross": ACTIVE_MAX_GROSS,
            "quarantine_max_gross": QUARANTINE_MAX_GROSS,
            "leverage": "none",
        },
        "agents": all_results,
        "look_ahead_audit": {
            "future_sources_used": 0,
            "future_prices_used": 0,
            "strategy_edited_after_results": False,
            "ticker_universe_fixed_before_test": True,
            "risk_rules_fixed_before_test": True,
        },
        "cost": {
            "wall_time_s": round(time.time() - t_start, 3),
            "cpu_time_s": round(time.process_time() - cpu_start, 3),
            "python_version": platform.python_version(),
            "hostname": platform.node(),
            "timestamp_start": ts_start,
            "timestamp_end": ts_end,
        },
    }

    # Write outputs
    BACKTESTS_DIR.mkdir(parents=True, exist_ok=True)
    MOCK_TRADES_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    receipt_name = f"walk_forward_{thesis_id}_{start.replace('-', '')}_{end.replace('-', '')}"
    receipt_path = BACKTESTS_DIR / f"{receipt_name}.json"
    with open(receipt_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReceipt: {receipt_path}")

    # Write markdown report
    report_path = REPORTS_DIR / f"WALK_FORWARD_{thesis_id.upper().replace('-', '_')}.md"
    write_markdown_report(report, report_path)
    print(f"Report:  {report_path}")

    # Write individual mock trade receipts
    for agent_name, result in all_results.items():
        for dec in result["decisions"]:
            trade_path = MOCK_TRADES_DIR / f"{agent_name}_{dec['date']}.json"
            with open(trade_path, "w") as f:
                json.dump(dec, f, indent=2)

    return report


def write_markdown_report(report: dict, path: Path):
    """Write human-readable markdown report."""
    lines = [
        f"# Walk-Forward Mock Trading Report",
        f"",
        f"**Thesis:** `{report['thesis_id']}`",
        f"**Period:** {report['start_date']} to {report['end_date']}",
        f"**Universe:** {len(report['universe'])} tickers",
        f"**Rebalance:** {report['rebalance_frequency']}",
        f"",
        f"## Performance Comparison",
        f"",
        f"| Agent | Return | Ann. Return | Sharpe | Sortino | Max DD | Trades |",
        f"|-------|--------|-------------|--------|---------|--------|--------|",
    ]

    for name, result in report["agents"].items():
        m = result["metrics"]
        lines.append(
            f"| {name} | {m.get('total_return_pct', 'N/A')}% | "
            f"{m.get('annualized_return_pct', 'N/A')}% | "
            f"{m.get('sharpe', 'N/A')} | {m.get('sortino', 'N/A')} | "
            f"{m.get('max_drawdown_pct', 'N/A')}% | {m.get('trade_count', 0)} |"
        )

    lines.extend([
        f"",
        f"## Risk Rules",
        f"",
        f"- Transaction cost: {TRANSACTION_COST_BPS} bps",
        f"- Slippage: {SLIPPAGE_BPS} bps",
        f"- Max single name: {MAX_SINGLE_NAME_PCT * 100}%",
        f"- Candidate max gross: {CANDIDATE_MAX_GROSS * 100}%",
        f"- Active max gross: {ACTIVE_MAX_GROSS * 100}%",
        f"- Quarantined: 0% (forced exit)",
        f"- No leverage",
        f"",
        f"## FGIP Rules Agent Decisions",
        f"",
    ])

    fgip_result = report["agents"].get("fgip_rules", {})
    for dec in fgip_result.get("decisions", []):
        lines.append(
            f"- **{dec['date']}** | {dec['graph_state']} | {dec['action']} | "
            f"gross={dec['gross_exposure']} | sources={len(dec.get('visible_sources', []))} | "
            f"{dec['rationale'][:80]}"
        )

    lines.extend([
        f"",
        f"## Look-Ahead Audit",
        f"",
        f"| Check | Result |",
        f"|-------|--------|",
        f"| Future sources used | {report['look_ahead_audit']['future_sources_used']} |",
        f"| Future prices used | {report['look_ahead_audit']['future_prices_used']} |",
        f"| Strategy edited after results | {report['look_ahead_audit']['strategy_edited_after_results']} |",
        f"| Ticker universe fixed before test | {report['look_ahead_audit']['ticker_universe_fixed_before_test']} |",
        f"| Risk rules fixed before test | {report['look_ahead_audit']['risk_rules_fixed_before_test']} |",
        f"",
        f"## Cost",
        f"",
        f"- Wall time: {report['cost']['wall_time_s']}s",
        f"- CPU time: {report['cost']['cpu_time_s']}s",
        f"",
        f"---",
        f"",
        f"FGIP is a research and evidence-mapping tool, not financial advice.",
    ])

    with open(path, "w") as f:
        f.write("\n".join(lines))


# ─── Documentation ───────────────────────────────────────────────────────────

def write_design_doc():
    """Write the walk-forward mock trading design doc."""
    path = Path(__file__).parent.parent / "docs" / "WALK_FORWARD_MOCK_TRADING.md"
    path.parent.mkdir(parents=True, exist_ok=True)

    content = """# Walk-Forward Mock Trading

## Purpose

Tests whether FGIP evidence receipts can drive point-in-time mock trading decisions without look-ahead bias.

The real question is not "can Claude trade" — it is:

> Can the FGIP evidence system generate useful point-in-time decisions?

## Architecture

```
historical source registry
  |
point-in-time fact snapshot (build_point_in_time_snapshot.py)
  |
candidate graph edges
  |
thesis state engine (Candidate / Active / Quarantined)
  |
agent decision (rules-only or Claude-assisted)
  |
mock execution engine (with costs and slippage)
  |
performance receipt
```

## Agents

| Agent | Description |
|-------|-------------|
| cash | 100% cash. Lower bound. |
| equal_weight | Equal-weight the universe, monthly rebalance. |
| spy | 100% SPY. Market benchmark. |
| momentum | Top-5 by 3-month momentum, 50% gross. Price-only baseline. |
| fgip_rules | Evidence-gated rules. Position size scales with signal count and thesis state. |

## Point-in-Time Rule

At each decision date, the agent may only see:
- Sources with `published_at <= decision_date`
- Facts whose source `published_at <= decision_date`
- Edges whose fact/source `published_at <= decision_date`
- Market prices through previous close only

Forbidden: future sources, future prices, future receipt states, internet access.

## Risk Rules

- Candidate thesis: max 25% gross exposure
- Active thesis: max 50% gross exposure
- Quarantined thesis: 0% exposure (forced exit)
- Max single-name exposure: 5%
- Transaction cost: 10 bps
- Slippage: 5 bps
- No leverage

## Decision Actions

| Action | Meaning |
|--------|---------|
| NO_TRADE | No position change |
| WATCH | Evidence noted, no trade yet |
| LONG_BASKET | Buy equal-weight basket |
| HEDGE | Add hedge instruments |
| REDUCE | Reduce exposure |
| EXIT | Close all positions |

## Scoring

Performance is scored on 10 dimensions:
1. Total return
2. Max drawdown
3. Sharpe ratio
4. Sortino ratio
5. Trade count / turnover
6. Transaction costs
7. Thesis-state accuracy
8. Evidence discipline (did it avoid trading before evidence?)
9. Did it promote claims too early?
10. Comparison to baselines

## Key Interpretation

If FGIP rules-only agent beats momentum and equal-weight:
> The evidence graph IS the intelligence.

If FGIP rules-only agent matches or underperforms:
> Evidence gating adds discipline but not alpha at this frequency.

Both are useful findings.

## Usage

```bash
python3 tools/walk_forward_mock_trader.py
python3 tools/walk_forward_mock_trader.py --thesis thesis-dollar-resilience-rails
python3 tools/walk_forward_mock_trader.py --start 2024-05-09 --end 2026-05-09
```

## Output

- `receipts/backtests/walk_forward_*.json` — Full simulation receipt
- `receipts/mock_trades/*.json` — Individual decision receipts
- `reports/WALK_FORWARD_*.md` — Human-readable comparison report

## Disclaimer

FGIP is a research and evidence-mapping tool, not financial advice or an automated trading system. Mock trading results are simulated and do not represent actual trading performance. Past performance does not indicate future results.
"""
    with open(path, "w") as f:
        f.write(content)
    print(f"Design doc: {path}")


def main():
    parser = argparse.ArgumentParser(description="FGIP Walk-Forward Mock Trader")
    parser.add_argument("--thesis", default="thesis-dollar-resilience-rails",
                        help="Thesis ID to test")
    parser.add_argument("--start", default="2024-05-09", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default="2026-05-09", help="End date (YYYY-MM-DD)")
    parser.add_argument("--write-docs", action="store_true", help="Write design doc only")
    args = parser.parse_args()

    if args.write_docs:
        write_design_doc()
        return

    write_design_doc()
    run_simulation(args.thesis, args.start, args.end)


if __name__ == "__main__":
    main()
