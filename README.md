<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://capsule-render.vercel.app/api?type=waving&color=0:0d1117,100:6b5a1a&height=200&section=header&text=FGIP&fontSize=42&fontColor=58a6ff&animation=fadeIn&fontAlignY=35&desc=Forensic%20graph%20intelligence%20platform&descSize=16&descColor=8b949e&descAlignY=55">
  <source media="(prefers-color-scheme: light)" srcset="https://capsule-render.vercel.app/api?type=waving&color=0:f0f6fc,100:ba9a2a&height=200&section=header&text=FGIP&fontSize=42&fontColor=1f2328&animation=fadeIn&fontAlignY=35&desc=Forensic%20graph%20intelligence%20platform&descSize=16&descColor=656d76&descAlignY=55">
  <img alt="FGIP" src="https://capsule-render.vercel.app/api?type=waving&color=0:0d1117,100:6b5a1a&height=200&section=header&text=FGIP&fontSize=42&fontColor=58a6ff&animation=fadeIn&fontAlignY=35&desc=Forensic%20graph%20intelligence%20platform&descSize=16&descColor=8b949e&descAlignY=55">
</picture>

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://python.org)
[![SQLite](https://img.shields.io/badge/SQLite-003B57?logo=sqlite&logoColor=white)](https://sqlite.org)
[![License](https://img.shields.io/badge/license-Echo%20Labs-green)](LICENSE)
[![1,801 nodes](https://img.shields.io/badge/nodes-1%2C801-brightgreen)]()
[![3,286 edges](https://img.shields.io/badge/edges-3%2C286-blue)]()

**Track the money. Test the thesis. Present the documents.**
**Forensic-grade graph intelligence -- from lobbying networks to investment signals.**

</div>

# FGIP

FGIP is a dual-use intelligence platform that exposes the lobbying, ownership, and judicial network behind American industrial policy and tracks the reshoring correction as an investable thesis. Every claim is adversarial-tested. Every edge has a source. The graph is the evidence.

## What it does

The platform builds a knowledge graph from government data (SEC EDGAR 13F filings, FEC campaign finance, Congress.gov voting records, Federal Register rulemakings, FRED economic data) and subjects investment theses to forensic verification.

Three-layer architecture:

```
+---------------------------------------------------------+
|  LAYER C: Agent Runtime                                  |
|  42 agents * tool routing * adversarial testing          |
+---------------------------------------------------------+
|  LAYER B: Graph / Memory                                 |
|  1,801 nodes * 3,286 edges * 1,659 claims * 1,040 sources|
+---------------------------------------------------------+
|  LAYER A: Model Substrate                                |
|  CDNA inference * GGUF models * compressed weights       |
+---------------------------------------------------------+
```

## Graph statistics

| Table | Count |
|-------|-------|
| Nodes | 1,801 |
| Edges | 3,286 |
| Claims | 1,659 |
| Sources | 1,040 |
| Pending proposals | 7,684 |

17 node types (ORGANIZATION, PERSON, LEGISLATION, COURT_CASE, COMPANY, FINANCIAL_INST, ETF_FUND, AGENCY, POLICY, ECONOMIC_METRIC, and more).
55 edge types across problem and correction layers.

## Analytical framework

Every claim goes through:

1. **Claim Parser** -- Atomic claims + falsification criteria
2. **Primary Source (Tier 0/1)** -- Treasury, FRED, SEC, Congress.gov
3. **Counter-Model** -- Strongest competing explanation
4. **Control Group** -- Comparison that should NOT show the effect
5. **Graph Edge Builder** -- Only edges with qualifying sources + confidence
6. **Investment Relevance** -- Maps verified edges to tradable implications

## Verified findings

### Real inflation is 6.3%, not 2.7%

M2 money supply growth tracks actual purchasing power loss (housing +220%, S&P +411%). 25-year backtest, 7/7 predictions confirmed, 3/3 adversarial attacks survived.

### Structural capital concentration (refined)

Big Three (Vanguard/BlackRock/State Street) own 18-20% of ALL large-cap firms -- CHIPS recipients AND control group. Difference: -0.08%. This is passive indexing, not strategic positioning. The refined thesis is stronger: structural concentration mechanically creates both-sides exposure regardless of intent.

### Congress overlap -- weakened

32 members voting for both CHIPS and related legislation. Statistical expectation: 70.1. Ratio: 0.46x (below expected). NOT a strong signal.

## Data sources

| Source | Type | Coverage |
|--------|------|----------|
| SEC EDGAR 13F | Institutional ownership | Quarterly |
| FEC | Campaign finance | Continuous |
| Congress.gov | Voting records, bill text | Continuous |
| Federal Register | Rulemakings (FDIC, Commerce, SEC, Treasury) | Daily |
| FRED | Economic indicators (M2, CPI, employment) | Monthly |
| OpenSecrets | Dark money, 990 filings | Annual |
| RSS feeds | News monitoring | Continuous |

## Thesis Pack

The `THESIS_PACK/` directory contains 5 investment thesis claims with backtest results:

- `claims_backtest_results.md` -- 25-year M2 vs asset price validation
- `claims_genius_act.md` -- GENIUS Act stablecoin framework analysis
- `claims_industrial_base.md` -- Industrial base reshoring thesis
- `claims_inflation_proxy.md` -- Real inflation vs CPI divergence
- `claims_reshoring_etfs.md` -- Reshoring ETF positioning

## Quick start

```bash
# Check thesis score
python3 -m fgip.cli score

# Run adversarial testing
python3 -m fgip.analysis.adversarial

# Run gap analysis
python3 -m fgip.analysis.gap_detector

# Portfolio allocation
python3 -m fgip.allocator --settlement 250000 --risk-tolerance conservative

# Location scoring
python3 -m fgip.location --address "123 Main St, Hampton, GA"
```

## Project structure

```
fgip-engine/
+-- fgip/
|   +-- agents/          # 42 analytical agents (FEC, Congress, dark money, etc.)
|   +-- allocator/       # Portfolio allocation with policy constraints
|   +-- analysis/        # Gap detection, signal convergence, adversarial testing
|   +-- backtest/        # Portfolio backtesting and risk metrics
|   +-- decisions/       # Evidence-gated decision framework
|   +-- governance/      # Family cost index, housing gate, IPS
|   +-- location/        # Property scoring (crime, flood, insurance, HOA)
|   +-- ontology/        # Graph schema constraints and validation
|   +-- regime/          # Regime classification and belief revision
|   +-- resolve/         # Entity resolution and deduplication
+-- echo_gateway/        # Agent runtime and task routing
+-- cdna_server/         # CDNA compressed model inference
+-- THESIS_PACK/         # Investment thesis claims + backtest receipts
+-- scripts/             # Graph insertion scripts
+-- tools/               # Diagnostic and calibration tools
+-- tests/               # Test suite
```

## Companion projects

| Project | What it does |
|---------|-------------|
| [helix-substrate](https://github.com/echo313unfolding/helix-substrate) | Calibration-free weight compression (4x, beats GPTQ) |
| [helix-online-kv](https://github.com/echo313unfolding/helix-online-kv) | Online KV cache compression + compressed-domain attention |
| [echo_runtime](https://github.com/echo313unfolding/echo_runtime) | Unified compressed AI inference runtime |

## License

Echo Labs LLC. See LICENSE for details.

<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://capsule-render.vercel.app/api?type=waving&color=0:6b5a1a,100:0d1117&height=100&section=footer">
  <source media="(prefers-color-scheme: light)" srcset="https://capsule-render.vercel.app/api?type=waving&color=0:ba9a2a,100:f0f6fc&height=100&section=footer">
  <img alt="footer" src="https://capsule-render.vercel.app/api?type=waving&color=0:6b5a1a,100:0d1117&height=100&section=footer" width="100%">
</picture>

</div>
