# FGIP Pipeline

Data integrity checking and orchestration for the agent pipeline.

## Components

| File | Purpose |
|------|---------|
| `leak_detector.py` | Invariant checker - detects when data bypasses the pipeline |
| `orchestrator.py` | DEPRECATED - redirects to `fgip.agents.pipeline_orchestrator` |

## Leak Detector

The "pressure gauge" that catches when data flows around the filter.

```python
from fgip.pipeline.leak_detector import LeakDetector

detector = LeakDetector("fgip.db")
report = detector.check_invariants()

if report.total_leaks > 0:
    print(f"DEGRADED: {report.total_leaks} leaks detected")
```

### Leak Types Detected

| Leak | What It Catches |
|------|-----------------|
| **Leak 1** | Proposals with NULL `evidence_span` |
| **Leak 2** | Proposals with NULL `reason_codes` |
| **Leak 3** | Orphan proposals (artifact_id not in artifact_queue) |
| **Leak 4** | Bypass writes (proposals from non-pipeline sources) |
| **Leak 5** | FK violations (edges referencing missing nodes) |

### Allowed Bypass Agents

Some agents are allowed to create proposals without full pipeline:

- `reasoning-agent` — Graph inference
- `genius-edge-stager` — Manual staging
- `correction-loader` — Correction manifests
- `gapfill-loader` — Gap fill manifests
- `manual` — Manual imports

### Health Status

| Status | Condition |
|--------|-----------|
| GREEN | 0 leaks |
| DEGRADED | 1-100 leaks |
| CRITICAL | >100 leaks |

### CLI Usage

```bash
python3 tools/check_invariants.py
```

### LeakReport Fields

```python
@dataclass
class LeakReport:
    timestamp: str
    check_id: str
    leak_1_no_evidence: int
    leak_2_no_reason_codes: int
    leak_3_orphan_proposals: int
    leak_4_bypass_writes: int
    leak_5_fk_violations: int
    total_leaks: int
    total_proposals_checked: int
    health_status: str  # GREEN, DEGRADED, CRITICAL
```

## Orchestrator

**DEPRECATED:** The orchestrator has moved to `fgip.agents.pipeline_orchestrator`.

```python
# Old import (redirects automatically)
from fgip.pipeline.orchestrator import PipelineOrchestrator

# New canonical import
from fgip.agents.pipeline_orchestrator import PipelineOrchestrator
```

The orchestrator coordinates: `FilterAgent → NLPAgent → Proposals`
