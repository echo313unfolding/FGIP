#!/usr/bin/env python3
"""
Add Operational Intelligence Layer to FGIP graph.

The FGIP Operational Triad:
- DETECT (Hughes): Identify narrative manipulation via psyop detection
- DECODE (Greene): Understand power mechanics via 48 Laws
- DEFEND (Luna): Protect assets from documented extraction

These methodology nodes transform the graph from "what happened" into "what to do about it."
"""

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path


# =============================================================================
# OPERATIONAL INTELLIGENCE NODES
# =============================================================================

METHODOLOGY_SOURCES = [
    {
        "node_id": "person-chase-hughes",
        "name": "Chase Hughes",
        "node_type": "PERSON",
        "description": "Navy Chief (20yr), HUMINT behavioral scientist. SRS #253 guest. IRONCLAD PSYOP docuseries creator. Key heuristic: 'if an opinion must be silenced for another to flourish, you are in a psyop.'",
        "aliases": ["Hughes", "Chase Hughes"],
        "metadata": {
            "role": "methodology_source",
            "layer": "psyop_detection",
            "tier": "T2",
            "source": "Shawn Ryan Show #253, IRONCLAD PSYOP docuseries",
            "books": ["The Ellipsis Manual", "The Behavior Operations Manual"]
        }
    },
    {
        "node_id": "person-robert-greene",
        "name": "Robert Greene",
        "node_type": "PERSON",
        "description": "Strategist. Author of 48 Laws of Power, 33 Strategies of War, Laws of Human Nature. Distills 3000 years of power dynamics into actionable frameworks.",
        "aliases": ["Greene", "Robert Greene"],
        "metadata": {
            "role": "methodology_source",
            "layer": "power_analysis",
            "tier": "T2",
            "books": ["48 Laws of Power", "33 Strategies of War", "Laws of Human Nature", "Mastery"]
        }
    },
    {
        "node_id": "person-jj-luna",
        "name": "J.J. Luna",
        "node_type": "PERSON",
        "description": "Privacy/asset protection consultant. 50+ years experience. Expert in ghost addresses, LLC shielding, nominee structures, low-profile banking.",
        "aliases": ["Luna", "J.J. Luna"],
        "metadata": {
            "role": "methodology_source",
            "layer": "asset_protection",
            "tier": "T2",
            "books": ["How to Be Invisible (3rd ed)", "Invisible Money", "Off the Grid"],
            "legal_note": "All methods legal - emphasizes law-abiding approach"
        }
    },
]

METHODOLOGY_FRAMEWORKS = [
    {
        "node_id": "methodology-psyop-detection",
        "name": "FGIP Psyop Detection Framework",
        "node_type": "METHODOLOGY",
        "description": "Hughes NCI framework for FGIP. 5 detection criteria: (1) Opinion Suppression - dismissal over data, (2) Identity Capture - belief as identity, (3) Authority Exploitation - credentials bypass data, (4) Algorithmic Caging - media restricts counter-evidence, (5) Hughes Master Test - 'if an opinion must be silenced, you're in a psyop.' Counter-narrative scoring >= 3 = HIGH SIGNAL.",
        "aliases": ["psyop_detection", "narrative_control_detection"],
        "metadata": {
            "layer": "meta_analysis",
            "source": "Hughes NCI",
            "criteria_count": 5,
            "application": "Score counter-narratives. >= 3 markers = suppressed truth = increase thesis confidence"
        }
    },
    {
        "node_id": "methodology-power-analysis",
        "name": "FGIP Power Dynamics Framework",
        "node_type": "METHODOLOGY",
        "description": "Greene's laws applied to FGIP institutional capture. Law 3 (Conceal Intentions) = Chamber PNTR lobbying. Law 11 (Keep Dependent) = revolving door. Law 15 (Crush Totally) = 37 vs 7 amicus. Law 23 (Concentrate Forces) = Big Three 20% passive. Law 31 (Control Options) = CPI binary. Strategy 2 (Don't Fight Last War) = GENIUS flanks Fed.",
        "aliases": ["power_analysis", "greene_framework"],
        "metadata": {
            "layer": "meta_analysis",
            "source": "48 Laws of Power, 33 Strategies of War",
            "application": "Identify which law explains entity behavior to predict next moves"
        }
    },
    {
        "node_id": "methodology-asset-protection",
        "name": "FGIP Personal Protection Framework",
        "node_type": "METHODOLOGY",
        "description": "Luna privacy doctrine for FGIP extraction environment. 6 layers: L1-Banking (HYSA), L2-LLC Shielding (NM/WY), L3-Ghost Address, L4-Income Diversification, L5-Jurisdictional, L6-Inflation Hedge (M2=6.3% not CPI=2.7%). Not hiding from law - hiding from the extraction system FGIP documents.",
        "aliases": ["asset_protection", "luna_framework", "operational_security"],
        "metadata": {
            "layer": "personal_protection",
            "source": "How to Be Invisible",
            "application": "Apply to personal_runway calculations. Question: how to HOLD assets, not just what to buy"
        }
    },
    {
        "node_id": "methodology-operational-triad",
        "name": "FGIP Operational Triad",
        "node_type": "METHODOLOGY",
        "description": "DETECT (Hughes) - identify narrative manipulation. DECODE (Greene) - understand power mechanics. DEFEND (Luna) - protect from documented extraction. Together: survive and prosper during the correction transition.",
        "aliases": ["operational_triad", "detect_decode_defend"],
        "metadata": {
            "layer": "meta_framework",
            "components": ["Hughes/DETECT", "Greene/DECODE", "Luna/DEFEND"]
        }
    },
]

# =============================================================================
# EDGES
# =============================================================================

METHODOLOGY_EDGES = [
    # Source → Framework
    ("person-chase-hughes", "methodology-psyop-detection", "METHODOLOGY_SOURCE", 0.90, "TIER_2", "Hughes NCI framework provides detection heuristics"),
    ("person-robert-greene", "methodology-power-analysis", "METHODOLOGY_SOURCE", 0.90, "TIER_2", "Greene 48 Laws explain entity behavior patterns"),
    ("person-jj-luna", "methodology-asset-protection", "METHODOLOGY_SOURCE", 0.90, "TIER_2", "Luna privacy doctrine for defensive application"),

    # Triad connections
    ("methodology-psyop-detection", "methodology-operational-triad", "COMPONENT_OF", 0.95, "TIER_2", "DETECT component"),
    ("methodology-power-analysis", "methodology-operational-triad", "COMPONENT_OF", 0.95, "TIER_2", "DECODE component"),
    ("methodology-asset-protection", "methodology-operational-triad", "COMPONENT_OF", 0.95, "TIER_2", "DEFEND component"),

    # Applications
    ("methodology-psyop-detection", "bls", "ANALYZES", 0.85, "TIER_2", "CPI methodology change exhibits all 5 psyop markers"),
    ("methodology-power-analysis", "us-chamber-of-commerce", "ANALYZES", 0.80, "TIER_2", "Chamber behavior = Law 3 (Conceal Intentions) + Law 25 (Re-Create Yourself)"),
    ("methodology-power-analysis", "blackrock", "ANALYZES", 0.80, "TIER_2", "Big Three = Law 23 (Concentrate Forces via passive mechanism)"),

    # Media sources
    ("person-chase-hughes", "media-shawn-ryan-show", "APPEARED_ON", 0.95, "TIER_2", "SRS #253 guest, IRONCLAD PSYOP docuseries"),
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
    parser = argparse.ArgumentParser(description="Add Operational Intelligence Layer to FGIP")
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
    print("FGIP OPERATIONAL INTELLIGENCE LAYER")
    print("="*60)
    print("\nDETECT (Hughes) → DECODE (Greene) → DEFEND (Luna)")

    nodes_added = 0
    edges_added = 0

    # Add methodology sources (persons)
    print("\n[METHODOLOGY SOURCES]")
    for node in METHODOLOGY_SOURCES:
        if add_node(conn, node, args.dry_run):
            nodes_added += 1

    # Add methodology frameworks
    print("\n[METHODOLOGY FRAMEWORKS]")
    for node in METHODOLOGY_FRAMEWORKS:
        if add_node(conn, node, args.dry_run):
            nodes_added += 1

    if not args.dry_run:
        conn.commit()

    # Add edges
    print("\n[METHODOLOGY EDGES]")
    for edge in METHODOLOGY_EDGES:
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
        print("\nOperational Triad loaded:")
        print("  • methodology-psyop-detection (DETECT)")
        print("  • methodology-power-analysis (DECODE)")
        print("  • methodology-asset-protection (DEFEND)")

    conn.close()
    return 0


if __name__ == "__main__":
    exit(main())
