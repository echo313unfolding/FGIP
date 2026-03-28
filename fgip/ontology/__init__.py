"""
FGIP Ontology Guard - Type-safe graph validation.

Enforces:
- Required fields per node/edge type
- Edge type constraints (valid from→to type pairs)
- Orphan edge detection
- Assertion level consistency
"""

from .constraints import EDGE_TYPE_CONSTRAINTS, validate_edge_types
from .properties import (
    NODE_PROPERTIES,
    EDGE_PROPERTIES,
    validate_properties,
)
from .validator import (
    ValidationResult,
    OntologyValidator,
    validate_jsonl_export,
)

__all__ = [
    'EDGE_TYPE_CONSTRAINTS',
    'validate_edge_types',
    'NODE_PROPERTIES',
    'EDGE_PROPERTIES',
    'validate_properties',
    'ValidationResult',
    'OntologyValidator',
    'validate_jsonl_export',
]
