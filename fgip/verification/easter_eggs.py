"""Easter Eggs - Known-true facts for pipeline validation.

Easter eggs are facts that specific agents MUST discover when run.
If an agent runs but fails to produce the expected easter egg,
the agent or data pipeline is broken.

Usage:
    from fgip.verification.easter_eggs import EASTER_EGGS, check_egg, check_all_eggs

    # Check all eggs
    results = check_all_eggs(conn)

    # Check eggs for specific agent
    results = check_all_eggs(conn, agent_name="edgar")
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any


@dataclass
class EasterEgg:
    """A known-true fact that an agent MUST discover."""
    egg_id: str               # e.g., "EE-01"
    agent_name: str           # e.g., "edgar"
    egg_type: str             # "edge" or "topic"

    # For edge-type eggs
    from_node_pattern: Optional[str] = None   # Regex pattern for from_node
    edge_type: Optional[str] = None           # EdgeType value
    to_node_pattern: Optional[str] = None     # Regex pattern for to_node

    # For topic-type eggs
    topic_pattern: Optional[str] = None       # Regex for topic detection

    description: str = ""                     # Human-readable description
    source_tier: int = 0                      # Expected source tier
    verification_hint: str = ""               # What source proves this
    planted_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


# The 8 known-true easter eggs
EASTER_EGGS = [
    # ============ EDGAR Agent (SEC filings) ============
    EasterEgg(
        egg_id="EE-01",
        agent_name="edgar",
        egg_type="edge",
        from_node_pattern=r"vanguard.*",
        edge_type="OWNS_SHARES",
        to_node_pattern=r"intel.*",
        description="Vanguard owns shares in Intel",
        source_tier=0,
        verification_hint="SEC EDGAR 13F filing - Vanguard institutional holdings",
    ),
    EasterEgg(
        egg_id="EE-02",
        agent_name="edgar",
        egg_type="edge",
        from_node_pattern=r"blackrock.*",
        edge_type="OWNS_SHARES",
        to_node_pattern=r"nucor.*",
        description="BlackRock owns shares in Nucor",
        source_tier=0,
        verification_hint="SEC EDGAR 13F filing - BlackRock institutional holdings",
    ),

    # ============ USASpending Agent (federal awards) ============
    EasterEgg(
        egg_id="EE-03",
        agent_name="usaspending",
        egg_type="edge",
        from_node_pattern=r"chips.*act.*",
        edge_type="AWARDED_GRANT",
        to_node_pattern=r"intel.*",
        description="CHIPS Act awarded ~$8.5B preliminary grant to Intel",
        source_tier=0,
        verification_hint="commerce.gov press release March 2024",
    ),
    EasterEgg(
        egg_id="EE-04",
        agent_name="usaspending",
        egg_type="edge",
        from_node_pattern=r"chips.*act.*",
        edge_type="AWARDED_GRANT",
        to_node_pattern=r"tsmc.*",
        description="CHIPS Act awarded ~$6.6B preliminary grant to TSMC Arizona",
        source_tier=0,
        verification_hint="commerce.gov press release April 2024",
    ),

    # ============ Federal Register Agent (rulemaking) ============
    EasterEgg(
        egg_id="EE-05",
        agent_name="federal_register",
        egg_type="edge",
        from_node_pattern=r"fdic.*",
        edge_type="RULEMAKING_FOR",
        to_node_pattern=r"genius.*act.*",
        description="FDIC issued RFI on payment stablecoins after GENIUS Act",
        source_tier=0,
        verification_hint="fdic.gov press release / Federal Register notice",
    ),

    # ============ Dark Money Agent (FEC/990 data) ============
    EasterEgg(
        egg_id="EE-06",
        agent_name="dark_money",
        egg_type="edge",
        from_node_pattern=r"us.*chamber.*commerce.*|chamber.*",
        edge_type="DONATED_TO",
        to_node_pattern=r"chamber.*pac.*",
        description="US Chamber operates political spending arm (Chamber PAC)",
        source_tier=0,
        verification_hint="FEC.gov committee data / OpenSecrets",
    ),

    # ============ RSS Signal Agent (news monitoring) ============
    EasterEgg(
        egg_id="EE-07",
        agent_name="rss",
        egg_type="topic",
        topic_pattern=r"reshoring|domestic.*manufactur|bring.*back.*jobs|onshoring",
        description="Recent news articles about domestic manufacturing/reshoring",
        source_tier=1,
        verification_hint="Reuters/AP/financial press coverage of reshoring trend",
    ),

    # ============ Podcast Agent (long-form content) ============
    EasterEgg(
        egg_id="EE-08",
        agent_name="podcast",
        egg_type="topic",
        topic_pattern=r"tariff|trade.*policy|trade.*war|import.*duty|reshoring",
        description="Recent podcast episodes discussing tariffs/trade policy",
        source_tier=2,
        verification_hint="All-In, Breaking Points, or similar policy podcasts",
    ),
]


def check_egg(conn, egg: EasterEgg) -> Dict[str, Any]:
    """Check if an easter egg has been discovered.

    Looks in both staging tables (proposed_edges) and production tables (edges).

    Args:
        conn: Database connection
        egg: EasterEgg to check

    Returns:
        Dict with: found, in_staging, in_production, proposal_id, edge_id, details
    """
    result = {
        "egg_id": egg.egg_id,
        "agent": egg.agent_name,
        "description": egg.description,
        "found": False,
        "in_staging": False,
        "in_production": False,
        "proposal_id": None,
        "edge_id": None,
        "claim_id": None,
        "details": [],
    }

    if egg.egg_type == "edge":
        # Check proposed_edges (staging)
        rows = conn.execute(
            """SELECT proposal_id, from_node, to_node, relationship, proposed_claim_id, status
               FROM proposed_edges
               WHERE agent_name = ? AND relationship = ?""",
            (egg.agent_name, egg.edge_type)
        ).fetchall()

        for row in rows:
            from_match = re.search(egg.from_node_pattern, row["from_node"], re.IGNORECASE)
            to_match = re.search(egg.to_node_pattern, row["to_node"], re.IGNORECASE)

            if from_match and to_match:
                result["found"] = True
                result["in_staging"] = True
                result["proposal_id"] = row["proposal_id"]
                result["claim_id"] = row["proposed_claim_id"]
                result["details"].append({
                    "source": "staging",
                    "status": row["status"],
                    "from_node": row["from_node"],
                    "to_node": row["to_node"],
                })
                break

        # Check production edges
        rows = conn.execute(
            """SELECT edge_id, from_node_id, to_node_id, edge_type, claim_id
               FROM edges
               WHERE edge_type = ?""",
            (egg.edge_type,)
        ).fetchall()

        for row in rows:
            from_match = re.search(egg.from_node_pattern, row["from_node_id"], re.IGNORECASE)
            to_match = re.search(egg.to_node_pattern, row["to_node_id"], re.IGNORECASE)

            if from_match and to_match:
                result["found"] = True
                result["in_production"] = True
                result["edge_id"] = row["edge_id"]
                result["claim_id"] = row["claim_id"]
                result["details"].append({
                    "source": "production",
                    "edge_id": row["edge_id"],
                    "from_node": row["from_node_id"],
                    "to_node": row["to_node_id"],
                })
                break

    elif egg.egg_type == "topic":
        # Check proposed_claims for topic mentions
        rows = conn.execute(
            """SELECT proposal_id, claim_text, topic, status
               FROM proposed_claims
               WHERE agent_name = ?""",
            (egg.agent_name,)
        ).fetchall()

        for row in rows:
            topic_match = re.search(egg.topic_pattern, row["claim_text"], re.IGNORECASE)
            if not topic_match:
                topic_match = re.search(egg.topic_pattern, row["topic"] or "", re.IGNORECASE)

            if topic_match:
                result["found"] = True
                result["in_staging"] = True
                result["proposal_id"] = row["proposal_id"]
                result["details"].append({
                    "source": "staging",
                    "status": row["status"],
                    "claim_text": row["claim_text"][:100] + "..." if len(row["claim_text"]) > 100 else row["claim_text"],
                    "topic": row["topic"],
                })
                break

        # Check production claims
        rows = conn.execute(
            """SELECT claim_id, claim_text, topic
               FROM claims"""
        ).fetchall()

        for row in rows:
            topic_match = re.search(egg.topic_pattern, row["claim_text"], re.IGNORECASE)
            if not topic_match:
                topic_match = re.search(egg.topic_pattern, row["topic"] or "", re.IGNORECASE)

            if topic_match:
                result["found"] = True
                result["in_production"] = True
                result["claim_id"] = row["claim_id"]
                result["details"].append({
                    "source": "production",
                    "claim_id": row["claim_id"],
                    "claim_text": row["claim_text"][:100] + "..." if len(row["claim_text"]) > 100 else row["claim_text"],
                    "topic": row["topic"],
                })
                break

    return result


def check_all_eggs(conn, agent_name: Optional[str] = None) -> Dict[str, Any]:
    """Check all easter eggs, optionally filtered by agent.

    Args:
        conn: Database connection
        agent_name: Optional filter by agent

    Returns:
        Dict with: total, found, missing, by_agent, results
    """
    eggs_to_check = EASTER_EGGS
    if agent_name:
        eggs_to_check = [e for e in EASTER_EGGS if e.agent_name == agent_name]

    results = []
    for egg in eggs_to_check:
        result = check_egg(conn, egg)
        results.append(result)

    found = sum(1 for r in results if r["found"])
    missing = [r["egg_id"] for r in results if not r["found"]]

    # Group by agent
    by_agent = {}
    for egg in eggs_to_check:
        if egg.agent_name not in by_agent:
            by_agent[egg.agent_name] = {"total": 0, "found": 0, "missing": []}
        by_agent[egg.agent_name]["total"] += 1

    for r in results:
        agent = r["agent"]
        if r["found"]:
            by_agent[agent]["found"] += 1
        else:
            by_agent[agent]["missing"].append(r["egg_id"])

    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "total": len(eggs_to_check),
        "found": found,
        "missing": missing,
        "by_agent": by_agent,
        "results": results,
    }


def get_eggs_for_agent(agent_name: str) -> List[EasterEgg]:
    """Get all easter eggs for a specific agent."""
    return [e for e in EASTER_EGGS if e.agent_name == agent_name]
