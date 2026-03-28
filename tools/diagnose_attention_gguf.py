#!/usr/bin/env python3
"""
Diagnose Attention using ORIGINAL GGUF weights (bypass CDNA)

Compares attention behavior with original vs CDNA-reconstructed weights.
"""

import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, "/home/voidstr3m33/helix-cdc")

from cdna_server.generate import D_HEAD, N_HEADS, N_KV_HEADS, rms_norm, NORM_EPS
from cdna_server.tensor_cache import cached_matmul
from helix_cdc.regrow.stream_transformer_block import load_norm_weights_from_gguf


def load_gguf_tensor(gguf_path: str, tensor_name: str):
    """Load tensor directly from GGUF file."""
    from gguf import GGUFReader
    reader = GGUFReader(gguf_path)
    for tensor in reader.tensors:
        if tensor.name == tensor_name:
            data = tensor.data.copy()
            if tensor.tensor_type.name == "F16":
                data = data.astype(np.float32)
            return data.reshape(tensor.shape)
    raise ValueError(f"Tensor {tensor_name} not found in GGUF")


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


def run_attention_comparison(prompt: str = "Paris is the capital of"):
    """Compare attention with GGUF vs CDNA weights."""
    from cdna_server.generate import CDNAGenerator

    print("=" * 70)
    print("ATTENTION: ORIGINAL GGUF vs CDNA")
    print("=" * 70)
    print(f"Prompt: {prompt!r}")
    print()

    generator = CDNAGenerator()
    gguf_path = "/home/voidstr3m33/helix-cdc/tmp/mistral_fp8combined_canonical.gguf"

    # Get embeddings
    prompt_ids, _ = generator.tokenizer.encode(prompt, add_bos=True)
    embeddings, _ = generator.tokenizer.lookup_embeddings(prompt_ids)
    X = embeddings.reshape(1, len(prompt_ids), -1).astype(np.float32)

    batch, seq, d_model = X.shape
    print(f"Input shape: batch={batch}, seq={seq}, d_model={d_model}")

    # Apply attention norm
    attn_norm, _ = load_norm_weights_from_gguf(generator.model_loader.gguf_path, 0)
    X_norm = rms_norm(X, attn_norm, NORM_EPS)
    X_2d = X_norm.reshape(-1, d_model)

    # Load Q, K weights from GGUF
    W_q_orig = load_gguf_tensor(gguf_path, "blk.0.attn_q.weight")
    W_k_orig = load_gguf_tensor(gguf_path, "blk.0.attn_k.weight")

    print(f"\nW_q shape: {W_q_orig.shape}")
    print(f"W_k shape: {W_k_orig.shape}")

    # Compute Q, K with original GGUF weights
    Q_orig_2d = X_2d @ W_q_orig
    K_orig_2d = X_2d @ W_k_orig

    # Reshape to heads
    Q_orig = Q_orig_2d.reshape(batch, seq, N_HEADS, D_HEAD).transpose(0, 2, 1, 3)
    K_orig = K_orig_2d.reshape(batch, seq, N_KV_HEADS, D_HEAD).transpose(0, 2, 1, 3)

    # Also get CDNA versions
    manifest = generator._manifest
    base_path = generator._base_path
    manifest_hash = generator.model_loader.manifest_hash

    Q_cdna_2d, _ = cached_matmul(X_2d, "blk.0.attn_q.weight", manifest, base_path, manifest_hash)
    K_cdna_2d, _ = cached_matmul(X_2d, "blk.0.attn_k.weight", manifest, base_path, manifest_hash)

    Q_cdna = Q_cdna_2d.reshape(batch, seq, N_HEADS, D_HEAD).transpose(0, 2, 1, 3)
    K_cdna = K_cdna_2d.reshape(batch, seq, N_KV_HEADS, D_HEAD).transpose(0, 2, 1, 3)

    # Apply RoPE
    positions = np.arange(seq, dtype=np.int32)
    Q_orig_rope = apply_rope_numpy(Q_orig, positions)
    K_orig_rope = apply_rope_numpy(K_orig, positions)
    Q_cdna_rope = apply_rope_numpy(Q_cdna, positions)
    K_cdna_rope = apply_rope_numpy(K_cdna, positions)

    scale = 1.0 / np.sqrt(D_HEAD)

    print("\n" + "=" * 70)
    print("Q·K DOT PRODUCTS (head 0, query position = last)")
    print("=" * 70)

    print(f"\n{'Position':<10} {'GGUF (raw)':<15} {'CDNA (raw)':<15} {'GGUF (scaled)':<15} {'CDNA (scaled)':<15}")
    print("-" * 70)

    scores_orig = []
    scores_cdna = []

    q_orig_last = Q_orig_rope[0, 0, -1, :]
    q_cdna_last = Q_cdna_rope[0, 0, -1, :]

    for kv_pos in range(seq):
        k_orig = K_orig_rope[0, 0, kv_pos, :]
        k_cdna = K_cdna_rope[0, 0, kv_pos, :]

        dot_orig = np.dot(q_orig_last, k_orig)
        dot_cdna = np.dot(q_cdna_last, k_cdna)

        scores_orig.append(dot_orig * scale)
        scores_cdna.append(dot_cdna * scale)

        print(f"{kv_pos:<10} {dot_orig:<15.4f} {dot_cdna:<15.4f} {dot_orig*scale:<15.4f} {dot_cdna*scale:<15.4f}")

    scores_orig = np.array(scores_orig)
    scores_cdna = np.array(scores_cdna)

    print("\n" + "=" * 70)
    print("SOFTMAX ATTENTION WEIGHTS")
    print("=" * 70)

    def softmax(x):
        exp_x = np.exp(x - x.max())
        return exp_x / exp_x.sum()

    attn_orig = softmax(scores_orig)
    attn_cdna = softmax(scores_cdna)

    print(f"\n{'Position':<10} {'GGUF':<15} {'CDNA':<15} {'Diff':<15}")
    print("-" * 60)
    for i in range(seq):
        diff = attn_orig[i] - attn_cdna[i]
        print(f"{i:<10} {attn_orig[i]:<15.4f} {attn_cdna[i]:<15.4f} {diff:<15.6f}")

    # Statistics
    print("\n" + "=" * 70)
    print("STATISTICS")
    print("=" * 70)

    print(f"\nScore statistics (before softmax):")
    print(f"  GGUF: range=[{scores_orig.min():.4f}, {scores_orig.max():.4f}], std={scores_orig.std():.4f}")
    print(f"  CDNA: range=[{scores_cdna.min():.4f}, {scores_cdna.max():.4f}], std={scores_cdna.std():.4f}")

    entropy_orig = -np.sum(attn_orig * np.log(attn_orig + 1e-10))
    entropy_cdna = -np.sum(attn_cdna * np.log(attn_cdna + 1e-10))
    max_entropy = np.log(seq)

    print(f"\nAttention entropy:")
    print(f"  GGUF: {entropy_orig:.4f}")
    print(f"  CDNA: {entropy_cdna:.4f}")
    print(f"  Max (uniform): {max_entropy:.4f}")

    print("\n" + "=" * 70)
    print("DIAGNOSIS")
    print("=" * 70)

    if scores_orig.std() < 0.5:
        print("\n⚠️  ORIGINAL GGUF ALSO HAS NEAR-ZERO Q·K SCORES!")
        print("   This is NOT a CDNA compression issue.")
        print("   The original model produces uniform attention for this input.")
        print("\n   Possible causes:")
        print("   - This is early in generation (short sequence)")
        print("   - The model's attention is input-dependent")
        print("   - Check with longer sequences or different prompts")
    else:
        if scores_cdna.std() < 0.5:
            print("\n⚠️  CDNA has uniform attention but GGUF doesn't!")
            print("   Compression IS damaging attention behavior.")
        else:
            print("\n✓ Both GGUF and CDNA produce non-uniform attention.")


if __name__ == "__main__":
    run_attention_comparison()
