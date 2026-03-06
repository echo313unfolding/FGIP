# FGIP Manifests

Proposed graph modifications in JSONL format.

## Purpose

Manifests define batches of edges/claims to be staged into the graph. They provide:
- Version control for graph updates
- Review before application
- Rollback capability

## Files

| File | Purpose |
|------|---------|
| `correction_layer_v0.jsonl` | GENIUS Act and correction layer edges |

## Format

Each line is a JSON object representing a proposed edge:

```json
{
  "from_node_id": "genius-act-2025",
  "to_node_id": "fed-treasury-purchases",
  "edge_type": "REDUCES",
  "confidence": 0.85,
  "assertion_level": "HYPOTHESIS",
  "evidence_span": "GENIUS Act replaces Fed Treasury absorption...",
  "source_url": "https://www.govinfo.gov/...",
  "agent_name": "genius-edge-stager"
}
```

## Loading Manifests

### Using CLI

```bash
python3 tools/correction_loader.py manifests/correction_layer_v0.jsonl
```

### Using Python

```python
from tools.correction_loader import load_manifest

loaded = load_manifest("manifests/correction_layer_v0.jsonl", "fgip.db")
print(f"Loaded {loaded} edges to staging")
```

## Manifest Lifecycle

1. **Create** — Generate manifest from analysis
2. **Review** — Human reviews proposed edges
3. **Stage** — Load into `proposed_edges` table
4. **Approve** — Promote to `edges` table
5. **Archive** — Move to `receipts/gapfill/`

## Creating New Manifests

```python
import json

manifest = [
    {
        "from_node_id": "node-a",
        "to_node_id": "node-b",
        "edge_type": "RELATED_TO",
        "confidence": 0.80,
        "assertion_level": "HYPOTHESIS",
        "agent_name": "my-stager"
    }
]

with open("manifests/my_manifest_v0.jsonl", "w") as f:
    for edge in manifest:
        f.write(json.dumps(edge) + "\n")
```

## Versioning

Use version suffixes for iterations:

```
correction_layer_v0.jsonl  # Initial
correction_layer_v1.jsonl  # After review
correction_layer_v2.jsonl  # After corrections
```

## Validation

Required fields for each edge:

| Field | Type | Required |
|-------|------|----------|
| `from_node_id` | string | Yes |
| `to_node_id` | string | Yes |
| `edge_type` | string | Yes |
| `confidence` | float | No (default 0.5) |
| `assertion_level` | string | No (default HYPOTHESIS) |
| `agent_name` | string | Yes |

## See Also

- `tools/correction_loader.py` — Manifest loader
- `tools/gapfill_loader.py` — Gap-fill manifest loader
- `fgip/proposals/` — Programmatic proposal generation
- `receipts/gapfill/` — Applied manifest receipts
