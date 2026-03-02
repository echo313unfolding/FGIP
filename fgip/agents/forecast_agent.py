"""
FGIP Forecast Agent - Probability distributions and outcome forecasting.

Generates forecast objects with:
- P10/P50/P90 distributions (pessimistic/base/optimistic)
- Probability of loss
- Maximum drawdown estimates
- Time horizons
- Confidence intervals

This is the "quantified uncertainty" layer - not predictions, but ranges.

Safety rules:
- All forecasts include uncertainty ranges
- Never presents point estimates without ranges
- Calibration tracking built-in
- Not investment advice
"""

import json
import math
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fgip.analysis.provenance import DataProvenance



# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class Distribution:
    """Probability distribution for an outcome."""
    p10: float  # 10th percentile (pessimistic)
    p50: float  # 50th percentile (base case)
    p90: float  # 90th percentile (optimistic)
    unit: str   # %, $, bps, etc.


@dataclass
class ForecastObject:
    """Complete forecast for a thesis/position."""
    forecast_id: str
    thesis_id: str
    symbol: Optional[str]

    # Core distributions
    return_distribution: Distribution  # Expected returns
    drawdown_distribution: Distribution  # Max drawdown range

    # Probabilities
    probability_of_loss: float  # P(return < 0)
    probability_of_thesis: float  # P(thesis plays out)
    probability_of_timing: float  # P(within time horizon)

    # Time horizon
    time_horizon_days: int
    earliest_catalyst: Optional[str]
    latest_catalyst: Optional[str]

    # Confidence
    confidence_in_forecast: float  # Meta: how confident in these numbers
    data_quality_score: float  # Quality of inputs

    # Calibration
    prior_forecasts: int  # How many forecasts made before
    prior_accuracy: float  # Historical accuracy

    # Metadata
    created_at: str
    inputs: Dict[str, Any]
    methodology: str
    provenance: Optional[DataProvenance] = None  # Data source verification


@dataclass
class CalibrationRecord:
    """Track forecast accuracy over time."""
    forecast_id: str
    thesis_id: str
    predicted_p50: float
    predicted_range: Tuple[float, float]  # p10, p90
    actual_outcome: Optional[float]
    within_range: Optional[bool]
    resolved_at: Optional[str]


@dataclass
class Scenario:
    """A single scenario in a scenario tree."""
    id: str
    description: str
    probability: float  # 0.0 to 1.0
    confidence_interval: Tuple[float, float]  # e.g., (0.60, 0.80) for 70%
    time_horizon: str  # "30d", "90d", "1y"
    expected_return: float  # Expected return if this scenario occurs
    catalysts: List[str] = field(default_factory=list)  # What would trigger this
    evidence_for: List[str] = field(default_factory=list)  # claim_ids supporting
    evidence_against: List[str] = field(default_factory=list)  # claim_ids opposing


@dataclass
class ScenarioTree:
    """Complete scenario tree with probabilities that sum to 1.0."""
    thesis_id: str
    base_case: Scenario
    bull_case: Scenario
    bear_case: Scenario
    tail_risk: Scenario  # Low probability, high impact
    probability_sum: float  # Should sum to 1.0
    calibration_score: Optional[float] = None  # Brier score from past forecasts
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def validate(self) -> List[str]:
        """Validate scenario tree."""
        errors = []
        prob_sum = (self.base_case.probability + self.bull_case.probability +
                    self.bear_case.probability + self.tail_risk.probability)
        if abs(prob_sum - 1.0) > 0.01:
            errors.append(f"Probabilities sum to {prob_sum:.2f}, not 1.0")
        for scenario in [self.base_case, self.bull_case, self.bear_case, self.tail_risk]:
            if scenario.probability < 0 or scenario.probability > 1:
                errors.append(f"Scenario {scenario.id} has invalid probability {scenario.probability}")
        return errors

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "thesis_id": self.thesis_id,
            "base_case": {
                "id": self.base_case.id,
                "description": self.base_case.description,
                "probability": self.base_case.probability,
                "expected_return": self.base_case.expected_return,
                "catalysts": self.base_case.catalysts,
            },
            "bull_case": {
                "id": self.bull_case.id,
                "description": self.bull_case.description,
                "probability": self.bull_case.probability,
                "expected_return": self.bull_case.expected_return,
                "catalysts": self.bull_case.catalysts,
            },
            "bear_case": {
                "id": self.bear_case.id,
                "description": self.bear_case.description,
                "probability": self.bear_case.probability,
                "expected_return": self.bear_case.expected_return,
                "catalysts": self.bear_case.catalysts,
            },
            "tail_risk": {
                "id": self.tail_risk.id,
                "description": self.tail_risk.description,
                "probability": self.tail_risk.probability,
                "expected_return": self.tail_risk.expected_return,
                "catalysts": self.tail_risk.catalysts,
            },
            "probability_sum": self.probability_sum,
            "calibration_score": self.calibration_score,
            "created_at": self.created_at,
        }


# =============================================================================
# FORECAST CALCULATIONS
# =============================================================================

def estimate_return_distribution(
    conviction_level: int,
    thesis_confidence: float,
    market_confirmation: float,
    historical_vol: float = 0.30
) -> Distribution:
    """
    Estimate return distribution based on inputs.

    Args:
        conviction_level: 1-5 conviction score
        thesis_confidence: 0-1 confidence in thesis
        market_confirmation: 0-1 market tape confirmation
        historical_vol: Annualized volatility

    Returns:
        Distribution with P10/P50/P90
    """
    # Base case depends on conviction
    conviction_to_base = {
        1: 0.05,   # 5% base expectation
        2: 0.10,
        3: 0.15,
        4: 0.25,
        5: 0.40
    }
    base_return = conviction_to_base.get(conviction_level, 0.10)

    # Adjust for confidence
    base_return *= thesis_confidence

    # Market confirmation narrows the range
    range_mult = 1.0 - (market_confirmation * 0.3)

    # Build distribution using vol
    p50 = base_return
    p10 = base_return - (historical_vol * range_mult * 1.28)  # ~10th percentile
    p90 = base_return + (historical_vol * range_mult * 1.28)  # ~90th percentile

    return Distribution(
        p10=round(p10 * 100, 1),
        p50=round(p50 * 100, 1),
        p90=round(p90 * 100, 1),
        unit="%"
    )


def estimate_drawdown_distribution(
    position_size_pct: float,
    historical_vol: float = 0.30,
    leverage: float = 1.0
) -> Distribution:
    """
    Estimate max drawdown distribution.

    Args:
        position_size_pct: Position size as % of portfolio
        historical_vol: Annualized volatility
        leverage: Position leverage

    Returns:
        Distribution of max drawdown (negative numbers)
    """
    # Base drawdown from vol and position
    base_dd = historical_vol * position_size_pct * leverage * 2  # 2-sigma base

    p10 = -base_dd * 2.5  # Bad case
    p50 = -base_dd
    p90 = -base_dd * 0.4  # Good case (smaller drawdown)

    return Distribution(
        p10=round(p10 * 100, 1),
        p50=round(p50 * 100, 1),
        p90=round(p90 * 100, 1),
        unit="%"
    )


def calculate_probability_of_loss(return_dist: Distribution) -> float:
    """
    Calculate probability of negative return from distribution.

    Assumes roughly normal distribution between P10 and P90.
    """
    if return_dist.p10 >= 0:
        return 0.0
    if return_dist.p90 <= 0:
        return 1.0

    # Linear interpolation (approximation)
    range_width = return_dist.p90 - return_dist.p10
    if range_width == 0:
        return 0.5

    # Where does 0 fall in the range?
    zero_position = (0 - return_dist.p10) / range_width

    # Convert to probability (P10 = 10%, P90 = 90%)
    prob_below_zero = 0.10 + (zero_position * 0.80)

    return round(min(max(prob_below_zero, 0.0), 1.0), 2)


# =============================================================================
# FORECAST AGENT
# =============================================================================

class ForecastAgent:
    """
    Generate quantified forecasts with probability distributions.

    Key outputs:
    - P10/P50/P90 return ranges
    - Probability of loss
    - Max drawdown estimates
    - Time horizon expectations
    """

    AGENT_NAME = "forecast"
    TIER = 3  # Derived from other data

    def __init__(self, db_path: str = "fgip.db"):
        """Initialize with database path."""
        self.db_path = Path(db_path)
        self._ensure_tables()

    def _get_db(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self):
        """Create forecast tables if needed."""
        conn = self._get_db()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS forecasts (
                    forecast_id TEXT PRIMARY KEY,
                    thesis_id TEXT,
                    symbol TEXT,
                    return_p10 REAL,
                    return_p50 REAL,
                    return_p90 REAL,
                    drawdown_p10 REAL,
                    drawdown_p50 REAL,
                    drawdown_p90 REAL,
                    probability_of_loss REAL,
                    probability_of_thesis REAL,
                    probability_of_timing REAL,
                    time_horizon_days INTEGER,
                    confidence_in_forecast REAL,
                    data_quality_score REAL,
                    inputs_json TEXT,
                    methodology TEXT,
                    created_at TEXT,
                    resolved_at TEXT,
                    actual_outcome REAL
                );

                CREATE TABLE IF NOT EXISTS calibration_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    forecast_id TEXT,
                    predicted_p50 REAL,
                    predicted_p10 REAL,
                    predicted_p90 REAL,
                    actual_outcome REAL,
                    within_range INTEGER,
                    resolved_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_forecasts_thesis ON forecasts(thesis_id);
            """)
            conn.commit()
        finally:
            conn.close()

    def generate_forecast(
        self,
        thesis_id: str,
        symbol: Optional[str] = None,
        conviction_level: int = 3,
        thesis_confidence: float = 0.5,
        market_confirmation: float = 0.5,
        position_size_pct: float = 0.05,
        time_horizon_days: int = 90,
        historical_vol: float = 0.30,
        earliest_catalyst: Optional[str] = None,
        latest_catalyst: Optional[str] = None,
        inputs: Optional[Dict[str, Any]] = None
    ) -> ForecastObject:
        """
        Generate a complete forecast object.

        Args:
            thesis_id: ID of the thesis being forecasted
            symbol: Optional ticker symbol
            conviction_level: 1-5 conviction
            thesis_confidence: 0-1 confidence in thesis truth
            market_confirmation: 0-1 tape confirmation score
            position_size_pct: Position as % of portfolio
            time_horizon_days: Expected time for thesis to play out
            historical_vol: Annualized volatility
            earliest_catalyst: Earliest expected catalyst
            latest_catalyst: Latest expected catalyst
            inputs: Additional input data

        Returns:
            ForecastObject with full distribution
        """
        # Generate distributions
        return_dist = estimate_return_distribution(
            conviction_level=conviction_level,
            thesis_confidence=thesis_confidence,
            market_confirmation=market_confirmation,
            historical_vol=historical_vol
        )

        drawdown_dist = estimate_drawdown_distribution(
            position_size_pct=position_size_pct,
            historical_vol=historical_vol
        )

        # Calculate probabilities
        prob_loss = calculate_probability_of_loss(return_dist)

        # Probability of thesis depends on confidence and triangulation
        prob_thesis = thesis_confidence * 0.8  # Discount for uncertainty

        # Probability of timing is harder - use conviction as proxy
        prob_timing = 0.5 + (conviction_level - 3) * 0.1

        # Data quality based on inputs
        data_quality = self._assess_data_quality(inputs or {})

        # Get prior calibration
        prior_forecasts, prior_accuracy = self._get_calibration_stats(thesis_id)

        # Confidence in this forecast
        confidence = (data_quality * 0.4 + min(prior_forecasts / 10, 1.0) * 0.2 +
                     market_confirmation * 0.2 + thesis_confidence * 0.2)

        forecast_id = f"forecast-{thesis_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        forecast = ForecastObject(
            forecast_id=forecast_id,
            thesis_id=thesis_id,
            symbol=symbol,
            return_distribution=return_dist,
            drawdown_distribution=drawdown_dist,
            probability_of_loss=prob_loss,
            probability_of_thesis=round(prob_thesis, 2),
            probability_of_timing=round(prob_timing, 2),
            time_horizon_days=time_horizon_days,
            earliest_catalyst=earliest_catalyst,
            latest_catalyst=latest_catalyst,
            confidence_in_forecast=round(confidence, 2),
            data_quality_score=round(data_quality, 2),
            prior_forecasts=prior_forecasts,
            prior_accuracy=prior_accuracy,
            created_at=datetime.now().isoformat(),
            inputs=inputs or {},
            methodology="conviction_adjusted_distribution_v1"
        )

        # Store forecast
        self._store_forecast(forecast)

        # Set provenance after storing (DB is source of truth)
        forecast.provenance = DataProvenance(
            source_type="forecast_db",
            source_ref=forecast_id,
            retrieved_at=forecast.created_at,
            content_hash=None,  # DB row is the source of truth
            notes=f"Stored in forecasts table, methodology={forecast.methodology}"
        )

        return forecast

    def _assess_data_quality(self, inputs: Dict[str, Any]) -> float:
        """Assess quality of input data."""
        score = 0.5  # Base score

        # Bonus for tier-0 sources
        if inputs.get("tier_0_sources", 0) > 0:
            score += 0.2

        # Bonus for triangulation
        if inputs.get("source_types", 0) >= 3:
            score += 0.15

        # Bonus for recent data
        if inputs.get("data_age_days", 30) < 7:
            score += 0.1

        # Penalty for single source
        if inputs.get("source_count", 1) == 1:
            score -= 0.2

        return min(max(score, 0.1), 1.0)

    def _get_calibration_stats(self, thesis_id: str) -> Tuple[int, float]:
        """Get historical calibration for similar forecasts."""
        conn = self._get_db()
        try:
            # Count prior forecasts
            row = conn.execute("""
                SELECT COUNT(*) as cnt
                FROM forecasts
                WHERE thesis_id = ? AND resolved_at IS NOT NULL
            """, (thesis_id,)).fetchone()

            prior_count = row['cnt'] if row else 0

            # Calculate accuracy (% within P10-P90 range)
            if prior_count > 0:
                row = conn.execute("""
                    SELECT AVG(CASE
                        WHEN actual_outcome >= return_p10 AND actual_outcome <= return_p90 THEN 1
                        ELSE 0
                    END) as accuracy
                    FROM forecasts
                    WHERE thesis_id = ? AND resolved_at IS NOT NULL
                """, (thesis_id,)).fetchone()
                accuracy = row['accuracy'] if row and row['accuracy'] else 0.8
            else:
                accuracy = 0.8  # Prior assumption: 80% calibration

            return prior_count, round(accuracy, 2)
        finally:
            conn.close()

    def _store_forecast(self, forecast: ForecastObject):
        """Store forecast in database."""
        conn = self._get_db()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO forecasts (
                    forecast_id, thesis_id, symbol,
                    return_p10, return_p50, return_p90,
                    drawdown_p10, drawdown_p50, drawdown_p90,
                    probability_of_loss, probability_of_thesis, probability_of_timing,
                    time_horizon_days, confidence_in_forecast, data_quality_score,
                    inputs_json, methodology, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                forecast.forecast_id, forecast.thesis_id, forecast.symbol,
                forecast.return_distribution.p10, forecast.return_distribution.p50,
                forecast.return_distribution.p90,
                forecast.drawdown_distribution.p10, forecast.drawdown_distribution.p50,
                forecast.drawdown_distribution.p90,
                forecast.probability_of_loss, forecast.probability_of_thesis,
                forecast.probability_of_timing,
                forecast.time_horizon_days, forecast.confidence_in_forecast,
                forecast.data_quality_score,
                json.dumps(forecast.inputs), forecast.methodology, forecast.created_at
            ))
            conn.commit()
        finally:
            conn.close()

    def resolve_forecast(
        self,
        forecast_id: str,
        actual_outcome: float
    ) -> CalibrationRecord:
        """
        Resolve a forecast with actual outcome for calibration.

        Args:
            forecast_id: ID of forecast to resolve
            actual_outcome: Actual return achieved

        Returns:
            CalibrationRecord with accuracy assessment
        """
        conn = self._get_db()
        try:
            row = conn.execute("""
                SELECT * FROM forecasts WHERE forecast_id = ?
            """, (forecast_id,)).fetchone()

            if not row:
                raise ValueError(f"Forecast {forecast_id} not found")

            within_range = row['return_p10'] <= actual_outcome <= row['return_p90']

            # Update forecast
            conn.execute("""
                UPDATE forecasts
                SET resolved_at = ?, actual_outcome = ?
                WHERE forecast_id = ?
            """, (datetime.now().isoformat(), actual_outcome, forecast_id))

            # Log calibration
            conn.execute("""
                INSERT INTO calibration_log (
                    forecast_id, predicted_p50, predicted_p10, predicted_p90,
                    actual_outcome, within_range, resolved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                forecast_id, row['return_p50'], row['return_p10'], row['return_p90'],
                actual_outcome, 1 if within_range else 0, datetime.now().isoformat()
            ))

            conn.commit()

            return CalibrationRecord(
                forecast_id=forecast_id,
                thesis_id=row['thesis_id'],
                predicted_p50=row['return_p50'],
                predicted_range=(row['return_p10'], row['return_p90']),
                actual_outcome=actual_outcome,
                within_range=within_range,
                resolved_at=datetime.now().isoformat()
            )
        finally:
            conn.close()

    def get_calibration_report(self) -> Dict[str, Any]:
        """Get overall calibration statistics."""
        conn = self._get_db()
        try:
            rows = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(within_range) as correct,
                    AVG(ABS(actual_outcome - predicted_p50)) as avg_error
                FROM calibration_log
            """).fetchone()

            if not rows or rows['total'] == 0:
                return {
                    "total_resolved": 0,
                    "calibration_rate": None,
                    "average_error": None,
                    "status": "No resolved forecasts yet"
                }

            return {
                "total_resolved": rows['total'],
                "calibration_rate": round(rows['correct'] / rows['total'], 2),
                "average_error": round(rows['avg_error'], 2) if rows['avg_error'] else None,
                "status": "Calibration tracking active"
            }
        finally:
            conn.close()

    def generate_scenario_tree(
        self,
        thesis_id: str,
        base_probability: float = 0.50,
        bull_probability: float = 0.25,
        bear_probability: float = 0.20,
        tail_probability: float = 0.05,
        base_return: float = 0.10,
        bull_return: float = 0.30,
        bear_return: float = -0.15,
        tail_return: float = -0.50,
        time_horizon: str = "90d",
        catalysts: Optional[Dict[str, List[str]]] = None,
    ) -> ScenarioTree:
        """
        Generate a scenario tree with calibrated probabilities.

        Args:
            thesis_id: ID of the thesis
            base_probability: P(base case) - thesis plays out as expected
            bull_probability: P(bull case) - better than expected
            bear_probability: P(bear case) - worse than expected
            tail_probability: P(tail risk) - catastrophic outcome
            base_return: Expected return in base case
            bull_return: Expected return in bull case
            bear_return: Expected return in bear case
            tail_return: Expected return in tail risk
            time_horizon: "30d", "90d", "1y"
            catalysts: Dict mapping scenario to list of catalysts

        Returns:
            ScenarioTree with validated probabilities
        """
        catalysts = catalysts or {}

        # Normalize probabilities to sum to 1.0
        total_prob = base_probability + bull_probability + bear_probability + tail_probability
        if total_prob != 1.0:
            base_probability /= total_prob
            bull_probability /= total_prob
            bear_probability /= total_prob
            tail_probability /= total_prob

        # Get historical calibration score
        calibration_score = self._get_brier_score(thesis_id)

        tree = ScenarioTree(
            thesis_id=thesis_id,
            base_case=Scenario(
                id=f"{thesis_id}-base",
                description="Thesis plays out as expected",
                probability=base_probability,
                confidence_interval=(base_probability * 0.8, min(1.0, base_probability * 1.2)),
                time_horizon=time_horizon,
                expected_return=base_return,
                catalysts=catalysts.get("base", []),
            ),
            bull_case=Scenario(
                id=f"{thesis_id}-bull",
                description="Better than expected - catalysts accelerate",
                probability=bull_probability,
                confidence_interval=(bull_probability * 0.7, min(1.0, bull_probability * 1.3)),
                time_horizon=time_horizon,
                expected_return=bull_return,
                catalysts=catalysts.get("bull", []),
            ),
            bear_case=Scenario(
                id=f"{thesis_id}-bear",
                description="Worse than expected - headwinds materialize",
                probability=bear_probability,
                confidence_interval=(bear_probability * 0.7, min(1.0, bear_probability * 1.3)),
                time_horizon=time_horizon,
                expected_return=bear_return,
                catalysts=catalysts.get("bear", []),
            ),
            tail_risk=Scenario(
                id=f"{thesis_id}-tail",
                description="Catastrophic outcome - thesis invalidated",
                probability=tail_probability,
                confidence_interval=(0.01, tail_probability * 2),
                time_horizon=time_horizon,
                expected_return=tail_return,
                catalysts=catalysts.get("tail", []),
            ),
            probability_sum=1.0,
            calibration_score=calibration_score,
        )

        # Validate
        errors = tree.validate()
        if errors:
            raise ValueError(f"Invalid scenario tree: {errors}")

        # Store in database
        self._store_scenario_tree(tree)

        return tree

    def _get_brier_score(self, thesis_id: str) -> Optional[float]:
        """Get historical Brier score for this thesis type."""
        conn = self._get_db()
        try:
            # Check if calibration_metrics table exists
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='calibration_metrics'"
            ).fetchone()

            if not tables:
                return None

            row = conn.execute("""
                SELECT brier_score FROM calibration_metrics
                WHERE agent_name = 'forecast-agent'
                ORDER BY computed_at DESC LIMIT 1
            """).fetchone()

            return row['brier_score'] if row else None
        except:
            return None
        finally:
            conn.close()

    def _store_scenario_tree(self, tree: ScenarioTree):
        """Store scenario tree in forecasts table."""
        conn = self._get_db()
        try:
            # Check if the new forecasts schema exists
            cols = conn.execute("PRAGMA table_info(forecasts)").fetchall()
            col_names = [c[1] for c in cols]

            if "scenario_tree" in col_names:
                # Schema with scenario_tree column added
                forecast_id = f"tree-{tree.thesis_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                # Use forecast_id as primary key (existing schema)
                conn.execute("""
                    INSERT OR REPLACE INTO forecasts (
                        forecast_id, thesis_id, scenario_tree, time_horizon,
                        created_at, agent_name, inputs_json, methodology
                    ) VALUES (?, ?, ?, ?, ?, 'forecast-agent', ?, 'scenario_tree_v1')
                """, (
                    forecast_id,
                    tree.thesis_id,
                    json.dumps(tree.to_dict()),
                    tree.base_case.time_horizon,
                    tree.created_at,
                    json.dumps(tree.to_dict()),  # Also store in inputs_json for compatibility
                ))
            else:
                # Legacy schema - store in existing columns
                forecast_id = f"tree-{tree.thesis_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                conn.execute("""
                    INSERT OR REPLACE INTO forecasts (
                        forecast_id, thesis_id,
                        return_p10, return_p50, return_p90,
                        probability_of_thesis, probability_of_timing,
                        time_horizon_days, confidence_in_forecast,
                        inputs_json, methodology, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    forecast_id, tree.thesis_id,
                    tree.tail_risk.expected_return * 100,  # P10 ~ tail
                    tree.base_case.expected_return * 100,  # P50 ~ base
                    tree.bull_case.expected_return * 100,  # P90 ~ bull
                    tree.base_case.probability,
                    1.0 - tree.tail_risk.probability,  # P(not tail)
                    int(tree.base_case.time_horizon.replace("d", "").replace("y", "365")),
                    tree.calibration_score or 0.5,
                    json.dumps(tree.to_dict()),
                    "scenario_tree_v1",
                    tree.created_at,
                ))

            conn.commit()
        finally:
            conn.close()

    def expected_value(self, tree: ScenarioTree) -> float:
        """Calculate expected value across scenario tree."""
        return (
            tree.base_case.probability * tree.base_case.expected_return +
            tree.bull_case.probability * tree.bull_case.expected_return +
            tree.bear_case.probability * tree.bear_case.expected_return +
            tree.tail_risk.probability * tree.tail_risk.expected_return
        )

# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import sys

    agent = ForecastAgent()

    if len(sys.argv) > 1:
        cmd = sys.argv[1]

        if cmd == "generate":
            # Example: python -m fgip.agents.forecast_agent generate test-thesis INTC 4
            thesis_id = sys.argv[2] if len(sys.argv) > 2 else "test-thesis"
            symbol = sys.argv[3] if len(sys.argv) > 3 else None
            conviction = int(sys.argv[4]) if len(sys.argv) > 4 else 3

            forecast = agent.generate_forecast(
                thesis_id=thesis_id,
                symbol=symbol,
                conviction_level=conviction,
                thesis_confidence=0.7,
                market_confirmation=0.6,
                time_horizon_days=90
            )

            print(f"\n=== Forecast: {forecast.forecast_id} ===")
            print(f"Thesis: {forecast.thesis_id}")
            if forecast.symbol:
                print(f"Symbol: {forecast.symbol}")
            print(f"\nReturn Distribution:")
            print(f"  P10 (pessimistic): {forecast.return_distribution.p10}%")
            print(f"  P50 (base case):   {forecast.return_distribution.p50}%")
            print(f"  P90 (optimistic):  {forecast.return_distribution.p90}%")
            print(f"\nMax Drawdown Distribution:")
            print(f"  P10 (worst):  {forecast.drawdown_distribution.p10}%")
            print(f"  P50 (likely): {forecast.drawdown_distribution.p50}%")
            print(f"  P90 (best):   {forecast.drawdown_distribution.p90}%")
            print(f"\nProbabilities:")
            print(f"  P(loss):   {forecast.probability_of_loss:.0%}")
            print(f"  P(thesis): {forecast.probability_of_thesis:.0%}")
            print(f"  P(timing): {forecast.probability_of_timing:.0%}")
            print(f"\nConfidence: {forecast.confidence_in_forecast:.0%}")
            print(f"Data Quality: {forecast.data_quality_score:.0%}")
            print(f"Time Horizon: {forecast.time_horizon_days} days")

        elif cmd == "calibration":
            report = agent.get_calibration_report()
            print("\n=== Calibration Report ===")
            for k, v in report.items():
                print(f"  {k}: {v}")

        else:
            print(f"Unknown command: {cmd}")

    else:
        print("Usage:")
        print("  python -m fgip.agents.forecast_agent generate [thesis_id] [symbol] [conviction]")
        print("  python -m fgip.agents.forecast_agent calibration")
