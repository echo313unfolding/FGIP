"""
FGIP Conviction Engine - "Would I bet my own money on this?"

The Conviction Engine answers the core question: Do I have enough independent signals,
validated by Tier 0 sources, with stress-tested counter-theses, to risk real capital?

CONVICTION LEVELS:
- CONVICTION_5 (95%+): Max position. Multiple Tier 0 confirmations, no valid counter-thesis.
- CONVICTION_4 (80-95%): Full position. Tier 0/1 confirmations, weak counter-thesis.
- CONVICTION_3 (60-80%): Half position. Mixed signals, manageable counter-thesis.
- CONVICTION_2 (40-60%): Quarter position. Speculative, limited confirmation.
- CONVICTION_1 (<40%): No position. Thesis is unproven or counter-thesis is stronger.

DATA SOURCES FOR CONVICTION:
Tier 0 (Highest Conviction Boost):
  - SEC EDGAR 13F filings (insider/institutional buys)
  - USASpending grants (government funding confirmed)
  - NRC permits (regulatory approvals)
  - Federal Register rules (policy implementation)
  - Congress.gov votes (legislation passed)

Tier 1 (Moderate Conviction Boost):
  - Options unusual activity (smart money positioning)
  - Insider transaction forms (Form 4)
  - Credit rating changes
  - Analyst upgrades/downgrades
  - Industry conference announcements

Tier 2 (Weak Conviction - Context Only):
  - News articles
  - Social sentiment
  - Podcast mentions
  - YouTube signals

TRIANGULATION REQUIREMENT:
Minimum 3 independent signals from different source TYPES to reach CONVICTION_3+

ADVERSARIAL REQUIREMENT:
Must articulate and test strongest counter-thesis before any position.
"""

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base import (
    FGIPAgent,
    Artifact,
    StructuredFact,
    ProposedClaim,
    ProposedEdge,
    ProposedNode,
)

# Tier-0 agents that MUST have artifact_id for proposals to count in triangulation
# WO-FGIP-TRIANGULATION-HYGIENE-02
TIER0_AGENTS = [
    'edgar', 'usaspending', 'federal_register', 'congress',
    'nuclear_smr', 'tic', 'fec', 'scotus', 'gao', 'fara', 'chips-facility'
]


# =============================================================================
# CONVICTION LEVELS
# =============================================================================

class ConvictionLevel(Enum):
    """Conviction levels with position sizing implications."""
    CONVICTION_5 = 5  # 95%+: Max position (20% of portfolio)
    CONVICTION_4 = 4  # 80-95%: Full position (15% of portfolio)
    CONVICTION_3 = 3  # 60-80%: Half position (10% of portfolio)
    CONVICTION_2 = 2  # 40-60%: Quarter position (5% of portfolio)
    CONVICTION_1 = 1  # <40%: No position (0%)

    @property
    def position_size_pct(self) -> float:
        """Recommended position size as percentage of portfolio."""
        return {
            5: 0.20,
            4: 0.15,
            3: 0.10,
            2: 0.05,
            1: 0.00,
        }[self.value]

    @property
    def description(self) -> str:
        return {
            5: "MAX CONVICTION: Multiple Tier 0 confirmations, counter-thesis invalidated",
            4: "HIGH CONVICTION: Tier 0/1 confirmations, weak counter-thesis",
            3: "MODERATE CONVICTION: Mixed signals, manageable counter-thesis",
            2: "LOW CONVICTION: Speculative, limited confirmation",
            1: "NO CONVICTION: Unproven or counter-thesis dominates",
        }[self.value]


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class Signal:
    """An independent signal supporting or refuting a thesis."""
    signal_id: str
    signal_type: str  # 'confirming', 'refuting', 'neutral'
    source_type: str  # 'edgar', 'usaspending', 'options', 'news', etc.
    source_tier: int  # 0, 1, or 2
    source_url: str
    description: str
    signal_strength: float  # 0-1
    timestamp: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CounterThesis:
    """A counter-thesis that could invalidate the investment thesis."""
    counter_id: str
    description: str
    severity: str  # 'fatal', 'serious', 'manageable', 'weak'
    likelihood: float  # 0-1
    evidence: List[str]  # Supporting evidence for counter-thesis
    mitigation: Optional[str] = None  # How to mitigate if true
    invalidated_by: Optional[str] = None  # What evidence would invalidate this counter

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Catalyst:
    """An event that could trigger entry or exit."""
    catalyst_id: str
    catalyst_type: str  # 'entry', 'exit', 'accelerator', 'decelerator'
    description: str
    expected_date: Optional[str] = None
    probability: float = 0.5
    impact: str = 'moderate'  # 'low', 'moderate', 'high', 'extreme'
    monitoring_source: Optional[str] = None  # Where to watch for this

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ConvictionReport:
    """Complete conviction analysis for an investment thesis."""
    thesis_id: str
    thesis_statement: str
    tickers: List[str]
    sector: str

    # Conviction scoring
    conviction_level: int
    conviction_score: float  # 0-100
    position_size_pct: float

    # Supporting evidence
    confirming_signals: List[Signal]
    refuting_signals: List[Signal]
    neutral_signals: List[Signal]

    # Triangulation
    triangulation_count: int
    triangulation_sources: List[str]
    triangulation_met: bool

    # Adversarial analysis
    counter_theses: List[CounterThesis]
    strongest_counter: Optional[CounterThesis]
    counter_thesis_severity: str

    # Catalysts
    entry_catalysts: List[Catalyst]
    exit_catalysts: List[Catalyst]

    # Recommendations
    recommendation: str  # 'BUY', 'HOLD', 'AVOID', 'EXIT'
    entry_timing: str  # 'NOW', 'WAIT_CATALYST', 'NOT_YET', 'MISSED'
    stop_loss_pct: Optional[float] = None
    target_price_pct: Optional[float] = None

    # Metadata
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    data_freshness: str = "live"  # 'live', 'stale', 'historical'

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["confirming_signals"] = [s.to_dict() for s in self.confirming_signals]
        d["refuting_signals"] = [s.to_dict() for s in self.refuting_signals]
        d["neutral_signals"] = [s.to_dict() for s in self.neutral_signals]
        d["counter_theses"] = [c.to_dict() for c in self.counter_theses]
        d["strongest_counter"] = self.strongest_counter.to_dict() if self.strongest_counter else None
        d["entry_catalysts"] = [c.to_dict() for c in self.entry_catalysts]
        d["exit_catalysts"] = [c.to_dict() for c in self.exit_catalysts]
        return d


# =============================================================================
# SIGNAL SOURCE MAPPINGS
# =============================================================================

# Source type -> Tier mapping
SOURCE_TIERS: Dict[str, int] = {
    # Tier 0 - Government/Primary
    "edgar_13f": 0,
    "edgar_10k": 0,
    "edgar_8k": 0,
    "edgar_form4": 0,
    "usaspending": 0,
    "nrc_permit": 0,
    "federal_register": 0,
    "congress_vote": 0,
    "tic_data": 0,
    "fred_data": 0,
    "scotus_filing": 0,
    # Tier 1 - Professional/Journalism
    "options_flow": 1,
    "credit_rating": 1,
    "analyst_rating": 1,
    "reuters": 1,
    "wsj": 1,
    "industry_conference": 1,
    "earnings_call": 1,
    # Tier 2 - Commentary
    "news_article": 2,
    "social_sentiment": 2,
    "podcast": 2,
    "youtube_signal": 2,
    "blog": 2,
}

# Conviction boost per tier
TIER_CONVICTION_BOOST: Dict[int, float] = {
    0: 15.0,  # Tier 0 signal adds 15 points
    1: 8.0,   # Tier 1 signal adds 8 points
    2: 3.0,   # Tier 2 signal adds 3 points
}

# Counter-thesis severity penalties
COUNTER_SEVERITY_PENALTY: Dict[str, float] = {
    "fatal": 50.0,      # Fatal counter-thesis kills the thesis
    "serious": 25.0,    # Serious counter-thesis significantly reduces conviction
    "manageable": 10.0, # Manageable counter-thesis minor reduction
    "weak": 3.0,        # Weak counter-thesis negligible
}


# =============================================================================
# INVESTMENT THESES
# =============================================================================

# Pre-defined theses to evaluate
INVESTMENT_THESES: List[Dict[str, Any]] = [
    {
        "thesis_id": "nuclear-smr-thesis",
        "thesis_statement": "Nuclear SMR companies will outperform as grid baseload demand exceeds supply, driven by data centers, reshoring, and grid modernization. Trump EO + DoE ARDP funding + NRC fast-track = policy tailwind.",
        "tickers": ["SMR", "OKLO", "CEG", "BWXT", "LEU"],
        "sector": "nuclear",
        "entry_triggers": ["NRC permit approval", "DoE grant announcement", "Utility PPA signing"],
        "exit_triggers": ["Construction delays >6mo", "Cost overrun >30%", "NRC permit denial"],
        "counter_theses": [
            "Vogtle cost overruns repeat",
            "Natural gas stays cheap (<$3)",
            "Renewables + storage cheaper",
            "NRC bureaucracy stalls permits",
        ],
    },
    {
        "thesis_id": "uranium-thesis",
        "thesis_statement": "Uranium prices will rise as SMR buildout requires HALEU fuel, supply constrained by Russia sanctions, and inventory drawdown accelerates.",
        "tickers": ["CCJ", "URA", "UUUU", "LEU", "NXE"],
        "sector": "nuclear_fuel",
        "entry_triggers": ["Utility long-term contract", "HALEU production milestone", "Russia supply disruption"],
        "exit_triggers": ["New mine production surge", "SMR buildout delays", "Utility contract cancellations"],
        "counter_theses": [
            "Kazakhstan expands production",
            "Russia sanctions lifted",
            "SMR buildout slower than expected",
        ],
    },
    {
        "thesis_id": "reshoring-steel-thesis",
        "thesis_statement": "Domestic steel producers benefit from tariff protection and reshoring demand. Infrastructure spending + defense buildup = sustained demand.",
        "tickers": ["NUE", "STLD", "X", "CLF"],
        "sector": "steel",
        "entry_triggers": ["Tariff implementation", "Infrastructure bill passage", "Defense contract award"],
        "exit_triggers": ["Tariff reduction/removal", "Recession demand collapse", "Import surge"],
        "counter_theses": [
            "Recession kills demand",
            "Next administration removes tariffs",
            "Chinese dumping circumvents tariffs",
        ],
    },
    {
        "thesis_id": "defense-anduril-thesis",
        "thesis_statement": "Defense tech companies (Anduril, Palantir) benefit from DoD modernization away from legacy contractors. Software-defined warfare + autonomous systems.",
        "tickers": ["PLTR", "LHX", "RTX"],  # Anduril not public
        "sector": "defense",
        "entry_triggers": ["DoD contract award", "DARPA grant", "Foreign ally contract"],
        "exit_triggers": ["Defense budget cut", "Contract loss", "Tech failure"],
        "counter_theses": [
            "Legacy contractors lobby successfully",
            "DoD procurement remains bureaucratic",
            "Peace dividend reduces spending",
        ],
    },
    {
        "thesis_id": "rare-earth-thesis",
        "thesis_statement": "MP Materials and rare earth processors benefit from China supply chain de-risking. Defense, EV, and electronics all need domestic supply.",
        "tickers": ["MP", "UUUU"],
        "sector": "critical_minerals",
        "entry_triggers": ["DoD contract", "Processing facility approval", "China export restriction"],
        "exit_triggers": ["China floods market", "Technology substitution", "MP execution failure"],
        "counter_theses": [
            "MP can't scale processing",
            "China undercuts prices to kill competition",
            "Substitutes reduce rare earth demand",
        ],
    },
    # NEW: Infrastructure picks and shovels thesis
    {
        "thesis_id": "infrastructure-picks-shovels",
        "thesis_statement": "Infrastructure equipment companies (electrical, cooling, packaging, materials) are toll bridges between $500B+ committed AI/fab capex and physical reality. These are bottleneck plays with locked-in demand.",
        # Include both tickers AND company names for LIKE matching
        "tickers": ["FPS", "POWL", "VRT", "MOD", "AMKR", "ENTG", "LIN",
                    "vertiv", "modine", "amkor", "entegris", "linde", "powell", "forgent",
                    "air-products", "asml"],
        "sector": "infrastructure_equipment",
        "entry_triggers": [
            "Data center capex announcement",
            "Fab construction milestone",
            "Backlog growth in earnings",
            "CHIPS Act award to customer",
            "Utility IRP capacity addition",
        ],
        "exit_triggers": [
            "Capex cancellation",
            "Construction delays >12mo",
            "Backlog decline",
            "New competitor capacity",
            "Technology substitution",
        ],
        "counter_theses": [
            "AI capex bubble bursts - hyperscalers cut spending",
            "Fab buildout slower than announced",
            "Foreign competition undercuts pricing",
            "Recession delays infrastructure spend",
            "Technology shift reduces demand (e.g., air cooling improves)",
        ],
        "triangulation_sources": [
            "SEC_13F",  # Institutional positioning
            "CHIPS_awards",  # Customer funding confirmed
            "utility_IRPs",  # Power demand forecasts
            "earnings_backlog",  # Company backlog data
            "options_flow",  # Smart money positioning
        ],
        "bottlenecks": {
            "FPS": "Transformers - 4yr lead time",
            "POWL": "Custom electrical distribution",
            "VRT": "Liquid cooling + power - dual exposure",
            "MOD": "Thermal wall at 100kW/rack",
            "AMKR": "Only US advanced packaging",
            "ENTG": "Filtration - razor blades model",
            "LIN": "15-20yr gas supply contracts",
        },
    },
    {
        "thesis_id": "ai-data-center-power",
        "thesis_statement": "AI compute buildout requires massive power infrastructure expansion. Companies providing power generation, distribution, and cooling equipment benefit from hyperscaler capex surge.",
        "tickers": ["VRT", "ETN", "FPS", "POWL", "NVT", "MOD"],
        "sector": "electrical_power",
        "entry_triggers": [
            "Hyperscaler earnings capex guidance",
            "Utility IRP data center load forecast",
            "Transformer/switchgear order announcement",
            "Book-to-bill ratio >1.5",
        ],
        "exit_triggers": [
            "AI spending slowdown",
            "Hyperscaler capex cut",
            "New capacity oversupply",
            "Recession demand destruction",
        ],
        "counter_theses": [
            "AI winter - spending collapses",
            "Efficiency gains reduce power needs",
            "On-site generation reduces grid demand",
            "Lead times normalize as capacity expands",
        ],
    },
    {
        "thesis_id": "semiconductor-materials",
        "thesis_statement": "Semiconductor specialty materials (gases, chemicals, filtration) providers have recurring revenue model tied to fab production. Every wafer run consumes their products.",
        "tickers": ["ENTG", "LIN", "APD", "DD"],
        "sector": "specialty_materials",
        "entry_triggers": [
            "Fab production ramp",
            "CHIPS Act facility operational",
            "New supply contract announcement",
            "Capacity expansion investment",
        ],
        "exit_triggers": [
            "Fab production decline",
            "Technology substitution",
            "Contract loss",
            "Commodity price pressure",
        ],
        "counter_theses": [
            "Fab buildout delays reduce demand",
            "Chinese alternatives emerge",
            "Pricing pressure from customers",
            "Technology change reduces material consumption",
        ],
    },
]


# =============================================================================
# CONVICTION ENGINE AGENT
# =============================================================================

class ConvictionEngine(FGIPAgent):
    """
    The Conviction Engine evaluates investment theses with adversarial rigor.

    Ask yourself: "Would I bet my own money on this?"

    Pipeline:
    1. COLLECT signals from all available sources (EDGAR, USASpending, options, news)
    2. TRIANGULATE - require 3+ independent signals from different source types
    3. ATTACK - articulate and test strongest counter-thesis
    4. SCORE - compute conviction level based on evidence quality
    5. SIZE - recommend position size based on conviction
    6. MONITOR - identify entry/exit catalysts to watch

    Output: ConvictionReport with actionable recommendation
    """

    def __init__(self, db, artifact_dir: str = "data/artifacts/conviction"):
        super().__init__(
            db=db,
            name="conviction_engine",
            description="Evaluates investment theses with adversarial rigor - would I bet my own money?"
        )
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self._theses = INVESTMENT_THESES.copy()

    def add_thesis(self, thesis: Dict[str, Any]):
        """Add a custom thesis to evaluate."""
        self._theses.append(thesis)

    def evaluate_thesis(self, thesis_id: str) -> ConvictionReport:
        """
        Evaluate a single thesis and return a ConvictionReport.

        This is the main entry point for thesis evaluation.
        """
        thesis = next((t for t in self._theses if t["thesis_id"] == thesis_id), None)
        if not thesis:
            raise ValueError(f"Thesis not found: {thesis_id}")

        # 1. Collect signals
        confirming, refuting, neutral = self._collect_signals_for_thesis(thesis)

        # 2. Check triangulation
        triangulation = self._check_triangulation(confirming)

        # 3. Analyze counter-theses
        counter_theses = self._analyze_counter_theses(thesis, refuting)
        strongest_counter = max(counter_theses, key=lambda c: COUNTER_SEVERITY_PENALTY.get(c.severity, 0)) if counter_theses else None

        # 4. Compute conviction score
        score, level = self._compute_conviction(
            confirming, refuting, neutral,
            triangulation["triangulation_met"],
            strongest_counter
        )

        # 5. Identify catalysts
        entry_catalysts = self._identify_entry_catalysts(thesis)
        exit_catalysts = self._identify_exit_catalysts(thesis)

        # 6. Generate recommendation
        recommendation, entry_timing = self._generate_recommendation(
            level, triangulation["triangulation_met"], strongest_counter, entry_catalysts
        )

        return ConvictionReport(
            thesis_id=thesis["thesis_id"],
            thesis_statement=thesis["thesis_statement"],
            tickers=thesis["tickers"],
            sector=thesis["sector"],
            conviction_level=level.value,
            conviction_score=score,
            position_size_pct=level.position_size_pct,
            confirming_signals=confirming,
            refuting_signals=refuting,
            neutral_signals=neutral,
            triangulation_count=triangulation["triangulation_count"],
            triangulation_sources=triangulation["triangulation_sources"],
            triangulation_met=triangulation["triangulation_met"],
            counter_theses=counter_theses,
            strongest_counter=strongest_counter,
            counter_thesis_severity=strongest_counter.severity if strongest_counter else "none",
            entry_catalysts=entry_catalysts,
            exit_catalysts=exit_catalysts,
            recommendation=recommendation,
            entry_timing=entry_timing,
            stop_loss_pct=self._compute_stop_loss(level),
            target_price_pct=self._compute_target(level),
        )

    def evaluate_all_theses(self) -> List[ConvictionReport]:
        """Evaluate all registered theses."""
        reports = []
        for thesis in self._theses:
            try:
                report = self.evaluate_thesis(thesis["thesis_id"])
                reports.append(report)
            except Exception as e:
                print(f"  Error evaluating {thesis['thesis_id']}: {e}")
        return reports

    def _collect_signals_for_thesis(self, thesis: Dict[str, Any]) -> Tuple[List[Signal], List[Signal], List[Signal]]:
        """Collect all signals relevant to a thesis."""
        confirming = []
        refuting = []
        neutral = []

        sector = thesis["sector"]
        tickers = thesis["tickers"]

        # Query graph for edges related to this sector/tickers
        conn = self.db.connect()

        # 1. Check for EDGAR filings (Form 13F institutional buys)
        for ticker in tickers:
            node_id = ticker.lower()
            rows = conn.execute("""
                SELECT e.from_node_id, e.edge_type, e.to_node_id, e.confidence, e.notes, e.source_url
                FROM edges e
                WHERE (e.from_node_id = ? OR e.to_node_id = ?)
                AND e.edge_type IN ('OWNS_SHARES', 'INCREASED_POSITION', 'DECREASED_POSITION')
            """, (node_id, node_id)).fetchall()

            for row in rows:
                signal_type = "confirming" if row[1] in ('OWNS_SHARES', 'INCREASED_POSITION') else "refuting"
                signal = Signal(
                    signal_id=f"edgar-{row[0]}-{row[2]}",
                    signal_type=signal_type,
                    source_type="edgar_13f",
                    source_tier=0,
                    source_url=row[5] or "https://sec.gov",
                    description=f"{row[0]} {row[1]} {row[2]}",
                    signal_strength=float(row[3]) if row[3] else 0.7,
                    timestamp=datetime.utcnow().isoformat() + "Z",
                )
                if signal_type == "confirming":
                    confirming.append(signal)
                else:
                    refuting.append(signal)

        # 2. Check for USASpending grants (FUNDED_BY edges)
        rows = conn.execute("""
            SELECT e.from_node_id, e.to_node_id, e.confidence, e.notes
            FROM edges e
            JOIN nodes n ON e.from_node_id = n.node_id
            WHERE json_extract(n.metadata, '$.sector') = ?
            AND e.edge_type = 'FUNDED_BY'
        """, (sector,)).fetchall()

        for row in rows:
            confirming.append(Signal(
                signal_id=f"grant-{row[0]}-{row[1]}",
                signal_type="confirming",
                source_type="usaspending",
                source_tier=0,
                source_url="https://usaspending.gov",
                description=f"{row[0]} funded by {row[1]}",
                signal_strength=float(row[2]) if row[2] else 0.8,
                timestamp=datetime.utcnow().isoformat() + "Z",
            ))

        # 3. Check for NRC permits (LICENSED_BY edges for nuclear)
        if sector in ("nuclear", "nuclear_fuel", "nuclear_smr"):
            rows = conn.execute("""
                SELECT e.from_node_id, e.to_node_id, e.confidence
                FROM edges e
                WHERE e.edge_type IN ('LICENSED_BY', 'PERMITTED_BY')
                AND e.to_node_id = 'nrc'
            """).fetchall()

            for row in rows:
                confirming.append(Signal(
                    signal_id=f"nrc-{row[0]}",
                    signal_type="confirming",
                    source_type="nrc_permit",
                    source_tier=0,
                    source_url="https://nrc.gov",
                    description=f"{row[0]} licensed by NRC",
                    signal_strength=float(row[2]) if row[2] else 0.9,
                    timestamp=datetime.utcnow().isoformat() + "Z",
                ))

        # 4. Check PROPOSED EDGES from Tier 0 agents (staging data = authoritative but pending review)
        # These are government sources, so we treat them as high-confidence signals
        # WO-FGIP-TRIANGULATION-HYGIENE-02: Only count proposals WITH artifact_id evidence
        tier_0_agents = TIER0_AGENTS  # All Tier-0 agents (dynamic placeholders)
        tier0_placeholders = ",".join(["?"] * len(tier_0_agents))

        for ticker in tickers:
            ticker_lower = ticker.lower()

            # Query proposed_edges for this ticker from Tier 0 agents
            # REQUIRES artifact_id to ensure evidence trail
            rows = conn.execute(f"""
                SELECT pe.from_node, pe.to_node, pe.relationship, pe.confidence, pe.agent_name, pe.reasoning
                FROM proposed_edges pe
                WHERE (LOWER(pe.from_node) LIKE ? OR LOWER(pe.to_node) LIKE ?)
                AND pe.agent_name IN ({tier0_placeholders})
                AND pe.status = 'PENDING'
                AND pe.artifact_id IS NOT NULL
                AND pe.artifact_id != ''
            """, (f"%{ticker_lower}%", f"%{ticker_lower}%", *tier_0_agents)).fetchall()

            for row in rows:
                agent_name = row[4]
                relationship = row[2]

                # Map agent to source type
                source_type_map = {
                    'edgar': 'edgar_13f',
                    'usaspending': 'usaspending',
                    'federal_register': 'federal_register',
                    'congress': 'congress_vote',
                    'nuclear_smr': 'nrc_permit',
                    'tic': 'tic_data',
                    'fec': 'fec_contribution',
                }
                source_type = source_type_map.get(agent_name, 'government')

                # Determine if confirming or refuting
                confirming_relationships = [
                    'OWNS_SHARES', 'INCREASED_POSITION', 'FUNDED_BY', 'LICENSED_BY',
                    'PERMITTED_BY', 'AWARDED_GRANT', 'VOTED_FOR', 'SUPPORTS'
                ]
                refuting_relationships = ['DECREASED_POSITION', 'VOTED_AGAINST', 'OPPOSES', 'DENIED']

                if relationship in confirming_relationships:
                    signal_type = "confirming"
                elif relationship in refuting_relationships:
                    signal_type = "refuting"
                else:
                    signal_type = "neutral"

                signal = Signal(
                    signal_id=f"pending-{agent_name}-{row[0]}-{row[1]}",
                    signal_type=signal_type,
                    source_type=source_type,
                    source_tier=0,
                    source_url=f"staging://{agent_name}",
                    description=f"[PENDING] {row[0]} {relationship} {row[1]}",
                    signal_strength=float(row[3]) if row[3] else 0.75,
                    timestamp=datetime.utcnow().isoformat() + "Z",
                    metadata={"agent": agent_name, "reasoning": row[5], "status": "pending_review"}
                )

                if signal_type == "confirming":
                    confirming.append(signal)
                elif signal_type == "refuting":
                    refuting.append(signal)
                else:
                    neutral.append(signal)

        # 5. Check proposed_edges for sector-level signals (not ticker-specific)
        # WO-FGIP-TRIANGULATION-HYGIENE-02: Only count proposals WITH artifact_id evidence
        rows = conn.execute(f"""
            SELECT pe.from_node, pe.to_node, pe.relationship, pe.confidence, pe.agent_name
            FROM proposed_edges pe
            WHERE pe.agent_name IN ({tier0_placeholders})
            AND pe.status = 'PENDING'
            AND (pe.from_node LIKE ? OR pe.to_node LIKE ?)
            AND pe.artifact_id IS NOT NULL
            AND pe.artifact_id != ''
            LIMIT 20
        """, (*tier_0_agents, f"%{sector}%", f"%{sector}%")).fetchall()

        for row in rows:
            agent_name = row[4]
            source_type_map = {
                'edgar': 'edgar_13f',
                'usaspending': 'usaspending',
                'federal_register': 'federal_register',
                'congress': 'congress_vote',
                'nuclear_smr': 'nrc_permit',
                'tic': 'tic_data',
                'fec': 'fec_contribution',
            }
            source_type = source_type_map.get(agent_name, 'government')

            confirming.append(Signal(
                signal_id=f"sector-{agent_name}-{row[0][:20]}",
                signal_type="confirming",
                source_type=source_type,
                source_tier=0,
                source_url=f"staging://{agent_name}",
                description=f"[SECTOR] {row[0]} {row[2]} {row[1]}",
                signal_strength=float(row[3]) if row[3] else 0.7,
                timestamp=datetime.utcnow().isoformat() + "Z",
            ))

        # 6. Check YouTube/RSS signal layer for sector mentions (Tier 2 - context only)
        rows = conn.execute("""
            SELECT pc.claim_text, pc.source_url, pc.created_at
            FROM proposed_claims pc
            WHERE pc.topic LIKE ? OR pc.topic LIKE ?
            AND pc.status = 'PENDING'
            LIMIT 10
        """, (f"%{sector}%", f"%signal%")).fetchall()

        for row in rows:
            neutral.append(Signal(
                signal_id=f"signal-{hashlib.md5(row[0].encode()).hexdigest()[:8]}",
                signal_type="neutral",
                source_type="youtube_signal",
                source_tier=2,
                source_url=row[1] or "",
                description=row[0][:100],
                signal_strength=0.5,
                timestamp=row[2] or datetime.utcnow().isoformat() + "Z",
            ))

        return confirming, refuting, neutral

    def _check_triangulation(self, confirming_signals: List[Signal]) -> Dict[str, Any]:
        """
        Check if triangulation requirement is met.

        Triangulation = 3+ independent signals from different source TYPES.
        """
        source_types = set(s.source_type for s in confirming_signals)

        # Require at least one Tier 0 source
        tier_0_sources = set(s.source_type for s in confirming_signals if s.source_tier == 0)

        return {
            "triangulation_count": len(source_types),
            "triangulation_sources": list(source_types),
            "triangulation_met": len(source_types) >= 3 and len(tier_0_sources) >= 1,
            "tier_0_count": len(tier_0_sources),
        }

    def _analyze_counter_theses(self, thesis: Dict[str, Any], refuting_signals: List[Signal]) -> List[CounterThesis]:
        """Analyze and score counter-theses."""
        counter_theses = []

        for i, counter_desc in enumerate(thesis.get("counter_theses", [])):
            # Assess severity based on keywords and refuting signals
            severity = "manageable"  # Default

            if any(kw in counter_desc.lower() for kw in ["fatal", "kills", "impossible", "shutdown"]):
                severity = "fatal"
            elif any(kw in counter_desc.lower() for kw in ["serious", "significant", "major"]):
                severity = "serious"
            elif any(kw in counter_desc.lower() for kw in ["minor", "weak", "unlikely"]):
                severity = "weak"

            # Check if any refuting signals support this counter-thesis
            supporting_evidence = [
                s.description for s in refuting_signals
                if any(kw in s.description.lower() for kw in counter_desc.lower().split()[:3])
            ]

            counter_theses.append(CounterThesis(
                counter_id=f"counter-{thesis['thesis_id']}-{i}",
                description=counter_desc,
                severity=severity,
                likelihood=0.3 if not supporting_evidence else 0.5,
                evidence=supporting_evidence,
                mitigation=self._suggest_mitigation(counter_desc),
            ))

        return counter_theses

    def _suggest_mitigation(self, counter_desc: str) -> str:
        """Suggest mitigation for a counter-thesis."""
        counter_lower = counter_desc.lower()

        if "cost" in counter_lower or "overrun" in counter_lower:
            return "Position sizing, stop-loss on -30%"
        elif "delay" in counter_lower:
            return "Monitor NRC/DoE announcements, scale in over time"
        elif "recession" in counter_lower:
            return "Hedge with inverse ETF or cash position"
        elif "tariff" in counter_lower:
            return "Monitor trade policy announcements"
        elif "china" in counter_lower or "competition" in counter_lower:
            return "Focus on companies with differentiated tech or government contracts"
        else:
            return "Monitor news and regulatory announcements"

    def _compute_conviction(
        self,
        confirming: List[Signal],
        refuting: List[Signal],
        neutral: List[Signal],
        triangulation_met: bool,
        strongest_counter: Optional[CounterThesis]
    ) -> Tuple[float, ConvictionLevel]:
        """Compute conviction score and level."""
        score = 30.0  # Base score (neutral starting point)

        # Add conviction for confirming signals based on tier
        for signal in confirming:
            boost = TIER_CONVICTION_BOOST.get(signal.source_tier, 3.0)
            score += boost * signal.signal_strength

        # Subtract for refuting signals
        for signal in refuting:
            boost = TIER_CONVICTION_BOOST.get(signal.source_tier, 3.0)
            score -= boost * signal.signal_strength * 0.8  # Slightly less weight to refuting

        # Triangulation bonus
        if triangulation_met:
            score += 10.0

        # Counter-thesis penalty
        if strongest_counter:
            penalty = COUNTER_SEVERITY_PENALTY.get(strongest_counter.severity, 5.0)
            score -= penalty * strongest_counter.likelihood

        # Clamp to 0-100
        score = max(0.0, min(100.0, score))

        # Determine level
        if score >= 95:
            level = ConvictionLevel.CONVICTION_5
        elif score >= 80:
            level = ConvictionLevel.CONVICTION_4
        elif score >= 60:
            level = ConvictionLevel.CONVICTION_3
        elif score >= 40:
            level = ConvictionLevel.CONVICTION_2
        else:
            level = ConvictionLevel.CONVICTION_1

        return score, level

    def _identify_entry_catalysts(self, thesis: Dict[str, Any]) -> List[Catalyst]:
        """Identify entry catalysts to monitor."""
        catalysts = []

        for trigger in thesis.get("entry_triggers", []):
            catalysts.append(Catalyst(
                catalyst_id=f"entry-{thesis['thesis_id']}-{len(catalysts)}",
                catalyst_type="entry",
                description=trigger,
                probability=0.5,
                impact="high",
                monitoring_source=self._suggest_monitoring_source(trigger),
            ))

        return catalysts

    def _identify_exit_catalysts(self, thesis: Dict[str, Any]) -> List[Catalyst]:
        """Identify exit catalysts to monitor."""
        catalysts = []

        for trigger in thesis.get("exit_triggers", []):
            catalysts.append(Catalyst(
                catalyst_id=f"exit-{thesis['thesis_id']}-{len(catalysts)}",
                catalyst_type="exit",
                description=trigger,
                probability=0.3,
                impact="high",
                monitoring_source=self._suggest_monitoring_source(trigger),
            ))

        return catalysts

    def _suggest_monitoring_source(self, trigger: str) -> str:
        """Suggest where to monitor for a catalyst."""
        trigger_lower = trigger.lower()

        if "nrc" in trigger_lower or "permit" in trigger_lower:
            return "NRC ADAMS, Federal Register"
        elif "doe" in trigger_lower or "grant" in trigger_lower:
            return "USASpending, DoE News"
        elif "contract" in trigger_lower or "ppa" in trigger_lower:
            return "SEC EDGAR 8-K filings"
        elif "cost" in trigger_lower or "overrun" in trigger_lower:
            return "Earnings calls, 10-K filings"
        elif "tariff" in trigger_lower:
            return "Federal Register, Congress.gov"
        else:
            return "RSS feeds, SEC filings"

    def _generate_recommendation(
        self,
        level: ConvictionLevel,
        triangulation_met: bool,
        strongest_counter: Optional[CounterThesis],
        entry_catalysts: List[Catalyst]
    ) -> Tuple[str, str]:
        """Generate recommendation and entry timing."""

        # Recommendation
        if level.value >= 4 and triangulation_met:
            recommendation = "BUY"
        elif level.value >= 3:
            recommendation = "HOLD" if triangulation_met else "AVOID"
        elif level.value == 2:
            recommendation = "AVOID"
        else:
            recommendation = "AVOID"

        # If fatal counter-thesis, always avoid
        if strongest_counter and strongest_counter.severity == "fatal":
            recommendation = "AVOID"

        # Entry timing
        if recommendation == "BUY":
            if any(c.probability > 0.7 for c in entry_catalysts):
                entry_timing = "NOW"
            else:
                entry_timing = "WAIT_CATALYST"
        elif recommendation == "HOLD":
            entry_timing = "WAIT_CATALYST"
        else:
            entry_timing = "NOT_YET"

        return recommendation, entry_timing

    def _compute_stop_loss(self, level: ConvictionLevel) -> float:
        """Compute stop-loss percentage based on conviction."""
        # Higher conviction = tighter stop (more confident in thesis)
        return {
            5: 0.15,  # 15% stop on max conviction
            4: 0.20,
            3: 0.25,
            2: 0.30,
            1: 0.0,  # No position, no stop
        }[level.value]

    def _compute_target(self, level: ConvictionLevel) -> float:
        """Compute target gain percentage based on conviction."""
        return {
            5: 0.50,  # 50% target on max conviction
            4: 0.40,
            3: 0.30,
            2: 0.20,
            1: 0.0,
        }[level.value]

    # ==========================================================================
    # AGENT INTERFACE (for scheduler integration)
    # ==========================================================================

    def collect(self) -> List[Artifact]:
        """Collect artifacts by evaluating all theses."""
        reports = self.evaluate_all_theses()

        # Create artifact with conviction reports
        report_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "theses_evaluated": len(reports),
            "reports": [r.to_dict() for r in reports],
        }

        content = json.dumps(report_data, indent=2).encode()
        content_hash = hashlib.sha256(content).hexdigest()

        local_path = self.artifact_dir / f"conviction_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        local_path.write_bytes(content)

        return [Artifact(
            url="internal://conviction_engine",
            artifact_type="json",
            local_path=str(local_path),
            content_hash=content_hash,
            metadata={
                "theses_evaluated": len(reports),
                "buy_recommendations": sum(1 for r in reports if r.recommendation == "BUY"),
                "avoid_recommendations": sum(1 for r in reports if r.recommendation == "AVOID"),
            }
        )]

    def extract(self, artifacts: List[Artifact]) -> List[StructuredFact]:
        """Extract facts from conviction reports."""
        facts = []

        for artifact in artifacts:
            if not artifact.local_path:
                continue

            try:
                with open(artifact.local_path, "r") as f:
                    data = json.load(f)
            except Exception:
                continue

            for report in data.get("reports", []):
                facts.append(StructuredFact(
                    fact_type="conviction_assessment",
                    subject=report["thesis_id"],
                    predicate=f"CONVICTION_{report['conviction_level']}",
                    object=report["recommendation"],
                    source_artifact=artifact,
                    confidence=report["conviction_score"] / 100.0,
                    raw_text=f"{report['thesis_statement'][:100]}... → {report['recommendation']}",
                    metadata={
                        "conviction_level": report["conviction_level"],
                        "conviction_score": report["conviction_score"],
                        "position_size_pct": report["position_size_pct"],
                        "triangulation_met": report["triangulation_met"],
                        "entry_timing": report["entry_timing"],
                    }
                ))

        return facts

    def propose(self, facts: List[StructuredFact]) -> Tuple[List[ProposedClaim], List[ProposedEdge]]:
        """Propose claims for conviction assessments."""
        claims = []
        edges = []

        for fact in facts:
            proposal_id = self._generate_proposal_id()

            meta = fact.metadata
            claim_text = (
                f"Conviction Assessment: {fact.subject} → {fact.object} "
                f"(Level {meta['conviction_level']}, Score {meta['conviction_score']:.1f}%, "
                f"Size {meta['position_size_pct']*100:.0f}% of portfolio)"
            )

            claims.append(ProposedClaim(
                proposal_id=proposal_id,
                claim_text=claim_text,
                topic="conviction",
                agent_name=self.name,
                source_url="internal://conviction_engine",
                reasoning=f"Entry timing: {meta['entry_timing']}, Triangulation: {meta['triangulation_met']}",
                promotion_requirement="Manual review of conviction report",
            ))

        return claims, edges


# =============================================================================
# WHAT DATA SOURCES INCREASE CONFIDENCE?
# =============================================================================

DATA_SOURCES_FOR_CONVICTION = """
## DATA SOURCES THAT INCREASE CONVICTION

### TIER 0 - MAXIMUM CONVICTION BOOST (+15 points each)

1. **SEC EDGAR 13F Filings** (Institutional ownership)
   - Tool: EDGARAgent
   - What: Large funds increasing positions
   - Signal: Smart money accumulation
   - Schedule: Daily 2AM via systemd timer

2. **SEC EDGAR Form 4** (Insider transactions)
   - Tool: EDGARAgent
   - What: CEO/CFO buying shares with own money
   - Signal: Insiders believe in thesis
   - Schedule: Daily 2AM

3. **USASpending Grants** (Government funding)
   - Tool: USASpendingAgent
   - What: DoE, DoD, CHIPS Act grants awarded
   - Signal: Policy thesis validated
   - Schedule: Daily 2AM

4. **NRC Permits** (Nuclear regulatory)
   - Tool: NuclearSMRAgent
   - What: Design certifications, construction permits
   - Signal: Regulatory thesis validated
   - Schedule: Daily 2AM

5. **Federal Register Rules** (Policy implementation)
   - Tool: FederalRegisterAgent
   - What: Final rules, not just proposed
   - Signal: Policy actually happening
   - Schedule: Daily 2AM

6. **FRED Economic Data** (Macro confirmation)
   - Tool: SignalConvergenceAnalyzer
   - What: M2, trade deficit, manufacturing employment
   - Signal: Macro thesis validated by data
   - Schedule: On-demand

### TIER 1 - MODERATE CONVICTION BOOST (+8 points each)

7. **Options Unusual Activity**
   - Tool: NEED TO BUILD
   - What: Large call buying, put selling
   - Signal: Smart money positioning for catalyst
   - Data Source: CBOE, unusual_whales API

8. **Credit Rating Changes**
   - Tool: NEED TO BUILD
   - What: S&P/Moody's upgrades
   - Signal: Fundamental improvement
   - Data Source: S&P, Moody's

9. **Analyst Ratings**
   - Tool: NEED TO BUILD
   - What: Buy ratings, price target raises
   - Signal: Professional validation
   - Data Source: FactSet, Bloomberg (paid)

10. **Industry Conference Announcements**
    - Tool: RSSSignalAgent
    - What: CEO presentations, partnership announcements
    - Signal: Company executing on thesis
    - Data Source: 8-K filings, press releases

### TIER 2 - CONTEXT ONLY (+3 points each)

11. **YouTube/Podcast Signals**
    - Tool: YouTubeSignalAnalyzer, PrometheanAgent
    - What: Expert guests discussing sector
    - Signal: Narrative building
    - Note: Does NOT increase conviction alone

12. **Social Sentiment**
    - Tool: NEED TO BUILD
    - What: Twitter/Reddit activity
    - Signal: Retail awareness (contrarian indicator)
    - Data Source: Social APIs

---

## TOOLS NEEDED TO ADD

1. **OptionsFlowAgent** - Monitor unusual options activity (CBOE API)
2. **CreditRatingAgent** - Track rating changes (public filings)
3. **AnalystRatingAgent** - Track consensus changes (FactSet/Yahoo)
4. **SocialSentimentAgent** - Monitor retail awareness (contrarian signal)
5. **EarningsCallAgent** - Parse transcripts for thesis keywords
6. **ConferenceAgent** - Track industry event announcements
"""


# =============================================================================
# STANDALONE EXECUTION
# =============================================================================

def main():
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from fgip.db import FGIPDatabase

    import argparse
    parser = argparse.ArgumentParser(description="FGIP Conviction Engine")
    parser.add_argument("db_path", help="Path to FGIP database")
    parser.add_argument("--thesis", "-t", help="Specific thesis ID to evaluate")
    parser.add_argument("--all", "-a", action="store_true", help="Evaluate all theses")
    parser.add_argument("--list", "-l", action="store_true", help="List available theses")
    parser.add_argument("--sources", "-s", action="store_true", help="Show data sources info")
    args = parser.parse_args()

    if args.sources:
        print(DATA_SOURCES_FOR_CONVICTION)
        return

    if args.list:
        print("Available Investment Theses:")
        print("=" * 60)
        for thesis in INVESTMENT_THESES:
            print(f"  {thesis['thesis_id']}")
            print(f"    Tickers: {', '.join(thesis['tickers'])}")
            print(f"    Sector: {thesis['sector']}")
            print()
        return

    db = FGIPDatabase(args.db_path)
    engine = ConvictionEngine(db)

    print("=" * 60)
    print("FGIP CONVICTION ENGINE")
    print("Would I bet my own money on this?")
    print("=" * 60)

    if args.thesis:
        report = engine.evaluate_thesis(args.thesis)
        _print_report(report)
    elif args.all:
        reports = engine.evaluate_all_theses()
        for report in reports:
            _print_report(report)
            print()
    else:
        # Default: run as agent
        result = engine.run()
        print(f"\nAgent Results:")
        print(f"  Artifacts collected: {result['artifacts_collected']}")
        print(f"  Facts extracted: {result['facts_extracted']}")
        print(f"  Claims proposed: {result['claims_proposed']}")


def _print_report(report: ConvictionReport):
    """Print a conviction report."""
    print()
    print(f"THESIS: {report.thesis_id}")
    print(f"  {report.thesis_statement[:80]}...")
    print(f"  Tickers: {', '.join(report.tickers)}")
    print()
    print(f"CONVICTION: Level {report.conviction_level} ({report.conviction_score:.1f}%)")
    print(f"  {ConvictionLevel(report.conviction_level).description}")
    print(f"  Position Size: {report.position_size_pct*100:.0f}% of portfolio")
    print()
    print(f"TRIANGULATION: {'MET' if report.triangulation_met else 'NOT MET'}")
    print(f"  {report.triangulation_count} independent sources: {', '.join(report.triangulation_sources)}")
    print()
    print(f"SIGNALS:")
    print(f"  Confirming: {len(report.confirming_signals)} ({sum(1 for s in report.confirming_signals if s.source_tier == 0)} Tier 0)")
    print(f"  Refuting: {len(report.refuting_signals)}")
    print(f"  Neutral: {len(report.neutral_signals)}")
    print()
    print(f"COUNTER-THESIS: {report.counter_thesis_severity}")
    if report.strongest_counter:
        print(f"  {report.strongest_counter.description}")
        if report.strongest_counter.mitigation:
            print(f"  Mitigation: {report.strongest_counter.mitigation}")
    print()
    print(f"RECOMMENDATION: {report.recommendation}")
    print(f"  Entry Timing: {report.entry_timing}")
    if report.stop_loss_pct:
        print(f"  Stop Loss: {report.stop_loss_pct*100:.0f}%")
    if report.target_price_pct:
        print(f"  Target: +{report.target_price_pct*100:.0f}%")
    print()
    print(f"CATALYSTS TO MONITOR:")
    for cat in report.entry_catalysts[:3]:
        print(f"  [ENTRY] {cat.description}")
        print(f"          Source: {cat.monitoring_source}")
    for cat in report.exit_catalysts[:3]:
        print(f"  [EXIT] {cat.description}")


if __name__ == "__main__":
    main()
