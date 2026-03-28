"""
Temporal edge generation for FGIP graph.

Generates LEADS and PRECEDES edges to make time a first-class relationship.
Enables queries like "What typically precedes a CRISIS regime?"

Edge types:
- PRECEDES: Sequential time ordering (regime-state-2021-03 PRECEDES regime-state-2021-04)
- LEADS: Feature X leads feature Y by N months (m2_gap LEADS cpi_yoy)

v1.0: Sequential regime edges + cross-correlation lead/lag edges
"""

import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple

from .regime_classifier import RegimeState


def _json_canonical(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _stable_edge_id(edge_type: str, from_id: str, to_id: str, salt: str = "") -> str:
    h = hashlib.sha256(f"{edge_type}|{from_id}|{to_id}|{salt}".encode("utf-8")).hexdigest()
    return f"{edge_type.lower()}-{h[:16]}"


def generate_regime_sequence_edges(
    regime_nodes: List[Dict],
    regime_states: List[RegimeState],
) -> List[Dict]:
    """
    Generate PRECEDES edges between consecutive regime nodes.

    This makes temporal sequence queryable:
    "Show me all regimes that PRECEDE a CRISIS"

    Args:
        regime_nodes: List of regime node dicts (from generate_regime_nodes)
        regime_states: Corresponding RegimeState objects (same order)

    Returns:
        List of PRECEDES edge dicts
    """
    if len(regime_nodes) < 2:
        return []

    edges = []

    for i in range(len(regime_nodes) - 1):
        prev_node = regime_nodes[i]
        next_node = regime_nodes[i + 1]
        prev_state = regime_states[i]
        next_state = regime_states[i + 1]

        edge_id = _stable_edge_id("PRECEDES", prev_node["node_id"], next_node["node_id"])

        # Detect regime transitions
        is_transition = prev_state.regime != next_state.regime
        transition_type = None
        if is_transition:
            transition_type = f"{prev_state.regime}->{next_state.regime}"

        edges.append({
            "edge_id": edge_id,
            "edge_type": "PRECEDES",
            "from_node_id": prev_node["node_id"],
            "to_node_id": next_node["node_id"],
            "confidence": 1.0,  # Factual: temporal sequence is certain
            "notes": f"Temporal sequence: {prev_state.date} precedes {next_state.date}",
            "metadata": _json_canonical({
                "from_date": prev_state.date,
                "to_date": next_state.date,
                "from_regime": prev_state.regime,
                "to_regime": next_state.regime,
                "is_transition": is_transition,
                "transition_type": transition_type,
                "assertion_level": "FACT",
            }),
        })

    return edges


def generate_transition_edges(
    regime_nodes: List[Dict],
    regime_states: List[RegimeState],
) -> List[Dict]:
    """
    Generate edges only for regime transitions (state changes).

    More compact than full sequence - only emits when regime changes.
    Useful for "what preceded this CRISIS?" queries.

    Returns edges tagged with transition severity.
    """
    if len(regime_nodes) < 2:
        return []

    # Severity ordering for transitions
    severity_order = {"LOW": 0, "NORMAL": 1, "STRESS": 2, "CRISIS": 3}

    edges = []

    for i in range(len(regime_nodes) - 1):
        prev_state = regime_states[i]
        next_state = regime_states[i + 1]

        # Only emit on transitions
        if prev_state.regime == next_state.regime:
            continue

        prev_node = regime_nodes[i]
        next_node = regime_nodes[i + 1]

        # Determine direction
        prev_sev = severity_order.get(prev_state.regime, 1)
        next_sev = severity_order.get(next_state.regime, 1)

        if next_sev > prev_sev:
            direction = "ESCALATION"
        elif next_sev < prev_sev:
            direction = "DE_ESCALATION"
        else:
            direction = "LATERAL"

        edge_id = _stable_edge_id(
            "PRECEDES",
            prev_node["node_id"],
            next_node["node_id"],
            salt="transition"
        )

        edges.append({
            "edge_id": edge_id,
            "edge_type": "PRECEDES",
            "from_node_id": prev_node["node_id"],
            "to_node_id": next_node["node_id"],
            "confidence": 1.0,
            "weight": abs(next_sev - prev_sev) / 3.0,  # Normalize to 0-1
            "notes": f"Regime transition: {prev_state.regime} -> {next_state.regime}",
            "metadata": _json_canonical({
                "from_date": prev_state.date,
                "to_date": next_state.date,
                "from_regime": prev_state.regime,
                "to_regime": next_state.regime,
                "direction": direction,
                "severity_delta": next_sev - prev_sev,
                "is_transition": True,
                "assertion_level": "FACT",
            }),
        })

    return edges


def generate_feature_lead_edges(
    feature_correlations: Dict[str, Dict[str, int]],
    *,
    min_correlation: float = 0.5,
) -> List[Dict]:
    """
    Generate LEADS edges between features based on cross-correlation.

    Args:
        feature_correlations: Dict mapping feature pairs to lead/lag months
            e.g., {"m2_gap": {"cpi_yoy": 3}} means m2_gap leads cpi_yoy by 3 months
        min_correlation: Minimum correlation strength to emit edge

    Returns:
        List of LEADS edge dicts
    """
    edges = []

    for from_feature, targets in feature_correlations.items():
        for to_feature, lag_months in targets.items():
            if lag_months <= 0:
                continue  # Only emit forward leads

            from_id = f"feature:{from_feature}"
            to_id = f"feature:{to_feature}"

            edge_id = _stable_edge_id("LEADS", from_id, to_id, salt=str(lag_months))

            edges.append({
                "edge_id": edge_id,
                "edge_type": "LEADS",
                "from_node_id": from_id,
                "to_node_id": to_id,
                "confidence": min_correlation,
                "notes": f"{from_feature} leads {to_feature} by {lag_months} months",
                "metadata": _json_canonical({
                    "lead_months": lag_months,
                    "from_feature": from_feature,
                    "to_feature": to_feature,
                    "correlation": min_correlation,
                    "assertion_level": "INFERENCE",
                }),
            })

    return edges


# Known empirical lead/lag relationships (can be computed from data later)
EMPIRICAL_FEATURE_LEADS = {
    "m2_yoy": {
        "cpi_yoy": 12,      # M2 leads CPI by ~12 months
        "housing_yoy": 6,   # M2 leads housing by ~6 months
    },
    "housing_yoy": {
        "cpi_yoy": 3,       # Housing leads CPI by ~3 months (OER lag)
    },
    "m2_cpi_gap": {
        "cpi_yoy": 9,       # M2-CPI gap leads inflation by ~9 months
    },
}


def get_empirical_lead_edges() -> List[Dict]:
    """Generate LEADS edges from known empirical relationships."""
    return generate_feature_lead_edges(
        EMPIRICAL_FEATURE_LEADS,
        min_correlation=0.6,
    )


if __name__ == "__main__":
    from .features_from_fred import extract_features
    from .regime_classifier import RegimeClassifier
    from .calibration import load_calibration
    from .graph_nodes import generate_regime_nodes

    # Load and classify
    cal = load_calibration()
    features, _ = extract_features()
    regimes = RegimeClassifier(calibrated=cal).classify_series(features)
    filtered = [r for r in regimes if r.date >= "2020-01"]

    nodes = generate_regime_nodes(regimes, cal.calibration_hash, start_date="2020-01")

    # Generate temporal edges
    seq_edges = generate_regime_sequence_edges(nodes, filtered)
    trans_edges = generate_transition_edges(nodes, filtered)
    lead_edges = get_empirical_lead_edges()

    print(f"Regime sequence edges (PRECEDES): {len(seq_edges)}")
    print(f"Transition edges only: {len(trans_edges)}")
    print(f"Feature LEADS edges: {len(lead_edges)}")

    # Show sample transitions
    print("\nSample transitions:")
    for e in trans_edges[:5]:
        meta = json.loads(e["metadata"])
        print(f"  {meta['from_regime']} -> {meta['to_regime']} ({meta['from_date']})")

    # Show lead/lag relationships
    print("\nFeature lead relationships:")
    for e in lead_edges:
        meta = json.loads(e["metadata"])
        print(f"  {meta['from_feature']} LEADS {meta['to_feature']} by {meta['lead_months']} months")
