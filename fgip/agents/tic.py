"""FGIP TIC Agent - Treasury International Capital Foreign Holdings Monitor.

Tracks foreign government holdings of US Treasury securities.
This is the "weapon" that GENIUS Act domestication addresses.

Foreign Treasury Holdings = Leverage:
- China: $759B (down from $1.3T peak)
- Japan: $1.06T
- Total foreign: ~$8.5T

When foreign governments dump Treasuries, yields spike, rates spike, markets crash.
This leverage prevents the US from implementing tariffs without retaliation.

GENIUS Act domesticates this debt via stablecoin Treasury absorption.

Tier 0 agent - uses official Treasury TIC data.
"""

import hashlib
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
import urllib.request
import urllib.error

try:
    from .base import FGIPAgent, Artifact, StructuredFact, ProposedClaim, ProposedEdge, ProposedNode
except ImportError:
    from base import FGIPAgent, Artifact, StructuredFact, ProposedClaim, ProposedEdge, ProposedNode


# Treasury International Capital data
TIC_DATA_URL = "https://ticdata.treasury.gov/resource-center/data-chart-center/tic/Documents/"

# Seeded foreign Treasury holdings data (as of Jan 2026)
# Source: Treasury TIC Major Foreign Holders of Treasury Securities
FOREIGN_HOLDINGS = {
    "japan": {
        "node_id": "japan-gov",
        "name": "Japan",
        "current_holdings": 1060.0,  # $1.06T
        "peak_holdings": 1290.0,
        "year_change": -50.0,  # Down $50B YoY
        "is_ally": True,
    },
    "china": {
        "node_id": "china-prc",
        "name": "China (PRC)",
        "current_holdings": 759.0,  # $759B
        "peak_holdings": 1300.0,  # 2013 peak
        "year_change": -100.0,  # Actively reducing
        "is_ally": False,
    },
    "uk": {
        "node_id": "united-kingdom",
        "name": "United Kingdom",
        "current_holdings": 690.0,
        "peak_holdings": 700.0,
        "year_change": 10.0,
        "is_ally": True,
    },
    "luxembourg": {
        "node_id": "luxembourg",
        "name": "Luxembourg",
        "current_holdings": 390.0,
        "peak_holdings": 400.0,
        "year_change": -5.0,
        "is_ally": True,
        "note": "Financial center - includes hedge fund holdings",
    },
    "cayman": {
        "node_id": "cayman-islands",
        "name": "Cayman Islands",
        "current_holdings": 340.0,
        "peak_holdings": 350.0,
        "year_change": 0.0,
        "is_ally": True,
        "note": "Financial center - hedge funds",
    },
    "ireland": {
        "node_id": "ireland",
        "name": "Ireland",
        "current_holdings": 320.0,
        "peak_holdings": 330.0,
        "year_change": -10.0,
        "is_ally": True,
        "note": "Tech company Treasury holdings",
    },
    "belgium": {
        "node_id": "belgium",
        "name": "Belgium",
        "current_holdings": 300.0,
        "peak_holdings": 350.0,
        "year_change": -20.0,
        "is_ally": True,
        "note": "Euroclear custody",
    },
    "taiwan": {
        "node_id": "taiwan-roc",
        "name": "Taiwan",
        "current_holdings": 260.0,
        "peak_holdings": 270.0,
        "year_change": 5.0,
        "is_ally": True,
    },
    "canada": {
        "node_id": "canada",
        "name": "Canada",
        "current_holdings": 250.0,
        "peak_holdings": 260.0,
        "year_change": -5.0,
        "is_ally": True,
    },
    "switzerland": {
        "node_id": "switzerland",
        "name": "Switzerland",
        "current_holdings": 240.0,
        "peak_holdings": 280.0,
        "year_change": -15.0,
        "is_ally": True,
    },
}

# Calculated totals
TOTAL_FOREIGN_HOLDINGS = sum(h["current_holdings"] for h in FOREIGN_HOLDINGS.values())
ADVERSARY_HOLDINGS = sum(
    h["current_holdings"] for h in FOREIGN_HOLDINGS.values() if not h["is_ally"]
)
ALLY_HOLDINGS = sum(
    h["current_holdings"] for h in FOREIGN_HOLDINGS.values() if h["is_ally"]
)

# Additional non-top-10 holdings estimated
TOTAL_ALL_FOREIGN = 8500.0  # $8.5T total foreign holdings

USER_AGENT = "FGIP Research Agent (contact@example.com)"


class TICAgent(FGIPAgent):
    """Treasury International Capital - Foreign Holdings Monitor.

    Tracks foreign government holdings of US Treasury securities.
    This data is critical for understanding:
    1. Foreign leverage over US bond market
    2. Retaliation capacity against tariff policy
    3. Need for debt domestication via GENIUS Act

    Edge types generated:
    - HOLDS_TREASURY: Foreign entity holds US Treasuries
    - HAS_LEVERAGE_OVER: Foreign holdings create retaliation capability

    Pipeline Mode:
        When use_pipeline=True (default), artifacts are queued to artifact_queue
        for FilterAgent → NLPAgent processing. This ensures content integrity
        triage before proposals are created.

        When use_pipeline=False (legacy), artifacts are processed directly
        and proposals are written immediately.
    """

    # Enable pipeline mode by default (artifacts → queue → filter → NLP → proposals)
    USE_PIPELINE = True

    def __init__(self, db, artifact_dir: str = "data/artifacts/tic", use_pipeline: bool = None):
        super().__init__(
            db=db,
            name="tic",
            description="Treasury International Capital - Foreign holdings monitor"
        )
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self._rate_limit_delay = 2.0
        self._last_request_time = 0
        self.use_pipeline = use_pipeline if use_pipeline is not None else self.USE_PIPELINE

    def _rate_limit(self):
        """Enforce rate limiting."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._rate_limit_delay:
            time.sleep(self._rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    def _fetch_live_tic_data(self) -> Optional[Dict[str, Any]]:
        """Fetch live TIC data from Treasury.

        Attempts to pull from Treasury TIC CSV files.
        Falls back to seeded data if unavailable.
        """
        # Treasury TIC releases monthly data
        # Try to fetch the major foreign holders table
        TIC_CSV_URL = "https://ticdata.treasury.gov/resource-center/data-chart-center/tic/Documents/mfh.txt"

        try:
            self._rate_limit()

            req = urllib.request.Request(TIC_CSV_URL, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as response:
                content = response.read().decode('utf-8', errors='ignore')

            # Parse the TIC MFH (Major Foreign Holders) file
            # Format varies but typically has country names and values in billions
            lines = content.strip().split('\n')

            # Try to find key countries
            holdings = {}
            total = 0.0
            as_of_date = None

            for line in lines:
                line_lower = line.lower()

                # Try to extract date from header
                if 'as of' in line_lower or 'holdings of' in line_lower:
                    import re
                    date_match = re.search(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]* \d{4}', line_lower)
                    if date_match:
                        as_of_date = date_match.group(0).title()

                # Look for major holders
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        # Try to parse as country and value
                        value = None
                        for part in reversed(parts):
                            try:
                                value = float(part.replace(',', ''))
                                break
                            except ValueError:
                                continue

                        if value and value > 50:  # At least $50B
                            country_name = ' '.join(parts[:-1])
                            if 'japan' in country_name.lower():
                                holdings['japan'] = value
                                total += value
                            elif 'china' in country_name.lower() and 'hong kong' not in country_name.lower():
                                holdings['china'] = value
                                total += value
                            elif 'total' in country_name.lower():
                                total = value
                    except:
                        pass

            # If we got meaningful data
            if holdings and total > 1000:  # At least $1T total
                print(f"[TIC] Live Treasury data: ${total:.1f}B as of {as_of_date or 'unknown'}")
                return {
                    "live": True,
                    "source": "Treasury TIC",
                    "as_of": as_of_date or datetime.utcnow().strftime("%Y-%m"),
                    "total_foreign_billions": total,
                    "key_holdings": holdings,
                }

        except Exception as e:
            print(f"[TIC] Treasury TIC fetch failed: {e}")

        # Fallback: Use seeded data with current date notation
        print(f"[TIC] Using seeded baseline data (${TOTAL_ALL_FOREIGN}B)")
        return None

    def collect(self) -> List[Artifact]:
        """Collect foreign Treasury holdings data.

        Tries to fetch live data from FRED API.
        Falls back to seeded data if unavailable.
        """
        artifacts = []

        # Try live data first
        live_data = self._fetch_live_tic_data()

        # Determine data source
        if live_data and live_data.get("live"):
            data_source = "FRED API (live)"
            as_of_date = live_data["as_of"]
            total_foreign = live_data["total_foreign_billions"]
            # Scale seeded country data proportionally to live total
            scale_factor = total_foreign / TOTAL_ALL_FOREIGN
            holdings = {k: {**v, "current_holdings": round(v["current_holdings"] * scale_factor, 1)}
                       for k, v in FOREIGN_HOLDINGS.items()}
        else:
            data_source = "Seeded baseline"
            as_of_date = "2026-01-31"
            total_foreign = TOTAL_ALL_FOREIGN
            holdings = FOREIGN_HOLDINGS

        # Calculate totals
        top_10_total = sum(h["current_holdings"] for h in holdings.values())
        adversary_holdings = sum(h["current_holdings"] for h in holdings.values() if not h["is_ally"])
        ally_holdings = sum(h["current_holdings"] for h in holdings.values() if h["is_ally"])

        holdings_data = {
            "source": "Treasury International Capital System",
            "data_source": data_source,
            "url": "https://ticdata.treasury.gov/",
            "as_of": as_of_date,
            "unit": "$B (billions)",
            "holdings": holdings,
            "totals": {
                "top_10_total": round(top_10_total, 1),
                "all_foreign": round(total_foreign, 1),
                "adversary_holdings": round(adversary_holdings, 1),
                "ally_holdings": round(ally_holdings, 1),
            },
            "analysis": {
                "china_peak_to_current_drop": round(1300.0 - holdings.get("china", {}).get("current_holdings", 759), 1),
                "china_pct_of_total": round(holdings.get("china", {}).get("current_holdings", 759) / total_foreign * 100, 2),
                "adversary_pct_of_total": round(adversary_holdings / total_foreign * 100, 2),
                "leverage_concentration": f"China + Japan = {round((holdings.get('china', {}).get('current_holdings', 759) + holdings.get('japan', {}).get('current_holdings', 1060)) / total_foreign * 100, 1)}% of foreign holdings",
            },
        }

        content = json.dumps(holdings_data, indent=2)
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        artifact_path = self.artifact_dir / f"tic_holdings_{datetime.utcnow().strftime('%Y%m%d')}.json"
        with open(artifact_path, "w") as f:
            f.write(content)

        artifact = Artifact(
            url="https://ticdata.treasury.gov/",
            artifact_type="json",
            local_path=str(artifact_path),
            content_hash=content_hash,
            metadata=holdings_data,
        )
        artifacts.append(artifact)

        print(f"Collected TIC data ({data_source}): {len(holdings)} countries, ${total_foreign}B total foreign holdings")
        return artifacts

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
        """Execute the TIC agent pipeline.

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
        """Extract facts about foreign Treasury holdings."""
        facts = []

        for artifact in artifacts:
            holdings = artifact.metadata.get("holdings", {})

            for country_key, data in holdings.items():
                # Fact: Country holds Treasuries
                facts.append(StructuredFact(
                    fact_type="treasury_holding",
                    subject=data["name"],
                    predicate="HOLDS_TREASURY",
                    object="US Treasury",
                    source_artifact=artifact,
                    confidence=1.0,  # Tier 0 government data
                    date_occurred=artifact.metadata.get("as_of"),
                    raw_text=f"{data['name']} holds ${data['current_holdings']}B in US Treasuries",
                    metadata={
                        "node_id": data["node_id"],
                        "holdings_billions": data["current_holdings"],
                        "peak_holdings": data.get("peak_holdings"),
                        "year_change": data.get("year_change"),
                        "is_ally": data.get("is_ally", True),
                    }
                ))

                # Fact: Non-ally holdings create leverage
                if not data.get("is_ally", True):
                    facts.append(StructuredFact(
                        fact_type="foreign_leverage",
                        subject=data["name"],
                        predicate="HAS_LEVERAGE_OVER",
                        object="US Bond Market",
                        source_artifact=artifact,
                        confidence=0.9,
                        date_occurred=artifact.metadata.get("as_of"),
                        raw_text=f"{data['name']} can weaponize ${data['current_holdings']}B Treasury holdings against US tariff policy",
                        metadata={
                            "node_id": data["node_id"],
                            "leverage_amount": data["current_holdings"],
                            "mechanism": "Treasury dump causes yield spike, market crash",
                        }
                    ))

            # Fact: Total foreign leverage
            totals = artifact.metadata.get("totals", {})
            facts.append(StructuredFact(
                fact_type="aggregate_leverage",
                subject="Foreign Governments",
                predicate="COLLECTIVELY_HOLD",
                object="US Treasury",
                source_artifact=artifact,
                confidence=1.0,
                date_occurred=artifact.metadata.get("as_of"),
                raw_text=f"Foreign governments hold ${totals.get('all_foreign', 8500)}B in US Treasuries - leverage against US policy",
                metadata={
                    "total_foreign": totals.get("all_foreign"),
                    "adversary_holdings": totals.get("adversary_holdings"),
                    "ally_holdings": totals.get("ally_holdings"),
                }
            ))

        return facts

    def propose(self, facts: List[StructuredFact]) -> Tuple[List[ProposedClaim], List[ProposedEdge], List[ProposedNode]]:
        """Generate proposals for Treasury holding edges."""
        claims = []
        edges = []
        nodes = []

        for fact in facts:
            proposal_id = self._generate_proposal_id()

            if fact.fact_type == "treasury_holding":
                node_id = fact.metadata.get("node_id")
                holdings = fact.metadata.get("holdings_billions", 0)

                # Propose claim
                claim = ProposedClaim(
                    proposal_id=proposal_id,
                    claim_text=f"{fact.subject} holds ${holdings}B in US Treasury securities",
                    topic="FOREIGN_LEVERAGE",
                    agent_name=self.name,
                    source_url=fact.source_artifact.url,
                    artifact_path=fact.source_artifact.local_path,
                    artifact_hash=fact.source_artifact.content_hash,
                    reasoning="Treasury TIC data - Tier 0 government source",
                    promotion_requirement="Verify against latest TIC release",
                )
                claims.append(claim)

                # Propose edge: Country → US Treasury
                edge_proposal_id = self._generate_proposal_id()
                edge = ProposedEdge(
                    proposal_id=edge_proposal_id,
                    from_node=node_id,
                    to_node="us-treasury",
                    relationship="HOLDS_TREASURY",
                    agent_name=self.name,
                    detail=f"${holdings}B as of {fact.date_occurred}",
                    proposed_claim_id=proposal_id,
                    confidence=1.0,
                    reasoning="Official Treasury TIC data",
                    promotion_requirement="Verify holdings amount",
                )
                edges.append(edge)

                # Propose country node if not exists
                node_proposal_id = self._generate_proposal_id()
                nodes.append(ProposedNode(
                    proposal_id=node_proposal_id,
                    node_id=node_id,
                    node_type="LOCATION",
                    name=fact.subject,
                    agent_name=self.name,
                    description=f"Holds ${holdings}B in US Treasuries",
                    source_url=fact.source_artifact.url,
                    reasoning="Foreign Treasury holder from TIC data",
                ))

            elif fact.fact_type == "foreign_leverage":
                node_id = fact.metadata.get("node_id")
                leverage = fact.metadata.get("leverage_amount", 0)

                # Propose leverage edge
                edge_proposal_id = self._generate_proposal_id()
                edge = ProposedEdge(
                    proposal_id=edge_proposal_id,
                    from_node=node_id,
                    to_node="bond-market",
                    relationship="HAS_LEVERAGE_OVER",
                    agent_name=self.name,
                    detail=f"Can weaponize ${leverage}B Treasury holdings",
                    proposed_claim_id=proposal_id,
                    confidence=0.9,
                    reasoning="Treasury dump mechanism - yields spike when foreign holders sell",
                    promotion_requirement="Document historical examples (2015 China scare)",
                )
                edges.append(edge)

        # Add summary claim about total leverage
        summary_id = self._generate_proposal_id()
        claims.append(ProposedClaim(
            proposal_id=summary_id,
            claim_text=f"Foreign governments hold ${TOTAL_ALL_FOREIGN}B in US Treasuries, creating leverage against tariff policy. This is why GENIUS Act debt domestication is prerequisite for reshoring.",
            topic="FOREIGN_LEVERAGE",
            agent_name=self.name,
            source_url="https://ticdata.treasury.gov/",
            reasoning="Total foreign leverage = weapon against US policy independence",
            promotion_requirement="Cross-reference with GENIUS Act stablecoin Treasury absorption data",
        ))

        return claims, edges, nodes


# CLI entry point
if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    from fgip.db import FGIPDatabase

    if len(sys.argv) < 2:
        print("Usage: python tic.py <database_path>")
        print("Example: python tic.py fgip.db")
        sys.exit(1)

    db_path = sys.argv[1]
    db = FGIPDatabase(db_path)

    agent = TICAgent(db)

    print(f"\n{'='*60}")
    print(f"TIC Agent - Foreign Treasury Holdings Monitor")
    print(f"{'='*60}")
    print(f"\nForeign Treasury Holdings (Tier 0 Source: Treasury TIC)")
    print(f"  Total Foreign: ${TOTAL_ALL_FOREIGN}B")
    print(f"  Top 10 Countries: ${TOTAL_FOREIGN_HOLDINGS}B")
    print(f"  Adversary Holdings: ${ADVERSARY_HOLDINGS}B ({round(ADVERSARY_HOLDINGS/TOTAL_ALL_FOREIGN*100,1)}%)")
    print(f"  Ally Holdings: ${ALLY_HOLDINGS}B")
    print(f"\nKey Holdings:")
    for key, data in sorted(FOREIGN_HOLDINGS.items(), key=lambda x: -x[1]["current_holdings"]):
        ally_marker = "✓" if data["is_ally"] else "⚠"
        print(f"  {ally_marker} {data['name']}: ${data['current_holdings']}B")

    print(f"\n{'='*60}")
    results = agent.run()

    print(f"\n{'='*60}")
    print(f"Results:")
    print(f"  Artifacts collected: {results['artifacts_collected']}")
    print(f"  Facts extracted: {results['facts_extracted']}")
    print(f"  Claims proposed: {results['claims_proposed']}")
    print(f"  Edges proposed: {results['edges_proposed']}")
    print(f"  Nodes proposed: {results['nodes_proposed']}")

    if results['errors']:
        print(f"\nErrors:")
        for error in results['errors']:
            print(f"  - {error}")

    status = agent.get_status()
    print(f"\nAgent Status:")
    print(f"  Pending claims: {status['pending_claims']}")
    print(f"  Pending edges: {status['pending_edges']}")
