"""KAT Harness Runner - Executes Known Answer Tests.

This module provides the KATHarness class that runs deterministic tests
against the FGIP pipeline to verify correctness.

Usage:
    from fgip.tests.kat.runner import KATHarness
    from fgip.db import FGIPDatabase

    db = FGIPDatabase("fgip.db")
    harness = KATHarness(db)
    result = harness.run_all()
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from . import TestCase, TestResult, KATResult, load_test_cases, hash_test_cases
from .variants import expand_with_variants


class KATHarness:
    """Known Answer Test harness for FGIP pipeline verification.

    Runs deterministic tests to verify:
    1. Easter eggs: Known-true facts that MUST exist in the graph
    2. Adversarial cases: Manipulation patterns that MUST be filtered
    """

    def __init__(self, db, cases_dir: Optional[Path] = None):
        """Initialize KAT harness.

        Args:
            db: FGIPDatabase instance
            cases_dir: Directory containing test case JSONL files
        """
        self.db = db
        if cases_dir is None:
            cases_dir = Path(__file__).parent
        self.cases_dir = Path(cases_dir)

    def run_all(
        self,
        fail_fast: bool = False,
        verbose: bool = False,
        expand_variants: bool = False,
    ) -> KATResult:
        """Run all KAT tests.

        Args:
            fail_fast: Stop on first failure
            verbose: Print detailed output
            expand_variants: Expand adversarial cases with deterministic variants

        Returns:
            KATResult with all test results
        """
        start_time = time.time()
        all_cases = []
        results = []

        # Load easter egg cases
        easter_egg_file = self.cases_dir / "easter_egg_cases.jsonl"
        if easter_egg_file.exists():
            all_cases.extend(load_test_cases(easter_egg_file))

        # Load adversarial cases
        adversarial_file = self.cases_dir / "adversarial_cases.jsonl"
        if adversarial_file.exists():
            adversarial_cases = load_test_cases(adversarial_file)
            if expand_variants:
                adversarial_cases = expand_with_variants(adversarial_cases)
            all_cases.extend(adversarial_cases)

        # Load benign guard cases
        benign_file = self.cases_dir / "benign_cases.jsonl"
        if benign_file.exists():
            all_cases.extend(load_test_cases(benign_file))

        if not all_cases:
            return KATResult(
                timestamp=datetime.utcnow().isoformat() + "Z",
                total=0,
                passed=0,
                failed=0,
                skipped=0,
                results=[],
                duration_ms=0.0,
                inputs_hash="empty",
            )

        inputs_hash = hash_test_cases(all_cases)

        for case in all_cases:
            if verbose:
                print(f"Running: {case.id}...", end=" ", flush=True)

            result = self._run_test(case)
            results.append(result)

            if verbose:
                status = "PASS" if result.passed else "FAIL"
                print(f"{status} ({result.duration_ms:.1f}ms)")

            if fail_fast and not result.passed:
                break

        duration_ms = (time.time() - start_time) * 1000

        passed = sum(1 for r in results if r.passed)
        failed = sum(1 for r in results if not r.passed)
        skipped = len(all_cases) - len(results)

        # Count expected limitations (failures that are marked as known limitations)
        # Build a map from test_id to case for metadata lookup
        cases_by_id = {c.id: c for c in all_cases}
        expected_limitations = sum(
            1 for r in results
            if not r.passed
            and cases_by_id.get(r.test_id)
            and (cases_by_id[r.test_id].metadata or {}).get("expected_limitation", False)
        )

        return KATResult(
            timestamp=datetime.utcnow().isoformat() + "Z",
            total=len(all_cases),
            passed=passed,
            failed=failed,
            skipped=skipped,
            results=results,
            duration_ms=round(duration_ms, 2),
            inputs_hash=inputs_hash,
            expected_limitations=expected_limitations,
        )

    def run_easter_eggs(self, verbose: bool = False) -> KATResult:
        """Run only easter egg tests."""
        easter_egg_file = self.cases_dir / "easter_egg_cases.jsonl"
        if not easter_egg_file.exists():
            return KATResult(
                timestamp=datetime.utcnow().isoformat() + "Z",
                total=0, passed=0, failed=0, skipped=0,
                results=[], duration_ms=0.0, inputs_hash="empty",
            )

        cases = load_test_cases(easter_egg_file)
        return self._run_cases(cases, verbose)

    def run_adversarial(
        self,
        verbose: bool = False,
        expand_variants: bool = False
    ) -> KATResult:
        """Run only adversarial tests.

        Args:
            verbose: Print detailed output
            expand_variants: Expand with deterministic variants (9 base → ~45 total)
        """
        adversarial_file = self.cases_dir / "adversarial_cases.jsonl"
        if not adversarial_file.exists():
            return KATResult(
                timestamp=datetime.utcnow().isoformat() + "Z",
                total=0, passed=0, failed=0, skipped=0,
                results=[], duration_ms=0.0, inputs_hash="empty",
            )

        cases = load_test_cases(adversarial_file)
        if expand_variants:
            cases = expand_with_variants(cases)
        return self._run_cases(cases, verbose)

    def run_benign(self, verbose: bool = False) -> KATResult:
        """Run only benign guard tests (false-positive prevention)."""
        benign_file = self.cases_dir / "benign_cases.jsonl"
        if not benign_file.exists():
            return KATResult(
                timestamp=datetime.utcnow().isoformat() + "Z",
                total=0, passed=0, failed=0, skipped=0,
                results=[], duration_ms=0.0, inputs_hash="empty",
            )

        cases = load_test_cases(benign_file)
        return self._run_cases(cases, verbose)

    def _run_cases(self, cases: List[TestCase], verbose: bool) -> KATResult:
        """Run a list of test cases."""
        start_time = time.time()
        results = []

        for case in cases:
            if verbose:
                print(f"Running: {case.id}...", end=" ", flush=True)

            result = self._run_test(case)
            results.append(result)

            if verbose:
                status = "PASS" if result.passed else "FAIL"
                print(f"{status} ({result.duration_ms:.1f}ms)")

        duration_ms = (time.time() - start_time) * 1000

        # Count expected limitations
        cases_by_id = {c.id: c for c in cases}
        expected_limitations = sum(
            1 for r in results
            if not r.passed
            and cases_by_id.get(r.test_id)
            and (cases_by_id[r.test_id].metadata or {}).get("expected_limitation", False)
        )

        return KATResult(
            timestamp=datetime.utcnow().isoformat() + "Z",
            total=len(cases),
            passed=sum(1 for r in results if r.passed),
            failed=sum(1 for r in results if not r.passed),
            skipped=0,
            results=results,
            duration_ms=round(duration_ms, 2),
            inputs_hash=hash_test_cases(cases),
            expected_limitations=expected_limitations,
        )

    def _run_test(self, case: TestCase) -> TestResult:
        """Run a single test case."""
        start_time = time.time()

        try:
            if case.type == "must_exist":
                result = self._test_must_exist(case)
            elif case.type == "must_filter":
                result = self._test_must_filter(case)
            elif case.type == "must_not_exist":
                result = self._test_must_not_exist(case)
            else:
                result = TestResult(
                    test_id=case.id,
                    test_type=case.type,
                    passed=False,
                    expected=None,
                    actual=None,
                    details=f"Unknown test type: {case.type}",
                )
        except Exception as e:
            result = TestResult(
                test_id=case.id,
                test_type=case.type,
                passed=False,
                expected=case.expected,
                actual=None,
                details=f"Exception: {str(e)}",
            )

        result.duration_ms = round((time.time() - start_time) * 1000, 2)
        return result

    def _test_must_exist(self, case: TestCase) -> TestResult:
        """Test that an edge or node exists in the graph."""
        conn = self.db.connect()
        query = case.query or {}

        # Check for edge existence
        if "edge" in query:
            edge_spec = query["edge"]
            from_node = self._normalize_node_id(edge_spec.get("from", ""))
            to_node = self._normalize_node_id(edge_spec.get("to", ""))
            relation = edge_spec.get("relation", "")
            min_confidence = query.get("min_confidence", 0.0)

            # Check production edges
            sql = """
                SELECT edge_id, confidence FROM edges
                WHERE (
                    LOWER(REPLACE(from_node_id, '_', '-')) = ?
                    OR LOWER(REPLACE(from_node_id, '_', '-')) LIKE ?
                )
            """
            params = [from_node, f"%{from_node}%"]

            if relation:
                sql += " AND edge_type = ?"
                params.append(relation)

            if to_node:
                sql += """
                    AND (
                        LOWER(REPLACE(to_node_id, '_', '-')) = ?
                        OR LOWER(REPLACE(to_node_id, '_', '-')) LIKE ?
                    )
                """
                params.extend([to_node, f"%{to_node}%"])

            row = conn.execute(sql, params).fetchone()

            if row:
                edge_id, confidence = row[0], row[1] if len(row) > 1 else 1.0
                confidence = confidence or 1.0

                if confidence >= min_confidence:
                    return TestResult(
                        test_id=case.id,
                        test_type=case.type,
                        passed=True,
                        expected={"exists": True, "min_confidence": min_confidence},
                        actual={"edge_id": edge_id, "confidence": confidence},
                        details="Edge found in production",
                    )
                else:
                    return TestResult(
                        test_id=case.id,
                        test_type=case.type,
                        passed=False,
                        expected={"min_confidence": min_confidence},
                        actual={"confidence": confidence},
                        details=f"Edge found but confidence {confidence} < {min_confidence}",
                    )
            else:
                # Check proposed_edges as fallback
                sql = """
                    SELECT proposal_id, confidence FROM proposed_edges
                    WHERE (
                        LOWER(REPLACE(from_node, '_', '-')) LIKE ?
                        OR from_node LIKE ?
                    )
                """
                params = [f"%{from_node}%", f"%{from_node}%"]

                if relation:
                    sql += " AND relationship = ?"
                    params.append(relation)

                if to_node:
                    sql += " AND (LOWER(REPLACE(to_node, '_', '-')) LIKE ? OR to_node LIKE ?)"
                    params.extend([f"%{to_node}%", f"%{to_node}%"])

                row = conn.execute(sql, params).fetchone()

                if row:
                    return TestResult(
                        test_id=case.id,
                        test_type=case.type,
                        passed=True,
                        expected={"exists": True},
                        actual={"proposal_id": row[0], "location": "proposed_edges"},
                        details="Edge found in proposals (not yet promoted)",
                    )

                return TestResult(
                    test_id=case.id,
                    test_type=case.type,
                    passed=False,
                    expected={"exists": True},
                    actual={"exists": False},
                    details=f"Edge not found: {from_node} -> {relation} -> {to_node}",
                )

        # Check for node existence
        elif "node" in query:
            node_spec = query["node"]
            node_id = self._normalize_node_id(node_spec.get("id", ""))
            node_type = node_spec.get("type")

            sql = """
                SELECT node_id, node_type FROM nodes
                WHERE LOWER(REPLACE(node_id, '_', '-')) LIKE ?
                   OR LOWER(REPLACE(name, ' ', '-')) LIKE ?
            """
            params = [f"%{node_id}%", f"%{node_id}%"]

            if node_type:
                sql += " AND node_type = ?"
                params.append(node_type)

            row = conn.execute(sql, params).fetchone()

            if row:
                return TestResult(
                    test_id=case.id,
                    test_type=case.type,
                    passed=True,
                    expected={"exists": True},
                    actual={"node_id": row[0], "node_type": row[1]},
                    details="Node found",
                )
            else:
                return TestResult(
                    test_id=case.id,
                    test_type=case.type,
                    passed=False,
                    expected={"exists": True},
                    actual={"exists": False},
                    details=f"Node not found: {node_id}",
                )

        return TestResult(
            test_id=case.id,
            test_type=case.type,
            passed=False,
            expected=None,
            actual=None,
            details="Invalid query: must specify 'edge' or 'node'",
        )

    def _test_must_filter(self, case: TestCase) -> TestResult:
        """Test that content triggers correct integrity filtering."""
        # Import filter agent
        try:
            from fgip.agents.filter_agent import FilterAgent
        except ImportError:
            return TestResult(
                test_id=case.id,
                test_type=case.type,
                passed=False,
                expected=None,
                actual=None,
                details="FilterAgent not available",
            )

        filter_agent = FilterAgent(self.db)

        # Create a mock artifact from the test content
        content = case.artifact_content or ""

        # Score the content directly using score_text()
        score_result = filter_agent.score_text(content, source_url="")

        passed = True
        details = []

        # Check integrity threshold
        if case.expected_integrity_below is not None:
            if score_result.final_score >= case.expected_integrity_below:
                passed = False
                details.append(
                    f"Integrity {score_result.final_score:.2f} >= threshold {case.expected_integrity_below}"
                )

        # Check expected flags (check both red flags AND manipulation_markers)
        if case.expected_flags:
            # Combine red flags and manipulation markers for unified checking
            detected_markers = set(score_result.flags or [])
            detected_markers.update(score_result.manipulation_markers or [])
            expected_flags = set(case.expected_flags)
            missing_flags = expected_flags - detected_markers

            if missing_flags:
                passed = False
                details.append(f"Missing markers: {missing_flags}")

        return TestResult(
            test_id=case.id,
            test_type=case.type,
            passed=passed,
            expected={
                "integrity_below": case.expected_integrity_below,
                "flags": case.expected_flags,
            },
            actual={
                "integrity": score_result.final_score,
                "flags": score_result.flags,
                "manipulation_markers": score_result.manipulation_markers,
            },
            details="; ".join(details) if details else "Content correctly filtered",
        )

    def _test_must_not_exist(self, case: TestCase) -> TestResult:
        """Test that something should NOT exist (negative test)."""
        # Inverse of must_exist
        result = self._test_must_exist(case)

        # Flip the pass/fail
        return TestResult(
            test_id=case.id,
            test_type="must_not_exist",
            passed=not result.passed,
            expected={"exists": False},
            actual=result.actual,
            details="Correctly absent" if not result.passed else "Unexpectedly present",
        )

    def _normalize_node_id(self, node_id: str) -> str:
        """Normalize node ID for comparison."""
        if not node_id:
            return ""
        return node_id.lower().replace(" ", "-").replace("_", "-")

    def store_results(self, result: KATResult) -> str:
        """Store KAT results in database.

        Returns:
            Run ID for the stored results
        """
        import uuid
        conn = self.db.connect()
        run_id = f"kat-{result.timestamp.replace(':', '-')}"

        for test_result in result.results:
            conn.execute("""
                INSERT OR REPLACE INTO kat_results
                (id, run_timestamp, test_id, test_type, expected_result,
                 actual_result, passed, details, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                f"{run_id}-{test_result.test_id}",
                result.timestamp,
                test_result.test_id,
                test_result.test_type,
                json.dumps(test_result.expected),
                json.dumps(test_result.actual),
                1 if test_result.passed else 0,
                test_result.details,
                test_result.duration_ms,
            ))

        conn.commit()
        return run_id

    def run_with_delta(self) -> Dict[str, Any]:
        """Run KAT harness and return delta-style results for scheduler integration."""
        result = self.run_all()

        return {
            "success": result.all_passed,
            "delta_count": result.failed,  # Number of regressions
            "claims_proposed": 0,
            "edges_proposed": 0,
            "tests_passed": result.passed,
            "tests_failed": result.failed,
            "tests_total": result.total,
            "pass_rate": result.pass_rate,
            "duration_ms": result.duration_ms,
        }
