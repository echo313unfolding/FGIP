"""CDNA Server - OpenAI-compatible inference endpoint.

Stage 0: Stub server that proves wiring works.
Stage 1+: Real CDNA model loading and inference.

Usage:
    python3 -m uvicorn cdna_server.app:app --host 0.0.0.0 --port 7778
"""

import hashlib
import time
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


# Server configuration
CDNA_MODEL = "qwen2.5:3b-cdna-stub"  # Will be real model in Stage 1+
CDNA_VERSION = "0.1.0-stub"


app = FastAPI(title="CDNA Server", version=CDNA_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Track server state
_startup_time = time.time()
_request_count = 0


# ============ Request/Response Models ============

class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: List[Message]
    temperature: float = 0.0
    max_tokens: Optional[int] = None
    stream: bool = False


class ChatChoice(BaseModel):
    index: int
    message: Message
    finish_reason: str


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatChoice]
    usage: Usage
    system_fingerprint: str = "fp_cdna_stub"


# ============ Stub Inference ============

def stub_inference(messages: List[Message], temperature: float) -> str:
    """
    Stage 0: Deterministic stub response.

    Returns hash-based response so we can verify determinism.
    In Stage 1+, this becomes real CDNA decode.
    """
    # Hash the input for deterministic output
    input_str = "|".join(f"{m.role}:{m.content}" for m in messages)
    input_hash = hashlib.sha256(input_str.encode()).hexdigest()[:8]

    # Check for simple patterns
    last_content = messages[-1].content.lower() if messages else ""

    if "ping" in last_content:
        return f"pong [cdna-stub:{input_hash}]"
    elif "hello" in last_content or "hi" in last_content:
        return f"Hello from CDNA stub server. Input hash: {input_hash}"
    elif "what" in last_content and "model" in last_content:
        return f"I am {CDNA_MODEL}, a stub server proving CDNA wiring works. Real inference coming in Stage 1+."
    else:
        return f"[CDNA STUB] Received {len(messages)} messages. Input hash: {input_hash}. Temperature: {temperature}. This is deterministic stub output - real CDNA inference not yet wired."


def count_tokens(text: str) -> int:
    """Rough token count (will be accurate in Stage 1+)."""
    return len(text.split()) + len(text) // 4


# ============ Endpoints ============

@app.get("/v1/health")
async def health() -> dict[str, Any]:
    """Health check endpoint."""
    global _request_count
    return {
        "status": "ok",
        "model": CDNA_MODEL,
        "version": CDNA_VERSION,
        "stage": "stub",
        "uptime_seconds": round(time.time() - _startup_time, 2),
        "requests_served": _request_count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/v1/models")
async def list_models() -> dict[str, Any]:
    """List available models (OpenAI-compatible)."""
    return {
        "object": "list",
        "data": [
            {
                "id": CDNA_MODEL,
                "object": "model",
                "created": int(_startup_time),
                "owned_by": "cdna",
                "permission": [],
                "root": CDNA_MODEL,
                "parent": None,
            }
        ]
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest) -> ChatResponse:
    """
    OpenAI-compatible chat completions endpoint.

    Stage 0: Returns deterministic stub output.
    Stage 1+: Real CDNA inference.
    """
    global _request_count
    _request_count += 1

    start_time = time.time()

    # Run inference (stub for now)
    response_text = stub_inference(request.messages, request.temperature)

    # Calculate tokens
    prompt_tokens = sum(count_tokens(m.content) for m in request.messages)
    completion_tokens = count_tokens(response_text)

    # Build response
    return ChatResponse(
        id=f"chatcmpl-cdna-{uuid.uuid4().hex[:8]}",
        created=int(time.time()),
        model=request.model,
        choices=[
            ChatChoice(
                index=0,
                message=Message(role="assistant", content=response_text),
                finish_reason="stop",
            )
        ],
        usage=Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7778)
