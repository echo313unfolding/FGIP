"""
Cognitive extensions for agentic reasoning.

WO-AGENTIC-COGNITION-01

Adds:
1. Adversarial self-testing (attack your own conclusions)
2. Se-based confidence regulation (H×C×D entropy routing)
3. Evidence triangulation (multi-source coherence)
4. Scale-invariant reasoning (local→global coherence)

Inspired by:
- Regime classifier's Se = H × C × D
- Palantir-mode adversarial testing
- Nature's scale-invariant self-organization
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone

# Import substrate integration
try:
    from .agentic_substrate import SubstrateIntegratedReasoning, FIBPI_AVAILABLE
except ImportError:
    FIBPI_AVAILABLE = False
    SubstrateIntegratedReasoning = None


@dataclass
class AdversarialAttack:
    """A single adversarial attack on a conclusion."""
    attack_id: str
    attack_type: str  # 'counter_argument', 'missing_evidence', 'selection_bias', 'confounding', 'base_rate'
    claim_targeted: str
    attack_content: str
    severity: str  # 'fatal', 'weakening', 'minor'
    survived: bool = False
    defense: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attack_id": self.attack_id,
            "attack_type": self.attack_type,
            "claim_targeted": self.claim_targeted,
            "attack_content": self.attack_content,
            "severity": self.severity,
            "survived": self.survived,
            "defense": self.defense,
            "timestamp": self.timestamp,
        }


@dataclass
class SeState:
    """
    Signal Entropy state for reasoning confidence.

    Adapted from regime_classifier.py for reasoning context:
    - H (Entropy): How contradictory/uncertain is the evidence?
    - C (Coherence): Do different evidence sources agree?
    - D (Depth): How many independent evidence chains?
    - Se = H × C × D (routing metric)

    High Se = high entropy, high coherence, high depth
           = complex but well-supported conclusion

    Low Se = either simple (low H), unsupported (low D), or conflicting (low C)
    """
    H: float = 0.5  # Entropy (0=certain, 1=chaotic)
    C: float = 0.5  # Coherence (0=conflicting, 1=unanimous)
    D: float = 0.0  # Depth (0=no evidence, 1=full triangulation)
    Se: float = 0.0  # H × C × D

    # Reasoning-specific
    evidence_sources: int = 0
    contradictions: int = 0
    tool_calls: int = 0
    source_tiers: List[int] = field(default_factory=list)  # Tier 0, 1, 2 counts

    def compute(self) -> float:
        """Recompute Se from components."""
        self.Se = self.H * self.C * self.D
        return self.Se

    def to_dict(self) -> Dict[str, Any]:
        return {
            "H": round(self.H, 4),
            "C": round(self.C, 4),
            "D": round(self.D, 4),
            "Se": round(self.Se, 4),
            "evidence_sources": self.evidence_sources,
            "contradictions": self.contradictions,
            "tool_calls": self.tool_calls,
            "source_tiers": self.source_tiers,
        }


# Adversarial attack templates
ADVERSARIAL_ATTACKS = {
    "counter_argument": """Generate the strongest counter-argument to this conclusion:
CONCLUSION: {conclusion}

Think like a skeptical opponent. What would disprove this? What alternative explanation fits the same evidence?

Format:
<attack>
type: counter_argument
target: [what claim this attacks]
argument: [the counter-argument]
severity: [fatal/weakening/minor]
</attack>""",

    "missing_evidence": """What evidence is MISSING that would be needed to prove this conclusion?
CONCLUSION: {conclusion}
EVIDENCE USED: {evidence}

What wasn't checked? What data sources weren't queried? What assumptions weren't verified?

Format:
<attack>
type: missing_evidence
target: [what claim this attacks]
missing: [what evidence is needed]
severity: [fatal/weakening/minor]
</attack>""",

    "selection_bias": """Check for selection bias in this conclusion:
CONCLUSION: {conclusion}
TOOL CALLS: {tool_calls}

Did we only query nodes that support our hypothesis? Did we ignore contradicting data?
Is this cherry-picking?

Format:
<attack>
type: selection_bias
target: [what claim this attacks]
bias: [the selection bias identified]
severity: [fatal/weakening/minor]
</attack>""",

    "confounding": """Identify confounding variables:
CONCLUSION: {conclusion}
CAUSAL CLAIM: {causal_claim}

What third factor could explain BOTH the cause and effect?
Is correlation being mistaken for causation?

Format:
<attack>
type: confounding
target: [what claim this attacks]
confound: [the confounding variable]
severity: [fatal/weakening/minor]
</attack>""",

    "base_rate": """Apply base rate analysis:
CONCLUSION: {conclusion}
PATTERN FOUND: {pattern}

Is this pattern significant or expected by chance?
What's the base rate in the general population?

Format:
<attack>
type: base_rate
target: [what claim this attacks]
base_rate: [the base rate argument]
severity: [fatal/weakening/minor]
</attack>""",
}


class AdversarialTester:
    """
    Adversarial self-testing for reasoning conclusions.

    Implements Palantir-mode doctrine:
    - Break the thesis first
    - Generate strongest counter-arguments
    - Apply control groups and base rates
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client

    async def attack_conclusion(
        self,
        conclusion: str,
        evidence: List[Dict],
        tool_calls: List[Dict],
        attack_types: Optional[List[str]] = None,
    ) -> List[AdversarialAttack]:
        """
        Generate adversarial attacks against a conclusion.

        Args:
            conclusion: The conclusion to attack
            evidence: Evidence used to reach conclusion
            tool_calls: Tool calls made during reasoning
            attack_types: Which attack types to run (default: all)

        Returns:
            List of AdversarialAttack objects
        """
        if attack_types is None:
            attack_types = ["counter_argument", "missing_evidence", "selection_bias"]

        attacks = []

        for i, attack_type in enumerate(attack_types):
            if attack_type not in ADVERSARIAL_ATTACKS:
                continue

            template = ADVERSARIAL_ATTACKS[attack_type]

            # Format prompt
            prompt = template.format(
                conclusion=conclusion,
                evidence=json.dumps(evidence[:5], default=str),  # Limit for context
                tool_calls=json.dumps([t.get("tool_name", t.get("name", "?")) for t in tool_calls[:10]]),
                causal_claim=self._extract_causal_claim(conclusion),
                pattern=self._extract_pattern(conclusion),
            )

            # Generate attack
            try:
                response = await self.llm_client.chat(
                    messages=[
                        {"role": "system", "content": "You are an adversarial analyst. Your job is to find weaknesses in arguments. Be ruthless but fair."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                )

                content = ""
                if "choices" in response and response["choices"]:
                    content = response["choices"][0].get("message", {}).get("content", "")

                # Parse attack
                attack = self._parse_attack(content, attack_type, i)
                if attack:
                    attacks.append(attack)

            except Exception as e:
                # Don't fail on attack generation errors
                pass

        return attacks

    def _extract_causal_claim(self, conclusion: str) -> str:
        """Extract causal claims from conclusion."""
        causal_markers = ["causes", "leads to", "results in", "because", "therefore", "due to"]
        for marker in causal_markers:
            if marker in conclusion.lower():
                return conclusion
        return "No explicit causal claim"

    def _extract_pattern(self, conclusion: str) -> str:
        """Extract patterns from conclusion."""
        pattern_markers = ["pattern", "both sides", "ownership", "concentration", "same"]
        for marker in pattern_markers:
            if marker in conclusion.lower():
                return conclusion
        return "No explicit pattern claim"

    def _parse_attack(self, content: str, attack_type: str, index: int) -> Optional[AdversarialAttack]:
        """Parse attack from LLM response."""
        attack_match = re.search(r"<attack>(.*?)</attack>", content, re.DOTALL)
        if not attack_match:
            return None

        attack_content = attack_match.group(1)

        # Extract fields
        target = ""
        argument = ""
        severity = "minor"

        for line in attack_content.split("\n"):
            line = line.strip()
            if line.startswith("target:"):
                target = line[7:].strip()
            elif line.startswith("argument:") or line.startswith("missing:") or line.startswith("bias:") or line.startswith("confound:") or line.startswith("base_rate:"):
                argument = line.split(":", 1)[1].strip()
            elif line.startswith("severity:"):
                sev = line[9:].strip().lower()
                if sev in ("fatal", "weakening", "minor"):
                    severity = sev

        if not argument:
            argument = attack_content[:200]

        return AdversarialAttack(
            attack_id=f"attack-{attack_type}-{index}",
            attack_type=attack_type,
            claim_targeted=target,
            attack_content=argument,
            severity=severity,
        )

    async def defend_against_attacks(
        self,
        conclusion: str,
        attacks: List[AdversarialAttack],
        evidence: List[Dict],
    ) -> List[AdversarialAttack]:
        """
        Attempt to defend conclusion against attacks.

        Returns attacks with survived/defense fields updated.
        """
        for attack in attacks:
            if attack.severity == "minor":
                attack.survived = True
                attack.defense = "Minor concern acknowledged but not fatal to conclusion."
                continue

            # Generate defense
            defense_prompt = f"""An adversarial attack was made against this conclusion:

CONCLUSION: {conclusion}

ATTACK ({attack.attack_type}):
{attack.attack_content}

EVIDENCE AVAILABLE:
{json.dumps(evidence[:3], default=str)}

Can you defend the conclusion against this attack? Be honest - if the attack is valid, say so.

Format:
<defense>
survived: [true/false]
reasoning: [why the conclusion survives or fails]
</defense>"""

            try:
                response = await self.llm_client.chat(
                    messages=[
                        {"role": "system", "content": "You are evaluating whether a conclusion survives an adversarial attack. Be honest and rigorous."},
                        {"role": "user", "content": defense_prompt},
                    ],
                    temperature=0.0,
                )

                content = ""
                if "choices" in response and response["choices"]:
                    content = response["choices"][0].get("message", {}).get("content", "")

                # Parse defense
                defense_match = re.search(r"<defense>(.*?)</defense>", content, re.DOTALL)
                if defense_match:
                    defense_content = defense_match.group(1)
                    attack.survived = "survived: true" in defense_content.lower()

                    reasoning_match = re.search(r"reasoning:\s*(.+?)(?=\n|$)", defense_content, re.DOTALL)
                    if reasoning_match:
                        attack.defense = reasoning_match.group(1).strip()

            except Exception:
                pass

        return attacks


class SeRegulator:
    """
    Se-based confidence regulation for reasoning.

    Uses H×C×D to:
    - Route to different reasoning strategies
    - Adjust confidence based on evidence quality
    - Trigger deeper investigation when needed
    """

    # Routing thresholds
    SE_THRESHOLDS = {
        "high_confidence": 0.6,    # Se > 0.6 = well-supported
        "needs_more": 0.3,         # Se 0.3-0.6 = needs more evidence
        "low_confidence": 0.1,     # Se < 0.3 = poorly supported
        "abort": 0.05,             # Se < 0.1 = should not conclude
    }

    def compute_se_state(
        self,
        tool_results: List[Dict],
        scratchpad: List[Dict],
        reflections: List[Dict],
    ) -> SeState:
        """
        Compute Se state from reasoning trace.

        H (Entropy): Based on contradictions and uncertainty markers
        C (Coherence): Based on source agreement
        D (Depth): Based on evidence chain depth
        """
        se = SeState()
        se.tool_calls = len(tool_results)

        # Count evidence sources and tiers
        tier_counts = [0, 0, 0]  # Tier 0, 1, 2
        for result in tool_results:
            result_data = result.get("result", {})
            if isinstance(result_data, dict):
                # Check for source tiers in results
                if "sources" in result_data:
                    for source in result_data.get("sources", []):
                        tier = source.get("tier", 2)
                        if 0 <= tier <= 2:
                            tier_counts[tier] += 1
                se.evidence_sources += 1

        se.source_tiers = tier_counts

        # Compute H (Entropy) - higher if more uncertainty
        contradiction_markers = ["however", "but", "contradicts", "unlike", "opposite", "conflict"]
        contradictions = 0
        for step in scratchpad:
            content = step.get("content", "").lower()
            for marker in contradiction_markers:
                if marker in content:
                    contradictions += 1
        se.contradictions = contradictions

        # H = 0.5 baseline, increases with contradictions, decreases with strong evidence
        se.H = min(1.0, 0.5 + (contradictions * 0.1) - (tier_counts[0] * 0.05))
        se.H = max(0.1, se.H)  # Floor at 0.1

        # Compute C (Coherence) - agreement among sources
        if se.evidence_sources == 0:
            se.C = 0.5  # No evidence = uncertain
        elif contradictions == 0:
            se.C = 0.9  # No contradictions = high coherence
        else:
            se.C = max(0.2, 1.0 - (contradictions / max(1, se.evidence_sources)))

        # Compute D (Depth) - evidence chain depth
        # Higher tier sources = more depth
        # More tool calls = more investigation
        depth_score = (
            tier_counts[0] * 1.0 +   # Tier 0 (government) = full credit
            tier_counts[1] * 0.7 +   # Tier 1 (official) = 70%
            tier_counts[2] * 0.3     # Tier 2 (commentary) = 30%
        )
        max_possible = se.evidence_sources * 1.0 if se.evidence_sources > 0 else 1
        se.D = min(1.0, depth_score / max(1, max_possible))

        # Bonus for reflections (self-awareness)
        if len(reflections) > 0:
            se.D = min(1.0, se.D + 0.1)

        # Compute Se
        se.compute()

        return se

    def get_routing_decision(self, se: SeState) -> Dict[str, Any]:
        """
        Get routing decision based on Se state.

        Returns routing advice for the reasoning loop.
        """
        if se.Se >= self.SE_THRESHOLDS["high_confidence"]:
            return {
                "decision": "conclude",
                "confidence_modifier": 0.1,
                "reason": f"Se={se.Se:.2f} indicates well-supported conclusion",
            }
        elif se.Se >= self.SE_THRESHOLDS["needs_more"]:
            return {
                "decision": "continue",
                "confidence_modifier": 0.0,
                "reason": f"Se={se.Se:.2f} - need more evidence (D={se.D:.2f})",
                "suggestion": "Query more Tier 0/1 sources" if se.D < 0.5 else "Resolve contradictions" if se.C < 0.7 else "Continue reasoning",
            }
        elif se.Se >= self.SE_THRESHOLDS["low_confidence"]:
            return {
                "decision": "caution",
                "confidence_modifier": -0.15,
                "reason": f"Se={se.Se:.2f} - poorly supported, consider stopping",
                "warning": "Evidence is thin or conflicting",
            }
        else:
            return {
                "decision": "abort",
                "confidence_modifier": -0.3,
                "reason": f"Se={se.Se:.2f} - insufficient evidence to conclude",
                "warning": "Should not make claims at this confidence level",
            }


class SubstrateEnhancedRegulator:
    """
    Se regulator enhanced with FibPi3D wave substrate.

    Combines:
    - Traditional Se = H × C × D from evidence analysis
    - Wave dynamics from FibPi3D lattice (resonance, coherence)

    The substrate provides a "second opinion" on reasoning coherence
    by treating thoughts as waves on a golden-spiral geometry.
    """

    def __init__(self, n_nodes: int = 128):
        self.se_regulator = SeRegulator()
        self.substrate = None

        if FIBPI_AVAILABLE and SubstrateIntegratedReasoning:
            self.substrate = SubstrateIntegratedReasoning(n_nodes=n_nodes)

    def compute_enhanced_se(
        self,
        tool_results: List[Dict],
        scratchpad: List[Dict],
        reflections: List[Dict],
    ) -> Dict[str, Any]:
        """
        Compute enhanced Se state using both traditional and substrate methods.

        Returns:
            Dict with:
            - traditional_se: H×C×D from evidence
            - substrate_se: H×C×D from wave dynamics
            - combined_se: Weighted combination
            - routing: Decision and modifiers
        """
        # Traditional Se computation
        traditional = self.se_regulator.compute_se_state(
            tool_results, scratchpad, reflections
        )

        result = {
            "traditional_se": traditional.to_dict(),
            "substrate_se": None,
            "substrate_mode": None,
            "combined_Se": traditional.Se,
            "fibpi_available": FIBPI_AVAILABLE,
        }

        # Substrate Se computation (if available)
        if self.substrate:
            substrate_result = self.substrate.process_scratchpad(scratchpad)
            result["substrate_se"] = substrate_result.get("substrate_se")
            result["substrate_mode"] = substrate_result.get("dominant_mode")
            result["resonances"] = substrate_result.get("resonances", [])

            # Combine Se values (weighted average)
            substrate_se = substrate_result.get("substrate_se", {}).get("Se", 0.25)
            result["combined_Se"] = 0.7 * traditional.Se + 0.3 * substrate_se

            # Get substrate confidence modifier
            result["substrate_modifier"] = self.substrate.get_confidence_modifier(substrate_result)

        return result

    def get_enhanced_routing(self, enhanced_se: Dict) -> Dict[str, Any]:
        """
        Get routing decision from enhanced Se state.
        """
        combined_se = enhanced_se.get("combined_Se", 0.25)
        substrate_mode = enhanced_se.get("substrate_mode", "unknown")

        # Base routing from combined Se
        if combined_se >= 0.5:
            decision = "conclude"
            base_modifier = 0.1
        elif combined_se >= 0.25:
            decision = "continue"
            base_modifier = 0.0
        elif combined_se >= 0.1:
            decision = "caution"
            base_modifier = -0.1
        else:
            decision = "abort"
            base_modifier = -0.2

        # Adjust based on substrate mode
        substrate_modifier = enhanced_se.get("substrate_modifier", 0.0)

        # Special case: if substrate is conflicted, don't conclude even if Se is ok
        if substrate_mode == "conflicted" and decision == "conclude":
            decision = "caution"
            substrate_modifier = -0.15

        return {
            "decision": decision,
            "combined_Se": combined_se,
            "confidence_modifier": base_modifier + substrate_modifier,
            "substrate_mode": substrate_mode,
            "reason": f"Se={combined_se:.2f}, mode={substrate_mode}",
        }


class EvidenceTriangulator:
    """
    Multi-source evidence triangulation.

    Principle: Don't declare truth from one source.
    Require multiple independent sources to agree.
    """

    def triangulate(
        self,
        tool_results: List[Dict],
        claim: str,
    ) -> Dict[str, Any]:
        """
        Check if a claim is triangulated (supported by multiple sources).

        Returns:
            Dict with triangulation status and details
        """
        supporting = []
        contradicting = []
        neutral = []

        for result in tool_results:
            tool_name = result.get("tool_name", "")
            result_data = result.get("result", {})

            # Simple heuristic - check if result contains relevant data
            result_str = json.dumps(result_data, default=str).lower()
            claim_keywords = claim.lower().split()[:5]  # First 5 words

            matches = sum(1 for kw in claim_keywords if kw in result_str and len(kw) > 3)

            if matches >= 2:
                if "error" in result_str or "not found" in result_str:
                    contradicting.append(tool_name)
                else:
                    supporting.append(tool_name)
            else:
                neutral.append(tool_name)

        # Triangulation requires 2+ independent supporting sources
        is_triangulated = len(supporting) >= 2

        return {
            "claim": claim,
            "triangulated": is_triangulated,
            "supporting_sources": supporting,
            "contradicting_sources": contradicting,
            "neutral_sources": neutral,
            "confidence_boost": 0.15 if is_triangulated else 0.0,
            "warning": "Single source only" if len(supporting) == 1 else None,
        }


# Enhanced reflection prompt with adversarial testing
ADVERSARIAL_REFLECTION_PROMPT = """Review your reasoning with ADVERSARIAL SELF-TESTING.

## YOUR REASONING SO FAR
{scratchpad}

## TOOL RESULTS
{tool_results}

## Se STATE (Signal Entropy)
H (Entropy/Uncertainty): {H:.3f}
C (Coherence/Agreement): {C:.3f}
D (Depth/Evidence): {D:.3f}
Se (Routing Metric): {Se:.3f}

## ADVERSARIAL CHECKLIST

Attack your own conclusion:

1. **Counter-argument**: What's the strongest argument AGAINST your conclusion?
2. **Missing evidence**: What data did you NOT check that could disprove this?
3. **Selection bias**: Did you only query nodes that support your hypothesis?
4. **Confounding**: What third factor could explain both cause and effect?
5. **Base rate**: Is this pattern significant or expected by chance?

## TRIANGULATION CHECK

- How many INDEPENDENT sources support the conclusion?
- Do Tier 0 (government) sources confirm this?
- Did you check a control group?

## YOUR ADVERSARIAL REFLECTION

<reflection>
assessment: [sound/weakened/fatal]
attacks_survived: [X/Y]
weakest_link: [what's the most vulnerable part of the argument]
confidence_delta: [change from previous, e.g., -0.15]
se_routing: [continue/conclude/abort based on Se={Se:.3f}]
correction: [if needed, what to investigate next]
</reflection>
"""
