# Walk-Forward Mock Trading

## Purpose

Tests whether FGIP evidence receipts can drive point-in-time mock trading decisions without look-ahead bias.

The real question is not "can Claude trade" — it is:

> Can the FGIP evidence system generate useful point-in-time decisions?

## Architecture

```
historical source registry
  |
point-in-time fact snapshot (build_point_in_time_snapshot.py)
  |
candidate graph edges
  |
thesis state engine (Candidate / Active / Quarantined)
  |
agent decision (rules-only or Claude-assisted)
  |
mock execution engine (with costs and slippage)
  |
performance receipt
```

## Agents

| Agent | Description |
|-------|-------------|
| cash | 100% cash. Lower bound. |
| equal_weight | Equal-weight the universe, monthly rebalance. |
| spy | 100% SPY. Market benchmark. |
| momentum | Top-5 by 3-month momentum, 50% gross. Price-only baseline. |
| fgip_rules | Evidence-gated rules. Position size scales with signal count and thesis state. |

## Point-in-Time Rule

At each decision date, the agent may only see:
- Sources with `published_at <= decision_date`
- Facts whose source `published_at <= decision_date`
- Edges whose fact/source `published_at <= decision_date`
- Market prices through previous close only

Forbidden: future sources, future prices, future receipt states, internet access.

## Risk Rules

- Candidate thesis: max 25% gross exposure
- Active thesis: max 50% gross exposure
- Quarantined thesis: 0% exposure (forced exit)
- Max single-name exposure: 5%
- Transaction cost: 10 bps
- Slippage: 5 bps
- No leverage

## Decision Actions

| Action | Meaning |
|--------|---------|
| NO_TRADE | No position change |
| WATCH | Evidence noted, no trade yet |
| LONG_BASKET | Buy equal-weight basket |
| HEDGE | Add hedge instruments |
| REDUCE | Reduce exposure |
| EXIT | Close all positions |

## Scoring

Performance is scored on 10 dimensions:
1. Total return
2. Max drawdown
3. Sharpe ratio
4. Sortino ratio
5. Trade count / turnover
6. Transaction costs
7. Thesis-state accuracy
8. Evidence discipline (did it avoid trading before evidence?)
9. Did it promote claims too early?
10. Comparison to baselines

## Key Interpretation

If FGIP rules-only agent beats momentum and equal-weight:
> The evidence graph IS the intelligence.

If FGIP rules-only agent matches or underperforms:
> Evidence gating adds discipline but not alpha at this frequency.

Both are useful findings.

## Usage

```bash
python3 tools/walk_forward_mock_trader.py
python3 tools/walk_forward_mock_trader.py --thesis thesis-dollar-resilience-rails
python3 tools/walk_forward_mock_trader.py --start 2024-05-09 --end 2026-05-09
```

## Output

- `receipts/backtests/walk_forward_*.json` — Full simulation receipt
- `receipts/mock_trades/*.json` — Individual decision receipts
- `reports/WALK_FORWARD_*.md` — Human-readable comparison report

## Disclaimer

FGIP is a research and evidence-mapping tool, not financial advice or an automated trading system. Mock trading results are simulated and do not represent actual trading performance. Past performance does not indicate future results.
