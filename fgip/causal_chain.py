"""FGIP Causal Chain Builder - Build inference/hypothesis chains with explicit assertion levels.

This module enforces "forensically tight" discipline by requiring explicit
assertion_level for each edge in a causal chain.

Usage:
    chain = CausalChainBuilder(db)
    chain.add_link(
        from_node="pntr-2000",
        to_node="china-trade-normalization",
        edge_type="ENABLED",
        assertion_level="INFERENCE",
        claim_text="PNTR normalized trade relations with China",
        source_url="https://..."
    )
    receipt = chain.commit()
"""

import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any

from .db import FGIPDatabase
from .schema import (
    Node, Edge, Claim, Source, Receipt, NodeType, EdgeType,
    ClaimStatus, AssertionLevel, INFERENTIAL_EDGE_TYPES,
    compute_sha256
)


class ChainLink:
    """A single link in a causal chain."""

    def __init__(
        self,
        from_node: str,
        to_node: str,
        edge_type: str,
        assertion_level: str,
        claim_text: str,
        source_url: Optional[str] = None,
        topic: str = "Causal",
        notes: Optional[str] = None,
    ):
        self.from_node = from_node
        self.to_node = to_node
        self.edge_type = edge_type
        self.assertion_level = assertion_level
        self.claim_text = claim_text
        self.source_url = source_url
        self.topic = topic
        self.notes = notes

    def validate(self) -> List[str]:
        """Validate the link configuration."""
        errors = []

        # Validate assertion level
        valid_levels = {"FACT", "INFERENCE", "HYPOTHESIS"}
        if self.assertion_level not in valid_levels:
            errors.append(f"Invalid assertion_level: {self.assertion_level}. Must be one of {valid_levels}")

        # Enforce INFERENCE/HYPOTHESIS for inferential edge types
        if self.edge_type in INFERENTIAL_EDGE_TYPES and self.assertion_level == "FACT":
            errors.append(
                f"Edge type {self.edge_type} requires assertion_level INFERENCE or HYPOTHESIS, "
                f"not FACT (unless you have direct Tier 0 evidence)"
            )

        # Validate edge type exists
        try:
            EdgeType(self.edge_type)
        except ValueError:
            errors.append(f"Invalid edge_type: {self.edge_type}")

        return errors


class CausalChainBuilder:
    """Build causal chains with explicit assertion levels."""

    def __init__(self, db: FGIPDatabase):
        self.db = db
        self.links: List[ChainLink] = []
        self.nodes_to_create: Dict[str, Dict[str, Any]] = {}

    def add_node(
        self,
        node_id: str,
        name: str,
        node_type: str,
        description: Optional[str] = None,
    ) -> "CausalChainBuilder":
        """Register a node to be created if it doesn't exist."""
        self.nodes_to_create[node_id] = {
            "node_id": node_id,
            "name": name,
            "node_type": node_type,
            "description": description,
        }
        return self

    def add_link(
        self,
        from_node: str,
        to_node: str,
        edge_type: str,
        assertion_level: str,
        claim_text: str,
        source_url: Optional[str] = None,
        topic: str = "Causal",
        notes: Optional[str] = None,
    ) -> "CausalChainBuilder":
        """Add a link to the chain.

        Args:
            from_node: Source node ID
            to_node: Target node ID
            edge_type: Relationship type (e.g., ENABLED, CAUSED)
            assertion_level: FACT | INFERENCE | HYPOTHESIS (required!)
            claim_text: The claim backing this edge
            source_url: Optional source URL for the claim
            topic: Topic category (default: "Causal")
            notes: Optional notes about this link

        Returns:
            self (for chaining)
        """
        link = ChainLink(
            from_node=from_node,
            to_node=to_node,
            edge_type=edge_type,
            assertion_level=assertion_level,
            claim_text=claim_text,
            source_url=source_url,
            topic=topic,
            notes=notes,
        )
        self.links.append(link)
        return self

    def validate(self) -> List[str]:
        """Validate the entire chain."""
        errors = []

        if not self.links:
            errors.append("Chain has no links")
            return errors

        for i, link in enumerate(self.links):
            link_errors = link.validate()
            for err in link_errors:
                errors.append(f"Link {i+1} ({link.from_node} -> {link.to_node}): {err}")

        # Check chain connectivity
        for i in range(1, len(self.links)):
            if self.links[i].from_node != self.links[i-1].to_node:
                errors.append(
                    f"Chain broken at link {i+1}: "
                    f"{self.links[i-1].to_node} != {self.links[i].from_node}"
                )

        return errors

    def commit(self) -> Receipt:
        """Commit the chain to the database.

        Returns:
            Receipt with details of what was created
        """
        errors = self.validate()
        if errors:
            return Receipt(
                receipt_id=str(uuid.uuid4()),
                operation="add_causal_chain",
                timestamp=datetime.utcnow().isoformat() + "Z",
                input_hash=compute_sha256({"links": len(self.links)}),
                output_hash=compute_sha256({"errors": errors}),
                success=False,
                details={"errors": errors},
            )

        nodes_created = []
        claims_created = []
        edges_created = []
        sources_created = []

        # Create any registered nodes
        for node_id, node_data in self.nodes_to_create.items():
            existing = self.db.get_node(node_id)
            if not existing:
                try:
                    node = Node(
                        node_id=node_data["node_id"],
                        node_type=NodeType(node_data["node_type"]),
                        name=node_data["name"],
                        description=node_data.get("description"),
                    )
                    receipt = self.db.insert_node(node)
                    if receipt.success:
                        nodes_created.append(node_id)
                except Exception as e:
                    return Receipt(
                        receipt_id=str(uuid.uuid4()),
                        operation="add_causal_chain",
                        timestamp=datetime.utcnow().isoformat() + "Z",
                        input_hash=compute_sha256({"node_id": node_id}),
                        output_hash=compute_sha256({"error": str(e)}),
                        success=False,
                        details={"error": f"Failed to create node {node_id}: {e}"},
                    )

        # Create each link
        for link in self.links:
            # Create source if URL provided
            source_id = None
            if link.source_url:
                source = Source.from_url(link.source_url)
                if self.db.insert_source(source):
                    sources_created.append(source.source_id)
                source_id = source.source_id

            # Create claim
            claim_id = self.db.get_next_claim_id()
            status = ClaimStatus.PARTIAL if link.source_url else ClaimStatus.MISSING

            # Determine required tier based on assertion level
            if link.assertion_level == "FACT":
                required_tier = 0  # Facts need Tier 0
            elif link.assertion_level == "INFERENCE":
                required_tier = 1  # Inferences need at least Tier 1
            else:
                required_tier = 2  # Hypotheses can use Tier 2

            claim = Claim(
                claim_id=claim_id,
                claim_text=f"[{link.assertion_level}] {link.claim_text}",
                topic=link.topic,
                status=status,
                required_tier=required_tier,
                notes=f"Assertion: {link.assertion_level}. {link.notes or ''}".strip(),
            )

            if self.db.insert_claim(claim):
                claims_created.append(claim_id)

                # Link claim to source
                if source_id:
                    self.db.link_claim_source(claim_id, source_id)

            # Create edge
            edge_type = EdgeType(link.edge_type)
            edge_id = f"{edge_type.value.lower()}_{link.from_node}_{link.to_node}"

            edge = Edge(
                edge_id=edge_id,
                edge_type=edge_type,
                from_node_id=link.from_node,
                to_node_id=link.to_node,
                claim_id=claim_id,
                assertion_level=link.assertion_level,
                notes=link.notes,
            )

            try:
                receipt = self.db.insert_edge(edge)
                if receipt.success:
                    edges_created.append({
                        "edge_id": edge_id,
                        "from": link.from_node,
                        "to": link.to_node,
                        "type": link.edge_type,
                        "assertion": link.assertion_level,
                        "claim_id": claim_id,
                    })
            except Exception as e:
                return Receipt(
                    receipt_id=str(uuid.uuid4()),
                    operation="add_causal_chain",
                    timestamp=datetime.utcnow().isoformat() + "Z",
                    input_hash=compute_sha256({"edge_id": edge_id}),
                    output_hash=compute_sha256({"error": str(e)}),
                    success=False,
                    details={"error": f"Failed to create edge {edge_id}: {e}"},
                )

        return Receipt(
            receipt_id=str(uuid.uuid4()),
            operation="add_causal_chain",
            timestamp=datetime.utcnow().isoformat() + "Z",
            input_hash=compute_sha256({
                "links": len(self.links),
                "nodes": len(self.nodes_to_create),
            }),
            output_hash=compute_sha256({
                "nodes_created": len(nodes_created),
                "claims_created": len(claims_created),
                "edges_created": len(edges_created),
            }),
            success=True,
            details={
                "nodes_created": nodes_created,
                "claims_created": claims_created,
                "edges_created": edges_created,
                "sources_created": sources_created,
                "chain_length": len(self.links),
            },
        )

    def clear(self):
        """Clear the builder for reuse."""
        self.links = []
        self.nodes_to_create = {}


def parse_chain_spec(spec: str) -> List[Dict[str, str]]:
    """Parse a chain specification string.

    Format: "node1 --(EDGE_TYPE:LEVEL)--> node2 --(EDGE_TYPE:LEVEL)--> node3"

    Example:
        "pntr-2000 --(ENABLED:INFERENCE)--> china-trade --(ENABLED:HYPOTHESIS)--> fentanyl"

    Returns:
        List of dicts with from_node, to_node, edge_type, assertion_level
    """
    import re

    # Pattern: node --(TYPE:LEVEL)--> node
    pattern = r'(\S+)\s*--\((\w+):(\w+)\)-->\s*'

    links = []
    remaining = spec.strip()

    while remaining:
        match = re.match(pattern, remaining)
        if not match:
            # Last node
            break

        from_node = match.group(1)
        edge_type = match.group(2)
        assertion_level = match.group(3)
        remaining = remaining[match.end():]

        # Get the next node (either another link or final node)
        next_match = re.match(r'(\S+)', remaining)
        if next_match:
            to_node = next_match.group(1)
            links.append({
                "from_node": from_node,
                "to_node": to_node,
                "edge_type": edge_type,
                "assertion_level": assertion_level,
            })

    return links
