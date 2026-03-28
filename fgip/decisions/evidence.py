"""
Evidence Collection for Decisions.

Every claim needs a receipt. Evidence tracks where information came from.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from enum import Enum
import hashlib
import json


class EvidenceType(str, Enum):
    """Types of evidence that support a decision."""
    DOCUMENT = "document"           # PDF, docx, etc.
    QUOTE = "quote"                 # Insurance quote, price quote
    INSPECTION = "inspection"       # Building inspection report
    FINANCIAL = "financial"         # Bank statement, tax document
    LEGAL = "legal"                 # HOA docs, title search
    MEASUREMENT = "measurement"     # Distance, area, etc.
    SCREENSHOT = "screenshot"       # Web capture
    RECEIPT = "receipt"             # FGIP system receipt
    MANUAL = "manual"               # Manual observation/note
    API = "api"                     # API response data


@dataclass
class Evidence:
    """A piece of evidence supporting a decision or gate check."""
    evidence_id: str
    evidence_type: EvidenceType
    description: str
    source: str                     # Where it came from
    collected_at: str               # ISO timestamp
    collected_by: str               # Who collected it

    # Content
    content_summary: str            # Brief summary of what it shows
    content_path: Optional[str] = None  # Path to file if stored
    content_hash: Optional[str] = None  # SHA256 if file exists

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Provenance
    supersedes: Optional[str] = None  # ID of evidence this replaces

    def to_dict(self) -> dict:
        return {
            "evidence_id": self.evidence_id,
            "evidence_type": self.evidence_type.value,
            "description": self.description,
            "source": self.source,
            "collected_at": self.collected_at,
            "collected_by": self.collected_by,
            "content_summary": self.content_summary,
            "content_path": self.content_path,
            "content_hash": self.content_hash,
            "metadata": self.metadata,
            "supersedes": self.supersedes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Evidence":
        return cls(
            evidence_id=data["evidence_id"],
            evidence_type=EvidenceType(data["evidence_type"]),
            description=data["description"],
            source=data["source"],
            collected_at=data["collected_at"],
            collected_by=data["collected_by"],
            content_summary=data["content_summary"],
            content_path=data.get("content_path"),
            content_hash=data.get("content_hash"),
            metadata=data.get("metadata", {}),
            supersedes=data.get("supersedes"),
        )


def create_evidence(
    evidence_type: EvidenceType,
    description: str,
    source: str,
    content_summary: str,
    collected_by: str = "system",
    content_path: Optional[str] = None,
    metadata: Optional[Dict] = None,
    supersedes: Optional[str] = None,
) -> Evidence:
    """Create a new evidence record with auto-generated ID and timestamp."""
    ts = datetime.now(timezone.utc)
    evidence_id = f"ev-{ts.strftime('%Y%m%dT%H%M%S')}-{hashlib.sha256(description.encode()).hexdigest()[:8]}"

    # Compute hash if file path provided
    content_hash = None
    if content_path:
        try:
            from pathlib import Path
            content_hash = hashlib.sha256(Path(content_path).read_bytes()).hexdigest()
        except Exception:
            pass

    return Evidence(
        evidence_id=evidence_id,
        evidence_type=evidence_type,
        description=description,
        source=source,
        collected_at=ts.isoformat(),
        collected_by=collected_by,
        content_summary=content_summary,
        content_path=content_path,
        content_hash=content_hash,
        metadata=metadata or {},
        supersedes=supersedes,
    )


def create_location_score_evidence(area_id: str, score: float, scorer_output: dict) -> Evidence:
    """Create evidence from location scorer output."""
    return create_evidence(
        evidence_type=EvidenceType.RECEIPT,
        description=f"Location score for {area_id}",
        source="FGIP Location Scorer (WO-FGIP-LOCATION-GATE-01)",
        content_summary=f"Area {area_id} scored {score:.1f}/100",
        metadata={
            "area_id": area_id,
            "score": score,
            "component_scores": scorer_output.get("component_scores", {}),
            "red_flags": scorer_output.get("red_flags", []),
        },
    )


def create_insurance_quote_evidence(
    carrier: str,
    annual_premium: float,
    coverage: str,
    quote_date: str,
    community: str,
) -> Evidence:
    """Create evidence from insurance quote."""
    return create_evidence(
        evidence_type=EvidenceType.QUOTE,
        description=f"Insurance quote from {carrier} for {community}",
        source=carrier,
        content_summary=f"Annual premium ${annual_premium:,.0f} for {coverage}",
        metadata={
            "carrier": carrier,
            "annual_premium": annual_premium,
            "coverage": coverage,
            "quote_date": quote_date,
            "community": community,
        },
    )


def create_hoa_evidence(
    community: str,
    reserve_funded_pct: float,
    monthly_fee: float,
    has_litigation: bool,
    recent_assessments: List[dict],
) -> Evidence:
    """Create evidence from HOA document review."""
    return create_evidence(
        evidence_type=EvidenceType.LEGAL,
        description=f"HOA reserve study and records for {community}",
        source=f"{community} HOA",
        content_summary=f"Reserve {reserve_funded_pct:.0f}% funded, HOA ${monthly_fee}/mo",
        metadata={
            "community": community,
            "reserve_funded_pct": reserve_funded_pct,
            "monthly_fee": monthly_fee,
            "has_litigation": has_litigation,
            "recent_assessments": recent_assessments,
        },
    )
