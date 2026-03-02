# GENIUS Act Causal Chain - Verification Plan

## Master Claim

> "GENIUS Act → domesticate debt → remove foreign leverage → tariffs become feasible"

---

## Chain Atomization

```
EDGE 1: GENIUS Act → Stablecoin issuers must hold Treasuries
EDGE 2: Stablecoin Treasury demand → Replaces foreign demand
EDGE 3: Reduced foreign holdings → Reduced foreign leverage
EDGE 4: Reduced leverage → Tariff policy becomes feasible
```

---

## EDGE 1: GENIUS Act Mandates Treasury Holdings

### Claim
GENIUS Act Section 4(a) requires stablecoin issuers to hold 100% reserves in short-term Treasuries, creating forced domestic demand for UST.

### Data Required
- GENIUS Act bill text (Section 4 reserve requirements)
- Current stablecoin market cap ($170B)
- Projected stablecoin market cap (2027-2030)
- Composition of current stablecoin reserves

### Tier-0/1 Sources
| Source | Tier | What It Proves |
|--------|------|----------------|
| Congress.gov S.394 (GENIUS Act text) | 0 | Reserve requirement language |
| Tether transparency reports | 1 | Current reserve composition |
| Circle attestations | 1 | USDC reserve breakdown |
| Treasury TIC data | 0 | Baseline foreign vs domestic holdings |

### Adversarial Attack
**Attack:** The bill allows "cash equivalents" and "bank deposits" alongside Treasuries. Issuers might park reserves in banks or money markets, not directly in UST.

**Test:** Read Section 4(a) precisely. What percentage MUST be Treasuries vs MAY be alternatives?

### Control Group
Compare reserve compositions of:
- Tether (offshore, less regulated)
- USDC (US-domiciled, more regulated)

If USDC already holds mostly Treasuries without mandate, GENIUS Act is codifying existing behavior, not creating new demand.

### Verdict Template
```
IF Section 4(a) requires >80% Treasuries: PROVEN
IF allows significant alternatives: HEURISTIC (demand increase uncertain)
IF no specific Treasury requirement: DISPROVEN
```

### Weakest Link Risk
Bill text interpretation. "Short-term government securities" might not mean exclusively UST.

---

## EDGE 2: Stablecoin Demand Replaces Foreign Demand

### Claim
As stablecoin market cap grows, forced Treasury buying replaces Fed QE and foreign purchases, domesticating the debt.

### Data Required
- Current foreign holdings of UST (~$8.5T)
- Annual foreign net purchases/sales trend
- Fed balance sheet trajectory (QT pace)
- Stablecoin market cap projections
- Scale threshold: at what stablecoin cap does replacement become material?

### Tier-0/1 Sources
| Source | Tier | What It Proves |
|--------|------|----------------|
| Treasury TIC Major Foreign Holders | 0 | Foreign holdings breakdown |
| Fed H.4.1 Balance Sheet | 0 | Fed Treasury holdings |
| FRED WALCL | 0 | Fed assets time series |
| DefiLlama / CoinGecko | 2 | Stablecoin market caps |
| Treasury auction results | 0 | Bid-to-cover, foreign participation |

### Adversarial Attack
**Attack:** Scale mismatch. Stablecoins = $170B. Foreign holdings = $8.5T. Fed balance sheet = $7T. Even $2T stablecoins replaces only 12% of foreign holdings.

**Test:** Model the threshold:
```
At what stablecoin market cap does annual Treasury demand from issuers
exceed annual net foreign purchases/sales?

If foreign net sales = $200B/year
And stablecoin growth = 30%/year from $170B base
Then equilibrium reached at ~$670B stablecoin cap (year 5-6)
```

### Control Group
**Japan/China holdings trajectory** - If foreign holdings are declining anyway (de-dollarization), stablecoins might be filling a gap that's already opening, not creating new domestication.

Compare:
- Foreign holdings 2015 vs 2025 (trend)
- Stablecoin growth 2020-2025 (trend)
- Correlation: R² of stablecoin growth vs foreign holdings decline

### Verdict Template
```
IF stablecoin projected cap > 50% of annual foreign purchases within 5 years: HEURISTIC (material but not dominant)
IF stablecoin cap could reach parity with foreign holdings: PROVEN at scale
IF scale threshold is 20+ years out: DISPROVEN (too slow to matter for tariff timeline)
```

### Weakest Link Risk
Scale and timeline. The mechanism is real but may be too slow to matter for near-term policy.

---

## EDGE 3: Reduced Foreign Holdings → Reduced Foreign Leverage

### Claim
Foreign holders (China, Japan, sovereign wealth funds) currently have leverage over US policy via threat of Treasury dumping. Domestication reduces this leverage.

### Data Required
- Historical instances of foreign Treasury sales during geopolitical tension
- Yield sensitivity to foreign selling
- Concentration of holdings (top 10 holders % of foreign total)
- What % of UST is foreign-held (currently ~30%)

### Tier-0/1 Sources
| Source | Tier | What It Proves |
|--------|------|----------------|
| Treasury TIC monthly | 0 | Foreign holdings by country |
| Treasury auction data | 0 | Foreign participation rates |
| Academic literature (Bertaut et al.) | 1 | Yield sensitivity estimates |
| Fed papers on reserve currency | 1 | Analysis of foreign holder behavior |

### Adversarial Attack
**Attack:** Foreign holders can't dump without self-harm. China holds $800B UST. Dumping crashes the dollar, which crashes their export competitiveness and the value of remaining holdings. It's mutually assured destruction - the leverage is theoretical, not operational.

**Test:** Historical evidence:
- Has any major holder actually dumped during a dispute?
- What happened to yields when China reduced holdings 2015-2016?
- Did Russia's sanctions-driven exit (2018) move yields materially?

### Control Group
**Russia 2018 divestment** - Russia reduced holdings from $100B to ~$5B after sanctions.

Test: Did 10-year yields spike? Did it constrain US policy? If Russia's exit was absorbed without yield disruption, the "foreign leverage" thesis weakens.

### Verdict Template
```
IF historical dumps caused yield spikes >50bps: PROVEN (leverage is real)
IF dumps were absorbed with <20bps impact: DISPROVEN (leverage is theoretical)
IF mixed evidence: HEURISTIC (leverage exists but is muted)
```

### Weakest Link Risk
The leverage might be a paper tiger. If historical evidence shows foreign selling doesn't move yields, the whole chain weakens.

---

## EDGE 4: Reduced Leverage → Tariffs Become Feasible

### Claim
With foreign leverage neutralized, the US can pursue aggressive tariff policy without fear of bond market retaliation.

### Data Required
- Timeline of tariff policy vs Treasury market stress
- Instances where tariff policy was constrained by bond market concerns
- Current administration statements linking debt/tariff policy

### Tier-0/1 Sources
| Source | Tier | What It Proves |
|--------|------|----------------|
| Trump 2018-2019 tariff timeline | 0 | Policy sequence |
| Treasury yields during tariff escalation | 0 | Market reaction |
| USTR announcements | 0 | Policy rationale |
| Fed statements on trade policy | 0 | Central bank concerns |

### Adversarial Attack
**Attack:** Tariffs are already happening without debt domestication. Trump 2018-2019 tariffs happened with $6T foreign holdings. The constraint might not exist.

**Test:** Did the 2018-2019 tariff rounds cause:
- Material yield spikes attributed to foreign retaliation?
- Policy reversal due to bond market pressure?
- Any evidence tariffs were constrained by foreign leverage concerns?

### Control Group
**2018-2019 Tariff Period** - Tariffs escalated significantly while foreign holdings remained high.

If tariffs proceeded without bond market disruption, GENIUS Act is not a **prerequisite** for tariffs - it's a **risk reduction** measure.

### Verdict Template
```
IF 2018-2019 tariffs were constrained by bond concerns: PROVEN (domestication enables more)
IF tariffs proceeded despite foreign holdings: HEURISTIC (domestication is belt-and-suspenders)
IF no evidence of bond market constraint on tariffs: DISPROVEN (solving a problem that doesn't exist)
```

### Weakest Link Risk
This is the weakest edge. Historical evidence may show tariffs don't require debt domestication.

---

## FULL CHAIN VERDICT

| Edge | Current Assessment | Weakest Link |
|------|-------------------|--------------|
| 1: GENIUS → Treasury reserves | **HEURISTIC** | Bill text interpretation (alternatives allowed?) |
| 2: Stablecoin → Replaces foreign | **HEURISTIC** | Scale/timeline (material by when?) |
| 3: Reduced foreign → Reduced leverage | **UNTESTED** | May be paper tiger (Russia absorbed) |
| 4: Reduced leverage → Tariffs feasible | **UNTESTED** | Tariffs already happening without this |

**Chain Confidence:** ~55% (heuristic)

**Critical Tests Needed:**
1. Read GENIUS Act Section 4(a) for exact reserve language
2. Model stablecoin growth vs foreign holdings trajectory
3. Pull Russia 2018 divestment yield impact data
4. Analyze 2018-2019 tariff period for bond market constraints

---

## INVESTMENT IMPLICATIONS (Conditional on Verification)

### If Chain PROVEN:

**Beneficiaries:**
- Stablecoin issuers (Circle, Tether ecosystem)
- Short-duration Treasury ETFs (SHY, BIL, SGOV)
- Domestic manufacturing (reshoring accelerates under tariff cover)
- Russell 2000 domestic revenue exposure

**Losers:**
- Foreign export-dependent economies (China, Germany, Japan)
- Long-duration bonds if inflation expectations rise
- Import-dependent US retailers

**Signals That Flip the Trade:**
- GENIUS Act fails to pass
- Stablecoin market cap growth stalls (<10%/year)
- Foreign holders demonstrate willingness to dump (yield spike event)

### If Chain DISPROVEN:

**Implication:** Tariff policy proceeds independently of debt structure. GENIUS Act is regulatory housekeeping, not strategic enabler.

**Trade:** No change to tariff thesis; GENIUS Act is noise.

---

## PROPOSED EDGES FOR FGIP DATABASE

```python
proposed_edges = [
    ProposedEdge(
        from_node="genius-act-2025",
        to_node="stablecoin-treasury-mandate",
        relationship="REQUIRES",
        confidence=0.7,
        reasoning="Section 4(a) reserve requirements - pending bill text verification",
        tier=1,
    ),
    ProposedEdge(
        from_node="stablecoin-treasury-mandate",
        to_node="domestic-treasury-demand",
        relationship="INCREASES",
        confidence=0.6,
        reasoning="Forced buying creates demand - scale depends on market cap growth",
        tier=2,
    ),
    ProposedEdge(
        from_node="domestic-treasury-demand",
        to_node="foreign-treasury-holdings",
        relationship="REPLACES",
        confidence=0.5,
        reasoning="Substitution effect - timeline and scale uncertain",
        tier=2,
    ),
    ProposedEdge(
        from_node="foreign-treasury-holdings",
        to_node="foreign-policy-leverage",
        relationship="ENABLES",
        confidence=0.4,
        reasoning="Leverage may be theoretical - Russia test case needed",
        tier=2,
    ),
    ProposedEdge(
        from_node="foreign-policy-leverage",
        to_node="tariff-policy-constraints",
        relationship="CONSTRAINS",
        confidence=0.3,
        reasoning="Weakest link - 2018-2019 tariffs proceeded without this",
        tier=2,
    ),
]
```

---

## NEXT ACTIONS

1. **Pull GENIUS Act text** - Congress.gov S.394, read Section 4(a) verbatim
2. **Pull Treasury TIC** - Foreign holdings time series, focus on 2018-2019 period
3. **Pull Russia 2018 divestment data** - Holdings before/after, yield impact
4. **Model stablecoin threshold** - At what cap does demand become material?
5. **Run as ProposedEdges** - Stage in FGIP for human review

---

*Generated: 2026-02-24*
*Chain Confidence: 55% (heuristic, pending verification)*
*Weakest Link: Edge 4 (tariffs already proceed without domestication)*
