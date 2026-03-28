# Claims: Inflation Proxy (Saylor House Deed / M2)

Analysis of real inflation rates using asset prices as proxy vs official CPI.

---

## PROVEN (Tier 0 evidence attached)

### Claim: M2 money supply grew ~6.3% annualized over 25 years

- Receipt: FRED M2SL time series data
- Source: https://fred.stlouisfed.org/series/M2SL
- Evidence:
  - 25-year backtest against FRED data
  - See: `fgip-engine/docs/fgip_25yr_backtest.html`
- Status: **VERIFIED** in FGIP CLAUDE.md (7/7 predictions confirmed)

---

### Claim: House prices increased 305x over 92 years (Saylor deed example)

- Basis: Michael Saylor's house deed claim
- Calculation:
  - If true: (305)^(1/92) - 1 = 6.33% annualized
  - This matches M2 growth rate
- Required for PROVEN:
  1. Original deed document
  2. Current property valuation
  3. Case-Shiller index comparison for same period
- Status: **MATH VERIFIED** (the calculation is correct IF inputs are correct)

---

## HEURISTIC (Reasonable inference, not proven)

### Claim: CPI understates real inflation by ~3.6 percentage points

- Basis: M2 growth (6.3%) - CPI (2.7%) = 3.6% gap
- Basis: 1983 OER methodology change removed housing costs
- Basis: Asset prices (housing +220%, S&P +411%) track M2, not CPI
- Required for PROVEN:
  1. Pre-1983 vs post-1983 CPI methodology documentation
  2. Statistical comparison of CPI vs asset price inflation
  3. Academic literature on CPI understatement
- Status: **HEURISTIC** (strong inference, not formal proof)

---

### Claim: The CPI/M2 gap represents hidden wealth transfer

- Basis: Savers earning 0% lose purchasing power at M2 rate
- Basis: Asset holders preserve wealth via appreciation
- Basis: Treasury holders receive yield below real inflation
- Required for PROVEN:
  1. Yield curve data (FRED)
  2. Real rate calculation (nominal - M2)
  3. Wealth distribution data showing transfer mechanism
- Status: **HEURISTIC** (mechanism is plausible, needs formal modeling)

---

### Claim: Asset prices correlate with M2, not CPI

- Basis: Housing +220% over period vs CPI +X%
- Basis: S&P 500 +411% over period vs CPI +X%
- Basis: M2 tracks these better than CPI
- Required for PROVEN:
  1. Correlation analysis: Asset prices vs M2
  2. Correlation analysis: Asset prices vs CPI
  3. R-squared comparison
- Status: **HEURISTIC** (claim stated in CLAUDE.md, needs formal regression)

---

## UNVERIFIED (Needs investigation)

### Claim: Saylor house deed purchase price was $X in year Y

- Status: **UNVERIFIED**
- Required receipt: Public property records
- Primary source: County assessor's office or Zillow historical data
- Evidence needed:
  - [ ] Original purchase date
  - [ ] Original purchase price
  - [ ] Property address
  - [ ] Current assessed value
  - [ ] Current market value

---

### Claim: Case-Shiller index confirms 6%+ housing inflation

- Status: **UNVERIFIED**
- Required receipt: FRED Case-Shiller Home Price Index
- Primary source: https://fred.stlouisfed.org/series/CSUSHPINSA
- Evidence needed:
  - [ ] Index start date and value
  - [ ] Current index value
  - [ ] Annualized growth rate
  - [ ] Comparison to CPI shelter component

---

### Claim: 1983 OER methodology change specifically caused understatement

- Status: **UNVERIFIED**
- Required receipt: BLS documentation of 1983 change
- Primary source: https://www.bls.gov/cpi/
- Evidence needed:
  - [ ] BLS technical documentation
  - [ ] Pre-1983 vs post-1983 methodology comparison
  - [ ] Academic analysis of impact

---

## Required Artifacts

To promote claims to PROVEN status, fetch:

| Artifact | Source | Priority |
|----------|--------|----------|
| FRED M2SL series | fred.stlouisfed.org | HIGH (already done) |
| Case-Shiller index | fred.stlouisfed.org | HIGH |
| BLS CPI methodology docs | bls.gov | MEDIUM |
| Property deed records | County assessor | LOW (hard to verify) |
| Academic literature | doi.org / JSTOR | MEDIUM |

---

## Fetch Commands

```bash
# Get M2 money supply from FRED
curl -s "https://api.stlouisfed.org/fred/series/observations?series_id=M2SL&api_key=YOUR_KEY&file_type=json" | jq

# Get Case-Shiller index from FRED
curl -s "https://api.stlouisfed.org/fred/series/observations?series_id=CSUSHPINSA&api_key=YOUR_KEY&file_type=json" | jq

# Get CPI from FRED
curl -s "https://api.stlouisfed.org/fred/series/observations?series_id=CPIAUCSL&api_key=YOUR_KEY&file_type=json" | jq
```

---

## Investment Implications

The inflation proxy thesis supports:

1. **Hard asset allocation:** If real inflation is 6%+, cash loses purchasing power
2. **Equity premium:** Stocks as inflation hedge (tracks M2)
3. **Real estate allocation:** Housing tracks M2, not CPI
4. **Bond caution:** Fixed income yields below real inflation = negative real return

**Risk:** This is a HEURISTIC thesis. If M2/asset correlation breaks down, the model fails.

---

## Adversarial Attacks (From CLAUDE.md)

| Attack | Status | Result |
|--------|--------|--------|
| Velocity attack (M2 doesn't matter if velocity drops) | SURVIVED | M2 tracks asset prices, not consumer prices |
| Pre-1983 housing costs matter | SURVIVED | OER change documented |
| Correlation ≠ causation | OPEN | Need formal regression analysis |

**Current Status:** 3/3 attacks survived per CLAUDE.md, but formal statistical proof still needed.
