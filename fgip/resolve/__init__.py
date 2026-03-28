"""
FGIP Entity Resolution - Deduplication and canonical ID management.

Components:
- Canonical ID derivation (CIK, ticker, LEI, CFDA, etc.)
- SAME_AS proposal generation (inferential)
- MERGED_INTO tracking (factual post-approval)
"""

from .canonical import (
    CANONICAL_PATTERNS,
    get_canonical_id,
    normalize_name,
)
from .resolver import (
    SameAsProposal,
    EntityResolver,
)

__all__ = [
    'CANONICAL_PATTERNS',
    'get_canonical_id',
    'normalize_name',
    'SameAsProposal',
    'EntityResolver',
]
