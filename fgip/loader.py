"""FGIP Loader - Load seed data from JSON files."""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from .db import FGIPDatabase
from .schema import Node, Edge, NodeType, EdgeType, SourceType, Receipt, compute_sha256


def _timestamp() -> str:
    """Generate ISO8601 timestamp."""
    return datetime.utcnow().isoformat() + "Z"


def slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '_', text)
    return text[:50]


def generate_node_id(node_type: NodeType, name: str) -> str:
    """Generate a unique node ID from type and name."""
    prefix = {
        NodeType.ORGANIZATION: "org",
        NodeType.PERSON: "person",
        NodeType.LEGISLATION: "leg",
        NodeType.COURT_CASE: "case",
        NodeType.POLICY: "policy",
        NodeType.COMPANY: "company",
        NodeType.MEDIA_OUTLET: "media",
        NodeType.FINANCIAL_INST: "fin",
        NodeType.AMICUS_BRIEF: "amicus",
        NodeType.ETF_FUND: "etf",
        NodeType.ECONOMIC_EVENT: "event",
    }.get(node_type, "node")

    slug = slugify(name)
    return f"{prefix}_{slug}"


def generate_edge_id(edge_type: EdgeType, from_node: str, to_node: str) -> str:
    """Generate a unique edge ID from type and nodes."""
    type_slug = edge_type.value.lower()
    from_slug = from_node[:20] if len(from_node) > 20 else from_node
    to_slug = to_node[:20] if len(to_node) > 20 else to_node
    return f"edge_{type_slug}_{from_slug}_{to_slug}"


class FGIPLoader:
    """Load nodes and edges from JSON files."""

    def __init__(self, db: FGIPDatabase):
        self.db = db

    def load_nodes(self, filepath: str) -> Receipt:
        """Load nodes from a JSON file."""
        path = Path(filepath)
        with open(path) as f:
            data = json.load(f)

        nodes = data if isinstance(data, list) else data.get("nodes", [])
        is_synthetic = data.get("is_synthetic", False) if isinstance(data, dict) else False

        loaded = 0
        errors = []

        for node_data in nodes:
            try:
                # Handle both formats
                if "node_id" not in node_data:
                    node_type = NodeType(node_data.get("node_type", "ORGANIZATION"))
                    name = node_data.get("name", "")
                    node_data["node_id"] = generate_node_id(node_type, name)

                node = Node.from_dict(node_data)
                validation_errors = node.validate()
                if validation_errors:
                    errors.append({"node": node_data, "errors": validation_errors})
                    continue

                receipt = self.db.insert_node(node)
                if receipt.success:
                    loaded += 1
                else:
                    errors.append({"node": node_data, "errors": ["Insert failed"]})
            except Exception as e:
                errors.append({"node": node_data, "errors": [str(e)]})

        return Receipt(
            receipt_id=f"load_nodes_{compute_sha256(filepath)[:8]}",
            operation="load_nodes",
            timestamp=_timestamp(),
            input_hash=compute_sha256(str(path)),
            output_hash=compute_sha256(str(loaded)),
            success=len(errors) == 0,
            details={
                "loaded": loaded,
                "errors": errors,
                "is_synthetic": is_synthetic,
            }
        )

    def load_edges(self, filepath: str) -> Receipt:
        """Load edges from a JSON file."""
        path = Path(filepath)
        with open(path) as f:
            data = json.load(f)

        edges = data if isinstance(data, list) else data.get("edges", [])

        loaded = 0
        errors = []

        for edge_data in edges:
            try:
                # Handle both formats
                if "edge_id" not in edge_data:
                    edge_type = EdgeType(edge_data.get("edge_type", "CAUSED"))
                    from_node = edge_data.get("from_node_id", "")
                    to_node = edge_data.get("to_node_id", "")
                    edge_data["edge_id"] = generate_edge_id(edge_type, from_node, to_node)

                edge = Edge.from_dict(edge_data)
                validation_errors = edge.validate()
                if validation_errors:
                    # Square-One: Allow edges without claim_id during migration
                    validation_errors = [e for e in validation_errors if "claim_id" not in e.lower()]
                    if validation_errors:
                        errors.append({"edge": edge_data, "errors": validation_errors})
                        continue

                receipt = self.db.insert_edge(edge)
                if receipt.success:
                    loaded += 1
                else:
                    errors.append({"edge": edge_data, "errors": ["Insert failed"]})
            except Exception as e:
                errors.append({"edge": edge_data, "errors": [str(e)]})

        return Receipt(
            receipt_id=f"load_edges_{compute_sha256(filepath)[:8]}",
            operation="load_edges",
            timestamp=_timestamp(),
            input_hash=compute_sha256(str(path)),
            output_hash=compute_sha256(str(loaded)),
            success=len(errors) == 0,
            details={
                "loaded": loaded,
                "errors": errors,
            }
        )
