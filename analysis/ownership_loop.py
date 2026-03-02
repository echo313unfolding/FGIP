"""FGIP Ownership Loop - Detect circular ownership structures."""

from dataclasses import dataclass
from typing import Optional

from fgip.db import FGIPDatabase
from fgip.schema import Node, Edge


@dataclass
class OwnershipLoop:
    """A circular ownership structure in the graph."""
    nodes: list[Node]
    edges: list[Edge]
    total_stake: float

    def __len__(self):
        return len(self.edges)

    def describe(self) -> str:
        """Human-readable loop description."""
        names = [n.name for n in self.nodes]
        return " -> ".join(names) + f" ({self.total_stake:.1f}% stake)"


def detect_ownership_loops(
    db: FGIPDatabase,
    start_id: str,
    max_depth: int = 10,
) -> list[OwnershipLoop]:
    """
    Detect circular ownership starting from an entity.

    Looks for OWNS_SHARES, INVESTED_IN, MEMBER_OF edges that form cycles.
    """
    start_node = db.get_node(start_id)
    if not start_node:
        return []

    ownership_edges = {"OWNS_SHARES", "INVESTED_IN", "MEMBER_OF"}
    loops = []

    # DFS to find cycles
    def dfs(node_id: str, path_nodes: list[Node], path_edges: list[Edge], visited: set):
        if len(path_edges) > max_depth:
            return

        neighbors = db.get_neighbors(node_id, direction="outgoing")
        for edge, neighbor in neighbors:
            if edge.edge_type.value not in ownership_edges:
                continue

            # Found a cycle back to start
            if neighbor.node_id == start_id and len(path_edges) > 0:
                total_stake = 1.0
                for e in path_edges + [edge]:
                    # Extract stake from notes (e.g., "42.8% (87.9M shares)")
                    if e.notes:
                        import re
                        match = re.search(r'([\d.]+)%', e.notes)
                        if match:
                            stake = float(match.group(1)) / 100
                            total_stake *= stake

                loops.append(OwnershipLoop(
                    nodes=path_nodes + [neighbor],
                    edges=path_edges + [edge],
                    total_stake=total_stake * 100,
                ))
                return

            # Avoid intermediate cycles
            if neighbor.node_id in visited:
                continue

            visited.add(neighbor.node_id)
            dfs(
                neighbor.node_id,
                path_nodes + [neighbor],
                path_edges + [edge],
                visited,
            )
            visited.remove(neighbor.node_id)

    dfs(start_id, [start_node], [], {start_id})
    return loops


def map_ownership_structure(
    db: FGIPDatabase,
    entity_id: str,
    max_depth: int = 3,
) -> dict:
    """
    Map ownership structure for an entity.

    Returns dict with:
    - entity: the center node
    - owners: entities that own this one
    - owned: entities this one owns
    """
    entity = db.get_node(entity_id)
    if not entity:
        return {"entity": None, "owners": [], "owned": []}

    ownership_edges = {"OWNS_SHARES", "INVESTED_IN", "MEMBER_OF"}

    # Find owners (incoming ownership edges)
    owners = []
    for edge, neighbor in db.get_neighbors(entity_id, direction="incoming"):
        if edge.edge_type.value in ownership_edges:
            owners.append({
                "node": neighbor.to_dict(),
                "edge_type": edge.edge_type.value,
                "notes": edge.notes,
                "claim_id": edge.claim_id,
            })

    # Find owned (outgoing ownership edges)
    owned = []
    for edge, neighbor in db.get_neighbors(entity_id, direction="outgoing"):
        if edge.edge_type.value in ownership_edges:
            owned.append({
                "node": neighbor.to_dict(),
                "edge_type": edge.edge_type.value,
                "notes": edge.notes,
                "claim_id": edge.claim_id,
            })

    return {
        "entity": entity.to_dict(),
        "owners": owners,
        "owned": owned,
    }
