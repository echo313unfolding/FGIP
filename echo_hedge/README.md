# Echo Hedge

FGIP-integrated portfolio allocation router.

## Core Principle

**Confidence scales sizing, NOT expected returns.**

Expected returns are labeled assumptions, not predictions. The allocator uses graph evidence to size positions.

## Components

| File | Purpose |
|------|---------|
| `fgip_allocator.py` | Deterministic position sizing from graph evidence |
| `mcp_client.py` | MCP bridge for in-process tool calls |

## Quick Start

```python
from echo_hedge import allocate_portfolio

result = allocate_portfolio(
    include_mining=False,
    base_expected_return=0.10,
    monthly_expenses=5000.0,
    current_savings=50000.0,
    max_single_position=0.20
)

for alloc in result["allocations"]:
    print(f"{alloc['name']}: {alloc['weight']:.1%}")
```

## Evidence Score

Position size is driven by evidence score, not expected return:

```python
score = 1.0 / (1.0 + anomaly_score)  # Lower anomaly = higher score
score *= 1.15 if both_sides_motif else 1.0  # Hedge potential bonus
score *= (1.0 + min(edges, 30) / 100)  # More edges = more validation
score *= (0.8 + avg_confidence * 0.4)  # Higher confidence = better
```

## Allocation Categories

| Category | Cap | Description |
|----------|-----|-------------|
| `reshoring` | 40% | CHIPS Act beneficiaries |
| `fixed_income` | 30% | T-Bills, Treasury |
| `commodity` | 20% | Gold, commodities |
| `crypto` | 5% | Digital assets |
| `mining` | 5% | Mining pools (optional) |

## Constraints

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `max_single_position` | 20% | No single position > 20% |
| `max_category_weight` | varies | Category caps |
| `min_weight_threshold` | 1% | Positions below 1% dropped |

## Output Format

```json
{
  "timestamp": "2026-03-02T12:00:00Z",
  "allocations": [
    {
      "candidate_id": "intel",
      "name": "Intel Corporation",
      "category": "reshoring",
      "weight": 0.15,
      "rationale": {
        "evidence_score": 0.82,
        "anomaly_score": 0.3,
        "both_sides_motif": true,
        "total_edges": 45
      }
    }
  ],
  "portfolio_metrics": {
    "total_weight": 1.0,
    "category_weights": {...}
  },
  "receipt": {
    "inputs_hash": "sha256:...",
    "allocations_hash": "sha256:...",
    "determinism_seal": true
  }
}
```

## Receipts

Allocations logged to `receipts/echo_hedge/`:

```
receipts/echo_hedge/allocation_20260302T120000Z.json
```

## MCP Integration

The allocator calls FGIP MCP tools:

- `get_allocation_candidates` — Get candidates with graph metadata
- `get_candidate_risk_context` — Get risk context per candidate

```python
from echo_hedge import mcp_call

candidates = mcp_call("get_allocation_candidates", {
    "include_mining": False,
    "base_expected_return": 0.10
})
```

## See Also

- `fgip/analysis/purchasing_power.py` — Personal exposure analysis
- `fgip/agents/trade_plan_agent.py` — Trade decision gates
- `echo_gateway/` — Chat interface for allocation queries
