"""FGIP DecisionAgent - Policy-Bounded Position Sizing.

Converts forecasts to position sizes with risk guardrails:
- Kelly criterion for optimal sizing
- Policy caps (max position, max sector, drawdown triggers)
- Triangulation requirements (min source diversity)
- Calibration thresholds (min Brier score quality)
- Fatal counter-thesis veto

Output: PositionRecommendation with action, size, and hedge recommendations.

Usage:
    from fgip.agents.decision_agent import DecisionAgent
    from fgip.db import FGIPDatabase

    db = FGIPDatabase("fgip.db")
    agent = DecisionAgent(db)
    rec = agent.evaluate_thesis("uranium-thesis")
    print(f"Action: {rec.action}, Size: {rec.position_size}")
"""

import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import uuid

from .base import FGIPAgent, Artifact, StructuredFact, ProposedClaim, ProposedEdge


@dataclass
class Policy:
    """Risk policy guardrails."""
    max_single_position: float = 0.20  # 20% max per thesis
    max_sector_exposure: float = 0.40  # 40% max per sector
    max_drawdown_trigger: float = 0.15  # Exit if 15% drawdown
    min_triangulation_sources: int = 3  # Require 3+ source types
    min_calibration_score: float = 0.35  # Brier < 0.35 required
    min_integrity_score: float = 0.50  # Avg integrity >= 0.50
    fatal_counter_thesis_veto: bool = True  # Auto-exit on fatal counter
    kelly_fraction: float = 0.25  # Quarter Kelly by default

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_single_position": self.max_single_position,
            "max_sector_exposure": self.max_sector_exposure,
            "max_drawdown_trigger": self.max_drawdown_trigger,
            "min_triangulation_sources": self.min_triangulation_sources,
            "min_calibration_score": self.min_calibration_score,
            "min_integrity_score": self.min_integrity_score,
            "fatal_counter_thesis_veto": self.fatal_counter_thesis_veto,
            "kelly_fraction": self.kelly_fraction,
        }


@dataclass
class PositionRecommendation:
    """Position sizing recommendation with full reasoning."""
    id: str
    thesis_id: str
    action: str  # BUY, HOLD, REDUCE, EXIT, AVOID
    position_size: float  # 0.0 to max_single_position
    confidence: float
    kelly_raw: float  # Raw Kelly fraction before caps
    kelly_adjusted: float  # After fractional Kelly
    policy_caps_applied: List[str]  # Which policy limits kicked in
    reasoning: List[str]
    risk_factors: List[str]
    hedge_recommendations: List[str]
    review_triggers: List[str]  # What would change recommendation
    triangulation_met: bool
    calibration_adequate: bool
    integrity_adequate: bool
    counter_thesis_clear: bool
    expected_value: float
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    expires_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "thesis_id": self.thesis_id,
            "action": self.action,
            "position_size": self.position_size,
            "confidence": self.confidence,
            "kelly_raw": self.kelly_raw,
            "kelly_adjusted": self.kelly_adjusted,
            "policy_caps_applied": self.policy_caps_applied,
            "reasoning": self.reasoning,
            "risk_factors": self.risk_factors,
            "hedge_recommendations": self.hedge_recommendations,
            "review_triggers": self.review_triggers,
            "triangulation_met": self.triangulation_met,
            "calibration_adequate": self.calibration_adequate,
            "integrity_adequate": self.integrity_adequate,
            "counter_thesis_clear": self.counter_thesis_clear,
            "expected_value": self.expected_value,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }


class DecisionAgent(FGIPAgent):
    """Policy-bounded position sizing agent.

    Converts scenario trees and conviction scores to position recommendations
    with full audit trail of reasoning.
    """

    def __init__(self, db, name: str = "decision-agent", policy: Optional[Policy] = None):
        super().__init__(
            db, name,
            "Policy-bounded position sizing with risk guardrails"
        )
        self.policy = policy or Policy()

    def collect(self) -> List[Artifact]:
        """Not used - DecisionAgent operates on forecasts, not artifacts."""
        return []

    def extract(self, artifacts: List[Artifact]) -> List[StructuredFact]:
        """Not used - DecisionAgent operates on forecasts."""
        return []

    def propose(
        self, facts: List[StructuredFact]
    ) -> Tuple[List[ProposedClaim], List[ProposedEdge]]:
        """Not used - DecisionAgent produces recommendations, not proposals."""
        return ([], [])

    def evaluate_thesis(
        self,
        thesis_id: str,
        scenario_tree: Optional[Dict] = None,
        conviction_level: int = 3,
        current_position: float = 0.0,
        sector: Optional[str] = None,
        current_sector_exposure: float = 0.0,
    ) -> PositionRecommendation:
        """Evaluate a thesis and generate position recommendation.

        Args:
            thesis_id: ID of the thesis to evaluate
            scenario_tree: Optional pre-computed scenario tree
            conviction_level: 1-5 conviction score
            current_position: Current position size (for HOLD/REDUCE decisions)
            sector: Sector for concentration limits
            current_sector_exposure: Current sector exposure

        Returns:
            PositionRecommendation with full reasoning
        """
        reasoning = []
        risk_factors = []
        policy_caps = []
        hedge_recs = []
        review_triggers = []

        # 1. Check triangulation
        triangulation_met, source_count, source_types = self._check_triangulation(thesis_id)
        if triangulation_met:
            reasoning.append(f"Triangulation met: {source_count} sources across {source_types} types")
        else:
            reasoning.append(f"Triangulation NOT met: only {source_count} sources, {source_types} types")
            risk_factors.append("Insufficient source diversity")

        # 2. Check calibration
        calibration_adequate, brier_score = self._check_calibration()
        if calibration_adequate:
            reasoning.append(f"Calibration adequate: Brier={brier_score:.3f}")
        else:
            reasoning.append(f"Calibration inadequate: Brier={brier_score:.3f} > {self.policy.min_calibration_score}")
            risk_factors.append("Poor historical calibration")

        # 3. Check integrity scores
        integrity_adequate, avg_integrity = self._check_integrity(thesis_id)
        if integrity_adequate:
            reasoning.append(f"Integrity adequate: avg={avg_integrity:.2f}")
        else:
            reasoning.append(f"Integrity inadequate: avg={avg_integrity:.2f}")
            risk_factors.append("Low source integrity scores")

        # 4. Check for fatal counter-thesis
        counter_thesis_clear, counter_details = self._check_counter_thesis(thesis_id)
        if counter_thesis_clear:
            reasoning.append("No fatal counter-thesis detected")
        else:
            reasoning.append(f"FATAL counter-thesis: {counter_details}")
            risk_factors.append("Fatal counter-evidence exists")

        # 5. Calculate expected value from scenario tree
        if scenario_tree:
            expected_value = self._calculate_ev(scenario_tree)
        else:
            expected_value = self._estimate_ev(thesis_id, conviction_level)
        reasoning.append(f"Expected value: {expected_value:.1%}")

        # 6. Calculate Kelly criterion
        win_prob = 0.5 + (conviction_level - 3) * 0.1
        if expected_value > 0:
            # Simplified Kelly for positive EV
            kelly_raw = expected_value / (abs(expected_value) + 0.15)  # Assume 15% loss if wrong
        else:
            kelly_raw = 0.0

        kelly_adjusted = kelly_raw * self.policy.kelly_fraction
        reasoning.append(f"Kelly: raw={kelly_raw:.2%}, adjusted={kelly_adjusted:.2%}")

        # 7. Apply policy caps
        position_size = kelly_adjusted

        # Cap at max single position
        if position_size > self.policy.max_single_position:
            position_size = self.policy.max_single_position
            policy_caps.append("max_single_position")

        # Cap at sector limit
        remaining_sector = self.policy.max_sector_exposure - current_sector_exposure
        if position_size > remaining_sector:
            position_size = max(0, remaining_sector)
            policy_caps.append("max_sector_exposure")

        # Triangulation veto
        if not triangulation_met:
            position_size = min(position_size, 0.05)  # Max 5% without triangulation
            policy_caps.append("triangulation_required")

        # Calibration veto
        if not calibration_adequate:
            position_size *= 0.5  # Half position with poor calibration
            policy_caps.append("calibration_penalty")

        # Integrity veto
        if not integrity_adequate:
            position_size *= 0.7
            policy_caps.append("integrity_penalty")

        # Fatal counter-thesis veto
        if not counter_thesis_clear and self.policy.fatal_counter_thesis_veto:
            position_size = 0.0
            policy_caps.append("fatal_counter_veto")

        # 8. Determine action
        if position_size == 0:
            if current_position > 0:
                action = "EXIT"
            else:
                action = "AVOID"
        elif current_position == 0:
            action = "BUY"
        elif position_size > current_position * 1.1:
            action = "BUY"  # Add to position
        elif position_size < current_position * 0.9:
            action = "REDUCE"
        else:
            action = "HOLD"

        # 9. Generate hedge recommendations
        if position_size > 0.10:
            hedge_recs.append("Consider protective puts for downside protection")
        if conviction_level < 4:
            hedge_recs.append("Consider smaller position with defined risk")
        if not triangulation_met:
            hedge_recs.append("Wait for additional source confirmation before adding")

        # 10. Generate review triggers
        review_triggers.append(f"Re-evaluate if conviction changes from {conviction_level}")
        review_triggers.append("Re-evaluate on new Tier 0 evidence")
        if scenario_tree:
            review_triggers.append("Re-evaluate if catalyst timeline shifts")
        if current_position > 0:
            review_triggers.append(f"Exit if drawdown exceeds {self.policy.max_drawdown_trigger:.0%}")

        # 11. Calculate confidence
        confidence_factors = [
            0.3 if triangulation_met else 0.0,
            0.2 if calibration_adequate else 0.0,
            0.2 if integrity_adequate else 0.0,
            0.2 if counter_thesis_clear else 0.0,
            0.1 * (conviction_level / 5),
        ]
        confidence = sum(confidence_factors)

        rec_id = f"rec-{thesis_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        recommendation = PositionRecommendation(
            id=rec_id,
            thesis_id=thesis_id,
            action=action,
            position_size=round(position_size, 4),
            confidence=round(confidence, 2),
            kelly_raw=round(kelly_raw, 4),
            kelly_adjusted=round(kelly_adjusted, 4),
            policy_caps_applied=policy_caps,
            reasoning=reasoning,
            risk_factors=risk_factors,
            hedge_recommendations=hedge_recs,
            review_triggers=review_triggers,
            triangulation_met=triangulation_met,
            calibration_adequate=calibration_adequate,
            integrity_adequate=integrity_adequate,
            counter_thesis_clear=counter_thesis_clear,
            expected_value=round(expected_value, 4),
        )

        # Save to database
        self._save_recommendation(recommendation)

        return recommendation

    def _check_triangulation(self, thesis_id: str) -> Tuple[bool, int, int]:
        """Check if thesis meets triangulation requirements.

        Returns: (met, source_count, source_types)
        """
        conn = self.db.connect()

        # Count sources linked to claims related to this thesis
        # This is a simplified check - in practice would check edge sources
        rows = conn.execute(
            """SELECT DISTINCT s.tier, s.domain
               FROM sources s
               JOIN claim_sources cs ON s.source_id = cs.source_id
               JOIN claims c ON cs.claim_id = c.claim_id
               WHERE c.topic LIKE ?""",
            (f"%{thesis_id}%",)
        ).fetchall()

        source_count = len(rows)
        tiers = set(row[0] for row in rows if row[0] is not None)
        source_types = len(tiers)

        met = source_count >= self.policy.min_triangulation_sources

        return met, source_count, source_types

    def _check_calibration(self) -> Tuple[bool, float]:
        """Check if calibration is adequate.

        Returns: (adequate, brier_score)
        """
        conn = self.db.connect()

        # Check calibration_metrics table
        try:
            row = conn.execute(
                """SELECT brier_score FROM calibration_metrics
                   WHERE agent_name = 'forecast-agent' AND time_window = 'all_time'
                   ORDER BY computed_at DESC LIMIT 1"""
            ).fetchone()

            if row and row[0] is not None:
                brier = row[0]
                adequate = brier < self.policy.min_calibration_score
                return adequate, brier
        except:
            pass

        # Default: assume adequate with moderate score
        return True, 0.25

    def _check_integrity(self, thesis_id: str) -> Tuple[bool, float]:
        """Check if source integrity is adequate.

        Returns: (adequate, avg_integrity)
        """
        conn = self.db.connect()

        try:
            row = conn.execute(
                """SELECT AVG(final_score) FROM integrity_scores
                   WHERE artifact_id IN (
                       SELECT artifact_id FROM artifact_queue
                       WHERE url LIKE ?
                   )""",
                (f"%{thesis_id}%",)
            ).fetchone()

            if row and row[0] is not None:
                avg = row[0]
                adequate = avg >= self.policy.min_integrity_score
                return adequate, avg
        except:
            pass

        # Default: assume adequate
        return True, 0.70

    def _check_counter_thesis(self, thesis_id: str) -> Tuple[bool, str]:
        """Check for fatal counter-thesis evidence.

        Returns: (clear, details)
        """
        conn = self.db.connect()

        try:
            rows = conn.execute(
                """SELECT counter_claim, severity FROM counter_evidence
                   WHERE severity = 'fatal'
                   ORDER BY detected_at DESC LIMIT 5"""
            ).fetchall()

            if rows:
                details = "; ".join(row[0][:50] for row in rows)
                return False, details
        except:
            pass

        return True, ""

    def _calculate_ev(self, scenario_tree: Dict) -> float:
        """Calculate expected value from scenario tree."""
        ev = 0.0
        for scenario_key in ["base_case", "bull_case", "bear_case", "tail_risk"]:
            scenario = scenario_tree.get(scenario_key, {})
            prob = scenario.get("probability", 0)
            ret = scenario.get("expected_return", 0)
            ev += prob * ret
        return ev

    def _estimate_ev(self, thesis_id: str, conviction_level: int) -> float:
        """Estimate expected value from conviction level."""
        # Simple mapping from conviction to expected return
        conviction_to_ev = {
            1: -0.05,  # Avoid
            2: 0.02,   # Neutral
            3: 0.08,   # Slight positive
            4: 0.15,   # Positive
            5: 0.25,   # Strong positive
        }
        return conviction_to_ev.get(conviction_level, 0.05)

    def _save_recommendation(self, rec: PositionRecommendation):
        """Save recommendation to database."""
        conn = self.db.connect()

        try:
            conn.execute(
                """INSERT INTO decision_recommendations
                   (id, thesis_id, action, position_size, confidence, kelly_fraction,
                    policy_caps_applied, reasoning, risk_factors, hedge_recommendations,
                    review_triggers, created_at, agent_name)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rec.id,
                    rec.thesis_id,
                    rec.action,
                    rec.position_size,
                    rec.confidence,
                    rec.kelly_adjusted,
                    json.dumps(rec.policy_caps_applied),
                    json.dumps(rec.reasoning),
                    json.dumps(rec.risk_factors),
                    json.dumps(rec.hedge_recommendations),
                    json.dumps(rec.review_triggers),
                    rec.created_at,
                    self.agent_name,
                )
            )
            conn.commit()
        except Exception as e:
            # Table might not exist yet
            pass

    def run(self) -> Dict[str, Any]:
        """Run decision agent on pending theses.

        This agent is typically called on-demand rather than scheduled.
        """
        return {
            "agent": self.name,
            "status": "Decision agent runs on-demand via evaluate_thesis()",
            "recommendations_generated": 0,
        }

    def get_recent_recommendations(self, limit: int = 10) -> List[Dict]:
        """Get recent recommendations."""
        conn = self.db.connect()

        try:
            rows = conn.execute(
                """SELECT * FROM decision_recommendations
                   ORDER BY created_at DESC LIMIT ?""",
                (limit,)
            ).fetchall()

            return [dict(row) for row in rows]
        except:
            return []


def kelly_criterion(
    win_probability: float,
    win_return: float,
    loss_return: float = -1.0,
    fraction: float = 0.25
) -> float:
    """Compute Kelly criterion for position sizing.

    The Kelly criterion determines optimal bet size to maximize
    long-term geometric growth rate.

    Args:
        win_probability: Probability of winning (0 to 1)
        win_return: Return if win (e.g., 0.5 for 50% gain)
        loss_return: Return if loss (e.g., -1.0 for 100% loss)
        fraction: Fraction of full Kelly to use (0.25 = quarter Kelly)

    Returns:
        Optimal position size as fraction of bankroll (0 to 1)
    """
    if win_probability <= 0 or win_probability >= 1:
        return 0.0

    if win_return <= 0:
        return 0.0

    # Kelly formula: (p * b - q) / b
    # where p = win_probability, q = 1-p, b = win_return / |loss_return|
    p = win_probability
    q = 1 - p
    b = win_return / abs(loss_return) if loss_return != 0 else win_return

    kelly_full = (p * b - q) / b if b > 0 else 0.0

    # Apply fractional Kelly and clamp to [0, 1]
    kelly_fractional = kelly_full * fraction
    return max(0.0, min(1.0, kelly_fractional))
