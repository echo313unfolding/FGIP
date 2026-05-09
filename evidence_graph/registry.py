"""Domain registry — runtime type system loaded from a YAML manifest.

Replaces hardcoded NodeType/EdgeType enums with configurable, per-domain
type sets. The registry validates all graph operations at runtime while
allowing any domain (security, compliance, FGIP, academic citations) to
define its own ontology.

Usage:
    registry = DomainRegistry.from_yaml("domains/security.yaml")
    registry.validate_node_type("THREAT_ACTOR")  # OK
    registry.validate_node_type("LEGISLATION")   # raises ValueError
    registry.is_inferential("INDICATES")         # True
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


class DomainRegistry:
    """Runtime type registry for an evidence graph domain."""

    def __init__(
        self,
        domain_name: str,
        prefix: str,
        node_types: set[str],
        factual_edges: set[str],
        inferential_edges: set[str],
        tier_domains: dict[int, list[str]],
        constraints: dict[str, list[list[str]]],
        node_properties: dict[str, dict],
        edge_properties: dict[str, dict],
        default_staleness_days: int = 90,
    ):
        self.domain_name = domain_name
        self.prefix = prefix
        self.node_types = node_types
        self.factual_edges = factual_edges
        self.inferential_edges = inferential_edges
        self.edge_types = factual_edges | inferential_edges
        self.tier_domains = tier_domains
        self.constraints = constraints
        self.node_properties = node_properties
        self.edge_properties = edge_properties
        self.default_staleness_days = default_staleness_days

    @classmethod
    def from_yaml(cls, path: str | Path) -> DomainRegistry:
        """Load registry from a YAML domain manifest."""
        try:
            import yaml
        except ImportError:
            raise ImportError(
                "PyYAML required for YAML manifests: pip install pyyaml"
            )
        path = Path(path)
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, d: dict) -> DomainRegistry:
        """Load registry from a plain dict (parsed YAML or JSON)."""
        edge_types = d.get("edge_types", {})
        factual = set(edge_types.get("factual", []))
        inferential = set(edge_types.get("inferential", []))
        # Also support flat list under "belief_revision" etc.
        for category in edge_types:
            if category not in ("factual", "inferential"):
                # Extra categories (belief_revision, entity_resolution, etc.)
                # go into the appropriate set based on a flag, or inferential
                # by default
                extras = edge_types[category]
                if isinstance(extras, list):
                    inferential.update(extras)

        tier_domains = {}
        for tier_key, domains in d.get("source_tiers", {}).items():
            tier_domains[int(tier_key)] = domains

        constraints = d.get("constraints", {})
        node_props = d.get("properties", {}).get("nodes", {})
        edge_props = d.get("properties", {}).get("edges", {})

        return cls(
            domain_name=d.get("domain", "default"),
            prefix=d.get("prefix", "EG"),
            node_types=set(d.get("node_types", [])),
            factual_edges=factual,
            inferential_edges=inferential,
            tier_domains=tier_domains,
            constraints=constraints,
            node_properties=node_props,
            edge_properties=edge_props,
            default_staleness_days=d.get("default_staleness_days", 90),
        )

    def to_dict(self) -> dict:
        """Serialize for storage in _meta table."""
        return {
            "domain": self.domain_name,
            "prefix": self.prefix,
            "node_types": sorted(self.node_types),
            "edge_types": {
                "factual": sorted(self.factual_edges),
                "inferential": sorted(self.inferential_edges),
            },
            "source_tiers": {
                str(k): v for k, v in self.tier_domains.items()
            },
            "constraints": self.constraints,
            "properties": {
                "nodes": self.node_properties,
                "edges": self.edge_properties,
            },
            "default_staleness_days": self.default_staleness_days,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    # --- Validation methods ---

    def validate_node_type(self, node_type: str) -> None:
        """Raise ValueError if node_type is not in this domain."""
        if node_type not in self.node_types:
            raise ValueError(
                f"'{node_type}' is not a valid node type in domain "
                f"'{self.domain_name}'. Valid types: {sorted(self.node_types)}"
            )

    def validate_edge_type(self, edge_type: str) -> None:
        """Raise ValueError if edge_type is not in this domain."""
        if edge_type not in self.edge_types:
            raise ValueError(
                f"'{edge_type}' is not a valid edge type in domain "
                f"'{self.domain_name}'. Valid types: {sorted(self.edge_types)}"
            )

    def is_inferential(self, edge_type: str) -> bool:
        """Check if an edge type defaults to INFERENCE/HYPOTHESIS."""
        return edge_type in self.inferential_edges

    def is_factual(self, edge_type: str) -> bool:
        """Check if an edge type defaults to FACT."""
        return edge_type in self.factual_edges

    def auto_tier_domain(self, domain: str) -> int:
        """Auto-assign source tier based on domain URL."""
        domain_lower = domain.lower()
        for tier in sorted(self.tier_domains.keys()):
            for d in self.tier_domains[tier]:
                if d in domain_lower:
                    return tier
        return 2  # Default: commentary tier

    def validate_edge_constraint(
        self, edge_type: str, from_type: str, to_type: str
    ) -> tuple[bool, str]:
        """Check if an edge is valid between the given node types."""
        if edge_type not in self.constraints:
            return True, ""  # No constraint defined = allow
        allowed = self.constraints[edge_type]
        for pair in allowed:
            if len(pair) == 2 and pair[0] == from_type and pair[1] == to_type:
                return True, ""
        return False, (
            f"{edge_type} not allowed from {from_type} to {to_type}. "
            f"Allowed: {allowed}"
        )

    def get_node_properties(self, node_type: str) -> dict:
        """Get required/optional properties for a node type."""
        return self.node_properties.get(node_type, {
            "required": [],
            "optional": [],
        })

    def get_edge_properties(self, edge_type: str) -> dict:
        """Get required/optional properties for an edge type."""
        return self.edge_properties.get(edge_type, {
            "required": ["assertion_level"],
            "optional": [],
        })

    # --- ID formatting ---

    def format_claim_id(self, num: int) -> str:
        """Generate a claim ID with the domain prefix."""
        return f"{self.prefix}-{num:06d}"

    def format_proposal_id(
        self, agent_name: str, date_str: str, short_sha: str
    ) -> str:
        """Generate a proposal ID with the domain prefix."""
        return f"{self.prefix}-PROPOSED-{agent_name.upper()}-{date_str}-{short_sha}"

    def __repr__(self) -> str:
        return (
            f"DomainRegistry(domain='{self.domain_name}', "
            f"prefix='{self.prefix}', "
            f"node_types={len(self.node_types)}, "
            f"edge_types={len(self.edge_types)})"
        )
