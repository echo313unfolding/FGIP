"""
Feature extraction from FRED Tier-0 artifacts.

Loads M2SL, CPIAUCSL, PCEPI, CSUSHPINSA CSVs and computes:
- YoY changes for each series
- M2-CPI gap (monetary expansion minus official inflation)
- Housing-CPI spread (housing inflation minus official)
- Rolling volatility (12-month std of YoY changes)

All computations are deterministic and auditable.
"""

import csv
import hashlib
import math
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class FREDFeatures:
    """Feature set for a single observation date."""
    date: str
    # Raw YoY changes (%)
    cpi_yoy: Optional[float]
    pce_yoy: Optional[float]
    m2_yoy: Optional[float]
    housing_yoy: Optional[float]
    # Derived gaps/spreads (%)
    m2_cpi_gap: Optional[float]
    housing_cpi_spread: Optional[float]
    # Rolling volatility (12-month std of YoY)
    cpi_vol_12m: Optional[float]
    m2_vol_12m: Optional[float]
    housing_vol_12m: Optional[float]


def load_fred_csv(path: str) -> List[Tuple[str, float]]:
    """
    Load FRED CSV, return list of (date, value) tuples.

    FRED CSVs have format: observation_date,{SERIES_NAME}
    Dates are YYYY-MM-DD, values are floats.
    Handles empty values gracefully.
    """
    data = []
    with open(path, 'r') as f:
        reader = csv.reader(f)
        header = next(reader)  # Skip header
        for row in reader:
            if len(row) >= 2 and row[1].strip():
                try:
                    date = row[0].strip()
                    value = float(row[1].strip())
                    data.append((date, value))
                except ValueError:
                    continue  # Skip malformed rows
    return data


def compute_yoy(series: List[Tuple[str, float]]) -> Dict[str, float]:
    """
    Compute 12-month year-over-year percentage change.

    Returns dict mapping date -> YoY change (%).
    Requires at least 12 months of history.
    """
    # Index by date for lookups
    by_date = {d: v for d, v in series}

    # Sort dates
    dates = sorted(by_date.keys())

    yoy = {}
    for date in dates:
        # Find date 12 months ago
        year = int(date[:4])
        month = int(date[5:7])
        day = date[8:10]

        prev_year = year - 1
        prev_date = f"{prev_year:04d}-{month:02d}-{day}"

        if prev_date in by_date and by_date[prev_date] != 0:
            current = by_date[date]
            previous = by_date[prev_date]
            change = ((current / previous) - 1) * 100
            yoy[date] = change

    return yoy


def compute_rolling_std(yoy_series: Dict[str, float], window: int = 12) -> Dict[str, float]:
    """
    Compute rolling standard deviation of YoY changes.

    Returns dict mapping date -> rolling std (%).
    Requires at least `window` months of YoY data.
    """
    dates = sorted(yoy_series.keys())
    rolling_std = {}

    for i, date in enumerate(dates):
        if i < window - 1:
            continue

        # Get last `window` values
        window_dates = dates[i - window + 1:i + 1]
        values = [yoy_series[d] for d in window_dates if d in yoy_series]

        if len(values) >= window:
            mean = sum(values) / len(values)
            variance = sum((v - mean) ** 2 for v in values) / len(values)
            rolling_std[date] = math.sqrt(variance)

    return rolling_std


def compute_file_hash(path: str) -> str:
    """Compute SHA256 hash of file for receipt verification."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def extract_features(
    receipts_dir: str = "THESIS_PACK/receipts/inflation"
) -> Tuple[List[FREDFeatures], Dict[str, str]]:
    """
    Main entry: load all CSVs, compute all features, return aligned table.

    Args:
        receipts_dir: Path to directory containing FRED CSVs

    Returns:
        Tuple of (list of FREDFeatures, dict of file hashes)
    """
    base = Path(receipts_dir)

    # Define series to load
    series_files = {
        'm2': base / 'fred_M2SL.csv',
        'cpi': base / 'fred_CPIAUCSL.csv',
        'pce': base / 'fred_PCEPI.csv',
        'housing': base / 'fred_CSUSHPINSA.csv',
    }

    # Verify all files exist
    for name, path in series_files.items():
        if not path.exists():
            raise FileNotFoundError(f"Missing FRED artifact: {path}")

    # Compute file hashes for receipts
    file_hashes = {name: compute_file_hash(str(path)) for name, path in series_files.items()}

    # Load raw series
    raw_series = {name: load_fred_csv(str(path)) for name, path in series_files.items()}

    # Compute YoY for each
    yoy_series = {name: compute_yoy(series) for name, series in raw_series.items()}

    # Compute rolling volatility for each
    vol_series = {name: compute_rolling_std(yoy) for name, yoy in yoy_series.items()}

    # Find common date range (intersection of all series that have YoY)
    # Case-Shiller starts 1987, others earlier - use CS as limiter
    all_dates = set(yoy_series['housing'].keys())
    for name in ['cpi', 'pce', 'm2']:
        all_dates &= set(yoy_series[name].keys())

    # Also need volatility data
    for name in ['cpi', 'm2', 'housing']:
        all_dates &= set(vol_series[name].keys())

    dates = sorted(all_dates)

    # Build feature table
    features = []
    for date in dates:
        cpi_yoy = yoy_series['cpi'].get(date)
        pce_yoy = yoy_series['pce'].get(date)
        m2_yoy = yoy_series['m2'].get(date)
        housing_yoy = yoy_series['housing'].get(date)

        # Compute derived features
        m2_cpi_gap = None
        if m2_yoy is not None and cpi_yoy is not None:
            m2_cpi_gap = m2_yoy - cpi_yoy

        housing_cpi_spread = None
        if housing_yoy is not None and cpi_yoy is not None:
            housing_cpi_spread = housing_yoy - cpi_yoy

        features.append(FREDFeatures(
            date=date,
            cpi_yoy=cpi_yoy,
            pce_yoy=pce_yoy,
            m2_yoy=m2_yoy,
            housing_yoy=housing_yoy,
            m2_cpi_gap=m2_cpi_gap,
            housing_cpi_spread=housing_cpi_spread,
            cpi_vol_12m=vol_series['cpi'].get(date),
            m2_vol_12m=vol_series['m2'].get(date),
            housing_vol_12m=vol_series['housing'].get(date),
        ))

    return features, file_hashes


def features_to_dict(features: List[FREDFeatures]) -> List[Dict]:
    """Convert features list to list of dicts for JSON serialization."""
    return [asdict(f) for f in features]


if __name__ == "__main__":
    # Quick test
    import json

    features, hashes = extract_features()
    print(f"Extracted {len(features)} feature observations")
    print(f"Date range: {features[0].date} to {features[-1].date}")
    print(f"\nFile hashes:")
    for name, h in hashes.items():
        print(f"  {name}: {h[:16]}...")

    print(f"\nLatest observation ({features[-1].date}):")
    latest = features[-1]
    print(f"  CPI YoY:      {latest.cpi_yoy:.2f}%")
    print(f"  PCE YoY:      {latest.pce_yoy:.2f}%")
    print(f"  M2 YoY:       {latest.m2_yoy:.2f}%")
    print(f"  Housing YoY:  {latest.housing_yoy:.2f}%")
    print(f"  M2-CPI Gap:   {latest.m2_cpi_gap:.2f}%")
    print(f"  Housing-CPI:  {latest.housing_cpi_spread:.2f}%")
