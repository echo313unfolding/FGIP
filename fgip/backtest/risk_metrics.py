"""
FGIP Risk Metrics - Portfolio performance and risk calculations.

Provides standardized financial metrics:
- Sharpe Ratio: Risk-adjusted return
- Sortino Ratio: Downside risk-adjusted return
- Max Drawdown: Peak-to-trough decline
- Alpha/Beta: CAPM regression metrics
- Information Ratio: Active return vs tracking error

Usage:
    from fgip.backtest.risk_metrics import sharpe_ratio, max_drawdown

    import pandas as pd
    returns = pd.Series([0.01, -0.02, 0.03, 0.01, -0.01])

    sharpe = sharpe_ratio(returns)
    mdd, duration = max_drawdown(equity_curve)
"""

import math
from typing import Tuple, Optional

try:
    import pandas as pd
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


def sharpe_ratio(
    returns: "pd.Series",
    risk_free_rate: float = 0.045,
    annualize: bool = True
) -> float:
    """
    Calculate Sharpe ratio (risk-adjusted return).

    Sharpe = (Mean Return - Risk Free Rate) / Std Dev of Returns

    Args:
        returns: Daily returns series
        risk_free_rate: Annual risk-free rate (default 4.5% for current T-bills)
        annualize: If True, annualize the ratio (default True)

    Returns:
        Sharpe ratio (higher is better, >1 is good, >2 is excellent)
    """
    if len(returns) < 2:
        return 0.0

    # Daily risk-free rate
    daily_rf = risk_free_rate / 252

    excess_returns = returns - daily_rf
    mean_excess = excess_returns.mean()
    std = excess_returns.std()

    if std == 0 or math.isnan(std):
        return 0.0

    sharpe = mean_excess / std

    if annualize:
        sharpe = sharpe * math.sqrt(252)

    return float(sharpe)


def sortino_ratio(
    returns: "pd.Series",
    risk_free_rate: float = 0.045,
    annualize: bool = True
) -> float:
    """
    Calculate Sortino ratio (downside risk-adjusted return).

    Unlike Sharpe, Sortino only penalizes downside volatility,
    not upside volatility. Better for asymmetric return distributions.

    Sortino = (Mean Return - Risk Free Rate) / Downside Std Dev

    Args:
        returns: Daily returns series
        risk_free_rate: Annual risk-free rate
        annualize: If True, annualize the ratio

    Returns:
        Sortino ratio (higher is better)
    """
    if len(returns) < 2:
        return 0.0

    # Daily risk-free rate
    daily_rf = risk_free_rate / 252

    excess_returns = returns - daily_rf
    mean_excess = excess_returns.mean()

    # Downside returns only (negative returns)
    downside_returns = returns[returns < 0]

    if len(downside_returns) == 0:
        return float('inf') if mean_excess > 0 else 0.0

    downside_std = downside_returns.std()

    if downside_std == 0 or math.isnan(downside_std):
        return 0.0

    sortino = mean_excess / downside_std

    if annualize:
        sortino = sortino * math.sqrt(252)

    return float(sortino)


def max_drawdown(equity_curve: "pd.Series") -> Tuple[float, int]:
    """
    Calculate maximum drawdown and duration.

    Max drawdown = largest peak-to-trough decline (as negative percentage)
    Duration = number of days from peak to recovery

    Args:
        equity_curve: Time series of portfolio values

    Returns:
        Tuple of (max_drawdown_pct, duration_days)
        max_drawdown_pct is negative (e.g., -0.15 for 15% drawdown)
    """
    if len(equity_curve) < 2:
        return (0.0, 0)

    # Running maximum (high water mark)
    running_max = equity_curve.expanding().max()

    # Drawdown series
    drawdown = (equity_curve - running_max) / running_max

    # Max drawdown
    max_dd = float(drawdown.min())

    # Duration calculation - find longest underwater period
    underwater = drawdown < 0
    if not underwater.any():
        return (0.0, 0)

    # Group consecutive underwater days
    groups = (underwater != underwater.shift()).cumsum()
    underwater_groups = groups[underwater]

    if len(underwater_groups) == 0:
        return (max_dd, 0)

    duration_counts = underwater_groups.groupby(underwater_groups).count()
    max_duration = int(duration_counts.max())

    return (max_dd, max_duration)


def alpha_beta(
    portfolio_returns: "pd.Series",
    benchmark_returns: "pd.Series",
    risk_free_rate: float = 0.045
) -> Tuple[float, float]:
    """
    Calculate CAPM alpha and beta.

    Alpha: Excess return not explained by market exposure
    Beta: Sensitivity to market movements (beta=1 means moves with market)

    Uses ordinary least squares regression:
    R_portfolio - R_f = alpha + beta * (R_benchmark - R_f) + epsilon

    Args:
        portfolio_returns: Daily portfolio returns
        benchmark_returns: Daily benchmark returns (e.g., SPY)
        risk_free_rate: Annual risk-free rate

    Returns:
        Tuple of (alpha, beta)
        Alpha is annualized
    """
    if len(portfolio_returns) < 10 or len(benchmark_returns) < 10:
        return (0.0, 1.0)

    # Align series
    aligned = pd.concat([portfolio_returns, benchmark_returns], axis=1).dropna()
    if len(aligned) < 10:
        return (0.0, 1.0)

    port_ret = aligned.iloc[:, 0]
    bench_ret = aligned.iloc[:, 1]

    # Daily risk-free rate
    daily_rf = risk_free_rate / 252

    # Excess returns
    port_excess = port_ret - daily_rf
    bench_excess = bench_ret - daily_rf

    # OLS regression: y = alpha + beta * x
    # beta = cov(x,y) / var(x)
    # alpha = mean(y) - beta * mean(x)
    cov = port_excess.cov(bench_excess)
    var = bench_excess.var()

    if var == 0 or math.isnan(var):
        return (0.0, 1.0)

    beta = cov / var
    alpha_daily = port_excess.mean() - beta * bench_excess.mean()

    # Annualize alpha
    alpha_annual = alpha_daily * 252

    return (float(alpha_annual), float(beta))


def information_ratio(
    portfolio_returns: "pd.Series",
    benchmark_returns: "pd.Series",
    annualize: bool = True
) -> float:
    """
    Calculate Information Ratio.

    IR = Active Return / Tracking Error
    Active Return = Portfolio Return - Benchmark Return
    Tracking Error = Std Dev of Active Returns

    Measures consistency of outperformance.

    Args:
        portfolio_returns: Daily portfolio returns
        benchmark_returns: Daily benchmark returns
        annualize: If True, annualize the ratio

    Returns:
        Information ratio (higher is better, >0.5 is good)
    """
    if len(portfolio_returns) < 10 or len(benchmark_returns) < 10:
        return 0.0

    # Align series
    aligned = pd.concat([portfolio_returns, benchmark_returns], axis=1).dropna()
    if len(aligned) < 10:
        return 0.0

    port_ret = aligned.iloc[:, 0]
    bench_ret = aligned.iloc[:, 1]

    # Active returns
    active_returns = port_ret - bench_ret

    mean_active = active_returns.mean()
    tracking_error = active_returns.std()

    if tracking_error == 0 or math.isnan(tracking_error):
        return 0.0

    ir = mean_active / tracking_error

    if annualize:
        ir = ir * math.sqrt(252)

    return float(ir)


def calmar_ratio(
    returns: "pd.Series",
    equity_curve: Optional["pd.Series"] = None
) -> float:
    """
    Calculate Calmar Ratio.

    Calmar = Annualized Return / |Max Drawdown|

    Measures return relative to worst-case loss.

    Args:
        returns: Daily returns series
        equity_curve: Portfolio value series (optional, computed from returns if not provided)

    Returns:
        Calmar ratio (higher is better)
    """
    if len(returns) < 20:
        return 0.0

    # Annualized return
    total_return = (1 + returns).prod() - 1
    days = len(returns)
    annual_return = (1 + total_return) ** (252 / days) - 1

    # Compute equity curve if not provided
    if equity_curve is None:
        equity_curve = (1 + returns).cumprod()

    mdd, _ = max_drawdown(equity_curve)

    if mdd >= 0:  # No drawdown
        return float('inf') if annual_return > 0 else 0.0

    calmar = annual_return / abs(mdd)
    return float(calmar)


def volatility(returns: "pd.Series", annualize: bool = True) -> float:
    """
    Calculate return volatility (standard deviation).

    Args:
        returns: Daily returns series
        annualize: If True, annualize (multiply by sqrt(252))

    Returns:
        Volatility (as decimal, e.g., 0.20 for 20%)
    """
    if len(returns) < 2:
        return 0.0

    vol = returns.std()

    if annualize:
        vol = vol * math.sqrt(252)

    return float(vol) if not math.isnan(vol) else 0.0


def win_rate(returns: "pd.Series") -> float:
    """
    Calculate win rate (percentage of positive returns).

    Args:
        returns: Returns series

    Returns:
        Win rate as decimal (e.g., 0.55 for 55%)
    """
    if len(returns) == 0:
        return 0.0

    positive = (returns > 0).sum()
    return float(positive / len(returns))


def profit_factor(returns: "pd.Series") -> float:
    """
    Calculate profit factor.

    Profit Factor = Sum of Gains / |Sum of Losses|

    Args:
        returns: Returns series

    Returns:
        Profit factor (>1 is profitable, >2 is good)
    """
    gains = returns[returns > 0].sum()
    losses = abs(returns[returns < 0].sum())

    if losses == 0:
        return float('inf') if gains > 0 else 0.0

    return float(gains / losses)


def avg_win_loss(returns: "pd.Series") -> Tuple[float, float]:
    """
    Calculate average winning and losing returns.

    Args:
        returns: Returns series

    Returns:
        Tuple of (avg_winner, avg_loser)
        avg_loser is negative
    """
    winners = returns[returns > 0]
    losers = returns[returns < 0]

    avg_win = float(winners.mean()) if len(winners) > 0 else 0.0
    avg_loss = float(losers.mean()) if len(losers) > 0 else 0.0

    return (avg_win, avg_loss)


def risk_metrics_summary(
    returns: "pd.Series",
    benchmark_returns: Optional["pd.Series"] = None,
    risk_free_rate: float = 0.045
) -> dict:
    """
    Calculate all risk metrics in one call.

    Args:
        returns: Daily portfolio returns
        benchmark_returns: Daily benchmark returns (optional)
        risk_free_rate: Annual risk-free rate

    Returns:
        Dict with all metrics
    """
    equity = (1 + returns).cumprod()
    mdd, mdd_duration = max_drawdown(equity)
    avg_win, avg_loss = avg_win_loss(returns)

    result = {
        "total_return": float((1 + returns).prod() - 1),
        "annualized_return": float((1 + returns).prod() ** (252 / len(returns)) - 1) if len(returns) > 0 else 0.0,
        "volatility": volatility(returns),
        "sharpe_ratio": sharpe_ratio(returns, risk_free_rate),
        "sortino_ratio": sortino_ratio(returns, risk_free_rate),
        "max_drawdown": mdd,
        "max_drawdown_duration": mdd_duration,
        "calmar_ratio": calmar_ratio(returns, equity),
        "win_rate": win_rate(returns),
        "profit_factor": profit_factor(returns),
        "avg_winner": avg_win,
        "avg_loser": avg_loss,
    }

    if benchmark_returns is not None and len(benchmark_returns) > 0:
        alpha, beta = alpha_beta(returns, benchmark_returns, risk_free_rate)
        ir = information_ratio(returns, benchmark_returns)
        result["alpha"] = alpha
        result["beta"] = beta
        result["information_ratio"] = ir

    return result
