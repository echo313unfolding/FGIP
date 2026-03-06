# FGIP Data

Raw data storage, artifacts, and caching.

## Directory Structure

```
data/
├── seed_nodes.json       # Initial node definitions
├── seed_edges.json       # Initial edge definitions
├── artifacts/            # Collected source artifacts
│   ├── congress/         # Congress.gov data
│   ├── edgar/            # SEC EDGAR filings
│   ├── fara/             # FARA registrations
│   ├── fec/              # FEC campaign finance
│   ├── federal_register/ # Federal Register rules
│   ├── gao/              # GAO reports
│   ├── rss/              # RSS article snapshots
│   ├── scotus/           # Supreme Court filings
│   ├── tic/              # Treasury TIC data
│   ├── usaspending/      # USAspending awards
│   └── youtube_takeout/  # YouTube watch history
├── bias_audits/          # Bias audit results
├── cache/                # Temporary cache files
└── reports/              # Generated analysis reports
```

## Seed Data

### seed_nodes.json

Initial node definitions loaded by `fgip.cli load-citations`:

```json
[
  {
    "node_id": "blackrock",
    "name": "BlackRock",
    "node_type": "FINANCIAL_INST",
    "description": "Largest asset manager globally"
  }
]
```

### seed_edges.json

Initial edge definitions:

```json
[
  {
    "from_node_id": "blackrock",
    "to_node_id": "intel",
    "edge_type": "OWNS_SHARES",
    "confidence": 0.95
  }
]
```

## Artifacts

### Collection Pattern

Agents collect artifacts with content hashing:

```python
artifact = Artifact(
    url="https://sec.gov/...",
    artifact_type="json",
    local_path="data/artifacts/edgar/filing_abc123.json",
    content_hash="sha256:...",
    fetched_at="2026-03-02T12:00:00Z"
)
```

### Artifact Types by Source

| Source | Directory | Format |
|--------|-----------|--------|
| SEC EDGAR | `edgar/` | JSON (API responses) |
| Congress.gov | `congress/` | JSON/XML |
| FARA | `fara/` | TXT (parsed PDFs) |
| FEC | `fec/` | JSON (OpenFEC API) |
| Federal Register | `federal_register/` | TXT/JSON |
| GAO | `gao/` | TXT (report summaries) |
| RSS | `rss/` | JSON (article snapshots) |
| SCOTUS | `scotus/` | JSON/XML |
| TIC | `tic/` | CSV/JSON |
| USAspending | `usaspending/` | TXT/JSON |
| YouTube | `youtube_takeout/` | HTML/CSV (Takeout) |

### YouTube Takeout

Google Takeout data for signal layer:

```
data/artifacts/youtube_takeout/Takeout/YouTube and YouTube Music/
├── history/
│   ├── watch-history.html    # Watch history
│   └── search-history.html   # Search history
├── subscriptions/
│   └── subscriptions.csv
└── playlists/
    └── *.csv
```

## Cache

Temporary files that can be safely deleted:

```bash
rm -rf data/cache/*
```

## Reports

Generated analysis reports:

```
data/reports/
├── convergence_report.json
├── gap_analysis.json
└── thesis_score.json
```

## Retention

| Directory | Retention | Notes |
|-----------|-----------|-------|
| `artifacts/` | Permanent | Provenance chain |
| `cache/` | Temporary | Delete anytime |
| `reports/` | Regenerable | Re-run analysis |
| `seed_*.json` | Version controlled | Core data |

## Adding New Data Sources

1. Create subdirectory in `data/artifacts/{source}/`
2. Implement agent in `fgip/agents/{source}.py`
3. Use content hashing for deduplication
4. Write artifacts with ISO8601 timestamps

## See Also

- `fgip/agents/` — Agent implementations
- `fgip/analysis/provenance_tracker.py` — Artifact provenance
- `receipts/` — Execution receipts (separate from data)
