"""
FGIP Regime Detection System v1.1

Infers economic regime state (LOW/NORMAL/STRESS/CRISIS) from multiple
signal families using triangulation. Produces receipts for audit trail.

v1 adds:
- Calibrated thresholds (percentile-based from historical data)
- Graph node generation (REGIME_STATE nodes)
- MODULATES edges to thesis nodes

v1.1 adds:
- JSONL export bridge (deterministic, with SHA256 hashes)
- Coherence gate (only emit edges when C >= 0.66)
- regime_receipt_id provenance tracking

Usage:
    python -m fgip.regime                    # Run analysis (hand-tuned)
    python -m fgip.regime --calibrated       # Run with percentile thresholds
    python -m fgip.regime --receipts-dir DIR # Custom input path

API:
    from fgip.regime import run_regime_analysis
    state = run_regime_analysis(calibrated=True)
    print(f"Current regime: {state.regime}")
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .features_from_fred import FREDFeatures, extract_features, features_to_dict
from .regime_classifier import RegimeClassifier, RegimeState, state_to_dict
from .calibration import CalibratedThresholds, calibrate, load_calibration
from .graph_nodes import (
    DEFAULT_COHERENCE_GATE,
    generate_regime_nodes,
    generate_thesis_edges,
    generate_increases_risk_edges,
    regime_state_to_node,
)
from .jsonl_bridge import (
    export_regime_graph_jsonl,
    export_full_graph_jsonl,
    run_full_export,
)
from .thesis_nodes import (
    ThesisDefinition,
    thesis_to_node,
    generate_thesis_nodes,
    CANONICAL_THESES,
    get_canonical_thesis,
    get_all_canonical_thesis_ids,
)
from .temporal_edges import (
    generate_regime_sequence_edges,
    generate_transition_edges,
    generate_feature_lead_edges,
    get_empirical_lead_edges,
    EMPIRICAL_FEATURE_LEADS,
)
from .belief_revision import (
    compute_content_hash,
    get_logical_id,
    make_versioned_id,
    load_snapshot,
    find_latest_export,
    compute_revision,
    apply_revision,
    NodeVersion,
    RevisionResult,
)
from .negative_space import (
    HypothesisDefinition,
    EvaluationResult,
    PREDICATE_REGISTRY,
    generate_escalation_hypothesis,
    generate_persistence_hypothesis,
    generate_all_v0_hypotheses,
    hypothesis_to_node,
    generate_hypothesis_nodes,
    generate_predicts_edges,
    generate_outcome_edges,
    generate_evaluated_at_edges,
    evaluate_hypothesis,
    run_hypothesis_generation,
    run_hypothesis_evaluation,
    write_negative_space_receipt,
)

__version__ = "1.4.0"
__all__ = [
    'run_regime_analysis',
    'extract_features',
    'RegimeClassifier',
    'RegimeState',
    'FREDFeatures',
    # v1 additions
    'calibrate',
    'load_calibration',
    'CalibratedThresholds',
    'generate_regime_nodes',
    'generate_thesis_edges',
    'regime_state_to_node',
    # v1.1 additions
    'export_regime_graph_jsonl',
    'DEFAULT_COHERENCE_GATE',
    # v1.4 additions (full graph export)
    'export_full_graph_jsonl',
    'run_full_export',
    # v1.2 additions
    'generate_increases_risk_edges',
    # v1.3 additions (THESIS nodes - no more dangling edges)
    'ThesisDefinition',
    'thesis_to_node',
    'generate_thesis_nodes',
    'CANONICAL_THESES',
    'get_canonical_thesis',
    'get_all_canonical_thesis_ids',
    # v1.3 additions (temporal edges - time as first-class relationship)
    'generate_regime_sequence_edges',
    'generate_transition_edges',
    'generate_feature_lead_edges',
    'get_empirical_lead_edges',
    'EMPIRICAL_FEATURE_LEADS',
    # v1.3 additions (belief revision - SUPERSEDES)
    'compute_content_hash',
    'get_logical_id',
    'make_versioned_id',
    'load_snapshot',
    'find_latest_export',
    'compute_revision',
    'apply_revision',
    'NodeVersion',
    'RevisionResult',
    # v1.4 additions (negative space - DID_NOT_MATERIALIZE + EVALUATED_AT)
    'HypothesisDefinition',
    'EvaluationResult',
    'PREDICATE_REGISTRY',
    'generate_escalation_hypothesis',
    'generate_persistence_hypothesis',
    'generate_all_v0_hypotheses',
    'hypothesis_to_node',
    'generate_hypothesis_nodes',
    'generate_predicts_edges',
    'generate_outcome_edges',
    'generate_evaluated_at_edges',
    'evaluate_hypothesis',
    'run_hypothesis_generation',
    'run_hypothesis_evaluation',
    'write_negative_space_receipt',
]


def compute_outputs_hash(regimes: List[RegimeState]) -> str:
    """Compute SHA256 of regime classification outputs."""
    data = json.dumps([state_to_dict(r) for r in regimes], sort_keys=True)
    return hashlib.sha256(data.encode()).hexdigest()


def compute_script_hash() -> str:
    """Compute combined hash of source files for reproducibility."""
    files = [
        Path(__file__).parent / 'features_from_fred.py',
        Path(__file__).parent / 'regime_classifier.py',
        Path(__file__).parent / '__init__.py',
    ]
    h = hashlib.sha256()
    for f in files:
        if f.exists():
            h.update(f.read_bytes())
    return h.hexdigest()


def write_regime_receipt(
    features: List[FREDFeatures],
    regimes: List[RegimeState],
    file_hashes: Dict[str, str],
    classifier: RegimeClassifier,
    output_dir: str = "receipts/regime"
) -> str:
    """
    Write JSON receipt with input/output hashes.

    Returns path to written receipt.
    """
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    receipt_id = f"regime-run-{timestamp}"
    receipt_path = Path(output_dir) / f"{receipt_id}.json"

    current = regimes[-1] if regimes else None

    # Build regime transition history (just the transitions)
    transitions = []
    prev_regime = None
    for r in regimes:
        if r.regime != prev_regime:
            transitions.append({
                "date": r.date,
                "regime": r.regime,
                "Se": r.Se,
                "drivers": r.drivers,
            })
            prev_regime = r.regime

    receipt = {
        "receipt_id": receipt_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": __version__,
        "operation": "regime_classification",
        "inputs": {
            "fred_m2sl_hash": file_hashes.get('m2', ''),
            "fred_cpiaucsl_hash": file_hashes.get('cpi', ''),
            "fred_pcepi_hash": file_hashes.get('pce', ''),
            "fred_csushpinsa_hash": file_hashes.get('housing', ''),
            "script_hash": compute_script_hash(),
        },
        "outputs": {
            "features_count": len(features),
            "date_range": {
                "start": features[0].date if features else None,
                "end": features[-1].date if features else None,
            },
            "regime_transitions": transitions[-10:],  # Last 10 transitions
            "current_regime": current.regime if current else None,
            "current_confidence": current.confidence if current else None,
            "current_Se": current.Se if current else None,
            "current_drivers": current.drivers if current else [],
            "risk_state_vector": {
                "H": current.H if current else None,
                "C": current.C if current else None,
                "D": current.D if current else None,
                "Se": current.Se if current else None,
            },
            "outputs_hash": compute_outputs_hash(regimes)[:32],
        },
        "thresholds_used": classifier.get_thresholds_dict(),
        "regime_distribution": {},
        "success": True,
    }

    # Compute regime distribution
    from collections import Counter
    dist = Counter(r.regime for r in regimes)
    receipt["regime_distribution"] = {k: v for k, v in sorted(dist.items())}

    with open(receipt_path, 'w') as f:
        json.dump(receipt, f, indent=2)

    return str(receipt_path)


def run_regime_analysis(
    receipts_dir: str = "THESIS_PACK/receipts/inflation",
    output_dir: str = "receipts/regime",
    verbose: bool = True,
    calibrated: bool = False
) -> RegimeState:
    """
    Main entry point: run full regime detection analysis.

    Args:
        receipts_dir: Path to FRED CSV artifacts
        output_dir: Path to write regime receipts
        verbose: Print progress to stdout
        calibrated: Use percentile-based thresholds (v1)

    Returns:
        Current RegimeState
    """
    version = "v1 (calibrated)" if calibrated else "v0 (hand-tuned)"
    if verbose:
        print(f"Regime Detection System {version}")
        print("=" * 50)

    # Step 1: Extract features from FRED CSVs
    if verbose:
        print("\n[1/5] Loading FRED series...")

    features, file_hashes = extract_features(receipts_dir)

    if verbose:
        print(f"      Loaded 4 series (M2SL, CPIAUCSL, PCEPI, CSUSHPINSA)")
        print(f"      Computed features for {len(features)} months")
        print(f"      Date range: {features[0].date} to {features[-1].date}")

    # Step 2: Load/compute calibration if requested
    cal = None
    if calibrated:
        if verbose:
            print("\n[2/5] Loading calibration...")

        cal = load_calibration()
        if cal is None:
            if verbose:
                print("      No calibration found, computing...")
            cal = calibrate(receipts_dir, output_dir)

        if verbose:
            print(f"      CPI STRESS threshold: p80 = {cal.cpi_yoy[80]:.2f}%")
            print(f"      Housing STRESS threshold: p80 = {cal.housing_yoy[80]:.2f}%")
            print(f"      M2 Gap STRESS threshold: p80 = {cal.m2_cpi_gap[80]:.2f}%")

    # Step 3: Classify regimes
    if verbose:
        step = "[3/5]" if calibrated else "[2/4]"
        print(f"\n{step} Classifying regimes...")

    classifier = RegimeClassifier(calibrated=cal)
    regimes = classifier.classify_series(features)

    # Step 4: Report current state
    current = regimes[-1]

    if verbose:
        step = "[4/5]" if calibrated else "[3/4]"
        print(f"\n{step} Current State ({current.date})")
        print(f"      Regime:     {current.regime}")
        print(f"      Confidence: {current.confidence:.0%}")
        print(f"      Drivers:    {current.drivers if current.drivers else 'none'}")
        print(f"\n      Risk State Vector:")
        print(f"        H (Entropy):   {current.H:.3f}")
        print(f"        C (Coherence): {current.C:.3f}")
        print(f"        D (Depth):     {current.D:.3f}")
        print(f"        Se:            {current.Se:.4f}")

    # Step 5: Write receipt
    if verbose:
        step = "[5/5]" if calibrated else "[4/4]"
        print(f"\n{step} Writing receipt...")

    receipt_path = write_regime_receipt(
        features, regimes, file_hashes, classifier, output_dir
    )

    if verbose:
        print(f"      {receipt_path}")
        mode = "calibrated" if calibrated else "hand-tuned"
        print("\n" + "=" * 50)
        print(f"RESULT: {current.regime} (Se={current.Se:.3f}, mode={mode})")

    return current


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="FGIP Regime Detection System"
    )
    parser.add_argument(
        "--receipts-dir",
        default="THESIS_PACK/receipts/inflation",
        help="Path to FRED CSV artifacts"
    )
    parser.add_argument(
        "--output-dir",
        default="receipts/regime",
        help="Path to write regime receipts"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress verbose output"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output current state as JSON"
    )
    parser.add_argument(
        "--calibrated", "-c",
        action="store_true",
        help="Use percentile-based thresholds (v1)"
    )

    args = parser.parse_args()

    state = run_regime_analysis(
        receipts_dir=args.receipts_dir,
        output_dir=args.output_dir,
        verbose=not args.quiet and not args.json,
        calibrated=args.calibrated
    )

    if args.json:
        print(json.dumps(state_to_dict(state), indent=2))


if __name__ == "__main__":
    main()
