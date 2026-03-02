#!/usr/bin/env python3
"""Easter Egg Verification Script for FGIP Agents.

Verifies that agents are discovering known-true facts (easter eggs).
If agents find these facts, the pipeline is working correctly.
If not, we know what's broken.

Usage:
    python3 tools/verify_easter_eggs.py
    python3 tools/verify_easter_eggs.py --verbose
    python3 tools/verify_easter_eggs.py --check-proposals
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fgip.db import FGIPDatabase


# Easter Eggs: Known-true facts that agents MUST discover
# These are verifiable via public government sources

EASTER_EGGS = [
    # ===== USASpending Easter Eggs =====
    # Source: commerce.gov press releases, usaspending.gov
    {
        "id": "usaspending-intel-chips",
        "description": "Intel received CHIPS Act preliminary award ~$8.5B",
        "edge": {
            "from": "chips-act",
            "edge_type": "AWARDED_GRANT",
            "to": "intel",
        },
        "metadata_contains": {"amount": "8"},  # Partial match on amount
        "agent": "usaspending",
        "source_tier": 0,
        "verification_url": "https://www.commerce.gov/news/press-releases/2024/03/biden-harris-administration-announces-preliminary-terms-intel-receive",
    },
    {
        "id": "usaspending-tsmc-chips",
        "description": "TSMC Arizona received CHIPS Act preliminary award ~$6.6B",
        "edge": {
            "from": "chips-act",
            "edge_type": "AWARDED_GRANT",
            "to": "tsmc",
        },
        "agent": "usaspending",
        "source_tier": 0,
        "verification_url": "https://www.commerce.gov/news/press-releases/2024/04/biden-harris-administration-announces-preliminary-terms-tsmc",
    },
    {
        "id": "usaspending-samsung-chips",
        "description": "Samsung Texas received CHIPS Act preliminary award ~$6.4B",
        "edge": {
            "from": "chips-act",
            "edge_type": "AWARDED_GRANT",
            "to": "samsung",
        },
        "agent": "usaspending",
        "source_tier": 0,
        "verification_url": "https://www.commerce.gov/news/press-releases/2024/04/biden-harris-administration-announces-preliminary-terms-samsung",
    },

    # ===== EDGAR Easter Eggs =====
    # Source: SEC EDGAR 13F filings
    {
        "id": "edgar-vanguard-intel",
        "description": "Vanguard holds Intel shares (13F filing)",
        "edge": {
            "from": "vanguard",
            "edge_type": "OWNS_SHARES",
            "to": "intel",
        },
        "agent": "edgar",
        "source_tier": 0,
        "verification_url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000102909&type=13F",
    },
    {
        "id": "edgar-blackrock-nucor",
        "description": "BlackRock holds Nucor shares (13F filing)",
        "edge": {
            "from": "blackrock",
            "edge_type": "OWNS_SHARES",
            "to": "nucor",
        },
        "agent": "edgar",
        "source_tier": 0,
    },
    {
        "id": "edgar-statestreet-caterpillar",
        "description": "State Street holds Caterpillar shares (13F filing)",
        "edge": {
            "from": "state-street",
            "edge_type": "OWNS_SHARES",
            "to": "caterpillar",
        },
        "agent": "edgar",
        "source_tier": 0,
    },

    # ===== Federal Register Easter Eggs =====
    # Source: federalregister.gov
    {
        "id": "fedreg-genius-fdic",
        "description": "GENIUS Act implementation rule by FDIC",
        "edge": {
            "from": "genius-act",
            "edge_type": "IMPLEMENTED_BY",
            "to": "fdic",
        },
        "agent": "federal_register",
        "source_tier": 0,
    },
    {
        "id": "fedreg-chips-commerce",
        "description": "CHIPS Act incentives final rule by Commerce",
        "edge": {
            "from": "chips-act",
            "edge_type": "IMPLEMENTED_BY",  # Also accepts RULEMAKING_FOR
            "to": "commerce",
        },
        "agent": "federal_register",
        "source_tier": 0,
        "alternate_to_nodes": ["commerce-department", "commerce-dept", "department-of-commerce"],
        "alternate_edge_types": ["RULEMAKING_FOR"],
    },

    # ===== Dark Money / FEC Easter Eggs =====
    # Source: ProPublica 990s, FEC.gov
    {
        "id": "darkmoney-chamber-501c4",
        "description": "US Chamber of Commerce 501(c)(4) status",
        "node": {
            "node_id": "us-chamber-of-commerce",
            "node_type": "ORGANIZATION",
        },
        "agent": "dark_money",
        "source_tier": 1,
    },
    {
        "id": "darkmoney-clubforgrowth-pac",
        "description": "Club for Growth independent expenditures (FEC)",
        "edge": {
            "from": "club-for-growth",
            "edge_type": "DONATED_TO",
            "to": None,  # Any target is fine
        },
        "agent": "dark_money",
        "source_tier": 1,
    },
]


def normalize_node_id(node_id: str) -> str:
    """Normalize node ID for comparison."""
    if not node_id:
        return ""
    return node_id.lower().replace(" ", "-").replace("_", "-")


def check_edge_in_production(conn, edge_spec: Dict[str, Any]) -> Optional[Dict]:
    """Check if an edge exists in production edges table.

    Args:
        conn: Database connection
        edge_spec: Edge specification with from, edge_type, to

    Returns:
        Matching edge row or None
    """
    from_node = normalize_node_id(edge_spec["from"])
    to_node = normalize_node_id(edge_spec.get("to", ""))
    edge_type = edge_spec["edge_type"]

    if to_node:
        query = """
            SELECT * FROM edges
            WHERE (
                LOWER(REPLACE(from_node_id, '_', '-')) = ?
                OR LOWER(REPLACE(from_node_id, '_', '-')) LIKE ?
            )
            AND edge_type = ?
            AND (
                LOWER(REPLACE(to_node_id, '_', '-')) = ?
                OR LOWER(REPLACE(to_node_id, '_', '-')) LIKE ?
            )
        """
        row = conn.execute(query, (
            from_node, f"%{from_node}%",
            edge_type,
            to_node, f"%{to_node}%"
        )).fetchone()
    else:
        # Any target is acceptable
        query = """
            SELECT * FROM edges
            WHERE (
                LOWER(REPLACE(from_node_id, '_', '-')) = ?
                OR LOWER(REPLACE(from_node_id, '_', '-')) LIKE ?
            )
            AND edge_type = ?
        """
        row = conn.execute(query, (
            from_node, f"%{from_node}%",
            edge_type
        )).fetchone()

    return dict(row) if row else None


def check_edge_in_proposals(conn, edge_spec: Dict[str, Any], agent: str = None) -> Optional[Dict]:
    """Check if an edge exists in proposed_edges staging table.

    Args:
        conn: Database connection
        edge_spec: Edge specification with from, edge_type, to
        agent: Optional agent name filter

    Returns:
        Matching proposal row or None
    """
    from_node = normalize_node_id(edge_spec["from"])
    to_node = normalize_node_id(edge_spec.get("to", ""))
    edge_type = edge_spec["edge_type"]

    query = """
        SELECT * FROM proposed_edges
        WHERE (
            LOWER(REPLACE(from_node, '_', '-')) LIKE ?
            OR from_node LIKE ?
        )
        AND relationship = ?
    """
    params = [f"%{from_node}%", f"%{from_node}%", edge_type]

    if to_node:
        query += " AND (LOWER(REPLACE(to_node, '_', '-')) LIKE ? OR to_node LIKE ?)"
        params.extend([f"%{to_node}%", f"%{to_node}%"])

    if agent:
        query += " AND agent_name = ?"
        params.append(agent)

    row = conn.execute(query, params).fetchone()
    return dict(row) if row else None


def check_node_in_production(conn, node_spec: Dict[str, Any]) -> Optional[Dict]:
    """Check if a node exists in production nodes table.

    Args:
        conn: Database connection
        node_spec: Node specification with node_id and optionally node_type

    Returns:
        Matching node row or None
    """
    node_id = normalize_node_id(node_spec["node_id"])

    query = """
        SELECT * FROM nodes
        WHERE LOWER(REPLACE(node_id, '_', '-')) LIKE ?
           OR LOWER(REPLACE(name, ' ', '-')) LIKE ?
    """
    params = [f"%{node_id}%", f"%{node_id}%"]

    if node_spec.get("node_type"):
        query += " AND node_type = ?"
        params.append(node_spec["node_type"])

    row = conn.execute(query, params).fetchone()
    return dict(row) if row else None


def verify_easter_eggs(db_path: str = "fgip.db",
                       check_proposals: bool = False,
                       verbose: bool = False) -> Dict[str, Any]:
    """Verify all easter eggs against the database.

    Args:
        db_path: Path to FGIP database
        check_proposals: Also check staging tables
        verbose: Print detailed output

    Returns:
        Verification results summary
    """
    db = FGIPDatabase(db_path)
    conn = db.connect()

    results = {
        "total": len(EASTER_EGGS),
        "found_production": 0,
        "found_proposals": 0,
        "missing": 0,
        "eggs": [],
    }

    print("\n" + "=" * 60)
    print("FGIP Easter Egg Verification")
    print("=" * 60 + "\n")

    for egg in EASTER_EGGS:
        egg_result = {
            "id": egg["id"],
            "description": egg["description"],
            "agent": egg["agent"],
            "status": "MISSING",
            "location": None,
        }

        # Check for edge-based easter eggs
        if "edge" in egg:
            # Check production first
            found = check_edge_in_production(conn, egg["edge"])
            if found:
                egg_result["status"] = "FOUND_PRODUCTION"
                egg_result["location"] = "edges"
                results["found_production"] += 1
            elif check_proposals:
                # Check staging tables
                found = check_edge_in_proposals(conn, egg["edge"], egg["agent"])
                if found:
                    egg_result["status"] = "FOUND_PROPOSAL"
                    egg_result["location"] = "proposed_edges"
                    results["found_proposals"] += 1

            # Check alternate node names if provided
            if not found and egg.get("alternate_to_nodes"):
                for alt_to in egg["alternate_to_nodes"]:
                    alt_edge = {**egg["edge"], "to": alt_to}
                    found = check_edge_in_production(conn, alt_edge)
                    if found:
                        egg_result["status"] = "FOUND_PRODUCTION"
                        egg_result["location"] = "edges"
                        results["found_production"] += 1
                        break
                    if check_proposals:
                        found = check_edge_in_proposals(conn, alt_edge, egg["agent"])
                        if found:
                            egg_result["status"] = "FOUND_PROPOSAL"
                            egg_result["location"] = "proposed_edges"
                            results["found_proposals"] += 1
                            break

        # Check for node-based easter eggs
        elif "node" in egg:
            found = check_node_in_production(conn, egg["node"])
            if found:
                egg_result["status"] = "FOUND_PRODUCTION"
                egg_result["location"] = "nodes"
                results["found_production"] += 1

        if egg_result["status"] == "MISSING":
            results["missing"] += 1

        results["eggs"].append(egg_result)

        # Print result
        if egg_result["status"] == "FOUND_PRODUCTION":
            status_icon = "✅"
        elif egg_result["status"] == "FOUND_PROPOSAL":
            status_icon = "🔶"
        else:
            status_icon = "❌"

        print(f"{status_icon} [{egg['agent']:15}] {egg['description'][:50]}")

        if verbose:
            if "edge" in egg:
                print(f"   Edge: {egg['edge']['from']} → {egg['edge']['edge_type']} → {egg['edge'].get('to', '*')}")
            if egg_result["location"]:
                print(f"   Found in: {egg_result['location']}")
            print()

    # Summary
    print("\n" + "-" * 60)
    print("SUMMARY")
    print("-" * 60)
    print(f"Total Easter Eggs:    {results['total']}")
    print(f"Found (Production):   {results['found_production']}")
    if check_proposals:
        print(f"Found (Proposals):    {results['found_proposals']}")
    print(f"Missing:              {results['missing']}")
    print()

    found_total = results['found_production'] + results['found_proposals']
    if found_total == results['total']:
        print("✅ ALL EASTER EGGS VERIFIED - Pipeline is working!")
    elif found_total > 0:
        print(f"⚠️  {found_total}/{results['total']} easter eggs found - Pipeline partially working")
    else:
        print("❌ NO EASTER EGGS FOUND - Check agent implementations")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Verify FGIP easter eggs against the database"
    )
    parser.add_argument(
        "--db",
        default="fgip.db",
        help="Path to FGIP database (default: fgip.db)"
    )
    parser.add_argument(
        "--check-proposals",
        action="store_true",
        help="Also check staging/proposal tables"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print detailed output"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )

    args = parser.parse_args()

    results = verify_easter_eggs(
        db_path=args.db,
        check_proposals=args.check_proposals,
        verbose=args.verbose
    )

    if args.json:
        print("\n" + json.dumps(results, indent=2))

    # Exit with error code if missing eggs
    sys.exit(0 if results["missing"] == 0 else 1)


if __name__ == "__main__":
    main()
