# Work Order Reality Audit — 2026-03-16

**Trigger:** Claude caught sign-off on WO-M/N when code was not present.
**Rule:** Receipts or it didn't happen.

## Status Summary

| WO | Name | Status | Completion | Code | Tests | Receipts |
|----|------|--------|------------|------|-------|----------|
| **K** | Trading Research Runtime | **PARTIAL** | 80% | Yes | Yes (43/44) | Yes (8 backtests) |
| **L** | Backtest Integrity | **PARTIAL** | 40% | Yes (wrong scope) | No | Partial |
| **M** | Thesis→Signal→Trade Trace | **PARTIAL** | 35% | Yes (building blocks) | No | Partial |
| **N** | Market Realism + Determinism | **SPEC** | 10% | No | No | No |

## Last Verified Baseline: WO-K (Partial)

**What's real:**
- `ConvictionEngine` — 1256 lines, tier-aware scoring, counter-thesis ✓
- `TradePlanAgent` — decision gates, trade memos ✓
- `PortfolioBacktest` — no-lookahead, slippage, conviction sizing ✓
- 8 thesis backtests with SHA256 hashes (2026-03-03) ✓
- 43/44 tests pass ✓

**What's stub:**
- `position_sizing.py` — functions defined, not wired into backtest loop
- `trailing_stop_pct` — field exists, implementation unclear

## WO-L Gaps (Backtest Integrity)

**Exists:** LeakDetector (pipeline scope), anti-lookahead in backtest, inputs_hash in receipts
**Missing:** DataValidator, ResultAuditor, backtest test suite, out-of-sample separation, walk-forward validation, statistical significance testing

## WO-M Gaps (Traceability)

**Exists:** DataProvenance, ProvenanceTracker, ConvictionReport, TradeMemo, Gate audit trail, belief revision
**Missing:** ThesisSnapshot, SignalSnapshot, ConvictionTrace, TradeDecision, BenchmarkComparison, end-to-end trace chain

## WO-N Gaps (Market Realism)

**Exists:** slippage_bps=10 (flat), commission_per_trade=0.0, PriceManager caching
**Missing:** DataSnapshot, ExecutionModel, RobustnessTest, Monte Carlo, market impact, fill model, fragility flags — essentially everything

## Forward Path

1. **Complete WO-K** — wire position_sizing, verify stops, add backtest tests
2. **Build WO-L** — BacktestAuditor (data validation, statistical tests, out-of-sample)
3. **Build WO-M** — TraceChain (snapshot → snapshot → trace → decision → result)
4. **Build WO-N** — DataSnapshot, ExecutionModel (presets), RobustnessTest (Monte Carlo)
5. **Then WO-O** — Experiment Registry (only after real artifacts exist to register)

## Manifest Location

Full machine-readable audit: `receipts/audit/work_order_reality_audit.json`
