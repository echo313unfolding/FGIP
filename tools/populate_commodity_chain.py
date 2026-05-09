#!/usr/bin/env python3
"""
FGIP Commodity Supply Chain — Full downstream from AI to atoms.

The thesis: You can't have NVIDIA/OpenAI without the physical supply chain.
Every layer of the tech stack bottlenecks on commodities that take 5-15 years
to bring new supply online. The market prices the top of the stack (NVDA, META)
but underprices the foundation (gas, uranium, copper, silver, rare earths, coal).

This script maps the COMPLETE supply chain:

LAYER 0 — Commodities (atoms)
  Natural gas, uranium, copper, silver, coal, rare earths, lithium, helium, potash

LAYER 1 — Extraction (mines, wells, enrichment)
  E&P companies, miners, enrichment facilities

LAYER 2 — Transport/Processing (midstream, refining)
  Pipelines, gathering, processing, smelting

LAYER 3 — Conversion (power generation, manufacturing)
  Gas turbines, nuclear plants, coal plants, semiconductor fabs

LAYER 4 — Infrastructure (data centers, grid)
  Utility service, data center campuses

LAYER 5 — Platform (hyperscalers, AI)
  Cloud, AI training, inference

Each layer DEPENDS_ON the layer below it. Constraints at Layer 0-1
create the biggest alpha because they're furthest from the market's attention.
"""

import json
import sqlite3
import hashlib
import time
from datetime import datetime

DB_PATH = "/home/voidstr3m33/fgip-engine/fgip.db"


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def ensure_node(conn, node_id, name, node_type, description="", aliases=None, metadata=None):
    existing = conn.execute("SELECT node_id FROM nodes WHERE node_id = ?", (node_id,)).fetchone()
    aliases_json = json.dumps(aliases or [])
    metadata_json = json.dumps(metadata or {})
    if existing:
        conn.execute("UPDATE nodes SET name=?, description=?, aliases=?, metadata=? WHERE node_id=?",
                     (name, description, aliases_json, metadata_json, node_id))
    else:
        conn.execute("""INSERT INTO nodes (node_id, node_type, name, description, aliases, metadata, created_at, sha256)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (node_id, node_type, name, description, aliases_json, metadata_json,
             datetime.utcnow().isoformat() + "Z", sha256(f"{node_id}-{name}")))


def ensure_edge(conn, edge_id, edge_type, from_id, to_id, confidence=0.8, notes="", source_url=""):
    existing = conn.execute("SELECT edge_id FROM edges WHERE edge_id = ?", (edge_id,)).fetchone()
    if not existing:
        conn.execute("""INSERT INTO edges (edge_id, edge_type, from_node_id, to_node_id,
                        confidence, notes, source_url, assertion_level, date_documented, created_at, sha256)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (edge_id, edge_type, from_id, to_id, confidence, notes, source_url,
             "CONFIRMED", datetime.utcnow().strftime("%Y-%m-%d"),
             datetime.utcnow().isoformat() + "Z", sha256(f"{edge_id}-{from_id}-{to_id}")))
        return True
    return False


def populate_commodities(conn):
    """Layer 0 — Physical commodities. The atoms everything is built on."""
    print("\n=== LAYER 0: COMMODITIES ===")
    commodities = [
        ("commodity-natural-gas", "Natural Gas (Henry Hub)", "COMMODITY", ["NG", "NATGAS"],
         {"unit": "MMBtu", "price_2026": 4.00, "source": "EIA STEO Apr 2026"},
         "Primary fuel for power generation. 55% of new generation capacity entering queue in 2025. "
         "Data centers driving 8 Bcf/d incremental demand by 2030. Also feedstock for nitrogen fertilizer."),

        ("commodity-uranium", "Uranium (U3O8)", "COMMODITY", ["URA"],
         {"unit": "lb", "price_2026": 100, "deficit_mlb": 35, "source": "Cameco/WNA"},
         "30-40M lb annual supply deficit. Primary mine production below reactor demand (179M lb). "
         "HALEU needed for SMRs. US produces <1% of global enrichment. Russian import restrictions 2028."),

        ("commodity-copper", "Copper", "COMMODITY", ["HG", "COPPER"],
         {"unit": "lb", "price_2026": 5.61, "record_high": 6.00, "source": "COMEX"},
         "27 tons per MW of data center capacity. Record $6/lb Jan 2026. 10+ year mine development cycle. "
         "No substitute for electrical wiring. Grid + EV + DC = structural deficit."),

        ("commodity-silver", "Silver", "COMMODITY", ["SI", "SILVER"],
         {"unit": "oz", "deficit_year": 6, "source": "Silver Institute"},
         "6th consecutive year of structural deficit. Mexico mining moratorium. China export controls. "
         "Solar paste (photovoltaic) driving industrial demand. No copper paste substitute at scale yet."),

        ("commodity-coal", "Thermal Coal", "COMMODITY", ["COAL"],
         {"unit": "ton", "source": "EIA"},
         "40% of planned coal retirements delayed due to data center demand. DOE issued 8 emergency "
         "declarations in 2025 to stop coal unit retirements. Appalachian proximity to data center markets."),

        ("commodity-rare-earths", "Rare Earth Elements", "COMMODITY", ["REE"],
         {"unit": "kg", "china_share_pct": 70, "source": "USGS"},
         "China controls 70% of mining, 90% of processing. Export curbs 2025 targeting semiconductor supply chain. "
         "Critical for chip manufacturing, permanent magnets, defense. No near-term substitutes."),

        ("commodity-lithium", "Lithium", "COMMODITY", ["LI"],
         {"unit": "ton", "source": "Benchmark Minerals"},
         "Battery storage for grid + data center backup. Prices crashed 2023-24 but structural demand rising. "
         "4-hour battery storage increasingly paired with solar for data center power."),

        ("commodity-helium", "Helium", "COMMODITY", ["HE"],
         {"unit": "mcf", "source": "CGA"},
         "Critical for semiconductor fab cooling. Qatar 33% of global supply — 2026 strikes doubled spot price. "
         "Taiwan/Korea fabs rationing. No substitute for chip manufacturing."),

        ("commodity-potash", "Potash (MOP)", "COMMODITY", ["POTASH"],
         {"unit": "ton", "source": "World Bank Commodity Markets"},
         "Fertilizer input. MOP +19% in 2025. Trade policy risks (Belarus/Russia sanctions). "
         "Food security linkage to energy security — gas feeds nitrogen, potash feeds yield."),

        ("commodity-nitrogen-fertilizer", "Nitrogen Fertilizer (Urea)", "COMMODITY", ["UREA"],
         {"unit": "ton", "source": "DTN/World Bank"},
         "Direct function of natural gas price. Urea +30% in 2025. Gas at $4/MMBtu (2026 EIA) "
         "means elevated nitrogen costs. Food inflation channel."),
    ]

    count = 0
    for node_id, name, ntype, aliases, metadata, desc in commodities:
        ensure_node(conn, node_id, name, ntype, desc, aliases, metadata)
        count += 1
    conn.commit()
    print(f"  {count} commodity nodes")


def populate_extraction_companies(conn):
    """Layer 1 — Extraction companies (new ones not already in graph)."""
    print("\n=== LAYER 1: EXTRACTION COMPANIES ===")
    companies = [
        # Uranium
        ("cameco", "Cameco Corp", "COMPANY", ["CCJ"], {"sector": "uranium", "ticker": "CCJ"},
         "Largest Western uranium producer. McArthur River/Key Lake restart. 18M lb production target."),
        ("energy-fuels", "Energy Fuels Inc", "COMPANY", ["UUUU"], {"sector": "uranium", "ticker": "UUUU"},
         "Only US conventional processing mill. 620K-880K lb deliveries in 2026. Rare earth diversification."),
        ("uranium-energy", "Uranium Energy Corp", "COMPANY", ["UEC"], {"sector": "uranium", "ticker": "UEC"},
         "US ISR uranium producer. South Texas + Wyoming. Production ramp underway."),
        ("denison-mines", "Denison Mines Corp", "COMPANY", ["DNN"], {"sector": "uranium", "ticker": "DNN"},
         "Wheeler River project (Athabasca Basin). ISR method. Pre-development."),
        ("encore-energy", "enCore Energy Corp", "COMPANY", ["EU"], {"sector": "uranium", "ticker": "EU"},
         "Low-cost ISR production. Expansion capacity. US-based supply security."),

        # Coal (data center bridge fuel)
        ("core-natural-resources", "Core Natural Resources", "COMPANY", ["CNR"], {"sector": "coal", "ticker": "CNR"},
         "CONSOL + Arch merged. $5.2B combined. Appalachian proximity to data center markets. "
         "Coal retirements delayed by DOE emergency declarations."),
        ("peabody-energy", "Peabody Energy Corp", "COMPANY", ["BTU"], {"sector": "coal", "ticker": "BTU"},
         "Largest global pure-play coal. 25 countries. PRB + Appalachian. Data center demand extending mine life."),
        ("alliance-resource", "Alliance Resource Partners LP", "COMPANY", ["ARLP"], {"sector": "coal", "ticker": "ARLP"},
         "Central Appalachian coal. Proximity to PJM data center load. Benefits from delayed retirements."),

        # Fertilizer (gas → food chain)
        ("cf-industries", "CF Industries Holdings", "COMPANY", ["CF"], {"sector": "fertilizer", "ticker": "CF"},
         "Largest US nitrogen fertilizer producer. Gas feedstock = direct gas price exposure. Urea, UAN, ammonia."),
        ("nutrien", "Nutrien Ltd", "COMPANY", ["NTR"], {"sector": "fertilizer", "ticker": "NTR"},
         "Largest global fertilizer company. Potash + nitrogen + phosphate. Retail distribution."),
        ("mosaic-company", "The Mosaic Company", "COMPANY", ["MOS"], {"sector": "fertilizer", "ticker": "MOS"},
         "Phosphate + potash producer. Food security exposure. Structural demand growth."),

        # Rare earths
        ("mp-materials", "MP Materials Corp", "COMPANY", ["MP"], {"sector": "rare_earths", "ticker": "MP"},
         "Only US rare earth mine (Mountain Pass, CA). Processing expansion. Defense supply chain."),
        ("lynas-rare-earths", "Lynas Rare Earths Ltd", "COMPANY", ["LYSDY"], {"sector": "rare_earths", "ticker": "LYSDY"},
         "Non-China rare earth processing (Malaysia + Australia). US processing plant under construction."),

        # Lithium
        ("albemarle", "Albemarle Corp", "COMPANY", ["ALB"], {"sector": "lithium", "ticker": "ALB"},
         "Largest lithium producer. Battery-grade lithium for grid storage + EV. Price recovery play."),

        # Semiconductor (Layer 3 but supply-chain critical)
        ("nvidia-corp", "NVIDIA Corp", "COMPANY", ["NVDA"], {"sector": "semiconductor", "ticker": "NVDA"},
         "AI chip monopoly. Data center revenue >$100B run rate. Depends on TSMC fabs, rare earths, copper, helium."),
        ("tsmc", "TSMC", "COMPANY", ["TSM"], {"sector": "semiconductor", "ticker": "TSM"},
         "Fabricates >90% of advanced AI chips. Taiwan + Arizona fabs. Helium rationing risk. Rare earth dependency."),
    ]

    count = 0
    for node_id, name, ntype, aliases, metadata, desc in companies:
        ensure_node(conn, node_id, name, ntype, desc, aliases, metadata)
        count += 1
    conn.commit()
    print(f"  {count} extraction/mfg companies")


def populate_supply_chain_layers(conn):
    """Wire the full Layer 0→5 supply chain."""
    print("\n=== FULL SUPPLY CHAIN WIRING ===")
    edges = [
        # ─── LAYER 0→1: Commodity → Extraction ───
        # Gas
        ("chain-gas-eqt", "EXTRACTS", "eqt-corp", "commodity-natural-gas", 0.95,
         "EQT is largest US nat gas producer (Appalachian). Direct commodity exposure."),
        ("chain-gas-ar", "EXTRACTS", "antero-resources", "commodity-natural-gas", 0.90,
         "Antero Resources Utica/Marcellus gas production."),
        ("chain-gas-rrc", "EXTRACTS", "range-resources", "commodity-natural-gas", 0.85,
         "Range Resources Marcellus gas production."),
        ("chain-gas-cnx", "EXTRACTS", "cnx-resources", "commodity-natural-gas", 0.80,
         "CNX Appalachian gas production."),

        # Uranium
        ("chain-u-ccj", "EXTRACTS", "cameco", "commodity-uranium", 0.95,
         "Cameco largest Western uranium miner. McArthur River restart."),
        ("chain-u-uuuu", "EXTRACTS", "energy-fuels", "commodity-uranium", 0.85,
         "Energy Fuels only US conventional mill. 620K-880K lb in 2026."),
        ("chain-u-uec", "EXTRACTS", "uranium-energy", "commodity-uranium", 0.80,
         "UEC US ISR uranium producer. Production ramp."),
        ("chain-u-eu", "EXTRACTS", "encore-energy", "commodity-uranium", 0.75,
         "enCore Energy low-cost ISR. Expansion capacity."),

        # Copper
        ("chain-cu-fcx", "EXTRACTS", "freeport-mcmoran", "commodity-copper", 0.95,
         "FCX largest US copper producer. Grasberg mine."),
        ("chain-cu-scco", "EXTRACTS", "southern-copper", "commodity-copper", 0.90,
         "SCCO largest copper reserves globally. Mexico/Peru."),

        # Silver
        ("chain-ag-ag", "EXTRACTS", "first-majestic-silver", "commodity-silver", 0.90,
         "First Majestic primary silver miner. Mexico moratorium risk."),
        ("chain-ag-paas", "EXTRACTS", "pan-american-silver", "commodity-silver", 0.85,
         "PAAS diversified silver. Multiple jurisdictions."),

        # Coal
        ("chain-coal-cnr", "EXTRACTS", "core-natural-resources", "commodity-coal", 0.90,
         "Core Natural Resources (CONSOL+Arch). Appalachian proximity to DC markets."),
        ("chain-coal-btu", "EXTRACTS", "peabody-energy", "commodity-coal", 0.90,
         "Peabody largest global coal. PRB + Appalachian."),
        ("chain-coal-arlp", "EXTRACTS", "alliance-resource", "commodity-coal", 0.85,
         "Alliance Resource central Appalachian. PJM proximity."),

        # Fertilizer (gas → nitrogen)
        ("chain-fert-cf", "PROCESSES", "cf-industries", "commodity-natural-gas", 0.90,
         "CF Industries converts nat gas → nitrogen fertilizer. Direct gas price exposure."),
        ("chain-fert-ntr", "PROCESSES", "nutrien", "commodity-potash", 0.85,
         "Nutrien largest potash + nitrogen producer."),
        ("chain-fert-mos", "PROCESSES", "mosaic-company", "commodity-potash", 0.80,
         "Mosaic phosphate + potash producer."),

        # Rare earths
        ("chain-ree-mp", "EXTRACTS", "mp-materials", "commodity-rare-earths", 0.90,
         "MP Materials only US rare earth mine (Mountain Pass)."),

        # Lithium
        ("chain-li-alb", "EXTRACTS", "albemarle", "commodity-lithium", 0.85,
         "Albemarle largest lithium producer. Battery-grade."),

        # ─── LAYER 1→2: Extraction → Transport ───
        # Gas supply → Pipeline
        ("chain-eqt-nexus", "FEEDS_INTO", "eqt-corp", "facility-nexus-pipeline", 0.85,
         "EQT Marcellus/Utica production feeds NEXUS pipeline"),
        ("chain-ar-nexus", "FEEDS_INTO", "antero-resources", "facility-nexus-pipeline", 0.80,
         "Antero Utica production feeds NEXUS"),
        ("chain-eqt-transco", "FEEDS_INTO", "eqt-corp", "facility-transco-pipeline", 0.80,
         "EQT feeds Transco via Appalachian interconnects"),

        # ─── LAYER 2→3: Transport → Power Generation ───
        # Pipeline → Power project
        ("chain-nexus-stargate", "SUPPLIES_FUEL", "facility-nexus-pipeline", "project-stargate-mi", 0.85,
         "NEXUS pipeline delivers gas to DTE for Stargate 1.4 GW data center power"),
        ("chain-aristotle-socrates", "SUPPLIES_FUEL", "facility-aristotle-pipeline", "project-socrates-south", 0.95,
         "Aristotle pipeline built specifically to fuel Socrates power facility"),
        ("chain-oasis-cloudburst", "SUPPLIES_FUEL", "facility-oasis-pipeline", "project-cloudburst-tx", 0.95,
         "Oasis pipeline 450K MMBtu/d firm supply to CloudBurst DC"),

        # Uranium → Nuclear power
        ("chain-u-ceg", "FUELS", "commodity-uranium", "constellation-energy", 0.90,
         "Uranium fuels CEG nuclear fleet (largest US). Direct fuel cost exposure."),
        ("chain-u-vst", "FUELS", "commodity-uranium", "vistra-corp", 0.85,
         "Uranium fuels Vistra Comanche Peak nuclear."),
        ("chain-u-oklo", "FUELS", "commodity-uranium", "oklo", 0.80,
         "HALEU uranium required for Oklo SMR. US enrichment capacity <1% of global."),

        # Coal → Power (bridge)
        ("chain-coal-power", "FUELS", "commodity-coal", "geo-virginia-dc-corridor", 0.75,
         "Appalachian coal fuels power plants with delayed retirements serving VA data center demand."),

        # ─── LAYER 3→4: Power → Data Center ───
        # Power project → Data center
        ("chain-socrates-meta", "POWERS_DC", "project-socrates-south", "project-meta-new-albany", 0.95,
         "Socrates 200MW behind-the-meter power for Meta New Albany DC"),

        # ─── LAYER 4→5: Data Center → Hyperscaler/AI ───
        # Data center → AI platform
        ("chain-dc-nvidia", "ENABLES", "project-meta-new-albany", "nvidia-corp", 0.70,
         "Meta DC houses NVIDIA GPU clusters. No power = no inference."),
        ("chain-dc-tsmc", "ENABLES", "commodity-rare-earths", "tsmc", 0.85,
         "TSMC requires rare earths + helium for chip fabrication. China export curbs = supply risk."),
        ("chain-helium-tsmc", "CRITICAL_INPUT", "commodity-helium", "tsmc", 0.90,
         "Helium critical for semiconductor fab cooling. Qatar strikes doubled spot price. Rationing."),
        ("chain-cu-dc", "CRITICAL_INPUT", "commodity-copper", "geo-virginia-dc-corridor", 0.85,
         "27 tons copper per MW of data center. VA corridor 12.1 GW = 326,700 tons copper needed."),
        ("chain-cu-grid", "CRITICAL_INPUT", "commodity-copper", "dominion-energy", 0.80,
         "Copper wiring for grid expansion. Dominion serving 12.1 GW data center load in VA."),

        # ─── CROSS-CHAIN: Gas → Fertilizer → Food Inflation ───
        ("chain-gas-urea", "FEEDSTOCK_FOR", "commodity-natural-gas", "commodity-nitrogen-fertilizer", 0.95,
         "Natural gas is primary feedstock for nitrogen fertilizer (urea, UAN, ammonia). "
         "Gas at $4/MMBtu (2026) → elevated urea prices → food inflation."),
        ("chain-urea-food", "DRIVES_COST", "commodity-nitrogen-fertilizer", "commodity-potash", 0.70,
         "Elevated fertilizer costs (N+K) → higher food prices → real inflation above CPI."),

        # ─── THESIS LINKAGES: Bottleneck → Investment ───
        ("thesis-gas-bottleneck", "BOTTLENECK_FOR", "commodity-natural-gas", "sector-hyperscalers", 0.90,
         "8 Bcf/d incremental gas demand by 2030 for data centers. Gas turbine waitlists to 2030s. "
         "55% of new capacity queue is gas-fired. Structural bottleneck."),
        ("thesis-cu-bottleneck", "BOTTLENECK_FOR", "commodity-copper", "sector-hyperscalers", 0.85,
         "27 tons/MW × 50+ GW = 1.35M+ tons copper for existing data centers alone. "
         "10+ year mine development cycle. No substitute. Record $6/lb."),
        ("thesis-u-bottleneck", "BOTTLENECK_FOR", "commodity-uranium", "sector-nuclear-power", 0.85,
         "30-40M lb annual supply deficit. SMRs need HALEU. US enrichment <1% of global. "
         "Russian import ban 2028. Nuclear = only scalable baseload for post-gas era."),
        ("thesis-ree-bottleneck", "BOTTLENECK_FOR", "commodity-rare-earths", "nvidia-corp", 0.80,
         "China 70% mining, 90% processing. Export curbs targeting semiconductor supply chain. "
         "No near-term substitutes. Lead times >40 weeks for affected components."),
        ("thesis-he-bottleneck", "BOTTLENECK_FOR", "commodity-helium", "tsmc", 0.85,
         "Qatar 33% of global helium. 2026 strikes doubled price. Taiwan/Korea fabs rationing. "
         "No substitute for chip manufacturing cooling."),
    ]

    count = 0
    for item in edges:
        edge_id, etype, from_id, to_id, conf, notes = item[:6]
        source_url = item[6] if len(item) > 6 else ""
        if ensure_edge(conn, edge_id, etype, from_id, to_id, conf, notes, source_url):
            count += 1
    conn.commit()
    print(f"  {count} new supply chain edges")


def populate_new_theses(conn):
    """Add new investment theses to track."""
    print("\n=== NEW THESIS NODES ===")
    theses = [
        ("thesis-uranium-screen", "Uranium Structural Deficit Thesis", "THESIS",
         "30-40M lb annual deficit. SMR demand rising. HALEU enrichment bottleneck. "
         "US import dependency. $100+/lb consensus through 2026.",
         {"tickers": ["CCJ", "UUUU", "UEC", "DNN", "EU", "CEG", "VST", "OKLO", "SMR"]}),

        ("thesis-coal-bridge", "Coal Bridge Fuel Thesis", "THESIS",
         "Data center demand delaying 40% of planned coal retirements. DOE emergency declarations. "
         "Appalachian proximity to PJM data center load. Bridge until gas turbines/SMRs online.",
         {"tickers": ["CNR", "BTU", "ARLP"]}),

        ("thesis-fertilizer-inflation", "Fertilizer-Food Inflation Thesis", "THESIS",
         "Gas feedstock → nitrogen cost → food price → real inflation above CPI. "
         "M2 at 6.3% real. Urea +30% in 2025. Potash +19%. Agricultural input cost squeeze.",
         {"tickers": ["CF", "NTR", "MOS"]}),

        ("thesis-rare-earth-security", "Rare Earth Supply Security Thesis", "THESIS",
         "China 70% mining, 90% processing, export curbs targeting semicon. "
         "US Mountain Pass only domestic mine. Chip supply chain at risk. Defense implications.",
         {"tickers": ["MP", "LYSDY"]}),

        ("thesis-smr-endgame", "SMR Nuclear End Game Thesis", "THESIS",
         "Only baseload source that scales to GW without pipeline infrastructure. "
         "2028+ earliest revenue. HALEU fuel bottleneck. NRC certified (NuScale). "
         "Sam Altman backed (Oklo). Convergence point for gas transition.",
         {"tickers": ["OKLO", "SMR", "CCJ", "UUUU"]}),
    ]

    count = 0
    for node_id, name, ntype, desc, metadata in theses:
        ensure_node(conn, node_id, name, ntype, desc, metadata=metadata)
        count += 1

    # Wire thesis DEPENDS_ON edges
    thesis_deps = [
        ("thesis-uranium-screen", ["cameco", "energy-fuels", "uranium-energy", "denison-mines", "encore-energy"]),
        ("thesis-coal-bridge", ["core-natural-resources", "peabody-energy", "alliance-resource"]),
        ("thesis-fertilizer-inflation", ["cf-industries", "nutrien", "mosaic-company"]),
        ("thesis-rare-earth-security", ["mp-materials"]),
        ("thesis-smr-endgame", ["oklo", "nuscale-power", "cameco", "energy-fuels"]),
    ]

    edge_count = 0
    for thesis_id, companies in thesis_deps:
        for comp in companies:
            eid = f"tdep-{thesis_id}-{comp}"
            if ensure_edge(conn, eid, "DEPENDS_ON", comp, thesis_id, 0.85,
                          f"{comp} is a constituent of {thesis_id}"):
                edge_count += 1

    conn.commit()
    print(f"  {count} thesis nodes, {edge_count} new dependency edges")


def populate_sector_nodes_extended(conn):
    """Extended sector groupings."""
    print("\n=== EXTENDED SECTORS ===")
    sectors = {
        "sector-uranium-miners": ("Uranium Miners", [
            "cameco", "energy-fuels", "uranium-energy", "denison-mines", "encore-energy"]),
        "sector-coal-producers": ("Coal Producers", [
            "core-natural-resources", "peabody-energy", "alliance-resource"]),
        "sector-fertilizer": ("Fertilizer Producers", [
            "cf-industries", "nutrien", "mosaic-company"]),
        "sector-rare-earth-miners": ("Rare Earth Miners", [
            "mp-materials"]),
        "sector-lithium": ("Lithium Producers", [
            "albemarle"]),
        "sector-ai-semiconductor": ("AI Semiconductor", [
            "nvidia-corp", "tsmc"]),
    }

    count_n = 0
    count_e = 0
    for sid, (name, members) in sectors.items():
        ensure_node(conn, sid, name, "SECTOR", f"Sector: {name}")
        count_n += 1
        for m in members:
            eid = f"member-{m}-{sid}"
            if ensure_edge(conn, eid, "MEMBER_OF", m, sid, 0.95, f"{m} in {name}"):
                count_e += 1
    conn.commit()
    print(f"  {count_n} sector nodes, {count_e} new edges")


def populate_inflation_thesis_edges(conn):
    """Wire the M2 → commodity → food → real inflation chain."""
    print("\n=== INFLATION CHAIN ===")
    edges = [
        ("inflation-m2-commodities", "DRIVES", "commodity-natural-gas", "thesis-fertilizer-inflation", 0.90,
         "Gas price directly drives nitrogen fertilizer cost. $4/MMBtu 2026 → urea +30%. "
         "M2 at 6.3% (FRED) means commodities repricing in REAL purchasing power terms."),
        ("inflation-gas-datacenter", "COMPETES_FOR", "sector-hyperscalers", "commodity-natural-gas", 0.80,
         "Data centers competing with fertilizer/heating for gas supply. "
         "8 Bcf/d incremental demand by 2030 creates gas price pressure → food inflation."),
        ("inflation-cu-grid", "COMPETES_FOR", "sector-hyperscalers", "commodity-copper", 0.80,
         "Data centers competing with grid/EV for copper. 27 tons/MW at 50+ GW total."),
        ("inflation-food-cpi", "UNDERSTATED_BY", "commodity-nitrogen-fertilizer", "commodity-natural-gas", 0.85,
         "CPI understates real food inflation. OER methodology change 1983. "
         "M2 tracks actual purchasing power loss (+220% housing, +411% S&P). Gap IS the wealth transfer."),
    ]

    count = 0
    for item in edges:
        edge_id, etype, from_id, to_id, conf, notes = item[:6]
        if ensure_edge(conn, edge_id, etype, from_id, to_id, conf, notes):
            count += 1
    conn.commit()
    print(f"  {count} new inflation chain edges")


def main():
    t_start = time.time()
    conn = sqlite3.connect(DB_PATH)

    n_before = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    e_before = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]

    populate_commodities(conn)
    populate_extraction_companies(conn)
    populate_supply_chain_layers(conn)
    populate_new_theses(conn)
    populate_sector_nodes_extended(conn)
    populate_inflation_thesis_edges(conn)

    n_after = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    e_after = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]

    elapsed = time.time() - t_start
    print(f"\n{'='*60}")
    print(f"  COMMODITY CHAIN COMPLETE — {elapsed:.1f}s")
    print(f"  Nodes: {n_before} → {n_after} (+{n_after - n_before})")
    print(f"  Edges: {e_before} → {e_after} (+{e_after - e_before})")
    print(f"{'='*60}")

    conn.close()


if __name__ == "__main__":
    main()
