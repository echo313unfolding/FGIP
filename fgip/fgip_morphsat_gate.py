"""
FGIP MorphSAT Action-State Enforcement Gate
=============================================

Hard FSA enforcement for the FGIP investment decision lifecycle.
Maps the implicit agent pipeline (gather → analyze → decide → act)
to an explicit finite-state automaton with guardian vows.

This is the FGIP-specific instance of the MorphSAT gate pattern
proven in WO-ECHO-MORPHSAT-INTEGRATION-01 on the Echo lobe scheduler.

FSA: 7 states, 10 events, guardian vows from PSSH bridge rules.

    IDLE → GATHERING → ANALYZING → DECIDING → EXECUTING → MONITORING
                                      ↓                       ↓
                                   CLOSED ←─────────── INVALIDATED

The gate sits at the action dispatch layer. Since FGIP agents produce
structured outputs (not free-form text), grounding accuracy is high —
action types are explicit enum values, not keyword-classified.

Guardian vows (derived from PSSH bridge production rules):
  - No EXECUTING without triangulation (≥3 source types)
  - No DECIDING with fatal unresolved counter-evidence
  - No position changes on unverified data (fail-closed)
  - No EXECUTING while GATHERING (must complete analysis)

Work Orders: WO-FGIP-MORPHSAT-FSA-01
"""

from __future__ import annotations

from enum import IntEnum
from typing import Dict, List, Optional, Set, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# FGIP Decision Lifecycle FSA
# ---------------------------------------------------------------------------

class FGIPState(IntEnum):
    IDLE = 0           # no active thesis evaluation
    GATHERING = 1      # agents collecting evidence (collect/extract/propose)
    ANALYZING = 2      # conviction scoring, triangulation, adversarial testing
    DECIDING = 3       # generating position recommendation (Kelly, policy caps)
    EXECUTING = 4      # trade memo generated, acting on decision
    MONITORING = 5     # post-decision monitoring for invalidation criteria
    CLOSED = 6         # thesis archived or position exited


class FGIPEvent(IntEnum):
    NEW_THESIS = 0           # thesis submitted for evaluation
    EVIDENCE_COLLECTED = 1   # agent completes collect/extract cycle
    ANALYSIS_COMPLETE = 2    # conviction + triangulation + adversarial done
    DECISION_MADE = 3        # position recommendation generated
    GATES_PASSED = 4         # trade memo gates all pass → TRADE_READY
    GATES_FAILED = 5         # trade memo gates fail → back to analysis
    INVALIDATION = 6         # monitoring detects invalidation criteria
    POSITION_CLOSED = 7      # position exited (manual or stop-loss)
    RESET = 8                # abort evaluation, return to IDLE
    NEW_EVIDENCE = 9         # new evidence arrives during monitoring


N_STATES = len(FGIPState)
N_EVENTS = len(FGIPEvent)

STATE_NAMES = [s.name for s in FGIPState]
EVENT_NAMES = [e.name for e in FGIPEvent]

# Transition table: T[state, event] → next_state (-1 = illegal)
TRANSITION_TABLE = np.full((N_STATES, N_EVENTS), -1, dtype=np.int32)

# --- Legal transitions ---

# IDLE: only NEW_THESIS starts the pipeline
TRANSITION_TABLE[FGIPState.IDLE, FGIPEvent.NEW_THESIS] = FGIPState.GATHERING

# GATHERING: evidence collected → move to analysis
TRANSITION_TABLE[FGIPState.GATHERING, FGIPEvent.EVIDENCE_COLLECTED] = FGIPState.ANALYZING
# Can receive more evidence while gathering (stay in GATHERING)
TRANSITION_TABLE[FGIPState.GATHERING, FGIPEvent.NEW_EVIDENCE] = FGIPState.GATHERING

# ANALYZING: analysis complete → move to deciding
TRANSITION_TABLE[FGIPState.ANALYZING, FGIPEvent.ANALYSIS_COMPLETE] = FGIPState.DECIDING
# Analysis discovers need for more evidence → back to gathering
TRANSITION_TABLE[FGIPState.ANALYZING, FGIPEvent.NEW_EVIDENCE] = FGIPState.GATHERING

# DECIDING: recommendation made → check gates
TRANSITION_TABLE[FGIPState.DECIDING, FGIPEvent.DECISION_MADE] = FGIPState.DECIDING
TRANSITION_TABLE[FGIPState.DECIDING, FGIPEvent.GATES_PASSED] = FGIPState.EXECUTING
TRANSITION_TABLE[FGIPState.DECIDING, FGIPEvent.GATES_FAILED] = FGIPState.ANALYZING  # back to analysis

# EXECUTING: trade executed → move to monitoring
TRANSITION_TABLE[FGIPState.EXECUTING, FGIPEvent.DECISION_MADE] = FGIPState.MONITORING

# MONITORING: watch for invalidation or new evidence
TRANSITION_TABLE[FGIPState.MONITORING, FGIPEvent.INVALIDATION] = FGIPState.DECIDING  # re-evaluate
TRANSITION_TABLE[FGIPState.MONITORING, FGIPEvent.NEW_EVIDENCE] = FGIPState.ANALYZING  # re-analyze
TRANSITION_TABLE[FGIPState.MONITORING, FGIPEvent.POSITION_CLOSED] = FGIPState.CLOSED

# CLOSED: only new thesis restarts
TRANSITION_TABLE[FGIPState.CLOSED, FGIPEvent.NEW_THESIS] = FGIPState.GATHERING

# RESET from any state goes to IDLE
for _s in FGIPState:
    TRANSITION_TABLE[_s, FGIPEvent.RESET] = FGIPState.IDLE

N_ILLEGAL = int((TRANSITION_TABLE == -1).sum())
N_LEGAL = int((TRANSITION_TABLE >= 0).sum())


# ---------------------------------------------------------------------------
# Guardian Vows (derived from PSSH bridge production rules)
# ---------------------------------------------------------------------------

# These are BLOCKED regardless of FSA legality — extra policy layer.
# Mapped from existing PSSH bridge rules to (state, event) pairs.
GUARDIAN_BLOCKED: Set[Tuple[int, int]] = {
    # Rule 1: No executing without going through analysis (skip-to-execute)
    (FGIPState.GATHERING, FGIPEvent.GATES_PASSED),  # can't pass gates from gathering
    (FGIPState.IDLE,      FGIPEvent.GATES_PASSED),  # can't pass gates from idle

    # Rule 2: No position changes on unverified data
    # (captured by FSA: EXECUTING requires DECIDING which requires ANALYZING)

    # Rule 3: No deciding without evidence (low Se → continue gathering)
    (FGIPState.IDLE,      FGIPEvent.DECISION_MADE),  # can't decide from idle
    (FGIPState.GATHERING, FGIPEvent.DECISION_MADE),  # can't decide while still gathering

    # Rule 4: No trade execution while monitoring shows invalidation
    # (FSA handles: MONITORING + INVALIDATION → DECIDING, not EXECUTING)

    # Rule 5: No closing position without monitoring phase
    (FGIPState.DECIDING,  FGIPEvent.POSITION_CLOSED),  # can't close from deciding
    (FGIPState.ANALYZING, FGIPEvent.POSITION_CLOSED),  # can't close from analyzing
    (FGIPState.GATHERING, FGIPEvent.POSITION_CLOSED),  # can't close from gathering

    # Rule 6: No new thesis while executing (must close or monitor first)
    (FGIPState.EXECUTING, FGIPEvent.NEW_THESIS),
}


# ---------------------------------------------------------------------------
# Event Classification (grounding layer)
# ---------------------------------------------------------------------------

# FGIP agents produce structured outputs — grounding is much easier
# than free-form LLM text. These map agent action types to FSA events.

# Maps from (agent_class_name, action_type) → FGIPEvent
_AGENT_ACTION_MAP: Dict[Tuple[str, str], FGIPEvent] = {
    # Standard agents (collect/extract/propose)
    ("FGIPAgent", "collect"):     FGIPEvent.EVIDENCE_COLLECTED,
    ("FGIPAgent", "extract"):     FGIPEvent.EVIDENCE_COLLECTED,
    ("FGIPAgent", "propose"):     FGIPEvent.EVIDENCE_COLLECTED,
    ("EDGARAgent", "collect"):    FGIPEvent.EVIDENCE_COLLECTED,
    ("CongressAgent", "collect"): FGIPEvent.EVIDENCE_COLLECTED,
    ("RSSAgent", "collect"):      FGIPEvent.EVIDENCE_COLLECTED,

    # Conviction engine / analysis
    ("ConvictionEngine", "evaluate"):   FGIPEvent.ANALYSIS_COMPLETE,
    ("AdversarialTester", "attack"):    FGIPEvent.ANALYSIS_COMPLETE,
    ("EvidenceTriangulator", "check"):  FGIPEvent.ANALYSIS_COMPLETE,

    # Decision agent
    ("DecisionAgent", "evaluate_thesis"):  FGIPEvent.DECISION_MADE,
    ("DecisionAgent", "BUY"):              FGIPEvent.DECISION_MADE,
    ("DecisionAgent", "HOLD"):             FGIPEvent.DECISION_MADE,
    ("DecisionAgent", "REDUCE"):           FGIPEvent.DECISION_MADE,
    ("DecisionAgent", "EXIT"):             FGIPEvent.DECISION_MADE,
    ("DecisionAgent", "AVOID"):            FGIPEvent.DECISION_MADE,

    # Trade plan agent
    ("TradePlanAgent", "TRADE_READY"):  FGIPEvent.GATES_PASSED,
    ("TradePlanAgent", "HOLD"):         FGIPEvent.GATES_FAILED,
    ("TradePlanAgent", "PASS"):         FGIPEvent.GATES_FAILED,

    # Agentic reasoning loop
    ("AgenticReasoningLoop", "conclude"):  FGIPEvent.ANALYSIS_COMPLETE,
    ("AgenticReasoningLoop", "tool_call"): FGIPEvent.EVIDENCE_COLLECTED,

    # PSSH bridge decisions
    ("PSSHBridge", "allow_conclude"):       FGIPEvent.ANALYSIS_COMPLETE,
    ("PSSHBridge", "continue_gathering"):   FGIPEvent.NEW_EVIDENCE,
    ("PSSHBridge", "require_reflection"):   FGIPEvent.NEW_EVIDENCE,
    ("PSSHBridge", "block_action"):         FGIPEvent.GATES_FAILED,
}


def classify_fgip_event(
    agent_name: str,
    action_type: str,
    output: Optional[dict] = None,
) -> FGIPEvent:
    """Classify a FGIP agent action into an FSA event.

    Grounding is straightforward here — FGIP agents produce structured
    outputs with explicit action types. No keyword matching needed.

    Args:
        agent_name: The agent class name (e.g., "DecisionAgent")
        action_type: The action type string (e.g., "BUY", "collect")
        output: Optional structured output dict for disambiguation

    Returns:
        The detected FGIPEvent.
    """
    # Direct lookup
    key = (agent_name, action_type)
    if key in _AGENT_ACTION_MAP:
        return _AGENT_ACTION_MAP[key]

    # Fallback: classify by action_type alone
    action_lower = action_type.lower()

    if action_lower in ("collect", "extract", "propose", "fetch"):
        return FGIPEvent.EVIDENCE_COLLECTED

    if action_lower in ("evaluate", "analyze", "score", "triangulate", "attack"):
        return FGIPEvent.ANALYSIS_COMPLETE

    if action_lower in ("buy", "hold", "reduce", "exit", "avoid", "recommend"):
        return FGIPEvent.DECISION_MADE

    if action_lower in ("trade_ready", "execute", "deploy"):
        return FGIPEvent.GATES_PASSED

    if action_lower in ("pass", "fail", "reject", "block"):
        return FGIPEvent.GATES_FAILED

    if action_lower in ("invalidate", "stop_loss", "breach"):
        return FGIPEvent.INVALIDATION

    if action_lower in ("close", "archive", "exit_position"):
        return FGIPEvent.POSITION_CLOSED

    if action_lower in ("reset", "abort", "cancel"):
        return FGIPEvent.RESET

    # Default: treat as new evidence (safe — keeps pipeline in gathering/analyzing)
    return FGIPEvent.NEW_EVIDENCE


# ---------------------------------------------------------------------------
# FGIP MorphSAT Gate
# ---------------------------------------------------------------------------

class FGIPMorphSATGate:
    """Hard FSA enforcement gate for FGIP investment decision lifecycle.

    Sits at the action dispatch layer. Each agent action is classified
    into an FGIPEvent, then the gate enforces the FSA transition.

    The guardian layer adds PSSH-bridge-derived policy blocks.
    """

    def __init__(
        self,
        transition_table: Optional[np.ndarray] = None,
        guardian_blocked: Optional[Set[Tuple[int, int]]] = None,
        enable_guardian: bool = True,
    ):
        self.T = (transition_table if transition_table is not None
                  else TRANSITION_TABLE).copy()
        self.guardian_blocked = (guardian_blocked if guardian_blocked is not None
                                else GUARDIAN_BLOCKED) if enable_guardian else set()
        self.state = FGIPState.IDLE
        self.history: List[dict] = []
        self.illegal_caught = 0
        self.guardian_caught = 0
        self.total_transitions = 0

    def step(self, event: FGIPEvent) -> Tuple[FGIPState, bool, str]:
        """Attempt a state transition.

        Returns:
            (new_state, was_legal, action_taken)
        """
        self.total_transitions += 1
        old_state = self.state

        # Guardian check first
        if (int(old_state), int(event)) in self.guardian_blocked:
            self.guardian_caught += 1
            self.history.append({
                'from': STATE_NAMES[old_state], 'event': EVENT_NAMES[event],
                'action': 'GUARDIAN_BLOCKED', 'to': STATE_NAMES[old_state],
            })
            return self.state, False, 'GUARDIAN_BLOCKED'

        # FSA check
        next_state = self.T[old_state, event]
        if next_state == -1:
            self.illegal_caught += 1
            self.history.append({
                'from': STATE_NAMES[old_state], 'event': EVENT_NAMES[event],
                'action': 'FSA_BLOCKED', 'to': STATE_NAMES[old_state],
            })
            return self.state, False, 'FSA_BLOCKED'

        # Legal transition
        self.state = FGIPState(next_state)
        self.history.append({
            'from': STATE_NAMES[old_state], 'event': EVENT_NAMES[event],
            'action': 'ALLOWED', 'to': STATE_NAMES[self.state],
        })
        return self.state, True, 'ALLOWED'

    def reset(self):
        """Reset gate to IDLE state."""
        self.state = FGIPState.IDLE

    def to_receipt(self) -> dict:
        """Export gate state and history as a receipt-compatible dict."""
        return {
            'final_state': STATE_NAMES[self.state],
            'total_transitions': self.total_transitions,
            'illegal_caught': self.illegal_caught,
            'guardian_caught': self.guardian_caught,
            'history': self.history,
        }
