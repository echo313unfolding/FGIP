# Claims: Backtest Results

Backtest period: 2024-01-01 to 2026-02-28
Benchmark: SPY
Initial capital: $100,000

---

## PROVEN (Tier 0 evidence attached)

### Claim: nuclear-smr-thesis achieved 24.5% total return with +2.7% alpha vs SPY

- Receipt: `receipts/backtest/backtest_20260303T015754Z.json`
- Hash: `sha256:3b5b66c49515c1b6db0ea0100d465eba373e0e3627e658f50764d151d11491bf`
- Metrics:
  - Total Return: 24.49%
  - Annualized Return: 10.26%
  - Alpha: +2.69%
  - Sharpe: 0.82
  - Max Drawdown: -6.18%
  - Win Rate: 70.9%
- Reproduce: `python3 tools/paper_trade.py fgip.db --thesis nuclear-smr-thesis --backtest`

---

### Claim: uranium-thesis achieved 21.7% total return with +1.6% alpha vs SPY

- Receipt: `receipts/backtest/backtest_20260303T015757Z.json`
- Hash: `sha256:32d80c93b23877ade8927c9bdb0852e9375f20ce95eb25a2932a746bc19a465d`
- Metrics:
  - Total Return: 21.74%
  - Annualized Return: 9.17%
  - Alpha: +1.56%
  - Sharpe: 0.58
  - Max Drawdown: -7.48%
  - Win Rate: 62.7%
- Reproduce: `python3 tools/paper_trade.py fgip.db --thesis uranium-thesis --backtest`

---

### Claim: rare-earth-thesis achieved 17.9% total return with +1.4% alpha vs SPY

- Receipt: `receipts/backtest/backtest_20260303T015807Z.json`
- Hash: `sha256:b6d111814c55cc33087911fd803e6ecb08cb3d9e68d87573376d4ad74841410a`
- Metrics:
  - Total Return: 17.89%
  - Annualized Return: 7.61%
  - Alpha: +1.36%
  - Sharpe: 0.47
  - Max Drawdown: -5.92%
  - Win Rate: 58.3%
- Reproduce: `python3 tools/paper_trade.py fgip.db --thesis rare-earth-thesis --backtest`

---

### Claim: defense-anduril-thesis achieved 15.2% total return with +0.4% alpha vs SPY

- Receipt: `receipts/backtest/backtest_20260303T015804Z.json`
- Hash: `sha256:e1e1aa459bd60aa6bdd12cde8ce132a8acf180659139b239e58454aa1692e183`
- Metrics:
  - Total Return: 15.18%
  - Annualized Return: 6.50%
  - Alpha: +0.44%
  - Sharpe: 0.69
  - Max Drawdown: -1.59%
  - Win Rate: 82.0%
- Reproduce: `python3 tools/paper_trade.py fgip.db --thesis defense-anduril-thesis --backtest`

---

### Claim: 4 of 8 theses beat SPY with positive alpha

- Receipt: `receipts/backtest/SUMMARY.json`
- Hash: `sha256:4c148e6d5841c25f2dc7545b6d3b0f81020ee21d067d0b37bac93b1ba5e5932b`
- Evidence:
  - Theses with positive alpha:
    1. nuclear-smr-thesis: +2.69%
    2. uranium-thesis: +1.56%
    3. rare-earth-thesis: +1.36%
    4. defense-anduril-thesis: +0.44%
  - Theses with negative alpha:
    1. ai-data-center-power: -0.91%
    2. infrastructure-picks-shovels: -2.00%
    3. semiconductor-materials: -4.49%
    4. reshoring-steel-thesis: -5.53%
- Reproduce: `cat receipts/paper_trade/SUMMARY.json | jq '.results[] | {thesis_id, alpha}'`

---

### Claim: All 8 theses had max drawdown under 15%

- Receipt: `receipts/backtest/SUMMARY.json`
- Hash: `sha256:4c148e6d5841c25f2dc7545b6d3b0f81020ee21d067d0b37bac93b1ba5e5932b`
- Evidence:
  - Worst drawdown: -7.48% (uranium-thesis)
  - Best drawdown: -1.59% (defense-anduril-thesis)
  - All theses: < 15% max drawdown
- Reproduce: `cat receipts/paper_trade/SUMMARY.json | jq '.results[] | {thesis_id, max_drawdown}'`

---

### Claim: Average thesis Sharpe ratio was 0.03

- Receipt: `receipts/backtest/SUMMARY.json`
- Hash: `sha256:4c148e6d5841c25f2dc7545b6d3b0f81020ee21d067d0b37bac93b1ba5e5932b`
- Evidence:
  - avg_sharpe: 0.032
  - Only 2 theses had Sharpe > 0.7 (nuclear-smr: 0.82, defense: 0.69)
  - 2 theses had negative Sharpe (semiconductor-materials, reshoring-steel)
- Note: This is NOT institutional-grade risk-adjusted return

---

## HEURISTIC (Reasonable inference from proven data)

### Claim: Nuclear/uranium sector shows strongest thesis validity

- Basis: Both nuclear-smr-thesis and uranium-thesis in top 4 performers
- Basis: Combined average alpha of +2.1% vs SPY
- Basis: Related supply chain exposure (SMRs need uranium fuel)
- Required for PROVEN: Correlation analysis showing independent signal vs SPY

---

### Claim: Defense thesis shows lowest volatility profile

- Basis: defense-anduril-thesis had lowest max drawdown (-1.59%)
- Basis: Highest win rate (82.0%)
- Basis: Consistent with government contract revenue stability
- Required for PROVEN: Sector volatility comparison vs market

---

### Claim: Reshoring thesis currently invalidated

- Basis: reshoring-steel-thesis returned only 0.7% total (vs SPY 47.9%)
- Basis: -5.53% alpha is worst of all theses
- Basis: Tariff/reshoring may be "priced in" or not materializing yet
- Required for PROVEN: Event study on tariff announcement dates vs steel prices

---

## UNVERIFIED (Not supported by current data)

### Claim: "15.6%/yr sustainable returns" - REJECTED

- Status: **NOT SUPPORTED BY DATA**
- Actual: Best thesis annualized at 10.3%, not 15.6%
- Note: Do not cite this claim - it is inconsistent with receipts

---

### Claim: "Money printer thesis" - REJECTED

- Status: **NOT SUPPORTED BY DATA**
- Actual: avg_sharpe = 0.03, which is noise-level risk-adjusted return
- Actual: 4/8 theses underperformed SPY
- Note: This is **signal for thesis validation**, not alpha generation

---

## Summary Statistics

| Thesis | Total Return | Alpha | Sharpe | Status |
|--------|--------------|-------|--------|--------|
| nuclear-smr | 24.5% | +2.69% | 0.82 | PROVEN |
| uranium | 21.7% | +1.56% | 0.58 | PROVEN |
| rare-earth | 17.9% | +1.36% | 0.47 | PROVEN |
| defense | 15.2% | +0.44% | 0.69 | PROVEN |
| ai-data-center | 13.7% | -0.91% | 0.34 | PROVEN |
| infrastructure | 11.2% | -2.00% | 0.09 | PROVEN |
| semiconductor | 3.4% | -4.49% | -1.29 | PROVEN |
| reshoring-steel | 0.7% | -5.53% | -1.45 | PROVEN |

---

## Verification Command

```bash
# Verify all receipt hashes
cd /home/voidstr3m33/fgip-engine
sha256sum receipts/paper_trade/*.json
```
