"""Data Provenance Tracking for FGIP.

Tracks the source and verifiability of data used in trade decision-making.
This enables fail-closed gating - decisions cannot proceed with unverified data.

Usage:
    from fgip.analysis.provenance import DataProvenance

    prov = DataProvenance(
        source_type="yfinance",
        source_ref="INTC",
        retrieved_at="2025-02-25T12:00:00Z",
        content_hash="abc123...",
    )
    if prov.is_verifiable():
        # Safe to use data in gating decisions
        pass
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class DataProvenance:
    """Tracks the source and verifiability of data.

    Attributes:
        source_type: Origin of data ("yfinance", "mock", "forecast_db", "artifact")
        source_ref: Reference identifier (ticker, forecast_id, artifact_id)
        retrieved_at: ISO timestamp when data was fetched
        content_hash: SHA256 of raw data (for external sources)
        notes: Additional context about the data source
    """

    source_type: str  # "yfinance", "mock", "forecast_db", "artifact"
    source_ref: Optional[str]  # forecast_id, artifact_id, ticker symbol
    retrieved_at: str  # ISO timestamp
    content_hash: Optional[str] = None  # SHA256 of raw data (if available)
    notes: str = ""

    def is_verifiable(self) -> bool:
        """Returns True if data has auditable provenance.

        Verifiable sources:
        - yfinance with content_hash (live market data with checksum)
        - forecast_db with source_ref (DB-backed forecast with ID)
        - artifact with source_ref (stored document/artifact)

        Non-verifiable sources:
        - mock (placeholder data, no real source)
        - missing source_ref for DB-backed types

        Returns:
            True if the data source can be audited and verified.
        """
        # Mock data is NEVER verifiable
        if self.source_type == "mock":
            return False

        # DB-backed with ID is verifiable
        if self.source_type in ("forecast_db", "artifact") and self.source_ref:
            return True

        # yfinance with content hash is verifiable
        if self.source_type == "yfinance" and self.content_hash:
            return True

        return False

    def to_dict(self) -> dict:
        """Serialize provenance for JSON output."""
        return {
            "source_type": self.source_type,
            "source_ref": self.source_ref,
            "retrieved_at": self.retrieved_at,
            "content_hash": self.content_hash,
            "notes": self.notes,
            "verified": self.is_verifiable(),
        }


__all__ = ["DataProvenance"]
