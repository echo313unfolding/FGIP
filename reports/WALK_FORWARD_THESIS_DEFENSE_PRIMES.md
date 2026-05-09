# Walk-Forward Mock Trading Report

**Thesis:** `thesis-defense-primes`
**Period:** 2024-05-09 to 2026-05-09
**Universe:** 21 tickers
**Rebalance:** monthly

## Performance Comparison

| Agent | Return | Ann. Return | Sharpe | Sortino | Max DD | Trades |
|-------|--------|-------------|--------|---------|--------|--------|
| cash | 0.0% | 0.0% | 0.0 | 0.0 | 0.0% | 0 |
| equal_weight | 24.3% | 11.1% | 0.837 | 1.172 | 14.28% | 339 |
| spy | 45.3% | 19.81% | 1.187 | 1.494 | 18.77% | 1 |
| momentum | 10.36% | 4.88% | 0.385 | 0.561 | 19.21% | 163 |
| fgip_rules | 3.12% | 1.5% | 0.73 | 1.006 | 2.43% | 96 |

## Risk Rules

- Transaction cost: 10 bps
- Slippage: 5 bps
- Max single name: 5.0%
- Candidate max gross: 25.0%
- Active max gross: 50.0%
- Quarantined: 0% (forced exit)
- No leverage

## FGIP Rules Agent Decisions

- **2024-05-09** | Candidate | LONG_BASKET | gross=0.062 | sources=1 | State=Candidate, Tier0=1, Tier1=0, Sources=1, Edges=2, Score=15, Gross=0.062, Ma
- **2024-06-01** | Candidate | LONG_BASKET | gross=0.062 | sources=1 | State=Candidate, Tier0=1, Tier1=0, Sources=1, Edges=2, Score=15, Gross=0.062, Ma
- **2024-07-01** | Candidate | LONG_BASKET | gross=0.062 | sources=1 | State=Candidate, Tier0=1, Tier1=0, Sources=1, Edges=2, Score=15, Gross=0.062, Ma
- **2024-08-01** | Candidate | LONG_BASKET | gross=0.062 | sources=1 | State=Candidate, Tier0=1, Tier1=0, Sources=1, Edges=2, Score=15, Gross=0.062, Ma
- **2024-09-01** | Candidate | LONG_BASKET | gross=0.062 | sources=1 | State=Candidate, Tier0=1, Tier1=0, Sources=1, Edges=2, Score=15, Gross=0.062, Ma
- **2024-10-01** | Candidate | LONG_BASKET | gross=0.062 | sources=1 | State=Candidate, Tier0=1, Tier1=0, Sources=1, Edges=2, Score=15, Gross=0.062, Ma
- **2024-11-01** | Candidate | LONG_BASKET | gross=0.062 | sources=1 | State=Candidate, Tier0=1, Tier1=0, Sources=1, Edges=2, Score=15, Gross=0.062, Ma
- **2024-12-01** | Candidate | LONG_BASKET | gross=0.062 | sources=1 | State=Candidate, Tier0=1, Tier1=0, Sources=1, Edges=2, Score=15, Gross=0.062, Ma
- **2025-01-01** | Candidate | LONG_BASKET | gross=0.126 | sources=2 | State=Candidate, Tier0=2, Tier1=0, Sources=2, Edges=8, Score=30, Gross=0.125, Ma
- **2025-02-01** | Candidate | LONG_BASKET | gross=0.126 | sources=2 | State=Candidate, Tier0=2, Tier1=0, Sources=2, Edges=8, Score=30, Gross=0.125, Ma
- **2025-03-01** | Candidate | LONG_BASKET | gross=0.126 | sources=2 | State=Candidate, Tier0=2, Tier1=0, Sources=2, Edges=8, Score=30, Gross=0.125, Ma
- **2025-04-01** | Candidate | LONG_BASKET | gross=0.126 | sources=2 | State=Candidate, Tier0=2, Tier1=0, Sources=2, Edges=8, Score=30, Gross=0.125, Ma
- **2025-05-01** | Candidate | LONG_BASKET | gross=0.126 | sources=2 | State=Candidate, Tier0=2, Tier1=0, Sources=2, Edges=8, Score=30, Gross=0.125, Ma
- **2025-06-01** | Candidate | LONG_BASKET | gross=0.126 | sources=2 | State=Candidate, Tier0=2, Tier1=0, Sources=2, Edges=8, Score=30, Gross=0.125, Ma
- **2025-07-01** | Candidate | LONG_BASKET | gross=0.126 | sources=2 | State=Candidate, Tier0=2, Tier1=0, Sources=2, Edges=8, Score=30, Gross=0.125, Ma
- **2025-08-01** | Candidate | LONG_BASKET | gross=0.126 | sources=2 | State=Candidate, Tier0=2, Tier1=0, Sources=2, Edges=9, Score=30, Gross=0.125, Ma
- **2025-09-01** | Candidate | LONG_BASKET | gross=0.126 | sources=2 | State=Candidate, Tier0=2, Tier1=0, Sources=2, Edges=9, Score=30, Gross=0.125, Ma
- **2025-10-01** | Candidate | LONG_BASKET | gross=0.126 | sources=2 | State=Candidate, Tier0=2, Tier1=0, Sources=2, Edges=9, Score=30, Gross=0.125, Ma
- **2025-11-01** | Candidate | LONG_BASKET | gross=0.126 | sources=2 | State=Candidate, Tier0=2, Tier1=0, Sources=2, Edges=9, Score=30, Gross=0.125, Ma
- **2025-12-01** | Candidate | LONG_BASKET | gross=0.126 | sources=2 | State=Candidate, Tier0=2, Tier1=0, Sources=2, Edges=9, Score=30, Gross=0.125, Ma
- **2026-01-01** | Candidate | LONG_BASKET | gross=0.126 | sources=2 | State=Candidate, Tier0=2, Tier1=0, Sources=2, Edges=9, Score=30, Gross=0.125, Ma
- **2026-02-01** | Candidate | LONG_BASKET | gross=0.126 | sources=2 | State=Candidate, Tier0=2, Tier1=0, Sources=2, Edges=9, Score=30, Gross=0.125, Ma
- **2026-03-01** | Candidate | LONG_BASKET | gross=0.126 | sources=2 | State=Candidate, Tier0=2, Tier1=0, Sources=2, Edges=9, Score=30, Gross=0.125, Ma
- **2026-04-01** | Candidate | LONG_BASKET | gross=0.126 | sources=2 | State=Candidate, Tier0=2, Tier1=0, Sources=2, Edges=9, Score=30, Gross=0.125, Ma
- **2026-05-01** | Candidate | LONG_BASKET | gross=0.158 | sources=3 | State=Candidate, Tier0=2, Tier1=1, Sources=3, Edges=10, Score=38, Gross=0.158, M

## Look-Ahead Audit

| Check | Result |
|-------|--------|
| Future sources used | 0 |
| Future prices used | 0 |
| Strategy edited after results | False |
| Ticker universe fixed before test | True |
| Risk rules fixed before test | True |

## Cost

- Wall time: 0.413s
- CPU time: 0.838s

---

FGIP is a research and evidence-mapping tool, not financial advice.