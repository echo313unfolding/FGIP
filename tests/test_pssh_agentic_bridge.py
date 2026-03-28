"""
Tests for PSSH Agentic Bridge.

WO-PSSH-AGENTIC-BRIDGE-01

Tests all 6 production rules:
1. high Se + coherent + triangulated + attacks survived -> ALLOW_CONCLUDE
2. low Se -> CONTINUE_GATHERING
3. conflicted substrate -> REQUIRE_REFLECTION
4. fatal adversarial attack unsolved -> REQUIRE_REFLECTION
5. missing triangulation -> DOWNGRADE_CONFIDENCE
6. unsafe tool -> BLOCK_ACTION
"""

import pytest
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from echo_gateway.pssh_agentic_bridge import (
    PSSHAgenticBridge,
    BridgeOutcome,
    BridgeConfig,
    BridgeDecision,
    BridgeReceipt,
)


@dataclass
class MockAgenticState:
    """Mock AgenticState for testing."""
    se_state: Optional[Dict[str, Any]] = None
    adversarial_attacks: List[Any] = field(default_factory=list)
    triangulation: Optional[Dict[str, Any]] = None
    attacks_survived: int = 0
    attacks_total: int = 0


@dataclass
class MockAdversarialAttack:
    """Mock adversarial attack."""
    severity: str
    survived: bool


class TestPSSHAgenticBridge:
    """Test suite for PSSHAgenticBridge."""

    def setup_method(self):
        """Set up test fixtures."""
        self.bridge = PSSHAgenticBridge()

    # Test 1: High Se + coherent + triangulated + attacks survived -> ALLOW_CONCLUDE
    def test_allow_conclude_high_se_triangulated_survived(self):
        """Policy should allow conclude when all conditions met."""
        state = MockAgenticState(
            se_state={
                "combined_Se": 0.65,  # Above threshold
                "substrate_mode": "coherent",
            },
            triangulation={"triangulated": True},
            attacks_total=3,
            attacks_survived=3,  # All survived
        )

        decision, receipt = self.bridge.evaluate_proposed_conclusion(
            state,
            "Test answer",
            0.85,
        )

        assert decision.outcome == BridgeOutcome.ALLOW_CONCLUDE
        assert decision.rule_fired == "gate_conclusion_high_se"
        assert receipt.decision == "allow_conclude"
        assert not decision.blocked
        assert not decision.continued
        assert not decision.required_reflection

    # Test 2: Low Se -> CONTINUE_GATHERING
    def test_continue_gathering_low_se(self):
        """Policy should require more evidence when Se is too low."""
        state = MockAgenticState(
            se_state={
                "combined_Se": 0.05,  # Below abort threshold
                "substrate_mode": "coherent",
            },
            triangulation={"triangulated": True},
            attacks_total=0,
            attacks_survived=0,
        )

        decision, receipt = self.bridge.evaluate_proposed_conclusion(
            state,
            "Test answer",
            0.80,
        )

        assert decision.outcome == BridgeOutcome.CONTINUE_GATHERING
        assert decision.rule_fired == "gate_conclusion_low_se"
        assert decision.continued
        assert receipt.adjusted_confidence <= 0.30  # Capped

    # Test 3: Conflicted substrate -> REQUIRE_REFLECTION
    def test_require_reflection_conflicted_substrate(self):
        """Policy should require reflection when substrate is conflicted."""
        state = MockAgenticState(
            se_state={
                "combined_Se": 0.60,
                "substrate_mode": "conflicted",  # Conflicted
            },
            triangulation={"triangulated": True},
            attacks_total=2,
            attacks_survived=2,
        )

        decision, receipt = self.bridge.evaluate_proposed_conclusion(
            state,
            "Test answer",
            0.85,
        )

        assert decision.outcome == BridgeOutcome.REQUIRE_REFLECTION
        assert decision.rule_fired == "gate_conclusion_conflicted_substrate"
        assert decision.required_reflection
        assert receipt.adjusted_confidence <= 0.50  # Capped

    # Test 4: Fatal adversarial attack unsolved -> REQUIRE_REFLECTION
    def test_require_reflection_fatal_attack_unsolved(self):
        """Policy should require reflection when fatal attack not survived."""
        state = MockAgenticState(
            se_state={
                "combined_Se": 0.60,
                "substrate_mode": "coherent",
            },
            triangulation={"triangulated": True},
            attacks_total=2,
            attacks_survived=1,
            adversarial_attacks=[
                MockAdversarialAttack(severity="fatal", survived=False),
                MockAdversarialAttack(severity="minor", survived=True),
            ],
        )

        decision, receipt = self.bridge.evaluate_proposed_conclusion(
            state,
            "Test answer",
            0.85,
        )

        assert decision.outcome == BridgeOutcome.REQUIRE_REFLECTION
        assert decision.rule_fired == "adversarial_recovery_rule"
        assert decision.required_reflection

    # Test 5: Missing triangulation -> DOWNGRADE_CONFIDENCE
    def test_downgrade_confidence_no_triangulation(self):
        """Policy should cap confidence when not triangulated."""
        state = MockAgenticState(
            se_state={
                "combined_Se": 0.60,
                "substrate_mode": "coherent",
            },
            triangulation={"triangulated": False},  # Not triangulated
            attacks_total=2,
            attacks_survived=2,
        )

        decision, receipt = self.bridge.evaluate_proposed_conclusion(
            state,
            "Test answer",
            0.90,
        )

        assert decision.outcome == BridgeOutcome.DOWNGRADE_CONFIDENCE
        assert decision.rule_fired == "confidence_downgrade_rule"
        assert receipt.adjusted_confidence == 0.60  # Capped at config default

    # Test 6: Unsafe tool -> BLOCK_ACTION
    def test_block_action_unsafe_tool(self):
        """Policy should block unsafe tools."""
        state = MockAgenticState()

        decision, receipt = self.bridge.evaluate_tool_action(
            state,
            "delete_data",  # Blocked tool
            {"target": "users"},
        )

        assert decision.outcome == BridgeOutcome.BLOCK_ACTION
        assert decision.rule_fired == "unsafe_tool_gate"
        assert decision.blocked

    def test_block_action_dangerous_args(self):
        """Policy should block tools with dangerous args."""
        state = MockAgenticState()

        decision, receipt = self.bridge.evaluate_tool_action(
            state,
            "graph_query",  # Allowed tool
            {"query": "DROP TABLE users"},  # Dangerous pattern
        )

        assert decision.outcome == BridgeOutcome.BLOCK_ACTION
        assert decision.rule_fired == "unsafe_tool_gate"
        assert decision.blocked

    def test_allow_safe_tool(self):
        """Policy should allow safe tools."""
        state = MockAgenticState()

        decision, receipt = self.bridge.evaluate_tool_action(
            state,
            "graph_query",
            {"query": "SELECT * FROM nodes"},
        )

        assert decision.outcome == BridgeOutcome.ALLOW_CONCLUDE  # Means allow action
        assert decision.rule_fired == "tool_action_allowed"
        assert not decision.blocked

    # Test bridge disabled
    def test_bridge_disabled(self):
        """Bridge should allow everything when disabled."""
        config = BridgeConfig(enabled=False)
        bridge = PSSHAgenticBridge(config=config)

        state = MockAgenticState(
            se_state={"combined_Se": 0.01},  # Would normally block
        )

        decision, receipt = bridge.evaluate_proposed_conclusion(
            state,
            "Test answer",
            0.85,
        )

        assert decision.outcome == BridgeOutcome.ALLOW_CONCLUDE
        assert decision.rule_fired == "bridge_disabled"

    # Test receipt creation
    def test_receipt_fields(self):
        """Receipt should contain all required fields."""
        state = MockAgenticState(
            se_state={
                "combined_Se": 0.55,
                "substrate_mode": "focused",
            },
            triangulation={"triangulated": True},
            attacks_total=2,
            attacks_survived=2,
        )

        decision, receipt = self.bridge.evaluate_proposed_conclusion(
            state,
            "Test answer",
            0.85,
        )

        # Check receipt fields
        assert receipt.receipt_id.startswith("bridge-")
        assert receipt.timestamp
        assert receipt.rule_fired
        assert receipt.decision
        assert receipt.proposed_action_type == "conclude"
        assert receipt.proposed_confidence == 0.85
        assert receipt.combined_se == 0.55
        assert receipt.substrate_mode == "focused"
        assert receipt.attacks_total == 2
        assert receipt.attacks_survived == 2
        assert receipt.triangulated == True
        assert isinstance(receipt.reasons, list)

    # Test low survival rate
    def test_require_reflection_low_survival_rate(self):
        """Policy should require reflection when survival rate is low."""
        state = MockAgenticState(
            se_state={
                "combined_Se": 0.60,
                "substrate_mode": "coherent",
            },
            triangulation={"triangulated": True},
            attacks_total=5,
            attacks_survived=2,  # 40% survival - below 70% threshold
        )

        decision, receipt = self.bridge.evaluate_proposed_conclusion(
            state,
            "Test answer",
            0.85,
        )

        assert decision.outcome == BridgeOutcome.REQUIRE_REFLECTION
        assert decision.rule_fired == "adversarial_recovery_rule"

    # Test fallback continue
    def test_fallback_continue_mid_se(self):
        """Policy should continue gathering when Se is between thresholds."""
        state = MockAgenticState(
            se_state={
                "combined_Se": 0.35,  # Above abort (0.10) but below conclude (0.50)
                "substrate_mode": "coherent",
            },
            triangulation={"triangulated": True},
            attacks_total=2,
            attacks_survived=2,
        )

        decision, receipt = self.bridge.evaluate_proposed_conclusion(
            state,
            "Test answer",
            0.85,
        )

        assert decision.outcome == BridgeOutcome.CONTINUE_GATHERING
        assert decision.rule_fired == "fallback_continue_rule"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
