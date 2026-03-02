"""FGIP KAT (Known Answer Test) Module.

Provides deterministic verification of the FGIP pipeline:
- Easter egg tests: Known-true facts that MUST be found
- Adversarial tests: Manipulation patterns that MUST be filtered

Usage:
    from fgip.tests.kat import KATHarness, KATResult

    harness = KATHarness(db)
    result = harness.run_all()
    print(f"Passed: {result.passed}/{result.total}")
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import hashlib


@dataclass
class TestCase:
    """A single KAT test case."""
    id: str
    type: str  # "must_exist", "must_filter", "must_not_exist"
    description: str
    category: str
    query: Optional[Dict[str, Any]] = None  # For must_exist tests
    artifact_content: Optional[str] = None  # For must_filter tests
    expected: Any = None
    expected_integrity_below: Optional[float] = None
    expected_flags: Optional[List[str]] = None
    source_url: Optional[str] = None
    agent: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None  # For variant tracking, expected_limitation, etc.

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestCase":
        return cls(
            id=data["id"],
            type=data["type"],
            description=data["description"],
            category=data.get("category", "general"),
            query=data.get("query"),
            artifact_content=data.get("artifact_content"),
            expected=data.get("expected"),
            expected_integrity_below=data.get("expected_integrity_below"),
            expected_flags=data.get("expected_flags"),
            source_url=data.get("source_url"),
            agent=data.get("agent"),
            metadata=data.get("metadata"),
        )


@dataclass
class TestResult:
    """Result of a single test case."""
    test_id: str
    test_type: str
    passed: bool
    expected: Any
    actual: Any
    details: Optional[str] = None
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "test_type": self.test_type,
            "passed": self.passed,
            "expected": self.expected,
            "actual": self.actual,
            "details": self.details,
            "duration_ms": self.duration_ms,
        }


@dataclass
class KATResult:
    """Complete KAT run results."""
    timestamp: str
    total: int
    passed: int
    failed: int
    skipped: int
    results: List[TestResult]
    duration_ms: float
    inputs_hash: str  # Hash of test cases for reproducibility
    expected_limitations: int = 0  # Failures that are known limitations (not regressions)

    @property
    def pass_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.passed / self.total

    @property
    def regressions(self) -> int:
        """Count of failures that are NOT expected limitations."""
        return self.failed - self.expected_limitations

    @property
    def all_passed(self) -> bool:
        return self.failed == 0 and self.skipped == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "expected_limitations": self.expected_limitations,
            "regressions": self.regressions,
            "pass_rate": round(self.pass_rate, 4),
            "all_passed": self.all_passed,
            "duration_ms": self.duration_ms,
            "inputs_hash": self.inputs_hash,
            "results": [r.to_dict() for r in self.results],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


def load_test_cases(cases_file: Path) -> List[TestCase]:
    """Load test cases from a JSONL file."""
    cases = []
    with open(cases_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                data = json.loads(line)
                cases.append(TestCase.from_dict(data))
    return cases


def hash_test_cases(cases: List[TestCase]) -> str:
    """Generate a hash of test cases for reproducibility."""
    content = json.dumps([{
        "id": c.id,
        "type": c.type,
        "query": c.query,
        "expected": c.expected,
    } for c in cases], sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


# Import the harness class if available (for convenience)
try:
    from .runner import KATHarness
except ImportError:
    KATHarness = None


__all__ = [
    "TestCase",
    "TestResult",
    "KATResult",
    "KATHarness",
    "load_test_cases",
    "hash_test_cases",
]
