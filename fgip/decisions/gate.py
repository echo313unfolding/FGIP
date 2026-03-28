"""
Decision Gate System.

Gates are binary checkpoints that must pass before a decision can proceed.
Any RED gate is a hard stop. All gates must be GREEN to advance.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from enum import Enum
import json


class GateStatus(str, Enum):
    """Gate status values."""
    NOT_STARTED = "NOT_STARTED"  # Haven't begun checking
    PENDING = "PENDING"          # In progress, awaiting data
    GREEN = "GREEN"              # Pass - can proceed
    AMBER = "AMBER"              # Caution - needs review
    RED = "RED"                  # Fail - hard stop


@dataclass
class GateCheck:
    """A single check/update to a gate."""
    checked_at: str
    status: GateStatus
    evidence: str           # What was checked
    source: str             # Where the data came from
    notes: Optional[str] = None
    checked_by: str = "system"

    def to_dict(self) -> dict:
        return {
            "checked_at": self.checked_at,
            "status": self.status.value,
            "evidence": self.evidence,
            "source": self.source,
            "notes": self.notes,
            "checked_by": self.checked_by,
        }


@dataclass
class Gate:
    """A decision gate with criteria and status tracking."""
    gate_id: str
    gate_number: int
    name: str
    criteria: str
    category: str           # financial, location, property, personal

    # Current status
    status: GateStatus = GateStatus.NOT_STARTED

    # Check history (belief revision - track all checks, not just latest)
    checks: List[GateCheck] = field(default_factory=list)

    # For community-specific gates
    applies_to: str = "decision"  # "decision" or specific community_id

    def check(
        self,
        status: GateStatus,
        evidence: str,
        source: str,
        notes: Optional[str] = None,
        checked_by: str = "system",
    ) -> GateCheck:
        """Record a gate check. Updates status and appends to history."""
        check = GateCheck(
            checked_at=datetime.now(timezone.utc).isoformat(),
            status=status,
            evidence=evidence,
            source=source,
            notes=notes,
            checked_by=checked_by,
        )
        self.checks.append(check)
        self.status = status
        return check

    def latest_check(self) -> Optional[GateCheck]:
        """Get most recent check."""
        return self.checks[-1] if self.checks else None

    def is_blocking(self) -> bool:
        """Returns True if this gate is blocking progress."""
        return self.status in (GateStatus.NOT_STARTED, GateStatus.PENDING, GateStatus.RED)

    def to_dict(self) -> dict:
        return {
            "gate_id": self.gate_id,
            "gate_number": self.gate_number,
            "name": self.name,
            "criteria": self.criteria,
            "category": self.category,
            "status": self.status.value,
            "applies_to": self.applies_to,
            "checks": [c.to_dict() for c in self.checks],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Gate":
        gate = cls(
            gate_id=data["gate_id"],
            gate_number=data["gate_number"],
            name=data["name"],
            criteria=data["criteria"],
            category=data["category"],
            status=GateStatus(data["status"]),
            applies_to=data.get("applies_to", "decision"),
        )
        gate.checks = [
            GateCheck(
                checked_at=c["checked_at"],
                status=GateStatus(c["status"]),
                evidence=c["evidence"],
                source=c["source"],
                notes=c.get("notes"),
                checked_by=c.get("checked_by", "system"),
            )
            for c in data.get("checks", [])
        ]
        return gate


# Standard gates for condo decision (from CONDO_DECISION_2026 doc)
CONDO_DECISION_GATES = [
    Gate(
        gate_id="financial_runway",
        gate_number=1,
        name="Financial Runway",
        criteria="12-18 months living costs in liquid T-Bills/cash BEFORE any purchase",
        category="financial",
    ),
    Gate(
        gate_id="tax_set_aside",
        gate_number=2,
        name="Tax Set-Aside",
        criteria="CPA-confirmed tax liability bucket funded in separate account",
        category="financial",
    ),
    Gate(
        gate_id="cooling_period",
        gate_number=3,
        name="Cooling Period",
        criteria="Minimum 60 days post-settlement before any binding offer",
        category="financial",
    ),
    Gate(
        gate_id="location_score",
        gate_number=4,
        name="Location Score >= 70",
        criteria="FGIP Location Scorer must rate area >= 70/100",
        category="location",
    ),
    Gate(
        gate_id="insurance_verified",
        gate_number=5,
        name="Insurance Verified",
        criteria="Written quote in hand. Annual < 2% of purchase price.",
        category="property",
    ),
    Gate(
        gate_id="hoa_reserve_health",
        gate_number=6,
        name="HOA Reserve Health",
        criteria="Reserve study reviewed. Funded > 70%. No pending assessments. No litigation.",
        category="property",
    ),
    Gate(
        gate_id="flood_zone_clear",
        gate_number=7,
        name="Flood Zone Clear",
        criteria="FEMA Zone X confirmed for specific parcel",
        category="property",
    ),
    Gate(
        gate_id="building_age_check",
        gate_number=8,
        name="Building Age Check",
        criteria="If pre-2002: structural inspection. Post-Surfside SB 4D milestone confirmed.",
        category="property",
    ),
    Gate(
        gate_id="healthcare_gate",
        gate_number=9,
        name="Healthcare Gate",
        criteria="Quality hospital (CMS 3+ stars) within 30-45 min drive",
        category="location",
    ),
    Gate(
        gate_id="rent_vs_buy_calc",
        gate_number=10,
        name="Rent vs Buy Calc",
        criteria="Total monthly ownership (PITI+HOA+insurance+maint) < 1.3x comparable rent",
        category="financial",
    ),
    Gate(
        gate_id="stacey_signoff",
        gate_number=11,
        name="Stacey Sign-Off",
        criteria="Both decision owners agree. Documented.",
        category="personal",
    ),
]


def get_default_gates() -> List[Gate]:
    """Get fresh copy of default condo decision gates."""
    return [
        Gate(
            gate_id=g.gate_id,
            gate_number=g.gate_number,
            name=g.name,
            criteria=g.criteria,
            category=g.category,
        )
        for g in CONDO_DECISION_GATES
    ]
