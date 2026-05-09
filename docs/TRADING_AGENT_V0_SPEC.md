# GO FGIP_TRADING_AGENT_V0 — On-Box Trading Collaborator Spec

## What This Is

An on-box trading agent that:
1. Watches your thesis tickers 24/7 (daily price + catalyst feeds)
2. Runs signal detection against FGIP graph + market data
3. Generates **proposals** (not executions) with full receipts
4. Pushes alerts to your phone when action is warranted
5. Logs everything for audit (WO-L/M compliance)

## What This Is NOT

- Not autonomous execution (Layer 2 is human-gated)
- Not a "bot" — it's a decision-support system with receipts
- Not real-time HFT — daily/hourly cadence is the target
- Not a replacement for the FGIP graph — it READS the graph for conviction

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  FGIP TRADING AGENT                   │
├─────────────────────────────────────────────────────┤
│                                                      │
│  Layer 0: DATA INGEST (cron, automated)              │
│  ├─ PriceManager.bulk_fetch() — daily OHLCV         │
│  ├─ FERC eLibrary scraper — capacity filings        │
│  ├─ State PUC RSS — docket alerts (MI, GA)          │
│  └─ Earnings keyword scanner — "data center",       │
│     "throughput", "capacity"                         │
│                                                      │
│  Layer 1: SIGNAL ENGINE (runs after ingest)          │
│  ├─ ConvictionEngine — graph-derived conviction      │
│  ├─ MarketTapeAgent — technicals + volume           │
│  ├─ CascadeDetector — timing stage advancement      │
│  ├─ RiskCalculator — position size + stops          │
│  └─ Output: SignalProposal (structured)             │
│                                                      │
│  Layer 2: PROPOSAL GATE (human approval)             │
│  ├─ Proposal displayed via CLI / webhook            │
│  ├─ User approves/rejects/modifies                  │
│  └─ Approved proposals → execution queue            │
│                                                      │
│  Layer 3: EXECUTION (after approval only)            │
│  ├─ Alpaca API (stocks) — paper first, then live    │
│  ├─ Solana program (crypto) — your existing infra   │
│  ├─ Immediate stop-loss placement                   │
│  └─ Fill receipt logged                             │
│                                                      │
│  Layer 4: MONITORING (continuous)                    │
│  ├─ Daily P&L calculation                           │
│  ├─ Trailing stop adjustment                        │
│  ├─ Thesis invalidation check                       │
│  └─ Weekly summary report                           │
│                                                      │
└─────────────────────────────────────────────────────┘
```

## Existing Components (Already Built)

| Component | File | Status |
|-----------|------|--------|
| Price data ingest | `fgip/data/price_manager.py` | COMPLETE |
| Position sizing | `fgip/backtest/position_sizing.py` | COMPLETE |
| Risk metrics | `fgip/backtest/risk_metrics.py` | COMPLETE |
| Conviction engine | `fgip/agents/conviction_engine.py` | COMPLETE |
| Market tape (technicals) | `fgip/agents/market_tape.py` | COMPLETE |
| Trade plan (gates) | `fgip/agents/trade_plan_agent.py` | COMPLETE |
| Forecast distributions | `fgip/agents/forecast_agent.py` | COMPLETE |
| FGIP graph (1910 nodes) | `fgip.db` | COMPLETE |
| Allocation policy | `fgip/allocator/policy.py` | COMPLETE |
| RSS signal scanner | `fgip/agents/rss_signal.py` | COMPLETE |

## New Components to Build

### 1. `fgip/agents/trading_agent.py` — Orchestrator

The top-level agent that ties everything together into a single daily run.

```python
class TradingAgent:
    """Daily run: ingest → signal → propose → monitor."""

    def daily_scan(self) -> List[SignalProposal]:
        """Run full pipeline, return proposals."""

    def check_exits(self) -> List[ExitSignal]:
        """Check existing positions for stop/target/invalidation."""

    def portfolio_status(self) -> PortfolioReport:
        """Current state: positions, P&L, risk metrics."""
```

### 2. `fgip/agents/cascade_detector.py` — Timing Cascade Stage Tracker

Monitors the FERC → gathering → permits → production cascade.

```python
class CascadeDetector:
    """Detect timing cascade stage advancement."""

    def check_stage(self, thesis_id: str) -> CascadeState:
        """What stage is this thesis at in the timing cascade?"""
        # Reads FGIP graph edges for:
        # - PUC filings (stage 1)
        # - FERC capacity reservations (stage 4 — biggest alpha)
        # - Permit surge signals (stage 5-6)
```

### 3. `fgip/agents/alert_dispatcher.py` — Push Notifications

```python
class AlertDispatcher:
    """Push proposals to user's phone."""

    def send_proposal(self, proposal: SignalProposal):
        """Send via Pushover/Telegram."""

    def send_exit_alert(self, exit_signal: ExitSignal):
        """Urgent: position needs attention."""
```

### 4. `fgip/execution/paper_trader.py` — Paper Trading First

```python
class PaperTrader:
    """Simulated execution for validation before going live."""

    def execute_buy(self, proposal: SignalProposal) -> PaperFill:
        """Simulate fill at next-day open + slippage."""

    def execute_sell(self, position_id: str, reason: str) -> PaperFill:
        """Simulate exit."""
```

### 5. `fgip/execution/alpaca_executor.py` — Live Execution (Phase 2)

```python
class AlpacaExecutor:
    """Live execution via Alpaca API. Paper mode first."""

    def __init__(self, paper: bool = True):
        """Start in paper mode. Must explicitly switch to live."""
```

## Watchlist (From Thesis Nodes)

### Tier 1 — Highest Conviction (daily scan)
```
DTM   — DT Midstream (FERC/NEXUS, top pick)
AR    — Antero Resources (Appalachian E&P)
MPLX  — MPLX LP (Ohio gathering)
EQT   — EQT Corp (largest Appalachian)
WMB   — Williams Companies (Transco)
```

### Tier 2 — Structural Bottleneck (daily scan)
```
AG    — First Majestic (silver)
PAAS  — Pan American Silver
FCX   — Freeport McMoRan (copper)
CEG   — Constellation Energy (nuclear)
GEV   — GE Vernova (gas turbines)
```

### Tier 3 — Utilities / Power (weekly scan)
```
DTE   — DTE Energy (Michigan, Stargate)
CMS   — CMS Energy (Grand Rapids)
SO    — Southern Company (Hampton/GA)
VST   — Vistra (ERCOT/nuclear)
OKLO  — Oklo (SMR, long-dated)
```

## Signal Types

### Entry Signals
| Signal | Source | Confidence Boost |
|--------|--------|-----------------|
| FERC capacity filing | FERC eLibrary scrape | +2 conviction |
| PUC approval | State docket | +1 conviction |
| Volume breakout (>2x ADV + price > SMA20) | MarketTapeAgent | Confirms timing |
| Earnings keyword ("data center capacity") | Transcript scan | +1 conviction |
| Field observation logged | FGIP graph new edge | +1 conviction |
| Cascade stage advance | CascadeDetector | Confirms thesis |

### Exit Signals
| Signal | Action |
|--------|--------|
| Price < trailing stop (ATR-based) | EXIT immediately |
| Thesis invalidation (graph edge disproven) | EXIT within 1 day |
| Gas < $3.00 for 2 quarters (AR-specific) | EXIT AR only |
| Target reached (2x conviction-weighted) | TRIM 50% |
| Daily drawdown > 5% portfolio | HALT new entries |

## Risk Parameters (Hard-Coded, Not AI-Adjustable)

```python
MAX_SINGLE_POSITION = 0.20      # 20% of portfolio
MAX_SECTOR_EXPOSURE = 0.40      # 40% in one sector
MAX_DAILY_LOSS = 0.05           # 5% portfolio — halt all entries
TRAILING_STOP_ATR_MULT = 2.0    # 2x ATR trailing stop
MIN_CONVICTION_TO_TRADE = 3     # Level 3+ only
KELLY_FRACTION = 0.25           # Quarter Kelly
MAX_ADV_PARTICIPATION = 0.01    # 1% of avg daily volume
SLIPPAGE_BPS = 10               # 10 bps assumed slippage
```

**These are NOT tunable by the AI.** They are safety rails. Only you modify them.

## Proposal Format (What You See on Your Phone)

```
📊 FGIP SIGNAL: BUY DTM

Conviction: 4/5 (FERC filing + volume breakout)
Position: 12% ($6,000 of $50,000)
Entry: ~$78.50 (market @ open)
Stop: $72.30 (2x ATR below)
Target: $95.00 (cascade stage 5 analog)

WHY:
- FERC NEXUS capacity reservation filed 2026-05-02
- Volume 3.2x ADV today (institutional accumulation)
- Graph: 8 edges supporting, 0 contradicting
- Cascade stage: 4 (FERC) — biggest alpha window

RISK:
- Gas < $3.00 sustained invalidates E&P leg
- Michigan PUC reversal (AG motion pending)

APPROVE / REJECT / MODIFY
```

## Cron Schedule

```
# Daily (6 AM ET, before market open)
0 6 * * 1-5  python3 -m fgip.agents.trading_agent --daily-scan

# Hourly during market (9:30 AM - 4 PM ET)
30 9-15 * * 1-5  python3 -m fgip.agents.trading_agent --check-exits

# Weekly (Sunday 8 PM)
0 20 * * 0  python3 -m fgip.agents.trading_agent --weekly-report

# Monthly (1st of month)
0 8 1 * *  python3 -m fgip.agents.trading_agent --rebalance-check
```

## Implementation Phases

### Phase 1: Scanner (THIS SPRINT)
- Wire up daily price ingest for watchlist
- Connect existing ConvictionEngine + MarketTapeAgent
- Generate proposals to local JSON file
- CLI: `python3 -m fgip.agents.trading_agent --scan`
- **No execution. Read-only.**

### Phase 2: Alerts + Paper Trading
- AlertDispatcher (Pushover or Telegram bot)
- PaperTrader (simulated fills, track P&L)
- Cron schedule active
- **Still no real money.**

### Phase 3: Live Execution (Gated)
- Alpaca API (paper mode first, verify 30 days)
- Switch to live only after paper P&L is positive
- Solana program integration for crypto leg
- **Real money, human-approved only.**

## Receipt Format

Every proposal, approval, fill, and exit generates a receipt:

```json
{
  "receipt_id": "trade-proposal-dtm-20260505-001",
  "type": "PROPOSAL",
  "timestamp": "2026-05-05T06:00:00Z",
  "symbol": "DTM",
  "direction": "BUY",
  "conviction": 4,
  "position_pct": 0.12,
  "entry_target": 78.50,
  "stop_loss": 72.30,
  "signals": [
    {"type": "FERC_FILING", "confidence": 0.85, "source": "ferc_elibrary"},
    {"type": "VOLUME_BREAKOUT", "confidence": 0.72, "source": "market_tape"}
  ],
  "risk_params": {
    "max_loss_dollars": 3720,
    "reward_risk_ratio": 2.6,
    "portfolio_heat_after": 0.12
  },
  "graph_support": {
    "supporting_edges": 8,
    "contradicting_edges": 0,
    "thesis_id": "thesis-power-uranium-screen"
  },
  "status": "PENDING_APPROVAL",
  "cost": {
    "wall_time_s": 2.3,
    "cpu_time_s": 1.8,
    "timestamp_start": "2026-05-05T06:00:00",
    "timestamp_end": "2026-05-05T06:00:02"
  }
}
```

## Dependencies

```
Already installed: pandas, numpy, yfinance, sqlite3
New (Phase 1):    none
New (Phase 2):    pushover (pip install python-pushover2) OR telegram-bot
New (Phase 3):    alpaca-trade-api (pip install alpaca-trade-api)
```

## Safety Rules (Non-Negotiable)

1. **No autonomous execution.** Every trade requires explicit human approval.
2. **Paper first.** 30 days of paper trading before any live dollar.
3. **Hard stops.** Stops are placed immediately on fill, not "mental" stops.
4. **Risk params are constants, not variables.** AI cannot adjust its own risk limits.
5. **Daily drawdown halt.** If portfolio drops 5% in one day, agent stops proposing.
6. **Receipt everything.** No proposal without a receipt. No fill without a receipt.
7. **Thesis invalidation = immediate exit.** If the graph says the thesis is dead, get out.

## Relation to Existing Work Orders

| WO | Relevance |
|----|-----------|
| WO-K (COMPLETE) | Position sizer already wired in |
| WO-L (PARTIAL) | Backtest integrity — validate agent proposals against historical |
| WO-M (PARTIAL) | Trace chain — proposal receipts ARE the trace |
| WO-N (SPEC) | Market realism — slippage/impact modeled in proposals |

This agent naturally completes WO-L/M/N by producing live trace chains with real market data.

## File Structure

```
fgip-engine/
├── fgip/
│   ├── agents/
│   │   ├── trading_agent.py        ← NEW: orchestrator
│   │   ├── cascade_detector.py     ← NEW: timing stage tracker
│   │   ├── alert_dispatcher.py     ← NEW: phone notifications
│   │   ├── conviction_engine.py    (existing)
│   │   ├── market_tape.py          (existing)
│   │   ├── trade_plan_agent.py     (existing)
│   │   └── forecast_agent.py       (existing)
│   ├── execution/
│   │   ├── __init__.py             ← NEW
│   │   ├── paper_trader.py         ← NEW
│   │   └── alpaca_executor.py      ← NEW (Phase 3)
│   ├── backtest/
│   │   ├── portfolio_backtest.py   (existing)
│   │   ├── position_sizing.py      (existing)
│   │   └── risk_metrics.py         (existing)
│   └── data/
│       └── price_manager.py        (existing)
├── config/
│   └── watchlist.json              ← NEW: ticker tiers + risk params
└── docs/
    └── TRADING_AGENT_V0_SPEC.md    ← THIS FILE
```

## Start Command (Phase 1)

```bash
cd ~/fgip-engine

# Ingest latest prices
python3 -m fgip.data.price_manager fgip.db \
  --symbols DTM AR MPLX EQT WMB AG PAAS FCX CEG GEV DTE CMS SO VST OKLO \
  --start 2025-01-01 --verbose

# Run signal scan
python3 -m fgip.agents.trading_agent --scan --output proposals/

# Check existing positions
python3 -m fgip.agents.trading_agent --check-exits
```

## Decision: Build Phase 1 Now?

Phase 1 is:
- `trading_agent.py` (orchestrator, ~200 lines)
- `cascade_detector.py` (timing stage tracker, ~150 lines)
- `config/watchlist.json` (ticker config)
- Wire existing components together
- CLI that outputs proposals to JSON

No new dependencies. No API keys. No execution. Just the scanner that says "here's what I see" with receipts.
