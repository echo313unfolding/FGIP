#!/usr/bin/env python3
"""
Add Infrastructure Supply Chain Company Nodes to FGIP graph.

The "picks and shovels" layer: companies that sit between committed capex
and physical reality. Every $100B fab/data center commitment MUST flow through:

1. ELECTRICAL POWER: Transformers, switchgear, power distribution
   - 4-year lead times on large transformers
   - FPS, POWL, VRT, ETN, NVT

2. THERMAL MANAGEMENT: Cooling systems for AI/data centers
   - 100kW/rack requires liquid cooling
   - MOD, VRT, JCI

3. ADVANCED PACKAGING: Backend semiconductor processing
   - Only US-based advanced packaging capacity
   - AMKR, ASX

4. SPECIALTY MATERIALS: Filtration, purification, industrial gases
   - Ultra-pure chemicals, 15-20yr supply contracts
   - ENTG, LIN, APD

Investment signal: These are TOLL BRIDGES, not speculative bets.
The capital flow is LOCKED IN by $500B+ committed capex.
"""

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path


# =============================================================================
# INFRASTRUCTURE COMPANY NODES
# =============================================================================

INFRASTRUCTURE_COMPANIES = [
    # -------------------------------------------------------------------------
    # ELECTRICAL POWER EQUIPMENT
    # -------------------------------------------------------------------------
    {
        "node_id": "company-forgent",
        "name": "Forgent Power Solutions",
        "node_type": "COMPANY",
        "description": "Electrical equipment for data centers and energy developers. Transformers, switchgears, controls. IPO Feb 2026. $1B+ backlog exceeds full FY2025 revenue.",
        "aliases": ["Forgent", "FPS"],
        "metadata": {
            "ticker": "FPS",
            "sector": "electrical_power",
            "sectors": ["electrical_power", "data_center_infrastructure"],
            "market_cap_approx": "8B",
            "backlog": "1.03B",
            "revenue_growth_yoy": "56%",
            "bottleneck_role": "Transformers and switchgear - 4yr lead times",
            "thesis_relevance": "Every data center needs their equipment before it can operate",
            "ipo_date": "2026-02-05",
            "layer": "correction",
        }
    },
    {
        "node_id": "company-powell",
        "name": "Powell Industries",
        "node_type": "COMPANY",
        "description": "Custom-engineered electrical distribution equipment. Markets: oil/gas, petrochemical, utilities, data centers. Small-cap, high-beta industrial.",
        "aliases": ["Powell", "POWL"],
        "metadata": {
            "ticker": "POWL",
            "sector": "electrical_power",
            "sectors": ["electrical_power", "energy_infrastructure"],
            "market_cap_approx": "3B",
            "bottleneck_role": "Custom electrical distribution - specialized manufacturing",
            "thesis_relevance": "Competitor to Forgent, pure-play electrical equipment",
            "layer": "correction",
        }
    },
    {
        "node_id": "company-vertiv",
        "name": "Vertiv Holdings",
        "node_type": "COMPANY",
        "description": "Critical digital infrastructure: power, cooling, IT management. Gold standard in liquid cooling for AI data centers. $15B backlog, book-to-bill 2.9.",
        "aliases": ["Vertiv", "VRT"],
        "metadata": {
            "ticker": "VRT",
            "sector": "electrical_power",
            "sectors": ["electrical_power", "thermal_management", "data_center_infrastructure"],
            "market_cap_approx": "45B",
            "backlog": "15B",
            "book_to_bill": "2.9",
            "organic_orders_growth_yoy": "252%",
            "bottleneck_role": "Power AND cooling - dual exposure to data center build",
            "thesis_relevance": "Liquid cooling leader as AI racks hit 100kW+",
            "layer": "correction",
        }
    },
    {
        "node_id": "company-eaton",
        "name": "Eaton Corporation",
        "node_type": "COMPANY",
        "description": "Diversified power management. Electrical backlog $13.2B, Q4 data center orders +40%. Large-cap industrial with data center exposure.",
        "aliases": ["Eaton", "ETN"],
        "metadata": {
            "ticker": "ETN",
            "sector": "electrical_power",
            "sectors": ["electrical_power", "grid_infrastructure"],
            "market_cap_approx": "140B",
            "electrical_backlog": "13.2B",
            "data_center_orders_growth_yoy": "40%",
            "bottleneck_role": "Large-scale power distribution infrastructure",
            "thesis_relevance": "Diversified but significant data center/reshoring exposure",
            "layer": "correction",
        }
    },
    {
        "node_id": "company-nvent",
        "name": "nVent Electric",
        "node_type": "COMPANY",
        "description": "Electrical connection and protection solutions. Enclosures, thermal management, electrical connections for industrial and infrastructure.",
        "aliases": ["nVent", "NVT"],
        "metadata": {
            "ticker": "NVT",
            "sector": "electrical_power",
            "sectors": ["electrical_power", "industrial_infrastructure"],
            "market_cap_approx": "12B",
            "bottleneck_role": "Electrical enclosures and connections",
            "thesis_relevance": "Critical components for electrical infrastructure",
            "layer": "correction",
        }
    },

    # -------------------------------------------------------------------------
    # THERMAL MANAGEMENT / COOLING
    # -------------------------------------------------------------------------
    {
        "node_id": "company-modine",
        "name": "Modine Manufacturing",
        "node_type": "COMPANY",
        "description": "Thermal management solutions. Pivoted from truck radiators to data center cooling. Data center revenue to exceed $2B by FY2028. 119% DC revenue growth vs Vertiv 29%.",
        "aliases": ["Modine", "MOD"],
        "metadata": {
            "ticker": "MOD",
            "sector": "thermal_management",
            "sectors": ["thermal_management", "data_center_infrastructure"],
            "market_cap_approx": "12B",
            "data_center_revenue_growth": "119%",
            "data_center_revenue_target_fy28": "2B",
            "bottleneck_role": "Liquid cooling systems - thermal wall at 100kW/rack",
            "thesis_relevance": "No cooling = no AI. Every H100 generates 700W",
            "5yr_return": "1000%+",
            "layer": "correction",
        }
    },
    {
        "node_id": "company-johnson-controls",
        "name": "Johnson Controls International",
        "node_type": "COMPANY",
        "description": "Building automation and HVAC. Data center cooling solutions. Large-cap diversified with infrastructure exposure.",
        "aliases": ["Johnson Controls", "JCI"],
        "metadata": {
            "ticker": "JCI",
            "sector": "thermal_management",
            "sectors": ["thermal_management", "building_automation"],
            "market_cap_approx": "50B",
            "bottleneck_role": "Large-scale HVAC and building systems",
            "thesis_relevance": "Data center and industrial cooling",
            "layer": "correction",
        }
    },

    # -------------------------------------------------------------------------
    # ADVANCED PACKAGING
    # -------------------------------------------------------------------------
    {
        "node_id": "company-amkor",
        "name": "Amkor Technology",
        "node_type": "COMPANY",
        "description": "Semiconductor packaging and test services. Breaking ground on $7B Arizona advanced packaging campus - ONLY large-scale US advanced packaging. Apple and Nvidia as lead customers.",
        "aliases": ["Amkor", "AMKR"],
        "metadata": {
            "ticker": "AMKR",
            "sector": "advanced_packaging",
            "sectors": ["advanced_packaging", "semiconductors"],
            "market_cap_approx": "12B",
            "arizona_investment": "7B",
            "chips_funding": "900M",
            "key_customers": ["Apple", "Nvidia"],
            "bottleneck_role": "ONLY US advanced packaging - wafers useless without packaging",
            "thesis_relevance": "Critical gap in US semiconductor supply chain",
            "production_start": "2028",
            "layer": "correction",
        }
    },
    {
        "node_id": "company-ase",
        "name": "ASE Technology Holding",
        "node_type": "COMPANY",
        "description": "World's largest OSAT (outsourced semiconductor assembly and test). Taiwan-based. Competitor to Amkor.",
        "aliases": ["ASE", "ASX"],
        "metadata": {
            "ticker": "ASX",
            "sector": "advanced_packaging",
            "sectors": ["advanced_packaging", "semiconductors"],
            "market_cap_approx": "20B",
            "bottleneck_role": "Global advanced packaging capacity",
            "thesis_relevance": "Taiwan concentration risk vs Amkor US expansion",
            "headquarters": "Taiwan",
            "layer": "correction",
        }
    },

    # -------------------------------------------------------------------------
    # SPECIALTY MATERIALS / INDUSTRIAL GASES
    # -------------------------------------------------------------------------
    {
        "node_id": "company-entegris",
        "name": "Entegris",
        "node_type": "COMPANY",
        "description": "Filtration, purification, contamination control for semiconductor fabs. If a SINGLE particle lands on a wafer, the chip is dead. $1.4B US investment committed.",
        "aliases": ["Entegris", "ENTG"],
        "metadata": {
            "ticker": "ENTG",
            "sector": "specialty_materials",
            "sectors": ["specialty_materials", "semiconductors"],
            "market_cap_approx": "22B",
            "us_investment": "1.4B",
            "bottleneck_role": "Filtration and purification - razor blades model",
            "thesis_relevance": "Consumables for every wafer run. Recurring revenue.",
            "colorado_facility": "operational",
            "layer": "correction",
        }
    },
    {
        "node_id": "company-linde",
        "name": "Linde plc",
        "node_type": "COMPANY",
        "description": "World's largest industrial gas company. Nitrogen, argon, hydrogen for semiconductor fabs. 15-20 year supply contracts - build air separation unit, collect rent for decades.",
        "aliases": ["Linde", "LIN"],
        "metadata": {
            "ticker": "LIN",
            "sector": "industrial_gases",
            "sectors": ["industrial_gases", "semiconductors", "energy"],
            "market_cap_approx": "220B",
            "contract_length": "15-20 years",
            "bottleneck_role": "Industrial gases - every fab needs on-site production",
            "thesis_relevance": "Locked-in revenue once facility built",
            "layer": "correction",
        }
    },
    {
        "node_id": "company-air-products",
        "name": "Air Products and Chemicals",
        "node_type": "COMPANY",
        "description": "Industrial gases and hydrogen infrastructure. Nitrogen, hydrogen, argon for semiconductor fabs. Also major hydrogen energy player.",
        "aliases": ["Air Products", "APD"],
        "metadata": {
            "ticker": "APD",
            "sector": "industrial_gases",
            "sectors": ["industrial_gases", "hydrogen", "semiconductors"],
            "market_cap_approx": "70B",
            "bottleneck_role": "Industrial gases for fab operations",
            "thesis_relevance": "Both fab supply and hydrogen energy transition",
            "layer": "correction",
        }
    },
    {
        "node_id": "company-dupont",
        "name": "DuPont de Nemours",
        "node_type": "COMPANY",
        "description": "Specialty materials including semiconductor-grade chemicals, photoresists, and electronic materials division.",
        "aliases": ["DuPont", "DD"],
        "metadata": {
            "ticker": "DD",
            "sector": "specialty_materials",
            "sectors": ["specialty_materials", "semiconductors"],
            "market_cap_approx": "35B",
            "bottleneck_role": "Semiconductor-grade specialty chemicals",
            "thesis_relevance": "Materials supplier to fab buildout",
            "layer": "correction",
        }
    },

    # -------------------------------------------------------------------------
    # SEMICONDUCTOR EQUIPMENT (for completeness)
    # -------------------------------------------------------------------------
    {
        "node_id": "company-asml",
        "name": "ASML Holding",
        "node_type": "COMPANY",
        "description": "MONOPOLY on EUV lithography machines. $380M per machine, 2-year backlog. There is literally NO alternative for sub-5nm chip production.",
        "aliases": ["ASML"],
        "metadata": {
            "ticker": "ASML",
            "sector": "semiconductor_equipment",
            "sectors": ["semiconductor_equipment"],
            "market_cap_approx": "350B",
            "machine_price": "380M",
            "backlog": "2+ years",
            "bottleneck_role": "MONOPOLY - EUV lithography required for advanced nodes",
            "thesis_relevance": "Gatekeeper of advanced chip production",
            "headquarters": "Netherlands",
            "layer": "correction",
        }
    },
    {
        "node_id": "company-applied-materials",
        "name": "Applied Materials",
        "node_type": "COMPANY",
        "description": "Semiconductor equipment: deposition, etch, inspection. Critical for fab buildout.",
        "aliases": ["Applied Materials", "AMAT"],
        "metadata": {
            "ticker": "AMAT",
            "sector": "semiconductor_equipment",
            "sectors": ["semiconductor_equipment"],
            "market_cap_approx": "160B",
            "bottleneck_role": "Deposition and etch equipment",
            "thesis_relevance": "Required for every new fab",
            "layer": "correction",
        }
    },
    {
        "node_id": "company-lam-research",
        "name": "Lam Research",
        "node_type": "COMPANY",
        "description": "Semiconductor equipment: etch and deposition systems. Major supplier to leading fabs.",
        "aliases": ["Lam Research", "LRCX"],
        "metadata": {
            "ticker": "LRCX",
            "sector": "semiconductor_equipment",
            "sectors": ["semiconductor_equipment"],
            "market_cap_approx": "110B",
            "bottleneck_role": "Etch and deposition systems",
            "thesis_relevance": "Required for advanced chip manufacturing",
            "layer": "correction",
        }
    },
    {
        "node_id": "company-kla",
        "name": "KLA Corporation",
        "node_type": "COMPANY",
        "description": "Process control and inspection equipment for semiconductor manufacturing. Quality assurance for chip production.",
        "aliases": ["KLA", "KLAC"],
        "metadata": {
            "ticker": "KLAC",
            "sector": "semiconductor_equipment",
            "sectors": ["semiconductor_equipment"],
            "market_cap_approx": "100B",
            "bottleneck_role": "Process control and inspection",
            "thesis_relevance": "Quality assurance layer for fab production",
            "layer": "correction",
        }
    },
]


# =============================================================================
# SUPPLY CHAIN EDGES
# =============================================================================

INFRASTRUCTURE_EDGES = [
    # -------------------------------------------------------------------------
    # CAPEX COMMITMENTS → SUPPLIERS
    # -------------------------------------------------------------------------

    # TSMC Arizona ($65B commitment) → Suppliers
    ("tsmc-arizona", "company-amkor", "DEPENDS_ON", 0.90, "INFERENCE",
     "Advanced packaging required for Arizona fab output"),
    ("tsmc-arizona", "company-linde", "DEPENDS_ON", 0.85, "INFERENCE",
     "Industrial gases for fab operations"),
    ("tsmc-arizona", "company-entegris", "DEPENDS_ON", 0.85, "INFERENCE",
     "Filtration and purification for cleanroom"),
    ("tsmc-arizona", "company-asml", "DEPENDS_ON", 0.95, "FACT",
     "EUV machines required for advanced nodes"),

    # Intel Ohio ($100B commitment) → Suppliers
    ("intel-ohio", "company-vertiv", "DEPENDS_ON", 0.80, "INFERENCE",
     "Power and cooling infrastructure"),
    ("intel-ohio", "company-linde", "DEPENDS_ON", 0.85, "INFERENCE",
     "Industrial gases for fab operations"),
    ("intel-ohio", "company-applied-materials", "DEPENDS_ON", 0.90, "INFERENCE",
     "Deposition and etch equipment"),

    # Hyperscale data center buildout → Electrical/Cooling
    ("hyperscale-capex", "company-forgent", "DEPENDS_ON", 0.85, "INFERENCE",
     "Transformers and switchgear for data centers"),
    ("hyperscale-capex", "company-modine", "DEPENDS_ON", 0.80, "INFERENCE",
     "Liquid cooling systems for AI racks"),
    ("hyperscale-capex", "company-vertiv", "DEPENDS_ON", 0.85, "INFERENCE",
     "Power and thermal management"),
    ("hyperscale-capex", "company-eaton", "DEPENDS_ON", 0.80, "INFERENCE",
     "Power distribution infrastructure"),

    # -------------------------------------------------------------------------
    # COMPANY → COMMODITY RELATIONSHIPS
    # -------------------------------------------------------------------------

    # Electrical equipment → Copper
    ("company-forgent", "commodity-copper", "CONSUMES", 0.90, "INFERENCE",
     "Copper for transformers and electrical equipment"),
    ("company-powell", "commodity-copper", "CONSUMES", 0.90, "INFERENCE",
     "Copper for electrical distribution equipment"),
    ("company-eaton", "commodity-copper", "CONSUMES", 0.85, "INFERENCE",
     "Copper for power distribution systems"),

    # Cooling → Aluminum
    ("company-modine", "commodity-aluminum", "CONSUMES", 0.85, "INFERENCE",
     "Aluminum for heat exchangers and cooling systems"),
    ("company-vertiv", "commodity-aluminum", "CONSUMES", 0.80, "INFERENCE",
     "Aluminum for cooling infrastructure"),

    # Semiconductor → Silicon
    ("company-amkor", "commodity-silicon", "DEPENDS_ON", 0.90, "INFERENCE",
     "Silicon wafers for packaging operations"),
    ("company-entegris", "commodity-silicon", "ENABLES", 0.85, "INFERENCE",
     "Purification enables silicon wafer production"),

    # -------------------------------------------------------------------------
    # SECTOR BOTTLENECK RELATIONSHIPS
    # -------------------------------------------------------------------------

    ("company-amkor", "sector-semiconductors", "BOTTLENECK_FOR", 0.90, "INFERENCE",
     "Only large-scale US advanced packaging facility"),
    ("company-asml", "sector-semiconductors", "BOTTLENECK_FOR", 0.95, "FACT",
     "Monopoly on EUV lithography - no alternative exists"),
    ("company-forgent", "sector-data-centers", "BOTTLENECK_FOR", 0.80, "INFERENCE",
     "4-year transformer lead times constrain buildout"),
    ("company-linde", "sector-semiconductors", "BOTTLENECK_FOR", 0.85, "INFERENCE",
     "Industrial gas supply required for fab operations"),
]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def compute_sha256(data: dict) -> str:
    """Compute SHA256 hash of node data."""
    content = json.dumps(data, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()


def add_node(conn: sqlite3.Connection, node: dict, dry_run: bool = False) -> bool:
    """Add a node to the graph if it doesn't exist."""
    cursor = conn.cursor()

    existing = cursor.execute(
        "SELECT node_id FROM nodes WHERE node_id = ?",
        (node["node_id"],)
    ).fetchone()

    if existing:
        print(f"  SKIP: {node['node_id']} (already exists)")
        return False

    sha256 = compute_sha256(node)

    if dry_run:
        print(f"  WOULD ADD: {node['node_id']} ({node['node_type']}) - {node['metadata'].get('ticker', 'N/A')}")
        return True

    cursor.execute("""
        INSERT INTO nodes (node_id, node_type, name, aliases, description, metadata, created_at, sha256)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        node["node_id"],
        node["node_type"],
        node["name"],
        json.dumps(node.get("aliases", [])),
        node.get("description"),
        json.dumps(node.get("metadata", {})),
        datetime.utcnow().isoformat() + "Z",
        sha256
    ))

    print(f"  ADDED: {node['node_id']} ({node['metadata'].get('ticker', 'N/A')})")
    return True


def add_edge(conn: sqlite3.Connection, edge: tuple, dry_run: bool = False) -> bool:
    """Add an edge to the graph."""
    from_id, to_id, edge_type, confidence, tier, notes = edge
    cursor = conn.cursor()

    # Check nodes exist
    from_exists = cursor.execute("SELECT node_id FROM nodes WHERE node_id = ?", (from_id,)).fetchone()
    to_exists = cursor.execute("SELECT node_id FROM nodes WHERE node_id = ?", (to_id,)).fetchone()

    if not from_exists:
        print(f"  SKIP EDGE: {from_id} -> {to_id} (from_node missing)")
        return False
    if not to_exists:
        print(f"  SKIP EDGE: {from_id} -> {to_id} (to_node missing)")
        return False

    existing = cursor.execute("""
        SELECT edge_id FROM edges WHERE from_node_id = ? AND to_node_id = ? AND edge_type = ?
    """, (from_id, to_id, edge_type)).fetchone()

    if existing:
        print(f"  SKIP EDGE: {from_id} -[{edge_type}]-> {to_id} (exists)")
        return False

    if dry_run:
        print(f"  WOULD ADD EDGE: {from_id} -[{edge_type}]-> {to_id}")
        return True

    sha256 = compute_sha256({"from": from_id, "to": to_id, "type": edge_type})

    cursor.execute("""
        INSERT INTO edges (edge_id, from_node_id, to_node_id, edge_type, confidence, assertion_level, notes, created_at, sha256)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        f"edge-{from_id}-{to_id}-{edge_type}".lower(),
        from_id, to_id, edge_type, confidence, tier, notes,
        datetime.utcnow().isoformat() + "Z", sha256
    ))

    print(f"  ADDED EDGE: {from_id} -[{edge_type}]-> {to_id}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Add Infrastructure Supply Chain Companies to FGIP")
    parser.add_argument("db_path", help="Path to FGIP database")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be added")
    parser.add_argument("--edges-only", action="store_true", help="Only add edges (nodes already exist)")
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}")
        return 1

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    print("=" * 70)
    print("FGIP INFRASTRUCTURE SUPPLY CHAIN COMPANIES")
    print("=" * 70)
    print("\nThe 'picks and shovels' layer: toll bridges between capex and reality")
    print("$500B+ committed AI/fab capex MUST flow through these companies")

    nodes_added = 0
    edges_added = 0

    # Add infrastructure company nodes
    if not args.edges_only:
        print("\n[INFRASTRUCTURE COMPANIES]")
        print("-" * 50)

        sectors = {}
        for node in INFRASTRUCTURE_COMPANIES:
            sector = node["metadata"].get("sector", "unknown")
            if sector not in sectors:
                sectors[sector] = []
            sectors[sector].append(node)

        for sector, nodes in sorted(sectors.items()):
            print(f"\n  {sector.upper().replace('_', ' ')}:")
            for node in nodes:
                if add_node(conn, node, args.dry_run):
                    nodes_added += 1

    if not args.dry_run and not args.edges_only:
        conn.commit()

    # Add edges
    print("\n[SUPPLY CHAIN EDGES]")
    print("-" * 50)
    for edge in INFRASTRUCTURE_EDGES:
        if add_edge(conn, edge, args.dry_run):
            edges_added += 1

    if not args.dry_run:
        conn.commit()

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Nodes added: {nodes_added}")
    print(f"Edges added: {edges_added}")

    if args.dry_run:
        print("\n(DRY RUN - no changes made)")
    else:
        print("\nInfrastructure layer loaded:")
        print("  Electrical Power: FPS, POWL, VRT, ETN, NVT")
        print("  Thermal Management: MOD, VRT, JCI")
        print("  Advanced Packaging: AMKR, ASX")
        print("  Specialty Materials: ENTG, LIN, APD, DD")
        print("  Semiconductor Equipment: ASML, AMAT, LRCX, KLAC")
        print("\nTicker reference (picks & shovels):")
        for node in INFRASTRUCTURE_COMPANIES:
            ticker = node.get("metadata", {}).get("ticker", "")
            sector = node.get("metadata", {}).get("sector", "")
            bottleneck = node.get("metadata", {}).get("bottleneck_role", "")[:50]
            if ticker:
                print(f"  {ticker:6} | {sector:20} | {bottleneck}")

    conn.close()
    return 0


if __name__ == "__main__":
    exit(main())
