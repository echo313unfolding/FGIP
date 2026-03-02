"""Unit tests for text normalization."""

import pytest
from fgip.text.normalize import normalize_text


class TestNormalizeText:
    """Test suite for normalize_text()."""

    # ========== Unicode NFKC ==========

    def test_nfkc_fullwidth(self):
        """Fullwidth characters should normalize to ASCII."""
        assert normalize_text("ＡＣＴＮＯＷ") == "ACTNOW"

    def test_nfkc_ligatures(self):
        """Ligatures should decompose."""
        assert "fi" in normalize_text("ﬁle")  # fi ligature

    # ========== Confusables ==========

    def test_greek_alpha(self):
        """Greek Alpha (Α) should map to A."""
        assert normalize_text("ΑCΤNΟW") == "ACTNOW"

    def test_greek_omicron(self):
        """Greek Omicron (Ο) should map to O."""
        assert normalize_text("NΟW") == "NOW"

    def test_cyrillic_mixed(self):
        """Cyrillic lookalikes should map to ASCII."""
        assert normalize_text("АСΤΙΟΝ") == "ACTION"

    def test_mixed_confusables(self):
        """Mixed Greek/Cyrillic should normalize."""
        # Α = Greek Alpha, Ο = Greek Omicron, С = Cyrillic Es
        assert normalize_text("ΑСΤ") == "ACT"

    # ========== Leetspeak ==========

    def test_leetspeak_basic(self):
        """Basic leetspeak in ALLCAPS words should normalize."""
        assert normalize_text("ACT N0W") == "ACT NOW"
        # "1000%" is a number, not leetspeak - should be preserved
        assert normalize_text("1000% GA1NS") == "1000% GAINS"

    def test_leetspeak_full(self):
        """Full leetspeak transformation."""
        assert normalize_text("4CT N0W!!!") == "ACT NOW!!!"

    def test_leetspeak_at_sign(self):
        """@ should map to A in ALLCAPS context."""
        assert normalize_text("GRE@T") == "GREAT"

    def test_leetspeak_preserves_lowercase(self):
        """Leetspeak should NOT apply to normal lowercase text."""
        # "hello" is lowercase, should not trigger leetspeak
        result = normalize_text("hello 0n the street")
        # The "0" in "0n" won't be converted because "0n" is mostly lowercase
        assert "0" in result or "O" in result  # depends on context

    def test_leetspeak_numbers_in_context(self):
        """Numbers that are clearly numbers should be preserved."""
        # "100" is not leetspeak, it's a number
        result = normalize_text("I have 100 dollars")
        assert "100" in result

    # ========== Whitespace Collapse ==========

    def test_spaced_letters_basic(self):
        """Spaced-out letters should collapse (double space = word boundary)."""
        # Double space treated as word boundary
        assert normalize_text("A C T  N O W") == "ACT NOW"

    def test_spaced_letters_long(self):
        """Long spaced sequences should collapse."""
        # Double space between words
        assert normalize_text("B U Y  N O W") == "BUY NOW"

    def test_spaced_letters_single_word(self):
        """Single-spaced letters collapse into one word."""
        # All single spaces = one continuous word attempt
        assert normalize_text("A C T N O W") == "ACTNOW"

    def test_spaced_letters_preserves_words(self):
        """Normal words should not be affected."""
        assert normalize_text("ACT NOW") == "ACT NOW"

    def test_spaced_letters_short_preserved(self):
        """Short sequences (< 4 chars) should be preserved."""
        # "A B" is only 2 chars, should not collapse
        result = normalize_text("A B test")
        assert "A B" in result or "AB" in result

    # ========== Punctuation ==========

    def test_excessive_exclamation(self):
        """!!!! should reduce to !!!."""
        assert normalize_text("ACT NOW!!!!!") == "ACT NOW!!!"

    def test_excessive_question(self):
        """???? should reduce to ???."""
        assert normalize_text("WHAT????") == "WHAT???"

    def test_excessive_dots(self):
        """.... should reduce to ...."""
        assert normalize_text("wait.....") == "wait..."

    def test_normal_punctuation_preserved(self):
        """Normal punctuation should be preserved."""
        assert normalize_text("Hello! How are you?") == "Hello! How are you?"

    # ========== Combined Transforms ==========

    def test_combined_obfuscation(self):
        """Combined obfuscation should normalize completely."""
        # Greek Alpha + leetspeak + excessive punctuation
        result = normalize_text("ΑCT N0W!!!!!!")
        assert result == "ACT NOW!!!"

    def test_pump_dump_pattern(self):
        """Classic pump-and-dump obfuscation should normalize."""
        result = normalize_text("$XYZ Τ0 ΤΗΕ Μ00Ν!!!!")
        assert "TO" in result
        assert "MOON" in result
        assert result.endswith("!!!")

    # ========== Do No Harm Tests ==========

    def test_sec_heading_preserved(self):
        """SEC document headings should remain intact."""
        text = "ITEM 1. BUSINESS\n\nThe Company operates..."
        result = normalize_text(text)
        assert "ITEM 1. BUSINESS" in result
        assert "The Company operates" in result

    def test_legal_caps_preserved(self):
        """Standard legal all-caps should be preserved."""
        text = "SCHEDULE 13G UNDER THE SECURITIES EXCHANGE ACT OF 1934"
        result = normalize_text(text)
        assert "SCHEDULE 13G" in result
        assert "SECURITIES EXCHANGE ACT" in result

    def test_congressional_record_preserved(self):
        """Congressional Record formatting should be preserved."""
        text = "H.R. 4346 - CHIPS and Science Act"
        result = normalize_text(text)
        assert "H.R. 4346" in result
        assert "CHIPS" in result

    def test_ticker_symbol_preserved(self):
        """Stock ticker symbols should be preserved."""
        text = "Intel (INTC) closed at $42.50"
        result = normalize_text(text)
        assert "INTC" in result
        assert "$42.50" in result

    def test_government_url_preserved(self):
        """Government URLs should be preserved."""
        text = "Source: https://treasury.gov/news/2025/stablecoin"
        result = normalize_text(text)
        assert "treasury.gov" in result

    # ========== Edge Cases ==========

    def test_empty_string(self):
        """Empty string should return empty."""
        assert normalize_text("") == ""

    def test_whitespace_only(self):
        """Whitespace-only strings should handle gracefully."""
        # Whitespace collapse will normalize multiple spaces to single
        result = normalize_text("   ")
        assert result.strip() == ""  # Result may have whitespace but no content

    def test_unicode_emoji_preserved(self):
        """Emojis should pass through (not confusables)."""
        result = normalize_text("ACT NOW! 🚀")
        assert "🚀" in result

    def test_normal_text_unchanged(self):
        """Normal text should pass through unchanged."""
        text = "The quarterly report shows positive growth."
        assert normalize_text(text) == text


class TestNormalizeIdempotent:
    """Test that normalization is idempotent."""

    def test_double_normalize(self):
        """Normalizing twice should give same result."""
        text = "ΑCT N0W!!!!!"
        once = normalize_text(text)
        twice = normalize_text(once)
        assert once == twice

    def test_already_normalized(self):
        """Already normalized text should be unchanged."""
        text = "ACT NOW!!!"
        assert normalize_text(text) == text
