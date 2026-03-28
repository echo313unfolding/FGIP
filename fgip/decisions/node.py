"""
Decision Node - First-class decision tracking.

A DecisionNode is a graph entity that tracks:
- Current phase and status
- All gates with check history
- Communities under evaluation
- Evidence collected
- Final decision record
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Tuple
from enum import Enum
import json
import hashlib

from .gate import Gate, GateStatus, GateCheck, get_default_gates
from .evidence import Evidence, EvidenceType
from .community import CommunityCandidate, CommunityStatus, get_initial_communities


class DecisionStatus(str, Enum):
    """Overall decision status."""
    DRAFT = "DRAFT"                 # Initial setup
    EVIDENCE_COLLECTION = "EVIDENCE_COLLECTION"  # Gathering data
    GATES_IN_PROGRESS = "GATES_IN_PROGRESS"      # Checking gates
    READY_FOR_DECISION = "READY_FOR_DECISION"    # All gates green
    DECIDED = "DECIDED"             # Final choice made
    EXECUTED = "EXECUTED"           # Purchase complete
    ABANDONED = "ABANDONED"         # Decision not to proceed


class DecisionPhase(str, Enum):
    """Execution phase."""
    PHASE_0 = "PHASE_0"  # Protect the Principal (Days 1-60)
    PHASE_1 = "PHASE_1"  # Rent-First Reconnaissance (Months 2-12)
    PHASE_2 = "PHASE_2"  # Offer with Gates (Month 6-18)
    PHASE_3 = "PHASE_3"  # Post-Purchase Monitoring


@dataclass
class DecisionRecord:
    """Final decision record - completed when purchase is made."""
    location_scorer_area: str = ""
    location_score: float = 0
    property_address: str = ""
    community_name: str = ""
    purchase_price: float = 0
    monthly_piti: float = 0
    monthly_hoa: float = 0
    annual_insurance: float = 0
    annual_property_tax: float = 0
    total_monthly_cost: float = 0
    flood_zone: str = ""
    reserve_funded_pct: float = 0
    building_age: int = 0
    healthcare_distance_min: float = 0
    healthcare_hospital: str = ""
    healthcare_rating: int = 0
    alternatives_considered: List[str] = field(default_factory=list)
    red_flags_accepted: List[str] = field(default_factory=list)
    red_flags_killed_options: List[str] = field(default_factory=list)
    josh_signature_date: str = ""
    stacey_signature_date: str = ""

    def to_dict(self) -> dict:
        return {
            "location_scorer_area": self.location_scorer_area,
            "location_score": self.location_score,
            "property_address": self.property_address,
            "community_name": self.community_name,
            "purchase_price": self.purchase_price,
            "monthly_piti": self.monthly_piti,
            "monthly_hoa": self.monthly_hoa,
            "annual_insurance": self.annual_insurance,
            "annual_property_tax": self.annual_property_tax,
            "total_monthly_cost": self.total_monthly_cost,
            "flood_zone": self.flood_zone,
            "reserve_funded_pct": self.reserve_funded_pct,
            "building_age": self.building_age,
            "healthcare_distance_min": self.healthcare_distance_min,
            "healthcare_hospital": self.healthcare_hospital,
            "healthcare_rating": self.healthcare_rating,
            "alternatives_considered": self.alternatives_considered,
            "red_flags_accepted": self.red_flags_accepted,
            "red_flags_killed_options": self.red_flags_killed_options,
            "josh_signature_date": self.josh_signature_date,
            "stacey_signature_date": self.stacey_signature_date,
        }


@dataclass
class DecisionNode:
    """First-class decision tracking node."""
    decision_id: str
    decision_type: str              # e.g., "condo_purchase"
    title: str
    description: str

    # Owners
    decision_owners: List[str] = field(default_factory=list)

    # Status
    status: DecisionStatus = DecisionStatus.DRAFT
    phase: DecisionPhase = DecisionPhase.PHASE_0

    # Budget
    budget_min: float = 0
    budget_max: float = 0

    # Gates
    gates: List[Gate] = field(default_factory=list)

    # Communities under evaluation
    communities: List[CommunityCandidate] = field(default_factory=list)

    # Evidence
    evidence: List[Evidence] = field(default_factory=list)

    # Final record
    decision_record: Optional[DecisionRecord] = None

    # Timestamps
    created_at: str = ""
    updated_at: str = ""

    # Versioning
    version: int = 1
    supersedes: Optional[str] = None  # Previous version ID

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at

    def _touch(self):
        """Update timestamp."""
        self.updated_at = datetime.now(timezone.utc).isoformat()

    # Gate management
    def get_gate(self, gate_id: str) -> Optional[Gate]:
        """Get a gate by ID."""
        for gate in self.gates:
            if gate.gate_id == gate_id:
                return gate
        return None

    def check_gate(
        self,
        gate_id: str,
        status: GateStatus,
        evidence: str,
        source: str,
        notes: Optional[str] = None,
        checked_by: str = "system",
    ) -> Optional[GateCheck]:
        """Check a gate and record the result."""
        gate = self.get_gate(gate_id)
        if not gate:
            return None

        check = gate.check(status, evidence, source, notes, checked_by)
        self._touch()
        return check

    def get_gate_summary(self) -> Dict[str, int]:
        """Get count of gates by status."""
        summary = {s.value: 0 for s in GateStatus}
        for gate in self.gates:
            summary[gate.status.value] += 1
        return summary

    def all_gates_green(self) -> bool:
        """Check if all gates are GREEN."""
        return all(g.status == GateStatus.GREEN for g in self.gates)

    def any_gates_red(self) -> bool:
        """Check if any gate is RED."""
        return any(g.status == GateStatus.RED for g in self.gates)

    def blocking_gates(self) -> List[Gate]:
        """Get list of gates blocking progress."""
        return [g for g in self.gates if g.is_blocking()]

    # Community management
    def get_community(self, community_id: str) -> Optional[CommunityCandidate]:
        """Get a community by ID."""
        for c in self.communities:
            if c.community_id == community_id:
                return c
        return None

    def add_community(self, community: CommunityCandidate):
        """Add a community to evaluation."""
        self.communities.append(community)
        self._touch()

    def update_community_status(
        self,
        community_id: str,
        status: CommunityStatus,
        reason: str = "",
    ):
        """Update a community's status."""
        community = self.get_community(community_id)
        if community:
            community.update_status(status, reason)
            self._touch()

    def get_communities_by_status(self, status: CommunityStatus) -> List[CommunityCandidate]:
        """Get communities with a specific status."""
        return [c for c in self.communities if c.status == status]

    def get_shortlist(self) -> List[CommunityCandidate]:
        """Get communities on shortlist or better."""
        return [
            c for c in self.communities
            if c.status in (CommunityStatus.SHORTLIST, CommunityStatus.OFFER, CommunityStatus.SELECTED)
        ]

    # Evidence management
    def add_evidence(self, ev: Evidence):
        """Add evidence to the decision."""
        self.evidence.append(ev)
        self._touch()

    def get_evidence_for_gate(self, gate_id: str) -> List[Evidence]:
        """Get evidence related to a gate."""
        # Simple keyword match for now
        return [e for e in self.evidence if gate_id in e.description.lower()]

    # Status management
    def advance_phase(self):
        """Advance to next phase if conditions met."""
        phases = list(DecisionPhase)
        current_idx = phases.index(self.phase)
        if current_idx < len(phases) - 1:
            self.phase = phases[current_idx + 1]
            self._touch()

    def update_status(self, status: DecisionStatus):
        """Update decision status."""
        self.status = status
        self._touch()

    # Serialization
    def to_dict(self) -> dict:
        return {
            "decision_id": self.decision_id,
            "decision_type": self.decision_type,
            "title": self.title,
            "description": self.description,
            "decision_owners": self.decision_owners,
            "status": self.status.value,
            "phase": self.phase.value,
            "budget_min": self.budget_min,
            "budget_max": self.budget_max,
            "gates": [g.to_dict() for g in self.gates],
            "communities": [c.to_dict() for c in self.communities],
            "evidence": [e.to_dict() for e in self.evidence],
            "decision_record": self.decision_record.to_dict() if self.decision_record else None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
            "supersedes": self.supersedes,
        }

    def compute_hash(self) -> str:
        """Compute deterministic hash of decision state."""
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    @classmethod
    def from_dict(cls, data: dict) -> "DecisionNode":
        node = cls(
            decision_id=data["decision_id"],
            decision_type=data["decision_type"],
            title=data["title"],
            description=data["description"],
            decision_owners=data.get("decision_owners", []),
            status=DecisionStatus(data.get("status", "DRAFT")),
            phase=DecisionPhase(data.get("phase", "PHASE_0")),
            budget_min=data.get("budget_min", 0),
            budget_max=data.get("budget_max", 0),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            version=data.get("version", 1),
            supersedes=data.get("supersedes"),
        )
        node.gates = [Gate.from_dict(g) for g in data.get("gates", [])]
        node.communities = [CommunityCandidate.from_dict(c) for c in data.get("communities", [])]
        node.evidence = [Evidence.from_dict(e) for e in data.get("evidence", [])]
        if data.get("decision_record"):
            node.decision_record = DecisionRecord(**data["decision_record"])
        return node

    # Report generation
    def generate_status_report(self) -> str:
        """Generate human-readable status report."""
        lines = [
            f"# Decision: {self.title}",
            "",
            f"**ID:** {self.decision_id}",
            f"**Status:** {self.status.value}",
            f"**Phase:** {self.phase.value}",
            f"**Budget:** ${self.budget_min:,.0f} - ${self.budget_max:,.0f}",
            f"**Owners:** {', '.join(self.decision_owners)}",
            "",
            "---",
            "",
            "## Gate Status",
            "",
        ]

        gate_summary = self.get_gate_summary()
        lines.append(f"**GREEN:** {gate_summary['GREEN']} | **PENDING:** {gate_summary['PENDING']} | **RED:** {gate_summary['RED']} | **NOT_STARTED:** {gate_summary['NOT_STARTED']}")
        lines.append("")
        lines.append("| # | Gate | Status | Last Check |")
        lines.append("|---|------|--------|------------|")

        for gate in sorted(self.gates, key=lambda g: g.gate_number):
            last_check = gate.latest_check()
            check_info = last_check.checked_at[:10] if last_check else "Never"
            lines.append(f"| {gate.gate_number} | {gate.name} | {gate.status.value} | {check_info} |")

        lines.extend([
            "",
            "---",
            "",
            "## Communities",
            "",
        ])

        status_counts = {}
        for c in self.communities:
            status_counts[c.status.value] = status_counts.get(c.status.value, 0) + 1

        lines.append(f"**Total:** {len(self.communities)} | " + " | ".join(f"**{k}:** {v}" for k, v in status_counts.items()))
        lines.append("")
        lines.append("| Community | Area | Price Range | Status | Red Flags |")
        lines.append("|-----------|------|-------------|--------|-----------|")

        for c in self.communities:
            flags = len(c.red_flags)
            flag_str = f"{flags} flags" if flags else "None"
            lines.append(
                f"| {c.name} | {c.area} | ${c.price_range_low/1000:.0f}K-${c.price_range_high/1000:.0f}K | "
                f"{c.status.value} | {flag_str} |"
            )

        lines.extend([
            "",
            "---",
            "",
            f"**Evidence Collected:** {len(self.evidence)} items",
            f"**Last Updated:** {self.updated_at}",
            f"**Version:** {self.version}",
            "",
        ])

        if self.any_gates_red():
            lines.append("**WARNING:** One or more gates are RED - decision blocked.")
        elif self.all_gates_green():
            lines.append("**READY:** All gates GREEN - may proceed to decision.")
        else:
            blocking = self.blocking_gates()
            lines.append(f"**BLOCKING:** {len(blocking)} gates need attention before proceeding.")

        return "\n".join(lines)

    # Persistence
    def save(self, output_dir: str = "receipts/decisions") -> Tuple[str, str]:
        """Save decision node to disk."""
        out_path = Path(output_dir) / self.decision_id
        out_path.mkdir(parents=True, exist_ok=True)

        # Save JSON
        json_path = out_path / "DECISION_NODE.json"
        data = self.to_dict()
        data["node_hash"] = self.compute_hash()
        with json_path.open("w") as f:
            json.dump(data, f, indent=2)

        # Save markdown report
        md_path = out_path / "DECISION_STATUS.md"
        md_path.write_text(self.generate_status_report())

        return str(json_path), str(md_path)

    @classmethod
    def load(cls, decision_id: str, input_dir: str = "receipts/decisions") -> Optional["DecisionNode"]:
        """Load decision node from disk."""
        json_path = Path(input_dir) / decision_id / "DECISION_NODE.json"
        if not json_path.exists():
            return None

        with json_path.open() as f:
            data = json.load(f)

        return cls.from_dict(data)


def create_condo_decision_2026() -> DecisionNode:
    """Create the CONDO_DECISION_2026 decision node."""
    node = DecisionNode(
        decision_id="CONDO_DECISION_2026",
        decision_type="condo_purchase",
        title="Florida Condo Purchase Decision",
        description="Real estate acquisition - condominium in gated community, inland Florida. "
                    "Priority: gated security, low insurance/flood exposure, healthcare proximity.",
        decision_owners=["Josh", "Stacey"],
        status=DecisionStatus.EVIDENCE_COLLECTION,
        phase=DecisionPhase.PHASE_0,
        budget_min=200000,
        budget_max=300000,
    )

    # Add gates
    node.gates = get_default_gates()

    # Add communities
    node.communities = get_initial_communities()

    # Check Gate 4 (Location Score) since we already have scorer data
    gate4 = node.get_gate("location_score")
    if gate4:
        gate4.check(
            status=GateStatus.GREEN,
            evidence="All top 5 areas scored >= 70 (Villages 83.5, Ocala 78.8, Clermont 74.0, Lakeland 72.6, Sebring 72.0)",
            source="FGIP Location Scorer (WO-FGIP-LOCATION-GATE-01)",
            notes="Scorer run 2026-03-04",
            checked_by="system",
        )

    return node
