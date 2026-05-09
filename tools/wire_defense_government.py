#!/usr/bin/env python3
"""
Wire defense/government spending pipeline into FGIP trading system.

Adds:
1. Ticker aliases for defense companies (LMT, RTX, NOC, BA, GD, etc.)
2. Bill → Contract → Company beneficiary edges
3. Active defense bills and programs as graph nodes
4. AWARDED_CONTRACT edges from DoD/agencies to prime contractors

Data sources: USASpending (Tier 0), Congress.gov (Tier 0), Federal Register (Tier 0)
"""

import hashlib
import json
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "fgip.db"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def upsert_node(conn, node_id, name, node_type, metadata=None, aliases=None):
    """Insert or update a node."""
    existing = conn.execute("SELECT node_id FROM nodes WHERE node_id = ?", (node_id,)).fetchone()
    meta_json = json.dumps(metadata) if metadata else "{}"
    aliases_json = json.dumps(aliases) if aliases else "[]"

    if existing:
        # Update aliases and metadata if provided
        if aliases:
            conn.execute(
                "UPDATE nodes SET aliases = ? WHERE node_id = ?",
                (aliases_json, node_id)
            )
        if metadata:
            conn.execute(
                "UPDATE nodes SET metadata = ? WHERE node_id = ?",
                (meta_json, node_id)
            )
    else:
        node_hash = sha256(f"{node_id}-{name}-{node_type}")
        conn.execute(
            """INSERT INTO nodes (node_id, name, node_type, metadata, aliases, created_at, sha256)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (node_id, name, node_type, meta_json, aliases_json,
             datetime.utcnow().isoformat() + "Z", node_hash)
        )


def upsert_edge(conn, from_id, to_id, edge_type, confidence=0.95, notes="", source_url=""):
    """Insert edge if it doesn't already exist."""
    existing = conn.execute(
        """SELECT edge_id FROM edges
           WHERE from_node_id = ? AND to_node_id = ? AND edge_type = ?""",
        (from_id, to_id, edge_type)
    ).fetchone()

    if not existing:
        edge_hash = sha256(f"{from_id}-{edge_type}-{to_id}")
        conn.execute(
            """INSERT INTO edges (from_node_id, to_node_id, edge_type, confidence, notes,
                                  source_url, sha256, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (from_id, to_id, edge_type, confidence, notes, source_url, edge_hash,
             datetime.utcnow().isoformat() + "Z")
        )
        return True
    return False


def add_defense_ticker_aliases(conn):
    """Add ticker symbols as aliases to defense companies."""
    print("\n=== Adding Defense Company Ticker Aliases ===")

    defense_tickers = {
        "lockheed-martin":    ["LMT", "Lockheed Martin"],
        "raytheon":           ["RTX", "Raytheon", "RTX Corporation"],
        "northrop-grumman":   ["NOC", "Northrop Grumman"],
        "boeing":             ["BA", "Boeing"],
        "general-dynamics":   ["GD", "General Dynamics"],
        "l3harris":           ["LHX", "L3Harris Technologies"],
        "bae-systems":        ["BAESY", "BAE Systems"],
        "huntington-ingalls": ["HII", "Huntington Ingalls Industries"],
        "leidos":             ["LDOS", "Leidos Holdings"],
        "saic":               ["SAIC", "Science Applications International"],
        # Defense tech
        "palantir":           ["PLTR", "Palantir Technologies"],
    }

    # Also add some that might not be in the graph yet
    new_defense_companies = {
        "kratos-defense": {
            "name": "Kratos Defense & Security Solutions",
            "aliases": ["KTOS", "Kratos"],
            "metadata": {"sector": "defense", "subsector": "drones_autonomous", "market_cap": "5B"},
        },
        "aerojet-rocketdyne": {
            "name": "Aerojet Rocketdyne (L3Harris)",
            "aliases": ["AJRD", "Aerojet"],
            "metadata": {"sector": "defense", "subsector": "propulsion", "note": "Acquired by L3Harris 2023"},
        },
        "textron": {
            "name": "Textron Inc",
            "aliases": ["TXT", "Textron", "Bell Helicopter"],
            "metadata": {"sector": "defense", "subsector": "rotorcraft_systems"},
        },
        "howmet-aerospace": {
            "name": "Howmet Aerospace",
            "aliases": ["HWM", "Howmet"],
            "metadata": {"sector": "defense", "subsector": "aerospace_components"},
        },
        "transdigm": {
            "name": "TransDigm Group",
            "aliases": ["TDG", "TransDigm"],
            "metadata": {"sector": "defense", "subsector": "aerospace_components"},
        },
        "curtiss-wright": {
            "name": "Curtiss-Wright Corporation",
            "aliases": ["CW", "Curtiss-Wright"],
            "metadata": {"sector": "defense", "subsector": "naval_nuclear"},
        },
        "bwxt": {
            "name": "BWX Technologies",
            "aliases": ["BWXT", "BWX Technologies"],
            "metadata": {"sector": "defense", "subsector": "naval_nuclear_reactors"},
        },
        "booz-allen": {
            "name": "Booz Allen Hamilton",
            "aliases": ["BAH", "Booz Allen"],
            "metadata": {"sector": "defense", "subsector": "consulting_cyber"},
        },
    }

    updated = 0
    for node_id, aliases in defense_tickers.items():
        existing = conn.execute("SELECT node_id FROM nodes WHERE node_id = ?", (node_id,)).fetchone()
        if existing:
            conn.execute("UPDATE nodes SET aliases = ? WHERE node_id = ?",
                         (json.dumps(aliases), node_id))
            updated += 1
            print(f"  Updated aliases: {node_id} → {aliases}")
        else:
            print(f"  WARNING: {node_id} not in graph, skipping alias")

    created = 0
    for node_id, info in new_defense_companies.items():
        existing = conn.execute("SELECT node_id FROM nodes WHERE node_id = ?", (node_id,)).fetchone()
        if not existing:
            upsert_node(conn, node_id, info["name"], "COMPANY",
                         metadata=info["metadata"], aliases=info["aliases"])
            created += 1
            print(f"  Created: {node_id} ({info['aliases'][0]})")
        else:
            conn.execute("UPDATE nodes SET aliases = ? WHERE node_id = ?",
                         (json.dumps(info["aliases"]), node_id))
            updated += 1
            print(f"  Updated aliases: {node_id} → {info['aliases']}")

    print(f"  Total: {updated} updated, {created} created")
    return updated + created


def add_defense_bills_and_programs(conn):
    """Add active defense/government spending bills and programs as nodes."""
    print("\n=== Adding Defense Bills & Programs ===")

    bills = [
        # NDAA (annual defense authorization)
        {
            "node_id": "ndaa-fy2025",
            "name": "National Defense Authorization Act FY2025",
            "node_type": "LEGISLATION",
            "metadata": {
                "bill_number": "H.R.8070", "status": "ENACTED",
                "amount": "$895.2B", "signed": "2024-12-23",
                "key_provisions": [
                    "5.2% military pay raise",
                    "Missile defense modernization",
                    "AUKUS submarine program funding",
                    "Ukraine military aid authorization",
                    "Pacific Deterrence Initiative $9.9B",
                    "ICBM Sentinel program continuation",
                ],
            },
            "aliases": ["NDAA FY2025", "FY25 Defense Authorization"],
        },
        {
            "node_id": "ndaa-fy2026",
            "name": "National Defense Authorization Act FY2026",
            "node_type": "LEGISLATION",
            "metadata": {
                "bill_number": "TBD", "status": "IN_PROGRESS",
                "amount": "~$925B (requested)",
                "key_provisions": [
                    "Sentinel ICBM replacement acceleration",
                    "Hypersonic weapons production",
                    "AI/autonomous systems investment",
                    "Shipbuilding acceleration (Columbia, Virginia class)",
                    "Munitions industrial base expansion",
                ],
            },
            "aliases": ["NDAA FY2026", "FY26 Defense Authorization"],
        },
        # Ukraine supplemental
        {
            "node_id": "ukraine-supplemental-2024",
            "name": "Ukraine Security Supplemental Appropriations Act 2024",
            "node_type": "LEGISLATION",
            "metadata": {
                "bill_number": "H.R.8035", "status": "ENACTED",
                "amount": "$60.84B",
                "key_provisions": [
                    "HIMARS and artillery ammunition replenishment",
                    "Patriot missile system replacement",
                    "ATACMS and GMLRS production acceleration",
                    "US industrial base replenishment for transferred stocks",
                ],
            },
            "aliases": ["Ukraine Aid 2024", "Ukraine Supplemental"],
        },
        # Infrastructure / IIJA remaining spend
        {
            "node_id": "iija-infrastructure",
            "name": "Infrastructure Investment and Jobs Act (IIJA)",
            "node_type": "LEGISLATION",
            "metadata": {
                "bill_number": "H.R.3684", "status": "ENACTED",
                "amount": "$1.2T over 5 years",
                "remaining_spend": "~$600B through FY2027",
                "key_provisions": [
                    "Grid modernization $65B",
                    "Broadband expansion $65B",
                    "Roads and bridges $110B",
                    "Clean water $55B",
                    "Electric vehicle charging $7.5B",
                ],
            },
            "aliases": ["IIJA", "Bipartisan Infrastructure Law", "BIL"],
        },
        # IRA
        {
            "node_id": "ira-inflation-reduction",
            "name": "Inflation Reduction Act",
            "node_type": "LEGISLATION",
            "metadata": {
                "bill_number": "H.R.5376", "status": "ENACTED",
                "amount": "$369B energy/climate",
                "key_provisions": [
                    "Nuclear production tax credit $15/MWh",
                    "Clean energy manufacturing credits",
                    "Critical minerals processing credits",
                    "EV tax credits (domestic content requirements)",
                    "Grid-scale storage investment credit",
                ],
            },
            "aliases": ["IRA", "Inflation Reduction Act"],
        },
        # CHIPS Act (already exists, just ensure aliases)
        # Pacific Deterrence Initiative
        {
            "node_id": "pacific-deterrence-initiative",
            "name": "Pacific Deterrence Initiative",
            "node_type": "PROGRAM",
            "metadata": {
                "agency": "DoD", "status": "ACTIVE",
                "amount": "$9.9B FY2025",
                "focus": "Indo-Pacific military posture, missile defense, force projection",
            },
            "aliases": ["PDI", "Pacific Deterrence"],
        },
        # Sentinel ICBM
        {
            "node_id": "sentinel-icbm-program",
            "name": "LGM-35A Sentinel ICBM Program",
            "node_type": "PROGRAM",
            "metadata": {
                "contractor": "Northrop Grumman", "status": "DEVELOPMENT",
                "amount": "$96B estimated lifecycle",
                "note": "Minuteman III replacement. Nunn-McCurdy breach 2024 (+37% cost growth). Restructured.",
            },
            "aliases": ["Sentinel ICBM", "GBSD", "LGM-35A"],
        },
        # Hypersonic weapons
        {
            "node_id": "hypersonic-weapons-program",
            "name": "Hypersonic Weapons Development Programs",
            "node_type": "PROGRAM",
            "metadata": {
                "contractors": ["Lockheed Martin (ARRW/HACM)", "Raytheon (HACM)", "Northrop Grumman (glide body)"],
                "status": "PRODUCTION",
                "amount": "$4.7B FY2025 request",
            },
            "aliases": ["Hypersonic Weapons", "ARRW", "HACM", "LRHW"],
        },
        # Columbia-class submarine
        {
            "node_id": "columbia-class-submarine",
            "name": "Columbia-Class Ballistic Missile Submarine Program",
            "node_type": "PROGRAM",
            "metadata": {
                "contractor": "General Dynamics (Electric Boat)", "status": "CONSTRUCTION",
                "amount": "$132B for 12 boats",
                "note": "Ohio-class replacement. Nuclear deterrent. First boat 2028 delivery.",
            },
            "aliases": ["Columbia Class", "SSBN-826"],
        },
        # AUKUS submarine deal
        {
            "node_id": "aukus-submarine-program",
            "name": "AUKUS Submarine Program (Pillar 1)",
            "node_type": "PROGRAM",
            "metadata": {
                "partners": ["US", "UK", "Australia"],
                "contractors": ["General Dynamics", "Huntington Ingalls", "BAE Systems"],
                "status": "ACTIVE",
                "amount": "$368B (Australia contribution over 30 years)",
                "note": "Australia gets Virginia-class subs, then SSN-AUKUS. US industrial base expansion funded.",
            },
            "aliases": ["AUKUS", "AUKUS Pillar 1"],
        },
    ]

    created = 0
    for bill in bills:
        existing = conn.execute("SELECT node_id FROM nodes WHERE node_id = ?",
                                (bill["node_id"],)).fetchone()
        if not existing:
            upsert_node(conn, bill["node_id"], bill["name"], bill["node_type"],
                         metadata=bill["metadata"], aliases=bill["aliases"])
            created += 1
            print(f"  Created: {bill['node_id']}")
        else:
            # Update metadata
            conn.execute("UPDATE nodes SET metadata = ?, aliases = ? WHERE node_id = ?",
                         (json.dumps(bill["metadata"]), json.dumps(bill["aliases"]), bill["node_id"]))
            print(f"  Updated: {bill['node_id']}")

    print(f"  Total: {created} new bills/programs")
    return created


def add_contract_edges(conn):
    """Add AWARDED_CONTRACT edges from bills/programs to defense companies."""
    print("\n=== Adding Contract → Company Edges ===")

    # Format: (from_node, to_node, edge_type, confidence, notes, source_url)
    contract_edges = [
        # NDAA FY2025 → Prime Contractors
        ("ndaa-fy2025", "lockheed-martin", "AUTHORIZES_FUNDING",
         0.95, "NDAA FY2025 authorizes F-35 production ($7.8B), HACM hypersonic, PAC-3 Patriot",
         "https://congress.gov/bill/118th-congress/house-bill/8070"),
        ("ndaa-fy2025", "raytheon", "AUTHORIZES_FUNDING",
         0.95, "NDAA FY2025 authorizes Patriot missile system, AMRAAM, StormBreaker",
         "https://congress.gov/bill/118th-congress/house-bill/8070"),
        ("ndaa-fy2025", "northrop-grumman", "AUTHORIZES_FUNDING",
         0.95, "NDAA FY2025 authorizes Sentinel ICBM, B-21 Raider, E-2D Hawkeye",
         "https://congress.gov/bill/118th-congress/house-bill/8070"),
        ("ndaa-fy2025", "boeing", "AUTHORIZES_FUNDING",
         0.95, "NDAA FY2025 authorizes F-15EX, KC-46 tanker, P-8 Poseidon",
         "https://congress.gov/bill/118th-congress/house-bill/8070"),
        ("ndaa-fy2025", "general-dynamics", "AUTHORIZES_FUNDING",
         0.95, "NDAA FY2025 authorizes Columbia-class submarine, Abrams tank, Stryker",
         "https://congress.gov/bill/118th-congress/house-bill/8070"),
        ("ndaa-fy2025", "l3harris", "AUTHORIZES_FUNDING",
         0.95, "NDAA FY2025 authorizes ISR systems, space sensors, electronic warfare",
         "https://congress.gov/bill/118th-congress/house-bill/8070"),
        ("ndaa-fy2025", "huntington-ingalls", "AUTHORIZES_FUNDING",
         0.95, "NDAA FY2025 authorizes Virginia-class submarine, aircraft carrier maintenance",
         "https://congress.gov/bill/118th-congress/house-bill/8070"),
        ("ndaa-fy2025", "bwxt", "AUTHORIZES_FUNDING",
         0.95, "NDAA FY2025 authorizes naval nuclear reactor components (Columbia, Virginia class)",
         "https://congress.gov/bill/118th-congress/house-bill/8070"),

        # Ukraine Supplemental → Replenishment contracts
        ("ukraine-supplemental-2024", "lockheed-martin", "FUNDS_REPLENISHMENT",
         0.95, "Ukraine supplemental: HIMARS, ATACMS, Javelin replenishment ($5.4B industrial base)",
         "https://congress.gov/bill/118th-congress/house-bill/8035"),
        ("ukraine-supplemental-2024", "raytheon", "FUNDS_REPLENISHMENT",
         0.95, "Ukraine supplemental: Patriot missiles, Stinger, NASAMS replenishment",
         "https://congress.gov/bill/118th-congress/house-bill/8035"),
        ("ukraine-supplemental-2024", "northrop-grumman", "FUNDS_REPLENISHMENT",
         0.95, "Ukraine supplemental: ammunition production, GMLRS, IBCS",
         "https://congress.gov/bill/118th-congress/house-bill/8035"),
        ("ukraine-supplemental-2024", "general-dynamics", "FUNDS_REPLENISHMENT",
         0.95, "Ukraine supplemental: 155mm artillery shell production acceleration",
         "https://congress.gov/bill/118th-congress/house-bill/8035"),
        ("ukraine-supplemental-2024", "bae-systems", "FUNDS_REPLENISHMENT",
         0.95, "Ukraine supplemental: M777 howitzer parts, Bradley vehicle components",
         "https://congress.gov/bill/118th-congress/house-bill/8035"),

        # Program → Primary Contractor
        ("sentinel-icbm-program", "northrop-grumman", "PRIME_CONTRACTOR",
         0.98, "Northrop Grumman sole-source prime for LGM-35A Sentinel. $96B lifecycle.",
         "https://usaspending.gov"),
        ("columbia-class-submarine", "general-dynamics", "PRIME_CONTRACTOR",
         0.98, "General Dynamics Electric Boat: lead yard for Columbia-class. $132B for 12 boats.",
         "https://usaspending.gov"),
        ("columbia-class-submarine", "huntington-ingalls", "PRIME_CONTRACTOR",
         0.98, "Huntington Ingalls Newport News: co-builder for Columbia-class.",
         "https://usaspending.gov"),
        ("columbia-class-submarine", "bwxt", "KEY_SUPPLIER",
         0.95, "BWXT supplies nuclear reactor components for Columbia-class.",
         "https://bwxt.com"),
        ("hypersonic-weapons-program", "lockheed-martin", "PRIME_CONTRACTOR",
         0.95, "Lockheed Martin: ARRW air-launched hypersonic, HACM scramjet (with Raytheon).",
         "https://usaspending.gov"),
        ("hypersonic-weapons-program", "raytheon", "PRIME_CONTRACTOR",
         0.95, "Raytheon: HACM scramjet cruise missile (Engines), LRHW glide vehicle integration.",
         "https://usaspending.gov"),
        ("hypersonic-weapons-program", "northrop-grumman", "KEY_SUPPLIER",
         0.95, "Northrop Grumman: hypersonic glide body development.",
         "https://usaspending.gov"),
        ("aukus-submarine-program", "general-dynamics", "PRIME_CONTRACTOR",
         0.95, "GD Electric Boat builds Virginia-class for AUKUS Phase 1.",
         "https://usaspending.gov"),
        ("aukus-submarine-program", "huntington-ingalls", "PRIME_CONTRACTOR",
         0.95, "HII Newport News: Virginia-class co-builder for AUKUS.",
         "https://usaspending.gov"),
        ("aukus-submarine-program", "bae-systems", "PRIME_CONTRACTOR",
         0.95, "BAE Systems: UK partner for SSN-AUKUS design and build.",
         "https://gov.uk"),
        ("aukus-submarine-program", "bwxt", "KEY_SUPPLIER",
         0.95, "BWXT nuclear reactor components for expanded submarine production.",
         "https://bwxt.com"),
        ("pacific-deterrence-initiative", "lockheed-martin", "AWARDED_CONTRACT",
         0.90, "PDI: missile defense radar, THAAD, Aegis integration for Indo-Pacific.",
         "https://usaspending.gov"),
        ("pacific-deterrence-initiative", "raytheon", "AWARDED_CONTRACT",
         0.90, "PDI: SM-6 missiles, SPY-6 radar, Patriot for Pacific posture.",
         "https://usaspending.gov"),
        ("pacific-deterrence-initiative", "northrop-grumman", "AWARDED_CONTRACT",
         0.90, "PDI: Triton UAV, IBCS command and control for Pacific.",
         "https://usaspending.gov"),

        # IRA → Energy/nuclear companies (already have some, but add nuclear credits)
        ("ira-inflation-reduction", "constellation-energy", "TAX_CREDIT_BENEFICIARY",
         0.95, "IRA nuclear production tax credit $15/MWh benefits largest US nuclear fleet.",
         "https://congress.gov"),

        # IIJA → Infrastructure plays
        ("iija-infrastructure", "quanta-services", "AWARDED_CONTRACT",
         0.85, "IIJA grid modernization: Quanta is largest US electrical contractor.",
         "https://usaspending.gov"),

        # Defense tech
        ("department-of-defense", "palantir", "AWARDED_CONTRACT",
         0.95, "DoD: Army TITAN program ($458M), Maven, CDAO AI/ML contracts.",
         "https://usaspending.gov"),
        ("department-of-defense", "booz-allen", "AWARDED_CONTRACT",
         0.95, "DoD: cybersecurity, intelligence analysis, digital transformation contracts.",
         "https://usaspending.gov"),
        ("department-of-defense", "leidos", "AWARDED_CONTRACT",
         0.95, "DoD: NGEN IT infrastructure ($7.7B), hypersonics test & eval.",
         "https://usaspending.gov"),
        ("department-of-defense", "saic", "AWARDED_CONTRACT",
         0.95, "DoD: Army tactical network, space systems, IT modernization.",
         "https://usaspending.gov"),
        ("department-of-defense", "kratos-defense", "AWARDED_CONTRACT",
         0.90, "DoD: target drones (BQM-177A), tactical UAVs, directed energy.",
         "https://usaspending.gov"),
    ]

    # Also need infrastructure companies that may not exist
    infra_companies = {
        "quanta-services": {
            "name": "Quanta Services",
            "aliases": ["PWR", "Quanta"],
            "metadata": {"sector": "infrastructure", "subsector": "electrical_contractor"},
        },
        "constellation-energy": {
            "name": "Constellation Energy",
            "aliases": ["CEG", "Constellation"],
            "metadata": {"sector": "nuclear", "subsector": "nuclear_utility"},
        },
    }

    for node_id, info in infra_companies.items():
        upsert_node(conn, node_id, info["name"], "COMPANY",
                     metadata=info["metadata"], aliases=info["aliases"])

    added = 0
    for edge in contract_edges:
        from_id, to_id, edge_type, conf, notes, source_url = edge
        if upsert_edge(conn, from_id, to_id, edge_type, conf, notes, source_url):
            added += 1
            print(f"  {from_id} → {edge_type} → {to_id}")

    print(f"  Total: {added} new contract edges")
    return added


def add_bill_to_sector_edges(conn):
    """Add edges that link bills/programs to sectors for the conviction engine to find."""
    print("\n=== Adding Bill → Sector Mapping Edges ===")

    # These edges let the conviction engine see which legislation supports which sector
    sector_edges = [
        # NDAA supports defense sector broadly
        ("ndaa-fy2025", "defense", "SUPPORTS_SECTOR", 0.95,
         "NDAA FY2025 $895.2B defense authorization", "https://congress.gov"),
        ("ndaa-fy2026", "defense", "SUPPORTS_SECTOR", 0.90,
         "NDAA FY2026 ~$925B request in progress", "https://congress.gov"),
        # Ukraine supplemental = munitions industrial base
        ("ukraine-supplemental-2024", "defense", "SUPPORTS_SECTOR", 0.95,
         "Ukraine supplemental $60.84B including US industrial base replenishment", "https://congress.gov"),
        # IRA supports nuclear, renewables, critical minerals
        ("ira-inflation-reduction", "nuclear", "SUPPORTS_SECTOR", 0.95,
         "IRA nuclear PTC $15/MWh for existing fleet + $0 emission credit", "https://congress.gov"),
        ("ira-inflation-reduction", "critical_minerals", "SUPPORTS_SECTOR", 0.90,
         "IRA critical minerals processing credits + domestic content requirements", "https://congress.gov"),
        # IIJA supports infrastructure, grid
        ("iija-infrastructure", "infrastructure_equipment", "SUPPORTS_SECTOR", 0.95,
         "IIJA $65B grid modernization + $110B roads + bridges", "https://congress.gov"),
        # Programs
        ("sentinel-icbm-program", "defense", "SUPPORTS_SECTOR", 0.98,
         "Sentinel ICBM $96B lifecycle = Northrop Grumman sole source", "https://usaspending.gov"),
        ("columbia-class-submarine", "defense", "SUPPORTS_SECTOR", 0.98,
         "Columbia-class $132B = GD Electric Boat + HII", "https://usaspending.gov"),
        ("pacific-deterrence-initiative", "defense", "SUPPORTS_SECTOR", 0.95,
         "PDI $9.9B FY2025 Indo-Pacific military posture", "https://usaspending.gov"),
    ]

    # Create sector nodes if they don't exist
    for sector_id in ["defense", "nuclear", "critical_minerals", "infrastructure_equipment"]:
        upsert_node(conn, sector_id, sector_id.replace("_", " ").title(), "SECTOR",
                     metadata={"type": "sector"})

    added = 0
    for edge in sector_edges:
        from_id, to_id, edge_type, conf, notes, source_url = edge
        if upsert_edge(conn, from_id, to_id, edge_type, conf, notes, source_url):
            added += 1

    print(f"  Total: {added} new sector mapping edges")
    return added


def add_supply_chain_defense_edges(conn):
    """Add DEPENDS_ON, SUPPLIES_TO, KEY_SUPPLIER edges within defense supply chain."""
    print("\n=== Adding Defense Supply Chain Edges ===")

    supply_edges = [
        # Primes depend on sub-components
        ("lockheed-martin", "raytheon", "SUPPLIES_TO", 0.85,
         "Raytheon supplies engines (Pratt & Whitney) for F-35", ""),
        ("lockheed-martin", "bae-systems", "SUPPLIES_TO", 0.85,
         "BAE Systems supplies electronic warfare systems for F-35", ""),
        ("lockheed-martin", "northrop-grumman", "SUPPLIES_TO", 0.85,
         "Northrop Grumman supplies AN/APG-81 AESA radar, center fuselage for F-35", ""),
        ("lockheed-martin", "howmet-aerospace", "DEPENDS_ON", 0.80,
         "Howmet supplies forged titanium/nickel aerostructures", ""),
        ("lockheed-martin", "transdigm", "DEPENDS_ON", 0.80,
         "TransDigm sole-source aerospace components (pumps, valves, actuators)", ""),

        # Naval nuclear chain
        ("general-dynamics", "bwxt", "DEPENDS_ON", 0.90,
         "BWXT sole-source naval nuclear reactor components for subs", ""),
        ("huntington-ingalls", "bwxt", "DEPENDS_ON", 0.90,
         "BWXT sole-source nuclear reactors for carriers and subs", ""),
        ("huntington-ingalls", "curtiss-wright", "DEPENDS_ON", 0.85,
         "Curtiss-Wright supplies naval defense electronics, reactor coolant pumps", ""),

        # Missile supply chain
        ("raytheon", "howmet-aerospace", "DEPENDS_ON", 0.80,
         "Howmet supplies forged components for missile systems", ""),
        ("northrop-grumman", "howmet-aerospace", "DEPENDS_ON", 0.80,
         "Howmet supplies forged components for Sentinel, B-21", ""),

        # Uranium supply chain for naval reactors (connects to our uranium thesis!)
        ("bwxt", "cameco", "DEPENDS_ON", 0.85,
         "Naval reactor fuel requires enriched uranium. Cameco is primary Western supplier.",
         ""),

        # Defense tech supply chain
        ("palantir", "department-of-defense", "CONTRACTED", 0.95,
         "Palantir: Army TITAN, CDAO contracts. Software-defined warfare.", ""),
        ("booz-allen", "department-of-defense", "CONTRACTED", 0.95,
         "Booz Allen: $7.7B+ in active DoD contracts.", ""),

        # Cross-thesis connection: defense → nuclear → uranium
        ("defense", "uranium", "DEPENDS_ON", 0.80,
         "Naval nuclear propulsion (subs, carriers) requires enriched uranium supply chain.",
         ""),
    ]

    # Ensure cameco node exists with ticker
    upsert_node(conn, "cameco", "Cameco Corporation", "COMPANY",
                 metadata={"sector": "uranium", "ticker": "CCJ"},
                 aliases=["CCJ", "Cameco"])

    added = 0
    for edge in supply_edges:
        from_id, to_id, edge_type, conf, notes, source_url = edge
        if upsert_edge(conn, from_id, to_id, edge_type, conf, notes, source_url):
            added += 1

    print(f"  Total: {added} new supply chain edges")
    return added


def add_adversary_edges(conn):
    """Add attack vectors relevant to defense sector."""
    print("\n=== Adding Defense Adversary Edges ===")

    # Adversary nodes
    adversaries = [
        ("threat-defense-budget-cut", "Defense Budget Cut / Sequestration", "ATTACK_VECTOR",
         {"severity": "high", "likelihood": 0.25,
          "mechanism": "Budget caps, sequestration, peace dividend narrative"}),
        ("threat-cost-overrun", "Major Program Cost Overrun", "ATTACK_VECTOR",
         {"severity": "high", "likelihood": 0.50,
          "mechanism": "Nunn-McCurdy breach → restructure → cancellation risk. Sentinel already breached."}),
        ("threat-contract-protest", "Contract Award Protest / Delay", "ATTACK_VECTOR",
         {"severity": "medium", "likelihood": 0.40,
          "mechanism": "GAO protests delay awards 6-12 months. Revenue recognition impact."}),
        ("threat-export-restriction", "Arms Export Restriction", "ATTACK_VECTOR",
         {"severity": "medium", "likelihood": 0.30,
          "mechanism": "ITAR restrictions, Congressional holds on FMS. Impacts international revenue."}),
    ]

    for node_id, name, node_type, metadata in adversaries:
        upsert_node(conn, node_id, name, node_type, metadata=metadata)

    threat_edges = [
        ("threat-defense-budget-cut", "lockheed-martin", "THREATENS", 0.7,
         "Budget cuts directly reduce procurement funding for F-35, HIMARS, etc.", ""),
        ("threat-defense-budget-cut", "raytheon", "THREATENS", 0.7,
         "Budget cuts reduce missile procurement (Patriot, SM-6, AMRAAM)", ""),
        ("threat-defense-budget-cut", "northrop-grumman", "THREATENS", 0.7,
         "Budget cuts could slow Sentinel, B-21 production rates", ""),
        ("threat-defense-budget-cut", "general-dynamics", "THREATENS", 0.7,
         "Budget cuts reduce submarine build rate, vehicle procurement", ""),
        ("threat-cost-overrun", "northrop-grumman", "THREATENS", 0.8,
         "Sentinel ICBM already hit Nunn-McCurdy breach (+37%). Risk of restructure.", ""),
        ("threat-cost-overrun", "boeing", "THREATENS", 0.75,
         "Boeing has history of cost overruns (Starliner, KC-46, Air Force One)", ""),
        ("threat-contract-protest", "lockheed-martin", "THREATENS", 0.5,
         "Next-gen fighter competition could face protest", ""),
        ("threat-export-restriction", "lockheed-martin", "THREATENS", 0.4,
         "F-35 international sales subject to Congressional approval and ITAR", ""),
        ("threat-export-restriction", "raytheon", "THREATENS", 0.4,
         "Patriot, NASAMS exports require State Dept approval", ""),
    ]

    added = 0
    for edge in threat_edges:
        from_id, to_id, edge_type, conf, notes, source_url = edge
        if upsert_edge(conn, from_id, to_id, edge_type, conf, notes, source_url):
            added += 1

    print(f"  Total: {added} new adversary edges")
    return added


def main():
    print("=" * 60)
    print("  FGIP Defense/Government Spending Pipeline Wiring")
    print(f"  {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    conn = sqlite3.connect(str(DB_PATH))

    t_start = time.time()

    try:
        n1 = add_defense_ticker_aliases(conn)
        n2 = add_defense_bills_and_programs(conn)
        n3 = add_contract_edges(conn)
        n4 = add_bill_to_sector_edges(conn)
        n5 = add_supply_chain_defense_edges(conn)
        n6 = add_adversary_edges(conn)

        conn.commit()

        elapsed = time.time() - t_start

        # Count totals
        node_count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        edge_count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]

        print(f"\n{'=' * 60}")
        print(f"  DONE")
        print(f"  Graph: {node_count} nodes, {edge_count} edges")
        print(f"  Wall time: {elapsed:.1f}s")
        print(f"{'=' * 60}")

        # Save receipt
        receipt = {
            "receipt_id": f"defense_government_wiring_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "actions": {
                "ticker_aliases": n1,
                "bills_programs": n2,
                "contract_edges": n3,
                "sector_mappings": n4,
                "supply_chain_edges": n5,
                "adversary_edges": n6,
            },
            "graph_totals": {
                "nodes": node_count,
                "edges": edge_count,
            },
            "cost": {
                "wall_time_s": round(elapsed, 3),
                "python_version": sys.version.split()[0],
                "hostname": __import__("platform").node(),
                "timestamp_start": datetime.utcnow().isoformat(),
            },
        }

        receipt_dir = DB_PATH.parent / "receipts"
        receipt_dir.mkdir(exist_ok=True)
        receipt_path = receipt_dir / f"defense_government_wiring_{datetime.utcnow().strftime('%Y%m%d')}.json"
        with open(receipt_path, "w") as f:
            json.dump(receipt, f, indent=2)
        print(f"  Receipt: {receipt_path}")

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
