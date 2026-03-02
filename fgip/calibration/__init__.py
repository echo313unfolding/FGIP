"""FGIP Calibration Module - Brier scores, log scores, calibration curves.

This module provides tools for measuring forecast accuracy and calibration:

- Brier Score: Mean squared error of probability forecasts (0=perfect, 0.25=random)
- Log Score: Logarithmic scoring rule (sensitive to confident wrong predictions)
- Calibration Curves: Plot predicted vs actual frequencies

The shift from "conviction vibes" to calibrated probabilities makes the system
auditable, improvable, and honest about its uncertainty.
"""

from .scoring import (
    brier_score,
    log_score,
    calibration_error,
    CalibrationResult,
    compute_calibration_metrics,
    kelly_criterion,
    CalibrationTracker,
)

from .backtest import (
    WalkForwardBacktest,
    BacktestResult,
    BacktestStep,
)

__all__ = [
    "brier_score",
    "log_score",
    "calibration_error",
    "CalibrationResult",
    "compute_calibration_metrics",
    "kelly_criterion",
    "CalibrationTracker",
    "WalkForwardBacktest",
    "BacktestResult",
    "BacktestStep",
]
