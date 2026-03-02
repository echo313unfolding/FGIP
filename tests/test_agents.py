"""Tests for FGIP Agent System."""

import json
import os
import tempfile
import unittest
from pathlib import Path

# Add parent to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from fgip.db import FGIPDatabase
from fgip.schema import Node, NodeType, Claim, ClaimStatus
from fgip.agents.base import (
    FGIPAgent, Artifact, StructuredFact, ProposedClaim, ProposedEdge
)
from fgip import staging


class MockAgent(FGIPAgent):
    """Mock agent for testing."""

    def __init__(self, db):
        super().__init__(db, name="mock", description="Mock test agent")
        self.mock_artifacts = []
        self.mock_facts = []

    def collect(self):
        return self.mock_artifacts

    def extract(self, artifacts):
        return self.mock_facts

    def propose(self, facts):
        claims = []
        edges = []

        for fact in facts:
            proposal_id = self._generate_proposal_id()
            claim = ProposedClaim(
                proposal_id=proposal_id,
                claim_text=f"Test claim: {fact.subject} {fact.predicate} {fact.object}",
                topic="TEST",
                agent_name=self.name,
                source_url="https://example.com/test",
                reasoning="Test reasoning",
                promotion_requirement="Test verification",
            )
            claims.append(claim)

            edge = ProposedEdge(
                proposal_id=self._generate_proposal_id(),
                from_node=fact.subject.lower().replace(" ", "_"),
                to_node=fact.object.lower().replace(" ", "_"),
                relationship=fact.predicate,
                agent_name=self.name,
                detail=f"Test edge detail",
                proposed_claim_id=proposal_id,
                confidence=0.8,
                reasoning="Test edge reasoning",
            )
            edges.append(edge)

        return claims, edges


class TestSchema(unittest.TestCase):
    """Test schema and staging tables."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.db = FGIPDatabase(self.db_path)
        self.db.init_schema()

    def tearDown(self):
        self.db.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_staging_tables_exist(self):
        """Verify all staging tables were created."""
        conn = self.db.connect()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = [t[0] for t in tables]

        required = [
            'proposed_claims',
            'proposed_edges',
            'correlation_metrics',
            'review_audit',
            'proposal_counter',
        ]

        for table in required:
            self.assertIn(table, table_names, f"Missing table: {table}")

    def test_proposed_claims_columns(self):
        """Verify proposed_claims has all required columns."""
        conn = self.db.connect()
        columns = conn.execute("PRAGMA table_info(proposed_claims)").fetchall()
        column_names = [c[1] for c in columns]

        required = [
            'proposal_id', 'claim_text', 'topic', 'agent_name',
            'source_url', 'artifact_path', 'artifact_hash',
            'reasoning', 'promotion_requirement', 'status',
            'resolved_claim_id', 'reviewer_notes', 'created_at', 'resolved_at'
        ]

        for col in required:
            self.assertIn(col, column_names, f"Missing column: {col}")

    def test_proposed_edges_columns(self):
        """Verify proposed_edges has all required columns."""
        conn = self.db.connect()
        columns = conn.execute("PRAGMA table_info(proposed_edges)").fetchall()
        column_names = [c[1] for c in columns]

        required = [
            'proposal_id', 'from_node', 'to_node', 'relationship',
            'detail', 'proposed_claim_id', 'agent_name', 'confidence',
            'reasoning', 'promotion_requirement', 'status',
            'resolved_edge_id', 'reviewer_notes', 'created_at', 'resolved_at'
        ]

        for col in required:
            self.assertIn(col, column_names, f"Missing column: {col}")


class TestAgentBase(unittest.TestCase):
    """Test FGIPAgent base class."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.db = FGIPDatabase(self.db_path)
        self.db.init_schema()
        self.agent = MockAgent(self.db)

    def tearDown(self):
        self.db.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_agent_name(self):
        """Test agent name property."""
        self.assertEqual(self.agent.name, "mock")
        self.assertEqual(self.agent.agent_name, "mock")

    def test_generate_proposal_id(self):
        """Test proposal ID generation."""
        id1 = self.agent._generate_proposal_id()
        id2 = self.agent._generate_proposal_id()

        self.assertTrue(id1.startswith("FGIP-PROPOSED-MOCK-"))
        self.assertTrue(id2.startswith("FGIP-PROPOSED-MOCK-"))
        self.assertNotEqual(id1, id2)

    def test_run_empty(self):
        """Test running agent with no data."""
        results = self.agent.run()

        self.assertEqual(results["agent"], "mock")
        self.assertEqual(results["artifacts_collected"], 0)
        self.assertEqual(results["facts_extracted"], 0)
        self.assertEqual(results["claims_proposed"], 0)
        self.assertEqual(results["edges_proposed"], 0)

    def test_run_with_data(self):
        """Test running agent with mock data."""
        # Set up mock data
        artifact = Artifact(
            url="https://example.com/test.pdf",
            artifact_type="pdf",
            local_path="/tmp/test.pdf",
        )
        artifact.content_hash = "abc123"

        fact = StructuredFact(
            fact_type="test",
            subject="Test Corp",
            predicate="OWNS_SHARES",
            object="Other Corp",
            source_artifact=artifact,
            confidence=0.9,
        )

        self.agent.mock_artifacts = [artifact]
        self.agent.mock_facts = [fact]

        results = self.agent.run()

        self.assertEqual(results["artifacts_collected"], 1)
        self.assertEqual(results["facts_extracted"], 1)
        self.assertEqual(results["claims_proposed"], 1)
        self.assertEqual(results["edges_proposed"], 1)

    def test_proposals_written_to_staging(self):
        """Test that proposals are written to staging tables."""
        artifact = Artifact(
            url="https://example.com/test.pdf",
            artifact_type="pdf",
        )
        artifact.content_hash = "abc123"

        fact = StructuredFact(
            fact_type="test",
            subject="Test Corp",
            predicate="OWNS_SHARES",
            object="Other Corp",
            source_artifact=artifact,
        )

        self.agent.mock_artifacts = [artifact]
        self.agent.mock_facts = [fact]

        self.agent.run()

        # Check staging tables
        conn = self.db.connect()

        claims = conn.execute(
            "SELECT * FROM proposed_claims WHERE agent_name = 'mock'"
        ).fetchall()
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["status"], "PENDING")

        edges = conn.execute(
            "SELECT * FROM proposed_edges WHERE agent_name = 'mock'"
        ).fetchall()
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["status"], "PENDING")

    def test_agent_status(self):
        """Test agent status reporting."""
        # Run agent with data
        artifact = Artifact(url="https://example.com/test.pdf", artifact_type="pdf")
        artifact.content_hash = "abc"
        fact = StructuredFact(
            fact_type="test", subject="A", predicate="REL", object="B",
            source_artifact=artifact
        )
        self.agent.mock_artifacts = [artifact]
        self.agent.mock_facts = [fact]
        self.agent.run()

        status = self.agent.get_status()

        self.assertEqual(status["agent"], "mock")
        self.assertEqual(status["pending_claims"], 1)
        self.assertEqual(status["pending_edges"], 1)
        self.assertEqual(status["approved_claims"], 0)
        self.assertEqual(status["rejected_claims"], 0)


class TestStaging(unittest.TestCase):
    """Test staging module functions."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.db = FGIPDatabase(self.db_path)
        self.db.init_schema()
        self.conn = self.db.connect()

        # Insert test proposal
        self.conn.execute("""
            INSERT INTO proposed_claims
            (proposal_id, claim_text, topic, agent_name, source_url, status, created_at)
            VALUES ('TEST-001', 'Test claim text', 'TEST', 'test_agent',
                    'https://example.com', 'PENDING', datetime('now'))
        """)
        self.conn.execute("""
            INSERT INTO proposed_edges
            (proposal_id, from_node, to_node, relationship, agent_name,
             confidence, status, created_at)
            VALUES ('TEST-002', 'node_a', 'node_b', 'RELATES_TO', 'test_agent',
                    0.75, 'PENDING', datetime('now'))
        """)
        self.conn.commit()

    def tearDown(self):
        self.db.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_get_pending_proposals(self):
        """Test fetching pending proposals."""
        proposals = staging.get_pending_proposals(self.conn)

        self.assertEqual(len(proposals["claims"]), 1)
        self.assertEqual(len(proposals["edges"]), 1)
        self.assertEqual(proposals["claims"][0]["proposal_id"], "TEST-001")
        self.assertEqual(proposals["edges"][0]["proposal_id"], "TEST-002")

    def test_get_pending_proposals_by_agent(self):
        """Test filtering by agent name."""
        proposals = staging.get_pending_proposals(self.conn, agent_name="test_agent")
        self.assertEqual(len(proposals["claims"]), 1)

        proposals = staging.get_pending_proposals(self.conn, agent_name="other_agent")
        self.assertEqual(len(proposals["claims"]), 0)

    def test_get_proposal_by_id(self):
        """Test fetching proposal by ID."""
        proposal = staging.get_proposal_by_id(self.conn, "TEST-001")

        self.assertIsNotNone(proposal)
        self.assertEqual(proposal["type"], "claim")
        self.assertEqual(proposal["claim_text"], "Test claim text")

        proposal = staging.get_proposal_by_id(self.conn, "TEST-002")
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal["type"], "edge")

        proposal = staging.get_proposal_by_id(self.conn, "NONEXISTENT")
        self.assertIsNone(proposal)

    def test_accept_claim(self):
        """Test accepting a claim proposal."""
        new_claim_id = staging.accept_claim(
            self.conn, "TEST-001",
            reviewer_notes="Verified",
            reviewer="test_reviewer"
        )

        self.assertIsNotNone(new_claim_id)
        self.assertTrue(new_claim_id.startswith("FGIP-"))

        # Check proposal updated
        proposal = staging.get_proposal_by_id(self.conn, "TEST-001")
        self.assertEqual(proposal["status"], "APPROVED")

        # Check claim created
        claim = self.db.get_claim(new_claim_id)
        self.assertIsNotNone(claim)
        self.assertIn("Test claim text", claim.claim_text)

        # Check audit trail
        audit = self.conn.execute(
            "SELECT * FROM review_audit WHERE proposal_id = 'TEST-001'"
        ).fetchone()
        self.assertIsNotNone(audit)
        self.assertEqual(audit["decision"], "APPROVED")

    def test_reject_proposal(self):
        """Test rejecting a proposal."""
        result = staging.reject_proposal(
            self.conn, "TEST-001",
            reason="Invalid source",
            reviewer="test_reviewer"
        )

        self.assertTrue(result)

        # Check proposal updated
        proposal = staging.get_proposal_by_id(self.conn, "TEST-001")
        self.assertEqual(proposal["status"], "REJECTED")
        self.assertEqual(proposal["reviewer_notes"], "Invalid source")

        # Check audit trail
        audit = self.conn.execute(
            "SELECT * FROM review_audit WHERE proposal_id = 'TEST-001'"
        ).fetchone()
        self.assertIsNotNone(audit)
        self.assertEqual(audit["decision"], "REJECTED")

    def test_cannot_accept_non_pending(self):
        """Test that non-pending proposals cannot be accepted."""
        # First reject
        staging.reject_proposal(self.conn, "TEST-001", reason="test")

        # Try to accept
        result = staging.accept_claim(self.conn, "TEST-001")
        self.assertIsNone(result)

    def test_get_agent_stats(self):
        """Test agent statistics."""
        stats = staging.get_agent_stats(self.conn)

        self.assertIn("test_agent", stats)
        self.assertEqual(stats["test_agent"]["pending_claims"], 1)
        self.assertEqual(stats["test_agent"]["pending_edges"], 1)


class TestCorrelationMetrics(unittest.TestCase):
    """Test correlation metrics computation."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.db = FGIPDatabase(self.db_path)
        self.db.init_schema()
        self.conn = self.db.connect()

        # Create test nodes
        node_a = Node(
            node_id="node_a", node_type=NodeType.ORGANIZATION,
            name="Organization A"
        )
        node_b = Node(
            node_id="node_b", node_type=NodeType.ORGANIZATION,
            name="Organization B"
        )
        self.db.insert_node(node_a)
        self.db.insert_node(node_b)

        # Insert test edge proposal
        self.conn.execute("""
            INSERT INTO proposed_edges
            (proposal_id, from_node, to_node, relationship, agent_name,
             confidence, status, created_at)
            VALUES ('EDGE-001', 'node_a', 'node_b', 'RELATES_TO', 'test',
                    0.75, 'PENDING', datetime('now'))
        """)

        # Insert test claim proposal
        self.conn.execute("""
            INSERT INTO proposed_claims
            (proposal_id, claim_text, topic, agent_name, status, created_at)
            VALUES ('CLAIM-001', 'Test claim about something', 'TEST', 'test',
                    'PENDING', datetime('now'))
        """)
        self.conn.commit()

    def tearDown(self):
        self.db.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_compute_edge_metrics(self):
        """Test computing metrics for edge proposal."""
        metrics = staging.compute_correlation_metrics(self.conn, "EDGE-001")

        self.assertIn("metrics", metrics)
        self.assertIn("source_overlap", metrics["metrics"])
        self.assertIn("path_distance", metrics["metrics"])
        self.assertIn("convergence_score", metrics["metrics"])

    def test_compute_claim_metrics(self):
        """Test computing metrics for claim proposal."""
        metrics = staging.compute_correlation_metrics(self.conn, "CLAIM-001")

        self.assertIn("metrics", metrics)
        self.assertIn("similar_claims", metrics["metrics"])

    def test_metrics_stored_in_db(self):
        """Test that computed metrics are stored."""
        staging.compute_correlation_metrics(self.conn, "EDGE-001")

        stored = self.conn.execute(
            "SELECT * FROM correlation_metrics WHERE proposal_id = 'EDGE-001'"
        ).fetchall()

        self.assertGreater(len(stored), 0)


class TestDataClasses(unittest.TestCase):
    """Test data classes."""

    def test_artifact(self):
        """Test Artifact dataclass."""
        artifact = Artifact(
            url="https://example.com/file.pdf",
            artifact_type="pdf",
            local_path="/tmp/file.pdf",
        )

        self.assertIsNotNone(artifact.fetched_at)
        self.assertEqual(artifact.artifact_type, "pdf")

        # Test hash computation
        test_content = b"test content"
        hash_val = artifact.compute_hash(test_content)
        self.assertEqual(len(hash_val), 64)  # SHA256 hex

        # Test to_dict
        data = artifact.to_dict()
        self.assertIn("url", data)
        self.assertIn("content_hash", data)

    def test_structured_fact(self):
        """Test StructuredFact dataclass."""
        artifact = Artifact(url="https://example.com", artifact_type="html")

        fact = StructuredFact(
            fact_type="ownership",
            subject="Corp A",
            predicate="OWNS",
            object="Corp B",
            source_artifact=artifact,
            confidence=0.9,
        )

        self.assertIsNotNone(fact.date_extracted)
        self.assertEqual(fact.confidence, 0.9)

        data = fact.to_dict()
        self.assertEqual(data["subject"], "Corp A")
        self.assertEqual(data["source_url"], "https://example.com")

    def test_proposed_claim(self):
        """Test ProposedClaim dataclass."""
        claim = ProposedClaim(
            proposal_id="TEST-001",
            claim_text="Test claim",
            topic="TEST",
            agent_name="test",
            source_url="https://example.com",
        )

        self.assertIsNotNone(claim.created_at)

        data = claim.to_dict()
        self.assertEqual(data["proposal_id"], "TEST-001")
        self.assertEqual(data["topic"], "TEST")

    def test_proposed_edge(self):
        """Test ProposedEdge dataclass."""
        edge = ProposedEdge(
            proposal_id="EDGE-001",
            from_node="node_a",
            to_node="node_b",
            relationship="OWNS_SHARES",
            agent_name="test",
            confidence=0.8,
        )

        self.assertIsNotNone(edge.created_at)
        self.assertEqual(edge.confidence, 0.8)

        data = edge.to_dict()
        self.assertEqual(data["from_node"], "node_a")
        self.assertEqual(data["relationship"], "OWNS_SHARES")


class TestAgentImports(unittest.TestCase):
    """Test that all agents can be imported."""

    def test_import_edgar(self):
        """Test EDGARAgent import."""
        from fgip.agents.edgar import EDGARAgent
        self.assertTrue(callable(EDGARAgent))

    def test_import_scotus(self):
        """Test SCOTUSAgent import."""
        from fgip.agents.scotus import SCOTUSAgent
        self.assertTrue(callable(SCOTUSAgent))

    def test_import_gao(self):
        """Test GAOAgent import."""
        from fgip.agents.gao import GAOAgent
        self.assertTrue(callable(GAOAgent))

    def test_import_rss(self):
        """Test RSSSignalAgent import."""
        from fgip.agents.rss_signal import RSSSignalAgent
        self.assertTrue(callable(RSSSignalAgent))

    def test_import_from_package(self):
        """Test imports from agents package."""
        from fgip.agents import (
            FGIPAgent, Artifact, StructuredFact,
            ProposedClaim, ProposedEdge,
            EDGARAgent, SCOTUSAgent, GAOAgent, RSSSignalAgent
        )
        self.assertTrue(callable(FGIPAgent))
        self.assertTrue(callable(EDGARAgent))


class TestAgentInstantiation(unittest.TestCase):
    """Test that agents can be instantiated."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.db = FGIPDatabase(self.db_path)
        self.db.init_schema()

    def tearDown(self):
        self.db.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_edgar_agent(self):
        """Test EDGARAgent instantiation."""
        from fgip.agents.edgar import EDGARAgent
        agent = EDGARAgent(self.db)
        self.assertEqual(agent.name, "edgar")

    def test_scotus_agent(self):
        """Test SCOTUSAgent instantiation."""
        from fgip.agents.scotus import SCOTUSAgent
        agent = SCOTUSAgent(self.db)
        self.assertEqual(agent.name, "scotus")

    def test_gao_agent(self):
        """Test GAOAgent instantiation."""
        from fgip.agents.gao import GAOAgent
        agent = GAOAgent(self.db)
        self.assertEqual(agent.name, "gao")

    def test_rss_agent(self):
        """Test RSSSignalAgent instantiation."""
        from fgip.agents.rss_signal import RSSSignalAgent
        agent = RSSSignalAgent(self.db)
        self.assertEqual(agent.name, "rss")


if __name__ == "__main__":
    unittest.main(verbosity=2)
