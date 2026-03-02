"""FGIP Nuclear SMR Agent - Nuclear Regulatory Commission & DoE Watcher.

Tracks NRC licensing, DoE ARDP grants, and SEC filings for nuclear companies.
The nuclear sector is the POWER GENERATION component of the reshoring thesis:
  Reshoring → Factories need power → AI data centers need baseload →
  Grid can't handle it → SMRs are the answer → Correction Layer infrastructure

Tier 0 agent - uses official NRC and DoE sources.

Safety rules:
- Uses official NRC.gov and Energy.gov APIs
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
from typing import List, Optional, Dict, Any, Tuple
from urllib.parse import urljoin
import urllib.request
import urllib.error

from .base import FGIPAgent, Artifact, StructuredFact, ProposedClaim, ProposedEdge, ProposedNode


# =============================================================================
# NUCLEAR COMPANY IDENTIFIERS
# =============================================================================

# CIK numbers for SEC EDGAR lookups
NUCLEAR_CIKS = {
    "nne": "0001976315",           # NuScale (now trades as SMR)
    "oklo": "0001849820",          # Oklo
    "bwxt": "0001486957",          # BWX Technologies
    "centrus-energy": "0000042291", # Centrus (LEU)
    "constellation-energy": "0001868275",  # CEG
}

# NRC docket numbers for licensing tracking
NRC_DOCKETS = {
    "nne": "52-048",              # NuScale US460 design
    "oklo": "52-049",             # Aurora
    "terrapower": "50-610",       # Natrium
    "kairos-power": "50-609",     # Hermes
    "x-energy": "52-050",         # Xe-100
}

# EDGAR filing types we care about
RELEVANT_FILING_TYPES = {
    "10-K": "Annual report",
    "10-K/A": "Amended annual report",
    "8-K": "Material event report",
    "8-K/A": "Amended material event",
    "S-1": "IPO registration",
    "DEF 14A": "Proxy statement",
}

# =============================================================================
# API ENDPOINTS
# =============================================================================

NRC_NEWS_URL = "https://www.nrc.gov/reading-rm/doc-collections/news/"
NRC_SMR_PAGE = "https://www.nrc.gov/reactors/new-reactors/smr.html"
DOE_NE_NEWS = "https://www.energy.gov/ne/listings/nuclear-energy-news"
DOE_ARDP_PAGE = "https://www.energy.gov/ne/advanced-reactor-demonstration-program"
EDGAR_FILINGS_API = "https://data.sec.gov/submissions/CIK{cik}.json"
EDGAR_FILING_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{filename}"

USER_AGENT = "FGIP Nuclear Research Agent (research@example.com)"


class NuclearSMRAgent(FGIPAgent):
    """Nuclear SMR sector watcher agent.

    Monitors:
    - NRC licensing actions (permits, design certifications)
    - DoE ARDP grant announcements
    - Nuclear company EDGAR filings (10-K, 8-K)
    - SMR project milestones

    Proposes:
    - LICENSED_BY edges (company → NRC)
    - FUNDED_BY edges (company → DoE)
    - DEVELOPS edges (company → technology)
    - Material event claims (8-K filings)
    """

    def __init__(self, db, artifact_dir: str = "data/artifacts/nuclear"):
        super().__init__(
            db=db,
            name="nuclear_smr",
            description="Nuclear SMR sector watcher - NRC permits, DoE grants, EDGAR"
        )
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self._rate_limit_delay = 0.2  # 200ms between requests
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
                "Accept": "text/html, application/json, */*",
            }
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()
        except urllib.error.HTTPError as e:
            if e.code == 429:  # Rate limited
                time.sleep(5)
                return self._fetch_url(url)
            print(f"  HTTP Error {e.code} fetching {url}")
            return None
        except Exception as e:
            print(f"  Error fetching {url}: {e}")
            return None

    def collect(self) -> List[Artifact]:
        """Fetch artifacts from NRC, DoE, and SEC EDGAR.

        1. Scrape NRC new reactor licensing page
        2. Scrape DoE nuclear energy news
        3. Fetch EDGAR filings for nuclear tickers
        """
        artifacts = []

        # 1. NRC SMR Licensing Page
        print("  Fetching NRC SMR licensing page...")
        nrc_content = self._fetch_url(NRC_SMR_PAGE)
        if nrc_content:
            content_hash = hashlib.sha256(nrc_content).hexdigest()
            local_path = self.artifact_dir / f"nrc_smr_page_{datetime.utcnow().strftime('%Y%m%d')}.html"
            local_path.write_bytes(nrc_content)

            artifacts.append(Artifact(
                url=NRC_SMR_PAGE,
                artifact_type="html",
                local_path=str(local_path),
                content_hash=content_hash,
                metadata={
                    "source": "nrc",
                    "type": "smr_licensing_page",
                }
            ))

        # 2. DoE Nuclear Energy News
        print("  Fetching DoE Nuclear Energy news...")
        doe_content = self._fetch_url(DOE_NE_NEWS)
        if doe_content:
            content_hash = hashlib.sha256(doe_content).hexdigest()
            local_path = self.artifact_dir / f"doe_ne_news_{datetime.utcnow().strftime('%Y%m%d')}.html"
            local_path.write_bytes(doe_content)

            artifacts.append(Artifact(
                url=DOE_NE_NEWS,
                artifact_type="html",
                local_path=str(local_path),
                content_hash=content_hash,
                metadata={
                    "source": "doe",
                    "type": "nuclear_news",
                }
            ))

        # 3. EDGAR filings for nuclear companies
        print("  Fetching EDGAR filings for nuclear companies...")
        for node_id, cik in NUCLEAR_CIKS.items():
            filings = self._get_recent_filings(cik, days=90)

            for filing in filings[:3]:  # Limit to 3 most recent per company
                url = EDGAR_FILING_URL.format(
                    cik=cik.lstrip("0"),
                    accession=filing["accession"].replace("-", ""),
                    filename=filing["primary_document"]
                )

                content = self._fetch_url(url)
                if not content:
                    continue

                content_hash = hashlib.sha256(content).hexdigest()
                safe_doc = filing["primary_document"].replace("/", "_")
                filename = f"{node_id}_{filing['accession']}_{safe_doc}"
                local_path = self.artifact_dir / filename

                local_path.write_bytes(content)

                artifacts.append(Artifact(
                    url=url,
                    artifact_type=safe_doc.split(".")[-1].lower() if "." in safe_doc else "html",
                    local_path=str(local_path),
                    content_hash=content_hash,
                    metadata={
                        "source": "edgar",
                        "cik": cik,
                        "form": filing["form"],
                        "filing_date": filing["filing_date"],
                        "entity_node_id": node_id,
                    }
                ))

        print(f"  Collected {len(artifacts)} artifacts")
        return artifacts

    def _get_recent_filings(self, cik: str, days: int = 90) -> List[Dict[str, Any]]:
        """Get recent EDGAR filings for a CIK."""
        url = EDGAR_FILINGS_API.format(cik=cik.zfill(10))
        content = self._fetch_url(url)

        if not content:
            return []

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return []

        filings = []
        recent = data.get("filings", {}).get("recent", {})

        if not recent:
            return []

        cutoff_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])

        for i, form in enumerate(forms):
            if form not in RELEVANT_FILING_TYPES:
                continue

            filing_date = dates[i] if i < len(dates) else ""
            if filing_date < cutoff_date:
                continue

            accession = accessions[i] if i < len(accessions) else ""
            primary_doc = primary_docs[i] if i < len(primary_docs) else ""

            if not primary_doc:
                continue

            filings.append({
                "form": form,
                "filing_date": filing_date,
                "accession": accession,
                "primary_document": primary_doc,
                "description": RELEVANT_FILING_TYPES.get(form, ""),
            })

        return filings

    def extract(self, artifacts: List[Artifact]) -> List[StructuredFact]:
        """Extract licensing, funding, and event facts from artifacts."""
        facts = []

        for artifact in artifacts:
            source = artifact.metadata.get("source", "")

            if source == "nrc":
                facts.extend(self._extract_nrc_licensing(artifact))
            elif source == "doe":
                facts.extend(self._extract_doe_grants(artifact))
            elif source == "edgar":
                facts.extend(self._extract_edgar_events(artifact))

        print(f"  Extracted {len(facts)} facts")
        return facts

    def _extract_nrc_licensing(self, artifact: Artifact) -> List[StructuredFact]:
        """Extract NRC licensing milestones from page."""
        facts = []

        if not artifact.local_path:
            return facts

        try:
            with open(artifact.local_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            return facts

        # Patterns for licensing milestones
        patterns = {
            "design_certification": re.compile(
                r"(NuScale|Oklo|TerraPower|Kairos|X-Energy|BWXT).*?design\s+certification.*?(?:approved|issued|granted|submitted)",
                re.IGNORECASE | re.DOTALL
            ),
            "construction_permit": re.compile(
                r"(NuScale|Oklo|TerraPower|Kairos|X-Energy).*?construction\s+permit.*?(?:approved|issued|granted|submitted)",
                re.IGNORECASE | re.DOTALL
            ),
            "operating_license": re.compile(
                r"(NuScale|Oklo|TerraPower|Kairos|X-Energy).*?operating\s+license.*?(?:approved|issued|submitted)",
                re.IGNORECASE | re.DOTALL
            ),
        }

        company_map = {
            "nuscale": "nne",
            "oklo": "oklo",
            "terrapower": "terrapower",
            "kairos": "kairos-power",
            "x-energy": "x-energy",
            "bwxt": "bwxt",
        }

        for milestone_type, pattern in patterns.items():
            for match in pattern.findall(content):
                company_name = match.strip().lower()
                for key, node_id in company_map.items():
                    if key in company_name:
                        facts.append(StructuredFact(
                            fact_type="nrc_licensing",
                            subject=node_id,
                            predicate=f"NRC_{milestone_type.upper()}",
                            object="nrc",
                            source_artifact=artifact,
                            confidence=0.85,
                            date_occurred=datetime.utcnow().strftime("%Y-%m-%d"),
                            raw_text=match[:200] if isinstance(match, str) else str(match)[:200],
                            metadata={"milestone": milestone_type}
                        ))
                        break

        return facts

    def _extract_doe_grants(self, artifact: Artifact) -> List[StructuredFact]:
        """Extract DoE grant announcements from page."""
        facts = []

        if not artifact.local_path:
            return facts

        try:
            with open(artifact.local_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            return facts

        # ARDP grant patterns
        ardp_pattern = re.compile(
            r"(TerraPower|X-Energy|Kairos|NuScale|Oklo).*?(?:receives?|awarded?|grants?).*?\$?(\d+(?:\.\d+)?)\s*(?:billion|million|B|M)",
            re.IGNORECASE | re.DOTALL
        )

        haleu_pattern = re.compile(
            r"(Centrus|BWXT).*?HALEU.*?(?:contract|award|funding).*?\$?(\d+(?:\.\d+)?)\s*(?:billion|million|B|M)",
            re.IGNORECASE | re.DOTALL
        )

        company_map = {
            "terrapower": "terrapower",
            "x-energy": "x-energy",
            "kairos": "kairos-power",
            "nuscale": "nne",
            "oklo": "oklo",
            "centrus": "centrus-energy",
            "bwxt": "bwxt",
        }

        for pattern in [ardp_pattern, haleu_pattern]:
            for match in pattern.findall(content):
                company_name = match[0].strip().lower() if isinstance(match, tuple) else match.lower()
                amount = match[1] if isinstance(match, tuple) and len(match) > 1 else None

                for key, node_id in company_map.items():
                    if key in company_name:
                        facts.append(StructuredFact(
                            fact_type="doe_funding",
                            subject=node_id,
                            predicate="FUNDED_BY",
                            object="doe-ne",
                            source_artifact=artifact,
                            confidence=0.90,
                            date_occurred=datetime.utcnow().strftime("%Y-%m-%d"),
                            raw_text=f"{company_name} awarded ${amount}",
                            metadata={"amount": amount}
                        ))
                        break

        return facts

    def _extract_edgar_events(self, artifact: Artifact) -> List[StructuredFact]:
        """Extract material events from EDGAR filings."""
        facts = []

        if not artifact.local_path:
            return facts

        try:
            with open(artifact.local_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()[:50000]  # Limit to first 50K chars
        except Exception:
            return facts

        entity_node_id = artifact.metadata.get("entity_node_id", "")
        form = artifact.metadata.get("form", "")
        filing_date = artifact.metadata.get("filing_date", "")

        # 8-K event patterns
        if "8-K" in form:
            event_patterns = [
                (r"Item\s+1\.01.*?Entry into.*?(?:Agreement|Contract)", "AGREEMENT"),
                (r"Item\s+2\.01.*?(?:Acquisition|Merger)", "ACQUISITION"),
                (r"Item\s+5\.02.*?(?:appointed|resigned|elected)", "EXECUTIVE_CHANGE"),
                (r"(?:NRC|DOE|Department of Energy).*?(?:approved|granted|awarded)", "REGULATORY_APPROVAL"),
                (r"construction\s+(?:permit|license).*?(?:received|approved|granted)", "CONSTRUCTION_PERMIT"),
            ]

            for pattern, event_type in event_patterns:
                if re.search(pattern, content, re.IGNORECASE | re.DOTALL):
                    facts.append(StructuredFact(
                        fact_type="material_event",
                        subject=entity_node_id,
                        predicate=event_type,
                        object=f"8-K Event: {event_type}",
                        source_artifact=artifact,
                        confidence=0.85,
                        date_occurred=filing_date,
                        metadata={"form": form}
                    ))

        # 10-K patterns (annual report)
        elif "10-K" in form:
            # Look for NRC/DoE mentions
            nrc_mention = re.search(
                r"(?:NRC|Nuclear Regulatory Commission).*?(?:approved|granted|certified|license)",
                content, re.IGNORECASE
            )
            if nrc_mention:
                facts.append(StructuredFact(
                    fact_type="regulatory_status",
                    subject=entity_node_id,
                    predicate="LICENSED_BY",
                    object="nrc",
                    source_artifact=artifact,
                    confidence=0.80,
                    date_occurred=filing_date,
                    raw_text=nrc_mention.group(0)[:200],
                    metadata={"form": form}
                ))

            doe_mention = re.search(
                r"(?:DOE|Department of Energy|ARDP).*?(?:grant|award|funding|contract).*?\$?(\d+(?:\.\d+)?)\s*(?:billion|million)?",
                content, re.IGNORECASE
            )
            if doe_mention:
                facts.append(StructuredFact(
                    fact_type="funding_status",
                    subject=entity_node_id,
                    predicate="FUNDED_BY",
                    object="doe-ne",
                    source_artifact=artifact,
                    confidence=0.80,
                    date_occurred=filing_date,
                    raw_text=doe_mention.group(0)[:200],
                    metadata={"form": form}
                ))

        return facts

    def propose(self, facts: List[StructuredFact]) -> Tuple[List[ProposedClaim], List[ProposedEdge]]:
        """Generate HYPOTHESIS claims and edges from extracted facts."""
        claims = []
        edges = []

        for fact in facts:
            proposal_id = self._generate_proposal_id()

            # Generate claim text
            claim_text = self._generate_claim_text(fact)

            claim = ProposedClaim(
                proposal_id=proposal_id,
                claim_text=claim_text,
                topic=self._fact_type_to_topic(fact.fact_type),
                agent_name=self.name,
                source_url=fact.source_artifact.url,
                artifact_path=fact.source_artifact.local_path,
                artifact_hash=fact.source_artifact.content_hash,
                reasoning=f"Extracted from {fact.source_artifact.metadata.get('source', 'nuclear source')}",
                promotion_requirement=self._get_promotion_requirement(fact.predicate),
            )
            claims.append(claim)

            # Generate edge proposal
            edge_proposal_id = self._generate_proposal_id()

            from_node, to_node = self._resolve_edge_nodes(fact)

            edge = ProposedEdge(
                proposal_id=edge_proposal_id,
                from_node=from_node,
                to_node=to_node,
                relationship=fact.predicate,
                agent_name=self.name,
                detail=claim_text,
                proposed_claim_id=proposal_id,
                confidence=fact.confidence,
                reasoning=f"Nuclear SMR sector - {fact.fact_type}",
                promotion_requirement=self._get_promotion_requirement(fact.predicate),
            )
            edges.append(edge)

        return claims, edges

    def _generate_claim_text(self, fact: StructuredFact) -> str:
        """Generate human-readable claim text."""
        if fact.fact_type == "nrc_licensing":
            milestone = fact.metadata.get("milestone", "licensing")
            return f"{fact.subject} achieved NRC {milestone.replace('_', ' ')} milestone"
        elif fact.fact_type == "doe_funding":
            amount = fact.metadata.get("amount", "")
            return f"{fact.subject} received DoE funding" + (f" (${amount})" if amount else "")
        elif fact.fact_type == "material_event":
            return f"{fact.subject} reported {fact.predicate.lower().replace('_', ' ')}"
        elif fact.fact_type == "regulatory_status":
            return f"{fact.subject} has NRC licensing relationship"
        elif fact.fact_type == "funding_status":
            return f"{fact.subject} has DoE funding relationship"
        else:
            return f"{fact.subject} {fact.predicate} {fact.object}"

    def _fact_type_to_topic(self, fact_type: str) -> str:
        """Map fact type to topic category."""
        mapping = {
            "nrc_licensing": "Nuclear",
            "doe_funding": "Nuclear",
            "material_event": "Nuclear",
            "regulatory_status": "Nuclear",
            "funding_status": "Nuclear",
        }
        return mapping.get(fact_type, "Nuclear")

    def _resolve_edge_nodes(self, fact: StructuredFact) -> Tuple[str, str]:
        """Resolve from_node and to_node for an edge."""
        return fact.subject, fact.object

    def _get_promotion_requirement(self, predicate: str) -> str:
        """Get promotion requirement based on edge type."""
        requirements = {
            "LICENSED_BY": "Verify against NRC ADAMS document database",
            "FUNDED_BY": "Verify against DoE grant announcement",
            "AGREEMENT": "Verify against 8-K filing on SEC.gov",
            "CONSTRUCTION_PERMIT": "Verify against NRC docket",
            "REGULATORY_APPROVAL": "Verify against NRC/DoE official announcement",
            "EXECUTIVE_CHANGE": "Verify against 8-K filing",
        }
        return requirements.get(predicate, "Verify against official source")


# =============================================================================
# STANDALONE EXECUTION
# =============================================================================

def main():
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from fgip.db import FGIPDatabase

    import argparse
    parser = argparse.ArgumentParser(description="Run Nuclear SMR Agent")
    parser.add_argument("db_path", help="Path to FGIP database")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to database")
    args = parser.parse_args()

    db = FGIPDatabase(args.db_path)
    agent = NuclearSMRAgent(db)

    print("="*60)
    print("FGIP NUCLEAR SMR AGENT")
    print("="*60)
    print("\nMonitoring: NRC licensing, DoE grants, EDGAR filings")
    print("Companies: NuScale, Oklo, TerraPower, X-Energy, Kairos, BWXT, Centrus, Constellation")

    if args.dry_run:
        print("\n[DRY RUN - Collecting and extracting only]")
        artifacts = agent.collect()
        print(f"\nArtifacts collected: {len(artifacts)}")
        facts = agent.extract(artifacts)
        print(f"Facts extracted: {len(facts)}")
        for fact in facts[:10]:
            print(f"  - {fact.subject} {fact.predicate} {fact.object}")
    else:
        result = agent.run()
        print(f"\nResults:")
        print(f"  Artifacts collected: {result['artifacts_collected']}")
        print(f"  Facts extracted: {result['facts_extracted']}")
        print(f"  Claims proposed: {result['claims_proposed']}")
        print(f"  Edges proposed: {result['edges_proposed']}")

        if result.get('errors'):
            print(f"\nErrors:")
            for error in result['errors']:
                print(f"  - {error}")


if __name__ == "__main__":
    main()
