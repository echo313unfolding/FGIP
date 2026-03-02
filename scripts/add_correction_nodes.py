#!/usr/bin/env python3
"""
Add missing correction-layer nodes to FGIP graph.

From Kokinda catalog analysis:
- CRITICAL: Bessent, Greer, Warsh (executing Hamiltonian correction)
- HIGH: CFR, Trilateral Commission, Navarro, Lutnick
"""

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


# =============================================================================
# CRITICAL CORRECTION-LAYER NODES
# =============================================================================

CRITICAL_PERSONS = [
    {
        "node_id": "scott-bessent",
        "name": "Scott Bessent",
        "node_type": "PERSON",
        "description": "Treasury Secretary. Hamiltonian economics advocate. 'Grow Baby Grow' Davos speech. Key corrective mechanism executor.",
        "aliases": ["Bessent"],
        "metadata": {
            "role": "treasury_secretary",
            "layer": "correction",
            "appointed": "2025",
            "source": "kokinda_catalog"
        }
    },
    {
        "node_id": "jamieson-greer",
        "name": "Jamieson Greer",
        "node_type": "PERSON",
        "description": "US Trade Representative. American System speech at Davos. Tariff policy executor.",
        "aliases": ["Greer", "Ambassador Greer"],
        "metadata": {
            "role": "ustr",
            "layer": "correction",
            "appointed": "2025",
            "source": "kokinda_catalog"
        }
    },
    {
        "node_id": "kevin-warsh",
        "name": "Kevin Warsh",
        "node_type": "PERSON",
        "description": "Fed Chair nominee. Correction mechanism for central banking capture. 'Declaration of war on Wall Street bailouts.'",
        "aliases": ["Warsh"],
        "metadata": {
            "role": "fed_nominee",
            "layer": "correction",
            "nominated": "2026",
            "source": "kokinda_catalog"
        }
    },
]

HIGH_PRIORITY_PERSONS = [
    {
        "node_id": "peter-navarro",
        "name": "Peter Navarro",
        "node_type": "PERSON",
        "description": "Trade advisor. CFR ambush speech. Australia rare earth deal architect.",
        "aliases": ["Navarro"],
        "metadata": {
            "role": "trade_advisor",
            "layer": "correction",
            "source": "kokinda_catalog"
        }
    },
    {
        "node_id": "howard-lutnick",
        "name": "Howard Lutnick",
        "node_type": "PERSON",
        "description": "Commerce Secretary. Davos team. Cantor Fitzgerald CEO.",
        "aliases": ["Lutnick"],
        "metadata": {
            "role": "commerce_secretary",
            "layer": "correction",
            "source": "kokinda_catalog"
        }
    },
    {
        "node_id": "tulsi-gabbard",
        "name": "Tulsi Gabbard",
        "node_type": "PERSON",
        "description": "DNI. Released explosive documents on Obama administration. Intelligence layer.",
        "aliases": ["Gabbard", "DNI Gabbard"],
        "metadata": {
            "role": "dni",
            "layer": "correction",
            "source": "kokinda_catalog"
        }
    },
    {
        "node_id": "kash-patel",
        "name": "Kash Patel",
        "node_type": "PERSON",
        "description": "FBI Director. MI5 panic trigger. Intelligence restructuring.",
        "aliases": ["Patel"],
        "metadata": {
            "role": "fbi_director",
            "layer": "correction",
            "source": "kokinda_catalog"
        }
    },
]

# =============================================================================
# PROBLEM-LAYER ORGANIZATIONS (Missing)
# =============================================================================

PROBLEM_ORGS = [
    {
        "node_id": "cfr",
        "name": "Council on Foreign Relations",
        "node_type": "ORGANIZATION",
        "description": "Think tank. Navarro ambush speech location. 'Managed decline' policy origin. Founded 1921.",
        "aliases": ["CFR", "Council on Foreign Relations"],
        "metadata": {
            "layer": "problem",
            "founded": "1921",
            "role": "policy_think_tank",
            "source": "kokinda_catalog"
        }
    },
    {
        "node_id": "trilateral-commission",
        "name": "Trilateral Commission",
        "node_type": "ORGANIZATION",
        "description": "1977 deindustrialization blueprint authors. Rubio: 'managed decline was a conscious policy choice.'",
        "aliases": ["Trilateral", "TC"],
        "metadata": {
            "layer": "problem",
            "founded": "1973",
            "role": "policy_coordination",
            "source": "kokinda_catalog"
        }
    },
    {
        "node_id": "business-roundtable",
        "name": "Business Roundtable",
        "node_type": "ORGANIZATION",
        "description": "CEO lobbying coalition. PNTR advocacy. Trade policy influence.",
        "aliases": ["BRT"],
        "metadata": {
            "layer": "problem",
            "founded": "1972",
            "role": "lobbying",
            "source": "kokinda_catalog"
        }
    },
    {
        "node_id": "national-foreign-trade-council",
        "name": "National Foreign Trade Council",
        "node_type": "ORGANIZATION",
        "description": "Trade lobbying organization. Free trade advocacy.",
        "aliases": ["NFTC"],
        "metadata": {
            "layer": "problem",
            "role": "lobbying",
            "source": "kokinda_catalog"
        }
    },
    {
        "node_id": "brennan-center",
        "name": "Brennan Center for Justice",
        "node_type": "ORGANIZATION",
        "description": "2026 midterm wargaming with Whitmer. Election infrastructure focus.",
        "aliases": ["Brennan Center"],
        "metadata": {
            "layer": "problem",
            "role": "election_policy",
            "source": "kokinda_catalog"
        }
    },
]

# =============================================================================
# CORRECTION-LAYER AGENCIES
# =============================================================================

CORRECTION_AGENCIES = [
    {
        "node_id": "fsoc",
        "name": "Financial Stability Oversight Council",
        "node_type": "AGENCY",
        "description": "2025 report prioritizes people over financial parasites. Correction mechanism.",
        "aliases": ["FSOC"],
        "metadata": {
            "layer": "correction",
            "role": "financial_regulation",
            "source": "kokinda_catalog"
        }
    },
    {
        "node_id": "ustr",
        "name": "Office of the US Trade Representative",
        "node_type": "AGENCY",
        "description": "Trade policy execution. Greer appointed.",
        "aliases": ["USTR"],
        "metadata": {
            "layer": "correction",
            "role": "trade_policy",
            "source": "kokinda_catalog"
        }
    },
]

# =============================================================================
# EDGES TO CREATE
# =============================================================================

CORRECTION_EDGES = [
    # Bessent connections
    ("scott-bessent", "treasury-department", "EMPLOYED", 0.95, "FACT", "Treasury Secretary"),
    ("scott-bessent", "tariff-policy", "ADVOCATES", 0.90, "TIER_1", "Hamiltonian economics Davos speech"),

    # Greer connections
    ("jamieson-greer", "ustr", "EMPLOYED", 0.95, "FACT", "US Trade Representative"),
    ("jamieson-greer", "tariff-policy", "ADVOCATES", 0.90, "TIER_1", "American System Davos speech"),

    # Warsh connections
    ("kevin-warsh", "federal-reserve", "NOMINATED", 0.85, "TIER_1", "Fed Chair nominee"),

    # Navarro connections
    ("peter-navarro", "cfr", "CONFRONTED", 0.90, "TIER_2", "CFR ambush speech"),
    ("peter-navarro", "tariff-policy", "ADVOCATES", 0.85, "TIER_1", "Trade policy architect"),

    # Lutnick connections
    ("howard-lutnick", "commerce", "EMPLOYED", 0.95, "FACT", "Commerce Secretary"),

    # CFR connections
    ("cfr", "us-chamber-of-commerce", "COORDINATES_WITH", 0.70, "TIER_2", "Policy alignment"),
    ("cfr", "managed-decline-policy", "AUTHORED", 0.75, "TIER_2", "1977 deindustrialization blueprint"),

    # Trilateral connections
    ("trilateral-commission", "cfr", "COORDINATES_WITH", 0.75, "TIER_2", "Overlapping membership"),

    # FSOC connections
    ("fsoc", "federal-reserve", "OVERSEES", 0.80, "TIER_1", "Financial stability mandate"),
]


def compute_sha256(data: dict) -> str:
    """Compute SHA256 hash of node data."""
    content = json.dumps(data, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()


def add_node(conn: sqlite3.Connection, node: dict, dry_run: bool = False) -> bool:
    """Add a node to the graph if it doesn't exist."""
    cursor = conn.cursor()

    # Check if exists
    existing = cursor.execute(
        "SELECT node_id FROM nodes WHERE node_id = ?",
        (node["node_id"],)
    ).fetchone()

    if existing:
        print(f"  SKIP: {node['node_id']} (already exists)")
        return False

    # Compute hash
    sha256 = compute_sha256(node)

    if dry_run:
        print(f"  WOULD ADD: {node['node_id']} ({node['node_type']})")
        return True

    # Insert
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
    """Add an edge to the graph if it doesn't exist."""
    from_id, to_id, edge_type, confidence, tier, notes = edge
    cursor = conn.cursor()

    # Check if both nodes exist
    from_exists = cursor.execute(
        "SELECT node_id FROM nodes WHERE node_id = ?", (from_id,)
    ).fetchone()
    to_exists = cursor.execute(
        "SELECT node_id FROM nodes WHERE node_id = ?", (to_id,)
    ).fetchone()

    if not from_exists:
        print(f"  SKIP EDGE: {from_id} -> {to_id} (from_node missing)")
        return False
    if not to_exists:
        print(f"  SKIP EDGE: {from_id} -> {to_id} (to_node missing)")
        return False

    # Check if edge exists
    existing = cursor.execute("""
        SELECT edge_id FROM edges
        WHERE from_node_id = ? AND to_node_id = ? AND edge_type = ?
    """, (from_id, to_id, edge_type)).fetchone()

    if existing:
        print(f"  SKIP EDGE: {from_id} -[{edge_type}]-> {to_id} (exists)")
        return False

    if dry_run:
        print(f"  WOULD ADD EDGE: {from_id} -[{edge_type}]-> {to_id}")
        return True

    # Compute hash
    edge_data = {"from": from_id, "to": to_id, "type": edge_type}
    sha256 = compute_sha256(edge_data)

    # Insert
    cursor.execute("""
        INSERT INTO edges (from_node_id, to_node_id, edge_type, confidence, assertion_level, notes, created_at, sha256)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        from_id,
        to_id,
        edge_type,
        confidence,
        tier,
        notes,
        datetime.utcnow().isoformat() + "Z",
        sha256
    ))

    print(f"  ADDED EDGE: {from_id} -[{edge_type}]-> {to_id}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Add correction-layer nodes to FGIP graph")
    parser.add_argument("db_path", help="Path to FGIP database")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be added without modifying")
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}")
        return 1

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    print("="*60)
    print("ADDING CORRECTION-LAYER NODES")
    print("="*60)

    nodes_added = 0
    edges_added = 0

    # Add CRITICAL persons
    print("\n[CRITICAL] Correction Layer Persons:")
    for node in CRITICAL_PERSONS:
        if add_node(conn, node, args.dry_run):
            nodes_added += 1

    # Add HIGH priority persons
    print("\n[HIGH] Additional Persons:")
    for node in HIGH_PRIORITY_PERSONS:
        if add_node(conn, node, args.dry_run):
            nodes_added += 1

    # Add problem-layer organizations
    print("\n[HIGH] Problem Layer Organizations:")
    for node in PROBLEM_ORGS:
        if add_node(conn, node, args.dry_run):
            nodes_added += 1

    # Add correction-layer agencies
    print("\n[HIGH] Correction Layer Agencies:")
    for node in CORRECTION_AGENCIES:
        if add_node(conn, node, args.dry_run):
            nodes_added += 1

    if not args.dry_run:
        conn.commit()

    # Add edges
    print("\n" + "="*60)
    print("ADDING EDGES")
    print("="*60)

    for edge in CORRECTION_EDGES:
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

    conn.close()
    return 0


if __name__ == "__main__":
    exit(main())
