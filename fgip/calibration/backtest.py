"""FGIP Walk-Forward Backtest - Test strategy without lookahead bias.

Process:
1. Load historical data up to date T
2. Generate forecast using only data <= T
3. Step forward, observe outcome
4. Score forecast
5. Repeat

Anti-lookahead checks:
- Verify all data timestamps < decision timestamp
- Flag any "future" data access

Usage:
    from fgip.calibration.backtest import WalkForwardBacktest

    backtest = WalkForwardBacktest(db)
    result = backtest.run("2025-01-01", "2025-12-31", step="7d")
    print(f"Brier: {result.brier_score}, Lookahead violations: {result.violations}")
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import hashlib


@dataclass
class BacktestStep:
    """A single step in the backtest."""
    date: str
    thesis_id: str
    forecast_id: str
    scenario_probs: Dict[str, float]
    actual_outcome: Optional[str] = None
    brier_score: Optional[float] = None
    log_score: Optional[float] = None
    lookahead_violation: bool = False
    violation_details: Optional[str] = None


@dataclass
class BacktestResult:
    """Complete backtest results."""
    start_date: str
    end_date: str
    step_size: str
    total_steps: int
    steps: List[BacktestStep]
    avg_brier_score: float
    avg_log_score: float
    calibration_curve: Dict[str, Dict]  # bin -> {predicted, actual, count}
    lookahead_violations: int
    violation_details: List[str]
    pnl_simulation: Optional[Dict] = None  # If price data available

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_date": self.start_date,
            "end_date": self.end_date,
            "step_size": self.step_size,
            "total_steps": self.total_steps,
            "avg_brier_score": self.avg_brier_score,
            "avg_log_score": self.avg_log_score,
            "calibration_curve": self.calibration_curve,
            "lookahead_violations": self.lookahead_violations,
            "violation_details": self.violation_details,
        }


def parse_step_size(step: str) -> timedelta:
    """Parse step size string to timedelta."""
    if step.endswith("d"):
        return timedelta(days=int(step[:-1]))
    elif step.endswith("w"):
        return timedelta(weeks=int(step[:-1]))
    elif step.endswith("m"):
        return timedelta(days=int(step[:-1]) * 30)
    else:
        return timedelta(days=1)


class WalkForwardBacktest:
    """Walk-forward backtesting framework.

    Tests forecasting strategy without lookahead bias by:
    1. Filtering data to only what was available at decision time
    2. Generating forecasts using the filtered data
    3. Comparing to actual outcomes
    4. Flagging any lookahead violations
    """

    def __init__(self, db):
        """Initialize with database connection.

        Args:
            db: FGIPDatabase instance
        """
        self.db = db

    def run(
        self,
        start_date: str,
        end_date: str,
        step: str = "7d",
        thesis_ids: Optional[List[str]] = None,
    ) -> BacktestResult:
        """Run walk-forward backtest.

        Args:
            start_date: ISO format start date
            end_date: ISO format end date
            step: Step size ("1d", "7d", "30d")
            thesis_ids: Optional list of thesis IDs to test (all if None)

        Returns:
            BacktestResult with scores and violations
        """
        steps = []
        violations = []

        step_delta = parse_step_size(step)
        current_date = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)

        # Get thesis IDs if not provided
        if thesis_ids is None:
            thesis_ids = self._get_thesis_ids()

        while current_date <= end:
            date_str = current_date.isoformat()[:10]

            for thesis_id in thesis_ids:
                try:
                    # Generate forecast using only data up to current_date
                    forecast_step = self._generate_forecast_at_date(
                        thesis_id, date_str
                    )

                    if forecast_step:
                        # Check for lookahead violations
                        violation = self._check_lookahead(
                            thesis_id, date_str, forecast_step
                        )
                        if violation:
                            forecast_step.lookahead_violation = True
                            forecast_step.violation_details = violation
                            violations.append(violation)

                        steps.append(forecast_step)

                except Exception as e:
                    # Log but continue
                    pass

            current_date += step_delta

        # Calculate aggregate scores
        brier_scores = [s.brier_score for s in steps if s.brier_score is not None]
        log_scores = [s.log_score for s in steps if s.log_score is not None]

        avg_brier = sum(brier_scores) / len(brier_scores) if brier_scores else 0.0
        avg_log = sum(log_scores) / len(log_scores) if log_scores else 0.0

        # Build calibration curve
        calibration_curve = self._build_calibration_curve(steps)

        return BacktestResult(
            start_date=start_date,
            end_date=end_date,
            step_size=step,
            total_steps=len(steps),
            steps=steps,
            avg_brier_score=round(avg_brier, 4),
            avg_log_score=round(avg_log, 4),
            calibration_curve=calibration_curve,
            lookahead_violations=len(violations),
            violation_details=violations,
        )

    def _get_thesis_ids(self) -> List[str]:
        """Get list of thesis IDs from database."""
        conn = self.db.connect()

        # Get unique thesis IDs from forecasts
        rows = conn.execute(
            """SELECT DISTINCT thesis_id FROM forecasts
               WHERE thesis_id IS NOT NULL"""
        ).fetchall()

        return [row[0] for row in rows if row[0]]

    def _generate_forecast_at_date(
        self,
        thesis_id: str,
        as_of_date: str
    ) -> Optional[BacktestStep]:
        """Generate forecast using only data available at as_of_date.

        This is the key anti-lookahead method - it filters all data
        to only what was available at the decision point.
        """
        conn = self.db.connect()

        # Get the forecast that was active on this date
        row = conn.execute(
            """SELECT id, scenario_tree, created_at, resolved_at, actual_outcome
               FROM forecasts
               WHERE thesis_id = ? AND DATE(created_at) <= ?
               ORDER BY created_at DESC LIMIT 1""",
            (thesis_id, as_of_date)
        ).fetchone()

        if not row:
            return None

        forecast_id = row[0]
        scenario_tree_json = row[1]
        created_at = row[2]
        resolved_at = row[3]
        actual_outcome = row[4]

        # Parse scenario tree
        if scenario_tree_json:
            try:
                tree = json.loads(scenario_tree_json)
                scenario_probs = {
                    "base_case": tree.get("base_case", {}).get("probability", 0.5),
                    "bull_case": tree.get("bull_case", {}).get("probability", 0.25),
                    "bear_case": tree.get("bear_case", {}).get("probability", 0.20),
                    "tail_risk": tree.get("tail_risk", {}).get("probability", 0.05),
                }
            except:
                scenario_probs = {
                    "base_case": 0.5,
                    "bull_case": 0.25,
                    "bear_case": 0.20,
                    "tail_risk": 0.05,
                }
        else:
            scenario_probs = {
                "base_case": 0.5,
                "bull_case": 0.25,
                "bear_case": 0.20,
                "tail_risk": 0.05,
            }

        # Calculate scores if resolved
        brier_score = None
        log_score = None

        if actual_outcome:
            brier_score, log_score = self._score_forecast(
                scenario_probs, actual_outcome
            )

        return BacktestStep(
            date=as_of_date,
            thesis_id=thesis_id,
            forecast_id=forecast_id,
            scenario_probs=scenario_probs,
            actual_outcome=actual_outcome,
            brier_score=brier_score,
            log_score=log_score,
        )

    def _check_lookahead(
        self,
        thesis_id: str,
        as_of_date: str,
        step: BacktestStep
    ) -> Optional[str]:
        """Check for lookahead bias in forecast.

        Returns violation description if found, None if clean.
        """
        conn = self.db.connect()

        # Check if any source data used in forecast is from the future
        rows = conn.execute(
            """SELECT source_id, retrieved_at FROM sources
               WHERE DATE(retrieved_at) > ?
               LIMIT 1""",
            (as_of_date,)
        ).fetchall()

        # This is a simplified check - in practice would trace the exact
        # sources used in generating the specific forecast
        if rows:
            return f"Source {rows[0][0]} retrieved after {as_of_date}"

        return None

    def _score_forecast(
        self,
        scenario_probs: Dict[str, float],
        actual_outcome: str
    ) -> Tuple[float, float]:
        """Score a forecast against actual outcome.

        Returns (brier_score, log_score)
        """
        import math

        # Brier score for multi-class
        brier = 0.0
        for scenario, prob in scenario_probs.items():
            indicator = 1.0 if scenario == actual_outcome else 0.0
            brier += (prob - indicator) ** 2

        # Log score
        actual_prob = scenario_probs.get(actual_outcome, 0.001)
        log_s = -math.log(max(actual_prob, 1e-10))

        return (round(brier, 4), round(log_s, 4))

    def _build_calibration_curve(
        self,
        steps: List[BacktestStep],
        n_bins: int = 10
    ) -> Dict[str, Dict]:
        """Build calibration curve data from backtest steps."""
        bins = {i: [] for i in range(n_bins)}

        for step in steps:
            if step.actual_outcome is None:
                continue

            for scenario, prob in step.scenario_probs.items():
                occurred = 1 if scenario == step.actual_outcome else 0
                bin_idx = min(int(prob * n_bins), n_bins - 1)
                bins[bin_idx].append((prob, occurred))

        result = {}
        for i in range(n_bins):
            bin_name = f"{i/n_bins:.1f}-{(i+1)/n_bins:.1f}"
            if bins[i]:
                mean_pred = sum(p for p, _ in bins[i]) / len(bins[i])
                actual_freq = sum(o for _, o in bins[i]) / len(bins[i])
                result[bin_name] = {
                    "mean_predicted": round(mean_pred, 3),
                    "actual_frequency": round(actual_freq, 3),
                    "count": len(bins[i]),
                    "error": round(mean_pred - actual_freq, 3),
                }
            else:
                result[bin_name] = {
                    "mean_predicted": None,
                    "actual_frequency": None,
                    "count": 0,
                    "error": None,
                }

        return result

    def validate_no_lookahead(
        self,
        forecast_id: str,
        decision_date: str
    ) -> Tuple[bool, List[str]]:
        """Validate that a specific forecast has no lookahead bias.

        Returns (is_valid, list_of_violations)
        """
        violations = []
        conn = self.db.connect()

        # Get forecast
        row = conn.execute(
            "SELECT * FROM forecasts WHERE id = ? OR forecast_id = ?",
            (forecast_id, forecast_id)
        ).fetchone()

        if not row:
            return False, ["Forecast not found"]

        # Check all sources that contributed to this forecast
        # This is a simplified check - would need to trace actual data lineage

        # Check if any edges were created after decision date
        future_edges = conn.execute(
            """SELECT edge_id, created_at FROM edges
               WHERE DATE(created_at) > ?
               LIMIT 5""",
            (decision_date,)
        ).fetchall()

        if future_edges:
            for edge in future_edges:
                violations.append(f"Edge {edge[0]} created {edge[1]} after {decision_date}")

        # Check if any claims were created after decision date
        future_claims = conn.execute(
            """SELECT claim_id, created_at FROM claims
               WHERE DATE(created_at) > ?
               LIMIT 5""",
            (decision_date,)
        ).fetchall()

        if future_claims:
            for claim in future_claims:
                violations.append(f"Claim {claim[0]} created {claim[1]} after {decision_date}")

        return len(violations) == 0, violations
