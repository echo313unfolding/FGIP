"""
PSSH Agentic Bridge - Policy Gate for Reasoning Loop.

WO-PSSH-AGENTIC-BRIDGE-01

The LLM may propose. PSSH decides whether to:
- ALLOW_CONCLUDE: proceed with conclusion
- CONTINUE_GATHERING: need more evidence
- REQUIRE_REFLECTION: force adversarial retry
- DOWNGRADE_CONFIDENCE: cap confidence ceiling
- BLOCK_ACTION: reject unsafe tool call

This is a GATE layer, not a wrapper. PSSH reads state but does not
generate language or replace the reasoning loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import uuid


class BridgeOutcome(str, Enum):
    """Possible outcomes from the PSSH policy gate."""
    ALLOW_CONCLUDE = "allow_conclude"
    CONTINUE_GATHERING = "continue_gathering"
    REQUIRE_REFLECTION = "require_reflection"
    BLOCK_ACTION = "block_action"
    DOWNGRADE_CONFIDENCE = "downgrade_confidence"


@dataclass
class BridgeDecision:
    """Decision from the PSSH policy gate."""
    outcome: BridgeOutcome
    rule_fired: str
    reasons: List[str] = field(default_factory=list)
    adjusted_confidence: Optional[float] = None
    blocked: bool = False
    continued: bool = False
    required_reflection: bool = False


@dataclass
class BridgeReceipt:
    """
    Audit receipt for every bridge gate decision.

    Every gate, block, override, and promotion is logged.
    """
    receipt_id: str
    timestamp: str
    rule_fired: str
    decision: str
    proposed_action_type: str
    proposed_confidence: float
    adjusted_confidence: float
    combined_se: float
    substrate_mode: str
    attacks_total: int
    attacks_survived: int
    triangulated: bool
    reasons: List[str]
    blocked: bool
    continued: bool
    required_reflection: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "timestamp": self.timestamp,
            "rule_fired": self.rule_fired,
            "decision": self.decision,
            "proposed_action_type": self.proposed_action_type,
            "proposed_confidence": self.proposed_confidence,
            "adjusted_confidence": self.adjusted_confidence,
            "combined_se": self.combined_se,
            "substrate_mode": self.substrate_mode,
            "attacks_total": self.attacks_total,
            "attacks_survived": self.attacks_survived,
            "triangulated": self.triangulated,
            "reasons": self.reasons,
            "blocked": self.blocked,
            "continued": self.continued,
            "required_reflection": self.required_reflection,
        }


@dataclass
class BridgeConfig:
    """Configuration for PSSH bridge thresholds."""
    # Conclusion gates
    min_conclude_se: float = 0.50          # Se >= this to allow conclude
    abort_se: float = 0.10                  # Se < this blocks conclude
    min_survival_rate: float = 0.70         # Attack survival rate required

    # Confidence caps
    confidence_cap_untriangulated: float = 0.60
    confidence_cap_conflicted: float = 0.50
    confidence_cap_low_se: float = 0.30

    # Tool blocking
    blocked_tools: List[str] = field(default_factory=lambda: [
        "delete_data",
        "exfiltrate",
        "unsafe_exec",
        "drop_table",
        "rm_rf",
    ])

    # Master switch
    enabled: bool = True


class PSSHAgenticBridge:
    """
    PSSH policy gate for the agentic reasoning loop.

    Reads Se/FibPi state and applies production rules to gate
    conclusions and tool actions. Does NOT generate language or
    replace the reasoning loop.

    Production Rules:
    1. gate_conclusion_high_se: Allow if Se >= 0.50 AND survival >= 0.70 AND triangulated
    2. gate_conclusion_low_se: Block if Se < 0.10
    3. gate_conclusion_conflicted_substrate: Require reflection if conflicted
    4. adversarial_recovery_rule: Require reflection if fatal attacks not survived
    5. confidence_downgrade_rule: Cap confidence if not triangulated
    6. unsafe_tool_gate: Block unsafe tools
    """

    def __init__(self, config: Optional[BridgeConfig] = None):
        self.config = config or BridgeConfig()

    def _extract_context(self, state: Any) -> Dict[str, Any]:
        """
        Extract policy-relevant context from AgenticState.

        Reads Se state, adversarial results, triangulation - does not modify.
        """
        se_state = getattr(state, "se_state", None) or {}

        # Handle both enhanced (combined_Se) and basic (Se) formats
        if isinstance(se_state, dict):
            if "combined_Se" in se_state:
                combined_se = float(se_state.get("combined_Se", 0.0))
                substrate_mode = str(se_state.get("substrate_mode", "unknown") or "unknown")
            else:
                combined_se = float(se_state.get("Se", 0.0))
                substrate_mode = "unknown"
        else:
            combined_se = 0.0
            substrate_mode = "unknown"

        # Adversarial state
        attacks_total = int(getattr(state, "attacks_total", 0))
        attacks_survived = int(getattr(state, "attacks_survived", 0))
        survival_rate = attacks_survived / max(1, attacks_total)

        # Check for fatal unsolved attacks
        adversarial_attacks = getattr(state, "adversarial_attacks", []) or []
        has_fatal_unsolved = False
        for attack in adversarial_attacks:
            if hasattr(attack, "severity") and hasattr(attack, "survived"):
                if attack.severity == "fatal" and not attack.survived:
                    has_fatal_unsolved = True
                    break
            elif isinstance(attack, dict):
                if attack.get("severity") == "fatal" and not attack.get("survived"):
                    has_fatal_unsolved = True
                    break

        # Triangulation
        triangulation = getattr(state, "triangulation", None) or {}
        if isinstance(triangulation, dict):
            triangulated = bool(triangulation.get("triangulated", False))
        else:
            triangulated = False

        return {
            "combined_se": combined_se,
            "substrate_mode": substrate_mode,
            "attacks_total": attacks_total,
            "attacks_survived": attacks_survived,
            "survival_rate": survival_rate,
            "has_fatal_unsolved": has_fatal_unsolved,
            "triangulated": triangulated,
        }

    def evaluate_proposed_conclusion(
        self,
        state: Any,
        proposed_answer: str,
        proposed_confidence: float,
    ) -> Tuple[BridgeDecision, BridgeReceipt]:
        """
        Evaluate whether a proposed conclusion should be allowed.

        Applies production rules in priority order:
        1. gate_conclusion_low_se (blocks)
        2. gate_conclusion_conflicted_substrate (requires reflection)
        3. adversarial_recovery_rule (requires reflection)
        4. confidence_downgrade_rule (caps confidence)
        5. gate_conclusion_high_se (allows)
        6. fallback_continue_rule (continues gathering)

        Returns:
            Tuple of (BridgeDecision, BridgeReceipt)
        """
        if not self.config.enabled:
            # Bridge disabled - allow everything
            decision = BridgeDecision(
                outcome=BridgeOutcome.ALLOW_CONCLUDE,
                rule_fired="bridge_disabled",
                reasons=["PSSH bridge disabled"],
                adjusted_confidence=proposed_confidence,
            )
            return decision, self._make_receipt(
                "conclude", proposed_confidence, decision,
                {"combined_se": 0, "substrate_mode": "disabled", "attacks_total": 0,
                 "attacks_survived": 0, "triangulated": True}
            )

        ctx = self._extract_context(state)
        reasons: List[str] = []

        # Rule 1: gate_conclusion_low_se
        if ctx["combined_se"] < self.config.abort_se:
            reasons.append(f"combined_se {ctx['combined_se']:.3f} < abort threshold {self.config.abort_se}")
            decision = BridgeDecision(
                outcome=BridgeOutcome.CONTINUE_GATHERING,
                rule_fired="gate_conclusion_low_se",
                reasons=reasons,
                adjusted_confidence=min(proposed_confidence, self.config.confidence_cap_low_se),
                continued=True,
            )
            return decision, self._make_receipt("conclude", proposed_confidence, decision, ctx)

        # Rule 2: gate_conclusion_conflicted_substrate
        if ctx["substrate_mode"] == "conflicted":
            reasons.append("substrate_mode is conflicted - waves out of phase")
            decision = BridgeDecision(
                outcome=BridgeOutcome.REQUIRE_REFLECTION,
                rule_fired="gate_conclusion_conflicted_substrate",
                reasons=reasons,
                adjusted_confidence=min(proposed_confidence, self.config.confidence_cap_conflicted),
                required_reflection=True,
            )
            return decision, self._make_receipt("conclude", proposed_confidence, decision, ctx)

        # Rule 3: adversarial_recovery_rule
        if ctx["has_fatal_unsolved"]:
            reasons.append("fatal adversarial attack not survived")
            decision = BridgeDecision(
                outcome=BridgeOutcome.REQUIRE_REFLECTION,
                rule_fired="adversarial_recovery_rule",
                reasons=reasons,
                adjusted_confidence=min(proposed_confidence, 0.45),
                required_reflection=True,
            )
            return decision, self._make_receipt("conclude", proposed_confidence, decision, ctx)

        # Rule 3b: Low survival rate (but no fatal unsolved)
        if ctx["attacks_total"] > 0 and ctx["survival_rate"] < self.config.min_survival_rate:
            reasons.append(
                f"attack survival rate {ctx['survival_rate']:.2f} < required {self.config.min_survival_rate:.2f}"
            )
            decision = BridgeDecision(
                outcome=BridgeOutcome.REQUIRE_REFLECTION,
                rule_fired="adversarial_recovery_rule",
                reasons=reasons,
                adjusted_confidence=min(proposed_confidence, 0.50),
                required_reflection=True,
            )
            return decision, self._make_receipt("conclude", proposed_confidence, decision, ctx)

        # Rule 4: confidence_downgrade_rule
        if not ctx["triangulated"]:
            reasons.append("evidence not triangulated - single source")
            capped = min(proposed_confidence, self.config.confidence_cap_untriangulated)
            decision = BridgeDecision(
                outcome=BridgeOutcome.DOWNGRADE_CONFIDENCE,
                rule_fired="confidence_downgrade_rule",
                reasons=reasons,
                adjusted_confidence=capped,
            )
            return decision, self._make_receipt("conclude", proposed_confidence, decision, ctx)

        # Rule 5: gate_conclusion_high_se (all checks passed)
        if (
            ctx["combined_se"] >= self.config.min_conclude_se
            and ctx["survival_rate"] >= self.config.min_survival_rate
            and ctx["triangulated"]
        ):
            reasons.append("policy gate passed - Se/survival/triangulation OK")
            decision = BridgeDecision(
                outcome=BridgeOutcome.ALLOW_CONCLUDE,
                rule_fired="gate_conclusion_high_se",
                reasons=reasons,
                adjusted_confidence=proposed_confidence,
            )
            return decision, self._make_receipt("conclude", proposed_confidence, decision, ctx)

        # Rule 6: fallback - Se between abort and min_conclude
        reasons.append(f"Se {ctx['combined_se']:.3f} below conclude threshold {self.config.min_conclude_se}")
        decision = BridgeDecision(
            outcome=BridgeOutcome.CONTINUE_GATHERING,
            rule_fired="fallback_continue_rule",
            reasons=reasons,
            adjusted_confidence=min(proposed_confidence, 0.55),
            continued=True,
        )
        return decision, self._make_receipt("conclude", proposed_confidence, decision, ctx)

    def evaluate_tool_action(
        self,
        state: Any,
        tool_name: str,
        tool_args: Dict[str, Any],
    ) -> Tuple[BridgeDecision, BridgeReceipt]:
        """
        Evaluate whether a tool action should be allowed.

        Applies unsafe_tool_gate rule.

        Returns:
            Tuple of (BridgeDecision, BridgeReceipt)
        """
        if not self.config.enabled:
            decision = BridgeDecision(
                outcome=BridgeOutcome.ALLOW_CONCLUDE,  # ALLOW_CONCLUDE means allow action
                rule_fired="bridge_disabled",
                reasons=["PSSH bridge disabled"],
            )
            return decision, self._make_receipt(
                "tool", 0.0, decision,
                {"combined_se": 0, "substrate_mode": "disabled", "attacks_total": 0,
                 "attacks_survived": 0, "triangulated": True}
            )

        ctx = self._extract_context(state)
        reasons: List[str] = []

        # Rule: unsafe_tool_gate
        if tool_name in self.config.blocked_tools:
            reasons.append(f"tool '{tool_name}' is blocked by policy")
            decision = BridgeDecision(
                outcome=BridgeOutcome.BLOCK_ACTION,
                rule_fired="unsafe_tool_gate",
                reasons=reasons,
                blocked=True,
            )
            return decision, self._make_receipt("tool", 0.0, decision, ctx)

        # Check for dangerous patterns in args
        dangerous_patterns = ["rm -rf", "drop table", "delete from", "truncate"]
        args_str = str(tool_args).lower()
        for pattern in dangerous_patterns:
            if pattern in args_str:
                reasons.append(f"tool args contain dangerous pattern: '{pattern}'")
                decision = BridgeDecision(
                    outcome=BridgeOutcome.BLOCK_ACTION,
                    rule_fired="unsafe_tool_gate",
                    reasons=reasons,
                    blocked=True,
                )
                return decision, self._make_receipt("tool", 0.0, decision, ctx)

        # Tool allowed
        decision = BridgeDecision(
            outcome=BridgeOutcome.ALLOW_CONCLUDE,  # Allow action
            rule_fired="tool_action_allowed",
            reasons=["tool allowed by policy"],
        )
        return decision, self._make_receipt("tool", 0.0, decision, ctx)

    def _make_receipt(
        self,
        action_type: str,
        proposed_confidence: float,
        decision: BridgeDecision,
        ctx: Dict[str, Any],
    ) -> BridgeReceipt:
        """Create audit receipt for the gate decision."""
        return BridgeReceipt(
            receipt_id=f"bridge-{uuid.uuid4().hex[:12]}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            rule_fired=decision.rule_fired,
            decision=decision.outcome.value,
            proposed_action_type=action_type,
            proposed_confidence=proposed_confidence,
            adjusted_confidence=(
                proposed_confidence if decision.adjusted_confidence is None
                else decision.adjusted_confidence
            ),
            combined_se=float(ctx.get("combined_se", 0)),
            substrate_mode=str(ctx.get("substrate_mode", "unknown")),
            attacks_total=int(ctx.get("attacks_total", 0)),
            attacks_survived=int(ctx.get("attacks_survived", 0)),
            triangulated=bool(ctx.get("triangulated", False)),
            reasons=decision.reasons,
            blocked=decision.blocked,
            continued=decision.continued,
            required_reflection=decision.required_reflection,
        )
