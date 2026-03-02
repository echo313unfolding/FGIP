# FGIP Systemd Timers

Automated scheduling for FGIP agents.

## Installation

```bash
# Copy to user systemd directory
mkdir -p ~/.config/systemd/user
cp systemd/fgip-*.service ~/.config/systemd/user/
cp systemd/fgip-*.timer ~/.config/systemd/user/

# Reload systemd
systemctl --user daemon-reload

# Enable and start ALL timers
systemctl --user enable --now fgip-tier0.timer
systemctl --user enable --now fgip-tier1.timer
systemctl --user enable --now fgip-tier2.timer
systemctl --user enable --now fgip-tier3.timer
systemctl --user enable --now fgip-conviction.timer

# Check timer status
systemctl --user list-timers | grep fgip
```

## Cadence

| Timer | Cadence | Agents | Purpose |
|-------|---------|--------|---------|
| `fgip-tier0.timer` | Daily 2:00 AM | EDGAR, USASpending, GAO, FederalRegister, TIC, SCOTUS, FARA, FEC, Congress, CHIPS-Facility, NuclearSMR | Government primary sources |
| `fgip-tier1.timer` | Every 6 hours | RSS, OpenSecrets, OptionsFlow | Journalism & smart money |
| `fgip-tier2.timer` | Every 6 hours (offset) | Promethean, YouTube | Commentary |
| `fgip-tier3.timer` | Daily 4:00 AM | GapDetector, SupplyChainExtractor, Causal, SignalGapEcosystem | Meta-analysis |
| `fgip-conviction.timer` | Daily 6:00 AM | ConvictionEngine | **"Would I bet my own money?"** |

## Pipeline Flow

```
02:00 AM  →  Tier 0 agents collect government data (EDGAR, USASpending, etc.)
04:00 AM  →  Tier 3 agents analyze gaps and patterns
06:00 AM  →  Conviction Engine evaluates all theses
06:00/12:00/18:00/00:00  →  Tier 1 agents track news & options flow
03:00/09:00/15:00/21:00  →  Tier 2 agents track commentary
```

## Manual Runs

```bash
# Run a specific tier manually
systemctl --user start fgip-tier0.service
systemctl --user start fgip-conviction.service

# Or use the schedule runner directly
python3 tools/schedule_runner.py --tier 0   # Government data
python3 tools/schedule_runner.py --tier 1   # Journalism
python3 tools/schedule_runner.py --tier 2   # Commentary
python3 tools/schedule_runner.py --tier 3   # Meta-analysis
python3 tools/schedule_runner.py --tier 4   # Conviction

python3 tools/schedule_runner.py --agent edgar
python3 tools/schedule_runner.py --agent conviction-engine
python3 tools/schedule_runner.py --all

# List available agents
python3 tools/schedule_runner.py --list-agents
```

## Conviction Engine Direct Access

```bash
# Evaluate specific thesis
python3 -m fgip.agents.conviction_engine fgip.db --thesis uranium-thesis

# Evaluate all theses
python3 -m fgip.agents.conviction_engine fgip.db --all

# List available theses
python3 -m fgip.agents.conviction_engine fgip.db --list

# Show data sources info
python3 -m fgip.agents.conviction_engine fgip.db --sources
```

## Logs

Logs are written to:
- `receipts/schedule/tier0.log`
- `receipts/schedule/tier1.log`
- `receipts/schedule/tier2.log`
- `receipts/schedule/tier3.log`
- `receipts/schedule/conviction.log`

Receipts (JSON) are written to:
- `receipts/schedule/run_YYYYMMDDTHHMMSSZ.json`

## Viewing Logs

```bash
# Recent runs
journalctl --user -u fgip-tier0.service -n 50
journalctl --user -u fgip-conviction.service -n 50

# Follow logs
tail -f receipts/schedule/conviction.log
```

## Conviction Results

When the conviction engine runs, it outputs:
- **TRIANGULATION MET/NOT MET**: Do you have 3+ independent source types?
- **CONVICTION LEVEL 1-5**: How strong is the evidence?
- **RECOMMENDATION**: BUY / HOLD / AVOID / EXIT
- **POSITION SIZE**: 0% to 20% of portfolio

**Only act when:**
- `triangulation_met = True`
- `recommendation = BUY`
- No fatal counter-thesis
