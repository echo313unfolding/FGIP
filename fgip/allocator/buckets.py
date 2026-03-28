"""
Allocation bucket definitions.

Defines the core asset categories for settlement allocation,
with generic categories mapped to specific low-cost defaults.
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class AllocationBucket:
    """
    A category of allocation with instrument options.

    Each bucket represents a distinct purpose in the portfolio
    with its own risk/return profile and regime sensitivity.
    """

    bucket_id: str                      # e.g., "safety_floor"
    name: str                           # Human-readable name
    purpose: str                        # Why this bucket exists
    category: str                       # Generic category name
    default_tickers: List[str]          # Specific low-cost defaults
    default_weight: float               # Base allocation % (0-1)
    min_weight: float                   # Floor
    max_weight: float                   # Ceiling
    regime_adjustments: Dict[str, float] = field(default_factory=dict)
    expense_ratio_cap_bps: int = 20     # Max ER in basis points


# Core bucket definitions (generic category + specific defaults)
BUCKETS: Dict[str, AllocationBucket] = {
    "safety_floor": AllocationBucket(
        bucket_id="safety_floor",
        name="Safety Floor (Liquidity)",
        purpose="Protect against forced selling; immediate access",
        category="cash-equivalents",
        default_tickers=["SGOV", "BIL", "SHV"],  # 0-3mo T-bills
        default_weight=0.10,
        min_weight=0.05,
        max_weight=0.25,
        regime_adjustments={"STRESS": 0.05, "CRISIS": 0.10},
        expense_ratio_cap_bps=10,
    ),
    "inflation_hedge": AllocationBucket(
        bucket_id="inflation_hedge",
        name="Inflation Hedge",
        purpose="Protect purchasing power from M2-CPI gap",
        category="inflation-protected",
        default_tickers=["VTIP", "SCHP", "TIP"],  # Short/broad TIPS
        default_weight=0.20,
        min_weight=0.10,
        max_weight=0.35,
        regime_adjustments={"m2_gap_high": 0.10},
        expense_ratio_cap_bps=10,
    ),
    "income_ladder": AllocationBucket(
        bucket_id="income_ladder",
        name="Income Ladder (Treasuries)",
        purpose="Predictable income; duration-matched to needs",
        category="treasury-duration",
        default_tickers=["VGSH", "VGIT", "SCHR"],  # Short/intermediate treasuries
        default_weight=0.40,
        min_weight=0.20,
        max_weight=0.60,
        regime_adjustments={"CRISIS": 0.10},
        expense_ratio_cap_bps=10,
    ),
    "growth": AllocationBucket(
        bucket_id="growth",
        name="Growth (Equities)",
        purpose="Long-horizon compounding; accept volatility",
        category="broad-equity",
        default_tickers=["VTI", "VXUS", "VT"],  # Total US, Intl, World
        default_weight=0.30,
        min_weight=0.10,
        max_weight=0.50,
        regime_adjustments={"STRESS": -0.10, "CRISIS": -0.15},
        expense_ratio_cap_bps=10,
    ),
}


# Ticker override map (user can customize)
# Maps generic category -> preferred ticker
DEFAULT_TICKER_MAP: Dict[str, str] = {
    "cash-equivalents": "SGOV",      # iShares 0-3 Month Treasury (0.07% ER)
    "inflation-protected": "VTIP",   # Vanguard Short-Term TIPS (0.04% ER)
    "treasury-duration": "VGIT",     # Vanguard Intermediate Treasury (0.04% ER)
    "broad-equity": "VTI",           # Vanguard Total Stock (0.03% ER)
}


def get_bucket_ids() -> List[str]:
    """Return list of all bucket IDs."""
    return list(BUCKETS.keys())


def get_bucket(bucket_id: str) -> AllocationBucket:
    """Get bucket by ID, raise KeyError if not found."""
    return BUCKETS[bucket_id]


def get_preferred_ticker(category: str) -> str:
    """Get preferred ticker for a category."""
    return DEFAULT_TICKER_MAP.get(category, category)
