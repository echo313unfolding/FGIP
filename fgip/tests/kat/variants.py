"""Deterministic Variant Generator for KAT Adversarial Tests.

Generates N=5 deterministic variants from adversarial test cases using
seeded transforms for reproducibility.

Usage:
    from fgip.tests.kat.variants import expand_with_variants

    cases = load_test_cases(adversarial_file)
    expanded = expand_with_variants(cases)  # 9 base → ~45 total
"""

import hashlib
import random
import re
from typing import List, Optional

from . import TestCase


# Unicode confusables (deterministic small set)
CONFUSABLES = {
    'A': 'Α',  # Greek Alpha
    'B': 'Β',  # Greek Beta
    'E': 'Ε',  # Greek Epsilon
    'H': 'Η',  # Greek Eta
    'I': 'Ι',  # Greek Iota
    'K': 'Κ',  # Greek Kappa
    'M': 'Μ',  # Greek Mu
    'N': 'Ν',  # Greek Nu
    'O': 'Ο',  # Greek Omicron
    'P': 'Ρ',  # Greek Rho
    'T': 'Τ',  # Greek Tau
    'X': 'Χ',  # Greek Chi
    'Y': 'Υ',  # Greek Upsilon
    'Z': 'Ζ',  # Greek Zeta
}

# Leetspeak substitutions
LEETSPEAK = {
    'A': '4',
    'E': '3',
    'I': '1',
    'O': '0',
    'S': '5',
    'T': '7',
}


def _seed_from_case_id(case_id: str) -> int:
    """Generate deterministic seed from case ID."""
    return int(hashlib.md5(case_id.encode()).hexdigest()[:8], 16)


def transform_reduce_caps(content: str, seed: int) -> str:
    """Reduce some uppercase letters to lowercase (makes detection harder)."""
    rng = random.Random(seed)
    chars = list(content)
    for i, c in enumerate(chars):
        if c.isupper() and rng.random() < 0.3:
            chars[i] = c.lower()
    return ''.join(chars)


def transform_increase_caps(content: str, seed: int) -> str:
    """Increase uppercase letters (makes detection easier, tests thresholds)."""
    rng = random.Random(seed)
    chars = list(content)
    for i, c in enumerate(chars):
        if c.islower() and rng.random() < 0.4:
            chars[i] = c.upper()
    return ''.join(chars)


def transform_punctuation_reduce(content: str, seed: int) -> str:
    """Reduce excessive punctuation (!!! → !!)."""
    # Reduce runs of 3+ to 2
    result = re.sub(r'!{3,}', '!!', content)
    result = re.sub(r'\?{3,}', '??', result)
    return result


def transform_punctuation_increase(content: str, seed: int) -> str:
    """Increase punctuation (! → !!!)."""
    result = re.sub(r'!+', '!!!', content)
    result = re.sub(r'\?+', '???', result)
    return result


def transform_whitespace_split(content: str, seed: int) -> str:
    """Split some words with spaces (ACT NOW → A C T  N O W)."""
    rng = random.Random(seed)
    words = content.split()
    result = []
    for word in words:
        if word.isupper() and len(word) >= 3 and rng.random() < 0.3:
            # Split the word: ACT → A C T
            result.append(' '.join(word))
        else:
            result.append(word)
    return ' '.join(result)


def transform_unicode_confusables(content: str, seed: int) -> str:
    """Replace some characters with Unicode confusables."""
    rng = random.Random(seed)
    chars = list(content)
    for i, c in enumerate(chars):
        if c.upper() in CONFUSABLES and rng.random() < 0.25:
            chars[i] = CONFUSABLES[c.upper()]
    return ''.join(chars)


def transform_leetspeak(content: str, seed: int) -> str:
    """Apply leetspeak substitutions (O→0, I→1, E→3)."""
    rng = random.Random(seed)
    chars = list(content)
    for i, c in enumerate(chars):
        if c.upper() in LEETSPEAK and rng.random() < 0.3:
            chars[i] = LEETSPEAK[c.upper()]
    return ''.join(chars)


# Transform registry
TRANSFORMS = [
    ("caps-reduce", transform_reduce_caps),
    ("caps-increase", transform_increase_caps),
    ("punct-reduce", transform_punctuation_reduce),
    ("punct-increase", transform_punctuation_increase),
    ("whitespace", transform_whitespace_split),
    ("unicode", transform_unicode_confusables),
    ("leetspeak", transform_leetspeak),
]

# Transforms that should be neutralized by normalization
# If these fail, it's a regression (normalization should handle them)
NORMALIZABLE_TRANSFORMS = {
    "whitespace",
    "unicode",
    "leetspeak",
    "punct-reduce",
    "punct-increase",
}

# Transforms that are expected limitations (normalization can't fully handle)
# caps-reduce/increase change the actual caps ratio, not just obfuscation
EXPECTED_LIMITATION_TRANSFORMS = {
    "caps-reduce",
    "caps-increase",
}


def generate_variants(
    case: TestCase,
    n_variants: int = 5,
    seed: Optional[int] = None
) -> List[TestCase]:
    """Generate N deterministic variants from a test case.

    Args:
        case: Base test case to generate variants from
        n_variants: Number of variants to generate (default 5)
        seed: Optional override seed (defaults to hash of case.id)

    Returns:
        List of variant TestCase objects (does NOT include original)
    """
    if seed is None:
        seed = _seed_from_case_id(case.id)

    if not case.artifact_content:
        return []

    # Only generate variants for adversarial cases (not positive/benign)
    if case.category not in ("adversarial_filter", "adversarial"):
        return []

    variants = []
    rng = random.Random(seed)

    # Select which transforms to apply
    selected = rng.sample(TRANSFORMS, min(n_variants, len(TRANSFORMS)))

    for idx, (transform_name, transform_fn) in enumerate(selected):
        variant_seed = seed + idx + 1

        new_content = transform_fn(case.artifact_content, variant_seed)

        # Skip if transform had no effect
        if new_content == case.artifact_content:
            continue

        # Determine if this transform is an expected limitation
        is_expected_limitation = transform_name in EXPECTED_LIMITATION_TRANSFORMS

        variant = TestCase(
            id=f"{case.id}-v{idx+1}-{transform_name}",
            type=case.type,
            description=f"[Variant: {transform_name}] {case.description}",
            category=case.category,
            query=case.query,
            artifact_content=new_content,
            expected=case.expected,
            expected_integrity_below=case.expected_integrity_below,
            expected_flags=case.expected_flags,  # Inherit expected flags
            source_url=case.source_url,
            agent=case.agent,
            metadata={
                "variant_transform": transform_name,
                "expected_limitation": is_expected_limitation,
                "base_case_id": case.id,
            },
        )
        variants.append(variant)

    return variants


def expand_with_variants(
    cases: List[TestCase],
    n_variants: int = 5
) -> List[TestCase]:
    """Expand a list of test cases with their variants.

    Returns original cases + generated variants for adversarial cases.
    Non-adversarial cases are returned as-is without variants.

    Args:
        cases: List of test cases
        n_variants: Number of variants per adversarial case

    Returns:
        Expanded list with base cases + variants
    """
    expanded = []
    for case in cases:
        expanded.append(case)
        variants = generate_variants(case, n_variants)
        expanded.extend(variants)
    return expanded


__all__ = [
    "generate_variants",
    "expand_with_variants",
    "TRANSFORMS",
    "NORMALIZABLE_TRANSFORMS",
    "EXPECTED_LIMITATION_TRANSFORMS",
]
