"""
CDNA Forward Pass - Full forward pass through CDNA model.

Stage 1 of WO-ECHO-CDNA-BACKEND-02.

This module implements the full forward pass using proven helix-cdc primitives:
1. Token embedding lookup
2. 32 transformer blocks (streaming from CDNA)
3. Final norm + LM head projection

Pipeline:
    Text "Hello"
        ↓ tokenizer.encode()
    Token IDs [1, 15043, ...]
        ↓ tokenizer.lookup_embeddings()
    Embeddings X [seq, 4096]
        ↓ cdna_forward_pass() → stream_multi_block_forward()
    Hidden states [seq, 4096]
        ↓ tokenizer.project_to_logits()
    Logits [vocab_size]
        ↓ argmax
    Next token ID
"""

import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from helix_cdc.regrow.stream_transformer_block import (
    stream_multi_block_forward,
    TransformerBlockReceipt,
)
from helix_cdc.regrow.stream_xw_matmul import VerifyPolicy

from .model_loader import CDNAModelLoader, DEFAULT_MANIFEST_PATH, DEFAULT_GGUF_PATH
from .tokenizer import CDNATokenizer


# Architecture constants (Mistral 7B)
N_LAYERS = 32
D_HEAD = 128


@dataclass
class CDNAForwardReceipt:
    """
    Receipt for CDNA forward pass.

    Contains all fingerprints needed for verification:
    - manifest_hash: SHA256[:16] of CDNA manifest
    - tokenizer_hash: SHA256[:16] of tokenizer model
    - inputs_hash: SHA256[:16] of input text
    - outputs_hash: SHA256[:16] of output logits
    - block_receipts: Per-block receipts (optional)
    """

    schema: str = "cdna_forward_receipt_v1"
    work_order: str = "WO-ECHO-CDNA-BACKEND-02"

    # Input info
    prompt: str = ""
    token_ids: List[int] = field(default_factory=list)
    token_count: int = 0
    inputs_hash: str = ""

    # Model info
    manifest_hash: str = ""
    tokenizer_hash: str = ""
    gguf_path: str = ""

    # Output info
    logits_shape: List[int] = field(default_factory=list)
    outputs_hash: str = ""
    top5_token_ids: List[int] = field(default_factory=list)
    top5_logits: List[float] = field(default_factory=list)

    # Timing
    embed_ms: float = 0.0
    blocks_ms: float = 0.0
    lm_head_ms: float = 0.0
    total_ms: float = 0.0

    # Block receipts (optional - can be large)
    block_receipts: Optional[List[Dict[str, Any]]] = None

    # Status
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    status: str = "PASS"
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        d = {
            "schema": self.schema,
            "work_order": self.work_order,
            "prompt": self.prompt,
            "token_ids": self.token_ids,
            "token_count": self.token_count,
            "inputs_hash": self.inputs_hash,
            "manifest_hash": self.manifest_hash,
            "tokenizer_hash": self.tokenizer_hash,
            "gguf_path": self.gguf_path,
            "logits_shape": self.logits_shape,
            "outputs_hash": self.outputs_hash,
            "top5_token_ids": self.top5_token_ids,
            "top5_logits": self.top5_logits,
            "timing": {
                "embed_ms": round(self.embed_ms, 2),
                "blocks_ms": round(self.blocks_ms, 2),
                "lm_head_ms": round(self.lm_head_ms, 2),
                "total_ms": round(self.total_ms, 2),
            },
            "timestamp": self.timestamp,
            "status": self.status,
        }

        if self.block_receipts is not None:
            d["block_receipts"] = self.block_receipts

        if self.error_message is not None:
            d["error_message"] = self.error_message

        return d


def _hash_array(arr: np.ndarray) -> str:
    """Compute SHA256[:16] hash of numpy array."""
    return hashlib.sha256(arr.astype(np.float32).tobytes()).hexdigest()[:16]


def _hash_text(text: str) -> str:
    """Compute SHA256[:16] hash of text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def cdna_forward_pass(
    prompt: str,
    model_loader: Optional[CDNAModelLoader] = None,
    tokenizer: Optional[CDNATokenizer] = None,
    verify_policy: VerifyPolicy = "trust_cached",
    include_block_receipts: bool = False,
) -> Tuple[np.ndarray, CDNAForwardReceipt]:
    """
    Full forward pass through CDNA model.

    Args:
        prompt: Input text
        model_loader: CDNAModelLoader instance (created if None)
        tokenizer: CDNATokenizer instance (created if None)
        verify_policy: Block verification policy
        include_block_receipts: Whether to include per-block receipts

    Returns:
        (logits [vocab_size], receipt)

    The logits are for the LAST token position.
    """
    t0_total = time.perf_counter()

    # Initialize components if not provided
    if model_loader is None:
        model_loader = CDNAModelLoader()
    if tokenizer is None:
        tokenizer = CDNATokenizer()

    receipt = CDNAForwardReceipt(
        prompt=prompt,
        inputs_hash=_hash_text(prompt),
        manifest_hash=model_loader.manifest_hash,
        tokenizer_hash=tokenizer.model_hash,
        gguf_path=str(model_loader.gguf_path),
    )

    try:
        # Step 1: Tokenize and embed
        t0 = time.perf_counter()
        token_ids, _ = tokenizer.encode(prompt, add_bos=True)
        embeddings, _ = tokenizer.lookup_embeddings(token_ids)

        # Reshape to [batch, seq, d_model]
        X = embeddings.reshape(1, len(token_ids), -1).astype(np.float32)
        receipt.embed_ms = (time.perf_counter() - t0) * 1000

        receipt.token_ids = list(token_ids)
        receipt.token_count = len(token_ids)

        # Step 2: Run 32 transformer blocks
        t0 = time.perf_counter()
        block_indices = list(range(N_LAYERS))

        hidden, block_receipts_list, _ = stream_multi_block_forward(
            X,
            manifest_path=model_loader.manifest_path,
            block_indices=block_indices,
            d_head=D_HEAD,
            verify_policy=verify_policy,
            gguf_path=model_loader.gguf_path,
        )
        receipt.blocks_ms = (time.perf_counter() - t0) * 1000

        if include_block_receipts:
            receipt.block_receipts = [r.to_dict() for r in block_receipts_list]

        # Step 3: Project to logits
        t0 = time.perf_counter()

        # Get last token hidden state
        if hidden.ndim == 3:
            last_hidden = hidden[0, -1, :]  # [d_model]
        else:
            last_hidden = hidden[-1, :]  # [d_model]

        logits, _ = tokenizer.project_to_logits(last_hidden)
        receipt.lm_head_ms = (time.perf_counter() - t0) * 1000

        # Get top-5
        top5_idx = np.argsort(logits)[-5:][::-1]
        top5_logits = logits[top5_idx]

        receipt.logits_shape = list(logits.shape)
        receipt.outputs_hash = _hash_array(logits)
        receipt.top5_token_ids = [int(i) for i in top5_idx]
        receipt.top5_logits = [float(l) for l in top5_logits]

        receipt.total_ms = (time.perf_counter() - t0_total) * 1000
        receipt.status = "PASS"

        return logits, receipt

    except Exception as e:
        receipt.total_ms = (time.perf_counter() - t0_total) * 1000
        receipt.status = "FAIL"
        receipt.error_message = str(e)
        return np.array([]), receipt


def cdna_forward_topk(
    prompt: str,
    k: int = 5,
    model_loader: Optional[CDNAModelLoader] = None,
    tokenizer: Optional[CDNATokenizer] = None,
) -> Tuple[List[Tuple[int, float, str]], CDNAForwardReceipt]:
    """
    Forward pass returning top-k tokens with decoded text.

    Args:
        prompt: Input text
        k: Number of top tokens to return
        model_loader: CDNAModelLoader instance
        tokenizer: CDNATokenizer instance

    Returns:
        ([(token_id, logit, decoded_text), ...], receipt)
    """
    if model_loader is None:
        model_loader = CDNAModelLoader()
    if tokenizer is None:
        tokenizer = CDNATokenizer()

    logits, receipt = cdna_forward_pass(
        prompt,
        model_loader=model_loader,
        tokenizer=tokenizer,
    )

    if receipt.status != "PASS":
        return [], receipt

    # Get top-k
    topk_idx = np.argsort(logits)[-k:][::-1]
    topk_logits = logits[topk_idx]

    # Decode each token
    results = []
    for idx, logit in zip(topk_idx, topk_logits):
        try:
            decoded, _ = tokenizer.decode([int(idx)])
        except Exception:
            decoded = f"<{idx}>"
        results.append((int(idx), float(logit), decoded))

    return results, receipt


if __name__ == "__main__":
    import sys

    print("=== CDNA Forward Pass Test ===")
    print()

    prompt = "Paris is the capital of"
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])

    print(f"Prompt: '{prompt}'")
    print()

    try:
        topk, receipt = cdna_forward_topk(prompt)

        print(f"Status: {receipt.status}")
        print(f"Tokens: {receipt.token_ids} (count={receipt.token_count})")
        print(f"Timing: embed={receipt.embed_ms:.1f}ms, blocks={receipt.blocks_ms:.1f}ms, lm_head={receipt.lm_head_ms:.1f}ms, total={receipt.total_ms:.1f}ms")
        print()

        print("Top-5 predictions:")
        for i, (token_id, logit, text) in enumerate(topk):
            print(f"  {i+1}. [{token_id}] {text!r} (logit={logit:.2f})")

        print()
        print(f"Manifest hash: {receipt.manifest_hash}")
        print(f"Tokenizer hash: {receipt.tokenizer_hash}")
        print(f"Outputs hash: {receipt.outputs_hash}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
