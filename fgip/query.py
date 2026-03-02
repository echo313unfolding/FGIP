"""FGIP Query - Graph queries and analysis."""

from typing import Optional
from .db import FGIPDatabase


class FGIPQuery:
    """Query interface for the FGIP knowledge graph."""

    def __init__(self, db: FGIPDatabase):
        self.db = db

    def export_graph(self, output_format: str = "json") -> dict:
        """Export the full graph as JSON with evidence status."""
        nodes = self.db.list_nodes(limit=10000)
        edges = self.db.list_edges(limit=10000)

        nodes_data = []
        for node in nodes:
            nodes_data.append(node.to_dict())

        edges_data = []
        for edge in edges:
            edge_dict = edge.to_dict()
            # Add claim info if available
            if edge.claim_id:
                claim = self.db.get_claim(edge.claim_id)
                if claim:
                    edge_dict["claim_status"] = claim.status.value
                    sources = self.db.get_claim_sources(edge.claim_id)
                    edge_dict["best_tier"] = min((s.tier for s in sources), default=None)
            edges_data.append(edge_dict)

        return {
            "nodes": nodes_data,
            "edges": edges_data,
            "stats": {
                "nodes": len(nodes_data),
                "edges": len(edges_data),
            }
        }

    def search_nodes(self, query: str, limit: int = 20) -> list:
        """Full-text search for nodes."""
        return self.db.search_nodes(query, limit)

    def search_edges(self, query: str, limit: int = 20) -> list:
        """Full-text search for edges."""
        return self.db.search_edges(query, limit)
