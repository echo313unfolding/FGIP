"""
Belief revision system for FGIP graph.

Implements SUPERSEDES edges to make the graph self-correcting:
- When inputs change (FRED revisions)
- When calibration changes
- When classifier logic changes

Design:
- Stable logical_id: "regime-state-2021-04" (what humans mean)
- Versioned node_id: "regime-state-2021-04@<hash16>" (what computers diff)
- SUPERSEDES edge: new_version -> old_version

v1.0: File-based comparison against previous export
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _json_canonical(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _stable_edge_id(edge_type: str, from_id: str, to_id: str, salt: str = "") -> str:
    h = hashlib.sha256(f"{edge_type}|{from_id}|{to_id}|{salt}".encode("utf-8")).hexdigest()
    return f"{edge_type.lower()}-{h[:16]}"


# ============================================================================
# Content hashing for version identity
# ============================================================================

def compute_content_hash(node: Dict[str, Any]) -> str:
    """
    Compute content hash for a node.

    Hash is based on:
    - node_type
    - logical_id (extracted from node_id)
    - canonical metadata (excluding timestamp fields)

    NOT included (would cause unnecessary churn):
    - created_at, timestamp, exported_at
    - logical_id, content_hash, is_latest (meta-metadata)
    """
    # Extract logical_id (strip version suffix if present)
    node_id = node.get("node_id", "")
    if "@" in node_id:
        logical_id = node_id.split("@")[0]
    else:
        logical_id = node_id

    # Get metadata and filter out timestamp/meta fields
    metadata = node.get("metadata", "{}")
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}

    # Remove fields that would cause spurious churn
    excluded_keys = {
        "created_at", "timestamp", "exported_at", "generated_at",
        "logical_id", "content_hash", "is_latest",
    }
    filtered_meta = {k: v for k, v in metadata.items() if k not in excluded_keys}

    # Compute hash of content (not timestamps)
    content = f"{node.get('node_type', '')}|{logical_id}|{_json_canonical(filtered_meta)}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def get_logical_id(node: Dict[str, Any]) -> str:
    """Extract logical_id from node (strips version suffix)."""
    node_id = node.get("node_id", "")
    if "@" in node_id:
        return node_id.split("@")[0]
    return node_id


def make_versioned_id(logical_id: str, content_hash: str) -> str:
    """Create versioned node_id from logical_id and content_hash."""
    return f"{logical_id}@{content_hash}"


# ============================================================================
# Snapshot loading
# ============================================================================

@dataclass
class NodeVersion:
    """A specific version of a node."""
    node_id: str            # Versioned ID (logical_id@hash)
    logical_id: str         # Stable logical ID
    content_hash: str       # Hash of canonical content
    node_type: str
    metadata: str           # Canonical JSON string
    full_node: Dict         # Original node dict


def load_snapshot(export_dir: Path) -> Dict[str, NodeVersion]:
    """
    Load previous snapshot from JSONL export.

    Returns dict mapping logical_id -> latest NodeVersion
    """
    nodes_file = export_dir / "regime_nodes.jsonl"
    if not nodes_file.exists():
        return {}

    versions: Dict[str, NodeVersion] = {}

    with nodes_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            node = json.loads(line)
            logical_id = get_logical_id(node)
            content_hash = compute_content_hash(node)

            # Store latest version per logical_id
            versions[logical_id] = NodeVersion(
                node_id=node.get("node_id", ""),
                logical_id=logical_id,
                content_hash=content_hash,
                node_type=node.get("node_type", ""),
                metadata=node.get("metadata", "{}"),
                full_node=node,
            )

    return versions


def find_latest_export(exports_root: Path) -> Optional[Path]:
    """Find most recent export directory."""
    if not exports_root.exists():
        return None

    # Find export dirs (any directory containing regime_nodes.jsonl)
    export_dirs = []
    for d in exports_root.iterdir():
        if d.is_dir() and (d / "regime_nodes.jsonl").exists():
            export_dirs.append(d)

    if not export_dirs:
        return None

    # Sort by modification time (most recent first)
    export_dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
    return export_dirs[0]


# ============================================================================
# Belief revision (diff + SUPERSEDES)
# ============================================================================

@dataclass
class RevisionResult:
    """Result of comparing current nodes against previous snapshot."""
    new_nodes: List[Dict]           # Nodes that didn't exist before
    unchanged_nodes: List[Dict]     # Nodes with same content hash
    superseded_nodes: List[Dict]    # New versions of changed nodes
    supersedes_edges: List[Dict]    # SUPERSEDES edges (new -> old)
    stats: Dict[str, int]


def compute_revision(
    current_nodes: List[Dict],
    previous_snapshot: Dict[str, NodeVersion],
    *,
    reason: str = "inputs_changed",
) -> RevisionResult:
    """
    Compare current nodes against previous snapshot.

    Returns:
    - New versioned nodes
    - SUPERSEDES edges for changed content

    Args:
        current_nodes: Current node dicts (will be upgraded to versioned IDs)
        previous_snapshot: Previous snapshot (from load_snapshot)
        reason: Why revision occurred ("inputs_changed", "calibration_changed", etc.)
    """
    new_nodes = []
    unchanged_nodes = []
    superseded_nodes = []
    supersedes_edges = []

    for node in current_nodes:
        logical_id = get_logical_id(node)
        content_hash = compute_content_hash(node)
        versioned_id = make_versioned_id(logical_id, content_hash)

        # Upgrade node to versioned ID
        versioned_node = dict(node)
        versioned_node["node_id"] = versioned_id

        # Add version metadata
        if "metadata" in versioned_node:
            try:
                meta = json.loads(versioned_node["metadata"])
            except (json.JSONDecodeError, TypeError):
                meta = {}
            meta["logical_id"] = logical_id
            meta["content_hash"] = content_hash
            meta["is_latest"] = True
            versioned_node["metadata"] = _json_canonical(meta)

        # Check against previous snapshot
        prev = previous_snapshot.get(logical_id)

        if prev is None:
            # New node (didn't exist before)
            new_nodes.append(versioned_node)
        elif prev.content_hash == content_hash:
            # Unchanged (same content hash)
            unchanged_nodes.append(versioned_node)
        else:
            # Content changed -> supersedes old version
            superseded_nodes.append(versioned_node)

            # Create SUPERSEDES edge
            edge_id = _stable_edge_id(
                "SUPERSEDES",
                versioned_id,
                prev.node_id,
                salt=logical_id
            )

            # Compute diff summary (what changed)
            try:
                old_meta = json.loads(prev.metadata)
                new_meta = json.loads(versioned_node["metadata"])
                diff_keys = []
                for k in set(old_meta.keys()) | set(new_meta.keys()):
                    if k in ("logical_id", "content_hash", "is_latest"):
                        continue
                    if old_meta.get(k) != new_meta.get(k):
                        diff_keys.append(k)
            except (json.JSONDecodeError, TypeError):
                diff_keys = ["metadata_parse_error"]

            supersedes_edges.append({
                "edge_id": edge_id,
                "edge_type": "SUPERSEDES",
                "from_node_id": versioned_id,
                "to_node_id": prev.node_id,
                "confidence": 1.0,
                "notes": f"Belief revision: {reason}",
                "metadata": _json_canonical({
                    "logical_id": logical_id,
                    "old_hash": prev.content_hash,
                    "new_hash": content_hash,
                    "reason": reason,
                    "diff_keys": diff_keys,
                    "assertion_level": "FACT",
                }),
            })

    stats = {
        "new": len(new_nodes),
        "unchanged": len(unchanged_nodes),
        "superseded": len(superseded_nodes),
        "supersedes_edges": len(supersedes_edges),
        "total_current": len(current_nodes),
        "total_previous": len(previous_snapshot),
    }

    return RevisionResult(
        new_nodes=new_nodes,
        unchanged_nodes=unchanged_nodes,
        superseded_nodes=superseded_nodes,
        supersedes_edges=supersedes_edges,
        stats=stats,
    )


def apply_revision(
    current_nodes: List[Dict],
    exports_root: str = "receipts/regime/exports",
    *,
    reason: str = "inputs_changed",
) -> RevisionResult:
    """
    High-level API: compare against latest export and compute revision.

    Args:
        current_nodes: Current node dicts
        exports_root: Path to exports directory
        reason: Why revision occurred

    Returns:
        RevisionResult with versioned nodes and SUPERSEDES edges
    """
    exports_path = Path(exports_root)
    latest_export = find_latest_export(exports_path)

    if latest_export is None:
        # No previous export - all nodes are new
        versioned_nodes = []
        for node in current_nodes:
            logical_id = get_logical_id(node)
            content_hash = compute_content_hash(node)
            versioned_id = make_versioned_id(logical_id, content_hash)

            versioned_node = dict(node)
            versioned_node["node_id"] = versioned_id

            if "metadata" in versioned_node:
                try:
                    meta = json.loads(versioned_node["metadata"])
                except (json.JSONDecodeError, TypeError):
                    meta = {}
                meta["logical_id"] = logical_id
                meta["content_hash"] = content_hash
                meta["is_latest"] = True
                versioned_node["metadata"] = _json_canonical(meta)

            versioned_nodes.append(versioned_node)

        return RevisionResult(
            new_nodes=versioned_nodes,
            unchanged_nodes=[],
            superseded_nodes=[],
            supersedes_edges=[],
            stats={
                "new": len(versioned_nodes),
                "unchanged": 0,
                "superseded": 0,
                "supersedes_edges": 0,
                "total_current": len(current_nodes),
                "total_previous": 0,
            },
        )

    # Load previous snapshot and compare
    previous = load_snapshot(latest_export)
    return compute_revision(current_nodes, previous, reason=reason)


# ============================================================================
# Test
# ============================================================================

if __name__ == "__main__":
    from .features_from_fred import extract_features
    from .regime_classifier import RegimeClassifier
    from .calibration import load_calibration
    from .graph_nodes import generate_regime_nodes
    from .thesis_nodes import generate_thesis_nodes, CANONICAL_THESES

    # Generate current nodes
    thesis_nodes = generate_thesis_nodes(CANONICAL_THESES)

    cal = load_calibration()
    features, _ = extract_features()
    regimes = RegimeClassifier(calibrated=cal).classify_series(features)
    filtered = [r for r in regimes if r.date >= "2020-01"]

    regime_nodes = generate_regime_nodes(
        regimes, cal.calibration_hash,
        start_date="2020-01",
        regime_receipt_id="revision-test"
    )

    all_nodes = thesis_nodes + regime_nodes

    # Apply revision against previous export
    result = apply_revision(all_nodes, reason="test_revision")

    print("=== BELIEF REVISION RESULT ===")
    print(f"  New nodes:        {result.stats['new']}")
    print(f"  Unchanged:        {result.stats['unchanged']}")
    print(f"  Superseded:       {result.stats['superseded']}")
    print(f"  SUPERSEDES edges: {result.stats['supersedes_edges']}")

    # Show sample versioned ID
    if result.new_nodes:
        sample = result.new_nodes[0]
        print(f"\nSample versioned ID: {sample['node_id']}")

    # Show supersedes edges if any
    if result.supersedes_edges:
        print("\nSUPERSEDES edges:")
        for e in result.supersedes_edges[:5]:
            meta = json.loads(e["metadata"])
            print(f"  {e['from_node_id'][:40]}... -> {e['to_node_id'][:40]}...")
            print(f"    reason: {meta['reason']}, diff: {meta['diff_keys']}")
