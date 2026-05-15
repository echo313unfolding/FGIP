<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://capsule-render.vercel.app/api?type=waving&color=0:0d1117,100:6b5a1a&height=200&section=header&text=FGIP&fontSize=42&fontColor=58a6ff&animation=fadeIn&fontAlignY=35&desc=Fifth%20Generation%20Institute%20for%20Prosperity&descSize=12&descColor=8b949e&descAlignY=55">
  <source media="(prefers-color-scheme: light)" srcset="https://capsule-render.vercel.app/api?type=waving&color=0:f0f6fc,100:ba9a2a&height=200&section=header&text=FGIP&fontSize=42&fontColor=1f2328&animation=fadeIn&fontAlignY=35&desc=Fifth%20Generation%20Institute%20for%20Prosperity&descSize=12&descColor=656d76&descAlignY=55">
  <img alt="FGIP" src="https://capsule-render.vercel.app/api?type=waving&color=0:0d1117,100:6b5a1a&height=200&section=header&text=FGIP&fontSize=42&fontColor=58a6ff&animation=fadeIn&fontAlignY=35&desc=Fifth%20Generation%20Institute%20for%20Prosperity&descSize=12&descColor=8b949e&descAlignY=55">
</picture>

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://python.org)
[![SQLite](https://img.shields.io/badge/SQLite-003B57?logo=sqlite&logoColor=white)](https://sqlite.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![2,100+ nodes](https://img.shields.io/badge/nodes-2%2C100%2B-brightgreen)]()
[![2,800+ edges](https://img.shields.io/badge/edges-2%2C800%2B-blue)]()
[![69K+ proposed edges](https://img.shields.io/badge/proposed_edges-69K%2B-orange)]()

**Track the money. Test the thesis. Present the documents.**

</div>

The Fifth Generation Institute for Prosperity exists to make the flow of public capital visible — structurally, source-by-source, in machine-tractable form.

### Why we exist

Every federal dollar starts on a worksite, a paycheck, or a tax bill. By the time that dollar reaches a contractor, a supplier, a commodity producer, or a public ticker, it has typically passed through six or more institutional layers: appropriation, agency disbursement, prime contract, sub-tier supplier, commodity input, and the equities that ultimately price the flow. Each layer is documented in public government records. None of them are connected to each other in a way an ordinary citizen, journalist, or independent investor can query.

The result is that public debate operates at the level of bill names and headlines while the actual disposition of the capital remains opaque. Citizens are asked to support or oppose legislation whose downstream beneficiaries they cannot trace. Journalists are asked to report on spending decisions without graph infrastructure to follow the money past one or two hops. Independent investors are asked to evaluate exposures while the structural drivers — federal funding chains, commodity bottlenecks, lobbying flows — remain undisclosed in any unified form.

### What we do

FGIP builds and maintains the connective infrastructure. Twenty-four specialized agents continuously ingest Tier-0 government sources — Congress.gov, SEC EDGAR, USASpending, the Federal Register, FEC, FARA, NRC ADAMS, SCOTUS dockets, OpenSecrets — and structure them into a single forensic graph: who funds whom, who supplies whom, who lobbies whom, what commodities bind the chain, what public tickers are exposed at each layer.

Every claim in the graph carries a source document. Every thesis must survive three independent signals from different source types — at least one Tier-0 government record — and an articulated counter-thesis before it is recognized as supported. Conviction is a scored quantity, not a sentiment. This is the methodology of a serious intelligence operation applied to public information, with the receipts foregrounded.

### Our position

FGIP is non-partisan and presents structure as it is. We do not tell you which party is responsible for any given flow, what to do about any finding, or whom to vote for. We show you, source by source, where capital authorized by your representatives has been obligated, who has received it, what they have done with it, and which companies, commodities, and supply chains the flow ultimately reaches. The conclusions are yours to draw.

We accept no government funding. We do not represent issuers, donors, or lobbying clients. The graph is the product. The methodology is documented. The sources are public. Anyone can audit the chain.

### Why this is Promethean

The analytical tools that institutional power has long reserved for itself — graph databases, evidence triangulation, source-tier classification, adversarial testing of theses — are not exotic. They are standard intelligence-community and quantitative-finance practice. Their absence from public-facing investigative infrastructure is a distributional choice, not a technical limitation.

FGIP exists to redistribute that capability. The labor and taxes of working people constitute the federal capital being tracked. The tools to see where that capital actually goes belong to them.

---

## How it works

FGIP maps where public funding is committed before it becomes recognized revenue, then traces the beneficiary chain.

```
bill → appropriation → agency → contract/grant → company → supplier → commodity → public ticker → hedge
```

Most trading systems look at price, volume, earnings, sentiment, and technical indicators. FGIP looks at where funding has been committed — in public government records — before the market headline says who benefits.

A headline is downstream. The funding trail is upstream.

## Verified findings

### Real inflation is 6.3%, not 2.7%

M2 money supply growth tracks actual purchasing power loss (housing +220%, S&P +411%). 25-year backtest against FRED data, 7/7 predictions confirmed, 3/3 adversarial attacks survived.

### Structural capital concentration

Big Three (Vanguard/BlackRock/State Street) own 18-20% of ALL large-cap firms — CHIPS recipients AND non-CHIPS control group. Difference: -0.08%. This is passive indexing, not strategic positioning. Structural concentration mechanically creates both-sides exposure regardless of intent.

### Defense funding chains

NDAA FY2025 ($895.2B) → 8 prime contractor AUTHORIZES_FUNDING edges. Ukraine supplemental ($60.84B) → 5 FUNDS_REPLENISHMENT edges. Columbia-class ($132B) → sole-source naval nuclear chain (GD → HII → BWXT → Cameco uranium). All traced from bill text to company to supplier to commodity.

## How it works

24 specialized agents ingest Tier 0 (government) and Tier 1 (professional) data sources. Each agent produces **proposed edges** — structured claims about relationships between entities, backed by source documents.

```
public records → graph edges → thesis conviction → evidence / risk mapping
```

### The funding chain

Every node in the graph is either a source of funds, a channel for funds, or a recipient of funds. The edges are the flows.

```
Congress funds NDAA
  → DoD funds Lockheed Martin
    → Lockheed funds Howmet for forgings
      → Howmet procures copper
        → FCX sells the copper
```

The graph traces these chains across 6 layers:

| Layer | What | Examples |
|-------|------|---------|
| 0 | Commodities | Gas, uranium, copper, silver, rare earths |
| 1 | Extraction | Cameco, Freeport, MP Materials |
| 2 | Transport/midstream | DT Midstream, Williams, Energy Transfer |
| 3 | Conversion/power | Constellation Energy, GE Vernova, utilities |
| 4 | Infrastructure | Data centers, fabs, grid equipment |
| 5 | Platform/hyperscalers | The demand layer that drives everything below |

## Architecture

```
+------------------------------------------------------------+
|  CONVICTION ENGINE                                          |
|  Signal collection → triangulation → adversarial testing    |
|  → conviction scoring                                       |
+------------------------------------------------------------+
|  GRAPH + PROPOSED EDGES                                     |
|  2,100+ nodes · 2,800+ edges · 69K+ proposed · 24 agents   |
+------------------------------------------------------------+
|  DATA INGEST (Tier 0 / Tier 1)                              |
|  Congress · EDGAR · USASpending · Federal Register · FEC    |
|  FARA · NRC · SCOTUS · OpenSecrets · RSS · Options flow     |
+------------------------------------------------------------+
```

> **Note:** FGIP is the intelligence/research layer. The `fgip/agents/trading_agent.py` and `fgip/allocator/` modules are reference implementations of how the intelligence can be consumed downstream; they are not part of the core research product.

### Conviction engine

Every thesis goes through:

1. **Signal collection** — Query graph edges and proposed edges for confirming/refuting evidence
2. **Triangulation** — Require 3+ independent signals from different source types, at least 1 Tier 0
3. **Adversarial testing** — Articulate and test the strongest counter-thesis
4. **Conviction scoring** — 1-5 levels based on evidence quality (not quantity)
5. **Position sizing** — Conviction level maps to position size (conviction 3 = half position)

### Evidence tiers

| Tier | Source type | Conviction boost |
|------|-----------|-----------------|
| 0 | Government records (EDGAR, USASpending, Congress, Federal Register, NRC) | +15 per signal |
| 1 | Professional sources (options flow, analyst, earnings, industry conference) | +8 per signal |
| 2 | Commentary (news, social, podcast, YouTube) | +3 per signal |

### Proposed edges pipeline

Agents scrape sources and produce **proposed edges** — structured claims that sit in a staging table until reviewed. Each proposed edge has:

- `from_node` / `to_node` — entities connected
- `relationship` — edge type (VOTED_FOR, AWARDED_CONTRACT, OWNS_SHARES, etc.)
- `confidence` — 0.0 to 1.0
- `agent_name` — which agent produced it
- `artifact_id` — link to source document

Tier 0 agents (government sources) self-certify. Lower-tier agents require artifact evidence for promotion.

## Agents

| Agent | Source | Edge types | Count |
|-------|--------|-----------|-------|
| congress | Congress.gov, House/Senate Clerks | VOTED_FOR, VOTED_AGAINST, SPONSORED | 3,136 |
| usaspending | USASpending.gov | AWARDED_GRANT, AWARDED_CONTRACT, FUNDED_PROJECT | 4,100 |
| edgar | SEC EDGAR | OWNS_SHARES, ACQUIRED, SUPPLIES_TO, COMPETES_WITH | 2,265 |
| federal_register | Federal Register | RULEMAKING_FOR, IMPLEMENTED_BY, AUTHORIZED_BY | 828 |
| fec | FEC.gov | DONATED_TO | 11,201 |
| opensecrets | OpenSecrets | LOBBIED_FOR, DONATED_TO | 4,644 |
| scotus | SCOTUS dockets | FILED_AMICUS, CITED_BY | 4,659 |
| rss | News feeds | Various | 14,503 |
| supply_chain_extractor | 10-K filings | SUPPLIES_TO, DEPENDS_ON, CUSTOMER_OF | 12,413 |
| stablecoin | Treasury, FDIC | RULEMAKING_FOR, REGULATES | 8,315 |
| nuclear_smr | NRC ADAMS | LICENSED_BY, PERMITTED_BY | 184 |
| fara | FARA.gov | REGISTERED_AGENT, REPRESENTS | 450 |
| And 12 more... | | | |

### Analytical desks (managed agents)

IC-style specialist desks that evaluate incoming intelligence through independent analytical lenses:

| Desk | Function | IC Analog |
|------|----------|-----------|
| [thesis-war-room](managed-agents/thesis-war-room/) | MoE panel — 5 desks score a thesis simultaneously, arbiter synthesizes | War room / NIE |
| [intel-brief](managed-agents/intel-brief/) | Produces PDB-style structured briefs with key judgments and confidence levels | PDB / finished intelligence |
| [field-debrief](managed-agents/field-debrief/) | Structures raw field observations into graph-insertable JSON | HUMINT intake |
| [source-evaluator](managed-agents/source-evaluator/) | ADMIRALTY-scale source reliability and tier classification | Source reliability desk |
| [sitrep](managed-agents/sitrep/) | Periodic graph delta, thesis movements, signal alerts | SITREP |
| [claim-verifier](managed-agents/claim-verifier/) | Adversarial verification of individual claims | Fact-checking / QC |
| [tariff-analyzer](managed-agents/tariff-analyzer/) | Three-layer tariff decomposition (formula + gradient + lever) | Subject desk |
| [entity-screener](managed-agents/entity-screener/) | Entity screening against graph for exposure and risk | Entity resolution |
| [littlesis-ingest](managed-agents/littlesis-ingest/) | LittleSis relationship database (400K entities, 1.6M relationships) | HUMINT database |
| [opensanctions-ingest](managed-agents/opensanctions-ingest/) | Sanctions screening against 320+ government watchlists | Sanctions desk |
| [corporate-registry](managed-agents/corporate-registry/) | Shell LLC → parent company ownership chain tracing | Corporate intel |

The war room runs all 5 specialist desks in parallel (funding, supply chain, regulatory, adversarial, timing) and synthesizes a verdict based on desk agreement. Disagreement between desks IS the intelligence.

## Investment theses

FGIP evaluates 15+ investment theses across sectors:

| Thesis | Sector | Key tickers | Signal sources |
|--------|--------|-------------|---------------|
| Data center power | Midstream, E&P, utility | DTM, AR, WMB, EQT, DTE | FERC filings, PUC approvals, pipeline throughput |
| Uranium structural deficit | Nuclear | CCJ, UUUU, CEG, OKLO | NRC permits, DoE grants, supply/demand data |
| Defense primes | Defense | LMT, RTX, NOC, GD, HII, BWXT | NDAA, USASpending contracts, Ukraine supplemental |
| Silver bottleneck | Silver mining | AG, PAAS | COMEX inventory, Mexico moratorium |
| Copper wiring | Copper | FCX | Grid modernization contracts, mine supply |
| Rare earth security | Critical minerals | MP | China export restrictions, DoD procurement |
| Fertilizer/inflation | Fertilizer | CF, NTR | Henry Hub gas, urea prices, M2 data |
| Government infrastructure | Infrastructure | PWR, LDOS | IIJA/IRA remaining spend, state DOT awards |
| SMR endgame | Nuclear SMR | OKLO, SMR | NRC design approvals, utility PPAs |
| Dollar resilience rails | Digital asset rails | — | GENIUS Act, OCC/FDIC rulemakings, Treasury reserve data |

## Quick start

```bash
# Clone
git clone https://github.com/echo313unfolding/FGIP.git
cd FGIP

# Initialize database (creates schema, no data)
python3 -m fgip.cli init

# Populate graph with structural data
python3 tools/populate_full_graph.py
python3 tools/populate_commodity_chain.py
python3 tools/wire_defense_government.py

# Run conviction engine
python3 -m fgip.agents.conviction_engine

# Run adversarial testing
python3 -m fgip.analysis.adversarial
```

## Project structure

```
fgip-engine/
├── fgip/
│   ├── agents/          # 24 analytical agents + conviction engine
│   ├── allocator/       # Reference: downstream portfolio allocation consumer
│   ├── analysis/        # Gap detection, adversarial testing, signal convergence
│   ├── backtest/        # Portfolio backtesting and risk metrics
│   ├── decisions/       # Evidence-gated decision framework
│   ├── governance/      # Family cost index, housing gate, IPS
│   ├── ontology/        # Graph schema constraints and validation
│   ├── regime/          # Regime classification and belief revision
│   ├── resolve/         # Entity resolution and deduplication
│   └── pipeline/        # Artifact processing pipeline
├── evidence_graph/      # Evidence graph with FSA state machine
├── config/              # Watchlist, risk parameters
├── tools/               # Graph population and diagnostic tools
├── scripts/             # Graph insertion scripts
├── data/                # Source registry, extracted facts, candidate edges
├── receipts/            # Thesis receipts (cryptographic, substrate-agnostic)
├── THESIS_PACK/         # Investment thesis claims + backtest receipts
├── articulations/       # Analytical write-ups on specific topics
├── tests/               # Test suite
└── web/                 # Web UI and API endpoints
```

## Data sources (all public)

| Source | URL | Type |
|--------|-----|------|
| SEC EDGAR | sec.gov/cgi-bin/browse-edgar | 13F filings, 10-K, 8-K |
| Congress.gov | congress.gov | Voting records, bill text |
| USASpending | usaspending.gov | Federal contracts and grants |
| Federal Register | federalregister.gov | Rulemakings and executive orders |
| FEC | fec.gov | Campaign finance |
| FARA | fara.gov | Foreign agent registrations |
| FRED | fred.stlouisfed.org | Economic indicators |
| OpenSecrets | opensecrets.org | Dark money, lobbying |
| NRC ADAMS | nrc.gov/reading-rm/adams.html | Nuclear regulatory documents |

## Companion projects

| Project | What it does |
|---------|-------------|
| [helix-substrate](https://github.com/echo313unfolding/helix-substrate) | HXQ tensor compression (4x from FP32, cos>0.999) |
| [helix-codec](https://github.com/echo313unfolding/helix-codec) | Standalone C99 tensor codec library |
| [echo-sentry](https://github.com/echo313unfolding/echo-sentry) | Security monitoring with SSM+Transformer hybrid |

## Documentation

| Document | What it covers |
|----------|---------------|
| [SUPPORTING_FACTORS.md](docs/SUPPORTING_FACTORS.md) | Source-backed evidence packets for each thesis (claims, evidence, funding chains, counter-theses) |
| [EVIDENCE_TIERS.md](docs/EVIDENCE_TIERS.md) | How data sources are classified (Tier 0 government → Tier 3 hypothesis) |
| [THESIS_RECEIPT_SCHEMA.md](docs/THESIS_RECEIPT_SCHEMA.md) | Receipt format for thesis validation (evidence, conviction, graph state) |
| [SOURCE_AND_FACT_MODEL.md](docs/SOURCE_AND_FACT_MODEL.md) | How citations, extracted facts, and proposed edges are separated |
| [DIGITAL_ASSET_RAILS.md](docs/DIGITAL_ASSET_RAILS.md) | Stablecoin, tokenization, and regulated settlement rail layer |
| [DOLLAR_RESILIENCE_RAILS.md](docs/DOLLAR_RESILIENCE_RAILS.md) | Candidate thesis: stablecoin reserves as dollar-demand channel |
| [OSINT_LANDSCAPE.md](docs/OSINT_LANDSCAPE.md) | Competitive landscape: peers, agent frameworks, data sources |

## Source registry

Citations live in the source registry. Extracted facts become graph edges. Receipts promote claims.

```
data/
├── sources/sources.jsonl          # Citable documents (who said it, when, where)
├── extracted/facts.jsonl          # Structured claims (what was said, machine-readable)
└── edges/proposed_edges_examples.jsonl  # Candidate graph edges (how it connects)
```

Each layer serves a different consumer: sources are for humans verifying citations, facts are for agents querying structured claims, and edges are for the conviction engine scoring theses. See [SOURCE_AND_FACT_MODEL.md](docs/SOURCE_AND_FACT_MODEL.md) for the full model.

## The core idea

```
Where is money authorized?
Where is it obligated?
Who receives it?
Who supplies them?
What commodity bottlenecks bind it?
What public tickers are exposed?
What hedges offset the failure case?
```

Money moves through public records before headlines move prices.

## License

MIT. See [LICENSE](LICENSE).

<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://capsule-render.vercel.app/api?type=waving&color=0:6b5a1a,100:0d1117&height=100&section=footer">
  <source media="(prefers-color-scheme: light)" srcset="https://capsule-render.vercel.app/api?type=waving&color=0:ba9a2a,100:f0f6fc&height=100&section=footer">
  <img alt="footer" src="https://capsule-render.vercel.app/api?type=waving&color=0:6b5a1a,100:0d1117&height=100&section=footer" width="100%">
</picture>

</div>
