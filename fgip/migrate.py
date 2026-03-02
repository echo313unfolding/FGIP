"""FGIP Migration - Convert legacy edges to Square-One compliant claims."""

import json
from datetime import datetime
from typing import Optional
import re

from .schema import (
    Source, Claim, ClaimStatus, compute_sha256, extract_domain, auto_tier_domain
)
from .db import FGIPDatabase


# Topic inference from edge types and notes
TOPIC_INFERENCE = {
    "LOBBIED_FOR": "Lobbying",
    "LOBBIED_AGAINST": "Lobbying",
    "FILED_AMICUS": "Judicial",
    "OWNS_SHARES": "Ownership",
    "EMPLOYS": "Network",
    "EMPLOYED": "Network",
    "MARRIED_TO": "Network",
    "DONATED_TO": "Network",
    "APPOINTED_BY": "Judicial",
    "RULED_ON": "Judicial",
    "CAUSED": "Downstream",
    "CORRECTS": "Reshoring",
    "OPPOSES_CORRECTION": "Reshoring",
    "OWNS_MEDIA": "Ownership",
    "REPORTS_ON": "Media",
    "MEMBER_OF": "Network",
    "INVESTED_IN": "Ownership",
    "SUPPLIES": "Supply Chain",
    "ENABLED": "Downstream",
}

# Required tier inference
def infer_required_tier(claim_text: str, edge_type: str) -> int:
    """Infer required evidence tier based on claim content."""
    text_lower = claim_text.lower()

    # Tier 0 required for hard numbers
    if any(x in text_lower for x in ['%', 'percent', 'shares', 'ownership']):
        return 0
    if re.search(r'\$[\d,]+', claim_text):  # Dollar amounts
        return 0
    if edge_type in ("OWNS_SHARES", "RULED_ON", "FILED_AMICUS"):
        return 0

    # Tier 1 for analytical claims
    if edge_type in ("CAUSED", "CORRECTS", "ENABLED"):
        return 1

    # Default
    return 1


def generate_claim_text(edge: dict) -> str:
    """Generate claim text from edge fields."""
    parts = []

    # Get node names if possible
    from_id = edge.get("from_node_id", "")
    to_id = edge.get("to_node_id", "")
    edge_type = edge.get("edge_type", "")
    notes = edge.get("notes", "")

    # Format based on edge type
    if edge_type == "OWNS_SHARES":
        parts.append(f"{from_id} owns shares in {to_id}")
        if notes:
            parts.append(f"({notes})")
    elif edge_type == "LOBBIED_FOR":
        parts.append(f"{from_id} lobbied for {to_id}")
        if notes:
            parts.append(f"- {notes}")
    elif edge_type == "LOBBIED_AGAINST":
        parts.append(f"{from_id} lobbied against {to_id}")
    elif edge_type == "FILED_AMICUS":
        parts.append(f"{from_id} filed amicus brief in {to_id}")
    elif edge_type == "MARRIED_TO":
        parts.append(f"{from_id} married to {to_id}")
    elif edge_type == "DONATED_TO":
        parts.append(f"{from_id} donated to {to_id}")
    elif edge_type == "EMPLOYS" or edge_type == "EMPLOYED":
        parts.append(f"{from_id} employed {to_id}")
    elif edge_type == "RULED_ON":
        parts.append(f"{from_id} ruled on {to_id}")
    elif edge_type == "CAUSED":
        parts.append(f"{from_id} caused {to_id}")
    elif edge_type == "CORRECTS":
        parts.append(f"{from_id} corrects {to_id}")
    elif edge_type == "OPPOSES_CORRECTION":
        parts.append(f"{from_id} opposes correction of {to_id}")
    elif edge_type == "MEMBER_OF":
        parts.append(f"{from_id} is member of {to_id}")
    elif edge_type == "INVESTED_IN":
        parts.append(f"{from_id} invested in {to_id}")
    else:
        parts.append(f"{from_id} --{edge_type}--> {to_id}")

    if notes and notes not in " ".join(parts):
        parts.append(f"[{notes}]")

    return " ".join(parts)


def determine_claim_status(source: Optional[str], source_url: Optional[str]) -> ClaimStatus:
    """Determine claim status based on source fields."""
    if not source_url or source_url.strip() == "":
        # No URL - check if source is a placeholder
        if not source or source.lower() in ("public record", "public records", "earnings calls",
                                            "tax filings", "sec filings", "court filings"):
            return ClaimStatus.MISSING
        return ClaimStatus.MISSING

    # Has URL - PARTIAL until artifact captured
    return ClaimStatus.PARTIAL


class FGIPMigrator:
    """Migrate legacy edges to Square-One compliance."""

    def __init__(self, db: FGIPDatabase):
        self.db = db
        self.sources_created = 0
        self.claims_created = 0
        self.edges_updated = 0
        self.errors = []

    def migrate_all(self) -> dict:
        """Run full migration from legacy edges to Square-One."""
        print("Starting Square-One migration...")

        # Step 1: Load all existing edges
        edges = self.db.list_edges(limit=10000)
        print(f"Found {len(edges)} edges to migrate")

        for edge in edges:
            try:
                self._migrate_edge(edge)
            except Exception as e:
                self.errors.append({"edge_id": edge.edge_id, "error": str(e)})

        return {
            "sources_created": self.sources_created,
            "claims_created": self.claims_created,
            "edges_updated": self.edges_updated,
            "errors": self.errors,
        }

    def _migrate_edge(self, edge):
        """Migrate a single edge to Square-One compliance."""
        # Skip if already has claim_id
        if edge.claim_id:
            return

        # Step 1: Create source from source_url if present
        source_id = None
        if edge.source_url and edge.source_url.strip():
            source = Source.from_url(edge.source_url)
            source.notes = edge.source
            if self.db.insert_source(source):
                self.sources_created += 1
            source_id = source.source_id

        # Step 2: Create claim
        claim_id = self.db.get_next_claim_id()
        claim_text = generate_claim_text(edge.to_dict())
        topic = TOPIC_INFERENCE.get(edge.edge_type.value, "General")
        status = determine_claim_status(edge.source, edge.source_url)
        required_tier = infer_required_tier(claim_text, edge.edge_type.value)

        claim = Claim(
            claim_id=claim_id,
            claim_text=claim_text,
            topic=topic,
            status=status,
            required_tier=required_tier,
            notes=f"Migrated from edge {edge.edge_id}. Source: {edge.source}"
        )

        if self.db.insert_claim(claim):
            self.claims_created += 1

            # Step 3: Link claim to source
            if source_id:
                self.db.link_claim_source(claim_id, source_id)

            # Step 4: Update edge with claim_id
            if self.db.update_edge_claim(edge.edge_id, claim_id):
                self.edges_updated += 1


def load_sources_from_file(db: FGIPDatabase, filepath: str) -> dict:
    """Load sources from fgip_all_source_urls.txt."""
    created = 0
    errors = []

    with open(filepath, 'r') as f:
        for line_num, line in enumerate(f, 1):
            url = line.strip()
            if not url or url.startswith('#'):
                continue

            try:
                source = Source.from_url(url)
                if db.insert_source(source):
                    created += 1
            except Exception as e:
                errors.append({"line": line_num, "url": url, "error": str(e)})

    return {"created": created, "errors": errors}


def upgrade_claim(db: FGIPDatabase, claim_id: str, artifact_path: str) -> bool:
    """Upgrade a claim by attaching artifact and computing hash."""
    import os

    claim = db.get_claim(claim_id)
    if not claim:
        return False

    # Compute artifact hash
    try:
        with open(artifact_path, 'rb') as f:
            artifact_hash = compute_sha256(f.read())
    except Exception:
        return False

    # Get sources for this claim and update with artifact
    sources = db.get_claim_sources(claim_id)
    for source in sources:
        conn = db.connect()
        conn.execute(
            "UPDATE sources SET artifact_path = ?, artifact_hash = ? WHERE source_id = ?",
            (artifact_path, artifact_hash, source.source_id)
        )
        conn.commit()

    # Determine new status based on source tier
    best_tier = min((s.tier for s in sources), default=2)
    if best_tier <= 1:
        new_status = ClaimStatus.VERIFIED
    else:
        new_status = ClaimStatus.EVIDENCED

    db.update_claim_status(claim_id, new_status)
    return True
