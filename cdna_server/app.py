"""CDNA Server - OpenAI-compatible inference endpoint.

Stage 0: Stub server that proves wiring works.
Stage 2: Real CDNA inference with KV cache.

Usage:
    # Stub mode (default, fast, for testing wiring)
    python3 -m uvicorn cdna_server.app:app --host 0.0.0.0 --port 7778

    # Real inference mode
    CDNA_MODE=real python3 -m uvicorn cdna_server.app:app --host 0.0.0.0 --port 7778
"""

import hashlib
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


# Server configuration
CDNA_MODE = os.environ.get("CDNA_MODE", "stub")  # "stub" or "real"
CDNA_MODEL = "mistral-7b-cdna" if CDNA_MODE == "real" else "qwen2.5:3b-cdna-stub"
CDNA_VERSION = "0.2.0-stage2" if CDNA_MODE == "real" else "0.1.0-stub"

# Global generator (lazy loaded for real mode)
_generator = None
_generator_ready = False


def _get_generator():
    """Get or create the CDNA generator (lazy loading)."""
    global _generator, _generator_ready
    if _generator is None and CDNA_MODE == "real":
        from .generate import CDNAGenerator
        _generator = CDNAGenerator()
        _generator_ready = True
    return _generator


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    global _generator_ready

    if CDNA_MODE == "real":
        print(f"[CDNA] Mode: REAL inference")
        print(f"[CDNA] Loading model...")
        try:
            _get_generator()
            print(f"[CDNA] Model loaded, ready for inference")
        except Exception as e:
            print(f"[CDNA] WARNING: Failed to load model: {e}")
            print(f"[CDNA] Falling back to stub mode")
    else:
        print(f"[CDNA] Mode: STUB (set CDNA_MODE=real for inference)")

    yield

    # Cleanup
    global _generator
    _generator = None
    _generator_ready = False


app = FastAPI(title="CDNA Server", version=CDNA_VERSION, lifespan=lifespan)

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
    top_p: float = 1.0
    stream: bool = False
    seed: Optional[int] = None


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
    system_fingerprint: str = "fp_cdna"
    cdna_receipt: Optional[Dict[str, Any]] = None  # Stage 2: include receipt


# ============ Stub Inference ============

def stub_inference(messages: List[Message], temperature: float) -> str:
    """
    Stage 0: Deterministic stub response.

    Returns hash-based response so we can verify determinism.
    """
    input_str = "|".join(f"{m.role}:{m.content}" for m in messages)
    input_hash = hashlib.sha256(input_str.encode()).hexdigest()[:8]

    last_content = messages[-1].content.lower() if messages else ""

    if "ping" in last_content:
        return f"pong [cdna-stub:{input_hash}]"
    elif "hello" in last_content or "hi" in last_content:
        return f"Hello from CDNA stub server. Input hash: {input_hash}"
    elif "what" in last_content and "model" in last_content:
        return f"I am {CDNA_MODEL}, a stub server proving CDNA wiring works."
    else:
        return f"[CDNA STUB] Received {len(messages)} messages. Input hash: {input_hash}. Temperature: {temperature}."


def count_tokens_approx(text: str) -> int:
    """Rough token count (for stub mode)."""
    return len(text.split()) + len(text) // 4


# ============ Real Inference ============

def real_inference(
    messages: List[Message],
    temperature: float,
    max_tokens: int,
    top_p: float,
    seed: Optional[int],
) -> tuple[str, Dict[str, Any], int, int]:
    """
    Stage 2: Real CDNA inference with KV cache.

    Returns (response_text, receipt_dict, prompt_tokens, completion_tokens)
    """
    generator = _get_generator()
    if generator is None:
        raise HTTPException(status_code=500, detail="Generator not initialized")

    # Build prompt from messages
    # Simple format: concatenate all messages
    prompt_parts = []
    for msg in messages:
        if msg.role == "system":
            prompt_parts.append(f"System: {msg.content}")
        elif msg.role == "user":
            prompt_parts.append(f"User: {msg.content}")
        elif msg.role == "assistant":
            prompt_parts.append(f"Assistant: {msg.content}")

    prompt = "\n".join(prompt_parts)
    if messages[-1].role == "user":
        prompt += "\nAssistant:"

    # Generate
    response_text, receipt = generator.generate(
        prompt=prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        seed=seed,
    )

    if receipt.status != "PASS":
        raise HTTPException(
            status_code=500,
            detail=f"Generation failed: {receipt.error_message}"
        )

    return (
        response_text,
        receipt.to_dict(),
        receipt.prompt_tokens,
        receipt.generated_tokens,
    )


# ============ Endpoints ============

@app.get("/v1/health")
async def health() -> dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "ok",
        "model": CDNA_MODEL,
        "version": CDNA_VERSION,
        "mode": CDNA_MODE,
        "generator_ready": _generator_ready if CDNA_MODE == "real" else None,
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

    Stage 0 (CDNA_MODE=stub): Returns deterministic stub output.
    Stage 2 (CDNA_MODE=real): Real CDNA inference with KV cache.
    """
    global _request_count
    _request_count += 1

    max_tokens = request.max_tokens or 64

    if CDNA_MODE == "real" and _generator_ready:
        # Real inference
        response_text, receipt, prompt_tokens, completion_tokens = real_inference(
            messages=request.messages,
            temperature=request.temperature,
            max_tokens=max_tokens,
            top_p=request.top_p,
            seed=request.seed,
        )
        finish_reason = receipt.get("params", {}).get("stop_reason", "stop")
        if finish_reason == "max_tokens":
            finish_reason = "length"
        elif finish_reason in ("eos", "stop_string"):
            finish_reason = "stop"

        return ChatResponse(
            id=f"chatcmpl-cdna-{uuid.uuid4().hex[:8]}",
            created=int(time.time()),
            model=CDNA_MODEL,
            choices=[
                ChatChoice(
                    index=0,
                    message=Message(role="assistant", content=response_text),
                    finish_reason=finish_reason,
                )
            ],
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
            system_fingerprint=f"fp_cdna_{receipt.get('model', {}).get('manifest_hash', 'unknown')[:8]}",
            cdna_receipt=receipt,
        )
    else:
        # Stub inference
        response_text = stub_inference(request.messages, request.temperature)
        prompt_tokens = sum(count_tokens_approx(m.content) for m in request.messages)
        completion_tokens = count_tokens_approx(response_text)

        return ChatResponse(
            id=f"chatcmpl-cdna-{uuid.uuid4().hex[:8]}",
            created=int(time.time()),
            model=CDNA_MODEL,
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
            system_fingerprint="fp_cdna_stub",
        )


@app.post("/v1/debug/forward_topk")
async def debug_forward_topk(prompt: str, k: int = 5) -> dict[str, Any]:
    """
    Debug endpoint: run forward pass and return top-k tokens.

    Only available in real mode.
    """
    if CDNA_MODE != "real":
        raise HTTPException(
            status_code=400,
            detail="Debug endpoint only available in CDNA_MODE=real"
        )

    from .cdna_forward import cdna_forward_topk

    topk, receipt = cdna_forward_topk(prompt, k=k)

    return {
        "prompt": prompt,
        "top_k": [
            {"token_id": t[0], "logit": t[1], "text": t[2]}
            for t in topk
        ],
        "receipt": receipt.to_dict(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7778)
