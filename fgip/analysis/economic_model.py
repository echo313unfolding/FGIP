"""FGIP Economic Model - Dynamic variable tracking and scenario modeling.

Tracks economic variables (M2, inflation, extraction rate) and models
how policy mechanisms propagate effects through the dependency graph.

Core insight: Static analysis shows 10.8% extraction. But 6.3% of that
is M2-based inflation CAUSED BY Fed printing. If a mechanism reduces
Fed printing, M2 drops, inflation drops, extraction drops. You can't
use the disease as the argument against the cure.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from collections import deque


@dataclass
class EconomicVariable:
    """A measurable metric that changes when mechanisms fire."""
    var_id: str                    # "m2_growth_rate"
    name: str                      # "M2 Money Supply Growth Rate"
    current_value: float           # 6.3
    unit: str                      # "%"
    data_source: str               # "FRED M2SL"
    last_updated: Optional[str] = None
    notes: Optional[str] = None

    def __post_init__(self):
        if self.last_updated is None:
            self.last_updated = datetime.now(timezone.utc).isoformat()


@dataclass
class CorrectionMechanism:
    """How a policy reduces the problem."""
    mechanism_id: str              # "genius-act-reduces-fed-printing"
    policy_node_id: str            # "genius-act-2025"
    target_variable: str           # "fed_treasury_purchases"
    effect_type: str               # "REDUCES" | "BLOCKS" | "REPLACES"
    expected_delta: float          # -25 (reduce by 25%)
    confidence: float              # 0.8
    narrative: str                 # Human explanation

    def to_dict(self) -> dict:
        return {
            "mechanism_id": self.mechanism_id,
            "policy_node_id": self.policy_node_id,
            "target_variable": self.target_variable,
            "effect_type": self.effect_type,
            "expected_delta": self.expected_delta,
            "confidence": self.confidence,
            "narrative": self.narrative,
        }


@dataclass
class DynamicScenario:
    """Before/after modeling of a correction mechanism."""
    scenario_id: str
    mechanism: CorrectionMechanism
    variable_chain: List[Tuple[str, float]]  # [(var_id, delta), ...]
    extraction_before: float       # 10.8%
    extraction_after: float        # 4.5%
    thesis_delta: float            # +12 points
    narrative: str

    def to_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "mechanism": self.mechanism.to_dict(),
            "variable_chain": self.variable_chain,
            "extraction_before": self.extraction_before,
            "extraction_after": self.extraction_after,
            "thesis_delta": self.thesis_delta,
            "narrative": self.narrative,
        }


@dataclass
class DynamicThesisResult:
    """Extended scoring that includes mechanism modeling."""
    static_score: float                # Current thesis_score
    dynamic_score: float               # After modeling corrections
    scenarios: List[DynamicScenario]
    confidence_delta: float            # Score change from static -> dynamic
    narrative: str

    def to_dict(self) -> dict:
        return {
            "static_score": self.static_score,
            "dynamic_score": self.dynamic_score,
            "scenarios": [s.to_dict() for s in self.scenarios],
            "confidence_delta": self.confidence_delta,
            "narrative": self.narrative,
        }


class EconomicModel:
    """Tracks economic variables and their dependencies.

    The dependency graph models how changes in one variable propagate
    to others. For example:
        Fed Treasury Purchases -> M2 Growth -> Real Inflation -> Extraction Rate

    When a correction mechanism fires (e.g., GENIUS Act reduces Fed printing),
    we propagate the effect through the graph to see how the final metrics change.
    """

    # Baseline economic variables with current values
    BASELINE_VARIABLES = {
        "fed_treasury_purchases": EconomicVariable(
            var_id="fed_treasury_purchases",
            name="Fed Treasury Purchases (baseline=100)",
            current_value=100.0,
            unit="%",
            data_source="FRED",
            notes="Baseline 100% = current Fed QE level",
        ),
        "m2_growth_rate": EconomicVariable(
            var_id="m2_growth_rate",
            name="M2 Money Supply Growth Rate",
            current_value=6.3,
            unit="%",
            data_source="FRED M2SL",
            notes="Year-over-year M2 growth rate",
        ),
        "cpi_official": EconomicVariable(
            var_id="cpi_official",
            name="Official CPI Inflation",
            current_value=2.7,
            unit="%",
            data_source="BLS",
            notes="Official CPI (understates real inflation due to OER)",
        ),
        "real_inflation": EconomicVariable(
            var_id="real_inflation",
            name="Real Inflation (M2-based)",
            current_value=6.3,
            unit="%",
            data_source="M2SL-derived",
            notes="M2 growth as proxy for real inflation",
        ),
        "treasury_yield_4wk": EconomicVariable(
            var_id="treasury_yield_4wk",
            name="4-Week Treasury Yield",
            current_value=4.5,
            unit="%",
            data_source="Treasury",
            notes="Yield issuers earn on reserves",
        ),
        "stablecoin_holder_yield": EconomicVariable(
            var_id="stablecoin_holder_yield",
            name="Stablecoin Holder Yield",
            current_value=0.0,
            unit="%",
            data_source="GENIUS Act Section 4(a)",
            notes="Zero yield to holders per legislation",
        ),
        "extraction_rate": EconomicVariable(
            var_id="extraction_rate",
            name="Stablecoin Extraction Rate",
            current_value=10.8,
            unit="%",
            data_source="Computed",
            notes="treasury_yield + real_inflation - holder_yield",
        ),
        "issuer_spread": EconomicVariable(
            var_id="issuer_spread",
            name="Stablecoin Issuer Spread",
            current_value=4.5,
            unit="%",
            data_source="Treasury yield",
            notes="Treasury yield captured by issuer",
        ),
    }

    # Dependency graph: (source_var, target_var) -> correlation_coefficient
    # Positive correlation means they move together
    DEPENDENCY_GRAPH = {
        # Fed printing -> M2 growth (strong positive correlation)
        ("fed_treasury_purchases", "m2_growth_rate"): 0.85,

        # M2 growth -> real inflation (near-perfect correlation)
        ("m2_growth_rate", "real_inflation"): 0.95,

        # Real inflation feeds into extraction rate
        ("real_inflation", "extraction_rate"): 1.0,

        # Treasury yield feeds into extraction rate (if it changes)
        ("treasury_yield_4wk", "extraction_rate"): 1.0,
        ("treasury_yield_4wk", "issuer_spread"): 1.0,
    }

    def __init__(self):
        # Copy baseline variables to allow scenario modifications
        self.variables: Dict[str, EconomicVariable] = {}
        for var_id, var in self.BASELINE_VARIABLES.items():
            self.variables[var_id] = EconomicVariable(
                var_id=var.var_id,
                name=var.name,
                current_value=var.current_value,
                unit=var.unit,
                data_source=var.data_source,
                last_updated=var.last_updated,
                notes=var.notes,
            )

    def get_current_values(self) -> Dict[str, float]:
        """Get current value of all variables."""
        return {var_id: var.current_value for var_id, var in self.variables.items()}

    def get_variable(self, var_id: str) -> Optional[EconomicVariable]:
        """Get a specific variable."""
        return self.variables.get(var_id)

    def propagate_effect(self, start_var: str, delta: float) -> Dict[str, float]:
        """Propagate a change through the dependency graph using BFS.

        Args:
            start_var: Variable that changes first (e.g., fed_treasury_purchases)
            delta: Absolute change in that variable (e.g., -25 for 25% reduction)

        Returns:
            Dict mapping var_id -> delta for all affected variables
        """
        deltas: Dict[str, float] = {start_var: delta}
        visited = {start_var}
        queue = deque([start_var])

        while queue:
            current = queue.popleft()
            current_delta = deltas[current]

            # Find all variables that depend on current
            for (src, tgt), correlation in self.DEPENDENCY_GRAPH.items():
                if src == current and tgt not in visited:
                    # Propagate delta with correlation scaling
                    # If Fed purchases drop 25% (delta=-25), M2 drops 25*0.85=21.25%
                    # But we need to be careful about units...
                    # For percentage-based metrics, we apply proportionally

                    # Get current value of source
                    src_current = self.variables[src].current_value

                    if src_current != 0:
                        # Proportional change
                        pct_change = current_delta / src_current
                        tgt_delta = pct_change * self.variables[tgt].current_value * correlation
                    else:
                        tgt_delta = current_delta * correlation

                    deltas[tgt] = tgt_delta
                    visited.add(tgt)
                    queue.append(tgt)

        return deltas

    def compute_extraction_rate(self, variables: Optional[Dict[str, float]] = None) -> float:
        """Compute extraction rate from component variables.

        Extraction = Treasury Yield + Real Inflation - Holder Yield
        """
        if variables is None:
            variables = self.get_current_values()

        treasury_yield = variables.get("treasury_yield_4wk", 4.5)
        real_inflation = variables.get("real_inflation", 6.3)
        holder_yield = variables.get("stablecoin_holder_yield", 0.0)

        return treasury_yield + real_inflation - holder_yield

    def model_scenario(self, mechanism: CorrectionMechanism) -> DynamicScenario:
        """Model what happens if a correction mechanism fires.

        Args:
            mechanism: The correction mechanism to model

        Returns:
            DynamicScenario with before/after extraction rates
        """
        # Get current values
        current_vars = self.get_current_values()
        extraction_before = self.compute_extraction_rate(current_vars)

        # Get variable deltas from propagation
        deltas = self.propagate_effect(
            mechanism.target_variable,
            mechanism.expected_delta
        )

        # Apply deltas to get projected values
        projected_vars = {}
        for var_id, value in current_vars.items():
            projected_vars[var_id] = value + deltas.get(var_id, 0)

        # Recompute extraction rate with projected values
        extraction_after = self.compute_extraction_rate(projected_vars)

        # Compute thesis delta (how much confidence increases if correction works)
        # More extraction reduction = more confidence in correction mechanism
        if extraction_before > 0:
            reduction_pct = (extraction_before - extraction_after) / extraction_before
            thesis_delta = min(15, reduction_pct * 30) * mechanism.confidence
        else:
            thesis_delta = 0

        # Generate narrative
        narrative = self._generate_scenario_narrative(
            mechanism, current_vars, projected_vars, deltas,
            extraction_before, extraction_after
        )

        return DynamicScenario(
            scenario_id=f"scenario-{mechanism.mechanism_id}",
            mechanism=mechanism,
            variable_chain=list(deltas.items()),
            extraction_before=extraction_before,
            extraction_after=extraction_after,
            thesis_delta=thesis_delta,
            narrative=narrative,
        )

    def _generate_scenario_narrative(
        self,
        mechanism: CorrectionMechanism,
        current_vars: Dict[str, float],
        projected_vars: Dict[str, float],
        deltas: Dict[str, float],
        extraction_before: float,
        extraction_after: float,
    ) -> str:
        """Generate human-readable narrative for a scenario."""
        lines = [
            f"Mechanism: {mechanism.narrative}",
            f"",
            f"Chain of Effects:",
        ]

        for var_id, delta in deltas.items():
            if var_id in self.variables:
                var = self.variables[var_id]
                before = current_vars.get(var_id, var.current_value)
                after = projected_vars.get(var_id, before)
                direction = "drops" if delta < 0 else "rises"
                lines.append(f"  {var.name}: {before:.1f}% -> {after:.1f}% ({direction} {abs(delta):.1f}%)")

        lines.extend([
            f"",
            f"Result:",
            f"  Static Extraction: {extraction_before:.1f}%",
            f"  Dynamic Extraction: {extraction_after:.1f}%",
            f"  Reduction: {extraction_before - extraction_after:.1f}%",
        ])

        if extraction_after < extraction_before:
            lines.append(f"")
            lines.append(f"Key insight: The {extraction_before - extraction_after:.1f}% reduction")
            lines.append(f"demonstrates that the mechanism addresses the root cause,")
            lines.append(f"not just the symptom.")

        return "\n".join(lines)


# Pre-defined correction mechanisms for known policies
KNOWN_MECHANISMS = {
    "genius-act-partial": CorrectionMechanism(
        mechanism_id="genius-act-partial",
        policy_node_id="genius-act",
        target_variable="fed_treasury_purchases",
        effect_type="REDUCES",
        expected_delta=-25.0,  # 25% reduction in Fed purchases
        confidence=0.7,
        narrative="GENIUS Act partially replaces Fed Treasury purchases with stablecoin issuer purchases",
    ),
    "genius-act-full": CorrectionMechanism(
        mechanism_id="genius-act-full",
        policy_node_id="genius-act",
        target_variable="fed_treasury_purchases",
        effect_type="REPLACES",
        expected_delta=-80.0,  # 80% reduction (at scale)
        confidence=0.5,
        narrative="GENIUS Act at scale ($2T+) significantly reduces Fed Treasury purchase needs",
    ),
    "chips-act-reshoring": CorrectionMechanism(
        mechanism_id="chips-act-reshoring",
        policy_node_id="chips-act",
        target_variable="fed_treasury_purchases",
        effect_type="REDUCES",
        expected_delta=-5.0,  # Small direct effect
        confidence=0.8,
        narrative="CHIPS Act reduces trade deficit pressure, marginally reducing Fed intervention needs",
    ),
}


def get_baseline_model() -> EconomicModel:
    """Get a fresh economic model with baseline values."""
    return EconomicModel()


def model_genius_act_scenarios() -> List[DynamicScenario]:
    """Model GENIUS Act scenarios (partial and full implementation)."""
    model = EconomicModel()

    scenarios = []
    for mech_id in ["genius-act-partial", "genius-act-full"]:
        mechanism = KNOWN_MECHANISMS[mech_id]
        scenario = model.model_scenario(mechanism)
        scenarios.append(scenario)

    return scenarios


if __name__ == "__main__":
    # Demo: Show GENIUS Act scenario modeling
    print("=" * 60)
    print("  FGIP ECONOMIC MODEL - GENIUS ACT SCENARIO")
    print("=" * 60)
    print()

    model = EconomicModel()

    print("BASELINE VARIABLES:")
    for var_id, var in model.variables.items():
        print(f"  {var.name}: {var.current_value}{var.unit}")
    print()

    print("STATIC EXTRACTION RATE:")
    static_extraction = model.compute_extraction_rate()
    print(f"  Treasury Yield (4.5%) + Real Inflation (6.3%) - Holder Yield (0%)")
    print(f"  = {static_extraction:.1f}%")
    print()

    print("-" * 60)
    print()

    for mech_id in ["genius-act-partial", "genius-act-full"]:
        mechanism = KNOWN_MECHANISMS[mech_id]
        scenario = model.model_scenario(mechanism)

        print(f"SCENARIO: {mech_id.upper()}")
        print(scenario.narrative)
        print()
        print(f"Thesis Confidence Delta: +{scenario.thesis_delta:.1f} points")
        print()
        print("-" * 60)
        print()

    print("KEY INSIGHT:")
    print("  The 6.3% 'real inflation' component of the 10.8% extraction")
    print("  IS CAUSED BY the Fed printing that GENIUS Act replaces.")
    print("  You can't use the disease as the argument against the cure.")
