"""FGIP Causality Chain Analysis - Trace paths with evidence coverage."""

from collections import deque
from dataclasses import dataclass
from typing import Optional

from fgip.db import FGIPDatabase
from fgip.schema import Edge, Node, ClaimStatus


@dataclass
class CausalityPath:
    """A path through the knowledge graph with evidence provenance."""
    nodes: list[Node]
    edges: list[Edge]
    total_confidence: float
    sources: list[str]
    # Square-One additions
    claim_ids: list[str]
    evidence_coverage: float  # Percentage of edges with Tier 0/1 sources

    def __len__(self):
        return len(self.edges)

    def to_dict(self) -> dict:
        return {
            "path_length": len(self.edges),
            "nodes": [n.node_id for n in self.nodes],
            "edges": [e.edge_id for e in self.edges],
            "edge_types": [e.edge_type.value for e in self.edges],
            "total_confidence": self.total_confidence,
            "sources": self.sources,
            "claim_ids": self.claim_ids,
            "evidence_coverage": self.evidence_coverage,
        }

    def describe(self) -> str:
        """Human-readable path description."""
        parts = []
        for i, node in enumerate(self.nodes):
            parts.append(f"[{node.name}]")
            if i < len(self.edges):
                edge = self.edges[i]
                parts.append(f" --{edge.edge_type.value}--> ")
        return "".join(parts)


def trace_causality(
    db: FGIPDatabase,
    start_id: str,
    end_id: str,
    max_depth: int = 6,
    allowed_edge_types: Optional[list[str]] = None,
) -> list[CausalityPath]:
    """
    Find all paths from start to end with evidence coverage calculation.

    Args:
        db: FGIP database connection
        start_id: Starting node ID
        end_id: Target node ID
        max_depth: Maximum path length (default 6)
        allowed_edge_types: Optional filter for edge types

    Returns:
        List of CausalityPath objects with evidence coverage, sorted by coverage then confidence
    """
    start_node = db.get_node(start_id)
    end_node = db.get_node(end_id)

    if not start_node:
        raise ValueError(f"Start node not found: {start_id}")
    if not end_node:
        raise ValueError(f"End node not found: {end_id}")

    paths = []

    # BFS from start
    queue = deque([(start_id, [start_node], [])])
    visited_paths = set()

    while queue:
        current_id, path_nodes, path_edges = queue.popleft()

        if len(path_edges) > max_depth:
            continue

        # Found target
        if current_id == end_id:
            path = _build_path(db, path_nodes, path_edges)
            paths.append(path)
            continue

        # Explore neighbors
        neighbors = db.get_neighbors(current_id, direction="outgoing")

        for edge, neighbor in neighbors:
            if allowed_edge_types and edge.edge_type.value not in allowed_edge_types:
                continue

            if neighbor.node_id in [n.node_id for n in path_nodes]:
                continue

            path_sig = tuple([n.node_id for n in path_nodes] + [neighbor.node_id])
            if path_sig in visited_paths:
                continue
            visited_paths.add(path_sig)

            new_nodes = path_nodes + [neighbor]
            new_edges = path_edges + [edge]
            queue.append((neighbor.node_id, new_nodes, new_edges))

    # Sort by evidence coverage (highest first), then by confidence
    paths.sort(key=lambda p: (p.evidence_coverage, p.total_confidence), reverse=True)

    return paths


def _build_path(db: FGIPDatabase, nodes: list[Node], edges: list[Edge]) -> CausalityPath:
    """Build a CausalityPath with evidence coverage calculation."""
    total_conf = 1.0
    sources = []
    claim_ids = []
    tier_01_count = 0

    for edge in edges:
        total_conf *= edge.confidence

        # Collect claim info
        if edge.claim_id:
            claim_ids.append(edge.claim_id)
            claim_sources = db.get_claim_sources(edge.claim_id)
            if claim_sources:
                best_tier = min(s.tier for s in claim_sources)
                if best_tier <= 1:
                    tier_01_count += 1
                sources.append(claim_sources[0].url)
        elif edge.source:
            sources.append(edge.source)

    # Calculate evidence coverage
    evidence_coverage = (tier_01_count / len(edges) * 100) if edges else 0

    return CausalityPath(
        nodes=nodes,
        edges=edges,
        total_confidence=total_conf,
        sources=sources,
        claim_ids=claim_ids,
        evidence_coverage=evidence_coverage,
    )


def trace_bidirectional(
    db: FGIPDatabase,
    start_id: str,
    end_id: str,
    max_depth: int = 6,
) -> list[CausalityPath]:
    """
    Bidirectional BFS - search from both ends and meet in middle.
    More efficient for long paths.
    """
    start_node = db.get_node(start_id)
    end_node = db.get_node(end_id)

    if not start_node or not end_node:
        return []

    forward_visited = {start_id: ([start_node], [])}
    forward_queue = deque([start_id])

    backward_visited = {end_id: ([end_node], [])}
    backward_queue = deque([end_id])

    meeting_points = []

    for depth in range(max_depth // 2 + 1):
        for _ in range(len(forward_queue)):
            if not forward_queue:
                break
            current_id = forward_queue.popleft()
            path_nodes, path_edges = forward_visited[current_id]

            for edge, neighbor in db.get_neighbors(current_id, direction="outgoing"):
                if neighbor.node_id in [n.node_id for n in path_nodes]:
                    continue

                if neighbor.node_id not in forward_visited:
                    forward_visited[neighbor.node_id] = (
                        path_nodes + [neighbor],
                        path_edges + [edge],
                    )
                    forward_queue.append(neighbor.node_id)

                if neighbor.node_id in backward_visited:
                    meeting_points.append(neighbor.node_id)

        for _ in range(len(backward_queue)):
            if not backward_queue:
                break
            current_id = backward_queue.popleft()
            path_nodes, path_edges = backward_visited[current_id]

            for edge, neighbor in db.get_neighbors(current_id, direction="incoming"):
                if neighbor.node_id in [n.node_id for n in path_nodes]:
                    continue

                if neighbor.node_id not in backward_visited:
                    backward_visited[neighbor.node_id] = (
                        path_nodes + [neighbor],
                        path_edges + [edge],
                    )
                    backward_queue.append(neighbor.node_id)

                if neighbor.node_id in forward_visited:
                    meeting_points.append(neighbor.node_id)

    paths = []
    for meet_id in set(meeting_points):
        forward_nodes, forward_edges = forward_visited[meet_id]
        backward_nodes, backward_edges = backward_visited[meet_id]

        full_nodes = forward_nodes + backward_nodes[1:][::-1]
        full_edges = forward_edges + backward_edges[::-1]

        if len(full_edges) <= max_depth:
            path = _build_path(db, full_nodes, full_edges)
            paths.append(path)

    paths.sort(key=lambda p: (p.evidence_coverage, p.total_confidence), reverse=True)
    return paths


def get_path_evidence_summary(db: FGIPDatabase, path: CausalityPath) -> dict:
    """Get detailed evidence summary for a path."""
    edges_info = []

    for edge in path.edges:
        edge_info = {
            "edge_id": edge.edge_id,
            "edge_type": edge.edge_type.value,
            "from": edge.from_node_id,
            "to": edge.to_node_id,
            "claim_id": edge.claim_id,
            "claim_status": None,
            "sources": [],
            "best_tier": None,
        }

        if edge.claim_id:
            claim = db.get_claim(edge.claim_id)
            if claim:
                edge_info["claim_status"] = claim.status.value

            sources = db.get_claim_sources(edge.claim_id)
            edge_info["sources"] = [
                {"url": s.url, "tier": s.tier, "has_artifact": s.artifact_path is not None}
                for s in sources
            ]
            if sources:
                edge_info["best_tier"] = min(s.tier for s in sources)

        edges_info.append(edge_info)

    return {
        "path_length": len(path.edges),
        "evidence_coverage": path.evidence_coverage,
        "total_confidence": path.total_confidence,
        "edges": edges_info,
    }
