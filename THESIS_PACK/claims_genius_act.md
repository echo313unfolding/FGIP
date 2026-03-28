# Claims: GENIUS Act (Stablecoin Legislation)

GENIUS Act = "Guiding and Establishing National Innovation for US Stablecoins"

**STATUS: EVIDENCED** (Tier-1 citations exist, Tier-0 artifacts needed)

---

## PROVEN (Tier-0 artifact exists)

*No claims currently have Tier-0 artifacts.*

---

## EVIDENCED (Tier-1 citation exists, needs Tier-0 upgrade)

### Claim: GENIUS Act signed into law with bipartisan support

- Tier-1 source: Paul Hastings LLP legal analysis
- Claimed: 308-122 in House (July 17, 2025), 68-30 in Senate (June 17, 2025)
- Status: **EVIDENCED**
- Required for PROVEN:
  - Artifact: `receipts/genius_act/bill_status.html`
  - Source: congress.gov bill status page
  - Artifact: `receipts/genius_act/roll_call_house.html`
  - Source: clerk.house.gov
  - Artifact: `receipts/genius_act/roll_call_senate.html`
  - Source: senate.gov
- Fetch command:
  ```bash
  curl -s "https://www.congress.gov/bill/119th-congress/senate-bill/XXX" \
    -o THESIS_PACK/receipts/genius_act/bill_status.html
  ```

---

### Claim: Reserve assets must have maturities of 93 days or less

- Tier-1 source: Georgetown Law analysis
- Status: **EVIDENCED**
- Required for PROVEN:
  - Artifact: `receipts/genius_act/bill_text.html`
  - Source: congress.gov bill text with specific section
- Fetch command:
  ```bash
  curl -s "https://www.congress.gov/bill/119th-congress/senate-bill/XXX/text" \
    -o THESIS_PACK/receipts/genius_act/bill_text.html
  ```

---

### Claim: Stablecoin market projected to reach $2T by 2028

- Tier-1 source: U.S. Department of the Treasury (secondary report)
- Status: **EVIDENCED**
- Required for PROVEN:
  - Artifact: `receipts/genius_act/tbac_minutes.pdf`
  - Source: Treasury TBAC meeting minutes with projection
- Fetch command:
  ```bash
  wget "https://home.treasury.gov/system/files/.../tbac_minutes.pdf" \
    -O THESIS_PACK/receipts/genius_act/tbac_minutes.pdf
  ```

---

### Claim: Stablecoin market projected to exceed $3T by 2030

- Tier-1 source: State Street institutional research
- Status: **EVIDENCED**
- Required for PROVEN:
  - Artifact: `receipts/genius_act/state_street_report.pdf`
  - Source: State Street published research (may be paywalled)
- Note: This may remain EVIDENCED if primary is not publicly accessible

---

### Claim: Asset reallocation from bank deposits to Treasuries

- Tier-1 source: State Street analysis
- Status: **EVIDENCED**
- Required for PROVEN:
  - Same artifact as above
- Note: Mechanism claim, may remain HEURISTIC even with primary

---

## HEURISTIC (Inference from proven/evidenced facts)

### Claim: GENIUS Act distributes Treasury demand away from Fed/foreign governments

- Basis: If $2-3T stablecoin market requires Treasury backing (EVIDENCED)
- Basis: Then private sector becomes significant Treasury buyer (INFERENCE)
- Status: **HEURISTIC**
- Required for PROVEN: Post-implementation Treasury auction data showing stablecoin issuer participation

---

### Claim: GENIUS Act puts downward pressure on interest rates

- Basis: Expanded buyer pool for short-term Treasuries (HEURISTIC)
- Basis: Supply/demand dynamics (THEORY)
- Status: **HEURISTIC**
- Required for PROVEN: Yield curve data post-implementation with attribution

---

## UNVERIFIED (Needs investigation)

### Claim: Specific bill number

- Status: **UNVERIFIED**
- Required: Identify exact S. or H.R. number
- Action: Search congress.gov for "GENIUS Act stablecoin"

---

## Investment Implications

| Implication | Status | Reasoning |
|-------------|--------|-----------|
| Bullish for short-term Treasury ETFs | HEURISTIC | New demand = price support (unproven) |
| Bullish for regulated stablecoin issuers | HEURISTIC | Compliance moat (unproven) |
| Treasury demand mechanism | EVIDENCED | State Street confirms, needs primary |

**Note:** All investment implications are HEURISTIC until underlying claims are PROVEN.

---

## Fetch Checklist

- [ ] Identify GENIUS Act bill number on congress.gov
- [ ] Download bill status page
- [ ] Download bill text
- [ ] Download House roll call
- [ ] Download Senate roll call
- [ ] Download TBAC minutes mentioning stablecoins
- [ ] Compute SHA256 for each artifact
- [ ] Add to MANIFEST.json with repro commands
- [ ] Upgrade claims to PROVEN
