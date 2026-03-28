#!/usr/bin/env python3
"""
Compare logits from original GGUF vs CDNA.

Uses HuggingFace to run the original GGUF and compares with our CDNA implementation.
"""

import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, "/home/voidstr3m33/helix-cdc")

# Check if transformers is available
try:
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import torch
    HF_AVAILABLE = True
except ImportError:
    HF_AVAILABLE = False


def run_hf_logits(prompt: str, model_path: str):
    """Get logits from HuggingFace."""
    if not HF_AVAILABLE:
        return None, None

    tokenizer = AutoTokenizer.from_pretrained(model_path)
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        torch_dtype=torch.float16,
        device_map="auto",
    )

    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        outputs = model(**inputs)
        logits = outputs.logits[0, -1, :].cpu().numpy()

    return logits, tokenizer


def run_cdna_logits(prompt: str):
    """Get logits from CDNA."""
    from cdna_server.generate import CDNAGenerator

    generator = CDNAGenerator()
    prompt_ids, _ = generator.tokenizer.encode(prompt, add_bos=True)
    logits, _ = generator._forward_with_cache(prompt_ids, None)

    return logits, generator.tokenizer


def main():
    print("=" * 70)
    print("GGUF vs CDNA LOGITS COMPARISON")
    print("=" * 70)

    prompt = "Paris is the capital of"
    print(f"Prompt: {prompt!r}")
    print()

    # Run CDNA
    print("Running CDNA forward pass...")
    cdna_logits, cdna_tokenizer = run_cdna_logits(prompt)

    print(f"CDNA logits shape: {cdna_logits.shape}")
    print(f"CDNA logits range: [{cdna_logits.min():.4f}, {cdna_logits.max():.4f}]")

    # Top-10 from CDNA
    top10_idx = np.argsort(cdna_logits)[-10:][::-1]
    print("\nCDNA Top-10:")
    for i, idx in enumerate(top10_idx):
        token = cdna_tokenizer.decode([int(idx)])
        # Handle the receipt object
        if hasattr(token, '__iter__') and not isinstance(token, str):
            token = str(token)
        print(f"  {i+1:2}. idx={idx:<6} logit={cdna_logits[idx]:.4f} token={repr(token)[:30]}")

    # Check France rank
    france_ids = []
    for test_token in ["France", " France"]:
        try:
            ids, _ = cdna_tokenizer.encode(test_token, add_bos=False)
            if ids:
                france_ids.extend(ids)
        except:
            pass

    print("\n'France' token analysis:")
    for fid in france_ids[:3]:
        logit = cdna_logits[fid]
        rank = (cdna_logits > logit).sum() + 1
        token_str = cdna_tokenizer.decode([int(fid)])
        if hasattr(token_str, '__iter__') and not isinstance(token_str, str):
            token_str = str(token_str)
        print(f"  Token ID {fid}: logit={logit:.4f}, rank={rank}")

    # Try HuggingFace if available
    if HF_AVAILABLE:
        print("\n" + "=" * 70)
        print("HUGGINGFACE COMPARISON")
        print("=" * 70)

        # Try to load the original model
        hf_model_path = "mistralai/Mistral-7B-v0.1"
        print(f"Loading HuggingFace model: {hf_model_path}")

        try:
            hf_logits, hf_tokenizer = run_hf_logits(prompt, hf_model_path)

            if hf_logits is not None:
                print(f"HF logits shape: {hf_logits.shape}")
                print(f"HF logits range: [{hf_logits.min():.4f}, {hf_logits.max():.4f}]")

                # Top-10 from HF
                top10_hf = np.argsort(hf_logits)[-10:][::-1]
                print("\nHuggingFace Top-10:")
                for i, idx in enumerate(top10_hf):
                    token = hf_tokenizer.decode([int(idx)])
                    print(f"  {i+1:2}. idx={idx:<6} logit={hf_logits[idx]:.4f} token={repr(token)[:30]}")

                # Compare
                cosine = np.dot(cdna_logits, hf_logits) / (np.linalg.norm(cdna_logits) * np.linalg.norm(hf_logits))
                max_diff = np.abs(cdna_logits - hf_logits).max()
                print(f"\nCDNA vs HF:")
                print(f"  Cosine similarity: {cosine:.6f}")
                print(f"  Max abs diff: {max_diff:.4f}")

        except Exception as e:
            print(f"Error loading HuggingFace model: {e}")
    else:
        print("\n⚠️ transformers not available for HF comparison")
        print("   Install with: pip install transformers torch")

    # Summary
    print("\n" + "=" * 70)
    print("DIAGNOSIS")
    print("=" * 70)

    # Check if top token is always "various"
    top_token_id = top10_idx[0]
    top_token = cdna_tokenizer.decode([int(top_token_id)])
    if hasattr(top_token, '__iter__') and not isinstance(top_token, str):
        top_token = str(top_token)

    if "various" in top_token.lower():
        print("\n⚠️  CDNA produces 'various' as top prediction")
        print("   This is WRONG for 'Paris is the capital of'")
        print("   Expected: 'France' should be top prediction")
        print("\n   Likely causes:")
        print("   1. Output projection (lm_head) weights damaged by compression")
        print("   2. Final hidden states collapsed to similar values")
        print("   3. FFN weights damaged causing feature collapse")
    else:
        print(f"\n✓ Top prediction: {repr(top_token)}")


if __name__ == "__main__":
    main()
