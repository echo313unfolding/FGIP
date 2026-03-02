# FGIP Master Implementation Plan
## Fifth Generation Institute for Prosperity - Complete System Architecture

**Generated:** 2026-02-23
**Context:** Synthesized from 19 spec documents + 4,477-line conversation transcript

---

## EXECUTIVE SUMMARY

FGIP is a **dual-use intelligence platform** that:
1. **Exposes** the lobbying/ownership/judicial network that hollowed American manufacturing (1990-2025)
2. **Tracks** the reshoring correction (2025-present) as an investable thesis
3. **Connects** what no other institute connects: money → policy → consequences → correction → investment

**Core insight:** The same graph serves both missions. Investment thesis + transparency mission = same data, same evidence standards, same receipts.

---

## PART 1: GRAPH ARCHITECTURE

### 1.1 The Two-Sided Graph

```
PROBLEM LAYER                           CORRECTION LAYER
─────────────────────────────────────   ─────────────────────────────────────
Lobbying → PNTR → Job Loss              CHIPS Act → Intel Grant → Ohio Fab
Chamber → FILED_AMICUS → Anti-Tariff    GENIUS Act → FDIC → Stablecoin Framework
Koch → DONATED_TO → Cato                Nucor → BUILT_IN → Domestic Steel
PRC → REGISTERED_AS_AGENT → CUSEF       TSMC → RESHORING → Arizona

                    CORRECTS edges link the two layers
```

### 1.2 Node Types (17 total)

| Type | Description | Count Target |
|------|-------------|--------------|
| ORGANIZATION | Think tanks, lobbying orgs, NGOs | 50+ |
| PERSON | Key individuals (Thomas, Crow, Luckey, etc.) | 100+ |
| LEGISLATION | PNTR, CHIPS, GENIUS, OBBBA, etc. | 30+ |
| COURT_CASE | Learning Resources v Trump, Citizens United | 20+ |
| POLICY | Tariff schedules, immigration policy | 20+ |
| COMPANY | Caterpillar, Intel, HSBC, etc. | 200+ |
| MEDIA_OUTLET | Gannett, Sinclair, Substack journalists | 50+ |
| FINANCIAL_INST | NY Fed, BIS, BlackRock, Vanguard | 30+ |
| AMICUS_BRIEF | Individual filings with case reference | 50+ |
| ETF_FUND | RSHO, MADE, IWM | 15+ |
| ECONOMIC_EVENT | Factory openings, job losses, trade data | 100+ |
| AGENCY | FDIC, Treasury, Commerce, DOD | 20+ |
| FACILITY | Ohio Fab, Arizona Fab, etc. | 50+ |
| LOCATION | States, cities for facility mapping | 50+ |
| PROJECT | Stargate, specific CHIPS projects | 30+ |
| PROGRAM | CHIPS Act, IRA, IIJA programs | 20+ |
| CRIME_EVENT | Feeding Our Future, HSBC laundering | 20+ |

### 1.3 Edge Types (55 total across all layers)

#### Problem Layer Edges (25 types)
```
LOBBIED_FOR            - org → legislation, with dollar amount + year
LOBBIED_AGAINST        - org → legislation/policy
FILED_AMICUS          - org → court_case, with position (for/against)
OWNS_SHARES           - org → org, with percentage + date
EMPLOYS               - org → person, with role + dates
EMPLOYED              - person → org (reverse employment)
MARRIED_TO            - person → person
DONATED_TO            - person/org → org, with amount
APPOINTED_BY          - person → person
RULED_ON              - person → court_case, with vote
CAUSED                - legislation → economic_event (documented causal link)
OPPOSES_CORRECTION    - org → legislation (anti-tariff amicus, etc.)
OWNS_MEDIA            - org → media_outlet, with percentage
REPORTS_ON            - media_outlet → topic, with framing sentiment
MEMBER_OF             - org → financial_inst (Fed membership, BIS)
INVESTED_IN           - org → company, with amount + sector
SUPPLIES              - company → company (supply chain link)
REGISTERED_AS_AGENT   - person/org → foreign_principal (FARA)
ENABLED               - legislation/policy → crime/negative outcome
PROFITED_FROM         - entity → crime/harmful activity
COORDINATED_WITH      - entity → entity (documented coordination)
INVESTIGATED          - body → crime/entity
KILLED_INVESTIGATION  - AG/agency → investigation
CENSORED              - platform → content/person
FUNDED_NARRATIVE      - org → media outlet/think tank
```

#### Correction Layer Edges (15 types)
```
CORRECTS              - correction → problem it addresses
AUTHORIZED_BY         - program → legislation
IMPLEMENTED_BY        - legislation → agency
RULEMAKING_FOR        - agency → legislation
AWARDED_GRANT         - agency → company, with amount
AWARDED_CONTRACT      - agency → company, with amount
FUNDED_PROJECT        - program → project
BUILT_IN              - company → location (facility)
EXPANDED_CAPACITY     - company → facility
RESHORING_SIGNAL      - company → action (announced reshoring)
OPENED_FACILITY       - company → location
CREATED_JOBS          - company → location, with count
DOMESTIC_SOURCING     - company → supply chain shift
ONSHORED_PRODUCTION   - company → product/process
REDUCED_CHINA_EXPOSURE - company → measured reduction
```

#### Deep Intelligence Edges (15 types)
```
SUPPLIES_TO           - company → company (from 10-K)
CUSTOMER_OF           - company → company (revenue concentration)
COMPETES_WITH         - company → company (from Risk Factors)
ACQUIRED              - company → company (from 8-K)
SIGNED_CONTRACT       - company → government_entity (from 8-K)
INCREASED_POSITION    - institution → company (13F delta)
DECREASED_POSITION    - institution → company (13F delta)
SITS_ON_BOARD         - person → company (from DEF 14A)
FILED_PATENT          - company → technology_area
CO_FILED_PATENT_WITH  - company → company (joint invention)
HIRING_FOR            - company → role_type at location
WARNED_LAYOFF         - company → location (WARN Act)
WON_CONTRACT_FROM     - company → company (competitive win)
CEO_STATED            - person → claim (earnings call)
GUIDANCE_RAISED       - company → sector (bullish signal)
```

---

## PART 2: AGENT ARCHITECTURE

### 2.1 Agent Classification

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FGIP AGENT ECOSYSTEM                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  TIER 0: DATA COLLECTION AGENTS (Government Sources)                │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ FARAAgent         │ FederalRegisterAgent │ USASpendingAgent │   │
│  │ EDGARAgent        │ GAOAgent             │ FECAgent         │   │
│  │ CourtListenerAgent│ PatentAgent          │ CensusTrade      │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  TIER 1: JOURNALISM INTELLIGENCE AGENTS                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ OpenSecretsAgent  │ ProPublicaAgent      │ RSSSignalAgent   │   │
│  │ PodcastAgent      │ InvestigativeAgent   │ SubstackAgent    │   │
│  │ CitationLoader    │ MediaCoverageAgent   │ EarningsCallNLP  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  TIER 2: ANALYSIS & SYNTHESIS AGENTS                                │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ DarkMoneyMonitor  │ ContradictionDetector│ DivergenceTracker│   │
│  │ StateReplication  │ OppositionResearch   │ AIBiasAuditor    │   │
│  │ RiskScorer        │ SignalConvergence    │ PatternMatcher   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  TIER 3: SOLUTION AGENTS                                            │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ LegislativePatch  │ MarketCorrection     │ TransparencyEnf  │   │
│  │ ConstitutionalRep │ PortfolioScorer      │ ThesisValidator  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Phase 1 Agents (Already Implemented - Verify & Enhance)

| Agent | File | Status | Enhancement Needed |
|-------|------|--------|-------------------|
| CitationLoaderAgent | `fgip/agents/citation_loader.py` | ✅ Done | Add 1,033 URLs from database |
| FARAAgent | `fgip/agents/fara.py` | ✅ Done | Real API integration |
| OpenSecretsAgent | `fgip/agents/opensecrets.py` | ✅ Done | Bulk data download |
| USASpendingAgent | `fgip/agents/usaspending.py` | ✅ Done | CHIPS Act tracking |
| FederalRegisterAgent | `fgip/agents/federal_register.py` | ✅ Done | Real-time RSS |
| EDGARAgent | `fgip/agents/edgar.py` | ✅ Done | 10-K NLP extraction |
| SCOTUSAgent | `fgip/agents/scotus.py` | ✅ Done | Amicus brief tracking |
| GAOAgent | `fgip/agents/gao.py` | ✅ Done | Report parsing |
| RSSSignalAgent | `fgip/agents/rss_signal.py` | ✅ Done | Expand feed list |

### 2.3 Phase 2 Agents (To Build)

#### DI-1: SEC EDGAR Deep Crawler
```python
# fgip/agents/edgar_deep.py
class EDGARDeepCrawler(FGIPAgent):
    """
    Deep extraction from SEC filings:
    - 10-K Risk Factors: competitors, supplier concentration
    - 10-K Properties: facility locations
    - 8-K: contracts, acquisitions, facility openings
    - DEF 14A: board members, related-party transactions
    - 13-F: institutional ownership changes
    - SC 13D/G: activist positions >5%
    - Exhibit 10: material contract text
    """
    EDGE_TYPES = [
        'SUPPLIES_TO', 'CUSTOMER_OF', 'COMPETES_WITH', 'ACQUIRED',
        'SIGNED_CONTRACT', 'OPENED_FACILITY', 'INCREASED_POSITION',
        'SITS_ON_BOARD', 'RELATED_PARTY_TRANSACTION'
    ]
```

#### DI-2: Government Contract Intelligence
```python
# fgip/agents/contracts_deep.py
class GovernmentContractAgent(FGIPAgent):
    """
    Sources: USASpending.gov, SAM.gov, FPDS, SBIR.gov
    Tracks: CHIPS Act, IRA, IIJA disbursements
    """
    EDGE_TYPES = [
        'AWARDED_CONTRACT', 'SUBCONTRACTED_TO', 'PERFORMED_WORK_AT',
        'DEBARRED_BY', 'COMPETED_WITH', 'FUNDED', 'BUILT_FACILITY'
    ]
```

#### DI-3: Trade Flow Intelligence
```python
# fgip/agents/trade_flow.py
class TradeFlowAgent(FGIPAgent):
    """
    Sources: Census USA Trade Online, USITC DataWeb
    Tracks: Import/export by HS code, tariff impacts
    """
    EDGE_TYPES = [
        'EXPORTS_TO', 'IMPORTS_FROM', 'SHIFTED_SOURCING',
        'TARIFF_APPLIED_TO', 'TRADE_REMEDY_FILED'
    ]
```

#### DI-4: Earnings Call NLP
```python
# fgip/agents/earnings_nlp.py
class EarningsCallAgent(FGIPAgent):
    """
    Sources: Seeking Alpha, SEC 8-K transcripts, company IR
    Extracts: Customer wins, facility announcements, reshoring signals
    """
    EDGE_TYPES = [
        'CEO_STATED', 'WON_CONTRACT_FROM', 'EXPANDING_FACILITY',
        'REDUCING_EXPOSURE_TO', 'GUIDANCE_RAISED'
    ]
```

#### DI-5: Patent Tracker
```python
# fgip/agents/patents.py
class PatentTrackerAgent(FGIPAgent):
    """
    Sources: USPTO PatentsView, Google Patents
    """
    EDGE_TYPES = ['FILED_PATENT', 'CO_FILED_PATENT_WITH', 'LICENSED_TO']
```

#### DI-6: Job Posting Intelligence
```python
# fgip/agents/jobs.py
class JobPostingAgent(FGIPAgent):
    """
    Sources: Indeed API (MCP), LinkedIn, H-1B DOL data
    """
    EDGE_TYPES = ['HIRING_FOR', 'EXPANDING_WORKFORCE', 'FILED_WARN_ACT']
```

#### DI-7: Institutional Flow Tracker
```python
# fgip/agents/institutional_flow.py
class InstitutionalFlowAgent(FGIPAgent):
    """
    Sources: 13-F filings, Form 3/4/5, ETF holdings
    """
    EDGE_TYPES = [
        'INITIATED_POSITION', 'INCREASED_POSITION', 'EXITED_POSITION',
        'INSIDER_BOUGHT', 'INSIDER_SOLD', 'ETF_ADDED', 'ETF_REMOVED'
    ]
```

#### DI-8: Dark Money Monitor
```python
# fgip/agents/dark_money.py
class DarkMoneyAgent(FGIPAgent):
    """
    Sources: IRS 990s (ProPublica), state campaign finance, FEC
    Patterns: Michigan/Ohio templates applied nationally
    """
    PATTERNS = {
        'michigan_bipartisan_solutions': {...},
        'ohio_firstenergy': {...},
        'pass_through_chain': {...}
    }
```

#### DI-9: Court Filing Monitor
```python
# fgip/agents/court_monitor.py
class CourtFilingAgent(FGIPAgent):
    """
    Sources: CourtListener/RECAP, DOJ press, SEC enforcement
    Critical: Non-action detection (evidence exists but no prosecution)
    """
    EDGE_TYPES = [
        'INDICTED', 'CHARGED', 'SUED', 'FILED_AMICUS',
        'SETTLED_WITH', 'DISMISSED', 'DECLINED_TO_PROSECUTE'
    ]
```

#### DI-10: Media & Narrative Monitor
```python
# fgip/agents/media_narrative.py
class MediaNarrativeAgent(FGIPAgent):
    """
    Sources: GDELT, Media Cloud, AllSides
    Tracks: Coverage vs non-coverage, framing variance
    """
    EDGE_TYPES = ['COVERED_BY', 'NOT_COVERED_BY', 'FRAMING_DIVERGENCE']
```

#### DI-11: Lobbyist Activity Tracker
```python
# fgip/agents/lobbyist_tracker.py
class LobbyistActivityAgent(FGIPAgent):
    """
    Sources: Senate LDA, FARA, state registrations, OpenSecrets
    """
    EDGE_TYPES = ['LOBBIED_FOR', 'REVOLVING_DOOR', 'REPRESENTS']
```

### 2.4 Phase 3 Agents (Specialized)

#### Podcast Intelligence Agent
```python
# fgip/agents/podcast.py
class PodcastIntelligenceAgent(FGIPAgent):
    """
    The 3-hour conversation produces more signal than a year of cable news.

    Tier 0 Podcast Sources:
    - Lex Fridman, Sean Ryan Show, Julian Dorey
    - Joe Rogan, Tucker Carlson, PBD Podcast
    - All-In Podcast, Breaking Points, Glenn Greenwald
    - Macro Voices, Real Vision, George Gammon

    Key Features:
    - Reference chain following (podcast → expert → study → data → gov source)
    - Claim extraction (factual claims only, not opinions)
    - Speaker diarization and identification
    - YouTube algorithm as intelligence signal
    """

    def follow_reference_chain(self, reference, max_depth=3):
        """Recursively follow references until hitting Tier 0."""
        pass
```

#### Investigative Narrative Agent
```python
# fgip/agents/investigative.py
class InvestigativeNarrativeAgent(FGIPAgent):
    """
    Two streams, one graph:

    Stream A: INVESTIGATIVE SIGNAL
    - ProPublica, Bridge Michigan, The Intercept
    - OCCRP, ICIJ, Bellingcat, POGO, MuckRock
    - Charlie LeDuff, Matt Taibbi, Glenn Greenwald

    Stream B: LOBBY RHETORIC
    - Heritage, Cato, Brookings, AEI
    - Chamber of Commerce, industry trade groups
    - Placed op-eds, astroturf orgs

    DIVERGENCE DETECTION:
    - Finding vs Denial
    - Evidence vs Framing
    - Coverage vs Silence
    - Timing Divergence
    - Source Quality Divergence
    """
```

### 2.5 Solution Agents

#### Legislative Patch Agent
```python
# fgip/agents/legislative_patch.py
class LegislativePatchAgent(FGIPAgent):
    """
    For every documented loophole, find legislation that closes it.

    Sources: NCSL, Brennan Center, Congress.gov, LegiScan

    Problem → Solution Mapping:
    - Dark money via 501(c)(4) → CA DISCLOSE Act model
    - AG conflict of interest → Independent prosecutor statutes
    - Revolving door → 5-year cooling-off period
    - No-bid earmarks → Mandatory competitive bidding
    """
```

#### AI Training Bias Auditor
```python
# fgip/agents/ai_bias.py
class AIBiasAuditor(FGIPAgent):
    """
    Test whether AI models reproduce captured media narratives.

    For each documented claim in graph:
    1. Ask 5+ LLMs the same question
    2. Compare to Tier 0 government data
    3. Compare to dominant media narrative
    4. Score alignment/divergence

    Output: Narrative Distortion Index per topic
    """
```

---

## PART 3: LAYERS & SCORING

### 3.1 Signal Layer (Independent Media Validation)

```json
{
  "signal_sources": [
    {"name": "Shawn Ryan Show", "type": "podcast", "topics": ["defense", "intelligence"]},
    {"name": "Sarah Adams (CIA)", "type": "whistleblower", "topics": ["infiltration", "border"]},
    {"name": "Tucker Carlson Network", "type": "independent", "topics": ["institutional_capture"]},
    {"name": "Substack Ecosystem", "type": "journalism", "topics": ["industrial_decline"]}
  ],
  "edge_type": "VALIDATES",
  "confidence_boost": 0.15
}
```

### 3.2 Accountability Layer (Crime/Fraud Nodes)

```json
{
  "crime_nodes": [
    {"id": "crime_feeding_our_future", "type": "fraud", "amount": 250000000, "location": "Minnesota"},
    {"id": "crime_hsbc_laundering", "type": "money_laundering", "fine": 1920000000},
    {"id": "crime_fentanyl_pipeline", "type": "narcotics", "deaths_per_year": 100000},
    {"id": "crime_forced_labor_xinjiang", "type": "human_rights_abuse"},
    {"id": "crime_censorship_infrastructure", "type": "government_overreach"}
  ]
}
```

### 3.3 Risk Management Layer

#### Thesis Risk Score (0-100)
```python
def thesis_risk_score(claim_or_path):
    """
    Factors:
    - Source tier (Tier 0 = +30, Tier 1 = +20, Tier 2 = +5)
    - Independent validation count (+10 each)
    - Signal layer confirmation (+10 each)
    - Accountability confirmation (+15 for criminal cases)
    - Contradiction check (+10 if entity contradicts itself)
    - Time consistency (+10 if verified across years)
    """
```

#### Investment Risk Score (0-100)
```python
def investment_risk_score(company):
    """
    Risk UP:
    - Filed anti-tariff amicus (+30)
    - BlackRock/Vanguard top shareholders (+10)
    - Revenue dependent on China trade (+20)
    - Single customer concentration (+10)

    Risk DOWN:
    - Government equity stake (-20)
    - Bipartisan support for correction (-15)
    - Physical assets already built (-15)
    - Domestic supply chain (-10)
    """
```

#### Signal Convergence Score
```python
def signal_convergence(topic):
    """
    Count independent signal categories confirming:
    1. Government officials validating
    2. Independent media covering
    3. Academic research confirming
    4. Market data confirming
    5. Criminal cases confirming
    6. Industry insiders confirming

    5-6 categories = extremely high confidence
    3-4 = high confidence
    1-2 = needs more validation
    """
```

---

## PART 4: IMPLEMENTATION ROADMAP

### Phase 1: Foundation (Weeks 1-2) - COMPLETED
- [x] SQLite database with nodes/edges/claims/sources
- [x] FK-safe staging pipeline with prelint
- [x] Basic agents: FARA, OpenSecrets, USASpending, FederalRegister
- [x] Correction layer manifest loading
- [x] CLI interface
- [x] 120 nodes, 88 edges operational

### Phase 2: Deep Intelligence (Weeks 3-6)
- [ ] DI-1: EDGAR Deep Crawler (10-K NLP)
- [ ] DI-2: Government Contract tracking (CHIPS Act)
- [ ] DI-3: Trade Flow intelligence
- [ ] DI-4: Earnings Call NLP
- [ ] DI-7: Institutional Flow Tracker (13-F)
- [ ] Load full citation database (1,033 URLs)

### Phase 3: Investigative Layer (Weeks 7-10)
- [ ] DI-8: Dark Money Monitor (990s, pattern detection)
- [ ] DI-9: Court Filing Monitor (CourtListener)
- [ ] DI-10: Media Narrative Monitor
- [ ] DI-11: Lobbyist Activity Tracker
- [ ] Podcast Intelligence Agent (reference chain engine)
- [ ] Investigative Narrative Agent (divergence tracking)

### Phase 4: Analysis & Solutions (Weeks 11-14)
- [ ] Risk Management Layer (thesis + investment scoring)
- [ ] Signal Convergence scoring
- [ ] Contradiction Detector
- [ ] Legislative Patch Agent
- [ ] AI Training Bias Auditor
- [ ] State Replication Agent

### Phase 5: Public Interface (Weeks 15-18)
- [ ] Web UI with D3/Cytoscape visualization
- [ ] Interactive sunburst chart
- [ ] Counter-thesis tracker visualization
- [ ] Public REST API
- [ ] Weekly briefing generator

### Phase 6: Content & Distribution (Weeks 19+)
- [ ] FGIP series episode outlines
- [ ] Angel Studios pitch deck
- [ ] ETF licensing documentation
- [ ] Research subscription product

---

## PART 5: KEY DATA TO LOAD

### Immediate Priority: Citation Database (1,033 URLs)

The `fgip_citation_database.md` file contains 1,033 unique source URLs across 11 categories:
1. Lobbying Network (PNTR, Chamber, revolving door)
2. Judicial Pipeline (Ginni Thomas, Harlan Crow, amicus briefs)
3. Ownership Structure (Fed ownership, BlackRock/Vanguard)
4. Downstream Consequences (fentanyl, forced labor, defense collapse)
5. Censorship Infrastructure (CISA, Haugen, AI control)
6. Reshoring/Correction (CHIPS, GENIUS, ETFs)
7. Think Tank Network (Cato, Heritage funding)
8. Independent Media (Substack, alternative infrastructure)
9. Fraud/Accountability (Minnesota, HSBC)
10. Stablecoin/Financial Alternatives
11. Rubio/Foreign Policy Framework

### Counter-Thesis Tracker Entities

From `fgip_counter_thesis.jsx` - entities that CAUSED the problems:
- US Chamber of Commerce ($1.8B lobbying)
- Bloomberg LP ($150B CCP bonds)
- Harlan Crow (Thomas gifts)
- Ginni Thomas ($680K Heritage)
- BlackRock/Vanguard ($6.5B in blacklisted Chinese companies)
- PNTR supporters (tracked by vote)

### FGIP Index Holdings (35 public companies)

From `fgip_index_prices.xlsx` - the correction portfolio:
```
Sector: Industrial Automation (7 stocks, ~$2,683)
Sector: Pharma/API (6 stocks, ~$1,850)
Sector: Energy/Grid (4 stocks, ~$1,654)
Sector: Shipbuilding/Defense (4 stocks, ~$1,471)
Sector: Semiconductors (5 stocks, ~$1,081)
Sector: Steel/Materials
Sector: Rare Earth/Critical Minerals
Sector: Consumer Reshoring
Sector: AI Infrastructure

Total: $10,355.66 for one share of each
```

---

## PART 6: SUCCESS METRICS

### Graph Completeness
- [ ] Every problem edge has corresponding correction edge
- [ ] Every correction edge has opposition mapping
- [ ] 90%+ edges have Tier 0/1 sources
- [ ] Zero edges without source attribution

### Agent Coverage
- [ ] All 11 Deep Intelligence agents operational
- [ ] All 7 Solution agents operational
- [ ] Podcast agent processing 50+ shows
- [ ] Dark money monitor scanning all 50 states

### Investment Thesis Validation
- [ ] Signal convergence 5+/6 on reshoring thesis
- [ ] IWM/RSHO outperformance tracked
- [ ] FGIP index returns documented
- [ ] Contradiction alerts for all amicus filers

### Public Reach
- [ ] Interactive graph explorer live
- [ ] Weekly briefing subscribers
- [ ] ETF partnership discussions
- [ ] Angel Studios pitch delivered

---

## APPENDIX: Key Quotes from Research

**The Gap FGIP Fills:**
> "Nobody is connecting all of it. Not one article, not one analyst, not one institute. The lobbying data, the capital flows, the media ownership, the judicial pipeline, the AI training bias, the reshoring correction - Wall Street is literally making money on the correction side of your thesis right now. They just don't know WHY the correction is happening at the structural level you've mapped."

**The Dual-Use Thesis:**
> "The same graph serves both missions simultaneously. Investment side: 'Company X is growing because CHIPS Act money flows to its customer.' Exposure side: 'Company Y's competitor is spending $2M lobbying through a 501(c)(4) that doesn't disclose its foreign corporate funders.' BOTH SIDES USE THE SAME EVIDENCE STANDARDS."

**The Bloomberg Analogy:**
> "FGIP does the same thing Bloomberg built but organized around the thesis. The index tracks the companies. The research papers explain WHY the index is constructed the way it is. The independent journalist network provides content. And Learning Resources v. Trump is the founding exhibit that shows the institutional resistance."

**Why This Doesn't Exist:**
> "Palantir does the investment/intelligence side but costs $100M+/year and doesn't expose corruption. OpenSecrets does transparency but doesn't connect to market data. Bloomberg Terminal does financial data but no corruption overlay. FGIP = Bloomberg + Palantir + OpenSecrets + ProPublica on a public graph with receipts for every edge."
