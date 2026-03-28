#!/usr/bin/env python3
"""
Diagnose Attention Uniformity Bug

Investigates why attention weights are uniform (~10% per position)
despite K vectors having different norms.

Checks:
1. Q vector similarity across positions
2. Q·K raw dot products before scaling
3. Q·K scaled scores before softmax
4. Whether the issue is in Q, K, or the dot product itself
"""

import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, "/home/voidstr3m33/helix-cdc")

from cdna_server.generate import CDNAGenerator, D_HEAD, N_HEADS, N_KV_HEADS, rms_norm, NORM_EPS
from cdna_server.tensor_cache import cached_matmul
from helix_cdc.regrow.stream_transformer_block import load_norm_weights_from_gguf


def apply_rope_numpy(x: np.ndarray, positions: np.ndarray, theta: float = 1000000.0) -> np.ndarray:
    """Apply RoPE to tensor x at given positions."""
    batch, n_heads, seq_len, head_dim = x.shape
    half_dim = head_dim // 2

    freqs = 1.0 / (theta ** (np.arange(0, half_dim, dtype=np.float32) / half_dim))
    pos = positions.reshape(-1, 1)
    angles = pos * freqs
    cos = np.cos(angles)
    sin = np.sin(angles)

    x1 = x[..., :half_dim]
    x2 = x[..., half_dim:]

    cos = cos.reshape(1, 1, seq_len, half_dim)
    sin = sin.reshape(1, 1, seq_len, half_dim)

    out1 = x1 * cos - x2 * sin
    out2 = x1 * sin + x2 * cos

    return np.concatenate([out1, out2], axis=-1).astype(np.float32)


def diagnose_attention(prompt: str = "Paris is the capital of"):
    """Deep dive into attention mechanism to find uniformity bug."""
    print("=" * 70)
    print("ATTENTION UNIFORMITY DIAGNOSTIC")
    print("=" * 70)
    print(f"Prompt: {prompt!r}")
    print()

    generator = CDNAGenerator()

    # Get embeddings
    prompt_ids, _ = generator.tokenizer.encode(prompt, add_bos=True)
    embeddings, _ = generator.tokenizer.lookup_embeddings(prompt_ids)
    X = embeddings.reshape(1, len(prompt_ids), -1).astype(np.float32)

    batch, seq, d_model = X.shape
    print(f"Input shape: batch={batch}, seq={seq}, d_model={d_model}")
    print()

    # Apply attention norm
    attn_norm, _ = load_norm_weights_from_gguf(generator.model_loader.gguf_path, 0)
    X_norm = rms_norm(X, attn_norm, NORM_EPS)
    X_2d = X_norm.reshape(-1, d_model)

    manifest = generator._manifest
    base_path = generator._base_path
    manifest_hash = generator.model_loader.manifest_hash

    # Project Q, K, V
    Q_2d, _ = cached_matmul(X_2d, "blk.0.attn_q.weight", manifest, base_path, manifest_hash)
    K_2d, _ = cached_matmul(X_2d, "blk.0.attn_k.weight", manifest, base_path, manifest_hash)

    # Reshape to heads
    Q = Q_2d.reshape(batch, seq, N_HEADS, D_HEAD).transpose(0, 2, 1, 3)  # [1, 32, seq, 128]
    K = K_2d.reshape(batch, seq, N_KV_HEADS, D_HEAD).transpose(0, 2, 1, 3)  # [1, 8, seq, 128]

    print("=" * 70)
    print("BEFORE ROPE")
    print("=" * 70)

    # Check Q similarity across positions (before RoPE)
    print("\n1. Q vectors per position (before RoPE):")
    for pos in range(min(seq, 5)):
        q_vec = Q[0, 0, pos, :]  # Head 0
        print(f"   Position {pos}: norm={np.linalg.norm(q_vec):.4f}, first 5 values: {q_vec[:5]}")

    # Check K similarity across positions (before RoPE)
    print("\n2. K vectors per position (before RoPE):")
    for pos in range(min(seq, 5)):
        k_vec = K[0, 0, pos, :]  # KV head 0
        print(f"   Position {pos}: norm={np.linalg.norm(k_vec):.4f}, first 5 values: {k_vec[:5]}")

    # Compute Q·K similarity BEFORE RoPE
    print("\n3. Q·K dot products BEFORE RoPE (head 0, query pos=last):")
    q_last = Q[0, 0, -1, :]  # Last position query
    for kv_pos in range(min(seq, 5)):
        k_vec = K[0, 0, kv_pos, :]
        dot = np.dot(q_last, k_vec)
        print(f"   Q[-1] · K[{kv_pos}] = {dot:.4f}")

    # Apply RoPE
    positions = np.arange(seq, dtype=np.int32)
    Q_rope = apply_rope_numpy(Q, positions)
    K_rope = apply_rope_numpy(K, positions)

    print("\n" + "=" * 70)
    print("AFTER ROPE")
    print("=" * 70)

    # Check Q similarity after RoPE
    print("\n4. Q vectors per position (after RoPE):")
    for pos in range(min(seq, 5)):
        q_vec = Q_rope[0, 0, pos, :]
        print(f"   Position {pos}: norm={np.linalg.norm(q_vec):.4f}, first 5 values: {q_vec[:5]}")

    # Check K similarity after RoPE
    print("\n5. K vectors per position (after RoPE):")
    for pos in range(min(seq, 5)):
        k_vec = K_rope[0, 0, pos, :]
        print(f"   Position {pos}: norm={np.linalg.norm(k_vec):.4f}, first 5 values: {k_vec[:5]}")

    # Compute Q·K dot products AFTER RoPE (raw, unscaled)
    print("\n6. Q·K dot products AFTER RoPE (raw, unscaled):")
    q_last_rope = Q_rope[0, 0, -1, :]
    for kv_pos in range(seq):
        k_vec = K_rope[0, 0, kv_pos, :]
        dot = np.dot(q_last_rope, k_vec)
        print(f"   Q[-1] · K[{kv_pos}] = {dot:.4f}")

    # Compute scaled scores
    scale = 1.0 / np.sqrt(D_HEAD)
    print(f"\n7. Scale factor: {scale:.6f} (1/sqrt({D_HEAD}))")

    print("\n8. Q·K scores SCALED (before softmax):")
    scores = []
    for kv_pos in range(seq):
        k_vec = K_rope[0, 0, kv_pos, :]
        dot = np.dot(q_last_rope, k_vec)
        scaled = dot * scale
        scores.append(scaled)
        print(f"   Q[-1] · K[{kv_pos}] * scale = {scaled:.4f}")

    scores = np.array(scores)
    print(f"\n   Score range: [{scores.min():.4f}, {scores.max():.4f}]")
    print(f"   Score std: {scores.std():.4f}")

    # Apply softmax
    print("\n9. Attention weights (after softmax):")
    exp_scores = np.exp(scores - scores.max())
    attn_weights = exp_scores / exp_scores.sum()
    for kv_pos in range(seq):
        print(f"   Position {kv_pos}: {attn_weights[kv_pos]:.4f}")

    print(f"\n   Entropy: {-np.sum(attn_weights * np.log(attn_weights + 1e-10)):.4f}")
    print(f"   Max entropy (uniform): {np.log(seq):.4f}")

    # Check if scores are TOO SMALL (causing uniform softmax)
    print("\n" + "=" * 70)
    print("DIAGNOSIS")
    print("=" * 70)

    if scores.std() < 0.5:
        print("\n⚠️  SCORES ARE TOO SIMILAR!")
        print("   Standard deviation of scores < 0.5")
        print("   This causes softmax to output near-uniform distribution")

        # Check if it's Q or K that's the problem
        q_norms = [np.linalg.norm(Q_rope[0, 0, i, :]) for i in range(seq)]
        k_norms = [np.linalg.norm(K_rope[0, 0, i, :]) for i in range(seq)]

        print(f"\n   Q norms: mean={np.mean(q_norms):.4f}, std={np.std(q_norms):.4f}")
        print(f"   K norms: mean={np.mean(k_norms):.4f}, std={np.std(k_norms):.4f}")

        # Check cosine similarity between K vectors
        print("\n   K vector cosine similarities:")
        for i in range(min(seq-1, 3)):
            for j in range(i+1, min(seq, 4)):
                ki = K_rope[0, 0, i, :]
                kj = K_rope[0, 0, j, :]
                cos_sim = np.dot(ki, kj) / (np.linalg.norm(ki) * np.linalg.norm(kj) + 1e-10)
                print(f"   K[{i}] · K[{j}] / (||K[{i}|| * ||K[{j}||) = {cos_sim:.4f}")
    else:
        print("\n✓ Scores have reasonable variance")
        print("   The attention should NOT be uniform")
        print("   Check if there's a bug elsewhere (mask, different code path, etc.)")

    print()

    return {
        "scores_before_softmax": scores.tolist(),
        "attention_weights": attn_weights.tolist(),
        "score_std": float(scores.std()),
        "entropy": float(-np.sum(attn_weights * np.log(attn_weights + 1e-10))),
    }


if __name__ == "__main__":
    result = diagnose_attention()
