# FGIP Scripts

One-time setup and data initialization scripts.

## Scripts

| Script | Purpose |
|--------|---------|
| `add_correction_nodes.py` | Add correction layer nodes (GENIUS Act, CHIPS, etc.) |
| `add_operational_intelligence.py` | Add operational intelligence nodes |
| `add_nuclear_nodes.py` | Add nuclear/SMR sector nodes |
| `add_commodity_nodes.py` | Add commodity nodes (uranium, rare earths, etc.) |
| `add_infrastructure_companies.py` | Add infrastructure company nodes |
| `init_calibration_tables.py` | Initialize calibration database tables |
| `cleanup_garbage_edges.py` | Remove invalid/garbage edges |
| `run_backtest.py` | Execute portfolio backtests |

## Usage

### Initialize Calibration Tables

```bash
python3 scripts/init_calibration_tables.py
```

### Add Nuclear Sector

```bash
python3 scripts/add_nuclear_nodes.py
```

### Add Commodities

```bash
python3 scripts/add_commodity_nodes.py
```

### Run Backtest

```bash
python3 scripts/run_backtest.py --start 2020-01-01 --end 2025-01-01
```

### Cleanup Garbage Edges

```bash
# Dry run first
python3 scripts/cleanup_garbage_edges.py --dry-run

# Apply
python3 scripts/cleanup_garbage_edges.py
```

## Bootstrap Sequence

For a fresh database:

```bash
# 1. Initialize database schema
python3 -m fgip.cli init

# 2. Load seed data
python3 -m fgip.cli load-citations

# 3. Add sector nodes
python3 scripts/add_correction_nodes.py
python3 scripts/add_nuclear_nodes.py
python3 scripts/add_commodity_nodes.py
python3 scripts/add_infrastructure_companies.py

# 4. Initialize calibration
python3 scripts/init_calibration_tables.py

# 5. Run agents to populate
python3 -m fgip.cli agent run edgar
python3 -m fgip.cli agent run usaspending
```

## Idempotency

Most scripts check for existing data before inserting:

```python
# Typical pattern
existing = db.execute("SELECT node_id FROM nodes WHERE node_id = ?", (node_id,)).fetchone()
if not existing:
    db.execute("INSERT INTO nodes ...")
```

## See Also

- `fgip/cli.py` — Main CLI interface
- `data/seed_nodes.json` — Initial seed data
- `data/seed_edges.json` — Initial seed edges
