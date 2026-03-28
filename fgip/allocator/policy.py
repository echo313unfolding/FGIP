"""
Allocation policy rules.

Deterministic rules that map (regime, constraints) -> bucket weights.
No randomness, no ML - just clear, auditable rules.
"""

from typing import Dict, List

from .constraints import SettlementConstraints, RiskTolerance
from .buckets import BUCKETS


class AllocationPolicy:
    """
    Deterministic allocation rules based on regime + constraints.

    This is the core decision engine. Given:
    - Current regime (LOW/NORMAL/STRESS/CRISIS)
    - Risk routing metric (Se)
    - User constraints

    It outputs bucket weights that sum to 1.0.
    """

    def compute_weights(
        self,
        regime: str,  # LOW | NORMAL | STRESS | CRISIS
        Se: float,    # Routing metric 0-1
        constraints: SettlementConstraints,
        m2_cpi_gap: float = 0,  # Current M2-CPI gap %
    ) -> Dict[str, float]:
        """
        Compute bucket weights given current regime and constraints.

        Args:
            regime: Current economic regime
            Se: Severity routing metric (H * C * D)
            constraints: User's settlement constraints
            m2_cpi_gap: Current inflation gap (M2 - CPI) in %

        Returns:
            {bucket_id: weight} summing to 1.0
        """
        weights = {}

        # Risk tolerance scaling factor for growth bucket
        risk_scale = {
            RiskTolerance.CONSERVATIVE: 0.7,
            RiskTolerance.MODERATE: 1.0,
            RiskTolerance.GROWTH: 1.3,
        }[constraints.risk_tolerance]

        for bucket_id, bucket in BUCKETS.items():
            base = bucket.default_weight

            # Apply regime adjustments
            if regime in bucket.regime_adjustments:
                base += bucket.regime_adjustments[regime]

            # Apply M2-CPI gap trigger for inflation hedge
            if bucket_id == "inflation_hedge" and m2_cpi_gap > 5:
                base += bucket.regime_adjustments.get("m2_gap_high", 0)

            # Scale growth bucket by risk tolerance
            if bucket_id == "growth":
                base *= risk_scale

            # Scale adjustments by Se for smoother transitions
            # (Higher Se = more severe, so adjustments are more pronounced)
            if regime in ("STRESS", "CRISIS") and Se > 0:
                adjustment = bucket.regime_adjustments.get(regime, 0)
                base = bucket.default_weight + (adjustment * min(Se * 1.5, 1.0))
                if bucket_id == "growth":
                    base *= risk_scale

            # Clamp to min/max
            base = max(bucket.min_weight, min(bucket.max_weight, base))
            weights[bucket_id] = base

        # Normalize to sum to 1.0
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}

        return weights

    def get_triggers(self, current_regime: str) -> List[dict]:
        """
        Return regime-conditional rebalance triggers.

        These are the conditions that would cause us to recommend
        a different allocation.
        """
        triggers = []

        # Escalation triggers
        if current_regime in ("LOW", "NORMAL"):
            triggers.append({
                "condition": "regime == STRESS",
                "action": "reduce_growth_by_10pct",
                "rationale": "Elevated risk detected; reduce equity exposure"
            })

        if current_regime != "CRISIS":
            triggers.append({
                "condition": "regime == CRISIS",
                "action": "activate_defensive_mode",
                "rationale": "Crisis detected; freeze discretionary, protect principal"
            })

        # De-escalation triggers
        if current_regime in ("STRESS", "CRISIS"):
            triggers.append({
                "condition": "regime returns to NORMAL for 3+ months",
                "action": "restore_baseline_allocation",
                "rationale": "Risk environment normalized; can restore growth exposure"
            })

        # Inflation triggers
        triggers.append({
            "condition": "M2_CPI_gap > 5% sustained 3mo",
            "action": "increase_TIPS_allocation",
            "rationale": "Hidden inflation eroding purchasing power"
        })

        triggers.append({
            "condition": "M2_CPI_gap < 2% sustained 3mo",
            "action": "reduce_TIPS_allocation",
            "rationale": "Inflation pressure normalized; can reduce TIPS weight"
        })

        return triggers

    def validate_allocation(
        self,
        weights: Dict[str, float],
        constraints: SettlementConstraints,
    ) -> List[str]:
        """
        Validate allocation against constraints.

        Returns list of violations (empty if valid).
        """
        violations = []

        # Check bucket count
        active_buckets = [k for k, v in weights.items() if v > 0]
        if len(active_buckets) < constraints.min_diversification_buckets:
            violations.append(
                f"Only {len(active_buckets)} buckets active, "
                f"minimum is {constraints.min_diversification_buckets}"
            )

        # Check max single position
        for bucket_id, weight in weights.items():
            if weight > constraints.max_single_position_pct:
                violations.append(
                    f"Bucket {bucket_id} at {weight:.1%} exceeds "
                    f"max position {constraints.max_single_position_pct:.1%}"
                )

        # Check expense ratios
        for bucket_id, weight in weights.items():
            if weight > 0:
                bucket = BUCKETS[bucket_id]
                if bucket.expense_ratio_cap_bps > constraints.max_expense_ratio_bps:
                    violations.append(
                        f"Bucket {bucket_id} ER cap ({bucket.expense_ratio_cap_bps}bps) "
                        f"exceeds constraint ({constraints.max_expense_ratio_bps}bps)"
                    )

        return violations
