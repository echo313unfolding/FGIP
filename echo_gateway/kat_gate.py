"""KAT Gate - Truth enforcement for phenotype expression.

The KAT (Known Answer Test) gate ensures that truth-asserting outputs
(ConvictionReports, forecasts, etc.) are only returned when the system
passes integrity verification.

Three verification modes:
- verify_always: Run KAT before every phenotype expression
- verify_sampled: Run KAT N% of the time (default 10%)
- trust_cached: Skip if last KAT < N minutes ago (default 15 min)
"""

import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class KATMode(Enum):
    """KAT verification modes."""

    VERIFY_ALWAYS = "verify_always"
    VERIFY_SAMPLED = "verify_sampled"
    TRUST_CACHED = "trust_cached"


@dataclass
class KATGateResult:
    """Result of KAT gate verification."""

    passed: bool
    mode: str
    skipped: bool = False
    kat_passed: int = 0
    kat_failed: int = 0
    kat_total: int = 0
    regressions: int = 0  # Failures that are NOT expected limitations
    expected_limitations: int = 0
    duration_ms: float = 0.0
    reason: Optional[str] = None
    run_timestamp: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "passed": self.passed,
            "mode": self.mode,
            "skipped": self.skipped,
            "kat_passed": self.kat_passed,
            "kat_failed": self.kat_failed,
            "kat_total": self.kat_total,
            "regressions": self.regressions,
            "expected_limitations": self.expected_limitations,
            "duration_ms": self.duration_ms,
            "reason": self.reason,
            "run_timestamp": self.run_timestamp,
        }


class KATGate:
    """
    KAT Gate for truth enforcement.

    Verifies system integrity before allowing phenotype expression
    (truth-asserting outputs like ConvictionReports).
    """

    # Agents that require KAT verification before output
    PHENOTYPE_AGENTS = {
        "conviction-engine",
        "conviction_engine",
        "forecast-agent",
        "forecast_agent",
        "trade-plan-agent",
        "trade_plan_agent",
    }

    def __init__(
        self,
        db,
        mode: KATMode = KATMode.TRUST_CACHED,
        sample_rate: float = 0.1,
        cache_minutes: int = 15,
    ):
        """
        Initialize KAT gate.

        Args:
            db: FGIPDatabase instance
            mode: Verification mode
            sample_rate: Sampling rate for VERIFY_SAMPLED mode (0.0-1.0)
            cache_minutes: Cache duration for TRUST_CACHED mode
        """
        self.db = db
        self.mode = mode
        self.sample_rate = sample_rate
        self.cache_minutes = cache_minutes
        self._last_result: Optional[KATGateResult] = None
        self._last_run_time: Optional[float] = None

    def requires_verification(self, agent_name: str, force: bool = False) -> bool:
        """
        Check if an agent requires KAT verification.

        Args:
            agent_name: Name of the agent
            force: Force verification regardless of agent type

        Returns:
            True if verification is required
        """
        if force:
            return True

        # Normalize agent name
        normalized = agent_name.lower().replace("_", "-")
        return normalized in self.PHENOTYPE_AGENTS

    def verify(self, force: bool = False) -> KATGateResult:
        """
        Run KAT verification according to configured mode.

        Args:
            force: Force full verification regardless of mode

        Returns:
            KATGateResult with verification status
        """
        start_time = time.time()

        # Check if we should skip based on mode
        if not force:
            if self.mode == KATMode.TRUST_CACHED:
                if self._is_cache_valid():
                    return KATGateResult(
                        passed=self._last_result.passed if self._last_result else True,
                        mode=self.mode.value,
                        skipped=True,
                        reason="Using cached result",
                        run_timestamp=self._last_result.run_timestamp
                        if self._last_result
                        else None,
                    )

            elif self.mode == KATMode.VERIFY_SAMPLED:
                if random.random() > self.sample_rate:
                    return KATGateResult(
                        passed=True,  # Assume pass when not sampled
                        mode=self.mode.value,
                        skipped=True,
                        reason=f"Not sampled (rate={self.sample_rate})",
                    )

        # Run actual KAT verification
        try:
            from fgip.tests.kat.runner import KATHarness

            harness = KATHarness(self.db)
            result = harness.run_all()

            duration_ms = round((time.time() - start_time) * 1000, 2)

            gate_result = KATGateResult(
                passed=result.regressions == 0,  # Pass if no regressions
                mode=self.mode.value,
                skipped=False,
                kat_passed=result.passed,
                kat_failed=result.failed,
                kat_total=result.total,
                regressions=result.regressions,
                expected_limitations=result.expected_limitations,
                duration_ms=duration_ms,
                run_timestamp=datetime.now(timezone.utc).isoformat(),
            )

            # Cache the result
            self._last_result = gate_result
            self._last_run_time = time.time()

            return gate_result

        except Exception as e:
            duration_ms = round((time.time() - start_time) * 1000, 2)
            return KATGateResult(
                passed=False,
                mode=self.mode.value,
                skipped=False,
                reason=f"KAT error: {str(e)}",
                duration_ms=duration_ms,
            )

    def _is_cache_valid(self) -> bool:
        """Check if cached KAT result is still valid."""
        if self._last_run_time is None or self._last_result is None:
            return False

        age_seconds = time.time() - self._last_run_time
        max_age_seconds = self.cache_minutes * 60

        return age_seconds < max_age_seconds

    def invalidate_cache(self) -> None:
        """Invalidate the cached KAT result."""
        self._last_result = None
        self._last_run_time = None

    def get_last_result(self) -> Optional[KATGateResult]:
        """Get the last KAT result (if any)."""
        return self._last_result

    def gate_output(
        self,
        agent_name: str,
        output: Any,
        require_kat: bool = False,
    ) -> tuple[bool, Any, Optional[KATGateResult]]:
        """
        Gate agent output through KAT verification.

        Args:
            agent_name: Name of the agent producing output
            output: The output to potentially gate
            require_kat: Force KAT verification

        Returns:
            Tuple of (allowed, output_or_blocked_message, kat_result)
        """
        # Check if verification is required
        if not self.requires_verification(agent_name, force=require_kat):
            return (True, output, None)

        # Run verification
        kat_result = self.verify(force=require_kat)

        if kat_result.passed:
            return (True, output, kat_result)
        else:
            blocked_message = {
                "error": "phenotype_blocked",
                "reason": "KAT verification failed",
                "regressions": kat_result.regressions,
                "kat_failed": kat_result.kat_failed,
                "kat_total": kat_result.kat_total,
            }
            return (False, blocked_message, kat_result)
