#!/usr/bin/env python3
"""
Check attention patterns during actual forward pass.

Runs the full forward pass and captures attention weights at each block.
"""

import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, "/home/voidstr3m33/helix-cdc")

from cdna_server.generate import (
    CDNAGenerator, D_HEAD, N_HEADS, N_KV_HEADS, N_LAYERS, D_MODEL,
    rms_norm, NORM_EPS
)
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


def forward_block_with_attention_capture(
    X, block_idx, generator, positions, d_model=D_MODEL
):
    """
    Forward pass through one block, capturing attention weights.

    Returns (X_out, attention_stats)
    """
    manifest = generator._manifest
    base_path = generator._base_path
    manifest_hash = generator.model_loader.manifest_hash

    batch, seq, _ = X.shape

    # Load norms
    attn_norm, ffn_norm = load_norm_weights_from_gguf(generator.model_loader.gguf_path, block_idx)

    # Attention norm
    X_norm = rms_norm(X, attn_norm, NORM_EPS)
    X_2d = X_norm.reshape(-1, d_model)

    # Q, K, V projections
    q_name = f"blk.{block_idx}.attn_q.weight"
    k_name = f"blk.{block_idx}.attn_k.weight"
    v_name = f"blk.{block_idx}.attn_v.weight"
    o_name = f"blk.{block_idx}.attn_output.weight"

    Q, _ = cached_matmul(X_2d, q_name, manifest, base_path, manifest_hash)
    K_new, _ = cached_matmul(X_2d, k_name, manifest, base_path, manifest_hash)
    V_new, _ = cached_matmul(X_2d, v_name, manifest, base_path, manifest_hash)

    # Reshape
    Q = Q.reshape(batch, seq, N_HEADS, D_HEAD).transpose(0, 2, 1, 3)
    K_new = K_new.reshape(batch, seq, N_KV_HEADS, D_HEAD).transpose(0, 2, 1, 3)
    V_new = V_new.reshape(batch, seq, N_KV_HEADS, D_HEAD).transpose(0, 2, 1, 3)

    # RoPE
    Q = apply_rope_numpy(Q, positions)
    K = apply_rope_numpy(K_new, positions)
    V = V_new

    # Attention
    scale = 1.0 / np.sqrt(D_HEAD)
    group_size = N_HEADS // N_KV_HEADS
    context_heads = np.zeros((batch, N_HEADS, seq, D_HEAD), dtype=np.float32)

    attention_stats = {}

    for hkv in range(N_KV_HEADS):
        h0 = hkv * group_size
        h1 = (hkv + 1) * group_size

        Qg = Q[:, h0:h1, :, :]
        Kg = K[:, hkv:hkv+1, :, :]
        Vg = V[:, hkv:hkv+1, :, :]

        scores = np.einsum('bgsd,bkdt->bgst', Qg, Kg.transpose(0, 1, 3, 2)) * scale

        # Causal mask
        causal_mask = np.triu(np.ones((seq, seq), dtype=np.float32), k=1) * -1e9
        scores = scores + causal_mask

        # Softmax
        scores_max = scores.max(axis=-1, keepdims=True)
        exp_scores = np.exp(scores - scores_max)
        attn_weights = exp_scores / exp_scores.sum(axis=-1, keepdims=True)

        # Capture stats for first head in each KV group
        if hkv == 0:
            # For the last query position
            attn_last = attn_weights[0, 0, -1, :]
            entropy = -np.sum(attn_last * np.log(attn_last + 1e-10))
            max_entropy = np.log(seq)

            attention_stats = {
                "attn_weights": attn_last.tolist(),
                "entropy": float(entropy),
                "max_entropy": float(max_entropy),
                "entropy_ratio": float(entropy / max_entropy),
                "max_attn": float(attn_last.max()),
                "argmax": int(np.argmax(attn_last)),
            }

        # Context
        ctx = np.einsum('bgst,bktd->bgsd', attn_weights, Vg)
        context_heads[:, h0:h1, :, :] = ctx

    # Output projection
    context = context_heads.transpose(0, 2, 1, 3).reshape(batch, seq, N_HEADS * D_HEAD)
    context_2d = context.reshape(-1, N_HEADS * D_HEAD)
    attn_out, _ = cached_matmul(context_2d, o_name, manifest, base_path, manifest_hash)
    attn_out = attn_out.reshape(batch, seq, d_model)

    # Residual 1
    X_mid = X + attn_out

    # FFN
    X_mid_norm = rms_norm(X_mid, ffn_norm, NORM_EPS)
    X_mid_2d = X_mid_norm.reshape(-1, d_model)

    gate_name = f"blk.{block_idx}.ffn_gate.weight"
    up_name = f"blk.{block_idx}.ffn_up.weight"
    down_name = f"blk.{block_idx}.ffn_down.weight"

    gate, _ = cached_matmul(X_mid_2d, gate_name, manifest, base_path, manifest_hash)
    up, _ = cached_matmul(X_mid_2d, up_name, manifest, base_path, manifest_hash)

    # SiLU activation and elementwise multiply
    hidden = (gate / (1 + np.exp(-gate))) * up

    ffn_out, _ = cached_matmul(hidden, down_name, manifest, base_path, manifest_hash)
    ffn_out = ffn_out.reshape(batch, seq, d_model)

    # Residual 2
    X_out = X_mid + ffn_out

    return X_out, attention_stats


def main():
    print("=" * 70)
    print("ATTENTION DURING ACTUAL FORWARD PASS")
    print("=" * 70)

    generator = CDNAGenerator()

    prompt = "Paris is the capital of"
    print(f"Prompt: {prompt!r}")

    # Tokenize
    prompt_ids, _ = generator.tokenizer.encode(prompt, add_bos=True)
    embeddings, _ = generator.tokenizer.lookup_embeddings(prompt_ids)
    X = embeddings.reshape(1, len(prompt_ids), -1).astype(np.float32)

    batch, seq, d_model = X.shape
    print(f"Sequence length: {seq}")
    print()

    positions = np.arange(seq, dtype=np.int32)

    print(f"{'Block':<8} {'Entropy Ratio':<15} {'Max Attn':<12} {'Argmax':<8} {'Top-3 Weights':<30}")
    print("-" * 80)

    # Run through all 32 blocks
    hidden = X
    for block_idx in range(N_LAYERS):
        hidden, stats = forward_block_with_attention_capture(
            hidden, block_idx, generator, positions
        )

        # Only print for select blocks
        if block_idx in [0, 7, 15, 23, 31]:
            attn = stats["attn_weights"]
            top3_idx = np.argsort(attn)[-3:][::-1]
            top3_str = ", ".join([f"{i}:{attn[i]:.3f}" for i in top3_idx])

            print(f"{block_idx:<8} {stats['entropy_ratio']:<15.4f} {stats['max_attn']:<12.4f} {stats['argmax']:<8} {top3_str:<30}")

    print()

    # Check final block stats
    if stats['entropy_ratio'] > 0.95:
        print(f"⚠️  Block 31 attention is nearly uniform (entropy_ratio={stats['entropy_ratio']:.3f})")
        print("   This may indicate the model needs longer context or different input.")
    else:
        print(f"✓ Block 31 has focused attention (entropy_ratio={stats['entropy_ratio']:.3f})")
        print(f"   Max attention weight: {stats['max_attn']:.4f} at position {stats['argmax']}")


if __name__ == "__main__":
    main()
