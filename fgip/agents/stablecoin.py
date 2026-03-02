"""FGIP Stablecoin Agent - Treasury Absorption & Debt Domestication Monitor.

Tracks stablecoin market and Treasury backing for debt domestication thesis.

GENIUS Act Mechanics:
- Stablecoins must be backed 1:1 by Treasuries or cash
- Holders earn ZERO yield (by law)
- Issuers hold Treasuries earning 4-5%, keep the spread
- Treasury projects $2T stablecoin market by 2028

Why This Matters:
- $2T in stablecoin Treasuries = $2T in domestic holders with ZERO leverage
- Each $1 domesticated = $1 less foreign leverage capacity
- This is the prerequisite for tariff policy without bond market retaliation

The mechanism:
  Foreign holders can dump → yields spike → rates spike → crash
  Stablecoin holders CANNOT dump → stable demand → no leverage
  = Hamilton's funding act in digital form

Tier 1 agent - uses stablecoin attestations and market data.
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


# GENIUS Act parameters (signed July 18, 2025)
GENIUS_ACT = {
    "signed_date": "2025-07-18",
    "senate_vote": "68-30",
    "house_vote": "308-122",
    "holder_yield": 0.0,  # Zero by law
    "issuer_yield": 4.5,  # Treasury rate captured by issuer
    "reserve_requirement": 1.0,  # 100% backing required
    "projected_market_2028": 2000.0,  # $2T Treasury projection
}

# Stablecoin issuer data (as of Feb 2026)
STABLECOIN_ISSUERS = {
    "tether": {
        "node_id": "tether-usdt",
        "name": "Tether (USDT)",
        "market_cap": 120.0,  # $120B
        "treasury_pct": 0.60,  # 60% in Treasuries
        "treasury_holdings": 72.0,  # $72B
        "headquarters": "British Virgin Islands",
        "genius_compliant": False,  # Pre-GENIUS, grandfathered
    },
    "circle": {
        "node_id": "circle-usdc",
        "name": "Circle (USDC)",
        "market_cap": 45.0,  # $45B
        "treasury_pct": 0.80,  # 80% in Treasuries
        "treasury_holdings": 36.0,  # $36B
        "headquarters": "United States",
        "genius_compliant": True,
    },
    "paxos": {
        "node_id": "paxos-usdp",
        "name": "Paxos (USDP)",
        "market_cap": 5.0,  # $5B
        "treasury_pct": 0.95,  # 95% in Treasuries
        "treasury_holdings": 4.75,
        "headquarters": "United States",
        "genius_compliant": True,
    },
    "paypal": {
        "node_id": "paypal-pyusd",
        "name": "PayPal (PYUSD)",
        "market_cap": 2.0,  # $2B
        "treasury_pct": 0.90,
        "treasury_holdings": 1.8,
        "headquarters": "United States",
        "genius_compliant": True,
    },
    "gemini": {
        "node_id": "gemini-gusd",
        "name": "Gemini (GUSD)",
        "market_cap": 0.5,
        "treasury_pct": 0.95,
        "treasury_holdings": 0.475,
        "headquarters": "United States",
        "genius_compliant": True,
    },
}

# Calculate totals
TOTAL_STABLECOIN_MARKET = sum(s["market_cap"] for s in STABLECOIN_ISSUERS.values())
TOTAL_TREASURY_HOLDINGS = sum(s["treasury_holdings"] for s in STABLECOIN_ISSUERS.values())
GENIUS_COMPLIANT_HOLDINGS = sum(
    s["treasury_holdings"] for s in STABLECOIN_ISSUERS.values() if s["genius_compliant"]
)

# Foreign holdings for comparison (from TIC agent)
FOREIGN_TREASURY_HOLDINGS = 8500.0  # $8.5T

USER_AGENT = "FGIP Research Agent (contact@example.com)"

# Debt domestication metrics
DEBT_DOMESTICATION_PCT = round(TOTAL_TREASURY_HOLDINGS / FOREIGN_TREASURY_HOLDINGS * 100, 2)
PROJECTED_DOMESTICATION_2028 = round(GENIUS_ACT["projected_market_2028"] / FOREIGN_TREASURY_HOLDINGS * 100, 2)

USER_AGENT = "FGIP Research Agent (contact@example.com)"


class StablecoinAgent(FGIPAgent):
    """Stablecoin Treasury Absorption Monitor.

    Tracks stablecoin market for debt domestication thesis:
    1. Current stablecoin Treasury holdings
    2. Debt domestication percentage
    3. Foreign leverage reduction
    4. GENIUS Act compliance status

    Key insight: Stablecoins are Hamilton's funding act in digital form.
    They domesticate Treasury debt, removing foreign leverage.

    Edge types generated:
    - HOLDS_TREASURY: Stablecoin issuer holds Treasuries
    - DOMESTICATES: Stablecoin reduces foreign debt dependency
    - REDUCES: Stablecoin absorption reduces foreign leverage
    - COMPLIES_WITH: Issuer complies with GENIUS Act
    """

    def __init__(self, db, artifact_dir: str = "data/artifacts/stablecoin"):
        super().__init__(
            db=db,
            name="stablecoin",
            description="Stablecoin Treasury absorption - debt domestication monitor"
        )
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self._rate_limit_delay = 1.0
        self._last_request_time = 0

    def _rate_limit(self):
        """Enforce rate limiting."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._rate_limit_delay:
            time.sleep(self._rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    def _fetch_live_stablecoin_data(self) -> Optional[Dict[str, Any]]:
        """Fetch live stablecoin data from DeFi Llama API."""
        DEFILLAMA_API = "https://stablecoins.llama.fi/stablecoins?includePrices=true"

        try:
            self._rate_limit()
            req = urllib.request.Request(DEFILLAMA_API, headers={"User-Agent": USER_AGENT})

            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode('utf-8'))

            # Parse stablecoins
            stablecoins = data.get("peggedAssets", [])

            # Map to our structure
            live_issuers = {}
            total_market = 0.0

            # Known issuer mappings
            issuer_map = {
                "Tether": ("tether", "tether-usdt", 0.60, False),
                "USD Coin": ("circle", "circle-usdc", 0.80, True),
                "USDC": ("circle", "circle-usdc", 0.80, True),
                "Pax Dollar": ("paxos", "paxos-usdp", 0.95, True),
                "PayPal USD": ("paypal", "paypal-pyusd", 0.90, True),
                "Gemini Dollar": ("gemini", "gemini-gusd", 0.95, True),
                "USDS": ("sky", "sky-usds", 0.70, True),
                "First Digital USD": ("firstdigital", "fd-fdusd", 0.85, True),
            }

            for coin in stablecoins:
                name = coin.get("name", "")
                # Get market cap in billions
                circulating = coin.get("circulating", {})
                if isinstance(circulating, dict):
                    market_cap = circulating.get("peggedUSD", 0) / 1e9
                else:
                    market_cap = 0

                if market_cap < 0.1:  # Skip tiny stablecoins
                    continue

                total_market += market_cap

                # Check if it's a known issuer
                for known_name, (key, node_id, treasury_pct, compliant) in issuer_map.items():
                    if known_name.lower() in name.lower():
                        live_issuers[key] = {
                            "node_id": node_id,
                            "name": name,
                            "market_cap": round(market_cap, 2),
                            "treasury_pct": treasury_pct,
                            "treasury_holdings": round(market_cap * treasury_pct, 2),
                            "headquarters": STABLECOIN_ISSUERS.get(key, {}).get("headquarters", "Unknown"),
                            "genius_compliant": compliant,
                        }
                        break

            if live_issuers:
                print(f"[Stablecoin] Live DeFi Llama data: ${total_market:.1f}B total market, {len(live_issuers)} issuers tracked")
                return {
                    "live": True,
                    "source": "DeFi Llama API",
                    "total_market": total_market,
                    "issuers": live_issuers,
                }

        except Exception as e:
            print(f"[Stablecoin] DeFi Llama fetch failed: {e}, using seeded data")

        return None

    def collect(self) -> List[Artifact]:
        """Collect stablecoin market and Treasury backing data.

        Tries to fetch live data from DeFi Llama API.
        Falls back to seeded data if unavailable.
        """
        artifacts = []

        # Try live data first
        live_data = self._fetch_live_stablecoin_data()

        # Determine data source
        if live_data and live_data.get("live"):
            data_source = "DeFi Llama API (live)"
            issuers = live_data["issuers"]
            total_market = live_data["total_market"]
        else:
            data_source = "Seeded baseline"
            issuers = STABLECOIN_ISSUERS
            total_market = TOTAL_STABLECOIN_MARKET

        # Calculate totals from current data
        total_treasury = sum(s["treasury_holdings"] for s in issuers.values())
        genius_compliant = sum(s["treasury_holdings"] for s in issuers.values() if s["genius_compliant"])
        domestication_pct = round(total_treasury / FOREIGN_TREASURY_HOLDINGS * 100, 2)
        projected_2028_pct = round(GENIUS_ACT["projected_market_2028"] / FOREIGN_TREASURY_HOLDINGS * 100, 2)

        # GENIUS Act artifact
        genius_data = {
            "source": "Congress.gov / Treasury",
            "legislation": "GENIUS Act (H.R. 4XXX)",
            "signed": GENIUS_ACT["signed_date"],
            "votes": {
                "senate": GENIUS_ACT["senate_vote"],
                "house": GENIUS_ACT["house_vote"],
            },
            "requirements": {
                "reserve_requirement": f"{GENIUS_ACT['reserve_requirement']*100}% backing",
                "holder_yield": f"{GENIUS_ACT['holder_yield']}% (zero by law)",
                "issuer_capture": f"{GENIUS_ACT['issuer_yield']}% Treasury yield",
            },
            "projections": {
                "market_2028": f"${GENIUS_ACT['projected_market_2028']}B",
                "debt_domestication_2028": f"{projected_2028_pct}%",
            },
        }

        genius_content = json.dumps(genius_data, indent=2)
        genius_hash = hashlib.sha256(genius_content.encode()).hexdigest()
        genius_path = self.artifact_dir / "genius_act_summary.json"
        with open(genius_path, "w") as f:
            f.write(genius_content)

        artifacts.append(Artifact(
            url="https://www.congress.gov/bill/119th-congress/house-bill/genius-act",
            artifact_type="json",
            local_path=str(genius_path),
            content_hash=genius_hash,
            metadata=genius_data,
        ))

        # Stablecoin market artifact
        market_data = {
            "source": "Stablecoin attestations / DeFi Llama",
            "data_source": data_source,
            "as_of": datetime.utcnow().strftime("%Y-%m-%d"),
            "issuers": issuers,
            "totals": {
                "total_market_cap": round(total_market, 2),
                "total_treasury_holdings": round(total_treasury, 2),
                "genius_compliant_holdings": round(genius_compliant, 2),
            },
            "domestication_metrics": {
                "current_domestication_pct": domestication_pct,
                "foreign_holdings_baseline": FOREIGN_TREASURY_HOLDINGS,
                "projected_2028_pct": projected_2028_pct,
            },
            "extraction_analysis": {
                "holder_yield": 0.0,
                "issuer_yield": GENIUS_ACT["issuer_yield"],
                "spread_captured_by_issuers": f"${round(total_treasury * GENIUS_ACT['issuer_yield'] / 100, 2)}B/year",
            },
        }

        market_content = json.dumps(market_data, indent=2)
        market_hash = hashlib.sha256(market_content.encode()).hexdigest()
        market_path = self.artifact_dir / f"stablecoin_market_{datetime.utcnow().strftime('%Y%m%d')}.json"
        with open(market_path, "w") as f:
            f.write(market_content)

        artifacts.append(Artifact(
            url="https://defillama.com/stablecoins",
            artifact_type="json",
            local_path=str(market_path),
            content_hash=market_hash,
            metadata=market_data,
        ))

        print(f"Collected stablecoin data ({data_source}): ${total_market:.1f}B market, ${total_treasury:.1f}B in Treasuries")
        print(f"Debt domestication: {domestication_pct}% current → {projected_2028_pct}% projected 2028")
        return artifacts

    def extract(self, artifacts: List[Artifact]) -> List[StructuredFact]:
        """Extract facts about stablecoin Treasury absorption."""
        facts = []

        for artifact in artifacts:
            if "issuers" in artifact.metadata:
                # Extract issuer facts
                for issuer_key, data in artifact.metadata["issuers"].items():
                    # Fact: Issuer holds Treasuries
                    facts.append(StructuredFact(
                        fact_type="stablecoin_treasury",
                        subject=data["name"],
                        predicate="HOLDS_TREASURY",
                        object="US Treasury",
                        source_artifact=artifact,
                        confidence=0.9,
                        date_occurred=artifact.metadata.get("as_of"),
                        raw_text=f"{data['name']} holds ${data['treasury_holdings']}B in US Treasuries ({data['treasury_pct']*100}% of reserves)",
                        metadata={
                            "node_id": data["node_id"],
                            "treasury_holdings": data["treasury_holdings"],
                            "treasury_pct": data["treasury_pct"],
                            "market_cap": data["market_cap"],
                            "genius_compliant": data["genius_compliant"],
                        }
                    ))

                    # Fact: GENIUS Act compliance
                    if data["genius_compliant"]:
                        facts.append(StructuredFact(
                            fact_type="genius_compliance",
                            subject=data["name"],
                            predicate="COMPLIES_WITH",
                            object="GENIUS Act",
                            source_artifact=artifact,
                            confidence=0.95,
                            raw_text=f"{data['name']} is GENIUS Act compliant - 1:1 Treasury backing",
                            metadata={
                                "node_id": data["node_id"],
                                "holder_yield": 0.0,
                            }
                        ))

                # Extract domestication metrics
                metrics = artifact.metadata.get("domestication_metrics", {})
                facts.append(StructuredFact(
                    fact_type="debt_domestication",
                    subject="Stablecoin Treasury Absorption",
                    predicate="DOMESTICATES",
                    object="US Treasury Debt",
                    source_artifact=artifact,
                    confidence=0.85,
                    raw_text=f"Stablecoins have domesticated {metrics.get('current_domestication_pct')}% of foreign Treasury holdings (${TOTAL_TREASURY_HOLDINGS}B of ${FOREIGN_TREASURY_HOLDINGS}B)",
                    metadata={
                        "current_pct": metrics.get("current_domestication_pct"),
                        "projected_2028_pct": metrics.get("projected_2028_pct"),
                        "total_domestic": TOTAL_TREASURY_HOLDINGS,
                        "total_foreign": FOREIGN_TREASURY_HOLDINGS,
                    }
                ))

                # Fact: Foreign leverage reduction
                facts.append(StructuredFact(
                    fact_type="leverage_reduction",
                    subject="Stablecoin Treasury Absorption",
                    predicate="REDUCES",
                    object="Foreign Treasury Leverage",
                    source_artifact=artifact,
                    confidence=0.80,
                    raw_text=f"Each $1 in stablecoin Treasuries = $1 less foreign leverage. Current: ${TOTAL_TREASURY_HOLDINGS}B domestic vs ${FOREIGN_TREASURY_HOLDINGS}B foreign",
                    metadata={
                        "domestic_holdings": TOTAL_TREASURY_HOLDINGS,
                        "foreign_holdings": FOREIGN_TREASURY_HOLDINGS,
                        "leverage_reduction_pct": DEBT_DOMESTICATION_PCT,
                    }
                ))

            elif "legislation" in artifact.metadata:
                # GENIUS Act facts
                facts.append(StructuredFact(
                    fact_type="legislation",
                    subject="GENIUS Act",
                    predicate="REQUIRES",
                    object="100% Treasury Backing",
                    source_artifact=artifact,
                    confidence=1.0,
                    date_occurred=GENIUS_ACT["signed_date"],
                    raw_text=f"GENIUS Act (signed {GENIUS_ACT['signed_date']}) requires 1:1 Treasury backing for stablecoins. Holders receive 0% yield by law.",
                    metadata={
                        "holder_yield": 0.0,
                        "issuer_yield": GENIUS_ACT["issuer_yield"],
                        "senate_vote": GENIUS_ACT["senate_vote"],
                        "house_vote": GENIUS_ACT["house_vote"],
                    }
                ))

                # GENIUS Act enables tariffs
                facts.append(StructuredFact(
                    fact_type="mechanism",
                    subject="GENIUS Act",
                    predicate="ENABLES",
                    object="Tariff Policy",
                    source_artifact=artifact,
                    confidence=0.85,
                    raw_text="GENIUS Act domesticates Treasury debt, reducing foreign leverage, enabling tariff implementation without bond market retaliation",
                    metadata={
                        "mechanism": "debt_domestication → reduced_leverage → enabled_tariffs",
                        "projected_impact": f"{PROJECTED_DOMESTICATION_2028}% debt domestication by 2028",
                    }
                ))

        return facts

    def propose(self, facts: List[StructuredFact]) -> Tuple[List[ProposedClaim], List[ProposedEdge], List[ProposedNode]]:
        """Generate proposals for stablecoin Treasury absorption edges."""
        claims = []
        edges = []
        nodes = []

        for fact in facts:
            proposal_id = self._generate_proposal_id()

            if fact.fact_type == "stablecoin_treasury":
                node_id = fact.metadata.get("node_id")
                holdings = fact.metadata.get("treasury_holdings", 0)

                claim = ProposedClaim(
                    proposal_id=proposal_id,
                    claim_text=f"{fact.subject} holds ${holdings}B in Treasury securities for stablecoin backing",
                    topic="DEBT_DOMESTICATION",
                    agent_name=self.name,
                    source_url=fact.source_artifact.url,
                    artifact_path=fact.source_artifact.local_path,
                    artifact_hash=fact.source_artifact.content_hash,
                    reasoning="Stablecoin attestation data",
                    promotion_requirement="Verify against latest attestation report",
                )
                claims.append(claim)

                # Edge: Issuer → Treasury
                edge_proposal_id = self._generate_proposal_id()
                edges.append(ProposedEdge(
                    proposal_id=edge_proposal_id,
                    from_node=node_id,
                    to_node="us-treasury",
                    relationship="HOLDS_TREASURY",
                    agent_name=self.name,
                    detail=f"${holdings}B ({fact.metadata.get('treasury_pct', 0)*100}% of reserves)",
                    proposed_claim_id=proposal_id,
                    confidence=0.9,
                    reasoning="Stablecoin reserve attestation",
                ))

                # Node: Stablecoin issuer
                nodes.append(ProposedNode(
                    proposal_id=self._generate_proposal_id(),
                    node_id=node_id,
                    node_type="COMPANY",
                    name=fact.subject,
                    agent_name=self.name,
                    description=f"Stablecoin issuer with ${holdings}B Treasury holdings",
                    source_url=fact.source_artifact.url,
                ))

            elif fact.fact_type == "debt_domestication":
                claim = ProposedClaim(
                    proposal_id=proposal_id,
                    claim_text=f"Stablecoin Treasury absorption has domesticated {fact.metadata.get('current_pct')}% of foreign holdings, projected {fact.metadata.get('projected_2028_pct')}% by 2028",
                    topic="DEBT_DOMESTICATION",
                    agent_name=self.name,
                    source_url=fact.source_artifact.url,
                    reasoning="Hamilton's funding act in digital form - removing foreign leverage",
                )
                claims.append(claim)

                # Edge: Stablecoin absorption → reduces foreign leverage
                edges.append(ProposedEdge(
                    proposal_id=self._generate_proposal_id(),
                    from_node="stablecoin-treasury-absorption",
                    to_node="foreign-leverage",
                    relationship="REDUCES",
                    agent_name=self.name,
                    detail=f"${TOTAL_TREASURY_HOLDINGS}B domestic = {DEBT_DOMESTICATION_PCT}% reduction",
                    proposed_claim_id=proposal_id,
                    confidence=0.85,
                    reasoning="Domestic holders have zero leverage capacity vs foreign governments",
                ))

            elif fact.fact_type == "mechanism" and "ENABLES" in fact.predicate:
                # GENIUS Act → Tariff enablement chain
                claim = ProposedClaim(
                    proposal_id=proposal_id,
                    claim_text="GENIUS Act is the prerequisite for tariff policy - it domesticates debt to remove foreign leverage",
                    topic="CAUSAL_CHAIN",
                    agent_name=self.name,
                    source_url=fact.source_artifact.url,
                    reasoning=fact.metadata.get("mechanism"),
                )
                claims.append(claim)

                edges.append(ProposedEdge(
                    proposal_id=self._generate_proposal_id(),
                    from_node="genius-act-2025",
                    to_node="tariff-enablement",
                    relationship="ENABLES",
                    agent_name=self.name,
                    detail="Debt domestication removes bond market retaliation threat",
                    proposed_claim_id=proposal_id,
                    confidence=0.85,
                    reasoning="Without domestication, China/Japan can crash bond market in response to tariffs",
                ))

        # Add key domestication nodes
        nodes.append(ProposedNode(
            proposal_id=self._generate_proposal_id(),
            node_id="stablecoin-treasury-absorption",
            node_type="ECONOMIC_EVENT",
            name="Stablecoin Treasury Absorption",
            agent_name=self.name,
            description=f"${TOTAL_TREASURY_HOLDINGS}B in domestic Treasury holdings via stablecoins",
        ))

        return claims, edges, nodes


# CLI entry point
if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    from fgip.db import FGIPDatabase

    if len(sys.argv) < 2:
        print("Usage: python stablecoin.py <database_path>")
        sys.exit(1)

    db_path = sys.argv[1]
    db = FGIPDatabase(db_path)

    agent = StablecoinAgent(db)

    print(f"\n{'='*70}")
    print(f"  STABLECOIN AGENT - DEBT DOMESTICATION MONITOR")
    print(f"{'='*70}")

    print(f"\n  GENIUS Act (signed {GENIUS_ACT['signed_date']})")
    print(f"    Senate: {GENIUS_ACT['senate_vote']} | House: {GENIUS_ACT['house_vote']}")
    print(f"    Holder yield: {GENIUS_ACT['holder_yield']}% (ZERO by law)")
    print(f"    Issuer yield: {GENIUS_ACT['issuer_yield']}% (Treasury rate captured)")
    print(f"    2028 projection: ${GENIUS_ACT['projected_market_2028']}B market")

    print(f"\n  STABLECOIN TREASURY HOLDINGS")
    print(f"    {'Issuer':<20} {'Market Cap':<12} {'Treasury %':<12} {'Holdings':<12} {'Compliant'}")
    print(f"    {'-'*68}")
    for key, data in sorted(STABLECOIN_ISSUERS.items(), key=lambda x: -x[1]["market_cap"]):
        compliant = "✓" if data["genius_compliant"] else "○"
        print(f"    {data['name']:<20} ${data['market_cap']:<10}B {data['treasury_pct']*100:<10}% ${data['treasury_holdings']:<10}B {compliant}")

    print(f"\n  TOTALS")
    print(f"    Total market cap:      ${TOTAL_STABLECOIN_MARKET}B")
    print(f"    Total Treasury held:   ${TOTAL_TREASURY_HOLDINGS}B")
    print(f"    GENIUS compliant:      ${GENIUS_COMPLIANT_HOLDINGS}B")

    print(f"\n  DEBT DOMESTICATION METRICS")
    print(f"    Foreign Treasury holdings: ${FOREIGN_TREASURY_HOLDINGS}B")
    print(f"    Stablecoin domestication:  {DEBT_DOMESTICATION_PCT}% current")
    print(f"    Projected 2028:            {PROJECTED_DOMESTICATION_2028}% at $2T market")

    print(f"\n  THESIS IMPLICATION")
    print(f"    GENIUS Act = Hamilton's funding act in digital form")
    print(f"    Domesticates debt → removes foreign leverage → enables tariffs")
    print(f"    Without this, China/Japan crash bond market if US imposes tariffs")

    print(f"\n{'='*70}")
    results = agent.run()

    print(f"\n{'='*70}")
    print(f"  Results:")
    print(f"    Artifacts collected: {results['artifacts_collected']}")
    print(f"    Facts extracted: {results['facts_extracted']}")
    print(f"    Claims proposed: {results['claims_proposed']}")
    print(f"    Edges proposed: {results['edges_proposed']}")
    print(f"    Nodes proposed: {results['nodes_proposed']}")

    if results['errors']:
        print(f"\n  Errors:")
        for error in results['errors']:
            print(f"    - {error}")
