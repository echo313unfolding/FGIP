"""FGIP Calibration Scoring - Brier scores, log scores, calibration metrics.

Core scoring functions for measuring forecast accuracy:

- Brier Score: Mean squared error of probability forecasts
  - 0.0 = perfect prediction
  - 0.25 = random guessing (50% on binary)
  - Lower is better

- Log Score: Logarithmic scoring rule
  - More sensitive to confident wrong predictions
  - Heavily penalizes high-confidence mistakes

- Calibration Error: |predicted_probability - actual_frequency|
  - Perfect calibration = 0
  - Measures systematic over/under confidence

Usage:
    from fgip.calibration import brier_score, log_score

    predictions = [(0.8, 1), (0.6, 0), (0.9, 1)]  # (probability, outcome)
    bs = brier_score(predictions)  # ~0.12
"""

import math
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional
from datetime import datetime
import json


@dataclass
class CalibrationResult:
    """Results from calibration analysis."""
    brier_score: float
    log_score: float
    sample_size: int
    mean_confidence: float
    hit_rate: float
    calibration_error: float
    overconfidence_ratio: float
    underconfidence_ratio: float
    bin_data: Dict[str, Dict] = field(default_factory=dict)  # For calibration curve
    computed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> Dict:
        return {
            "brier_score": self.brier_score,
            "log_score": self.log_score,
            "sample_size": self.sample_size,
            "mean_confidence": self.mean_confidence,
            "hit_rate": self.hit_rate,
            "calibration_error": self.calibration_error,
            "overconfidence_ratio": self.overconfidence_ratio,
            "underconfidence_ratio": self.underconfidence_ratio,
            "bin_data": self.bin_data,
            "computed_at": self.computed_at,
        }

    def is_well_calibrated(self, threshold: float = 0.1) -> bool:
        """Check if calibration error is within threshold."""
        return abs(self.calibration_error) <= threshold

    def summary(self) -> str:
        """Human-readable summary."""
        status = "WELL_CALIBRATED" if self.is_well_calibrated() else "NEEDS_CALIBRATION"
        conf = "OVERCONFIDENT" if self.overconfidence_ratio > 1.1 else (
            "UNDERCONFIDENT" if self.overconfidence_ratio < 0.9 else "CALIBRATED"
        )
        return (
            f"Brier={self.brier_score:.3f} "
            f"Log={self.log_score:.3f} "
            f"n={self.sample_size} "
            f"[{status}] [{conf}]"
        )


def brier_score(predictions: List[Tuple[float, int]]) -> float:
    """Compute Brier score for probability predictions.

    The Brier score measures the mean squared error between predicted
    probabilities and actual outcomes.

    Args:
        predictions: List of (predicted_probability, actual_outcome) tuples
                    predicted_probability: 0.0 to 1.0
                    actual_outcome: 1 if occurred, 0 if not

    Returns:
        Brier score (0.0 = perfect, 0.25 = random guessing on binary)

    Example:
        >>> brier_score([(0.9, 1), (0.1, 0), (0.8, 1)])
        0.02  # Very good predictions
        >>> brier_score([(0.5, 1), (0.5, 0)])
        0.25  # Random guessing
    """
    if not predictions:
        return 0.0

    total = 0.0
    for prob, outcome in predictions:
        # Clamp probability to valid range
        p = max(0.0, min(1.0, prob))
        o = 1 if outcome else 0
        total += (p - o) ** 2

    return total / len(predictions)


def log_score(predictions: List[Tuple[float, int]], epsilon: float = 1e-10) -> float:
    """Compute logarithmic scoring rule for predictions.

    The log score is more sensitive to confident wrong predictions than
    Brier score. It heavily penalizes high-probability predictions that
    turn out wrong.

    Args:
        predictions: List of (predicted_probability, actual_outcome) tuples
        epsilon: Small value to avoid log(0)

    Returns:
        Log score (lower is better, 0 = perfect)

    Note:
        A 99% confident wrong prediction scores -log(0.01) ≈ 4.6
        A 50% coin flip scores -log(0.5) ≈ 0.69
    """
    if not predictions:
        return 0.0

    total = 0.0
    for prob, outcome in predictions:
        # Clamp probability away from 0 and 1
        p = max(epsilon, min(1.0 - epsilon, prob))

        if outcome:
            total += -math.log(p)
        else:
            total += -math.log(1 - p)

    return total / len(predictions)


def calibration_error(predictions: List[Tuple[float, int]]) -> float:
    """Compute calibration error: |mean_predicted - actual_frequency|.

    A perfectly calibrated forecaster has calibration_error = 0.

    Args:
        predictions: List of (predicted_probability, actual_outcome) tuples

    Returns:
        Absolute calibration error
    """
    if not predictions:
        return 0.0

    mean_predicted = sum(p for p, _ in predictions) / len(predictions)
    actual_frequency = sum(o for _, o in predictions) / len(predictions)

    return abs(mean_predicted - actual_frequency)


def overconfidence_ratio(predictions: List[Tuple[float, int]]) -> float:
    """Compute overconfidence ratio: mean_predicted / actual_frequency.

    Returns:
        Ratio > 1.0 means overconfident (predicting higher than actuals)
        Ratio < 1.0 means underconfident
        Ratio = 1.0 means perfectly calibrated
    """
    if not predictions:
        return 1.0

    mean_predicted = sum(p for p, _ in predictions) / len(predictions)
    actual_frequency = sum(o for _, o in predictions) / len(predictions)

    if actual_frequency == 0:
        return float('inf') if mean_predicted > 0 else 1.0

    return mean_predicted / actual_frequency


def binned_calibration(
    predictions: List[Tuple[float, int]],
    n_bins: int = 10
) -> Dict[str, Dict]:
    """Compute binned calibration data for calibration curves.

    Groups predictions into bins by predicted probability, then compares
    mean predicted probability to actual frequency in each bin.

    Args:
        predictions: List of (predicted_probability, actual_outcome) tuples
        n_bins: Number of bins (default 10 for deciles)

    Returns:
        Dict mapping bin_name to {mean_predicted, actual_frequency, count}
    """
    bins = {i: [] for i in range(n_bins)}

    for prob, outcome in predictions:
        bin_idx = min(int(prob * n_bins), n_bins - 1)
        bins[bin_idx].append((prob, outcome))

    result = {}
    for i in range(n_bins):
        bin_name = f"{i/n_bins:.1f}-{(i+1)/n_bins:.1f}"
        if bins[i]:
            mean_pred = sum(p for p, _ in bins[i]) / len(bins[i])
            actual_freq = sum(o for _, o in bins[i]) / len(bins[i])
            result[bin_name] = {
                "mean_predicted": mean_pred,
                "actual_frequency": actual_freq,
                "count": len(bins[i]),
                "error": mean_pred - actual_freq,
            }
        else:
            result[bin_name] = {
                "mean_predicted": None,
                "actual_frequency": None,
                "count": 0,
                "error": None,
            }

    return result


def compute_calibration_metrics(
    predictions: List[Tuple[float, int]]
) -> CalibrationResult:
    """Compute full calibration metrics for a set of predictions.

    Args:
        predictions: List of (predicted_probability, actual_outcome) tuples

    Returns:
        CalibrationResult with all metrics
    """
    if not predictions:
        return CalibrationResult(
            brier_score=0.0,
            log_score=0.0,
            sample_size=0,
            mean_confidence=0.0,
            hit_rate=0.0,
            calibration_error=0.0,
            overconfidence_ratio=1.0,
            underconfidence_ratio=1.0,
        )

    bs = brier_score(predictions)
    ls = log_score(predictions)
    ce = calibration_error(predictions)
    over = overconfidence_ratio(predictions)
    under = 1.0 / over if over > 0 else float('inf')

    mean_conf = sum(p for p, _ in predictions) / len(predictions)
    hit_rate = sum(o for _, o in predictions) / len(predictions)

    bin_data = binned_calibration(predictions)

    return CalibrationResult(
        brier_score=bs,
        log_score=ls,
        sample_size=len(predictions),
        mean_confidence=mean_conf,
        hit_rate=hit_rate,
        calibration_error=ce,
        overconfidence_ratio=over,
        underconfidence_ratio=under,
        bin_data=bin_data,
    )


def score_scenario_tree(
    scenario_probs: Dict[str, float],
    actual_scenario: str
) -> Tuple[float, float]:
    """Score a scenario tree forecast when outcome is known.

    Converts multi-class scenario forecast to Brier/log scores.

    Args:
        scenario_probs: Dict mapping scenario_name to probability
                       e.g., {"base": 0.50, "bull": 0.25, "bear": 0.20, "tail": 0.05}
        actual_scenario: Which scenario actually occurred

    Returns:
        Tuple of (brier_score, log_score)

    Example:
        >>> probs = {"base": 0.50, "bull": 0.25, "bear": 0.20, "tail": 0.05}
        >>> score_scenario_tree(probs, "base")
        (0.375, 0.693)  # Base case occurred as predicted
    """
    if not scenario_probs:
        return (0.0, 0.0)

    # Normalize probabilities to sum to 1
    total_prob = sum(scenario_probs.values())
    if total_prob > 0:
        scenario_probs = {k: v / total_prob for k, v in scenario_probs.items()}

    # Brier score for multi-class: sum of (p - indicator)^2
    brier = 0.0
    for scenario, prob in scenario_probs.items():
        indicator = 1.0 if scenario == actual_scenario else 0.0
        brier += (prob - indicator) ** 2

    # Log score: -log(probability assigned to actual outcome)
    actual_prob = scenario_probs.get(actual_scenario, 1e-10)
    log_s = -math.log(max(actual_prob, 1e-10))

    return (brier, log_s)


def kelly_criterion(
    win_probability: float,
    win_return: float,
    loss_return: float = -1.0,
    fraction: float = 0.25
) -> float:
    """Compute Kelly criterion for position sizing.

    The Kelly criterion determines optimal bet size to maximize
    long-term geometric growth rate.

    Args:
        win_probability: Probability of winning (0 to 1)
        win_return: Return if win (e.g., 0.5 for 50% gain)
        loss_return: Return if loss (e.g., -1.0 for 100% loss)
        fraction: Fraction of full Kelly to use (0.25 = quarter Kelly)

    Returns:
        Optimal position size as fraction of bankroll (0 to 1)

    Example:
        >>> kelly_criterion(0.6, 1.0, -1.0, fraction=0.25)
        0.05  # 5% position size at quarter Kelly
    """
    if win_probability <= 0 or win_probability >= 1:
        return 0.0

    if win_return <= 0:
        return 0.0

    # Kelly formula: (p * b - q) / b
    # where p = win_probability, q = 1-p, b = win_return / |loss_return|
    p = win_probability
    q = 1 - p
    b = win_return / abs(loss_return) if loss_return != 0 else win_return

    kelly_full = (p * b - q) / b if b > 0 else 0.0

    # Apply fractional Kelly and clamp to [0, 1]
    kelly_fractional = kelly_full * fraction
    return max(0.0, min(1.0, kelly_fractional))


def expected_value(
    scenarios: List[Dict],
    return_key: str = "expected_return"
) -> float:
    """Compute expected value across weighted scenarios.

    Args:
        scenarios: List of dicts with 'probability' and return_key
        return_key: Key for expected return in each scenario

    Returns:
        Probability-weighted expected value

    Example:
        >>> scenarios = [
        ...     {"probability": 0.5, "expected_return": 0.10},
        ...     {"probability": 0.3, "expected_return": 0.25},
        ...     {"probability": 0.2, "expected_return": -0.15},
        ... ]
        >>> expected_value(scenarios)
        0.095  # 9.5% expected return
    """
    if not scenarios:
        return 0.0

    total = 0.0
    for scenario in scenarios:
        prob = scenario.get("probability", 0.0)
        ret = scenario.get(return_key, 0.0)
        total += prob * ret

    return total


class CalibrationTracker:
    """Track calibration over time for an agent.

    Usage:
        tracker = CalibrationTracker(db, "forecast-agent")
        tracker.record_forecast("thesis-123", {"base": 0.5, "bull": 0.3, "bear": 0.2})
        # ... later when outcome known ...
        tracker.resolve_forecast("thesis-123", "bull")
        metrics = tracker.get_calibration_metrics()
    """

    def __init__(self, db, agent_name: str):
        self.db = db
        self.agent_name = agent_name

    def record_forecast(
        self,
        thesis_id: str,
        scenario_probs: Dict[str, float],
        time_horizon: str = "90d",
        metadata: Optional[Dict] = None
    ) -> str:
        """Record a new forecast for later scoring.

        Returns:
            forecast_id
        """
        import uuid
        from datetime import datetime

        conn = self.db.connect()
        forecast_id = f"forecast-{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow().isoformat() + "Z"

        # Insert forecast
        conn.execute(
            """INSERT INTO forecasts
               (id, thesis_id, scenario_tree, time_horizon, created_at, agent_name, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                forecast_id,
                thesis_id,
                json.dumps(scenario_probs),
                time_horizon,
                now,
                self.agent_name,
                json.dumps(metadata or {}),
            )
        )

        # Insert individual scenario probabilities
        for scenario_name, prob in scenario_probs.items():
            conn.execute(
                """INSERT INTO forecast_probabilities
                   (forecast_id, scenario_name, predicted_probability)
                   VALUES (?, ?, ?)""",
                (forecast_id, scenario_name, prob)
            )

        conn.commit()
        return forecast_id

    def resolve_forecast(
        self,
        thesis_id: str,
        actual_outcome: str
    ) -> Optional[Tuple[float, float]]:
        """Resolve a forecast and compute scores.

        Returns:
            Tuple of (brier_score, log_score) or None if not found
        """
        conn = self.db.connect()
        now = datetime.utcnow().isoformat() + "Z"

        # Get the most recent unresolved forecast for this thesis
        row = conn.execute(
            """SELECT id, scenario_tree FROM forecasts
               WHERE thesis_id = ? AND resolved_at IS NULL
               ORDER BY created_at DESC LIMIT 1""",
            (thesis_id,)
        ).fetchone()

        if not row:
            return None

        forecast_id = row[0]
        scenario_probs = json.loads(row[1])

        # Compute scores
        brier, log_s = score_scenario_tree(scenario_probs, actual_outcome)

        # Update forecast
        conn.execute(
            """UPDATE forecasts SET
               resolved_at = ?, actual_outcome = ?, brier_score = ?, log_score = ?
               WHERE id = ?""",
            (now, actual_outcome, brier, log_s, forecast_id)
        )

        # Update individual probabilities
        for scenario_name in scenario_probs:
            occurred = 1 if scenario_name == actual_outcome else 0
            conn.execute(
                """UPDATE forecast_probabilities
                   SET occurred = ?
                   WHERE forecast_id = ? AND scenario_name = ?""",
                (occurred, forecast_id, scenario_name)
            )

        conn.commit()
        return (brier, log_s)

    def get_calibration_metrics(
        self,
        time_window: Optional[str] = None
    ) -> CalibrationResult:
        """Get calibration metrics for this agent.

        Args:
            time_window: Filter by time window ('30d', '90d', '1y', None for all)

        Returns:
            CalibrationResult with aggregate metrics
        """
        conn = self.db.connect()

        # Build time filter
        time_filter = ""
        if time_window == "30d":
            time_filter = "AND resolved_at > datetime('now', '-30 days')"
        elif time_window == "90d":
            time_filter = "AND resolved_at > datetime('now', '-90 days')"
        elif time_window == "1y":
            time_filter = "AND resolved_at > datetime('now', '-1 year')"

        # Get all resolved probability/outcome pairs
        rows = conn.execute(
            f"""SELECT predicted_probability, occurred
               FROM forecast_probabilities fp
               JOIN forecasts f ON fp.forecast_id = f.id
               WHERE f.agent_name = ? AND f.resolved_at IS NOT NULL
               AND fp.occurred IS NOT NULL
               {time_filter}""",
            (self.agent_name,)
        ).fetchall()

        predictions = [(row[0], row[1]) for row in rows]
        return compute_calibration_metrics(predictions)

    def update_rolling_metrics(self):
        """Update calibration_metrics table with current scores."""
        conn = self.db.connect()
        now = datetime.utcnow().isoformat() + "Z"

        for window in ["all_time", "30d", "90d", "1y"]:
            tw = None if window == "all_time" else window
            metrics = self.get_calibration_metrics(tw)

            conn.execute(
                """INSERT OR REPLACE INTO calibration_metrics
                   (agent_name, time_window, brier_score, log_score,
                    overconfidence_ratio, underconfidence_ratio, sample_size,
                    mean_confidence, hit_rate, calibration_error, computed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    self.agent_name,
                    window,
                    metrics.brier_score,
                    metrics.log_score,
                    metrics.overconfidence_ratio,
                    metrics.underconfidence_ratio,
                    metrics.sample_size,
                    metrics.mean_confidence,
                    metrics.hit_rate,
                    metrics.calibration_error,
                    now,
                )
            )

        conn.commit()
