"""
FGIP Supply Chain Bottleneck Registry

Tracks critical supply chain vulnerabilities and single points of failure.
These are the chokepoints where committed capital flow can be disrupted.

Categories:
- SINGLE_SOURCE: Only one producer/supplier globally
- MONOPOLY: Market controlled by single entity
- CAPACITY_CONSTRAINED: Long lead times, limited production
- GEOGRAPHIC_CONCENTRATION: Supply concentrated in one region
- GEOPOLITICAL_RISK: Supply subject to sanctions/conflict

Investment signal: Bottlenecks create pricing power for suppliers
and risk for dependent companies.
"""

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class BottleneckType(str, Enum):
    """Classification of supply chain bottleneck."""
    SINGLE_SOURCE = "SINGLE_SOURCE"  # Only one producer globally
    MONOPOLY = "MONOPOLY"  # Market controlled by one entity
    CAPACITY_CONSTRAINED = "CAPACITY_CONSTRAINED"  # Long lead times
    GEOGRAPHIC_CONCENTRATION = "GEOGRAPHIC_CONCENTRATION"  # One region
    GEOPOLITICAL_RISK = "GEOPOLITICAL_RISK"  # Sanctions/conflict risk
    TECHNICAL_BARRIER = "TECHNICAL_BARRIER"  # Hard to replicate


class SeverityLevel(str, Enum):
    """Impact severity if bottleneck is disrupted."""
    CRITICAL = "CRITICAL"  # Global production halt
    HIGH = "HIGH"  # Significant delays/cost increases
    MEDIUM = "MEDIUM"  # Workarounds possible but costly
    LOW = "LOW"  # Minor impact


@dataclass
class SupplyChainBottleneck:
    """A documented supply chain vulnerability."""
    bottleneck_id: str
    name: str
    description: str
    bottleneck_type: BottleneckType
    severity: SeverityLevel
    location: Optional[str]
    operators: List[str]
    vulnerability_detail: str
    downstream_impact: str
    affected_sectors: List[str]
    mitigation: Optional[str]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bottleneck_id": self.bottleneck_id,
            "name": self.name,
            "description": self.description,
            "bottleneck_type": self.bottleneck_type.value,
            "severity": self.severity.value,
            "location": self.location,
            "operators": self.operators,
            "vulnerability_detail": self.vulnerability_detail,
            "downstream_impact": self.downstream_impact,
            "affected_sectors": self.affected_sectors,
            "mitigation": self.mitigation,
            "metadata": self.metadata,
        }


# =============================================================================
# SUPPLY CHAIN BOTTLENECKS REGISTRY
# =============================================================================

SUPPLY_CHAIN_BOTTLENECKS: Dict[str, SupplyChainBottleneck] = {
    # -------------------------------------------------------------------------
    # SEMICONDUCTOR SUPPLY CHAIN
    # -------------------------------------------------------------------------
    "spruce_pine_quartz": SupplyChainBottleneck(
        bottleneck_id="bottleneck-spruce-pine-quartz",
        name="Spruce Pine Ultra-High-Purity Quartz",
        description="Ultra-high-purity quartz for silicon wafer crucibles. The quartz holds molten silicon during wafer production.",
        bottleneck_type=BottleneckType.SINGLE_SOURCE,
        severity=SeverityLevel.CRITICAL,
        location="Spruce Pine, North Carolina, USA",
        operators=["Covia Holdings", "The Quartz Corp"],
        vulnerability_detail="SINGLE SOURCE - No substitute exists. Hurricane Helene (2024) demonstrated vulnerability.",
        downstream_impact="Global chip production halt if supply disrupted. Every semiconductor fab depends on this quartz.",
        affected_sectors=["semiconductors", "electronics", "automotive", "defense"],
        mitigation=None,  # No known substitute or alternative source
        metadata={
            "hurricane_helene_impact": "2024 - temporary disruption",
            "dependency": "All silicon wafer production globally",
            "companies_at_risk": ["TSMC", "Samsung", "Intel", "GlobalFoundries"],
        }
    ),

    "euv_lithography": SupplyChainBottleneck(
        bottleneck_id="bottleneck-euv-lithography",
        name="EUV Lithography Machines",
        description="Extreme ultraviolet lithography machines for sub-5nm chip production.",
        bottleneck_type=BottleneckType.MONOPOLY,
        severity=SeverityLevel.CRITICAL,
        location="Veldhoven, Netherlands",
        operators=["ASML"],
        vulnerability_detail="MONOPOLY - ASML is the only producer. $380M per machine, 2+ year backlog.",
        downstream_impact="No advanced (sub-5nm) chip production without EUV. AI chips, high-end processors blocked.",
        affected_sectors=["semiconductors", "ai_compute", "data_centers"],
        mitigation="DUV multi-patterning for some nodes, but not sub-5nm",
        metadata={
            "machine_price": "380M USD",
            "backlog": "2+ years",
            "export_restrictions": "Netherlands restricts sales to China",
            "ticker": "ASML",
        }
    ),

    "advanced_packaging_us": SupplyChainBottleneck(
        bottleneck_id="bottleneck-advanced-packaging-us",
        name="US Advanced Semiconductor Packaging",
        description="Backend advanced packaging (2.5D, 3D, chiplets) capacity in the United States.",
        bottleneck_type=BottleneckType.CAPACITY_CONSTRAINED,
        severity=SeverityLevel.HIGH,
        location="USA (Arizona under construction)",
        operators=["Amkor Technology"],
        vulnerability_detail="CAPACITY GAP - No large-scale US advanced packaging until Amkor Arizona (2028). Wafers made in US must be shipped to Asia for packaging.",
        downstream_impact="US chip supply chain incomplete. Security risk for defense chips.",
        affected_sectors=["semiconductors", "defense", "ai_compute"],
        mitigation="Amkor Arizona $7B facility under construction, CHIPS Act funded",
        metadata={
            "amkor_investment": "7B USD",
            "chips_funding": "900M USD",
            "production_start": "2028",
            "ticker": "AMKR",
            "lead_customers": ["Apple", "Nvidia"],
        }
    ),

    # -------------------------------------------------------------------------
    # NUCLEAR SUPPLY CHAIN
    # -------------------------------------------------------------------------
    "haleu_enrichment": SupplyChainBottleneck(
        bottleneck_id="bottleneck-haleu-enrichment",
        name="HALEU Uranium Enrichment",
        description="High-Assay Low-Enriched Uranium (19.75% enrichment) required for advanced reactor fuel.",
        bottleneck_type=BottleneckType.CAPACITY_CONSTRAINED,
        severity=SeverityLevel.HIGH,
        location="Piketon, Ohio, USA (expanding)",
        operators=["Centrus Energy (LEU)", "Orano (planned)"],
        vulnerability_detail="WESTERN CAPACITY GAP - Russia dominated HALEU pre-2024. Western capacity being built but limited.",
        downstream_impact="SMR deployment delayed without HALEU fuel. NuScale, X-energy, Kairos need HALEU.",
        affected_sectors=["nuclear", "energy", "defense"],
        mitigation="Centrus Piketon expansion, DOE fuel availability program, Orano US enrichment",
        metadata={
            "leu_backlog": "3.8B USD to 2040",
            "ticker": "LEU",
            "doe_investment": "2.7B USD total program",
            "enrichment_level": "19.75%",
        }
    ),

    "nuclear_fuel_fabrication": SupplyChainBottleneck(
        bottleneck_id="bottleneck-nuclear-fuel-fab",
        name="Advanced Nuclear Fuel Fabrication",
        description="TRISO fuel particles, metallic fuel, and other advanced reactor fuel forms.",
        bottleneck_type=BottleneckType.TECHNICAL_BARRIER,
        severity=SeverityLevel.HIGH,
        location="USA (multiple facilities)",
        operators=["BWXT", "X-energy", "Centrus"],
        vulnerability_detail="TECHNICAL COMPLEXITY - Advanced fuel forms require specialized manufacturing not available at scale.",
        downstream_impact="SMR commercialization timeline depends on fuel fabrication scale-up.",
        affected_sectors=["nuclear", "energy"],
        mitigation="DOE ARDP funding for fuel development, BWXT TRISO expansion",
        metadata={
            "fuel_types": ["TRISO", "metallic", "molten salt"],
            "ticker": "BWXT",
        }
    ),

    # -------------------------------------------------------------------------
    # DATA CENTER / AI INFRASTRUCTURE
    # -------------------------------------------------------------------------
    "transformer_production": SupplyChainBottleneck(
        bottleneck_id="bottleneck-transformer-production",
        name="Large Power Transformer Production",
        description="Large power transformers (LPTs) for data centers, grid, and industrial facilities.",
        bottleneck_type=BottleneckType.CAPACITY_CONSTRAINED,
        severity=SeverityLevel.HIGH,
        location="USA, Germany, Japan (limited domestic)",
        operators=["Forgent (FPS)", "Powell (POWL)", "Hitachi", "Siemens", "ABB"],
        vulnerability_detail="4-YEAR LEAD TIME - Domestic US manufacturing can't keep up with demand. Data center buildout bottlenecked.",
        downstream_impact="Data centers cannot energize without transformers. AI capex delayed.",
        affected_sectors=["data_centers", "grid", "semiconductors", "ai_compute"],
        mitigation="Forgent IPO to expand capacity, but lead times remain long",
        metadata={
            "lead_time": "4 years",
            "tickers": ["FPS", "POWL", "ETN"],
            "demand_driver": "AI data center buildout",
        }
    ),

    "liquid_cooling_capacity": SupplyChainBottleneck(
        bottleneck_id="bottleneck-liquid-cooling",
        name="Data Center Liquid Cooling Systems",
        description="Liquid cooling infrastructure for high-density AI compute racks (100kW+).",
        bottleneck_type=BottleneckType.CAPACITY_CONSTRAINED,
        severity=SeverityLevel.MEDIUM,
        location="USA (expanding rapidly)",
        operators=["Vertiv (VRT)", "Modine (MOD)", "Johnson Controls (JCI)"],
        vulnerability_detail="THERMAL WALL - AI racks at 100kW+ cannot use air cooling. Liquid cooling capacity scaling rapidly but still constrained.",
        downstream_impact="AI compute deployment limited by cooling availability. Can't run H100 clusters without cooling.",
        affected_sectors=["data_centers", "ai_compute"],
        mitigation="Vertiv $15B backlog, Modine pivot to data centers, rapid capacity expansion",
        metadata={
            "thermal_density": "100kW+ per rack",
            "tickers": ["VRT", "MOD", "JCI"],
            "h100_tdp": "700W per GPU",
        }
    ),

    # -------------------------------------------------------------------------
    # CRITICAL MINERALS
    # -------------------------------------------------------------------------
    "rare_earth_processing": SupplyChainBottleneck(
        bottleneck_id="bottleneck-rare-earth-processing",
        name="Rare Earth Processing",
        description="Separation and processing of rare earth elements into usable forms.",
        bottleneck_type=BottleneckType.GEOGRAPHIC_CONCENTRATION,
        severity=SeverityLevel.HIGH,
        location="China (60%+ of global processing)",
        operators=["China Northern Rare Earth", "MP Materials (US)"],
        vulnerability_detail="CHINA DOMINANCE - 60%+ of rare earth processing in China. MP Materials only US mine/processor.",
        downstream_impact="Defense, EVs, wind turbines, electronics depend on rare earths.",
        affected_sectors=["defense", "evs", "wind_energy", "electronics"],
        mitigation="MP Materials expansion, DoD stockpiling, allied supply chain development",
        metadata={
            "china_share": "60%+",
            "us_producer": "MP Materials (Mountain Pass, CA)",
            "ticker": "MP",
            "critical_minerals_act": True,
        }
    ),

    "neon_gas_supply": SupplyChainBottleneck(
        bottleneck_id="bottleneck-neon-gas",
        name="Semiconductor-Grade Neon Gas",
        description="Ultra-pure neon gas required for semiconductor lithography lasers.",
        bottleneck_type=BottleneckType.GEOPOLITICAL_RISK,
        severity=SeverityLevel.MEDIUM,
        location="Ukraine (historically 50%+ of global supply)",
        operators=["Iceblick (Ukraine)", "Ingas (Ukraine)", "Linde", "Air Liquide"],
        vulnerability_detail="UKRAINE SUPPLY RISK - Ukraine historically produced 50%+ of semiconductor-grade neon. Russia invasion disrupted supply.",
        downstream_impact="Lithography operations at risk without neon. Chip production could be impacted.",
        affected_sectors=["semiconductors"],
        mitigation="Western gas producers expanding capacity, recycling programs, alternative sources",
        metadata={
            "ukraine_share_historical": "50%+",
            "russia_invasion_impact": "2022 disruption",
            "recovery": "Diversification underway",
        }
    ),
}


class BottleneckRegistry:
    """
    Registry for tracking and querying supply chain bottlenecks.

    Provides methods to:
    - Query bottlenecks by sector, severity, type
    - Link bottlenecks to graph nodes
    - Generate risk reports
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path
        self._bottlenecks = SUPPLY_CHAIN_BOTTLENECKS

    def get_all(self) -> List[SupplyChainBottleneck]:
        """Get all registered bottlenecks."""
        return list(self._bottlenecks.values())

    def get_by_id(self, bottleneck_id: str) -> Optional[SupplyChainBottleneck]:
        """Get bottleneck by ID."""
        return self._bottlenecks.get(bottleneck_id)

    def get_by_sector(self, sector: str) -> List[SupplyChainBottleneck]:
        """Get all bottlenecks affecting a sector."""
        return [
            b for b in self._bottlenecks.values()
            if sector in b.affected_sectors
        ]

    def get_by_severity(self, severity: SeverityLevel) -> List[SupplyChainBottleneck]:
        """Get all bottlenecks of a given severity."""
        return [
            b for b in self._bottlenecks.values()
            if b.severity == severity
        ]

    def get_by_type(self, bottleneck_type: BottleneckType) -> List[SupplyChainBottleneck]:
        """Get all bottlenecks of a given type."""
        return [
            b for b in self._bottlenecks.values()
            if b.bottleneck_type == bottleneck_type
        ]

    def get_critical(self) -> List[SupplyChainBottleneck]:
        """Get all CRITICAL severity bottlenecks."""
        return self.get_by_severity(SeverityLevel.CRITICAL)

    def get_monopolies(self) -> List[SupplyChainBottleneck]:
        """Get all MONOPOLY type bottlenecks."""
        return self.get_by_type(BottleneckType.MONOPOLY)

    def get_single_sources(self) -> List[SupplyChainBottleneck]:
        """Get all SINGLE_SOURCE bottlenecks."""
        return self.get_by_type(BottleneckType.SINGLE_SOURCE)

    def get_operators_at_risk(self, bottleneck_id: str) -> List[str]:
        """Get list of operators/companies for a bottleneck."""
        bottleneck = self.get_by_id(bottleneck_id)
        if bottleneck:
            return bottleneck.operators
        return []

    def generate_risk_report(self) -> Dict[str, Any]:
        """Generate summary risk report."""
        all_bottlenecks = self.get_all()

        by_severity = {}
        for sev in SeverityLevel:
            by_severity[sev.value] = len(self.get_by_severity(sev))

        by_type = {}
        for bt in BottleneckType:
            by_type[bt.value] = len(self.get_by_type(bt))

        sectors_at_risk = {}
        for b in all_bottlenecks:
            for sector in b.affected_sectors:
                if sector not in sectors_at_risk:
                    sectors_at_risk[sector] = []
                sectors_at_risk[sector].append(b.bottleneck_id)

        return {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "total_bottlenecks": len(all_bottlenecks),
            "by_severity": by_severity,
            "by_type": by_type,
            "sectors_at_risk": sectors_at_risk,
            "critical_bottlenecks": [b.name for b in self.get_critical()],
            "monopolies": [b.name for b in self.get_monopolies()],
            "single_sources": [b.name for b in self.get_single_sources()],
        }

    def link_to_graph(self, db_path: str) -> int:
        """
        Create bottleneck nodes and edges in the FGIP graph.

        Returns:
            Number of nodes/edges created
        """
        import hashlib

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        created = 0

        for bottleneck in self.get_all():
            # Check if node exists
            existing = cursor.execute(
                "SELECT node_id FROM nodes WHERE node_id = ?",
                (bottleneck.bottleneck_id,)
            ).fetchone()

            if not existing:
                # Create bottleneck node
                data = bottleneck.to_dict()
                sha256 = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

                cursor.execute("""
                    INSERT INTO nodes (node_id, node_type, name, description, metadata, created_at, sha256)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    bottleneck.bottleneck_id,
                    "BOTTLENECK",
                    bottleneck.name,
                    bottleneck.description,
                    json.dumps(data),
                    datetime.utcnow().isoformat() + "Z",
                    sha256,
                ))
                created += 1
                print(f"  Created node: {bottleneck.bottleneck_id}")

        conn.commit()
        conn.close()
        return created


# =============================================================================
# CLI
# =============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description="FGIP Supply Chain Bottleneck Registry")
    parser.add_argument("--report", action="store_true", help="Generate risk report")
    parser.add_argument("--sector", type=str, help="Filter by sector")
    parser.add_argument("--critical", action="store_true", help="Show only CRITICAL")
    parser.add_argument("--link-to-graph", type=str, metavar="DB_PATH", help="Create bottleneck nodes in graph")
    args = parser.parse_args()

    registry = BottleneckRegistry()

    if args.link_to_graph:
        print("=" * 60)
        print("LINKING BOTTLENECKS TO GRAPH")
        print("=" * 60)
        created = registry.link_to_graph(args.link_to_graph)
        print(f"\nCreated {created} bottleneck nodes")
        return

    if args.report:
        print("=" * 60)
        print("SUPPLY CHAIN BOTTLENECK RISK REPORT")
        print("=" * 60)
        report = registry.generate_risk_report()
        print(json.dumps(report, indent=2))
        return

    # List bottlenecks
    if args.critical:
        bottlenecks = registry.get_critical()
        print(f"\n=== CRITICAL BOTTLENECKS ({len(bottlenecks)}) ===\n")
    elif args.sector:
        bottlenecks = registry.get_by_sector(args.sector)
        print(f"\n=== BOTTLENECKS FOR SECTOR: {args.sector} ({len(bottlenecks)}) ===\n")
    else:
        bottlenecks = registry.get_all()
        print(f"\n=== ALL BOTTLENECKS ({len(bottlenecks)}) ===\n")

    for b in bottlenecks:
        print(f"[{b.severity.value}] {b.name}")
        print(f"  Type: {b.bottleneck_type.value}")
        print(f"  Location: {b.location}")
        print(f"  Operators: {', '.join(b.operators)}")
        print(f"  Vulnerability: {b.vulnerability_detail}")
        print(f"  Sectors: {', '.join(b.affected_sectors)}")
        print()


if __name__ == "__main__":
    main()
