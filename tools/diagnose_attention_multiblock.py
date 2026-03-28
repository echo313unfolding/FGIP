#!/usr/bin/env python3
"""
Check attention patterns across multiple blocks and prompts.

Tests:
1. Block 0 vs Block 15 vs Block 31
2. Short prompt vs Long prompt
3. Find where attention becomes focused (if ever)
"""

import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, "/home/voidstr3m33/helix-cdc")

from cdna_server.generate import (
    CDNAGenerator, D_HEAD, N_HEADS, N_KV_HEADS, N_LAYERS,
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


def compute_attention_stats(Q_rope, K_rope, seq):
    """Compute attention stats for last query position."""
    scale = 1.0 / np.sqrt(D_HEAD)

    # Head 0
    q_last = Q_rope[0, 0, -1, :]
    scores = []
    for kv_pos in range(seq):
        k_vec = K_rope[0, 0, kv_pos, :]
        dot = np.dot(q_last, k_vec) * scale
        scores.append(dot)

    scores = np.array(scores)

    # Softmax
    exp_scores = np.exp(scores - scores.max())
    attn = exp_scores / exp_scores.sum()

    entropy = -np.sum(attn * np.log(attn + 1e-10))
    max_entropy = np.log(seq)

    return {
        "score_std": float(scores.std()),
        "score_range": [float(scores.min()), float(scores.max())],
        "entropy": float(entropy),
        "max_entropy": float(max_entropy),
        "entropy_ratio": float(entropy / max_entropy),  # 1.0 = uniform
        "max_attn": float(attn.max()),
        "argmax": int(np.argmax(attn)),
    }


def analyze_block(generator, X_2d, block_idx, positions):
    """Run Q/K projection for a specific block and analyze attention."""
    manifest = generator._manifest
    base_path = generator._base_path
    manifest_hash = generator.model_loader.manifest_hash

    batch = 1
    seq = positions.shape[0]

    q_name = f"blk.{block_idx}.attn_q.weight"
    k_name = f"blk.{block_idx}.attn_k.weight"

    Q_2d, _ = cached_matmul(X_2d, q_name, manifest, base_path, manifest_hash)
    K_2d, _ = cached_matmul(X_2d, k_name, manifest, base_path, manifest_hash)

    Q = Q_2d.reshape(batch, seq, N_HEADS, D_HEAD).transpose(0, 2, 1, 3)
    K = K_2d.reshape(batch, seq, N_KV_HEADS, D_HEAD).transpose(0, 2, 1, 3)

    Q_rope = apply_rope_numpy(Q, positions)
    K_rope = apply_rope_numpy(K, positions)

    return compute_attention_stats(Q_rope, K_rope, seq)


def main():
    print("=" * 70)
    print("MULTI-BLOCK ATTENTION ANALYSIS")
    print("=" * 70)

    generator = CDNAGenerator()

    prompts = [
        ("short", "Paris is the capital of"),
        ("medium", "The quick brown fox jumps over the lazy dog. The capital of France is"),
        ("long", "In 1789, the French Revolution began with the storming of the Bastille in Paris, the capital of France. This event marked a turning point in European history. The capital of Germany is"),
    ]

    blocks_to_check = [0, 7, 15, 23, 31]

    for prompt_name, prompt in prompts:
        print(f"\n{'='*70}")
        print(f"PROMPT: {prompt_name} ({len(prompt)} chars)")
        print(f"{'='*70}")
        print(f'"{prompt}"')

        # Tokenize
        prompt_ids, _ = generator.tokenizer.encode(prompt, add_bos=True)
        embeddings, _ = generator.tokenizer.lookup_embeddings(prompt_ids)
        X = embeddings.reshape(1, len(prompt_ids), -1).astype(np.float32)
        batch, seq, d_model = X.shape

        print(f"\nSequence length: {seq}")

        # For simplicity, use block 0's norm (attention norm doesn't change much)
        attn_norm, _ = load_norm_weights_from_gguf(generator.model_loader.gguf_path, 0)
        X_norm = rms_norm(X, attn_norm, NORM_EPS)
        X_2d = X_norm.reshape(-1, d_model)

        positions = np.arange(seq, dtype=np.int32)

        print(f"\n{'Block':<8} {'Score Std':<12} {'Score Range':<20} {'Entropy Ratio':<15} {'Max Attn':<12} {'Argmax':<8}")
        print("-" * 85)

        for block_idx in blocks_to_check:
            stats = analyze_block(generator, X_2d, block_idx, positions)
            score_range_str = f"[{stats['score_range'][0]:.3f}, {stats['score_range'][1]:.3f}]"
            print(f"{block_idx:<8} {stats['score_std']:<12.4f} {score_range_str:<20} {stats['entropy_ratio']:<15.4f} {stats['max_attn']:<12.4f} {stats['argmax']:<8}")

        # Quick diagnosis
        last_stats = analyze_block(generator, X_2d, 31, positions)
        if last_stats['entropy_ratio'] > 0.95:
            print(f"\n⚠️  Block 31 attention is nearly uniform (entropy_ratio={last_stats['entropy_ratio']:.3f})")
        else:
            print(f"\n✓ Block 31 has focused attention (entropy_ratio={last_stats['entropy_ratio']:.3f})")


if __name__ == "__main__":
    main()
