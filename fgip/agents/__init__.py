"""FGIP Agents - Evidence gathering and hypothesis proposers.

Agents can ONLY write to staging tables (proposed_claims, proposed_edges).
Human review is required to promote HYPOTHESIS → FACT.

Available agents:
- EDGARAgent: SEC EDGAR watcher (13F, 10-K, 8-K filings)
- SCOTUSAgent: Supreme Court docket watcher (opinions, orders, amicus)
- GAOAgent: GAO/Agency PDF watcher (government reports)
- RSSSignalAgent: RSS signal layer (news feeds)
- CitationLoaderAgent: Batch loader from citation database markdown
- FARAAgent: Foreign Agents Registration Act monitor (Tier 0)
- OpenSecretsAgent: Campaign finance and lobbying monitor (Tier 1)
- USASpendingAgent: Federal spending/awards monitor (Tier 0)
- FederalRegisterAgent: Rulemaking and regulation monitor (Tier 0)
- ReasoningAgent: Graph traversal, causal chains, same-actor detection (meta-agent)
- YouTubeSignalAnalyzer: YouTube watch history → signal graph (consumption layer)
- SignalGapEcosystemAgent: Detects signal/graph gaps, expands full ecosystem
"""

from .base import FGIPAgent, Artifact, StructuredFact, ProposedClaim, ProposedEdge, ProposedNode
from .edgar import EDGARAgent
from .scotus import SCOTUSAgent
from .gao import GAOAgent
from .rss_signal import RSSSignalAgent
from .citation_loader import CitationLoaderAgent
from .fara import FARAAgent
from .opensecrets import OpenSecretsAgent
from .usaspending import USASpendingAgent
from .federal_register import FederalRegisterAgent
from .reasoning import ReasoningAgent
from .congress import CongressAgent
from .fec import FECAgent
from .promethean import PrometheanAgent
from .tic import TICAgent
from .stablecoin import StablecoinAgent
from .youtube_signal import (
    YouTubeSignalAnalyzer,
    YouTubeVideo,
    ExtractedGuest,
    ChannelProfile,
    SignalLayerReport,
    parse_watch_history,
    extract_guests_from_title,
)
from .gap_detector import GapDetectorAgent
from .supply_chain_extractor import SupplyChainExtractor
from .agent_factory import AgentFactory
from .causal_agent import CausalAgent
from .nuclear_smr import NuclearSMRAgent
from .signal_gap_ecosystem import SignalGapEcosystemAgent, GapFinding
from .coverage_probe import CoverageProbeAgent, SentinelNode, CoverageGap
from .coverage_analyzer import CoverageAnalyzer, CoverageReport, ExpectedEntitySet
from .conviction_engine import (
    ConvictionEngine,
    ConvictionLevel,
    ConvictionReport,
    Signal,
    CounterThesis,
    Catalyst,
    INVESTMENT_THESES,
    DATA_SOURCES_FOR_CONVICTION,
)
from .options_flow import (
    OptionsFlowAgent,
    OptionsFlow,
    OptionsSignal,
    CONVICTION_TICKERS,
)
from .filter_agent import FilterAgent, IntegrityScore
from .nlp_agent import NLPAgent, ExtractionResult, EntityCandidate, RelationCandidate, ClaimCandidate
from .pipeline_orchestrator import PipelineOrchestrator, PipelineStats
from .market_tape import MarketTapeAgent, TapeAnalysis, PriceSnapshot, TechnicalSignals
from .forecast_agent import ForecastAgent, ForecastObject, Distribution
from .trade_plan_agent import TradePlanAgent, TradeMemo, GateResult
from .kalshi_signal import KalshiSignalAgent, PredictionMarket, MarketSignal

__all__ = [
    # Base classes
    "FGIPAgent",
    "Artifact",
    "StructuredFact",
    "ProposedClaim",
    "ProposedEdge",
    "ProposedNode",
    # Problem layer agents
    "EDGARAgent",
    "SCOTUSAgent",
    "GAOAgent",
    "RSSSignalAgent",
    "CitationLoaderAgent",
    "FARAAgent",
    "OpenSecretsAgent",
    # Correction layer agents
    "USASpendingAgent",
    "FederalRegisterAgent",
    # Meta agents (reason over graph)
    "ReasoningAgent",
    # Congressional records
    "CongressAgent",
    # Campaign finance
    "FECAgent",
    # Independent media
    "PrometheanAgent",
    # Debt domestication
    "TICAgent",
    "StablecoinAgent",
    # Signal layer (consumption patterns)
    "YouTubeSignalAnalyzer",
    "YouTubeVideo",
    "ExtractedGuest",
    "ChannelProfile",
    "SignalLayerReport",
    "parse_watch_history",
    "extract_guests_from_title",
    # Self-healing agents (Tier 3)
    "GapDetectorAgent",
    "SupplyChainExtractor",
    "AgentFactory",
    "CausalAgent",
    # Nuclear SMR sector
    "NuclearSMRAgent",
    # Signal gap ecosystem expansion
    "SignalGapEcosystemAgent",
    "GapFinding",
    # External graph coverage probing
    "CoverageProbeAgent",
    "SentinelNode",
    "CoverageGap",
    # Local coverage analysis
    "CoverageAnalyzer",
    "CoverageReport",
    "ExpectedEntitySet",
    # Conviction engine (would I bet my own money?)
    "ConvictionEngine",
    "ConvictionLevel",
    "ConvictionReport",
    "Signal",
    "CounterThesis",
    "Catalyst",
    "INVESTMENT_THESES",
    "DATA_SOURCES_FOR_CONVICTION",
    # Options flow (smart money positioning)
    "OptionsFlowAgent",
    "OptionsFlow",
    "OptionsSignal",
    "CONVICTION_TICKERS",
    # Hughes-style content filtering
    "FilterAgent",
    "IntegrityScore",
    # NLP extraction
    "NLPAgent",
    "ExtractionResult",
    "EntityCandidate",
    "RelationCandidate",
    "ClaimCandidate",
    # Pipeline orchestration (Filter → NLP → Proposals)
    "PipelineOrchestrator",
    "PipelineStats",
    # Market tape (price/volume signals)
    "MarketTapeAgent",
    "TapeAnalysis",
    "PriceSnapshot",
    "TechnicalSignals",
    # Forecasting (P10/P50/P90 distributions)
    "ForecastAgent",
    "ForecastObject",
    "Distribution",
    # Trade memo generation
    "TradePlanAgent",
    "TradeMemo",
    "GateResult",
    # Prediction markets
    "KalshiSignalAgent",
    "PredictionMarket",
    "MarketSignal",
]
