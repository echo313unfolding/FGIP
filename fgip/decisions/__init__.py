"""
FGIP Decision Node Infrastructure

First-class decision tracking with gates, evidence, and audit trails.
Decisions are graph nodes with provenance - not just outcomes, but the reasoning.
"""

from .node import (
    DecisionNode,
    DecisionStatus,
    DecisionPhase,
)
from .gate import (
    Gate,
    GateStatus,
    GateCheck,
)
from .evidence import (
    Evidence,
    EvidenceType,
)
from .community import (
    CommunityCandidate,
    CommunityStatus,
)

__all__ = [
    "DecisionNode",
    "DecisionStatus",
    "DecisionPhase",
    "Gate",
    "GateStatus",
    "GateCheck",
    "Evidence",
    "EvidenceType",
    "CommunityCandidate",
    "CommunityStatus",
]
