"""Deterministic Text Canonicalization for Pattern Detection.

Provides normalize_text() which applies a sequence of deterministic
transforms to neutralize common obfuscation techniques while preserving
semantic meaning for legitimate content.

Usage:
    from fgip.text.normalize import normalize_text

    normalized = normalize_text("ACT N0W!!! Α GREΑΤ 0PP0RTUN1TY!!!")
    # Returns: "ACT NOW!!! A GREAT OPPORTUNITY!!!"
"""

import re
import unicodedata
from typing import Dict


# Greek/Cyrillic lookalikes commonly used for obfuscation
# Maps visually similar Unicode characters to ASCII equivalents
CONFUSABLES: Dict[str, str] = {
    # Greek capitals
    'Α': 'A',  # Alpha
    'Β': 'B',  # Beta
    'Ε': 'E',  # Epsilon
    'Ζ': 'Z',  # Zeta
    'Η': 'H',  # Eta
    'Ι': 'I',  # Iota
    'Κ': 'K',  # Kappa
    'Μ': 'M',  # Mu
    'Ν': 'N',  # Nu
    'Ο': 'O',  # Omicron
    'Ρ': 'P',  # Rho
    'Τ': 'T',  # Tau
    'Υ': 'Y',  # Upsilon
    'Χ': 'X',  # Chi
    # Greek lowercase
    'α': 'a',
    'ο': 'o',
    'ι': 'i',
    # Cyrillic capitals
    'А': 'A',
    'В': 'B',
    'С': 'C',
    'Е': 'E',
    'Н': 'H',
    'К': 'K',
    'М': 'M',
    'О': 'O',
    'Р': 'P',
    'Т': 'T',
    'Х': 'X',
    # Cyrillic lowercase
    'а': 'a',
    'с': 'c',
    'е': 'e',
    'о': 'o',
    'р': 'p',
    'х': 'x',
}

# Leetspeak substitutions
# Only applied to words that look like they're trying to be all-caps
LEETSPEAK: Dict[str, str] = {
    '0': 'O',
    '1': 'I',
    '3': 'E',
    '4': 'A',
    '5': 'S',
    '7': 'T',
    '@': 'A',
}


def _apply_confusables(text: str) -> str:
    """Replace Unicode confusables with ASCII equivalents."""
    result = []
    for char in text:
        result.append(CONFUSABLES.get(char, char))
    return ''.join(result)


def _apply_leetspeak(text: str) -> str:
    """Apply leetspeak folding to words that look like ALLCAPS attempts.

    Only converts leetspeak in tokens where:
    - Token contains uppercase letters or leetspeak chars
    - Token looks like it's trying to be all-caps (mostly upper + leet)
    - Token is NOT a regulatory/form identifier (e.g., "13G", "10-K")

    Preserves original whitespace structure.
    """
    # Pattern for regulatory identifiers that should NOT be leetspeak-folded
    # Matches: 13G, 10-K, 8-K, 10-Q, etc. (2+ digits, or digit-dash-letter patterns)
    # Single digit + letters like "4CT" is likely leetspeak, not a form number
    regulatory_pattern = re.compile(r'^(\d{2,}[A-Za-z]+|\d+-[A-Za-z]+)$')

    def convert_word(match):
        word = match.group(0)

        # Skip regulatory form numbers
        if regulatory_pattern.match(word):
            return word

        # Check if word looks like an all-caps attempt with leetspeak
        upper_count = sum(1 for c in word if c.isupper())
        leet_count = sum(1 for c in word if c in LEETSPEAK)
        alpha_count = sum(1 for c in word if c.isalpha())

        # If word has leetspeak chars and is mostly uppercase/leet
        # Require at least 1 alpha char and word length >= 2
        if leet_count > 0 and alpha_count >= 1 and len(word) >= 2:
            upper_leet_ratio = (upper_count + leet_count) / (alpha_count + leet_count)
            if upper_leet_ratio >= 0.5:
                # Convert leetspeak to letters
                converted = []
                for char in word:
                    converted.append(LEETSPEAK.get(char, char))
                return ''.join(converted)

        return word

    # Match word-like tokens (letters, digits, and common punctuation attached to words)
    # This preserves whitespace between words
    return re.sub(r'\S+', convert_word, text)


def _collapse_spaced_letters(text: str) -> str:
    """Collapse spaced-out letters like 'A C T  N O W' to 'ACT NOW'.

    Detects sequences of single characters separated by single spaces
    and joins them. Sequences separated by 2+ spaces are treated as
    word boundaries.

    Examples:
        "A C T  N O W" -> "ACT NOW" (double space = word boundary)
        "A C T N O W" -> "ACTNOW" (single spaces = one word attempt)
        "A C T" -> "ACT" (3+ chars = collapse)
    """
    # First, normalize multiple spaces to detect word boundaries
    # Split on 2+ spaces to find word groups
    word_groups = re.split(r'\s{2,}', text)

    result_groups = []
    for group in word_groups:
        # Within each group, collapse single-spaced letters
        # Pattern: sequence of single letters separated by single spaces
        # Must be 3+ letters to collapse
        collapsed = re.sub(
            r'\b([A-Za-z])( [A-Za-z]){2,}\b',
            lambda m: m.group(0).replace(' ', ''),
            group
        )
        result_groups.append(collapsed)

    # Rejoin with single space (the original separator intent)
    return ' '.join(result_groups)


def _normalize_punctuation(text: str) -> str:
    """Normalize excessive punctuation runs.

    Reduces runs of !, ?, . to maximum length of 3.
    """
    # Reduce !!!! to !!!
    text = re.sub(r'!{4,}', '!!!', text)
    # Reduce ???? to ???
    text = re.sub(r'\?{4,}', '???', text)
    # Reduce .... to ...
    text = re.sub(r'\.{4,}', '...', text)
    return text


def normalize_text(text: str) -> str:
    """Apply deterministic text canonicalization.

    Transforms (in order):
    1. Unicode NFKC normalization (compatibility decomposition)
    2. Confusables mapping (Greek/Cyrillic lookalikes → ASCII)
    3. Leetspeak folding (0→O, 1→I, etc.) for ALLCAPS-ish words
    4. Whitespace collapse (spaced-out letters → joined)
    5. Punctuation normalization (!!!!! → !!!)

    Args:
        text: Input text to normalize

    Returns:
        Normalized text suitable for pattern detection
    """
    if not text:
        return text

    # Step 1: Unicode NFKC normalization
    # This handles things like fullwidth characters, ligatures, etc.
    result = unicodedata.normalize('NFKC', text)

    # Step 2: Map confusables to ASCII
    result = _apply_confusables(result)

    # Step 3: Fold leetspeak in ALLCAPS-ish tokens
    result = _apply_leetspeak(result)

    # Step 4: Collapse spaced-out letters
    result = _collapse_spaced_letters(result)

    # Step 5: Normalize punctuation
    result = _normalize_punctuation(result)

    return result


__all__ = ["normalize_text"]
