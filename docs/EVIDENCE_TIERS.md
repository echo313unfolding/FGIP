# Evidence Tiers

FGIP classifies all data sources into tiers based on authority and reliability. Tier determines conviction boost and triangulation weight.

## Tier 0 — Government / Primary Records

The source IS the evidence. No interpretation layer between the fact and the record.

| Source | What it provides | URL |
|--------|-----------------|-----|
| SEC EDGAR | 13F institutional holdings, 10-K annual reports, 8-K material events, Form 4 insider transactions | sec.gov |
| USASpending | Federal contracts, grants, and direct payments | usaspending.gov |
| Congress.gov | Bill text, voting records, committee actions | congress.gov |
| Federal Register | Rulemakings, executive orders, agency notices | federalregister.gov |
| FRED | Economic indicators (M2, CPI, employment, GDP) | fred.stlouisfed.org |
| FEC | Campaign contributions, expenditures, committee filings | fec.gov |
| FARA | Foreign agent registrations and activities | fara.gov |
| NRC ADAMS | Nuclear regulatory documents, permit applications, safety reviews | nrc.gov |
| SCOTUS | Supreme Court dockets, opinions, amicus briefs | supremecourt.gov |
| GAO | Government accountability reports and audits | gao.gov |
| Treasury TIC | Treasury International Capital flow data | treasury.gov |
| FERC | Energy regulatory filings, pipeline capacity, tariffs | ferc.gov |
| State PUCs | Public utility commission filings and orders | (state-specific) |

**Conviction boost:** +15 points per signal
**Triangulation:** Required — at least 1 Tier 0 source needed for Active status

### Self-certifying agents

FGIP agents that ingest Tier 0 data are **self-certifying** — the proposed edge itself is sufficient evidence because the data comes directly from a government source. These agents do not require a separate `artifact_id` for their proposed edges to count in conviction scoring.

Self-certifying agents: `edgar`, `usaspending`, `federal_register`, `congress`, `nuclear_smr`, `tic`, `fec`, `scotus`, `gao`, `fara`, `chips-facility`.

## Tier 1 — Professional / Corporate Records

Published by professionals or companies with legal/regulatory obligations. Generally reliable but may contain bias or selective disclosure.

| Source | What it provides |
|--------|-----------------|
| Earnings calls / transcripts | Company guidance, backlog data, management commentary |
| Options unusual activity | Institutional positioning signals |
| Credit rating changes | Moody's, S&P, Fitch assessments |
| Analyst upgrades/downgrades | Professional research opinions |
| Industry conferences | Company presentations, deal announcements |
| Reuters / WSJ / Bloomberg | Professional journalism with editorial standards |
| Company press releases | Product announcements, contract awards, partnerships |

**Conviction boost:** +8 points per signal
**Triangulation:** Counts as independent source type

## Tier 2 — Commentary / Secondary

Published without editorial or legal obligations. Useful for context and pattern detection, not for conviction.

| Source | What it provides |
|--------|-----------------|
| News articles (general) | Reporting, analysis, opinion |
| Social sentiment | Twitter/X, Reddit, StockTwits |
| Podcasts | Expert interviews, market commentary |
| YouTube signals | Financial channels, earnings analysis |
| Blog posts | Individual analysis and opinion |

**Conviction boost:** +3 points per signal
**Triangulation:** Counts as independent source type but cannot substitute for Tier 0

## Tier 3 — Hypothesis / Raw Observation

User-generated patterns, AI-assisted research output, or unverified observations. Must be converted to Tier 0/1 backed claims before entering the graph as Active.

| Source | What it provides |
|--------|-----------------|
| User observation | Pattern recognition, hypothesis |
| AI research output | Perplexity, ChatGPT, Claude analysis |
| Cross-reference inference | Graph-derived connections not yet source-verified |

**Conviction boost:** 0 points
**Triangulation:** Does not count
**Action:** Capture as Candidate. Convert to source-backed claim before promotion.

## Triangulation Requirement

A thesis reaches **Active** status (Conviction 3+) only when:

1. **3+ independent signals** from different source types confirm the thesis
2. **At least 1 signal** comes from a Tier 0 source
3. **Counter-thesis** has been articulated and assessed

Example of valid triangulation:
- Tier 0: Congress voting record (NDAA passage)
- Tier 0: USASpending contract award to defense prime
- Tier 1: Company earnings call confirming backlog growth

Example of invalid triangulation:
- Tier 2: News article about defense spending
- Tier 2: Podcast discussing same topic
- Tier 2: YouTube video citing the news article
(All three are the same signal echoed through commentary channels)

## Source quality signals

Watch for these when assessing source reliability:

| Signal | Interpretation |
|--------|---------------|
| Source cites specific dollar amounts | Higher reliability — concrete data |
| Source uses "may," "could," "potentially" | Lower reliability — speculation |
| Source is the entity itself (SEC filing, company press release) | Primary source — highest reliability |
| Source cites another source | Secondary — check the primary |
| Source is anonymous or unnamed | Lowest reliability — do not use for conviction |
| Multiple independent sources converge | Strong signal — triangulation met |
| Sources contradict each other | Flag for investigation — do not assume either is correct |
