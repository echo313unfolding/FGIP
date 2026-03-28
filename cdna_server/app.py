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

def _build_mistral_prompt(messages: List[Message]) -> str:
    """
    Build Mistral [INST] format prompt.

    Mistral instruct format:
    [INST] user message [/INST] assistant response </s>[INST] user message [/INST]

    Note: BOS token (<s>) is added by tokenizer.encode(add_bos=True), not here.
    """
    parts = []
    system_prefix = ""

    for msg in messages:
        if msg.role == "system":
            # Mistral has no system role - prepend to first user message
            system_prefix = msg.content.strip() + "\n\n"
        elif msg.role == "user":
            content = msg.content.strip()
            if system_prefix:
                content = system_prefix + content
                system_prefix = ""
            parts.append(f"[INST] {content} [/INST]")
        elif msg.role == "assistant":
            parts.append(f" {msg.content.strip()} </s>")

    # Don't add <s> here - tokenizer adds BOS automatically
    prompt = "".join(parts)
    return prompt


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

    # Build prompt with Mistral [INST] template
    prompt = _build_mistral_prompt(messages)

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


@app.post("/v1/prewarm")
async def prewarm() -> dict[str, Any]:
    """
    Prewarm the tensor cache by materializing all weight tensors.

    This eliminates the ~90s cold start penalty. After prewarm completes,
    the first real request will be fast (~6s instead of ~90s).

    Only available in real mode.
    """
    if CDNA_MODE != "real":
        raise HTTPException(
            status_code=400,
            detail="Prewarm endpoint only available in CDNA_MODE=real"
        )

    generator = _get_generator()
    if generator is None:
        raise HTTPException(status_code=500, detail="Generator not initialized")

    from .tensor_cache import prewarm_cache

    # Get manifest and base_path from generator (uses private attrs from model_loader)
    manifest = generator._manifest
    base_path = generator._base_path
    manifest_hash = generator.model_loader.manifest_hash

    result = prewarm_cache(manifest, base_path, manifest_hash)

    return {
        "status": "ok",
        "prewarm": result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/v1/debug/compare_logits")
async def compare_logits(request: dict) -> dict[str, Any]:
    """
    WO-CDNA-STAGE2-DEBUG: Compare Stage 1 vs Stage 2 logits for debugging.

    Stage 1 (cdna_forward_pass): Proven correct, uses streaming matmul directly
    Stage 2 (_forward_with_cache): Has bug, produces wrong logits

    This endpoint runs BOTH implementations on the same prompt and compares
    the output logits to help identify where the divergence occurs.

    Only available in real mode.
    """
    import numpy as np

    if CDNA_MODE != "real":
        raise HTTPException(
            status_code=400,
            detail="Debug endpoint only available in CDNA_MODE=real"
        )

    prompt = request.get("prompt", "Paris is the capital of")
    k = request.get("k", 5)

    # Stage 1: Proven forward pass
    from .cdna_forward import cdna_forward_pass
    generator = _get_generator()
    if generator is None:
        raise HTTPException(status_code=500, detail="Generator not initialized")

    logits1, receipt1 = cdna_forward_pass(
        prompt,
        model_loader=generator.model_loader,
        tokenizer=generator.tokenizer,
    )

    # Stage 2: KV-cached forward pass (potentially buggy)
    prompt_ids, _ = generator.tokenizer.encode(prompt, add_bos=True)
    logits2, _ = generator._forward_with_cache(prompt_ids, None)

    # Compare
    cosine_sim = float(np.dot(logits1, logits2) / (np.linalg.norm(logits1) * np.linalg.norm(logits2)))

    top_k_1 = np.argsort(logits1)[-k:][::-1]
    top_k_2 = np.argsort(logits2)[-k:][::-1]

    # Decode top tokens
    top_k_1_decoded = []
    top_k_2_decoded = []
    for i in range(k):
        text1, _ = generator.tokenizer.decode([int(top_k_1[i])])
        text2, _ = generator.tokenizer.decode([int(top_k_2[i])])
        top_k_1_decoded.append({"token_id": int(top_k_1[i]), "logit": float(logits1[top_k_1[i]]), "text": text1})
        top_k_2_decoded.append({"token_id": int(top_k_2[i]), "logit": float(logits2[top_k_2[i]]), "text": text2})

    return {
        "prompt": prompt,
        "prompt_tokens": len(prompt_ids),
        "stage1": {
            "top_k": top_k_1_decoded,
            "logits_stats": {
                "mean": float(logits1.mean()),
                "std": float(logits1.std()),
                "max": float(logits1.max()),
                "min": float(logits1.min()),
            },
        },
        "stage2": {
            "top_k": top_k_2_decoded,
            "logits_stats": {
                "mean": float(logits2.mean()),
                "std": float(logits2.std()),
                "max": float(logits2.max()),
                "min": float(logits2.min()),
            },
        },
        "comparison": {
            "cosine_similarity": cosine_sim,
            "top1_match": int(top_k_1[0]) == int(top_k_2[0]),
            "top5_match": bool(set(top_k_1[:5].tolist()) == set(top_k_2[:5].tolist())),
            "top1_tokens": {
                "stage1": top_k_1_decoded[0]["text"],
                "stage2": top_k_2_decoded[0]["text"],
            },
        },
        "verdict": "PASS" if int(top_k_1[0]) == int(top_k_2[0]) else "FAIL",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/v1/debug/layer_diff")
async def layer_diff(request: dict) -> dict[str, Any]:
    """
    WO-CDNA-STAGE2-DEBUG: Find first divergent layer between Stage 1 and Stage 2.

    Runs both implementations and captures per-layer snapshots to identify
    where the bug is introduced.

    Only available in real mode.
    """
    import numpy as np
    from helix_cdc.regrow.stream_transformer_block import (
        stream_multi_block_forward,
        rms_norm,
        load_norm_weights_from_gguf,
    )
    from .generate import N_LAYERS, D_HEAD, NORM_EPS, KVCache

    if CDNA_MODE != "real":
        raise HTTPException(
            status_code=400,
            detail="Debug endpoint only available in CDNA_MODE=real"
        )

    prompt = request.get("prompt", "Paris is the capital of")
    max_layers = request.get("max_layers", 4)  # Check first N layers to find divergence

    generator = _get_generator()
    if generator is None:
        raise HTTPException(status_code=500, detail="Generator not initialized")

    # Tokenize and embed (same for both)
    prompt_ids, _ = generator.tokenizer.encode(prompt, add_bos=True)
    embeddings, _ = generator.tokenizer.lookup_embeddings(prompt_ids)
    X = embeddings.reshape(1, len(prompt_ids), -1).astype(np.float32)

    # Run Stage 1 through first N layers
    stage1_hidden, _, _ = stream_multi_block_forward(
        X.copy(),
        manifest_path=generator.model_loader.manifest_path,
        block_indices=list(range(min(max_layers, N_LAYERS))),
        d_head=D_HEAD,
        verify_policy="trust_cached",
        gguf_path=generator.model_loader.gguf_path,
    )

    # Run Stage 2 through first N layers with snapshots
    stage2_snapshots = []
    kv_cache = KVCache()
    X_stage2 = X.copy()

    for block_idx in range(min(max_layers, N_LAYERS)):
        X_before = X_stage2.copy()
        X_stage2 = generator._forward_block_with_cache(X_stage2, block_idx, kv_cache, pos_offset=0)

        stage2_snapshots.append({
            "block": block_idx,
            "input_norm": float(np.linalg.norm(X_before)),
            "output_norm": float(np.linalg.norm(X_stage2)),
            "output_mean": float(X_stage2.mean()),
            "output_std": float(X_stage2.std()),
        })

    # Compare final hidden states
    def tensor_stats(arr):
        return {
            "shape": list(arr.shape),
            "mean": float(arr.mean()),
            "std": float(arr.std()),
            "max": float(arr.max()),
            "min": float(arr.min()),
            "norm": float(np.linalg.norm(arr)),
        }

    # Get last hidden state from each
    if stage1_hidden.ndim == 3:
        s1_last = stage1_hidden[0, -1, :]
    else:
        s1_last = stage1_hidden[-1, :]

    s2_last = X_stage2[0, -1, :]

    cosine = float(np.dot(s1_last, s2_last) / (np.linalg.norm(s1_last) * np.linalg.norm(s2_last)))
    max_abs_diff = float(np.abs(s1_last - s2_last).max())

    return {
        "prompt": prompt,
        "prompt_tokens": len(prompt_ids),
        "layers_compared": min(max_layers, N_LAYERS),
        "stage1_output": tensor_stats(s1_last),
        "stage2_output": tensor_stats(s2_last),
        "stage2_snapshots": stage2_snapshots,
        "comparison": {
            "cosine_similarity": cosine,
            "max_abs_diff": max_abs_diff,
            "match": cosine > 0.999 and max_abs_diff < 0.01,
        },
        "embedding_stats": tensor_stats(X[0, -1, :]),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/v1/debug/block0_diff")
async def block0_diff(request: dict) -> dict[str, Any]:
    """
    WO-CDNA-STAGE2-DEBUG: Deep dive into block 0 to find exact divergence point.

    Compares Stage 1 (proven) vs Stage 2 (buggy) at each operation within block 0:
    1. After input norm
    2. After Q/K/V projection
    3. After RoPE
    4. After attention
    5. After FFN

    Only available in real mode.
    """
    import numpy as np
    from helix_cdc.regrow.stream_transformer_block import (
        stream_transformer_block_forward,
        rms_norm,
        load_norm_weights_from_gguf,
    )
    from helix_cdc.regrow.stream_xw_matmul import stream_xw_from_manifest
    from .generate import (
        N_LAYERS, D_MODEL, D_HEAD, N_HEADS, N_KV_HEADS, NORM_EPS, ROPE_THETA,
        KVCache, apply_rope_single_head, silu, USE_TENSOR_CACHE,
    )
    from .tensor_cache import cached_matmul

    if CDNA_MODE != "real":
        raise HTTPException(
            status_code=400,
            detail="Debug endpoint only available in CDNA_MODE=real"
        )

    prompt = request.get("prompt", "Paris is the capital of")

    generator = _get_generator()
    if generator is None:
        raise HTTPException(status_code=500, detail="Generator not initialized")

    # Tokenize and embed (same for both)
    prompt_ids, _ = generator.tokenizer.encode(prompt, add_bos=True)
    embeddings, _ = generator.tokenizer.lookup_embeddings(prompt_ids)
    X = embeddings.reshape(1, len(prompt_ids), -1).astype(np.float32)

    def stats(name: str, arr: np.ndarray) -> dict:
        flat = arr.flatten()[:1000] if arr.size > 1000 else arr.flatten()
        return {
            "name": name,
            "shape": list(arr.shape),
            "mean": float(arr.mean()),
            "std": float(arr.std()),
            "max": float(arr.max()),
            "min": float(arr.min()),
            "norm": float(np.linalg.norm(flat)),
            "sample": [float(x) for x in flat[:5]],
        }

    # ==================== STAGE 1: Proven path ====================
    # Run through block 0 only using proven helix-cdc code
    stage1_output, _, _ = stream_transformer_block_forward(
        X.copy(),
        manifest_path=generator.model_loader.manifest_path,
        block_index=0,
        d_head=D_HEAD,
        verify_policy="trust_cached",
        gguf_path=generator.model_loader.gguf_path,
    )

    # ==================== STAGE 2: KV-cached path (with snapshots) ====================
    batch, seq, d_model = X.shape
    manifest = generator._manifest
    base_path = generator._base_path
    manifest_hash = generator.model_loader.manifest_hash
    block_idx = 0

    stage2_snapshots = []

    # Get norm weights
    attn_norm, ffn_norm = generator._get_norm_weights(block_idx)

    # Input
    stage2_snapshots.append(stats("input", X))

    # Attention norm
    X_norm = rms_norm(X, attn_norm, NORM_EPS)
    stage2_snapshots.append(stats("after_attn_norm", X_norm))

    # Project Q, K, V
    q_name = f"blk.{block_idx}.attn_q.weight"
    k_name = f"blk.{block_idx}.attn_k.weight"
    v_name = f"blk.{block_idx}.attn_v.weight"

    X_2d = X_norm.reshape(-1, d_model)

    if USE_TENSOR_CACHE:
        Q, _ = cached_matmul(X_2d, q_name, manifest, base_path, manifest_hash)
        K_new, _ = cached_matmul(X_2d, k_name, manifest, base_path, manifest_hash)
        V_new, _ = cached_matmul(X_2d, v_name, manifest, base_path, manifest_hash)
    else:
        Q, _ = stream_xw_from_manifest(X_2d, q_name, manifest, base_path, "trust_cached")
        K_new, _ = stream_xw_from_manifest(X_2d, k_name, manifest, base_path, "trust_cached")
        V_new, _ = stream_xw_from_manifest(X_2d, v_name, manifest, base_path, "trust_cached")

    stage2_snapshots.append(stats("Q_raw", Q))
    stage2_snapshots.append(stats("K_raw", K_new))

    # Reshape for attention
    Q = Q.reshape(batch, seq, N_HEADS, D_HEAD)
    K_new = K_new.reshape(batch, seq, N_KV_HEADS, D_HEAD)
    V_new = V_new.reshape(batch, seq, N_KV_HEADS, D_HEAD)

    # Apply RoPE to Q and K
    Q_before_rope = Q.copy()
    for h in range(N_HEADS):
        Q[0, :, h, :] = apply_rope_single_head(Q[0, :, h, :], pos_offset=0)
    for h in range(N_KV_HEADS):
        K_new[0, :, h, :] = apply_rope_single_head(K_new[0, :, h, :], pos_offset=0)

    stage2_snapshots.append(stats("Q_after_rope", Q))
    stage2_snapshots.append(stats("K_after_rope", K_new))

    # Transpose for attention: [batch, heads, seq, d_head]
    Q = Q.transpose(0, 2, 1, 3)
    K_new = K_new.transpose(0, 2, 1, 3)
    V_new = V_new.transpose(0, 2, 1, 3)

    # Create KV cache and update
    kv_cache = KVCache()
    kv_cache.update(block_idx, K_new, V_new)
    K_full, V_full = kv_cache.get_kv(block_idx)
    full_seq = K_full.shape[2]

    # GQA attention
    scale = 1.0 / np.sqrt(D_HEAD)
    group_size = N_HEADS // N_KV_HEADS
    context_heads = np.zeros((batch, N_HEADS, seq, D_HEAD), dtype=np.float32)

    # Sample attention scores from first head group
    hkv = 0
    h0 = 0
    h1 = group_size
    Qg = Q[:, h0:h1, :, :]
    Kg = K_full[:, hkv:hkv+1, :, :]
    scores_sample = np.einsum('bgsd,bkdt->bgst', Qg, Kg.transpose(0, 1, 3, 2)) * scale

    stage2_snapshots.append(stats("attn_scores_head0_raw", scores_sample))

    # Run full attention
    for hkv in range(N_KV_HEADS):
        h0 = hkv * group_size
        h1 = (hkv + 1) * group_size
        Qg = Q[:, h0:h1, :, :]
        Kg = K_full[:, hkv:hkv+1, :, :]
        Vg = V_full[:, hkv:hkv+1, :, :]
        scores = np.einsum('bgsd,bkdt->bgst', Qg, Kg.transpose(0, 1, 3, 2)) * scale

        if seq > 1:
            causal_mask = np.triu(np.ones((seq, full_seq), dtype=np.float32), k=1) * -1e9
        else:
            causal_mask = np.zeros((seq, full_seq), dtype=np.float32)
        scores = scores + causal_mask

        scores_max = scores.max(axis=-1, keepdims=True)
        exp_scores = np.exp(scores - scores_max)
        attn_weights = exp_scores / exp_scores.sum(axis=-1, keepdims=True)
        ctx = np.einsum('bgst,bktd->bgsd', attn_weights, Vg)
        context_heads[:, h0:h1, :, :] = ctx

    context = context_heads.transpose(0, 2, 1, 3).reshape(batch, seq, N_HEADS * D_HEAD)
    stage2_snapshots.append(stats("after_attention", context))

    # Output projection
    o_name = f"blk.{block_idx}.attn_output.weight"
    context_2d = context.reshape(-1, N_HEADS * D_HEAD)
    if USE_TENSOR_CACHE:
        attn_out, _ = cached_matmul(context_2d, o_name, manifest, base_path, manifest_hash)
    else:
        attn_out, _ = stream_xw_from_manifest(context_2d, o_name, manifest, base_path, "trust_cached")
    attn_out = attn_out.reshape(batch, seq, d_model)

    # Residual 1
    X_mid = X + attn_out
    stage2_snapshots.append(stats("after_residual1", X_mid))

    # FFN
    X_mid_norm = rms_norm(X_mid, ffn_norm, NORM_EPS)
    gate_name = f"blk.{block_idx}.ffn_gate.weight"
    up_name = f"blk.{block_idx}.ffn_up.weight"
    down_name = f"blk.{block_idx}.ffn_down.weight"

    X_mid_2d = X_mid_norm.reshape(-1, d_model)
    if USE_TENSOR_CACHE:
        gate, _ = cached_matmul(X_mid_2d, gate_name, manifest, base_path, manifest_hash)
        up, _ = cached_matmul(X_mid_2d, up_name, manifest, base_path, manifest_hash)
    else:
        gate, _ = stream_xw_from_manifest(X_mid_2d, gate_name, manifest, base_path, "trust_cached")
        up, _ = stream_xw_from_manifest(X_mid_2d, up_name, manifest, base_path, "trust_cached")

    hidden = silu(gate) * up

    if USE_TENSOR_CACHE:
        ffn_out, _ = cached_matmul(hidden, down_name, manifest, base_path, manifest_hash)
    else:
        ffn_out, _ = stream_xw_from_manifest(hidden, down_name, manifest, base_path, "trust_cached")
    ffn_out = ffn_out.reshape(batch, seq, d_model)

    # Residual 2
    output = X_mid + ffn_out
    stage2_snapshots.append(stats("output", output))

    # Compare Stage 1 vs Stage 2 outputs
    s1_last = stage1_output[0, -1, :] if stage1_output.ndim == 3 else stage1_output[-1, :]
    s2_last = output[0, -1, :]

    cosine = float(np.dot(s1_last, s2_last) / (np.linalg.norm(s1_last) * np.linalg.norm(s2_last)))
    max_diff = float(np.abs(s1_last - s2_last).max())

    return {
        "prompt": prompt,
        "prompt_tokens": len(prompt_ids),
        "stage1_output": stats("stage1_block0", s1_last),
        "stage2_output": stats("stage2_block0", s2_last),
        "stage2_snapshots": stage2_snapshots,
        "comparison": {
            "cosine_similarity": cosine,
            "max_abs_diff": max_diff,
            "match": cosine > 0.9999 and max_diff < 0.001,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/v1/cache_stats")
async def cache_stats() -> dict[str, Any]:
    """
    Return current tensor cache statistics without triggering inference.

    Useful for monitoring cache warmth and health.
    """
    if CDNA_MODE != "real":
        return {"status": "mock", "cache_enabled": False}

    from .tensor_cache import get_cache_stats

    stats = get_cache_stats()
    return {
        "status": "ok",
        "cache_stats": stats,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7778)
