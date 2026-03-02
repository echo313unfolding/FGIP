# FGIP Solution Agent Architecture
## "The graph doesn't just show what's broken — it proposes how to fix it"

### Design Philosophy

Every problem edge in the graph gets a corresponding correction edge. Every correction edge cites:
1. **The problem it addresses** (linked to source nodes with evidence)
2. **The mechanism of correction** (legislative, market, structural, transparency)
3. **Existing precedent** (where this fix already works — state, country, or sector)
4. **Measurable outcome** (what changes if implemented, with metrics)
5. **Opposition mapping** (who would fight it and why, with dollar amounts)

The agents don't generate opinions. They pattern-match: "Problem X exists with evidence Y. 
Jurisdiction Z solved a structurally identical problem using mechanism W. Here's the data."

---

## Agent 1: LEGISLATIVE PATCH AGENT
**Purpose:** For every documented loophole, find legislation that closes it — existing bills, passed laws in other states, or model legislation from nonpartisan orgs.

### Problem → Solution Mapping

| Documented Problem | Evidence Nodes | Proposed Fix | Precedent |
|---|---|---|---|
| Dark money via 501(c)(4)s | Bipartisan Solutions $782K, Unlock Michigan $2.4M | Require donor disclosure for any org spending >$10K on ballot issues | CA DISCLOSE Act (2017), 11 states already require this |
| AG conflict of interest | Nessel/Kornak, Nessel/wife's ballot committee | Independent prosecutor appointment when AG has personal connection to case | 28 states have special prosecutor statutes |
| Lobbyist meal loopholes | MI $485K meals, $79/month disclosure threshold | $0 gift limit for public officials | 8 states ban all lobbyist gifts (SC, MA, WI, etc.) |
| Revolving door (legislators → lobbyists) | Iden, Lilly became lobbyists for industries they regulated | 5-year cooling-off period | Federal: 2-year for senior officials, some states have 6-year |
| No-bid earmarks to donors | Beydoun $20M, zero competitive process | Mandatory competitive bidding for all grants >$100K, ban grants to entities that don't exist | Federal: FAR requires competitive bidding; most states have procurement codes |
| Governor/Legislature exempt from FOIA | MI among worst transparency laws | Extend FOIA to all branches | 40+ states include governor's office in public records laws |
| Media consolidation via Telecom Act | 50 companies → 6 since 1996 | Cross-ownership limits, local ownership requirements | Pre-1996 FCC rules, Canada's Broadcasting Act |
| Campaign finance post-Citizens United | Unlimited corporate spending → dark money pipeline | Constitutional amendment (long), state-level disclosure (near-term), public financing (medium) | 22 states have public financing programs |

### Data Sources
- National Conference of State Legislatures (NCSL) — bill tracking by topic across all 50 states
- Brennan Center for Justice — model legislation database
- ALEC/SPN exposed bills — for tracking WHERE model legislation originates (and who funds it)
- Congress.gov — federal bill text and status
- LegiScan API — all 50 states real-time bill tracking
- Michigan Legislature (legislature.mi.gov) — state-specific

### Output Format
```json
{
  "problem_edge_id": "E-047",
  "problem_summary": "AG Nessel killed investigation into political ally Kornak",
  "correction_type": "LEGISLATIVE",
  "proposal": "Mandatory recusal + independent special prosecutor when AG has documented personal/financial relationship with investigation target",
  "precedent": [
    {"jurisdiction": "Texas", "mechanism": "Court-appointed special prosecutor", "statute": "CCP Art. 2.07"},
    {"jurisdiction": "Federal", "mechanism": "Special counsel regulations", "statute": "28 CFR 600"},
    {"jurisdiction": "New York", "mechanism": "Governor appoints special prosecutor", "statute": "Executive Law §63(2)"}
  ],
  "opposition_map": {
    "who": "Attorney General associations, incumbent AGs of both parties",
    "why": "Reduces AG discretion and political power",
    "funding": "AG campaign donors who benefit from selective prosecution"
  },
  "measurable_outcome": "Number of investigations closed without charges where AG has documented conflict → target: zero",
  "evidence_tier": 0,
  "sources": ["MI House Oversight hearing transcripts", "Kent County charging documents"]
}
```

---

## Agent 2: MARKET CORRECTION AGENT
**Purpose:** Track capital flows that confirm or contradict the thesis. If lobbying distorts markets, show WHERE capital is moving to correct the distortion.

### What It Tracks

| Thesis Prediction | Market Signal | Current Status | Data Source |
|---|---|---|---|
| Reshoring reverses offshoring damage | Small-cap domestic manufacturers outperform | IWM +6.75% YTD, outperforming S&P by 4% | Yahoo Finance, FRED |
| Domestic manufacturing investment accelerates | RSHO ETF (reshoring-focused) performance | 28.7% avg annual return, $194M AUM | SEC 13F, ETF holdings |
| Semiconductor sovereignty reduces Taiwan risk | CHIPS Act disbursements flow to domestic fabs | Intel $8.9B, TSMC Arizona, Samsung Texas | USASpending.gov |
| Stablecoin framework creates monetary sovereignty | GENIUS Act implementation → institutional adoption | Signed July 2025, FDIC implementing, crypto >$4T | Federal Register, FDIC.gov |
| Capital-intensive manufacturers benefit from OBBBA | EBITDA interest deductibility → capex increase | One Big Beautiful Bill Act changed 30% EBIT → EBITDA | IRS guidance, SEC filings |
| Dark money distorts election outcomes | Correlation between undisclosed spending and incumbent retention | Measurable at state level | FEC, state campaign finance databases |

### Portfolio-as-Proof Concept
The graph doesn't give investment advice. But it can show: "If the reshoring thesis is correct, these are the sectors that benefit, and here's the capital flow data showing whether markets agree." 

If IWM outperforms SPY for 4+ consecutive quarters after decades of underperformance, that's not a stock tip — that's empirical confirmation that capital is flowing toward the correction the graph predicted.

### Data Sources
- FRED (Federal Reserve Economic Data) — macro indicators
- SEC EDGAR — 13F filings (institutional holdings), 10-K/10-Q (company financials)
- USASpending.gov API — CHIPS Act, IRA, IIJA disbursements
- Federal Register API — GENIUS Act implementation rules
- Bureau of Labor Statistics — manufacturing employment, reshoring job data
- Reshoring Initiative (reshorenow.org) — job announcements by company/state

### Output Format
```json
{
  "thesis_edge_id": "E-CORRECTION-012",
  "thesis_statement": "CHIPS Act disbursements reduce semiconductor supply chain vulnerability",
  "confirmation_data": {
    "total_disbursed": "$39.2B allocated, $XX.XB disbursed to date",
    "recipients": ["Intel ($8.9B)", "TSMC ($6.6B)", "Samsung ($6.4B)"],
    "jobs_created": "XX,XXX announced",
    "facilities": ["Arizona fab (TSMC)", "Ohio fab (Intel)", "Texas fab (Samsung)"]
  },
  "market_signal": {
    "indicator": "SOXX (semiconductor ETF) vs SPY",
    "period": "2024-2026",
    "result": "Outperformance of X% since first disbursement"
  },
  "counter_signal": {
    "risk": "China retaliatory export controls on rare earth minerals",
    "impact": "Could slow domestic fab ramp-up",
    "source": "Commerce Department report"
  },
  "confidence": 0.85,
  "evidence_tier": 0
}
```

---

## Agent 3: TRANSPARENCY ENFORCEMENT AGENT
**Purpose:** For every transparency failure documented in the graph, identify the specific disclosure mechanism that should exist, whether it exists elsewhere, and how to implement it.

### Core Principle
The graph proves: corruption survives in darkness. Every documented fraud (Kornak, Beydoun, Feeding Our Future, HSBC) exploited a specific transparency gap. This agent maps gap → fix.

### Transparency Gap Inventory

| Gap | Who Benefits | Fix | Implementation |
|---|---|---|---|
| MI lobbyist meals <$79/month not disclosed | Lobbyists, legislators | Real-time disclosure of ALL meals/gifts regardless of amount | Digital reporting app (several states use this) |
| 501(c)(4) donor anonymity | Dark money operators, both parties | Require donor disclosure for political spending >$5K | IRS form modification + state-level reporting |
| MI Governor/Legislature FOIA exempt | All elected officials hiding records | Extend FOIA to all branches | Constitutional amendment or statute |
| AI training data composition undisclosed | Tech companies, consolidated media | Require AI companies to publish training data composition by source domain | EU AI Act requires this; US has no equivalent |
| Federal lobbying spending by issue not fully itemized | Multi-client lobbying firms | Require per-client, per-issue spending breakdown | Lobbying Disclosure Act amendment |
| State grant spending not publicly trackable | Grant recipients (Beydoun) | Real-time public dashboard for all grants >$50K | USASpending.gov model applied to states |
| Judicial financial disclosures delayed/incomplete | Justices with conflicts | Real-time electronic filing, mandatory recusal triggers | Fix the Financial Disclosure Act (federal), replicate at state level |
| Common Crawl composition not auditable | AI companies using skewed data | Training data transparency requirements | Legislation modeled on EU AI Act Article 53 |

### Data Sources
- National Freedom of Information Coalition — state-by-state FOIA comparison
- Reporters Committee for Freedom of the Press — open government guides
- EU AI Act text — transparency requirements for foundation models
- State integrity investigations (Center for Public Integrity ranked all 50 states)
- Global Right to Information Rating — international comparison

---

## Agent 4: STATE REPLICATION AGENT
**Purpose:** Take every pattern documented in Michigan and search for structural equivalents in other states. The Michigan template (donor → appointment → earmark → AG covers) is a PATTERN, not an isolated event.

### The Michigan Template (documented)
```
1. Donor gives to governor campaign ($20K+ Beydoun, $7,150 Kornak)
2. Donor gets appointed to board/committee (MEDC board, transition team)
3. Donor creates or steers nonprofit (Global Link International, conservatorship)
4. Money flows to nonprofit via earmark/grant ($20M Beydoun) or direct theft ($419K Kornak)
5. AG has personal connection to actors (transition team, party treasurer, wife's ballot committee)
6. Investigation opened and closed without charges
7. Only exposed by: independent journalist, county prosecutor, or legislative oversight
8. Reform legislation introduced and dies
```

### Search Methodology Per State
For each of the 50 states, query:
1. **State AG campaign donors** → cross-reference with **targets/subjects of AG investigations** (or non-investigations)
2. **Governor appointees to economic development boards** → cross-reference with **grant recipients**
3. **State party treasurers/officers** → cross-reference with **criminal charges or ethics complaints**
4. **501(c)(4) organizations** → cross-reference with **ballot committee donors** 
5. **Lobbyist disclosure reports** → cross-reference with **legislative votes on relevant industries**

### Data Sources (per state)
- FollowTheMoney.org (National Institute on Money in Politics) — all 50 states campaign finance
- State AG office websites — press releases, investigation announcements
- State ethics commission filings
- State-level FOIA/public records requests
- Local investigative outlets (equivalent of Bridge Michigan in each state)
- IRS 990 filings for nonprofits in each state

### Priority States (highest lobbying spend, most documented issues)
1. **California** — largest economy, most lobbying spend
2. **Texas** — energy lobby, minimal disclosure
3. **New York** — financial services lobby, Albany corruption history
4. **Florida** — real estate/insurance lobby, minimal transparency
5. **Illinois** — documented corruption history (multiple governors convicted)
6. **Ohio** — FirstEnergy/HB6 bribery scandal (already proven template)
7. **Pennsylvania** — swing state, major dark money flows
8. **Virginia** — proximity to DC, revolving door epicenter
9. **Georgia** — election integrity battles, rapid demographic change
10. **Arizona** — border state politics, water rights lobbying

### Ohio as Validation Case
Ohio's FirstEnergy/HB6 scandal is the closest documented parallel to the Michigan template:
- FirstEnergy spent $60M in dark money through 501(c)(4) Generation Now
- Money went to Speaker Larry Householder's campaign
- Householder passed HB6 ($1.5B ratepayer bailout for FirstEnergy nuclear plants)
- Householder convicted of racketeering (20 years, largest bribery case in OH history)
- Same pattern: corporate money → dark money vehicle → elected official → favorable legislation → public pays

If the agent finds this pattern in 10+ states with documented evidence, that's not a conspiracy theory — that's a systemic design flaw in American campaign finance architecture.

---

## Agent 5: AI TRAINING BIAS AUDITOR
**Purpose:** Systematically test whether AI models reproduce narratives that align with consolidated media rather than primary source data. This is the "corrupted training data" hypothesis made testable.

### Methodology
For each documented claim in the FGIP graph, ask 5+ LLMs the same question and compare responses to:
1. Government source data (Tier 0)
2. Investigative journalism findings (Tier 1)
3. The dominant media narrative

### Test Battery

| Question | Government/Primary Source Answer | Expected AI Bias Direction | Why |
|---|---|---|---|
| "Did PNTR with China benefit American workers?" | BLS: 3.7M manufacturing jobs lost 2001-2018. EPI: $37B/yr wage suppression | Likely hedged or positive ("trade benefits consumers") | Training data dominated by free-trade editorial consensus |
| "Is lobbying corruption?" | Senate lobbying disclosures show $4.1B/yr, revolving door documented | Likely framed as "legitimate advocacy" | Media owned by companies that lobby; Wikipedia reflects establishment framing |
| "Did the CHIPS Act work?" | USASpending: $39.2B allocated, fabs under construction | Likely accurate (bipartisan support = media consensus aligns with reality) | Both parties supported, so media narrative matches facts |
| "Is Michigan's AG office compromised?" | House Oversight: documented firewall breaches, closed investigations | Likely defensive of Nessel or "both sides" | Left-leaning media overrepresented in training data; Nessel is Democrat |
| "Did media consolidation reduce news diversity?" | FCC data: 50 companies → 6, local news deserts documented | Likely acknowledged but minimized | Models can't critique the media that trained them without self-undermining |

### Scoring
- **Alignment with Tier 0 sources:** 0-100%
- **Alignment with media consensus:** 0-100%
- **Gap score:** |Tier 0 alignment - Media consensus alignment|
- High gap score = evidence that training data bias is distorting model output on that topic

### Output
This agent produces a "Narrative Distortion Index" for each topic in the graph. Topics where AI models diverge most from government source data are flagged as highest-priority for the transparency enforcement agent.

---

## Agent 6: OPPOSITION RESEARCH AGENT
**Purpose:** For every proposed correction, map WHO will fight it, HOW MUCH they'll spend, and WHAT their arguments will be. No correction succeeds without understanding the counter-force.

### For Every Proposed Fix, Document:
1. **Industry groups that would oppose** (with lobbying spend data from OpenSecrets)
2. **Think tanks that will produce counter-arguments** (with funding sources from 990s)
3. **Specific legislators who will block** (with campaign donor overlap)
4. **Legal challenges expected** (with precedent cases)
5. **Media narrative expected** (based on ownership/advertiser relationships)

### Example: Michigan "Money Out of Politics" Ballot Initiative

```
PROPOSED FIX: Ban utility/contractor donations to state candidates, require issue ad donor disclosure

OPPOSITION MAP:
├── Michigan Chamber of Commerce
│   ├── Lobbying spend: $X.XM/year (MI lobby disclosures)
│   ├── Treasurer Wendy Block running opposition committee
│   └── Argument: "First Amendment, free speech"
├── Consumers Energy (parent CMS Energy)  
│   ├── Donated $15K to Protect MI Free Speech
│   ├── Also donated $840K+ to pro-Whitmer groups in 2018
│   └── Argument: "Employees lose right to association"
├── Blue Cross Blue Shield of Michigan
│   ├── Donated $15K to Protect MI Free Speech
│   └── Argument: "PAC funded by voluntary employee contributions"
├── Legal challenge likely based on:
│   ├── Citizens United v. FEC (corporate spending = speech)
│   ├── Americans for Prosperity v. Bonta (donor disclosure burden)
│   └── But: 11 states already require similar disclosure and have survived challenge
└── Media coverage:
    ├── Detroit News (Glengariff Group/Czuba does their polling — conflict)
    ├── Bridge Michigan (independent, likely favorable coverage)
    └── TV stations (Sinclair-owned stations may frame as "anti-business")
```

---

## Agent 7: CONSTITUTIONAL REPAIR AGENT
**Purpose:** Some problems can't be fixed at the state or legislative level because they're baked into judicial precedent or constitutional structure. This agent maps the structural fixes.

### Supreme Court Decisions That Created the Architecture

| Decision | What It Did | Downstream Damage | Fix Required |
|---|---|---|---|
| Citizens United v. FEC (2010) | Corporate spending = protected speech | Unlimited dark money pipeline | Constitutional amendment (only fix) OR creative state-level workarounds |
| Buckley v. Valeo (1976) | Money = speech, struck down spending limits | Foundation for all subsequent deregulation | Constitutional amendment |
| McCutcheon v. FEC (2014) | Struck down aggregate contribution limits | Donors can max out to unlimited candidates | Constitutional amendment or new case |
| Americans for Prosperity v. Bonta (2021) | Donor disclosure requirements face strict scrutiny | Makes state disclosure laws harder to enforce | Narrow legislative drafting to survive scrutiny |
| Shelby County v. Holder (2013) | Gutted Voting Rights Act preclearance | States free to change election rules without federal review | New VRA legislation (John Lewis Act) |

### State-Level Workarounds (What's Working Despite SCOTUS)
- **Alaska:** Top-4 primary + ranked choice voting (reduces dark money influence on primaries)
- **Maine/Arizona:** Public campaign financing (Clean Elections Acts)
- **Montana:** Stringent disclosure requirements survived AFP v. Bonta because narrowly tailored
- **Colorado:** Independent redistricting commission (removes gerrymandering)
- **South Dakota:** Voters passed anti-corruption act (legislature repealed it — documented)

### Constitutional Amendment Tracker
28+ states have called for an amendment to overturn Citizens United. 
Amendment requires 2/3 of Congress + 3/4 of state legislatures.
Current count: Not close. But documenting the state-by-state status creates accountability.

---

## Cross-Agent Integration

The power isn't in any single agent — it's in the CONNECTIONS between them.

### Example Workflow: Michigan Dark Money Problem

1. **State Replication Agent** documents: MI Bipartisan Solutions pattern matches OH FirstEnergy pattern
2. **Legislative Patch Agent** finds: 11 states require issue ad donor disclosure, MI doesn't
3. **Opposition Research Agent** maps: Chamber of Commerce + Consumers Energy + BCBS funding opposition
4. **Transparency Enforcement Agent** identifies: MI governor/legislature still FOIA-exempt
5. **Market Correction Agent** shows: States with better transparency have lower corruption indices AND better business climate scores
6. **AI Training Bias Auditor** tests: Ask LLMs about MI dark money — do they reproduce the "both sides" narrative or cite the documented evidence?
7. **Constitutional Repair Agent** notes: Any state disclosure law must survive AFP v. Bonta strict scrutiny — draft accordingly

### The Graph Output

For every PROBLEM cluster in the graph, a SOLUTION cluster exists with:
- Specific legislative text (from precedent states)
- Dollar-amount opposition mapping
- Timeline for implementation
- Measurable success criteria
- Evidence that the solution works (from states/countries that already did it)

---

## Implementation Priority

### Phase 1 (Build Now — Data Already in Graph)
1. **Legislative Patch Agent** — cross-references problems with existing legislation in other states
2. **Opposition Research Agent** — uses OpenSecrets + state lobby data already collected

### Phase 2 (Next Sprint — Requires New Data Sources)
3. **State Replication Agent** — needs FollowTheMoney.org integration + state-level data
4. **Market Correction Agent** — needs FRED + SEC EDGAR + USASpending API

### Phase 3 (Research Layer)
5. **AI Training Bias Auditor** — requires systematic testing methodology
6. **Transparency Enforcement Agent** — needs state-by-state FOIA comparison data
7. **Constitutional Repair Agent** — mostly analytical, uses existing legal databases

---

## The Difference From Existing Think Tanks

| Organization | What They Do | What They Miss |
|---|---|---|
| Heritage Foundation | Propose conservative policy | Don't show who funds them or map opposition |
| Brookings | Propose centrist/liberal policy | Don't trace lobbying money to policy outcomes |
| Cato Institute | Propose libertarian policy | Funded by Koch, don't disclose conflict |
| OpenSecrets | Track money in politics | Don't propose solutions or map state-level |
| Brennan Center | Propose democracy reforms | Don't connect to market data or AI bias |
| EPI | Track economic impact | Don't map the lobbying that caused the impact |

**FGIP Solution Agents do ALL of the above simultaneously:**
- Show the problem (with receipts)
- Show who caused it (with dollar amounts)
- Show who's blocking the fix (with dollar amounts)
- Show where the fix already works (with measurable outcomes)
- Show whether AI is reproducing the cover story (with test results)
- Show whether markets are confirming the correction (with price data)

No single organization does this because each one is funded by donors who benefit from the system staying partially opaque. FGIP has no donors. It has a graph.

---

## Success Metric

The graph is complete when every PROBLEM edge has a corresponding CORRECTION edge, and every CORRECTION edge has:
- [ ] Specific legislative/policy mechanism
- [ ] Precedent jurisdiction where it works
- [ ] Opposition mapped with dollar amounts
- [ ] Measurable outcome defined
- [ ] AI narrative distortion score
- [ ] Market signal (if applicable)

**Current state:** ~65 problem nodes, ~17 edges documented, 51 pending proposals.
**Target state:** Every problem edge paired with a correction edge. Graph becomes not just a diagnosis but a prescription — one that shows its work.
