"""FGIP SCOTUS Agent - Supreme Court Docket Watcher.

Watches supremecourt.gov for opinions, orders, amicus briefs.
Extracts case parties, outcomes, amicus filers.
Proposes FILED_AMICUS, RULED_ON edges.

Tier 0 agent - uses official Supreme Court website.

Safety rules:
- Uses official supremecourt.gov
- Stores only public documents
- Respects rate limits
- Artifacts saved locally with SHA256 hash
"""

import hashlib
import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any
import urllib.request
import urllib.error

try:
    from .base import FGIPAgent, Artifact, StructuredFact, ProposedClaim, ProposedEdge
except ImportError:
    from base import FGIPAgent, Artifact, StructuredFact, ProposedClaim, ProposedEdge


# Supreme Court URLs
SCOTUS_BASE_URL = "https://www.supremecourt.gov"
SCOTUS_ORDERS_URL = f"{SCOTUS_BASE_URL}/orders/ordersofthecourt"
SCOTUS_OPINIONS_URL = f"{SCOTUS_BASE_URL}/opinions/slipopinion/"  # Format: /opinions/slipopinion/{term}
SCOTUS_DOCKET_URL = f"{SCOTUS_BASE_URL}/search.aspx?filename=/docket/docketfiles/html/public/"

USER_AGENT = "FGIP Research Agent (contact@example.com)"


class SCOTUSAgent(FGIPAgent):
    """Supreme Court docket watcher agent.

    Monitors Supreme Court for:
    - New opinions and orders
    - Amicus brief filings
    - Case outcomes

    Proposes edges:
    - FILED_AMICUS: Organization filed amicus brief in case
    - RULED_ON: Court ruled on case
    """

    def __init__(self, db, artifact_dir: str = "data/artifacts/scotus"):
        super().__init__(
            db=db,
            name="scotus",
            description="Supreme Court docket watcher - opinions, orders, amicus"
        )
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self._rate_limit_delay = 1.0  # 1 second between requests
        self._last_request_time = 0

    def _rate_limit(self):
        """Enforce rate limiting."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._rate_limit_delay:
            time.sleep(self._rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    def _fetch_url(self, url: str) -> Optional[bytes]:
        """Fetch URL with proper headers and rate limiting."""
        self._rate_limit()

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html, application/pdf, */*",
            }
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()
        except urllib.error.HTTPError:
            return None
        except Exception:
            return None

    def _get_tracked_cases(self) -> List[Dict[str, Any]]:
        """Get court cases from nodes table."""
        conn = self.db.connect()
        rows = conn.execute(
            """SELECT node_id, name, metadata FROM nodes
               WHERE node_type = 'COURT_CASE'"""
        ).fetchall()

        cases = []
        for row in rows:
            metadata = json.loads(row["metadata"]) if row["metadata"] else {}
            cases.append({
                "node_id": row["node_id"],
                "name": row["name"],
                "docket_number": metadata.get("docket_number"),
                "term": metadata.get("term"),
            })
        return cases

    def _get_tracked_organizations(self) -> List[Dict[str, Any]]:
        """Get organizations that might file amicus briefs."""
        conn = self.db.connect()
        rows = conn.execute(
            """SELECT node_id, name, aliases FROM nodes
               WHERE node_type IN ('ORGANIZATION', 'COMPANY')"""
        ).fetchall()

        orgs = []
        for row in rows:
            aliases = json.loads(row["aliases"]) if row["aliases"] else []
            orgs.append({
                "node_id": row["node_id"],
                "name": row["name"],
                "aliases": aliases,
            })
        return orgs

    def _get_recent_term(self) -> str:
        """Get current SCOTUS term (October term year, last 2 digits).

        SCOTUS URLs use 2-digit term numbers (e.g., /slipopinion/24 for OT 2024).
        """
        now = datetime.utcnow()
        if now.month >= 10:
            term_year = now.year
        else:
            term_year = now.year - 1
        # Return 2-digit format for URL
        return str(term_year)[-2:]

    def _fetch_docket_page(self, docket_number: str) -> Optional[str]:
        """Fetch docket page for a case."""
        # Format: 22-451 -> search URL
        url = f"{SCOTUS_BASE_URL}/search.aspx?filename=/docket/docketfiles/html/public/{docket_number}.html"
        content = self._fetch_url(url)
        if content:
            return content.decode("utf-8", errors="ignore")
        return None

    def _fetch_opinions_page(self, term: str) -> Optional[str]:
        """Fetch opinions page for a term."""
        url = f"{SCOTUS_OPINIONS_URL}{term}"
        content = self._fetch_url(url)
        if content:
            return content.decode("utf-8", errors="ignore")
        return None

    def collect(self) -> List[Artifact]:
        """Fetch recent SCOTUS documents."""
        artifacts = []
        term = self._get_recent_term()

        # Fetch opinions page
        opinions_html = self._fetch_opinions_page(term)
        if opinions_html:
            content_hash = hashlib.sha256(opinions_html.encode()).hexdigest()
            local_path = self.artifact_dir / f"opinions_{term}.html"

            with open(local_path, "w", encoding="utf-8") as f:
                f.write(opinions_html)

            artifacts.append(Artifact(
                url=f"{SCOTUS_OPINIONS_URL}{term}",
                artifact_type="html",
                local_path=str(local_path),
                content_hash=content_hash,
                metadata={
                    "doc_type": "opinions_index",
                    "term": term,
                }
            ))

        # Fetch tracked case dockets
        cases = self._get_tracked_cases()
        for case in cases[:10]:  # Limit per run
            docket = case.get("docket_number")
            if not docket:
                continue

            docket_html = self._fetch_docket_page(docket)
            if docket_html:
                content_hash = hashlib.sha256(docket_html.encode()).hexdigest()
                local_path = self.artifact_dir / f"docket_{docket.replace('-', '_')}.html"

                with open(local_path, "w", encoding="utf-8") as f:
                    f.write(docket_html)

                artifacts.append(Artifact(
                    url=f"{SCOTUS_BASE_URL}/docket/{docket}",
                    artifact_type="html",
                    local_path=str(local_path),
                    content_hash=content_hash,
                    metadata={
                        "doc_type": "docket",
                        "docket_number": docket,
                        "case_node_id": case["node_id"],
                        "case_name": case["name"],
                    }
                ))

        return artifacts

    def extract(self, artifacts: List[Artifact]) -> List[StructuredFact]:
        """Extract facts from SCOTUS documents."""
        facts = []

        for artifact in artifacts:
            doc_type = artifact.metadata.get("doc_type")

            if doc_type == "opinions_index":
                facts.extend(self._extract_opinions(artifact))
            elif doc_type == "docket":
                facts.extend(self._extract_docket_info(artifact))

        return facts

    def _extract_opinions(self, artifact: Artifact) -> List[StructuredFact]:
        """Extract opinion information from opinions index."""
        facts = []

        if not artifact.local_path:
            return facts

        try:
            with open(artifact.local_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return facts

        term = artifact.metadata.get("term", "")

        # Look for opinion entries
        # Pattern: case name, docket number, date, PDF link
        opinion_pattern = re.compile(
            r'<tr[^>]*>.*?'
            r'(?P<date>\d{1,2}/\d{1,2}/\d{2,4}).*?'
            r'(?P<docket>\d{2,4}-\d+).*?'
            r'(?P<name>[A-Z][^<]{10,100})'
            r'.*?</tr>',
            re.IGNORECASE | re.DOTALL
        )

        for match in opinion_pattern.finditer(content):
            try:
                date = match.group("date")
                docket = match.group("docket")
                name = match.group("name").strip()

                # Clean up case name
                name = re.sub(r'\s+', ' ', name)
                name = name[:100]

                facts.append(StructuredFact(
                    fact_type="opinion",
                    subject="Supreme Court",
                    predicate="RULED_ON",
                    object=name,
                    source_artifact=artifact,
                    confidence=0.95,
                    date_occurred=date,
                    metadata={
                        "docket_number": docket,
                        "term": term,
                    }
                ))
            except Exception:
                continue

        return facts

    def _extract_docket_info(self, artifact: Artifact) -> List[StructuredFact]:
        """Extract docket information including amicus briefs."""
        facts = []

        if not artifact.local_path:
            return facts

        try:
            with open(artifact.local_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return facts

        case_name = artifact.metadata.get("case_name", "")
        docket_number = artifact.metadata.get("docket_number", "")
        case_node_id = artifact.metadata.get("case_node_id", "")

        # Extract amicus brief filers
        # Look for "Brief amicus curiae of [ORGANIZATION]"
        amicus_pattern = re.compile(
            r'(?:Brief|Motion)\s+(?:of\s+)?(?:amicus|amici)\s+curiae\s+(?:of\s+)?'
            r'([A-Z][A-Za-z\s,\.&]+?)(?:\s+(?:filed|in support|urging))',
            re.IGNORECASE
        )

        amicus_orgs = amicus_pattern.findall(content)

        tracked_orgs = self._get_tracked_organizations()
        tracked_names = {org["name"].lower(): org for org in tracked_orgs}
        for org in tracked_orgs:
            for alias in org.get("aliases", []):
                tracked_names[alias.lower()] = org

        for org_name in amicus_orgs:
            org_name = org_name.strip().rstrip(",.")

            # Check if this is a tracked organization
            org_lower = org_name.lower()
            matched_org = None

            for tracked_name, org_data in tracked_names.items():
                if tracked_name in org_lower or org_lower in tracked_name:
                    matched_org = org_data
                    break

            facts.append(StructuredFact(
                fact_type="amicus_filing",
                subject=org_name,
                predicate="FILED_AMICUS",
                object=case_name,
                source_artifact=artifact,
                confidence=0.85 if matched_org else 0.6,
                metadata={
                    "docket_number": docket_number,
                    "case_node_id": case_node_id,
                    "matched_org_node_id": matched_org["node_id"] if matched_org else None,
                }
            ))

        # Extract case outcome if decided
        outcome_patterns = [
            (r"(?:affirmed|reversed|vacated|remanded)", "decided"),
            (r"certiorari\s+(?:granted|denied)", "cert_decision"),
        ]

        for pattern, outcome_type in outcome_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                facts.append(StructuredFact(
                    fact_type="case_outcome",
                    subject="Supreme Court",
                    predicate="RULED_ON",
                    object=case_name,
                    source_artifact=artifact,
                    confidence=0.9,
                    metadata={
                        "outcome_type": outcome_type,
                        "docket_number": docket_number,
                    }
                ))
                break

        return facts

    def propose(self, facts: List[StructuredFact]) -> tuple[List[ProposedClaim], List[ProposedEdge]]:
        """Generate HYPOTHESIS claims and edges from extracted facts."""
        claims = []
        edges = []

        for fact in facts:
            proposal_id = self._generate_proposal_id()

            # Create claim
            if fact.fact_type == "amicus_filing":
                claim_text = f"{fact.subject} filed amicus curiae brief in {fact.object}"
            elif fact.fact_type == "opinion":
                claim_text = f"Supreme Court issued opinion in {fact.object}"
                if fact.metadata.get("docket_number"):
                    claim_text += f" (Docket: {fact.metadata['docket_number']})"
            elif fact.fact_type == "case_outcome":
                claim_text = f"Supreme Court ruled on {fact.object}"
            else:
                claim_text = f"{fact.subject} {fact.predicate} {fact.object}"

            claim = ProposedClaim(
                proposal_id=proposal_id,
                claim_text=claim_text,
                topic="SCOTUS",
                agent_name=self.name,
                source_url=fact.source_artifact.url,
                artifact_path=fact.source_artifact.local_path,
                artifact_hash=fact.source_artifact.content_hash,
                reasoning=f"Extracted from Supreme Court docket/opinion page",
                promotion_requirement="Verify against official supremecourt.gov docket",
            )
            claims.append(claim)

            # Create edge proposals
            if fact.fact_type == "amicus_filing":
                edge_proposal_id = self._generate_proposal_id()

                from_node = fact.metadata.get("matched_org_node_id") or fact.subject.lower().replace(" ", "_")[:30]
                to_node = fact.metadata.get("case_node_id") or fact.object.lower().replace(" ", "_")[:30]

                edge = ProposedEdge(
                    proposal_id=edge_proposal_id,
                    from_node=from_node,
                    to_node=to_node,
                    relationship="FILED_AMICUS",
                    agent_name=self.name,
                    detail=claim_text,
                    proposed_claim_id=proposal_id,
                    confidence=fact.confidence,
                    reasoning="Supreme Court amicus brief filing",
                    promotion_requirement="Verify organization node exists; confirm amicus filing in docket",
                )
                edges.append(edge)

            elif fact.fact_type in ("opinion", "case_outcome"):
                edge_proposal_id = self._generate_proposal_id()

                edge = ProposedEdge(
                    proposal_id=edge_proposal_id,
                    from_node="scotus",
                    to_node=fact.metadata.get("case_node_id") or fact.object.lower().replace(" ", "_")[:30],
                    relationship="RULED_ON",
                    agent_name=self.name,
                    detail=claim_text,
                    proposed_claim_id=proposal_id,
                    confidence=fact.confidence,
                    reasoning="Supreme Court opinion/order",
                    promotion_requirement="Verify case node exists; confirm ruling in official opinion",
                )
                edges.append(edge)

        return claims, edges


# CLI entry point
if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    from fgip.db import FGIPDatabase

    if len(sys.argv) < 2:
        print("Usage: python scotus.py <database_path>")
        print("Example: python scotus.py fgip.db")
        sys.exit(1)

    db_path = sys.argv[1]
    db = FGIPDatabase(db_path)

    agent = SCOTUSAgent(db)

    print(f"\n{'='*60}")
    print(f"SCOTUS Agent - Supreme Court Docket Watcher")
    print(f"{'='*60}")

    results = agent.run()

    print(f"\n{'='*60}")
    print(f"Results:")
    print(f"  Artifacts collected: {results['artifacts_collected']}")
    print(f"  Facts extracted: {results['facts_extracted']}")
    print(f"  Claims proposed: {results['claims_proposed']}")
    print(f"  Edges proposed: {results['edges_proposed']}")

    if results['errors']:
        print(f"\nErrors:")
        for error in results['errors']:
            print(f"  - {error}")

    # Show status
    status = agent.get_status()
    print(f"\nAgent Status:")
    print(f"  Pending claims: {status['pending_claims']}")
    print(f"  Pending edges: {status['pending_edges']}")
    print(f"  Approved claims: {status['approved_claims']}")
    print(f"  Approved edges: {status['approved_edges']}")
