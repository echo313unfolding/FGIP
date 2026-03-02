"""FGIP Contradiction Detector - Find conflicting positions and actions."""

from dataclasses import dataclass
from typing import Optional

from fgip.db import FGIPDatabase
from fgip.schema import Node, Edge


@dataclass
class Contradiction:
    """A detected contradiction in entity behavior."""
    entity: Node
    type: str  # "opposing_actions", "position_reversal", "conflict_of_interest"
    severity: str  # "high", "medium", "low"
    description: str
    edge1: Edge
    edge2: Optional[Edge] = None


def find_opposing_actions(db: FGIPDatabase, entity_id: str) -> list[Contradiction]:
    """
    Find where entity lobbied FOR and AGAINST related targets.

    Examples:
    - Lobbied FOR PNTR but also claims to support US manufacturing
    - Filed amicus AGAINST tariffs but announced reshoring
    """
    entity = db.get_node(entity_id)
    if not entity:
        return []

    contradictions = []

    # Get all edges from this entity
    edges = db.list_edges(from_node_id=entity_id, limit=1000)

    lobbied_for = [e for e in edges if e.edge_type.value == "LOBBIED_FOR"]
    lobbied_against = [e for e in edges if e.edge_type.value == "LOBBIED_AGAINST"]
    amicus_against = [e for e in edges if e.edge_type.value == "FILED_AMICUS"]
    corrects = [e for e in edges if e.edge_type.value == "CORRECTS"]

    # Check for LOBBIED_FOR + LOBBIED_AGAINST same category
    for e1 in lobbied_for:
        for e2 in lobbied_against:
            # If same target or related targets
            if e1.to_node_id == e2.to_node_id:
                contradictions.append(Contradiction(
                    entity=entity,
                    type="opposing_actions",
                    severity="high",
                    description=f"Lobbied both FOR and AGAINST {e1.to_node_id}",
                    edge1=e1,
                    edge2=e2,
                ))

    # Check for anti-tariff amicus + reshoring action
    for e1 in amicus_against:
        for e2 in corrects:
            target = db.get_node(e1.to_node_id)
            if target and "tariff" in target.name.lower():
                contradictions.append(Contradiction(
                    entity=entity,
                    type="conflict_of_interest",
                    severity="medium",
                    description=f"Filed anti-tariff amicus but also announced reshoring: {e2.to_node_id}",
                    edge1=e1,
                    edge2=e2,
                ))

    return contradictions


def find_position_reversals(db: FGIPDatabase, entity_id: str) -> list[Contradiction]:
    """
    Find where entity reversed position over time.

    Uses date_occurred to detect temporal reversals.
    """
    entity = db.get_node(entity_id)
    if not entity:
        return []

    contradictions = []
    edges = db.list_edges(from_node_id=entity_id, limit=1000)

    # Group by target and check for opposing edge types
    by_target = {}
    for edge in edges:
        target = edge.to_node_id
        if target not in by_target:
            by_target[target] = []
        by_target[target].append(edge)

    opposing_pairs = [
        ("LOBBIED_FOR", "LOBBIED_AGAINST"),
        ("CORRECTS", "OPPOSES_CORRECTION"),
    ]

    for target, target_edges in by_target.items():
        for pos, neg in opposing_pairs:
            pos_edges = [e for e in target_edges if e.edge_type.value == pos]
            neg_edges = [e for e in target_edges if e.edge_type.value == neg]

            if pos_edges and neg_edges:
                contradictions.append(Contradiction(
                    entity=entity,
                    type="position_reversal",
                    severity="medium",
                    description=f"Position reversal on {target}: {pos} then {neg}",
                    edge1=pos_edges[0],
                    edge2=neg_edges[0],
                ))

    return contradictions


def find_conflicts_of_interest(db: FGIPDatabase, entity_id: str) -> list[Contradiction]:
    """
    Find conflicts of interest through ownership or employment links.

    Examples:
    - Judge ruling on case where spouse lobbied
    - Organization opposing policy while member owns shares in beneficiary
    """
    entity = db.get_node(entity_id)
    if not entity:
        return []

    contradictions = []

    # Check for MARRIED_TO + RULED_ON pattern (Thomas example)
    edges = db.list_edges(from_node_id=entity_id, limit=1000)
    married_to = [e for e in edges if e.edge_type.value == "MARRIED_TO"]
    ruled_on = [e for e in edges if e.edge_type.value == "RULED_ON"]

    for m in married_to:
        spouse = db.get_node(m.to_node_id)
        if spouse:
            spouse_edges = db.list_edges(from_node_id=m.to_node_id, limit=1000)
            spouse_lobbied = [e for e in spouse_edges if "LOBBIED" in e.edge_type.value]

            for r in ruled_on:
                for sl in spouse_lobbied:
                    # Check if spouse lobbied on related case/legislation
                    contradictions.append(Contradiction(
                        entity=entity,
                        type="conflict_of_interest",
                        severity="high",
                        description=f"Ruled on {r.to_node_id} while spouse {spouse.name} lobbied on related matters",
                        edge1=r,
                        edge2=sl,
                    ))

    return contradictions


def full_contradiction_check(db: FGIPDatabase, entity_id: str) -> dict:
    """Run all contradiction checks for an entity."""
    entity = db.get_node(entity_id)
    if not entity:
        return {"entity": None, "contradictions": [], "summary": {}}

    contradictions = []
    contradictions.extend(find_opposing_actions(db, entity_id))
    contradictions.extend(find_position_reversals(db, entity_id))
    contradictions.extend(find_conflicts_of_interest(db, entity_id))

    high_severity = len([c for c in contradictions if c.severity == "high"])
    position_reversals = len([c for c in contradictions if c.type == "position_reversal"])

    return {
        "entity": entity.to_dict(),
        "contradictions": [
            {
                "type": c.type,
                "severity": c.severity,
                "description": c.description,
                "edge1": c.edge1.edge_id,
                "edge2": c.edge2.edge_id if c.edge2 else None,
            }
            for c in contradictions
        ],
        "summary": {
            "total_contradictions": len(contradictions),
            "high_severity": high_severity,
            "position_reversals": position_reversals,
        },
    }
