"""FGIP Dark Money Monitor Agent (DI-8).

Continuous monitoring of dark money flows:
- IRS Tax Exempt Organization filings (new 501(c)(3)/(c)(4))
- IRS 990 e-file data via ProPublica Nonprofit Explorer
- FEC.gov federal PACs, super PACs, independent expenditures
- State campaign finance (via FollowTheMoney.org patterns)

Detects structural patterns matching known dark money architectures.

Tier 0/1 agent - uses government filings + journalism aggregators.
"""

import hashlib
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import urllib.request
import urllib.error

from .base import FGIPAgent, Artifact, StructuredFact, ProposedClaim, ProposedEdge, ProposedNode


# ProPublica Nonprofit Explorer API
PROPUBLICA_990_API = "https://projects.propublica.org/nonprofits/api/v2"

# FEC API
FEC_API = "https://api.open.fec.gov/v1"

# IRS Tax Exempt Search (no official API, but structured search)
IRS_EO_SEARCH = "https://apps.irs.gov/app/eos/"

# User Agent
USER_AGENT = "FGIP Dark Money Monitor (research@fgip.org)"


@dataclass
class DarkMoneyPattern:
    """A detected dark money pattern."""
    pattern_type: str
    confidence: float
    signals_matched: List[str]
    entities_involved: List[str]
    filing_source: str
    description: str


# Known dark money pattern signatures
KNOWN_PATTERNS = {
    "pass_through_chain": {
        "description": "Money passes through 3+ entities before political spending",
        "signals": [
            "grant_chain_length_3plus",
            "shell_org_indicators",
            "timing_correlation",
            "same_registered_agent"
        ]
    },
    "c4_ballot_funding": {
        "description": "501(c)(4) providing majority funding to ballot committee",
        "signals": [
            "single_source_majority_funding",
            "c4_to_ballot_committee",
            "undisclosed_donors",
            "connected_officers"
        ]
    },
    "corporate_laundering": {
        "description": "Corporation to 501(c)(4) to campaign with legislative benefit",
        "signals": [
            "corporate_to_c4",
            "c4_to_campaign",
            "legislative_action_follows",
            "financial_benefit_to_corporation"
        ]
    },
    "donor_obscured_pac": {
        "description": "Super PAC with single large LLC donor (shell company)",
        "signals": [
            "llc_major_donor",
            "llc_no_operating_business",
            "pac_single_candidate_focus",
            "timing_before_election"
        ]
    }
}


class DarkMoneyAgent(FGIPAgent):
    """Continuous Dark Money Monitor (DI-8).

    Monitors tax-exempt organizations, PACs, and campaign finance
    for structural patterns indicating dark money flows.
    """

    def __init__(self, db, artifact_dir: str = "data/artifacts/dark_money"):
        super().__init__(
            db=db,
            name="dark_money",
            description="Dark Money Monitor - 501(c)(4), PACs, campaign finance"
        )
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self._rate_limit_delay = 0.5  # 500ms between requests
        self._last_request_time = 0
        self._fec_api_key = None  # Set via environment or config
        self._graph_entities = None  # Cache

    def _rate_limit(self):
        """Enforce rate limiting."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._rate_limit_delay:
            time.sleep(self._rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    def _fetch_url(self, url: str, headers: Dict = None) -> Optional[bytes]:
        """Fetch URL with rate limiting."""
        self._rate_limit()

        req_headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
        if headers:
            req_headers.update(headers)

        request = urllib.request.Request(url, headers=req_headers)

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(5)
                return self._fetch_url(url, headers)
            return None
        except Exception:
            return None

    def _get_graph_entities(self) -> Dict[str, Dict]:
        """Get all entities from nodes table for cross-reference."""
        if self._graph_entities is None:
            conn = self.db.connect()
            rows = conn.execute(
                """SELECT node_id, name, node_type, metadata FROM nodes"""
            ).fetchall()
            self._graph_entities = {}
            for row in rows:
                self._graph_entities[row["node_id"]] = {
                    "name": row["name"],
                    "type": row["node_type"],
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else {}
                }
        return self._graph_entities

    def collect(self) -> List[Artifact]:
        """Collect data from dark money sources.

        Sources:
        1. ProPublica Nonprofit Explorer - recent 990 filings
        2. FEC API - recent committee filings
        3. Watch for entities already in graph
        """
        artifacts = []

        # Collect ProPublica 990 data for tracked organizations
        artifacts.extend(self._collect_propublica_990s())

        # Collect FEC committee data
        artifacts.extend(self._collect_fec_committees())

        return artifacts

    def _collect_propublica_990s(self) -> List[Artifact]:
        """Fetch 990 filings from ProPublica for tracked orgs."""
        artifacts = []
        entities = self._get_graph_entities()

        # Focus on ORGANIZATION type entities
        org_entities = [
            (node_id, info) for node_id, info in entities.items()
            if info.get("type") in ("ORGANIZATION", "COMPANY")
        ]

        for node_id, info in org_entities[:20]:  # Limit per run
            org_name = info.get("name", "")
            if not org_name:
                continue

            # Search ProPublica for this organization
            search_url = f"{PROPUBLICA_990_API}/search.json?q={urllib.parse.quote(org_name)}"
            content = self._fetch_url(search_url)

            if not content:
                continue

            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                continue

            organizations = data.get("organizations", [])
            if not organizations:
                continue

            # Get the most relevant match
            org = organizations[0]
            ein = org.get("ein")

            if ein:
                # Fetch detailed 990 data
                org_url = f"{PROPUBLICA_990_API}/organizations/{ein}.json"
                org_content = self._fetch_url(org_url)

                if org_content:
                    content_hash = hashlib.sha256(org_content).hexdigest()
                    local_path = self.artifact_dir / f"990_{ein}.json"

                    with open(local_path, "wb") as f:
                        f.write(org_content)

                    artifact = Artifact(
                        url=org_url,
                        artifact_type="json",
                        local_path=str(local_path),
                        content_hash=content_hash,
                        metadata={
                            "source": "propublica_nonprofit",
                            "ein": ein,
                            "org_name": org.get("name", ""),
                            "graph_node_id": node_id,
                        }
                    )
                    artifacts.append(artifact)

        return artifacts

    def _collect_fec_committees(self) -> List[Artifact]:
        """Fetch FEC committee data."""
        artifacts = []

        # Search for committees related to tracked entities
        entities = self._get_graph_entities()

        # Also search for generic terms related to our topics
        search_terms = ["reshoring", "manufacturing", "trade", "tariff"]

        for term in search_terms[:3]:
            # FEC committee search
            search_url = f"{FEC_API}/names/committees/?q={term}"
            if self._fec_api_key:
                search_url += f"&api_key={self._fec_api_key}"

            content = self._fetch_url(search_url)
            if not content:
                continue

            content_hash = hashlib.sha256(content).hexdigest()
            local_path = self.artifact_dir / f"fec_search_{term}.json"

            with open(local_path, "wb") as f:
                f.write(content)

            artifact = Artifact(
                url=search_url,
                artifact_type="json",
                local_path=str(local_path),
                content_hash=content_hash,
                metadata={
                    "source": "fec",
                    "search_term": term,
                }
            )
            artifacts.append(artifact)

        return artifacts

    def extract(self, artifacts: List[Artifact]) -> List[StructuredFact]:
        """Extract dark money facts from collected data."""
        facts = []

        for artifact in artifacts:
            source = artifact.metadata.get("source", "")

            if source == "propublica_nonprofit":
                facts.extend(self._extract_990_facts(artifact))
            elif source == "fec":
                facts.extend(self._extract_fec_facts(artifact))

        return facts

    def _extract_990_facts(self, artifact: Artifact) -> List[StructuredFact]:
        """Extract facts from 990 filing data."""
        facts = []

        if not artifact.local_path:
            return facts

        try:
            with open(artifact.local_path, "r") as f:
                data = json.load(f)
        except Exception:
            return facts

        org = data.get("organization", {})
        org_name = org.get("name", artifact.metadata.get("org_name", "Unknown"))
        ein = artifact.metadata.get("ein", "")
        graph_node_id = artifact.metadata.get("graph_node_id", "")

        # Extract from filings_with_data
        filings = data.get("filings_with_data", [])

        for filing in filings[:3]:  # Recent 3 years
            tax_period = filing.get("tax_prd", "")
            totrevenue = filing.get("totrevenue", 0)
            totexpns = filing.get("totexpns", 0)
            totassetsend = filing.get("totassetsend", 0)

            # Track large organizations
            if totrevenue and totrevenue > 1000000:
                facts.append(StructuredFact(
                    fact_type="dark_money_990",
                    subject=org_name,
                    predicate="REPORTED_REVENUE",
                    object=f"${totrevenue:,}",
                    source_artifact=artifact,
                    confidence=0.9,
                    date_occurred=tax_period,
                    metadata={
                        "ein": ein,
                        "graph_node_id": graph_node_id,
                        "totexpns": totexpns,
                        "totassetsend": totassetsend,
                    }
                ))

            # Look for grants to other organizations (pass-through detection)
            # This would be in Part IV / Schedule I of full 990

        # Detect patterns
        patterns = self._detect_patterns_990(org, filings)
        for pattern in patterns:
            facts.append(StructuredFact(
                fact_type="dark_money_pattern",
                subject=org_name,
                predicate=f"PATTERN_{pattern.pattern_type.upper()}",
                object=pattern.description,
                source_artifact=artifact,
                confidence=pattern.confidence,
                raw_text=f"Pattern detected: {pattern.description}. Signals: {', '.join(pattern.signals_matched)}",
                metadata={
                    "pattern_type": pattern.pattern_type,
                    "signals_matched": pattern.signals_matched,
                    "entities_involved": pattern.entities_involved,
                }
            ))

        return facts

    def _extract_fec_facts(self, artifact: Artifact) -> List[StructuredFact]:
        """Extract facts from FEC committee data."""
        facts = []

        if not artifact.local_path:
            return facts

        try:
            with open(artifact.local_path, "r") as f:
                data = json.load(f)
        except Exception:
            return facts

        results = data.get("results", [])

        for result in results[:20]:
            committee_name = result.get("name", "")
            committee_id = result.get("id", "")

            if committee_name:
                facts.append(StructuredFact(
                    fact_type="fec_committee",
                    subject=committee_name,
                    predicate="REGISTERED_AS",
                    object="FEC Political Committee",
                    source_artifact=artifact,
                    confidence=0.95,
                    metadata={
                        "committee_id": committee_id,
                        "search_term": artifact.metadata.get("search_term", ""),
                    }
                ))

        return facts

    def _detect_patterns_990(self, org: Dict, filings: List[Dict]) -> List[DarkMoneyPattern]:
        """Detect dark money patterns in 990 filing data."""
        patterns = []
        org_name = org.get("name", "")

        # Check for pass-through indicators
        signals_found = []

        # Shell org indicators: high revenue but minimal program expense ratio
        for filing in filings:
            totrevenue = filing.get("totrevenue", 0)
            totfuncexpns = filing.get("totfuncexpns", 0)

            if totrevenue > 0 and totfuncexpns > 0:
                program_ratio = totfuncexpns / totrevenue
                if program_ratio < 0.3:  # Less than 30% on programs
                    signals_found.append("shell_org_indicators")

        # Large grants in/out ratio would indicate pass-through
        # (Would need full 990 Schedule I data)

        # If we have enough signals, report a pattern
        if len(signals_found) >= 1:
            patterns.append(DarkMoneyPattern(
                pattern_type="potential_shell",
                confidence=0.5 + (0.1 * len(signals_found)),
                signals_matched=signals_found,
                entities_involved=[org_name],
                filing_source="990",
                description=f"Organization shows {len(signals_found)} shell org indicator(s)"
            ))

        return patterns

    def propose(self, facts: List[StructuredFact]) -> tuple[List[ProposedClaim], List[ProposedEdge], List[ProposedNode]]:
        """Generate proposals from dark money facts."""
        claims = []
        edges = []
        nodes = []

        for fact in facts:
            proposal_id = self._generate_proposal_id()

            # Generate claim text
            if fact.fact_type == "dark_money_990":
                claim_text = f"{fact.subject} reported {fact.object} in revenue ({fact.date_occurred})"
            elif fact.fact_type == "dark_money_pattern":
                claim_text = f"Dark money pattern detected: {fact.subject} - {fact.object}"
            elif fact.fact_type == "fec_committee":
                claim_text = f"{fact.subject} is registered as {fact.object}"
            else:
                claim_text = f"{fact.subject} {fact.predicate} {fact.object}"

            # Determine topic
            topic = "ThinkTank" if "501(c)" in claim_text else "Lobbying"

            claim = ProposedClaim(
                proposal_id=proposal_id,
                claim_text=claim_text,
                topic=topic,
                agent_name=self.name,
                source_url=fact.source_artifact.url,
                artifact_path=fact.source_artifact.local_path,
                artifact_hash=fact.source_artifact.content_hash,
                reasoning=f"Extracted from {fact.source_artifact.metadata.get('source', 'dark money source')}",
                promotion_requirement="Verify against original IRS 990 or FEC filing",
            )
            claims.append(claim)

            # Create edge for patterns with existing graph entities
            if fact.metadata.get("graph_node_id"):
                edge_id = self._generate_proposal_id()

                # Link to existing node if we have it
                from_node = fact.metadata["graph_node_id"]
                to_node = self._slugify(fact.predicate.lower())

                edge = ProposedEdge(
                    proposal_id=edge_id,
                    from_node=from_node,
                    to_node=to_node,
                    relationship="FUNDED_BY" if "revenue" in claim_text.lower() else "ASSOCIATED_WITH",
                    agent_name=self.name,
                    detail=claim_text,
                    proposed_claim_id=proposal_id,
                    confidence=fact.confidence,
                    reasoning="Dark money monitor pattern detection",
                )
                edges.append(edge)

        return claims, edges, nodes

    def _slugify(self, name: str) -> str:
        """Convert name to node_id slug."""
        slug = name.lower()
        slug = re.sub(r'[^a-z0-9]+', '-', slug)
        return slug.strip('-')[:50]


# Import urllib.parse for URL encoding
import urllib.parse
