"""Receipt generation for Echo Gateway tasks.

Every task execution produces a verifiable receipt with SHA256 hashes
of inputs and outputs for audit trails.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class Receipt:
    """Verifiable receipt for task execution."""

    timestamp: str
    backend_used: str  # 'basin', 'cell', 'swarm'
    duration_ms: float
    inputs_hash: str  # SHA256[:16]
    outputs_hash: str  # SHA256[:16]
    task_type: str
    metadata: Optional[dict] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "timestamp": self.timestamp,
            "backend_used": self.backend_used,
            "duration_ms": self.duration_ms,
            "inputs_hash": self.inputs_hash,
            "outputs_hash": self.outputs_hash,
            "task_type": self.task_type,
        }
        if self.metadata:
            result["metadata"] = self.metadata
        return result


def hash_content(content: Any) -> str:
    """Generate SHA256[:16] hash of content."""
    if content is None:
        content = ""

    if isinstance(content, (dict, list)):
        content_str = json.dumps(content, sort_keys=True, default=str)
    else:
        content_str = str(content)

    return hashlib.sha256(content_str.encode()).hexdigest()[:16]


def generate_receipt(
    task_type: str,
    backend_used: str,
    start_time: float,
    inputs: Any,
    outputs: Any,
    metadata: Optional[dict] = None,
) -> Receipt:
    """
    Generate verifiable receipt for task execution.

    Args:
        task_type: Type of task ('chat', 'cell', 'swarm')
        backend_used: Backend that handled the task ('basin', 'cell', 'swarm')
        start_time: Unix timestamp when task started (from time.time())
        inputs: Task inputs (will be hashed)
        outputs: Task outputs (will be hashed)
        metadata: Optional additional metadata

    Returns:
        Receipt with timestamps and hashes
    """
    duration_ms = round((time.time() - start_time) * 1000, 2)

    return Receipt(
        timestamp=datetime.now(timezone.utc).isoformat(),
        backend_used=backend_used,
        duration_ms=duration_ms,
        inputs_hash=hash_content(inputs),
        outputs_hash=hash_content(outputs),
        task_type=task_type,
        metadata=metadata,
    )


@dataclass
class ReceiptWriter:
    """Writes receipts to JSONL files for audit trail."""

    output_dir: str = "receipts/echo_tasks"

    def __post_init__(self):
        from pathlib import Path
        self._output_path = Path(self.output_dir)
        self._output_path.mkdir(parents=True, exist_ok=True)

    def write(self, receipt: Receipt, session_id: Optional[str] = None) -> str:
        """
        Write receipt to JSONL file.

        Args:
            receipt: Receipt to write
            session_id: Optional session ID for grouping

        Returns:
            Path to receipt file
        """
        import uuid

        # Generate file path
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        file_path = self._output_path / f"tasks_{date_str}.jsonl"

        # Build record
        record = receipt.to_dict()
        record["receipt_id"] = str(uuid.uuid4())[:8]
        if session_id:
            record["session_id"] = session_id

        # Append to file
        with open(file_path, "a") as f:
            f.write(json.dumps(record) + "\n")

        return str(file_path)
