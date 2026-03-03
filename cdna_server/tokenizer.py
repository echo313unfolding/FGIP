"""
CDNA Tokenizer - Wrapper around MistralTokenizerBridge.

Stage 1 of WO-ECHO-CDNA-BACKEND-02.

This module provides tokenization for CDNA inference, wrapping
the proven helix-cdc MistralTokenizerBridge.
"""

import hashlib
from pathlib import Path
from typing import List, Optional, Tuple, Any, Dict

import numpy as np

from helix_cdc.regrow.tokenizer_bridge import (
    MistralTokenizerBridge,
    TokenizerBridgeReceipt,
    check_tokenizer_bridge_available,
)

from .model_loader import DEFAULT_GGUF_PATH


class CDNATokenizer:
    """
    Tokenizer for CDNA inference.

    Wraps MistralTokenizerBridge with:
    - Model hash for receipts
    - Simplified encode/decode API
    - Embedding lookup and logits projection
    """

    def __init__(self, gguf_path: Path = DEFAULT_GGUF_PATH):
        """
        Initialize tokenizer.

        Args:
            gguf_path: Path to GGUF file for vocabulary
        """
        self.gguf_path = Path(gguf_path).absolute()

        # Check availability
        available, msg = check_tokenizer_bridge_available()
        if not available:
            raise ImportError(f"Tokenizer bridge not available: {msg}")

        # Get bridge (singleton)
        self._bridge = MistralTokenizerBridge.get_bridge(self.gguf_path)

        # Compute model hash from GGUF file (first 1MB for speed)
        with open(self.gguf_path, "rb") as f:
            self._model_hash = hashlib.sha256(f.read(1024 * 1024)).hexdigest()[:16]

    @property
    def model_hash(self) -> str:
        """Get SHA256[:16] hash of model file for receipt fingerprinting."""
        return self._model_hash

    @property
    def vocab_size(self) -> int:
        """Get vocabulary size."""
        return self._bridge.vocab_size

    @property
    def vocab_hash(self) -> str:
        """Get vocabulary hash from bridge."""
        return self._bridge.vocab_hash

    @property
    def d_model(self) -> int:
        """Get model hidden dimension."""
        return self._bridge.d_model

    def encode(
        self,
        text: str,
        add_bos: bool = True,
    ) -> Tuple[List[int], TokenizerBridgeReceipt]:
        """
        Encode text to token IDs.

        Args:
            text: Input text
            add_bos: Whether to add BOS token

        Returns:
            (token_ids, receipt)
        """
        return self._bridge.encode(text, add_bos=add_bos)

    def decode(self, token_ids: List[int]) -> Tuple[str, TokenizerBridgeReceipt]:
        """
        Decode token IDs to text.

        Args:
            token_ids: List of token IDs

        Returns:
            (text, receipt)
        """
        return self._bridge.decode(token_ids)

    def lookup_embeddings(
        self,
        token_ids: List[int],
    ) -> Tuple[np.ndarray, TokenizerBridgeReceipt]:
        """
        Look up embeddings for token IDs.

        Args:
            token_ids: List of token IDs

        Returns:
            (embeddings [seq, d_model], receipt)
        """
        return self._bridge.lookup_embeddings(token_ids)

    def project_to_logits(
        self,
        hidden: np.ndarray,
        temperature: float = 1.0,
    ) -> Tuple[np.ndarray, TokenizerBridgeReceipt]:
        """
        Project hidden states to logits.

        Args:
            hidden: Hidden states [..., d_model]
            temperature: Temperature for scaling

        Returns:
            (logits [..., vocab_size], receipt)
        """
        return self._bridge.project_to_logits(hidden, temperature=temperature)

    def get_bos_token_id(self) -> int:
        """Get beginning-of-sequence token ID."""
        return self._bridge.get_bos_token_id()

    def get_eos_token_id(self) -> int:
        """Get end-of-sequence token ID."""
        return self._bridge.get_eos_token_id()

    def to_dict(self) -> Dict[str, Any]:
        """Convert tokenizer state to dict for receipts."""
        return {
            "gguf_path": str(self.gguf_path),
            "model_hash": self._model_hash,
            "vocab_size": self.vocab_size,
            "vocab_hash": self.vocab_hash,
            "d_model": self.d_model,
        }

    def close(self) -> None:
        """Close tokenizer and release resources."""
        if hasattr(self, '_bridge') and self._bridge is not None:
            self._bridge.close()


if __name__ == "__main__":
    print("=== CDNA Tokenizer Test ===")
    print()

    available, msg = check_tokenizer_bridge_available()
    print(f"Available: {available}")
    print(f"Message: {msg}")
    print()

    if available:
        try:
            tokenizer = CDNATokenizer()
            print(f"GGUF: {tokenizer.gguf_path}")
            print(f"Model hash: {tokenizer.model_hash}")
            print(f"Vocab size: {tokenizer.vocab_size}")
            print(f"Vocab hash: {tokenizer.vocab_hash}")
            print(f"D_model: {tokenizer.d_model}")
            print()

            # Test encode/decode
            text = "Hello, world!"
            token_ids, receipt = tokenizer.encode(text)
            print(f"Encode '{text}': {token_ids}")
            print(f"  Receipt status: {receipt.status}")

            decoded, receipt = tokenizer.decode(token_ids)
            print(f"Decode: '{decoded}'")

        except Exception as e:
            print(f"Error: {e}")
