"""
FGIP Leak Detector - Invariant checker for pipeline health.

The "pressure gauge" that catches when data flows around the filter.

Detects:
1. Proposals with NULL evidence_span (should have evidence)
2. Proposals with NULL reason_codes (should have provenance)
3. Orphan proposals (artifact_id not in artifact_queue)
4. Bypass writes (proposals from non-pipeline sources)
5. FK violations (edges referencing missing nodes)

Usage:
    from fgip.pipeline.leak_detector import LeakDetector

    detector = LeakDetector("fgip.db")
    report = detector.check_invariants()

    if report.total_leaks > 0:
        print(f"DEGRADED: {report.total_leaks} leaks detected")
"""

import json
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class LeakReport:
    """Report from invariant checking."""
    timestamp: str
    check_id: str

    # Leak counts
    leak_1_no_evidence: int       # proposals with evidence_span IS NULL
    leak_2_no_reason_codes: int   # proposals with reason_codes IS NULL
    leak_3_orphan_proposals: int  # proposals whose artifact_id not in artifact_queue
    leak_4_bypass_writes: int     # proposals not from allowed agents
    leak_5_fk_violations: int     # edges referencing missing nodes

    # Totals
    total_leaks: int
    total_proposals_checked: int

    # Health status
    health_status: str  # GREEN (0), DEGRADED (>0), CRITICAL (>100)

    # Details for debugging
    leak_1_samples: List[str] = field(default_factory=list)
    leak_2_samples: List[str] = field(default_factory=list)
    leak_3_samples: List[str] = field(default_factory=list)
    leak_4_samples: List[str] = field(default_factory=list)
    leak_5_samples: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Agents that are allowed to create proposals without full pipeline
ALLOWED_BYPASS_AGENTS = {
    "reasoning-agent",      # Graph inference
    "genius-edge-stager",   # Manual staging
    "correction-loader",    # Correction manifests
    "gapfill-loader",       # Gap fill manifests
    "manual",               # Manual imports
}


# =============================================================================
# LEAK DETECTOR
# =============================================================================

class LeakDetector:
    """
    Invariant checker - detects when data bypasses the pipeline.

    Run after each processing cycle to catch leaks.
    """

    def __init__(self, db_path: str = "fgip.db"):
        self.db_path = Path(db_path)

    def _get_db(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def check_invariants(self, sample_limit: int = 5) -> LeakReport:
        """
        Run all invariant checks and return a leak report.

        Args:
            sample_limit: Max samples to include per leak type

        Returns:
            LeakReport with leak counts and health status
        """
        check_id = f"check-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        conn = self._get_db()

        try:
            # Total proposals being checked
            total_claims = conn.execute(
                "SELECT COUNT(*) FROM proposed_claims WHERE status = 'PENDING'"
            ).fetchone()[0]
            total_edges = conn.execute(
                "SELECT COUNT(*) FROM proposed_edges WHERE status = 'PENDING'"
            ).fetchone()[0]
            total_proposals = total_claims + total_edges

            # Leak 1: Proposals with NULL evidence_span (excluding bypass agents)
            leak_1_count, leak_1_samples = self._check_no_evidence(conn, sample_limit)

            # Leak 2: Proposals with NULL reason_codes
            leak_2_count, leak_2_samples = self._check_no_reason_codes(conn, sample_limit)

            # Leak 3: Orphan proposals (artifact_id set but not in artifact_queue)
            leak_3_count, leak_3_samples = self._check_orphan_artifacts(conn, sample_limit)

            # Leak 4: Bypass writes (from non-allowed agents without bypass_pipeline=1)
            leak_4_count, leak_4_samples = self._check_bypass_writes(conn, sample_limit)

            # Leak 5: FK violations (edges referencing missing nodes)
            leak_5_count, leak_5_samples = self._check_fk_violations(conn, sample_limit)

            total_leaks = leak_1_count + leak_2_count + leak_3_count + leak_4_count + leak_5_count

            # Determine health status
            if total_leaks == 0:
                health_status = "GREEN"
            elif total_leaks < 100:
                health_status = "DEGRADED"
            else:
                health_status = "CRITICAL"

            return LeakReport(
                timestamp=datetime.now().isoformat(),
                check_id=check_id,
                leak_1_no_evidence=leak_1_count,
                leak_2_no_reason_codes=leak_2_count,
                leak_3_orphan_proposals=leak_3_count,
                leak_4_bypass_writes=leak_4_count,
                leak_5_fk_violations=leak_5_count,
                total_leaks=total_leaks,
                total_proposals_checked=total_proposals,
                health_status=health_status,
                leak_1_samples=leak_1_samples,
                leak_2_samples=leak_2_samples,
                leak_3_samples=leak_3_samples,
                leak_4_samples=leak_4_samples,
                leak_5_samples=leak_5_samples,
            )

        finally:
            conn.close()

    def _check_no_evidence(self, conn: sqlite3.Connection, limit: int) -> tuple[int, List[str]]:
        """Check for proposals missing evidence_span."""
        # Build agent exclusion clause
        agent_placeholders = ",".join("?" * len(ALLOWED_BYPASS_AGENTS))

        # Check claims
        claim_count = conn.execute(f"""
            SELECT COUNT(*) FROM proposed_claims
            WHERE status = 'PENDING'
            AND evidence_span IS NULL
            AND LOWER(agent_name) NOT IN ({agent_placeholders})
            AND (bypass_pipeline IS NULL OR bypass_pipeline = 0)
        """, tuple(ALLOWED_BYPASS_AGENTS)).fetchone()[0]

        # Check edges
        edge_count = conn.execute(f"""
            SELECT COUNT(*) FROM proposed_edges
            WHERE status = 'PENDING'
            AND evidence_span IS NULL
            AND LOWER(agent_name) NOT IN ({agent_placeholders})
            AND (bypass_pipeline IS NULL OR bypass_pipeline = 0)
        """, tuple(ALLOWED_BYPASS_AGENTS)).fetchone()[0]

        total = claim_count + edge_count

        # Get samples
        samples = []
        rows = conn.execute(f"""
            SELECT proposal_id, agent_name, 'claim' as type FROM proposed_claims
            WHERE status = 'PENDING'
            AND evidence_span IS NULL
            AND LOWER(agent_name) NOT IN ({agent_placeholders})
            AND (bypass_pipeline IS NULL OR bypass_pipeline = 0)
            LIMIT ?
        """, tuple(ALLOWED_BYPASS_AGENTS) + (limit,)).fetchall()

        for row in rows:
            samples.append(f"{row['proposal_id']} ({row['agent_name']})")

        return total, samples

    def _check_no_reason_codes(self, conn: sqlite3.Connection, limit: int) -> tuple[int, List[str]]:
        """Check for proposals missing reason_codes."""
        agent_placeholders = ",".join("?" * len(ALLOWED_BYPASS_AGENTS))

        # Check claims
        claim_count = conn.execute(f"""
            SELECT COUNT(*) FROM proposed_claims
            WHERE status = 'PENDING'
            AND reason_codes IS NULL
            AND LOWER(agent_name) NOT IN ({agent_placeholders})
            AND (bypass_pipeline IS NULL OR bypass_pipeline = 0)
        """, tuple(ALLOWED_BYPASS_AGENTS)).fetchone()[0]

        # Check edges
        edge_count = conn.execute(f"""
            SELECT COUNT(*) FROM proposed_edges
            WHERE status = 'PENDING'
            AND reason_codes IS NULL
            AND LOWER(agent_name) NOT IN ({agent_placeholders})
            AND (bypass_pipeline IS NULL OR bypass_pipeline = 0)
        """, tuple(ALLOWED_BYPASS_AGENTS)).fetchone()[0]

        total = claim_count + edge_count

        # Get samples
        samples = []
        rows = conn.execute(f"""
            SELECT proposal_id, agent_name FROM proposed_claims
            WHERE status = 'PENDING'
            AND reason_codes IS NULL
            AND LOWER(agent_name) NOT IN ({agent_placeholders})
            AND (bypass_pipeline IS NULL OR bypass_pipeline = 0)
            LIMIT ?
        """, tuple(ALLOWED_BYPASS_AGENTS) + (limit,)).fetchall()

        for row in rows:
            samples.append(f"{row['proposal_id']} ({row['agent_name']})")

        return total, samples

    def _check_orphan_artifacts(self, conn: sqlite3.Connection, limit: int) -> tuple[int, List[str]]:
        """Check for proposals with artifact_id not in artifact_queue."""
        # Claims with artifact_id that doesn't exist in artifact_queue
        claim_count = conn.execute("""
            SELECT COUNT(*) FROM proposed_claims pc
            LEFT JOIN artifact_queue aq ON pc.artifact_id = aq.artifact_id
            WHERE pc.status = 'PENDING'
            AND pc.artifact_id IS NOT NULL
            AND aq.artifact_id IS NULL
        """).fetchone()[0]

        # Edges with artifact_id that doesn't exist
        edge_count = conn.execute("""
            SELECT COUNT(*) FROM proposed_edges pe
            LEFT JOIN artifact_queue aq ON pe.artifact_id = aq.artifact_id
            WHERE pe.status = 'PENDING'
            AND pe.artifact_id IS NOT NULL
            AND aq.artifact_id IS NULL
        """).fetchone()[0]

        total = claim_count + edge_count

        # Get samples
        samples = []
        rows = conn.execute("""
            SELECT pc.proposal_id, pc.artifact_id FROM proposed_claims pc
            LEFT JOIN artifact_queue aq ON pc.artifact_id = aq.artifact_id
            WHERE pc.status = 'PENDING'
            AND pc.artifact_id IS NOT NULL
            AND aq.artifact_id IS NULL
            LIMIT ?
        """, (limit,)).fetchall()

        for row in rows:
            samples.append(f"{row['proposal_id']} (artifact: {row['artifact_id']})")

        return total, samples

    def _check_bypass_writes(self, conn: sqlite3.Connection, limit: int) -> tuple[int, List[str]]:
        """Check for proposals from non-allowed agents without bypass flag."""
        # This detects proposals that should have gone through pipeline but didn't
        # We check for proposals that:
        # 1. Are not from allowed bypass agents
        # 2. Don't have bypass_pipeline=1
        # 3. Don't have artifact_id (meaning they bypassed artifact_queue)
        # 4. Don't have se_score (meaning they bypassed NLP)

        agent_placeholders = ",".join("?" * len(ALLOWED_BYPASS_AGENTS))

        claim_count = conn.execute(f"""
            SELECT COUNT(*) FROM proposed_claims
            WHERE status = 'PENDING'
            AND LOWER(agent_name) NOT IN ({agent_placeholders})
            AND (bypass_pipeline IS NULL OR bypass_pipeline = 0)
            AND artifact_id IS NULL
            AND se_score IS NULL
        """, tuple(ALLOWED_BYPASS_AGENTS)).fetchone()[0]

        edge_count = conn.execute(f"""
            SELECT COUNT(*) FROM proposed_edges
            WHERE status = 'PENDING'
            AND LOWER(agent_name) NOT IN ({agent_placeholders})
            AND (bypass_pipeline IS NULL OR bypass_pipeline = 0)
            AND artifact_id IS NULL
            AND se_score IS NULL
        """, tuple(ALLOWED_BYPASS_AGENTS)).fetchone()[0]

        total = claim_count + edge_count

        # Get samples
        samples = []
        rows = conn.execute(f"""
            SELECT proposal_id, agent_name FROM proposed_claims
            WHERE status = 'PENDING'
            AND LOWER(agent_name) NOT IN ({agent_placeholders})
            AND (bypass_pipeline IS NULL OR bypass_pipeline = 0)
            AND artifact_id IS NULL
            AND se_score IS NULL
            LIMIT ?
        """, tuple(ALLOWED_BYPASS_AGENTS) + (limit,)).fetchall()

        for row in rows:
            samples.append(f"{row['proposal_id']} (agent: {row['agent_name']})")

        return total, samples

    def _check_fk_violations(self, conn: sqlite3.Connection, limit: int) -> tuple[int, List[str]]:
        """Check for edges referencing non-existent nodes."""
        # Check from_node violations
        from_violations = conn.execute("""
            SELECT COUNT(*) FROM proposed_edges pe
            LEFT JOIN nodes n ON pe.from_node = n.node_id
            WHERE pe.status = 'PENDING'
            AND n.node_id IS NULL
        """).fetchone()[0]

        # Check to_node violations
        to_violations = conn.execute("""
            SELECT COUNT(*) FROM proposed_edges pe
            LEFT JOIN nodes n ON pe.to_node = n.node_id
            WHERE pe.status = 'PENDING'
            AND n.node_id IS NULL
        """).fetchone()[0]

        total = from_violations + to_violations

        # Get samples
        samples = []
        rows = conn.execute("""
            SELECT pe.proposal_id, pe.from_node, pe.to_node,
                   (SELECT COUNT(*) FROM nodes WHERE node_id = pe.from_node) as from_exists,
                   (SELECT COUNT(*) FROM nodes WHERE node_id = pe.to_node) as to_exists
            FROM proposed_edges pe
            WHERE pe.status = 'PENDING'
            AND (
                pe.from_node NOT IN (SELECT node_id FROM nodes)
                OR pe.to_node NOT IN (SELECT node_id FROM nodes)
            )
            LIMIT ?
        """, (limit,)).fetchall()

        for row in rows:
            missing = []
            if row['from_exists'] == 0:
                missing.append(f"from:{row['from_node']}")
            if row['to_exists'] == 0:
                missing.append(f"to:{row['to_node']}")
            samples.append(f"{row['proposal_id']} (missing: {', '.join(missing)})")

        return total, samples

    def log_report(self, report: LeakReport) -> None:
        """Log a leak report to the database."""
        conn = self._get_db()
        try:
            conn.execute("""
                INSERT INTO leak_reports (
                    check_id, timestamp, total_leaks, health_status,
                    leak_1, leak_2, leak_3, leak_4, leak_5,
                    total_checked, report_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                report.check_id,
                report.timestamp,
                report.total_leaks,
                report.health_status,
                report.leak_1_no_evidence,
                report.leak_2_no_reason_codes,
                report.leak_3_orphan_proposals,
                report.leak_4_bypass_writes,
                report.leak_5_fk_violations,
                report.total_proposals_checked,
                json.dumps(report.as_dict())
            ))
            conn.commit()
        except sqlite3.OperationalError:
            # Table doesn't exist yet - create it
            conn.execute("""
                CREATE TABLE IF NOT EXISTS leak_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    check_id TEXT UNIQUE,
                    timestamp TEXT,
                    total_leaks INTEGER,
                    health_status TEXT,
                    leak_1 INTEGER,
                    leak_2 INTEGER,
                    leak_3 INTEGER,
                    leak_4 INTEGER,
                    leak_5 INTEGER,
                    total_checked INTEGER,
                    report_json TEXT
                )
            """)
            # Retry insert
            conn.execute("""
                INSERT INTO leak_reports (
                    check_id, timestamp, total_leaks, health_status,
                    leak_1, leak_2, leak_3, leak_4, leak_5,
                    total_checked, report_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                report.check_id,
                report.timestamp,
                report.total_leaks,
                report.health_status,
                report.leak_1_no_evidence,
                report.leak_2_no_reason_codes,
                report.leak_3_orphan_proposals,
                report.leak_4_bypass_writes,
                report.leak_5_fk_violations,
                report.total_proposals_checked,
                json.dumps(report.as_dict())
            ))
            conn.commit()
        finally:
            conn.close()


# =============================================================================
# CLI
# =============================================================================

def format_report(report: LeakReport) -> str:
    """Format leak report for display."""
    lines = []
    lines.append(f"\n{'='*60}")
    lines.append(f"LEAK DETECTOR REPORT: {report.check_id}")
    lines.append(f"{'='*60}")
    lines.append(f"Timestamp: {report.timestamp}")
    lines.append(f"Proposals checked: {report.total_proposals_checked}")
    lines.append(f"\nHealth Status: {report.health_status}")
    lines.append(f"Total Leaks: {report.total_leaks}")

    lines.append(f"\n--- Leak Breakdown ---")
    lines.append(f"  [1] No evidence_span:    {report.leak_1_no_evidence}")
    lines.append(f"  [2] No reason_codes:     {report.leak_2_no_reason_codes}")
    lines.append(f"  [3] Orphan artifact_id:  {report.leak_3_orphan_proposals}")
    lines.append(f"  [4] Bypass writes:       {report.leak_4_bypass_writes}")
    lines.append(f"  [5] FK violations:       {report.leak_5_fk_violations}")

    if report.total_leaks > 0:
        lines.append(f"\n--- Samples ---")

        if report.leak_1_samples:
            lines.append(f"\n[1] No evidence:")
            for s in report.leak_1_samples[:3]:
                lines.append(f"    - {s}")

        if report.leak_2_samples:
            lines.append(f"\n[2] No reason_codes:")
            for s in report.leak_2_samples[:3]:
                lines.append(f"    - {s}")

        if report.leak_3_samples:
            lines.append(f"\n[3] Orphan artifacts:")
            for s in report.leak_3_samples[:3]:
                lines.append(f"    - {s}")

        if report.leak_4_samples:
            lines.append(f"\n[4] Bypass writes:")
            for s in report.leak_4_samples[:3]:
                lines.append(f"    - {s}")

        if report.leak_5_samples:
            lines.append(f"\n[5] FK violations:")
            for s in report.leak_5_samples[:3]:
                lines.append(f"    - {s}")

    lines.append(f"\n{'='*60}")

    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    detector = LeakDetector()

    if len(sys.argv) > 1:
        cmd = sys.argv[1]

        if cmd == "check":
            report = detector.check_invariants()
            print(format_report(report))

        elif cmd == "json":
            report = detector.check_invariants()
            print(json.dumps(report.as_dict(), indent=2))

        elif cmd == "log":
            report = detector.check_invariants()
            detector.log_report(report)
            print(f"Report logged: {report.check_id}")
            print(f"Health: {report.health_status}, Leaks: {report.total_leaks}")

        else:
            print(f"Unknown command: {cmd}")

    else:
        print("Usage:")
        print("  python -m fgip.pipeline.leak_detector check  # Run check, print report")
        print("  python -m fgip.pipeline.leak_detector json   # Output as JSON")
        print("  python -m fgip.pipeline.leak_detector log    # Run check and log to DB")
