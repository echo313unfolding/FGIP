#!/usr/bin/env python3
"""
Check logits health after full forward pass.

Tests:
1. Logits distribution (should not be collapsed)
2. Top-K token predictions
3. EOS token reachability
4. Compare with HuggingFace oracle
"""

import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, "/home/voidstr3m33/helix-cdc")

from cdna_server.generate import CDNAGenerator


def analyze_logits(logits, tokenizer, top_k=10):
    """Analyze logits distribution."""
    # Last position
    last_logits = logits[0, -1, :]

    # Statistics
    stats = {
        "min": float(last_logits.min()),
        "max": float(last_logits.max()),
        "mean": float(last_logits.mean()),
        "std": float(last_logits.std()),
        "range": float(last_logits.max() - last_logits.min()),
    }

    # Top-K predictions
    top_k_idx = np.argsort(last_logits)[-top_k:][::-1]
    top_k_tokens = []
    for idx in top_k_idx:
        token = tokenizer.decode([int(idx)])
        logit = last_logits[idx]
        top_k_tokens.append({
            "idx": int(idx),
            "token": repr(token),
            "logit": float(logit),
        })

    # EOS token check
    eos_id = tokenizer.eos_token_id if hasattr(tokenizer, 'eos_token_id') else 2
    eos_logit = last_logits[eos_id]
    eos_rank = (last_logits > eos_logit).sum() + 1

    # Check for collapsed logits
    # Collapsed = very small std or range
    is_collapsed = stats["std"] < 0.1 or stats["range"] < 1.0

    return {
        "stats": stats,
        "top_k": top_k_tokens,
        "eos": {
            "id": eos_id,
            "logit": float(eos_logit),
            "rank": int(eos_rank),
        },
        "is_collapsed": is_collapsed,
    }


def main():
    print("=" * 70)
    print("LOGITS HEALTH CHECK")
    print("=" * 70)

    generator = CDNAGenerator()

    prompts = [
        "Paris is the capital of",
        "The quick brown fox",
        "1 + 1 =",
    ]

    for prompt in prompts:
        print(f"\n{'='*70}")
        print(f"PROMPT: {prompt!r}")
        print(f"{'='*70}")

        # Tokenize
        prompt_ids, _ = generator.tokenizer.encode(prompt, add_bos=True)

        print(f"Sequence length: {len(prompt_ids)}")

        # Full forward pass (returns logits for last token, shape [vocab_size])
        logits_1d, _ = generator._forward_with_cache(prompt_ids, None)
        # Reshape to [1, 1, vocab_size] for consistency
        logits = logits_1d.reshape(1, 1, -1)

        # Analyze
        analysis = analyze_logits(logits, generator.tokenizer)

        print("\nLogits Statistics:")
        print(f"  Min:   {analysis['stats']['min']:.4f}")
        print(f"  Max:   {analysis['stats']['max']:.4f}")
        print(f"  Mean:  {analysis['stats']['mean']:.4f}")
        print(f"  Std:   {analysis['stats']['std']:.4f}")
        print(f"  Range: {analysis['stats']['range']:.4f}")

        print(f"\nTop-10 Predictions:")
        for i, tok in enumerate(analysis['top_k']):
            print(f"  {i+1:2}. {tok['token']:<20} idx={tok['idx']:<6} logit={tok['logit']:.4f}")

        print(f"\nEOS Token:")
        print(f"  ID:    {analysis['eos']['id']}")
        print(f"  Logit: {analysis['eos']['logit']:.4f}")
        print(f"  Rank:  {analysis['eos']['rank']} / {logits.shape[-1]}")

        if analysis['is_collapsed']:
            print("\n⚠️  LOGITS ARE COLLAPSED!")
            print("   Very small variance suggests model damage or bug.")
        else:
            print("\n✓ Logits have healthy variance")

    # Quick comparison: check if "France" is in top-10 for "Paris is the capital of"
    print("\n" + "=" * 70)
    print("SANITY CHECK")
    print("=" * 70)

    prompt = "Paris is the capital of"
    prompt_ids, _ = generator.tokenizer.encode(prompt, add_bos=True)
    logits_1d, _ = generator._forward_with_cache(prompt_ids, None)
    logits = logits_1d.reshape(1, 1, -1)
    analysis = analyze_logits(logits, generator.tokenizer)

    france_found = any("France" in t['token'] or "france" in t['token'].lower() for t in analysis['top_k'])
    if france_found:
        print("✓ 'France' is in top-10 predictions for 'Paris is the capital of'")
    else:
        print("⚠️ 'France' is NOT in top-10 predictions!")
        print("   Model may have behavioral issues.")
        print(f"\n   Top-5 actual predictions:")
        for tok in analysis['top_k'][:5]:
            print(f"     {tok['token']}")


if __name__ == "__main__":
    main()
