"""
Canonical ID rules for FGIP entity resolution.

Defines patterns for deriving canonical IDs from node metadata
and normalizing entity names for comparison.
"""

import re
from typing import Dict, List, Optional, Tuple


# Canonical ID patterns per node type
# Format: (field_name, regex_pattern)
# Patterns should match the full canonical ID string
CANONICAL_PATTERNS: Dict[str, List[Tuple[str, str]]] = {
    "COMPANY": [
        ("cik", r"^cik:\d{10}$"),              # SEC CIK (10 digits, zero-padded)
        ("lei", r"^lei:[A-Z0-9]{20}$"),        # Legal Entity Identifier (20 chars)
        ("ticker", r"^ticker:[A-Z]{1,5}$"),    # Stock ticker (1-5 uppercase)
    ],
    "FINANCIAL_INST": [
        ("cik", r"^cik:\d{10}$"),
        ("lei", r"^lei:[A-Z0-9]{20}$"),
    ],
    "ETF_FUND": [
        ("ticker", r"^ticker:[A-Z]{1,5}$"),
    ],
    "THESIS": [
        ("thesis_id", r"^thesis:[\w-]+$"),     # Thesis ID format
    ],
    "REGIME_STATE": [
        ("date_key", r"^regime-state-\d{4}-\d{2}$"),  # regime-state-YYYY-MM
    ],
    "HYPOTHESIS": [
        ("hypothesis_id", r"^hyp:[\w-]+$"),   # Hypothesis ID format
    ],
    "PROGRAM": [
        ("cfda", r"^cfda:\d{2}\.\d{3}$"),     # CFDA number (XX.XXX)
        ("sam_uei", r"^uei:[A-Z0-9]{12}$"),   # SAM.gov UEI (12 chars)
    ],
    "PERSON": [
        ("orcid", r"^orcid:\d{4}-\d{4}-\d{4}-\d{4}$"),  # ORCID ID
    ],
    "AGENCY": [
        ("abbreviation", r"^agency:[A-Z]{2,10}$"),  # Agency abbreviation
    ],
    "LEGISLATION": [
        ("bill_id", r"^bill:\d{3}-(hr|s|hjres|sjres|hconres|sconres)-\d+$"),
    ],
}

# Common company name suffixes to remove for normalization
COMPANY_SUFFIXES = [
    r'\s+INC\.?$',
    r'\s+CORP\.?$',
    r'\s+LLC\.?$',
    r'\s+LTD\.?$',
    r'\s+LP\.?$',
    r'\s+LLP\.?$',
    r'\s+PLC\.?$',
    r'\s+SA\.?$',
    r'\s+AG\.?$',
    r'\s+NV\.?$',
    r'\s+BV\.?$',
    r'\s+GMBH\.?$',
    r'\s+CORPORATION$',
    r'\s+INCORPORATED$',
    r'\s+COMPANY$',
    r'\s+COMPANIES$',
    r'\s+CO\.?$',
    r'\s+LIMITED$',
    r'\s+HOLDINGS?$',
    r'\s+GROUP$',
    r'\s+INTERNATIONAL$',
    r'\s+INTL\.?$',
    r',?\s+THE$',
]


def get_canonical_id(node_type: str, node: dict) -> Optional[str]:
    """
    Extract or derive canonical ID for a node.

    Checks node_id first (may already be canonical), then metadata fields.

    Args:
        node_type: The node's type (e.g., "COMPANY")
        node: Node dict with node_id and metadata

    Returns:
        Canonical ID string if determinable, None otherwise
    """
    patterns = CANONICAL_PATTERNS.get(node_type, [])
    if not patterns:
        return None

    # Check if node_id is already canonical
    node_id = node.get("node_id", "")
    for field_name, pattern in patterns:
        if re.match(pattern, node_id):
            return node_id

    # Check metadata fields
    metadata = node.get("metadata", {})
    if isinstance(metadata, str):
        import json
        try:
            metadata = json.loads(metadata)
        except (json.JSONDecodeError, TypeError):
            metadata = {}

    for field_name, pattern in patterns:
        if field_name in metadata:
            value = metadata[field_name]
            if value:
                # Construct canonical ID from field
                canonical = f"{field_name}:{value}"
                if re.match(pattern, canonical):
                    return canonical

                # Try without prefix (some fields already have it)
                if re.match(pattern, str(value)):
                    return str(value)

    return None


def normalize_name(name: str) -> str:
    """
    Normalize entity name for comparison.

    Transformations:
    - Convert to uppercase
    - Remove common suffixes (Inc, Corp, LLC, Ltd, etc.)
    - Remove punctuation
    - Collapse whitespace
    - Strip leading/trailing whitespace

    Args:
        name: Raw entity name

    Returns:
        Normalized name string
    """
    if not name:
        return ""

    name = name.upper()

    # Remove common suffixes
    for suffix in COMPANY_SUFFIXES:
        name = re.sub(suffix, '', name, flags=re.IGNORECASE)

    # Remove punctuation (keep alphanumeric and whitespace)
    name = re.sub(r'[^\w\s]', ' ', name)

    # Collapse whitespace
    name = re.sub(r'\s+', ' ', name).strip()

    return name


def extract_cik(value: str) -> Optional[str]:
    """
    Extract CIK from various formats.

    Args:
        value: String that may contain CIK

    Returns:
        10-digit zero-padded CIK or None
    """
    if not value:
        return None

    # Remove any prefix
    value = re.sub(r'^cik:?', '', value, flags=re.IGNORECASE)

    # Extract digits
    digits = re.sub(r'\D', '', value)

    if digits and len(digits) <= 10:
        # Zero-pad to 10 digits
        return digits.zfill(10)

    return None


def extract_ticker(value: str) -> Optional[str]:
    """
    Extract stock ticker from various formats.

    Args:
        value: String that may contain ticker

    Returns:
        Uppercase ticker symbol or None
    """
    if not value:
        return None

    # Remove any prefix
    value = re.sub(r'^ticker:?', '', value, flags=re.IGNORECASE)

    # Extract uppercase letters only
    match = re.match(r'^[A-Za-z]{1,5}$', value.strip())
    if match:
        return match.group().upper()

    return None


def match_by_canonical_id(
    node_a: dict,
    node_b: dict,
    node_type: str,
) -> Tuple[bool, Optional[str]]:
    """
    Check if two nodes match by canonical ID.

    Args:
        node_a: First node dict
        node_b: Second node dict
        node_type: Node type for both

    Returns:
        (is_match, canonical_id) - canonical_id is the shared ID if matched
    """
    id_a = get_canonical_id(node_type, node_a)
    id_b = get_canonical_id(node_type, node_b)

    if id_a and id_b and id_a == id_b:
        return True, id_a

    return False, None
