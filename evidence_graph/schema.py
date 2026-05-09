"""Evidence graph schema — domain-agnostic dataclasses.

Node and Edge types are strings validated at runtime by a DomainRegistry,
not hardcoded enums. ClaimStatus, SourceTier, and AssertionLevel remain
enums because they are universal across all domains.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import hashlib
import json
from urllib.parse import urlparse


# --- Universal enums (apply to every domain) ---

class ClaimStatus(str, Enum):
    """Status of a claim's evidence."""
    MISSING = "MISSING"      # Placeholder only, no URL
    PARTIAL = "PARTIAL"      # Has URL, no artifact captured
    EVIDENCED = "EVIDENCED"  # Artifact captured
    VERIFIED = "VERIFIED"    # Tier 0/1 artifact attached


class SourceTier(int, Enum):
    """Evidence tier hierarchy."""
    PRIMARY = 0     # Government docs, court filings, official databases
    JOURNALISM = 1  # Journalism citing primary sources
    COMMENTARY = 2  # Commentary, blogs, user-generated


class AssertionLevel(str, Enum):
    """Epistemic level of an edge assertion.

    FACT: Direct evidence exists (e.g., "CVE-2024-1234 affects nginx")
    INFERENCE: Reasonable conclusion from facts (e.g., "actor likely used this technique")
    HYPOTHESIS: Speculative chain (e.g., "this indicator suggests APT28")
    """
    FACT = "FACT"
    INFERENCE = "INFERENCE"
    HYPOTHESIS = "HYPOTHESIS"


# --- Utility functions ---

def compute_sha256(data) -> str:
    """Compute SHA256 hash of data."""
    if isinstance(data, dict):
        canonical = json.dumps(data, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    elif isinstance(data, str):
        return hashlib.sha256(data.encode('utf-8')).hexdigest()
    elif isinstance(data, bytes):
        return hashlib.sha256(data).hexdigest()
    else:
        return hashlib.sha256(str(data).encode('utf-8')).hexdigest()


def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


# --- Dataclasses ---

@dataclass
class Source:
    """A source URL with evidence metadata."""
    source_id: str  # sha256(url)
    url: str
    domain: Optional[str] = None
    tier: int = 2
    retrieved_at: Optional[str] = None
    artifact_path: Optional[str] = None
    artifact_hash: Optional[str] = None
    notes: Optional[str] = None

    def __post_init__(self):
        if self.source_id is None:
            self.source_id = compute_sha256(self.url)
        if self.domain is None:
            self.domain = extract_domain(self.url)
        # No auto-tiering here — caller or DB layer handles it via registry
        if self.retrieved_at is None:
            self.retrieved_at = datetime.utcnow().isoformat() + "Z"

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "url": self.url,
            "domain": self.domain,
            "tier": self.tier,
            "retrieved_at": self.retrieved_at,
            "artifact_path": self.artifact_path,
            "artifact_hash": self.artifact_hash,
            "notes": self.notes,
        }

    @classmethod
    def from_url(cls, url: str, registry=None) -> "Source":
        """Create Source from URL with optional registry-based tiering."""
        source_id = compute_sha256(url)
        domain = extract_domain(url)
        tier = 2
        if registry is not None:
            tier = registry.auto_tier_domain(domain)
        return cls(source_id=source_id, url=url, domain=domain, tier=tier)


@dataclass
class Claim:
    """A factual claim with evidence tracking."""
    claim_id: str
    claim_text: str
    topic: str
    status: ClaimStatus = ClaimStatus.PARTIAL
    required_tier: int = 1
    created_at: Optional[str] = None
    notes: Optional[str] = None

    def __post_init__(self):
        if isinstance(self.status, str):
            self.status = ClaimStatus(self.status)
        if self.created_at is None:
            self.created_at = datetime.utcnow().isoformat() + "Z"

    def to_dict(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "claim_text": self.claim_text,
            "topic": self.topic,
            "status": self.status.value,
            "required_tier": self.required_tier,
            "created_at": self.created_at,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Claim":
        return cls(
            claim_id=data["claim_id"],
            claim_text=data["claim_text"],
            topic=data["topic"],
            status=ClaimStatus(data.get("status", "PARTIAL")),
            required_tier=data.get("required_tier", 1),
            created_at=data.get("created_at"),
            notes=data.get("notes"),
        )


@dataclass
class Node:
    """A node in the evidence graph."""
    node_id: str
    node_type: str  # Validated by DomainRegistry at insert time
    name: str
    aliases: list[str] = field(default_factory=list)
    description: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    created_at: Optional[str] = None
    sha256: Optional[str] = None

    def __post_init__(self):
        # node_type stays as string — validation happens in DB layer
        if self.created_at is None:
            self.created_at = datetime.utcnow().isoformat() + "Z"
        if self.sha256 is None:
            self.sha256 = self._compute_hash()

    def _compute_hash(self) -> str:
        return compute_sha256({
            "node_id": self.node_id,
            "node_type": self.node_type,
            "name": self.name,
            "aliases": self.aliases,
            "description": self.description,
            "metadata": self.metadata,
        })

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "name": self.name,
            "aliases": self.aliases,
            "description": self.description,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "sha256": self.sha256,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Node":
        return cls(
            node_id=data["node_id"],
            node_type=data["node_type"],
            name=data["name"],
            aliases=data.get("aliases", []),
            description=data.get("description"),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at"),
            sha256=data.get("sha256"),
        )

    def validate(self) -> list[str]:
        errors = []
        if not self.node_id:
            errors.append("node_id is required")
        if not self.name:
            errors.append("name is required")
        if not isinstance(self.aliases, list):
            errors.append("aliases must be a list")
        return errors


@dataclass
class Edge:
    """A relationship edge in the evidence graph."""
    edge_id: str
    edge_type: str  # Validated by DomainRegistry at insert time
    from_node_id: str
    to_node_id: str
    claim_id: Optional[str] = None
    assertion_level: Optional[str] = None  # FACT | INFERENCE | HYPOTHESIS
    source: Optional[str] = None
    source_url: Optional[str] = None
    date_documented: Optional[str] = None
    date_occurred: Optional[str] = None
    date_ended: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    created_at: Optional[str] = None
    sha256: Optional[str] = None

    def __post_init__(self):
        # edge_type stays as string — validation in DB layer
        # assertion_level auto-set deferred to DB layer (needs registry)
        if isinstance(self.assertion_level, AssertionLevel):
            self.assertion_level = self.assertion_level.value
        if self.created_at is None:
            self.created_at = datetime.utcnow().isoformat() + "Z"
        if self.sha256 is None:
            self.sha256 = self._compute_hash()

    def _compute_hash(self) -> str:
        return compute_sha256({
            "edge_id": self.edge_id,
            "edge_type": self.edge_type,
            "from_node_id": self.from_node_id,
            "to_node_id": self.to_node_id,
            "claim_id": self.claim_id,
            "assertion_level": self.assertion_level,
            "source": self.source,
            "source_url": self.source_url,
            "date_occurred": self.date_occurred,
            "confidence": self.confidence,
            "notes": self.notes,
            "metadata": self.metadata,
        })

    def to_dict(self) -> dict:
        return {
            "edge_id": self.edge_id,
            "edge_type": self.edge_type,
            "from_node_id": self.from_node_id,
            "to_node_id": self.to_node_id,
            "claim_id": self.claim_id,
            "assertion_level": self.assertion_level,
            "source": self.source,
            "source_url": self.source_url,
            "date_documented": self.date_documented,
            "date_occurred": self.date_occurred,
            "date_ended": self.date_ended,
            "confidence": self.confidence,
            "notes": self.notes,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "sha256": self.sha256,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Edge":
        return cls(
            edge_id=data["edge_id"],
            edge_type=data["edge_type"],
            from_node_id=data["from_node_id"],
            to_node_id=data["to_node_id"],
            claim_id=data.get("claim_id"),
            assertion_level=data.get("assertion_level"),
            source=data.get("source"),
            source_url=data.get("source_url"),
            date_documented=data.get("date_documented"),
            date_occurred=data.get("date_occurred"),
            date_ended=data.get("date_ended"),
            confidence=data.get("confidence", 1.0),
            notes=data.get("notes"),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at"),
            sha256=data.get("sha256"),
        )

    def validate(self) -> list[str]:
        errors = []
        if not self.edge_id:
            errors.append("edge_id is required")
        if not self.from_node_id:
            errors.append("from_node_id is required")
        if not self.to_node_id:
            errors.append("to_node_id is required")
        if not self.claim_id and not self.source:
            errors.append("claim_id or source is required (prefer claim_id)")
        if self.confidence < 0 or self.confidence > 1:
            errors.append("confidence must be between 0 and 1")
        return errors


@dataclass
class Receipt:
    """Verification receipt for operations."""
    receipt_id: str
    operation: str
    timestamp: str
    input_hash: str
    output_hash: str
    success: bool
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "receipt_id": self.receipt_id,
            "operation": self.operation,
            "timestamp": self.timestamp,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "success": self.success,
            "details": self.details,
        }
