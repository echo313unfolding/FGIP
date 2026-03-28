"""
Satellite correction layer for CDNA models.

Applies model-wide corrections to compensate for accumulated
quantization errors across all transformer blocks.

Architecture:
    Sidecars  = per-tensor local corrections (applied at dequant)
    Satellite = whole-model global correction (applied after final norm)

Usage:
    sat = load_satellite(Path("corrections/satellite_v1.json"))
    hidden_corrected = sat.apply(hidden)  # [batch, seq, d_model]
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import hashlib
import json
import numpy as np


@dataclass
class SatelliteCorrection:
    """Model-wide correction applied after final norm, before LM head.

    Correction types:
        bias:     hidden + bias
        scale:    hidden * scale
        affine:   hidden * scale + bias (recommended default)
        low_rank: hidden + (hidden @ down_proj) @ up_proj
    """

    schema: str = "satellite_correction_v1"
    model_manifest_hash: str = ""

    # Correction type
    correction_type: str = "affine"  # bias | scale | affine | low_rank

    # Correction parameters (numpy arrays when loaded)
    bias: Optional[np.ndarray] = None       # [d_model]
    scale: Optional[np.ndarray] = None      # [d_model]
    down_proj: Optional[np.ndarray] = None  # [d_model, rank]
    up_proj: Optional[np.ndarray] = None    # [rank, d_model]
    rank: int = 0

    # Calibration metadata
    calibration_set_hash: str = ""
    calibration_samples: int = 0
    mse_before: float = 0.0
    mse_after: float = 0.0
    improvement_pct: float = 0.0

    # Timestamps
    created_at: str = ""
    calibration_receipt_id: str = ""

    def apply(self, hidden: np.ndarray) -> np.ndarray:
        """Apply correction to hidden states.

        Args:
            hidden: Hidden states [batch, seq, d_model] or [seq, d_model]

        Returns:
            Corrected hidden states, same shape as input
        """
        if self.correction_type == "bias":
            if self.bias is None:
                return hidden
            return hidden + self.bias

        elif self.correction_type == "scale":
            if self.scale is None:
                return hidden
            return hidden * self.scale

        elif self.correction_type == "affine":
            result = hidden
            if self.scale is not None:
                result = result * self.scale
            if self.bias is not None:
                result = result + self.bias
            return result

        elif self.correction_type == "low_rank":
            if self.down_proj is None or self.up_proj is None:
                return hidden
            # hidden: [..., d_model]
            # down_proj: [d_model, rank]
            # up_proj: [rank, d_model]
            delta = (hidden @ self.down_proj) @ self.up_proj
            return hidden + delta

        return hidden

    def get_storage_size_bytes(self) -> int:
        """Calculate storage size of correction parameters."""
        size = 0
        if self.bias is not None:
            size += self.bias.nbytes
        if self.scale is not None:
            size += self.scale.nbytes
        if self.down_proj is not None:
            size += self.down_proj.nbytes
        if self.up_proj is not None:
            size += self.up_proj.nbytes
        return size

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for JSON storage."""
        d: Dict[str, Any] = {
            "schema": self.schema,
            "model_manifest_hash": self.model_manifest_hash,
            "correction_type": self.correction_type,
            "rank": self.rank,
            "calibration_set_hash": self.calibration_set_hash,
            "calibration_samples": self.calibration_samples,
            "mse_before": self.mse_before,
            "mse_after": self.mse_after,
            "improvement_pct": self.improvement_pct,
            "created_at": self.created_at,
            "calibration_receipt_id": self.calibration_receipt_id,
        }

        # Serialize numpy arrays as lists
        if self.bias is not None:
            d["bias"] = self.bias.astype(np.float32).tolist()
        if self.scale is not None:
            d["scale"] = self.scale.astype(np.float32).tolist()
        if self.down_proj is not None:
            d["down_proj"] = self.down_proj.astype(np.float32).tolist()
        if self.up_proj is not None:
            d["up_proj"] = self.up_proj.astype(np.float32).tolist()

        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SatelliteCorrection":
        """Load from serialized dict."""
        sat = cls(
            schema=d.get("schema", "satellite_correction_v1"),
            model_manifest_hash=d.get("model_manifest_hash", ""),
            correction_type=d.get("correction_type", "affine"),
            rank=d.get("rank", 0),
            calibration_set_hash=d.get("calibration_set_hash", ""),
            calibration_samples=d.get("calibration_samples", 0),
            mse_before=d.get("mse_before", 0.0),
            mse_after=d.get("mse_after", 0.0),
            improvement_pct=d.get("improvement_pct", 0.0),
            created_at=d.get("created_at", ""),
            calibration_receipt_id=d.get("calibration_receipt_id", ""),
        )

        # Load numpy arrays from lists
        if "bias" in d and d["bias"] is not None:
            sat.bias = np.array(d["bias"], dtype=np.float32)
        if "scale" in d and d["scale"] is not None:
            sat.scale = np.array(d["scale"], dtype=np.float32)
        if "down_proj" in d and d["down_proj"] is not None:
            sat.down_proj = np.array(d["down_proj"], dtype=np.float32)
        if "up_proj" in d and d["up_proj"] is not None:
            sat.up_proj = np.array(d["up_proj"], dtype=np.float32)

        return sat


def load_satellite(path: Path) -> Optional[SatelliteCorrection]:
    """Load satellite correction from JSON file.

    Args:
        path: Path to satellite correction JSON file

    Returns:
        SatelliteCorrection if file exists, None otherwise
    """
    if not path.exists():
        return None

    with open(path, "r") as f:
        d = json.load(f)

    return SatelliteCorrection.from_dict(d)


def save_satellite(sat: SatelliteCorrection, path: Path) -> str:
    """Save satellite correction to JSON file.

    Args:
        sat: SatelliteCorrection to save
        path: Output path

    Returns:
        SHA256 hash of saved content
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    # Set created_at if not set
    if not sat.created_at:
        sat.created_at = datetime.now(timezone.utc).isoformat()

    content = json.dumps(sat.to_dict(), indent=2)

    with open(path, "w") as f:
        f.write(content)

    return hashlib.sha256(content.encode()).hexdigest()


def load_satellite_with_verification(
    path: Path,
    expected_sha256: Optional[str] = None
) -> Optional[SatelliteCorrection]:
    """Load satellite with optional SHA256 verification.

    Args:
        path: Path to satellite correction JSON
        expected_sha256: Expected SHA256 hash (if provided, will verify)

    Returns:
        SatelliteCorrection if valid, None if not found

    Raises:
        ValueError: If SHA256 mismatch
    """
    if not path.exists():
        return None

    content = path.read_bytes()

    if expected_sha256:
        actual_sha256 = hashlib.sha256(content).hexdigest()
        if actual_sha256 != expected_sha256:
            raise ValueError(
                f"Satellite SHA256 mismatch: expected {expected_sha256}, "
                f"got {actual_sha256}"
            )

    d = json.loads(content.decode())
    return SatelliteCorrection.from_dict(d)


# Factory functions for creating corrections

def create_bias_correction(
    bias: np.ndarray,
    model_manifest_hash: str = "",
    calibration_set_hash: str = "",
    calibration_samples: int = 0,
    mse_before: float = 0.0,
    mse_after: float = 0.0,
) -> SatelliteCorrection:
    """Create a bias-only correction (hidden + bias)."""
    improvement = ((mse_before - mse_after) / mse_before * 100) if mse_before > 0 else 0
    return SatelliteCorrection(
        correction_type="bias",
        bias=bias.astype(np.float32),
        model_manifest_hash=model_manifest_hash,
        calibration_set_hash=calibration_set_hash,
        calibration_samples=calibration_samples,
        mse_before=mse_before,
        mse_after=mse_after,
        improvement_pct=improvement,
    )


def create_scale_correction(
    scale: np.ndarray,
    model_manifest_hash: str = "",
    calibration_set_hash: str = "",
    calibration_samples: int = 0,
    mse_before: float = 0.0,
    mse_after: float = 0.0,
) -> SatelliteCorrection:
    """Create a scale-only correction (hidden * scale)."""
    improvement = ((mse_before - mse_after) / mse_before * 100) if mse_before > 0 else 0
    return SatelliteCorrection(
        correction_type="scale",
        scale=scale.astype(np.float32),
        model_manifest_hash=model_manifest_hash,
        calibration_set_hash=calibration_set_hash,
        calibration_samples=calibration_samples,
        mse_before=mse_before,
        mse_after=mse_after,
        improvement_pct=improvement,
    )


def create_affine_correction(
    scale: np.ndarray,
    bias: np.ndarray,
    model_manifest_hash: str = "",
    calibration_set_hash: str = "",
    calibration_samples: int = 0,
    mse_before: float = 0.0,
    mse_after: float = 0.0,
) -> SatelliteCorrection:
    """Create an affine correction (hidden * scale + bias)."""
    improvement = ((mse_before - mse_after) / mse_before * 100) if mse_before > 0 else 0
    return SatelliteCorrection(
        correction_type="affine",
        scale=scale.astype(np.float32),
        bias=bias.astype(np.float32),
        model_manifest_hash=model_manifest_hash,
        calibration_set_hash=calibration_set_hash,
        calibration_samples=calibration_samples,
        mse_before=mse_before,
        mse_after=mse_after,
        improvement_pct=improvement,
    )


def create_low_rank_correction(
    down_proj: np.ndarray,
    up_proj: np.ndarray,
    model_manifest_hash: str = "",
    calibration_set_hash: str = "",
    calibration_samples: int = 0,
    mse_before: float = 0.0,
    mse_after: float = 0.0,
) -> SatelliteCorrection:
    """Create a low-rank correction (hidden + (hidden @ down) @ up)."""
    improvement = ((mse_before - mse_after) / mse_before * 100) if mse_before > 0 else 0
    rank = down_proj.shape[1] if len(down_proj.shape) > 1 else 1
    return SatelliteCorrection(
        correction_type="low_rank",
        down_proj=down_proj.astype(np.float32),
        up_proj=up_proj.astype(np.float32),
        rank=rank,
        model_manifest_hash=model_manifest_hash,
        calibration_set_hash=calibration_set_hash,
        calibration_samples=calibration_samples,
        mse_before=mse_before,
        mse_after=mse_after,
        improvement_pct=improvement,
    )
