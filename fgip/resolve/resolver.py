"""
Entity resolver for FGIP - generates SAME_AS proposals.

Resolution strategies (in confidence order):
1. Canonical ID match (CIK, ticker, LEI, etc.) - 0.95 confidence
2. Exact normalized name match - 0.80 confidence
3. Alias match - 0.70 confidence
4. Fuzzy name match - configurable threshold (optional)

All proposals are inferential (SAME_AS) until approved,
at which point they become factual (MERGED_INTO).
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .canonical import get_canonical_id, normalize_name


@dataclass
class SameAsProposal:
    """A proposed entity merge between two nodes."""

    proposal_id: str
    node_a_id: str
    node_b_id: str
    node_type: str
    confidence: float
    reason: str
    match_type: str  # "canonical", "name_exact", "name_fuzzy", "alias"
    status: str = "PENDING"  # PENDING, APPROVED, REJECTED
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reviewed_at: Optional[str] = None
    reviewed_by: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dict for serialization."""
        return {
            "proposal_id": self.proposal_id,
            "node_a_id": self.node_a_id,
            "node_b_id": self.node_b_id,
            "node_type": self.node_type,
            "confidence": self.confidence,
            "reason": self.reason,
            "match_type": self.match_type,
            "status": self.status,
            "created_at": self.created_at,
            "reviewed_at": self.reviewed_at,
            "reviewed_by": self.reviewed_by,
        }

    def to_edge_dict(self) -> dict:
        """Convert to SAME_AS edge format for graph export."""
        return {
            "edge_id": self.proposal_id,
            "edge_type": "SAME_AS",
            "from_node_id": self.node_a_id,
            "to_node_id": self.node_b_id,
            "confidence": self.confidence,
            "notes": self.reason,
            "metadata": json.dumps({
                "match_type": self.match_type,
                "status": self.status,
                "assertion_level": "INFERENCE",
            }, sort_keys=True, separators=(",", ":")),
        }


class EntityResolver:
    """
    Resolve duplicate entities and generate SAME_AS proposals.

    Usage:
        resolver = EntityResolver()
        proposals = resolver.find_duplicates(nodes)
        edges = resolver.to_same_as_edges()
    """

    # Node types that should be excluded from entity resolution
    # (they already have unique, structured IDs)
    EXCLUDED_TYPES = {"HYPOTHESIS", "REGIME_STATE"}

    def __init__(self, fuzzy_threshold: float = 0.0):
        """
        Args:
            fuzzy_threshold: Minimum similarity for fuzzy matches (0 = disabled)
        """
        self.fuzzy_threshold = fuzzy_threshold
        self.proposals: List[SameAsProposal] = []

        # Indexes for resolution
        self.canonical_index: Dict[str, List[str]] = {}  # canonical_id -> [node_ids]
        self.name_index: Dict[str, List[str]] = {}       # normalized_name -> [node_ids]
        self.alias_index: Dict[str, List[str]] = {}      # alias -> [node_ids]

        # Node lookup
        self.nodes_by_id: Dict[str, dict] = {}

    def _stable_proposal_id(self, node_a: str, node_b: str) -> str:
        """Generate deterministic proposal ID from node pair."""
        # Sort to ensure same pair always gets same ID
        pair = tuple(sorted([node_a, node_b]))
        h = hashlib.sha256(f"SAME_AS|{pair[0]}|{pair[1]}".encode()).hexdigest()
        return f"same_as-{h[:16]}"

    def _parse_metadata(self, node: dict) -> dict:
        """Parse metadata from node, handling string or dict."""
        metadata = node.get("metadata", {})
        if isinstance(metadata, str):
            try:
                return json.loads(metadata)
            except (json.JSONDecodeError, TypeError):
                return {}
        return metadata if isinstance(metadata, dict) else {}

    def _parse_aliases(self, node: dict) -> List[str]:
        """Parse aliases from node, handling string or list."""
        aliases = node.get("aliases", [])
        if isinstance(aliases, str):
            try:
                aliases = json.loads(aliases)
            except (json.JSONDecodeError, TypeError):
                aliases = []
        return aliases if isinstance(aliases, list) else []

    def build_indexes(self, nodes: List[dict]) -> None:
        """
        Build lookup indexes from node list.

        Args:
            nodes: List of node dicts
        """
        self.canonical_index.clear()
        self.name_index.clear()
        self.alias_index.clear()
        self.nodes_by_id.clear()

        for node in nodes:
            node_id = node.get("node_id", "")
            if not node_id:
                continue

            node_type = node.get("node_type", "")
            name = node.get("name", "")

            self.nodes_by_id[node_id] = node

            # Skip excluded types (they have structured unique IDs)
            if node_type in self.EXCLUDED_TYPES:
                continue

            # Canonical ID index (keyed by type:canonical_id)
            canonical = get_canonical_id(node_type, node)
            if canonical:
                key = f"{node_type}:{canonical}"
                if key not in self.canonical_index:
                    self.canonical_index[key] = []
                if node_id not in self.canonical_index[key]:
                    self.canonical_index[key].append(node_id)

            # Name index (keyed by type:normalized_name)
            norm_name = normalize_name(name)
            if norm_name:
                key = f"{node_type}:{norm_name}"
                if key not in self.name_index:
                    self.name_index[key] = []
                if node_id not in self.name_index[key]:
                    self.name_index[key].append(node_id)

            # Alias index
            aliases = self._parse_aliases(node)
            for alias in aliases:
                norm_alias = normalize_name(alias)
                if norm_alias:
                    key = f"{node_type}:{norm_alias}"
                    if key not in self.alias_index:
                        self.alias_index[key] = []
                    if node_id not in self.alias_index[key]:
                        self.alias_index[key].append(node_id)

    def find_duplicates(self, nodes: List[dict]) -> List[SameAsProposal]:
        """
        Find duplicate entities and generate SAME_AS proposals.

        Args:
            nodes: List of node dicts

        Returns:
            List of SameAsProposal objects
        """
        self.build_indexes(nodes)
        self.proposals.clear()
        seen_pairs: Set[Tuple[str, str]] = set()

        # 1. Canonical ID matches (highest confidence)
        for key, node_ids in self.canonical_index.items():
            if len(node_ids) > 1:
                node_type = key.split(":", 1)[0]
                canonical_id = key.split(":", 1)[1] if ":" in key else key

                for i, id_a in enumerate(node_ids):
                    for id_b in node_ids[i + 1:]:
                        pair = tuple(sorted([id_a, id_b]))
                        if pair not in seen_pairs:
                            seen_pairs.add(pair)
                            self.proposals.append(SameAsProposal(
                                proposal_id=self._stable_proposal_id(id_a, id_b),
                                node_a_id=pair[0],
                                node_b_id=pair[1],
                                node_type=node_type,
                                confidence=0.95,
                                reason=f"Same canonical ID: {canonical_id}",
                                match_type="canonical",
                            ))

        # 2. Exact name matches (medium-high confidence)
        for key, node_ids in self.name_index.items():
            if len(node_ids) > 1:
                node_type = key.split(":", 1)[0]
                norm_name = key.split(":", 1)[1] if ":" in key else key

                for i, id_a in enumerate(node_ids):
                    for id_b in node_ids[i + 1:]:
                        pair = tuple(sorted([id_a, id_b]))
                        if pair not in seen_pairs:
                            seen_pairs.add(pair)
                            self.proposals.append(SameAsProposal(
                                proposal_id=self._stable_proposal_id(id_a, id_b),
                                node_a_id=pair[0],
                                node_b_id=pair[1],
                                node_type=node_type,
                                confidence=0.80,
                                reason=f"Same normalized name: {norm_name}",
                                match_type="name_exact",
                            ))

        # 3. Alias matches (medium confidence)
        for key, node_ids in self.alias_index.items():
            if len(node_ids) > 1:
                node_type = key.split(":", 1)[0]
                alias_name = key.split(":", 1)[1] if ":" in key else key

                for i, id_a in enumerate(node_ids):
                    for id_b in node_ids[i + 1:]:
                        pair = tuple(sorted([id_a, id_b]))
                        if pair not in seen_pairs:
                            seen_pairs.add(pair)
                            self.proposals.append(SameAsProposal(
                                proposal_id=self._stable_proposal_id(id_a, id_b),
                                node_a_id=pair[0],
                                node_b_id=pair[1],
                                node_type=node_type,
                                confidence=0.70,
                                reason=f"Same alias: {alias_name}",
                                match_type="alias",
                            ))

        # Sort by confidence descending for review prioritization
        self.proposals.sort(key=lambda p: -p.confidence)

        return self.proposals

    def to_same_as_edges(self) -> List[dict]:
        """
        Convert proposals to SAME_AS edge dicts for graph export.

        Returns:
            List of edge dicts
        """
        return [p.to_edge_dict() for p in self.proposals]

    def write_proposals(
        self,
        output_dir: str,
        receipt_id: Optional[str] = None,
    ) -> Tuple[str, str]:
        """
        Write proposals to JSONL file with receipt.

        Args:
            output_dir: Directory to write proposals
            receipt_id: Optional receipt ID (auto-generated if not provided)

        Returns:
            (proposals_file_path, receipt_file_path)
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        if receipt_id is None:
            receipt_id = f"entity-resolve-{ts}"

        proposals_file = output_path / f"same_as_proposals-{ts}.jsonl"

        # Write proposals
        with proposals_file.open("w") as f:
            for p in self.proposals:
                f.write(json.dumps(p.to_dict(), sort_keys=True, separators=(",", ":")) + "\n")

        # Compute hash
        proposals_hash = hashlib.sha256(proposals_file.read_bytes()).hexdigest()

        # Write receipt
        receipt_file = output_path / f"RESOLVE_RECEIPT-{ts}.json"
        receipt = {
            "receipt_id": receipt_id,
            "generated_at": ts,
            "proposals_file": str(proposals_file),
            "proposals_hash": proposals_hash,
            "proposal_count": len(self.proposals),
            "by_match_type": {
                match_type: len([p for p in self.proposals if p.match_type == match_type])
                for match_type in ["canonical", "name_exact", "alias"]
            },
            "by_status": {
                status: len([p for p in self.proposals if p.status == status])
                for status in ["PENDING", "APPROVED", "REJECTED"]
            },
        }

        with receipt_file.open("w") as f:
            json.dump(receipt, f, indent=2)

        return str(proposals_file), str(receipt_file)

    def get_summary(self) -> dict:
        """
        Get summary statistics of proposals.

        Returns:
            Dict with proposal counts by type and status
        """
        return {
            "total_proposals": len(self.proposals),
            "by_match_type": {
                "canonical": len([p for p in self.proposals if p.match_type == "canonical"]),
                "name_exact": len([p for p in self.proposals if p.match_type == "name_exact"]),
                "alias": len([p for p in self.proposals if p.match_type == "alias"]),
            },
            "by_status": {
                "PENDING": len([p for p in self.proposals if p.status == "PENDING"]),
                "APPROVED": len([p for p in self.proposals if p.status == "APPROVED"]),
                "REJECTED": len([p for p in self.proposals if p.status == "REJECTED"]),
            },
            "avg_confidence": (
                sum(p.confidence for p in self.proposals) / len(self.proposals)
                if self.proposals else 0.0
            ),
        }
