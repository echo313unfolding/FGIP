"""FGIP Pipeline - Data integrity checking and orchestration.

Components:
- LeakDetector: Invariant checker for pipeline health
- PipelineOrchestrator: Coordinates FilterAgent → NLPAgent → Proposals (in fgip.agents)
"""

from .leak_detector import LeakDetector, LeakReport

__all__ = ["LeakDetector", "LeakReport"]
