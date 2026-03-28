"""
Edge type constraints for FGIP ontology.

Defines which edge types are valid between which node type pairs.
Uses "*" as wildcard for "any type" (forward-compatible).
"""

from typing import List, Tuple

# Allowed (from_type, to_type) pairs for each edge type
# "*" = any type (wildcard)
EDGE_TYPE_CONSTRAINTS = {
    # =========================================================================
    # Regime-related edges
    # =========================================================================
    "MODULATES": [
        ("REGIME_STATE", "THESIS"),
    ],
    "INCREASES_RISK_FOR": [
        ("REGIME_STATE", "THESIS"),
    ],
    "AFFECTS_CONVICTION": [
        ("REGIME_STATE", "THESIS"),
    ],

    # =========================================================================
    # Hypothesis/Negative Space edges
    # =========================================================================
    "PREDICTS": [
        ("HYPOTHESIS", "THESIS"),
        ("HYPOTHESIS", "REGIME_STATE"),
    ],
    "CONFIRMS": [
        ("HYPOTHESIS", "THESIS"),
        ("HYPOTHESIS", "REGIME_STATE"),
    ],
    "DID_NOT_MATERIALIZE": [
        ("HYPOTHESIS", "THESIS"),
    ],
    "EVALUATED_AT": [
        ("HYPOTHESIS", "REGIME_STATE"),
    ],
    "FALSIFIED_BY": [
        ("HYPOTHESIS", "THESIS"),
        ("HYPOTHESIS", "REGIME_STATE"),
    ],

    # =========================================================================
    # Temporal edges
    # =========================================================================
    "PRECEDES": [
        ("REGIME_STATE", "REGIME_STATE"),
        ("*", "*"),  # Allow generic temporal ordering
    ],
    "FOLLOWS": [
        ("REGIME_STATE", "REGIME_STATE"),
        ("*", "*"),
    ],
    "LEADS": [
        ("*", "*"),  # Features not typed yet
    ],

    # =========================================================================
    # Belief revision edges
    # =========================================================================
    "SUPERSEDES": [
        ("*", "*"),  # Same type replaces same type (validated separately)
    ],
    "INVALIDATES": [
        ("*", "*"),
    ],
    "WEAKENS": [
        ("*", "*"),
    ],

    # =========================================================================
    # Entity resolution edges
    # =========================================================================
    "SAME_AS": [
        ("*", "*"),  # Same type only (validated separately in resolver)
    ],
    "MERGED_INTO": [
        ("*", "*"),  # Same type only
    ],

    # =========================================================================
    # Corporate/Ownership edges
    # =========================================================================
    "OWNS_SHARES": [
        ("COMPANY", "COMPANY"),
        ("FINANCIAL_INST", "COMPANY"),
        ("PERSON", "COMPANY"),
        ("ETF_FUND", "COMPANY"),
    ],
    "EMPLOYS": [
        ("COMPANY", "PERSON"),
        ("ORGANIZATION", "PERSON"),
        ("AGENCY", "PERSON"),
    ],
    "SITS_ON_BOARD": [
        ("PERSON", "COMPANY"),
        ("PERSON", "ORGANIZATION"),
    ],
    "INVESTED_IN": [
        ("COMPANY", "COMPANY"),
        ("FINANCIAL_INST", "COMPANY"),
        ("PERSON", "COMPANY"),
    ],
    "INCREASED_POSITION": [
        ("FINANCIAL_INST", "COMPANY"),
        ("ETF_FUND", "COMPANY"),
    ],
    "DECREASED_POSITION": [
        ("FINANCIAL_INST", "COMPANY"),
        ("ETF_FUND", "COMPANY"),
    ],

    # =========================================================================
    # Supply chain edges
    # =========================================================================
    "SUPPLIES": [
        ("COMPANY", "COMPANY"),
        ("FACILITY", "COMPANY"),
    ],
    "SUPPLIES_TO": [
        ("COMPANY", "COMPANY"),
    ],
    "CUSTOMER_OF": [
        ("COMPANY", "COMPANY"),
    ],
    "COMPETES_WITH": [
        ("COMPANY", "COMPANY"),
    ],
    "DEPENDS_ON": [
        ("COMPANY", "COMPANY"),
        ("COMPANY", "FACILITY"),
    ],
    "SUBCONTRACTED_TO": [
        ("COMPANY", "COMPANY"),
    ],

    # =========================================================================
    # Government/Policy edges
    # =========================================================================
    "AUTHORIZED_BY": [
        ("PROJECT", "LEGISLATION"),
        ("PROJECT", "PROGRAM"),
        ("PROGRAM", "LEGISLATION"),
    ],
    "IMPLEMENTED_BY": [
        ("LEGISLATION", "AGENCY"),
        ("PROGRAM", "AGENCY"),
    ],
    "RULEMAKING_FOR": [
        ("AGENCY", "LEGISLATION"),
        ("AGENCY", "PROGRAM"),
    ],
    "AWARDED_GRANT": [
        ("AGENCY", "COMPANY"),
        ("AGENCY", "ORGANIZATION"),
        ("PROGRAM", "COMPANY"),
    ],
    "AWARDED_CONTRACT": [
        ("AGENCY", "COMPANY"),
    ],
    "FUNDED_PROJECT": [
        ("COMPANY", "PROJECT"),
        ("AGENCY", "PROJECT"),
    ],
    "LOBBIED_FOR": [
        ("COMPANY", "LEGISLATION"),
        ("ORGANIZATION", "LEGISLATION"),
        ("PERSON", "LEGISLATION"),
    ],
    "LOBBIED_AGAINST": [
        ("COMPANY", "LEGISLATION"),
        ("ORGANIZATION", "LEGISLATION"),
        ("PERSON", "LEGISLATION"),
    ],

    # =========================================================================
    # Location/Facility edges
    # =========================================================================
    "BUILT_IN": [
        ("FACILITY", "LOCATION"),
        ("PROJECT", "LOCATION"),
    ],
    "OPENED_FACILITY": [
        ("COMPANY", "LOCATION"),
    ],
    "CAPACITY_AT": [
        ("COMPANY", "FACILITY"),
    ],
    "BOTTLENECK_AT": [
        ("*", "FACILITY"),
        ("*", "LOCATION"),
    ],

    # =========================================================================
    # Causal/Inferential edges
    # =========================================================================
    "CAUSED": [
        ("*", "*"),
    ],
    "ENABLED": [
        ("*", "*"),
    ],
    "CONTRIBUTED_TO": [
        ("*", "*"),
    ],
    "FACILITATED": [
        ("*", "*"),
    ],
    "PROFITED_FROM": [
        ("COMPANY", "*"),
        ("PERSON", "*"),
        ("FINANCIAL_INST", "*"),
    ],
    "COORDINATED_WITH": [
        ("*", "*"),
    ],

    # =========================================================================
    # Correction layer edges
    # =========================================================================
    "CORRECTS": [
        ("*", "*"),
    ],
    "OPPOSES_CORRECTION": [
        ("*", "*"),
    ],
    "EXPANDED_CAPACITY": [
        ("COMPANY", "*"),
    ],
    "RESHORING_SIGNAL": [
        ("COMPANY", "*"),
    ],

    # =========================================================================
    # Economic mechanism edges
    # =========================================================================
    "REDUCES": [
        ("*", "*"),
    ],
    "BLOCKS": [
        ("*", "*"),
    ],
    "REPLACES": [
        ("*", "*"),
    ],
    "CORRELATES": [
        ("*", "*"),
    ],
    "DERIVES_FROM": [
        ("*", "*"),
    ],
}


def validate_edge_types(
    edge_type: str,
    from_type: str,
    to_type: str
) -> Tuple[bool, str]:
    """
    Check if edge type is valid for this node type pair.

    Args:
        edge_type: The edge type to validate
        from_type: NodeType of the source node
        to_type: NodeType of the target node

    Returns:
        (is_valid, error_message)
    """
    if edge_type not in EDGE_TYPE_CONSTRAINTS:
        # Unknown edge type - allow for forward compatibility
        return True, ""

    allowed = EDGE_TYPE_CONSTRAINTS[edge_type]

    for allowed_from, allowed_to in allowed:
        # Check wildcards or exact match
        from_ok = (allowed_from == "*") or (allowed_from == from_type)
        to_ok = (allowed_to == "*") or (allowed_to == to_type)

        if from_ok and to_ok:
            return True, ""

    # No match found
    allowed_pairs = [f"({f}, {t})" for f, t in allowed]
    return False, (
        f"{edge_type} not valid from {from_type} to {to_type}. "
        f"Allowed: {', '.join(allowed_pairs)}"
    )


def get_allowed_edge_types(from_type: str, to_type: str) -> List[str]:
    """
    Get list of edge types valid for this node type pair.

    Args:
        from_type: NodeType of the source node
        to_type: NodeType of the target node

    Returns:
        List of valid edge type names
    """
    valid = []

    for edge_type, allowed in EDGE_TYPE_CONSTRAINTS.items():
        for allowed_from, allowed_to in allowed:
            from_ok = (allowed_from == "*") or (allowed_from == from_type)
            to_ok = (allowed_to == "*") or (allowed_to == to_type)

            if from_ok and to_ok:
                valid.append(edge_type)
                break

    return valid
