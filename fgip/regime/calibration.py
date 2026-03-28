"""
Historical percentile calibration for regime thresholds.

Computes p50/p75/p80/p90/p95 for each feature to define
data-driven STRESS/CRISIS thresholds instead of hand-tuned values.

The calibration is stored as a Tier-0 receipt with:
- Input hashes (FRED CSVs)
- Computed percentiles for each feature
- Derived thresholds (p80=STRESS, p95=CRISIS)
"""

import hashlib
import json
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .features_from_fred import FREDFeatures, extract_features


# Percentile levels to compute
PERCENTILE_LEVELS = [50, 75, 80, 90, 95]


@dataclass
class CalibratedThresholds:
    """Percentile-based thresholds computed from historical data."""
    cpi_yoy: Dict[int, float] = field(default_factory=dict)       # {80: 4.2, 90: 5.1, 95: 6.3}
    pce_yoy: Dict[int, float] = field(default_factory=dict)
    housing_yoy: Dict[int, float] = field(default_factory=dict)
    m2_cpi_gap: Dict[int, float] = field(default_factory=dict)
    calibration_date: str = ""
    calibration_hash: str = ""
    sample_count: int = 0
    date_range: Tuple[str, str] = ("", "")


@dataclass
class CalibrationResult:
    """Result of percentile calibration for a single feature."""
    feature: str                    # e.g., "cpi_yoy"
    computed_at: str                # ISO timestamp
    sample_count: int               # Number of observations
    percentiles: Dict[int, float]   # {50: 2.5, 75: 3.8, 80: 4.2, 90: 5.1, 95: 6.3}
    min_value: float
    max_value: float
    mean_value: float


def compute_percentile(values: List[float], p: int) -> float:
    """
    Compute the p-th percentile of a list of values.

    Uses linear interpolation method (same as numpy.percentile default).
    """
    if not values:
        return 0.0

    sorted_values = sorted(values)
    n = len(sorted_values)

    # Compute position (0-indexed)
    k = (p / 100) * (n - 1)
    f = int(k)  # Floor
    c = f + 1   # Ceil

    if c >= n:
        return sorted_values[-1]

    # Linear interpolation
    d = k - f
    return sorted_values[f] * (1 - d) + sorted_values[c] * d


def compute_percentiles_for_feature(
    values: List[float],
    feature_name: str,
    percentiles: List[int] = PERCENTILE_LEVELS
) -> CalibrationResult:
    """Compute percentiles for a single feature."""
    # Filter out None values
    valid = [v for v in values if v is not None]

    if not valid:
        return CalibrationResult(
            feature=feature_name,
            computed_at=datetime.now(timezone.utc).isoformat(),
            sample_count=0,
            percentiles={p: 0.0 for p in percentiles},
            min_value=0.0,
            max_value=0.0,
            mean_value=0.0,
        )

    pct_values = {p: round(compute_percentile(valid, p), 4) for p in percentiles}

    return CalibrationResult(
        feature=feature_name,
        computed_at=datetime.now(timezone.utc).isoformat(),
        sample_count=len(valid),
        percentiles=pct_values,
        min_value=round(min(valid), 4),
        max_value=round(max(valid), 4),
        mean_value=round(sum(valid) / len(valid), 4),
    )


def calibrate(
    receipts_dir: str = "THESIS_PACK/receipts/inflation",
    output_dir: str = "receipts/regime"
) -> CalibratedThresholds:
    """
    Run full calibration: extract features, compute percentiles, write receipt.

    Returns CalibratedThresholds for use in RegimeClassifier.
    """
    # Extract features from FRED CSVs
    features, file_hashes = extract_features(receipts_dir)

    if not features:
        raise ValueError("No features extracted - cannot calibrate")

    # Extract values for each feature
    feature_values = {
        'cpi_yoy': [f.cpi_yoy for f in features],
        'pce_yoy': [f.pce_yoy for f in features],
        'housing_yoy': [f.housing_yoy for f in features],
        'm2_cpi_gap': [f.m2_cpi_gap for f in features],
    }

    # Compute percentiles for each
    results = {}
    for name, values in feature_values.items():
        results[name] = compute_percentiles_for_feature(values, name)

    # Build calibration result
    timestamp = datetime.now(timezone.utc)

    calibration = CalibratedThresholds(
        cpi_yoy=results['cpi_yoy'].percentiles,
        pce_yoy=results['pce_yoy'].percentiles,
        housing_yoy=results['housing_yoy'].percentiles,
        m2_cpi_gap=results['m2_cpi_gap'].percentiles,
        calibration_date=timestamp.isoformat(),
        sample_count=len(features),
        date_range=(features[0].date, features[-1].date),
    )

    # Compute calibration hash (for receipt linkage)
    hash_input = json.dumps({
        'cpi_yoy': calibration.cpi_yoy,
        'pce_yoy': calibration.pce_yoy,
        'housing_yoy': calibration.housing_yoy,
        'm2_cpi_gap': calibration.m2_cpi_gap,
    }, sort_keys=True)
    calibration.calibration_hash = hashlib.sha256(hash_input.encode()).hexdigest()

    # Write receipt
    _write_calibration_receipt(calibration, results, file_hashes, output_dir)

    return calibration


def _write_calibration_receipt(
    calibration: CalibratedThresholds,
    results: Dict[str, CalibrationResult],
    file_hashes: Dict[str, str],
    output_dir: str
) -> str:
    """Write calibration as Tier-0 receipt."""
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    receipt_id = f"calibration-{timestamp}"
    receipt_path = Path(output_dir) / f"{receipt_id}.json"

    receipt = {
        "receipt_id": receipt_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "operation": "percentile_calibration",
        "version": "1.0.0",
        "inputs": {
            "features_count": calibration.sample_count,
            "date_range": {
                "start": calibration.date_range[0],
                "end": calibration.date_range[1],
            },
            "source_hashes": {
                "m2": file_hashes.get('m2', ''),
                "cpi": file_hashes.get('cpi', ''),
                "pce": file_hashes.get('pce', ''),
                "housing": file_hashes.get('housing', ''),
            },
        },
        "outputs": {
            "calibration_hash": calibration.calibration_hash,
            "percentiles": {
                "cpi_yoy": calibration.cpi_yoy,
                "pce_yoy": calibration.pce_yoy,
                "housing_yoy": calibration.housing_yoy,
                "m2_cpi_gap": calibration.m2_cpi_gap,
            },
            "statistics": {
                name: {
                    "sample_count": r.sample_count,
                    "min": r.min_value,
                    "max": r.max_value,
                    "mean": r.mean_value,
                }
                for name, r in results.items()
            },
        },
        "thresholds_derived": {
            "stress_p80": {
                "cpi": calibration.cpi_yoy.get(80),
                "pce": calibration.pce_yoy.get(80),
                "housing": calibration.housing_yoy.get(80),
                "m2_gap": calibration.m2_cpi_gap.get(80),
            },
            "crisis_p95": {
                "cpi": calibration.cpi_yoy.get(95),
                "pce": calibration.pce_yoy.get(95),
                "housing": calibration.housing_yoy.get(95),
                "m2_gap": calibration.m2_cpi_gap.get(95),
            },
        },
        "success": True,
    }

    with open(receipt_path, 'w') as f:
        json.dump(receipt, f, indent=2)

    return str(receipt_path)


def _int_keys(d: Dict) -> Dict[int, float]:
    """Convert string keys to int keys (JSON loads strings)."""
    return {int(k): v for k, v in d.items()}


def load_calibration(receipt_path: Optional[str] = None) -> Optional[CalibratedThresholds]:
    """
    Load calibration from most recent receipt.

    If receipt_path not specified, finds most recent calibration-*.json.
    """
    if receipt_path is None:
        # Find most recent calibration receipt
        receipts_dir = Path("receipts/regime")
        if not receipts_dir.exists():
            return None

        calibration_files = list(receipts_dir.glob("calibration-*.json"))
        if not calibration_files:
            return None

        # Sort by name (timestamp is in filename)
        receipt_path = str(sorted(calibration_files)[-1])

    with open(receipt_path, 'r') as f:
        receipt = json.load(f)

    outputs = receipt.get('outputs', {})
    percentiles = outputs.get('percentiles', {})

    return CalibratedThresholds(
        cpi_yoy=_int_keys(percentiles.get('cpi_yoy', {})),
        pce_yoy=_int_keys(percentiles.get('pce_yoy', {})),
        housing_yoy=_int_keys(percentiles.get('housing_yoy', {})),
        m2_cpi_gap=_int_keys(percentiles.get('m2_cpi_gap', {})),
        calibration_date=receipt.get('timestamp', ''),
        calibration_hash=outputs.get('calibration_hash', ''),
        sample_count=receipt.get('inputs', {}).get('features_count', 0),
        date_range=(
            receipt.get('inputs', {}).get('date_range', {}).get('start', ''),
            receipt.get('inputs', {}).get('date_range', {}).get('end', ''),
        ),
    )


if __name__ == "__main__":
    print("Regime Calibration")
    print("=" * 50)

    cal = calibrate()

    print(f"\nCalibrated from {cal.sample_count} observations")
    print(f"Date range: {cal.date_range[0]} to {cal.date_range[1]}")
    print(f"Calibration hash: {cal.calibration_hash[:16]}...")

    print("\nSTRESS thresholds (p80):")
    print(f"  CPI YoY:      > {cal.cpi_yoy[80]:.2f}%")
    print(f"  PCE YoY:      > {cal.pce_yoy[80]:.2f}%")
    print(f"  Housing YoY:  > {cal.housing_yoy[80]:.2f}%")
    print(f"  M2-CPI Gap:   > {cal.m2_cpi_gap[80]:.2f}%")

    print("\nCRISIS thresholds (p95):")
    print(f"  CPI YoY:      > {cal.cpi_yoy[95]:.2f}%")
    print(f"  PCE YoY:      > {cal.pce_yoy[95]:.2f}%")
    print(f"  Housing YoY:  > {cal.housing_yoy[95]:.2f}%")
    print(f"  M2-CPI Gap:   > {cal.m2_cpi_gap[95]:.2f}%")
