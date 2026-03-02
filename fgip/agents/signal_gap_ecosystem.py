"""
FGIP Signal Gap Ecosystem Agent - Detects signal/graph gaps and auto-expands ecosystems.

Core concept:
    Signal Layer (YouTube/RSS) -> Gap Detection -> Ecosystem Expansion -> Auto-spawn Nodes

When signal layer shows consumption of a topic but graph has no coverage:
1. DETECT the gap (signal != graph)
2. EXPAND beyond obvious players to full ecosystem
3. AUTO-SPAWN proposed nodes/edges for review

Expansion layers:
- Direct Players: Companies in sector
- Suppliers: Who supplies them
- Lenders/Financiers: Who funds projects (DoE, private equity, utility PPAs)
- Upstream Commodities: Raw inputs (uranium, rare earths, copper)
- Adjacent Beneficiaries: Who benefits downstream (data centers, utilities, grid operators)

Safety rules:
- All proposals go to staging tables for human review
- Uses existing FGIP loaders for signal data
- Respects graph provenance requirements
"""

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .base import (
    FGIPAgent,
    Artifact,
    StructuredFact,
    ProposedClaim,
    ProposedEdge,
    ProposedNode,
)


# =============================================================================
# SECTOR MAPPINGS
# =============================================================================

# Sector -> Upstream commodity mapping
SECTOR_COMMODITIES: Dict[str, List[str]] = {
    "nuclear": ["uranium", "rare-earths", "zirconium", "cobalt"],
    "semiconductors": ["silicon", "neon", "copper", "palladium"],
    "steel": ["iron-ore", "coking-coal", "nickel", "chromium"],
    "evs": ["lithium", "cobalt", "nickel", "copper", "graphite"],
    "defense": ["titanium", "rare-earths", "aluminum", "steel"],
    "reshoring": ["copper", "steel", "aluminum", "cement"],
    "data_centers": ["copper", "rare-earths", "natural-gas"],
    "grid": ["copper", "aluminum", "transformers", "steel"],
    # NEW: Infrastructure equipment sectors
    "data_center_infrastructure": ["copper", "aluminum", "transformers", "cooling-equipment"],
    "fab_infrastructure": ["industrial-gases", "specialty-chemicals", "ultra-pure-water", "silicon"],
    "electrical_power": ["copper", "steel", "transformers"],
    "thermal_management": ["aluminum", "copper", "refrigerants"],
    "advanced_packaging": ["silicon", "specialty-chemicals", "copper"],
}

# Sector -> Infrastructure company tickers (picks and shovels layer)
SECTOR_COMPANIES: Dict[str, List[str]] = {
    "electrical_power": ["FPS", "POWL", "VRT", "ETN", "NVT"],
    "thermal_management": ["MOD", "VRT", "JCI"],
    "advanced_packaging": ["AMKR", "ASX"],
    "specialty_materials": ["ENTG", "LIN", "APD", "DD"],
    "industrial_gases": ["LIN", "APD"],
    "semiconductor_equipment": ["ASML", "AMAT", "LRCX", "KLAC"],
    "data_center_infrastructure": ["FPS", "POWL", "VRT", "MOD", "ETN"],
    "fab_infrastructure": ["ENTG", "LIN", "APD", "ASML", "AMAT"],
}

# Sector -> Typical lenders/funders
SECTOR_FUNDERS: Dict[str, List[str]] = {
    "nuclear": ["doe-ne", "ardp", "loan-programs-office"],
    "semiconductors": ["chips-program", "doe", "defense-production-act"],
    "defense": ["dod", "darpa", "diu"],
    "infrastructure": ["dot", "iija", "build-america"],
    "evs": ["doe-vehicle", "ira-credits"],
    "reshoring": ["chips-program", "ira", "iija"],
}

# Sector -> SIC codes for EDGAR search
SECTOR_SIC_CODES: Dict[str, List[str]] = {
    "nuclear": ["4911", "4931", "3829"],  # Electric utilities, measuring instruments
    "semiconductors": ["3674", "3672"],  # Semiconductors, printed circuits
    "steel": ["3312", "3316", "3317"],  # Steel works, cold-rolled, steel pipe
    "evs": ["3711", "3714"],  # Motor vehicles, parts
    "defense": ["3812", "3761"],  # Navigation systems, guided missiles
}

# Guest -> Sector mapping (for signal layer analysis)
GUEST_SECTOR_MAP: Dict[str, str] = {
    "jay yu": "nuclear",
    "isaiah taylor": "nuclear",
    "palmer luckey": "defense",
    "peter zeihan": "reshoring",
    "michael saylor": "monetary",
    "scott bessent": "correction",
    "jamieson greer": "reshoring",
}

# Topic keywords -> Sector mapping
TOPIC_SECTOR_MAP: Dict[str, str] = {
    "nuclear": "nuclear",
    "smr": "nuclear",
    "reactor": "nuclear",
    "uranium": "nuclear",
    "semiconductor": "semiconductors",
    "chips": "semiconductors",
    "fab": "semiconductors",
    "defense": "defense",
    "military": "defense",
    "reshoring": "reshoring",
    "manufacturing": "reshoring",
    "tariff": "reshoring",
    "steel": "steel",
    "ev": "evs",
    "battery": "evs",
    "lithium": "evs",
    "data center": "data_centers",
    "grid": "grid",
    "power": "grid",
    # NEW: Infrastructure equipment topics
    "transformer": "electrical_power",
    "switchgear": "electrical_power",
    "electrical equipment": "electrical_power",
    "power distribution": "electrical_power",
    "cooling": "thermal_management",
    "liquid cooling": "thermal_management",
    "thermal": "thermal_management",
    "hvac": "thermal_management",
    "packaging": "advanced_packaging",
    "advanced packaging": "advanced_packaging",
    "osat": "advanced_packaging",
    "industrial gas": "industrial_gases",
    "nitrogen": "industrial_gases",
    "argon": "industrial_gases",
    "filtration": "specialty_materials",
    "purification": "specialty_materials",
    "photoresist": "specialty_materials",
    "euv": "semiconductor_equipment",
    "lithography": "semiconductor_equipment",
    "deposition": "semiconductor_equipment",
    "etch": "semiconductor_equipment",
    # IPO-related keywords for infrastructure detection
    "ipo": "infrastructure_ipo",
    "goes public": "infrastructure_ipo",
    "public offering": "infrastructure_ipo",
}


# =============================================================================
# COMMODITY DEFINITIONS
# =============================================================================

COMMODITY_NODES: Dict[str, Dict[str, Any]] = {
    "uranium": {
        "node_id": "commodity-uranium",
        "name": "Uranium Exposure",
        "node_type": "COMMODITY",
        "description": "Nuclear fuel commodity. Leading indicator for nuclear sector moves.",
        "aliases": ["Uranium", "U3O8"],
        "metadata": {
            "sector": "nuclear",
            "tickers": ["CCJ", "URA", "UUUU", "URG", "NXE", "UEC"],
            "upstream_of": ["nuclear_smr", "nuclear_utility"],
        }
    },
    "copper": {
        "node_id": "commodity-copper",
        "name": "Copper Exposure",
        "node_type": "COMMODITY",
        "description": "Industrial metal. Grid buildout, EVs, data centers. Infrastructure proxy.",
        "aliases": ["Copper", "Dr. Copper"],
        "metadata": {
            "sector": "infrastructure",
            "tickers": ["FCX", "COPX", "SCCO", "TECK"],
            "upstream_of": ["reshoring", "evs", "data_centers", "grid"],
        }
    },
    "rare-earths": {
        "node_id": "commodity-rare-earths",
        "name": "Rare Earths Exposure",
        "node_type": "COMMODITY",
        "description": "Critical minerals for defense, EVs, electronics. China supply chain risk.",
        "aliases": ["Rare Earth Elements", "REE"],
        "metadata": {
            "sector": "critical_minerals",
            "tickers": ["MP", "REMX", "UUUU"],
            "upstream_of": ["defense", "evs", "semiconductors"],
            "supply_risk": "china_dominant",
        }
    },
    "lithium": {
        "node_id": "commodity-lithium",
        "name": "Lithium Exposure",
        "node_type": "COMMODITY",
        "description": "Battery metal. EV supply chain critical input.",
        "aliases": ["Lithium"],
        "metadata": {
            "sector": "evs",
            "tickers": ["ALB", "SQM", "LTHM", "LAC"],
            "upstream_of": ["evs", "energy_storage"],
        }
    },
    "nickel": {
        "node_id": "commodity-nickel",
        "name": "Nickel Exposure",
        "node_type": "COMMODITY",
        "description": "Steel alloy and battery input. Indonesia/Philippines supply.",
        "aliases": ["Nickel"],
        "metadata": {
            "sector": "metals",
            "tickers": ["VALE", "BHP"],
            "upstream_of": ["steel", "evs", "batteries"],
        }
    },
    "steel": {
        "node_id": "commodity-steel",
        "name": "Steel Exposure",
        "node_type": "COMMODITY",
        "description": "Infrastructure and manufacturing foundation. Reshoring proxy.",
        "aliases": ["Steel"],
        "metadata": {
            "sector": "metals",
            "tickers": ["NUE", "STLD", "X", "CLF"],
            "upstream_of": ["infrastructure", "reshoring", "defense"],
        }
    },
    "aluminum": {
        "node_id": "commodity-aluminum",
        "name": "Aluminum Exposure",
        "node_type": "COMMODITY",
        "description": "Lightweight metal for defense, transportation, packaging.",
        "aliases": ["Aluminum", "Aluminium"],
        "metadata": {
            "sector": "metals",
            "tickers": ["AA", "CENX"],
            "upstream_of": ["defense", "transportation", "grid"],
        }
    },
    "neon": {
        "node_id": "commodity-neon",
        "name": "Neon Exposure",
        "node_type": "COMMODITY",
        "description": "Critical for semiconductor lithography. Ukraine supply disruption risk.",
        "aliases": ["Neon Gas"],
        "metadata": {
            "sector": "semiconductors",
            "tickers": [],  # No direct exposure
            "upstream_of": ["semiconductors"],
            "supply_risk": "ukraine_russia",
        }
    },
    # NEW: Infrastructure equipment commodities
    "industrial-gases": {
        "node_id": "commodity-industrial-gases",
        "name": "Industrial Gases Exposure",
        "node_type": "COMMODITY",
        "description": "Nitrogen, argon, hydrogen for semiconductor fabs. 15-20yr supply contracts.",
        "aliases": ["Industrial Gases", "Specialty Gases"],
        "metadata": {
            "sector": "fab_infrastructure",
            "tickers": ["LIN", "APD"],
            "upstream_of": ["semiconductors", "data_centers"],
            "contract_length": "15-20 years",
        }
    },
    "cooling-equipment": {
        "node_id": "commodity-cooling-equipment",
        "name": "Data Center Cooling Equipment",
        "node_type": "COMMODITY",
        "description": "Liquid cooling systems for AI data centers. Thermal wall at 100kW/rack.",
        "aliases": ["Cooling Systems", "Liquid Cooling"],
        "metadata": {
            "sector": "thermal_management",
            "tickers": ["MOD", "VRT", "JCI"],
            "upstream_of": ["data_centers", "ai_compute"],
            "bottleneck": "100kW/rack thermal wall",
        }
    },
    "transformers": {
        "node_id": "commodity-transformers",
        "name": "Power Transformers",
        "node_type": "COMMODITY",
        "description": "Large power transformers for data centers and grid. 4-year lead times.",
        "aliases": ["Transformers", "Switchgear", "Power Distribution"],
        "metadata": {
            "sector": "electrical_power",
            "tickers": ["FPS", "POWL", "ETN"],
            "upstream_of": ["data_centers", "grid", "semiconductors"],
            "lead_time": "4 years",
            "bottleneck": "Domestic manufacturing capacity constrained",
        }
    },
    "specialty-chemicals": {
        "node_id": "commodity-specialty-chemicals",
        "name": "Semiconductor Specialty Chemicals",
        "node_type": "COMMODITY",
        "description": "Ultra-pure chemicals, photoresists, CMP slurries for chip manufacturing.",
        "aliases": ["Specialty Chemicals", "Electronic Chemicals"],
        "metadata": {
            "sector": "specialty_materials",
            "tickers": ["ENTG", "DD"],
            "upstream_of": ["semiconductors"],
            "criticality": "Single particle contamination kills chip",
        }
    },
}


# =============================================================================
# GAP FINDING DATA CLASS
# =============================================================================

@dataclass
class GapFinding:
    """A detected gap between signal layer and graph coverage."""
    topic: str
    sector: str
    signal_strength: int  # Number of videos/articles
    graph_coverage: int  # Number of nodes in sector
    gap_ratio: float  # signal_strength / (graph_coverage + 1)
    guests_detected: List[str] = field(default_factory=list)
    channels_detected: List[str] = field(default_factory=list)
    recommended_expansions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "sector": self.sector,
            "signal_strength": self.signal_strength,
            "graph_coverage": self.graph_coverage,
            "gap_ratio": self.gap_ratio,
            "guests_detected": self.guests_detected,
            "channels_detected": self.channels_detected,
            "recommended_expansions": self.recommended_expansions,
        }


# =============================================================================
# SIGNAL GAP ECOSYSTEM AGENT
# =============================================================================

class SignalGapEcosystemAgent(FGIPAgent):
    """
    Detects gaps between signal layer and graph coverage,
    then auto-expands to full ecosystem.

    DETECT: Compare YouTube signal topics to graph sectors
    EXPAND: For each gap, find suppliers, lenders, commodities
    SPAWN: Propose nodes/edges for the full ecosystem

    This is a meta-agent that combines:
    - Signal layer data (YouTube/RSS consumption)
    - Graph topology analysis
    - Sector ecosystem knowledge
    """

    def __init__(self, db, artifact_dir: str = "data/artifacts/signal_gap"):
        super().__init__(
            db=db,
            name="signal_gap_ecosystem",
            description="Detects signal/graph gaps, expands full ecosystem"
        )
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self._gaps: List[GapFinding] = []

    def detect_gaps(self, signal_threshold: int = 5) -> List[GapFinding]:
        """
        Detect gaps between signal layer and graph coverage.

        Args:
            signal_threshold: Minimum signal strength to consider

        Returns:
            List of GapFinding objects
        """
        gaps = []

        # Get signal layer data
        signal_topics = self._get_signal_topics()
        signal_guests = self._get_signal_guests()

        # Get graph coverage by sector
        graph_coverage = self._get_graph_coverage_by_sector()

        # Check topic-based gaps
        for topic, signal_strength in signal_topics.items():
            if signal_strength < signal_threshold:
                continue

            # Map topic to sector
            sector = self._topic_to_sector(topic)
            if not sector:
                continue

            coverage = graph_coverage.get(sector, 0)

            # Gap detected if high signal but low coverage
            gap_ratio = signal_strength / (coverage + 1)
            if gap_ratio > 2.0:  # Signal significantly exceeds coverage
                gaps.append(GapFinding(
                    topic=topic,
                    sector=sector,
                    signal_strength=signal_strength,
                    graph_coverage=coverage,
                    gap_ratio=gap_ratio,
                    recommended_expansions=self._get_expansion_recommendations(sector),
                ))

        # Check guest-based gaps
        for guest, count in signal_guests.items():
            if count < 3:  # Need multiple appearances
                continue

            sector = GUEST_SECTOR_MAP.get(guest.lower())
            if not sector:
                continue

            coverage = graph_coverage.get(sector, 0)
            gap_ratio = count / (coverage + 1)

            if gap_ratio > 1.5:
                # Check if gap already exists for this sector
                existing = next((g for g in gaps if g.sector == sector), None)
                if existing:
                    existing.guests_detected.append(guest)
                else:
                    gaps.append(GapFinding(
                        topic=f"guest:{guest}",
                        sector=sector,
                        signal_strength=count,
                        graph_coverage=coverage,
                        gap_ratio=gap_ratio,
                        guests_detected=[guest],
                        recommended_expansions=self._get_expansion_recommendations(sector),
                    ))

        self._gaps = gaps
        return gaps

    def _get_signal_topics(self) -> Dict[str, int]:
        """Get topic distribution from signal layer."""
        try:
            from fgip.loaders.chatgpt_signal import get_category_distribution
            return get_category_distribution()
        except (ImportError, RuntimeError):
            # Fallback: query proposed_claims for topic distribution
            conn = self.db.connect()
            rows = conn.execute("""
                SELECT topic, COUNT(*) as cnt
                FROM proposed_claims
                GROUP BY topic
            """).fetchall()
            return {row[0]: row[1] for row in rows}

    def _get_signal_guests(self) -> Dict[str, int]:
        """Get guest frequency from signal layer."""
        try:
            from fgip.loaders.chatgpt_signal import _LOADED_DATA
            return _LOADED_DATA.get("guest_frequency", {})
        except ImportError:
            return {}

    def _get_graph_coverage_by_sector(self) -> Dict[str, int]:
        """Query graph for node counts by sector."""
        conn = self.db.connect()

        # Count nodes by sector metadata
        rows = conn.execute("""
            SELECT
                json_extract(metadata, '$.sector') as sector,
                COUNT(*) as cnt
            FROM nodes
            WHERE json_extract(metadata, '$.sector') IS NOT NULL
            GROUP BY sector
        """).fetchall()

        coverage = {row[0]: row[1] for row in rows if row[0]}

        # Also count by node_type patterns
        type_sector_map = {
            "COMMODITY": "commodities",
            "TECHNOLOGY": "technology",
            "POLICY": "policy",
        }

        for row in conn.execute("""
            SELECT node_type, COUNT(*) as cnt FROM nodes GROUP BY node_type
        """).fetchall():
            sector = type_sector_map.get(row[0])
            if sector:
                coverage[sector] = coverage.get(sector, 0) + row[1]

        return coverage

    def _topic_to_sector(self, topic: str) -> Optional[str]:
        """Map a topic keyword to a sector."""
        topic_lower = topic.lower().replace("_", " ").replace("-", " ")

        for keyword, sector in TOPIC_SECTOR_MAP.items():
            if keyword in topic_lower:
                return sector

        return None

    def _get_expansion_recommendations(self, sector: str) -> List[str]:
        """Get recommended expansion types for a sector."""
        recommendations = []

        if sector in SECTOR_COMMODITIES:
            recommendations.append("commodities")
        if sector in SECTOR_FUNDERS:
            recommendations.append("funders")
        if sector in SECTOR_SIC_CODES:
            recommendations.append("companies_via_edgar")

        recommendations.extend(["suppliers", "adjacent_beneficiaries"])
        return recommendations

    def collect(self) -> List[Artifact]:
        """
        Collect artifacts by detecting gaps and loading signal data.

        Returns:
            List of Artifact objects representing gap findings
        """
        artifacts = []

        # Detect gaps
        gaps = self.detect_gaps()

        if not gaps:
            print("  No significant signal/graph gaps detected")
            return artifacts

        # Create artifact for gap analysis
        gap_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "gaps_detected": len(gaps),
            "gaps": [g.to_dict() for g in gaps],
        }

        content = json.dumps(gap_data, indent=2).encode()
        content_hash = hashlib.sha256(content).hexdigest()

        local_path = self.artifact_dir / f"gap_analysis_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        local_path.write_bytes(content)

        artifacts.append(Artifact(
            url="internal://signal_gap_analysis",
            artifact_type="json",
            local_path=str(local_path),
            content_hash=content_hash,
            metadata={
                "source": "signal_gap_detection",
                "gaps_count": len(gaps),
                "sectors": list(set(g.sector for g in gaps)),
            }
        ))

        print(f"  Detected {len(gaps)} signal/graph gaps")
        for gap in gaps:
            print(f"    - {gap.sector}: signal={gap.signal_strength}, coverage={gap.graph_coverage}, ratio={gap.gap_ratio:.2f}")

        return artifacts

    def extract(self, artifacts: List[Artifact]) -> List[StructuredFact]:
        """
        Extract ecosystem expansion facts from gap analysis.

        For each gap:
        1. Find direct players (existing in graph or to propose)
        2. Map to upstream commodities
        3. Identify funding sources
        4. Find adjacent beneficiaries
        """
        facts = []

        for gap in self._gaps:
            sector = gap.sector

            # 1. Commodity facts
            if sector in SECTOR_COMMODITIES:
                for commodity in SECTOR_COMMODITIES[sector]:
                    if commodity in COMMODITY_NODES:
                        commodity_data = COMMODITY_NODES[commodity]
                        artifact = artifacts[0] if artifacts else None

                        facts.append(StructuredFact(
                            fact_type="ecosystem_commodity",
                            subject=commodity_data["node_id"],
                            predicate="UPSTREAM_OF",
                            object=sector,
                            source_artifact=artifact or Artifact(
                                url="internal://ecosystem_mapping",
                                artifact_type="internal"
                            ),
                            confidence=0.85,
                            raw_text=f"{commodity_data['name']} is upstream commodity for {sector}",
                            metadata={
                                "commodity_data": commodity_data,
                                "gap_sector": sector,
                                "expansion_type": "commodity",
                            }
                        ))

            # 2. Funder facts
            if sector in SECTOR_FUNDERS:
                for funder in SECTOR_FUNDERS[sector]:
                    facts.append(StructuredFact(
                        fact_type="ecosystem_funder",
                        subject=funder,
                        predicate="FUNDS",
                        object=sector,
                        source_artifact=artifacts[0] if artifacts else Artifact(
                            url="internal://ecosystem_mapping",
                            artifact_type="internal"
                        ),
                        confidence=0.75,
                        raw_text=f"{funder} is funding source for {sector}",
                        metadata={
                            "funder_id": funder,
                            "gap_sector": sector,
                            "expansion_type": "funder",
                        }
                    ))

            # 3. Guest-to-sector facts
            for guest in gap.guests_detected:
                facts.append(StructuredFact(
                    fact_type="signal_guest",
                    subject=self._guest_to_node_id(guest),
                    predicate="SIGNAL_DETECTED_FOR",
                    object=sector,
                    source_artifact=artifacts[0] if artifacts else Artifact(
                        url="internal://signal_analysis",
                        artifact_type="internal"
                    ),
                    confidence=0.80,
                    raw_text=f"Signal layer detected {guest} discussing {sector}",
                    metadata={
                        "guest_name": guest,
                        "signal_strength": gap.signal_strength,
                        "expansion_type": "signal_guest",
                    }
                ))

        print(f"  Extracted {len(facts)} ecosystem facts")
        return facts

    def propose(self, facts: List[StructuredFact]) -> Tuple[List[ProposedClaim], List[ProposedEdge], List[ProposedNode]]:
        """
        Generate proposals for ecosystem expansion.

        Creates:
        - ProposedNode for commodities not in graph
        - ProposedEdge for relationships
        - ProposedClaim documenting expansion reasoning
        """
        claims = []
        edges = []
        nodes = []

        # Track which commodities to propose
        proposed_commodity_ids = set()

        for fact in facts:
            proposal_id = self._generate_proposal_id()

            if fact.fact_type == "ecosystem_commodity":
                commodity_data = fact.metadata.get("commodity_data", {})
                commodity_id = commodity_data.get("node_id", fact.subject)

                # Check if node exists
                if not self._node_exists(commodity_id) and commodity_id not in proposed_commodity_ids:
                    proposed_commodity_ids.add(commodity_id)

                    # Propose the commodity node
                    node = ProposedNode(
                        proposal_id=self._generate_proposal_id(),
                        node_id=commodity_id,
                        node_type="COMMODITY",
                        name=commodity_data.get("name", fact.subject),
                        agent_name=self.name,
                        aliases=commodity_data.get("aliases", []),
                        description=commodity_data.get("description", ""),
                        source_url="internal://signal_gap_ecosystem",
                        reasoning=f"Gap detection: {fact.metadata.get('gap_sector')} sector has signal but no commodity exposure nodes",
                    )
                    nodes.append(node)

                # Propose edge: commodity -> sector entities
                sector = fact.metadata.get("gap_sector", "")
                sector_entities = self._get_sector_entities(sector)

                for entity_id in sector_entities[:5]:  # Limit to 5 edges per commodity
                    edge = ProposedEdge(
                        proposal_id=self._generate_proposal_id(),
                        from_node=commodity_id,
                        to_node=entity_id,
                        relationship="UPSTREAM_OF",
                        agent_name=self.name,
                        detail=f"{commodity_data.get('name', commodity_id)} is upstream input for {entity_id}",
                        confidence=fact.confidence,
                        reasoning=f"Sector ecosystem mapping: {commodity_id} provides raw materials for {sector}",
                        promotion_requirement="Verify commodity dependency in 10-K Item 1 or supply chain disclosure",
                    )
                    edges.append(edge)

                # Create claim
                claim = ProposedClaim(
                    proposal_id=proposal_id,
                    claim_text=f"{commodity_data.get('name', fact.subject)} is upstream commodity exposure for {fact.metadata.get('gap_sector')} sector",
                    topic="ecosystem_expansion",
                    agent_name=self.name,
                    source_url=fact.source_artifact.url if fact.source_artifact else None,
                    reasoning=f"Gap ratio {self._get_gap_ratio_for_sector(fact.metadata.get('gap_sector')):.2f}x - signal significantly exceeds graph coverage",
                    promotion_requirement="Verify commodity dependency in sector company filings",
                )
                claims.append(claim)

            elif fact.fact_type == "ecosystem_funder":
                funder_id = fact.metadata.get("funder_id", fact.subject)
                sector = fact.metadata.get("gap_sector", "")

                # Propose edges: funder -> sector entities
                sector_entities = self._get_sector_entities(sector)

                for entity_id in sector_entities[:3]:  # Limit funding edges
                    if self._node_exists(funder_id):
                        edge = ProposedEdge(
                            proposal_id=self._generate_proposal_id(),
                            from_node=entity_id,
                            to_node=funder_id,
                            relationship="FUNDED_BY",
                            agent_name=self.name,
                            detail=f"{entity_id} potentially funded by {funder_id}",
                            confidence=0.60,  # Lower confidence - needs verification
                            reasoning=f"Sector ecosystem mapping: {funder_id} is typical funding source for {sector}",
                            promotion_requirement="Verify via USASpending.gov or company SEC filings",
                        )
                        edges.append(edge)

            elif fact.fact_type == "signal_guest":
                guest_node_id = fact.subject
                sector = fact.object

                # Create claim about signal detection
                claim = ProposedClaim(
                    proposal_id=proposal_id,
                    claim_text=f"Signal layer detected guest {fact.metadata.get('guest_name')} discussing {sector} ({fact.metadata.get('signal_strength')} appearances)",
                    topic="signal_detection",
                    agent_name=self.name,
                    source_url="internal://youtube_signal_layer",
                    reasoning="YouTube/RSS consumption pattern indicates interest in sector with low graph coverage",
                    promotion_requirement="Cross-reference guest with sector companies/policies",
                )
                claims.append(claim)

        print(f"  Proposed: {len(claims)} claims, {len(edges)} edges, {len(nodes)} nodes")
        return claims, edges, nodes

    def _node_exists(self, node_id: str) -> bool:
        """Check if a node exists in the graph."""
        conn = self.db.connect()
        result = conn.execute(
            "SELECT 1 FROM nodes WHERE node_id = ?", (node_id,)
        ).fetchone()
        return result is not None

    def _get_sector_entities(self, sector: str) -> List[str]:
        """Get existing node IDs in a sector."""
        conn = self.db.connect()

        rows = conn.execute("""
            SELECT node_id FROM nodes
            WHERE json_extract(metadata, '$.sector') = ?
            LIMIT 10
        """, (sector,)).fetchall()

        return [row[0] for row in rows]

    def _guest_to_node_id(self, guest_name: str) -> str:
        """Convert guest name to node_id format."""
        return guest_name.lower().replace(" ", "-")

    def _get_gap_ratio_for_sector(self, sector: str) -> float:
        """Get the gap ratio for a sector from detected gaps."""
        for gap in self._gaps:
            if gap.sector == sector:
                return gap.gap_ratio
        return 0.0

    def detect_infrastructure_ipo(self, news_text: str) -> Optional[ProposedNode]:
        """
        Detect IPO announcements in infrastructure sectors.

        When a new IPO in infrastructure sectors is detected (via RSS/news),
        auto-propose a node for the company.

        Args:
            news_text: News article or headline text

        Returns:
            ProposedNode if infrastructure IPO detected, None otherwise
        """
        import re

        # IPO detection patterns
        ipo_patterns = [
            r"(\w+(?:\s+\w+)?)\s+(?:IPO|goes public|files for IPO|initial public offering)",
            r"IPO.*?(\w+\s+\w+(?:\s+\w+)?)\s+(?:power|electrical|cooling|semiconductor|data center)",
            r"(\w+(?:\s+\w+)?)\s+raises.*?in IPO",
        ]

        # Infrastructure sector keywords
        infrastructure_keywords = [
            "power", "electrical", "transformer", "switchgear",
            "cooling", "thermal", "hvac", "liquid cooling",
            "semiconductor", "chip", "fab", "packaging",
            "industrial gas", "filtration", "purification",
            "data center", "infrastructure",
        ]

        news_lower = news_text.lower()

        # Check if this is infrastructure-related
        is_infrastructure = any(kw in news_lower for kw in infrastructure_keywords)
        if not is_infrastructure:
            return None

        # Try to extract company name
        company_name = None
        for pattern in ipo_patterns:
            match = re.search(pattern, news_text, re.IGNORECASE)
            if match:
                company_name = match.group(1).strip()
                break

        if not company_name:
            return None

        # Determine sector from keywords
        sector = "infrastructure"
        for keyword, sec in TOPIC_SECTOR_MAP.items():
            if keyword in news_lower and sec != "infrastructure_ipo":
                sector = sec
                break

        # Generate node ID
        node_id = f"company-{company_name.lower().replace(' ', '-').replace('.', '')}"

        return ProposedNode(
            proposal_id=self._generate_proposal_id(),
            node_id=node_id,
            node_type="COMPANY",
            name=company_name,
            agent_name=self.name,
            aliases=[company_name],
            description=f"Infrastructure company detected via IPO announcement. Sector: {sector}",
            source_url="internal://signal_gap_ipo_detection",
            reasoning=f"IPO detected in infrastructure sector ({sector}). Auto-proposed for review.",
        )

    def get_sector_companies(self, sector: str) -> List[str]:
        """Get list of company tickers for a sector."""
        return SECTOR_COMPANIES.get(sector, [])


# =============================================================================
# STANDALONE EXECUTION
# =============================================================================

def main():
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from fgip.db import FGIPDatabase

    import argparse
    parser = argparse.ArgumentParser(description="Run Signal Gap Ecosystem Agent")
    parser.add_argument("db_path", help="Path to FGIP database")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to database")
    parser.add_argument("--threshold", type=int, default=5, help="Signal threshold for gap detection")
    args = parser.parse_args()

    db = FGIPDatabase(args.db_path)
    agent = SignalGapEcosystemAgent(db)

    print("=" * 60)
    print("FGIP SIGNAL GAP ECOSYSTEM AGENT")
    print("=" * 60)
    print("\nDetects gaps between signal layer and graph coverage")
    print("Expands to full ecosystem: suppliers, lenders, commodities")

    # Detect gaps first
    print("\n[GAP DETECTION]")
    gaps = agent.detect_gaps(signal_threshold=args.threshold)

    if not gaps:
        print("No significant gaps detected. Try lowering --threshold.")
        return

    print(f"\nDetected {len(gaps)} gaps:")
    for gap in gaps:
        print(f"  {gap.sector}:")
        print(f"    Signal: {gap.signal_strength}, Coverage: {gap.graph_coverage}")
        print(f"    Gap ratio: {gap.gap_ratio:.2f}x")
        if gap.guests_detected:
            print(f"    Guests: {', '.join(gap.guests_detected)}")
        print(f"    Expand: {', '.join(gap.recommended_expansions)}")

    if args.dry_run:
        print("\n[DRY RUN - Collecting and extracting only]")
        artifacts = agent.collect()
        print(f"\nArtifacts collected: {len(artifacts)}")
        facts = agent.extract(artifacts)
        print(f"Facts extracted: {len(facts)}")
        for fact in facts[:10]:
            print(f"  - {fact.subject} {fact.predicate} {fact.object}")

        claims, edges, nodes = agent.propose(facts)
        print(f"\nWould propose:")
        print(f"  Claims: {len(claims)}")
        print(f"  Edges: {len(edges)}")
        print(f"  Nodes: {len(nodes)}")
        for node in nodes[:5]:
            print(f"    Node: {node.node_id} ({node.node_type})")
    else:
        result = agent.run()
        print(f"\nResults:")
        print(f"  Artifacts collected: {result['artifacts_collected']}")
        print(f"  Facts extracted: {result['facts_extracted']}")
        print(f"  Claims proposed: {result['claims_proposed']}")
        print(f"  Edges proposed: {result['edges_proposed']}")
        print(f"  Nodes proposed: {result['nodes_proposed']}")

        if result.get('errors'):
            print(f"\nErrors:")
            for error in result['errors']:
                print(f"  - {error}")


if __name__ == "__main__":
    main()
