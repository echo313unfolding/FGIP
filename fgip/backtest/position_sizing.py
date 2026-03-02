"""
FGIP Position Sizing - Methods for determining position sizes.

Position sizing strategies:
1. Conviction-based: Size based on thesis conviction level (1-5)
2. Kelly criterion: Optimal sizing based on win probability and odds
3. Volatility-adjusted: Scale by inverse volatility
4. Liquidity-adjusted: Cap based on average daily volume

Usage:
    from fgip.backtest.position_sizing import conviction_based_size, kelly_fraction

    # Conviction-based
    size = conviction_based_size(conviction_level=4, max_pct=0.20)  # 15%

    # Kelly
    size = kelly_fraction(win_prob=0.6, win_loss_ratio=2.0)  # ~20%
"""

import math
from typing import Dict, Optional


def conviction_based_size(
    conviction_level: int,
    max_pct: float = 0.20,
    min_conviction_to_trade: int = 2
) -> float:
    """
    Determine position size based on conviction level.

    Maps conviction levels (1-5) to position sizes.

    Args:
        conviction_level: Conviction from 1 (lowest) to 5 (highest)
        max_pct: Maximum position size (default 20%)
        min_conviction_to_trade: Minimum conviction required to take position

    Returns:
        Position size as percentage (0.0 to max_pct)

    Conviction Level Mapping:
        Level 5: max_pct (20%) - Multiple Tier 0 confirmations
        Level 4: 75% of max (15%) - High confidence
        Level 3: 50% of max (10%) - Moderate confidence
        Level 2: 25% of max (5%) - Speculative
        Level 1: 0% - No position
    """
    if conviction_level < min_conviction_to_trade:
        return 0.0

    size_multipliers = {
        5: 1.00,   # 100% of max
        4: 0.75,   # 75% of max
        3: 0.50,   # 50% of max
        2: 0.25,   # 25% of max
        1: 0.00,   # No position
    }

    multiplier = size_multipliers.get(conviction_level, 0.0)
    return max_pct * multiplier


def kelly_fraction(
    win_prob: float,
    win_loss_ratio: float,
    fractional: float = 0.25
) -> float:
    """
    Calculate Kelly criterion position size.

    Full Kelly: f* = (p * b - q) / b
    where:
        p = win probability
        q = 1 - p (loss probability)
        b = win/loss ratio (average win / average loss)

    Args:
        win_prob: Probability of winning (0 to 1)
        win_loss_ratio: Ratio of average win to average loss (e.g., 2.0 means wins are 2x losses)
        fractional: Fraction of full Kelly to use (0.25 = quarter Kelly is common)

    Returns:
        Position size as decimal (0.0 to 1.0)

    Note:
        Full Kelly is aggressive and leads to high volatility.
        Quarter Kelly (fractional=0.25) is commonly used in practice.
    """
    if win_prob <= 0 or win_prob >= 1:
        return 0.0

    if win_loss_ratio <= 0:
        return 0.0

    p = win_prob
    q = 1 - p
    b = win_loss_ratio

    # Kelly formula
    kelly_full = (p * b - q) / b

    if kelly_full <= 0:
        return 0.0

    # Apply fractional Kelly and clamp
    kelly_sized = kelly_full * fractional
    return max(0.0, min(1.0, kelly_sized))


def volatility_adjusted_size(
    base_size: float,
    current_vol: float,
    target_vol: float = 0.15
) -> float:
    """
    Scale position size by inverse volatility.

    Higher volatility -> smaller position
    Lower volatility -> larger position

    Targets a consistent volatility contribution to portfolio.

    Args:
        base_size: Base position size (e.g., from conviction)
        current_vol: Current annualized volatility of the asset
        target_vol: Target volatility for position (default 15%)

    Returns:
        Adjusted position size

    Example:
        If asset has 30% vol and target is 15%, position is halved.
        If asset has 10% vol and target is 15%, position is increased 50%.
    """
    if current_vol <= 0 or math.isnan(current_vol):
        return base_size

    adjustment = target_vol / current_vol
    adjusted_size = base_size * adjustment

    # Cap at reasonable bounds
    return max(0.0, min(adjusted_size, base_size * 2.0))


def liquidity_adjusted_size(
    base_size: float,
    portfolio_value: float,
    avg_daily_volume: float,
    avg_price: float,
    max_adv_pct: float = 0.01
) -> float:
    """
    Cap position to percentage of average daily volume.

    Prevents taking positions that would be difficult to exit.

    Args:
        base_size: Base position size as percentage of portfolio
        portfolio_value: Total portfolio value in dollars
        avg_daily_volume: Average daily volume in shares
        avg_price: Average price per share
        max_adv_pct: Maximum percentage of ADV to represent (default 1%)

    Returns:
        Adjusted position size (may be smaller than base_size)

    Example:
        Portfolio: $1M, Position: 10%, Stock: $50/share, ADV: 100K shares
        Position would be $100K / $50 = 2,000 shares
        Max ADV = 100K * 1% = 1,000 shares = $50K = 5%
        Adjusted position = 5%
    """
    if avg_daily_volume <= 0 or avg_price <= 0:
        return base_size

    # Calculate position in shares
    position_value = portfolio_value * base_size
    position_shares = position_value / avg_price

    # Calculate max shares based on ADV
    max_shares = avg_daily_volume * max_adv_pct

    if position_shares <= max_shares:
        return base_size

    # Scale down to max ADV
    max_value = max_shares * avg_price
    max_size = max_value / portfolio_value

    return max_size


def equal_weight_size(
    num_positions: int,
    max_position_pct: float = 0.20
) -> float:
    """
    Calculate equal weight position size.

    Args:
        num_positions: Number of positions to hold
        max_position_pct: Maximum single position (default 20%)

    Returns:
        Position size for each holding
    """
    if num_positions <= 0:
        return 0.0

    equal_size = 1.0 / num_positions
    return min(equal_size, max_position_pct)


def risk_parity_size(
    asset_volatility: float,
    portfolio_target_vol: float,
    num_assets: int
) -> float:
    """
    Calculate risk parity position size.

    Each position contributes equally to portfolio volatility.

    Args:
        asset_volatility: Annualized volatility of this asset
        portfolio_target_vol: Target portfolio volatility
        num_assets: Number of assets in portfolio

    Returns:
        Position size for this asset
    """
    if asset_volatility <= 0 or num_assets <= 0:
        return 0.0

    # Equal risk budget per asset
    risk_budget = portfolio_target_vol / math.sqrt(num_assets)

    # Size to achieve risk budget
    size = risk_budget / asset_volatility

    return max(0.0, min(1.0, size))


def position_sizer(
    conviction_level: int,
    win_prob: Optional[float] = None,
    win_loss_ratio: Optional[float] = None,
    asset_volatility: Optional[float] = None,
    portfolio_value: Optional[float] = None,
    avg_daily_volume: Optional[int] = None,
    avg_price: Optional[float] = None,
    max_position_pct: float = 0.20,
    target_volatility: float = 0.15,
    kelly_fraction_pct: float = 0.25,
    max_adv_pct: float = 0.01,
    method: str = "conviction"
) -> Dict[str, float]:
    """
    Comprehensive position sizing with multiple methods.

    Calculates position size using specified method, then applies
    volatility and liquidity adjustments.

    Args:
        conviction_level: Conviction from 1-5
        win_prob: Win probability for Kelly (optional)
        win_loss_ratio: Win/loss ratio for Kelly (optional)
        asset_volatility: Annualized volatility (optional)
        portfolio_value: Portfolio value in dollars (optional)
        avg_daily_volume: ADV in shares (optional)
        avg_price: Average price per share (optional)
        max_position_pct: Maximum position size
        target_volatility: Target vol for vol-adjusted sizing
        kelly_fraction_pct: Fraction of full Kelly
        max_adv_pct: Max percentage of ADV
        method: "conviction", "kelly", or "equal"

    Returns:
        Dict with:
            - base_size: Initial size from method
            - vol_adjusted_size: After volatility adjustment
            - final_size: After liquidity adjustment
            - adjustments: List of adjustments applied
    """
    adjustments = []

    # Step 1: Calculate base size
    if method == "kelly" and win_prob is not None and win_loss_ratio is not None:
        base_size = kelly_fraction(win_prob, win_loss_ratio, kelly_fraction_pct)
        base_size = min(base_size, max_position_pct)
        adjustments.append(f"kelly(p={win_prob:.2f}, b={win_loss_ratio:.2f})")
    elif method == "conviction":
        base_size = conviction_based_size(conviction_level, max_position_pct)
        adjustments.append(f"conviction(level={conviction_level})")
    else:
        base_size = max_position_pct
        adjustments.append(f"fixed({max_position_pct*100:.0f}%)")

    # Step 2: Volatility adjustment (if volatility provided)
    vol_adjusted_size = base_size
    if asset_volatility is not None and asset_volatility > 0:
        vol_adjusted_size = volatility_adjusted_size(
            base_size, asset_volatility, target_volatility
        )
        if abs(vol_adjusted_size - base_size) > 0.001:
            adjustments.append(f"vol_adj({asset_volatility*100:.1f}%)")

    # Step 3: Liquidity adjustment (if liquidity data provided)
    final_size = vol_adjusted_size
    if (portfolio_value is not None and avg_daily_volume is not None and
        avg_price is not None and all(v > 0 for v in [portfolio_value, avg_daily_volume, avg_price])):
        final_size = liquidity_adjusted_size(
            vol_adjusted_size, portfolio_value, avg_daily_volume, avg_price, max_adv_pct
        )
        if abs(final_size - vol_adjusted_size) > 0.001:
            adjustments.append(f"liq_adj(adv={avg_daily_volume:,.0f})")

    return {
        "base_size": base_size,
        "vol_adjusted_size": vol_adjusted_size,
        "final_size": final_size,
        "adjustments": adjustments,
    }
