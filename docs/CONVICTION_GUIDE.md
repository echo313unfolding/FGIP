# FGIP Conviction Engine - Would I Bet My Own Money?

## Core Principle

**Conviction = Independent Signals × Source Quality - Counter-Thesis Strength**

You need:
1. **TRIANGULATION**: 3+ independent signal TYPES (not just 3 signals from same source)
2. **TIER 0 ANCHOR**: At least 1 government/primary source signal
3. **ADVERSARIAL ATTACK**: Test strongest counter-thesis BEFORE any position
4. **CATALYST TIMING**: Entry signal (not just "this is good")
5. **EXIT PLAN**: Stop-loss and target defined upfront

---

## Conviction Levels & Position Sizing

| Level | Score | Position Size | Description |
|-------|-------|---------------|-------------|
| **CONVICTION_5** | 95%+ | 20% max | Multiple Tier 0, no valid counter-thesis |
| **CONVICTION_4** | 80-95% | 15% | Tier 0/1 confirmations, weak counter |
| **CONVICTION_3** | 60-80% | 10% | Mixed signals, manageable counter |
| **CONVICTION_2** | 40-60% | 5% | Speculative, limited confirmation |
| **CONVICTION_1** | <40% | 0% | Unproven, counter-thesis dominates |

---

## Data Sources That Increase Conviction

### TIER 0 - Maximum Boost (+15 points each)

These are PRIMARY sources. Government filings. Cannot be faked.

| Source | Agent | What It Shows | Schedule |
|--------|-------|---------------|----------|
| **SEC EDGAR 13F** | EDGARAgent | Institutional ownership | Daily 2AM |
| **SEC EDGAR Form 4** | EDGARAgent | Insider buys/sells | Daily 2AM |
| **USASpending Grants** | USASpendingAgent | DoE/DoD/CHIPS funding | Daily 2AM |
| **NRC Permits** | NuclearSMRAgent | Regulatory approvals | Daily 2AM |
| **Federal Register** | FederalRegisterAgent | Final rules (not proposed) | Daily 2AM |
| **FRED Economic Data** | SignalConvergence | Macro confirmation | On-demand |
| **Congress.gov** | CongressAgent | Legislation passed | Daily 2AM |

### TIER 1 - Moderate Boost (+8 points each)

Professional signals. Smart money positioning.

| Source | Agent | What It Shows | Status |
|--------|-------|---------------|--------|
| **Options Flow** | OptionsFlowAgent | Smart money positioning | **NEEDS API KEY** |
| **Credit Ratings** | -- | Fundamental improvement | **TO BUILD** |
| **Analyst Ratings** | -- | Professional validation | **TO BUILD** |
| **Industry Conferences** | RSSSignalAgent | Company execution | Daily |
| **Earnings Calls** | -- | Management commentary | **TO BUILD** |

### TIER 2 - Context Only (+3 points each)

Commentary. Does NOT increase conviction alone.

| Source | Agent | What It Shows | Schedule |
|--------|-------|---------------|----------|
| **YouTube/Podcasts** | YouTubeSignalAnalyzer | Narrative building | 6-hourly |
| **RSS News** | RSSSignalAgent | Market awareness | 6-hourly |
| **Social Sentiment** | -- | Retail awareness (contrarian) | **TO BUILD** |

---

## What's Missing (Priority Order)

### 1. Options Flow Data (HIGH PRIORITY)
The OptionsFlowAgent exists but Yahoo Finance now requires auth.

**Solutions:**
```bash
# Option A: TDAmeritrade API (free tier)
# Requires TD account, get API key at developer.tdameritrade.com

# Option B: Unusual Whales API ($30/mo for pro)
# https://unusualwhales.com/api

# Option C: CBOE official data (expensive, institutional)
```

**What to look for:**
- Call/Put ratio > 1.5 = bullish
- Volume > 2x average = unusual
- LEAPS (>180 days) = high conviction positioning
- Premium > $100K = institutional

### 2. Insider Transaction Alerts (HIGH PRIORITY)
Form 4 filings show when insiders buy with own money.

**Already have:** EDGARAgent collects Form 4
**Need:** Real-time alert when CEO/CFO buys

```python
# Add to EDGARAgent or create Form4AlertAgent
INSIDER_ALERT_THRESHOLD = 100_000  # $100K+ insider buy
```

### 3. Earnings Call Parser (MEDIUM PRIORITY)
Parse transcripts for thesis keywords.

**Data sources:**
- SEC EDGAR 8-K (free)
- Seeking Alpha transcripts (free tier)
- Company IR pages

**What to extract:**
- Mentions of "CHIPS Act", "DoE grant", "NRC permit"
- CapEx guidance changes
- Supply chain commentary

### 4. Social Sentiment (LOW PRIORITY - CONTRARIAN)
High retail awareness = contrarian signal.

**Data sources:**
- Reddit API (free)
- Twitter/X API (expensive now)
- StockTwits (free)

**Contrarian signal:** If WSB is excited about your thesis, you're late.

---

## Scheduler Integration

Your system already has scheduling via systemd timers:

```
TIER 0 (Daily 2AM)
├─ EDGAR, USASpending, GAO, FederalRegister
├─ TIC, SCOTUS, FARA, FEC, Congress
└─ NuclearSMRAgent

TIER 1 (Every 6 hours)
├─ RSS (00:00, 06:00, 12:00, 18:00)
├─ OpenSecrets
└─ OptionsFlowAgent (ADD THIS)

TIER 2 (Every 6 hours offset)
├─ Promethean (03:00, 09:00, 15:00, 21:00)
└─ YouTube

CONVICTION (On-demand or Daily)
└─ ConvictionEngine (evaluate all theses)
```

### Add ConvictionEngine to Schedule

```bash
# Add to tools/schedule_runner.py AGENT_TIERS
AGENT_TIERS = {
    "tier_0": [...],
    "tier_1": [..., "options_flow"],
    "tier_2": [...],
    "tier_3": ["gap_detector", "supply_chain_extractor", "causal"],
    "conviction": ["conviction_engine"],  # ADD THIS
}
```

---

## Swarm Integration

Your agentic cell system can run multiple thesis evaluations in parallel:

```python
# Swarm pattern: Evaluate all theses concurrently
from concurrent.futures import ThreadPoolExecutor
from fgip.agents import ConvictionEngine, INVESTMENT_THESES

def evaluate_thesis_swarm(db, max_workers=4):
    engine = ConvictionEngine(db)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(engine.evaluate_thesis, thesis["thesis_id"]): thesis
            for thesis in INVESTMENT_THESES
        }

        reports = []
        for future in futures:
            try:
                reports.append(future.result())
            except Exception as e:
                print(f"Error: {e}")

        return reports

# Filter to actionable
actionable = [r for r in reports if r.recommendation == "BUY"]
```

### Adversarial Swarm Pattern

Run attackers against each thesis:

```python
def adversarial_swarm(thesis_id: str, db):
    """
    1. Thesis Agent: Builds bull case
    2. Attacker Agent: Builds bear case
    3. Judge Agent: Weighs evidence
    """

    # Bull case (ConvictionEngine)
    bull = ConvictionEngine(db)
    bull_report = bull.evaluate_thesis(thesis_id)

    # Bear case (same engine, inverted)
    bear_signals = bull_report.refuting_signals
    bear_counters = bull_report.counter_theses

    # Judge (compare signal strength)
    bull_strength = sum(s.signal_strength for s in bull_report.confirming_signals)
    bear_strength = sum(s.signal_strength for s in bear_signals)

    winner = "BULL" if bull_strength > bear_strength * 1.5 else "BEAR"

    return {
        "thesis_id": thesis_id,
        "bull_strength": bull_strength,
        "bear_strength": bear_strength,
        "winner": winner,
        "margin": bull_strength / max(bear_strength, 0.01),
    }
```

---

## Usage Examples

### Quick Thesis Check

```bash
# List available theses
python3 -m fgip.agents.conviction_engine fgip.db --list

# Evaluate specific thesis
python3 -m fgip.agents.conviction_engine fgip.db --thesis nuclear-smr-thesis

# Evaluate all theses
python3 -m fgip.agents.conviction_engine fgip.db --all

# Show data sources info
python3 -m fgip.agents.conviction_engine fgip.db --sources
```

### Add Custom Thesis

```python
from fgip.db import FGIPDatabase
from fgip.agents import ConvictionEngine

db = FGIPDatabase("fgip.db")
engine = ConvictionEngine(db)

# Add custom thesis
engine.add_thesis({
    "thesis_id": "my-custom-thesis",
    "thesis_statement": "Company X will outperform because...",
    "tickers": ["TICK"],
    "sector": "my_sector",
    "entry_triggers": ["Catalyst A", "Catalyst B"],
    "exit_triggers": ["Risk A", "Risk B"],
    "counter_theses": ["What could go wrong 1", "What could go wrong 2"],
})

# Evaluate
report = engine.evaluate_thesis("my-custom-thesis")
print(f"Conviction: {report.conviction_level} ({report.conviction_score:.1f}%)")
print(f"Recommendation: {report.recommendation}")
```

### Check Options Flow

```bash
# Single ticker
python3 -m fgip.agents.options_flow fgip.db --ticker CCJ

# All conviction tickers (dry run)
python3 -m fgip.agents.options_flow fgip.db --dry-run

# Full agent run (writes to staging)
python3 -m fgip.agents.options_flow fgip.db
```

---

## What Would Make You CONVICTION_5?

For the nuclear thesis example:

**Current state:** CONVICTION_3 (78.8%)
- Triangulation NOT MET (only NRC permit signals)
- Missing: EDGAR 13F, USASpending, Options flow

**To reach CONVICTION_5:**

1. **Add EDGAR 13F signals** (Tier 0, +15 pts)
   - Run EDGARAgent for SMR, OKLO, CEG, BWXT, LEU
   - Look for Vanguard/BlackRock increasing positions

2. **Add USASpending signals** (Tier 0, +15 pts)
   - Check for DoE ARDP grants to X-Energy, TerraPower
   - Check for HALEU funding to Centrus

3. **Add Options flow signals** (Tier 1, +8 pts)
   - Check for unusual call buying in LEU, CCJ
   - Look for LEAPS positioning

4. **Triangulation met** (+10 pts bonus)
   - 3+ source types: NRC + EDGAR + USASpending

5. **Counter-thesis weakened**
   - Vogtle cost overruns don't apply to SMRs (different tech)
   - Natural gas prices rising (validating baseload demand)

**Target conviction:** 95%+ = 20% position size

---

## Continuous Monitoring

### Systemd Timer for Daily Conviction

```ini
# /etc/systemd/system/fgip-conviction.timer
[Unit]
Description=FGIP Conviction Engine Daily

[Timer]
OnCalendar=*-*-* 06:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

```ini
# /etc/systemd/system/fgip-conviction.service
[Unit]
Description=FGIP Conviction Engine

[Service]
Type=oneshot
User=voidstr3m33
WorkingDirectory=/home/voidstr3m33/fgip-engine
ExecStart=/usr/bin/python3 -m fgip.agents.conviction_engine fgip.db --all
```

### Alert on Conviction Change

```python
# Add to tools/scheduler.py

def conviction_alert(db):
    from fgip.agents import ConvictionEngine

    engine = ConvictionEngine(db)
    reports = engine.evaluate_all_theses()

    for report in reports:
        if report.recommendation == "BUY" and report.triangulation_met:
            send_alert(
                "CONVICTION_BUY",
                f"{report.thesis_id}: {report.conviction_level} ({report.conviction_score:.1f}%)"
            )
        elif report.recommendation == "EXIT":
            send_alert(
                "CONVICTION_EXIT",
                f"{report.thesis_id}: Counter-thesis triggered"
            )
```

---

## Summary: What You Need to Bet Your Own Money

1. **TRIANGULATION**: 3+ independent source TYPES
   - [x] NRC permits (Tier 0) - HAVE
   - [ ] EDGAR 13F (Tier 0) - RUN AGENT
   - [ ] USASpending (Tier 0) - RUN AGENT
   - [ ] Options flow (Tier 1) - NEED API KEY

2. **ADVERSARIAL TEST**: Test counter-thesis
   - [x] Counter-theses defined - HAVE
   - [x] Mitigation strategies - HAVE
   - [ ] Historical backtest - TO BUILD

3. **CATALYST TIMING**: Know when to enter
   - [x] Entry triggers defined - HAVE
   - [x] Exit triggers defined - HAVE
   - [ ] Real-time catalyst alerts - TO BUILD

4. **POSITION SIZING**: Based on conviction
   - [x] ConvictionEngine - HAVE
   - [x] Position size calculator - HAVE
   - [x] Stop-loss recommendations - HAVE

**Bottom line:** You have the framework. You need to:
1. Run all Tier 0 agents for your thesis tickers
2. Add options flow data source (TD or Unusual Whales API)
3. Set up daily conviction monitoring
4. Act only when triangulation_met = True

The system will tell you when you have enough evidence to bet your own money.
