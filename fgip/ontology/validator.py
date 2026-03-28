"""
Main validation engine for FGIP ontology.

Enforces:
- Required fields present on nodes/edges
- Edge type valid for node type pair
- Required metadata properties present
- Assertion level consistent with edge type
- Endpoints exist (orphan check)
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .constraints import validate_edge_types
from .properties import validate_properties


@dataclass
class ValidationResult:
    """Result of validating a node, edge, or full export."""

    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.valid

    def merge(self, other: "ValidationResult") -> "ValidationResult":
        """Merge another result into this one."""
        return ValidationResult(
            valid=self.valid and other.valid,
            errors=self.errors + other.errors,
            warnings=self.warnings + other.warnings,
        )


class OntologyValidator:
    """
    Validates nodes and edges against FGIP ontology rules.

    Rules enforced:
    1. Required fields present
    2. Edge type valid for node type pair
    3. Required metadata properties present
    4. Assertion level consistent with edge type
    5. Endpoints exist (orphan check with logical_id resolution)
    """

    # Edge types that intentionally reference historical versions
    HISTORICAL_EDGE_TYPES = {"SUPERSEDES", "INVALIDATES", "MERGED_INTO"}

    # Edge types that may reference external entities (features, sensors, etc.)
    EXTERNAL_REF_EDGE_TYPES = {"LEADS", "CORRELATES", "DERIVES_FROM"}

    def __init__(self, node_index: Optional[Dict[str, dict]] = None):
        """
        Args:
            node_index: Dict mapping node_id -> node dict (for orphan checks)
        """
        self.node_index = node_index or {}
        # Maps logical_id -> node_id for nodes with belief revision
        self.logical_id_index: Dict[str, str] = {}

    def _resolve_node(self, node_id: str) -> Optional[dict]:
        """
        Resolve a node ID, checking direct match first then logical_id.

        Args:
            node_id: The node ID to resolve

        Returns:
            Node dict if found, None otherwise
        """
        # Direct match
        if node_id in self.node_index:
            return self.node_index[node_id]

        # Try logical_id resolution
        if node_id in self.logical_id_index:
            versioned_id = self.logical_id_index[node_id]
            return self.node_index.get(versioned_id)

        return None

    def validate_node(self, node: dict) -> ValidationResult:
        """
        Validate a single node.

        Args:
            node: Node dict with node_id, node_type, name, metadata

        Returns:
            ValidationResult with errors and warnings
        """
        errors = []
        warnings = []

        # Required fields
        for req_field in ["node_id", "node_type", "name"]:
            if not node.get(req_field):
                errors.append(f"Missing required field: {req_field}")

        if errors:
            return ValidationResult(False, errors, warnings)

        node_type = node["node_type"]
        node_id = node["node_id"]

        # Parse metadata
        metadata = node.get("metadata", "{}")
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError as e:
                errors.append(f"Invalid JSON in metadata for node {node_id}: {e}")
                return ValidationResult(False, errors, warnings)

        # Required properties per type
        missing = validate_properties(node_type, metadata, "node")
        for prop in missing:
            errors.append(f"Node {node_id}: missing required metadata.{prop} for {node_type}")

        return ValidationResult(len(errors) == 0, errors, warnings)

    def validate_edge(self, edge: dict) -> ValidationResult:
        """
        Validate a single edge.

        Args:
            edge: Edge dict with edge_id, edge_type, from_node_id, to_node_id, metadata

        Returns:
            ValidationResult with errors and warnings
        """
        errors = []
        warnings = []

        # Required fields
        for req_field in ["edge_id", "edge_type", "from_node_id", "to_node_id"]:
            if not edge.get(req_field):
                errors.append(f"Missing required field: {req_field}")

        if errors:
            return ValidationResult(False, errors, warnings)

        edge_type = edge["edge_type"]
        edge_id = edge["edge_id"]
        from_id = edge["from_node_id"]
        to_id = edge["to_node_id"]

        # Orphan check (if node index is populated)
        if self.node_index:
            # Resolve node IDs (check direct match, then logical_id)
            from_node = self._resolve_node(from_id)
            to_node = self._resolve_node(to_id)

            # Historical edge types (SUPERSEDES, etc.) may reference old versions
            is_historical = edge_type in self.HISTORICAL_EDGE_TYPES
            # External reference edge types (LEADS, etc.) may reference features/sensors
            is_external = edge_type in self.EXTERNAL_REF_EDGE_TYPES

            if from_node is None:
                if is_external:
                    warnings.append(
                        f"Edge {edge_id}: {edge_type} references external entity {from_id}"
                    )
                else:
                    errors.append(f"Edge {edge_id}: orphan from_node_id {from_id} not in node index")

            if to_node is None:
                # For historical edges, orphan to_node_id is expected (old version not in export)
                if is_historical:
                    warnings.append(
                        f"Edge {edge_id}: {edge_type} references historical node {to_id} (expected)"
                    )
                elif is_external:
                    warnings.append(
                        f"Edge {edge_id}: {edge_type} references external entity {to_id}"
                    )
                else:
                    errors.append(f"Edge {edge_id}: orphan to_node_id {to_id} not in node index")

            # Type constraint check (only if both endpoints resolved)
            if from_node is not None and to_node is not None:
                from_type = from_node.get("node_type", "UNKNOWN")
                to_type = to_node.get("node_type", "UNKNOWN")

                valid, msg = validate_edge_types(edge_type, from_type, to_type)
                if not valid:
                    errors.append(f"Edge {edge_id}: {msg}")

        # Parse metadata
        metadata = edge.get("metadata", "{}")
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError as e:
                errors.append(f"Invalid JSON in metadata for edge {edge_id}: {e}")
                return ValidationResult(False, errors, warnings)

        # Required properties per edge type (warnings only - many edges may lack full metadata)
        missing = validate_properties(edge_type, metadata, "edge")
        for prop in missing:
            warnings.append(f"Edge {edge_id}: missing recommended metadata.{prop} for {edge_type}")

        # Assertion level consistency
        assertion = metadata.get("assertion_level")
        if assertion:
            # Import here to avoid circular dependency
            try:
                from ..schema import INFERENTIAL_EDGE_TYPES, FACTUAL_EDGE_TYPES

                if edge_type in INFERENTIAL_EDGE_TYPES and assertion == "FACT":
                    warnings.append(
                        f"Edge {edge_id}: {edge_type} is inferential but assertion_level=FACT"
                    )
                if edge_type in FACTUAL_EDGE_TYPES and assertion == "INFERENCE":
                    warnings.append(
                        f"Edge {edge_id}: {edge_type} is factual but assertion_level=INFERENCE"
                    )
            except ImportError:
                # Schema not available, skip consistency check
                pass

        return ValidationResult(len(errors) == 0, errors, warnings)

    def validate_export(
        self, nodes: List[dict], edges: List[dict]
    ) -> ValidationResult:
        """
        Validate a full export (nodes + edges).

        Args:
            nodes: List of node dicts
            edges: List of edge dicts

        Returns:
            ValidationResult with all errors and warnings
        """
        all_errors = []
        all_warnings = []

        # Build node index
        self.node_index = {n["node_id"]: n for n in nodes if "node_id" in n}

        # Build logical_id index for belief revision support
        self.logical_id_index = {}
        for node in nodes:
            node_id = node.get("node_id", "")
            metadata = node.get("metadata", {})
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except (json.JSONDecodeError, TypeError):
                    metadata = {}

            logical_id = metadata.get("logical_id")
            if logical_id and logical_id != node_id:
                # Map logical_id -> versioned node_id
                self.logical_id_index[logical_id] = node_id

        # Validate nodes
        for node in nodes:
            result = self.validate_node(node)
            all_errors.extend(result.errors)
            all_warnings.extend(result.warnings)

        # Validate edges
        for edge in edges:
            result = self.validate_edge(edge)
            all_errors.extend(result.errors)
            all_warnings.extend(result.warnings)

        return ValidationResult(len(all_errors) == 0, all_errors, all_warnings)


def validate_jsonl_export(
    export_dir: str,
    fail_hard: bool = False,
    max_errors_shown: int = 20,
) -> ValidationResult:
    """
    Validate a JSONL export directory.

    Args:
        export_dir: Path to export directory containing *_nodes.jsonl and *_edges.jsonl
        fail_hard: If True, raise exception on validation failure
        max_errors_shown: Max errors to include in exception message

    Returns:
        ValidationResult with errors and warnings

    Raises:
        ValueError: If fail_hard=True and validation fails
    """
    export_path = Path(export_dir)

    if not export_path.exists():
        return ValidationResult(False, [f"Export directory not found: {export_dir}"], [])

    nodes = []
    edges = []

    # Load all nodes
    for node_file in sorted(export_path.glob("*_nodes.jsonl")):
        with node_file.open() as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    nodes.append(json.loads(line))
                except json.JSONDecodeError as e:
                    return ValidationResult(
                        False,
                        [f"Invalid JSON in {node_file.name} line {line_num}: {e}"],
                        [],
                    )

    # Load all edges
    for edge_file in sorted(export_path.glob("*_edges.jsonl")):
        with edge_file.open() as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    edges.append(json.loads(line))
                except json.JSONDecodeError as e:
                    return ValidationResult(
                        False,
                        [f"Invalid JSON in {edge_file.name} line {line_num}: {e}"],
                        [],
                    )

    validator = OntologyValidator()
    result = validator.validate_export(nodes, edges)

    if fail_hard and not result.valid:
        shown_errors = result.errors[:max_errors_shown]
        error_msg = f"Validation failed with {len(result.errors)} errors:\n" + "\n".join(
            f"  - {e}" for e in shown_errors
        )
        if len(result.errors) > max_errors_shown:
            error_msg += f"\n  ... and {len(result.errors) - max_errors_shown} more"
        raise ValueError(error_msg)

    return result
