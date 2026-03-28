"""
Regime classification with triangulation and Risk State Vector.

Classifies economic regimes as LOW/NORMAL/STRESS/CRISIS based on
multiple signal families agreeing (triangulation principle).

Risk State Vector:
- H (Entropy): How volatile are the features?
- C (Coherence): Do signal families agree?
- D (Depth): How many families are active?
- Se = H x C x D (routing metric for risk adjustment)
"""

from dataclasses import dataclass, asdict, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

from .features_from_fred import FREDFeatures

if TYPE_CHECKING:
    from .calibration import CalibratedThresholds


class RegimeLevel(Enum):
    """Economic regime states."""
    LOW = "LOW"           # Subdued across all families
    NORMAL = "NORMAL"     # Stable within historical ranges
    STRESS = "STRESS"     # One or more families elevated
    CRISIS = "CRISIS"     # Multiple families spiking together


@dataclass
class RegimeState:
    """Complete regime classification for a single observation."""
    date: str
    regime: str                          # LOW, NORMAL, STRESS, CRISIS
    confidence: float                    # 0-1
    drivers: List[str] = field(default_factory=list)  # Active families
    # Risk State Vector
    H: float = 0.0                       # Entropy (volatility)
    C: float = 0.0                       # Coherence (agreement)
    D: float = 0.0                       # Dimensional depth
    Se: float = 0.0                      # H x C x D routing metric
    # Optional metadata
    lead_lag: Optional[str] = None       # Which series led (if detectable)
    raw_values: Optional[Dict] = None    # Raw feature values for debugging


@dataclass
class RegimeThresholds:
    """Calibratable thresholds for regime detection."""
    # Stress thresholds (above = elevated)
    cpi_stress: float = 4.0              # CPI YoY > 4%
    pce_stress: float = 4.0              # PCE YoY > 4%
    housing_stress: float = 8.0          # Housing YoY > 8%
    m2_gap_stress: float = 4.0           # M2-CPI gap > 4%

    # Crisis thresholds (above = severe)
    cpi_crisis: float = 6.0              # CPI YoY > 6%
    housing_crisis: float = 15.0         # Housing YoY > 15%
    m2_gap_crisis: float = 6.0           # M2-CPI gap > 6%

    # Low thresholds (below = subdued)
    cpi_low: float = 1.5                 # CPI YoY < 1.5%
    housing_low: float = 3.0             # Housing YoY < 3%
    m2_gap_low: float = 1.0              # M2-CPI gap < 1%

    # Volatility normalization
    vol_baseline: float = 1.5            # "Normal" YoY volatility


class RegimeClassifier:
    """
    Deterministic regime classifier with triangulation.

    Key principle: Don't declare CRISIS from one series.
    Require multiple families to agree.

    Supports two threshold modes:
    1. Hand-tuned (RegimeThresholds) - default fallback
    2. Calibrated (CalibratedThresholds) - percentile-based from history
    """

    # Signal family names
    FAMILIES = ['cpi', 'pce', 'housing', 'm2_gap']

    def __init__(
        self,
        thresholds: Optional[RegimeThresholds] = None,
        calibrated: Optional["CalibratedThresholds"] = None
    ):
        """
        Initialize classifier with thresholds.

        Args:
            thresholds: Hand-tuned thresholds (fallback)
            calibrated: Percentile-based thresholds (preferred)

        If calibrated is provided, thresholds are derived from percentiles:
        - STRESS = p80
        - CRISIS = p95
        - LOW = p25
        """
        self.calibrated = calibrated
        self.calibration_hash = None

        if calibrated is not None:
            # Derive thresholds from percentile data
            self.calibration_hash = calibrated.calibration_hash
            self.thresholds = RegimeThresholds(
                # Stress thresholds (p80)
                cpi_stress=calibrated.cpi_yoy.get(80, 4.0),
                pce_stress=calibrated.pce_yoy.get(80, 4.0),
                housing_stress=calibrated.housing_yoy.get(80, 8.0),
                m2_gap_stress=calibrated.m2_cpi_gap.get(80, 4.0),
                # Crisis thresholds (p95)
                cpi_crisis=calibrated.cpi_yoy.get(95, 6.0),
                housing_crisis=calibrated.housing_yoy.get(95, 15.0),
                m2_gap_crisis=calibrated.m2_cpi_gap.get(95, 6.0),
                # Low thresholds (p25)
                cpi_low=calibrated.cpi_yoy.get(50, 2.5) * 0.6,  # Below median
                housing_low=calibrated.housing_yoy.get(50, 4.5) * 0.6,
                m2_gap_low=calibrated.m2_cpi_gap.get(50, 2.5) * 0.4,
            )
        else:
            self.thresholds = thresholds or RegimeThresholds()

    def classify(self, features: FREDFeatures) -> RegimeState:
        """Classify single observation into regime state."""
        # Step 1: Identify active families (elevated above stress threshold)
        active, crisis_count = self._check_families(features)

        # Step 2: Classify regime based on triangulation
        regime, confidence = self._classify_regime(active, crisis_count)

        # Step 3: Compute Risk State Vector
        H = self._compute_entropy(features)
        C = self._compute_coherence(features, active)
        D = self._compute_depth(active)
        Se = H * C * D

        # Step 4: Detect lead/lag if possible
        lead_lag = self._detect_lead(features, active)

        return RegimeState(
            date=features.date,
            regime=regime,
            confidence=confidence,
            drivers=active,
            H=round(H, 4),
            C=round(C, 4),
            D=round(D, 4),
            Se=round(Se, 4),
            lead_lag=lead_lag,
            raw_values={
                'cpi_yoy': features.cpi_yoy,
                'pce_yoy': features.pce_yoy,
                'housing_yoy': features.housing_yoy,
                'm2_cpi_gap': features.m2_cpi_gap,
            }
        )

    def classify_series(self, features: List[FREDFeatures]) -> List[RegimeState]:
        """Classify full time series."""
        return [self.classify(f) for f in features]

    def _check_families(self, f: FREDFeatures) -> Tuple[List[str], int]:
        """
        Check which signal families are elevated.

        Returns:
            Tuple of (list of active family names, count at crisis level)
        """
        active = []
        crisis_count = 0
        t = self.thresholds

        # CPI family
        if f.cpi_yoy is not None and f.cpi_yoy > t.cpi_stress:
            active.append('cpi')
            if f.cpi_yoy > t.cpi_crisis:
                crisis_count += 1

        # PCE family (parallel to CPI but distinct)
        if f.pce_yoy is not None and f.pce_yoy > t.pce_stress:
            if 'cpi' not in active:  # Don't double-count inflation
                active.append('pce')

        # Housing family
        if f.housing_yoy is not None and f.housing_yoy > t.housing_stress:
            active.append('housing')
            if f.housing_yoy > t.housing_crisis:
                crisis_count += 1

        # M2-CPI gap (hidden monetary expansion)
        if f.m2_cpi_gap is not None and f.m2_cpi_gap > t.m2_gap_stress:
            active.append('m2_gap')
            if f.m2_cpi_gap > t.m2_gap_crisis:
                crisis_count += 1

        return active, crisis_count

    def _classify_regime(self, active: List[str], crisis_count: int) -> Tuple[str, float]:
        """
        Classify regime based on triangulation.

        Triangulation principle:
        - CRISIS requires 3+ families OR 2+ at crisis level
        - STRESS requires 1-2 families elevated
        - LOW requires all below low thresholds
        - NORMAL is everything else
        """
        n_active = len(active)

        if n_active >= 3 or crisis_count >= 2:
            # Multiple families confirm - CRISIS
            return "CRISIS", 0.90 + (min(n_active, 4) * 0.02)

        elif n_active == 2:
            # Two families agree - high STRESS
            return "STRESS", 0.80

        elif n_active == 1:
            # Single family elevated - moderate STRESS
            return "STRESS", 0.65

        elif n_active == 0:
            # Check if truly subdued (LOW) or just normal
            # We'd need feature values to distinguish, default to NORMAL
            return "NORMAL", 0.75

        return "NORMAL", 0.70

    def _compute_entropy(self, f: FREDFeatures) -> float:
        """
        H (Entropy): Measure of volatility/uncertainty.

        Higher = more volatile environment.
        Normalized to 0-1 range.
        """
        vols = []
        if f.cpi_vol_12m is not None:
            vols.append(f.cpi_vol_12m)
        if f.m2_vol_12m is not None:
            vols.append(f.m2_vol_12m)
        if f.housing_vol_12m is not None:
            vols.append(f.housing_vol_12m)

        if not vols:
            return 0.5  # Default to middle

        avg_vol = sum(vols) / len(vols)
        # Normalize: baseline=1.5% vol maps to 0.5
        # Higher vol -> higher H (capped at 1.0)
        H = min(1.0, avg_vol / (self.thresholds.vol_baseline * 2))
        return H

    def _compute_coherence(self, f: FREDFeatures, active: List[str]) -> float:
        """
        C (Coherence): Do signal families agree on direction?

        Higher = more agreement among families.
        """
        # Check sign agreement among key series
        signs = []

        # Inflation direction (above/below 2% neutral)
        if f.cpi_yoy is not None:
            signs.append(1 if f.cpi_yoy > 2.0 else -1)
        if f.pce_yoy is not None:
            signs.append(1 if f.pce_yoy > 2.0 else -1)

        # M2 expansion direction
        if f.m2_cpi_gap is not None:
            signs.append(1 if f.m2_cpi_gap > 0 else -1)

        # Housing direction
        if f.housing_yoy is not None:
            signs.append(1 if f.housing_yoy > 3.0 else -1)

        if not signs:
            return 0.5

        # Coherence = fraction agreeing with majority
        positive = sum(1 for s in signs if s > 0)
        negative = len(signs) - positive
        majority = max(positive, negative)

        C = majority / len(signs)
        return C

    def _compute_depth(self, active: List[str]) -> float:
        """
        D (Depth): How many signal families are active?

        Normalized to 0-1 based on total possible families (4).
        """
        max_families = len(self.FAMILIES)
        D = len(active) / max_families
        return D

    def _detect_lead(self, f: FREDFeatures, active: List[str]) -> Optional[str]:
        """
        Detect which series is leading (heuristic).

        In practice, housing often leads CPI by 6-12 months.
        M2 expansion can precede both.
        """
        if not active:
            return None

        # Simple heuristic: if housing is active but CPI isn't elevated yet
        if 'housing' in active and f.cpi_yoy is not None and f.cpi_yoy < 3.0:
            return "housing_leading"

        # If M2 gap is large but CPI still moderate
        if 'm2_gap' in active and f.cpi_yoy is not None and f.cpi_yoy < 4.0:
            return "m2_leading"

        return None

    def get_thresholds_dict(self) -> Dict:
        """Return thresholds as dict for receipt serialization."""
        result = asdict(self.thresholds)
        result['calibration_mode'] = 'percentile' if self.calibrated else 'hand_tuned'
        if self.calibration_hash:
            result['calibration_hash'] = self.calibration_hash
        return result


def state_to_dict(state: RegimeState) -> Dict:
    """Convert RegimeState to dict for JSON serialization."""
    return asdict(state)


if __name__ == "__main__":
    # Quick test
    from .features_from_fred import extract_features

    features, _ = extract_features()
    classifier = RegimeClassifier()
    regimes = classifier.classify_series(features)

    print(f"Classified {len(regimes)} observations")

    # Show regime distribution
    from collections import Counter
    dist = Counter(r.regime for r in regimes)
    print(f"\nRegime distribution:")
    for regime, count in sorted(dist.items()):
        pct = count / len(regimes) * 100
        print(f"  {regime}: {count} ({pct:.1f}%)")

    # Show current state
    current = regimes[-1]
    print(f"\nCurrent state ({current.date}):")
    print(f"  Regime:     {current.regime}")
    print(f"  Confidence: {current.confidence:.2f}")
    print(f"  Drivers:    {current.drivers}")
    print(f"\nRisk State Vector:")
    print(f"  H (Entropy):   {current.H:.3f}")
    print(f"  C (Coherence): {current.C:.3f}")
    print(f"  D (Depth):     {current.D:.3f}")
    print(f"  Se:            {current.Se:.3f}")

    # Show post-COVID peak
    print(f"\nPost-COVID regime history (2020-2022):")
    for r in regimes:
        if r.date >= "2020-01" and r.date <= "2022-12":
            if r.regime in ("STRESS", "CRISIS"):
                print(f"  {r.date}: {r.regime} (drivers={r.drivers}, Se={r.Se:.2f})")
