# Claims: Industrial Base Vulnerability

Documentation of US manufacturing decline, defense industrial base gaps, and China dependency.

**STATUS: EVIDENCED** (Tier-1 citations exist, Tier-0 artifacts needed)

---

## PROVEN (Tier-0 artifact exists)

*No claims currently have Tier-0 artifacts.*

---

## EVIDENCED (Tier-1 citation exists, needs Tier-0 upgrade)

### Claim: Manufacturing declined from 16% to under 10% of GDP

- Tier-1 source: Trace One SAS, TheGlobalEconomy.com
- Claimed: 16.12% peak in 1997 → 9.98% in 2024 (minimum ever)
- Status: **EVIDENCED**
- Required for PROVEN:
  - Artifact: `receipts/industrial_base/fred_mfg_gdp.json`
  - Source: FRED VAPGDPMA or similar series
- Fetch command:
  ```bash
  curl -s "https://api.stlouisfed.org/fred/series/observations?series_id=VAPGDPMA&api_key=YOUR_KEY&file_type=json" \
    -o THESIS_PACK/receipts/industrial_base/fred_mfg_gdp.json
  ```

---

### Claim: 1/3 of US manufacturing jobs lost 2001-2009

- Tier-1 source: Wikipedia (citing BLS)
- Status: **EVIDENCED**
- Required for PROVEN:
  - Artifact: `receipts/industrial_base/bls_mfg_employment.json`
  - Source: BLS employment data series
- Fetch command:
  ```bash
  curl -s "https://api.bls.gov/publicAPI/v2/timeseries/data/CES3000000001" \
    -o THESIS_PACK/receipts/industrial_base/bls_mfg_employment.json
  ```

---

### Claim: China has 232x US shipbuilding capability

- Tier-1 source: American Enterprise Institute (citing ONI declassified)
- Status: **EVIDENCED**
- Required for PROVEN:
  - Artifact: `receipts/industrial_base/oni_shipbuilding.pdf`
  - Source: Office of Naval Intelligence declassified slide/report
- Note: **MANUAL FETCH REQUIRED** - need to locate actual ONI document
- This is the highest priority Tier-0 upgrade - the "232x" number is cited everywhere but the primary is elusive

---

### Claim: China built 1,000+ commercial vessels in 2024 vs US 8

- Tier-1 source: Thinkers360
- Status: **EVIDENCED**
- Required for PROVEN:
  - Artifact: Same ONI document or maritime industry report
  - Source: Clarksons Research, Lloyd's List, or ONI

---

### Claim: Zero domestic production of shipping containers

- Tier-1 source: Thinkers360
- Claimed: China manufactures 96% of shipping containers used in US
- Status: **EVIDENCED**
- Required for PROVEN:
  - Artifact: `receipts/industrial_base/container_industry.pdf`
  - Source: Industry trade association data or DOT report

---

### Claim: Zero domestic production of ship-to-shore cranes

- Tier-1 source: Thinkers360
- Claimed: China manufactures 80% of ship-to-shore cranes used in US
- Status: **EVIDENCED**
- Required for PROVEN:
  - Artifact: Same as above or CISA infrastructure report

---

### Claim: Last ammunition plant built December 26, 1940

- Tier-1 source: American Enterprise Institute
- Status: **EVIDENCED**
- Required for PROVEN:
  - Artifact: `receipts/industrial_base/army_ammo_history.pdf`
  - Source: Army historical records or GAO report on ammunition production
- Fetch command: Need to locate Army or GAO primary source

---

### Claim: US military stockpiles could deplete in less than one week vs China

- Tier-1 source: Fox Business (citing CSIS)
- Status: **EVIDENCED**
- Required for PROVEN:
  - Artifact: `receipts/industrial_base/csis_munitions.pdf`
  - Source: CSIS report (specific title needed)
- Fetch command:
  ```bash
  # Need to identify exact CSIS report URL
  wget "https://www.csis.org/analysis/..." \
    -O THESIS_PACK/receipts/industrial_base/csis_munitions.pdf
  ```

---

### Claim: China controls 90% of rare earth processing

- Tier-1 source: Rare Earth Exchanges
- Status: **EVIDENCED**
- Required for PROVEN:
  - Artifact: `receipts/industrial_base/usgs_rare_earth.pdf`
  - Source: USGS Mineral Commodity Summaries
- Fetch command:
  ```bash
  wget "https://pubs.usgs.gov/periodicals/mcs2025/mcs2025-rare-earths.pdf" \
    -O THESIS_PACK/receipts/industrial_base/usgs_rare_earth.pdf
  ```

---

### Claim: China banned germanium, gallium, antimony exports to US (Dec 2024)

- Tier-1 source: RFF (Resources for the Future)
- Status: **EVIDENCED**
- Required for PROVEN:
  - Artifact: `receipts/industrial_base/china_export_ban.pdf`
  - Source: Chinese Ministry of Commerce announcement (translated) or US Commerce response

---

### Claim: China export ban suspension is temporary (Nov 2025 - Nov 2026)

- Tier-1 source: CNBC, Pillsbury Winthrop Shaw Pittman
- Status: **EVIDENCED**
- Required for PROVEN:
  - Artifact: Same as above or USTR/Commerce announcement

---

## HEURISTIC (Inference from evidenced facts)

### Claim: Deindustrialization was policy-driven, not market-driven

- Basis: $2.3B Koch network assets backing amicus briefs (UNVERIFIED)
- Basis: $1.8B Chamber of Commerce lobbying since 1998 (UNVERIFIED)
- Status: **HEURISTIC**
- Required for PROVEN: OpenSecrets lobbying data + Supreme Court amicus filings

---

### Claim: Industrial base vulnerability creates national security crisis

- Basis: All the above data points (EVIDENCED)
- Basis: "Crisis" is interpretation
- Status: **HEURISTIC**
- Note: MWI "Logistics Left of Boom" supports this framing but doesn't prove it

---

## Fetch Priority

| Claim | Source | Priority | Difficulty |
|-------|--------|----------|------------|
| 232x shipbuilding | ONI declassified | **HIGH** | HARD (need to locate) |
| One week munitions | CSIS report | **HIGH** | MEDIUM |
| 90% rare earth | USGS MCS | **HIGH** | EASY |
| Mfg GDP decline | FRED | MEDIUM | EASY |
| Mfg jobs lost | BLS | MEDIUM | EASY |
| Container/crane production | Industry/DOT | LOW | MEDIUM |
| Ammo plant history | Army/GAO | LOW | MEDIUM |
| China export ban | Commerce/MOFCOM | LOW | MEDIUM |

---

## Fetch Checklist

- [ ] Locate ONI shipbuilding slide (AEI may have direct link)
- [ ] Download CSIS munitions report
- [ ] Download USGS rare earth mineral commodity summary
- [ ] Fetch FRED VAPGDPMA series
- [ ] Fetch BLS manufacturing employment series
- [ ] Compute SHA256 for each artifact
- [ ] Add to MANIFEST.json with repro commands
- [ ] Upgrade claims to PROVEN
