"""
FGIP Trading Agent — Daily scanner and proposal generator.

Orchestrates: price ingest → conviction → tape → cascade → risk → proposal.

This is the Phase 1 implementation: READ-ONLY, NO EXECUTION.
Output: JSON proposal files for human review.

Usage:
    python3 -m fgip.agents.trading_agent --scan
    python3 -m fgip.agents.trading_agent --check-exits
    python3 -m fgip.agents.trading_agent --status
"""

import json
import os
import time
import resource
import platform
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .conviction_engine import ConvictionEngine
from .market_tape import MarketTapeAgent
from .cascade_detector import CascadeDetector

try:
    from ..data.price_manager import PriceManager
    from ..backtest.position_sizing import position_sizer
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False


# ═══════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════

@dataclass
class SignalProposal:
    """A proposed trade action for human review."""
    proposal_id: str
    timestamp: str
    symbol: str
    direction: str          # BUY, SELL, HOLD
    conviction_level: int   # 1-5
    conviction_score: float # 0-100

    # Sizing
    position_pct: float
    position_method: str

    # Price context
    current_price: float
    stop_loss: Optional[float]
    target_price: Optional[float]

    # Signals that triggered this proposal
    signals: List[Dict[str, Any]]

    # Graph support
    thesis_id: str
    thesis_statement: str
    supporting_edges: int
    contradicting_edges: int

    # Cascade
    cascade_stage: int
    cascade_label: str
    alpha_window: bool

    # Tape
    tape_verdict: str       # CONFIRMING, NEUTRAL, DIVERGING
    trend: str              # BULLISH, BEARISH, NEUTRAL
    volume_ratio: float
    rsi: Optional[float]

    # Risk
    risk_reward_ratio: Optional[float]
    max_loss_pct: float

    # Decision
    recommendation: str     # TRADE_READY, HOLD, PASS
    reason: str

    # Status
    status: str = "PENDING_REVIEW"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExitSignal:
    """Signal that an existing position should be reviewed."""
    symbol: str
    signal_type: str    # STOP_HIT, THESIS_INVALID, TARGET_REACHED, DRAWDOWN
    reason: str
    urgency: str        # IMMEDIATE, WITHIN_1_DAY, REVIEW
    current_price: float
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScanResult:
    """Complete result of a daily scan."""
    scan_id: str
    timestamp: str
    proposals: List[SignalProposal]
    exit_signals: List[ExitSignal]
    watchlist_summary: List[Dict[str, Any]]
    scan_duration_s: float
    symbols_scanned: int
    errors: List[str]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["proposals"] = [p.to_dict() for p in self.proposals]
        d["exit_signals"] = [e.to_dict() for e in self.exit_signals]
        return d


# ═══════════════════════════════════════════════════════════════════
# RISK PARAMETERS (HARD-CODED — NOT AI-ADJUSTABLE)
# ═══════════════════════════════════════════════════════════════════

def load_risk_params(watchlist_path: str) -> Dict[str, Any]:
    """Load risk parameters from watchlist config."""
    with open(watchlist_path) as f:
        config = json.load(f)
    return config["risk_params"]


def load_watchlist(watchlist_path: str) -> Dict[str, Dict[str, Any]]:
    """Load watchlist tickers with metadata, flattened across tiers."""
    with open(watchlist_path) as f:
        config = json.load(f)

    symbols = {}
    for tier_name, tier_data in config["tiers"].items():
        for sym, meta in tier_data["symbols"].items():
            meta["tier"] = tier_name
            meta["scan_frequency"] = tier_data["scan_frequency"]
            symbols[sym] = meta
    return symbols


def load_exit_rules(watchlist_path: str) -> Dict[str, Dict[str, str]]:
    """Load per-symbol exit/invalidation rules."""
    with open(watchlist_path) as f:
        config = json.load(f)
    return config.get("exit_rules", {})


# ═══════════════════════════════════════════════════════════════════
# TRADING AGENT
# ═══════════════════════════════════════════════════════════════════

class TradingAgent:
    """
    Daily scanning agent. Reads graph + market data, produces proposals.

    Phase 1: Read-only. No execution. Human reviews proposals.
    """

    def __init__(
        self,
        db_path: str = "fgip.db",
        watchlist_path: str = "config/watchlist.json",
        output_dir: str = "proposals",
    ):
        self.db_path = db_path
        self.watchlist_path = watchlist_path
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Load config
        self.risk_params = load_risk_params(watchlist_path)
        self.watchlist = load_watchlist(watchlist_path)
        self.exit_rules = load_exit_rules(watchlist_path)

        # Initialize components
        self.tape = MarketTapeAgent(db_path=db_path)
        self.cascade = CascadeDetector(db_path=db_path)

        # ConvictionEngine needs the DB object, not path
        self._conviction = None  # lazy init

    def _get_conviction_engine(self) -> ConvictionEngine:
        """Lazy-init conviction engine (needs DB import)."""
        if self._conviction is None:
            from fgip.db import FGIPDatabase
            db = FGIPDatabase(self.db_path)
            self._conviction = ConvictionEngine(db)
        return self._conviction

    def daily_scan(self, tiers: Optional[List[str]] = None) -> ScanResult:
        """
        Run full daily scan pipeline.

        1. Fetch tape for all watchlist symbols
        2. Evaluate thesis conviction
        3. Check cascade stages
        4. Generate proposals for actionable signals
        """
        t_start = time.time()
        now = datetime.utcnow()
        scan_id = f"scan-{now.strftime('%Y%m%dT%H%M%SZ')}"

        proposals = []
        exit_signals = []
        summary = []
        errors = []

        # Filter by tier if specified
        symbols = self.watchlist
        if tiers:
            symbols = {s: m for s, m in symbols.items() if m["tier"] in tiers}
        else:
            # Filter by scan frequency (skip weekly on non-Monday) only when no explicit tier
            if now.weekday() != 0:  # Not Monday
                symbols = {s: m for s, m in symbols.items()
                           if m["scan_frequency"] != "weekly"}

        print(f"\n{'='*60}")
        print(f"  FGIP TRADING AGENT — Daily Scan")
        print(f"  {now.strftime('%Y-%m-%d %H:%M UTC')}")
        print(f"  Scanning {len(symbols)} symbols")
        print(f"{'='*60}\n")

        # Evaluate theses
        conviction_engine = self._get_conviction_engine()
        thesis_reports = {}
        try:
            for report in conviction_engine.evaluate_all_theses():
                thesis_reports[report.thesis_id] = report
        except Exception as e:
            errors.append(f"Conviction engine error: {e}")

        # Scan each symbol
        for sym, meta in sorted(symbols.items()):
            try:
                result = self._scan_symbol(
                    sym, meta, thesis_reports
                )
                summary.append(result["summary"])
                if result.get("proposal"):
                    proposals.append(result["proposal"])
                if result.get("exit_signal"):
                    exit_signals.append(result["exit_signal"])
            except Exception as e:
                errors.append(f"{sym}: {e}")
                summary.append({
                    "symbol": sym,
                    "status": "ERROR",
                    "error": str(e),
                })

        elapsed = time.time() - t_start

        scan = ScanResult(
            scan_id=scan_id,
            timestamp=now.isoformat() + "Z",
            proposals=proposals,
            exit_signals=exit_signals,
            watchlist_summary=summary,
            scan_duration_s=round(elapsed, 2),
            symbols_scanned=len(symbols),
            errors=errors,
        )

        # Save to file
        self._save_scan(scan)
        self._print_scan(scan)

        return scan

    def _scan_symbol(
        self,
        symbol: str,
        meta: Dict[str, Any],
        thesis_reports: Dict,
    ) -> Dict[str, Any]:
        """Scan a single symbol: tape + conviction + cascade → proposal."""

        result: Dict[str, Any] = {"summary": {}, "proposal": None, "exit_signal": None}

        # 1. Fetch tape
        tape_analysis = self.tape.fetch_tape(symbol)

        price = 0.0
        tape_verdict = "UNKNOWN"
        trend = "UNKNOWN"
        volume_ratio = 0.0
        rsi = None

        if tape_analysis:
            price = tape_analysis.snapshot.price
            tape_verdict = tape_analysis.tape_verdict
            trend = tape_analysis.technicals.trend
            volume_ratio = tape_analysis.technicals.volume_ratio
            rsi = tape_analysis.technicals.rsi_14

        # 2. Get thesis conviction
        thesis_id = meta.get("thesis", "")
        conviction_level = 0
        conviction_score = 0.0
        recommendation = "HOLD"
        supporting = 0
        contradicting = 0
        thesis_statement = ""
        stop_loss_pct = None
        target_pct = None

        # Try exact thesis match first, then partial
        report = thesis_reports.get(thesis_id)
        if not report:
            # Try matching by ticker in any thesis
            for tid, r in thesis_reports.items():
                if symbol in [t.upper() for t in r.tickers]:
                    report = r
                    break

        if report:
            conviction_level = report.conviction_level
            conviction_score = report.conviction_score
            recommendation = report.recommendation
            supporting = len(report.confirming_signals)
            contradicting = len(report.refuting_signals)
            thesis_statement = report.thesis_statement
            stop_loss_pct = report.stop_loss_pct
            target_pct = report.target_price_pct

        # 3. Check cascade
        cascade_state = self.cascade.check_stage(thesis_id) if thesis_id else None
        cascade_stage = cascade_state.current_stage if cascade_state else 0
        cascade_label = cascade_state.stage_label if cascade_state else "NO_ACTIVITY"
        alpha_window = cascade_state.alpha_window if cascade_state else False

        # 4. Position sizing
        sizing = {"final_size": 0.0, "base_size": 0.0}
        if HAS_DEPS and conviction_level >= self.risk_params["min_conviction_to_trade"]:
            sizing = position_sizer(
                conviction_level=conviction_level,
                max_position_pct=self.risk_params["max_single_position"],
                method="conviction",
            )

        # 5. Compute stop/target prices
        stop_price = None
        target_price = None
        risk_reward = None
        if price > 0 and stop_loss_pct:
            stop_price = round(price * (1 - stop_loss_pct), 2)
        if price > 0 and target_pct:
            target_price = round(price * (1 + target_pct), 2)
        if stop_price and target_price and price > stop_price:
            risk_reward = round((target_price - price) / (price - stop_price), 2)

        # 6. Collect signals
        signals = []
        if tape_analysis:
            for event in tape_analysis.events:
                signals.append({
                    "type": event.event_type,
                    "description": event.description,
                    "magnitude": event.magnitude,
                    "source": "market_tape",
                })
        if alpha_window:
            signals.append({
                "type": "CASCADE_ALPHA_WINDOW",
                "description": f"Thesis at stage {cascade_stage} ({cascade_label})",
                "magnitude": 1.0,
                "source": "cascade_detector",
            })

        # 7. Determine recommendation
        action = "HOLD"
        reason = ""

        if conviction_level >= self.risk_params["min_conviction_to_trade"]:
            if tape_verdict == "CONFIRMING" and trend in ("BULLISH", "NEUTRAL"):
                action = "TRADE_READY"
                reason = f"Conviction {conviction_level}/5, tape {tape_verdict}, trend {trend}"
                if alpha_window:
                    reason += f", CASCADE ALPHA WINDOW (stage {cascade_stage})"
            elif tape_verdict == "CONFIRMING":
                action = "HOLD"
                reason = f"Conviction {conviction_level}/5 but trend {trend} — wait for setup"
            else:
                action = "HOLD"
                reason = f"Conviction {conviction_level}/5 but tape {tape_verdict}"
        else:
            action = "PASS"
            reason = f"Conviction {conviction_level}/5 below minimum {self.risk_params['min_conviction_to_trade']}"

        # 8. Build summary
        result["summary"] = {
            "symbol": symbol,
            "name": meta.get("name", symbol),
            "tier": meta["tier"],
            "price": price,
            "conviction": conviction_level,
            "tape": tape_verdict,
            "trend": trend,
            "volume_ratio": round(volume_ratio, 2),
            "rsi": round(rsi, 1) if rsi else None,
            "cascade_stage": cascade_stage,
            "action": action,
        }

        status_icon = {"TRADE_READY": ">>", "HOLD": "--", "PASS": "  "}
        print(f"  {status_icon.get(action, '  ')} {symbol:5s} ${price:>8.2f}  "
              f"conv={conviction_level}  tape={tape_verdict:10s}  "
              f"trend={trend:8s}  vol={volume_ratio:.1f}x  "
              f"cascade={cascade_stage}  → {action}")

        # 9. Create proposal if actionable
        if action == "TRADE_READY" and price > 0:
            now_str = datetime.utcnow().isoformat() + "Z"
            proposal = SignalProposal(
                proposal_id=f"prop-{symbol}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}",
                timestamp=now_str,
                symbol=symbol,
                direction="BUY",
                conviction_level=conviction_level,
                conviction_score=conviction_score,
                position_pct=sizing["final_size"],
                position_method="conviction",
                current_price=price,
                stop_loss=stop_price,
                target_price=target_price,
                signals=signals,
                thesis_id=thesis_id,
                thesis_statement=thesis_statement[:200],
                supporting_edges=supporting,
                contradicting_edges=contradicting,
                cascade_stage=cascade_stage,
                cascade_label=cascade_label,
                alpha_window=alpha_window,
                tape_verdict=tape_verdict,
                trend=trend,
                volume_ratio=round(volume_ratio, 2),
                rsi=round(rsi, 1) if rsi else None,
                risk_reward_ratio=risk_reward,
                max_loss_pct=self.risk_params["max_daily_loss"],
                recommendation=action,
                reason=reason,
            )
            result["proposal"] = proposal

        # 10. Check exit rules
        exit_rule = self.exit_rules.get(symbol)
        if exit_rule and tape_verdict == "DIVERGING" and trend == "BEARISH":
            result["exit_signal"] = ExitSignal(
                symbol=symbol,
                signal_type="THESIS_DIVERGING",
                reason=f"Tape diverging + bearish trend. Invalidation: {exit_rule.get('invalidation', 'N/A')}",
                urgency="REVIEW",
                current_price=price,
                timestamp=datetime.utcnow().isoformat() + "Z",
            )

        return result

    def _save_scan(self, scan: ScanResult):
        """Save scan results to JSON file."""
        filename = f"{scan.scan_id}.json"
        filepath = self.output_dir / filename

        output = scan.to_dict()

        # Add cost block per WO-RECEIPT-COST-01
        output["cost"] = {
            "wall_time_s": scan.scan_duration_s,
            "python_version": platform.python_version(),
            "hostname": platform.node(),
            "timestamp": scan.timestamp,
        }

        with open(filepath, "w") as f:
            json.dump(output, f, indent=2, default=str)

        print(f"\n  Saved: {filepath}")

    def _print_scan(self, scan: ScanResult):
        """Print scan summary to terminal."""
        print(f"\n{'='*60}")
        print(f"  SCAN COMPLETE — {scan.scan_duration_s:.1f}s")
        print(f"  Symbols: {scan.symbols_scanned}")
        print(f"  Proposals: {len(scan.proposals)}")
        print(f"  Exit signals: {len(scan.exit_signals)}")
        if scan.errors:
            print(f"  Errors: {len(scan.errors)}")
            for e in scan.errors[:5]:
                print(f"    - {e}")
        print(f"{'='*60}")

        if scan.proposals:
            print(f"\n  PROPOSALS:")
            for p in scan.proposals:
                print(f"\n  {'─'*56}")
                print(f"  {p.direction} {p.symbol} — {p.recommendation}")
                print(f"  Conviction: {p.conviction_level}/5 ({p.conviction_score:.0f})")
                stop = f"${p.stop_loss:.2f}" if p.stop_loss else "N/A"
                target = f"${p.target_price:.2f}" if p.target_price else "N/A"
                print(f"  Price: ${p.current_price:.2f}  Stop: {stop}  Target: {target}")
                print(f"  Position: {p.position_pct*100:.1f}%  "
                      f"R:R = {p.risk_reward_ratio or 'N/A'}")
                print(f"  Tape: {p.tape_verdict}  Trend: {p.trend}  "
                      f"Vol: {p.volume_ratio:.1f}x  RSI: {p.rsi or 'N/A'}")
                if p.alpha_window:
                    print(f"  *** CASCADE ALPHA WINDOW — Stage {p.cascade_stage} ***")
                print(f"  Reason: {p.reason}")
                print(f"  Thesis: {p.thesis_statement[:80]}...")

        if scan.exit_signals:
            print(f"\n  EXIT SIGNALS:")
            for e in scan.exit_signals:
                print(f"  !! {e.symbol} [{e.urgency}]: {e.reason}")

        print()


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="FGIP Trading Agent — scan, propose, monitor"
    )
    parser.add_argument("--scan", action="store_true",
                        help="Run daily scan and generate proposals")
    parser.add_argument("--tier", nargs="+",
                        help="Only scan specific tiers (tier_1, tier_2, tier_3)")
    parser.add_argument("--status", action="store_true",
                        help="Show watchlist status (no proposals)")
    parser.add_argument("--db", default="fgip.db",
                        help="FGIP database path")
    parser.add_argument("--config", default="config/watchlist.json",
                        help="Watchlist config path")
    parser.add_argument("--output", default="proposals",
                        help="Proposal output directory")
    args = parser.parse_args()

    agent = TradingAgent(
        db_path=args.db,
        watchlist_path=args.config,
        output_dir=args.output,
    )

    if args.scan or args.status:
        agent.daily_scan(tiers=args.tier)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
