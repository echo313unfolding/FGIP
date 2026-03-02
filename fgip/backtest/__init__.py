"""FGIP Backtest Module - Portfolio backtesting with conviction signals."""

from .risk_metrics import (
    sharpe_ratio,
    sortino_ratio,
    max_drawdown,
    alpha_beta,
    information_ratio,
    calmar_ratio,
)
from .position_sizing import (
    conviction_based_size,
    kelly_fraction,
    volatility_adjusted_size,
    liquidity_adjusted_size,
)
from .portfolio_backtest import (
    BacktestConfig,
    BacktestResult,
    PortfolioBacktest,
)

__all__ = [
    # Risk metrics
    "sharpe_ratio",
    "sortino_ratio",
    "max_drawdown",
    "alpha_beta",
    "information_ratio",
    "calmar_ratio",
    # Position sizing
    "conviction_based_size",
    "kelly_fraction",
    "volatility_adjusted_size",
    "liquidity_adjusted_size",
    # Backtest
    "BacktestConfig",
    "BacktestResult",
    "PortfolioBacktest",
]
