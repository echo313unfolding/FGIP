"""USASpending Agent - Federal spending data monitor.

Monitors usaspending.gov for grants, contracts, and awards.
Tier 0 government source (direct appropriations/awards data).

Tracks:
- Federal grants to companies/organizations
- Federal contracts to vendors
- Program authorizations (CHIPS, IRA, IIJA, etc.)

Edge types proposed:
- AWARDED_GRANT (agency/program → recipient)
- AWARDED_CONTRACT (agency → vendor)
- FUNDED_PROJECT (recipient → facility/project)
- AUTHORIZED_BY (project/award → statute/program)

Usage:
    from fgip.agents.usaspending import USASpendingAgent

    agent = USASpendingAgent(db)
    results = agent.run()
"""

import re
import time
import hashlib
import json
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass

from .base import FGIPAgent, Artifact, StructuredFact, ProposedClaim, ProposedEdge, ProposedNode


# Known correction-layer awards from research (seeded data)
# Format: (program, recipient, amount, award_type, year, source_url)
KNOWN_AWARDS = [
    # CHIPS Act awards
    ("CHIPS Act", "Intel", "$8.9B", "grant", "2024",
     "https://www.commerce.gov/news/press-releases/2024/03/biden-harris-administration-announces-preliminary-terms-intel-receive"),
    ("CHIPS Act", "TSMC Arizona", "$6.6B", "grant", "2024",
     "https://www.commerce.gov/news/press-releases/2024/04/biden-harris-administration-announces-preliminary-terms-tsmc"),
    ("CHIPS Act", "Samsung Texas", "$6.4B", "grant", "2024",
     "https://www.commerce.gov/news/press-releases/2024/04/biden-harris-administration-announces-preliminary-terms-samsung"),
    ("CHIPS Act", "Micron", "$6.1B", "grant", "2024",
     "https://www.commerce.gov/news/press-releases/2024/04/biden-harris-administration-announces-preliminary-terms-micron"),
    ("CHIPS Act", "GlobalFoundries", "$1.5B", "grant", "2024",
     "https://www.commerce.gov/news/press-releases/2024/02/biden-harris-administration-announces-preliminary-terms-globalfoundries"),

    # Infrastructure Investment and Jobs Act (IIJA)
    ("IIJA", "National EV Charging Network", "$7.5B", "program", "2022-2027",
     "https://www.fhwa.dot.gov/environment/alternative_fuel_corridors/"),

    # Inflation Reduction Act (IRA) - clean energy
    ("IRA", "Domestic Manufacturing Tax Credits", "$60B+", "program", "2022-2032",
     "https://www.energy.gov/lpo/inflation-reduction-act-2022"),
]

# Known facility buildouts (correction signals)
# Format: (company, facility, location, investment, year, source_url)
KNOWN_BUILDOUTS = [
    ("Intel", "Ohio Fab Complex", "Ohio", "$20B", "2022-2027",
     "https://www.intel.com/content/www/us/en/newsroom/news/intel-announces-ohio.html"),
    ("TSMC", "Arizona Fab", "Arizona", "$40B", "2021-2026",
     "https://pr.tsmc.com/english/news/2907"),
    ("Samsung", "Taylor Texas Fab", "Texas", "$17B", "2021-2024",
     "https://news.samsung.com/us/samsung-electronics-announces-new-advanced-semiconductor-fab-in-taylor-texas/"),
    ("Hyundai", "Georgia EV Plant", "Georgia", "$5.5B", "2022-2025",
     "https://www.hyundaimotorgroup.com/news/CONT0000000000036505"),
    ("Eli Lilly", "Indiana Manufacturing", "Indiana", "$3.7B", "2023-2026",
     "https://investor.lilly.com/news-releases/news-release-details/lilly-invests-additional-16-billion-expand-indiana-manufacturing"),
]


@dataclass
class AwardRecord:
    """A federal award record."""
    program: str
    recipient: str
    amount: str
    award_type: str  # grant, contract, program
    year: str
    source_url: str


@dataclass
class BuildoutRecord:
    """A facility buildout record."""
    company: str
    facility: str
    location: str
    investment: str
    year: str
    source_url: str


class USASpendingAgent(FGIPAgent):
    """USASpending.gov monitoring agent.

    Monitors federal spending data for grants, contracts, and awards.
    This is Tier 0 source (direct government appropriations data).

    The agent:
    1. Collects award data from USASpending API
    2. Extracts funding relationships
    3. Proposes AWARDED_GRANT, AWARDED_CONTRACT, FUNDED_PROJECT edges
    4. Tracks buildout signals for reshoring thesis
    """

    def __init__(self, db, artifact_dir: str = "data/artifacts/usaspending"):
        """Initialize the USASpending agent.

        Args:
            db: FGIPDatabase instance
            artifact_dir: Directory to store downloaded data
        """
        super().__init__(
            db=db,
            name="usaspending",
            description="USASpending federal awards monitor (Tier 0)"
        )
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self._rate_limit_delay = 1.0
        self._last_request_time = 0
        self._existing_nodes = None

        # USASpending API base URL
        self.api_base = "https://api.usaspending.gov/api/v2"

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._rate_limit_delay:
            time.sleep(self._rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    def collect(self) -> List[Artifact]:
        """Fetch USASpending data from live API with seeded fallback.

        Calls live api.usaspending.gov endpoints for:
        - Award search by recipient
        - Award details

        Falls back to seeded data if API unavailable.

        Returns:
            List of Artifact objects with award data
        """
        artifacts = []

        # Target recipients for CHIPS Act / correction layer awards
        target_recipients = [
            "Intel",
            "TSMC",
            "Samsung",
            "Micron",
            "GlobalFoundries",
            "Texas Instruments",
            "Hyundai",
            "Eli Lilly",
        ]

        # Collect live API data
        live_awards = self._collect_live_awards(target_recipients)
        if live_awards:
            artifacts.extend(live_awards)

        # Also include seeded awards (known ground truth)
        awards_content = self._format_awards_data()
        awards_bytes = awards_content.encode('utf-8')
        awards_hash = hashlib.sha256(awards_bytes).hexdigest()

        awards_path = self.artifact_dir / f"usaspending_seeded_{datetime.utcnow().strftime('%Y%m%d')}.txt"
        awards_path.write_bytes(awards_bytes)

        artifacts.append(Artifact(
            url="https://www.usaspending.gov/",
            artifact_type="usaspending_seeded",
            local_path=str(awards_path),
            content_hash=awards_hash,
            metadata={
                "record_count": len(KNOWN_AWARDS),
                "source": "usaspending_seeded_awards",
            }
        ))

        # Create artifact from known buildouts
        buildouts_content = self._format_buildouts_data()
        buildouts_bytes = buildouts_content.encode('utf-8')
        buildouts_hash = hashlib.sha256(buildouts_bytes).hexdigest()

        buildouts_path = self.artifact_dir / f"usaspending_buildouts_{datetime.utcnow().strftime('%Y%m%d')}.txt"
        buildouts_path.write_bytes(buildouts_bytes)

        artifacts.append(Artifact(
            url="https://www.usaspending.gov/",
            artifact_type="usaspending_buildouts",
            local_path=str(buildouts_path),
            content_hash=buildouts_hash,
            metadata={
                "record_count": len(KNOWN_BUILDOUTS),
                "source": "usaspending_known_buildouts",
            }
        ))

        return artifacts

    def _collect_live_awards(self, recipients: List[str]) -> List[Artifact]:
        """Fetch awards from live USASpending API.

        Args:
            recipients: List of recipient names to search

        Returns:
            List of Artifact objects from API responses
        """
        artifacts = []

        for recipient in recipients:
            # Search for awards by recipient using keyword search
            search_url = f"{self.api_base}/search/spending_by_award/"

            # Use keywords filter which is supported for recipient name searching
            # Note: time_period limited to 2007-10-01 earliest per API docs
            search_payload = json.dumps({
                "subawards": False,
                "filters": {
                    "keywords": [recipient],
                    "award_type_codes": ["A", "B", "C", "D"],
                    "time_period": [
                        {"start_date": "2022-01-01", "end_date": "2025-12-31"}
                    ]
                },
                "fields": [
                    "Award ID",
                    "Recipient Name",
                    "Award Amount",
                    "Awarding Agency",
                    "Award Type",
                    "Description",
                    "generated_internal_id"
                ],
                "page": 1,
                "limit": 50
            }).encode('utf-8')

            response = self._fetch_api(search_url, method="POST", data=search_payload)

            if response:
                content_hash = hashlib.sha256(response).hexdigest()[:16]
                safe_name = re.sub(r'[^a-z0-9]+', '_', recipient.lower())
                local_path = self.artifact_dir / f"api_awards_{safe_name}_{datetime.utcnow().strftime('%Y%m%d')}_{content_hash}.json"
                local_path.write_bytes(response)

                try:
                    data = json.loads(response)
                    result_count = len(data.get("results", []))
                except json.JSONDecodeError:
                    result_count = 0

                artifacts.append(Artifact(
                    url=search_url,
                    artifact_type="usaspending_api_awards",
                    local_path=str(local_path),
                    content_hash=hashlib.sha256(response).hexdigest(),
                    metadata={
                        "source": "usaspending_api",
                        "recipient_search": recipient,
                        "result_count": result_count,
                    }
                ))

        return artifacts

    def _fetch_api(self, url: str, method: str = "GET", data: bytes = None) -> Optional[bytes]:
        """Fetch from USASpending API with rate limiting.

        Args:
            url: API endpoint URL
            method: HTTP method (GET or POST)
            data: Request body for POST requests

        Returns:
            Response bytes or None on error
        """
        self._rate_limit()

        try:
            request = urllib.request.Request(
                url,
                data=data,
                method=method,
                headers={
                    "User-Agent": "FGIP Research Agent (research@fgip.org)",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                }
            )

            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()
        except urllib.error.HTTPError as e:
            if e.code == 429:
                # Rate limited - wait and retry
                time.sleep(5)
                return self._fetch_api(url, method, data)
            print(f"USASpending API error {e.code}: {e.reason}")
            return None
        except Exception as e:
            print(f"USASpending API fetch error: {e}")
            return None

    def _format_awards_data(self) -> str:
        """Format award data as artifact content."""
        lines = ["USASpending Award Data", "=" * 50, ""]

        for record in KNOWN_AWARDS:
            program, recipient, amount, award_type, year, url = record
            lines.extend([
                f"Program: {program}",
                f"Recipient: {recipient}",
                f"Amount: {amount}",
                f"Type: {award_type}",
                f"Year: {year}",
                f"URL: {url}",
                "",
            ])

        return "\n".join(lines)

    def _format_buildouts_data(self) -> str:
        """Format buildout data as artifact content."""
        lines = ["Facility Buildout Data (Reshoring Signals)", "=" * 50, ""]

        for record in KNOWN_BUILDOUTS:
            company, facility, location, investment, year, url = record
            lines.extend([
                f"Company: {company}",
                f"Facility: {facility}",
                f"Location: {location}",
                f"Investment: {investment}",
                f"Year: {year}",
                f"URL: {url}",
                "",
            ])

        return "\n".join(lines)

    def extract(self, artifacts: List[Artifact]) -> List[StructuredFact]:
        """Extract award and buildout relationships.

        Args:
            artifacts: USASpending artifact data

        Returns:
            List of StructuredFact objects
        """
        facts = []

        for artifact in artifacts:
            if artifact.artifact_type == "usaspending_api_awards":
                facts.extend(self._extract_api_award_facts(artifact))
            elif artifact.artifact_type in ("usaspending_awards", "usaspending_seeded"):
                facts.extend(self._extract_award_facts(artifact))
            elif artifact.artifact_type == "usaspending_buildouts":
                facts.extend(self._extract_buildout_facts(artifact))

        return facts

    def _extract_api_award_facts(self, artifact: Artifact) -> List[StructuredFact]:
        """Extract facts from live USASpending API response.

        Args:
            artifact: API response artifact

        Returns:
            List of StructuredFact objects
        """
        facts = []

        if not artifact.local_path:
            return facts

        try:
            with open(artifact.local_path, 'r') as f:
                data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"Error reading API artifact: {e}")
            return facts

        results = data.get("results", [])
        recipient_search = artifact.metadata.get("recipient_search", "Unknown")

        for result in results:
            award_amount = result.get("Award Amount", 0)
            recipient_name = result.get("Recipient Name", recipient_search)
            awarding_agency = result.get("Awarding Agency", "")
            award_type = result.get("Award Type", "")
            description = result.get("Description", "")
            start_date = result.get("Start Date", "")
            award_id = result.get("Award ID", "")
            internal_id = result.get("generated_internal_id", "")

            # Skip small awards (focus on significant federal funding)
            if award_amount and award_amount < 1000000:
                continue

            # Format amount
            if award_amount:
                if award_amount >= 1_000_000_000:
                    amount_str = f"${award_amount / 1_000_000_000:.2f}B"
                elif award_amount >= 1_000_000:
                    amount_str = f"${award_amount / 1_000_000:.1f}M"
                else:
                    amount_str = f"${award_amount:,.0f}"
            else:
                amount_str = "N/A"

            # Determine predicate based on award type
            if award_type and "grant" in award_type.lower():
                predicate = "AWARDED_GRANT"
            elif award_type and "contract" in award_type.lower():
                predicate = "AWARDED_CONTRACT"
            else:
                predicate = "AWARDED_GRANT"  # Default for federal awards

            # Detect CHIPS Act or other programs from description
            program = "Federal Award"
            desc_lower = description.lower() if description else ""
            if "chips" in desc_lower or "semiconductor" in desc_lower:
                program = "CHIPS Act"
            elif "ira" in desc_lower or "inflation reduction" in desc_lower:
                program = "Inflation Reduction Act"
            elif "iija" in desc_lower or "infrastructure" in desc_lower:
                program = "Infrastructure Investment"

            fact = StructuredFact(
                fact_type="federal_award_api",
                subject=awarding_agency or program,
                predicate=predicate,
                object=recipient_name,
                source_artifact=artifact,
                confidence=0.95,  # Tier 0 government data
                date_occurred=start_date,
                raw_text=f"{awarding_agency} awarded {amount_str} to {recipient_name}: {description[:100] if description else 'N/A'}",
                metadata={
                    "amount": award_amount,
                    "amount_str": amount_str,
                    "award_type": award_type,
                    "award_id": award_id,
                    "internal_id": internal_id,
                    "description": description,
                    "program": program,
                    "source_url": f"https://www.usaspending.gov/award/{internal_id}" if internal_id else artifact.url,
                    "source_tier": 0,
                }
            )
            facts.append(fact)

        return facts

    def _extract_award_facts(self, artifact: Artifact) -> List[StructuredFact]:
        """Extract award facts from artifact."""
        facts = []

        for record in KNOWN_AWARDS:
            program, recipient, amount, award_type, year, url = record

            # Determine edge type based on award type
            if award_type == "grant":
                predicate = "AWARDED_GRANT"
            elif award_type == "contract":
                predicate = "AWARDED_CONTRACT"
            else:
                predicate = "AUTHORIZED_BY"  # program authorization

            fact = StructuredFact(
                fact_type="federal_award",
                subject=program,
                predicate=predicate,
                object=recipient,
                source_artifact=artifact,
                confidence=0.95,  # Tier 0 government data
                date_occurred=year,
                raw_text=f"{program} awarded {amount} {award_type} to {recipient}",
                metadata={
                    "amount": amount,
                    "award_type": award_type,
                    "year": year,
                    "source_url": url,
                    "source_tier": 0,
                }
            )
            facts.append(fact)

        return facts

    def _extract_buildout_facts(self, artifact: Artifact) -> List[StructuredFact]:
        """Extract buildout facts from artifact."""
        facts = []

        for record in KNOWN_BUILDOUTS:
            company, facility, location, investment, year, url = record

            # BUILT_IN edge: facility → location
            built_in_fact = StructuredFact(
                fact_type="facility_buildout",
                subject=facility,
                predicate="BUILT_IN",
                object=location,
                source_artifact=artifact,
                confidence=0.90,
                date_occurred=year,
                raw_text=f"{company} building {facility} in {location} ({investment})",
                metadata={
                    "company": company,
                    "investment": investment,
                    "year": year,
                    "source_url": url,
                    "source_tier": 1,  # Company press release
                }
            )
            facts.append(built_in_fact)

            # FUNDED_PROJECT edge: company → facility
            funded_fact = StructuredFact(
                fact_type="project_funding",
                subject=company,
                predicate="FUNDED_PROJECT",
                object=facility,
                source_artifact=artifact,
                confidence=0.90,
                date_occurred=year,
                raw_text=f"{company} investing {investment} in {facility}",
                metadata={
                    "investment": investment,
                    "location": location,
                    "year": year,
                    "source_url": url,
                    "source_tier": 1,
                }
            )
            facts.append(funded_fact)

        return facts

    def propose(self, facts: List[StructuredFact]) -> Tuple[List[ProposedClaim], List[ProposedEdge], List[ProposedNode]]:
        """Generate proposals from USASpending facts.

        Args:
            facts: Extracted USASpending facts

        Returns:
            Tuple of (claims, edges, nodes)
        """
        claims = []
        edges = []
        proposed_node_ids = {}

        for fact in facts:
            # Create claim
            claim_id = self._generate_proposal_id()

            tier = fact.metadata.get('source_tier', 0)
            promotion_req = None if tier == 0 else "Verify with primary government filing"

            claim = ProposedClaim(
                proposal_id=claim_id,
                claim_text=fact.raw_text,
                topic=self._determine_topic(fact),
                agent_name=self.name,
                source_url=fact.metadata.get('source_url'),
                artifact_path=fact.source_artifact.local_path,
                artifact_hash=fact.source_artifact.content_hash,
                reasoning=f"USASpending Tier {tier}. {fact.metadata.get('amount', '')}",
                promotion_requirement=promotion_req,
            )
            claims.append(claim)

            # Create edge
            from_node = self._slugify(fact.subject)
            to_node = self._slugify(fact.object)

            # Track node proposals
            for node_id, entity_name, is_from in [
                (from_node, fact.subject, True),
                (to_node, fact.object, False)
            ]:
                if node_id and node_id not in proposed_node_ids and not self._node_exists(node_id):
                    node_type = self._infer_node_type(entity_name, fact, is_from)
                    proposed_node_ids[node_id] = {
                        'node_id': node_id,
                        'name': entity_name,
                        'node_type': node_type,
                    }

            edge = ProposedEdge(
                proposal_id=self._generate_proposal_id(),
                from_node=from_node,
                to_node=to_node,
                relationship=fact.predicate,
                agent_name=self.name,
                detail=fact.raw_text,
                proposed_claim_id=claim_id,
                confidence=fact.confidence,
                reasoning=f"USASpending Tier {tier}. Source: {fact.metadata.get('source_url')}",
                promotion_requirement=promotion_req,
            )
            edges.append(edge)

        # Create node proposals
        nodes = []
        for node_info in proposed_node_ids.values():
            node = ProposedNode(
                proposal_id=self._generate_proposal_id(),
                node_id=node_info['node_id'],
                node_type=node_info['node_type'],
                name=node_info['name'],
                agent_name=self.name,
                reasoning="Entity from USASpending/correction layer data.",
            )
            nodes.append(node)

        return claims, edges, nodes

    def _determine_topic(self, fact: StructuredFact) -> str:
        """Determine topic from fact type."""
        if fact.fact_type == "federal_award":
            return "CorrectionLayer"
        elif fact.fact_type == "facility_buildout":
            return "Reshoring"
        elif fact.fact_type == "project_funding":
            return "CorrectionLayer"
        return "USASpending"

    def _infer_node_type(self, entity_name: str, fact: StructuredFact, is_from: bool) -> str:
        """Infer node type from entity name and fact context."""
        name_lower = entity_name.lower()

        # Program/Act indicators
        if 'act' in name_lower or 'chips' in name_lower or 'ira' in name_lower or 'iija' in name_lower:
            return "PROGRAM"

        # Location indicators
        if any(loc in name_lower for loc in ['ohio', 'texas', 'arizona', 'georgia', 'indiana']):
            return "LOCATION"

        # Facility indicators
        if 'fab' in name_lower or 'plant' in name_lower or 'complex' in name_lower or 'manufacturing' in name_lower:
            return "FACILITY"

        # Company indicators
        if any(co in name_lower for co in ['intel', 'tsmc', 'samsung', 'micron', 'hyundai', 'lilly', 'globalfoundries']):
            return "COMPANY"

        # Default based on position
        if is_from and fact.predicate in ('AWARDED_GRANT', 'AWARDED_CONTRACT'):
            return "PROGRAM"
        elif not is_from and fact.predicate in ('AWARDED_GRANT', 'AWARDED_CONTRACT'):
            return "COMPANY"

        return "ORGANIZATION"

    def _slugify(self, name: str) -> str:
        """Convert name to node_id slug."""
        if not name:
            return ""
        slug = name.lower()
        slug = re.sub(r'[^a-z0-9]+', '-', slug)
        slug = re.sub(r'-+', '-', slug)
        return slug.strip('-')

    def _node_exists(self, node_id: str) -> bool:
        """Check if node exists in production."""
        if self._existing_nodes is None:
            conn = self.db.connect()
            rows = conn.execute("SELECT node_id FROM nodes").fetchall()
            self._existing_nodes = {row[0] for row in rows}
        return node_id in self._existing_nodes
