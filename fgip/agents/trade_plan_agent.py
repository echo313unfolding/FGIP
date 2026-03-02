"""
FGIP Trade Plan Agent - Decision gates and trade memo generation.

The culmination of the trade memo pipeline:
1. Graph truth (mechanism) - from ConvictionEngine
2. Market confirmation (tape) - from MarketTapeAgent
3. Forecast (distributions) - from ForecastAgent
4. Decision gates (provenance, triangulation, calibration, risk)
5. Trade memo output

A trade memo is NOT a recommendation - it's a structured summary
of what we know, how confident we are, and what could go wrong.

Safety rules:
- All gates must pass for TRADE_READY
- Gate failures produce HOLD or PASS
- Every decision is logged for audit
- Not investment advice
"""

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fgip.analysis.provenance import DataProvenance
from .conviction_engine import ConvictionEngine, ConvictionReport
from .market_tape import MarketTapeAgent, TapeAnalysis
from .forecast_agent import ForecastAgent, ForecastObject


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class GateResult:
    """Result of a decision gate check."""
    gate_name: str
    passed: bool
    score: float  # 0-1
    reason: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TradeMemo:
    """Complete trade memo combining all layers."""
    memo_id: str
    thesis_id: str
    symbol: Optional[str]
    created_at: str

    # Three layers of why
    mechanism_layer: Dict[str, Any]  # Graph truth
    market_layer: Dict[str, Any]  # Tape confirmation
    forecast_layer: Dict[str, Any]  # Probability distributions

    # Decision gates
    gates: List[GateResult]
    gates_passed: int
    gates_total: int

    # Final decision
    decision: str  # TRADE_READY, HOLD, PASS
    decision_confidence: float
    position_sizing: Dict[str, Any]

    # What could go wrong
    risks: List[str]
    counter_thesis: str
    invalidation_criteria: List[str]

    # Audit trail
    source_ids: List[str]
    evidence_count: int
    tier_0_count: int


# =============================================================================
# DECISION GATES
# =============================================================================

def provenance_gate(
    sources: List[Dict[str, Any]],
    tier_0_required: int = 1
) -> GateResult:
    """
    Gate 1: Provenance - Do we have authoritative sources?

    Requires at least tier_0_required Tier-0/1 sources.
    """
    tier_01_count = sum(1 for s in sources if s.get('tier', 3) <= 1)

    passed = tier_01_count >= tier_0_required
    score = min(tier_01_count / max(tier_0_required, 1), 1.0)

    return GateResult(
        gate_name="PROVENANCE",
        passed=passed,
        score=score,
        reason=f"{tier_01_count} Tier-0/1 sources (need {tier_0_required})",
        details={"tier_01_count": tier_01_count, "required": tier_0_required}
    )


def triangulation_gate(
    source_types: List[str],
    required_types: int = 3
) -> GateResult:
    """
    Gate 2: Triangulation - Multiple independent source types?

    Requires at least required_types different source types.
    """
    unique_types = set(source_types)
    count = len(unique_types)

    passed = count >= required_types
    score = min(count / required_types, 1.0)

    return GateResult(
        gate_name="TRIANGULATION",
        passed=passed,
        score=score,
        reason=f"{count} source types (need {required_types}): {', '.join(sorted(unique_types))}",
        details={"source_types": list(unique_types), "count": count, "required": required_types}
    )


def calibration_gate(
    forecast: ForecastObject,
    min_confidence: float = 0.5
) -> GateResult:
    """
    Gate 3: Calibration - Is forecast confidence sufficient?

    Checks forecast confidence, data quality, AND provenance verification.
    FAIL-CLOSED: If forecast has no verifiable provenance, gate fails.
    """
    # FAIL-CLOSED: Check provenance first
    if not forecast.provenance or not forecast.provenance.is_verifiable():
        return GateResult(
            gate_name="CALIBRATION",
            passed=False,
            score=0.0,
            reason="FORECAST UNVERIFIED - no provenance",
            details={
                "verified": False,
                "provenance": forecast.provenance.source_type if forecast.provenance else "missing"
            }
        )

    confidence = forecast.confidence_in_forecast
    data_quality = forecast.data_quality_score

    combined = (confidence + data_quality) / 2
    passed = combined >= min_confidence

    return GateResult(
        gate_name="CALIBRATION",
        passed=passed,
        score=combined,
        reason=f"Forecast confidence {confidence:.0%}, data quality {data_quality:.0%}",
        details={
            "confidence": confidence,
            "data_quality": data_quality,
            "combined": combined,
            "prior_accuracy": forecast.prior_accuracy,
            "verified": True,
            "forecast_id": forecast.provenance.source_ref
        }
    )


def risk_gate(
    forecast: ForecastObject,
    max_prob_loss: float = 0.50,
    max_drawdown: float = -25.0
) -> GateResult:
    """
    Gate 4: Risk - Is the risk/reward acceptable?

    Checks probability of loss and max drawdown.
    """
    prob_loss = forecast.probability_of_loss
    max_dd = forecast.drawdown_distribution.p10  # Worst case

    risk_ok = prob_loss <= max_prob_loss
    dd_ok = max_dd >= max_drawdown

    passed = risk_ok and dd_ok
    score = (1 - prob_loss) * (1 - abs(max_dd) / 100)

    reasons = []
    if not risk_ok:
        reasons.append(f"P(loss) {prob_loss:.0%} > {max_prob_loss:.0%}")
    if not dd_ok:
        reasons.append(f"Max DD {max_dd:.0%} < {max_drawdown:.0%}")

    return GateResult(
        gate_name="RISK",
        passed=passed,
        score=max(score, 0),
        reason=" | ".join(reasons) if reasons else f"P(loss) {prob_loss:.0%}, Max DD {max_dd:.0%}",
        details={
            "probability_of_loss": prob_loss,
            "max_drawdown_p10": max_dd,
            "max_prob_loss": max_prob_loss,
            "max_drawdown_limit": max_drawdown
        }
    )


def market_confirmation_gate(
    tape: Optional[TapeAnalysis],
    thesis_direction: str = "BULLISH"
) -> GateResult:
    """
    Gate 5: Market Confirmation - Does the tape agree?

    FAIL-CLOSED: Requires verified tape data.
    If tape is mock/unverified, gate fails.
    """
    # FAIL-CLOSED: No tape data
    if tape is None:
        return GateResult(
            gate_name="MARKET_CONFIRMATION",
            passed=False,  # CHANGED from True
            score=0.0,     # CHANGED from 0.5
            reason="TAPE UNAVAILABLE - cannot confirm market",
            details={"verified": False}
        )

    # FAIL-CLOSED: Check tape provenance
    if not tape.provenance or not tape.provenance.is_verifiable():
        return GateResult(
            gate_name="MARKET_CONFIRMATION",
            passed=False,
            score=0.0,
            reason="TAPE UNVERIFIED - mock data cannot confirm market",
            details={
                "verified": False,
                "provenance": tape.provenance.source_type if tape.provenance else "missing"
            }
        )

    if thesis_direction == "BULLISH":
        confirms = tape.tape_verdict == "CONFIRMING"
        diverges = tape.tape_verdict == "DIVERGING"
    else:
        confirms = tape.tape_verdict == "DIVERGING"
        diverges = tape.tape_verdict == "CONFIRMING"

    # Soft gate - divergence doesn't fail but reduces score
    passed = not diverges
    score = tape.confidence if confirms else (0.5 if not diverges else 0.3)

    return GateResult(
        gate_name="MARKET_CONFIRMATION",
        passed=passed,
        score=score,
        reason=f"Tape: {tape.tape_verdict} ({tape.technicals.trend} trend)",
        details={
            "tape_verdict": tape.tape_verdict,
            "trend": tape.technicals.trend,
            "confirms": confirms,
            "diverges": diverges,
            "verified": True,
            "provenance": tape.provenance.source_type
        }
    )


# =============================================================================
# TRADE PLAN AGENT
# =============================================================================

class TradePlanAgent:
    """
    Generate complete trade memos with decision gates.

    Integrates:
    - ConvictionEngine (mechanism truth)
    - MarketTapeAgent (market confirmation)
    - ForecastAgent (probability distributions)
    """

    AGENT_NAME = "trade-plan"
    TIER = 3  # Meta-agent

    def __init__(self, db_path: str = "fgip.db"):
        """Initialize with all sub-agents."""
        from fgip.db import FGIPDatabase
        self.db_path = Path(db_path)
        self.db = FGIPDatabase(str(db_path))
        self.conviction = ConvictionEngine(self.db)
        self.tape = MarketTapeAgent(str(db_path))
        self.forecast = ForecastAgent(str(db_path))
        self._ensure_tables()

    def _get_db(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self):
        """Create trade memo tables if needed."""
        conn = self._get_db()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS trade_memos (
                    memo_id TEXT PRIMARY KEY,
                    thesis_id TEXT,
                    symbol TEXT,
                    decision TEXT,
                    decision_confidence REAL,
                    gates_passed INTEGER,
                    gates_total INTEGER,
                    position_size_pct REAL,
                    created_at TEXT,
                    memo_json TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_memos_thesis ON trade_memos(thesis_id);
                CREATE INDEX IF NOT EXISTS idx_memos_decision ON trade_memos(decision);
            """)
            conn.commit()
        finally:
            conn.close()

    def generate_memo(
        self,
        thesis_id: str,
        symbol: Optional[str] = None,
        thesis_direction: str = "BULLISH",
        time_horizon_days: int = 90,
        max_position_pct: float = 0.10
    ) -> TradeMemo:
        """
        Generate a complete trade memo.

        Args:
            thesis_id: ID of thesis to evaluate
            symbol: Optional ticker symbol
            thesis_direction: BULLISH or BEARISH
            time_horizon_days: Investment horizon
            max_position_pct: Maximum position size

        Returns:
            TradeMemo with full analysis
        """
        # Layer 1: Mechanism (Graph Truth)
        try:
            conviction_report = self.conviction.evaluate_thesis(thesis_id)
            mechanism_layer = {
                "conviction_level": conviction_report.conviction_level,
                "confidence": conviction_report.conviction_score / 100.0,
                "reasoning": f"Triangulation: {conviction_report.triangulation_met}, Sources: {conviction_report.triangulation_sources}",
                "source_count": len(conviction_report.confirming_signals),
                "triangulation": conviction_report.triangulation_met
            }
            sources = [{"tier": s.source_tier, "type": s.source_type} for s in conviction_report.confirming_signals]
            source_types = conviction_report.triangulation_sources
        except Exception as e:
            mechanism_layer = {
                "conviction_level": 1,
                "confidence": 0.3,
                "reasoning": f"Conviction evaluation failed: {e}",
                "source_count": 0,
                "triangulation": False
            }
            sources = []
            source_types = []

        # Layer 2: Market Confirmation
        tape_analysis = None
        if symbol:
            tape_analysis = self.tape.fetch_tape(symbol)

        # Check tape provenance for verification
        tape_verified = False
        if tape_analysis and tape_analysis.provenance:
            tape_verified = tape_analysis.provenance.is_verifiable()

        if tape_analysis and tape_verified:
            market_layer = {
                "tape_verdict": tape_analysis.tape_verdict,
                "trend": tape_analysis.technicals.trend,
                "rsi": tape_analysis.technicals.rsi_14,
                "price": tape_analysis.snapshot.price,
                "volume_ratio": tape_analysis.technicals.volume_ratio,
                "events": [e.event_type for e in tape_analysis.events],
                "provenance": tape_analysis.provenance.source_type,
                "verified": True
            }
        elif tape_analysis:
            # Tape exists but is NOT verified (mock data)
            market_layer = {
                "tape_verdict": "UNVERIFIED",
                "trend": "UNKNOWN",
                "rsi": None,
                "price": None,
                "volume_ratio": None,
                "events": [],
                "provenance": tape_analysis.provenance.source_type if tape_analysis.provenance else "missing",
                "verified": False
            }
        else:
            market_layer = {
                "tape_verdict": "UNAVAILABLE",
                "trend": "UNKNOWN",
                "rsi": None,
                "price": None,
                "volume_ratio": None,
                "events": [],
                "provenance": None,
                "verified": False
            }

        # Layer 3: Forecast
        forecast_obj = self.forecast.generate_forecast(
            thesis_id=thesis_id,
            symbol=symbol,
            conviction_level=mechanism_layer["conviction_level"],
            thesis_confidence=mechanism_layer["confidence"],
            market_confirmation=tape_analysis.confidence if tape_analysis else 0.5,
            time_horizon_days=time_horizon_days,
            inputs={
                "source_count": len(sources),
                "source_types": len(source_types),
                "tier_0_sources": sum(1 for s in sources if s.get('tier', 3) == 0)
            }
        )

        # Check forecast provenance for verification
        forecast_verified = False
        if forecast_obj.provenance:
            forecast_verified = forecast_obj.provenance.is_verifiable()

        if forecast_verified:
            forecast_layer = {
                "return_p10": forecast_obj.return_distribution.p10,
                "return_p50": forecast_obj.return_distribution.p50,
                "return_p90": forecast_obj.return_distribution.p90,
                "drawdown_p10": forecast_obj.drawdown_distribution.p10,
                "probability_of_loss": forecast_obj.probability_of_loss,
                "probability_of_thesis": forecast_obj.probability_of_thesis,
                "confidence": forecast_obj.confidence_in_forecast,
                "forecast_id": forecast_obj.provenance.source_ref,
                "verified": True
            }
        else:
            # FAIL CLOSED: Don't use unverified forecast numbers
            forecast_layer = {
                "return_p10": None,
                "return_p50": None,
                "return_p90": None,
                "drawdown_p10": None,
                "probability_of_loss": None,
                "probability_of_thesis": None,
                "confidence": None,
                "forecast_id": None,
                "verified": False
            }

        # Decision Gates
        gates = [
            provenance_gate(sources, tier_0_required=1),
            triangulation_gate(source_types, required_types=2),
            calibration_gate(forecast_obj, min_confidence=0.4),
            risk_gate(forecast_obj, max_prob_loss=0.50, max_drawdown=-30.0),
            market_confirmation_gate(tape_analysis, thesis_direction)
        ]

        gates_passed = sum(1 for g in gates if g.passed)
        gates_total = len(gates)

        # Final Decision
        if gates_passed == gates_total:
            decision = "TRADE_READY"
            decision_confidence = sum(g.score for g in gates) / gates_total
        elif gates_passed >= 3:
            decision = "HOLD"
            decision_confidence = sum(g.score for g in gates) / gates_total * 0.8
        else:
            decision = "PASS"
            decision_confidence = sum(g.score for g in gates) / gates_total * 0.5

        # Position Sizing (based on conviction and gates)
        if decision == "TRADE_READY":
            conviction_level = mechanism_layer["conviction_level"]
            base_size = {1: 0.02, 2: 0.04, 3: 0.06, 4: 0.08, 5: 0.10}.get(conviction_level, 0.05)
            position_size = min(base_size * decision_confidence, max_position_pct)
        else:
            position_size = 0.0

        position_sizing = {
            "recommended_pct": round(position_size * 100, 1),
            "max_pct": max_position_pct * 100,
            "conviction_level": mechanism_layer["conviction_level"],
            "scaling_factor": decision_confidence
        }

        # Risks and Counter-Thesis
        risks = self._identify_risks(mechanism_layer, market_layer, forecast_layer, gates)
        counter_thesis = self._generate_counter_thesis(thesis_id, thesis_direction)
        invalidation = self._generate_invalidation_criteria(forecast_obj, tape_analysis)

        memo_id = f"memo-{thesis_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        memo = TradeMemo(
            memo_id=memo_id,
            thesis_id=thesis_id,
            symbol=symbol,
            created_at=datetime.now().isoformat(),
            mechanism_layer=mechanism_layer,
            market_layer=market_layer,
            forecast_layer=forecast_layer,
            gates=gates,
            gates_passed=gates_passed,
            gates_total=gates_total,
            decision=decision,
            decision_confidence=round(decision_confidence, 2),
            position_sizing=position_sizing,
            risks=risks,
            counter_thesis=counter_thesis,
            invalidation_criteria=invalidation,
            source_ids=[s.get('id', 'unknown') for s in sources],
            evidence_count=len(sources),
            tier_0_count=sum(1 for s in sources if s.get('tier', 3) == 0)
        )

        # Store memo
        self._store_memo(memo)

        # Write provenance receipt for audit trail
        receipt_path = self._write_memo_receipt(
            memo,
            tape_analysis.provenance if tape_analysis else None,
            forecast_obj.provenance if forecast_obj else None,
            thesis_direction
        )

        return memo

    def _identify_risks(
        self,
        mechanism: Dict,
        market: Dict,
        forecast: Dict,
        gates: List[GateResult]
    ) -> List[str]:
        """Identify key risks from the analysis."""
        risks = []

        # Gate failures
        for gate in gates:
            if not gate.passed:
                risks.append(f"[{gate.gate_name}] {gate.reason}")

        # Forecast risks
        if forecast["probability_of_loss"] > 0.3:
            risks.append(f"High P(loss): {forecast['probability_of_loss']:.0%}")

        if forecast["drawdown_p10"] < -20:
            risks.append(f"Severe drawdown risk: {forecast['drawdown_p10']:.0%}")

        # Market risks
        if market["tape_verdict"] == "DIVERGING":
            risks.append("Tape diverges from thesis")

        if market.get("rsi") and market["rsi"] > 70:
            risks.append("RSI overbought - may pullback")

        # Conviction risks
        if mechanism["conviction_level"] <= 2:
            risks.append("Low conviction - weak evidence base")

        if not mechanism["triangulation"]:
            risks.append("No triangulation - single source type")

        return risks[:5]  # Cap at 5 most important

    def _generate_counter_thesis(self, thesis_id: str, direction: str) -> str:
        """Generate the strongest counter-argument."""
        # Query graph for counter-evidence
        conn = self._get_db()
        try:
            # Look for edges that contradict the thesis
            row = conn.execute("""
                SELECT e.edge_type, e.notes
                FROM edges e
                WHERE e.edge_type LIKE '%counter%' OR e.notes LIKE '%against%'
                LIMIT 1
            """).fetchone()

            if row:
                return f"Counter-evidence found: {row['edge_type']}"

            # Default counter based on direction
            if direction == "BULLISH":
                return "Bear case: Thesis may already be priced in; macro headwinds could override fundamentals"
            else:
                return "Bull case: Short squeeze risk; positive catalyst could invalidate bearish thesis"

        finally:
            conn.close()

    def _generate_invalidation_criteria(
        self,
        forecast: ForecastObject,
        tape: Optional[TapeAnalysis]
    ) -> List[str]:
        """Generate criteria that would invalidate the thesis."""
        criteria = []

        # Price-based invalidation
        if tape and tape.snapshot:
            stop_loss = tape.snapshot.price * 0.90  # 10% stop
            criteria.append(f"Price below ${stop_loss:.2f} (10% stop)")

        # Time-based invalidation
        criteria.append(f"No catalyst within {forecast.time_horizon_days} days")

        # Probability invalidation
        if forecast.probability_of_thesis < 0.6:
            criteria.append("P(thesis) drops below 40%")

        # Evidence invalidation
        criteria.append("Primary document contradicts thesis")

        return criteria

    def _store_memo(self, memo: TradeMemo):
        """Store trade memo in database."""
        conn = self._get_db()
        try:
            # Convert gates to serializable format
            gates_data = [
                {
                    "gate_name": g.gate_name,
                    "passed": g.passed,
                    "score": g.score,
                    "reason": g.reason
                }
                for g in memo.gates
            ]

            memo_json = json.dumps({
                "mechanism_layer": memo.mechanism_layer,
                "market_layer": memo.market_layer,
                "forecast_layer": memo.forecast_layer,
                "gates": gates_data,
                "position_sizing": memo.position_sizing,
                "risks": memo.risks,
                "counter_thesis": memo.counter_thesis,
                "invalidation_criteria": memo.invalidation_criteria
            })

            conn.execute("""
                INSERT OR REPLACE INTO trade_memos (
                    memo_id, thesis_id, symbol, decision, decision_confidence,
                    gates_passed, gates_total, position_size_pct, created_at, memo_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                memo.memo_id, memo.thesis_id, memo.symbol, memo.decision,
                memo.decision_confidence, memo.gates_passed, memo.gates_total,
                memo.position_sizing["recommended_pct"], memo.created_at, memo_json
            ))
            conn.commit()
        finally:
            conn.close()

    def _write_memo_receipt(
        self,
        memo: TradeMemo,
        tape_provenance: Optional[DataProvenance],
        forecast_provenance: Optional[DataProvenance],
        thesis_direction: str = "BULLISH"
    ) -> str:
        """Write JSON receipt for audit trail.

        Creates a provenance-tracking receipt in receipts/trade_memos/
        that documents the data sources and verification status.

        Returns:
            Path to receipt file
        """
        receipt_dir = Path(__file__).parent.parent.parent / "receipts" / "trade_memos"
        receipt_dir.mkdir(parents=True, exist_ok=True)

        receipt = {
            "memo_id": memo.memo_id,
            "thesis_id": memo.thesis_id,
            "symbol": memo.symbol,
            "direction": thesis_direction,
            "created_at": memo.created_at,
            "decision": memo.decision,
            "decision_confidence": memo.decision_confidence,

            # Provenance section
            "provenance": {
                "tape": {
                    "verified": tape_provenance.is_verifiable() if tape_provenance else False,
                    "source_type": tape_provenance.source_type if tape_provenance else None,
                    "retrieved_at": tape_provenance.retrieved_at if tape_provenance else None,
                    "content_hash": tape_provenance.content_hash if tape_provenance else None,
                },
                "forecast": {
                    "verified": forecast_provenance.is_verifiable() if forecast_provenance else False,
                    "source_type": forecast_provenance.source_type if forecast_provenance else None,
                    "source_ref": forecast_provenance.source_ref if forecast_provenance else None,
                },
            },

            # Conviction snapshot
            "conviction": {
                "level": memo.mechanism_layer.get("conviction_level"),
                "triangulation_met": memo.mechanism_layer.get("triangulation"),
                "source_count": memo.mechanism_layer.get("source_count"),
            },

            # Gates (only if computed from verified data)
            "gates": [
                {
                    "name": g.gate_name,
                    "passed": g.passed,
                    "score": g.score,
                    "reason": g.reason
                }
                for g in memo.gates
            ],

            # Market layer (only verified values)
            "market_layer": memo.market_layer if memo.market_layer.get("verified") else {"verified": False},

            # Forecast layer (only verified values)
            "forecast_layer": memo.forecast_layer if memo.forecast_layer.get("verified") else {"verified": False},
        }

        receipt_path = receipt_dir / f"{memo.memo_id}.json"
        receipt_path.write_text(json.dumps(receipt, indent=2))
        return str(receipt_path)

    def get_recent_memos(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent trade memos."""
        conn = self._get_db()
        try:
            rows = conn.execute("""
                SELECT memo_id, thesis_id, symbol, decision, decision_confidence,
                       gates_passed, gates_total, position_size_pct, created_at
                FROM trade_memos
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,)).fetchall()

            return [dict(row) for row in rows]
        finally:
            conn.close()

# =============================================================================
# CLI
# =============================================================================

def format_memo(memo: TradeMemo) -> str:
    """Format trade memo for display."""
    lines = []
    lines.append(f"\n{'='*60}")
    lines.append(f"TRADE MEMO: {memo.memo_id}")
    lines.append(f"{'='*60}")
    lines.append(f"Thesis: {memo.thesis_id}")
    if memo.symbol:
        lines.append(f"Symbol: {memo.symbol}")
    lines.append(f"Created: {memo.created_at}")

    lines.append(f"\n--- MECHANISM (Graph Truth) ---")
    m = memo.mechanism_layer
    lines.append(f"  Conviction: Level {m['conviction_level']} ({m['confidence']:.0%})")
    lines.append(f"  Sources: {m['source_count']}")
    lines.append(f"  Triangulation: {'Yes' if m['triangulation'] else 'No'}")

    lines.append(f"\n--- MARKET (Tape Confirmation) ---")
    mk = memo.market_layer
    if mk.get('verified', True):
        lines.append(f"  Verdict: {mk['tape_verdict']}")
        lines.append(f"  Trend: {mk['trend']}")
        if mk.get('price'):
            lines.append(f"  Price: ${mk['price']}")
        if mk.get('rsi'):
            lines.append(f"  RSI: {mk['rsi']}")
    else:
        lines.append(f"  ** TAPE UNVERIFIED - mock data ({mk.get('provenance', 'unknown')}) **")

    lines.append(f"\n--- FORECAST (Distributions) ---")
    f = memo.forecast_layer
    if f.get('verified', True) and f.get('return_p50') is not None:
        lines.append(f"  Returns (P10/P50/P90): {f['return_p10']:.1f}% / {f['return_p50']:.1f}% / {f['return_p90']:.1f}%")
        lines.append(f"  Max Drawdown (P10): {f['drawdown_p10']:.1f}%")
        lines.append(f"  P(loss): {f['probability_of_loss']:.0%}")
        lines.append(f"  Forecast confidence: {f['confidence']:.0%}")
    else:
        lines.append(f"  ** FORECAST UNVERIFIED - numbers not shown **")

    lines.append(f"\n--- DECISION GATES ({memo.gates_passed}/{memo.gates_total}) ---")
    for gate in memo.gates:
        status = "PASS" if gate.passed else "FAIL"
        lines.append(f"  [{status}] {gate.gate_name}: {gate.reason}")

    lines.append(f"\n--- DECISION ---")
    lines.append(f"  Status: {memo.decision}")
    lines.append(f"  Confidence: {memo.decision_confidence:.0%}")
    ps = memo.position_sizing
    lines.append(f"  Position Size: {ps['recommended_pct']:.1f}% (max {ps['max_pct']:.0f}%)")

    lines.append(f"\n--- RISKS ---")
    for risk in memo.risks:
        lines.append(f"  - {risk}")

    lines.append(f"\n--- COUNTER-THESIS ---")
    lines.append(f"  {memo.counter_thesis}")

    lines.append(f"\n--- INVALIDATION CRITERIA ---")
    for inv in memo.invalidation_criteria:
        lines.append(f"  - {inv}")

    lines.append(f"\n{'='*60}")

    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    agent = TradePlanAgent()

    if len(sys.argv) > 1:
        cmd = sys.argv[1]

        if cmd == "generate":
            # Example: python -m fgip.agents.trade_plan_agent generate "chips-thesis" INTC BULLISH
            thesis_id = sys.argv[2] if len(sys.argv) > 2 else "test-thesis"
            symbol = sys.argv[3] if len(sys.argv) > 3 else None
            direction = sys.argv[4] if len(sys.argv) > 4 else "BULLISH"

            memo = agent.generate_memo(
                thesis_id=thesis_id,
                symbol=symbol,
                thesis_direction=direction,
                time_horizon_days=90
            )

            print(format_memo(memo))

        elif cmd == "recent":
            memos = agent.get_recent_memos()
            print("\n=== Recent Trade Memos ===")
            for m in memos:
                print(f"  {m['memo_id']}: {m['thesis_id']} -> {m['decision']} ({m['decision_confidence']:.0%})")

        else:
            print(f"Unknown command: {cmd}")

    else:
        print("Usage:")
        print("  python -m fgip.agents.trade_plan_agent generate [thesis_id] [symbol] [BULLISH|BEARISH]")
        print("  python -m fgip.agents.trade_plan_agent recent")
