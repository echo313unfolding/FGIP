# Echo Gateway

FastAPI server providing chat UI with local LLM and MCP tool integration.

## Architecture

```
Echo UI (browser :7777) → Echo Gateway (FastAPI) → Local LLM (Ollama :11434)
                                                 ↘ MCP tools (in-process)
                                                 ↘ KAT gate (truth verification)
```

## Quick Start

```bash
# Start with Ollama
make echo-ui

# Or with explicit config
ECHO_LLM_BASE_URL=http://127.0.0.1:11434/v1 \
ECHO_MODEL=qwen2.5:latest \
make echo-ui
```

## Files

| File | Purpose |
|------|---------|
| `app.py` | FastAPI application, endpoints, lifespan management |
| `llm_client.py` | Async httpx client for OpenAI-compatible endpoints |
| `mcp_client.py` | MCP bridge for in-process tool calls |
| `tools.py` | Tool schemas and dispatcher |
| `task_router.py` | Routes tasks to Basin/Cell/Swarm backends |
| `kat_gate.py` | Truth enforcement for phenotype expression |
| `receipt.py` | Execution receipt generation |

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Serve chat UI |
| `/v1/health` | GET | Health check with warmup status |
| `/v1/chat` | POST | Direct chat (legacy) |
| `/v1/task` | POST | Unified task endpoint |
| `/v1/sessions` | GET | List recent sessions |

## Unified Task Endpoint

The `/v1/task` endpoint routes to appropriate backends:

```bash
curl -X POST http://localhost:7777/v1/task \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "chat",
    "payload": {"messages": [{"role": "user", "content": "Search for Intel"}]},
    "require_kat": false
  }'
```

### Task Types

| Type | Backend | Use Case |
|------|---------|----------|
| `chat` | Basin (LLM) | Conversational queries |
| `cell` | Single FGIPAgent | Focused evidence gathering |
| `swarm` | ThreadPoolExecutor | Parallel multi-agent collection |

### Response Format

```json
{
  "success": true,
  "result": { "content": "..." },
  "receipt": {
    "timestamp": "2026-03-02T12:00:00Z",
    "backend_used": "basin",
    "duration_ms": 1234,
    "inputs_hash": "sha256:...",
    "outputs_hash": "sha256:..."
  },
  "kat_gate": {
    "passed": true,
    "mode": "trust_cached",
    "skipped": false
  }
}
```

## KAT Gate

Truth enforcement for phenotype expression (ConvictionReports, forecasts).

### Modes

| Mode | Behavior |
|------|----------|
| `verify_always` | Run KAT before every phenotype expression |
| `verify_sampled` | Run KAT 10% of the time |
| `trust_cached` | Skip if last KAT < 15 minutes ago |

### Configuration

```bash
KAT_MODE=trust_cached make echo-ui
```

## MCP Tools Exposed

| Tool | Maps to MCP | Purpose |
|------|-------------|---------|
| `graph_query` | `query_graph` | SQL WHERE queries on nodes/edges |
| `graph_search_nodes` | `search_nodes` | Full-text search |
| `graph_get_node` | `explore_connections` | Node + connections |
| `graph_get_stats` | `get_graph_stats` | Graph statistics |

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `ECHO_LLM_BASE_URL` | `http://127.0.0.1:11434/v1` | LLM endpoint |
| `ECHO_MODEL` | `qwen2.5:3b` | Model name |
| `FGIP_DB_PATH` | `fgip.db` | Database path |
| `KAT_MODE` | `trust_cached` | KAT verification mode |
| `ECHO_LLM_BACKEND` | `ollama` | Backend type (ollama/cdna) |

## LLM Warmup

On startup, Echo Gateway warms up the LLM by sending a minimal completion request. This preloads the model into memory, eliminating cold-start latency.

```python
# Health check shows warmup status
{
  "status": "ok",
  "warmed": true,
  "warmup_time_ms": 2345.6
}
```

## Session Receipts

All chat sessions are logged to `receipts/echo_sessions/`:

```
receipts/echo_sessions/
└── session_{id}.jsonl
```

Each line is a JSON entry:

```json
{"timestamp": "...", "session_id": "abc123", "entry_type": "user_message", "content": "..."}
{"timestamp": "...", "session_id": "abc123", "entry_type": "tool_call", "content": {"name": "...", "args": {}}}
{"timestamp": "...", "session_id": "abc123", "entry_type": "tool_result", "content": {...}}
{"timestamp": "...", "session_id": "abc123", "entry_type": "assistant_message", "content": "..."}
```

## Smoke Test

```bash
make echo-ui-smoke

# Or manually
python3 tools/smoke_echo_ui.py
```

## See Also

- `echo_ui/` — Frontend chat interface
- `mcp_server.py` — Full MCP tool definitions
- `fgip/agents/` — Agent implementations for cell/swarm tasks
