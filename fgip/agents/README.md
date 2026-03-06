# FGIP Agents

Evidence gatherers that propose HYPOTHESIS claims/edges to the knowledge graph.

## Core Principle

**Agents are NOT truth-makers.** All proposals default to HYPOTHESIS status and require human review for promotion to FACT. This epistemological constraint is enforced by the base class.

```
Agent collects artifacts → extracts facts → proposes hypotheses → human reviews → promoted to graph
```

## Agent Capabilities

### Tier 0 — Government Primary Sources (Highest Confidence)

| Agent | Source | Edge Types |
|-------|--------|------------|
| `EDGARAgent` | SEC.gov EDGAR API | OWNS_SHARES, COMPETES_WITH, SUPPLIES_TO, SITS_ON_BOARD, ACQUIRED |
| `SCOTUSAgent` | supremecourt.gov | FILED_AMICUS, RULED_ON, ARGUED |
| `GAOAgent` | gao.gov, state.gov, treasury.gov | (Claims backed by reports) |
| `USASpendingAgent` | usaspending.gov | AWARDED_GRANT, AWARDED_CONTRACT, FUNDED_PROJECT |
| `FederalRegisterAgent` | federalregister.gov | RULEMAKING_FOR, IMPLEMENTED_BY, AUTHORIZED_BY |
| `CongressAgent` | Congress.gov API | VOTED_FOR, VOTED_AGAINST, SPONSORED, COSPONSORED |
| `TICAgent` | treasury.gov TIC data | HOLDS_TREASURY, FOREIGN_HOLDINGS |
| `FARAAgent` | fara.gov | LOBBIED_FOR, EMPLOYED, REGISTERED_AS_AGENT |
| `FECAgent` | FEC OpenFEC API | DONATED_TO, CONTRIBUTED_TO |
| `CHIPSFacilityAgent` | Commerce.gov CHIPS | CAPACITY_AT, BUILT_IN, OPENED_FACILITY |
| `NuclearSMRAgent` | nrc.gov, energy.gov | (Nuclear licensing/grants) |

### Tier 1 — Journalism & Curated Data (Moderate Confidence)

| Agent | Source | Purpose |
|-------|--------|---------|
| `RSSSignalAgent` | Reuters, AP, WSJ, NYT, FT, Bloomberg | News convergence scoring |
| `OpenSecretsAgent` | opensecrets.org | Lobbying/donations (cites FEC/LDA) |
| `PrometheanAgent` | Promethean Action newsletter | Policy analysis signals |
| `StablecoinAgent` | Stablecoin attestations | GENIUS Act Treasury tracking |
| `OptionsFlowAgent` | Yahoo Finance, TDAmeritrade | Smart money positioning |
| `KalshiSignalAgent` | Kalshi prediction markets | Market probabilities |

### Tier 2 — Signal & Consumption Layers (Lower Confidence)

| Agent | Source | Output |
|-------|--------|--------|
| `YouTubeSignalAnalyzer` | Google Takeout watch history | Guest extraction, topic signals |
| `MarketTapeAgent` | yfinance | Price/volume technicals |
| `PodcastAgent` | Podcast RSS feeds | Topic extraction |

### Meta-Agents — Graph Reasoning & Analysis

| Agent | Function |
|-------|----------|
| `ReasoningAgent` | Multi-hop causal paths, "same actor both sides" patterns, thesis confidence |
| `GapDetectorAgent` | Finds orphan nodes, unused edges, promotion bottlenecks, stale claims |
| `CoverageProbeAgent` | Compares against Wikidata, OpenCorporates for coverage gaps |
| `CausalAgent` | Extracts CAUSED/ENABLED edges from policy documents |
| `SignalGapEcosystemAgent` | Auto-expands ecosystems when signal layer shows gaps |
| `SupplyChainExtractor` | Enhanced 10-K parsing for SUPPLIES_TO, DEPENDS_ON edges |
| `AgentFactory` | Generates specifications for new agents when gaps can't be filled |

### Quality Gates

| Agent | Function |
|-------|----------|
| `FilterAgent` | Hughes-style integrity triage by source tier + manipulation markers |
| `NLPAgent` | Structured extraction (entities, relations, evidence spans) |
| `PipelineOrchestrator` | FilterAgent → NLPAgent → Proposals pipeline |

### Trade & Decision Agents

| Agent | Function |
|-------|----------|
| `ConvictionEngine` | "Would I bet my own money?" — CONVICTION_5 to CONVICTION_1 scoring |
| `ForecastAgent` | P10/P50/P90 distributions, probability of loss |
| `TradePlanAgent` | Decision gates → TRADE_READY or HOLD/PASS |

---

## Base Class Lifecycle

All agents inherit from `FGIPAgent` and implement three methods:

```python
from fgip.agents.base import FGIPAgent, Artifact, StructuredFact, ProposedClaim, ProposedEdge

class MyAgent(FGIPAgent):
    def collect(self) -> list[Artifact]:
        """Fetch new artifacts (URLs, PDFs, filings)."""
        ...

    def extract(self, artifacts: list[Artifact]) -> list[StructuredFact]:
        """Extract structured facts from artifacts."""
        ...

    def propose(self, facts: list[StructuredFact]) -> tuple[list[ProposedClaim], list[ProposedEdge]]:
        """Generate hypothesis proposals from facts."""
        ...
```

### Data Structures

```python
@dataclass
class Artifact:
    url: str
    artifact_type: str           # 'pdf', 'html', 'json', 'xml'
    local_path: Optional[str]
    content_hash: Optional[str]  # SHA256
    fetched_at: Optional[str]
    metadata: dict[str, Any]

@dataclass
class StructuredFact:
    fact_type: str      # 'ownership', 'filing', 'ruling', 'event'
    subject: str
    predicate: str
    object: str
    source_artifact: Artifact
    confidence: float   # 0.0-1.0
    date_occurred: Optional[str]
    raw_text: Optional[str]

@dataclass
class ProposedClaim:
    proposal_id: str              # FGIP-PROPOSED-{AGENT}-{TIMESTAMP}-{UUID}
    claim_text: str
    topic: str
    agent_name: str
    source_url: Optional[str]
    artifact_hash: Optional[str]
    promotion_requirement: Optional[str]  # "Tier 0 doc XYZ would upgrade to FACT"

@dataclass
class ProposedEdge:
    proposal_id: str
    from_node: str
    to_node: str
    relationship: str   # EdgeType enum value
    agent_name: str
    confidence: float
    promotion_requirement: Optional[str]
```

---

## Staging Workflow

### Proposal Lifecycle

```
┌─────────────┐    human     ┌──────────┐    evidence    ┌──────────────┐
│   PENDING   │ ──────────►  │ APPROVED │ ─────────────► │ FACT/INFERENCE│
└─────────────┘    review    └──────────┘   promotion    └──────────────┘
       │                           │
       │         rejected          │
       └───────────────────────────┘
                   │
                   ▼
              ┌──────────┐
              │ REJECTED │
              └──────────┘
```

1. **PENDING** — Agent proposes with evidence snapshot
2. **APPROVED** — Human confirms hypothesis is sound
3. **FACT/INFERENCE** — Promoted after Tier 0 source OR multiple Tier 1 triangulations
4. **REJECTED** — Evidence insufficient (remains for audit)

### Staging Tables

Agents write to staging tables only:
- `proposed_claims` — Hypothesis claims
- `proposed_edges` — Hypothesis relationships
- `proposed_nodes` — Candidate entities

They CANNOT write directly to `claims` or `edges` tables.

---

## Running Agents

### CLI

```bash
# Run single agent
python3 -m fgip.cli agent run edgar
python3 -m fgip.cli agent run scotus

# Dry run (no database writes)
python3 -m fgip.cli agent run edgar --dry-run

# Check agent status
python3 -m fgip.cli agent status
python3 -m fgip.cli staging pending --agent edgar --limit 50
```

### Makefile

```bash
# Watch targets with receipts
make watch-edgar
make watch-scotus
make watch-gao
make watch-fara
make watch-all
```

### Scheduled (systemd)

See `/systemd/README.md` for timer configuration.

```bash
# Enable daily EDGAR runs
systemctl --user enable fgip-edgar.timer
systemctl --user start fgip-edgar.timer
```

---

## Writing a New Agent

### 1. Create the file

```python
# fgip/agents/my_source.py
"""MySource Agent - Brief description of data source."""

from typing import List, Tuple
from .base import FGIPAgent, Artifact, StructuredFact, ProposedClaim, ProposedEdge

class MySourceAgent(FGIPAgent):
    """
    My Source Agent

    Monitors [data source] for [edge types].

    Tier: 0/1/2
    Source: URL
    Edge Types: EDGE_A, EDGE_B
    """

    def __init__(self, db_path: str):
        super().__init__(db_path, agent_name="my_source")

    def collect(self) -> List[Artifact]:
        # Fetch from API/scrape
        artifacts = []
        # ...
        return artifacts

    def extract(self, artifacts: List[Artifact]) -> List[StructuredFact]:
        facts = []
        for artifact in artifacts:
            # Parse artifact content
            # ...
            pass
        return facts

    def propose(self, facts: List[StructuredFact]) -> Tuple[List[ProposedClaim], List[ProposedEdge]]:
        claims = []
        edges = []
        for fact in facts:
            edge = ProposedEdge(
                proposal_id=self._generate_proposal_id(),
                from_node=fact.subject,
                to_node=fact.object,
                relationship=fact.predicate,
                agent_name=self.agent_name,
                confidence=fact.confidence,
                promotion_requirement="Tier 0 filing would confirm",
            )
            edges.append(edge)
        return claims, edges
```

### 2. Register in `__init__.py`

```python
from .my_source import MySourceAgent

__all__ = [
    # ... existing exports ...
    "MySourceAgent",
]
```

### 3. Add to AGENT_CAPABILITIES (if applicable)

In `agent_factory.py`:

```python
AGENT_CAPABILITIES = {
    # ... existing ...
    'my_source': ['EDGE_A', 'EDGE_B'],
}
```

### 4. Add CLI command

In `fgip/cli.py` under the agent run command, add the mapping.

---

## Conviction Framework

The `ConvictionEngine` answers: "Would I bet my own money on this?"

### Conviction Levels

| Level | Confidence | Position | Requirements |
|-------|------------|----------|--------------|
| CONVICTION_5 | 95%+ | Max | Multiple Tier 0 confirmations, no valid counter |
| CONVICTION_4 | 80-95% | Full | Tier 0/1 confirmations, weak counter |
| CONVICTION_3 | 60-80% | Half | Mixed signals, manageable counter |
| CONVICTION_2 | 40-60% | Quarter | Speculative, limited confirmation |
| CONVICTION_1 | <40% | None | Unproven or stronger counter |

### Requirements for CONVICTION_3+

1. Minimum **3 independent signals** from different source types
2. Must **articulate and test strongest counter-thesis**
3. Stress-tested by adversarial model

---

## Self-Healing System

### Gap Detection

`GapDetectorAgent` identifies:
- Orphan nodes (< 3 edges)
- Unused edge types that should exist
- Promotion bottlenecks
- Stale claims (UNVERIFIED > 7 days)

### Ecosystem Expansion

`SignalGapEcosystemAgent` auto-expands when signal layer shows topic without graph coverage:
- Direct players (companies in sector)
- Suppliers (upstream)
- Lenders/financiers
- Upstream commodities
- Adjacent beneficiaries

### Agent Factory

`AgentFactory` generates specifications for new agents:
- Maps gap type → suggested data source
- Estimates complexity
- Lists dependencies
- Writes to `agents/proposed/` for human approval

---

## File Index

| File | Agent | Tier |
|------|-------|------|
| `base.py` | FGIPAgent (base class) | — |
| `edgar.py` | EDGARAgent | 0 |
| `scotus.py` | SCOTUSAgent | 0 |
| `gao.py` | GAOAgent | 0 |
| `usaspending.py` | USASpendingAgent | 0 |
| `federal_register.py` | FederalRegisterAgent | 0 |
| `congress.py` | CongressAgent | 0 |
| `tic.py` | TICAgent | 0 |
| `fara.py` | FARAAgent | 0 |
| `fec.py` | FECAgent | 0 |
| `chips_facility.py` | CHIPSFacilityAgent | 0 |
| `nuclear_smr.py` | NuclearSMRAgent | 0 |
| `rss_signal.py` | RSSSignalAgent | 1 |
| `opensecrets.py` | OpenSecretsAgent | 1 |
| `promethean.py` | PrometheanAgent | 1 |
| `stablecoin.py` | StablecoinAgent | 1 |
| `options_flow.py` | OptionsFlowAgent | 1 |
| `kalshi_signal.py` | KalshiSignalAgent | 1 |
| `youtube_signal.py` | YouTubeSignalAnalyzer | 2 |
| `market_tape.py` | MarketTapeAgent | 2 |
| `podcast.py` | PodcastAgent | 2 |
| `reasoning.py` | ReasoningAgent | meta |
| `gap_detector.py` | GapDetectorAgent | meta |
| `coverage_probe.py` | CoverageProbeAgent | meta |
| `causal_agent.py` | CausalAgent | meta |
| `signal_gap_ecosystem.py` | SignalGapEcosystemAgent | meta |
| `supply_chain_extractor.py` | SupplyChainExtractor | meta |
| `agent_factory.py` | AgentFactory | meta |
| `filter_agent.py` | FilterAgent | gate |
| `nlp_agent.py` | NLPAgent | gate |
| `pipeline_orchestrator.py` | PipelineOrchestrator | gate |
| `conviction_engine.py` | ConvictionEngine | decision |
| `forecast_agent.py` | ForecastAgent | decision |
| `trade_plan_agent.py` | TradePlanAgent | decision |
| `citation_loader.py` | CitationLoaderAgent | admin |
