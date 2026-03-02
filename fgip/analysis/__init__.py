"""FGIP Analysis Module - Risk scoring and intelligence analysis."""

from .risk_scorer import RiskScorer, ThesisRiskResult, InvestmentRiskResult, SignalConvergenceResult
from .gap_detector import GapDetector, Gap, AgentSuggestion, AgentRequest, GapReport
from .provenance_tracker import (
    ProvenanceTracker,
    EdgeProvenance,
    KnowledgeTimeline,
    KnowledgeTimelineEvent,
    YouTubeWatch,
    RSSArticle,
    SearchQuery,
)
from .provenance import DataProvenance
from .compression_patterns import (
    CompressionPatternAnalyzer,
    CompressionReport,
    MotifMatch,
    MotifTemplate,
    NeighborhoodSketch,
    AnomalyResult,
    SimilarPair,
    # Surprisal scoring
    ChainToken,
    SurprisalResult,
    TransitionModel,
)
from .purchasing_power import (
    PurchasingPowerAnalyzer,
    PurchasingPowerReport,
    PersonalScenario,
    RealRateResult,
    RunwayResult,
    compute_real_rates,
    compute_runway,
    generate_purchasing_power_report,
)

__all__ = [
    # Risk Scoring
    "RiskScorer",
    "ThesisRiskResult",
    "InvestmentRiskResult",
    "SignalConvergenceResult",
    # Gap Detection
    "GapDetector",
    "Gap",
    "AgentSuggestion",
    "AgentRequest",
    "GapReport",
    # Provenance Tracking
    "ProvenanceTracker",
    "EdgeProvenance",
    "KnowledgeTimeline",
    "KnowledgeTimelineEvent",
    "YouTubeWatch",
    "RSSArticle",
    "SearchQuery",
    # Data Provenance (for trade gating)
    "DataProvenance",
    # Compression Patterns
    "CompressionPatternAnalyzer",
    "CompressionReport",
    "MotifMatch",
    "MotifTemplate",
    "NeighborhoodSketch",
    "AnomalyResult",
    "SimilarPair",
    # Surprisal Scoring
    "ChainToken",
    "SurprisalResult",
    "TransitionModel",
    # Purchasing Power
    "PurchasingPowerAnalyzer",
    "PurchasingPowerReport",
    "PersonalScenario",
    "RealRateResult",
    "RunwayResult",
    "compute_real_rates",
    "compute_runway",
    "generate_purchasing_power_report",
]
