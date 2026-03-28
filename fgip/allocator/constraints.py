"""
Settlement constraints for allocation directives.

Defines the input parameters that constrain what allocations are valid.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class RiskTolerance(str, Enum):
    """Risk tolerance levels for allocation."""
    CONSERVATIVE = "conservative"   # Protect principal above all
    MODERATE = "moderate"           # Balanced growth/protection
    GROWTH = "growth"               # Accept volatility for returns


@dataclass
class SettlementConstraints:
    """
    Input constraints for allocation directive.

    These parameters define the boundaries within which the allocator
    must operate. All allocations must satisfy these constraints.
    """

    # Core parameters
    settlement_amount: float                    # Total amount to allocate ($)
    liquidity_runway_months: int = 18           # Cash reserve floor (months)
    time_horizon_years: int = 10                # Investment horizon (years)
    risk_tolerance: RiskTolerance = RiskTolerance.MODERATE
    max_expense_ratio_bps: int = 20             # Max 0.20% ER (basis points)

    # Income/withdrawal needs
    income_need_monthly: float = 0              # Regular withdrawal need ($)

    # Tax considerations
    tax_sensitive: bool = True                  # Prefer tax-efficient vehicles

    # Hard constraints (non-negotiable)
    no_single_stock: bool = True                # No individual stocks
    max_single_position_pct: float = 0.30       # Max 30% in one bucket
    min_diversification_buckets: int = 3        # At least 3 buckets

    def validate(self) -> list:
        """Validate constraints and return list of errors."""
        errors = []

        if self.settlement_amount <= 0:
            errors.append("settlement_amount must be positive")

        if self.liquidity_runway_months < 0:
            errors.append("liquidity_runway_months cannot be negative")

        if self.time_horizon_years < 1:
            errors.append("time_horizon_years must be at least 1")

        if self.max_expense_ratio_bps < 0 or self.max_expense_ratio_bps > 200:
            errors.append("max_expense_ratio_bps must be 0-200 (0-2%)")

        if self.max_single_position_pct <= 0 or self.max_single_position_pct > 1:
            errors.append("max_single_position_pct must be 0-1")

        if self.min_diversification_buckets < 2:
            errors.append("min_diversification_buckets must be at least 2")

        return errors

    def to_dict(self) -> dict:
        """Convert to dict for serialization."""
        return {
            "settlement_amount": self.settlement_amount,
            "liquidity_runway_months": self.liquidity_runway_months,
            "time_horizon_years": self.time_horizon_years,
            "risk_tolerance": self.risk_tolerance.value,
            "max_expense_ratio_bps": self.max_expense_ratio_bps,
            "income_need_monthly": self.income_need_monthly,
            "tax_sensitive": self.tax_sensitive,
            "no_single_stock": self.no_single_stock,
            "max_single_position_pct": self.max_single_position_pct,
            "min_diversification_buckets": self.min_diversification_buckets,
        }
