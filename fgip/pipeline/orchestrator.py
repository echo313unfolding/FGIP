"""
DEPRECATED: Import from fgip.agents.pipeline_orchestrator instead.

This module redirects to the canonical orchestrator location.
"""

# Redirect all imports to canonical location
from fgip.agents.pipeline_orchestrator import (
    PipelineOrchestrator,
    PipelineStats,
    QueueStatus,
    CycleReport,
)

__all__ = ['PipelineOrchestrator', 'PipelineStats', 'QueueStatus', 'CycleReport']
