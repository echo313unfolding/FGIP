# FGIP Architecture — Three-Layer Substrate

This document maps the FGIP codebase to a clean three-layer architecture.

---

## Layer Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                     LAYER C: Agent Runtime                          │
│  echo_gateway/    fgip/agents/    echo_hedge/    mcp_server.py     │
│  42 agents • tool routing • task execution • portfolio allocation   │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  │ queries / writes (controlled)
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     LAYER B: Graph / Memory                         │
│  fgip.db (SQLite)    data/artifacts/    receipts/    manifests/    │
│  1,801 nodes • 3,286 edges • 1,659 claims • 1,040 sources          │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  │ references (not raw tensors)
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     LAYER A: Model Substrate                        │
│  cdna_server/    GGUF files    sidecars    helix_cdc/              │
│  tensor shards • calibration artifacts • weight storage             │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Layer A — Model Substrate

**Location:** `cdna_server/`, external GGUF paths, helix-cdc system

**Contains:**
- GGUF model files (external, referenced by path)
- CDNA compressed shards
- Sidecars (parameter patches)
- Tensor metadata and calibration artifacts
- HelixCode indices for streaming decode

**Key Files:**
| File | Purpose |
|------|---------|
| `cdna_server/app.py` | FastAPI server for CDNA inference |
| `cdna_server/model_loader.py` | Load GGUF/CDNA artifacts |
| `cdna_server/tensor_cache.py` | Memory-mapped tensor streaming |
| `cdna_server/generate.py` | Token generation loop |
| `cdna_server/cdna_forward.py` | Forward pass from CDNA indices |

**Principle:** Raw weights never enter the graph. The graph holds **references** to weight artifacts.

---

## Layer B — Graph / Memory

**Location:** `fgip.db` (SQLite), `data/`, `receipts/`, `manifests/`

**Current Stats:**
| Table | Count |
|-------|-------|
| nodes | 1,801 |
| edges | 3,286 |
| claims | 1,659 |
| sources | 1,040 |
| proposed_edges | 7,684 pending |

### Schema — Core Tables

```sql
-- Entities
nodes (node_id, node_type, name, aliases, description, metadata, sha256)

-- Relationships
edges (edge_id, edge_type, from_node_id, to_node_id, claim_id,
       assertion_level, confidence, evidence_span, sha256)

-- Provenance
sources (source_id, url, domain, tier, artifact_path, artifact_hash)
claims (claim_id, claim_text, topic, status, required_tier)

-- Staging (controlled write path)
proposed_edges (proposal_id, from_node, to_node, relationship,
                agent_name, confidence, reasoning, status,
                evidence_span, se_score, artifact_id)

-- Audit
receipts (receipt_id, operation, timestamp, input_hash, output_hash)
```

### Node Types

| Type | Examples |
|------|----------|
| `FINANCIAL_INST` | BlackRock, Vanguard, State Street |
| `COMPANY` | Intel, TSMC, Micron |
| `LEGISLATION` | CHIPS Act, GENIUS Act |
| `AGENCY` | Treasury, FDIC, SEC |
| `POLICY` | Tariff rounds, QE programs |
| `ECONOMIC_METRIC` | M2, CPI, TIC flows |
| `PERSON` | CEOs, legislators |

### Edge Types

| Type | Meaning |
|------|---------|
| `OWNS_SHARES` | Equity ownership (from 13F) |
| `FUNDED_BY` | Grant/subsidy relationship |
| `REGULATES` | Agency → Entity |
| `REDUCES` | Correction mechanism |
| `INCREASES` | Causal effect |
| `LOBBIES` | Influence relationship |
| `SUPPLIES` | Supply chain link |

### Assertion Levels

| Level | Meaning | Requires |
|-------|---------|----------|
| `FACT` | Verified by Tier-0 source | Government doc |
| `INFERENCE` | Derived from facts | Triangulation |
| `HYPOTHESIS` | Proposed, needs validation | Agent proposal |

### Source Tiers

| Tier | Examples | Trust |
|------|----------|-------|
| 0 | SEC EDGAR, Congress.gov, FRED | Authoritative |
| 1 | Reuters, WSJ, academic | High |
| 2 | RSS signals, transcripts | Medium |
| 3 | Social, unverified | Low |

### Artifacts

```
data/artifacts/
├── congress/         # Bills, votes
├── edgar/            # 13F filings, 10-K
├── fara/             # Foreign agent registrations
├── fec/              # Campaign finance
├── federal_register/ # Rulemakings
├── gao/              # GAO reports
├── tic/              # Treasury TIC flows
└── usaspending/      # Federal contracts
```

Each artifact has:
- `artifact_path` — Local file
- `artifact_hash` — SHA256 content hash
- `retrieved_at` — Fetch timestamp

### Receipts (Audit Trail)

```
receipts/
├── audit_pack/      # Full snapshots
├── auto_approve/    # Approval decisions
├── echo_sessions/   # Chat logs
├── gapfill/         # Manifest applications
├── kat/             # Known Answer Tests
├── trade_memos/     # Trade decisions
└── watch/           # Agent runs
```

---

## Layer C — Agent Runtime

**Location:** `fgip/agents/`, `echo_gateway/`, `echo_hedge/`, `mcp_server.py`

### Agent Inventory (42 modules)

| Category | Agents |
|----------|--------|
| **Data Collection** | edgar, congress, fara, fec, gao, tic, usaspending, rss |
| **Extraction** | claim_extractor, entity_extractor, relation_extractor |
| **Analysis** | reasoning, both_sides, convergence, purchasing_power |
| **Scoring** | thesis_scorer, industrial_base_scorer, conviction |
| **Orchestration** | trade_plan_agent, gap_detector, watch_scheduler |

### Agent Lifecycle

```
Agent runs → proposes edges (HYPOTHESIS)
                    ↓
           proposed_edges table
                    ↓
         Human/auto approval gate
                    ↓
           edges table (FACT/INFERENCE)
```

### MCP Tools (exposed via `mcp_server.py`)

| Tool | Purpose |
|------|---------|
| `query_graph` | SQL queries on nodes/edges/claims |
| `search_nodes` | Full-text search |
| `explore_connections` | Node + edges at depth N |
| `get_thesis_score` | Thesis verification score |
| `get_convergence_report` | Promethean predictions vs reality |
| `get_both_sides` | Both-sides pattern detection |
| `propose_edge` | Stage new edge (controlled write) |

### Echo Gateway (Chat Interface)

```
echo_ui/index.html → echo_gateway/app.py → Local LLM (Ollama)
                                         → MCP tools (in-process)
```

**Endpoints:**
| Endpoint | Purpose |
|----------|---------|
| `/v1/chat` | Chat with tool calling |
| `/v1/task` | KAT-gated task execution |
| `/v1/health` | System status |

### Echo Hedge (Portfolio Allocation)

Deterministic allocation from graph evidence:
```python
score = 1.0 / (1.0 + anomaly_score)
score *= 1.15 if both_sides_motif else 1.0
score *= (1.0 + min(edges, 30) / 100)
```

Outputs to `receipts/echo_hedge/` with SHA256 determinism seal.

---

## Controlled Write Paths

The graph is NOT a "hallucination landfill." All writes go through gates:

### 1. Proposal Stage
```python
# Agent proposes edge
INSERT INTO proposed_edges (
    from_node, to_node, relationship,
    agent_name, confidence, reasoning,
    evidence_span, artifact_id,
    status='PENDING'
)
```

### 2. Approval Gate
```python
# Manual or auto-approval with rules
UPDATE proposed_edges SET status='APPROVED'
WHERE se_score > 0.7 AND source_tier <= 1

# Promotion to edges table
INSERT INTO edges SELECT ... FROM proposed_edges WHERE status='APPROVED'
```

### 3. Receipt Trail
```python
# Every mutation logged
INSERT INTO receipts (
    receipt_id, operation, timestamp,
    input_hash, output_hash, success
)
```

---

## Graph as Coordination Map (Not Weight Store)

The graph contains **references** to model artifacts, not raw tensors:

```sql
-- Example: Model artifact reference (conceptual)
INSERT INTO nodes (node_id, node_type, name, metadata) VALUES (
    'model-tinyllama-1.1b',
    'MODEL_ARTIFACT',
    'TinyLlama 1.1B',
    '{"gguf_path": "/models/tinyllama.gguf",
      "cdna_path": "/cdna/tinyllama/",
      "calibration_receipt": "cal_20260301.json"}'
);

-- Agent uses model
INSERT INTO edges (from_node_id, to_node_id, edge_type) VALUES (
    'agent-reasoning',
    'model-tinyllama-1.1b',
    'USES_MODEL'
);
```

---

## What the Graph DOES Contain

| Node Type | Examples |
|-----------|----------|
| `Entity` | BlackRock, Intel, CHIPS Act |
| `Document` | 13F filing, bill text |
| `Claim` | "BlackRock owns 7.2% of Intel" |
| `Source` | SEC EDGAR URL + hash |
| `Task` | "Run convergence analysis" |
| `Receipt` | Execution proof |
| `Agent` | Agent definition/status |
| `Model_Artifact` | Reference to GGUF/CDNA |

| Edge Type | Examples |
|-----------|----------|
| `OWNS_SHARES` | Institution → Company |
| `DOCUMENT_MENTIONS` | Filing → Entity |
| `CLAIM_SUPPORTED_BY` | Claim → Source |
| `RECEIPT_PROVES` | Receipt → Task |
| `AGENT_PROPOSED` | Agent → Edge |
| `MODEL_VALIDATED_BY` | Model → CalibrationRun |

---

## The Three Roles This Enables

### 1. Retrieval
LLM fetches relevant context:
```python
# Via MCP tool
result = query_graph("node_type='LEGISLATION' AND name LIKE '%CHIPS%'")
connections = explore_connections("chips-act", depth=2)
```

### 2. Routing
System chooses execution path:
```python
# Echo Gateway decides
if requires_graph_lookup(query):
    use_tool("query_graph")
elif requires_calculation(query):
    use_tool("purchasing_power")
else:
    direct_llm_response()
```

### 3. Provenance
Every output traceable:
```python
# Receipt chain
task → agent → proposed_edge → approval → edge → claim → sources → artifacts
```

---

## Summary

| Layer | Contains | Does NOT Contain |
|-------|----------|------------------|
| **A: Substrate** | GGUF, CDNA, tensors, sidecars | Graph nodes, agent state |
| **B: Graph** | Entities, edges, claims, sources, receipts, artifact refs | Raw weight arrays |
| **C: Runtime** | Agents, tools, routers, chat | Persistent state (uses B) |

The graph is the **coordination map**.
The weights are **building materials**.
The agents are **workers using the map**.

This separation keeps each layer clean and queryable.
