"""
CDNA Model Loader - Load manifest and verify SHA256s.

Stage 1 of WO-ECHO-CDNA-BACKEND-02.

This module loads the CDNA shard manifest and provides weight access
for the forward pass. It wraps the proven helix-cdc primitives.
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional

# Paths - relative to helix-cdc root
HELIX_CDC_ROOT = Path.home() / "helix-cdc"
DEFAULT_MANIFEST_PATH = HELIX_CDC_ROOT / "seeds/hybrid_manifest_v2_cdna2_fullblocks.json"
DEFAULT_GGUF_PATH = HELIX_CDC_ROOT / "tmp/mistral_fp8combined_canonical.gguf"


class CDNAModelLoader:
    """
    Load and manage CDNA model shards.

    Provides:
    - Manifest loading with SHA256 verification capability
    - Manifest hash for receipt fingerprinting
    - Access to manifest metadata
    """

    def __init__(
        self,
        manifest_path: Path = DEFAULT_MANIFEST_PATH,
        gguf_path: Path = DEFAULT_GGUF_PATH,
    ):
        """
        Initialize model loader.

        Args:
            manifest_path: Path to hybrid_manifest_v2.json
            gguf_path: Path to GGUF file for norm weights and embeddings
        """
        self.manifest_path = Path(manifest_path).absolute()
        self.gguf_path = Path(gguf_path).absolute()

        if not self.manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {self.manifest_path}")
        if not self.gguf_path.exists():
            raise FileNotFoundError(f"GGUF not found: {self.gguf_path}")

        # Load manifest
        self._manifest: Dict[str, Any] = json.loads(self.manifest_path.read_text())

        # Compute manifest hash
        self._manifest_hash = hashlib.sha256(
            json.dumps(self._manifest, sort_keys=True).encode()
        ).hexdigest()[:16]

        # Index shards by tensor name for quick lookup
        self._shard_index: Dict[str, Dict[str, Any]] = {}
        for shard in self._manifest.get("shards", []):
            tensor_name = shard.get("tensor_name")
            if tensor_name:
                self._shard_index[tensor_name] = shard

    @property
    def manifest_hash(self) -> str:
        """Get SHA256[:16] hash of manifest for receipt fingerprinting."""
        return self._manifest_hash

    @property
    def num_shards(self) -> int:
        """Get number of shards in manifest."""
        return len(self._manifest.get("shards", []))

    @property
    def total_bytes(self) -> int:
        """Get total size of all shards in bytes."""
        return self._manifest.get("total_bytes", 0)

    @property
    def schema(self) -> str:
        """Get manifest schema version."""
        return self._manifest.get("schema", "unknown")

    def get_shard_info(self, tensor_name: str) -> Optional[Dict[str, Any]]:
        """
        Get shard info by tensor name.

        Args:
            tensor_name: Name of tensor (e.g., 'blk.0.attn_q.weight')

        Returns:
            Shard info dict with path, size_bytes, sha256, or None if not found
        """
        return self._shard_index.get(tensor_name)

    def get_shard_path(self, tensor_name: str) -> Optional[Path]:
        """
        Get absolute path to a shard file.

        Args:
            tensor_name: Name of tensor

        Returns:
            Absolute path to shard file, or None if not found
        """
        info = self.get_shard_info(tensor_name)
        if info is None:
            return None

        # Path in manifest is relative to helix-cdc root
        rel_path = info.get("path", "")
        return HELIX_CDC_ROOT / rel_path

    def verify_shard(self, tensor_name: str) -> bool:
        """
        Verify shard file matches expected SHA256.

        Args:
            tensor_name: Name of tensor to verify

        Returns:
            True if SHA256 matches, False otherwise
        """
        info = self.get_shard_info(tensor_name)
        if info is None:
            return False

        shard_path = self.get_shard_path(tensor_name)
        if shard_path is None or not shard_path.exists():
            return False

        expected_sha256 = info.get("sha256", "")
        if not expected_sha256:
            return False

        # Compute actual SHA256
        actual_sha256 = hashlib.sha256(shard_path.read_bytes()).hexdigest()

        return actual_sha256.lower() == expected_sha256.lower()

    def list_tensors(self) -> list[str]:
        """Get list of all tensor names in manifest."""
        return list(self._shard_index.keys())

    def to_dict(self) -> Dict[str, Any]:
        """Convert loader state to dict for receipts."""
        return {
            "manifest_path": str(self.manifest_path),
            "manifest_hash": self._manifest_hash,
            "gguf_path": str(self.gguf_path),
            "num_shards": self.num_shards,
            "total_bytes": self.total_bytes,
            "schema": self.schema,
        }


if __name__ == "__main__":
    print("=== CDNA Model Loader Test ===")
    print()

    try:
        loader = CDNAModelLoader()
        print(f"Manifest: {loader.manifest_path}")
        print(f"Manifest hash: {loader.manifest_hash}")
        print(f"GGUF: {loader.gguf_path}")
        print(f"Shards: {loader.num_shards}")
        print(f"Total bytes: {loader.total_bytes:,}")
        print(f"Schema: {loader.schema}")
        print()

        # Sample tensor check
        tensors = loader.list_tensors()[:5]
        print(f"Sample tensors: {tensors}")

    except Exception as e:
        print(f"Error: {e}")
