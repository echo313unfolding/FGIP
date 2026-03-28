"""
Community Candidate Tracking.

Tracks communities under evaluation with per-community gate status.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Dict
from enum import Enum

from .gate import Gate, GateStatus, GateCheck


class CommunityStatus(str, Enum):
    """Status of a community in the evaluation pipeline."""
    IDENTIFIED = "IDENTIFIED"       # Found, not yet evaluated
    EVALUATE = "EVALUATE"           # Active evaluation
    SHORTLIST = "SHORTLIST"         # Passed initial gates, serious consideration
    OFFER = "OFFER"                 # Preparing or submitted offer
    REJECTED = "REJECTED"           # Eliminated for specific reason
    SELECTED = "SELECTED"           # Final choice


@dataclass
class CommunityCandidate:
    """A community under evaluation for purchase."""
    community_id: str
    name: str
    area: str                       # e.g., "Ocala"
    county: str

    # Basic info
    price_range_low: float
    price_range_high: float
    hoa_fee_low: Optional[float] = None
    hoa_fee_high: Optional[float] = None

    # Characteristics
    is_gated: bool = False
    gate_type: str = ""             # e.g., "24hr guard", "unmanned"
    is_55_plus: bool = False
    amenities: List[str] = field(default_factory=list)

    # Status
    status: CommunityStatus = CommunityStatus.IDENTIFIED
    status_reason: str = ""

    # Gate checks (community-specific)
    gate_checks: Dict[str, GateCheck] = field(default_factory=dict)

    # Evidence collected
    evidence_ids: List[str] = field(default_factory=list)

    # Notes
    notes: List[str] = field(default_factory=list)
    red_flags: List[str] = field(default_factory=list)

    # Timestamps
    added_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.added_at:
            self.added_at = datetime.now(timezone.utc).isoformat()
        if not self.updated_at:
            self.updated_at = self.added_at

    def update_status(self, status: CommunityStatus, reason: str = ""):
        """Update community status with timestamp."""
        self.status = status
        self.status_reason = reason
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def add_gate_check(self, gate_id: str, check: GateCheck):
        """Add a gate check for this community."""
        self.gate_checks[gate_id] = check
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def add_red_flag(self, flag: str):
        """Add a red flag."""
        self.red_flags.append(flag)
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def add_note(self, note: str):
        """Add a note."""
        self.notes.append(f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d')}] {note}")
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def get_gate_status(self, gate_id: str) -> GateStatus:
        """Get status of a specific gate for this community."""
        if gate_id in self.gate_checks:
            return self.gate_checks[gate_id].status
        return GateStatus.NOT_STARTED

    def passes_budget(self, max_budget: float) -> bool:
        """Check if community fits budget."""
        return self.price_range_low <= max_budget

    def to_dict(self) -> dict:
        return {
            "community_id": self.community_id,
            "name": self.name,
            "area": self.area,
            "county": self.county,
            "price_range_low": self.price_range_low,
            "price_range_high": self.price_range_high,
            "hoa_fee_low": self.hoa_fee_low,
            "hoa_fee_high": self.hoa_fee_high,
            "is_gated": self.is_gated,
            "gate_type": self.gate_type,
            "is_55_plus": self.is_55_plus,
            "amenities": self.amenities,
            "status": self.status.value,
            "status_reason": self.status_reason,
            "gate_checks": {k: v.to_dict() for k, v in self.gate_checks.items()},
            "evidence_ids": self.evidence_ids,
            "notes": self.notes,
            "red_flags": self.red_flags,
            "added_at": self.added_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CommunityCandidate":
        community = cls(
            community_id=data["community_id"],
            name=data["name"],
            area=data["area"],
            county=data["county"],
            price_range_low=data["price_range_low"],
            price_range_high=data["price_range_high"],
            hoa_fee_low=data.get("hoa_fee_low"),
            hoa_fee_high=data.get("hoa_fee_high"),
            is_gated=data.get("is_gated", False),
            gate_type=data.get("gate_type", ""),
            is_55_plus=data.get("is_55_plus", False),
            amenities=data.get("amenities", []),
            status=CommunityStatus(data.get("status", "IDENTIFIED")),
            status_reason=data.get("status_reason", ""),
            evidence_ids=data.get("evidence_ids", []),
            notes=data.get("notes", []),
            red_flags=data.get("red_flags", []),
            added_at=data.get("added_at", ""),
            updated_at=data.get("updated_at", ""),
        )
        # Load gate checks
        for gate_id, check_data in data.get("gate_checks", {}).items():
            community.gate_checks[gate_id] = GateCheck(
                checked_at=check_data["checked_at"],
                status=GateStatus(check_data["status"]),
                evidence=check_data["evidence"],
                source=check_data["source"],
                notes=check_data.get("notes"),
                checked_by=check_data.get("checked_by", "system"),
            )
        return community


# Communities from CONDO_DECISION_2026 v2
INITIAL_COMMUNITIES = [
    CommunityCandidate(
        community_id="oak-run",
        name="Oak Run",
        area="Ocala",
        county="Marion",
        price_range_low=150000,
        price_range_high=250000,
        hoa_fee_low=110,
        hoa_fee_high=250,
        is_gated=True,
        gate_type="guarded",
        is_55_plus=True,
        status=CommunityStatus.EVALUATE,
    ),
    CommunityCandidate(
        community_id="on-top-of-the-world",
        name="On Top of the World",
        area="Ocala",
        county="Marion",
        price_range_low=180000,
        price_range_high=350000,
        is_gated=True,
        is_55_plus=True,
        status=CommunityStatus.EVALUATE,
    ),
    CommunityCandidate(
        community_id="ocala-palms",
        name="Ocala Palms",
        area="Ocala",
        county="Marion",
        price_range_low=200000,
        price_range_high=280000,
        hoa_fee_low=175,
        hoa_fee_high=225,
        is_gated=True,
        is_55_plus=True,
        status=CommunityStatus.EVALUATE,
    ),
    CommunityCandidate(
        community_id="stone-creek",
        name="Stone Creek (Del Webb)",
        area="Ocala",
        county="Marion",
        price_range_low=250000,
        price_range_high=400000,
        is_gated=True,
        is_55_plus=True,
        status=CommunityStatus.EVALUATE,
    ),
    CommunityCandidate(
        community_id="brighton-fore-ranch",
        name="Brighton at Fore Ranch",
        area="Ocala",
        county="Marion",
        price_range_low=200000,
        price_range_high=280000,
        is_gated=True,
        is_55_plus=False,
        status=CommunityStatus.EVALUATE,
    ),
    CommunityCandidate(
        community_id="cypress-woods",
        name="Cypress Woods G&CC",
        area="Winter Haven",
        county="Polk",
        price_range_low=150000,
        price_range_high=250000,
        is_gated=True,
        gate_type="24hr guard",
        is_55_plus=False,
        status=CommunityStatus.EVALUATE,
    ),
    CommunityCandidate(
        community_id="magnolia-pointe",
        name="Magnolia Pointe",
        area="Clermont",
        county="Lake",
        price_range_low=200000,
        price_range_high=300000,
        is_gated=True,
        gate_type="guarded",
        is_55_plus=False,
        status=CommunityStatus.EVALUATE,
    ),
    CommunityCandidate(
        community_id="silver-lakes",
        name="Silver Lakes",
        area="Lakeland",
        county="Polk",
        price_range_low=220000,
        price_range_high=270000,
        is_gated=True,
        is_55_plus=True,
        status=CommunityStatus.EVALUATE,
    ),
    CommunityCandidate(
        community_id="sandpiper",
        name="Sandpiper G&CC",
        area="Lakeland",
        county="Polk",
        price_range_low=200000,
        price_range_high=300000,
        is_gated=True,
        is_55_plus=True,
        status=CommunityStatus.EVALUATE,
    ),
    CommunityCandidate(
        community_id="sandalwood",
        name="Sandalwood",
        area="Villages-adjacent",
        county="Sumter",
        price_range_low=100000,
        price_range_high=180000,
        is_gated=False,
        gate_type="partial",
        is_55_plus=False,
        status=CommunityStatus.EVALUATE,
        notes=["Villages access without Villages prices"],
    ),
]


def get_initial_communities() -> List[CommunityCandidate]:
    """Get fresh copy of initial communities."""
    return [
        CommunityCandidate(
            community_id=c.community_id,
            name=c.name,
            area=c.area,
            county=c.county,
            price_range_low=c.price_range_low,
            price_range_high=c.price_range_high,
            hoa_fee_low=c.hoa_fee_low,
            hoa_fee_high=c.hoa_fee_high,
            is_gated=c.is_gated,
            gate_type=c.gate_type,
            is_55_plus=c.is_55_plus,
            status=c.status,
            notes=c.notes.copy() if c.notes else [],
        )
        for c in INITIAL_COMMUNITIES
    ]
