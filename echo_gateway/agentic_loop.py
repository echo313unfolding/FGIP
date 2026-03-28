"""
Agentic Reasoning Loop - Think, Act, Observe, Reflect.

WO-AGENTIC-REASONER-01

Implements the ReAct pattern (Reasoning + Acting) with:
- Chain-of-thought prompting
- Tool calling
- Self-reflection and error correction
- Iteration until solved
"""

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .agentic_prompts import (
    AGENTIC_SYSTEM_PROMPT,
    REFLECTION_PROMPT,
    OBSERVATION_PROMPT,
    CONCLUSION_PROMPT,
    format_tools_description,
)
from .agentic_tools import AgenticToolDispatcher, get_all_agentic_tools
from .agentic_cognition import (
    AdversarialTester,
    AdversarialAttack,
    SeRegulator,
    SeState,
    EvidenceTriangulator,
    SubstrateEnhancedRegulator,
    ADVERSARIAL_REFLECTION_PROMPT,
    FIBPI_AVAILABLE,
)
from .pssh_agentic_bridge import (
    PSSHAgenticBridge,
    BridgeOutcome,
    BridgeConfig,
)


@dataclass
class ThoughtStep:
    """A single chain-of-thought step."""
    step_id: str
    iteration: int
    step_type: str  # 'think', 'action', 'observation', 'reflection', 'conclusion'
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "iteration": self.iteration,
            "step_type": self.step_type,
            "content": self.content,
            "timestamp": self.timestamp,
        }


@dataclass
class ToolResult:
    """Result from a tool call."""
    tool_name: str
    tool_args: Dict[str, Any]
    result: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "result": self.result,
            "timestamp": self.timestamp,
        }


@dataclass
class Reflection:
    """Self-critique moment."""
    reflection_id: str
    trigger: str
    assessment: str  # 'sound', 'error', 'stuck'
    critique: str
    correction: Optional[str]
    confidence_delta: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reflection_id": self.reflection_id,
            "trigger": self.trigger,
            "assessment": self.assessment,
            "critique": self.critique,
            "correction": self.correction,
            "confidence_delta": self.confidence_delta,
            "timestamp": self.timestamp,
        }


@dataclass
class ParsedAction:
    """Parsed action from LLM response."""
    action_type: str  # 'tool_call', 'conclude', 'invalid'
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    answer: Optional[str] = None
    confidence: Optional[float] = None
    raw: str = ""


@dataclass
class AgenticState:
    """State tracked across reasoning loop iterations."""
    task: str
    scratchpad: List[ThoughtStep] = field(default_factory=list)
    tool_results: List[ToolResult] = field(default_factory=list)
    reflections: List[Reflection] = field(default_factory=list)
    iteration: int = 0
    max_iterations: int = 10
    status: str = "initialized"  # 'thinking', 'acting', 'reflecting', 'complete', 'error'
    confidence: float = 0.5
    final_answer: Optional[str] = None
    receipt_id: str = field(default_factory=lambda: f"agentic-{uuid.uuid4().hex[:8]}")
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    # Cognitive extensions
    adversarial_attacks: List[Any] = field(default_factory=list)  # AdversarialAttack objects
    se_state: Optional[Dict[str, Any]] = None  # SeState as dict
    triangulation: Optional[Dict[str, Any]] = None
    attacks_survived: int = 0
    attacks_total: int = 0
    # PSSH bridge
    bridge_receipts: List[Dict[str, Any]] = field(default_factory=list)
    bridge_allowed: bool = False
    bridge_rule_fired: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task": self.task,
            "scratchpad": [s.to_dict() for s in self.scratchpad],
            "tool_results": [t.to_dict() for t in self.tool_results],
            "reflections": [r.to_dict() for r in self.reflections],
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
            "status": self.status,
            "confidence": self.confidence,
            "final_answer": self.final_answer,
            "receipt_id": self.receipt_id,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            # Cognitive extensions
            "adversarial_attacks": [a.to_dict() if hasattr(a, 'to_dict') else a for a in self.adversarial_attacks],
            "se_state": self.se_state,
            "triangulation": self.triangulation,
            "attacks_survived": self.attacks_survived,
            "attacks_total": self.attacks_total,
            # PSSH bridge
            "bridge_receipts": self.bridge_receipts,
            "bridge_allowed": self.bridge_allowed,
            "bridge_rule_fired": self.bridge_rule_fired,
        }


class AgenticReasoningLoop:
    """
    Agentic reasoning loop with chain-of-thought and self-reflection.

    Algorithm:
    1. THINK: Generate chain-of-thought, identify next action
    2. ACT: Execute tool if needed
    3. OBSERVE: Process tool results
    4. REFLECT: Self-critique, detect errors
    5. Repeat until solved or max iterations
    """

    def __init__(
        self,
        llm_client,
        db_path: str = "fgip.db",
        reflect_every: int = 3,
        enable_adversarial: bool = True,
        enable_se_routing: bool = True,
    ):
        """
        Initialize the reasoning loop.

        Args:
            llm_client: LLMClient instance for chat completions
            db_path: Path to FGIP database
            reflect_every: Force reflection every N iterations
            enable_adversarial: Enable adversarial self-testing
            enable_se_routing: Enable Se-based confidence routing
        """
        self.llm_client = llm_client
        self.tool_dispatcher = AgenticToolDispatcher(db_path)
        self.tools = get_all_agentic_tools()
        self.reflect_every = reflect_every

        # Cognitive extensions
        self.enable_adversarial = enable_adversarial
        self.enable_se_routing = enable_se_routing
        self.adversarial_tester = AdversarialTester(llm_client) if enable_adversarial else None
        self.triangulator = EvidenceTriangulator()

        # Use substrate-enhanced regulator if FibPi3D is available
        if enable_se_routing:
            if FIBPI_AVAILABLE:
                self.se_regulator = SubstrateEnhancedRegulator(n_nodes=128)
                self.use_substrate = True
            else:
                self.se_regulator = SeRegulator()
                self.use_substrate = False
        else:
            self.se_regulator = None
            self.use_substrate = False

        # PSSH policy bridge
        self.pssh_bridge = PSSHAgenticBridge()

    async def run(
        self,
        task: str,
        max_iterations: int = 10,
        require_reflection: bool = True,
    ) -> AgenticState:
        """
        Execute the reasoning loop.

        Args:
            task: The task/question to solve
            max_iterations: Maximum iterations before stopping
            require_reflection: Whether to require periodic reflection

        Returns:
            AgenticState with full reasoning trace
        """
        state = AgenticState(task=task, max_iterations=max_iterations)
        state.status = "thinking"

        # Build system prompt with tools
        tools_desc = format_tools_description(self.tools)
        system_prompt = AGENTIC_SYSTEM_PROMPT.format(tools_description=tools_desc)

        # Conversation history for the LLM
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Task: {task}"},
        ]

        while state.iteration < max_iterations:
            state.iteration += 1

            try:
                # 1. THINK - Get chain-of-thought from LLM
                state.status = "thinking"
                response = await self._think(messages)

                # Record thought
                thought = ThoughtStep(
                    step_id=f"thought-{state.iteration}",
                    iteration=state.iteration,
                    step_type="think",
                    content=response,
                )
                state.scratchpad.append(thought)
                messages.append({"role": "assistant", "content": response})

                # 2. Parse action from response
                action = self._parse_action(response)

                if action.action_type == "conclude":
                    # Before concluding: run cognitive checks
                    proposed_answer = action.answer
                    proposed_confidence = action.confidence or state.confidence

                    # 1. Compute Se state for routing decision
                    if self.se_regulator:
                        tool_dicts = [t.to_dict() for t in state.tool_results]
                        scratchpad_dicts = [s.to_dict() for s in state.scratchpad]
                        reflection_dicts = [r.to_dict() for r in state.reflections]

                        if self.use_substrate:
                            # Use enhanced regulator with FibPi3D substrate
                            enhanced_se = self.se_regulator.compute_enhanced_se(
                                tool_dicts, scratchpad_dicts, reflection_dicts
                            )
                            state.se_state = enhanced_se
                            routing = self.se_regulator.get_enhanced_routing(enhanced_se)
                        else:
                            # Use basic regulator
                            se_state = self.se_regulator.compute_se_state(
                                tool_dicts, scratchpad_dicts, reflection_dicts
                            )
                            state.se_state = se_state.to_dict()
                            routing = self.se_regulator.get_routing_decision(se_state)

                        proposed_confidence += routing.get("confidence_modifier", 0)

                        # If Se says abort, don't conclude yet
                        if routing["decision"] == "abort":
                            messages.append({
                                "role": "user",
                                "content": f"Se routing: {routing['reason']}\n{routing.get('warning', '')}\n"
                                           "Please gather more evidence before concluding."
                            })
                            continue

                    # 2. Run adversarial self-testing
                    if self.adversarial_tester and proposed_answer:
                        state.status = "adversarial_testing"
                        attacks = await self.adversarial_tester.attack_conclusion(
                            conclusion=proposed_answer,
                            evidence=[t.to_dict() for t in state.tool_results],
                            tool_calls=[t.to_dict() for t in state.tool_results],
                        )

                        # Defend against attacks
                        attacks = await self.adversarial_tester.defend_against_attacks(
                            conclusion=proposed_answer,
                            attacks=attacks,
                            evidence=[t.to_dict() for t in state.tool_results],
                        )

                        state.adversarial_attacks = attacks
                        state.attacks_total = len(attacks)
                        state.attacks_survived = sum(1 for a in attacks if a.survived)

                        # Check for fatal attacks
                        fatal_attacks = [a for a in attacks if a.severity == "fatal" and not a.survived]
                        if fatal_attacks:
                            # Fatal attack not survived - don't conclude
                            attack_summary = "\n".join([f"- {a.attack_content[:100]}" for a in fatal_attacks])
                            messages.append({
                                "role": "user",
                                "content": f"ADVERSARIAL CHECK FAILED:\n{attack_summary}\n\n"
                                           "These attacks were not successfully defended. "
                                           "Reconsider your conclusion or gather more evidence."
                            })
                            proposed_confidence -= 0.2
                            state.confidence = max(0.1, proposed_confidence)
                            continue

                        # Adjust confidence based on attack survival rate
                        if state.attacks_total > 0:
                            survival_rate = state.attacks_survived / state.attacks_total
                            proposed_confidence = proposed_confidence * (0.5 + 0.5 * survival_rate)

                    # 3. Check triangulation
                    if proposed_answer:
                        triangulation = self.triangulator.triangulate(
                            [t.to_dict() for t in state.tool_results],
                            proposed_answer,
                        )
                        state.triangulation = triangulation
                        proposed_confidence += triangulation.get("confidence_boost", 0)

                    # 4. PSSH Bridge - Policy gate decision
                    bridge_decision, bridge_receipt = self.pssh_bridge.evaluate_proposed_conclusion(
                        state,
                        proposed_answer,
                        proposed_confidence,
                    )
                    state.bridge_receipts.append(bridge_receipt.to_dict())
                    state.bridge_rule_fired = bridge_decision.rule_fired

                    if bridge_decision.outcome == BridgeOutcome.ALLOW_CONCLUDE:
                        # Policy gate passed - conclude
                        state.final_answer = proposed_answer
                        state.confidence = max(0.0, min(1.0, bridge_receipt.adjusted_confidence))
                        state.status = "complete"
                        state.completed_at = datetime.now(timezone.utc).isoformat()
                        state.bridge_allowed = True
                        break

                    elif bridge_decision.outcome == BridgeOutcome.DOWNGRADE_CONFIDENCE:
                        # Allow conclude but cap confidence
                        state.final_answer = proposed_answer
                        state.confidence = max(0.0, min(1.0, bridge_receipt.adjusted_confidence))
                        state.status = "complete"
                        state.completed_at = datetime.now(timezone.utc).isoformat()
                        state.bridge_allowed = True
                        break

                    elif bridge_decision.outcome == BridgeOutcome.REQUIRE_REFLECTION:
                        # Policy requires more reflection
                        messages.append({
                            "role": "user",
                            "content": f"PSSH bridge requires reflection. Rule: {bridge_decision.rule_fired}. "
                                       f"Reasons: {'; '.join(bridge_decision.reasons)}. "
                                       "Please reflect on this feedback and gather more evidence."
                        })
                        state.bridge_allowed = False
                        continue

                    elif bridge_decision.outcome == BridgeOutcome.CONTINUE_GATHERING:
                        # Policy requires more evidence
                        messages.append({
                            "role": "user",
                            "content": f"PSSH bridge requires more evidence. Rule: {bridge_decision.rule_fired}. "
                                       f"Reasons: {'; '.join(bridge_decision.reasons)}. "
                                       "Continue gathering evidence before concluding."
                        })
                        state.bridge_allowed = False
                        continue

                    else:
                        # Fallback - continue gathering
                        state.bridge_allowed = False
                        continue

                elif action.action_type == "tool_call":
                    # PSSH Bridge - Check if tool action is allowed
                    tool_decision, tool_receipt = self.pssh_bridge.evaluate_tool_action(
                        state,
                        action.tool_name,
                        action.tool_args or {},
                    )
                    state.bridge_receipts.append(tool_receipt.to_dict())

                    if tool_decision.outcome == BridgeOutcome.BLOCK_ACTION:
                        # Tool blocked by policy
                        messages.append({
                            "role": "user",
                            "content": f"PSSH bridge blocked tool '{action.tool_name}'. "
                                       f"Rule: {tool_decision.rule_fired}. "
                                       f"Reasons: {'; '.join(tool_decision.reasons)}. "
                                       "Choose a different action."
                        })
                        continue

                    # 3. ACT - Execute tool (allowed by policy)
                    state.status = "acting"
                    tool_result = await self._act(action.tool_name, action.tool_args)

                    # Record result
                    result_obj = ToolResult(
                        tool_name=action.tool_name,
                        tool_args=action.tool_args,
                        result=tool_result,
                    )
                    state.tool_results.append(result_obj)

                    # 4. OBSERVE - Format result for LLM
                    observation = self._observe(action.tool_name, action.tool_args, tool_result)
                    obs_step = ThoughtStep(
                        step_id=f"observation-{state.iteration}",
                        iteration=state.iteration,
                        step_type="observation",
                        content=observation,
                    )
                    state.scratchpad.append(obs_step)
                    messages.append({"role": "user", "content": observation})

                else:
                    # Invalid action - ask for clarification
                    messages.append({
                        "role": "user",
                        "content": "I couldn't parse your action. Please use the format:\n"
                                   "<action>\ntool_call: {\"name\": \"...\", \"args\": {...}}\n</action>\n"
                                   "or\n<action>\nconclude: {\"answer\": \"...\", \"confidence\": 0.85}\n</action>"
                    })

                # 5. REFLECT - Periodic self-critique
                if require_reflection and state.iteration % self.reflect_every == 0:
                    state.status = "reflecting"
                    reflection = await self._reflect(state, messages)
                    state.reflections.append(reflection)

                    # Adjust confidence
                    state.confidence = max(0.0, min(1.0, state.confidence + reflection.confidence_delta))

                    # If stuck, add reflection to conversation
                    if reflection.assessment in ("error", "stuck"):
                        messages.append({
                            "role": "user",
                            "content": f"Reflection: {reflection.critique}\n"
                                       f"Suggested correction: {reflection.correction}\n"
                                       "Please adjust your approach."
                        })

            except Exception as e:
                state.status = "error"
                error_step = ThoughtStep(
                    step_id=f"error-{state.iteration}",
                    iteration=state.iteration,
                    step_type="error",
                    content=str(e),
                )
                state.scratchpad.append(error_step)
                break

        # Generate receipt
        self._generate_receipt(state)

        return state

    async def _think(self, messages: List[Dict]) -> str:
        """Generate chain-of-thought response from LLM."""
        response = await self.llm_client.chat(
            messages=messages,
            tools=self.tools,
            temperature=0.0,
        )

        # Extract content
        if "choices" in response and response["choices"]:
            choice = response["choices"][0]
            if "message" in choice:
                return choice["message"].get("content", "")

        return ""

    def _parse_action(self, response: str) -> ParsedAction:
        """Parse action from LLM response."""
        # Look for <action> block
        action_match = re.search(r"<action>(.*?)</action>", response, re.DOTALL)
        if not action_match:
            return ParsedAction(action_type="invalid", raw=response)

        action_content = action_match.group(1).strip()

        # Check for tool_call
        if "tool_call:" in action_content:
            try:
                json_match = re.search(r"tool_call:\s*(\{.*\})", action_content, re.DOTALL)
                if json_match:
                    tool_data = json.loads(json_match.group(1))
                    return ParsedAction(
                        action_type="tool_call",
                        tool_name=tool_data.get("name"),
                        tool_args=tool_data.get("args", {}),
                        raw=action_content,
                    )
            except json.JSONDecodeError:
                pass

        # Check for conclude
        if "conclude:" in action_content:
            try:
                json_match = re.search(r"conclude:\s*(\{.*\})", action_content, re.DOTALL)
                if json_match:
                    conclude_data = json.loads(json_match.group(1))
                    return ParsedAction(
                        action_type="conclude",
                        answer=conclude_data.get("answer"),
                        confidence=conclude_data.get("confidence", 0.5),
                        raw=action_content,
                    )
            except json.JSONDecodeError:
                pass

        return ParsedAction(action_type="invalid", raw=action_content)

    async def _act(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool and return results."""
        return await self.tool_dispatcher.dispatch(tool_name, tool_args)

    def _observe(self, tool_name: str, tool_args: Dict[str, Any], result: Dict[str, Any]) -> str:
        """Format tool result as observation for LLM."""
        result_str = json.dumps(result, indent=2, default=str)
        return f"Tool result from {tool_name}({json.dumps(tool_args)}):\n```json\n{result_str}\n```\n\nContinue your reasoning based on this result."

    async def _reflect(self, state: AgenticState, messages: List[Dict]) -> Reflection:
        """Generate self-reflection with Se state and adversarial checking."""
        # Format scratchpad
        scratchpad_str = "\n".join(
            f"[{s.step_type}] {s.content[:500]}..."
            for s in state.scratchpad[-5:]  # Last 5 steps
        )

        # Format tool results
        tool_results_str = "\n".join(
            f"- {t.tool_name}: {json.dumps(t.result)[:200]}..."
            for t in state.tool_results[-3:]  # Last 3 results
        )

        # Compute Se state for reflection
        H, C, D, Se = 0.5, 0.5, 0.0, 0.0
        if self.se_regulator:
            tool_dicts = [t.to_dict() for t in state.tool_results]
            scratchpad_dicts = [s.to_dict() for s in state.scratchpad]
            reflection_dicts = [r.to_dict() for r in state.reflections]

            if self.use_substrate:
                # Use enhanced regulator
                enhanced_se = self.se_regulator.compute_enhanced_se(
                    tool_dicts, scratchpad_dicts, reflection_dicts
                )
                state.se_state = enhanced_se
                # Extract values for prompt (use traditional Se values)
                trad = enhanced_se.get("traditional_se", {})
                H = trad.get("H", 0.5)
                C = trad.get("C", 0.5)
                D = trad.get("D", 0.0)
                Se = enhanced_se.get("combined_Se", 0.0)
            else:
                se_state = self.se_regulator.compute_se_state(
                    tool_dicts, scratchpad_dicts, reflection_dicts
                )
                state.se_state = se_state.to_dict()
                H, C, D, Se = se_state.H, se_state.C, se_state.D, se_state.Se

        # Build reflection prompt - use adversarial version if enabled
        if self.enable_adversarial:
            reflection_prompt = ADVERSARIAL_REFLECTION_PROMPT.format(
                scratchpad=scratchpad_str,
                tool_results=tool_results_str,
                H=H,
                C=C,
                D=D,
                Se=Se,
            )
        else:
            reflection_prompt = REFLECTION_PROMPT.format(
                scratchpad=scratchpad_str,
                tool_results=tool_results_str,
            )

        # Get reflection from LLM
        reflection_messages = messages + [
            {"role": "user", "content": reflection_prompt}
        ]

        response = await self.llm_client.chat(
            messages=reflection_messages,
            temperature=0.0,
        )

        content = ""
        if "choices" in response and response["choices"]:
            content = response["choices"][0].get("message", {}).get("content", "")

        # Parse reflection
        assessment = "sound"
        confidence_delta = 0.0
        critique = content
        correction = None

        if "<reflection>" in content:
            ref_match = re.search(r"<reflection>(.*?)</reflection>", content, re.DOTALL)
            if ref_match:
                ref_content = ref_match.group(1)

                if "assessment:" in ref_content:
                    ass_match = re.search(r"assessment:\s*(\w+)", ref_content)
                    if ass_match:
                        assessment = ass_match.group(1)

                if "confidence_delta:" in ref_content:
                    delta_match = re.search(r"confidence_delta:\s*([-+]?[\d.]+)", ref_content)
                    if delta_match:
                        confidence_delta = float(delta_match.group(1))

                if "correction:" in ref_content:
                    corr_match = re.search(r"correction:\s*(.+?)(?=\n|$)", ref_content)
                    if corr_match:
                        correction = corr_match.group(1).strip()

                # Parse Se routing decision from reflection
                if "se_routing:" in ref_content:
                    route_match = re.search(r"se_routing:\s*(\w+)", ref_content)
                    if route_match:
                        se_routing = route_match.group(1).lower()
                        if se_routing == "abort":
                            confidence_delta = min(confidence_delta, -0.2)

                critique = ref_content

        return Reflection(
            reflection_id=f"reflection-{state.iteration}",
            trigger=f"periodic (iteration {state.iteration}, Se={Se:.3f})",
            assessment=assessment,
            critique=critique,
            correction=correction,
            confidence_delta=confidence_delta,
        )

    def _generate_receipt(self, state: AgenticState):
        """Generate audit receipt for the reasoning session."""
        receipt_dir = Path("receipts/agentic")
        receipt_dir.mkdir(parents=True, exist_ok=True)

        # Compute scratchpad hash
        scratchpad_str = json.dumps([s.to_dict() for s in state.scratchpad])
        scratchpad_hash = hashlib.sha256(scratchpad_str.encode()).hexdigest()[:16]

        receipt = {
            "receipt_id": state.receipt_id,
            "schema": "agentic_reasoning_v2",  # v2 includes cognitive state
            "work_order": "WO-AGENTIC-COGNITION-01",
            "inputs": {
                "task": state.task,
                "max_iterations": state.max_iterations,
            },
            "outputs": {
                "final_answer": state.final_answer,
                "confidence": state.confidence,
                "iterations": state.iteration,
                "tool_calls_count": len(state.tool_results),
                "reflection_count": len(state.reflections),
            },
            # Cognitive state
            "cognitive": {
                "se_state": state.se_state,
                "adversarial": {
                    "attacks_total": state.attacks_total,
                    "attacks_survived": state.attacks_survived,
                    "survival_rate": state.attacks_survived / max(1, state.attacks_total),
                },
                "triangulation": state.triangulation,
            },
            "scratchpad_hash": scratchpad_hash,
            "status": "PASS" if state.status == "complete" else "INCOMPLETE",
            "created_at": state.created_at,
            "completed_at": state.completed_at,
        }

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        receipt_path = receipt_dir / f"{state.receipt_id}_{timestamp}.json"

        with open(receipt_path, "w") as f:
            json.dump(receipt, f, indent=2)

        return receipt_path
