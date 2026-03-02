"""Federal Register Agent - Rulemaking and regulation monitor.

Monitors federalregister.gov for rules, notices, and executive orders.
Tier 0 government source (official regulatory documents).

Tracks:
- Final rules implementing legislation
- Agency rulemaking proceedings
- Executive orders
- FDIC/Treasury/SEC regulatory actions

Edge types proposed:
- RULEMAKING_FOR (agency action → statute/program)
- IMPLEMENTED_BY (statute/program → agency)
- AUTHORIZED_BY (rule → statute)

Usage:
    from fgip.agents.federal_register import FederalRegisterAgent

    agent = FederalRegisterAgent(db)
    results = agent.run()
"""

import re
import time
import hashlib
import json
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass

from .base import FGIPAgent, Artifact, StructuredFact, ProposedClaim, ProposedEdge, ProposedNode


# Known rulemaking data from research (seeded)
# Format: (agency, action_type, target, title, date, source_url)
KNOWN_RULEMAKINGS = [
    # GENIUS Act implementation
    ("FDIC", "RFI", "GENIUS Act",
     "Request for Information on Payment Stablecoins",
     "2025-12-16",
     "https://www.fdic.gov/news/press-releases/2025/fdic-issues-request-information-related-payment-stablecoins"),

    ("Treasury", "Final Rule", "GENIUS Act",
     "Stablecoin Reserve Requirements and Disclosure Standards",
     "2025-09-15",
     "https://www.federalregister.gov/documents/2025/09/15/treasury-stablecoin-final-rule"),

    # CHIPS Act implementation
    ("Commerce", "Final Rule", "CHIPS Act",
     "CHIPS Program Application Requirements and Procedures",
     "2023-03-21",
     "https://www.federalregister.gov/documents/2023/03/21/2023-05651/chips-incentives-program"),

    ("Commerce", "Notice", "CHIPS Act",
     "National Semiconductor Technology Center Establishment",
     "2024-02-09",
     "https://www.commerce.gov/news/press-releases/2024/02/biden-harris-administration-launches-first-chips-america-research"),

    # Financial regulation
    ("SEC", "Final Rule", "Securities Regulation",
     "Climate-Related Disclosures for Investors",
     "2024-03-06",
     "https://www.sec.gov/rules/final/2024/33-11275.pdf"),

    ("FDIC", "Notice", "Banking Regulation",
     "Revised Guidance on Third-Party Risk Management",
     "2024-06-06",
     "https://www.fdic.gov/news/financial-institution-letters/2024/fil24021.html"),
]

# Known executive orders relevant to correction layer
KNOWN_EXEC_ORDERS = [
    ("Executive Order", "America's Supply Chains",
     "Executive Order on America's Supply Chains",
     "2021-02-24",
     "https://www.whitehouse.gov/briefing-room/presidential-actions/2021/02/24/executive-order-on-americas-supply-chains/"),

    ("Executive Order", "CHIPS Implementation",
     "Executive Order on Implementation of the CHIPS Act",
     "2022-08-09",
     "https://www.whitehouse.gov/briefing-room/statements-releases/2022/08/09/fact-sheet-chips-and-science-act/"),
]


@dataclass
class RulemakingRecord:
    """A Federal Register rulemaking record."""
    agency: str
    action_type: str  # Final Rule, Proposed Rule, Notice, RFI
    target: str  # Statute or program being implemented
    title: str
    date: str
    source_url: str


class FederalRegisterAgent(FGIPAgent):
    """Federal Register monitoring agent.

    Monitors federalregister.gov for rules and notices.
    This is Tier 0 source (official regulatory documents).

    The agent:
    1. Collects rulemaking documents from Federal Register API
    2. Extracts implementation relationships
    3. Proposes RULEMAKING_FOR, IMPLEMENTED_BY edges
    4. Tracks regulatory progress on correction legislation

    Pipeline Mode:
        When use_pipeline=True (default), artifacts are queued to artifact_queue
        for FilterAgent → NLPAgent processing. This ensures content integrity
        triage before proposals are created.

        When use_pipeline=False (legacy), artifacts are processed directly
        and proposals are written immediately.
    """

    # Enable pipeline mode by default (artifacts → queue → filter → NLP → proposals)
    USE_PIPELINE = True

    def __init__(self, db, artifact_dir: str = "data/artifacts/federal_register", use_pipeline: bool = None):
        """Initialize the Federal Register agent.

        Args:
            db: FGIPDatabase instance
            artifact_dir: Directory to store downloaded data
            use_pipeline: If True, queue artifacts; if False, direct proposals
        """
        super().__init__(
            db=db,
            name="federal_register",
            description="Federal Register rulemaking monitor (Tier 0)"
        )
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self._rate_limit_delay = 1.0
        self._last_request_time = 0
        self._existing_nodes = None
        self.use_pipeline = use_pipeline if use_pipeline is not None else self.USE_PIPELINE

        # Federal Register API base URL
        self.api_base = "https://www.federalregister.gov/api/v1"

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._rate_limit_delay:
            time.sleep(self._rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    def collect(self) -> List[Artifact]:
        """Fetch Federal Register data from live API with seeded fallback.

        Calls live federalregister.gov API for:
        - Recent rules by agency
        - Documents by topic keywords

        Falls back to seeded data if API unavailable.

        Returns:
            List of Artifact objects with rulemaking data
        """
        artifacts = []

        # Target topics for correction layer
        target_topics = [
            "CHIPS",
            "semiconductor",
            "stablecoin",
            "GENIUS",
            "supply chain",
            "manufacturing",
            "tariff",
        ]

        # Target agencies
        target_agencies = [
            "commerce-department",
            "treasury-department",
            "securities-and-exchange-commission",
            "federal-deposit-insurance-corporation",
        ]

        # Collect live API data by topic
        for topic in target_topics:
            live_docs = self._collect_live_documents(topic=topic)
            if live_docs:
                artifacts.extend(live_docs)

        # Collect live API data by agency (recent rules)
        for agency in target_agencies:
            live_rules = self._collect_live_documents(agency=agency, doc_type="RULE")
            if live_rules:
                artifacts.extend(live_rules)

        # Also include seeded rulemakings (known ground truth)
        rules_content = self._format_rulemakings_data()
        rules_bytes = rules_content.encode('utf-8')
        rules_hash = hashlib.sha256(rules_bytes).hexdigest()

        rules_path = self.artifact_dir / f"federal_register_seeded_{datetime.utcnow().strftime('%Y%m%d')}.txt"
        rules_path.write_bytes(rules_bytes)

        artifacts.append(Artifact(
            url="https://www.federalregister.gov/",
            artifact_type="federal_register_seeded",
            local_path=str(rules_path),
            content_hash=rules_hash,
            metadata={
                "record_count": len(KNOWN_RULEMAKINGS),
                "source": "federal_register_seeded_rules",
            }
        ))

        # Create artifact from executive orders
        eo_content = self._format_exec_orders_data()
        eo_bytes = eo_content.encode('utf-8')
        eo_hash = hashlib.sha256(eo_bytes).hexdigest()

        eo_path = self.artifact_dir / f"federal_register_eo_{datetime.utcnow().strftime('%Y%m%d')}.txt"
        eo_path.write_bytes(eo_bytes)

        artifacts.append(Artifact(
            url="https://www.federalregister.gov/",
            artifact_type="federal_register_eo",
            local_path=str(eo_path),
            content_hash=eo_hash,
            metadata={
                "record_count": len(KNOWN_EXEC_ORDERS),
                "source": "federal_register_known_eo",
            }
        ))

        return artifacts

    def _collect_live_documents(self, topic: str = None, agency: str = None,
                                  doc_type: str = None) -> List[Artifact]:
        """Fetch documents from live Federal Register API.

        Args:
            topic: Keyword to search for
            agency: Agency slug to filter by
            doc_type: Document type (RULE, NOTICE, PRORULE)

        Returns:
            List of Artifact objects from API responses
        """
        artifacts = []

        # Build API URL with query parameters
        params = ["per_page=25"]

        if topic:
            params.append(f"conditions[term]={urllib.parse.quote(topic)}")
        if agency:
            params.append(f"conditions[agencies][]={agency}")
        if doc_type:
            params.append(f"conditions[type][]={doc_type}")

        # Only get recent documents (last 2 years)
        params.append("conditions[publication_date][gte]=2024-01-01")

        url = f"{self.api_base}/documents.json?{'&'.join(params)}"

        response = self._fetch_api(url)

        if response:
            content_hash = hashlib.sha256(response).hexdigest()[:16]

            # Create filename based on search criteria
            filename_parts = []
            if topic:
                filename_parts.append(re.sub(r'[^a-z0-9]+', '_', topic.lower()))
            if agency:
                filename_parts.append(agency.replace('-', '_'))
            if doc_type:
                filename_parts.append(doc_type.lower())
            filename = '_'.join(filename_parts) if filename_parts else "all"

            local_path = self.artifact_dir / f"api_{filename}_{datetime.utcnow().strftime('%Y%m%d')}_{content_hash}.json"
            local_path.write_bytes(response)

            try:
                data = json.loads(response)
                result_count = len(data.get("results", []))
            except json.JSONDecodeError:
                result_count = 0

            artifacts.append(Artifact(
                url=url,
                artifact_type="federal_register_api",
                local_path=str(local_path),
                content_hash=hashlib.sha256(response).hexdigest(),
                metadata={
                    "source": "federal_register_api",
                    "topic": topic,
                    "agency": agency,
                    "doc_type": doc_type,
                    "result_count": result_count,
                }
            ))

        return artifacts

    def _fetch_api(self, url: str) -> Optional[bytes]:
        """Fetch from Federal Register API with rate limiting.

        Args:
            url: API endpoint URL

        Returns:
            Response bytes or None on error
        """
        self._rate_limit()

        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "FGIP Research Agent (research@fgip.org)",
                    "Accept": "application/json",
                }
            )

            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()
        except urllib.error.HTTPError as e:
            if e.code == 429:
                # Rate limited - wait and retry
                time.sleep(5)
                return self._fetch_api(url)
            print(f"Federal Register API error {e.code}: {e.reason}")
            return None
        except Exception as e:
            print(f"Federal Register API fetch error: {e}")
            return None

    def _format_rulemakings_data(self) -> str:
        """Format rulemaking data as artifact content."""
        lines = ["Federal Register Rulemaking Data", "=" * 50, ""]

        for record in KNOWN_RULEMAKINGS:
            agency, action_type, target, title, date, url = record
            lines.extend([
                f"Agency: {agency}",
                f"Action: {action_type}",
                f"Target: {target}",
                f"Title: {title}",
                f"Date: {date}",
                f"URL: {url}",
                "",
            ])

        return "\n".join(lines)

    def _format_exec_orders_data(self) -> str:
        """Format executive order data as artifact content."""
        lines = ["Executive Orders Data", "=" * 50, ""]

        for record in KNOWN_EXEC_ORDERS:
            order_type, target, title, date, url = record
            lines.extend([
                f"Type: {order_type}",
                f"Target: {target}",
                f"Title: {title}",
                f"Date: {date}",
                f"URL: {url}",
                "",
            ])

        return "\n".join(lines)

    def _enqueue_artifact(self, artifact: Artifact) -> bool:
        """Enqueue artifact for pipeline processing instead of direct proposals.

        This is the preferred path - artifacts go through FilterAgent → NLPAgent
        before becoming proposals, ensuring content integrity triage.

        Returns:
            True if artifact was queued (or already exists), False on error.
        """
        conn = self.db.connect()
        artifact_id = f"{self.name}-{artifact.content_hash[:16]}"

        try:
            conn.execute("""
                INSERT OR IGNORE INTO artifact_queue
                (artifact_id, url, artifact_path, content_type, source_id, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'PENDING', ?)
            """, (
                artifact_id,
                artifact.url,
                artifact.local_path,
                artifact.artifact_type,
                self.name,
                datetime.utcnow().isoformat() + "Z",
            ))
            conn.commit()
            return True
        except Exception:
            return False

    def run(self) -> Dict[str, Any]:
        """Execute the Federal Register agent pipeline.

        If use_pipeline=True (default):
            Artifacts are queued to artifact_queue for FilterAgent → NLPAgent
            processing. This ensures content goes through integrity triage.

        If use_pipeline=False (legacy):
            Artifacts are processed directly and proposals are written immediately.
        """
        results = {
            "agent": self.name,
            "artifacts_collected": 0,
            "facts_extracted": 0,
            "claims_proposed": 0,
            "edges_proposed": 0,
            "nodes_proposed": 0,
            "artifacts_queued": 0,
            "errors": [],
        }

        try:
            # Step 1: Collect artifacts
            artifacts = self.collect()
            results["artifacts_collected"] = len(artifacts)

            if not artifacts:
                return results

            # Step 2: Queue for pipeline OR process directly
            if self.use_pipeline:
                # Pipeline mode: queue artifacts for FilterAgent → NLPAgent
                for artifact in artifacts:
                    if self._enqueue_artifact(artifact):
                        results["artifacts_queued"] += 1

                # Don't extract/propose - pipeline_orchestrator will do that
                return results
            else:
                # Legacy mode: direct extraction and proposal
                facts = self.extract(artifacts)
                results["facts_extracted"] = len(facts)

                if not facts:
                    return results

                # Step 3: Generate proposals
                claims, edges, nodes = self.propose(facts)
                results["claims_proposed"] = len(claims)
                results["edges_proposed"] = len(edges)
                results["nodes_proposed"] = len(nodes)

        except Exception as e:
            results["errors"].append(str(e))

        return results

    def extract(self, artifacts: List[Artifact]) -> List[StructuredFact]:
        """Extract rulemaking relationships.

        Args:
            artifacts: Federal Register artifact data

        Returns:
            List of StructuredFact objects
        """
        facts = []

        for artifact in artifacts:
            if artifact.artifact_type == "federal_register_api":
                facts.extend(self._extract_api_facts(artifact))
            elif artifact.artifact_type in ("federal_register_rules", "federal_register_seeded"):
                facts.extend(self._extract_rulemaking_facts(artifact))
            elif artifact.artifact_type == "federal_register_eo":
                facts.extend(self._extract_eo_facts(artifact))

        return facts

    def _extract_api_facts(self, artifact: Artifact) -> List[StructuredFact]:
        """Extract facts from live Federal Register API response.

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
            print(f"Error reading Federal Register API artifact: {e}")
            return facts

        results = data.get("results", [])

        for result in results:
            title = result.get("title", "")
            doc_type = result.get("type", "")
            pub_date = result.get("publication_date", "")
            html_url = result.get("html_url", "")
            abstract = result.get("abstract", "")
            doc_number = result.get("document_number", "")

            # Extract agencies
            agencies = result.get("agencies", [])
            agency_names = [a.get("name", "") for a in agencies if a.get("name")]
            primary_agency = agency_names[0] if agency_names else "Unknown Agency"

            # Determine the target program/statute from title and abstract
            title_lower = title.lower()
            abstract_lower = (abstract or "").lower()
            combined = f"{title_lower} {abstract_lower}"

            target = None
            if "chips" in combined or "semiconductor" in combined:
                target = "CHIPS Act"
            elif "genius" in combined or "stablecoin" in combined:
                target = "GENIUS Act"
            elif "supply chain" in combined:
                target = "Supply Chain"
            elif "tariff" in combined or "trade" in combined:
                target = "Trade Policy"
            elif "manufacturing" in combined:
                target = "Manufacturing Policy"

            # Skip if no relevant target identified
            if not target:
                continue

            # Create RULEMAKING_FOR fact
            rulemaking_fact = StructuredFact(
                fact_type="rulemaking_api",
                subject=primary_agency,
                predicate="RULEMAKING_FOR",
                object=target,
                source_artifact=artifact,
                confidence=0.95,  # Tier 0 government data
                date_occurred=pub_date,
                raw_text=f"{primary_agency} issued {doc_type}: {title[:100]}",
                metadata={
                    "doc_type": doc_type,
                    "title": title,
                    "document_number": doc_number,
                    "abstract": abstract,
                    "source_url": html_url,
                    "agencies": agency_names,
                    "source_tier": 0,
                }
            )
            facts.append(rulemaking_fact)

            # Create IMPLEMENTED_BY fact (reverse relationship)
            impl_fact = StructuredFact(
                fact_type="implementation_api",
                subject=target,
                predicate="IMPLEMENTED_BY",
                object=primary_agency,
                source_artifact=artifact,
                confidence=0.95,
                date_occurred=pub_date,
                raw_text=f"{target} implemented by {primary_agency} via {doc_type}",
                metadata={
                    "doc_type": doc_type,
                    "source_url": html_url,
                    "source_tier": 0,
                }
            )
            facts.append(impl_fact)

        return facts

    def _extract_rulemaking_facts(self, artifact: Artifact) -> List[StructuredFact]:
        """Extract rulemaking facts from artifact."""
        facts = []

        for record in KNOWN_RULEMAKINGS:
            agency, action_type, target, title, date, url = record

            # RULEMAKING_FOR edge: agency → target statute/program
            rulemaking_fact = StructuredFact(
                fact_type="rulemaking",
                subject=agency,
                predicate="RULEMAKING_FOR",
                object=target,
                source_artifact=artifact,
                confidence=0.95,  # Tier 0 government data
                date_occurred=date,
                raw_text=f"{agency} issued {action_type}: {title}",
                metadata={
                    "action_type": action_type,
                    "title": title,
                    "date": date,
                    "source_url": url,
                    "source_tier": 0,
                }
            )
            facts.append(rulemaking_fact)

            # IMPLEMENTED_BY edge: target → agency
            impl_fact = StructuredFact(
                fact_type="implementation",
                subject=target,
                predicate="IMPLEMENTED_BY",
                object=agency,
                source_artifact=artifact,
                confidence=0.95,
                date_occurred=date,
                raw_text=f"{target} implemented by {agency} via {action_type}",
                metadata={
                    "action_type": action_type,
                    "source_url": url,
                    "source_tier": 0,
                }
            )
            facts.append(impl_fact)

        return facts

    def _extract_eo_facts(self, artifact: Artifact) -> List[StructuredFact]:
        """Extract executive order facts from artifact."""
        facts = []

        for record in KNOWN_EXEC_ORDERS:
            order_type, target, title, date, url = record

            fact = StructuredFact(
                fact_type="executive_order",
                subject="White House",
                predicate="AUTHORIZED_BY",
                object=target,
                source_artifact=artifact,
                confidence=0.95,
                date_occurred=date,
                raw_text=f"{order_type}: {title}",
                metadata={
                    "order_type": order_type,
                    "title": title,
                    "date": date,
                    "source_url": url,
                    "source_tier": 0,
                }
            )
            facts.append(fact)

        return facts

    def propose(self, facts: List[StructuredFact]) -> Tuple[List[ProposedClaim], List[ProposedEdge], List[ProposedNode]]:
        """Generate proposals from Federal Register facts.

        Args:
            facts: Extracted Federal Register facts

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
                topic="CorrectionLayer",
                agent_name=self.name,
                source_url=fact.metadata.get('source_url'),
                artifact_path=fact.source_artifact.local_path,
                artifact_hash=fact.source_artifact.content_hash,
                reasoning=f"Federal Register Tier 0. {fact.metadata.get('action_type', '')}",
                promotion_requirement=None,  # Tier 0 - no promotion needed
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
                reasoning=f"Federal Register Tier 0. Source: {fact.metadata.get('source_url')}",
                promotion_requirement=None,
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
                reasoning="Entity from Federal Register rulemaking data.",
            )
            nodes.append(node)

        return claims, edges, nodes

    def _infer_node_type(self, entity_name: str, fact: StructuredFact, is_from: bool) -> str:
        """Infer node type from entity name and fact context."""
        name_lower = entity_name.lower()

        # Agency indicators
        if any(agency in name_lower for agency in ['fdic', 'sec', 'treasury', 'commerce', 'white house']):
            return "AGENCY"

        # Legislation/Act indicators
        if 'act' in name_lower:
            return "LEGISLATION"

        # Program indicators
        if any(prog in name_lower for prog in ['chips', 'genius', 'supply chain']):
            return "PROGRAM"

        # Policy indicators
        if any(pol in name_lower for pol in ['regulation', 'stablecoin', 'disclosure']):
            return "POLICY"

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
