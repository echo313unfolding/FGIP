# THESIS_PACK - FGIP Proof Infrastructure

**Status: 20% PROVEN** (9/45 claims have Tier-0 artifacts)

This folder contains structured claims with explicit evidence requirements and tier classifications.
The goal is to transform FGIP from "trust the graph" to "here are receipts."

---

## Current Reality Check

| Status | Count | What It Means |
|--------|-------|---------------|
| **PROVEN** | 9 | Tier-0 artifact exists locally + SHA256 hash |
| **EVIDENCED** | 19 | Tier-1 citation exists, NO Tier-0 artifact yet |
| **HEURISTIC** | 12 | Inference from proven facts |
| **UNVERIFIED** | 5 | Claim exists, no acceptable evidence |

**Only backtest receipts are PROVEN.** Everything else is EVIDENCED at best until primary artifacts are fetched and stored.

---

## Taxonomy (Court-Grade Receipts Rule)

### Tier-0 (Primary Receipt) = PROVEN
- Saved artifact (PDF/HTML/JSON) from:
  - congress.gov (bill status, roll call, text)
  - clerk.house.gov / senate.gov votes
  - SEC EDGAR (N-PORT, N-1A, prospectus)
  - Treasury (TBAC minutes), FRED series
  - USGS, ONI, CSIS (primary government/think tank docs)
- Stored locally in `THESIS_PACK/receipts/<category>/`
- Has SHA256 in MANIFEST
- Repro command included (curl/wget + date)

### Tier-1 (Secondary but reputable) = EVIDENCED
- Law firm analysis (Paul Hastings, etc.)
- Major outlet articles (Reuters, WSJ)
- Think tank summaries (AEI citing ONI)
- Fund marketing pages
- **Cannot** alone upgrade to PROVEN

### HEURISTIC
- Inference from PROVEN facts
- Must cite which PROVEN claims it derives from

### UNVERIFIED
- Claim exists, no acceptable evidence
- Must specify what Tier-0 source would verify it

---

## What's Actually PROVEN (9 claims)

All backtest receipts - local JSON files with SHA256 hashes:

| Thesis | Return | Alpha | Receipt Hash |
|--------|--------|-------|--------------|
| nuclear-smr | 24.5% | +2.69% | `3b5b66c4...` |
| uranium | 21.7% | +1.56% | `32d80c93...` |
| rare-earth | 17.9% | +1.36% | `b6d11181...` |
| defense | 15.2% | +0.44% | `e1e1aa45...` |
| ai-datacenter | 13.7% | -0.91% | `3f0a7191...` |
| infrastructure | 11.2% | -2.00% | `34e4b842...` |
| semiconductor | 3.4% | -4.49% | `4a1f713f...` |
| reshoring-steel | 0.7% | -5.53% | `f7752078...` |
| SUMMARY | 4/8 beat SPY | avg 0.03 Sharpe | `4c148e6d...` |

---

## What's EVIDENCED (needs Tier-0 upgrade)

### GENIUS Act (5 claims)
- Bill signed 308-122 / 68-30 → **Need:** congress.gov roll call + bill status
- 93-day maturity requirement → **Need:** bill text section citation
- $2-3T stablecoin projection → **Need:** Treasury TBAC minutes PDF

### Reshoring ETFs (4 claims)
- RSHO AUM $6M → $101.5M → **Need:** SEC EDGAR N-PORT filing
- BlackRock MADE launch → **Need:** SEC EDGAR N-1A filing

### Industrial Base (11 claims)
- 232x China shipbuilding → **Need:** ONI declassified document
- One week munitions → **Need:** CSIS report PDF
- 90% rare earth dependency → **Need:** USGS mineral summary
- Manufacturing 16% → 9.8% GDP → **Need:** FRED VAPGDPMA series

### Inflation Proxy (1 claim)
- M2 growth rate → **Need:** FRED M2SL series with computed CAGR

---

## Next Work Order: WO-FGIP-PACK-TIER0-01

**"Downgrade + fetch primaries"**

1. Fetch congress.gov GENIUS Act artifacts
2. Fetch SEC EDGAR N-PORT/N-1A for RSHO/MADE
3. Fetch CSIS munitions report PDF
4. Locate ONI declassified shipbuilding slide
5. Fetch USGS rare earth mineral summary
6. Fetch FRED M2SL + CSUSHPINSA series
7. Store all in `THESIS_PACK/receipts/<category>/`
8. Update MANIFEST with SHA256 + repro commands
9. Only then re-upgrade claims to PROVEN

---

## Folder Structure

```
THESIS_PACK/
├── README.md                      # This file
├── claims_backtest_results.md     # 9 PROVEN (local artifacts)
├── claims_genius_act.md           # 5 EVIDENCED (need congress.gov)
├── claims_industrial_base.md      # 11 EVIDENCED (need ONI/CSIS/USGS)
├── claims_reshoring_etfs.md       # 4 EVIDENCED (need SEC EDGAR)
├── claims_inflation_proxy.md      # 1 EVIDENCED (need FRED)
├── status.json                    # Aggregate counts
└── receipts/
    ├── MANIFEST.json              # Artifact registry
    ├── backtest/                  # Symlink to paper_trade receipts
    ├── genius_act/                # EMPTY - needs fetches
    ├── reshoring/                 # EMPTY - needs fetches
    ├── industrial_base/           # EMPTY - needs fetches
    └── inflation/                 # EMPTY - needs fetches
```

---

## Verification Commands

```bash
# Validate JSON files
python3 -m json.tool THESIS_PACK/status.json
python3 -m json.tool THESIS_PACK/receipts/MANIFEST.json

# Check actual PROVEN count
cat THESIS_PACK/status.json | jq '.summary.PROVEN'

# Verify backtest hashes
sha256sum THESIS_PACK/receipts/backtest/*.json

# List what needs Tier-0 upgrade
cat THESIS_PACK/receipts/MANIFEST.json | jq '.pending_tier0_fetches'
```

---

## Why This Discipline Matters

If you're going to use this system to justify real decisions, the entire chain must survive an adversary who wants to shred it.

"Finimize said" is not a receipt.
"Paul Hastings said" is not a receipt.
"AEI citing ONI" is not a receipt.

A receipt is: **artifact file + SHA256 + repro command**.
