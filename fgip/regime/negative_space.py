"""
Negative space tracking for FGIP graph.

Records failed expectations as first-class graph facts:
- HYPOTHESIS nodes with testable predicates and deadlines
- PREDICTS edges from hypothesis → target thesis
- DID_NOT_MATERIALIZE / CONFIRMS edges based on evaluation outcome

Key insight: "We said X should happen by date Y → it didn't → that itself is evidence."

v1.0: Graph-native hypotheses using existing sensors (CPI, housing, M2-gap)
"""

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .regime_classifier import RegimeState
from .features_from_fred import FREDFeatures
from .graph_nodes import DEFAULT_COHERENCE_GATE


# ============================================================================
# Canonical JSON helpers (match graph_nodes.py pattern)
# ============================================================================

def _json_canonical(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _stable_edge_id(edge_type: str, from_id: str, to_id: str, salt: str = "") -> str:
    h = hashlib.sha256(f"{edge_type}|{from_id}|{to_id}|{salt}".encode("utf-8")).hexdigest()
    return f"{edge_type.lower()}-{h[:16]}"


# ============================================================================
# Dataclasses
# ============================================================================

@dataclass
class HypothesisDefinition:
    """
    Definition of a testable hypothesis with expiration.

    Graph-native: uses existing sensor infrastructure (CPI, housing, M2-gap).
    """
    hypothesis_id: str                    # e.g., "hyp:escalation-2021-04"
    predicate_description: str            # Human-readable test condition
    predicate_fn_name: str                # Name of predicate function (for audit)

    # Temporal bounds
    created_at: str                       # YYYY-MM-DD when hypothesis created
    deadline: str                         # YYYY-MM-DD when evaluation required
    evaluation_window_months: int = 3     # Months after deadline to check

    # Linkage
    source_regime_node_id: Optional[str] = None  # Regime that triggered
    target_thesis_ids: List[str] = field(default_factory=list)

    # Sensor requirements
    required_sensors: List[str] = field(default_factory=list)

    # Classification
    hypothesis_type: str = "escalation"   # escalation | persistence | lead_relationship
    confidence: float = 0.7

    # Provenance
    calibration_hash: Optional[str] = None
    regime_receipt_id: Optional[str] = None


@dataclass
class EvaluationResult:
    """Result of evaluating a hypothesis at/after deadline."""
    hypothesis_id: str
    evaluated_at: str                     # ISO timestamp
    deadline: str
    sensors_available: bool
    coherence_met: bool

    outcome: str                          # "MATERIALIZED" | "DID_NOT_MATERIALIZE" | "INCONCLUSIVE"
    strength: Optional[str] = None        # "ABSENCE" | "COUNTER_OBSERVATION"
    coverage: float = 0.0                 # 0-1

    sensor_values: Dict[str, Any] = field(default_factory=dict)
    predicate_result: bool = False
    notes: str = ""


# ============================================================================
# Predicate Functions (graph-native)
# ============================================================================

def predicate_escalation_to_crisis(
    regime_states: List[RegimeState],
    trigger_date: str,
    window_months: int = 6,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Predicate: Regime escalates from STRESS to CRISIS within window.

    Returns: (materialized, notes, sensor_values)
    """
    trigger_dt = datetime.strptime(trigger_date, "%Y-%m-%d")
    deadline_dt = trigger_dt + relativedelta(months=window_months)

    # Find regimes in evaluation window
    window_states = []
    for r in regime_states:
        r_dt = datetime.strptime(r.date, "%Y-%m-%d")
        if trigger_dt <= r_dt <= deadline_dt:
            window_states.append(r)

    if not window_states:
        return False, "No regime data in evaluation window", {}

    # Check if CRISIS occurred
    crisis_months = [r for r in window_states if r.regime == "CRISIS"]

    if crisis_months:
        return True, f"Escalated to CRISIS in {crisis_months[0].date}", {
            "crisis_date": crisis_months[0].date,
            "crisis_Se": crisis_months[0].Se,
        }
    else:
        # Check for counter-observation (de-escalation)
        last_state = window_states[-1]
        if last_state.regime in ("NORMAL", "LOW"):
            return False, f"De-escalated to {last_state.regime} instead", {
                "final_regime": last_state.regime,
                "counter_observation": True,
            }
        return False, f"Remained at {last_state.regime}, no escalation", {
            "final_regime": last_state.regime,
        }


def predicate_regime_persistence(
    regime_states: List[RegimeState],
    trigger_date: str,
    target_regime: str = "CRISIS",
    min_months: int = 6,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Predicate: Regime persists at target level for N+ months.

    Returns: (materialized, notes, sensor_values)
    """
    trigger_dt = datetime.strptime(trigger_date, "%Y-%m-%d")
    deadline_dt = trigger_dt + relativedelta(months=min_months)

    # Get regimes from trigger to deadline
    window_states = []
    for r in regime_states:
        r_dt = datetime.strptime(r.date, "%Y-%m-%d")
        if trigger_dt <= r_dt <= deadline_dt:
            window_states.append(r)

    if not window_states:
        return False, "No regime data in evaluation window", {}

    # Check persistence
    at_target = [r for r in window_states if r.regime == target_regime]
    persistence_pct = len(at_target) / len(window_states) if window_states else 0

    if persistence_pct >= 0.8:  # 80% of months at target level
        return True, f"{target_regime} persisted for {len(at_target)}/{len(window_states)} months", {
            "persistence_months": len(at_target),
            "total_months": len(window_states),
            "persistence_pct": round(persistence_pct, 2),
        }
    else:
        final_regime = window_states[-1].regime if window_states else "UNKNOWN"
        return False, f"{target_regime} did not persist ({len(at_target)}/{len(window_states)} months)", {
            "persistence_months": len(at_target),
            "total_months": len(window_states),
            "final_regime": final_regime,
            "counter_observation": final_regime != target_regime,
        }


def predicate_lead_relationship_holds(
    features: List[FREDFeatures],
    leader: str,
    follower: str,
    trigger_date: str,
    expected_lag_months: int = 12,
    tolerance_pct: float = 0.3,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Predicate: Leader feature spike leads to follower spike within lag window.

    Returns: (materialized, notes, sensor_values)
    """
    trigger_dt = datetime.strptime(trigger_date, "%Y-%m-%d")
    lag_start = trigger_dt + relativedelta(months=expected_lag_months - 2)
    lag_end = trigger_dt + relativedelta(months=expected_lag_months + 2)

    # Get leader value at trigger
    leader_val = None
    for f in features:
        if f.date == trigger_date:
            leader_val = getattr(f, leader, None)
            break

    if leader_val is None:
        return False, f"No {leader} data at trigger date", {}

    # Get follower values in lag window
    follower_vals = []
    for f in features:
        f_dt = datetime.strptime(f.date, "%Y-%m-%d")
        if lag_start <= f_dt <= lag_end:
            val = getattr(f, follower, None)
            if val is not None:
                follower_vals.append((f.date, val))

    if not follower_vals:
        return False, f"No {follower} data in lag window", {}

    # Check if follower shows similar direction/magnitude
    max_follower = max(follower_vals, key=lambda x: abs(x[1]))

    # Simple correlation check: same sign and within tolerance
    same_direction = (leader_val > 0) == (max_follower[1] > 0)
    within_tolerance = abs(max_follower[1]) >= abs(leader_val) * (1 - tolerance_pct)

    if same_direction and within_tolerance:
        return True, f"{leader} led {follower}: {leader_val:.2f} -> {max_follower[1]:.2f}", {
            "leader": leader,
            "leader_value": leader_val,
            "follower": follower,
            "follower_value": max_follower[1],
            "follower_date": max_follower[0],
        }
    else:
        return False, f"Lead relationship did not hold: {leader}={leader_val:.2f}, {follower}={max_follower[1]:.2f}", {
            "leader": leader,
            "leader_value": leader_val,
            "follower": follower,
            "follower_value": max_follower[1],
            "same_direction": same_direction,
        }


# Predicate registry
PREDICATE_REGISTRY: Dict[str, Callable] = {
    "escalation_to_crisis": predicate_escalation_to_crisis,
    "regime_persistence": predicate_regime_persistence,
    "lead_relationship_holds": predicate_lead_relationship_holds,
}


# ============================================================================
# Hypothesis Generation
# ============================================================================

def generate_escalation_hypothesis(
    regime_state: RegimeState,
    regime_node_id: str,
    target_thesis_ids: List[str],
    calibration_hash: Optional[str] = None,
    regime_receipt_id: Optional[str] = None,
    coherence_gate: float = DEFAULT_COHERENCE_GATE,
) -> Optional[HypothesisDefinition]:
    """
    Generate escalation prediction hypothesis from STRESS regime.

    Only emits if regime is STRESS with C >= coherence_gate.
    """
    if regime_state.regime != "STRESS":
        return None

    if regime_state.C < coherence_gate:
        return None

    trigger_dt = datetime.strptime(regime_state.date, "%Y-%m-%d")
    deadline_dt = trigger_dt + relativedelta(months=6)

    return HypothesisDefinition(
        hypothesis_id=f"hyp:escalation-{regime_state.date[:7]}",
        predicate_description=f"STRESS regime at {regime_state.date} escalates to CRISIS within 6 months",
        predicate_fn_name="escalation_to_crisis",
        created_at=regime_state.date,
        deadline=deadline_dt.strftime("%Y-%m-%d"),
        evaluation_window_months=3,
        source_regime_node_id=regime_node_id,
        target_thesis_ids=target_thesis_ids,
        required_sensors=["cpi_yoy", "housing_yoy", "m2_cpi_gap"],
        hypothesis_type="escalation",
        confidence=0.6 + (regime_state.Se * 0.2),  # Higher Se = higher confidence
        calibration_hash=calibration_hash,
        regime_receipt_id=regime_receipt_id,
    )


def generate_persistence_hypothesis(
    regime_state: RegimeState,
    regime_node_id: str,
    target_thesis_ids: List[str],
    calibration_hash: Optional[str] = None,
    regime_receipt_id: Optional[str] = None,
    coherence_gate: float = DEFAULT_COHERENCE_GATE,
) -> Optional[HypothesisDefinition]:
    """
    Generate persistence prediction hypothesis from CRISIS regime.

    Only emits if regime is CRISIS with C >= coherence_gate.
    """
    if regime_state.regime != "CRISIS":
        return None

    if regime_state.C < coherence_gate:
        return None

    trigger_dt = datetime.strptime(regime_state.date, "%Y-%m-%d")
    deadline_dt = trigger_dt + relativedelta(months=6)

    return HypothesisDefinition(
        hypothesis_id=f"hyp:persistence-{regime_state.date[:7]}",
        predicate_description=f"CRISIS regime at {regime_state.date} persists for 6+ months",
        predicate_fn_name="regime_persistence",
        created_at=regime_state.date,
        deadline=deadline_dt.strftime("%Y-%m-%d"),
        evaluation_window_months=3,
        source_regime_node_id=regime_node_id,
        target_thesis_ids=target_thesis_ids,
        required_sensors=["cpi_yoy", "housing_yoy", "m2_cpi_gap"],
        hypothesis_type="persistence",
        confidence=0.5 + (regime_state.Se * 0.3),
        calibration_hash=calibration_hash,
        regime_receipt_id=regime_receipt_id,
    )


def generate_all_v0_hypotheses(
    regime_states: List[RegimeState],
    regime_nodes: List[Dict],
    target_thesis_ids: List[str],
    calibration_hash: Optional[str] = None,
    regime_receipt_id: Optional[str] = None,
    coherence_gate: float = DEFAULT_COHERENCE_GATE,
) -> List[HypothesisDefinition]:
    """
    Generate all v0 hypotheses from regime states.

    v0 types: escalation, persistence
    """
    hypotheses = []

    for state, node in zip(regime_states, regime_nodes):
        # Escalation hypothesis
        esc = generate_escalation_hypothesis(
            state, node["node_id"], target_thesis_ids,
            calibration_hash, regime_receipt_id, coherence_gate
        )
        if esc:
            hypotheses.append(esc)

        # Persistence hypothesis
        per = generate_persistence_hypothesis(
            state, node["node_id"], target_thesis_ids,
            calibration_hash, regime_receipt_id, coherence_gate
        )
        if per:
            hypotheses.append(per)

    return hypotheses


# ============================================================================
# Node Generation
# ============================================================================

def hypothesis_to_node(hyp: HypothesisDefinition) -> Dict[str, Any]:
    """Convert HypothesisDefinition to graph node dict."""
    description = (
        f"{hyp.predicate_description}. "
        f"Deadline: {hyp.deadline}. Confidence: {hyp.confidence:.0%}"
    )

    return {
        "node_id": hyp.hypothesis_id,
        "node_type": "HYPOTHESIS",
        "name": f"Hypothesis: {hyp.hypothesis_type} ({hyp.created_at[:7]})",
        "description": description,
        "aliases": json.dumps([hyp.hypothesis_type, hyp.created_at], sort_keys=True, separators=(",", ":")),
        "metadata": _json_canonical({
            "hypothesis_id": hyp.hypothesis_id,
            "predicate_description": hyp.predicate_description,
            "predicate_fn_name": hyp.predicate_fn_name,
            "created_at": hyp.created_at,
            "deadline": hyp.deadline,
            "evaluation_window_months": hyp.evaluation_window_months,
            "source_regime_node_id": hyp.source_regime_node_id,
            "target_thesis_ids": hyp.target_thesis_ids,
            "required_sensors": hyp.required_sensors,
            "hypothesis_type": hyp.hypothesis_type,
            "confidence": hyp.confidence,
            "calibration_hash": hyp.calibration_hash,
            "regime_receipt_id": hyp.regime_receipt_id,
        }),
    }


def generate_hypothesis_nodes(hypotheses: List[HypothesisDefinition]) -> List[Dict[str, Any]]:
    """Generate all hypothesis nodes for insertion."""
    return [hypothesis_to_node(h) for h in hypotheses]


# ============================================================================
# Edge Generation
# ============================================================================

def generate_predicts_edges(
    hypothesis_node: Dict,
    hypothesis: HypothesisDefinition,
) -> List[Dict]:
    """Generate PREDICTS edges from hypothesis -> target theses."""
    edges = []

    for thesis_id in hypothesis.target_thesis_ids:
        edge_id = _stable_edge_id(
            "PREDICTS",
            hypothesis_node["node_id"],
            thesis_id,
            salt=hypothesis.deadline
        )

        edges.append({
            "edge_id": edge_id,
            "edge_type": "PREDICTS",
            "from_node_id": hypothesis_node["node_id"],
            "to_node_id": thesis_id,
            "confidence": hypothesis.confidence,
            "notes": f"Hypothesis predicts outcome affecting {thesis_id}",
            "metadata": _json_canonical({
                "hypothesis_id": hypothesis.hypothesis_id,
                "hypothesis_type": hypothesis.hypothesis_type,
                "deadline": hypothesis.deadline,
                "predicate_description": hypothesis.predicate_description,
                "assertion_level": "HYPOTHESIS",
                "calibration_hash": hypothesis.calibration_hash,
                "regime_receipt_id": hypothesis.regime_receipt_id,
            }),
        })

    return edges


def generate_outcome_edges(
    hypothesis: HypothesisDefinition,
    evaluation: EvaluationResult,
    hypothesis_node: Dict,
    hypothesis_receipt_id: Optional[str] = None,
) -> List[Dict]:
    """
    Generate DID_NOT_MATERIALIZE or CONFIRMS edges based on evaluation.

    Only emits when outcome is definitive (not INCONCLUSIVE).
    """
    if evaluation.outcome == "INCONCLUSIVE":
        return []

    edges = []
    edge_type = "CONFIRMS" if evaluation.outcome == "MATERIALIZED" else "DID_NOT_MATERIALIZE"

    for thesis_id in hypothesis.target_thesis_ids:
        edge_id = _stable_edge_id(
            edge_type,
            hypothesis_node["node_id"],
            thesis_id,
            salt=f"{hypothesis.deadline}-{evaluation.evaluated_at[:10]}"
        )

        # Weight: higher for counter-observations, lower for simple absence
        weight = 1.0
        if edge_type == "DID_NOT_MATERIALIZE":
            weight = 0.9 if evaluation.strength == "COUNTER_OBSERVATION" else 0.6

        edges.append({
            "edge_id": edge_id,
            "edge_type": edge_type,
            "from_node_id": hypothesis_node["node_id"],
            "to_node_id": thesis_id,
            "confidence": evaluation.coverage,
            "weight": weight,
            "notes": evaluation.notes,
            "metadata": _json_canonical({
                "hypothesis_id": hypothesis.hypothesis_id,
                "deadline": hypothesis.deadline,
                "evaluated_at": evaluation.evaluated_at,
                "predicate_description": hypothesis.predicate_description,
                "evaluation_window_months": hypothesis.evaluation_window_months,
                "result": evaluation.predicate_result,
                "outcome": evaluation.outcome,
                "strength": evaluation.strength,
                "coverage": evaluation.coverage,
                "sensor_values": evaluation.sensor_values,
                "sensors_available": evaluation.sensors_available,
                "coherence_met": evaluation.coherence_met,
                "assertion_level": "INFERENCE",
                "calibration_hash": hypothesis.calibration_hash,
                "regime_receipt_id": hypothesis.regime_receipt_id,
                "hypothesis_receipt_id": hypothesis_receipt_id,
            }),
        })

    return edges


def generate_evaluated_at_edges(
    hypothesis: HypothesisDefinition,
    evaluation: EvaluationResult,
    hypothesis_node: Dict,
    regime_nodes: List[Dict],
    regime_states: List[RegimeState],
) -> List[Dict]:
    """
    Generate EVALUATED_AT edge linking hypothesis to regime context.

    This makes "failed predictions during CRISIS" a graph traversal:
    REGIME_STATE (CRISIS) ← [EVALUATED_AT] ← HYPOTHESIS → DID_NOT_MATERIALIZE → THESIS

    Direction: HYPOTHESIS -> REGIME_STATE (hypothesis evaluated in context of regime)

    Fixed in v1.4.1:
    - Map-based regime lookup (no zip alignment assumption)
    - Explicit window_start_month/window_end_month in metadata

    Only emits when:
    - Outcome is definitive (not INCONCLUSIVE)
    - Can find regime node for evaluation month
    """
    if evaluation.outcome == "INCONCLUSIVE":
        return []

    # Extract evaluation month (YYYY-MM)
    eval_month = evaluation.evaluated_at[:7]

    # Build separate maps (no alignment assumption)
    # This is safe under belief revision / sorting changes
    regime_node_by_month: Dict[str, Dict] = {}
    for node in regime_nodes:
        meta_str = node.get("metadata", "{}")
        try:
            meta = json.loads(meta_str) if isinstance(meta_str, str) else meta_str
            date_key = meta.get("date_key")
            if date_key:
                regime_node_by_month[date_key] = node
        except (json.JSONDecodeError, TypeError):
            continue

    regime_state_by_month: Dict[str, RegimeState] = {}
    for state in regime_states:
        date_key = state.date[:7]  # YYYY-MM
        regime_state_by_month[date_key] = state

    # Find regime node for evaluation month
    regime_node = regime_node_by_month.get(eval_month)
    regime_state = regime_state_by_month.get(eval_month)

    # Fall back to closest prior month if exact match not found
    if regime_node is None:
        sorted_months = sorted(regime_node_by_month.keys(), reverse=True)
        for month in sorted_months:
            if month < eval_month:
                regime_node = regime_node_by_month[month]
                regime_state = regime_state_by_month.get(month)
                break

    if regime_node is None or regime_state is None:
        return []

    # Compute evaluation window boundaries
    deadline_dt = datetime.strptime(hypothesis.deadline, "%Y-%m-%d")
    window_start = deadline_dt
    window_end = deadline_dt + relativedelta(months=hypothesis.evaluation_window_months)

    # Create EVALUATED_AT edge
    edge_id = _stable_edge_id(
        "EVALUATED_AT",
        hypothesis_node["node_id"],
        regime_node["node_id"],
        salt=f"{hypothesis.hypothesis_id}|{eval_month}"
    )

    return [{
        "edge_id": edge_id,
        "edge_type": "EVALUATED_AT",
        "from_node_id": hypothesis_node["node_id"],
        "to_node_id": regime_node["node_id"],
        "confidence": 1.0,  # Factual: we did evaluate at this time
        "weight": 1.0,
        "notes": f"Hypothesis {hypothesis.hypothesis_id} evaluated in {regime_state.regime} regime ({eval_month})",
        "metadata": _json_canonical({
            "hypothesis_id": hypothesis.hypothesis_id,
            "evaluation_date": evaluation.evaluated_at,
            "evaluation_month": eval_month,
            "deadline": hypothesis.deadline,
            "evaluation_window_months": hypothesis.evaluation_window_months,
            "window_start_month": window_start.strftime("%Y-%m"),
            "window_end_month": window_end.strftime("%Y-%m"),
            "regime": regime_state.regime,
            "regime_Se": regime_state.Se,
            "regime_C": regime_state.C,
            "outcome": evaluation.outcome,
            "strength": evaluation.strength,
            "assertion_level": "FACT",  # Observable: we evaluated it at this time
            "calibration_hash": hypothesis.calibration_hash,
            "regime_receipt_id": hypothesis.regime_receipt_id,
        }),
    }]


# ============================================================================
# Evaluation
# ============================================================================

def evaluate_hypothesis(
    hypothesis: HypothesisDefinition,
    features: List[FREDFeatures],
    regime_states: List[RegimeState],
    current_date: str,
    coherence_gate: float = DEFAULT_COHERENCE_GATE,
) -> EvaluationResult:
    """
    Evaluate hypothesis at/after deadline.

    Returns INCONCLUSIVE if:
    - Deadline not yet reached
    - Required sensors unavailable
    - Coherence conditions not met
    """
    evaluated_at = datetime.now(timezone.utc).isoformat()

    # Check if deadline has passed
    deadline_dt = datetime.strptime(hypothesis.deadline, "%Y-%m-%d")
    current_dt = datetime.strptime(current_date, "%Y-%m-%d")

    if current_dt < deadline_dt:
        return EvaluationResult(
            hypothesis_id=hypothesis.hypothesis_id,
            evaluated_at=evaluated_at,
            deadline=hypothesis.deadline,
            sensors_available=True,
            coherence_met=True,
            outcome="INCONCLUSIVE",
            notes=f"Deadline {hypothesis.deadline} not yet reached",
        )

    # Check sensor availability
    trigger_dt = datetime.strptime(hypothesis.created_at, "%Y-%m-%d")
    window_features = [
        f for f in features
        if trigger_dt <= datetime.strptime(f.date, "%Y-%m-%d") <= deadline_dt
    ]

    if not window_features:
        return EvaluationResult(
            hypothesis_id=hypothesis.hypothesis_id,
            evaluated_at=evaluated_at,
            deadline=hypothesis.deadline,
            sensors_available=False,
            coherence_met=True,
            outcome="INCONCLUSIVE",
            notes="No sensor data available in evaluation window",
        )

    # Check coherence in window
    window_regimes = [
        r for r in regime_states
        if trigger_dt <= datetime.strptime(r.date, "%Y-%m-%d") <= deadline_dt
    ]

    high_coherence = [r for r in window_regimes if r.C >= coherence_gate]
    if not high_coherence:
        return EvaluationResult(
            hypothesis_id=hypothesis.hypothesis_id,
            evaluated_at=evaluated_at,
            deadline=hypothesis.deadline,
            sensors_available=True,
            coherence_met=False,
            outcome="INCONCLUSIVE",
            notes=f"No regime in window met coherence gate C >= {coherence_gate}",
        )

    # Execute predicate
    predicate_fn = PREDICATE_REGISTRY.get(hypothesis.predicate_fn_name)
    if predicate_fn is None:
        return EvaluationResult(
            hypothesis_id=hypothesis.hypothesis_id,
            evaluated_at=evaluated_at,
            deadline=hypothesis.deadline,
            sensors_available=True,
            coherence_met=True,
            outcome="INCONCLUSIVE",
            notes=f"Unknown predicate: {hypothesis.predicate_fn_name}",
        )

    # Call predicate based on type
    if hypothesis.predicate_fn_name == "escalation_to_crisis":
        materialized, notes, sensor_values = predicate_fn(
            regime_states, hypothesis.created_at, 6
        )
    elif hypothesis.predicate_fn_name == "regime_persistence":
        materialized, notes, sensor_values = predicate_fn(
            regime_states, hypothesis.created_at, "CRISIS", 6
        )
    else:
        materialized, notes, sensor_values = predicate_fn(
            features, hypothesis.created_at
        )

    # Determine strength for DID_NOT_MATERIALIZE
    strength = None
    if not materialized:
        if sensor_values.get("counter_observation"):
            strength = "COUNTER_OBSERVATION"
        else:
            strength = "ABSENCE"

    # Compute coverage
    coverage = len(window_features) / max(1, hypothesis.evaluation_window_months + 6)
    coverage = min(1.0, coverage)

    return EvaluationResult(
        hypothesis_id=hypothesis.hypothesis_id,
        evaluated_at=evaluated_at,
        deadline=hypothesis.deadline,
        sensors_available=True,
        coherence_met=True,
        outcome="MATERIALIZED" if materialized else "DID_NOT_MATERIALIZE",
        strength=strength,
        coverage=coverage,
        sensor_values=sensor_values,
        predicate_result=materialized,
        notes=notes,
    )


# ============================================================================
# Receipt Generation
# ============================================================================

def write_negative_space_receipt(
    hypotheses: List[HypothesisDefinition],
    evaluations: List[EvaluationResult],
    nodes_generated: int,
    edges_generated: int,
    calibration_hash: Optional[str] = None,
    regime_receipt_id: Optional[str] = None,
    output_dir: str = "receipts/regime/negative_space",
) -> str:
    """Write negative-space-run receipt per evaluation."""
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    receipt_id = f"negative-space-run-{timestamp}"
    receipt_path = Path(output_dir) / f"{receipt_id}.json"

    # Count outcomes
    materialized = sum(1 for e in evaluations if e.outcome == "MATERIALIZED")
    did_not = sum(1 for e in evaluations if e.outcome == "DID_NOT_MATERIALIZE")
    inconclusive = sum(1 for e in evaluations if e.outcome == "INCONCLUSIVE")

    receipt = {
        "receipt_id": receipt_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "operation": "hypothesis_evaluation",
        "version": "1.0.0",
        "inputs": {
            "hypotheses_count": len(hypotheses),
            "hypothesis_ids": [h.hypothesis_id for h in hypotheses],
        },
        "outputs": {
            "total_evaluated": len(evaluations),
            "materialized_count": materialized,
            "did_not_materialize_count": did_not,
            "inconclusive_count": inconclusive,
            "nodes_generated": nodes_generated,
            "edges_generated": edges_generated,
        },
        "evaluations": [
            {
                "hypothesis_id": e.hypothesis_id,
                "deadline": e.deadline,
                "outcome": e.outcome,
                "strength": e.strength,
                "coverage": round(e.coverage, 3),
                "notes": e.notes,
            }
            for e in evaluations
        ],
        "provenance": {
            "calibration_hash": calibration_hash,
            "regime_receipt_id": regime_receipt_id,
        },
        "success": True,
    }

    with open(receipt_path, 'w') as f:
        json.dump(receipt, f, indent=2)

    return str(receipt_path)


# ============================================================================
# Entry Points
# ============================================================================

def run_hypothesis_generation(
    regime_states: List[RegimeState],
    regime_nodes: List[Dict],
    target_thesis_ids: List[str],
    calibration_hash: Optional[str] = None,
    regime_receipt_id: Optional[str] = None,
    coherence_gate: float = DEFAULT_COHERENCE_GATE,
) -> Tuple[List[Dict], List[Dict]]:
    """
    Generate hypothesis nodes and PREDICTS edges.

    Returns: (hypothesis_nodes, predicts_edges)
    """
    hypotheses = generate_all_v0_hypotheses(
        regime_states, regime_nodes, target_thesis_ids,
        calibration_hash, regime_receipt_id, coherence_gate
    )

    nodes = generate_hypothesis_nodes(hypotheses)

    edges = []
    for hyp, node in zip(hypotheses, nodes):
        edges.extend(generate_predicts_edges(node, hyp))

    return nodes, edges


def run_hypothesis_evaluation(
    hypotheses: List[HypothesisDefinition],
    features: List[FREDFeatures],
    regime_states: List[RegimeState],
    current_date: Optional[str] = None,
    calibration_hash: Optional[str] = None,
    regime_receipt_id: Optional[str] = None,
    output_dir: str = "receipts/regime/negative_space",
    regime_nodes: Optional[List[Dict]] = None,
) -> Tuple[List[Dict], str]:
    """
    Evaluate all hypotheses and generate outcome + EVALUATED_AT edges.

    Args:
        hypotheses: List of hypotheses to evaluate
        features: FRED features for evaluation
        regime_states: Regime states for context
        current_date: Date to evaluate against (default: now)
        calibration_hash: For provenance
        regime_receipt_id: For provenance
        output_dir: Where to write receipt
        regime_nodes: If provided, generates EVALUATED_AT edges linking to regime context

    Returns: (outcome_edges + evaluated_at_edges, receipt_path)
    """
    if current_date is None:
        current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    evaluations = []
    outcome_edges = []
    evaluated_at_edges = []

    for hyp in hypotheses:
        # Evaluate
        result = evaluate_hypothesis(
            hyp, features, regime_states, current_date
        )
        evaluations.append(result)

        # Generate edges if definitive outcome
        if result.outcome != "INCONCLUSIVE":
            node = hypothesis_to_node(hyp)
            edges = generate_outcome_edges(hyp, result, node)
            outcome_edges.extend(edges)

            # Generate EVALUATED_AT edge if regime nodes provided
            if regime_nodes is not None:
                eval_edges = generate_evaluated_at_edges(
                    hyp, result, node, regime_nodes, regime_states
                )
                evaluated_at_edges.extend(eval_edges)

    # Combine all edges
    all_edges = outcome_edges + evaluated_at_edges

    # Write receipt
    receipt_path = write_negative_space_receipt(
        hypotheses, evaluations,
        nodes_generated=len(hypotheses),
        edges_generated=len(all_edges),
        calibration_hash=calibration_hash,
        regime_receipt_id=regime_receipt_id,
        output_dir=output_dir,
    )

    return all_edges, receipt_path


# ============================================================================
# Test
# ============================================================================

if __name__ == "__main__":
    from .features_from_fred import extract_features
    from .regime_classifier import RegimeClassifier
    from .calibration import load_calibration
    from .graph_nodes import generate_regime_nodes
    from .thesis_nodes import get_all_canonical_thesis_ids

    # Load data
    cal = load_calibration()
    features, _ = extract_features()
    classifier = RegimeClassifier(calibrated=cal)
    regimes = classifier.classify_series(features)
    filtered = [r for r in regimes if r.date >= "2020-01"]

    regime_nodes = generate_regime_nodes(
        regimes, cal.calibration_hash,
        start_date="2020-01",
        regime_receipt_id="test-run"
    )

    thesis_ids = get_all_canonical_thesis_ids()

    # Generate hypotheses
    print("=== HYPOTHESIS GENERATION ===")
    hyp_nodes, predicts_edges = run_hypothesis_generation(
        regime_states=filtered,
        regime_nodes=regime_nodes,
        target_thesis_ids=thesis_ids,
        calibration_hash=cal.calibration_hash,
        regime_receipt_id="test-run",
    )
    print(f"Hypothesis nodes: {len(hyp_nodes)}")
    print(f"PREDICTS edges: {len(predicts_edges)}")

    # Show sample hypotheses
    print("\nSample hypotheses:")
    for node in hyp_nodes[:3]:
        meta = json.loads(node["metadata"])
        print(f"  {meta['hypothesis_id']}: {meta['hypothesis_type']}")
        print(f"    Deadline: {meta['deadline']}")

    # Generate hypotheses for evaluation
    hypotheses = generate_all_v0_hypotheses(
        filtered, regime_nodes, thesis_ids,
        cal.calibration_hash, "test-run"
    )

    # Evaluate (use latest date in data)
    current_date = features[-1].date if features else "2025-12-01"

    print(f"\n=== HYPOTHESIS EVALUATION (as of {current_date}) ===")
    outcome_edges, receipt = run_hypothesis_evaluation(
        hypotheses, features, regimes,
        current_date=current_date,
        calibration_hash=cal.calibration_hash,
        regime_receipt_id="test-run",
    )

    print(f"Outcome edges: {len(outcome_edges)}")
    print(f"Receipt: {receipt}")

    # Show outcomes
    materialized = [e for e in outcome_edges if e["edge_type"] == "CONFIRMS"]
    did_not = [e for e in outcome_edges if e["edge_type"] == "DID_NOT_MATERIALIZE"]

    print(f"\n  CONFIRMS: {len(materialized)}")
    print(f"  DID_NOT_MATERIALIZE: {len(did_not)}")

    if did_not:
        sample = did_not[0]
        meta = json.loads(sample["metadata"])
        print(f"\nSample DID_NOT_MATERIALIZE:")
        print(f"  {meta['hypothesis_id']}")
        print(f"  Strength: {meta['strength']}")
        print(f"  Notes: {sample['notes'][:60]}...")
