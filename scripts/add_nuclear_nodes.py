#!/usr/bin/env python3
"""
Add Nuclear SMR Sector Nodes to FGIP graph.

Gap identified: Graph has ZERO nodes for nuclear despite:
- YouTube signal showing SRS #275 (Jay Yu), SRS #219 (Isaiah Taylor)
- NNE trading at $25 (same "dead money" setup as Intel at $17)
- Trump EO mandating reactor permits by July 4
- DoE funding flowing to SMR projects

Thesis chain:
Reshoring → Factories need power → AI data centers need baseload →
Grid can't handle it → SMRs are the answer → Correction Layer infrastructure
"""

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path


# =============================================================================
# NUCLEAR SECTOR NODES
# =============================================================================

NUCLEAR_COMPANIES = [
    {
        "node_id": "nne",
        "name": "NuScale Energy Inc.",
        "node_type": "COMPANY",
        "description": "First NRC-approved SMR design. Ticker: SMR (was NNE). UAMPS project. 77 MWe modules.",
        "aliases": ["NuScale", "NuScale Power", "SMR"],
        "metadata": {
            "ticker": "SMR",
            "cik": "0001976315",
            "layer": "correction",
            "sector": "nuclear_smr",
            "founded": 2007,
            "nrc_certified": "2020-09-01"
        }
    },
    {
        "node_id": "oklo",
        "name": "Oklo Inc.",
        "node_type": "COMPANY",
        "description": "Aurora microreactor. Sam Altman backed/chairman. Ticker: OKLO. 1.5-15 MWe fast reactor.",
        "aliases": ["Oklo"],
        "metadata": {
            "ticker": "OKLO",
            "cik": "0001849820",
            "layer": "correction",
            "sector": "nuclear_smr"
        }
    },
    {
        "node_id": "valar-atomics",
        "name": "Valar Atomics",
        "node_type": "COMPANY",
        "description": "Jay Yu's company. Molten salt SMR. YC-backed. Data center power focus.",
        "aliases": ["Valar"],
        "metadata": {
            "layer": "correction",
            "sector": "nuclear_smr",
            "tech": "molten_salt"
        }
    },
    {
        "node_id": "terrapower",
        "name": "TerraPower",
        "node_type": "COMPANY",
        "description": "Bill Gates founded. Natrium reactor (sodium-cooled). Kemmerer, WY project. 345 MWe.",
        "aliases": ["Terra Power"],
        "metadata": {
            "layer": "correction",
            "sector": "nuclear_smr",
            "tech": "sodium_fast_reactor",
            "ardp_recipient": True
        }
    },
    {
        "node_id": "x-energy",
        "name": "X-Energy",
        "node_type": "COMPANY",
        "description": "Xe-100 reactor. TRISO fuel manufacturer. DoE ARDP recipient. 80 MWe high-temp gas reactor.",
        "aliases": ["X Energy", "XEnergy"],
        "metadata": {
            "layer": "correction",
            "sector": "nuclear_smr",
            "tech": "htgr",
            "ardp_recipient": True
        }
    },
    {
        "node_id": "kairos-power",
        "name": "Kairos Power",
        "node_type": "COMPANY",
        "description": "Hermes test reactor in Tennessee. Molten salt coolant with TRISO fuel. First new non-LWR construction permit since 1970s.",
        "aliases": ["Kairos"],
        "metadata": {
            "layer": "correction",
            "sector": "nuclear_smr",
            "tech": "molten_salt"
        }
    },
    {
        "node_id": "bwxt",
        "name": "BWX Technologies",
        "node_type": "COMPANY",
        "description": "Nuclear components manufacturer. US Navy reactor supplier. TRISO fuel. Ticker: BWXT.",
        "aliases": ["BWXT", "Babcock & Wilcox"],
        "metadata": {
            "ticker": "BWXT",
            "cik": "0001486957",
            "layer": "correction",
            "sector": "nuclear_components"
        }
    },
    {
        "node_id": "centrus-energy",
        "name": "Centrus Energy",
        "node_type": "COMPANY",
        "description": "HALEU fuel production. Piketon, Ohio facility. Only US commercial HALEU source. Ticker: LEU.",
        "aliases": ["Centrus", "LEU"],
        "metadata": {
            "ticker": "LEU",
            "cik": "0000042291",
            "layer": "correction",
            "sector": "nuclear_fuel"
        }
    },
    {
        "node_id": "constellation-energy",
        "name": "Constellation Energy",
        "node_type": "COMPANY",
        "description": "Largest US nuclear fleet operator. 21 reactors. Ticker: CEG. Three Mile Island restart.",
        "aliases": ["Constellation", "CEG"],
        "metadata": {
            "ticker": "CEG",
            "cik": "0001868275",
            "layer": "correction",
            "sector": "nuclear_utility"
        }
    },
]

NUCLEAR_PERSONS = [
    {
        "node_id": "jay-yu",
        "name": "Jay Yu",
        "node_type": "PERSON",
        "description": "Valar Atomics founder/CEO. SRS #275 guest. Molten salt SMR for data centers. Former SpaceX.",
        "aliases": ["Yu"],
        "metadata": {
            "role": "nuclear_entrepreneur",
            "source": "SRS #275",
            "company": "valar-atomics"
        }
    },
    {
        "node_id": "isaiah-taylor",
        "name": "Isaiah Taylor",
        "node_type": "PERSON",
        "description": "SRS #219 guest. Nuclear policy expert. SMR deployment advocate.",
        "aliases": ["Taylor"],
        "metadata": {
            "role": "nuclear_policy",
            "source": "SRS #219"
        }
    },
    {
        "node_id": "john-hopkins-nuscale",
        "name": "John Hopkins",
        "node_type": "PERSON",
        "description": "NuScale Power CEO. Led company through first SMR design certification.",
        "aliases": [],
        "metadata": {
            "role": "nuclear_executive",
            "company": "nne"
        }
    },
    {
        "node_id": "sam-altman",
        "name": "Sam Altman",
        "node_type": "PERSON",
        "description": "OpenAI CEO. Oklo investor and chairman. Y Combinator former president.",
        "aliases": ["Altman"],
        "metadata": {
            "role": "tech_investor",
            "nuclear_interest": "oklo",
            "other_roles": ["openai_ceo", "yc_president"]
        }
    },
    {
        "node_id": "bill-gates",
        "name": "Bill Gates",
        "node_type": "PERSON",
        "description": "TerraPower founder. Microsoft co-founder. Nuclear energy advocate since 2008.",
        "aliases": ["Gates"],
        "metadata": {
            "role": "tech_investor",
            "nuclear_interest": "terrapower"
        }
    },
]

NUCLEAR_AGENCIES = [
    {
        "node_id": "nrc",
        "name": "Nuclear Regulatory Commission",
        "node_type": "AGENCY",
        "description": "US nuclear regulator. SMR licensing, design certifications, construction permits, operating licenses.",
        "aliases": ["NRC"],
        "metadata": {
            "tier": 0,
            "layer": "regulatory",
            "api": "https://www.nrc.gov/reading-rm/adams.html"
        }
    },
    {
        "node_id": "doe-ne",
        "name": "DOE Office of Nuclear Energy",
        "node_type": "AGENCY",
        "description": "Department of Energy nuclear office. ARDP grants. HALEU funding. SMR deployment support.",
        "aliases": ["DOE Nuclear", "Office of Nuclear Energy"],
        "metadata": {
            "tier": 0,
            "layer": "regulatory",
            "parent": "doe",
            "api": "https://www.energy.gov/ne"
        }
    },
]

NUCLEAR_TECHNOLOGIES = [
    {
        "node_id": "smr-technology",
        "name": "Small Modular Reactor",
        "node_type": "TECHNOLOGY",
        "description": "Nuclear reactors <300 MWe designed for factory fabrication. Modular deployment. Passive safety.",
        "aliases": ["SMR", "Small Modular Reactors"],
        "metadata": {
            "type": "technology",
            "sector": "nuclear",
            "power_range": "<300 MWe"
        }
    },
    {
        "node_id": "triso-fuel",
        "name": "TRISO Fuel",
        "node_type": "TECHNOLOGY",
        "description": "Tri-structural isotropic particle fuel. Uranium kernel in ceramic/carbon layers. Accident-tolerant to 1600C.",
        "aliases": ["TRISO", "Tristructural-isotropic"],
        "metadata": {
            "type": "technology",
            "sector": "nuclear_fuel"
        }
    },
    {
        "node_id": "haleu",
        "name": "HALEU",
        "node_type": "TECHNOLOGY",
        "description": "High-Assay Low-Enriched Uranium. 5-20% U-235. Required by most advanced reactors. Limited supply.",
        "aliases": ["High-Assay LEU"],
        "metadata": {
            "type": "technology",
            "sector": "nuclear_fuel",
            "enrichment": "5-20%"
        }
    },
    {
        "node_id": "molten-salt-reactor",
        "name": "Molten Salt Reactor",
        "node_type": "TECHNOLOGY",
        "description": "MSR technology. Fuel dissolved in molten salt or solid fuel with molten salt coolant. Valar, Kairos.",
        "aliases": ["MSR", "Molten Salt"],
        "metadata": {
            "type": "technology",
            "sector": "nuclear"
        }
    },
]

NUCLEAR_POLICIES = [
    {
        "node_id": "trump-nuclear-eo",
        "name": "Trump Nuclear Executive Order",
        "node_type": "POLICY",
        "description": "Executive order mandating NRC reactor permit approvals. Fast-track SMR deployment. July 4 deadline.",
        "aliases": ["Nuclear EO"],
        "metadata": {
            "type": "executive_order",
            "layer": "correction",
            "effect": "nrc_fast_track"
        }
    },
    {
        "node_id": "ardp",
        "name": "Advanced Reactor Demonstration Program",
        "node_type": "POLICY",
        "description": "DoE program funding advanced reactor deployment. $2.5B total. X-Energy and TerraPower primary recipients.",
        "aliases": ["ARDP"],
        "metadata": {
            "type": "program",
            "agency": "doe-ne",
            "funding": "$2.5B"
        }
    },
    {
        "node_id": "neica",
        "name": "Nuclear Energy Innovation Capabilities Act",
        "node_type": "POLICY",
        "description": "2018 law enabling advanced reactor testing at national labs. Versatile Test Reactor authorization.",
        "aliases": ["NEICA"],
        "metadata": {
            "type": "legislation",
            "year": 2018
        }
    },
    {
        "node_id": "advance-act",
        "name": "ADVANCE Act",
        "node_type": "POLICY",
        "description": "2024 law reforming NRC licensing. Fee reform. International coordination. Advanced reactor acceleration.",
        "aliases": ["Accelerating Deployment of Versatile Advanced Nuclear for Clean Energy Act"],
        "metadata": {
            "type": "legislation",
            "year": 2024
        }
    },
]


# =============================================================================
# NUCLEAR SECTOR EDGES
# =============================================================================

NUCLEAR_EDGES = [
    # Persons → Companies
    ("jay-yu", "valar-atomics", "FOUNDED", 0.95, "TIER_2", "SRS #275 interview"),
    ("sam-altman", "oklo", "INVESTED_IN", 0.90, "TIER_1", "Oklo chairman"),
    ("bill-gates", "terrapower", "FOUNDED", 0.95, "TIER_1", "TerraPower founder"),
    ("john-hopkins-nuscale", "nne", "EMPLOYED", 0.95, "TIER_1", "NuScale CEO"),

    # Companies → Technology
    ("nne", "smr-technology", "DEVELOPS", 0.95, "TIER_0", "First NRC-certified SMR design"),
    ("oklo", "smr-technology", "DEVELOPS", 0.90, "TIER_1", "Aurora microreactor"),
    ("valar-atomics", "molten-salt-reactor", "DEVELOPS", 0.85, "TIER_2", "Molten salt SMR"),
    ("terrapower", "smr-technology", "DEVELOPS", 0.90, "TIER_1", "Natrium reactor"),
    ("kairos-power", "molten-salt-reactor", "DEVELOPS", 0.90, "TIER_0", "Hermes test reactor"),
    ("x-energy", "triso-fuel", "MANUFACTURES", 0.90, "TIER_0", "TRISO fuel facility"),
    ("bwxt", "triso-fuel", "MANUFACTURES", 0.90, "TIER_0", "TRISO fuel production"),
    ("centrus-energy", "haleu", "MANUFACTURES", 0.95, "TIER_0", "Only US commercial HALEU"),

    # Companies → Agencies (Regulatory)
    ("nne", "nrc", "LICENSED_BY", 0.95, "TIER_0", "First SMR design certification 2020"),
    ("terrapower", "nrc", "PERMITTED_BY", 0.80, "TIER_0", "Kemmerer construction permit app"),
    ("kairos-power", "nrc", "PERMITTED_BY", 0.90, "TIER_0", "Hermes construction permit 2023"),
    ("x-energy", "doe-ne", "FUNDED_BY", 0.95, "TIER_0", "ARDP $1.2B award"),
    ("terrapower", "doe-ne", "FUNDED_BY", 0.95, "TIER_0", "ARDP $1.2B award"),
    ("centrus-energy", "doe-ne", "FUNDED_BY", 0.90, "TIER_0", "HALEU demonstration contract"),

    # Policy → Agency
    ("trump-nuclear-eo", "nrc", "DIRECTS", 0.90, "TIER_1", "Fast-track permits mandate"),
    ("ardp", "doe-ne", "AUTHORIZED_BY", 0.95, "TIER_0", "Advanced reactor funding program"),
    ("advance-act", "nrc", "REFORMS", 0.90, "TIER_0", "NRC licensing reform"),

    # Utility → Technology
    ("constellation-energy", "smr-technology", "OPERATES", 0.70, "TIER_2", "Potential SMR deployment"),

    # Technology → Technology (dependency)
    ("smr-technology", "haleu", "REQUIRES", 0.85, "TIER_1", "Most SMR designs need HALEU fuel"),
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
        INSERT INTO edges (from_node_id, to_node_id, edge_type, confidence, assertion_level, notes, created_at, sha256)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (from_id, to_id, edge_type, confidence, tier, notes, datetime.utcnow().isoformat() + "Z", sha256))

    print(f"  ADDED EDGE: {from_id} -[{edge_type}]-> {to_id}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Add Nuclear SMR Sector to FGIP")
    parser.add_argument("db_path", help="Path to FGIP database")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be added")
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}")
        return 1

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    print("="*60)
    print("FGIP NUCLEAR SMR SECTOR")
    print("="*60)
    print("\nThesis: Reshoring → Power → SMR = Correction Layer Infrastructure")

    nodes_added = 0
    edges_added = 0

    # Add companies
    print("\n[NUCLEAR COMPANIES]")
    for node in NUCLEAR_COMPANIES:
        if add_node(conn, node, args.dry_run):
            nodes_added += 1

    # Add persons
    print("\n[NUCLEAR PERSONS]")
    for node in NUCLEAR_PERSONS:
        if add_node(conn, node, args.dry_run):
            nodes_added += 1

    # Add agencies
    print("\n[NUCLEAR AGENCIES]")
    for node in NUCLEAR_AGENCIES:
        if add_node(conn, node, args.dry_run):
            nodes_added += 1

    # Add technologies
    print("\n[NUCLEAR TECHNOLOGIES]")
    for node in NUCLEAR_TECHNOLOGIES:
        if add_node(conn, node, args.dry_run):
            nodes_added += 1

    # Add policies
    print("\n[NUCLEAR POLICIES]")
    for node in NUCLEAR_POLICIES:
        if add_node(conn, node, args.dry_run):
            nodes_added += 1

    if not args.dry_run:
        conn.commit()

    # Add edges
    print("\n[NUCLEAR EDGES]")
    for edge in NUCLEAR_EDGES:
        if add_edge(conn, edge, args.dry_run):
            edges_added += 1

    if not args.dry_run:
        conn.commit()

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Nodes added: {nodes_added}")
    print(f"Edges added: {edges_added}")

    if args.dry_run:
        print("\n(DRY RUN - no changes made)")
    else:
        print("\nNuclear sector loaded:")
        print("  Companies: NuScale, Oklo, Valar Atomics, TerraPower, X-Energy, Kairos, BWXT, Centrus, Constellation")
        print("  Persons: Jay Yu (SRS #275), Isaiah Taylor (SRS #219), Sam Altman, Bill Gates")
        print("  Agencies: NRC, DoE Nuclear Energy")
        print("  Technologies: SMR, TRISO, HALEU, Molten Salt")
        print("  Policies: Trump Nuclear EO, ARDP, NEICA, ADVANCE Act")

    conn.close()
    return 0


if __name__ == "__main__":
    exit(main())
