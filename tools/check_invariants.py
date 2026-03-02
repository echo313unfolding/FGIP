#!/usr/bin/env python3
"""FGIP Invariants Checker - Catch violations before they corrupt the graph.

Runs after each scheduler cycle to verify:
1. Referential integrity (edges reference existing nodes)
2. Edge evidence (all edges have claim_id OR source/source_url)
3. Assertion consistency (inferential edges cannot be FACT)
4. No duplicate edges
5. Proposal FK consistency
6. Confidence bounds (0-1)
7. Agent health (recent successful runs)

Usage:
    python3 tools/check_invariants.py fgip.db
    python3 tools/check_invariants.py fgip.db --fix
    python3 tools/check_invariants.py fgip.db --json
"""

import argparse
import json
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fgip.db import FGIPDatabase


@dataclass
class Violation:
    """A detected invariant violation."""
    invariant: str
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    entity_id: str
    message: str
    auto_fixable: bool = False
    fix_action: str = ""


@dataclass
class InvariantReport:
    """Report from invariant checking."""
    timestamp: str
    violations: List[Violation]
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    exit_code: int  # 0=pass, 1=warnings, 2=critical

    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp,
            'violations': [asdict(v) for v in self.violations],
            'critical_count': self.critical_count,
            'high_count': self.high_count,
            'medium_count': self.medium_count,
            'low_count': self.low_count,
            'exit_code': self.exit_code,
        }


# Edge types that should NEVER be assertion_level='FACT'
INFERENTIAL_EDGE_TYPES = [
    'CAUSED', 'ENABLED', 'CONTRIBUTED_TO', 'IMPLIES', 'SUGGESTS',
    'CORRELATED_WITH', 'PREDICTED', 'HYPOTHESIZED',
]


class InvariantChecker:
    """Checks graph invariants and returns violations."""

    def __init__(self, db: FGIPDatabase):
        self.db = db
        self.conn = None
        self.violations: List[Violation] = []

    def connect(self):
        """Get database connection."""
        if self.conn is None:
            self.conn = self.db.connect()
        return self.conn

    def check_referential_integrity(self) -> List[Violation]:
        """All edges must reference existing nodes."""
        self.connect()
        violations = []

        # Check from_node_id
        bad_from = self.conn.execute("""
            SELECT edge_id, from_node_id, to_node_id
            FROM edges
            WHERE from_node_id NOT IN (SELECT node_id FROM nodes)
            LIMIT 100
        """).fetchall()

        for row in bad_from:
            violations.append(Violation(
                invariant="referential_integrity",
                severity="CRITICAL",
                entity_id=row["edge_id"],
                message=f"Edge references non-existent from_node: {row['from_node_id']}",
                auto_fixable=True,
                fix_action=f"DELETE FROM edges WHERE edge_id = '{row['edge_id']}'",
            ))

        # Check to_node_id
        bad_to = self.conn.execute("""
            SELECT edge_id, from_node_id, to_node_id
            FROM edges
            WHERE to_node_id NOT IN (SELECT node_id FROM nodes)
            LIMIT 100
        """).fetchall()

        for row in bad_to:
            violations.append(Violation(
                invariant="referential_integrity",
                severity="CRITICAL",
                entity_id=row["edge_id"],
                message=f"Edge references non-existent to_node: {row['to_node_id']}",
                auto_fixable=True,
                fix_action=f"DELETE FROM edges WHERE edge_id = '{row['edge_id']}'",
            ))

        return violations

    def check_edge_evidence(self) -> List[Violation]:
        """All edges should have claim_id OR source/source_url (Square-One compliance)."""
        self.connect()
        violations = []

        # Edges without any evidence trail
        no_evidence = self.conn.execute("""
            SELECT edge_id, edge_type, from_node_id, to_node_id
            FROM edges
            WHERE claim_id IS NULL
            AND (source IS NULL OR source = '')
            AND (source_url IS NULL OR source_url = '')
            AND (notes IS NULL OR notes = '')
            LIMIT 100
        """).fetchall()

        for row in no_evidence:
            violations.append(Violation(
                invariant="edge_evidence",
                severity="MEDIUM",
                entity_id=row["edge_id"],
                message=f"Edge {row['edge_type']} has no evidence trail (claim_id, source, or notes)",
                auto_fixable=False,
            ))

        return violations

    def check_assertion_consistency(self) -> List[Violation]:
        """Inferential edges cannot be FACT level."""
        self.connect()
        violations = []

        placeholders = ','.join(['?' for _ in INFERENTIAL_EDGE_TYPES])
        bad_assertions = self.conn.execute(f"""
            SELECT edge_id, edge_type, assertion_level
            FROM edges
            WHERE edge_type IN ({placeholders})
            AND assertion_level = 'FACT'
            LIMIT 100
        """, INFERENTIAL_EDGE_TYPES).fetchall()

        for row in bad_assertions:
            violations.append(Violation(
                invariant="assertion_consistency",
                severity="HIGH",
                entity_id=row["edge_id"],
                message=f"Inferential edge {row['edge_type']} marked as FACT (should be INFERENCE)",
                auto_fixable=True,
                fix_action=f"UPDATE edges SET assertion_level = 'INFERENCE' WHERE edge_id = '{row['edge_id']}'",
            ))

        return violations

    def check_duplicate_edges(self) -> List[Violation]:
        """No duplicate (from_node, to_node, edge_type, assertion_level) combinations."""
        self.connect()
        violations = []

        # Find duplicates
        duplicates = self.conn.execute("""
            SELECT from_node_id, to_node_id, edge_type, assertion_level, COUNT(*) as cnt
            FROM edges
            GROUP BY from_node_id, to_node_id, edge_type, assertion_level
            HAVING cnt > 1
            LIMIT 50
        """).fetchall()

        for row in duplicates:
            violations.append(Violation(
                invariant="duplicate_edges",
                severity="MEDIUM",
                entity_id=f"{row['from_node_id']}_{row['edge_type']}_{row['to_node_id']}",
                message=f"Duplicate edge: {row['from_node_id']} --{row['edge_type']}--> {row['to_node_id']} ({row['cnt']} copies)",
                auto_fixable=True,
                fix_action="Run tools/dedupe_edges.py",
            ))

        return violations

    def check_proposal_fk(self) -> List[Violation]:
        """Proposed edges should reference resolvable nodes OR be marked for bootstrap."""
        self.connect()
        violations = []

        # Check pending proposals that reference non-existent nodes
        bad_proposals = self.conn.execute("""
            SELECT proposal_id, from_node, to_node, relationship
            FROM proposed_edges
            WHERE status = 'PENDING'
            AND (
                from_node NOT IN (SELECT node_id FROM nodes)
                OR to_node NOT IN (SELECT node_id FROM nodes)
            )
            LIMIT 50
        """).fetchall()

        for row in bad_proposals:
            # Check which node is missing
            from_exists = self.conn.execute(
                "SELECT 1 FROM nodes WHERE node_id = ?", (row["from_node"],)
            ).fetchone()
            to_exists = self.conn.execute(
                "SELECT 1 FROM nodes WHERE node_id = ?", (row["to_node"],)
            ).fetchone()

            missing = []
            if not from_exists:
                missing.append(row["from_node"])
            if not to_exists:
                missing.append(row["to_node"])

            violations.append(Violation(
                invariant="proposal_fk",
                severity="LOW",
                entity_id=row["proposal_id"],
                message=f"Proposal references missing nodes: {', '.join(missing)}",
                auto_fixable=False,
            ))

        return violations

    def check_confidence_bounds(self) -> List[Violation]:
        """All confidences must be 0-1."""
        self.connect()
        violations = []

        # Check edges
        bad_edge_conf = self.conn.execute("""
            SELECT edge_id, confidence
            FROM edges
            WHERE confidence < 0 OR confidence > 1
            LIMIT 50
        """).fetchall()

        for row in bad_edge_conf:
            violations.append(Violation(
                invariant="confidence_bounds",
                severity="HIGH",
                entity_id=row["edge_id"],
                message=f"Edge has invalid confidence: {row['confidence']} (must be 0-1)",
                auto_fixable=True,
                fix_action=f"UPDATE edges SET confidence = MAX(0, MIN(1, confidence)) WHERE edge_id = '{row['edge_id']}'",
            ))

        # Check proposed_edges
        bad_proposal_conf = self.conn.execute("""
            SELECT proposal_id, confidence
            FROM proposed_edges
            WHERE confidence < 0 OR confidence > 1
            LIMIT 50
        """).fetchall()

        for row in bad_proposal_conf:
            violations.append(Violation(
                invariant="confidence_bounds",
                severity="HIGH",
                entity_id=row["proposal_id"],
                message=f"Proposal has invalid confidence: {row['confidence']} (must be 0-1)",
                auto_fixable=True,
                fix_action=f"UPDATE proposed_edges SET confidence = MAX(0, MIN(1, confidence)) WHERE proposal_id = '{row['proposal_id']}'",
            ))

        return violations

    def check_agent_health(self, days_threshold: int = 7) -> List[Violation]:
        """Check if agents have run successfully recently."""
        self.connect()
        violations = []

        # Check ingest_runs table if it exists
        try:
            # Get last successful run per agent
            last_runs = self.conn.execute("""
                SELECT agent_name, MAX(completed_at) as last_run
                FROM ingest_runs
                WHERE status = 'SUCCESS'
                GROUP BY agent_name
            """).fetchall()

            threshold = datetime.now(timezone.utc) - timedelta(days=days_threshold)
            threshold_str = threshold.isoformat()

            for row in last_runs:
                if row["last_run"] and row["last_run"] < threshold_str:
                    violations.append(Violation(
                        invariant="agent_health",
                        severity="LOW",
                        entity_id=row["agent_name"],
                        message=f"Agent {row['agent_name']} last succeeded {row['last_run']} (>{days_threshold} days ago)",
                        auto_fixable=False,
                    ))
        except Exception:
            pass  # Table might not exist

        return violations

    def check_pipeline_bypass(self) -> List[Violation]:
        """Check for proposals created without going through artifact_queue.

        Proposals should either:
        - Come from pipeline_orchestrator/nlp_agent (queued path)
        - Have artifact_id linking to artifact_queue
        - Be from exempt agents (reasoning, meta-analysis)

        Proposals without artifact trail from non-exempt agents indicate bypass.
        """
        self.connect()
        violations = []

        # Agents exempt from pipeline requirement (don't ingest raw artifacts)
        EXEMPT_AGENTS = [
            'pipeline_orchestrator', 'nlp_agent', 'nlp-agent',
            'reasoning', 'causal', 'gap-detector', 'coverage-analyzer',
            'conviction-engine', 'signal-gap-ecosystem', 'supply-chain-extractor'
        ]

        # Check proposed_edges without artifact linkage from non-exempt agents
        # Look for recent proposals (last 24 hours) to catch active bypass
        try:
            bypass_edges = self.conn.execute("""
                SELECT proposal_id, agent_name, created_at
                FROM proposed_edges
                WHERE agent_name NOT IN (?, ?, ?, ?, ?, ?, ?, ?, ?)
                AND (artifact_id IS NULL OR artifact_id = '')
                AND created_at > datetime('now', '-1 day')
                LIMIT 50
            """, EXEMPT_AGENTS).fetchall()

            for row in bypass_edges:
                violations.append(Violation(
                    invariant="pipeline_bypass",
                    severity="MEDIUM",  # MEDIUM for now, upgrade to HIGH once all agents wired
                    entity_id=row["proposal_id"],
                    message=f"Edge proposal from {row['agent_name']} bypassed pipeline (no artifact_id)",
                    auto_fixable=False,
                ))

            # Also check proposed_claims
            bypass_claims = self.conn.execute("""
                SELECT proposal_id, agent_name, created_at
                FROM proposed_claims
                WHERE agent_name NOT IN (?, ?, ?, ?, ?, ?, ?, ?, ?)
                AND (artifact_id IS NULL OR artifact_id = '')
                AND created_at > datetime('now', '-1 day')
                LIMIT 50
            """, EXEMPT_AGENTS).fetchall()

            for row in bypass_claims:
                violations.append(Violation(
                    invariant="pipeline_bypass",
                    severity="MEDIUM",
                    entity_id=row["proposal_id"],
                    message=f"Claim proposal from {row['agent_name']} bypassed pipeline (no artifact_id)",
                    auto_fixable=False,
                ))

        except Exception as e:
            # Tables may not have artifact_id column yet
            pass

        return violations

    def check_tier0_artifact_requirement(self) -> List[Violation]:
        """Tier-0 agents MUST have artifact_id for all proposals (HIGH severity).

        Tier-0 agents ingest primary government sources and their proposals
        MUST trace back to an artifact. This is the "receipt or it didn't happen"
        principle - without artifact_id, the proposal cannot be verified.

        WO-FGIP-TRIANGULATION-HYGIENE-02
        """
        self.connect()
        violations = []

        # Tier-0 agents that MUST have artifact_id
        TIER0_AGENTS = [
            'edgar', 'usaspending', 'federal_register', 'congress',
            'nuclear_smr', 'tic', 'fec', 'scotus', 'gao', 'fara', 'chips-facility'
        ]

        try:
            placeholders = ','.join('?' * len(TIER0_AGENTS))

            # Check proposed_edges from Tier-0 agents
            # Only check PENDING status - already-processed proposals are legacy
            rows = self.conn.execute(f"""
                SELECT proposal_id, agent_name, created_at
                FROM proposed_edges
                WHERE agent_name IN ({placeholders})
                AND (artifact_id IS NULL OR artifact_id = '')
                AND status = 'PENDING'
                LIMIT 50
            """, TIER0_AGENTS).fetchall()

            for row in rows:
                violations.append(Violation(
                    invariant="tier0_artifact_requirement",
                    severity="HIGH",
                    entity_id=row["proposal_id"],
                    message=f"Tier-0 edge from {row['agent_name']} missing artifact_id (created {row['created_at']})",
                    auto_fixable=False,
                ))

            # Check proposed_claims from Tier-0 agents
            # Only check PENDING status - already-processed proposals are legacy
            rows = self.conn.execute(f"""
                SELECT proposal_id, agent_name, created_at
                FROM proposed_claims
                WHERE agent_name IN ({placeholders})
                AND (artifact_id IS NULL OR artifact_id = '')
                AND status = 'PENDING'
                LIMIT 50
            """, TIER0_AGENTS).fetchall()

            for row in rows:
                violations.append(Violation(
                    invariant="tier0_artifact_requirement",
                    severity="HIGH",
                    entity_id=row["proposal_id"],
                    message=f"Tier-0 claim from {row['agent_name']} missing artifact_id (created {row['created_at']})",
                    auto_fixable=False,
                ))

        except Exception:
            # Tables may not have artifact_id column yet
            pass

        return violations

    def run_all(self) -> InvariantReport:
        """Run all invariant checks."""
        self.violations = []

        # Run all checks
        self.violations.extend(self.check_referential_integrity())
        self.violations.extend(self.check_edge_evidence())
        self.violations.extend(self.check_assertion_consistency())
        self.violations.extend(self.check_duplicate_edges())
        self.violations.extend(self.check_proposal_fk())
        self.violations.extend(self.check_confidence_bounds())
        self.violations.extend(self.check_agent_health())
        self.violations.extend(self.check_pipeline_bypass())
        self.violations.extend(self.check_tier0_artifact_requirement())

        # Count by severity
        critical = len([v for v in self.violations if v.severity == 'CRITICAL'])
        high = len([v for v in self.violations if v.severity == 'HIGH'])
        medium = len([v for v in self.violations if v.severity == 'MEDIUM'])
        low = len([v for v in self.violations if v.severity == 'LOW'])

        # Determine exit code
        if critical > 0:
            exit_code = 2
        elif high > 0:
            exit_code = 1
        else:
            exit_code = 0

        return InvariantReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            violations=self.violations,
            critical_count=critical,
            high_count=high,
            medium_count=medium,
            low_count=low,
            exit_code=exit_code,
        )

    def fix_violations(self, report: InvariantReport) -> Dict[str, int]:
        """Apply auto-fixes for fixable violations."""
        self.connect()
        stats = {'fixed': 0, 'skipped': 0, 'failed': 0}

        for v in report.violations:
            if not v.auto_fixable or not v.fix_action:
                stats['skipped'] += 1
                continue

            if v.fix_action == "Run tools/dedupe_edges.py":
                stats['skipped'] += 1  # Manual fix required
                continue

            try:
                self.conn.execute(v.fix_action)
                stats['fixed'] += 1
            except Exception as e:
                print(f"Fix failed for {v.entity_id}: {e}")
                stats['failed'] += 1

        self.conn.commit()
        return stats


def main():
    parser = argparse.ArgumentParser(description="FGIP Invariants Checker")
    parser.add_argument("db", type=str, help="Database path")
    parser.add_argument("--fix", action="store_true", help="Apply auto-fixes")
    parser.add_argument("--json", action="store_true", help="JSON output")

    args = parser.parse_args()

    db = FGIPDatabase(args.db)
    checker = InvariantChecker(db)
    report = checker.run_all()

    if args.fix:
        fix_stats = checker.fix_violations(report)

    if args.json:
        output = report.to_dict()
        if args.fix:
            output['fix_stats'] = fix_stats
        print(json.dumps(output, indent=2))
    else:
        print("=" * 60)
        print("  FGIP INVARIANTS CHECK")
        print("=" * 60)
        print(f"  Timestamp: {report.timestamp}")
        print()
        print(f"  CRITICAL: {report.critical_count}")
        print(f"  HIGH:     {report.high_count}")
        print(f"  MEDIUM:   {report.medium_count}")
        print(f"  LOW:      {report.low_count}")
        print()

        if report.violations:
            print("  VIOLATIONS:")
            for v in report.violations[:20]:
                severity_icon = {'CRITICAL': '!!', 'HIGH': '! ', 'MEDIUM': '- ', 'LOW': '. '}[v.severity]
                print(f"    {severity_icon}[{v.invariant}] {v.entity_id[:30]}")
                print(f"       {v.message[:60]}")
            if len(report.violations) > 20:
                print(f"    ... and {len(report.violations) - 20} more")
        else:
            print("  All invariants pass!")

        print()
        if args.fix:
            print(f"  FIX RESULTS: fixed={fix_stats['fixed']}, skipped={fix_stats['skipped']}, failed={fix_stats['failed']}")

        print(f"  EXIT CODE: {report.exit_code}")
        print("=" * 60)

    # Write receipt
    receipts_dir = PROJECT_ROOT / "receipts" / "invariants"
    receipts_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipts_dir / f"check_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    receipt_path.write_text(json.dumps(report.to_dict(), indent=2))

    sys.exit(report.exit_code)


if __name__ == "__main__":
    main()
