"""
FGIP Purchasing Power Protection Module
========================================
Personal financial exposure analyzer that connects the macro thesis
to individual purchasing power protection.

Key Insight: The graph proves 3.6% hidden extraction (M2 6.3% - CPI 2.7%).
This module makes that finding personally protective by showing:
- Real savings yield (after M2 inflation)
- Real debt cost (inflation-adjusted)
- Financial runway under different scenarios

No PII is stored. All inputs are numbers, all outputs are calculations.
"""

import json
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Dict, Optional, Any, List

# Default economic parameters (validated via FGIP 25-year backtest)
DEFAULT_M2_INFLATION = 0.063      # 6.3% - M2 money supply growth
DEFAULT_CPI_OFFICIAL = 0.027     # 2.7% - BLS official CPI
DEFAULT_TREASURY_YIELD = 0.045   # 4.5% - 4-week Treasury yield
DEFAULT_SAVINGS_YIELD = 0.045    # 4.5% - typical HYSA rate


# ─── Data Structures ───────────────────────────────────────────────────────

@dataclass
class PersonalScenario:
    """User's financial inputs (no sensitive data - just numbers)."""
    monthly_expenses: float          # Monthly burn rate ($)
    current_savings: float           # Liquid assets ($)
    savings_yield: float = 0.045     # APY on savings (decimal, e.g., 0.045)
    debt_balance: float = 0.0        # Total debt ($)
    debt_apr: float = 0.0            # Weighted average APR (decimal)
    income_monthly: float = 0.0      # Optional: monthly income ($)


@dataclass
class RealRateResult:
    """Real (inflation-adjusted) rates."""
    nominal_savings_yield: float     # What bank says (4.5%)
    real_savings_yield: float        # After M2 inflation (-1.8%)
    nominal_debt_rate: float         # What card says (22%)
    real_debt_rate: float            # Inflation-adjusted (15.7%)
    inflation_proxy: float           # M2-tracked (6.3%)
    cpi_official: float              # BLS (2.7%)
    hidden_extraction: float         # The gap (3.6%)

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)


@dataclass
class RunwayResult:
    """Financial runway calculations."""
    nominal_months: float            # Savings / expenses
    inflation_adjusted_months: float # Accounting for purchasing power loss
    annual_savings_erosion: float    # $ lost to real negative yield
    real_rate_leak_per_year: float   # $ purchasing power lost (savings * (inflation - yield))
    debt_real_cost: float            # True cost of debt after inflation (annual $)
    net_monthly_burn: float          # expenses - income (if provided)
    scenario_shocks: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AllocationAssumption:
    """User-provided return assumption for an asset category."""
    name: str                        # e.g., "Gold proxy", "Reshoring ETF"
    expected_nominal_return: float   # decimal (0.08 for 8%)
    volatility_note: str = ""        # e.g., "High", "Moderate"
    liquidity_note: str = ""         # e.g., "T+1", "Monthly"
    node_id: str = ""                # Graph node_id for cross-reference
    expected_return_is_assumption: bool = True  # Flag: this is NOT evidence

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OffsetResult:
    """Required returns to offset purchasing power leak."""
    leak_per_year: float             # $ amount leaking
    savings_base: float              # Current savings
    required_real_return: float      # leak / savings (decimal)
    required_nominal_return: float   # inflation + required_real (decimal)
    scenarios: Dict[str, float]      # scenario_name -> required_nominal
    portfolio_offset_estimates: Dict[str, float]  # assumption_name -> $/year offset
    warning: str = "Expected returns are assumptions, not evidence. This computes requirements, not guarantees."

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PurchasingPowerReport:
    """Complete personal exposure assessment."""
    timestamp: str
    scenario: PersonalScenario
    real_rates: RealRateResult
    runway: RunwayResult
    offset: Optional[OffsetResult]   # Required returns to offset leak
    thesis_connection: str           # How this connects to FGIP thesis
    actionable_insight: str          # Plain-English takeaway

    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp,
            'scenario': asdict(self.scenario),
            'real_rates': self.real_rates.to_dict(),
            'runway': self.runway.to_dict(),
            'offset': self.offset.to_dict() if self.offset else None,
            'thesis_connection': self.thesis_connection,
            'actionable_insight': self.actionable_insight,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


# ─── Core Functions ────────────────────────────────────────────────────────

def compute_real_rates(
    savings_yield: float,
    debt_apr: float = 0.0,
    inflation_proxy: float = DEFAULT_M2_INFLATION,
    cpi_official: float = DEFAULT_CPI_OFFICIAL
) -> RealRateResult:
    """
    Compute inflation-adjusted rates.

    Real Savings = Nominal Yield - Inflation (M2)
    Real Debt = Nominal APR - Inflation (still painful due to cashflow timing)
    Hidden Extraction = M2 Inflation - CPI (the gap governments don't tell you)

    Args:
        savings_yield: Bank APY as decimal (e.g., 0.045 for 4.5%)
        debt_apr: Credit card/loan APR as decimal (e.g., 0.22 for 22%)
        inflation_proxy: M2-tracked real inflation (default 6.3%)
        cpi_official: BLS official CPI (default 2.7%)

    Returns:
        RealRateResult with all inflation-adjusted metrics
    """
    real_savings = savings_yield - inflation_proxy
    real_debt = debt_apr - inflation_proxy  # Note: still positive and painful
    hidden_extraction = inflation_proxy - cpi_official

    return RealRateResult(
        nominal_savings_yield=savings_yield,
        real_savings_yield=real_savings,
        nominal_debt_rate=debt_apr,
        real_debt_rate=real_debt,
        inflation_proxy=inflation_proxy,
        cpi_official=cpi_official,
        hidden_extraction=hidden_extraction,
    )


def compute_runway(
    current_savings: float,
    monthly_expenses: float,
    savings_yield: float = DEFAULT_SAVINGS_YIELD,
    inflation_proxy: float = DEFAULT_M2_INFLATION,
    income_monthly: float = 0.0,
    debt_balance: float = 0.0,
    debt_apr: float = 0.0,
) -> RunwayResult:
    """
    Calculate financial runway with inflation adjustment.

    Nominal runway: savings / monthly_burn
    Inflation-adjusted: accounts for purchasing power decay over time

    The inflation adjustment uses a simple model:
    - Each month, your savings lose (inflation_proxy / 12) of purchasing power
    - This compounds over the runway period

    Args:
        current_savings: Liquid assets in USD
        monthly_expenses: Monthly burn rate in USD
        savings_yield: APY on savings as decimal
        inflation_proxy: M2-tracked real inflation
        income_monthly: Monthly income (reduces burn rate)
        debt_balance: Total debt balance
        debt_apr: Weighted average debt APR

    Returns:
        RunwayResult with nominal and adjusted runway metrics
    """
    # Net monthly burn (expenses minus income)
    net_burn = max(0, monthly_expenses - income_monthly)

    # Nominal runway (simple division)
    nominal_months = current_savings / net_burn if net_burn > 0 else float('inf')

    # Real yield (what you actually earn after inflation)
    real_yield = savings_yield - inflation_proxy

    # Annual erosion from negative real yield
    # If real_yield < 0, you lose this much per year
    if real_yield < 0:
        annual_erosion = abs(real_yield) * current_savings
    else:
        annual_erosion = 0.0

    # Real-rate leak: explicit dollar amount of purchasing power lost per year
    # This is savings * (inflation - yield), always shows the leak even if yield > 0
    # For 50k savings at 4.5% yield vs 6.3% inflation: 50000 * (0.063 - 0.045) = $900/year
    real_rate_leak = current_savings * max(0, inflation_proxy - savings_yield)

    # Debt real cost (annual)
    # Even with inflation, you still owe the principal + interest
    # Real cost = nominal APR - inflation, applied to balance
    real_debt_rate = debt_apr - inflation_proxy
    debt_real_cost = max(0, real_debt_rate * debt_balance) if debt_balance > 0 else 0.0

    # Inflation-adjusted runway
    # Use a decay model: each month, purchasing power drops by (inflation / 12)
    # This is a conservative estimate
    if net_burn > 0 and nominal_months < float('inf'):
        monthly_inflation = inflation_proxy / 12
        # Approximate: total purchasing power over N months with decay
        # Integral of (1 - monthly_inflation)^n from 0 to N
        # Simplified: reduce nominal by (1 + inflation * nominal_years / 2)
        nominal_years = nominal_months / 12
        inflation_factor = 1 + (inflation_proxy * nominal_years / 2)
        inflation_adjusted_months = nominal_months / inflation_factor
    else:
        inflation_adjusted_months = nominal_months

    return RunwayResult(
        nominal_months=round(nominal_months, 1),
        inflation_adjusted_months=round(inflation_adjusted_months, 1),
        annual_savings_erosion=round(annual_erosion, 2),
        real_rate_leak_per_year=round(real_rate_leak, 2),
        debt_real_cost=round(debt_real_cost, 2),
        net_monthly_burn=round(net_burn, 2),
        scenario_shocks={},  # Filled by model_scenario_shocks
    )


def compute_offset_requirements(
    current_savings: float,
    real_rate_leak_per_year: float,
    inflation_proxy: float = DEFAULT_M2_INFLATION,
    assumptions: Optional[List[AllocationAssumption]] = None,
    shock_scenarios: Optional[Dict[str, float]] = None,
) -> OffsetResult:
    """
    Compute required returns to offset purchasing power leak.

    Args:
        current_savings: Liquid assets in USD
        real_rate_leak_per_year: Annual $ leak from real-rate gap
        inflation_proxy: M2-tracked inflation (default 6.3%)
        assumptions: Optional list of asset return assumptions
        shock_scenarios: Optional inflation scenarios to model

    Returns:
        OffsetResult with required returns and portfolio estimates
    """
    # Required real return to plug the leak
    required_real = (real_rate_leak_per_year / current_savings) if current_savings > 0 else 0.0

    # Required nominal = inflation + required real
    required_nominal = inflation_proxy + required_real

    # Scenario modeling
    if shock_scenarios is None:
        shock_scenarios = {
            "current_m2": inflation_proxy,
            "fed_normalization": 0.03,
            "crisis_10pct": 0.10,
            "genius_act": 0.045,
        }

    # Required nominal for each scenario
    scenario_required = {k: v + required_real for k, v in shock_scenarios.items()}

    # Portfolio offset estimates (if assumptions provided)
    portfolio_offsets = {}
    if assumptions:
        for a in assumptions:
            # How many $/year this assumption beats inflation by
            offset = current_savings * max(0.0, a.expected_nominal_return - inflation_proxy)
            portfolio_offsets[a.name] = round(offset, 2)

    return OffsetResult(
        leak_per_year=round(real_rate_leak_per_year, 2),
        savings_base=round(current_savings, 2),
        required_real_return=round(required_real, 4),
        required_nominal_return=round(required_nominal, 4),
        scenarios={k: round(v, 4) for k, v in scenario_required.items()},
        portfolio_offset_estimates=portfolio_offsets,
    )


def model_scenario_shocks(
    scenario: PersonalScenario,
    shock_scenarios: Optional[Dict[str, float]] = None
) -> Dict[str, float]:
    """
    Model runway under different inflation conditions.

    Default scenarios:
    - current_m2: 6.3% M2 inflation (validated baseline)
    - fed_normalization: 3% inflation (if Fed stops printing)
    - crisis_10pct: 10% inflation spike
    - genius_act: 4.5% (if stablecoin corridor replaces Fed printing)

    Args:
        scenario: PersonalScenario with financial inputs
        shock_scenarios: Optional custom scenarios {name: inflation_rate}

    Returns:
        Dict mapping scenario names to inflation-adjusted runway months
    """
    if shock_scenarios is None:
        shock_scenarios = {
            'current_m2': DEFAULT_M2_INFLATION,       # 6.3%
            'fed_normalization': 0.03,                 # 3%
            'crisis_10pct': 0.10,                      # 10%
            'genius_act': 0.045,                       # 4.5%
        }

    results = {}
    for name, inflation in shock_scenarios.items():
        runway = compute_runway(
            current_savings=scenario.current_savings,
            monthly_expenses=scenario.monthly_expenses,
            savings_yield=scenario.savings_yield,
            inflation_proxy=inflation,
            income_monthly=scenario.income_monthly,
            debt_balance=scenario.debt_balance,
            debt_apr=scenario.debt_apr,
        )
        results[name] = runway.inflation_adjusted_months

    return results


def generate_thesis_connection(real_rates: RealRateResult) -> str:
    """Generate narrative connecting personal metrics to FGIP thesis."""
    if real_rates.real_savings_yield < 0:
        return (
            f"Your savings are losing {abs(real_rates.real_savings_yield):.1%}/year in real terms "
            f"({real_rates.nominal_savings_yield:.1%} yield - {real_rates.inflation_proxy:.1%} M2 inflation). "
            f"This is the 'hidden extraction' the FGIP thesis documents: "
            f"the {real_rates.hidden_extraction:.1%} gap between M2 inflation and official CPI."
        )
    else:
        return (
            f"Your savings are growing at {real_rates.real_savings_yield:.1%}/year in real terms "
            f"({real_rates.nominal_savings_yield:.1%} yield - {real_rates.inflation_proxy:.1%} M2 inflation). "
            f"You're ahead of the {real_rates.hidden_extraction:.1%} hidden extraction rate "
            f"documented in the FGIP thesis."
        )


def generate_actionable_insight(
    scenario: PersonalScenario,
    real_rates: RealRateResult,
    runway: RunwayResult
) -> str:
    """Generate plain-English actionable advice."""
    insights = []

    # Runway insight
    if runway.inflation_adjusted_months < 6:
        insights.append(
            f"URGENT: Only {runway.inflation_adjusted_months:.0f} months of runway "
            f"after inflation adjustment."
        )
    elif runway.inflation_adjusted_months < 12:
        insights.append(
            f"CAUTION: {runway.inflation_adjusted_months:.0f} months of inflation-adjusted runway."
        )
    else:
        insights.append(
            f"Runway: {runway.inflation_adjusted_months:.0f} months (inflation-adjusted)."
        )

    # Real yield insight
    if real_rates.real_savings_yield < 0:
        erosion_monthly = runway.annual_savings_erosion / 12
        insights.append(
            f"Your savings lose ~${erosion_monthly:.0f}/month to inflation erosion."
        )

    # Debt insight
    if scenario.debt_balance > 0 and real_rates.real_debt_rate > 0:
        insights.append(
            f"Debt costs {real_rates.real_debt_rate:.1%}/year in real terms "
            f"(${runway.debt_real_cost:.0f}/year)."
        )

    # Recommendations
    recommendations = []
    if real_rates.real_savings_yield < 0:
        recommendations.append("higher-yield savings vehicles (T-bills, I-bonds)")
    if runway.net_monthly_burn > 0 and runway.inflation_adjusted_months < 12:
        recommendations.append("expense reduction")
    if scenario.debt_balance > 0 and real_rates.real_debt_rate > 0.10:
        recommendations.append(f"debt paydown (real cost {real_rates.real_debt_rate:.1%})")

    if recommendations:
        insights.append(f"Consider: {', '.join(recommendations)}.")

    return " ".join(insights)


def generate_purchasing_power_report(
    scenario: PersonalScenario,
    allocation_assumptions: Optional[List[AllocationAssumption]] = None,
) -> PurchasingPowerReport:
    """
    Generate complete personal exposure assessment.

    Args:
        scenario: PersonalScenario with financial inputs
        allocation_assumptions: Optional list of asset return assumptions

    Returns:
        PurchasingPowerReport with all metrics and insights
    """
    # Compute real rates
    real_rates = compute_real_rates(
        savings_yield=scenario.savings_yield,
        debt_apr=scenario.debt_apr,
    )

    # Compute runway
    runway = compute_runway(
        current_savings=scenario.current_savings,
        monthly_expenses=scenario.monthly_expenses,
        savings_yield=scenario.savings_yield,
        income_monthly=scenario.income_monthly,
        debt_balance=scenario.debt_balance,
        debt_apr=scenario.debt_apr,
    )

    # Model scenario shocks
    runway.scenario_shocks = model_scenario_shocks(scenario)

    # Compute offset requirements
    offset = compute_offset_requirements(
        current_savings=scenario.current_savings,
        real_rate_leak_per_year=runway.real_rate_leak_per_year,
        inflation_proxy=DEFAULT_M2_INFLATION,
        assumptions=allocation_assumptions,
    )

    # Generate narrative
    thesis_connection = generate_thesis_connection(real_rates)
    actionable_insight = generate_actionable_insight(scenario, real_rates, runway)

    return PurchasingPowerReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        scenario=scenario,
        real_rates=real_rates,
        runway=runway,
        offset=offset,
        thesis_connection=thesis_connection,
        actionable_insight=actionable_insight,
    )


# ─── Analyzer Class ────────────────────────────────────────────────────────

class PurchasingPowerAnalyzer:
    """
    Personal financial exposure analyzer using FGIP-validated inflation.

    Connects macro economic thesis to personal purchasing power metrics.
    """

    def __init__(self, db_path: str = 'fgip.db'):
        self.db_path = db_path
        self.inflation_proxy = DEFAULT_M2_INFLATION
        self.cpi_official = DEFAULT_CPI_OFFICIAL
        self.treasury_yield = DEFAULT_TREASURY_YIELD
        self.conn = None
        self._load_economic_baseline()

    def _get_connection(self):
        """Get database connection."""
        import sqlite3
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
        return self.conn

    def get_reshoring_beneficiaries(
        self,
        base_expected_return: float = 0.10,
        confidence_multiplier: float = 0.05,
    ) -> List[AllocationAssumption]:
        """
        Pull reshoring beneficiaries from the FGIP graph as allocation assumptions.

        Queries companies with AWARDED_GRANT, BUILT_IN, FUNDED_PROJECT edges
        from CHIPS Act and related reshoring programs.

        Args:
            base_expected_return: Base nominal return assumption (default 10%)
            confidence_multiplier: How much edge confidence boosts return (default 5%)

        Returns:
            List of AllocationAssumption for reshoring beneficiaries
        """
        conn = self._get_connection()

        # Query companies benefiting from reshoring programs
        sql = """
        SELECT DISTINCT
            n.node_id,
            n.name,
            MAX(e.confidence) as max_confidence,
            COUNT(DISTINCT e.edge_id) as edge_count,
            GROUP_CONCAT(DISTINCT e.edge_type) as edge_types
        FROM nodes n
        JOIN edges e ON n.node_id = e.to_node_id OR n.node_id = e.from_node_id
        WHERE e.edge_type IN ('AWARDED_GRANT', 'BUILT_IN', 'FUNDED_PROJECT')
        AND n.node_type = 'COMPANY'
        GROUP BY n.node_id, n.name
        ORDER BY max_confidence DESC, edge_count DESC
        """

        rows = conn.execute(sql).fetchall()

        assumptions = []
        for row in rows:
            # Expected return = base + (confidence * multiplier)
            # Higher graph confidence = higher return assumption
            confidence = row['max_confidence'] or 0.5
            expected_return = base_expected_return + (confidence * confidence_multiplier)

            # Volatility based on edge count (more edges = more validated = lower vol)
            edge_count = row['edge_count'] or 1
            if edge_count >= 5:
                volatility = "Moderate"
            elif edge_count >= 2:
                volatility = "Moderate-High"
            else:
                volatility = "High"

            assumptions.append(AllocationAssumption(
                name=f"{row['name']} (reshoring)",
                expected_nominal_return=round(expected_return, 4),
                volatility_note=volatility,
                liquidity_note="T+1 (public equity)",
                node_id=row['node_id'],
            ))

        return assumptions

    def get_gold_assumption(
        self,
        expected_return: float = 0.08,
    ) -> AllocationAssumption:
        """
        Create gold allocation assumption.

        Gold historically tracks M2 money supply growth, making it a natural
        inflation hedge in the FGIP thesis framework.
        """
        return AllocationAssumption(
            name="Gold proxy",
            expected_nominal_return=expected_return,
            volatility_note="Moderate",
            liquidity_note="T+1 (ETF/futures)",
            node_id="gold-proxy",
        )

    def get_tbill_assumption(self) -> AllocationAssumption:
        """
        Create T-Bill allocation assumption using current Treasury yield.
        """
        return AllocationAssumption(
            name="T-Bills (4-week)",
            expected_nominal_return=self.treasury_yield,
            volatility_note="Low",
            liquidity_note="Weekly",
            node_id="tbill-4wk",
        )

    def get_default_assumptions(self) -> List[AllocationAssumption]:
        """
        Get default allocation assumptions including reshoring beneficiaries.

        Combines:
        - Reshoring beneficiaries from graph (CHIPS Act recipients)
        - Gold proxy (M2 tracker)
        - T-Bills (risk-free baseline)
        """
        assumptions = []

        # Add reshoring beneficiaries from graph
        assumptions.extend(self.get_reshoring_beneficiaries())

        # Add gold
        assumptions.append(self.get_gold_assumption())

        # Add T-Bills
        assumptions.append(self.get_tbill_assumption())

        return assumptions

    def _load_economic_baseline(self):
        """
        Load M2, CPI, Treasury yields from economic_model if available.
        Falls back to defaults if not.
        """
        try:
            from .economic_model import get_baseline_model
            model = get_baseline_model()
            vars = model.variables

            if 'real_inflation' in vars:
                self.inflation_proxy = vars['real_inflation'].current_value / 100
            if 'cpi_official' in vars:
                self.cpi_official = vars['cpi_official'].current_value / 100
            if 'treasury_yield_4wk' in vars:
                self.treasury_yield = vars['treasury_yield_4wk'].current_value / 100

        except ImportError:
            pass  # Use defaults
        except Exception:
            pass  # Use defaults

    def analyze(
        self,
        scenario: PersonalScenario,
        allocation_assumptions: Optional[List[AllocationAssumption]] = None,
    ) -> PurchasingPowerReport:
        """Run full analysis with current economic baseline."""
        return generate_purchasing_power_report(scenario, allocation_assumptions)

    def get_real_rates(
        self,
        savings_yield: float,
        debt_apr: float = 0.0
    ) -> RealRateResult:
        """Quick real rate lookup using current baseline."""
        return compute_real_rates(
            savings_yield=savings_yield,
            debt_apr=debt_apr,
            inflation_proxy=self.inflation_proxy,
            cpi_official=self.cpi_official,
        )

    def get_runway(
        self,
        savings: float,
        expenses: float,
        yield_pct: float = None
    ) -> RunwayResult:
        """Quick runway calculation."""
        if yield_pct is None:
            yield_pct = self.treasury_yield

        return compute_runway(
            current_savings=savings,
            monthly_expenses=expenses,
            savings_yield=yield_pct,
            inflation_proxy=self.inflation_proxy,
        )


# ─── CLI Entry Point ───────────────────────────────────────────────────────

def main():
    import argparse
    import sys
    import os

    parser = argparse.ArgumentParser(
        description='FGIP Purchasing Power Analyzer - Personal financial runway calculator'
    )
    parser.add_argument('--expenses', type=float, required=True,
                        help='Monthly expenses in USD')
    parser.add_argument('--savings', type=float, required=True,
                        help='Current liquid savings in USD')
    parser.add_argument('--yield', dest='yield_pct', type=float, default=0.045,
                        help='Savings APY as decimal (default: 0.045)')
    parser.add_argument('--debt', type=float, default=0.0,
                        help='Total debt balance in USD (default: 0)')
    parser.add_argument('--debt-apr', type=float, default=0.0,
                        help='Weighted average debt APR as decimal (default: 0)')
    parser.add_argument('--income', type=float, default=0.0,
                        help='Monthly income in USD (default: 0)')
    parser.add_argument('--output', type=str,
                        help='Output JSON file path')
    parser.add_argument('--brief', action='store_true',
                        help='Show brief summary only')

    args = parser.parse_args()

    # Build scenario
    scenario = PersonalScenario(
        monthly_expenses=args.expenses,
        current_savings=args.savings,
        savings_yield=args.yield_pct,
        debt_balance=args.debt,
        debt_apr=args.debt_apr,
        income_monthly=args.income,
    )

    # Run analysis
    analyzer = PurchasingPowerAnalyzer()
    report = analyzer.analyze(scenario)

    # Output
    if args.brief:
        print(f"\n{'='*60}")
        print("  FGIP PURCHASING POWER ANALYSIS")
        print(f"{'='*60}")
        print(f"\n  Real Savings Yield: {report.real_rates.real_savings_yield:.1%}")
        print(f"  Hidden Extraction:  {report.real_rates.hidden_extraction:.1%}")
        print(f"\n  Nominal Runway:     {report.runway.nominal_months:.0f} months")
        print(f"  Inflation-Adjusted: {report.runway.inflation_adjusted_months:.0f} months")
        if report.runway.real_rate_leak_per_year > 0:
            print(f"  Real-Rate Leak:     ${report.runway.real_rate_leak_per_year:,.0f}/year")
        if report.runway.annual_savings_erosion > 0:
            print(f"  Annual Erosion:     ${report.runway.annual_savings_erosion:,.0f}")
        if report.offset:
            print(f"\n  -- Offset Requirements --")
            print(f"  Required Real Return:    {report.offset.required_real_return:.1%}")
            print(f"  Required Nominal Return: {report.offset.required_nominal_return:.1%}")
        print(f"\n  {report.actionable_insight}")
        print()
    else:
        print(report.to_json(indent=2))

    # Save to file if requested
    if args.output:
        os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
        with open(args.output, 'w') as f:
            f.write(report.to_json(indent=2))
        print(f"\nReport saved: {args.output}")


if __name__ == "__main__":
    main()
