"""
Process-global LRU cache for materialized weight tensors.

Stage 3 of WO-ECHO-CDNA-BACKEND-02.

Key insight: Each decode step needs the same 224 weight matrices (7 per block × 32 blocks).
First token pays full decompression cost, subsequent tokens hit cache.

The cache stores fully materialized float32 weight tensors. When a tensor is requested:
1. Check cache - if hit, do simple numpy matmul (fast)
2. If miss, call stream_xw_from_manifest to decompress and compute (slow)
3. Cache the result of Y = I @ W to get W for future use

Memory budget: ~224 tensors × ~64MB avg = ~14GB at full capacity.
This is acceptable since we're trading memory for speed.
"""

from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from collections import OrderedDict
import threading
import os
import numpy as np

from helix_cdc.regrow.cdna_stream_v2 import load_cdna_auto

# Stage 4: Cache size limit (default 28GB, configurable via env)
# Full model needs ~26GB; 28GB provides headroom
# On 64GB system, this leaves ~36GB for KV cache, page cache, and system
CACHE_MAX_MB = int(os.environ.get("CDNA_TENSOR_CACHE_MAX_MB", "28000"))
CACHE_MAX_BYTES = CACHE_MAX_MB * 1024 * 1024

# Process-global weight cache (LRU via OrderedDict)
# Key: "{manifest_hash}:{tensor_name}"
# Value: np.ndarray (float32 weight tensor)
_weight_cache: OrderedDict[str, np.ndarray] = OrderedDict()
_cache_lock = threading.Lock()

# Stats for receipts
_cache_stats = {
    "hits": 0,
    "misses": 0,
    "evictions": 0,
    "size_bytes": 0,
    "max_bytes": CACHE_MAX_BYTES,
}
_stats_lock = threading.Lock()


def get_cache_stats() -> Dict[str, Any]:
    """Return current cache statistics."""
    with _stats_lock:
        return {
            "hits": _cache_stats["hits"],
            "misses": _cache_stats["misses"],
            "evictions": _cache_stats["evictions"],
            "size_mb": _cache_stats["size_bytes"] / (1024 * 1024),
            "max_mb": _cache_stats["max_bytes"] / (1024 * 1024),
            "utilization_pct": round(100 * _cache_stats["size_bytes"] / _cache_stats["max_bytes"], 1) if _cache_stats["max_bytes"] > 0 else 0,
            "cached_tensors": len(_weight_cache),
        }


def clear_cache():
    """Clear the tensor cache (for testing)."""
    global _weight_cache
    with _cache_lock:
        _weight_cache = OrderedDict()
    with _stats_lock:
        _cache_stats["hits"] = 0
        _cache_stats["misses"] = 0
        _cache_stats["evictions"] = 0
        _cache_stats["size_bytes"] = 0


def _evict_until_under_budget(new_tensor_bytes: int):
    """
    Evict oldest cache entries (LRU) until there's room for new_tensor_bytes.
    Must be called with _cache_lock held.
    """
    target_bytes = CACHE_MAX_BYTES - new_tensor_bytes

    while _cache_stats["size_bytes"] > target_bytes and _weight_cache:
        # Pop oldest entry (FIFO order in OrderedDict)
        oldest_key, oldest_tensor = _weight_cache.popitem(last=False)
        evicted_bytes = oldest_tensor.nbytes
        with _stats_lock:
            _cache_stats["size_bytes"] -= evicted_bytes
            _cache_stats["evictions"] += 1


def _materialize_weight_from_cdna(
    tensor_name: str,
    manifest: Dict[str, Any],
    base_path: Path,
) -> np.ndarray:
    """
    Materialize a full weight tensor from CDNA format.

    Uses CDNAv2Reader.stream_rows_dequant to get all rows with
    dequantization and sidecar corrections applied.

    Args:
        tensor_name: Name of tensor (e.g., "blk.0.attn_q.weight")
        manifest: Parsed manifest dict
        base_path: Base path for resolving relative paths

    Returns:
        Weight tensor as np.ndarray [rows, cols] in float32
    """
    # Find tensor in manifest
    tensor_info = None
    for shard in manifest.get("shards", []):
        if shard.get("tensor_name") == tensor_name:
            tensor_info = shard
            break

    if tensor_info is None:
        raise KeyError(f"Tensor '{tensor_name}' not found in manifest")

    # Resolve paths
    cdna_path = base_path / tensor_info["path"]

    sidecar_path = None
    if tensor_info.get("outlier_sidecar_path"):
        # outlier_sidecar_path already includes the full relative path
        sidecar_path = base_path / tensor_info["outlier_sidecar_path"]

    # Load CDNA reader
    reader = load_cdna_auto(cdna_path)

    # Get all rows with dequantization (applies codebook + sidecar)
    W, _ = reader.stream_rows_dequant(
        start_row=0,
        end_row=reader.rows,
        sidecar_path=sidecar_path,
        decode_mode="accurate",
        emit_receipt=False,
    )

    return W


def cached_matmul(
    X: np.ndarray,
    tensor_name: str,
    manifest: Dict[str, Any],
    base_path: Path,
    manifest_hash: str,
    transpose_w: bool = False,
) -> Tuple[np.ndarray, bool]:
    """
    Compute Y = X @ W (or X @ W.T) using cached weight if available.

    Args:
        X: Input activations [batch, seq, K] or [seq, K] or [K]
        tensor_name: Name of weight tensor in manifest
        manifest: Parsed manifest dict
        base_path: Base path for resolving paths
        manifest_hash: Hash for cache key (invalidates on manifest change)
        transpose_w: If True, compute X @ W.T

    Returns:
        (Y, cache_hit) - output and whether cache was hit
    """
    cache_key = f"{manifest_hash}:{tensor_name}"

    # Check cache
    with _cache_lock:
        if cache_key in _weight_cache:
            W = _weight_cache[cache_key]
            # Move to end (mark as recently used for LRU)
            _weight_cache.move_to_end(cache_key)
            cache_hit = True
            with _stats_lock:
                _cache_stats["hits"] += 1
        else:
            cache_hit = False

    if not cache_hit:
        # Materialize weight
        W = _materialize_weight_from_cdna(tensor_name, manifest, base_path)

        # Cache it (with eviction if over budget)
        with _cache_lock:
            # Evict oldest entries if needed to make room
            if _cache_stats["size_bytes"] + W.nbytes > CACHE_MAX_BYTES:
                _evict_until_under_budget(W.nbytes)

            _weight_cache[cache_key] = W
            # Move to end (mark as recently used)
            _weight_cache.move_to_end(cache_key)

        with _stats_lock:
            _cache_stats["misses"] += 1
            _cache_stats["size_bytes"] += W.nbytes

    # Compute matmul
    original_shape = X.shape
    X_2d = X.reshape(-1, X.shape[-1])

    if transpose_w:
        Y = X_2d @ W.T
    else:
        Y = X_2d @ W

    # Reshape output to match input batch dimensions
    if len(original_shape) == 1:
        Y = Y.squeeze(axis=0)
    elif len(original_shape) == 2:
        pass  # Already [seq, d_out]
    else:
        # [batch, seq, d_out]
        batch = original_shape[0]
        seq = original_shape[1]
        Y = Y.reshape(batch, seq, -1)

    return Y, cache_hit
