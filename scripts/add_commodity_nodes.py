#!/usr/bin/env python3
"""
Add Commodity Exposure Nodes to FGIP graph.

Creates commodity nodes with ticker mappings for upstream sector exposure:
- Uranium (CCJ, URA) - nuclear upstream
- Copper (FCX, COPX) - infrastructure/grid/EVs
- Rare Earths (MP, REMX) - defense/EVs/semiconductors
- Lithium (ALB, SQM) - EV batteries
- Steel (NUE, STLD) - reshoring/infrastructure
- Aluminum (AA) - defense/grid
- Nickel (VALE) - steel/batteries
- Cobalt - batteries
- Silicon/Neon - semiconductors

Investment signal: These commodities are LEADING indicators.
When a sector moves, the upstream commodities move first or in parallel.
"""

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path


# =============================================================================
# COMMODITY NODES
# =============================================================================

COMMODITY_NODES = [
    {
        "node_id": "commodity-uranium",
        "name": "Uranium Exposure",
        "node_type": "COMMODITY",
        "description": "Nuclear fuel commodity. Leading indicator for SMR/nuclear sector. Tickers: CCJ (Cameco), URA (ETF), UUUU (Energy Fuels), URG (Ur-Energy), NXE (NexGen), UEC (Uranium Energy Corp).",
        "aliases": ["Uranium", "U3O8", "Yellowcake"],
        "metadata": {
            "sector": "nuclear",
            "tickers": ["CCJ", "URA", "UUUU", "URG", "NXE", "UEC"],
            "upstream_of": ["nuclear_smr", "nuclear_utility"],
            "supply_sources": ["Kazakhstan", "Canada", "Australia", "Namibia"],
            "layer": "correction",
        }
    },
    {
        "node_id": "commodity-copper",
        "name": "Copper Exposure",
        "node_type": "COMMODITY",
        "description": "Industrial metal. 'Dr. Copper' - economic bellwether. Grid buildout, EVs, data centers, manufacturing. Tickers: FCX (Freeport-McMoRan), COPX (ETF), SCCO (Southern Copper), TECK.",
        "aliases": ["Copper", "Dr. Copper"],
        "metadata": {
            "sector": "infrastructure",
            "tickers": ["FCX", "COPX", "SCCO", "TECK"],
            "upstream_of": ["reshoring", "evs", "data_centers", "grid", "semiconductors"],
            "supply_sources": ["Chile", "Peru", "USA", "Congo"],
            "layer": "correction",
        }
    },
    {
        "node_id": "commodity-rare-earths",
        "name": "Rare Earths Exposure",
        "node_type": "COMMODITY",
        "description": "17 elements critical for defense, EVs, electronics. China controls 60% processing. National security risk. Tickers: MP (MP Materials - only US mine), REMX (ETF), UUUU (also processes REE).",
        "aliases": ["Rare Earth Elements", "REE", "Critical Minerals"],
        "metadata": {
            "sector": "critical_minerals",
            "tickers": ["MP", "REMX", "UUUU"],
            "upstream_of": ["defense", "evs", "semiconductors", "wind_energy"],
            "supply_risk": "china_dominant",
            "supply_sources": ["China", "USA (MP)", "Australia"],
            "layer": "correction",
        }
    },
    {
        "node_id": "commodity-lithium",
        "name": "Lithium Exposure",
        "node_type": "COMMODITY",
        "description": "Battery metal. Critical for EVs and energy storage. Price volatile on EV demand. Tickers: ALB (Albemarle), SQM, LTHM, LAC (Lithium Americas).",
        "aliases": ["Lithium", "White Gold"],
        "metadata": {
            "sector": "evs",
            "tickers": ["ALB", "SQM", "LTHM", "LAC"],
            "upstream_of": ["evs", "energy_storage", "grid_batteries"],
            "supply_sources": ["Australia", "Chile", "Argentina", "China"],
            "layer": "correction",
        }
    },
    {
        "node_id": "commodity-steel",
        "name": "Steel Exposure",
        "node_type": "COMMODITY",
        "description": "Foundation metal for infrastructure and manufacturing. Reshoring proxy. Domestic production critical. Tickers: NUE (Nucor - best positioned), STLD (Steel Dynamics), X (US Steel), CLF (Cleveland-Cliffs).",
        "aliases": ["Steel"],
        "metadata": {
            "sector": "metals",
            "tickers": ["NUE", "STLD", "X", "CLF"],
            "upstream_of": ["infrastructure", "reshoring", "defense", "construction"],
            "supply_sources": ["USA (domestic)", "Brazil", "Korea"],
            "layer": "correction",
        }
    },
    {
        "node_id": "commodity-aluminum",
        "name": "Aluminum Exposure",
        "node_type": "COMMODITY",
        "description": "Lightweight metal. Defense, transportation, packaging, grid (transmission lines). Energy-intensive to produce. Tickers: AA (Alcoa), CENX (Century Aluminum).",
        "aliases": ["Aluminum", "Aluminium"],
        "metadata": {
            "sector": "metals",
            "tickers": ["AA", "CENX"],
            "upstream_of": ["defense", "transportation", "grid", "packaging"],
            "supply_sources": ["USA", "Canada", "Iceland"],
            "layer": "correction",
        }
    },
    {
        "node_id": "commodity-nickel",
        "name": "Nickel Exposure",
        "node_type": "COMMODITY",
        "description": "Steel alloy and EV battery input. Stainless steel (60%), batteries (growing). Indonesia/Philippines dominate supply. Tickers: VALE, BHP have nickel exposure.",
        "aliases": ["Nickel"],
        "metadata": {
            "sector": "metals",
            "tickers": ["VALE", "BHP"],
            "upstream_of": ["steel", "evs", "batteries", "aerospace"],
            "supply_sources": ["Indonesia", "Philippines", "Russia", "Canada"],
            "layer": "correction",
        }
    },
    {
        "node_id": "commodity-cobalt",
        "name": "Cobalt Exposure",
        "node_type": "COMMODITY",
        "description": "Battery cathode material. DRC supplies 70% - ethical/supply chain concerns. Battery chemistry shifting away. Tickers: Limited pure-play exposure.",
        "aliases": ["Cobalt"],
        "metadata": {
            "sector": "batteries",
            "tickers": ["GLEN", "VALE"],  # Glencore (GLEN.L), Vale have exposure
            "upstream_of": ["evs", "batteries", "aerospace"],
            "supply_risk": "drc_concentration",
            "supply_sources": ["DRC", "Australia", "Philippines"],
            "layer": "correction",
        }
    },
    {
        "node_id": "commodity-silicon",
        "name": "Polysilicon Exposure",
        "node_type": "COMMODITY",
        "description": "Semiconductor and solar panel feedstock. China dominates solar-grade. Electronic-grade critical for chips. Tickers: WFG (Wacker Chemie), Limited US exposure.",
        "aliases": ["Silicon", "Polysilicon", "Silicon Wafers"],
        "metadata": {
            "sector": "semiconductors",
            "tickers": ["WFG"],  # Wacker Chemie
            "upstream_of": ["semiconductors", "solar"],
            "supply_risk": "china_solar_dominance",
            "supply_sources": ["China", "Germany", "USA", "Korea"],
            "layer": "correction",
        }
    },
    {
        "node_id": "commodity-natural-gas",
        "name": "Natural Gas Exposure",
        "node_type": "COMMODITY",
        "description": "Power generation and industrial feedstock. Data center power. US has abundant supply (export opportunity). Tickers: LNG (Cheniere), EQT, DVN.",
        "aliases": ["Natural Gas", "LNG"],
        "metadata": {
            "sector": "energy",
            "tickers": ["LNG", "EQT", "DVN", "AR"],
            "upstream_of": ["data_centers", "power_generation", "manufacturing", "petrochemicals"],
            "supply_sources": ["USA (domestic)", "Qatar", "Australia"],
            "layer": "correction",
        }
    },
    {
        "node_id": "commodity-graphite",
        "name": "Graphite Exposure",
        "node_type": "COMMODITY",
        "description": "Battery anode material. China dominates supply/processing. Critical mineral designation. Tickers: Limited pure-play (GRPH in development).",
        "aliases": ["Graphite", "Battery Graphite"],
        "metadata": {
            "sector": "batteries",
            "tickers": [],  # Very limited public exposure
            "upstream_of": ["evs", "batteries"],
            "supply_risk": "china_dominant",
            "supply_sources": ["China", "Mozambique", "Madagascar"],
            "layer": "correction",
        }
    },
    {
        "node_id": "commodity-palladium",
        "name": "Palladium/Platinum Exposure",
        "node_type": "COMMODITY",
        "description": "Catalytic converters, semiconductors, hydrogen fuel cells. Russia/South Africa supply concentration. Tickers: PALL (ETF), IMPUY (Impala), SBSW (Sibanye).",
        "aliases": ["Palladium", "Platinum", "PGMs"],
        "metadata": {
            "sector": "auto_catalysts",
            "tickers": ["PALL", "IMPUY", "SBSW"],
            "upstream_of": ["auto", "semiconductors", "hydrogen"],
            "supply_risk": "russia_south_africa",
            "supply_sources": ["South Africa", "Russia", "Zimbabwe"],
            "layer": "correction",
        }
    },
    {
        "node_id": "commodity-titanium",
        "name": "Titanium Exposure",
        "node_type": "COMMODITY",
        "description": "Aerospace and defense critical metal. Strong, lightweight. Russia/Ukraine historically important suppliers. Tickers: RTX, HWM (Howmet) have aerospace titanium exposure.",
        "aliases": ["Titanium", "Ti"],
        "metadata": {
            "sector": "aerospace",
            "tickers": ["RTX", "HWM"],
            "upstream_of": ["defense", "aerospace", "medical"],
            "supply_risk": "russia_ukraine_disruption",
            "supply_sources": ["USA", "Japan", "Russia", "Ukraine"],
            "layer": "correction",
        }
    },
]


# =============================================================================
# COMMODITY EDGES
# =============================================================================

COMMODITY_EDGES = [
    # Uranium -> Nuclear sector
    ("commodity-uranium", "nne", "SUPPLIES_TO", 0.85, "HYPOTHESIS", "Uranium required for SMR fuel"),
    ("commodity-uranium", "centrus-energy", "SUPPLIES_TO", 0.90, "INFERENCE", "Centrus processes uranium to HALEU"),
    ("commodity-uranium", "bwxt", "SUPPLIES_TO", 0.80, "HYPOTHESIS", "BWXT manufactures fuel from uranium"),

    # Copper -> Infrastructure/Grid
    ("commodity-copper", "smr-technology", "ENABLES", 0.70, "HYPOTHESIS", "SMRs require copper for electrical systems"),
    ("commodity-copper", "constellation-energy", "SUPPLIES_TO", 0.75, "HYPOTHESIS", "Utilities need copper for grid"),

    # Rare Earths -> Defense
    ("commodity-rare-earths", "mp-materials", "PRODUCED_BY", 0.95, "FACT", "MP Materials only US rare earth mine"),

    # Steel -> Infrastructure/Reshoring
    ("commodity-steel", "nucor", "PRODUCED_BY", 0.95, "FACT", "Nucor largest US steel producer"),
    ("commodity-steel", "steel-dynamics", "PRODUCED_BY", 0.95, "FACT", "Steel Dynamics US steel producer"),

    # Natural Gas -> Data Centers
    ("commodity-natural-gas", "data-centers", "POWERS", 0.80, "INFERENCE", "Natural gas powers many data center sites"),
]


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
        print(f"  WOULD ADD: {node['node_id']} ({node['node_type']})")
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

    print(f"  ADDED: {node['node_id']} ({node['node_type']})")
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
    parser = argparse.ArgumentParser(description="Add Commodity Exposure Nodes to FGIP")
    parser.add_argument("db_path", help="Path to FGIP database")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be added")
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}")
        return 1

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    print("=" * 60)
    print("FGIP COMMODITY EXPOSURE NODES")
    print("=" * 60)
    print("\nUpstream commodity exposure for sector moves")
    print("Investment signal: Commodities are leading indicators")

    nodes_added = 0
    edges_added = 0

    # Add commodity nodes
    print("\n[COMMODITY NODES]")
    for node in COMMODITY_NODES:
        if add_node(conn, node, args.dry_run):
            nodes_added += 1

    if not args.dry_run:
        conn.commit()

    # Add edges
    print("\n[COMMODITY EDGES]")
    for edge in COMMODITY_EDGES:
        if add_edge(conn, edge, args.dry_run):
            edges_added += 1

    if not args.dry_run:
        conn.commit()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Nodes added: {nodes_added}")
    print(f"Edges added: {edges_added}")

    if args.dry_run:
        print("\n(DRY RUN - no changes made)")
    else:
        print("\nCommodity nodes loaded:")
        print("  Energy: Uranium, Natural Gas")
        print("  Industrial Metals: Copper, Steel, Aluminum, Nickel")
        print("  Critical Minerals: Rare Earths, Lithium, Cobalt, Graphite")
        print("  Specialty: Silicon, Palladium/Platinum, Titanium")
        print("\nTicker reference:")
        for node in COMMODITY_NODES:
            tickers = node.get("metadata", {}).get("tickers", [])
            if tickers:
                print(f"  {node['name']}: {', '.join(tickers)}")

    conn.close()
    return 0


if __name__ == "__main__":
    exit(main())
