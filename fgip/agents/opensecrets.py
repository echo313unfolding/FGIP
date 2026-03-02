"""OpenSecrets Agent - Campaign finance and lobbying data monitor.

Monitors opensecrets.org for lobbying expenditures, campaign contributions,
and revolving door relationships. Tier 1 journalism source (cites primary FEC/LDA data).

Catches:
- Corporate lobbying expenditures
- Campaign contributions (PACs, individual donors)
- Revolving door (lawmakers → lobbyists)
- Industry lobbying totals

Edge types proposed:
- LOBBIED_FOR (with $ amounts in metadata)
- DONATED_TO (campaign contributions)
- EMPLOYED (revolving door relationships)
- MEMBER_OF (trade association memberships)

Usage:
    from fgip.agents.opensecrets import OpenSecretsAgent

    agent = OpenSecretsAgent(db)
    results = agent.run()
"""

import re
import time
import hashlib
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass

from .base import FGIPAgent, Artifact, StructuredFact, ProposedClaim, ProposedEdge, ProposedNode


# Known lobbying data from research (seeded from OpenSecrets)
# Format: (lobbyer, target, amount, year, source_url)
KNOWN_LOBBYING = [
    # US Chamber of Commerce - massive lobbying operation
    ("US Chamber of Commerce", "PNTR", "$1.8B total lobbying (1998-2024)", "1998-2024",
     "https://www.opensecrets.org/federal-lobbying/clients/summary?cycle=2024&id=D000019798"),
    ("US Chamber of Commerce", "China Trade Policy", "$200M+ lobbying", "2000",
     "https://www.opensecrets.org/federal-lobbying/clients/summary?id=D000019798&cycle=2000"),

    # Business Roundtable
    ("Business Roundtable", "PNTR", "$50M+ lobbying", "1998-2001",
     "https://www.opensecrets.org/federal-lobbying/clients/summary?id=D000046963"),

    # Tech companies on China policy
    ("Apple Inc", "China Trade", "$9.8M lobbying", "2023",
     "https://www.opensecrets.org/federal-lobbying/clients/summary?id=D000021754"),
    ("Google", "China Trade", "$11.8M lobbying", "2023",
     "https://www.opensecrets.org/federal-lobbying/clients/summary?id=D000067823"),
    ("Microsoft", "China Trade", "$10.2M lobbying", "2023",
     "https://www.opensecrets.org/federal-lobbying/clients/summary?id=D000000115"),

    # Financial sector - NY Fed connection
    ("JPMorgan Chase", "Financial Regulation", "$8.5M lobbying", "2023",
     "https://www.opensecrets.org/federal-lobbying/clients/summary?id=D000000103"),
    ("Citigroup", "Financial Regulation", "$5.2M lobbying", "2023",
     "https://www.opensecrets.org/federal-lobbying/clients/summary?id=D000000071"),
    ("Goldman Sachs", "Financial Regulation", "$4.1M lobbying", "2023",
     "https://www.opensecrets.org/federal-lobbying/clients/summary?id=D000000085"),
    ("BlackRock", "Financial Regulation", "$3.8M lobbying", "2023",
     "https://www.opensecrets.org/federal-lobbying/clients/summary?id=D000067126"),
]

# Known campaign contributions (from OpenSecrets FEC data)
# Format: (donor, recipient, amount, cycle, source_url)
KNOWN_CONTRIBUTIONS = [
    # Chamber of Commerce PAC contributions
    ("US Chamber of Commerce", "Pro-trade candidates", "$35M", "2000",
     "https://www.opensecrets.org/orgs/us-chamber-of-commerce/summary?id=D000019798"),

    # Koch network
    ("Koch Industries", "Cato Institute", "Founder/Major Donor", "1977-present",
     "https://www.opensecrets.org/orgs/koch-industries/summary?id=D000000186"),
    ("Charles Koch", "Heritage Foundation", "Major Donor", "1980-present",
     "https://www.opensecrets.org/outsidespending/donor_detail.php?cycle=2024&id=U0000003655"),
]

# Revolving door data (lawmakers → lobbyists)
# Format: (person, previous_role, new_employer, year, source_url)
KNOWN_REVOLVING_DOOR = [
    # Former lawmakers lobbying for foreign/corporate interests
    ("Bill Archer", "House Ways and Means Chair", "PricewaterhouseCoopers",
     "2001", "https://www.opensecrets.org/revolving/rev_summary.php?id=70050"),
    ("Dick Gephardt", "House Minority Leader", "Gephardt Group (lobbying)",
     "2005", "https://www.opensecrets.org/revolving/rev_summary.php?id=70081"),
    ("Trent Lott", "Senate Majority Leader", "Squire Patton Boggs",
     "2008", "https://www.opensecrets.org/revolving/rev_summary.php?id=70083"),
    ("John Breaux", "Senator (D-LA)", "Squire Patton Boggs",
     "2005", "https://www.opensecrets.org/revolving/rev_summary.php?id=70068"),

    # Key PNTR vote connections
    ("Robert Matsui", "House (D-CA)", "Lobbied for PNTR (while in office)",
     "2000", "https://www.opensecrets.org/members-of-congress/robert-matsui/summary?cid=N00007187"),
]


@dataclass
class LobbyingRecord:
    """A lobbying expenditure record."""
    client: str
    target: str
    amount: str
    year: str
    source_url: str


@dataclass
class ContributionRecord:
    """A campaign contribution record."""
    donor: str
    recipient: str
    amount: str
    cycle: str
    source_url: str


@dataclass
class RevolvingDoorRecord:
    """A revolving door record."""
    person: str
    previous_role: str
    new_employer: str
    year: str
    source_url: str


class OpenSecretsAgent(FGIPAgent):
    """OpenSecrets (Center for Responsive Politics) monitoring agent.

    Monitors opensecrets.org for campaign finance and lobbying data.
    This is Tier 1 source (journalism citing FEC/LDA filings).

    The agent:
    1. Collects lobbying expenditure data
    2. Collects campaign contribution data
    3. Tracks revolving door relationships
    4. Proposes LOBBIED_FOR, DONATED_TO, EMPLOYED edges
    """

    def __init__(self, db, artifact_dir: str = "data/artifacts/opensecrets"):
        """Initialize the OpenSecrets agent.

        Args:
            db: FGIPDatabase instance
            artifact_dir: Directory to store downloaded data
        """
        super().__init__(
            db=db,
            name="opensecrets",
            description="OpenSecrets campaign finance/lobbying monitor (Tier 1)"
        )
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self._rate_limit_delay = 2.0  # Respectful rate limiting
        self._last_request_time = 0
        self._existing_nodes = None

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._rate_limit_delay:
            time.sleep(self._rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    def collect(self) -> List[Artifact]:
        """Fetch OpenSecrets data for tracked entities.

        For MVP, uses seeded data from research sessions.
        Real implementation would use OpenSecrets API or scrape.

        Returns:
            List of Artifact objects with OpenSecrets data
        """
        artifacts = []

        # Create artifact from known lobbying data
        lobbying_content = self._format_lobbying_data()
        lobbying_bytes = lobbying_content.encode('utf-8')
        lobbying_hash = hashlib.sha256(lobbying_bytes).hexdigest()

        lobbying_path = self.artifact_dir / f"opensecrets_lobbying_{datetime.utcnow().strftime('%Y%m%d')}.txt"
        lobbying_path.write_bytes(lobbying_bytes)

        artifacts.append(Artifact(
            url="https://www.opensecrets.org/federal-lobbying",
            artifact_type="opensecrets_lobbying",
            local_path=str(lobbying_path),
            content_hash=lobbying_hash,
            metadata={
                "record_count": len(KNOWN_LOBBYING),
                "source": "opensecrets_known_lobbying",
            }
        ))

        # Create artifact from known contributions
        contrib_content = self._format_contribution_data()
        contrib_bytes = contrib_content.encode('utf-8')
        contrib_hash = hashlib.sha256(contrib_bytes).hexdigest()

        contrib_path = self.artifact_dir / f"opensecrets_contributions_{datetime.utcnow().strftime('%Y%m%d')}.txt"
        contrib_path.write_bytes(contrib_bytes)

        artifacts.append(Artifact(
            url="https://www.opensecrets.org/political-action-committees-pacs",
            artifact_type="opensecrets_contributions",
            local_path=str(contrib_path),
            content_hash=contrib_hash,
            metadata={
                "record_count": len(KNOWN_CONTRIBUTIONS),
                "source": "opensecrets_known_contributions",
            }
        ))

        # Create artifact from revolving door data
        revolving_content = self._format_revolving_door_data()
        revolving_bytes = revolving_content.encode('utf-8')
        revolving_hash = hashlib.sha256(revolving_bytes).hexdigest()

        revolving_path = self.artifact_dir / f"opensecrets_revolving_{datetime.utcnow().strftime('%Y%m%d')}.txt"
        revolving_path.write_bytes(revolving_bytes)

        artifacts.append(Artifact(
            url="https://www.opensecrets.org/revolving",
            artifact_type="opensecrets_revolving_door",
            local_path=str(revolving_path),
            content_hash=revolving_hash,
            metadata={
                "record_count": len(KNOWN_REVOLVING_DOOR),
                "source": "opensecrets_known_revolving",
            }
        ))

        return artifacts

    def _format_lobbying_data(self) -> str:
        """Format lobbying data as artifact content."""
        lines = ["OpenSecrets Lobbying Data", "=" * 50, ""]

        for record in KNOWN_LOBBYING:
            client, target, amount, year, url = record
            lines.extend([
                f"Client: {client}",
                f"Target: {target}",
                f"Amount: {amount}",
                f"Year: {year}",
                f"URL: {url}",
                "",
            ])

        return "\n".join(lines)

    def _format_contribution_data(self) -> str:
        """Format contribution data as artifact content."""
        lines = ["OpenSecrets Contribution Data", "=" * 50, ""]

        for record in KNOWN_CONTRIBUTIONS:
            donor, recipient, amount, cycle, url = record
            lines.extend([
                f"Donor: {donor}",
                f"Recipient: {recipient}",
                f"Amount: {amount}",
                f"Cycle: {cycle}",
                f"URL: {url}",
                "",
            ])

        return "\n".join(lines)

    def _format_revolving_door_data(self) -> str:
        """Format revolving door data as artifact content."""
        lines = ["OpenSecrets Revolving Door Data", "=" * 50, ""]

        for record in KNOWN_REVOLVING_DOOR:
            person, prev_role, new_employer, year, url = record
            lines.extend([
                f"Person: {person}",
                f"Previous Role: {prev_role}",
                f"New Employer: {new_employer}",
                f"Year: {year}",
                f"URL: {url}",
                "",
            ])

        return "\n".join(lines)

    def extract(self, artifacts: List[Artifact]) -> List[StructuredFact]:
        """Extract lobbying and contribution relationships.

        Args:
            artifacts: OpenSecrets artifact data

        Returns:
            List of StructuredFact objects
        """
        facts = []

        for artifact in artifacts:
            if artifact.artifact_type == "opensecrets_lobbying":
                facts.extend(self._extract_lobbying_facts(artifact))
            elif artifact.artifact_type == "opensecrets_contributions":
                facts.extend(self._extract_contribution_facts(artifact))
            elif artifact.artifact_type == "opensecrets_revolving_door":
                facts.extend(self._extract_revolving_door_facts(artifact))

        return facts

    def _extract_lobbying_facts(self, artifact: Artifact) -> List[StructuredFact]:
        """Extract lobbying facts from artifact."""
        facts = []

        for record in KNOWN_LOBBYING:
            client, target, amount, year, url = record

            fact = StructuredFact(
                fact_type="lobbying_expenditure",
                subject=client,
                predicate="LOBBIED_FOR",
                object=target,
                source_artifact=artifact,
                confidence=0.90,  # Tier 1 journalism citing FEC/LDA
                date_occurred=year,
                raw_text=f"{client} spent {amount} lobbying for {target}",
                metadata={
                    "amount": amount,
                    "year": year,
                    "opensecrets_url": url,
                    "source_tier": 1,
                }
            )
            facts.append(fact)

        return facts

    def _extract_contribution_facts(self, artifact: Artifact) -> List[StructuredFact]:
        """Extract contribution facts from artifact."""
        facts = []

        for record in KNOWN_CONTRIBUTIONS:
            donor, recipient, amount, cycle, url = record

            fact = StructuredFact(
                fact_type="campaign_contribution",
                subject=donor,
                predicate="DONATED_TO",
                object=recipient,
                source_artifact=artifact,
                confidence=0.90,
                date_occurred=cycle,
                raw_text=f"{donor} contributed {amount} to {recipient}",
                metadata={
                    "amount": amount,
                    "cycle": cycle,
                    "opensecrets_url": url,
                    "source_tier": 1,
                }
            )
            facts.append(fact)

        return facts

    def _extract_revolving_door_facts(self, artifact: Artifact) -> List[StructuredFact]:
        """Extract revolving door facts from artifact."""
        facts = []

        for record in KNOWN_REVOLVING_DOOR:
            person, prev_role, new_employer, year, url = record

            fact = StructuredFact(
                fact_type="revolving_door",
                subject=person,
                predicate="EMPLOYED",
                object=new_employer,
                source_artifact=artifact,
                confidence=0.90,
                date_occurred=year,
                raw_text=f"{person} (former {prev_role}) joined {new_employer}",
                metadata={
                    "previous_role": prev_role,
                    "year": year,
                    "opensecrets_url": url,
                    "source_tier": 1,
                    "revolving_door": True,
                }
            )
            facts.append(fact)

        return facts

    def propose(self, facts: List[StructuredFact]) -> Tuple[List[ProposedClaim], List[ProposedEdge], List[ProposedNode]]:
        """Generate proposals from OpenSecrets facts.

        Args:
            facts: Extracted OpenSecrets facts

        Returns:
            Tuple of (claims, edges, nodes)
        """
        claims = []
        edges = []
        proposed_node_ids = {}

        for fact in facts:
            # Create claim
            claim_id = self._generate_proposal_id()

            claim = ProposedClaim(
                proposal_id=claim_id,
                claim_text=fact.raw_text,
                topic=self._determine_topic(fact),
                agent_name=self.name,
                source_url=fact.metadata.get('opensecrets_url'),
                artifact_path=fact.source_artifact.local_path,
                artifact_hash=fact.source_artifact.content_hash,
                reasoning=f"OpenSecrets Tier 1 data. {fact.metadata.get('amount', '')}",
                promotion_requirement="Verify with primary FEC/LDA filing",
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
                    node_type = self._infer_node_type(entity_name, fact)
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
                reasoning=f"OpenSecrets data. Source: {fact.metadata.get('opensecrets_url')}",
                promotion_requirement="Verify with primary FEC/LDA filing",
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
                reasoning="Entity from OpenSecrets lobbying/contribution data.",
            )
            nodes.append(node)

        return claims, edges, nodes

    def _determine_topic(self, fact: StructuredFact) -> str:
        """Determine topic from fact type."""
        if fact.fact_type == "lobbying_expenditure":
            return "Lobbying"
        elif fact.fact_type == "campaign_contribution":
            return "CampaignFinance"
        elif fact.fact_type == "revolving_door":
            return "RevolvingDoor"
        return "OpenSecrets"

    def _infer_node_type(self, entity_name: str, fact: StructuredFact) -> str:
        """Infer node type from entity name and fact context."""
        name_lower = entity_name.lower()

        # Person indicators
        person_patterns = ['gephardt', 'archer', 'lott', 'breaux', 'matsui', 'koch']
        if any(p in name_lower for p in person_patterns):
            return "PERSON"

        # Company indicators
        company_patterns = ['inc', 'corp', 'llc', 'llp', 'group', 'chase', 'bank',
                           'google', 'apple', 'microsoft', 'goldman', 'blackrock']
        if any(p in name_lower for p in company_patterns):
            return "COMPANY"

        # Organization indicators
        org_patterns = ['chamber', 'roundtable', 'institute', 'foundation', 'association']
        if any(p in name_lower for p in org_patterns):
            return "ORGANIZATION"

        # Legislation indicators
        if 'pntr' in name_lower or 'act' in name_lower:
            return "LEGISLATION"

        # Default to ORGANIZATION
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
