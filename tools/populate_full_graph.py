#!/usr/bin/env python3
"""
FGIP Full Graph Population — Country-wide data center power supply chain.

Populates the FGIP graph with:
1. All midstream/E&P/utility/nuclear companies in the thesis
2. Pipeline infrastructure (NEXUS, Transco, Guardian, Aristotle, etc.)
3. State regulatory bodies (PUC/PSC for every relevant state)
4. Data center projects and hyperscaler facilities
5. Supply chain edges (gas → pipeline → utility → data center → hyperscaler)
6. Regulatory edges (PUC approvals, FERC filings, permits)
7. Cross-asset correlations and hedge instruments
8. Adversary attack surfaces (short instruments, inverse ETFs)

Data sourced from: FERC, state PUC filings, SEC EDGAR, company earnings,
yfinance market data, public reporting (Fortune, Utility Dive, Power Engineering).
"""

import json
import sqlite3
import hashlib
import time
from datetime import datetime
from typing import List, Tuple

DB_PATH = "/home/voidstr3m33/fgip-engine/fgip.db"


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def ensure_node(conn, node_id, name, node_type, description="", aliases=None, metadata=None):
    """Insert node if not exists, update if exists."""
    existing = conn.execute("SELECT node_id FROM nodes WHERE node_id = ?", (node_id,)).fetchone()
    aliases_json = json.dumps(aliases or [])
    metadata_json = json.dumps(metadata or {})
    if existing:
        conn.execute("""
            UPDATE nodes SET name=?, description=?, aliases=?, metadata=?
            WHERE node_id=?
        """, (name, description, aliases_json, metadata_json, node_id))
    else:
        conn.execute("""
            INSERT INTO nodes (node_id, node_type, name, description, aliases, metadata, created_at, sha256)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (node_id, node_type, name, description, aliases_json, metadata_json,
              datetime.utcnow().isoformat() + "Z", sha256(f"{node_id}-{name}")))


def ensure_edge(conn, edge_id, edge_type, from_id, to_id, confidence=0.8, notes="",
                source_url="", assertion_level="CONFIRMED"):
    """Insert edge if not exists."""
    existing = conn.execute("SELECT edge_id FROM edges WHERE edge_id = ?", (edge_id,)).fetchone()
    if not existing:
        conn.execute("""
            INSERT INTO edges (edge_id, edge_type, from_node_id, to_node_id,
                              confidence, notes, source_url, assertion_level,
                              date_documented, created_at, sha256)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (edge_id, edge_type, from_id, to_id, confidence, notes, source_url,
              assertion_level, datetime.utcnow().strftime("%Y-%m-%d"),
              datetime.utcnow().isoformat() + "Z",
              sha256(f"{edge_id}-{from_id}-{to_id}")))
        return True
    return False


def populate_companies(conn):
    """All companies in the thesis universe."""
    print("\n=== COMPANIES ===")
    companies = [
        # Tier 1 — Midstream
        ("dtm-midstream", "DT Midstream Inc", "COMPANY", ["DTM"], {"sector": "midstream", "ticker": "DTM"},
         "NEXUS + Guardian + Midwest Gas Transmission pipelines. $1.2B FERC-regulated acquisition 2025."),
        ("williams-companies", "Williams Companies Inc", "COMPANY", ["WMB"], {"sector": "midstream", "ticker": "WMB"},
         "Transco pipeline (10K+ miles). Socrates/Aristotle power projects for Meta. $7.3B in power projects announced."),
        ("mplx", "MPLX LP", "COMPANY", ["MPLX"], {"sector": "midstream", "ticker": "MPLX"},
         "Ohio Utica gathering. Marathon Petroleum MLP. Distribution play."),
        ("energy-transfer", "Energy Transfer LP", "COMPANY", ["ET"], {"sector": "midstream", "ticker": "ET"},
         "First direct-to-data-center gas deal (CloudBurst, TX). 17.7mi NM pipeline under FERC review. 1.5 Bcf/d expansion."),
        ("kinder-morgan", "Kinder Morgan Inc", "COMPANY", ["KMI"], {"sector": "midstream", "ticker": "KMI"},
         "Largest midstream operator. Tennessee Gas Pipeline, Southern Natural Gas. Data center infrastructure plays."),
        ("targa-resources", "Targa Resources Corp", "COMPANY", ["TRGP"], {"sector": "midstream", "ticker": "TRGP"},
         "Permian Basin gathering + processing. NGL export. Benefits from E&P activity growth."),
        ("tallgrass-energy", "Tallgrass Energy Partners", "COMPANY", ["TGE"], {"sector": "midstream", "ticker": "TGE"},
         "JV with Crusoe: 1.8 GW AI Data Center campus in SE Wyoming."),

        # Tier 1 — E&P
        ("antero-resources", "Antero Resources Corp", "COMPANY", ["AR"], {"sector": "e_and_p", "ticker": "AR"},
         "Appalachian E&P. Utica/Marcellus. Gas price sensitive. Feeds NEXUS/Transco."),
        ("eqt-corp", "EQT Corporation", "COMPANY", ["EQT"], {"sector": "e_and_p", "ticker": "EQT"},
         "Largest US natural gas producer. Appalachian basin. Feeds midstream systems."),
        ("range-resources", "Range Resources Corp", "COMPANY", ["RRC"], {"sector": "e_and_p", "ticker": "RRC"},
         "Marcellus/Utica producer. SW Pennsylvania. Feeds Transco/TETCO."),
        ("cnx-resources", "CNX Resources Corp", "COMPANY", ["CNX"], {"sector": "e_and_p", "ticker": "CNX"},
         "Appalachian producer. Behind-the-meter power generation (CQP). Innovation pipeline."),
        ("southwestern-energy", "Southwestern Energy Co", "COMPANY", ["SWN"], {"sector": "e_and_p", "ticker": "SWN"},
         "Fayetteville + Appalachia E&P. Chesapeake merger target."),

        # Tier 2 — Utilities (data center load)
        ("dte-energy", "DTE Energy Co", "COMPANY", ["DTE"], {"sector": "utility", "ticker": "DTE"},
         "Michigan utility. MPSC approved 1.4 GW Stargate data center contract Dec 2025. $7B project."),
        ("cms-energy", "CMS Energy Corp", "COMPANY", ["CMS"], {"sector": "utility", "ticker": "CMS"},
         "Consumers Energy (Michigan). Rate GPD framework for data centers. Grand Rapids corridor."),
        ("southern-company-util", "Southern Company", "COMPANY", ["SO"], {"sector": "utility", "ticker": "SO"},
         "Georgia Power, Alabama Power. Hampton GA data center corridor. Equinix substation."),
        ("aep-company", "American Electric Power Co", "COMPANY", ["AEP"], {"sector": "utility", "ticker": "AEP"},
         "Ohio/PJM utility. Major data center load growth. Columbus/Central OH corridor."),
        ("dominion-energy", "Dominion Energy Inc", "COMPANY", ["D"], {"sector": "utility", "ticker": "D"},
         "Virginia utility. Data Center Alley (Ashburn/Loudoun). 12.1 GW data center demand in VA."),
        ("duke-energy", "Duke Energy Corp", "COMPANY", ["DUK"], {"sector": "utility", "ticker": "DUK"},
         "Carolinas + Florida utility. Growing data center load in Charlotte/NC."),
        ("entergy-corp", "Entergy Corp", "COMPANY", ["ETR"], {"sector": "utility", "ticker": "ETR"},
         "Louisiana/Mississippi/Texas. Data center + industrial load growth."),
        ("xcel-energy", "Xcel Energy Inc", "COMPANY", ["XEL"], {"sector": "utility", "ticker": "XEL"},
         "Minnesota/Colorado. Growing data center demand in Minneapolis corridor."),
        ("evergy-inc", "Evergy Inc", "COMPANY", ["EVRG"], {"sector": "utility", "ticker": "EVRG"},
         "Kansas/Missouri. Data center demand growth + Meta Sarpy County."),

        # Tier 2 — Nuclear/Gas Turbine
        ("constellation-energy", "Constellation Energy", "COMPANY", ["CEG"], {"sector": "nuclear", "ticker": "CEG"},
         "Largest US nuclear fleet. Data center PPAs with hyperscalers. Three Mile Island restart."),
        ("vistra-corp", "Vistra Corp", "COMPANY", ["VST"], {"sector": "nuclear", "ticker": "VST"},
         "ERCOT nuclear + gas. Comanche Peak nuclear. Data center power contracts."),
        ("ge-vernova", "GE Vernova Inc", "COMPANY", ["GEV"], {"sector": "gas_turbine", "ticker": "GEV"},
         "Gas turbine OEM. Behind-the-meter power plants. Backlog surge from data center orders."),
        ("oklo", "Oklo Inc.", "COMPANY", ["OKLO"], {"sector": "nuclear_smr", "ticker": "OKLO"},
         "SMR developer. 14 GW pipeline. 2028+ earliest revenue. Sam Altman backed."),
        ("nuscale-power", "NuScale Power Corp", "COMPANY", ["SMR"], {"sector": "nuclear_smr", "ticker": "SMR"},
         "SMR developer. NRC certified. Idaho project cancelled but tech validated."),

        # Tier 2 — Silver/Copper (structural bottleneck)
        ("first-majestic-silver", "First Majestic Silver Corp", "COMPANY", ["AG"], {"sector": "silver", "ticker": "AG"},
         "Primary silver miner. Mexico moratorium risk. High-grade Jerritt Canyon."),
        ("pan-american-silver", "Pan American Silver Corp", "COMPANY", ["PAAS"], {"sector": "silver", "ticker": "PAAS"},
         "Diversified silver miner. Multiple jurisdictions. Lower political risk."),
        ("freeport-mcmoran", "Freeport-McMoRan Inc", "COMPANY", ["FCX"], {"sector": "copper", "ticker": "FCX"},
         "Largest US copper producer. Grasberg mine. Grid wiring + EV + data center demand."),
        ("southern-copper", "Southern Copper Corp", "COMPANY", ["SCCO"], {"sector": "copper", "ticker": "SCCO"},
         "Mexico/Peru copper. Largest copper reserves globally."),

        # Hyperscalers (demand side)
        ("meta-platforms", "Meta Platforms Inc", "COMPANY", ["META"], {"sector": "hyperscaler", "ticker": "META"},
         "New Albany OH data center. Williams Socrates power project. Major gas power customer."),
        ("microsoft-corp", "Microsoft Corp", "COMPANY", ["MSFT"], {"sector": "hyperscaler", "ticker": "MSFT"},
         "Grand Rapids MI data center. Stargate JV with OpenAI. Nuclear PPAs."),
        ("amazon-aws", "Amazon Web Services", "COMPANY", ["AMZN"], {"sector": "hyperscaler", "ticker": "AMZN"},
         "Largest cloud provider. Virginia data center alley. Nuclear PPAs (Talen Energy)."),
        ("google-cloud", "Google / Alphabet", "COMPANY", ["GOOGL"], {"sector": "hyperscaler", "ticker": "GOOGL"},
         "Council Bluffs IA, The Dalles OR. Nuclear PPAs. Geothermal investment."),
        ("oracle-corp", "Oracle Corp", "COMPANY", ["ORCL"], {"sector": "hyperscaler", "ticker": "ORCL"},
         "Data center buildout acceleration. Nashville, Abilene TX. Power demand growth."),
    ]

    count = 0
    for node_id, name, ntype, aliases, metadata, desc in companies:
        ensure_node(conn, node_id, name, ntype, desc, aliases, metadata)
        count += 1
    conn.commit()
    print(f"  {count} companies ensured")


def populate_infrastructure(conn):
    """Pipeline infrastructure, power projects, data center facilities."""
    print("\n=== INFRASTRUCTURE ===")
    infra = [
        # Pipelines
        ("facility-nexus-pipeline", "NEXUS Gas Transmission Pipeline", "FACILITY",
         "1.5 Bcf/d capacity. Appalachian OH Utica → Michigan. Expandable to 2-2.5 Bcf/d. DTM operated.",
         {"type": "pipeline", "capacity_bcfd": 1.5, "operator": "DTM"}),
        ("facility-guardian-pipeline", "Guardian Pipeline LLC", "FACILITY",
         "1.3 Bcf/d. WI/IL. G3 expansion +537 MMcf/d (+40%). $850-930M. 20-year utility contracts. Online 2028.",
         {"type": "pipeline", "capacity_bcfd": 1.3, "operator": "DTM"}),
        ("facility-midwestern-gas-transmission", "Midwestern Gas Transmission", "FACILITY",
         "DTM-operated. Part of $1.2B acquisition. FERC-regulated.",
         {"type": "pipeline", "operator": "DTM"}),
        ("facility-viking-gas-transmission", "Viking Gas Transmission", "FACILITY",
         "DTM-operated. Part of $1.2B acquisition. FERC-regulated. MN/WI corridor.",
         {"type": "pipeline", "operator": "DTM"}),
        ("facility-transco-pipeline", "Transcontinental Gas Pipe Line (Transco)", "FACILITY",
         "10,000+ miles. Gulf Coast → NE. Largest US gas pipeline. WMB operated. Southeast data center exposure.",
         {"type": "pipeline", "capacity_bcfd": 17.0, "operator": "WMB"}),
        ("facility-aristotle-pipeline", "Aristotle Pipeline (Williams)", "FACILITY",
         "New Albany OH data center support. Commissioned 2025-2026. Feeds Socrates power facility.",
         {"type": "pipeline", "operator": "WMB"}),
        ("facility-oasis-pipeline", "Oasis Pipeline (Energy Transfer)", "FACILITY",
         "450K MMBtu/d firm supply to CloudBurst DC campus, San Marcos TX. First direct-to-DC gas deal.",
         {"type": "pipeline", "capacity_mmbtu_d": 450000, "operator": "ET"}),
        ("facility-nm-pipeline-et", "Energy Transfer NM AI Pipeline", "FACILITY",
         "17.7 miles. $60.2M. FERC review. Connects EPNG → Green Chile Ventures AI DC. Service Aug 2026.",
         {"type": "pipeline", "cost_m": 60.2, "operator": "ET"}),

        # Power projects
        ("project-socrates-south", "Socrates South Power Facility (Williams/Meta)", "PROJECT",
         "200 MW gas-fired behind-the-meter for Meta New Albany OH. OPSB approved Jun 2025. Solar Turbines Titan 250.",
         {"type": "power_plant", "capacity_mw": 200, "operator": "WMB", "customer": "META"}),
        ("project-socrates-north", "Socrates North Power Facility (Williams/Meta)", "PROJECT",
         "200 MW gas-fired behind-the-meter for Meta New Albany OH. Target Q4 2026.",
         {"type": "power_plant", "capacity_mw": 200, "operator": "WMB", "customer": "META"}),
        ("project-stargate-mi", "Project Stargate Michigan", "PROJECT",
         "1.4 GW data center. DTE Electric. $7B. MPSC approved Dec 2025. Washtenaw County. 19-year contract.",
         {"type": "data_center", "capacity_gw": 1.4, "utility": "DTE", "cost_b": 7.0}),
        ("project-microsoft-gr", "Microsoft Grand Rapids Data Center", "PROJECT",
         "1 GW data center complex. CMS Energy / Consumers Energy. Grand Rapids MI.",
         {"type": "data_center", "capacity_gw": 1.0, "utility": "CMS"}),
        ("project-cloudburst-tx", "CloudBurst Next-Gen Data Center (San Marcos TX)", "PROJECT",
         "Energy Transfer first direct-to-DC gas deal. 450K MMBtu/d. FID 2025, operational Q3 2026.",
         {"type": "data_center", "operator": "ET"}),
        ("project-crusoe-wy", "Crusoe/Tallgrass 1.8 GW AI Campus (Wyoming)", "PROJECT",
         "JV Tallgrass + Crusoe. SE Wyoming. 1.8 GW. Pipeline-direct gas supply.",
         {"type": "data_center", "capacity_gw": 1.8}),
        ("project-meta-new-albany", "Meta New Albany OH Data Center", "PROJECT",
         "Meta hyperscale facility. New Albany OH. Williams Socrates 400MW + Aristotle pipeline.",
         {"type": "data_center", "capacity_mw": 400, "customer": "META"}),

        # Data center corridors (geographic)
        ("geo-virginia-dc-corridor", "Virginia Data Center Alley", "GEOGRAPHY",
         "Ashburn/Loudoun County. 12.1 GW demand (2025). Largest US concentration. Dominion Energy service.",
         {"state": "VA", "demand_gw": 12.1}),
        ("geo-ohio-dc-corridor", "Ohio Data Center Corridor", "GEOGRAPHY",
         "Columbus/New Albany. Meta, AWS, Google. AEP + Williams power supply.",
         {"state": "OH", "demand_gw": 2.5}),
        ("geo-michigan-dc-corridor", "Michigan Data Center Corridor", "GEOGRAPHY",
         "Washtenaw (DTE Stargate 1.4GW), Grand Rapids (CMS/Microsoft 1GW). DTM NEXUS supply.",
         {"state": "MI", "demand_gw": 2.4}),
        ("geo-texas-dc-corridor", "Texas Data Center Corridor", "GEOGRAPHY",
         "San Marcos, Dallas, Houston. 9.7 GW demand (2025). ERCOT. Energy Transfer supply.",
         {"state": "TX", "demand_gw": 9.7}),
        ("geo-georgia-dc-corridor", "Georgia Data Center Corridor", "GEOGRAPHY",
         "Hampton, Atlanta metro. Southern Company/Georgia Power. Equinix, Switch.",
         {"state": "GA", "demand_gw": 2.3}),
        ("geo-wisconsin-dc-corridor", "Wisconsin Data Center Corridor", "GEOGRAPHY",
         "DTM Guardian pipeline expansion. Utility demand-driven. 20-year contracts.",
         {"state": "WI"}),
        ("geo-arizona-dc-corridor", "Arizona Data Center Corridor", "GEOGRAPHY",
         "Phoenix/Mesa. APS, SRP. Hot climate → high cooling load. Pipeline fuel lock-in.",
         {"state": "AZ", "demand_gw": 2.5}),
        ("geo-oregon-dc-corridor", "Oregon Data Center Corridor", "GEOGRAPHY",
         "The Dalles, Hillsboro. 4+ GW demand. Google, Meta, Apple. Hydro + gas backup.",
         {"state": "OR", "demand_gw": 4.0}),
    ]

    count = 0
    for item in infra:
        if len(item) == 5:
            node_id, name, ntype, desc, metadata = item
            ensure_node(conn, node_id, name, ntype, desc, metadata=metadata)
        else:
            node_id, name, ntype, desc = item[:4]
            ensure_node(conn, node_id, name, ntype, desc)
        count += 1
    conn.commit()
    print(f"  {count} infrastructure nodes ensured")


def populate_regulators(conn):
    """State PUCs, FERC, NRC, and relevant regulatory bodies."""
    print("\n=== REGULATORS ===")
    regulators = [
        ("ferc", "Federal Energy Regulatory Commission", "REGULATOR",
         "Regulates interstate pipelines, LNG, hydropower. Key approver for pipeline expansions."),
        ("nrc", "Nuclear Regulatory Commission", "REGULATOR",
         "Nuclear plant licensing. SMR approvals. Restart permits (TMI)."),
        ("mi-mpsc", "Michigan Public Service Commission", "REGULATOR",
         "Approved DTE 1.4 GW Stargate contract Dec 2025. Rate GPD framework for Consumers Energy."),
        ("ga-psc", "Georgia Public Service Commission", "REGULATOR",
         "Regulates Georgia Power. Data center tax credit elimination (SB 476)."),
        ("oh-puco", "Public Utilities Commission of Ohio", "REGULATOR",
         "Ohio Power Siting Board. Approved Socrates South 200MW Jun 2025."),
        ("va-scc", "Virginia State Corporation Commission", "REGULATOR",
         "Virginia data center regulation. 12.1 GW demand. Dominion Energy rate cases."),
        ("tx-puc", "Public Utility Commission of Texas", "REGULATOR",
         "ERCOT oversight. Data center interconnection. No retail rate regulation."),
        ("pa-puc", "Pennsylvania Public Utility Commission", "REGULATOR",
         "Marcellus/Utica drilling permits. Pipeline route approvals."),
        ("wv-psc", "West Virginia Public Service Commission", "REGULATOR",
         "Proposed 2 GW combined-cycle plant. E&P expansion permits."),
        ("wi-psc", "Public Service Commission of Wisconsin", "REGULATOR",
         "Guardian pipeline expansion territory. Data center power demand growth."),
        ("nc-uc", "North Carolina Utilities Commission", "REGULATOR",
         "Duke Energy territory. Growing Charlotte data center corridor."),
        ("az-acc", "Arizona Corporation Commission", "REGULATOR",
         "APS/SRP territory. Pipeline fuel supply for data center cooling load."),
        ("in-urc", "Indiana Utility Regulatory Commission", "REGULATOR",
         "Growing data center load. Settlement agreements on utility dockets."),
        ("il-icc", "Illinois Commerce Commission", "REGULATOR",
         "ComEd territory (Exelon). Northern IL data center corridor."),
        ("or-puc", "Oregon Public Utility Commission", "REGULATOR",
         "PGE/PacifiCorp territory. The Dalles, Hillsboro data centers."),
    ]

    count = 0
    for node_id, name, ntype, desc in regulators:
        ensure_node(conn, node_id, name, ntype, desc)
        count += 1
    conn.commit()
    print(f"  {count} regulator nodes ensured")


def populate_supply_chain_edges(conn):
    """Wire the entire supply chain: gas → pipeline → utility → data center → hyperscaler."""
    print("\n=== SUPPLY CHAIN EDGES ===")
    edges = [
        # E&P → Pipeline (gas supply)
        ("supply-ar-nexus", "SUPPLIES_GAS", "antero-resources", "facility-nexus-pipeline", 0.85,
         "Antero Utica production feeds NEXUS pipeline system"),
        ("supply-eqt-nexus", "SUPPLIES_GAS", "eqt-corp", "facility-nexus-pipeline", 0.85,
         "EQT Marcellus/Utica production feeds NEXUS"),
        ("supply-eqt-transco", "SUPPLIES_GAS", "eqt-corp", "facility-transco-pipeline", 0.80,
         "EQT production feeds Transco via interconnects"),
        ("supply-ar-transco", "SUPPLIES_GAS", "antero-resources", "facility-transco-pipeline", 0.75,
         "Antero production feeds Transco via Appalachian interconnects"),
        ("supply-rrc-transco", "SUPPLIES_GAS", "range-resources", "facility-transco-pipeline", 0.80,
         "Range Resources Marcellus feeds Transco"),
        ("supply-cnx-nexus", "SUPPLIES_GAS", "cnx-resources", "facility-nexus-pipeline", 0.70,
         "CNX Appalachian production contributes to NEXUS throughput"),

        # Pipeline → Utility (delivery)
        ("deliver-nexus-dte", "DELIVERS_TO", "facility-nexus-pipeline", "dte-energy", 0.90,
         "NEXUS delivers gas to DTE Energy Michigan service territory"),
        ("deliver-nexus-cms", "DELIVERS_TO", "facility-nexus-pipeline", "cms-energy", 0.90,
         "NEXUS delivers gas to Consumers Energy Michigan"),
        ("deliver-guardian-cms", "DELIVERS_TO", "facility-guardian-pipeline", "cms-energy", 0.85,
         "Guardian pipeline serves WI/IL, feeds into Michigan demand"),
        ("deliver-transco-so", "DELIVERS_TO", "facility-transco-pipeline", "southern-company-util", 0.90,
         "Transco Southern Natural Gas delivers to Southern Company territory"),
        ("deliver-transco-duke", "DELIVERS_TO", "facility-transco-pipeline", "duke-energy", 0.80,
         "Transco delivers to Duke Energy Carolinas territory"),
        ("deliver-transco-dom", "DELIVERS_TO", "facility-transco-pipeline", "dominion-energy", 0.85,
         "Transco delivers to Dominion Energy Virginia territory"),
        ("deliver-aristotle-meta", "DELIVERS_TO", "facility-aristotle-pipeline", "project-meta-new-albany", 0.95,
         "Aristotle pipeline commissioned specifically for Meta New Albany DC"),
        ("deliver-oasis-cloudburst", "DELIVERS_TO", "facility-oasis-pipeline", "project-cloudburst-tx", 0.95,
         "Oasis Pipeline 450K MMBtu/d firm supply to CloudBurst DC"),
        ("deliver-nm-greenchile", "DELIVERS_TO", "facility-nm-pipeline-et", "project-cloudburst-tx", 0.80,
         "Energy Transfer NM pipeline to Green Chile AI DC"),

        # Pipeline → Operator (ownership)
        ("operated-nexus-dtm", "OPERATED_BY", "facility-nexus-pipeline", "dtm-midstream", 0.95,
         "DTM operates NEXUS pipeline"),
        ("operated-guardian-dtm", "OPERATED_BY", "facility-guardian-pipeline", "dtm-midstream", 0.95,
         "DTM operates Guardian pipeline"),
        ("operated-mgt-dtm", "OPERATED_BY", "facility-midwestern-gas-transmission", "dtm-midstream", 0.95,
         "DTM acquired Midwestern Gas Transmission ($1.2B)"),
        ("operated-viking-dtm", "OPERATED_BY", "facility-viking-gas-transmission", "dtm-midstream", 0.95,
         "DTM acquired Viking Gas Transmission ($1.2B)"),
        ("operated-transco-wmb", "OPERATED_BY", "facility-transco-pipeline", "williams-companies", 0.95,
         "Williams operates Transco pipeline"),
        ("operated-aristotle-wmb", "OPERATED_BY", "facility-aristotle-pipeline", "williams-companies", 0.95,
         "Williams built + operates Aristotle pipeline for Meta"),
        ("operated-oasis-et", "OPERATED_BY", "facility-oasis-pipeline", "energy-transfer", 0.95,
         "Energy Transfer operates Oasis pipeline"),
        ("operated-nm-et", "OPERATED_BY", "facility-nm-pipeline-et", "energy-transfer", 0.95,
         "Energy Transfer building NM AI pipeline"),

        # Utility → Data Center Project (powers)
        ("powers-dte-stargate", "POWERS", "dte-energy", "project-stargate-mi", 0.95,
         "DTE Electric approved for 1.4 GW Stargate data center. 19-year contract."),
        ("powers-cms-msgr", "POWERS", "cms-energy", "project-microsoft-gr", 0.90,
         "Consumers Energy Rate GPD framework. Microsoft Grand Rapids DC."),
        ("powers-wmb-socrates-s", "POWERS", "williams-companies", "project-socrates-south", 0.95,
         "Williams 200MW behind-the-meter gas-fired for Meta. OPSB approved."),
        ("powers-wmb-socrates-n", "POWERS", "williams-companies", "project-socrates-north", 0.90,
         "Williams 200MW Socrates North. Target Q4 2026."),
        ("powers-et-cloudburst", "POWERS", "energy-transfer", "project-cloudburst-tx", 0.90,
         "Energy Transfer first direct gas-to-DC deal. San Marcos TX."),

        # Data Center Project → Hyperscaler (customer)
        ("customer-stargate-msft", "CONTRACTED", "project-stargate-mi", "microsoft-corp", 0.90,
         "Stargate JV includes Microsoft/OpenAI. Michigan facility."),
        ("customer-meta-newalbany", "CONTRACTED", "project-meta-new-albany", "meta-platforms", 0.95,
         "Meta hyperscale facility. Williams Socrates 400MW dedicated power."),
        ("customer-socrates-meta", "CONTRACTED", "project-socrates-south", "meta-platforms", 0.95,
         "Williams Socrates built specifically for Meta."),

        # Utility → Geography
        ("serves-dte-mi", "SERVES_TERRITORY", "dte-energy", "geo-michigan-dc-corridor", 0.95,
         "DTE Energy serves SE Michigan including Washtenaw County"),
        ("serves-cms-mi", "SERVES_TERRITORY", "cms-energy", "geo-michigan-dc-corridor", 0.90,
         "Consumers Energy serves West Michigan including Grand Rapids"),
        ("serves-so-ga", "SERVES_TERRITORY", "southern-company-util", "geo-georgia-dc-corridor", 0.95,
         "Georgia Power (Southern Co subsidiary) serves Atlanta metro"),
        ("serves-dom-va", "SERVES_TERRITORY", "dominion-energy", "geo-virginia-dc-corridor", 0.95,
         "Dominion Energy serves Virginia Data Center Alley"),
        ("serves-aep-oh", "SERVES_TERRITORY", "aep-company", "geo-ohio-dc-corridor", 0.90,
         "AEP Ohio serves Columbus/Central Ohio data center corridor"),

        # Pipeline geographic routes
        ("route-nexus-mi", "DELIVERS_TO", "facility-nexus-pipeline", "geo-michigan-dc-corridor", 0.90,
         "NEXUS Appalachian OH Utica → Michigan. 1.5 Bcf/d, expandable to 2.5 Bcf/d."),
        ("route-guardian-wi", "DELIVERS_TO", "facility-guardian-pipeline", "geo-wisconsin-dc-corridor", 0.90,
         "Guardian serves WI/IL. G3 expansion +40% capacity. 20-year utility contracts."),
        ("route-transco-ga", "DELIVERS_TO", "facility-transco-pipeline", "geo-georgia-dc-corridor", 0.85,
         "Transco Southern Natural Gas serves Georgia/Southeast corridor"),
        ("route-transco-va", "DELIVERS_TO", "facility-transco-pipeline", "geo-virginia-dc-corridor", 0.80,
         "Transco serves Virginia data center corridor via mid-Atlantic laterals"),

        # Gathering (MPLX)
        ("gathers-mplx-eqt", "GATHERS_FOR", "mplx", "eqt-corp", 0.85,
         "MPLX Ohio Utica gathering system serves EQT production"),
        ("gathers-mplx-ar", "GATHERS_FOR", "mplx", "antero-resources", 0.80,
         "MPLX gathering in Appalachian basin serves Antero wells"),

        # Gas turbine supply chain
        ("supplies-gev-socrates", "SUPPLIES_EQUIPMENT", "ge-vernova", "project-socrates-south", 0.70,
         "Siemens SGT400 + Solar Turbines (Caterpillar) used at Socrates. GEV supplies broader market."),
        ("supplies-gev-datacenter", "SUPPLIES_EQUIPMENT", "ge-vernova", "geo-texas-dc-corridor", 0.80,
         "GE Vernova gas turbines power behind-the-meter data center generation"),

        # JV/Partnership edges
        ("jv-tallgrass-crusoe", "CONTRACTED", "tallgrass-energy", "project-crusoe-wy", 0.90,
         "Tallgrass + Crusoe JV. 1.8 GW AI Data Center campus, SE Wyoming."),
    ]

    count = 0
    for edge_id, etype, from_id, to_id, conf, notes in edges:
        if ensure_edge(conn, edge_id, etype, from_id, to_id, conf, notes):
            count += 1
    conn.commit()
    print(f"  {count} new supply chain edges added")


def populate_regulatory_edges(conn):
    """Regulatory filings, approvals, and catalysts."""
    print("\n=== REGULATORY EDGES ===")
    edges = [
        # FERC filings
        ("ferc-nexus-expansion", "FILED_FERC", "dtm-midstream", "ferc", 0.85,
         "NEXUS expansion to 2-2.5 Bcf/d under FERC review. Data center power demand driven.",
         "https://www.ferc.gov/industries-data/natural-gas/approved-major-pipeline-projects-1997-present"),
        ("ferc-guardian-g3", "FILED_FERC", "dtm-midstream", "ferc", 0.90,
         "Guardian G3 expansion +537 MMcf/d. $850-930M. 20-year utility contracts. Target 2028.",
         "https://naturalgasintel.com/news/dt-midstream-upsizes-guardian-eyes-vector-expansion-as-midwest-gas-demand-grows/"),
        ("ferc-dtm-acquisition", "FILED_FERC", "dtm-midstream", "ferc", 0.95,
         "DTM $1.2B acquisition of Midwestern + Viking + Guardian pipelines. FERC-regulated.",
         "https://finance.yahoo.com/news/dt-midstream-announces-1-2-210100718.html"),
        ("ferc-et-nm-pipeline", "FILED_FERC", "energy-transfer", "ferc", 0.85,
         "ET 17.7-mile NM pipeline for AI DC under FERC blanket certificate review. $60.2M.",
         "https://pgjonline.com/news/2026/march/energy-transfer-s-177-mile-gas-pipeline-for-ai-data-center-in-new-mexico-under-ferc-review"),
        ("ferc-wmb-socrates", "FILED_FERC", "williams-companies", "ferc", 0.90,
         "Williams Socrates + Aristotle pipeline filings. $7.3B total power projects.",
         "https://www.williams.com/expansion-project/socrates-power-solution-facilities/"),
        ("ferc-colocation-ruling", "COMMISSION_ORDER", "ferc", "ferc", 0.95,
         "FERC Dec 2025 unanimous order: PJM must create data center colocation rules. 3 new transmission service options.",
         "https://www.ferc.gov/news-events/news/ferc-directs-nations-largest-grid-operator-create-new-rules-embrace-innovation-and"),

        # State PUC approvals
        ("mpsc-dte-stargate", "PUC_APPROVED", "mi-mpsc", "project-stargate-mi", 0.95,
         "MPSC approved DTE 1.4 GW Stargate data center contract Dec 2025. Conditions for customer protection.",
         "https://www.michigan.gov/mpsc/commission/news-releases/2025/12/18/mpsc-approves-dte-electric-energy-contracts-for-data-center"),
        ("mpsc-cms-rategpd", "COMMISSION_ORDER", "mi-mpsc", "cms-energy", 0.90,
         "MPSC Nov 2025 order: Consumers Energy Rate GPD framework for very large load (data centers).",
         "https://cubofmichigan.org/blog/new-standards-set-for-data-center-power-agreements-in-consumers-energy-service-territory/"),
        ("opsb-socrates-south", "PUC_APPROVED", "oh-puco", "project-socrates-south", 0.95,
         "Ohio Power Siting Board approved Socrates South 200MW Jun 2025.",
         "https://www.datacenterdynamics.com/en/news/ohio-regulators-approve-construction-of-200mw-gas-power-plant-to-serve-meta-data-center-in-new-albany-ohio/"),

        # Regulatory risks
        ("ga-sb476-tax", "FILED_MOTION", "ga-psc", "geo-georgia-dc-corridor", 0.75,
         "Georgia SB 476 passed Senate Feb 2026: eliminate data center tax credits. Risk to GA corridor growth.",
         "https://www.multistate.us/insider/2026/2/20/state-data-center-legislation-in-2026-tackles-energy-and-tax-issues"),

        # Utility → Regulator
        ("regulated-dte-mpsc", "REGULATES", "mi-mpsc", "dte-energy", 0.95, ""),
        ("regulated-cms-mpsc", "REGULATES", "mi-mpsc", "cms-energy", 0.95, ""),
        ("regulated-so-gapsc", "REGULATES", "ga-psc", "southern-company-util", 0.95, ""),
        ("regulated-dom-vascc", "REGULATES", "va-scc", "dominion-energy", 0.95, ""),
        ("regulated-aep-ohpuco", "REGULATES", "oh-puco", "aep-company", 0.90, ""),
        ("regulated-duke-ncuc", "REGULATES", "nc-uc", "duke-energy", 0.90, ""),
    ]

    count = 0
    for item in edges:
        edge_id, etype, from_id, to_id, conf, notes = item[:6]
        source_url = item[6] if len(item) > 6 else ""
        if ensure_edge(conn, edge_id, etype, from_id, to_id, conf, notes, source_url):
            count += 1
    conn.commit()
    print(f"  {count} new regulatory edges added")


def populate_sector_nodes(conn):
    """Sector grouping nodes and MEMBER_OF edges."""
    print("\n=== SECTOR NODES ===")
    sectors = {
        "sector-midstream-gas": ("Midstream Natural Gas", ["dtm-midstream", "williams-companies", "mplx",
                                                           "energy-transfer", "kinder-morgan", "targa-resources", "tallgrass-energy"]),
        "sector-appalachian-ep": ("Appalachian E&P", ["antero-resources", "eqt-corp", "range-resources",
                                                       "cnx-resources", "southwestern-energy"]),
        "sector-dc-utilities": ("Data Center Utilities", ["dte-energy", "cms-energy", "southern-company-util",
                                                          "aep-company", "dominion-energy", "duke-energy",
                                                          "entergy-corp", "xcel-energy", "evergy-inc"]),
        "sector-nuclear-power": ("Nuclear Power", ["constellation-energy", "vistra-corp", "oklo", "nuscale-power"]),
        "sector-gas-turbine-oem": ("Gas Turbine OEM", ["ge-vernova"]),
        "sector-precious-metals": ("Precious Metals Mining", ["first-majestic-silver", "pan-american-silver"]),
        "sector-base-metals": ("Base Metals Mining", ["freeport-mcmoran", "southern-copper"]),
        "sector-hyperscalers": ("Hyperscaler Data Centers", ["meta-platforms", "microsoft-corp", "amazon-aws",
                                                              "google-cloud", "oracle-corp"]),
    }

    count_nodes = 0
    count_edges = 0
    for sector_id, (name, members) in sectors.items():
        ensure_node(conn, sector_id, name, "SECTOR", f"Sector grouping: {name}")
        count_nodes += 1
        for member in members:
            eid = f"member-{member}-{sector_id}"
            if ensure_edge(conn, eid, "MEMBER_OF", member, sector_id, 0.95, f"{member} is part of {name}"):
                count_edges += 1
    conn.commit()
    print(f"  {count_nodes} sector nodes, {count_edges} new MEMBER_OF edges")


def populate_correlations(conn):
    """Compute cross-asset correlations for expanded universe + hedge instruments."""
    print("\n=== CORRELATIONS ===")
    try:
        import yfinance as yf
        import numpy as np
    except ImportError:
        print("  SKIP — yfinance/numpy not available")
        return

    # Full universe: our tickers + hedge instruments
    thesis_tickers = [
        "DTM", "AR", "MPLX", "EQT", "WMB",    # Tier 1
        "AG", "PAAS", "FCX", "CEG", "GEV",      # Tier 2
        "DTE", "CMS", "SO", "VST", "OKLO",      # Tier 3
        "ET", "KMI", "TRGP", "RRC", "CNX",      # Expanded midstream/E&P
        "AEP", "D", "DUK", "ETR", "XEL",        # Expanded utilities
        "SMR", "SCCO",                            # Expanded nuclear/copper
    ]

    hedge_tickers = [
        "UNG",   # Natural gas futures ETF
        "KOLD",  # 2x inverse natural gas
        "SLV",   # Silver ETF
        "GLD",   # Gold (macro hedge)
        "TLT",   # Long-term treasuries (rate hedge)
        "VIX",   # Volatility (can't trade directly but track)
        "XLU",   # Utilities sector ETF
        "XLE",   # Energy sector ETF
        "QQQ",   # Tech (hyperscaler exposure)
        "SPY",   # S&P 500 (market beta)
    ]

    all_tickers = thesis_tickers + hedge_tickers
    print(f"  Fetching 1yr data for {len(all_tickers)} tickers...")

    data = yf.download(all_tickers, period="1y", progress=False)
    if "Close" not in data.columns.get_level_values(0):
        # Single-level columns fallback
        closes = data["Close"] if "Close" in data else data
    else:
        closes = data["Close"]

    returns = closes.pct_change(fill_method=None).dropna()

    # Compute correlation matrix
    corr = returns.corr()

    # Record ticker-to-node mapping
    ticker_to_node = {
        "DTM": "dtm-midstream", "AR": "antero-resources", "MPLX": "mplx",
        "EQT": "eqt-corp", "WMB": "williams-companies", "DTE": "dte-energy",
        "CMS": "cms-energy", "SO": "southern-company-util", "GEV": "ge-vernova",
        "CEG": "constellation-energy", "VST": "vistra-corp", "OKLO": "oklo",
        "AG": "first-majestic-silver", "PAAS": "pan-american-silver",
        "FCX": "freeport-mcmoran", "ET": "energy-transfer", "KMI": "kinder-morgan",
        "TRGP": "targa-resources", "RRC": "range-resources", "CNX": "cnx-resources",
        "AEP": "aep-company", "D": "dominion-energy", "DUK": "duke-energy",
        "ETR": "entergy-corp", "XEL": "xcel-energy", "SMR": "nuscale-power",
        "SCCO": "southern-copper",
    }

    # 1. Strong positive correlations (>0.6) within thesis universe
    count_corr = 0
    seen = set()
    for t1 in thesis_tickers:
        for t2 in thesis_tickers:
            if t1 >= t2:
                continue
            pair = (t1, t2)
            if pair in seen:
                continue
            seen.add(pair)
            try:
                r = corr.loc[t1, t2]
                if abs(r) > 0.6 and not np.isnan(r):
                    n1 = ticker_to_node.get(t1, t1.lower())
                    n2 = ticker_to_node.get(t2, t2.lower())
                    edge_id = f"corr-{t1.lower()}-{t2.lower()}"
                    notes = f"1yr daily return correlation r={r:+.3f} ({returns.index[0].strftime('%Y-%m-%d')} to {returns.index[-1].strftime('%Y-%m-%d')})"
                    if ensure_edge(conn, edge_id, "CORRELATED_WITH", n1, n2, abs(r), notes):
                        count_corr += 1
            except (KeyError, TypeError):
                pass

    # 2. Hedge correlations (negative or low correlation with thesis tickers)
    count_hedge = 0
    for h_ticker in hedge_tickers:
        # Ensure hedge instrument node
        h_node = f"hedge-{h_ticker.lower()}"
        ensure_node(conn, h_node, h_ticker, "INSTRUMENT",
                    f"Hedge instrument: {h_ticker}",
                    aliases=[h_ticker],
                    metadata={"instrument_type": "etf", "ticker": h_ticker})

        for t_ticker in thesis_tickers[:15]:  # Core 15 only
            try:
                r = corr.loc[h_ticker, t_ticker]
                if np.isnan(r):
                    continue
                n1 = ticker_to_node.get(t_ticker, t_ticker.lower())

                if r < -0.2:
                    # Negative correlation = hedge
                    edge_id = f"hedge-{h_ticker.lower()}-{t_ticker.lower()}"
                    notes = f"HEDGE: 1yr r={r:+.3f}. {h_ticker} moves inversely to {t_ticker}."
                    if ensure_edge(conn, edge_id, "HEDGES_AGAINST", h_node, n1, abs(r), notes):
                        count_hedge += 1
                elif r > 0.7:
                    # High positive correlation = sector beta exposure
                    edge_id = f"beta-{h_ticker.lower()}-{t_ticker.lower()}"
                    notes = f"BETA: 1yr r={r:+.3f}. {h_ticker} tracks {t_ticker} (sector exposure)."
                    if ensure_edge(conn, edge_id, "CORRELATED_WITH", h_node, n1, r, notes):
                        count_corr += 1
            except (KeyError, TypeError):
                pass

    conn.commit()
    print(f"  {count_corr} new correlation edges, {count_hedge} new hedge edges")

    # Print summary table
    print("\n  TOP CORRELATIONS (thesis universe, |r| > 0.7):")
    for t1 in thesis_tickers:
        for t2 in thesis_tickers:
            if t1 >= t2:
                continue
            try:
                r = corr.loc[t1, t2]
                if abs(r) > 0.7 and not np.isnan(r):
                    print(f"    {t1:5s} ↔ {t2:5s}  r={r:+.3f}")
            except (KeyError, TypeError):
                pass

    print("\n  TOP HEDGES (r < -0.2 with thesis tickers):")
    for h_ticker in hedge_tickers:
        for t_ticker in thesis_tickers[:15]:
            try:
                r = corr.loc[h_ticker, t_ticker]
                if r < -0.2 and not np.isnan(r):
                    print(f"    {h_ticker:5s} vs {t_ticker:5s}  r={r:+.3f}")
            except (KeyError, TypeError):
                pass


def populate_adversary_edges(conn):
    """Map adversary attack vectors: what profits when our thesis fails?"""
    print("\n=== ADVERSARY ATTACK EDGES ===")

    # Attack vectors as nodes
    attacks = [
        ("attack-gas-price-collapse", "Gas Price Collapse (<$3.00)", "ATTACK_VECTOR",
         "Sustained gas <$3.00 kills E&P economics, reduces midstream throughput, destroys our Tier 1."),
        ("attack-ai-capex-bubble", "AI Capex Bubble Burst", "ATTACK_VECTOR",
         "Hyperscalers cut capex → data center cancellations → utility load growth fails → midstream demand drops."),
        ("attack-grid-constraints", "Grid Constraint / Interconnection Delays", "ATTACK_VECTOR",
         "Utility grid unable to handle data center load → projects delayed → utility revenue miss."),
        ("attack-renewable-undercut", "Renewables + Battery Cost Collapse", "ATTACK_VECTOR",
         "Solar+storage undercuts gas-fired baseload → stranded pipeline assets → midstream devaluation."),
        ("attack-recession", "Recession / Demand Destruction", "ATTACK_VECTOR",
         "Macro recession → power demand falls → all energy names get hit → correlations go to 1."),
        ("attack-rate-spike", "Interest Rate Spike", "ATTACK_VECTOR",
         "Higher rates → higher discount rate for utility DCFs → kills utility premium multiples."),
        ("attack-mexico-moratorium-lift", "Mexico Mining Moratorium Lifted", "ATTACK_VECTOR",
         "Mexico lifts mining moratorium → silver supply flood → AG/PAAS collapse."),
        ("attack-copper-substitution", "Copper Substitution Breakthrough", "ATTACK_VECTOR",
         "Aluminum or other substitute displaces copper in wiring → FCX/SCCO thesis dies."),
        ("attack-nuclear-accident", "Nuclear Accident / Regulatory Shutdown", "ATTACK_VECTOR",
         "Any nuclear incident globally → political shutdown → CEG/VST collapse."),
    ]

    for node_id, name, ntype, desc in attacks:
        ensure_node(conn, node_id, name, ntype, desc)

    # Map attacks to affected tickers
    attack_edges = [
        # Gas price collapse
        ("attack-gas-ar", "THREATENS", "attack-gas-price-collapse", "antero-resources", 0.90,
         "AR is pure-play gas E&P. Gas <$3 for 2 quarters = exit trigger."),
        ("attack-gas-eqt", "THREATENS", "attack-gas-price-collapse", "eqt-corp", 0.85,
         "EQT largest gas producer. Hedging program provides buffer but fundamentals hurt."),
        ("attack-gas-rrc", "THREATENS", "attack-gas-price-collapse", "range-resources", 0.85,
         "Range Resources gas-weighted production."),
        ("attack-gas-dtm", "THREATENS", "attack-gas-price-collapse", "dtm-midstream", 0.50,
         "DTM fee-based, insulated from commodity. Volume risk only if E&Ps shut in."),
        ("attack-gas-wmb", "THREATENS", "attack-gas-price-collapse", "williams-companies", 0.45,
         "WMB fee-based + long-term contracts. Less exposed. Demand-pull pipeline."),

        # AI capex bubble
        ("attack-ai-dte", "THREATENS", "attack-ai-capex-bubble", "dte-energy", 0.80,
         "DTE Stargate 1.4 GW depends on hyperscaler buildout continuing."),
        ("attack-ai-cms", "THREATENS", "attack-ai-capex-bubble", "cms-energy", 0.75,
         "CMS Microsoft deal depends on continued data center demand."),
        ("attack-ai-gev", "THREATENS", "attack-ai-capex-bubble", "ge-vernova", 0.85,
         "GEV gas turbine backlog is heavily data-center driven."),
        ("attack-ai-wmb", "THREATENS", "attack-ai-capex-bubble", "williams-companies", 0.70,
         "WMB $7.3B power projects depend on hyperscaler demand."),

        # Renewables undercut
        ("attack-renew-dtm", "THREATENS", "attack-renewable-undercut", "dtm-midstream", 0.60,
         "If solar+storage beats gas for baseload, pipeline throughput long-term risk."),
        ("attack-renew-gev", "THREATENS", "attack-renewable-undercut", "ge-vernova", 0.75,
         "Gas turbine demand collapses if renewables win for data center power."),

        # Nuclear accident
        ("attack-nuke-ceg", "THREATENS", "attack-nuclear-accident", "constellation-energy", 0.95,
         "CEG largest nuclear fleet. Any incident = existential."),
        ("attack-nuke-vst", "THREATENS", "attack-nuclear-accident", "vistra-corp", 0.85,
         "VST Comanche Peak nuclear exposure."),
        ("attack-nuke-oklo", "THREATENS", "attack-nuclear-accident", "oklo", 0.90,
         "OKLO SMR regulatory pathway dies on any nuclear incident."),

        # Mexico moratorium
        ("attack-mx-ag", "THREATENS", "attack-mexico-moratorium-lift", "first-majestic-silver", 0.90,
         "AG primary Mexico silver miner. Moratorium lift = supply flood."),
        ("attack-mx-paas", "THREATENS", "attack-mexico-moratorium-lift", "pan-american-silver", 0.70,
         "PAAS diversified, less Mexico exposure than AG."),

        # Copper substitution
        ("attack-cu-fcx", "THREATENS", "attack-copper-substitution", "freeport-mcmoran", 0.85,
         "FCX largest US copper. Substitution breakthrough = thesis death."),

        # Recession
        ("attack-recess-all", "THREATENS", "attack-recession", "sector-midstream-gas", 0.80,
         "Recession hits all energy. Correlations converge to 1. Portfolio-wide risk."),
    ]

    count = 0
    for item in attack_edges:
        edge_id, etype, from_id, to_id, conf, notes = item
        if ensure_edge(conn, edge_id, etype, from_id, to_id, conf, notes):
            count += 1

    # Hedge edges (what PROFITS when attacks hit)
    hedge_map = [
        ("hedge-attack-gas-kold", "PROFITS_FROM", "hedge-kold", "attack-gas-price-collapse", 0.85,
         "KOLD (2x inverse nat gas) profits from gas price collapse."),
        ("hedge-attack-recession-tlt", "PROFITS_FROM", "hedge-tlt", "attack-recession", 0.70,
         "TLT (long treasuries) rallies in recession (flight to safety)."),
        ("hedge-attack-recession-gld", "PROFITS_FROM", "hedge-gld", "attack-recession", 0.65,
         "GLD (gold) rallies in recession/uncertainty."),
        ("hedge-attack-rate-xlu", "PROFITS_FROM", "hedge-xlu", "attack-rate-spike", 0.50,
         "XLU (utilities ETF) drops on rate hikes — can short for rate hedge."),
    ]

    for item in hedge_map:
        edge_id, etype, from_id, to_id, conf, notes = item
        # Ensure hedge nodes exist
        for nid in [from_id, to_id]:
            if nid.startswith("hedge-"):
                ticker = nid.replace("hedge-", "").upper()
                ensure_node(conn, nid, ticker, "INSTRUMENT",
                           f"Hedge instrument: {ticker}",
                           aliases=[ticker])
        if ensure_edge(conn, edge_id, etype, from_id, to_id, conf, notes):
            count += 1

    conn.commit()
    print(f"  {count} new adversary/hedge edges added")


def populate_market_metrics(conn):
    """Fetch current market metrics for thesis tickers."""
    print("\n=== MARKET METRICS ===")
    try:
        import yfinance as yf
    except ImportError:
        print("  SKIP — yfinance not available")
        return

    ticker_to_node = {
        "DTM": "dtm-midstream", "AR": "antero-resources", "MPLX": "mplx",
        "EQT": "eqt-corp", "WMB": "williams-companies", "DTE": "dte-energy",
        "CMS": "cms-energy", "SO": "southern-company-util", "GEV": "ge-vernova",
        "CEG": "constellation-energy", "VST": "vistra-corp", "OKLO": "oklo",
        "AG": "first-majestic-silver", "PAAS": "pan-american-silver",
        "FCX": "freeport-mcmoran", "ET": "energy-transfer", "KMI": "kinder-morgan",
    }

    for ticker, node_id in ticker_to_node.items():
        try:
            info = yf.Ticker(ticker).info
            metadata = {
                "ticker": ticker,
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE"),
                "dividend_yield": info.get("dividendYield"),
                "52w_high": info.get("fiftyTwoWeekHigh"),
                "52w_low": info.get("fiftyTwoWeekLow"),
                "avg_volume": info.get("averageVolume"),
                "beta": info.get("beta"),
                "sector": info.get("sector"),
                "fetched_at": datetime.utcnow().isoformat() + "Z",
            }
            # Update node metadata
            existing = conn.execute("SELECT metadata FROM nodes WHERE node_id = ?", (node_id,)).fetchone()
            if existing:
                try:
                    current = json.loads(existing[0]) if existing[0] else {}
                except:
                    current = {}
                current.update(metadata)
                conn.execute("UPDATE nodes SET metadata = ? WHERE node_id = ?",
                           (json.dumps(current), node_id))
            print(f"  {ticker:5s} mcap={metadata['market_cap']:,.0f}  beta={metadata.get('beta', 'N/A')}  "
                  f"div={metadata.get('dividend_yield', 'N/A')}")
        except Exception as e:
            print(f"  {ticker:5s} FAILED: {e}")

    conn.commit()
    print("  Market metrics updated")


def main():
    t_start = time.time()
    conn = sqlite3.connect(DB_PATH)

    # Count before
    n_before = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    e_before = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]

    populate_companies(conn)
    populate_infrastructure(conn)
    populate_regulators(conn)
    populate_sector_nodes(conn)
    populate_supply_chain_edges(conn)
    populate_regulatory_edges(conn)
    populate_adversary_edges(conn)
    populate_correlations(conn)
    populate_market_metrics(conn)

    # Count after
    n_after = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    e_after = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]

    elapsed = time.time() - t_start
    print(f"\n{'='*60}")
    print(f"  GRAPH POPULATION COMPLETE — {elapsed:.1f}s")
    print(f"  Nodes: {n_before} → {n_after} (+{n_after - n_before})")
    print(f"  Edges: {e_before} → {e_after} (+{e_after - e_before})")
    print(f"{'='*60}")

    conn.close()


if __name__ == "__main__":
    main()
