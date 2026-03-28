"""
THESIS node generation for FGIP graph.

Thesis nodes are first-class entities that regime edges connect to.
This prevents dangling edges and enables proper graph traversal.

A thesis has:
- claim: the investment thesis statement
- scope: what's in/out of scope
- time_horizon: expected timeframe for thesis to play out
- risk_factors: what could invalidate the thesis
- falsifiability: how to test if thesis is wrong
- source_diversity: minimum independent source families required

v1.0: Initial thesis schema
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class ThesisDefinition:
    """Definition of an investment thesis for graph insertion."""
    thesis_id: str                          # e.g., "thesis:nuclear-smr"
    claim: str                              # The thesis statement
    scope: str                              # What's in/out
    time_horizon: str                       # e.g., "2025-2030", "5-10 years"
    risk_factors: List[str]                 # What could invalidate
    falsifiability: str                     # How to test if wrong
    sector: Optional[str] = None            # e.g., "Energy", "Defense"
    tickers: List[str] = field(default_factory=list)  # Related tickers
    created_at: Optional[str] = None
    conviction_level: int = 3               # 1-5 scale
    source_diversity_required: int = 2      # Min independent sources for confirmation


# Canonical JSON serialization
def _json_canonical(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def thesis_to_node(thesis: ThesisDefinition) -> Dict[str, Any]:
    """
    Convert ThesisDefinition to graph node dict.

    Returns dict ready for insertion into nodes table.
    """
    created = thesis.created_at or datetime.now(timezone.utc).isoformat()

    description = (
        f"{thesis.claim} "
        f"[Horizon: {thesis.time_horizon}] "
        f"[Conviction: {thesis.conviction_level}/5]"
    )

    return {
        "node_id": thesis.thesis_id,
        "node_type": "THESIS",
        "name": thesis.claim[:100],  # Truncate for display
        "description": description,
        "aliases": json.dumps(thesis.tickers, sort_keys=True, separators=(",", ":")),
        "metadata": _json_canonical({
            "claim": thesis.claim,
            "scope": thesis.scope,
            "time_horizon": thesis.time_horizon,
            "risk_factors": thesis.risk_factors,
            "falsifiability": thesis.falsifiability,
            "sector": thesis.sector,
            "tickers": thesis.tickers,
            "conviction_level": thesis.conviction_level,
            "source_diversity_required": thesis.source_diversity_required,
            "created_at": created,
        }),
    }


def generate_thesis_nodes(theses: List[ThesisDefinition]) -> List[Dict[str, Any]]:
    """Generate all thesis nodes for insertion."""
    return [thesis_to_node(t) for t in theses]


# ============================================================================
# Pre-defined theses (canonical list for regime edge targets)
# ============================================================================

CANONICAL_THESES = [
    ThesisDefinition(
        thesis_id="thesis:nuclear-smr",
        claim="Small modular reactors will see significant deployment 2025-2035 driven by AI datacenter demand and grid reliability needs",
        scope="US-based SMR development, manufacturing, and deployment. Excludes traditional large reactors.",
        time_horizon="2025-2035",
        risk_factors=[
            "NRC approval delays",
            "Cost overruns exceeding 50%",
            "Public opposition / NIMBY",
            "Natural gas remains cheap (<$3/mmBtu sustained)",
            "Competing tech (fusion, geothermal) breakthrough",
        ],
        falsifiability="No SMR receives NRC construction permit by 2028, or <5 units in construction by 2030",
        sector="Energy",
        tickers=["SMR", "OKLO", "NNE", "CCJ", "LEU"],
        conviction_level=4,
    ),
    ThesisDefinition(
        thesis_id="thesis:uranium",
        claim="Uranium supply/demand imbalance will drive sustained price elevation through 2030",
        scope="Uranium spot and term pricing, enrichment capacity, mine restarts",
        time_horizon="2025-2030",
        risk_factors=[
            "Kazakhstan production surge",
            "Japan reactor restarts slower than expected",
            "Secondary supply (decommissioning, HEU downblending)",
            "Demand destruction from reactor closures",
        ],
        falsifiability="Spot price falls below $60/lb sustained for 6+ months",
        sector="Commodities",
        tickers=["CCJ", "UEC", "NXE", "UUUU", "DNN"],
        conviction_level=4,
    ),
    ThesisDefinition(
        thesis_id="thesis:rare-earth",
        claim="US/allied rare earth supply chain will develop to reduce China dependence",
        scope="REE mining, processing, magnet manufacturing outside China",
        time_horizon="2025-2032",
        risk_factors=[
            "China price dumping to kill competitors",
            "Permitting delays in US/Canada/Australia",
            "Demand lower than projected (EV slowdown)",
            "Substitute materials emerge",
        ],
        falsifiability="No non-China heavy REE separation plant operational by 2028",
        sector="Materials",
        tickers=["MP", "UUUU", "LYSCF"],
        conviction_level=3,
    ),
    ThesisDefinition(
        thesis_id="thesis:defense",
        claim="Defense spending will remain elevated through 2030 driven by great power competition",
        scope="US and allied defense budgets, prime contractors, munitions",
        time_horizon="2025-2030",
        risk_factors=[
            "Major peace breakthrough (unlikely)",
            "US fiscal crisis forces cuts",
            "Political shift to non-intervention",
        ],
        falsifiability="US defense budget declines >10% YoY",
        sector="Defense",
        tickers=["LMT", "RTX", "NOC", "GD", "HII"],
        conviction_level=5,
    ),
    ThesisDefinition(
        thesis_id="thesis:reshoring",
        claim="US manufacturing reshoring will accelerate, driven by CHIPS Act, IRA, and supply chain security concerns",
        scope="Semiconductor, battery, pharmaceutical, critical mineral processing",
        time_horizon="2024-2032",
        risk_factors=[
            "Labor cost differential remains too high",
            "Permitting/NEPA delays kill projects",
            "Political reversal of incentives",
            "Automation doesn't close cost gap",
        ],
        falsifiability="Manufacturing employment flat/declining 2025-2028, or CHIPS projects cancelled >50%",
        sector="Industrials",
        tickers=["INTC", "MU", "GFS", "TXN", "AMAT"],
        conviction_level=4,
    ),
    ThesisDefinition(
        thesis_id="thesis:inflation-regime",
        claim="Structural inflation will remain elevated (3-5%) through 2028 due to deglobalization, labor costs, and fiscal dominance",
        scope="US CPI, PCE, wage growth, fiscal trajectory",
        time_horizon="2024-2028",
        risk_factors=[
            "Severe recession crushes demand",
            "AI productivity boom exceeds expectations",
            "Political will for fiscal austerity",
            "China deflation exports",
        ],
        falsifiability="Core PCE <2.5% for 12+ consecutive months",
        sector="Macro",
        tickers=[],  # Macro thesis, position via TIPS, commodities, etc.
        conviction_level=3,
    ),
]


def get_canonical_thesis(thesis_id: str) -> Optional[ThesisDefinition]:
    """Get a canonical thesis by ID."""
    for t in CANONICAL_THESES:
        if t.thesis_id == thesis_id:
            return t
    return None


def get_all_canonical_thesis_ids() -> List[str]:
    """Get list of all canonical thesis IDs."""
    return [t.thesis_id for t in CANONICAL_THESES]


if __name__ == "__main__":
    # Generate and print thesis nodes
    nodes = generate_thesis_nodes(CANONICAL_THESES)

    print(f"Generated {len(nodes)} thesis nodes:")
    for node in nodes:
        meta = json.loads(node["metadata"])
        print(f"\n  {node['node_id']}")
        print(f"    Claim: {meta['claim'][:60]}...")
        print(f"    Horizon: {meta['time_horizon']}")
        print(f"    Conviction: {meta['conviction_level']}/5")
        print(f"    Falsifiability: {meta['falsifiability'][:50]}...")
