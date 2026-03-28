#!/usr/bin/env python3
"""
Compare Q/K weight matrices: Original GGUF vs CDNA-reconstructed

Checks if compression damage to Q/K weights is causing uniform attention.
"""

import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, "/home/voidstr3m33/helix-cdc")

from helix_cdc.regrow.cache import get_manifest_and_base
from helix_cdc.regrow.cdna_stream_v2 import load_cdna_auto


def load_gguf_tensor(gguf_path: str, tensor_name: str):
    """Load tensor directly from GGUF file."""
    from gguf import GGUFReader
    reader = GGUFReader(gguf_path)
    for tensor in reader.tensors:
        if tensor.name == tensor_name:
            data = tensor.data.copy()
            # For F16, convert to F32
            if tensor.tensor_type.name == "F16":
                data = data.astype(np.float32)
            return data.reshape(tensor.shape)
    raise ValueError(f"Tensor {tensor_name} not found in GGUF")


def load_cdna_tensor(manifest_path: str, tensor_name: str):
    """Load tensor from CDNA via stream_rows_dequant."""
    manifest, base_path = get_manifest_and_base(manifest_path)

    for shard in manifest.get("shards", []):
        if shard.get("tensor_name") == tensor_name:
            cdna_path = base_path / shard["path"]
            sidecar_path = None
            if shard.get("outlier_sidecar_path"):
                sidecar_path = base_path / shard["outlier_sidecar_path"]

            reader = load_cdna_auto(cdna_path)
            W, _ = reader.stream_rows_dequant(
                start_row=0,
                end_row=reader.rows,
                sidecar_path=sidecar_path,
                decode_mode="accurate",
                emit_receipt=True,
            )
            return W

    raise ValueError(f"Tensor {tensor_name} not found in manifest")


def analyze_weight_damage(W_orig, W_cdna, tensor_name):
    """Analyze how compression damaged the weight matrix."""
    print(f"\n{tensor_name}")
    print("-" * 50)

    # Basic stats
    diff = W_orig - W_cdna
    print(f"Shape: {W_orig.shape}")
    print(f"Original range: [{W_orig.min():.6f}, {W_orig.max():.6f}]")
    print(f"CDNA range:     [{W_cdna.min():.6f}, {W_cdna.max():.6f}]")
    print(f"Max abs diff:   {np.abs(diff).max():.6f}")
    print(f"Mean abs diff:  {np.abs(diff).mean():.6f}")

    # Cosine similarity (flattened)
    orig_flat = W_orig.flatten()
    cdna_flat = W_cdna.flatten()
    cosine = np.dot(orig_flat, cdna_flat) / (np.linalg.norm(orig_flat) * np.linalg.norm(cdna_flat))
    print(f"Cosine sim:     {cosine:.6f}")

    # Frobenius norm ratio
    orig_norm = np.linalg.norm(W_orig, 'fro')
    cdna_norm = np.linalg.norm(W_cdna, 'fro')
    diff_norm = np.linalg.norm(diff, 'fro')
    print(f"||W_orig||_F:   {orig_norm:.4f}")
    print(f"||W_cdna||_F:   {cdna_norm:.4f}")
    print(f"||diff||_F:     {diff_norm:.4f}")
    print(f"Rel error:      {diff_norm / orig_norm:.6f}")

    # Check if specific structure is damaged
    # Look at row-wise cosine similarity
    n_rows = min(10, W_orig.shape[0])
    print(f"\nPer-row cosine (first {n_rows} rows):")
    for i in range(n_rows):
        row_orig = W_orig[i]
        row_cdna = W_cdna[i]
        row_cos = np.dot(row_orig, row_cdna) / (np.linalg.norm(row_orig) * np.linalg.norm(row_cdna) + 1e-10)
        print(f"  Row {i}: {row_cos:.6f}")

    return {
        "tensor": tensor_name,
        "cosine": float(cosine),
        "max_diff": float(np.abs(diff).max()),
        "rel_error": float(diff_norm / orig_norm),
    }


def main():
    print("=" * 70)
    print("Q/K WEIGHT COMPARISON: GGUF vs CDNA")
    print("=" * 70)

    # Paths
    gguf_path = "/home/voidstr3m33/helix-cdc/tmp/mistral_fp8combined_canonical.gguf"
    manifest_path = "/home/voidstr3m33/helix-cdc/seeds/hybrid_manifest_v2_cdna2_fullblocks.json"

    print(f"GGUF: {gguf_path}")
    print(f"Manifest: {manifest_path}")

    # Check if GGUF exists
    if not Path(gguf_path).exists():
        print(f"\n❌ GGUF not found: {gguf_path}")
        print("Cannot compare without original weights.")
        return

    tensors_to_check = [
        "blk.0.attn_q.weight",
        "blk.0.attn_k.weight",
        "blk.0.attn_v.weight",
        "blk.0.attn_output.weight",
    ]

    results = []
    for tensor_name in tensors_to_check:
        try:
            print(f"\nLoading {tensor_name}...")
            W_orig = load_gguf_tensor(gguf_path, tensor_name)
            W_cdna = load_cdna_tensor(manifest_path, tensor_name)

            result = analyze_weight_damage(W_orig, W_cdna, tensor_name)
            results.append(result)
        except Exception as e:
            print(f"Error loading {tensor_name}: {e}")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"{'Tensor':<30} {'Cosine':>10} {'Max Diff':>12} {'Rel Error':>12}")
    print("-" * 70)
    for r in results:
        print(f"{r['tensor']:<30} {r['cosine']:>10.6f} {r['max_diff']:>12.6f} {r['rel_error']:>12.6f}")

    # Diagnosis
    print("\n" + "=" * 70)
    print("DIAGNOSIS")
    print("=" * 70)

    q_result = next((r for r in results if "attn_q" in r["tensor"]), None)
    k_result = next((r for r in results if "attn_k" in r["tensor"]), None)

    if q_result and k_result:
        if q_result["cosine"] < 0.99 or k_result["cosine"] < 0.99:
            print("\n⚠️  Q/K WEIGHTS SIGNIFICANTLY DAMAGED BY COMPRESSION")
            print(f"   Q cosine: {q_result['cosine']:.6f}")
            print(f"   K cosine: {k_result['cosine']:.6f}")
            print("\n   This explains uniform attention - the Q·K structure is broken.")
        else:
            print("\n✓ Q/K weights have high fidelity (cosine > 0.99)")
            print("   Uniform attention may have another cause.")


if __name__ == "__main__":
    main()
