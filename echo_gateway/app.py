"""Echo Gateway - FastAPI application for Echo Chat UI.

Provides chat interface with local LLM and MCP tool integration.
One unified runtime: warm on startup, single /v1/task endpoint, KAT-gated truth.
"""

import json
import os
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from .llm_client import LLMClient
from .tools import dispatch_tool, get_tool_schemas
from .task_router import TaskRouter
from .kat_gate import KATMode
from .receipt import ReceiptWriter
from .agentic_loop import AgenticReasoningLoop

# Configuration from environment
LLM_BASE_URL = os.environ.get("ECHO_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
LLM_MODEL = os.environ.get("ECHO_MODEL", "qwen2.5:3b")
DB_PATH = os.environ.get("FGIP_DB_PATH", "fgip.db")
KAT_MODE = os.environ.get("KAT_MODE", "trust_cached")  # verify_always, verify_sampled, trust_cached

# Paths
FGIP_ROOT = Path(__file__).parent.parent
UI_PATH = FGIP_ROOT / "echo_ui" / "index.html"
SESSIONS_DIR = FGIP_ROOT / "receipts" / "echo_sessions"

# Add project root to path for imports
sys.path.insert(0, str(FGIP_ROOT))

# Ensure sessions directory exists
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

# System prompt for Echo
SYSTEM_PROMPT = """You are Echo, an assistant for the FGIP knowledge graph.

Available tools:
- graph_query: SQL queries on nodes/edges/claims/sources
- graph_search_nodes: Full-text search for entities
- graph_get_node: Node details + connections
- graph_get_stats: Graph statistics

Use tools to answer questions about the graph. Cite node IDs and edge types in your responses.
Be concise. If no results are found, suggest alternatives or broader queries.

The knowledge graph contains:
- Nodes: Organizations, people, legislation, companies, agencies, etc.
- Edges: Relationships like LOBBIED_FOR, OWNS, AWARDED_GRANT, INVESTED_IN, etc.
- Sources: Evidence backing the edges (Tier 0 = government, Tier 1 = official, Tier 2 = commentary)
"""

# Initialize LLM client (module-level for use in lifespan and endpoints)
llm_client = LLMClient(base_url=LLM_BASE_URL, model=LLM_MODEL)
receipt_writer = ReceiptWriter()

# Warmup status tracking
_warmup_result: dict[str, Any] = {"status": "not_started"}


def _get_kat_mode() -> KATMode:
    """Parse KAT mode from environment."""
    mode_map = {
        "verify_always": KATMode.VERIFY_ALWAYS,
        "verify_sampled": KATMode.VERIFY_SAMPLED,
        "trust_cached": KATMode.TRUST_CACHED,
    }
    return mode_map.get(KAT_MODE.lower(), KATMode.TRUST_CACHED)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan handler for startup/shutdown.

    Startup:
    - Warm up LLM (preload model into memory)
    - Initialize database connection
    - Create TaskRouter with KAT gate

    Shutdown:
    - Shutdown TaskRouter thread pool
    - Close LLM client
    """
    global _warmup_result

    # Startup: Warm up LLM
    print(f"Echo Gateway starting...")
    print(f"  LLM: {LLM_BASE_URL} ({LLM_MODEL})")
    print(f"  DB: {DB_PATH}")
    print(f"  KAT Mode: {KAT_MODE}")

    _warmup_result = await llm_client.warmup()
    print(f"  LLM Warmup: {_warmup_result.get('status')} ({_warmup_result.get('duration_ms', 0):.0f}ms)")

    # Initialize database
    try:
        from fgip.db import FGIPDatabase
        db = FGIPDatabase(DB_PATH)
        db.connect()
        print(f"  Database: connected")
    except Exception as e:
        print(f"  Database: error ({e})")
        db = None

    # Create TaskRouter
    if db:
        app.state.task_router = TaskRouter(
            db=db,
            llm_client=llm_client,
            kat_mode=_get_kat_mode(),
        )
        print(f"  TaskRouter: ready")
    else:
        app.state.task_router = None
        print(f"  TaskRouter: unavailable (no db)")

    app.state.db = db

    yield

    # Shutdown
    print("Echo Gateway shutting down...")
    if hasattr(app.state, "task_router") and app.state.task_router:
        app.state.task_router.shutdown()
    await llm_client.close()
    print("Echo Gateway stopped.")


# Initialize FastAPI app with lifespan
app = FastAPI(title="Echo Gateway", version="1.0.0", lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    """Chat request payload."""
    messages: list[dict[str, Any]]
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Chat response payload."""
    message: dict[str, Any]
    session_id: str
    tool_calls: Optional[list[dict[str, Any]]] = None


class TaskRequest(BaseModel):
    """Unified task request payload."""
    task_type: str  # 'chat', 'cell', 'swarm'
    payload: dict[str, Any]
    require_kat: bool = False  # Force KAT verification


class TaskResponse(BaseModel):
    """Unified task response payload."""
    success: bool
    result: Optional[Any] = None
    receipt: dict[str, Any]
    kat_gate: Optional[dict[str, Any]] = None
    errors: Optional[List[str]] = None


class AgenticRequest(BaseModel):
    """Agentic reasoning request payload."""
    task: str
    max_iterations: int = 10
    require_reflection: bool = True


class AgenticResponse(BaseModel):
    """Agentic reasoning response payload."""
    final_answer: Optional[str] = None
    confidence: float
    iterations: int
    status: str
    scratchpad: List[dict[str, Any]]
    tool_calls: List[dict[str, Any]]
    reflections: List[dict[str, Any]]
    receipt_id: str


def log_session_entry(session_id: str, entry_type: str, content: Any) -> None:
    """Log an entry to the session JSONL file."""
    session_file = SESSIONS_DIR / f"session_{session_id}.jsonl"

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "entry_type": entry_type,
        "content": content,
        "model": LLM_MODEL,
    }

    with open(session_file, "a") as f:
        f.write(json.dumps(entry) + "\n")


@app.get("/", response_class=HTMLResponse)
async def serve_ui() -> HTMLResponse:
    """Serve the Echo UI."""
    if not UI_PATH.exists():
        raise HTTPException(status_code=404, detail="UI not found")

    with open(UI_PATH, "r") as f:
        content = f.read()
    return HTMLResponse(content=content)


@app.get("/v1/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint with warmup status."""
    llm_health = await llm_client.health_check()

    # Check if database and router are available
    db_status = "connected" if hasattr(app.state, "db") and app.state.db else "unavailable"
    router_status = "ready" if hasattr(app.state, "task_router") and app.state.task_router else "unavailable"

    # Determine overall status
    if llm_client.is_warmed and db_status == "connected":
        status = "ok"
    elif llm_client.is_warmed:
        status = "degraded"
    else:
        status = "cold"

    return {
        "status": status,
        "warmed": llm_client.is_warmed,
        "warmup_time_ms": llm_client._warmup_time_ms,
        "llm_url": LLM_BASE_URL,
        "model": LLM_MODEL,
        "llm_status": llm_health,
        "db_status": db_status,
        "router_status": router_status,
        "kat_mode": KAT_MODE,
        "sessions_dir": str(SESSIONS_DIR),
    }


@app.post("/v1/chat")
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Main chat endpoint.

    Flow:
    1. Receive messages from client
    2. Inject system prompt with tool definitions
    3. Call LLM with tool_choice: auto
    4. If tool_calls returned: execute via MCP, append results, re-call LLM
    5. Log exchange to receipts/echo_sessions/
    6. Return response
    """
    # Generate or use existing session ID
    session_id = request.session_id or str(uuid.uuid4())[:8]

    # Build messages with system prompt
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(request.messages)

    # Log user message
    if request.messages:
        log_session_entry(
            session_id,
            "user_message",
            request.messages[-1].get("content", "")
        )

    # Get tool schemas
    tools = get_tool_schemas()

    # Track tool calls for response
    all_tool_calls = []

    # Call LLM (with tool calling loop)
    max_iterations = 5
    for _ in range(max_iterations):
        try:
            response = await llm_client.chat(
                messages=messages,
                tools=tools,
                temperature=0.0,
                tool_choice="auto",
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"LLM error: {str(e)}")

        # Extract assistant message
        choices = response.get("choices", [])
        if not choices:
            raise HTTPException(status_code=502, detail="No response from LLM")

        assistant_message = choices[0].get("message", {})
        tool_calls = assistant_message.get("tool_calls", [])

        if not tool_calls:
            # No tool calls - we have the final response
            break

        # Process tool calls
        messages.append(assistant_message)

        for tool_call in tool_calls:
            tool_id = tool_call.get("id", str(uuid.uuid4()))
            function = tool_call.get("function", {})
            tool_name = function.get("name", "")
            tool_args_str = function.get("arguments", "{}")

            # Parse arguments
            try:
                tool_args = json.loads(tool_args_str)
            except json.JSONDecodeError:
                tool_args = {}

            # Log tool call
            log_session_entry(session_id, "tool_call", {
                "name": tool_name,
                "args": tool_args,
            })

            # Execute tool
            result = await dispatch_tool(tool_name, tool_args)

            # Log tool result
            log_session_entry(session_id, "tool_result", result)

            # Track for response
            all_tool_calls.append({
                "name": tool_name,
                "args": tool_args,
                "result": result,
            })

            # Add tool result to messages
            messages.append({
                "role": "tool",
                "tool_call_id": tool_id,
                "content": json.dumps(result),
            })

    # Get final content
    final_content = assistant_message.get("content", "")

    # Log assistant message
    log_session_entry(session_id, "assistant_message", final_content)

    return ChatResponse(
        message={"role": "assistant", "content": final_content},
        session_id=session_id,
        tool_calls=all_tool_calls if all_tool_calls else None,
    )


@app.post("/v1/task")
async def execute_task(request: TaskRequest) -> TaskResponse:
    """
    Unified task endpoint.

    Routes tasks to appropriate backend:
    - chat: Basin (LLM) for conversational queries
    - cell: Single FGIPAgent for focused evidence gathering
    - swarm: Multiple agents via ThreadPoolExecutor

    If task involves phenotype expression (ConvictionReport, forecasts, etc.)
    and require_kat=True, KAT verification must pass before output is returned.

    Request:
        task_type: 'chat' | 'cell' | 'swarm'
        payload: Task-specific payload
        require_kat: Force KAT verification

    Response:
        success: bool
        result: Any
        receipt: {timestamp, backend_used, duration_ms, inputs_hash, outputs_hash}
        kat_gate: {passed, mode, skipped, ...} (if KAT ran)
        errors: List[str] (if any)
    """
    # Check if router is available
    if not hasattr(app.state, "task_router") or app.state.task_router is None:
        raise HTTPException(
            status_code=503,
            detail="TaskRouter not available. Database connection may have failed.",
        )

    # Route the task
    task_result = await app.state.task_router.route(
        task_type=request.task_type,
        payload=request.payload,
        require_kat=request.require_kat,
    )

    # Write receipt
    try:
        receipt_writer.write(task_result.receipt)
    except Exception as e:
        # Log but don't fail the request
        print(f"Warning: Failed to write receipt: {e}")

    return TaskResponse(
        success=task_result.success,
        result=task_result.result,
        receipt=task_result.receipt.to_dict(),
        kat_gate=task_result.kat_gate.to_dict() if task_result.kat_gate else None,
        errors=task_result.errors,
    )


@app.get("/v1/sessions")
async def list_sessions() -> dict[str, Any]:
    """List recent sessions."""
    sessions = []

    for session_file in sorted(SESSIONS_DIR.glob("session_*.jsonl"), reverse=True)[:20]:
        session_id = session_file.stem.replace("session_", "")

        # Read first and last lines for timestamps
        with open(session_file, "r") as f:
            lines = f.readlines()

        if lines:
            first_entry = json.loads(lines[0])
            last_entry = json.loads(lines[-1])

            sessions.append({
                "session_id": session_id,
                "started": first_entry.get("timestamp"),
                "last_activity": last_entry.get("timestamp"),
                "entries": len(lines),
            })

    return {
        "sessions": sessions,
        "count": len(sessions),
    }


@app.get("/v1/cache_stats")
async def cache_stats() -> dict[str, Any]:
    """
    Proxy cache stats from CDNA backend.

    Returns tensor cache statistics for monitoring warmth and health.
    """
    backend = os.environ.get("ECHO_LLM_BACKEND", "ollama")

    # Only CDNA backend has tensor cache
    if backend != "cdna":
        return {
            "status": "ok",
            "backend": backend,
            "cache_enabled": False,
            "message": "Tensor cache only available with CDNA backend",
        }

    try:
        # Extract base URL (remove /v1 suffix if present)
        base_url = LLM_BASE_URL.rstrip("/")
        if base_url.endswith("/v1"):
            base_url = base_url[:-3]

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base_url}/v1/cache_stats")
            if resp.status_code == 200:
                data = resp.json()
                data["backend"] = backend
                return data
            return {"status": "error", "code": resp.status_code, "backend": backend}
    except Exception as e:
        return {"status": "unavailable", "error": str(e), "backend": backend}


@app.post("/v1/agentic")
async def agentic_reasoning(request: AgenticRequest) -> AgenticResponse:
    """
    Agentic reasoning endpoint.

    Executes a multi-step reasoning loop with:
    - Chain-of-thought prompting
    - Tool calling (graph queries, calculations, causal chains)
    - Self-reflection and error correction
    - Iteration until solved or max iterations

    The ReAct pattern: Think → Act → Observe → Reflect → Repeat

    Request:
        task: The question/task to solve
        max_iterations: Maximum reasoning iterations (default: 10)
        require_reflection: Whether to require periodic self-reflection (default: True)

    Response:
        final_answer: The concluded answer (if reached)
        confidence: Confidence score (0.0 - 1.0)
        iterations: Number of iterations used
        status: 'complete', 'error', or 'max_iterations'
        scratchpad: Full reasoning trace
        tool_calls: All tool calls made
        reflections: All self-reflections
        receipt_id: Audit receipt ID
    """
    # Initialize reasoning loop
    loop = AgenticReasoningLoop(
        llm_client=llm_client,
        db_path=DB_PATH,
    )

    # Execute reasoning
    try:
        state = await loop.run(
            task=request.task,
            max_iterations=request.max_iterations,
            require_reflection=request.require_reflection,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reasoning error: {str(e)}")

    return AgenticResponse(
        final_answer=state.final_answer,
        confidence=state.confidence,
        iterations=state.iteration,
        status=state.status,
        scratchpad=[s.to_dict() for s in state.scratchpad],
        tool_calls=[t.to_dict() for t in state.tool_results],
        reflections=[r.to_dict() for r in state.reflections],
        receipt_id=state.receipt_id,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7777)
