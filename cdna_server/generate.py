"""
CDNA Generation - Autoregressive text generation with KV cache.

Stage 2 of WO-ECHO-CDNA-BACKEND-02.

Implements:
- Autoregressive generation loop (greedy first, sampling later)
- KV cache for O(N) scaling instead of O(N²)
- Deterministic mode with receipts

Pipeline:
    1. Tokenize prompt
    2. Forward pass (prefill) - cache K/V for all positions
    3. Sample next token (greedy: argmax)
    4. Forward pass (decode) - only new token, use cached K/V
    5. Repeat until max_tokens, stop token, or EOS
"""

import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

from helix_cdc.regrow.stream_xw_matmul import stream_xw_from_manifest, VerifyPolicy
from helix_cdc.regrow.stream_transformer_block import rms_norm, load_norm_weights_from_gguf

from .model_loader import CDNAModelLoader, DEFAULT_MANIFEST_PATH, DEFAULT_GGUF_PATH
from .tokenizer import CDNATokenizer
from .tensor_cache import cached_matmul, get_cache_stats, clear_cache
from .satellite import SatelliteCorrection


# Architecture constants - defaults for Mistral 7B (overridden at runtime from GGUF)
N_LAYERS = 32
D_MODEL = 4096
D_HEAD = 128
N_HEADS = 32
N_KV_HEADS = 8
NORM_EPS = 1e-5
ROPE_THETA = 1000000.0


def get_architecture_from_gguf(gguf_path: str) -> dict:
    """
    Read architecture parameters from GGUF metadata.

    WO-TINYLLAMA-SETUP-01: Supports any Llama-family model.
    """
    from gguf import GGUFReader

    reader = GGUFReader(gguf_path)
    arch = {}

    for field_name in reader.fields:
        field = reader.fields[field_name]
        if hasattr(field, 'parts') and len(field.parts) > 0:
            val = field.parts[-1]
            if hasattr(val, 'tolist'):
                val = val.tolist()

            # Map GGUF fields to our architecture params
            if field_name == "llama.block_count":
                arch["n_layers"] = int(val[0]) if isinstance(val, list) else int(val)
            elif field_name == "llama.embedding_length":
                arch["d_model"] = int(val[0]) if isinstance(val, list) else int(val)
            elif field_name == "llama.attention.head_count":
                arch["n_heads"] = int(val[0]) if isinstance(val, list) else int(val)
            elif field_name == "llama.attention.head_count_kv":
                arch["n_kv_heads"] = int(val[0]) if isinstance(val, list) else int(val)
            elif field_name == "llama.rope.freq_base":
                arch["rope_theta"] = float(val[0]) if isinstance(val, list) else float(val)
            elif field_name == "llama.attention.layer_norm_rms_epsilon":
                arch["norm_eps"] = float(val[0]) if isinstance(val, list) else float(val)

    # Compute d_head from d_model / n_heads
    if "d_model" in arch and "n_heads" in arch:
        arch["d_head"] = arch["d_model"] // arch["n_heads"]

    return arch

# Stage 3: Enable tensor caching (set to False to disable)
import os
USE_TENSOR_CACHE = os.environ.get("CDNA_USE_TENSOR_CACHE", "1") == "1"

# WO-CDNA-STAGE2-DEBUG: Safe forward mode toggle
# Stage 2 (CDNA_SAFE_FORWARD=0): Use cached_matmul + _forward_with_cache - CORRECT, matches HuggingFace
# Stage 1 (CDNA_SAFE_FORWARD=1): Use stream_xw_from_manifest - HAS BUG, produces wrong logits
# Default to Stage 2 (fast + correct)
CDNA_SAFE_FORWARD = os.environ.get("CDNA_SAFE_FORWARD", "0") == "1"


def _hash_text(text: str) -> str:
    """Compute SHA256[:16] hash of text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _hash_array(arr: np.ndarray) -> str:
    """Compute SHA256[:16] hash of numpy array."""
    return hashlib.sha256(arr.astype(np.float32).tobytes()).hexdigest()[:16]


@dataclass
class GenerationReceipt:
    """Receipt for generation request."""

    schema: str = "cdna_generation_receipt_v1"
    work_order: str = "WO-ECHO-CDNA-BACKEND-02"

    # Input
    prompt: str = ""
    prompt_hash: str = ""
    prompt_tokens: int = 0

    # Output
    generated_text: str = ""
    generated_text_hash: str = ""
    generated_tokens: int = 0
    token_ids: List[int] = field(default_factory=list)
    token_ids_hash: str = ""

    # Generation params
    max_tokens: int = 0
    temperature: float = 0.0
    top_p: float = 1.0
    seed: Optional[int] = None
    stop_reason: str = ""  # "max_tokens", "eos", "stop_string"

    # Performance
    ttft_ms: float = 0.0  # Time to first token
    total_ms: float = 0.0
    tokens_per_sec: float = 0.0
    prefill_ms: float = 0.0
    decode_ms: float = 0.0

    # Cache stats (Stage 3 performance engineering)
    tensor_cache_hits: int = 0
    tensor_cache_misses: int = 0
    tensor_cache_size_mb: float = 0.0

    # Model info
    manifest_hash: str = ""
    tokenizer_hash: str = ""

    # WO-SATELLITE-LAYER-01: Satellite correction info
    satellite_applied: bool = False
    satellite_type: str = ""
    satellite_hash: str = ""

    # Status
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    status: str = "PASS"
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "schema": self.schema,
            "work_order": self.work_order,
            "input": {
                "prompt": self.prompt,
                "prompt_hash": self.prompt_hash,
                "prompt_tokens": self.prompt_tokens,
            },
            "output": {
                "generated_text": self.generated_text,
                "generated_text_hash": self.generated_text_hash,
                "generated_tokens": self.generated_tokens,
                "token_ids_hash": self.token_ids_hash,
            },
            "params": {
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
                "top_p": self.top_p,
                "seed": self.seed,
                "stop_reason": self.stop_reason,
            },
            "performance": {
                "ttft_ms": round(self.ttft_ms, 2),
                "total_ms": round(self.total_ms, 2),
                "tokens_per_sec": round(self.tokens_per_sec, 3),
                "prefill_ms": round(self.prefill_ms, 2),
                "decode_ms": round(self.decode_ms, 2),
                "tensor_cache_hits": self.tensor_cache_hits,
                "tensor_cache_misses": self.tensor_cache_misses,
                "tensor_cache_size_mb": round(self.tensor_cache_size_mb, 2),
            },
            "model": {
                "manifest_hash": self.manifest_hash,
                "tokenizer_hash": self.tokenizer_hash,
            },
            "satellite": {
                "applied": self.satellite_applied,
                "type": self.satellite_type,
                "hash": self.satellite_hash,
            },
            "timestamp": self.timestamp,
            "status": self.status,
            "error_message": self.error_message,
        }


class KVCache:
    """
    KV cache for transformer attention.

    Stores K and V projections per layer to avoid recomputation.
    On each decode step, only the new token's K/V is computed and appended.
    """

    def __init__(self, n_layers: int = N_LAYERS, n_kv_heads: int = N_KV_HEADS, d_head: int = D_HEAD):
        """
        Initialize empty KV cache.

        Args:
            n_layers: Number of transformer layers
            n_kv_heads: Number of KV heads (for GQA)
            d_head: Head dimension
        """
        self.n_layers = n_layers
        self.n_kv_heads = n_kv_heads
        self.d_head = d_head

        # Cache storage: [layer][type] -> [batch, n_kv_heads, seq, d_head]
        self._k_cache: List[Optional[np.ndarray]] = [None] * n_layers
        self._v_cache: List[Optional[np.ndarray]] = [None] * n_layers

        self._seq_len = 0

    @property
    def seq_len(self) -> int:
        """Current sequence length in cache."""
        return self._seq_len

    def get_kv(self, layer: int) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Get cached K and V for a layer."""
        return self._k_cache[layer], self._v_cache[layer]

    def update(self, layer: int, k_new: np.ndarray, v_new: np.ndarray):
        """
        Append new K/V to cache for a layer.

        Args:
            layer: Layer index
            k_new: New K values [batch, n_kv_heads, new_seq, d_head]
            v_new: New V values [batch, n_kv_heads, new_seq, d_head]
        """
        if self._k_cache[layer] is None:
            self._k_cache[layer] = k_new
            self._v_cache[layer] = v_new
        else:
            self._k_cache[layer] = np.concatenate([self._k_cache[layer], k_new], axis=2)
            self._v_cache[layer] = np.concatenate([self._v_cache[layer], v_new], axis=2)

        # Update seq_len from first layer
        if layer == 0:
            self._seq_len = self._k_cache[0].shape[2]

    def clear(self):
        """Clear all cached values."""
        self._k_cache = [None] * self.n_layers
        self._v_cache = [None] * self.n_layers
        self._seq_len = 0


def apply_rope_single_head(x: np.ndarray, pos_offset: int = 0, theta: float = ROPE_THETA) -> np.ndarray:
    """
    Apply RoPE to a single head.

    Args:
        x: Input [seq, d_head]
        pos_offset: Position offset for incremental decoding
        theta: RoPE theta parameter

    Returns:
        Rotated tensor [seq, d_head]
    """
    seq_len, d_head = x.shape
    dim = d_head // 2

    freqs = 1.0 / (theta ** (np.arange(0, dim, dtype=np.float32) / dim))
    positions = np.arange(pos_offset, pos_offset + seq_len, dtype=np.float32)
    angles = np.outer(positions, freqs)
    freqs_cis = np.exp(1j * angles).astype(np.complex64)

    x_reshaped = x.reshape(seq_len, dim, 2)
    x_complex = x_reshaped[..., 0] + 1j * x_reshaped[..., 1]
    x_rotated = x_complex * freqs_cis
    x_out = np.stack([x_rotated.real, x_rotated.imag], axis=-1)
    return x_out.reshape(seq_len, d_head).astype(x.dtype)


def silu(x: np.ndarray) -> np.ndarray:
    """SiLU activation: x * sigmoid(x)"""
    return x * (1 / (1 + np.exp(-np.clip(x, -88, 88))))


class CDNAGenerator:
    """
    Autoregressive text generator using CDNA model.

    Supports:
    - KV caching for efficient generation
    - Greedy decoding (temp=0)
    - Temperature sampling (temp>0)
    - Top-p (nucleus) sampling
    """

    def __init__(
        self,
        model_loader: Optional[CDNAModelLoader] = None,
        tokenizer: Optional[CDNATokenizer] = None,
    ):
        """
        Initialize generator.

        Args:
            model_loader: CDNAModelLoader instance
            tokenizer: CDNATokenizer instance
        """
        self.model_loader = model_loader or CDNAModelLoader()
        self.tokenizer = tokenizer or CDNATokenizer()

        # WO-TINYLLAMA-SETUP-01: Load architecture from GGUF
        arch = get_architecture_from_gguf(str(self.model_loader.gguf_path))
        self.n_layers = arch.get("n_layers", N_LAYERS)
        self.d_model = arch.get("d_model", D_MODEL)
        self.d_head = arch.get("d_head", D_HEAD)
        self.n_heads = arch.get("n_heads", N_HEADS)
        self.n_kv_heads = arch.get("n_kv_heads", N_KV_HEADS)
        self.norm_eps = arch.get("norm_eps", NORM_EPS)
        self.rope_theta = arch.get("rope_theta", ROPE_THETA)

        print(f"[CDNAGenerator] Loaded architecture: layers={self.n_layers}, d_model={self.d_model}, "
              f"heads={self.n_heads}, kv_heads={self.n_kv_heads}, d_head={self.d_head}")

        # Load manifest for streaming
        self._manifest = self.model_loader._manifest
        self._manifest_path = Path(self.model_loader.manifest_path)
        # Base path for shard paths - manifest paths are relative to helix-cdc root
        # e.g. "seeds/cdna_v2_fullblocks/..." so base is helix-cdc, not helix-cdc/seeds
        self._base_path = self._manifest_path.parent.parent  # helix-cdc root

        # KV cache (architecture-aware)
        self._kv_cache: Optional[KVCache] = None

        # Preload norm weights (tiny, can keep in memory)
        self._norm_weights: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}

        # WO-SATELLITE-LAYER-01: Load satellite correction if present in manifest
        self._satellite: Optional[SatelliteCorrection] = None
        try:
            self._satellite = self.model_loader.load_satellite(verify=True)
            if self._satellite is not None:
                print(f"[CDNAGenerator] Loaded satellite correction: type={self._satellite.correction_type}, "
                      f"improvement={self._satellite.improvement_pct:.1f}%")
        except ValueError as e:
            print(f"[CDNAGenerator] Warning: Satellite verification failed: {e}")

    def _get_norm_weights(self, block_idx: int) -> Tuple[np.ndarray, np.ndarray]:
        """Get cached norm weights for a block."""
        key = f"blk.{block_idx}"
        if key not in self._norm_weights:
            self._norm_weights[key] = load_norm_weights_from_gguf(
                self.model_loader.gguf_path, block_idx
            )
        return self._norm_weights[key]

    def _forward_block_with_cache(
        self,
        X: np.ndarray,
        block_idx: int,
        kv_cache: KVCache,
        pos_offset: int = 0,
    ) -> np.ndarray:
        """
        Forward pass through one transformer block with KV caching.

        For prefill (pos_offset=0): processes full sequence, caches K/V
        For decode (pos_offset>0): processes only new token, uses cached K/V

        Args:
            X: Input activations [batch, seq, d_model]
            block_idx: Block index
            kv_cache: KV cache to use/update
            pos_offset: Position offset in sequence

        Returns:
            Output activations [batch, seq, d_model]
        """
        batch, seq, d_model = X.shape
        manifest = self._manifest
        base_path = self._base_path  # Path object for stream_xw_from_manifest

        # Get norm weights
        attn_norm, ffn_norm = self._get_norm_weights(block_idx)

        # Attention norm
        X_norm = rms_norm(X, attn_norm, self.norm_eps)

        # Project Q, K, V using streaming matmul
        q_name = f"blk.{block_idx}.attn_q.weight"
        k_name = f"blk.{block_idx}.attn_k.weight"
        v_name = f"blk.{block_idx}.attn_v.weight"
        o_name = f"blk.{block_idx}.attn_output.weight"

        X_2d = X_norm.reshape(-1, d_model)

        if USE_TENSOR_CACHE:
            # Stage 3: Use cached weights for faster decode
            # CDNA weights are [out, in] format, need transpose for matmul
            manifest_hash = self.model_loader.manifest_hash
            Q, _ = cached_matmul(X_2d, q_name, manifest, base_path, manifest_hash, transpose_w=True)
            K_new, _ = cached_matmul(X_2d, k_name, manifest, base_path, manifest_hash, transpose_w=True)
            V_new, _ = cached_matmul(X_2d, v_name, manifest, base_path, manifest_hash, transpose_w=True)
        else:
            # Original streaming path (for comparison/debugging)
            Q, _ = stream_xw_from_manifest(X_2d, q_name, manifest, base_path, "trust_cached")
            K_new, _ = stream_xw_from_manifest(X_2d, k_name, manifest, base_path, "trust_cached")
            V_new, _ = stream_xw_from_manifest(X_2d, v_name, manifest, base_path, "trust_cached")

        # Reshape for attention
        Q = Q.reshape(batch, seq, self.n_heads, self.d_head)
        K_new = K_new.reshape(batch, seq, self.n_kv_heads, self.d_head)
        V_new = V_new.reshape(batch, seq, self.n_kv_heads, self.d_head)

        # Apply RoPE to Q and K
        for h in range(self.n_heads):
            Q[0, :, h, :] = apply_rope_single_head(Q[0, :, h, :], pos_offset, self.rope_theta)
        for h in range(self.n_kv_heads):
            K_new[0, :, h, :] = apply_rope_single_head(K_new[0, :, h, :], pos_offset, self.rope_theta)

        # Transpose for attention: [batch, heads, seq, d_head]
        Q = Q.transpose(0, 2, 1, 3)
        K_new = K_new.transpose(0, 2, 1, 3)
        V_new = V_new.transpose(0, 2, 1, 3)

        # Update KV cache
        kv_cache.update(block_idx, K_new, V_new)

        # Get full K/V from cache
        K_full, V_full = kv_cache.get_kv(block_idx)
        full_seq = K_full.shape[2]

        # GQA attention
        scale = 1.0 / np.sqrt(self.d_head)
        group_size = self.n_heads // self.n_kv_heads
        context_heads = np.zeros((batch, self.n_heads, seq, self.d_head), dtype=np.float32)

        for hkv in range(self.n_kv_heads):
            h0 = hkv * group_size
            h1 = (hkv + 1) * group_size

            # Q for this group: [batch, group_size, seq, d_head]
            Qg = Q[:, h0:h1, :, :]
            # K/V from cache: [batch, 1, full_seq, d_head]
            Kg = K_full[:, hkv:hkv+1, :, :]
            Vg = V_full[:, hkv:hkv+1, :, :]

            # Attention scores: [batch, group_size, seq, full_seq]
            scores = np.einsum('bgsd,bkdt->bgst', Qg, Kg.transpose(0, 1, 3, 2)) * scale

            # Causal mask: can only attend to positions <= current position
            # For decode (seq=1), this just means attending to all cached positions
            # For prefill, need proper triangular mask
            if seq > 1:
                # Prefill: triangular mask
                causal_mask = np.triu(np.ones((seq, full_seq), dtype=np.float32), k=1) * -1e9
            else:
                # Decode: can attend to everything (all positions are in the past)
                causal_mask = np.zeros((seq, full_seq), dtype=np.float32)

            scores = scores + causal_mask

            # Softmax
            scores_max = scores.max(axis=-1, keepdims=True)
            exp_scores = np.exp(scores - scores_max)
            attn_weights = exp_scores / exp_scores.sum(axis=-1, keepdims=True)

            # Apply attention
            ctx = np.einsum('bgst,bktd->bgsd', attn_weights, Vg)
            context_heads[:, h0:h1, :, :] = ctx

        # Reshape context
        context = context_heads.transpose(0, 2, 1, 3).reshape(batch, seq, self.n_heads * self.d_head)

        # Output projection
        context_2d = context.reshape(-1, self.n_heads * self.d_head)
        if USE_TENSOR_CACHE:
            attn_out, _ = cached_matmul(context_2d, o_name, manifest, base_path, manifest_hash, transpose_w=True)
        else:
            attn_out, _ = stream_xw_from_manifest(context_2d, o_name, manifest, base_path, "trust_cached")
        attn_out = attn_out.reshape(batch, seq, d_model)

        # Residual connection 1
        X_mid = X + attn_out

        # FFN
        X_mid_norm = rms_norm(X_mid, ffn_norm, self.norm_eps)

        gate_name = f"blk.{block_idx}.ffn_gate.weight"
        up_name = f"blk.{block_idx}.ffn_up.weight"
        down_name = f"blk.{block_idx}.ffn_down.weight"

        X_mid_2d = X_mid_norm.reshape(-1, d_model)
        if USE_TENSOR_CACHE:
            gate, _ = cached_matmul(X_mid_2d, gate_name, manifest, base_path, manifest_hash, transpose_w=True)
            up, _ = cached_matmul(X_mid_2d, up_name, manifest, base_path, manifest_hash, transpose_w=True)
        else:
            gate, _ = stream_xw_from_manifest(X_mid_2d, gate_name, manifest, base_path, "trust_cached")
            up, _ = stream_xw_from_manifest(X_mid_2d, up_name, manifest, base_path, "trust_cached")

        # SiLU(gate) * up
        hidden = silu(gate) * up

        # Down projection
        if USE_TENSOR_CACHE:
            ffn_out, _ = cached_matmul(hidden, down_name, manifest, base_path, manifest_hash, transpose_w=True)
        else:
            ffn_out, _ = stream_xw_from_manifest(hidden, down_name, manifest, base_path, "trust_cached")
        ffn_out = ffn_out.reshape(batch, seq, d_model)

        # Residual connection 2
        output = X_mid + ffn_out

        return output

    def _forward_with_cache(
        self,
        token_ids: List[int],
        kv_cache: Optional[KVCache] = None,
    ) -> Tuple[np.ndarray, KVCache]:
        """
        Forward pass through all blocks with KV caching.

        Args:
            token_ids: Token IDs to process
            kv_cache: Existing KV cache (None for prefill)

        Returns:
            (logits [vocab_size], updated kv_cache)
        """
        # Initialize cache if needed (architecture-aware)
        if kv_cache is None:
            kv_cache = KVCache(n_layers=self.n_layers, n_kv_heads=self.n_kv_heads, d_head=self.d_head)
            pos_offset = 0
        else:
            pos_offset = kv_cache.seq_len

        # Get embeddings
        embeddings, _ = self.tokenizer.lookup_embeddings(token_ids)
        X = embeddings.reshape(1, len(token_ids), -1).astype(np.float32)

        # Run through all blocks
        for block_idx in range(self.n_layers):
            X = self._forward_block_with_cache(X, block_idx, kv_cache, pos_offset)

        # WO-SATELLITE-LAYER-01: Apply satellite correction if loaded
        # Satellite sees the whole model output and applies global correction
        if self._satellite is not None:
            X = self._satellite.apply(X)

        # Project to logits (last token only)
        last_hidden = X[0, -1, :]
        logits, _ = self.tokenizer.project_to_logits(last_hidden)

        return logits, kv_cache

    def generate(
        self,
        prompt: str,
        max_tokens: int = 32,
        temperature: float = 0.0,
        top_p: float = 1.0,
        stop_strings: Optional[List[str]] = None,
        seed: Optional[int] = None,
    ) -> Tuple[str, GenerationReceipt]:
        """
        Generate text autoregressively.

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0 = greedy)
            top_p: Nucleus sampling threshold
            stop_strings: Strings that stop generation
            seed: Random seed for reproducibility

        Returns:
            (generated_text, receipt)
        """
        t0_total = time.perf_counter()

        # WO-SATELLITE-LAYER-01: Capture satellite info for receipt
        satellite_applied = self._satellite is not None
        satellite_type = self._satellite.correction_type if self._satellite else ""
        satellite_hash = ""
        if self._satellite:
            sat_info = self.model_loader.get_satellite_info()
            if sat_info:
                satellite_hash = sat_info.get("sha256", "")[:16]

        receipt = GenerationReceipt(
            prompt=prompt,
            prompt_hash=_hash_text(prompt),
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            seed=seed,
            manifest_hash=self.model_loader.manifest_hash,
            tokenizer_hash=self.tokenizer.model_hash,
            satellite_applied=satellite_applied,
            satellite_type=satellite_type,
            satellite_hash=satellite_hash,
        )

        # Set random seed if provided
        if seed is not None:
            np.random.seed(seed)

        try:
            # Tokenize prompt
            prompt_ids, _ = self.tokenizer.encode(prompt, add_bos=True)
            receipt.prompt_tokens = len(prompt_ids)

            eos_id = self.tokenizer.get_eos_token_id()
            generated_ids: List[int] = []
            kv_cache: Optional[KVCache] = None

            # Prefill
            t0_prefill = time.perf_counter()
            if CDNA_SAFE_FORWARD:
                # WO-CDNA-STAGE2-DEBUG: Use proven Stage 1 forward (slow but correct)
                from .cdna_forward import cdna_forward_pass
                logits, forward_receipt = cdna_forward_pass(
                    prompt,
                    model_loader=self.model_loader,
                    tokenizer=self.tokenizer,
                )
                kv_cache = None  # Disable KV caching in safe mode
            else:
                # Stage 2: Use KV-cached forward (fast but has bug - for debugging)
                logits, kv_cache = self._forward_with_cache(prompt_ids, kv_cache)
            receipt.prefill_ms = (time.perf_counter() - t0_prefill) * 1000
            receipt.ttft_ms = receipt.prefill_ms

            # Generation loop
            t0_decode = time.perf_counter()
            stop_reason = "max_tokens"

            for _ in range(max_tokens):
                # Sample next token
                if temperature == 0.0:
                    # Greedy
                    next_id = int(np.argmax(logits))
                else:
                    # Temperature sampling
                    scaled_logits = logits / temperature

                    # Top-p filtering
                    if top_p < 1.0:
                        sorted_idx = np.argsort(scaled_logits)[::-1]
                        sorted_logits = scaled_logits[sorted_idx]
                        probs = np.exp(sorted_logits - sorted_logits.max())
                        probs = probs / probs.sum()
                        cumsum = np.cumsum(probs)
                        cutoff_idx = np.searchsorted(cumsum, top_p) + 1
                        valid_idx = sorted_idx[:cutoff_idx]
                        valid_probs = probs[:cutoff_idx]
                        valid_probs = valid_probs / valid_probs.sum()
                        next_id = int(np.random.choice(valid_idx, p=valid_probs))
                    else:
                        probs = np.exp(scaled_logits - scaled_logits.max())
                        probs = probs / probs.sum()
                        next_id = int(np.random.choice(len(probs), p=probs))

                generated_ids.append(next_id)

                # Check for EOS
                if next_id == eos_id:
                    stop_reason = "eos"
                    break

                # Check for stop strings
                if stop_strings:
                    current_text, _ = self.tokenizer.decode(generated_ids)
                    for stop_str in stop_strings:
                        if stop_str in current_text:
                            stop_reason = "stop_string"
                            break
                    if stop_reason == "stop_string":
                        break

                # Forward pass for next token
                if CDNA_SAFE_FORWARD:
                    # WO-CDNA-STAGE2-DEBUG: Use Stage 1 forward (no KV cache, slow)
                    full_text, _ = self.tokenizer.decode(list(prompt_ids) + generated_ids)
                    logits, _ = cdna_forward_pass(
                        full_text,
                        model_loader=self.model_loader,
                        tokenizer=self.tokenizer,
                    )
                else:
                    # Stage 2: Incremental decode with KV cache (fast)
                    logits, kv_cache = self._forward_with_cache([next_id], kv_cache)

            receipt.decode_ms = (time.perf_counter() - t0_decode) * 1000
            receipt.stop_reason = stop_reason

            # Decode generated tokens
            generated_text, _ = self.tokenizer.decode(generated_ids)
            receipt.generated_text = generated_text
            receipt.generated_text_hash = _hash_text(generated_text)
            receipt.generated_tokens = len(generated_ids)
            receipt.token_ids = generated_ids
            receipt.token_ids_hash = _hash_array(np.array(generated_ids, dtype=np.int64))

            receipt.total_ms = (time.perf_counter() - t0_total) * 1000
            if receipt.generated_tokens > 0:
                receipt.tokens_per_sec = receipt.generated_tokens / (receipt.total_ms / 1000)

            # Stage 3: Add cache stats
            if USE_TENSOR_CACHE:
                cache_stats = get_cache_stats()
                receipt.tensor_cache_hits = cache_stats["hits"]
                receipt.tensor_cache_misses = cache_stats["misses"]
                receipt.tensor_cache_size_mb = cache_stats["size_mb"]

            receipt.status = "PASS"
            return generated_text, receipt

        except Exception as e:
            receipt.total_ms = (time.perf_counter() - t0_total) * 1000
            receipt.status = "FAIL"
            receipt.error_message = str(e)
            return "", receipt


def generate(
    prompt: str,
    max_tokens: int = 32,
    temperature: float = 0.0,
    top_p: float = 1.0,
    stop_strings: Optional[List[str]] = None,
    seed: Optional[int] = None,
    model_loader: Optional[CDNAModelLoader] = None,
    tokenizer: Optional[CDNATokenizer] = None,
) -> Tuple[str, GenerationReceipt]:
    """
    Generate text using CDNA model.

    Convenience function that creates a CDNAGenerator internally.

    Args:
        prompt: Input prompt
        max_tokens: Maximum tokens to generate
        temperature: Sampling temperature (0 = greedy)
        top_p: Nucleus sampling threshold
        stop_strings: Strings that stop generation
        seed: Random seed for reproducibility
        model_loader: CDNAModelLoader instance
        tokenizer: CDNATokenizer instance

    Returns:
        (generated_text, receipt)
    """
    generator = CDNAGenerator(model_loader=model_loader, tokenizer=tokenizer)
    return generator.generate(
        prompt=prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        stop_strings=stop_strings,
        seed=seed,
    )


if __name__ == "__main__":
    import sys

    print("=== CDNA Generation Test ===")
    print()

    prompt = "Paris is the capital of"
    max_tokens = 8

    if len(sys.argv) > 1:
        prompt = sys.argv[1]
    if len(sys.argv) > 2:
        max_tokens = int(sys.argv[2])

    print(f"Prompt: '{prompt}'")
    print(f"Max tokens: {max_tokens}")
    print()

    try:
        text, receipt = generate(prompt, max_tokens=max_tokens, temperature=0.0)

        print(f"Status: {receipt.status}")
        print(f"Generated: '{text}'")
        print()
        print("Performance:")
        print(f"  TTFT: {receipt.ttft_ms:.1f}ms")
        print(f"  Prefill: {receipt.prefill_ms:.1f}ms")
        print(f"  Decode: {receipt.decode_ms:.1f}ms")
        print(f"  Total: {receipt.total_ms:.1f}ms")
        print(f"  Tokens/sec: {receipt.tokens_per_sec:.2f}")
        print()
        print(f"Stop reason: {receipt.stop_reason}")
        print(f"Token IDs: {receipt.token_ids}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
