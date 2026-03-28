"""
Generate FGIP graph nodes and edges from RegimeState classifications.

Converts regime detections into:
- REGIME_STATE nodes (one per month)
- MODULATES edges to thesis nodes (context affects conviction)
- INCREASES_RISK_FOR edges (STRESS/CRISIS only - stricter warning)
- AFFECTS_CONVICTION edges with conviction deltas

These are INFERENTIAL edges - derived from regime classification, not FACT.

v1.1 adds:
- Coherence gate: only emit MODULATES when C >= gate (triangulation enforcement)
- regime_receipt_id: provenance tracking back to regime receipt

v1.2 adds:
- INCREASES_RISK_FOR edge family (STRESS/CRISIS only, stricter than MODULATES)
"""

import hashlib
import json
from dataclasses import asdict
from typing import Dict, List, Optional

from .regime_classifier import RegimeState


# Coherence gate: only emit edges when signals agree
DEFAULT_COHERENCE_GATE = 0.66


def _stable_edge_id(edge_type: str, from_id: str, to_id: str, salt: str = "") -> str:
    """
    Generate deterministic edge ID from components.

    Same inputs always produce same output (no uuid4 randomness).
    This ensures JSONL exports are byte-identical across runs.

    Salt should be stable across date format changes - prefer node_id over raw date strings.
    """
    h = hashlib.sha256(f"{edge_type}|{from_id}|{to_id}|{salt}".encode("utf-8")).hexdigest()
    return f"{edge_type.lower()}-{h[:16]}"


def _extract_provenance(regime_node: Dict) -> Dict[str, Optional[str]]:
    """Extract provenance fields from regime node metadata."""
    try:
        md = json.loads(regime_node.get("metadata", "{}"))
    except (json.JSONDecodeError, TypeError):
        md = {}
    return {
        "calibration_hash": md.get("calibration_hash"),
        "regime_receipt_id": md.get("regime_receipt_id"),
    }


# Canonical JSON serialization for deterministic exports
def _json_canonical(obj: dict) -> str:
    """Serialize to canonical JSON (sorted keys, no whitespace)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def regime_state_to_node(
    state: RegimeState,
    calibration_hash: Optional[str] = None,
    regime_receipt_id: Optional[str] = None
) -> Dict:
    """
    Convert RegimeState to graph node dict.

    Args:
        state: RegimeState from classifier
        calibration_hash: Hash of calibration used (for receipt linkage)
        regime_receipt_id: ID of regime-run receipt (for provenance)

    Returns:
        Dict ready for insertion into nodes table
    """
    # Extract YYYY-MM from date
    date_key = state.date[:7]  # "2025-01-01" -> "2025-01"

    node_id = f"regime-state-{date_key}"

    # Build description
    drivers_str = ", ".join(state.drivers) if state.drivers else "none"
    description = (
        f"{state.regime} regime (confidence={state.confidence:.0%}). "
        f"Drivers: [{drivers_str}]. Se={state.Se:.3f}"
    )

    return {
        "node_id": node_id,
        "node_type": "REGIME_STATE",
        "name": f"Economic Regime: {date_key}",
        "description": description,
        "aliases": json.dumps([date_key, state.date], sort_keys=True, separators=(",", ":")),
        "metadata": _json_canonical({
            "date": state.date,
            "date_key": date_key,
            "regime": state.regime,
            "confidence": state.confidence,
            "drivers": state.drivers,
            "H": state.H,
            "C": state.C,
            "D": state.D,
            "Se": state.Se,
            "lead_lag": state.lead_lag,
            "raw_values": state.raw_values,
            "calibration_hash": calibration_hash,
            "regime_receipt_id": regime_receipt_id,
        }),
    }


def generate_regime_nodes(
    regimes: List[RegimeState],
    calibration_hash: Optional[str] = None,
    start_date: Optional[str] = None,
    regime_receipt_id: Optional[str] = None
) -> List[Dict]:
    """
    Generate all regime state nodes for insertion.

    Args:
        regimes: List of RegimeState classifications
        calibration_hash: Hash of calibration used
        start_date: Only generate for dates >= start_date (format: "YYYY-MM" or "YYYY-MM-DD")
        regime_receipt_id: ID of regime-run receipt (for provenance)

    Returns:
        List of node dicts ready for insertion
    """
    nodes = []

    for state in regimes:
        # Filter by start_date if specified
        if start_date:
            if state.date < start_date:
                continue

        node = regime_state_to_node(state, calibration_hash, regime_receipt_id)
        nodes.append(node)

    return nodes


def generate_thesis_edges(
    regime_node: Dict,
    theses: List[str],
    regime_state: RegimeState,
    *,
    coherence_gate: float = DEFAULT_COHERENCE_GATE
) -> List[Dict]:
    """
    Generate MODULATES edges from regime to theses.

    Coherence gate (v1.1):
    - Only emit edges when regime coherence C >= coherence_gate
    - This enforces "triangulation agreement" and prevents noisy regimes
      from spamming the graph

    Args:
        regime_node: Regime node dict (from regime_state_to_node)
        theses: List of thesis node IDs to connect
        regime_state: Original RegimeState for computing modulation
        coherence_gate: Minimum coherence required to emit edges (default 0.66)

    Returns:
        List of edge dicts ready for insertion (empty if C < gate)
    """
    # Coherence gate: if signals disagree, emit no edges
    if regime_state.C < coherence_gate:
        return []

    edges = []

    # Compute modulation based on regime
    regime_modulation = {
        "CRISIS": {"conviction_delta": -2, "risk_delta": 20},
        "STRESS": {"conviction_delta": -1, "risk_delta": 10},
        "NORMAL": {"conviction_delta": 0, "risk_delta": 0},
        "LOW": {"conviction_delta": 1, "risk_delta": -5},
    }

    mod = regime_modulation.get(regime_state.regime, {"conviction_delta": 0, "risk_delta": 0})

    # Scale by Se (higher Se = stronger modulation)
    se_scale = 1 + regime_state.Se

    # Extract provenance from node metadata
    provenance = _extract_provenance(regime_node)

    # Salt with node_id (stable across date format changes)
    salt = regime_node["node_id"]

    for thesis_id in theses:
        edge_id = _stable_edge_id("MODULATES", regime_node["node_id"], thesis_id, salt)

        # Build edge detail
        detail = (
            f"{regime_state.regime} regime modulates thesis conviction. "
            f"Drivers: {regime_state.drivers}. Se={regime_state.Se:.3f}. C={regime_state.C:.3f}"
        )

        edges.append({
            "edge_id": edge_id,
            "edge_type": "MODULATES",
            "from_node_id": regime_node["node_id"],
            "to_node_id": thesis_id,
            "confidence": regime_state.confidence,
            "notes": detail,
            "metadata": _json_canonical({
                "regime": regime_state.regime,
                "date": regime_state.date,
                "conviction_delta": mod["conviction_delta"],
                "risk_delta": mod["risk_delta"],
                "se_scale": round(se_scale, 3),
                "drivers": regime_state.drivers,
                "C": regime_state.C,
                "coherence_gate": coherence_gate,
                "assertion_level": "INFERENCE",
                # Provenance chain
                "calibration_hash": provenance["calibration_hash"],
                "regime_receipt_id": provenance["regime_receipt_id"],
            }),
        })

    return edges


def generate_increases_risk_edges(
    regime_node: Dict,
    theses: List[str],
    regime_state: RegimeState,
    *,
    coherence_gate: float = DEFAULT_COHERENCE_GATE
) -> List[Dict]:
    """
    Emit INCREASES_RISK_FOR edges for STRESS/CRISIS regimes only.

    This is STRICTER than MODULATES:
    - MODULATES: "context affects conviction" (fires in any coherent regime)
    - INCREASES_RISK_FOR: "this environment is riskier for holding this thesis"
      (only when regime is already elevated AND coherent)

    Policy:
    - Only if regime in {STRESS, CRISIS}
    - Only if coherence C >= coherence_gate (triangulation enforcement)
    - Always inferential

    Args:
        regime_node: Regime node dict (from regime_state_to_node)
        theses: List of thesis node IDs to connect
        regime_state: Original RegimeState for computing risk score
        coherence_gate: Minimum coherence required to emit edges (default 0.66)

    Returns:
        List of edge dicts ready for insertion (empty if regime not elevated or C < gate)
    """
    # Only emit for elevated regimes
    if regime_state.regime not in ("STRESS", "CRISIS"):
        return []

    # Coherence gate: if signals disagree, emit no edges
    if regime_state.C < coherence_gate:
        return []

    edges = []

    # Risk severity mapping (deterministic)
    # STRESS = moderate risk, CRISIS = high risk
    base_risk = 0.35 if regime_state.regime == "STRESS" else 0.65

    # Scale by confidence and Se (routing strength)
    # Clamp to [0, 1]
    risk_score = base_risk * regime_state.confidence * (1.0 + min(1.0, max(0.0, regime_state.Se)))
    risk_score = max(0.0, min(1.0, risk_score))

    # Extract provenance from node metadata
    provenance = _extract_provenance(regime_node)

    # Salt with node_id (stable across date format changes)
    salt = regime_node["node_id"]

    for thesis_id in theses:
        edge_id = _stable_edge_id("INCREASES_RISK_FOR", regime_node["node_id"], thesis_id, salt)

        # Build edge detail
        detail = (
            f"{regime_state.regime} regime increases risk for thesis. "
            f"Drivers: {regime_state.drivers}. Se={regime_state.Se:.3f}. "
            f"Risk score={risk_score:.3f}"
        )

        edges.append({
            "edge_id": edge_id,
            "edge_type": "INCREASES_RISK_FOR",
            "from_node_id": regime_node["node_id"],
            "to_node_id": thesis_id,
            "confidence": regime_state.confidence,
            "weight": round(risk_score, 6),
            "notes": detail,
            "metadata": _json_canonical({
                "regime": regime_state.regime,
                "date": regime_state.date,
                "risk_score": round(risk_score, 6),
                "base_risk": base_risk,
                "drivers": regime_state.drivers,
                "C": regime_state.C,
                "Se": regime_state.Se,
                "coherence_gate": coherence_gate,
                "assertion_level": "INFERENCE",
                # Provenance chain
                "calibration_hash": provenance["calibration_hash"],
                "regime_receipt_id": provenance["regime_receipt_id"],
            }),
        })

    return edges


def generate_conviction_edges(
    regime_node: Dict,
    thesis_id: str,
    old_conviction: int,
    new_conviction: int,
    regime_state: RegimeState
) -> Dict:
    """
    Generate AFFECTS_CONVICTION edge for a specific conviction change.

    Pattern A (stable edge id): edge_id is stable per (type, from, to, month).
    Conviction values are in metadata only - if scoring logic changes,
    the same edge gets updated rather than creating a new edge.

    Args:
        regime_node: Regime node dict
        thesis_id: Thesis that was affected
        old_conviction: Conviction level before regime change
        new_conviction: Conviction level after regime change
        regime_state: The regime that caused the change

    Returns:
        Edge dict ready for insertion
    """
    # Salt with node_id only (Pattern A: stable per month/thesis pair)
    salt = regime_node["node_id"]
    edge_id = _stable_edge_id("AFFECTS_CONVICTION", regime_node["node_id"], thesis_id, salt)

    # Extract provenance from node metadata
    provenance = _extract_provenance(regime_node)

    detail = (
        f"Regime changed from CONVICTION_{old_conviction} to CONVICTION_{new_conviction}. "
        f"Trigger: {regime_state.regime} ({regime_state.date})"
    )

    return {
        "edge_id": edge_id,
        "edge_type": "AFFECTS_CONVICTION",
        "from_node_id": regime_node["node_id"],
        "to_node_id": thesis_id,
        "confidence": regime_state.confidence,
        "notes": detail,
        "metadata": _json_canonical({
            "old_conviction": old_conviction,
            "new_conviction": new_conviction,
            "conviction_delta": new_conviction - old_conviction,
            "regime": regime_state.regime,
            "date": regime_state.date,
            "Se": regime_state.Se,
            "assertion_level": "INFERENCE",
            # Provenance chain
            "calibration_hash": provenance["calibration_hash"],
            "regime_receipt_id": provenance["regime_receipt_id"],
        }),
    }


if __name__ == "__main__":
    # Quick test
    from .features_from_fred import extract_features
    from .regime_classifier import RegimeClassifier
    from .calibration import load_calibration

    # Load calibration and classify
    cal = load_calibration()
    features, _ = extract_features()
    classifier = RegimeClassifier(calibrated=cal)
    regimes = classifier.classify_series(features)

    # Generate nodes for recent regimes (2020+)
    calibration_hash = cal.calibration_hash if cal else None
    filtered_regimes = [r for r in regimes if r.date >= "2020-01"]
    nodes = generate_regime_nodes(regimes, calibration_hash, start_date="2020-01")

    print(f"Generated {len(nodes)} regime nodes (2020+)")

    # Show sample nodes
    print("\nSample nodes:")
    for node in nodes[:3]:
        metadata = json.loads(node["metadata"])
        print(f"  {node['node_id']}: {metadata['regime']} (Se={metadata['Se']:.3f})")

    # Generate edges to example theses
    example_theses = ["nuclear-smr-thesis", "uranium-thesis", "reshoring-thesis"]

    # Generate both edge types for all regimes
    mod_edges = []
    risk_edges = []
    for node, state in zip(nodes, filtered_regimes):
        mod_edges.extend(generate_thesis_edges(node, example_theses, state))
        risk_edges.extend(generate_increases_risk_edges(node, example_theses, state))

    print(f"\nEdge Summary (2020+):")
    print(f"  MODULATES edges:          {len(mod_edges)}")
    print(f"  INCREASES_RISK_FOR edges: {len(risk_edges)}")

    # Show STRESS/CRISIS regimes that generated risk edges
    stress_crisis = [r for r in filtered_regimes if r.regime in ("STRESS", "CRISIS")]
    coherent_elevated = [r for r in stress_crisis if r.C >= DEFAULT_COHERENCE_GATE]
    print(f"\n  STRESS/CRISIS regimes:    {len(stress_crisis)}")
    print(f"  With C >= {DEFAULT_COHERENCE_GATE}:            {len(coherent_elevated)}")

    # Sample risk edge
    if risk_edges:
        sample = risk_edges[0]
        meta = json.loads(sample["metadata"])
        print(f"\nSample INCREASES_RISK_FOR edge:")
        print(f"  {sample['from_node_id']} -> {sample['to_node_id']}")
        print(f"  risk_score={meta['risk_score']:.3f}, regime={meta['regime']}")
