# FGIP Deep Intelligence Agents
## "Palantir-depth, open-source, serving both the investment thesis AND the exposure mission"

### Why This Is Different From the Solution Agents

The Solution Agents (spec v1) operate at POLICY level — "here's the loophole, here's the fix."
These Deep Intelligence Agents operate at ENTITY level — "here's the company, here's their 
supplier, here's their supplier's supplier, here's the contract, here's who lost the contract, 
here's who's lobbying to reverse it."

Same graph. Same evidence standards. But grain-level depth that turns the graph from a 
research tool into a live intelligence platform.

---

## INVESTMENT INTELLIGENCE LAYER

### Agent DI-1: SEC EDGAR Deep Crawler
**Purpose:** Extract supply chain, customer, contract, and risk relationships from public filings.

**What It Reads:**
- **10-K Annual Reports** — "Risk Factors" section names competitors; "Properties" section reveals facilities; supplier concentration disclosures (required when >10% revenue from single customer)
- **10-Q Quarterly Reports** — Material contract changes, new customer wins, supplier disruptions
- **8-K Current Reports** — Real-time: new contracts, acquisitions, executive departures, facility openings
- **DEF 14A Proxy Statements** — Executive compensation, board members, related-party transactions
- **13-F Institutional Holdings** — Every quarter: who owns what. BlackRock increases position in reshoring company = signal
- **SC 13D/G** — Activist investors taking positions >5%. Someone accumulating a reshoring small-cap = signal
- **Material Contracts (Exhibit 10)** — Actual contract text filed as exhibits. Supplier agreements, licensing deals, government contracts

**Edge Types Generated:**
```
COMPANY_X → SUPPLIES_TO → COMPANY_Y (from 10-K supplier disclosure)
COMPANY_X → CUSTOMER_OF → COMPANY_Y (from revenue concentration disclosure)
COMPANY_X → COMPETES_WITH → COMPANY_Y (from Risk Factors section)
COMPANY_X → ACQUIRED → COMPANY_Y (from 8-K)
COMPANY_X → SIGNED_CONTRACT → GOVERNMENT_ENTITY (from 8-K + Exhibit 10)
COMPANY_X → OPENED_FACILITY → LOCATION (from 8-K/10-K Properties)
INSTITUTION → INCREASED_POSITION → COMPANY_X (from 13-F delta)
INSTITUTION → DECREASED_POSITION → COMPANY_X (from 13-F delta)
BOARD_MEMBER → SITS_ON_BOARD → COMPANY_X (from DEF 14A)
BOARD_MEMBER → SITS_ON_BOARD → COMPANY_Y (shared director = connection)
EXECUTIVE → RELATED_PARTY_TRANSACTION → ENTITY (from proxy)
```

**Depth Example — A Reshoring Small-Cap:**
```
Moog Inc. (MOG.A) — precision motion control, defense/aerospace
├── 10-K reveals: 68% revenue from defense/aerospace
│   ├── CUSTOMER: Lockheed Martin (F-35 flight control actuators)
│   ├── CUSTOMER: Boeing (defense programs)
│   └── CUSTOMER: Northrop Grumman (B-21 program)
├── 10-K Properties: 12 US manufacturing facilities
│   ├── East Aurora, NY (HQ + manufacturing)
│   ├── Torrance, CA (space & defense)
│   └── Salt Lake City, UT (components)
├── 8-K filed Jan 2026: Won $47M contract for [specific program]
├── 10-K Risk Factors: "Certain components sourced from limited suppliers"
│   ├── SUPPLIER: [specific raw material vendor]
│   └── SUPPLIER: [specific electronics component vendor]
├── 13-F tracking: Vanguard increased from 9.2% → 10.1% (Q4 2025)
├── DEF 14A: Board member also sits on [defense think tank] board
└── GRAPH EDGE TO THESIS: Benefits from CHIPS Act (electronic components),
    IIJA (infrastructure), defense reshoring mandate (Berry Amendment)
```

That single company generates 15-20 graph edges from public filings alone. Multiply by every 
company in RSHO ETF (40+ holdings) and Russell 2000 reshoring candidates.

**Implementation:**
- SEC EDGAR FULL-TEXT SEARCH API (efts.sec.gov) — free, no key needed
- XBRL structured data for financial figures
- NLP extraction for unstructured sections (Risk Factors, MD&A)
- Quarterly poll on all tracked entities + real-time 8-K RSS feed

---

### Agent DI-2: Government Contract Intelligence
**Purpose:** Track every federal contract, grant, and sub-award flowing to companies in the graph. This is where CHIPS Act / IIJA / IRA money actually goes.

**Data Sources:**
- **USASpending.gov API** — $7T+ in federal spending, searchable by company, agency, program
- **SAM.gov** — System for Award Management. Every entity doing business with federal government registered here. Shows: entity details, exclusions (debarments), sub-awards
- **FPDS (Federal Procurement Data System)** — Contract-level detail: who won, who lost, dollar amount, period of performance, place of performance
- **SBIR.gov** — Small Business Innovation Research awards. Early-stage defense/tech companies.

**Edge Types Generated:**
```
AGENCY → AWARDED_CONTRACT → COMPANY ($amount, date, program)
COMPANY → SUBCONTRACTED_TO → COMPANY_B ($amount)
COMPANY → PERFORMED_WORK_AT → FACILITY/LOCATION
COMPANY → DEBARRED_BY → AGENCY (exclusion = red flag)
COMPANY → COMPETED_WITH → COMPANY_B (lost bids on same solicitation)
PROGRAM (CHIPS Act) → FUNDED → COMPANY → BUILT_FACILITY → STATE
```

**Depth Example — CHIPS Act Money Flow:**
```
CHIPS & Science Act ($52.7B authorized)
├── Intel Corporation
│   ├── $8.5B direct funding (announced March 2024)
│   ├── Ohio fab (New Albany) — $20B investment, 3,000 jobs
│   │   ├── CONSTRUCTION: [general contractor]
│   │   ├── EQUIPMENT: ASML (lithography), Applied Materials, Lam Research
│   │   └── MATERIALS: [silicon wafer supplier], [chemical supplier]
│   ├── Arizona fab (Chandler) — expansion
│   └── Oregon fab (Hillsboro) — advanced packaging
├── TSMC Arizona
│   ├── $6.6B direct funding
│   ├── Phoenix fab — $40B total investment
│   │   ├── CONSTRUCTION: [general contractor]  
│   │   ├── EQUIPMENT: Same equipment vendors (ASML, Applied Materials)
│   │   └── WORKFORCE: 4,500 direct jobs
│   └── SUB-AWARDS traceable via SAM.gov
├── Samsung Texas
│   ├── $6.4B direct funding
│   └── Taylor, TX fab — $17B investment
└── EVERY DOLLAR traceable from authorization → appropriation → award → sub-award → facility → job
```

The supply chain of a SINGLE fab generates 50+ graph edges. Equipment suppliers, construction 
firms, material vendors, workforce training programs — all connected, all documented in 
government databases.

**Investment Signal:** When USASpending shows a new sub-award to a small company you've never 
heard of, and that company is in the Russell 2000, that's EARLY intelligence. The contract is 
public record before Wall Street covers it.

---

### Agent DI-3: Import/Export & Trade Flow Intelligence
**Purpose:** Track what's actually moving across borders. Reshoring thesis says imports from China decrease, domestic production increases. This agent proves or disproves that with customs data.

**Data Sources:**
- **Census Bureau USA Trade Online** — Monthly import/export data by HS code, country, port
- **International Trade Commission (USITC) DataWeb** — Tariff rates, trade remedy cases, exclusion requests
- **ImportGenius / Panjiva** (commercial, but some data via FOIA) — Bill of lading data showing specific company-to-company shipments
- **BLS Producer Price Index** — Domestic production price trends by sector
- **Federal Reserve Industrial Production Index** — Monthly output by sector

**Edge Types Generated:**
```
COUNTRY → EXPORTS_TO → US ($amount, HS_code, product)
US_COMPANY → IMPORTS_FROM → FOREIGN_COMPANY (bill of lading)
US_COMPANY → SHIFTED_SOURCING_FROM → COUNTRY_A → TO → COUNTRY_B
TARIFF → APPLIED_TO → HS_CODE → AFFECTS → COMPANY
TRADE_REMEDY_CASE → FILED_BY → US_COMPANY → AGAINST → FOREIGN_COMPANY
```

**Depth Example — Steel Reshoring Signal:**
```
Steel tariffs (Section 232, maintained 2018-present)
├── Import volume: China steel imports ↓ 87% since 2018
├── Domestic production: US steel capacity utilization ↑ to ~78%
├── Beneficiaries (Russell 2000 / small-cap):
│   ├── Olympic Steel (ZEUS) — service center, sources domestic
│   │   ├── SUPPLIERS: Nucor, Steel Dynamics, Cleveland-Cliffs
│   │   ├── CUSTOMERS: Traceable from 10-K
│   │   └── FACILITY EXPANSIONS: [documented from 8-K filings]
│   ├── Haynes International (HAYN) — specialty alloys
│   │   ├── SUPPLIES_TO: Aerospace (GE, Pratt & Whitney)
│   │   ├── SUPPLIES_TO: Chemical processing
│   │   └── BENEFITS_FROM: Both tariffs AND defense spending
│   └── Northwest Steel Fabricators [private] — sub-awards on infrastructure projects
├── Losers (who lobbied against tariffs):
│   ├── Auto importers (filed 37 amicus briefs against tariff authority)
│   ├── Chamber of Commerce ($1.8B total lobby spend, anti-tariff position)
│   └── Specific companies that filed exclusion requests (public record at USITC)
└── NET EFFECT: Measurable via BLS employment (steel jobs ↑ 5,300 since tariffs)
```

---

### Agent DI-4: Earnings Call NLP Engine
**Purpose:** Every public company does quarterly earnings calls. CEOs and CFOs name customers, suppliers, competitors, and strategic priorities ON THE RECORD. This is unstructured gold.

**What It Extracts:**
- **Named entities:** Customer wins ("we signed a multi-year agreement with [Company]")
- **Supplier mentions:** "We're seeing improved lead times from our domestic suppliers"
- **Facility announcements:** "We're investing $200M in our Texas facility"
- **Reshoring signals:** "We've moved 40% of our sourcing back to North America"
- **Risk signals:** "Our China exposure has decreased from 35% to 18%"
- **Competitor mentions:** Analyst questions often name competitors directly
- **Guidance language:** Bullish/bearish signals extractable via sentiment

**Data Sources:**
- **Seeking Alpha / Motley Fool transcripts** (free tier available)
- **SEC EDGAR 8-K** — Some companies file transcripts
- **Company investor relations pages** — Direct source

**Edge Types Generated:**
```
CEO → STATED → "moved sourcing to domestic" (dated, quotable)
COMPANY → WON_CONTRACT_FROM → CUSTOMER (earnings call announcement)
COMPANY → EXPANDING_FACILITY → LOCATION (capex announcement)
COMPANY → REDUCING_EXPOSURE_TO → COUNTRY (supply chain shift)
COMPANY → GUIDANCE_RAISED → SECTOR (bullish signal)
ANALYST → ASKED_ABOUT → COMPETITOR (reveals market awareness)
```

**Depth Example:**
```
Earnings call: Insteel Industries (IIIN) Q3 2025
├── CEO: "Infrastructure spending driving record backlog"
│   ├── EDGE: IIJA → BENEFITS → Insteel (steel wire products for construction)
│   ├── EDGE: Insteel → BACKLOG_RECORD → $XXM
│   └── EDGE: Insteel → SUPPLIES_TO → Infrastructure contractors
├── CFO: "Raw material sourcing now 92% domestic, up from 78% three years ago"
│   ├── EDGE: Insteel → SHIFTED_SOURCING → Domestic (quantified)
│   └── EDGE: Insteel → REDUCED_IMPORT_DEPENDENCE → 78% → 92% domestic
├── Analyst question: "How does Nucor's capacity expansion affect your input costs?"
│   ├── EDGE: Insteel → SOURCES_FROM → Nucor (confirmed by Q&A)
│   └── EDGE: Nucor → CAPACITY_EXPANSION → Affects → Insteel input costs
└── All of this is ON THE RECORD, datestamped, attributable to named executives
```

---

### Agent DI-5: Patent & Innovation Tracker
**Purpose:** Patents reveal where companies are investing R&D 12-24 months before products ship. A small-cap filing patents in advanced manufacturing, semiconductor packaging, or defense systems = early signal.

**Data Sources:**
- **USPTO PatentsView API** — Free, comprehensive, searchable by assignee, class, date
- **Google Patents** — Full text search across global patent offices
- **WIPO** — International patent filings

**Edge Types Generated:**
```
COMPANY → FILED_PATENT → TECHNOLOGY_AREA
COMPANY → CO_FILED_PATENT_WITH → COMPANY_B (joint invention = partnership signal)
INVENTOR → PREVIOUSLY_AT → COMPANY_A → NOW_AT → COMPANY_B (talent flow)
PATENT → CITES → EARLIER_PATENT (technology dependency chain)
GOVERNMENT_LAB → LICENSED_TO → COMPANY (national lab tech transfer)
```

---

### Agent DI-6: Job Posting Intelligence
**Purpose:** Hiring = growth signal. WHO a company is hiring reveals strategy 6-12 months before earnings show it. A small-cap posting 50 manufacturing engineer jobs at a new facility = capacity expansion before it's announced.

**Data Sources:**
- **Indeed API** (we have access via MCP)
- **LinkedIn job postings** (scraping or API)
- **H-1B visa data** (DOL public disclosure) — reveals specialized talent needs
- **State workforce agency data** — WARN Act layoff notices (negative signal)

**Edge Types Generated:**
```
COMPANY → HIRING_FOR → ROLE_TYPE → AT → LOCATION
COMPANY → EXPANDING_WORKFORCE → FACILITY (job count delta)
COMPANY → FILED_WARN_ACT → LOCATION (layoff signal)
COMPANY → HIRING_FROM → COMPETITOR (talent poaching = competitive signal)
COMPANY → H1B_PETITION → SPECIALTY (reveals technical direction)
```

**Depth Example:**
```
Job postings scan: February 2026
├── Company X (Russell 2000, defense electronics): 
│   ├── 23 new postings in Salt Lake City — all RF engineering
│   ├── 8 new postings in Huntsville, AL — systems integration
│   ├── SIGNAL: Expanding into directed energy / electronic warfare
│   ├── CONNECT TO: DOD budget line items for EW spending
│   └── CONNECT TO: Competitors losing similar roles (LinkedIn departures)
├── Company Y (RSHO holding, industrial automation):
│   ├── 41 new postings at NEW facility address not in any prior filing
│   ├── SIGNAL: Facility expansion not yet in 8-K
│   └── EARLY INTELLIGENCE: Market doesn't know about this yet
```

---

### Agent DI-7: Institutional Flow Tracker
**Purpose:** Track what smart money is actually doing, not what they're saying. 13-F filings, insider transactions, ETF rebalancing.

**Data Sources:**
- **SEC 13-F filings** — Every institutional investor >$100M files quarterly holdings
- **SEC Forms 3, 4, 5** — Insider buying/selling (CEO buying own stock = confidence signal)
- **ETF holdings files** — Daily holdings for RSHO, IWM, sector ETFs
- **WhaleWisdom / Dataroma** (aggregators, but original data is SEC)

**Edge Types Generated:**
```
INSTITUTION → INITIATED_POSITION → COMPANY ($value, shares, quarter)
INSTITUTION → INCREASED_POSITION → COMPANY (% change quarter over quarter)
INSTITUTION → EXITED_POSITION → COMPANY (sold everything = bearish)
INSIDER → BOUGHT → OWN_COMPANY ($amount, date — Form 4)
INSIDER → SOLD → OWN_COMPANY ($amount, date)
ETF → ADDED → COMPANY (rebalancing signal)
ETF → REMOVED → COMPANY
INSTITUTION_A → CONVERGING_WITH → INSTITUTION_B (both buying same small-cap = signal)
```

---

## INVESTIGATIVE INTELLIGENCE LAYER

### Agent DI-8: Continuous Dark Money Monitor
**Purpose:** Don't just map dark money once — watch it in real time. New 501(c)(4) filings, new ballot committee registrations, new IRS 990s, new state campaign finance reports.

**Data Sources:**
- **IRS Tax Exempt Organization Search** — New 501(c)(3) and 501(c)(4) registrations
- **IRS 990 e-file data** (via ProPublica Nonprofit Explorer) — Annual financials for every tax-exempt org
- **State campaign finance databases** (each state has one, FollowTheMoney.org aggregates)
- **FEC.gov** — Federal PACs, super PACs, independent expenditures
- **State ballot committee registrations** — New committees forming for 2026 ballot initiatives

**What It Watches For:**
```
NEW 501(c)(4) registered → WHO are the officers?
  → Do officers appear in graph? (lobbyist, former official, donor)
  → Does registered address match known lobbying firm?
  → Is formation date suspiciously close to legislative action or ballot initiative?

NEW BALLOT COMMITTEE formed → WHO are the funders?
  → Do funders overlap with existing dark money network?
  → Is the "opposition committee" funded by entities the initiative would regulate?
  → (Michigan example: utility companies funding committee opposing utility donation ban)

990 FILED → WHERE did the money go?
  → Grants to other nonprofits (pass-through detection)
  → Payments to individuals (officer compensation)
  → "Consulting fees" to connected entities
```

**Pattern Detection:**
```python
class DarkMoneyPatternDetector:
    """Detects structural patterns matching known dark money architectures."""
    
    KNOWN_PATTERNS = {
        "michigan_bipartisan_solutions": {
            # Pattern: 501c4 → ballot committee → >50% of funding → no donor disclosure
            "signals": [
                "single_source_majority_funding",  # One org provides >50% of committee funds
                "c4_to_ballot_committee",           # Tax-exempt org funding ballot measure
                "undisclosed_donors",               # 501c4 doesn't disclose donors
                "connected_officers"                # Officers connected to benefiting candidate
            ]
        },
        "ohio_firstenergy": {
            # Pattern: corporation → 501c4 → elected official's campaign → favorable legislation
            "signals": [
                "corporate_to_c4",                  # Large corporate donations to 501c4
                "c4_to_campaign",                   # 501c4 funds campaign activities
                "legislative_action_follows",       # Bill introduced within 12 months of funding
                "financial_benefit_to_corporation"   # Corporation materially benefits from legislation
            ]
        },
        "pass_through_chain": {
            # Pattern: Donor → Org A → Org B → Org C → political spending (laundering)
            "signals": [
                "grant_chain_length_3plus",         # Money passes through 3+ entities
                "shell_org_indicators",             # Minimal staff, no apparent mission activity
                "timing_correlation",               # Grants coincide with election cycles
                "same_registered_agent"             # Multiple orgs share legal representation
            ]
        }
    }
    
    def scan_new_filing(self, filing):
        """Score a new 990 or campaign filing against known patterns."""
        matches = []
        for pattern_name, pattern in self.KNOWN_PATTERNS.items():
            score = sum(1 for s in pattern["signals"] if self.check_signal(filing, s))
            if score >= 2:
                matches.append({
                    "pattern": pattern_name,
                    "confidence": score / len(pattern["signals"]),
                    "filing": filing,
                    "edges_to_propose": self.generate_edges(filing, pattern_name)
                })
        return matches
```

---

### Agent DI-9: Court Filing & Legal Action Monitor
**Purpose:** Track every case involving entities in the graph. New indictments, new lawsuits, amicus briefs, settlements, consent decrees. Legal actions are the highest-confidence signals.

**Data Sources:**
- **CourtListener / RECAP** — Free archive of federal court filings
- **PACER** — Direct federal court access (paid, but CourtListener mirrors most)
- **State court systems** — Each state has electronic filing (varies in accessibility)
- **DOJ Press Releases** — Indictments, settlements, consent decrees
- **SEC Enforcement Actions** — Securities fraud, insider trading
- **State AG press releases** — State-level enforcement (or non-enforcement)

**Edge Types Generated:**
```
DOJ → INDICTED → PERSON/COMPANY (criminal)
SEC → CHARGED → PERSON/COMPANY (securities)
COMPANY_A → SUED → COMPANY_B (civil, with claim type)
ENTITY → FILED_AMICUS → CASE (reveals political alignment)
ENTITY → SETTLED_WITH → REGULATOR ($amount, terms)
COURT → DISMISSED → CASE (AG overreach indicator — like Nessel fake electors case)
AG → DECLINED_TO_PROSECUTE → ENTITY (non-action is also a signal)
WHISTLEBLOWER → FILED_QUI_TAM → AGAINST → ENTITY (False Claims Act suits)
```

**Critical Feature: Non-Action Detection**
```
For every entity in the graph with documented evidence of wrongdoing:
  → CHECK: Has any enforcement action been filed?
  → If NO and evidence exists for 12+ months:
    → FLAG: "Enforcement gap — [Entity] has documented evidence of [violation] 
       but no enforcement action by [responsible agency]"
    → CROSS-REFERENCE: Does entity appear in agency head's donor list?
    → This is exactly how we'd catch the Nessel/Kornak pattern AUTOMATICALLY
```

---

### Agent DI-10: Media & Narrative Monitor
**Purpose:** Track how stories about graph entities are covered (or NOT covered) across media. Which outlets cover the Kornak story? Which ignore it? Does coverage correlate with ownership/advertiser relationships?

**Data Sources:**
- **Google News API / NewsAPI.org** — Aggregated coverage by topic
- **Media Cloud** (mediacloud.org, MIT/Harvard) — Open-source media analysis platform
- **GDELT Project** — Global database of events, language, tone from news worldwide
- **AllSides Media Bias Ratings** — Bias classification by outlet
- **Ad Fontes Media** — Reliability and bias ratings

**What It Tracks:**
```
STORY (e.g., "Kornak embezzlement") → COVERED_BY → [list of outlets]
STORY → NOT_COVERED_BY → [list of outlets]  ← THIS IS THE SIGNAL
OUTLET → OWNED_BY → CONGLOMERATE
OUTLET → ADVERTISER → ENTITY_IN_STORY (conflict of interest)
COVERAGE → SENTIMENT → Positive/Negative/Neutral per outlet
COVERAGE → FRAMING → How each outlet frames the same facts

Example:
Kornak embezzlement story (Feb 2026):
├── COVERED BY: Charlie LeDuff (Deadline Detroit), Bridge Michigan, Detroit News, 
│   MLive, Fox 17, Livingston Daily
├── NOT COVERED BY: [track which major outlets ignored it]
├── FRAMING VARIANCE:
│   ├── LeDuff: "AG killed investigation to protect political ally"
│   ├── Bridge: Focused on Beydoun connection, systemic oversight failure
│   ├── Detroit News: Focused on House Oversight subpoena angle
│   └── [Others]: How did they frame it? Missing context? Buried lede?
├── GRAPH EDGES:
│   ├── Glengariff Group (Czuba) → POLLS_FOR → Detroit News
│   ├── Glengariff Group (Czuba) → PRESIDENT_OF → Bipartisan Solutions
│   └── POTENTIAL CONFLICT: Czuba's firm does polling for outlet covering story
│       his organization is implicated in
```

---

### Agent DI-11: Lobbyist Registration & Activity Tracker  
**Purpose:** Real-time monitoring of federal AND state lobbying registrations, expenditure reports, and revolving door movements.

**Data Sources:**
- **Senate Lobbying Disclosure Act Database** (lda.senate.gov)
- **House lobbyist disclosures**
- **FARA.gov** — Foreign agent registrations
- **State lobbyist registrations** (50 state databases, FollowTheMoney.org aggregates)
- **OpenSecrets Revolving Door database**
- **LegiStorm** — Congressional staff employment history

**Depth Example:**
```
New lobbying registration detected: February 2026
├── REGISTRANT: [Lobbying Firm X]
├── CLIENT: [Foreign semiconductor company Y]
├── ISSUES: "Trade policy, tariffs, semiconductor manufacturing incentives"
├── LOBBYISTS: 
│   ├── Person A — former DOC (Dept of Commerce) official, left 2024
│   │   └── EDGE: DOC → REVOLVING_DOOR → Lobbying Firm X → LOBBIES_FOR → Foreign Company Y
│   ├── Person B — former Senate Commerce Committee staffer
│   │   └── EDGE: Senate Commerce → REVOLVING_DOOR → Lobbying Firm X
│   └── Person C — registered FARA agent for [country]
│       └── EDGE: Foreign Government → FARA_AGENT → Person C → ALSO_LOBBIES_FOR → Foreign Company Y
├── CROSS-REFERENCE:
│   ├── Foreign Company Y competes with CHIPS Act recipients
│   ├── Foreign Company Y's government provides subsidies (documented by USTR)
│   └── Lobbying spend is DIRECTLY attempting to weaken domestic competitor advantage
│       created by CHIPS Act that graph already tracks
```

---

## INTEGRATION: HOW ALL AGENTS CONNECT

### The Full Picture on a Single Company

Take a Russell 2000 company that RSHO ETF holds. Here's what the full agent stack produces:

```
Company: Photon Dynamics (hypothetical small-cap, defense electronics)

DI-1 (SEC EDGAR):
├── 10-K: Revenue 72% DOD, top customer is Raytheon
├── 10-K: Supplier — buys gallium nitride wafers from IQE plc (UK)  
├── 8-K: Won $34M Navy contract (Jan 2026)
├── 13-F: Renaissance Technologies initiated position Q4 2025
└── DEF 14A: Board member also on CSIS advisory board

DI-2 (Government Contracts):
├── USASpending: $127M cumulative DOD contracts since 2020
├── SAM.gov: Active registrations, no exclusions, small business designation
├── Sub-awards: Subcontracts to 3 small firms in New Hampshire
└── SBIR: Received 2 Phase II SBIR awards for directed energy research

DI-3 (Trade Flow):
├── Previously imported GaN wafers from China (HS code 8541)
├── Shifted to UK supplier (IQE) after export controls
├── Import records confirm: China source → zero since 2023
└── Tariff impact: Competitor still sources from China, paying 25% tariff

DI-4 (Earnings Call):
├── CEO Q3 2025: "Our domestic supply chain is now a competitive advantage"
├── CFO: "Backlog at $89M, highest in company history"
├── Analyst question revealed competitor lost Navy contract to Photon
└── CEO mentioned "significant R&D investment in GaN-on-diamond technology"

DI-5 (Patents):
├── Filed 3 patents in GaN-on-diamond power amplifiers (2025)
├── Co-filed 1 patent with MIT Lincoln Laboratory
└── Patent citations reveal dependency on DARPA-funded research

DI-6 (Job Postings):
├── 31 open positions, up from 12 six months ago
├── New facility address in Nashua, NH appears in 6 postings
├── Hiring RF test engineers, program managers, security-cleared systems engineers
└── SIGNAL: Expansion to new facility not yet in any SEC filing

DI-7 (Institutional Flow):
├── Renaissance Technologies: New position $4.2M (Q4 2025 13-F)
├── Vanguard: Increased position 12% quarter-over-quarter
├── Insider buying: CEO purchased $180K open market (Form 4, Jan 2026)
└── RSHO ETF: Added to holdings at last rebalance

DI-8 (Dark Money):
├── Defense industry PAC donated to Armed Services Committee members
├── Competitor lobbying to change procurement rules (LDA filing)
└── No dark money connections detected for this company (clean)

DI-9 (Legal):
├── No current litigation
├── Sub-contractor in NH has open OSHA violation (minor)
└── Competitor filed patent infringement claim in EDTX (monitor)

DI-10 (Media):
├── Featured in Aviation Week (positive, technical coverage)
├── Not covered by mainstream business press (under radar = opportunity)
└── Defense industry trade press coverage aligns with SEC filings

DI-11 (Lobbying):
├── Registered lobbyist: 1 (appropriations, defense budget)
├── Spend: $120K/year (minimal compared to primes)
└── Foreign competitor has 4 lobbyists working to weaken Buy American provisions
```

**That's ONE COMPANY. Every edge sourced. Every claim verifiable.**

Now multiply by 200+ companies in the reshoring/defense/reshoring universe.
That's the intelligence layer Palantir charges $100M/year for.
Built on public data. Connected to the same graph that exposes the corruption.

---

## THE DUAL-USE THESIS

The same graph serves both missions simultaneously:

**INVESTMENT SIDE:**
"Company X is growing because CHIPS Act money flows to its customer (DI-2), it reshored 
its supply chain (DI-3), insiders are buying (DI-7), and it's hiring at a new facility 
nobody knows about yet (DI-6)."

**EXPOSURE SIDE:**
"Company Y's competitor is spending $2M lobbying to weaken Buy American provisions (DI-11) 
through a 501(c)(4) that doesn't disclose its foreign corporate funders (DI-8), while 
the media outlets owned by the same conglomerate that owns the foreign competitor aren't 
covering the story (DI-10)."

**BOTH SIDES USE THE SAME EVIDENCE STANDARDS.**
**BOTH SIDES CITE THE SAME GRAPH.**
**THE INVESTMENT THESIS AND THE TRANSPARENCY MISSION ARE THE SAME THING.**

Capital flowing toward companies that reshored = capital flowing away from the system that 
offshored jobs and captured regulators.

Every dollar invested in the correction IS the correction.

---

## IMPLEMENTATION ROADMAP

### Phase 1: Core Financial Intelligence (Weeks 1-4)
- DI-1: SEC EDGAR crawler (10-K, 8-K, 13-F parsing)
- DI-7: Institutional flow tracker (13-F delta detection)
- DI-4: Earnings call NLP (start with RSHO holdings)
- **OUTPUT:** Deep profiles on all RSHO ETF holdings + Russell 2000 reshoring candidates

### Phase 2: Government & Supply Chain (Weeks 5-8)  
- DI-2: USASpending.gov integration (CHIPS/IIJA/IRA tracking)
- DI-3: Trade flow intelligence (Census Bureau import/export)
- DI-6: Job posting intelligence (Indeed MCP integration)
- **OUTPUT:** Full supply chain maps for top 50 reshoring companies

### Phase 3: Investigative Layer (Weeks 9-12)
- DI-8: Dark money monitor (IRS 990s + state campaign finance)
- DI-9: Court filing monitor (CourtListener API)
- DI-11: Lobbyist activity tracker (LDA + state databases)
- **OUTPUT:** Opposition mapping for all policy-connected nodes in graph

### Phase 4: Narrative Intelligence (Weeks 13-16)
- DI-10: Media coverage monitor (GDELT + Media Cloud)
- DI-5: Patent tracker (USPTO API)
- AI Training Bias Auditor (from solution agents spec)
- **OUTPUT:** Full narrative distortion index, coverage gap analysis

### Phase 5: Pattern Detection & Cross-Referencing (Ongoing)
- Dark money pattern matching (Michigan/Ohio templates applied nationally)
- Supply chain vulnerability detection
- Enforcement gap detection (documented crime + no prosecution = flag)
- Signal convergence across all agents (3+ agents confirming same edge = high confidence)

---

## WHY THIS DOESN'T EXIST YET

Palantir does the investment/intelligence side but:
- Costs $100M+/year
- Serves government/corporate clients, not public
- Doesn't expose the corruption that benefits its clients
- Closed source, proprietary graph

OpenSecrets/Sunlight Foundation do the transparency side but:
- Don't connect to market data
- Don't go company-level depth on supply chains
- Don't track AI training bias
- Don't propose investment allocation as correction mechanism

Bloomberg Terminal does financial data but:
- $24K/year per seat
- No corruption/lobbying overlay
- No dark money tracking
- No government contract granularity
- No narrative distortion analysis

**FGIP with these agents = Bloomberg + Palantir + OpenSecrets + ProPublica**
**On a public graph. With receipts for every edge. Serving both profit and transparency.**

The data is all public. The APIs are all free or low-cost. 
What doesn't exist is the GRAPH that connects them.
That's what we're building.
