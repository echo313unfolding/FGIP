# FGIP Causality Engine — Claude Code Project Spec

## What This Is

A domain-specific knowledge graph and analysis engine that maps the documented causality chain behind U.S. economic hollowing (1990–2025) and the ongoing reshoring correction (2025–present). Not a general-purpose AI. A structured data system with reasoning capabilities focused on one thesis: tracing how lobbying, judicial, media, and financial ownership networks created and now resist correction of a 25-year structural economic distortion.

## Core Data Model

### The Knowledge Graph

The system is built on a **relational graph database** (Neo4j recommended, or SQLite with junction tables for MVP). Every entity is a node. Every documented relationship is an edge with metadata.

#### Node Types

```
ORGANIZATION    — Chamber of Commerce, BlackRock, Vanguard, Heritage Foundation, etc.
PERSON          — Ginni Thomas, Clarence Thomas, Harlan Crow, Larry Fink, etc.
LEGISLATION     — PNTR (2000), CHIPS Act, OBBBA, GENIUS Act, etc.
COURT_CASE      — Trump tariff cases, Citizens United, etc.
POLICY          — H-1B expansion, sanctuary city policies, tariff schedules, etc.
COMPANY         — Caterpillar, Intel, Nucor, HSBC, JPMorgan, etc.
MEDIA_OUTLET    — Gannett, Sinclair, specific publications
FINANCIAL_INST  — NY Fed, BIS, regional Fed banks, credit unions
AMICUS_BRIEF    — Individual filings with case reference
ETF_FUND        — RSHO, MADE, IWM, specific BlackRock/Vanguard funds
ECONOMIC_EVENT  — Factory opening, job losses, trade deficit data point
```

#### Edge Types (Relationships)

```
LOBBIED_FOR         — org → legislation, with dollar amount + year
LOBBIED_AGAINST     — org → legislation/policy
FILED_AMICUS        — org → court_case, with position (for/against)
OWNS_SHARES         — org → org, with percentage + date
EMPLOYS / EMPLOYED  — org → person, with role + dates
MARRIED_TO          — person → person
DONATED_TO          — person/org → org, with amount
APPOINTED_BY        — person → person
RULED_ON            — person → court_case, with vote
CAUSED              — legislation → economic_event (documented causal link)
CORRECTS            — legislation/company → economic_event
OPPOSES_CORRECTION  — org → legislation (anti-tariff amicus, etc.)
OWNS_MEDIA          — org → media_outlet, with percentage
REPORTS_ON          — media_outlet → topic, with framing sentiment
MEMBER_OF           — org → financial_inst (Fed membership, BIS membership)
INVESTED_IN         — org → company, with amount + sector
SUPPLIES            — company → company (supply chain link)
```

#### Edge Metadata (Every Edge Gets These)

```json
{
  "source": "ProPublica / OpenSecrets / SEC filing / House report / etc.",
  "source_url": "direct link to document",
  "date_documented": "when we found it",
  "date_occurred": "when the relationship existed",
  "confidence": "high / medium / low",
  "notes": "context"
}
```

### Seed Data — What We Already Have

Below is the structured seed data extracted from ~8 hours of research. Each entry should be converted into nodes + edges on first run.

#### Ownership Layer

| From | Relationship | To | Detail | Source |
|------|-------------|-----|--------|--------|
| Citibank | OWNS_SHARES | NY Fed | 42.8% (87.9M shares, 2018) | Institutional Investor FOIA |
| JPMorgan Chase | OWNS_SHARES | NY Fed | 29.5% (60.6M shares, 2018) | Institutional Investor FOIA |
| Goldman Sachs | OWNS_SHARES | NY Fed | 4.0% (8.3M shares) | Institutional Investor FOIA |
| HSBC Bank USA | OWNS_SHARES | NY Fed | 6.1% (12.6M shares) | Institutional Investor FOIA |
| Deutsche Bank Trust | OWNS_SHARES | NY Fed | 0.87% combined | Institutional Investor FOIA |
| Bank of NY Mellon | OWNS_SHARES | NY Fed | 3.5% (7.2M shares) | Institutional Investor FOIA |
| Vanguard | OWNS_SHARES | JPMorgan | 9.84% (270.7M shares) | SEC 13F |
| BlackRock | OWNS_SHARES | JPMorgan | 4.82% (132.6M shares) | SEC 13F |
| State Street | OWNS_SHARES | JPMorgan | 4.56% (125.3M shares) | SEC 13F |
| Vanguard | OWNS_SHARES | BlackRock | ~9.04% (13.9M shares) | SEC 13F |
| BlackRock | OWNS_SHARES | BlackRock | Self-holding (second largest) | SEC 13F |
| BlackRock+Vanguard | OWNS_SHARES | S&P 500 companies | Largest shareholder in 40% of all US listed firms | CORPNET research |
| BlackRock+Vanguard | OWNS_SHARES | Gannett, Sinclair, Graham Media | Enough to be "insiders" under US law | Harvard analysis |
| BlackRock+Vanguard | INVESTED_IN | 63 blacklisted Chinese firms | $6.5B total ($1.9B each) | House Select Committee on CCP |

#### Lobbying Layer

| From | Relationship | To | Detail | Source |
|------|-------------|-----|--------|--------|
| US Chamber of Commerce | LOBBIED_FOR | PNTR (2000) | Part of $1.8B+ total lobbying | OpenSecrets |
| US Chamber of Commerce | LOBBIED_FOR | Immigration expansion | $1.5B on immigration 2008-2012 | OpenSecrets |
| US Chamber of Commerce | FILED_AMICUS | Trump tariff cases | Part of 37 anti-tariff briefs | Learning Resources v Trump |
| Virginia Lamp (Ginni Thomas) | EMPLOYS | US Chamber of Commerce | Immigration/labor lobbyist | ProPublica |
| 678 organizations | LOBBIED_FOR | Immigration expansion | 6,712 quarterly reports, 170 sectors | OpenSecrets aggregate |
| Chamber "America Works" | LOBBIED_FOR | Double immigrant visas | $17.6M lobbying 2021 | Chamber public filings |

#### Judicial Pipeline Layer

| From | Relationship | To | Detail | Source |
|------|-------------|-----|--------|--------|
| Ginni Thomas | MARRIED_TO | Clarence Thomas | — | Public record |
| Ginni Thomas | FORMERLY_KNOWN_AS | Virginia Lamp | Chamber lobbyist | ProPublica |
| Harlan Crow | DONATED_TO | Clarence Thomas | Undisclosed financial benefits | ProPublica |
| Crow network | DONATED_TO | Heritage Foundation | — | Tax filings |
| Heritage Foundation | CONNECTED_TO | Federalist Society | Judicial pipeline | Public record |
| Federalist Society | PIPELINE_TO | Supreme Court nominees | 6 current justices | Public record |
| Supreme Court | RULED_ON | Trump tariff cases | 6-3 against | Court records |
| 37 organizations | FILED_AMICUS | Against tariffs | vs 7 for | Learning Resources v Trump |

#### Economic Impact Layer

| Event | Detail | Source |
|-------|--------|--------|
| PNTR passage (2000) | Led to 2.4M manufacturing jobs lost | Pierce & Schott (academic) |
| China Shock | Exposed communities: increased mortality, disability, opioid deaths | Autor, Dorn, Hanson |
| Reshoring (2025-26) | 3.8M manufacturing jobs needed over next decade | Reshoring Initiative |
| Semiconductor reshoring | $102.6B, 2/3 of all foreign capital Oct 2024-Apr 2025 | Commerce Dept |
| Great Rotation 2026 | Russell 2000 outperforming S&P 500 by 4% in 6 weeks | Multiple financial sources |
| Small cap inflows | $600M+ single week into Russell 2000 | Financial press |

#### Correction Portfolio Layer

| Company | Ticker | Role in Correction | Key Data Point | Source |
|---------|--------|-------------------|----------------|--------|
| Caterpillar | CAT | Factory building | +28% YTD, $51B backlog, $725M Lafayette IN | Earnings/filings |
| Intel | INTC | Semiconductor sovereignty | +80% 2025, US govt 9.9% equity, 18A node | CHIPS Act/filings |
| Nucor | NUE | Domestic steel | "Nucor Data Systems" 95% data center steel | Company reports |
| Eaton | ETN | Grid modernization | Backlog through late 2027 | Earnings calls |
| Constellation Energy | CEG | Nuclear baseload | Largest US nuclear fleet | Company data |
| Freeport-McMoRan | FCX | Copper supercycle | Bagdad mine expansion (Arizona) | Filings |
| GE Aerospace | GE | Domestic manufacturing | +87.5%, 5,000 new US jobs | Announcements |
| Oracle | ORCL | Infrastructure sovereignty | 1.2GW Abilene TX, outside BV cross-ownership | Public filings |

#### Financial System Layer

| Entity | Role | Detail | Source |
|--------|------|--------|--------|
| Federal Reserve | Money creation | 12 regional banks owned by member commercial banks | Federal Reserve Act |
| NY Fed | Most powerful regional | Executed $29T in bailout 2007-2010 | GAO audit |
| BIS (Basel) | Central bank coordination | 63 member central banks, 95% world GDP | BIS website |
| BIS meetings | Policy coordination | Bimonthly, Sunday evening inner group dinner | BIS public schedule |
| GENIUS Act | Stablecoin framework | Signed into law 2025, 100% Treasury backing | White House fact sheet |
| Anti-CBDC Act | Banned Fed digital dollar | Passed House July 2025 | Congress.gov |
| Credit unions | Alternative circuit | Not Fed members, NCUA regulated, tax exempt | NCUA |

---

## System Architecture

### Phase 1 — MVP (Week 1-2)

**Goal:** Get the seed data into a queryable graph and build basic reasoning.

```
/fgip-engine/
├── data/
│   ├── seed_nodes.json          # All entities from tables above
│   ├── seed_edges.json          # All relationships from tables above
│   ├── sources.json             # Source URLs and metadata
│   └── transcripts/             # Raw conversation transcripts
├── graph/
│   ├── schema.py                # Node/edge type definitions
│   ├── loader.py                # Parse seed data into graph
│   ├── query.py                 # Query functions (shortest path, connected components, etc.)
│   └── db.py                    # Neo4j or SQLite connection layer
├── analysis/
│   ├── causality_chain.py       # Trace: lobby → legislation → economic impact → correction
│   ├── ownership_loop.py        # Map circular ownership (BV → banks → Fed → BV)
│   ├── amicus_tracker.py        # Track who files what in correction cases
│   ├── contradiction_detector.py # Flag: company filed anti-tariff amicus BUT announced reshoring
│   └── portfolio_scorer.py      # Score companies by position in causality chain
├── agents/                      # Phase 2
│   ├── sec_monitor.py           # Watch EDGAR for new filings
│   ├── lobbying_monitor.py      # Watch OpenSecrets API for new disclosures
│   ├── court_monitor.py         # Watch PACER for new filings in tracked cases
│   ├── news_monitor.py          # Watch RSS feeds for reshoring announcements
│   └── synthesis.py             # Cross-reference new data against existing graph
├── output/
│   ├── diagram_generator.py     # Auto-generate the FGIP map visualization
│   ├── thesis_updater.py        # Generate updated investment thesis narrative
│   ├── weekly_briefing.py       # Produce weekly FGIP bulletin
│   └── api.py                   # REST API for public access to graph data
├── web/                         # Phase 3
│   ├── public_explorer.html     # Interactive graph explorer for public
│   └── dashboard.html           # Portfolio + thesis tracking dashboard
├── requirements.txt
├── config.py
└── README.md
```

### Phase 1 Implementation — Tell Claude Code This:

```
Build a Python project that stores a knowledge graph of entities and 
relationships documenting how U.S. lobbying networks, ownership 
structures, judicial pipelines, and media capture created a 25-year 
economic distortion (offshoring via PNTR) and how it's being corrected 
(reshoring 2025+).

Start with:
1. SQLite database with tables for nodes (entities) and edges 
   (relationships), each with source attribution and timestamps
2. A loader script that ingests the seed data from JSON files
3. Query functions:
   - trace_causality(start_node, end_node) — find all paths connecting two entities
   - ownership_loop(entity) — map all ownership connections (who owns who)
   - contradiction_check(entity) — find where an entity's actions contradict 
     (e.g., filing anti-tariff amicus while announcing domestic factory)
   - correction_score(company) — score how directly a company benefits from 
     the reshoring correction based on its graph position
4. A simple CLI interface where I can:
   - Add new nodes and edges with sources
   - Query relationships
   - Generate a text summary of the causality chain for any topic
   - Export the graph as JSON for visualization

Use Python 3.11+, SQLite for storage, and keep it simple enough to run 
on a laptop. No cloud dependencies. All data stays local.
```

### Phase 2 — Agent Layer (Week 3-4)

```
Add monitoring agents that pull from public APIs and check new data 
against the existing knowledge graph:

1. SEC EDGAR agent: Monitor 13F filings for ownership changes in tracked 
   companies. Flag when BlackRock/Vanguard increase or decrease positions 
   in reshoring companies.

2. OpenSecrets agent: Pull new lobbying disclosures quarterly. Flag new 
   amicus briefs in tariff cases. Track Chamber of Commerce spending.

3. News agent: RSS feeds from Reuters, AP, financial press. NLP to detect 
   reshoring announcements (factory openings, job creation, capex). Auto-
   create ECONOMIC_EVENT nodes.

4. Contradiction detector: Cross-reference agent outputs. Example: If 
   Company X files anti-tariff amicus in Q1 then announces domestic 
   factory in Q2, flag it.

5. Portfolio tracker: Pull daily prices for watchlist companies. Calculate 
   correction-weighted returns (weight by causality chain position).

Each agent runs on a cron schedule. New findings get added to the graph 
with source attribution. A daily synthesis pass checks for new 
connections across agent outputs.
```

### Phase 3 — Public Interface (Week 5+)

```
Build a web interface (React or simple HTML/JS) that:

1. Shows the FGIP causality diagram as an interactive graph 
   (D3.js or Cytoscape.js). Users can click any node to see:
   - All documented relationships
   - Source links for every claim
   - Date of documentation

2. Dashboard showing:
   - Portfolio performance (correction-weighted)
   - Latest agent findings
   - Contradiction alerts
   - Weekly thesis update

3. Public API (REST) allowing:
   - Query any entity's relationships
   - Download graph data as JSON
   - Submit new data points for review (volunteer model)

Keep the frontend simple. The data is the product, not the UI.
```

---

## Key Principles for Claude Code

1. **Every claim needs a source.** No edge in the graph exists without a 
   source URL or document reference. This is what separates FGIP from 
   conspiracy theory. If you can't source it, don't store it.

2. **The graph is append-only.** Never delete historical relationships. 
   Mark them as superseded if ownership changes, but keep the history. 
   The timeline IS the thesis.

3. **Contradictions are features.** When the data contradicts itself, 
   that's a finding, not a bug. The contradiction detector is the most 
   valuable analytical tool.

4. **Start with what we have.** The seed data above represents ~8 hours 
   of documented research with sources. Load it first, build queries 
   around it, then add agents to expand it.

5. **This runs on a laptop.** No cloud, no API keys for core functionality. 
   An unemployed person should be able to run this. Cloud/APIs are 
   optional enhancements for the agent layer.

---

## What This Enables

When someone asks "why is Caterpillar stock going up?", the system can 
trace: 

PNTR(2000) → 2.4M jobs lost → factories closed → tariff correction(2025) 
→ OBBBA tax incentives → domestic factory investment → CAT $51B backlog 
→ CAT +28% YTD

And simultaneously show: 

Chamber of Commerce LOBBIED_FOR PNTR → Chamber FILED_AMICUS against 
tariff correction → Chamber member companies NOW INVESTING in domestic 
factories → Contradiction flagged

That's the thesis in a queryable database. That's what nobody else has built.
