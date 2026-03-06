# FGIP Tools

CLI utilities for maintenance, verification, and batch operations.

## Tool Index

### Proposal Management

| Tool | Purpose |
|------|---------|
| `review_proposals.py` | Interactive proposal review |
| `apply_proposals.py` | Apply approved proposals to graph |
| `promote_proposals.py` | Promote APPROVED → FACT/INFERENCE |
| `filter_proposals.py` | Filter proposals by criteria |
| `auto_approve.py` | Auto-approve high-confidence proposals |
| `quarantine_no_evidence.py` | Quarantine proposals lacking evidence |

### Data Loading

| Tool | Purpose |
|------|---------|
| `correction_loader.py` | Load correction manifests |
| `gapfill_loader.py` | Load gap-fill manifests |
| `port_signal_layer.py` | Port signal layer data |
| `stage_edge_updates.py` | Stage edge updates from manifests |

### Verification & Integrity

| Tool | Purpose |
|------|---------|
| `verify_easter_eggs.py` | Validate known facts (easter eggs) |
| `check_invariants.py` | Run leak detector invariant checks |
| `verify_index.py` | Verify INDEX.jsonl integrity |
| `run_kat.py` | Run KAT (Known Answer Test) suite |

### GENIUS Act

| Tool | Purpose |
|------|---------|
| `extract_genius_4a.py` | Extract Section 4(a) from bill text |
| `extract_section.py` | Extract arbitrary bill sections |
| `compare_genius_versions.py` | Diff GENIUS Act versions |

### Calibration & Backtesting

| Tool | Purpose |
|------|---------|
| `walk_forward_calibrate.py` | Walk-forward calibration |
| `paper_trade_score.py` | Score paper trading performance |
| `filter_tune_receipt.py` | Tune filter parameters |
| `filter_route_receipt.py` | Route filtering receipts |

### Maintenance

| Tool | Purpose |
|------|---------|
| `dedupe_edges.py` | Remove duplicate edges |
| `fill_coverage_gaps.py` | Fill coverage gaps in graph |
| `generate_brief.py` | Generate intelligence briefs |

### Scheduling

| Tool | Purpose |
|------|---------|
| `scheduler.py` | Task scheduling definitions |
| `schedule_runner.py` | Run scheduled agent tasks |

### Testing

| Tool | Purpose |
|------|---------|
| `smoke_echo_ui.py` | Smoke test Echo Gateway |

## Usage Examples

### Check Invariants

```bash
python3 tools/check_invariants.py
```

### Auto-Approve High-Confidence

```bash
python3 tools/auto_approve.py --min-confidence 0.9 --limit 100
```

### Verify Easter Eggs

```bash
python3 tools/verify_easter_eggs.py
```

### Deduplicate Edges

```bash
# Dry run
python3 tools/dedupe_edges.py --dry-run

# Apply
python3 tools/dedupe_edges.py
```

### Run KAT Suite

```bash
python3 tools/run_kat.py
```

### Load Correction Manifest

```bash
python3 tools/correction_loader.py manifests/correction_layer_v0.jsonl
```

## Receipts

Most tools write receipts to `receipts/` subdirectories:

```
receipts/
├── auto_approve/
├── calibration/
├── coverage/
├── filter_route/
├── filter_tune/
├── invariants/
├── kat/
└── trade_memos/
```

## Adding New Tools

1. Create `tools/my_tool.py`
2. Add docstring with usage instructions
3. Use argparse for CLI arguments
4. Write receipts to appropriate `receipts/` subdirectory
5. Add entry to this README

## See Also

- `receipts/` — Tool execution receipts
- `fgip/cli.py` — Main CLI interface
- `systemd/` — Scheduled task timers
