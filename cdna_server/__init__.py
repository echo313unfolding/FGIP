"""CDNA Server - OpenAI-compatible inference backed by CDNA.

Stage 0: Stub server proving wiring works.
Stage 1: Real CDNA forward pass with HF oracle verification.

Modules:
- app.py: FastAPI server with OpenAI-compatible endpoints
- model_loader.py: Load and verify CDNA shard manifest
- tokenizer.py: Tokenization via MistralTokenizerBridge
- cdna_forward.py: Full forward pass through CDNA model
- verify_stage1.py: Stage 1 acceptance gate
"""

from .model_loader import CDNAModelLoader, DEFAULT_MANIFEST_PATH, DEFAULT_GGUF_PATH
from .tokenizer import CDNATokenizer
from .cdna_forward import cdna_forward_pass, cdna_forward_topk, CDNAForwardReceipt

__all__ = [
    "CDNAModelLoader",
    "CDNATokenizer",
    "cdna_forward_pass",
    "cdna_forward_topk",
    "CDNAForwardReceipt",
    "DEFAULT_MANIFEST_PATH",
    "DEFAULT_GGUF_PATH",
]
