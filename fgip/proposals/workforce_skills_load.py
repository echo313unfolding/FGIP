"""Workforce Skills Intelligence — load nodes, claims, sources, and edges.

Trades workforce aging, apprenticeship pipeline collapse, and skill-loss
as national security + GDP risk vector.

All claims enter per WO-TIER-GATE-01. Tier recomputed from URL domain.

Verified sources:
  - dol.gov  (apprenticeship statistics FY2021)       → tier 0
  - deloitte.com (manufacturing skills gap study)     → tier 2
  - nam.org  (2.1M unfilled jobs projection)          → tier 2
  - csis.org (Empty Bins defense industrial base)     → tier 1
  - rand.org (defense industrial base analysis)       → tier 1

Historical precedents sourced from academic/documented records.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fgip.db import FGIPDatabase
from fgip.schema import (
    Node, Edge, Claim, Source, NodeType, EdgeType, ClaimStatus,
    compute_sha256,
)


DB_PATH = str(Path(__file__).resolve().parents[2] / "fgip.db")


# ============================================================================
# SOURCES
# ============================================================================

SOURCES = [
    Source.from_url("https://www.dol.gov/agencies/eta/apprenticeship/about/statistics"),
    Source.from_url("https://www.deloitte.com/us/en/insights/industry/manufacturing-industrial-products/manufacturing-industry-diversity.html"),
    Source.from_url("https://www.nam.org/2-1-million-manufacturing-jobs-could-go-unfilled-by-2030-13743/"),
    Source.from_url("https://www.csis.org/analysis/empty-bins-wartime-environment-challenge-us-defense-industrial-base"),
    Source.from_url("https://www.rand.org/pubs/research_reports/RRA2534-1.html"),
    # BLS Occupational Outlook — construction/extraction
    Source.from_url("https://www.bls.gov/ooh/construction-and-extraction/home.htm"),
    # BLS employment projections
    Source.from_url("https://www.bls.gov/emp/tables/emp-by-detailed-occupation.htm"),
    # Historical precedents — academic sources
    Source.from_url("https://www.jstor.org/stable/10.1086/673397"),  # Roman concrete loss
    Source.from_url("https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/s/shipbuilding.html"),  # UK/US shipyard history
]


# ============================================================================
# NODES — Workforce Sectors
# ============================================================================

NODES = [
    # ── Workforce Sectors ──────────────────────────────────────────────
    Node(
        node_id="sector-construction-trades",
        node_type=NodeType.WORKFORCE_SECTOR,
        name="US Construction Trades Workforce",
        description="Skilled construction trades: welders, pipefitters, electricians, ironworkers, boilermakers, millwrights. Median age rising, apprenticeship pipeline insufficient to replace retirements.",
        metadata={
            "employment_approx": "7.7M (BLS 2023)",
            "shortage_estimate": "501K (ABC 2024)",
            "median_age_trend": "rising since 2003",
            "sector": "construction",
        },
    ),
    Node(
        node_id="sector-manufacturing",
        node_type=NodeType.WORKFORCE_SECTOR,
        name="US Manufacturing Workforce",
        description="Manufacturing production workers: CNC machinists, welders, maintenance technicians, industrial design engineers, production assemblers. 2.1M jobs projected unfilled by 2030.",
        metadata={
            "unfilled_2030_projection": "2.1M (Deloitte/MI 2021)",
            "economic_multiplier": "$2.74 per $1 spent",
            "gdp_risk": "$1T+ negative impact if unfilled",
            "jobs_lost_2020": "578K",
            "sector": "manufacturing",
        },
    ),
    Node(
        node_id="sector-defense-industrial-workforce",
        node_type=NodeType.WORKFORCE_SECTOR,
        name="Defense Industrial Base Workforce",
        description="Workers in shipyards, arsenals, munitions plants, aerospace manufacturing. Constrained by same skilled trades pipeline as commercial construction/manufacturing. National security dependency.",
        metadata={
            "sector": "defense",
            "dependency": "shares labor pool with commercial construction",
            "critical_trades": "welders, machinists, electricians, shipfitters",
        },
    ),
    Node(
        node_id="sector-shipbuilding",
        node_type=NodeType.WORKFORCE_SECTOR,
        name="US Shipbuilding Workforce",
        description="Naval and commercial shipyard workers. Down from 180K+ (WWII peak workforce legacy) to constrained levels. Skills take 5-8 years to develop, cannot be surged.",
        metadata={
            "sector": "shipbuilding",
            "training_time_years": "5-8",
            "surge_capability": "none — skills cannot be printed",
        },
    ),

    # ── Skill Domains ──────────────────────────────────────────────────
    Node(
        node_id="skill-welding",
        node_type=NodeType.SKILL_DOMAIN,
        name="Welding / Fusion Trades",
        description="Structural welding, pipe welding, TIG/MIG/stick, orbital welding, fusion technology for PVC/HDPE. Critical for pipelines, data centers, shipyards, power plants, infrastructure.",
        metadata={
            "apprentices_active": "est. 15-20K",
            "demand_growth": "increasing (data center + infrastructure boom)",
            "avg_journeyman_age": "mid-40s to 50s",
            "certification": "AWS, ASME, API",
        },
    ),
    Node(
        node_id="skill-pipefitting",
        node_type=NodeType.SKILL_DOMAIN,
        name="Pipefitting / Plumbing",
        description="Industrial pipefitting, plumbing, steamfitting. Required for every data center, power plant, and industrial facility. 21,971 active apprentices (DOL FY2021).",
        metadata={
            "apprentices_active_2021": 21971,
            "source": "DOL FY2021",
        },
    ),
    Node(
        node_id="skill-electrical",
        node_type=NodeType.SKILL_DOMAIN,
        name="Electrical Trades",
        description="Inside/outside electricians, instrumentation techs. Largest apprenticeship trade (71,812 active FY2021). Still insufficient for data center + grid buildout demand.",
        metadata={
            "apprentices_active_2021": 71812,
            "source": "DOL FY2021",
            "rank": "1st by apprentice count",
        },
    ),
    Node(
        node_id="skill-machining",
        node_type=NodeType.SKILL_DOMAIN,
        name="CNC Machining / Toolmaking",
        description="CNC operators, machinists, tool-and-die makers. Defense-critical (munitions, aerospace parts). Among most acute shortages in manufacturing.",
        metadata={
            "shortage_severity": "critical",
            "defense_dependency": "munitions, missile components, aircraft parts",
        },
    ),
    Node(
        node_id="skill-boilermaking",
        node_type=NodeType.SKILL_DOMAIN,
        name="Boilermaking",
        description="Boilermakers: pressure vessels, tanks, industrial boilers, nuclear containment. Extremely small workforce with long training pipeline.",
        metadata={
            "workforce_size": "small (under 50K nationally)",
            "training_time_years": "4-5",
        },
    ),
    Node(
        node_id="skill-millwright",
        node_type=NodeType.SKILL_DOMAIN,
        name="Millwright / Industrial Mechanics",
        description="Install, maintain, repair industrial machinery. Required for every manufacturing plant and power facility. Aging workforce with declining entry rates.",
        metadata={
            "sector_dependency": "manufacturing, power generation, mining",
        },
    ),

    # ── Historical Precedents ──────────────────────────────────────────
    Node(
        node_id="precedent-roman-concrete",
        node_type=NodeType.HISTORICAL_PRECEDENT,
        name="Roman Concrete Formula Loss",
        description="Roman opus caementicium (marine concrete) knowledge was lost when the guild system collapsed. Aqueducts, harbors, and infrastructure could not be maintained. Formula not rediscovered until modern materials science (2023 MIT study confirmed self-healing mechanism).",
        metadata={
            "era": "5th-6th century CE",
            "skill_type": "materials engineering",
            "consequence": "infrastructure collapse, no maintenance capability",
            "recovery_time": "1500+ years",
        },
    ),
    Node(
        node_id="precedent-uk-shipbuilding",
        node_type=NodeType.HISTORICAL_PRECEDENT,
        name="UK Shipbuilding Skill Loss (Post-1960s)",
        description="UK closed most commercial shipyards 1960s-1980s. When Falklands War hit (1982), couldn't surge naval construction. Had to requisition civilian ships (SS Canberra, Atlantic Conveyor). Workforce skills take a generation to rebuild; UK naval capacity never fully recovered.",
        metadata={
            "era": "1960-1982",
            "skill_type": "shipbuilding, marine engineering",
            "consequence": "could not surge naval production during Falklands",
            "trigger": "commercial shipyard closures + no apprenticeship pipeline",
        },
    ),
    Node(
        node_id="precedent-soviet-submarine",
        node_type=NodeType.HISTORICAL_PRECEDENT,
        name="Soviet Nuclear Submarine Maintenance Collapse",
        description="After Soviet collapse (1991), nuclear submarine maintenance workforce scattered. Skills were not documented — held by individual technicians. Result: rusting fleet, radiation risks, decommissioning crisis that took decades and international aid to address.",
        metadata={
            "era": "1991-2010s",
            "skill_type": "nuclear engineering, submarine maintenance",
            "consequence": "environmental hazard, fleet unusable",
        },
    ),
    Node(
        node_id="precedent-us-solid-rocket",
        node_type=NodeType.HISTORICAL_PRECEDENT,
        name="US Solid Rocket Motor Workforce Attrition",
        description="Post-Cold War drawdown shrank the solid rocket motor workforce (Minuteman III, Trident). When modernization programs launched (GBSD/Sentinel), the skilled workforce had retired or died. Rebuilding from scratch adds years and billions to programs.",
        metadata={
            "era": "1990s-2020s",
            "skill_type": "solid propellant manufacturing, rocket motor assembly",
            "consequence": "Sentinel ICBM program delays, cost overruns",
            "affected_programs": "GBSD/Sentinel, SLS boosters",
        },
    ),
    Node(
        node_id="precedent-damascus-steel",
        node_type=NodeType.HISTORICAL_PRECEDENT,
        name="Damascus Steel Production Loss",
        description="Wootz/Damascus steel production knowledge was lost by ~1750 CE. The specific ore sources depleted and the tacit knowledge of the smiths was not transmitted. Modern metallurgy can approximate but not exactly replicate the original process.",
        metadata={
            "era": "~1750 CE",
            "skill_type": "metallurgy, bladesmithing",
            "consequence": "technology permanently lost",
            "recovery": "partial (modern carbon nanotube analysis)",
        },
    ),
    Node(
        node_id="precedent-greek-fire",
        node_type=NodeType.HISTORICAL_PRECEDENT,
        name="Greek Fire Formula Loss",
        description="Byzantine incendiary weapon, closely guarded state secret. When Constantinople fell (1453), the formula and its practitioners were lost. Never conclusively reproduced despite centuries of attempts.",
        metadata={
            "era": "7th century - 1453 CE",
            "skill_type": "chemical weapons, naval warfare",
            "consequence": "military technology permanently lost",
        },
    ),
]


# ============================================================================
# CLAIMS
# ============================================================================

CLAIMS = [
    # ── DOL Apprenticeship Data (Tier 0) ───────────────────────────────
    Claim(
        claim_id="FGIP-WF-001",
        claim_text="US registered apprenticeship completions were 96,915 in FY2021, while 593,690 apprentices were active across 27,385 programs. Completion rate (~16% of active) indicates most apprentices do not finish.",
        topic="WorkforceIntel",
        status=ClaimStatus.EVIDENCED,
        required_tier=0,
        notes="DOL ETA apprenticeship statistics FY2021. Tier 0 (dol.gov).",
    ),
    Claim(
        claim_id="FGIP-WF-002",
        claim_text="Electricians have the largest apprenticeship pipeline at 71,812 active apprentices (FY2021), followed by carpenters (29,800) and plumbers (21,971). Combined top-5 trades account for ~156K of 593K total apprentices.",
        topic="WorkforceIntel",
        status=ClaimStatus.EVIDENCED,
        required_tier=0,
        notes="DOL ETA FY2021. Top 5: electrician 71,812; carpenter 29,800; plumber 21,971; sprinkler fitter 17,595; construction laborer 15,009.",
    ),
    Claim(
        claim_id="FGIP-WF-003",
        claim_text="Active apprentices dropped 6.7% from FY2020 (636,515) to FY2021 (593,690), despite new apprentice enrollments increasing 9% (222,243 → 241,849). More are starting but fewer are staying.",
        topic="WorkforceIntel",
        status=ClaimStatus.EVIDENCED,
        required_tier=0,
        notes="DOL ETA FY2020 vs FY2021 comparison.",
    ),

    # ── Deloitte/NAM Manufacturing Gap (Tier 2) ────────────────────────
    Claim(
        claim_id="FGIP-WF-004",
        claim_text="2.1 million US manufacturing jobs could go unfilled by 2030 (Deloitte/Manufacturing Institute 2021). 77% of manufacturers anticipate ongoing difficulty attracting and retaining workers. Baby boomer retirements are the top cited cause.",
        topic="WorkforceIntel",
        status=ClaimStatus.EVIDENCED,
        required_tier=2,
        notes="Deloitte/MI skills gap study. NAM confirms the 2.1M figure.",
    ),
    Claim(
        claim_id="FGIP-WF-005",
        claim_text="Manufacturing has the highest economic multiplier of any US sector: $2.74 added to the economy for every $1 spent. Leaving 2.1M manufacturing jobs unfilled could create a negative economic impact exceeding $1 trillion by 2030.",
        topic="WorkforceIntel",
        status=ClaimStatus.EVIDENCED,
        required_tier=2,
        notes="Deloitte/MI study. $1T impact = 2.1M positions × multiplier effect.",
    ),
    Claim(
        claim_id="FGIP-WF-006",
        claim_text="Critical middle-skill manufacturing positions in acute shortage include CNC machinists, welders, maintenance technicians, industrial design engineers, and production assemblers. These are the same skills required for defense industrial base production.",
        topic="WorkforceIntel",
        status=ClaimStatus.EVIDENCED,
        required_tier=2,
        notes="Deloitte/MI study. Defense crossover is structural — same labor pool.",
    ),

    # ── Defense Industrial Base Workforce (Tier 1) ─────────────────────
    Claim(
        claim_id="FGIP-WF-007",
        claim_text="The defense industrial base and commercial construction/manufacturing compete for the same skilled trades workforce. A welder who works on a data center is not available to work on a Navy destroyer. Infrastructure boom + reshoring + defense modernization create triple demand on a single shrinking labor pool.",
        topic="WorkforceIntel",
        status=ClaimStatus.PARTIAL,
        required_tier=1,
        notes="Structural observation. CSIS Empty Bins + RAND reports discuss capacity constraints. Specific labor-pool competition claim needs primary DOD source.",
    ),
    Claim(
        claim_id="FGIP-WF-008",
        claim_text="Shipyard skills (welding, pipefitting, marine electrical, shipfitting) require 5-8 years of apprenticeship and on-the-job training. Unlike software engineering, these skills cannot be learned in a bootcamp or surged with overtime. Lost skills take a generation to rebuild.",
        topic="WorkforceIntel",
        status=ClaimStatus.PARTIAL,
        required_tier=1,
        notes="Navy shipyard apprenticeship programs document 4-year minimum. 5-8 years to journeyman-level competence is industry consensus.",
    ),

    # ── Historical Pattern Claims (Tier 2/3) ──────────────────────────
    Claim(
        claim_id="FGIP-WF-009",
        claim_text="Every historical instance of skill-loss follows the same pattern: (1) economic pressure reduces demand for the skill, (2) training pipeline collapses, (3) practitioners retire/die without transferring knowledge, (4) when demand returns, the skill is gone and cannot be quickly regenerated. Pattern observed in: Roman concrete, Damascus steel, Greek fire, UK shipbuilding, Soviet submarine maintenance, US solid rocket motors.",
        topic="WorkforceIntel",
        status=ClaimStatus.PARTIAL,
        required_tier=2,
        notes="Synthesis across documented historical cases. Each individual case is documented; the meta-pattern is an inference.",
    ),
    Claim(
        claim_id="FGIP-WF-010",
        claim_text="The US is currently in phase 2-3 of the skill-loss pattern for multiple critical trades simultaneously: apprenticeship pipelines are insufficient (96K completions/year vs 2.1M projected gap), median workforce age is rising, and demand is surging (data centers, reshoring, defense modernization). This is predictive: phase 4 (irrecoverable loss) follows if pipeline is not rebuilt within 5-10 years.",
        topic="WorkforceIntel",
        status=ClaimStatus.PARTIAL,
        required_tier=2,
        notes="Predictive claim based on historical pattern + current DOL/Deloitte data. Falsifiable: if apprenticeship completions triple by 2030, gap closes.",
    ),
    Claim(
        claim_id="FGIP-WF-011",
        claim_text="Tariff-driven reshoring (confirmed by FGIP tariff analysis: energy intensity r=0.709) creates manufacturing demand that requires skilled trades workers who do not exist in sufficient numbers. Reshoring policy without workforce policy is an unfunded mandate.",
        topic="WorkforceIntel",
        status=ClaimStatus.PARTIAL,
        required_tier=2,
        notes="Connects to existing FGIP tariff analysis. Tariff creates demand; workforce gap constrains supply.",
    ),

    # ── GDP + National Security Correlation ────────────────────────────
    Claim(
        claim_id="FGIP-WF-012",
        claim_text="Skill-loss is both a GDP risk ($1T+ manufacturing impact by 2030) and a national security risk (cannot produce munitions, ships, or aircraft without machinists, welders, and electricians). The two risks compound: GDP decline reduces tax revenue for defense spending, while defense workforce gaps reduce industrial surge capacity.",
        topic="WorkforceIntel",
        status=ClaimStatus.PARTIAL,
        required_tier=2,
        notes="Compound risk thesis. GDP number from Deloitte. Defense constraint from CSIS/RAND.",
    ),
    Claim(
        claim_id="FGIP-WF-013",
        claim_text="Construction sector apprenticeship is dominated by male workers (86% per DOL FY2021 RAPIDS data). Workers 35+ constitute only 20% of apprentices, while the existing journeyman workforce is aging into retirement. The pipeline is not diverse enough or large enough to replace exits.",
        topic="WorkforceIntel",
        status=ClaimStatus.EVIDENCED,
        required_tier=0,
        notes="DOL RAPIDS FY2021 demographics. Gender 86% male, 13% female. Age: 24-under 38%, 25-34 40%, 35+ 20%.",
    ),
]


# ============================================================================
# EDGES — connect workforce nodes to existing graph
# ============================================================================

EDGES = [
    # ── Skills required by sectors ─────────────────────────────────────
    Edge(edge_id="wf-req-const-weld", from_node_id="sector-construction-trades",
         to_node_id="skill-welding", edge_type=EdgeType.REQUIRES_SKILL,
         claim_id="FGIP-WF-001", metadata={"criticality": "high"}),
    Edge(edge_id="wf-req-const-pipe", from_node_id="sector-construction-trades",
         to_node_id="skill-pipefitting", edge_type=EdgeType.REQUIRES_SKILL,
         claim_id="FGIP-WF-001", metadata={"criticality": "high"}),
    Edge(edge_id="wf-req-const-elec", from_node_id="sector-construction-trades",
         to_node_id="skill-electrical", edge_type=EdgeType.REQUIRES_SKILL,
         claim_id="FGIP-WF-001", metadata={"criticality": "high"}),
    Edge(edge_id="wf-req-const-boiler", from_node_id="sector-construction-trades",
         to_node_id="skill-boilermaking", edge_type=EdgeType.REQUIRES_SKILL,
         claim_id="FGIP-WF-001", metadata={"criticality": "medium"}),
    Edge(edge_id="wf-req-const-mill", from_node_id="sector-construction-trades",
         to_node_id="skill-millwright", edge_type=EdgeType.REQUIRES_SKILL,
         claim_id="FGIP-WF-001", metadata={"criticality": "medium"}),
    Edge(edge_id="wf-req-mfg-mach", from_node_id="sector-manufacturing",
         to_node_id="skill-machining", edge_type=EdgeType.REQUIRES_SKILL,
         claim_id="FGIP-WF-004", metadata={"criticality": "critical"}),
    Edge(edge_id="wf-req-mfg-weld", from_node_id="sector-manufacturing",
         to_node_id="skill-welding", edge_type=EdgeType.REQUIRES_SKILL,
         claim_id="FGIP-WF-004", metadata={"criticality": "high"}),
    Edge(edge_id="wf-req-mfg-mill", from_node_id="sector-manufacturing",
         to_node_id="skill-millwright", edge_type=EdgeType.REQUIRES_SKILL,
         claim_id="FGIP-WF-004", metadata={"criticality": "high"}),
    Edge(edge_id="wf-req-def-weld", from_node_id="sector-defense-industrial-workforce",
         to_node_id="skill-welding", edge_type=EdgeType.REQUIRES_SKILL,
         claim_id="FGIP-WF-007", metadata={"criticality": "critical", "note": "shipyards, munitions, aerospace"}),
    Edge(edge_id="wf-req-def-mach", from_node_id="sector-defense-industrial-workforce",
         to_node_id="skill-machining", edge_type=EdgeType.REQUIRES_SKILL,
         claim_id="FGIP-WF-007", metadata={"criticality": "critical", "note": "munitions, missile components"}),
    Edge(edge_id="wf-req-def-elec", from_node_id="sector-defense-industrial-workforce",
         to_node_id="skill-electrical", edge_type=EdgeType.REQUIRES_SKILL,
         claim_id="FGIP-WF-007", metadata={"criticality": "critical"}),
    Edge(edge_id="wf-req-ship-weld", from_node_id="sector-shipbuilding",
         to_node_id="skill-welding", edge_type=EdgeType.REQUIRES_SKILL,
         claim_id="FGIP-WF-008", metadata={"criticality": "critical", "training_years": "5-8"}),
    Edge(edge_id="wf-req-ship-pipe", from_node_id="sector-shipbuilding",
         to_node_id="skill-pipefitting", edge_type=EdgeType.REQUIRES_SKILL,
         claim_id="FGIP-WF-008", metadata={"criticality": "critical"}),
    Edge(edge_id="wf-req-ship-elec", from_node_id="sector-shipbuilding",
         to_node_id="skill-electrical", edge_type=EdgeType.REQUIRES_SKILL,
         claim_id="FGIP-WF-008", metadata={"criticality": "critical"}),

    # ── Skill shortages in sectors ─────────────────────────────────────
    Edge(edge_id="wf-short-mach-mfg", from_node_id="skill-machining",
         to_node_id="sector-manufacturing", edge_type=EdgeType.SKILL_SHORTAGE_IN,
         claim_id="FGIP-WF-004", metadata={"severity": "critical"}),
    Edge(edge_id="wf-short-weld-const", from_node_id="skill-welding",
         to_node_id="sector-construction-trades", edge_type=EdgeType.SKILL_SHORTAGE_IN,
         claim_id="FGIP-WF-002", metadata={"severity": "high"}),
    Edge(edge_id="wf-short-weld-def", from_node_id="skill-welding",
         to_node_id="sector-defense-industrial-workforce", edge_type=EdgeType.SKILL_SHORTAGE_IN,
         claim_id="FGIP-WF-007", metadata={"severity": "critical", "note": "shared labor pool with commercial"}),

    # ── Retirement risk ────────────────────────────────────────────────
    Edge(edge_id="wf-retire-const", from_node_id="sector-construction-trades",
         to_node_id="sector-construction-trades", edge_type=EdgeType.RETIREMENT_RISK,
         claim_id="FGIP-WF-010", metadata={"median_age_trend": "rising", "pipeline_ratio": "96K completions vs 501K shortage"}),
    Edge(edge_id="wf-retire-mfg", from_node_id="sector-manufacturing",
         to_node_id="sector-manufacturing", edge_type=EdgeType.RETIREMENT_RISK,
         claim_id="FGIP-WF-005", metadata={"top_cause": "baby boomer retirements", "gap_2030": "2.1M"}),

    # ── Historical parallels ──────────────────────────────────────────
    Edge(edge_id="wf-parallel-uk-ship", from_node_id="precedent-uk-shipbuilding",
         to_node_id="sector-shipbuilding", edge_type=EdgeType.PARALLELS,
         claim_id="FGIP-WF-008", metadata={"pattern": "commercial yard closure -> skill loss -> no surge capacity"}),
    Edge(edge_id="wf-parallel-us-rocket", from_node_id="precedent-us-solid-rocket",
         to_node_id="sector-defense-industrial-workforce", edge_type=EdgeType.PARALLELS,
         claim_id="FGIP-WF-009", metadata={"pattern": "post-war drawdown -> workforce attrition -> modernization blocked"}),
    Edge(edge_id="wf-parallel-roman", from_node_id="precedent-roman-concrete",
         to_node_id="sector-construction-trades", edge_type=EdgeType.PARALLELS,
         claim_id="FGIP-WF-009", metadata={"pattern": "guild collapse -> material knowledge lost -> infrastructure decay"}),

    # ── Constrains capacity (workforce gap blocks projects) ───────────
    Edge(edge_id="wf-constrain-const", from_node_id="sector-construction-trades",
         to_node_id="sector-construction-trades", edge_type=EdgeType.CONSTRAINS_CAPACITY,
         claim_id="FGIP-WF-012", metadata={"mechanism": "data center + infrastructure boom requires workers that don't exist"}),
    Edge(edge_id="wf-constrain-def", from_node_id="sector-defense-industrial-workforce",
         to_node_id="sector-defense-industrial-workforce", edge_type=EdgeType.CONSTRAINS_CAPACITY,
         claim_id="FGIP-WF-012", metadata={"mechanism": "Sentinel ICBM, Columbia-class sub, munitions surge all blocked by workforce"}),
]

# ── Edges connecting to EXISTING graph nodes ──────────────────────────

EXISTING_EDGES = [
    Edge(edge_id="wf-dep-def-const", from_node_id="sector-defense-industrial-workforce",
         to_node_id="sector-construction-trades", edge_type=EdgeType.DEPENDS_ON,
         claim_id="FGIP-WF-010", metadata={"mechanism": "shared skilled trades labor pool"}),
]


# ============================================================================
# LOAD FUNCTION
# ============================================================================

def load(db_path: str = DB_PATH, dry_run: bool = False):
    """Load workforce intelligence nodes, claims, sources, and edges."""
    db = FGIPDatabase(db_path)

    print(f"Loading workforce skills intelligence into {db_path}")
    print(f"  Nodes:   {len(NODES)}")
    print(f"  Claims:  {len(CLAIMS)}")
    print(f"  Sources: {len(SOURCES)}")
    print(f"  Edges:   {len(EDGES) + len(EXISTING_EDGES)}")

    if dry_run:
        print("DRY RUN — no changes written")
        return

    # Insert sources (INSERT OR REPLACE — safe for re-runs)
    for s in SOURCES:
        db.insert_source(s)
    print(f"  ✓ {len(SOURCES)} sources inserted")

    # Insert nodes
    n_ok = 0
    for n in NODES:
        r = db.insert_node(n)
        if r.success:
            n_ok += 1
    print(f"  ✓ {n_ok}/{len(NODES)} nodes inserted (rest already exist)")

    # Insert claims + link to sources
    claim_source_map = {
        "FGIP-WF-001": ["dol.gov"],
        "FGIP-WF-002": ["dol.gov"],
        "FGIP-WF-003": ["dol.gov"],
        "FGIP-WF-004": ["deloitte.com", "nam.org"],
        "FGIP-WF-005": ["deloitte.com"],
        "FGIP-WF-006": ["deloitte.com"],
        "FGIP-WF-007": ["csis.org", "rand.org"],
        "FGIP-WF-008": ["history.navy.mil"],
        "FGIP-WF-009": ["jstor.org", "history.navy.mil"],
        "FGIP-WF-010": ["dol.gov", "deloitte.com"],
        "FGIP-WF-011": ["deloitte.com"],
        "FGIP-WF-012": ["deloitte.com", "csis.org"],
        "FGIP-WF-013": ["dol.gov"],
    }
    c_ok = 0
    for c in CLAIMS:
        if db.insert_claim(c):
            c_ok += 1
        domains = claim_source_map.get(c.claim_id, [])
        for s in SOURCES:
            if s.domain and any(d in s.domain for d in domains):
                db.link_claim_source(c.claim_id, s.source_id)
    print(f"  ✓ {c_ok}/{len(CLAIMS)} claims inserted + linked (rest already exist)")

    # Insert edges
    e_ok = 0
    for e in EDGES + EXISTING_EDGES:
        r = db.insert_edge(e)
        if r.success:
            e_ok += 1
    print(f"  ✓ {e_ok}/{len(EDGES) + len(EXISTING_EDGES)} edges inserted (rest already exist)")

    # Summary
    stats = db.get_stats()
    print(f"\nGraph now: {stats['nodes']} nodes, {stats['edges']} edges, {stats['claims']} claims")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Load workforce skills intelligence")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--db", default=DB_PATH, help="Database path")
    args = parser.parse_args()
    load(db_path=args.db, dry_run=args.dry_run)
