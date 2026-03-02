"""FGIP CHIPS Facility Agent - Tracks semiconductor facility buildouts.

Extends USASpending data with:
- FACILITY nodes (Intel Ohio, TSMC Arizona, Samsung Taylor, etc.)
- CAPACITY_AT edges with metadata (wafer starts, process node)
- Facility status tracking (announced → construction → operational)

Source: Commerce.gov CHIPS announcements (Tier-0)
"""

import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from .base import FGIPAgent, Artifact, StructuredFact, ProposedClaim, ProposedEdge, ProposedNode


# CHIPS Act facilities with capacity metadata
# Format: (company, facility_id, facility_name, location, investment_usd,
#          process_nodes, capacity_type, capacity_value, capacity_unit,
#          status, expected_operational, source_url)
CHIPS_FACILITIES = [
    # Intel
    ("Intel", "intel-ohio-fab", "Intel Ohio Fab Complex", "Ohio",
     20_000_000_000, ["3nm", "5nm"], "fab_wafer_starts", 50_000, "wafers/month",
     "construction", "2027",
     "https://www.commerce.gov/news/press-releases/2024/03/biden-harris-administration-announces-preliminary-terms-intel-receive"),

    # TSMC
    ("TSMC", "tsmc-arizona-fab", "TSMC Arizona Fab", "Arizona",
     40_000_000_000, ["3nm", "4nm", "5nm"], "fab_wafer_starts", 30_000, "wafers/month",
     "construction", "2025",
     "https://www.commerce.gov/news/press-releases/2024/04/biden-harris-administration-announces-preliminary-terms-tsmc"),

    # Samsung
    ("Samsung", "samsung-taylor-fab", "Samsung Taylor Texas Fab", "Texas",
     17_000_000_000, ["4nm", "5nm"], "fab_wafer_starts", 25_000, "wafers/month",
     "construction", "2026",
     "https://www.commerce.gov/news/press-releases/2024/04/biden-harris-administration-announces-preliminary-terms-samsung"),

    # Micron
    ("Micron", "micron-idaho-fab", "Micron Idaho Fab", "Idaho",
     15_000_000_000, ["1β", "1α"], "fab_wafer_starts", 40_000, "wafers/month",
     "announced", "2028",
     "https://www.commerce.gov/news/press-releases/2024/04/biden-harris-administration-announces-preliminary-terms-micron"),
    ("Micron", "micron-ny-fab", "Micron New York Fab", "New York",
     100_000_000_000, ["1γ", "1β"], "fab_wafer_starts", 100_000, "wafers/month",
     "announced", "2030",
     "https://www.commerce.gov/news/press-releases/2024/04/biden-harris-administration-announces-preliminary-terms-micron"),

    # GlobalFoundries
    ("GlobalFoundries", "gf-vermont-fab", "GlobalFoundries Vermont", "Vermont",
     1_500_000_000, ["12nm", "14nm"], "fab_wafer_starts", 20_000, "wafers/month",
     "operational", "2024",
     "https://www.commerce.gov/news/press-releases/2024/02/biden-harris-administration-announces-preliminary-terms-globalfoundries"),
    ("GlobalFoundries", "gf-ny-fab", "GlobalFoundries Malta NY", "New York",
     1_500_000_000, ["12nm", "14nm"], "fab_wafer_starts", 30_000, "wafers/month",
     "operational", "2024",
     "https://www.commerce.gov/news/press-releases/2024/02/biden-harris-administration-announces-preliminary-terms-globalfoundries"),
]


@dataclass
class FacilityRecord:
    """A CHIPS Act facility record with capacity metadata."""
    company: str
    facility_id: str
    facility_name: str
    location: str
    investment_usd: float
    process_nodes: List[str]
    capacity_type: str
    capacity_value: float
    capacity_unit: str
    status: str  # announced, construction, operational
    expected_operational: str
    source_url: str


class CHIPSFacilityAgent(FGIPAgent):
    """CHIPS Facility tracking agent.

    Tracks CHIPS Act semiconductor facility buildouts with:
    - FACILITY nodes with location data
    - CAPACITY_AT edges linking companies to facilities
    - Capacity metadata (wafer starts, process nodes, timelines)

    This is Tier 0 source (Commerce.gov primary data).
    """

    def __init__(self, db):
        super().__init__(
            db,
            name="chips-facility",
            description="CHIPS Act facility buildout tracker"
        )
        self.facilities = [FacilityRecord(*f) for f in CHIPS_FACILITIES]

    def collect(self) -> List[Artifact]:
        """Collect facility data from seeded records.

        In production, this would also fetch from Commerce.gov API/feeds.
        """
        artifacts = []
        for fac in self.facilities:
            artifact = Artifact(
                url=fac.source_url,
                artifact_type="chips_facility",
                metadata={
                    "facility_id": fac.facility_id,
                    "company": fac.company,
                    "location": fac.location,
                }
            )
            artifacts.append(artifact)
        return artifacts

    def extract(self, artifacts: List[Artifact]) -> List[StructuredFact]:
        """Extract facility facts from collected artifacts."""
        facts = []

        for fac in self.facilities:
            # Find matching artifact
            artifact = next(
                (a for a in artifacts if a.metadata.get("facility_id") == fac.facility_id),
                artifacts[0] if artifacts else Artifact(url=fac.source_url, artifact_type="chips_facility")
            )

            # Extract capacity fact
            fact = StructuredFact(
                fact_type="facility_capacity",
                subject=fac.company,
                predicate="CAPACITY_AT",
                object=fac.facility_id,
                source_artifact=artifact,
                confidence=0.95,  # Tier-0 source
                date_occurred=fac.expected_operational,
                metadata={
                    "facility_name": fac.facility_name,
                    "location": fac.location,
                    "investment_usd": fac.investment_usd,
                    "process_nodes": fac.process_nodes,
                    "capacity_type": fac.capacity_type,
                    "capacity_value": fac.capacity_value,
                    "capacity_unit": fac.capacity_unit,
                    "status": fac.status,
                    "expected_operational": fac.expected_operational,
                }
            )
            facts.append(fact)

            # Extract location fact
            loc_fact = StructuredFact(
                fact_type="facility_location",
                subject=fac.facility_id,
                predicate="BUILT_IN",
                object=fac.location.lower().replace(" ", "-"),
                source_artifact=artifact,
                confidence=0.95,
                date_occurred=fac.expected_operational,
            )
            facts.append(loc_fact)

        return facts

    def propose(self, facts: List[StructuredFact]) -> tuple:
        """Generate proposals for facilities, capacity edges, and location edges."""
        claims = []
        edges = []
        nodes = []

        # Track facilities we've proposed nodes for
        proposed_facilities = set()

        for fact in facts:
            if fact.fact_type == "facility_capacity":
                # Create FACILITY node
                fac_id = fact.object
                if fac_id not in proposed_facilities:
                    node = ProposedNode(
                        proposal_id=self._generate_proposal_id(),
                        node_id=fac_id,
                        node_type="FACILITY",
                        name=fact.metadata.get("facility_name", fac_id),
                        agent_name=self.name,
                        description=f"{fact.metadata.get('capacity_type')}: {fact.metadata.get('capacity_value')} {fact.metadata.get('capacity_unit')}, {fact.metadata.get('status')}",
                        source_url=fact.source_artifact.url,
                        reasoning=f"CHIPS Act facility buildout for {fact.subject}",
                    )
                    nodes.append(node)
                    proposed_facilities.add(fac_id)

                # Create CAPACITY_AT edge
                edge = ProposedEdge(
                    proposal_id=self._generate_proposal_id(),
                    from_node=fact.subject.lower().replace(" ", "-"),
                    to_node=fac_id,
                    relationship="CAPACITY_AT",
                    agent_name=self.name,
                    confidence=fact.confidence,
                    detail=json.dumps({
                        "investment_usd": fact.metadata.get("investment_usd"),
                        "process_nodes": fact.metadata.get("process_nodes"),
                        "capacity_type": fact.metadata.get("capacity_type"),
                        "capacity_value": fact.metadata.get("capacity_value"),
                        "capacity_unit": fact.metadata.get("capacity_unit"),
                        "status": fact.metadata.get("status"),
                        "expected_operational": fact.metadata.get("expected_operational"),
                    }),
                    reasoning=f"CHIPS Act facility: ${fact.metadata.get('investment_usd', 0):,.0f} investment",
                )
                edges.append(edge)

                # Create claim for the facility
                claim = ProposedClaim(
                    proposal_id=self._generate_proposal_id(),
                    claim_text=f"{fact.subject} is building {fact.metadata.get('facility_name')} in {fact.metadata.get('location')} with ${fact.metadata.get('investment_usd', 0)/1e9:.1f}B investment, {fact.metadata.get('capacity_value')} {fact.metadata.get('capacity_unit')} capacity",
                    topic="chips-act-facility",
                    agent_name=self.name,
                    source_url=fact.source_artifact.url,
                    reasoning="CHIPS Act facility announcement from Commerce.gov",
                )
                claims.append(claim)

            elif fact.fact_type == "facility_location":
                # Create BUILT_IN edge
                edge = ProposedEdge(
                    proposal_id=self._generate_proposal_id(),
                    from_node=fact.subject,
                    to_node=fact.object,
                    relationship="BUILT_IN",
                    agent_name=self.name,
                    confidence=fact.confidence,
                    reasoning="CHIPS Act facility location",
                )
                edges.append(edge)

        return claims, edges, nodes

    def update_facility_capacity(self, facility_node_id: str, **kwargs):
        """Update facility_capacity table with new data.

        Args:
            facility_node_id: The facility node ID
            **kwargs: Capacity fields to update
        """
        conn = self.db.connect()

        # Build update or insert
        fields = ["facility_node_id"]
        values = [facility_node_id]

        valid_fields = ["company_node_id", "capacity_type", "capacity_value",
                       "capacity_unit", "process_node", "operational_status",
                       "operational_date", "investment_usd"]

        for field in valid_fields:
            if field in kwargs:
                fields.append(field)
                values.append(kwargs[field])

        fields.append("last_updated")
        values.append(datetime.utcnow().isoformat() + "Z")

        placeholders = ", ".join(["?"] * len(values))
        columns = ", ".join(fields)

        conn.execute(
            f"INSERT OR REPLACE INTO facility_capacity ({columns}) VALUES ({placeholders})",
            values
        )
        conn.commit()

    def seed_facility_capacity(self):
        """Seed the facility_capacity table with known CHIPS facilities."""
        for fac in self.facilities:
            self.update_facility_capacity(
                facility_node_id=fac.facility_id,
                company_node_id=fac.company.lower().replace(" ", "-"),
                capacity_type=fac.capacity_type,
                capacity_value=fac.capacity_value,
                capacity_unit=fac.capacity_unit,
                process_node=",".join(fac.process_nodes),
                operational_status=fac.status,
                operational_date=fac.expected_operational,
                investment_usd=fac.investment_usd,
            )


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(__file__).replace("/fgip/agents/chips_facility.py", ""))

    from fgip.db import FGIPDatabase

    db_path = sys.argv[1] if len(sys.argv) > 1 else "fgip.db"
    db = FGIPDatabase(db_path)
    db.connect()

    agent = CHIPSFacilityAgent(db)

    # Run with delta tracking
    if "--with-delta" in sys.argv:
        result = agent.run_with_delta()
        print(f"Run ID: {result['run_id']}")
        print(f"Delta count: {result['delta_count']}")
        print(f"Delta hash: {result['delta_hash'][:16]}...")
    else:
        result = agent.run()

    print(f"Artifacts collected: {result['artifacts_collected']}")
    print(f"Claims proposed: {result['claims_proposed']}")
    print(f"Edges proposed: {result['edges_proposed']}")
    print(f"Nodes proposed: {result.get('nodes_proposed', 0)}")

    # Seed facility_capacity table
    if "--seed-capacity" in sys.argv:
        agent.seed_facility_capacity()
        print("Facility capacity table seeded.")
