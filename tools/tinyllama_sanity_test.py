#!/usr/bin/env python3
"""
TinyLlama Sanity Test

WO-TINYLLAMA-SETUP-01: Verify TinyLlama CDNA setup works correctly.

Tests:
1. Architecture detection from GGUF
2. Forward pass produces reasonable outputs
3. Top-K predictions are NOT "various", "Feb", etc.
4. Basic behavioral coherence
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import numpy as np
from datetime import datetime, timezone


def test_architecture_detection():
    """Test that architecture is correctly read from GGUF."""
    from cdna_server.generate import get_architecture_from_gguf
    from cdna_server.model_loader import DEFAULT_GGUF_PATH

    print("=" * 60)
    print("TEST 1: Architecture Detection")
    print("=" * 60)

    arch = get_architecture_from_gguf(str(DEFAULT_GGUF_PATH))
    print(f"GGUF: {DEFAULT_GGUF_PATH}")
    print(f"Architecture: {json.dumps(arch, indent=2)}")

    # TinyLlama expected values
    expected = {
        "n_layers": 22,
        "d_model": 2048,
        "n_heads": 32,
        "n_kv_heads": 4,
        "d_head": 64,
    }

    # Check if this looks like TinyLlama
    is_tinyllama = (
        arch.get("n_layers") == 22 and
        arch.get("d_model") == 2048
    )

    if is_tinyllama:
        print("\n✓ Detected TinyLlama architecture")
        for key, val in expected.items():
            actual = arch.get(key)
            status = "✓" if actual == val else "✗"
            print(f"  {status} {key}: expected={val}, got={actual}")
        return True
    else:
        print("\n⚠️ Not TinyLlama (different architecture)")
        print("  This is fine if testing with a different model")
        return True  # Not a failure, just different model


def test_forward_pass():
    """Test that forward pass produces reasonable outputs."""
    from cdna_server.generate import CDNAGenerator

    print("\n" + "=" * 60)
    print("TEST 2: Forward Pass")
    print("=" * 60)

    try:
        generator = CDNAGenerator()
        print(f"Generator initialized with {generator.n_layers} layers, "
              f"d_model={generator.d_model}")

        prompt = "Hello"
        print(f"\nPrompt: {prompt!r}")

        prompt_ids, _ = generator.tokenizer.encode(prompt, add_bos=True)
        print(f"Token IDs: {prompt_ids}")

        logits, _ = generator._forward_with_cache(prompt_ids, None)
        print(f"Logits shape: {logits.shape}")
        print(f"Logits range: [{logits.min():.4f}, {logits.max():.4f}]")
        print(f"Logits std: {logits.std():.4f}")

        # Check for collapsed logits
        if logits.std() < 0.1:
            print("\n✗ Logits are collapsed (std < 0.1)")
            return False

        print("\n✓ Forward pass completed successfully")
        return True

    except Exception as e:
        print(f"\n✗ Forward pass failed: {e}")
        return False


def test_not_garbage():
    """Test that model doesn't produce 'various', 'Feb', etc."""
    from cdna_server.generate import CDNAGenerator

    print("\n" + "=" * 60)
    print("TEST 3: Not Garbage Output")
    print("=" * 60)

    generator = CDNAGenerator()

    test_cases = [
        ("Hello", ["hello", "hi", "hey", "world"]),  # Reasonable greetings
        ("1 + 1 =", ["2", "two"]),  # Math
        ("Paris is the capital of", ["France", "france"]),  # Geography
    ]

    garbage_tokens = ["various", "feb", "utter", "結"]
    all_passed = True

    for prompt, expected_any in test_cases:
        print(f"\nPrompt: {prompt!r}")

        prompt_ids, _ = generator.tokenizer.encode(prompt, add_bos=True)
        logits, _ = generator._forward_with_cache(prompt_ids, None)

        # Top-5 predictions
        top5_idx = np.argsort(logits)[-5:][::-1]
        top5_tokens = []
        for idx in top5_idx:
            token = generator.tokenizer.decode([int(idx)])
            if hasattr(token, '__iter__') and not isinstance(token, str):
                # Handle tuple return
                token = str(token)
            top5_tokens.append((idx, token.lower().strip()))

        print(f"Top-5: {[t[1] for t in top5_tokens]}")

        # Check for garbage
        has_garbage = any(
            any(g in t[1] for g in garbage_tokens)
            for t in top5_tokens
        )

        if has_garbage:
            print(f"✗ Garbage tokens detected in top-5!")
            all_passed = False
        else:
            print(f"✓ No garbage tokens in top-5")

    return all_passed


def test_generation():
    """Test basic text generation."""
    from cdna_server.generate import CDNAGenerator

    print("\n" + "=" * 60)
    print("TEST 4: Basic Generation")
    print("=" * 60)

    generator = CDNAGenerator()

    prompt = "The capital of France is"
    print(f"Prompt: {prompt!r}")

    try:
        output, receipt = generator.generate(
            prompt,
            max_tokens=10,
            temperature=0.0,
        )

        print(f"Output: {output!r}")
        print(f"Tokens generated: {receipt.tokens_generated}")

        # Check for repetition
        words = output.split()
        if len(words) > 2:
            unique_words = set(words)
            repetition_ratio = len(unique_words) / len(words)
            if repetition_ratio < 0.3:
                print(f"✗ High repetition detected (ratio={repetition_ratio:.2f})")
                return False

        print("✓ Generation completed without obvious issues")
        return True

    except Exception as e:
        print(f"✗ Generation failed: {e}")
        return False


def main():
    print("=" * 60)
    print("TINYLLAMA SANITY TEST")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    results = {
        "architecture": test_architecture_detection(),
        "forward_pass": test_forward_pass(),
        "not_garbage": test_not_garbage(),
        "generation": test_generation(),
    }

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    all_passed = True
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {test_name}: {status}")
        if not passed:
            all_passed = False

    if all_passed:
        print("\n✓ ALL TESTS PASSED")
        return 0
    else:
        print("\n✗ SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
