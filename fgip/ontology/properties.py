"""
Required and optional properties for FGIP node and edge types.

Defines metadata schema per type for validation.
"""

from typing import Dict, List

# Required and optional metadata fields per node type
NODE_PROPERTIES: Dict[str, Dict[str, List[str]]] = {
    # =========================================================================
    # Regime nodes
    # =========================================================================
    "REGIME_STATE": {
        "required": ["date_key", "regime", "confidence", "Se"],
        "optional": ["H", "C", "D", "drivers", "calibration_hash", "regime_receipt_id",
                     "lead_lag", "raw_values", "logical_id", "content_hash", "is_latest"],
    },

    # =========================================================================
    # Thesis nodes
    # =========================================================================
    "THESIS": {
        "required": ["claim", "time_horizon", "falsifiability"],
        "optional": ["scope", "risk_factors", "sector", "tickers", "conviction_level",
                     "source_diversity_required", "logical_id", "content_hash", "is_latest"],
    },

    # =========================================================================
    # Hypothesis nodes
    # =========================================================================
    "HYPOTHESIS": {
        "required": ["hypothesis_id", "predicate_description", "deadline"],
        "optional": ["evaluation_window_months", "hypothesis_type", "confidence",
                     "required_sensors", "calibration_hash", "regime_receipt_id",
                     "source_regime_node_id", "target_thesis_ids"],
    },

    # =========================================================================
    # Corporate nodes
    # =========================================================================
    "COMPANY": {
        "required": [],  # name is in node, not metadata
        "optional": ["cik", "ticker", "sector", "lei", "sic_code", "gics_sector",
                     "market_cap", "headquarters", "founded"],
    },
    "FINANCIAL_INST": {
        "required": [],
        "optional": ["cik", "ticker", "aum", "institution_type", "lei"],
    },
    "ETF_FUND": {
        "required": [],
        "optional": ["ticker", "expense_ratio", "aum", "tracking_index"],
    },

    # =========================================================================
    # Government nodes
    # =========================================================================
    "AGENCY": {
        "required": [],
        "optional": ["parent_agency", "abbreviation", "budget", "employees"],
    },
    "LEGISLATION": {
        "required": [],
        "optional": ["congress", "bill_type", "bill_number", "enacted_date", "status"],
    },
    "PROGRAM": {
        "required": [],
        "optional": ["cfda_number", "sam_uei", "funding_level", "agency"],
    },

    # =========================================================================
    # Physical nodes
    # =========================================================================
    "FACILITY": {
        "required": [],
        "optional": ["facility_type", "capacity", "owner", "location", "coordinates"],
    },
    "LOCATION": {
        "required": [],
        "optional": ["country", "state", "city", "coordinates", "region"],
    },
    "PROJECT": {
        "required": [],
        "optional": ["project_type", "status", "funding", "start_date", "end_date"],
    },

    # =========================================================================
    # Person nodes
    # =========================================================================
    "PERSON": {
        "required": [],
        "optional": ["title", "organization", "orcid", "linkedin", "biography"],
    },
    "ORGANIZATION": {
        "required": [],
        "optional": ["org_type", "headquarters", "founded", "mission"],
    },

    # =========================================================================
    # Default (fallback for unknown types)
    # =========================================================================
    "_DEFAULT": {
        "required": [],
        "optional": [],
    },
}


# Required and optional metadata fields per edge type
EDGE_PROPERTIES: Dict[str, Dict[str, List[str]]] = {
    # =========================================================================
    # Regime edges
    # =========================================================================
    "MODULATES": {
        "required": ["assertion_level"],
        "optional": ["regime", "date", "drivers", "calibration_hash", "regime_receipt_id",
                     "coherence_gate", "Se", "C"],
    },
    "INCREASES_RISK_FOR": {
        "required": ["assertion_level"],
        "optional": ["regime", "date", "drivers", "base_risk", "calibration_hash",
                     "regime_receipt_id", "coherence_gate", "Se", "C"],
    },
    "AFFECTS_CONVICTION": {
        "required": ["assertion_level"],
        "optional": ["regime", "direction", "magnitude"],
    },

    # =========================================================================
    # Hypothesis edges
    # =========================================================================
    "PREDICTS": {
        "required": ["assertion_level"],
        "optional": ["hypothesis_id", "deadline", "predicate_description",
                     "calibration_hash", "regime_receipt_id"],
    },
    "CONFIRMS": {
        "required": ["assertion_level"],
        "optional": ["hypothesis_id", "deadline", "evaluated_at", "outcome",
                     "coverage", "sensor_values", "coherence_met"],
    },
    "DID_NOT_MATERIALIZE": {
        "required": ["assertion_level"],
        "optional": ["hypothesis_id", "deadline", "evaluated_at", "outcome",
                     "strength", "coverage", "sensor_values", "coherence_met"],
    },
    "EVALUATED_AT": {
        "required": ["assertion_level"],
        "optional": ["hypothesis_id", "evaluation_month", "regime", "outcome",
                     "window_start_month", "window_end_month", "regime_Se", "regime_C"],
    },

    # =========================================================================
    # Temporal edges
    # =========================================================================
    "PRECEDES": {
        "required": ["assertion_level"],
        "optional": ["from_date", "to_date", "from_regime", "to_regime",
                     "is_transition", "transition_type", "direction", "severity_delta"],
    },
    "LEADS": {
        "required": ["assertion_level"],
        "optional": ["lead_months", "from_feature", "to_feature", "correlation"],
    },

    # =========================================================================
    # Belief revision edges
    # =========================================================================
    "SUPERSEDES": {
        "required": ["assertion_level"],
        "optional": ["logical_id", "old_hash", "new_hash", "reason", "diff_keys"],
    },

    # =========================================================================
    # Entity resolution edges
    # =========================================================================
    "SAME_AS": {
        "required": ["assertion_level"],
        "optional": ["match_type", "status", "confidence", "reason"],
    },
    "MERGED_INTO": {
        "required": ["assertion_level"],
        "optional": ["merged_at", "merged_by", "original_node_ids"],
    },

    # =========================================================================
    # Default (fallback for unknown types)
    # =========================================================================
    "_DEFAULT": {
        "required": [],
        "optional": [],
    },
}


def validate_properties(
    obj_type: str,
    metadata: dict,
    category: str = "node"
) -> List[str]:
    """
    Validate metadata has required properties for this type.

    Args:
        obj_type: Node type or edge type name
        metadata: Parsed metadata dict
        category: "node" or "edge"

    Returns:
        List of missing required property names (empty if valid)
    """
    props = NODE_PROPERTIES if category == "node" else EDGE_PROPERTIES
    spec = props.get(obj_type, props.get("_DEFAULT", {"required": [], "optional": []}))

    return [p for p in spec["required"] if p not in metadata]


def get_all_properties(obj_type: str, category: str = "node") -> Dict[str, List[str]]:
    """
    Get all required and optional properties for a type.

    Args:
        obj_type: Node type or edge type name
        category: "node" or "edge"

    Returns:
        Dict with "required" and "optional" lists
    """
    props = NODE_PROPERTIES if category == "node" else EDGE_PROPERTIES
    return props.get(obj_type, props.get("_DEFAULT", {"required": [], "optional": []}))
