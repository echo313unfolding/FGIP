"""
Investment Policy Statement (IPS) for family fund governance.

One-page document capturing objectives, constraints, and rules.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional
from enum import Enum


class RebalanceTrigger(str, Enum):
    """Types of events that trigger rebalance review."""
    CALENDAR = "calendar"      # Fixed schedule (quarterly)
    DRIFT = "drift"            # Percentage drift threshold
    REGIME_CHANGE = "regime"   # Regime transition


@dataclass
class InvestmentPolicyStatement:
    """One-page IPS for family fund governance."""

    # Identity
    beneficiary: str
    prepared_date: date
    review_frequency_months: int = 1  # Monthly check-in

    # Objectives
    time_horizon_years: int = 10
    primary_goal: str = "Preserve purchasing power; modest growth"
    risk_tolerance: str = "moderate"

    # Constraints
    liquidity_minimum_months: int = 18
    max_expense_ratio_bps: int = 20
    no_single_stocks: bool = True
    max_single_position_pct: float = 0.30
    tax_sensitive: bool = True

    # Rebalance rules
    rebalance_triggers: List[RebalanceTrigger] = field(
        default_factory=lambda: [RebalanceTrigger.CALENDAR, RebalanceTrigger.DRIFT]
    )
    calendar_frequency_months: int = 3  # Quarterly
    drift_threshold_pct: float = 5.0    # 5% band

    # Circuit breakers
    cooling_period_hours: int = 72      # No impulse rule
    cooling_applies_to_pct: float = 5.0 # Changes > 5%

    # Governance
    decision_makers: List[str] = field(default_factory=list)
    requires_unanimous: bool = False

    # Core/Satellite structure
    core_allocation_pct: float = 0.85   # 85% in core (safety+income+inflation)
    satellite_allocation_pct: float = 0.15  # 15% in growth

    def validate(self) -> List[str]:
        """Validate IPS constraints. Returns list of issues."""
        issues = []

        if self.core_allocation_pct + self.satellite_allocation_pct != 1.0:
            issues.append(
                f"Core ({self.core_allocation_pct}) + Satellite ({self.satellite_allocation_pct}) "
                f"must sum to 1.0"
            )

        if self.max_single_position_pct > 0.5:
            issues.append(
                f"Max single position {self.max_single_position_pct*100:.0f}% exceeds 50% limit"
            )

        if self.liquidity_minimum_months < 6:
            issues.append(
                f"Liquidity minimum {self.liquidity_minimum_months} months is below 6-month floor"
            )

        return issues

    def to_markdown(self) -> str:
        """Render IPS as one-page markdown."""
        lines = [
            "# Investment Policy Statement",
            "",
            f"**Beneficiary:** {self.beneficiary}",
            f"**Prepared:** {self.prepared_date.isoformat()}",
            f"**Review:** Monthly (1st of each month)",
            "",
            "---",
            "",
            "## Objectives",
            "",
            f"- **Time Horizon:** {self.time_horizon_years} years",
            f"- **Primary Goal:** {self.primary_goal}",
            f"- **Risk Tolerance:** {self.risk_tolerance.title()}",
            "",
            "---",
            "",
            "## Constraints",
            "",
            "| Constraint | Value |",
            "|------------|-------|",
            f"| Minimum liquidity | {self.liquidity_minimum_months} months |",
            f"| Max expense ratio | {self.max_expense_ratio_bps} bps ({self.max_expense_ratio_bps/100:.2f}%) |",
            f"| Single stocks | {'Prohibited' if self.no_single_stocks else 'Allowed'} |",
            f"| Max single position | {self.max_single_position_pct * 100:.0f}% |",
            f"| Tax sensitivity | {'Yes' if self.tax_sensitive else 'No'} |",
            "",
            "---",
            "",
            "## Rebalance Rules",
            "",
            f"1. **Calendar:** Review allocation every {self.calendar_frequency_months} months",
            f"2. **Drift:** Rebalance if any bucket drifts >{self.drift_threshold_pct:.0f}% from target",
            "3. **Regime:** Adjust per directive triggers on regime change",
            "",
            "---",
            "",
            "## Circuit Breakers",
            "",
            f"**No Impulse Rule:** Any allocation change >{self.cooling_applies_to_pct:.0f}% "
            f"requires {self.cooling_period_hours}-hour cooling period before execution.",
            "",
            "**Rationale:** Prevents emotion-driven decisions. Sleep on it.",
            "",
            "---",
            "",
            "## Core/Satellite Structure",
            "",
            "| Component | Allocation | Purpose |",
            "|-----------|------------|---------|",
            f"| Core | {self.core_allocation_pct*100:.0f}% | Safety floor + income ladder + inflation hedge |",
            f"| Satellite | {self.satellite_allocation_pct*100:.0f}% | Growth allocation (VTI) |",
            "",
            "Core is non-negotiable. Satellite can flex based on regime.",
            "",
            "---",
            "",
            "## Governance",
            "",
        ]

        if self.decision_makers:
            lines.append(f"Decision makers: {', '.join(self.decision_makers)}")
        else:
            lines.append("Decision makers: *Not specified*")

        lines.append(f"Unanimous required: {'Yes' if self.requires_unanimous else 'No'}")

        lines.extend([
            "",
            "---",
            "",
            "## What Would Trigger Review",
            "",
            "- Regime change (NORMAL -> STRESS/CRISIS)",
            "- FCI exceeds CPI by >2% for 3 months",
            "- Major life change (health, housing, income)",
            "- Annual scheduled review",
            "",
            "---",
            "",
            "*This IPS governs the family fund. Review monthly. Update annually or on major life changes.*",
        ])

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "beneficiary": self.beneficiary,
            "prepared_date": self.prepared_date.isoformat(),
            "review_frequency_months": self.review_frequency_months,
            "time_horizon_years": self.time_horizon_years,
            "primary_goal": self.primary_goal,
            "risk_tolerance": self.risk_tolerance,
            "liquidity_minimum_months": self.liquidity_minimum_months,
            "max_expense_ratio_bps": self.max_expense_ratio_bps,
            "no_single_stocks": self.no_single_stocks,
            "max_single_position_pct": self.max_single_position_pct,
            "tax_sensitive": self.tax_sensitive,
            "calendar_frequency_months": self.calendar_frequency_months,
            "drift_threshold_pct": self.drift_threshold_pct,
            "cooling_period_hours": self.cooling_period_hours,
            "cooling_applies_to_pct": self.cooling_applies_to_pct,
            "decision_makers": self.decision_makers,
            "requires_unanimous": self.requires_unanimous,
            "core_allocation_pct": self.core_allocation_pct,
            "satellite_allocation_pct": self.satellite_allocation_pct,
        }
