"""
FGIP Settlement Allocator - Regime-driven allocation directives.

Takes regime intelligence and outputs: "do this with the money."

Usage:
    python3 -m fgip.allocator --settlement 250000

Or programmatically:
    from fgip.allocator import generate_directive, SettlementConstraints
    directive = generate_directive(constraints, regime, Se, C, ...)
"""

from .constraints import SettlementConstraints, RiskTolerance
from .buckets import BUCKETS, AllocationBucket, DEFAULT_TICKER_MAP
from .policy import AllocationPolicy
from .directive import (
    AllocationDirective,
    generate_directive,
    write_directive,
)

__all__ = [
    'SettlementConstraints',
    'RiskTolerance',
    'BUCKETS',
    'AllocationBucket',
    'DEFAULT_TICKER_MAP',
    'AllocationPolicy',
    'AllocationDirective',
    'generate_directive',
    'write_directive',
]
