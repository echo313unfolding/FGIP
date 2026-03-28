"""
FGIP Location Module

Florida location scoring for condo purchase decision.
"""

from .scorer import (
    LocationScore,
    ScoringWeights,
    FloridaLocationScorer,
    AreaDefinition,
)

__all__ = [
    "LocationScore",
    "ScoringWeights",
    "FloridaLocationScorer",
    "AreaDefinition",
]
