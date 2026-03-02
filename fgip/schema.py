"""FGIP Schema - Node, Edge, Source, Claim dataclasses and enums."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import hashlib
import json
from urllib.parse import urlparse


class NodeType(str, Enum):
    """Valid node types in the FGIP knowledge graph."""
    ORGANIZATION = "ORGANIZATION"
    PERSON = "PERSON"
    LEGISLATION = "LEGISLATION"
    COURT_CASE = "COURT_CASE"
    POLICY = "POLICY"
    COMPANY = "COMPANY"
    MEDIA_OUTLET = "MEDIA_OUTLET"
    FINANCIAL_INST = "FINANCIAL_INST"
    AMICUS_BRIEF = "AMICUS_BRIEF"
    ETF_FUND = "ETF_FUND"
    ECONOMIC_EVENT = "ECONOMIC_EVENT"
    # Correction layer node types
    AGENCY = "AGENCY"              # Government agency (FDIC, Treasury, Commerce)
    FACILITY = "FACILITY"          # Physical facility/plant
    LOCATION = "LOCATION"          # Geographic location
    PROJECT = "PROJECT"            # Funded project/initiative
    PROGRAM = "PROGRAM"            # Government program (CHIPS funding, etc.)


class EdgeType(str, Enum):
    """Valid edge types representing relationships."""
    # Factual relationship types (direct evidence)
    LOBBIED_FOR = "LOBBIED_FOR"
    LOBBIED_AGAINST = "LOBBIED_AGAINST"
    FILED_AMICUS = "FILED_AMICUS"
    OWNS_SHARES = "OWNS_SHARES"
    EMPLOYS = "EMPLOYS"
    EMPLOYED = "EMPLOYED"
    MARRIED_TO = "MARRIED_TO"
    DONATED_TO = "DONATED_TO"
    APPOINTED_BY = "APPOINTED_BY"
    RULED_ON = "RULED_ON"
    OWNS_MEDIA = "OWNS_MEDIA"
    REPORTS_ON = "REPORTS_ON"
    MEMBER_OF = "MEMBER_OF"
    INVESTED_IN = "INVESTED_IN"
    SUPPLIES = "SUPPLIES"
    REGISTERED_AS_AGENT = "REGISTERED_AS_AGENT"  # FARA foreign agent registration
    # Causal/inferential relationship types (require assertion_level)
    CAUSED = "CAUSED"
    ENABLED = "ENABLED"
    CONTRIBUTED_TO = "CONTRIBUTED_TO"
    FACILITATED = "FACILITATED"
    PROFITED_FROM = "PROFITED_FROM"
    COORDINATED_WITH = "COORDINATED_WITH"
    # Correction-related
    CORRECTS = "CORRECTS"
    OPPOSES_CORRECTION = "OPPOSES_CORRECTION"
    # Correction layer - legislation/regulation flow
    AUTHORIZED_BY = "AUTHORIZED_BY"        # project/award → statute/program
    IMPLEMENTED_BY = "IMPLEMENTED_BY"      # statute/program → agency
    RULEMAKING_FOR = "RULEMAKING_FOR"      # agency action → statute/program
    # Correction layer - money flow
    AWARDED_GRANT = "AWARDED_GRANT"        # agency/program → recipient
    AWARDED_CONTRACT = "AWARDED_CONTRACT"  # agency → vendor
    FUNDED_PROJECT = "FUNDED_PROJECT"      # recipient → facility/project
    # Correction layer - operational/outcome signals
    BUILT_IN = "BUILT_IN"                  # facility/project → location
    EXPANDED_CAPACITY = "EXPANDED_CAPACITY"  # company → capability node
    RESHORING_SIGNAL = "RESHORING_SIGNAL"  # company → reshoring indicator
    # Deep Intelligence edge types (DI-1 through DI-11)
    SUPPLIES_TO = "SUPPLIES_TO"            # supplier → customer (from 10-K)
    CUSTOMER_OF = "CUSTOMER_OF"            # company → customer (revenue concentration)
    COMPETES_WITH = "COMPETES_WITH"        # company → competitor (from Risk Factors)
    ACQUIRED = "ACQUIRED"                  # acquirer → target (from 8-K/10-K)
    SIGNED_CONTRACT = "SIGNED_CONTRACT"    # company → contract/government entity
    OPENED_FACILITY = "OPENED_FACILITY"    # company → location (from 8-K Properties)
    INCREASED_POSITION = "INCREASED_POSITION"  # institution → company (13-F delta)
    DECREASED_POSITION = "DECREASED_POSITION"  # institution → company (13-F delta)
    SITS_ON_BOARD = "SITS_ON_BOARD"        # person → company (from DEF 14A)
    RELATED_PARTY_TXN = "RELATED_PARTY_TXN"  # person/entity → entity (proxy disclosure)
    SUBCONTRACTED_TO = "SUBCONTRACTED_TO"  # prime contractor → sub (from SAM.gov)
    # Industrial Base edges (supply chain, facilities, bottlenecks)
    DEPENDS_ON = "DEPENDS_ON"              # company → supplier (critical single-source dependency)
    PRODUCES = "PRODUCES"                  # facility → product_category (output tracking)
    CAPACITY_AT = "CAPACITY_AT"            # company → facility (with capacity metadata)
    BOTTLENECK_AT = "BOTTLENECK_AT"        # supply_chain → facility/location (identified chokepoint)
    # Narrative divergence types
    DIVERGES_FROM = "DIVERGES_FROM"        # investigative finding diverges from rhetoric
    CONTRADICTS = "CONTRADICTS"            # direct contradiction between claims
    APPEARED_ON = "APPEARED_ON"            # person appeared on media outlet/podcast
    # Economic mechanism types (for dynamic scenario modeling)
    REDUCES = "REDUCES"                    # policy reduces economic variable
    BLOCKS = "BLOCKS"                      # policy blocks economic behavior
    REPLACES = "REPLACES"                  # mechanism replaces another (Fed printing)
    CORRELATES = "CORRELATES"              # variable correlates with another
    DERIVES_FROM = "DERIVES_FROM"          # variable computed from others


class SourceType(str, Enum):
    """Source attribution types for edges (legacy)."""
    GOV_FILING = "gov_filing"
    JOURNALISM = "journalism"
    ACADEMIC = "academic"
    COURT_RECORD = "court_record"


class ClaimStatus(str, Enum):
    """Status of a claim's evidence."""
    MISSING = "MISSING"      # Placeholder only, no URL
    PARTIAL = "PARTIAL"      # Has URL, no artifact captured
    EVIDENCED = "EVIDENCED"  # Artifact captured
    VERIFIED = "VERIFIED"    # Tier 0/1 artifact attached


class SourceTier(int, Enum):
    """Evidence tier hierarchy."""
    PRIMARY = 0     # Government docs, court filings, SEC filings
    JOURNALISM = 1  # Journalism citing primary sources
    COMMENTARY = 2  # Commentary, blogs, Wikipedia


class AssertionLevel(str, Enum):
    """Epistemic level of an edge assertion.

    FACT: Direct evidence exists (e.g., "X owns Y" with SEC filing)
    INFERENCE: Reasonable conclusion from facts (e.g., "PNTR enabled trade flows")
    HYPOTHESIS: Speculative causal chain (e.g., "PNTR contributed to fentanyl crisis")
    """
    FACT = "FACT"              # Direct Tier 0/1 evidence
    INFERENCE = "INFERENCE"    # Reasonable conclusion from documented facts
    HYPOTHESIS = "HYPOTHESIS"  # Speculative or contested causal link


# Edge types that default to INFERENCE/HYPOTHESIS unless Tier 0 direct evidence
INFERENTIAL_EDGE_TYPES = {
    'ENABLED', 'CAUSED', 'PROFITED_FROM', 'COORDINATED_WITH',
    'CONTRIBUTED_TO', 'FACILITATED',
    # Correction layer - interpretive/causal
    'CORRECTS', 'OPPOSES_CORRECTION',
    'EXPANDED_CAPACITY', 'RESHORING_SIGNAL',
    # Economic mechanism types (dynamic scenario modeling)
    'REDUCES', 'BLOCKS', 'REPLACES', 'CORRELATES', 'DERIVES_FROM',
}

# Edge types that are factual by nature (reporting/documenting relationships)
FACTUAL_EDGE_TYPES = {
    'OWNS_SHARES', 'EMPLOYS', 'MARRIED_TO', 'MEMBER_OF',
    'FILED_AMICUS', 'REPORTS_ON', 'DONATED_TO', 'APPOINTED_BY',
    'LOBBIED_FOR', 'LOBBIED_AGAINST', 'RULED_ON', 'SUPPLIES',
    'REGISTERED_AS_AGENT',
    # Correction layer - documented flows (Tier 0 eligible)
    'AUTHORIZED_BY', 'IMPLEMENTED_BY', 'RULEMAKING_FOR',
    'AWARDED_GRANT', 'AWARDED_CONTRACT', 'FUNDED_PROJECT', 'BUILT_IN',
    # Deep Intelligence - SEC filing derived (Tier 0)
    'SUPPLIES_TO', 'CUSTOMER_OF', 'COMPETES_WITH', 'ACQUIRED',
    'SIGNED_CONTRACT', 'OPENED_FACILITY', 'INCREASED_POSITION',
    'DECREASED_POSITION', 'SITS_ON_BOARD', 'RELATED_PARTY_TXN',
    'SUBCONTRACTED_TO',
}


# Domain classification for auto-tiering
TIER_0_DOMAINS = [
    'congress.gov', 'house.gov', 'senate.gov', 'whitehouse.gov',
    'gao.gov', 'sec.gov', 'supremecourt.gov', 'justia.com',
    'federalreserve.gov', 'treasury.gov', 'state.gov', 'commerce.gov',
    'ncua.gov', 'archives.gov', 'govtrack.us', 'crsreports.congress.gov',
    'hhs.gov', 'bis.org', 'fda.gov', 'cbp.gov', 'federalregister.gov',
    'newyorkfed.org', 'stlouisfed.org',
    # FARA (Foreign Agents Registration Act)
    'fara.gov', 'efile.fara.gov',
    # Other government sources
    'usaspending.gov', 'courtlistener.com', 'recap.law',
]

TIER_1_DOMAINS = [
    'reuters.com', 'npr.org', 'propublica.org', 'opensecrets.org',
    'theintercept.com', 'scotusblog.com', 'cnn.com', 'washingtonpost.com',
    'nytimes.com', 'bbc.co.uk', 'apnews.com', 'fortune.com',
    'influencewatch.org', 'brookings.edu', 'cfr.org', 'rand.org',
    'aei.org', 'harvard.edu', 'columbia.edu', 'unc.edu',
    'ucdavis.edu', 'doi.org', 'yahoo.com', 'cnbc.com', 'foxnews.com',
    'thehill.com', 'politico.com', 'economist.com', 'ft.com',
    'wsj.com', 'bloomberg.com', 'newsweek.com', 'forbes.com',
    'finance.yahoo.com', 'seekingalpha.com'
]


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
        # Remove www. prefix
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain
    except:
        return ""


def auto_tier_domain(domain: str) -> int:
    """Auto-assign tier based on domain."""
    domain_lower = domain.lower()
    for t0 in TIER_0_DOMAINS:
        if t0 in domain_lower:
            return 0
    for t1 in TIER_1_DOMAINS:
        if t1 in domain_lower:
            return 1
    return 2


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
        if self.tier == 2 and self.domain:
            self.tier = auto_tier_domain(self.domain)
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
    def from_url(cls, url: str) -> "Source":
        """Create Source from URL with auto-tiering."""
        source_id = compute_sha256(url)
        domain = extract_domain(url)
        tier = auto_tier_domain(domain)
        return cls(source_id=source_id, url=url, domain=domain, tier=tier)


@dataclass
class Claim:
    """A factual claim with evidence tracking."""
    claim_id: str  # FGIP-000001 format
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
    """A node in the FGIP knowledge graph."""
    node_id: str
    node_type: NodeType
    name: str
    aliases: list[str] = field(default_factory=list)
    description: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    created_at: Optional[str] = None
    sha256: Optional[str] = None

    def __post_init__(self):
        if isinstance(self.node_type, str):
            self.node_type = NodeType(self.node_type)
        if self.created_at is None:
            self.created_at = datetime.utcnow().isoformat() + "Z"
        if self.sha256 is None:
            self.sha256 = self._compute_hash()

    def _compute_hash(self) -> str:
        return compute_sha256({
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "name": self.name,
            "aliases": self.aliases,
            "description": self.description,
            "metadata": self.metadata,
        })

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
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
            node_type=NodeType(data["node_type"]),
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
    """A relationship edge in the FGIP knowledge graph."""
    edge_id: str
    edge_type: EdgeType
    from_node_id: str
    to_node_id: str
    claim_id: Optional[str] = None  # Required for Square-One compliance
    assertion_level: Optional[str] = None  # FACT | INFERENCE | HYPOTHESIS
    # Legacy fields (kept for backward compatibility during migration)
    source: Optional[str] = None
    source_url: Optional[str] = None
    source_type: Optional[SourceType] = None
    date_documented: Optional[str] = None
    date_occurred: Optional[str] = None
    date_ended: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    created_at: Optional[str] = None
    sha256: Optional[str] = None

    def __post_init__(self):
        if isinstance(self.edge_type, str):
            self.edge_type = EdgeType(self.edge_type)
        if isinstance(self.source_type, str):
            self.source_type = SourceType(self.source_type)
        # Auto-set assertion_level based on edge_type if not provided
        if self.assertion_level is None:
            if self.edge_type.value in INFERENTIAL_EDGE_TYPES:
                self.assertion_level = AssertionLevel.INFERENCE.value
            else:
                self.assertion_level = AssertionLevel.FACT.value
        elif isinstance(self.assertion_level, AssertionLevel):
            self.assertion_level = self.assertion_level.value
        if self.created_at is None:
            self.created_at = datetime.utcnow().isoformat() + "Z"
        if self.sha256 is None:
            self.sha256 = self._compute_hash()

    def _compute_hash(self) -> str:
        return compute_sha256({
            "edge_id": self.edge_id,
            "edge_type": self.edge_type.value,
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
            "edge_type": self.edge_type.value,
            "from_node_id": self.from_node_id,
            "to_node_id": self.to_node_id,
            "claim_id": self.claim_id,
            "assertion_level": self.assertion_level,
            "source": self.source,
            "source_url": self.source_url,
            "source_type": self.source_type.value if self.source_type else None,
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
            edge_type=EdgeType(data["edge_type"]),
            from_node_id=data["from_node_id"],
            to_node_id=data["to_node_id"],
            claim_id=data.get("claim_id"),
            assertion_level=data.get("assertion_level"),
            source=data.get("source"),
            source_url=data.get("source_url"),
            source_type=SourceType(data["source_type"]) if data.get("source_type") else None,
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
        # Square-One: Edges without claim_id and source are invalid
        if not self.claim_id and not self.source:
            errors.append("claim_id or source is required (Square-One: prefer claim_id)")
        if self.confidence < 0 or self.confidence > 1:
            errors.append("confidence must be between 0 and 1")
        return errors


@dataclass
class Receipt:
    """Verification receipt for operations per CLAUDE.md."""
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
