#!/usr/bin/env python3
"""
Canonical Matmul Tri-Test - WO-CDNA-STAGE2-DEBUG

Settles the "which path is correct" debate definitively.

Creates ONE canonical W from stream_rows_dequant (accurate mode, with sidecar),
then compares Stage 1 and Stage 2 matmul paths against it.

Output: receipts/cdna_debug_matmul/verify_<timestamp>.json
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, "/home/voidstr3m33/helix-cdc")

from cdna_server.generate import CDNAGenerator, NORM_EPS
from cdna_server.generate import rms_norm
from cdna_server.tensor_cache import cached_matmul
from helix_cdc.regrow.stream_xw_matmul import stream_xw_from_manifest
from helix_cdc.regrow.stream_transformer_block import load_norm_weights_from_gguf
from helix_cdc.regrow.cache import get_manifest_and_base
from helix_cdc.regrow.cdna_stream_v2 import load_cdna_auto


def sha256_array(arr: np.ndarray) -> str:
    """SHA256 of float32 bytes."""
    return hashlib.sha256(arr.astype(np.float32).tobytes()).hexdigest()


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between flattened arrays."""
    a_flat = a.flatten()
    b_flat = b.flatten()
    return float(np.dot(a_flat, b_flat) / (np.linalg.norm(a_flat) * np.linalg.norm(b_flat) + 1e-10))


def max_abs_diff(a: np.ndarray, b: np.ndarray) -> float:
    """Max absolute difference."""
    return float(np.abs(a - b).max())


def run_canonical_tritest(
    tensor_name: str = "blk.0.attn_q.weight",
    prompt: str = "Paris is the capital of",
):
    """
    Run the canonical matmul tri-test.

    1. Materialize W_canon from stream_rows_dequant (accurate, with sidecar)
    2. Compute Y_canon = X @ W_canon
    3. Compute Y_stage2 from cached_matmul
    4. Compute Y_stage1 from stream_xw_from_manifest
    5. Compare all three against Y_canon
    """
    print("=" * 70)
    print("CANONICAL MATMUL TRI-TEST")
    print("=" * 70)
    print(f"Tensor: {tensor_name}")
    print(f"Prompt: {prompt!r}")
    print()

    # Initialize generator
    generator = CDNAGenerator()

    # Tokenize and get input X
    prompt_ids, _ = generator.tokenizer.encode(prompt, add_bos=True)
    embeddings, _ = generator.tokenizer.lookup_embeddings(prompt_ids)
    X = embeddings.reshape(1, len(prompt_ids), -1).astype(np.float32)

    batch, seq, d_model = X.shape
    block_idx = int(tensor_name.split(".")[1])  # Extract block index

    # Apply attention norm (to match what forward pass does)
    attn_norm, _ = load_norm_weights_from_gguf(generator.model_loader.gguf_path, block_idx)
    X_norm = rms_norm(X, attn_norm, NORM_EPS)
    X_2d = X_norm.reshape(-1, d_model)  # [seq, d_model]

    print(f"Input X shape: {X_2d.shape}")
    print(f"Input X hash: {sha256_array(X_2d)[:16]}")
    print()

    # ========================================================================
    # Step 1: Canonical W materialization
    # ========================================================================
    print("Step 1: Materializing canonical W...")

    manifest, base_path = get_manifest_and_base(generator.model_loader.manifest_path)

    # Find tensor shard info
    shard = None
    for s in manifest.get("shards", []):
        if s.get("tensor_name") == tensor_name:
            shard = s
            break

    if shard is None:
        raise ValueError(f"Tensor {tensor_name} not found in manifest")

    cdna_path = base_path / shard["path"]
    sidecar_path = None
    if shard.get("outlier_sidecar_path"):
        sidecar_path = base_path / shard["outlier_sidecar_path"]

    print(f"  CDNA path: {cdna_path}")
    print(f"  Sidecar path: {sidecar_path}")
    print(f"  Sidecar exists: {sidecar_path.exists() if sidecar_path else 'N/A'}")

    # Canonical materialization
    reader = load_cdna_auto(cdna_path)
    W_canon, dequant_receipt = reader.stream_rows_dequant(
        start_row=0,
        end_row=reader.rows,
        sidecar_path=sidecar_path,
        decode_mode="accurate",
        emit_receipt=True,
    )

    print(f"  W_canon shape: {W_canon.shape}")
    print(f"  W_canon hash: {sha256_array(W_canon)[:16]}")
    print(f"  W_canon range: [{W_canon.min():.6f}, {W_canon.max():.6f}]")
    print()

    # ========================================================================
    # Step 2: Compute Y_canon = X @ W_canon (ground truth)
    # ========================================================================
    print("Step 2: Computing canonical Y = X @ W_canon...")

    Y_canon = X_2d @ W_canon

    print(f"  Y_canon shape: {Y_canon.shape}")
    print(f"  Y_canon hash: {sha256_array(Y_canon)[:16]}")
    print(f"  Y_canon sample: {Y_canon[0, :5]}")
    print()

    # ========================================================================
    # Step 3: Compute Y_stage2 from cached_matmul
    # ========================================================================
    print("Step 3: Computing Y_stage2 via cached_matmul...")

    manifest_s2 = generator._manifest
    base_path_s2 = generator._base_path
    manifest_hash_s2 = generator.model_loader.manifest_hash

    Y_stage2, cache_hit = cached_matmul(
        X_2d, tensor_name, manifest_s2, base_path_s2, manifest_hash_s2
    )

    print(f"  Y_stage2 shape: {Y_stage2.shape}")
    print(f"  Y_stage2 hash: {sha256_array(Y_stage2)[:16]}")
    print(f"  Y_stage2 sample: {Y_stage2[0, :5]}")
    print(f"  Cache hit: {cache_hit}")
    print()

    # ========================================================================
    # Step 4: Compute Y_stage1 from stream_xw_from_manifest
    # ========================================================================
    print("Step 4: Computing Y_stage1 via stream_xw_from_manifest...")

    # Stage 1 expects 3D input
    X_3d = X_norm  # [1, seq, d_model]

    Y_stage1, s1_receipt = stream_xw_from_manifest(
        X_3d, tensor_name, manifest, base_path, "trust_cached"
    )

    # Reshape to match
    Y_stage1_2d = Y_stage1.reshape(-1, Y_stage1.shape[-1])

    print(f"  Y_stage1 shape: {Y_stage1_2d.shape}")
    print(f"  Y_stage1 hash: {sha256_array(Y_stage1_2d)[:16]}")
    print(f"  Y_stage1 sample: {Y_stage1_2d[0, :5]}")
    print()

    # ========================================================================
    # Step 5: Comparisons against canonical
    # ========================================================================
    print("=" * 70)
    print("COMPARISON RESULTS (against canonical Y_canon)")
    print("=" * 70)

    # Stage 2 vs Canon
    cos_s2 = cosine_sim(Y_canon, Y_stage2)
    diff_s2 = max_abs_diff(Y_canon, Y_stage2)
    match_s2 = cos_s2 > 0.9999999 and diff_s2 < 1e-5

    print(f"\nStage 2 (cached_matmul) vs Canon:")
    print(f"  Cosine similarity: {cos_s2:.10f}")
    print(f"  Max abs diff:      {diff_s2:.10f}")
    print(f"  MATCH:             {'✓ YES' if match_s2 else '✗ NO'}")

    # Stage 1 vs Canon
    cos_s1 = cosine_sim(Y_canon, Y_stage1_2d)
    diff_s1 = max_abs_diff(Y_canon, Y_stage1_2d)
    match_s1 = cos_s1 > 0.9999999 and diff_s1 < 1e-5

    print(f"\nStage 1 (stream_xw_from_manifest) vs Canon:")
    print(f"  Cosine similarity: {cos_s1:.10f}")
    print(f"  Max abs diff:      {diff_s1:.10f}")
    print(f"  MATCH:             {'✓ YES' if match_s1 else '✗ NO'}")

    # Stage 1 vs Stage 2 (for reference)
    cos_s1_s2 = cosine_sim(Y_stage1_2d, Y_stage2)
    diff_s1_s2 = max_abs_diff(Y_stage1_2d, Y_stage2)

    print(f"\nStage 1 vs Stage 2 (cross-check):")
    print(f"  Cosine similarity: {cos_s1_s2:.10f}")
    print(f"  Max abs diff:      {diff_s1_s2:.10f}")

    # ========================================================================
    # Step 6: Verdict
    # ========================================================================
    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)

    if match_s2 and match_s1:
        verdict = "BOTH_MATCH"
        print("Both Stage 1 and Stage 2 match canonical Y_canon.")
        print("Bug is ELSEWHERE (mask/GQA/KV/RoPE placement).")
    elif match_s2 and not match_s1:
        verdict = "STAGE2_CORRECT"
        print("Stage 2 matches canonical, Stage 1 does NOT.")
        print("Bug is in stream_xw_from_manifest.")
    elif match_s1 and not match_s2:
        verdict = "STAGE1_CORRECT"
        print("Stage 1 matches canonical, Stage 2 does NOT.")
        print("Bug is in cached_matmul.")
    else:
        verdict = "NEITHER_MATCH"
        print("NEITHER Stage 1 nor Stage 2 matches canonical Y_canon!")
        print("Check decode_mode/sidecar handling in canonical materialization.")

    print("=" * 70)

    # ========================================================================
    # Step 7: Write receipt
    # ========================================================================
    receipt_dir = Path(__file__).parent.parent / "receipts" / "cdna_debug_matmul"
    receipt_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    receipt_path = receipt_dir / f"verify_{timestamp}.json"

    receipt = {
        "schema": "cdna_canonical_matmul_tritest_v1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tensor_name": tensor_name,
        "prompt": prompt,
        "input": {
            "X_shape": list(X_2d.shape),
            "X_hash": sha256_array(X_2d)[:16],
        },
        "canonical": {
            "W_shape": list(W_canon.shape),
            "W_hash": sha256_array(W_canon)[:16],
            "cdna_path": str(cdna_path),
            "sidecar_path": str(sidecar_path) if sidecar_path else None,
            "decode_mode": "accurate",
            "Y_hash": sha256_array(Y_canon)[:16],
        },
        "stage2": {
            "method": "cached_matmul",
            "Y_hash": sha256_array(Y_stage2)[:16],
            "cosine_vs_canon": cos_s2,
            "max_diff_vs_canon": diff_s2,
            "matches_canon": match_s2,
        },
        "stage1": {
            "method": "stream_xw_from_manifest",
            "Y_hash": sha256_array(Y_stage1_2d)[:16],
            "cosine_vs_canon": cos_s1,
            "max_diff_vs_canon": diff_s1,
            "matches_canon": match_s1,
        },
        "cross_check": {
            "stage1_vs_stage2_cosine": cos_s1_s2,
            "stage1_vs_stage2_max_diff": diff_s1_s2,
        },
        "verdict": verdict,
    }

    with open(receipt_path, "w") as f:
        json.dump(receipt, f, indent=2)

    print(f"\nReceipt written to: {receipt_path}")

    return receipt


if __name__ == "__main__":
    receipt = run_canonical_tritest()
    print("\n" + json.dumps(receipt, indent=2))
