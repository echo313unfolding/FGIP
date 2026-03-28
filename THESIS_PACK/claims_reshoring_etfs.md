# Claims: Reshoring ETFs (MADE/RSHO)

ETFs tracking domestic manufacturing and reshoring themes.

**STATUS: EVIDENCED** (Tier-1 citations exist, Tier-0 artifacts needed)

---

## PROVEN (Tier-0 artifact exists)

*No claims currently have Tier-0 artifacts.*

---

## EVIDENCED (Tier-1 citation exists, needs Tier-0 upgrade)

### Claim: BlackRock launched iShares U.S. Manufacturing ETF (MADE)

- Tier-1 source: ETF Strategy, BlackRock marketing
- Status: **EVIDENCED**
- Required for PROVEN:
  - Artifact: `receipts/reshoring/made_n1a.html`
  - Source: SEC EDGAR N-1A registration statement
- Fetch command:
  ```bash
  # First find CIK for MADE ETF
  curl -s "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=iShares+Manufacturing&type=N-1A&output=atom" \
    -o THESIS_PACK/receipts/reshoring/made_search.xml
  # Then fetch N-1A
  curl -s "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=XXXXXX&type=N-1A" \
    -o THESIS_PACK/receipts/reshoring/made_n1a.html
  ```

---

### Claim: RSHO AUM grew from $6M to $101.5M (16x growth)

- Tier-1 source: Finimize
- Claimed: $6M in May 2023 → $101.5M in just over a year, ~16% YTD gains
- Status: **EVIDENCED**
- Required for PROVEN:
  - Artifact: `receipts/reshoring/rsho_nport_q1_2023.html`
  - Artifact: `receipts/reshoring/rsho_nport_q2_2024.html`
  - Source: SEC EDGAR N-PORT quarterly filings
- Fetch command:
  ```bash
  curl -s "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=Tema+American+Reshoring&type=N-PORT&output=atom" \
    -o THESIS_PACK/receipts/reshoring/rsho_search.xml
  ```
- Note: N-PORT shows total net assets which proves AUM

---

### Claim: Société Générale created investable US onshoring index

- Tier-1 source: ETF Stream
- Claimed: 28-stock index, estimates 350K new reshoring jobs
- Status: **EVIDENCED**
- Required for PROVEN:
  - Artifact: `receipts/reshoring/socgen_index.pdf`
  - Source: SocGen research publication (may be paywalled)
- Note: May remain EVIDENCED if primary is not publicly accessible

---

### Claim: Wall Street explicitly betting on reshoring correction

- Tier-1 source: Inference from multiple ETF launches
- Status: **EVIDENCED**
- Required for PROVEN:
  - Multiple ETF launch filings (MADE N-1A, RSHO N-1A)
  - This is a synthesis claim

---

## HEURISTIC (Inference from evidenced facts)

### Claim: AUM growth indicates institutional adoption

- Basis: RSHO 16x AUM growth (EVIDENCED)
- Basis: "Institutional" requires 13F data showing who holds
- Status: **HEURISTIC**
- Required for PROVEN:
  - Artifact: SEC 13F filings showing institutional RSHO holders
  - Query EDGAR for 13F-HR mentioning RSHO

---

### Claim: MADE/RSHO holdings align with FGIP thesis tickers

- Basis: Both target "reshoring beneficiaries"
- Status: **HEURISTIC**
- Required for PROVEN:
  - Artifact: N-PORT holdings files for both ETFs
  - Compare to FGIP thesis tickers (NUE, STLD, SMR, OKLO, etc.)

---

## Cross-Reference: FGIP Backtest Performance (PROVEN)

| Thesis | Total Return | Alpha | Status |
|--------|--------------|-------|--------|
| reshoring-steel | 0.7% | -5.53% | **PROVEN** |
| nuclear-smr | 24.5% | +2.69% | **PROVEN** |
| defense | 15.2% | +0.44% | **PROVEN** |

**Caution:** Our reshoring-steel-thesis underperformed significantly. If RSHO/MADE have similar holdings, their performance may disappoint.

**Counter-argument (EVIDENCED):** RSHO's 16% YTD gains (per Finimize) suggest their stock selection differs from our steel-heavy thesis. Need N-PORT to verify.

---

## Fetch Priority

| Claim | Source | Priority | Difficulty |
|-------|--------|----------|------------|
| RSHO AUM growth | SEC N-PORT | **HIGH** | EASY |
| MADE launch | SEC N-1A | **HIGH** | EASY |
| RSHO holdings | SEC N-PORT | MEDIUM | EASY |
| MADE holdings | SEC N-PORT | MEDIUM | EASY |
| SocGen index | SocGen research | LOW | HARD (paywall) |

---

## Fetch Checklist

- [ ] Search SEC EDGAR for Tema ETF filings
- [ ] Download RSHO N-PORT (most recent)
- [ ] Download RSHO N-1A (registration)
- [ ] Search SEC EDGAR for iShares Manufacturing
- [ ] Download MADE N-PORT (most recent)
- [ ] Download MADE N-1A (registration)
- [ ] Compute SHA256 for each artifact
- [ ] Add to MANIFEST.json with repro commands
- [ ] Compare holdings to FGIP thesis tickers
- [ ] Upgrade claims to PROVEN
