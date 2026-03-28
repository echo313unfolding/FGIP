"""FGIP Agent Base Class - Evidence gatherers that propose HYPOTHESIS claims/edges.

Key principle: Agents are evidence gatherers + hypothesis proposers, NOT truth-makers.
All proposals are HYPOTHESIS by default and require human review for promotion.

Agents can ONLY:
- Write to staging tables (proposed_claims, proposed_edges)
- Queue upgrade requirements (what evidence would promote HYPOTHESIS → INFERENCE/FACT)
- Compute correlation metrics

Agents CANNOT:
- Write directly to claims/edges tables
- Promote their own proposals
- Bypass human review
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any
import hashlib
import json
import logging
import uuid

from fgip.fsa import (
    FSAEnforcer, PIPELINE_FSA, PIPELINE_STATES, PIPELINE_EVENTS,
    PIPELINE_VIOLATIONS,
)

log = logging.getLogger(__name__)


@dataclass
class Artifact:
    """A fetched artifact (PDF, HTML, filing, etc.)."""
    url: str
    artifact_type: str  # 'pdf', 'html', 'json', 'xml'
    local_path: Optional[str] = None
    content_hash: Optional[str] = None
    fetched_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.fetched_at is None:
            self.fetched_at = datetime.utcnow().isoformat() + "Z"

    def compute_hash(self, content: bytes) -> str:
        """Compute SHA256 hash of artifact content."""
        self.content_hash = hashlib.sha256(content).hexdigest()
        return self.content_hash

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "artifact_type": self.artifact_type,
            "local_path": self.local_path,
            "content_hash": self.content_hash,
            "fetched_at": self.fetched_at,
            "metadata": self.metadata,
        }


@dataclass
class StructuredFact:
    """An extracted fact from an artifact (not yet a claim)."""
    fact_type: str  # 'ownership', 'filing', 'ruling', 'event', etc.
    subject: str  # Entity name or ID
    predicate: str  # Relationship or attribute
    object: str  # Target entity or value
    source_artifact: Artifact
    confidence: float = 0.5
    date_occurred: Optional[str] = None
    date_extracted: Optional[str] = None
    raw_text: Optional[str] = None  # Supporting text snippet
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.date_extracted is None:
            self.date_extracted = datetime.utcnow().isoformat() + "Z"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fact_type": self.fact_type,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "source_url": self.source_artifact.url,
            "confidence": self.confidence,
            "date_occurred": self.date_occurred,
            "date_extracted": self.date_extracted,
            "raw_text": self.raw_text,
            "metadata": self.metadata,
        }


@dataclass
class ProposedClaim:
    """A proposed claim awaiting human review (HYPOTHESIS by default)."""
    proposal_id: str
    claim_text: str
    topic: str
    agent_name: str
    source_url: Optional[str] = None
    artifact_path: Optional[str] = None
    artifact_hash: Optional[str] = None
    reasoning: Optional[str] = None
    promotion_requirement: Optional[str] = None  # What Tier 0/1 doc would upgrade this
    created_at: Optional[str] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow().isoformat() + "Z"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "claim_text": self.claim_text,
            "topic": self.topic,
            "agent_name": self.agent_name,
            "source_url": self.source_url,
            "artifact_path": self.artifact_path,
            "artifact_hash": self.artifact_hash,
            "reasoning": self.reasoning,
            "promotion_requirement": self.promotion_requirement,
            "created_at": self.created_at,
        }


@dataclass
class ProposedEdge:
    """A proposed edge awaiting human review (HYPOTHESIS by default)."""
    proposal_id: str
    from_node: str
    to_node: str
    relationship: str  # EdgeType value
    agent_name: str
    detail: Optional[str] = None
    proposed_claim_id: Optional[str] = None  # Links to ProposedClaim
    confidence: float = 0.5
    reasoning: Optional[str] = None
    promotion_requirement: Optional[str] = None
    created_at: Optional[str] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow().isoformat() + "Z"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "from_node": self.from_node,
            "to_node": self.to_node,
            "relationship": self.relationship,
            "detail": self.detail,
            "proposed_claim_id": self.proposed_claim_id,
            "agent_name": self.agent_name,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "promotion_requirement": self.promotion_requirement,
            "created_at": self.created_at,
        }


@dataclass
class ProposedNode:
    """A proposed node awaiting human review."""
    proposal_id: str
    node_id: str
    node_type: str  # NodeType value
    name: str
    agent_name: str
    aliases: Optional[List[str]] = None
    description: Optional[str] = None
    source_url: Optional[str] = None
    reasoning: Optional[str] = None
    created_at: Optional[str] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow().isoformat() + "Z"
        if self.aliases is None:
            self.aliases = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "node_id": self.node_id,
            "node_type": self.node_type,
            "name": self.name,
            "aliases": self.aliases,
            "description": self.description,
            "agent_name": self.agent_name,
            "source_url": self.source_url,
            "reasoning": self.reasoning,
            "created_at": self.created_at,
        }


class FGIPAgent(ABC):
    """Abstract base class for FGIP agents.

    Agents are evidence gatherers that can ONLY write to staging tables.
    They propose HYPOTHESIS claims/edges that require human review for promotion.

    Subclasses must implement:
        - collect(): Fetch new artifacts (URLs/PDFs/filings)
        - extract(): Extract structured facts from artifacts
        - propose(): Generate HYPOTHESIS claims/edges from facts

    Agents explicitly DO NOT have:
        - promote(), verify(), or direct writes to claims/edges tables
    """

    def __init__(self, db, name: str, description: str = "", fsa_enabled: bool = False):
        """Initialize agent with database connection.

        Args:
            db: FGIPDatabase instance
            name: Agent name (e.g., 'edgar', 'scotus')
            description: Human-readable description
            fsa_enabled: Enable MorphSAT FSA enforcement on run()
        """
        self.db = db
        self.name = name
        self.description = description
        self._proposal_counter = 0
        self._fsa_enabled = fsa_enabled
        self._fsa = FSAEnforcer(
            PIPELINE_FSA, PIPELINE_STATES, PIPELINE_EVENTS,
            violations=PIPELINE_VIOLATIONS, agent_name=name,
        )

    @property
    def agent_name(self) -> str:
        """Canonical agent name for database records."""
        return self.name

    def _generate_proposal_id(self) -> str:
        """Generate unique proposal ID."""
        self._proposal_counter += 1
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        short_uuid = uuid.uuid4().hex[:8]
        return f"FGIP-PROPOSED-{self.name.upper()}-{timestamp}-{short_uuid}"

    @abstractmethod
    def collect(self) -> List[Artifact]:
        """Fetch new artifacts (URLs/PDFs/filings).

        Should:
        - Check official sources (APIs, RSS, public documents)
        - Respect robots.txt and rate limits
        - Store artifacts locally with SHA256 hash

        Returns:
            List of fetched Artifact objects
        """
        pass

    @abstractmethod
    def extract(self, artifacts: List[Artifact]) -> List[StructuredFact]:
        """Extract entities, dates, amounts, docket numbers from artifacts.

        Should:
        - Parse artifact content (PDF text, HTML, JSON)
        - Extract structured data (entity names, relationships, dates)
        - Maintain provenance (which artifact, what text snippet)

        Args:
            artifacts: List of Artifact objects to process

        Returns:
            List of StructuredFact objects
        """
        pass

    @abstractmethod
    def propose(self, facts: List[StructuredFact]) -> Tuple[List[ProposedClaim], List[ProposedEdge]]:
        """Generate HYPOTHESIS claims/edges from extracted facts.

        Should:
        - Create claims with clear promotion_requirement
        - Link edges to their backing claims
        - Set appropriate confidence scores
        - Include reasoning for human reviewer

        Args:
            facts: List of StructuredFact objects

        Returns:
            Tuple of (proposed_claims, proposed_edges)
        """
        pass

    def queue_upgrade(self, proposal_id: str, required_evidence: str) -> bool:
        """Specify what receipt would promote HYPOTHESIS → INFERENCE/FACT.

        This is a hint to human reviewers about what additional evidence
        would strengthen the proposal.

        Args:
            proposal_id: The proposal to annotate
            required_evidence: Description of required evidence

        Returns:
            True if annotation was recorded
        """
        conn = self.db.connect()
        try:
            # Try proposed_claims first
            result = conn.execute(
                """UPDATE proposed_claims
                   SET promotion_requirement = ?
                   WHERE proposal_id = ?""",
                (required_evidence, proposal_id)
            )
            if result.rowcount == 0:
                # Try proposed_edges
                conn.execute(
                    """UPDATE proposed_edges
                       SET promotion_requirement = ?
                       WHERE proposal_id = ?""",
                    (required_evidence, proposal_id)
                )
            conn.commit()
            return True
        except Exception:
            return False

    def run(self) -> Dict[str, Any]:
        """Execute the full agent pipeline: collect → extract → propose.

        This is the main entry point for running an agent.
        When fsa_enabled=True, every step boundary emits an FSA event.
        Illegal transitions are logged and block the pipeline.

        Returns:
            Dict with run statistics
        """
        results = {
            "agent": self.name,
            "artifacts_collected": 0,
            "facts_extracted": 0,
            "claims_proposed": 0,
            "edges_proposed": 0,
            "nodes_proposed": 0,
            "errors": [],
        }

        # --- FSA gate: begin ---
        if self._fsa_enabled:
            self._fsa.reset()
            legal, _ = self._fsa.step(0)  # begin → COLLECTING
            if not legal:
                vtype = self._fsa.violations[-1].violation_type
                log.warning("FSA BLOCKED %s at begin: %s", self.name, vtype)
                results["errors"].append(f"FSA: {vtype}")
                results["fsa"] = self._fsa.summary()
                return results

        try:
            # Step 1: Collect artifacts
            artifacts = self.collect()
            results["artifacts_collected"] = len(artifacts)

            if not artifacts:
                if self._fsa_enabled:
                    self._fsa.step(8)  # error — no artifacts
                return results

            # --- FSA gate: artifact_in → integrity_ok ---
            if self._fsa_enabled:
                self._fsa.step(1)  # artifact_in → VALIDATING
                self._fsa.step(2)  # integrity_ok → EXTRACTING (auto: base.py has no FilterAgent)

            # Step 2: Extract facts
            facts = self.extract(artifacts)
            results["facts_extracted"] = len(facts)

            if not facts:
                if self._fsa_enabled:
                    self._fsa.step(8)  # error — no facts
                return results

            # --- FSA gate: facts_out ---
            if self._fsa_enabled:
                legal, _ = self._fsa.step(4)  # facts_out → PROPOSING
                if not legal:
                    vtype = self._fsa.violations[-1].violation_type
                    log.warning("FSA BLOCKED %s at facts_out: %s", self.name, vtype)
                    results["errors"].append(f"FSA: {vtype}")
                    results["fsa"] = self._fsa.summary()
                    return results

            # Step 3: Generate proposals
            propose_result = self.propose(facts)

            # Handle agents that return 2 or 3 elements (claims, edges) or (claims, edges, nodes)
            if len(propose_result) == 3:
                claims, edges, nodes = propose_result
            else:
                claims, edges = propose_result
                nodes = []
            results["claims_proposed"] = len(claims)
            results["edges_proposed"] = len(edges)
            results["nodes_proposed"] = len(nodes)

            # --- FSA gate: claim_formed → evidence_attached ---
            if self._fsa_enabled:
                self._fsa.step(5)  # claim_formed → CITING
                self._fsa.step(6)  # evidence_attached → WRITING (auto: base.py attaches in propose)

            # Step 4: Write to staging tables
            self._write_proposals(claims, edges)

            # Step 5: Write node proposals if any
            if nodes:
                self._write_node_proposals(nodes)

            # --- FSA gate: write_ok ---
            if self._fsa_enabled:
                self._fsa.step(7)  # write_ok → COMPLETE

        except Exception as e:
            results["errors"].append(str(e))
            if self._fsa_enabled:
                self._fsa.step(8)  # error

        if self._fsa_enabled:
            results["fsa"] = self._fsa.summary()

        return results

    def run_with_delta(self) -> Dict[str, Any]:
        """Execute agent with delta tracking for live signals.

        Wraps run() with:
        1. Record run start in ingest_runs table
        2. Execute normal run()
        3. Compute delta hash (SHA256 of new proposal IDs)
        4. Record completion with delta stats

        Returns:
            Dict with run statistics + delta info
        """
        conn = self.db.connect()
        run_id = f"{self.name}-{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}"

        # Get previous successful run for this agent
        prev_run = conn.execute(
            """SELECT run_id, completed_at FROM ingest_runs
               WHERE agent_name = ? AND status = 'SUCCESS'
               ORDER BY completed_at DESC LIMIT 1""",
            (self.name,)
        ).fetchone()

        prev_completed_at = prev_run[1] if prev_run else '1970-01-01T00:00:00Z'
        prev_run_id = prev_run[0] if prev_run else None

        # Get proposal counts before run
        before_claims = conn.execute(
            "SELECT COUNT(*) FROM proposed_claims WHERE agent_name = ?",
            (self.name,)
        ).fetchone()[0]
        before_edges = conn.execute(
            "SELECT COUNT(*) FROM proposed_edges WHERE agent_name = ?",
            (self.name,)
        ).fetchone()[0]

        # Record run start
        started_at = datetime.utcnow().isoformat() + "Z"
        conn.execute(
            """INSERT INTO ingest_runs (run_id, agent_name, started_at, status, previous_run_id)
               VALUES (?, ?, ?, 'RUNNING', ?)""",
            (run_id, self.name, started_at, prev_run_id)
        )
        conn.commit()

        # Execute the agent
        try:
            results = self.run()

            # Get new proposal IDs since last run
            new_claims = conn.execute(
                """SELECT proposal_id FROM proposed_claims
                   WHERE agent_name = ? AND created_at > ?
                   ORDER BY proposal_id""",
                (self.name, prev_completed_at)
            ).fetchall()
            new_edges = conn.execute(
                """SELECT proposal_id FROM proposed_edges
                   WHERE agent_name = ? AND created_at > ?
                   ORDER BY proposal_id""",
                (self.name, prev_completed_at)
            ).fetchall()

            # Compute delta hash
            delta_ids = sorted([r[0] for r in new_claims] + [r[0] for r in new_edges])
            delta_hash = hashlib.sha256(json.dumps(delta_ids).encode()).hexdigest()

            # Update run record with success
            completed_at = datetime.utcnow().isoformat() + "Z"
            proposals_count = results.get('claims_proposed', 0) + results.get('edges_proposed', 0)
            metadata = json.dumps({
                "claims_proposed": results.get('claims_proposed', 0),
                "edges_proposed": results.get('edges_proposed', 0),
                "nodes_proposed": results.get('nodes_proposed', 0),
                "artifacts_collected": results.get('artifacts_collected', 0),
            })

            conn.execute(
                """UPDATE ingest_runs SET
                   completed_at = ?, status = 'SUCCESS',
                   proposals_count = ?, delta_hash = ?, metadata = ?
                   WHERE run_id = ?""",
                (completed_at, proposals_count, delta_hash, metadata, run_id)
            )
            conn.commit()

            # Add delta info to results
            results['run_id'] = run_id
            results['delta_count'] = len(delta_ids)
            results['delta_hash'] = delta_hash
            results['previous_run_id'] = prev_run_id

        except Exception as e:
            # Record failure
            completed_at = datetime.utcnow().isoformat() + "Z"
            conn.execute(
                """UPDATE ingest_runs SET
                   completed_at = ?, status = 'FAILED',
                   metadata = ?
                   WHERE run_id = ?""",
                (completed_at, json.dumps({"error": str(e)}), run_id)
            )
            conn.commit()
            raise

        return results

    def _write_proposals(self, claims: List[ProposedClaim], edges: List[ProposedEdge]):
        """Write proposals to staging tables.

        This is the ONLY place agents write to the database.
        They can ONLY write to proposed_claims and proposed_edges.
        """
        conn = self.db.connect()

        for claim in claims:
            conn.execute(
                """INSERT INTO proposed_claims
                   (proposal_id, claim_text, topic, agent_name, source_url,
                    artifact_path, artifact_hash, reasoning, promotion_requirement,
                    status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)""",
                (claim.proposal_id, claim.claim_text, claim.topic, claim.agent_name,
                 claim.source_url, claim.artifact_path, claim.artifact_hash,
                 claim.reasoning, claim.promotion_requirement, claim.created_at)
            )

        for edge in edges:
            conn.execute(
                """INSERT INTO proposed_edges
                   (proposal_id, from_node, to_node, relationship, detail,
                    proposed_claim_id, agent_name, confidence, reasoning,
                    promotion_requirement, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)""",
                (edge.proposal_id, edge.from_node, edge.to_node, edge.relationship,
                 edge.detail, edge.proposed_claim_id, edge.agent_name, edge.confidence,
                 edge.reasoning, edge.promotion_requirement, edge.created_at)
            )

        conn.commit()

    def _write_node_proposals(self, nodes: List["ProposedNode"]):
        """Write node proposals to staging table.

        Args:
            nodes: List of ProposedNode objects
        """
        conn = self.db.connect()
        import json

        for node in nodes:
            aliases_json = json.dumps(node.aliases) if node.aliases else None
            conn.execute(
                """INSERT INTO proposed_nodes
                   (proposal_id, node_id, node_type, name, aliases, description,
                    agent_name, source_url, reasoning, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)""",
                (node.proposal_id, node.node_id, node.node_type, node.name,
                 aliases_json, node.description, node.agent_name, node.source_url,
                 node.reasoning, node.created_at)
            )

        conn.commit()

    def get_status(self) -> Dict[str, Any]:
        """Get agent status including pending proposals.

        Returns:
            Dict with agent status information
        """
        conn = self.db.connect()

        pending_claims = conn.execute(
            "SELECT COUNT(*) FROM proposed_claims WHERE agent_name = ? AND status = 'PENDING'",
            (self.name,)
        ).fetchone()[0]

        pending_edges = conn.execute(
            "SELECT COUNT(*) FROM proposed_edges WHERE agent_name = ? AND status = 'PENDING'",
            (self.name,)
        ).fetchone()[0]

        approved_claims = conn.execute(
            "SELECT COUNT(*) FROM proposed_claims WHERE agent_name = ? AND status = 'APPROVED'",
            (self.name,)
        ).fetchone()[0]

        approved_edges = conn.execute(
            "SELECT COUNT(*) FROM proposed_edges WHERE agent_name = ? AND status = 'APPROVED'",
            (self.name,)
        ).fetchone()[0]

        rejected_claims = conn.execute(
            "SELECT COUNT(*) FROM proposed_claims WHERE agent_name = ? AND status = 'REJECTED'",
            (self.name,)
        ).fetchone()[0]

        rejected_edges = conn.execute(
            "SELECT COUNT(*) FROM proposed_edges WHERE agent_name = ? AND status = 'REJECTED'",
            (self.name,)
        ).fetchone()[0]

        return {
            "agent": self.name,
            "description": self.description,
            "pending_claims": pending_claims,
            "pending_edges": pending_edges,
            "approved_claims": approved_claims,
            "approved_edges": approved_edges,
            "rejected_claims": rejected_claims,
            "rejected_edges": rejected_edges,
        }
