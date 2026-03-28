"""
FGIP FSA Definitions + MorphSAT Runtime Enforcer

Explicit finite-state automata for FGIP agent execution pipelines.
Designed to be imported into fgip-engine/fgip/agents/base.py as a
hard constraint layer.

Two FSAs defined:
  1. Pipeline FSA — artifact collection → claim → citation → write
  2. Conviction FSA — signals → triangulation → counter-thesis → recommendation

Integration point: wrap FGIPAgent.run() with FSAEnforcer to make
illegal transitions physically impossible.

Related WOs:
  - WO-ENDTOEND-GATE-PIPELINE-01 (3-layer stack proven on Python lexer)
  - WO-SPLICING-SSM-01 (K-entity tracking with shared FSA)
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ======================================================================
# PIPELINE FSA — Agent Execution Pathway
# ======================================================================
# Maps to: base.py run() → collect() → extract() → propose() → _write_proposals()
# With mandatory validation, extraction, and citation steps.
#
# The key illegal transitions this blocks:
#   IDLE → PROPOSING          (hallucinated claim — no evidence collected)
#   COLLECTING → PROPOSING    (uncited claim — skipped integrity check)
#   COLLECTING → WRITING      (bypass entire pipeline)
#   EXTRACTING → WRITING      (skip proposal generation and citation)
#   PROPOSING → WRITING       (skip citation — claim without source link)
#   FAILED → WRITING          (error state producing output)
#   FAILED → PROPOSING        (error state generating claims)

PIPELINE_STATES = [
    'IDLE',         # 0: Agent not running
    'COLLECTING',   # 1: Fetching artifacts (collect())
    'VALIDATING',   # 2: Integrity/filter check (FilterAgent)
    'EXTRACTING',   # 3: NLP fact extraction (extract())
    'PROPOSING',    # 4: Generating claims/edges (propose())
    'CITING',       # 5: Attaching source evidence to proposals
    'WRITING',      # 6: Persisting to staging tables (_write_proposals())
    'COMPLETE',     # 7: Run finished (terminal)
    'FAILED',       # 8: Error state (terminal)
]

PIPELINE_EVENTS = [
    'begin',              # 0: Start agent run
    'artifact_in',        # 1: Artifact received from source
    'integrity_ok',       # 2: Passes integrity filter
    'integrity_fail',     # 3: Fails integrity filter
    'facts_out',          # 4: NLP extraction complete
    'claim_formed',       # 5: Claim/edge generated from facts
    'evidence_attached',  # 6: Source citation linked to proposal
    'write_ok',           # 7: Staging write successful
    'error',              # 8: Error at any stage
]

N_PIPELINE_STATES = len(PIPELINE_STATES)
N_PIPELINE_EVENTS = len(PIPELINE_EVENTS)

# Transition table: PIPELINE_FSA[state, event] → next_state (-1 = ILLEGAL)
# 14 legal transitions out of 81 possible (17.3% legal rate)
PIPELINE_FSA = np.array([
    #  begin art_in int_ok int_fl facts claim  evid write error
    [    1,    -1,    -1,   -1,   -1,   -1,   -1,   -1,   -1],  # IDLE
    [   -1,     2,    -1,   -1,   -1,   -1,   -1,   -1,    8],  # COLLECTING
    [   -1,    -1,     3,    8,   -1,   -1,   -1,   -1,    8],  # VALIDATING
    [   -1,    -1,    -1,   -1,    4,   -1,   -1,   -1,    8],  # EXTRACTING
    [   -1,    -1,    -1,   -1,   -1,    5,   -1,   -1,    8],  # PROPOSING
    [   -1,    -1,    -1,   -1,   -1,   -1,    6,   -1,    8],  # CITING
    [   -1,    -1,    -1,   -1,   -1,   -1,   -1,    7,    8],  # WRITING
    [   -1,    -1,    -1,   -1,   -1,   -1,   -1,   -1,   -1],  # COMPLETE (absorbing)
    [   -1,    -1,    -1,   -1,   -1,   -1,   -1,   -1,   -1],  # FAILED (absorbing)
], dtype=np.int64)

# Named violation categories for audit trail
PIPELINE_VIOLATIONS = {
    (0, 5): 'HALLUCINATED_CLAIM',       # IDLE → claim_formed
    (0, 7): 'PHANTOM_WRITE',            # IDLE → write_ok
    (1, 5): 'UNCITED_CLAIM',            # COLLECTING → claim_formed
    (1, 7): 'PIPELINE_BYPASS',          # COLLECTING → write_ok
    (2, 5): 'UNVALIDATED_CLAIM',        # VALIDATING → claim_formed
    (2, 7): 'SKIP_EXTRACTION',          # VALIDATING → write_ok
    (3, 5): 'SKIP_PROPOSAL',            # EXTRACTING → claim_formed (wrong event)
    (3, 7): 'SKIP_PROPOSE_CITE',        # EXTRACTING → write_ok
    (4, 7): 'UNCITED_WRITE',            # PROPOSING → write_ok (skip citation)
    (5, 7): 'CITE_SKIP_WRITE',          # CITING → write_ok (wrong — need evidence_attached first)
    (8, 5): 'FAILED_CLAIMING',          # FAILED → claim_formed
    (8, 7): 'FAILED_WRITING',           # FAILED → write_ok
}


# ======================================================================
# CONVICTION FSA — Investment Thesis Evaluation Pathway
# ======================================================================
# Maps to: conviction_engine.py evaluate_thesis()
# Enforces: no recommendation without triangulation, no position without counter-thesis review
#
# Key illegal transitions:
#   NO_THESIS → RECOMMENDING    (recommendation without any analysis)
#   GATHERING → SCORING         (skip triangulation gate entirely)
#   GATHERING → RECOMMENDING    (skip everything)
#   TRIANGULATING → RECOMMENDING (skip counter-thesis + scoring)

CONVICTION_STATES = [
    'NO_THESIS',     # 0: No thesis under evaluation
    'GATHERING',     # 1: Collecting confirming/refuting/neutral signals
    'TRIANGULATING', # 2: Checking triangulation gate (3+ sources, 1+ Tier 0)
    'COUNTERING',    # 3: Analyzing counter-theses and severity
    'SCORING',       # 4: Computing conviction score (0-100)
    'RECOMMENDING',  # 5: Generating BUY/HOLD/AVOID/EXIT + timing
    'POSITIONED',    # 6: Position sized (terminal)
]

CONVICTION_EVENTS = [
    'thesis_formed',   # 0: New thesis to evaluate
    'signals_in',      # 1: Signal collection complete
    'tri_pass',        # 2: Triangulation gate passed (3+ sources, 1+ Tier 0)
    'tri_fail',        # 3: Triangulation failed (conviction will be capped)
    'counters_done',   # 4: Counter-thesis analysis complete
    'score_done',      # 5: Conviction score computed
    'rec_made',        # 6: Recommendation generated
]

N_CONVICTION_STATES = len(CONVICTION_STATES)
N_CONVICTION_EVENTS = len(CONVICTION_EVENTS)

# Transition table: CONVICTION_FSA[state, event] → next_state
# tri_fail still proceeds to COUNTERING (conviction capped downstream, not blocked)
CONVICTION_FSA = np.array([
    #  thesis signals tri_p tri_f counters score  rec
    [    1,     -1,    -1,   -1,    -1,    -1,   -1],  # NO_THESIS
    [   -1,      2,    -1,   -1,    -1,    -1,   -1],  # GATHERING
    [   -1,     -1,     3,    3,    -1,    -1,   -1],  # TRIANGULATING
    [   -1,     -1,    -1,   -1,     4,    -1,   -1],  # COUNTERING
    [   -1,     -1,    -1,   -1,    -1,     5,   -1],  # SCORING
    [   -1,     -1,    -1,   -1,    -1,    -1,    6],  # RECOMMENDING
    [   -1,     -1,    -1,   -1,    -1,    -1,   -1],  # POSITIONED (absorbing)
], dtype=np.int64)

CONVICTION_VIOLATIONS = {
    (0, 5): 'SCORE_WITHOUT_THESIS',    # NO_THESIS → score_done
    (0, 6): 'REC_WITHOUT_THESIS',      # NO_THESIS → rec_made
    (1, 5): 'SKIP_TRIANGULATION',      # GATHERING → score_done
    (1, 6): 'REC_WITHOUT_ANALYSIS',    # GATHERING → rec_made
    (2, 5): 'SKIP_COUNTER_THESIS',     # TRIANGULATING → score_done
    (2, 6): 'REC_WITHOUT_SCORING',     # TRIANGULATING → rec_made
    (3, 6): 'REC_WITHOUT_SCORING_2',   # COUNTERING → rec_made (skip scoring)
}


# ======================================================================
# Runtime Enforcer
# ======================================================================

@dataclass
class ViolationRecord:
    """Audit record for a blocked transition."""
    agent_name: str
    from_state: str
    event: str
    violation_type: str
    timestamp: str = ""
    detail: str = ""


class FSAEnforcer:
    """
    MorphSAT-style runtime enforcer for FGIP agents.

    Maintains FSA state per agent and blocks illegal transitions.
    This is the runtime equivalent of MorphSAT's FSA lookup table —
    exact integer state tracking with zero learned parameters.

    Usage:
        enforcer = FSAEnforcer(PIPELINE_FSA, PIPELINE_STATES, PIPELINE_EVENTS,
                               violations=PIPELINE_VIOLATIONS, agent_name="edgar")
        legal, state = enforcer.step(0)  # begin
        legal, state = enforcer.step(1)  # artifact_in
        ...
    """

    def __init__(self, fsa_table: np.ndarray, state_names: list, event_names: list,
                 violations: dict = None, agent_name: str = "unnamed"):
        self.fsa = fsa_table
        self.state_names = state_names
        self.event_names = event_names
        self.violations_map = violations or {}
        self.agent_name = agent_name
        self.state = 0
        self.trace: List[dict] = []
        self.violations: List[ViolationRecord] = []

    @property
    def state_name(self) -> str:
        return self.state_names[self.state]

    def step(self, event_id: int) -> Tuple[bool, str]:
        """
        Attempt a state transition.

        Returns (legal: bool, new_state_name: str).
        If illegal, state does NOT change and a ViolationRecord is logged.
        """
        if event_id < 0 or event_id >= len(self.event_names):
            raise ValueError(f"Invalid event_id {event_id}, max={len(self.event_names)-1}")

        next_state = int(self.fsa[self.state, event_id])
        event_name = self.event_names[event_id]
        legal = next_state != -1

        if legal:
            old_state = self.state
            self.state = next_state
            self.trace.append({
                'event': event_name,
                'from': self.state_names[old_state],
                'to': self.state_names[self.state],
                'legal': True,
            })
        else:
            vtype = self.violations_map.get(
                (self.state, event_id),
                f'ILLEGAL_{self.state_names[self.state]}_{event_name}'
            )
            record = ViolationRecord(
                agent_name=self.agent_name,
                from_state=self.state_names[self.state],
                event=event_name,
                violation_type=vtype,
            )
            self.violations.append(record)
            self.trace.append({
                'event': event_name,
                'from': self.state_names[self.state],
                'to': self.state_names[self.state],  # state unchanged
                'legal': False,
                'violation': vtype,
            })

        return legal, self.state_names[self.state]

    def reset(self):
        self.state = 0
        self.trace = []
        self.violations = []

    def is_terminal(self) -> bool:
        """Check if current state is absorbing (no legal outgoing transitions)."""
        return all(self.fsa[self.state, e] == -1 for e in range(len(self.event_names)))

    def legal_events(self) -> List[str]:
        """Return list of legal events from current state."""
        return [
            self.event_names[e]
            for e in range(len(self.event_names))
            if self.fsa[self.state, e] != -1
        ]

    def summary(self) -> dict:
        return {
            'agent': self.agent_name,
            'state': self.state_name,
            'steps': len(self.trace),
            'violations': len(self.violations),
            'violation_types': [v.violation_type for v in self.violations],
        }


class MultiAgentEnforcer:
    """
    Self-splicing enforcer: K parallel agents, each with independent FSA state,
    sharing the same transition table.

    This is the runtime analog of SplicingMorphSATSSM from WO-SPLICING-SSM-01:
    - K memory slots (one per agent)
    - Shared FSA structure
    - O(K * S) not O(S^K) state space

    Usage:
        tracker = MultiAgentEnforcer(
            agent_names=['edgar', 'congress', 'usaspending', ...],
            fsa_table=PIPELINE_FSA,
            state_names=PIPELINE_STATES,
            event_names=PIPELINE_EVENTS,
            violations=PIPELINE_VIOLATIONS,
        )
        legal, state = tracker.step('edgar', 0)      # edgar: begin
        legal, state = tracker.step('congress', 0)    # congress: begin
        legal, state = tracker.step('edgar', 1)       # edgar: artifact_in
        ...
    """

    def __init__(self, agent_names: List[str], fsa_table: np.ndarray,
                 state_names: list, event_names: list, violations: dict = None):
        self.agents: Dict[str, FSAEnforcer] = {}
        for name in agent_names:
            self.agents[name] = FSAEnforcer(
                fsa_table, state_names, event_names,
                violations=violations, agent_name=name
            )
        self.n_agents = len(agent_names)

    def step(self, agent_name: str, event_id: int) -> Tuple[bool, str]:
        """Route event to the correct agent's FSA slot."""
        if agent_name not in self.agents:
            raise KeyError(f"Unknown agent: {agent_name}")
        return self.agents[agent_name].step(event_id)

    def get_states(self) -> Dict[str, str]:
        """Current FSA state per agent."""
        return {name: agent.state_name for name, agent in self.agents.items()}

    def get_all_violations(self) -> List[ViolationRecord]:
        """All violations across all agents."""
        all_v = []
        for agent in self.agents.values():
            all_v.extend(agent.violations)
        return all_v

    def all_terminal(self) -> bool:
        """Check if all agents have reached terminal states."""
        return all(agent.is_terminal() for agent in self.agents.values())

    def summary(self) -> dict:
        states = self.get_states()
        violations = self.get_all_violations()
        return {
            'n_agents': self.n_agents,
            'states': states,
            'n_complete': sum(1 for s in states.values() if s == 'COMPLETE'),
            'n_failed': sum(1 for s in states.values() if s == 'FAILED'),
            'n_in_progress': sum(1 for s in states.values() if s not in ('COMPLETE', 'FAILED', 'IDLE')),
            'total_violations': len(violations),
            'violation_types': list(set(v.violation_type for v in violations)),
        }


# ======================================================================
# FGIP Agent Integration Example
# ======================================================================
#
# To wire into fgip-engine/fgip/agents/base.py:
#
# from fgip_fsa import (
#     FSAEnforcer, PIPELINE_FSA, PIPELINE_STATES, PIPELINE_EVENTS,
#     PIPELINE_VIOLATIONS
# )
#
# class FGIPAgent(ABC):
#     def __init__(self, db, name, description=""):
#         ...
#         self._fsa = FSAEnforcer(
#             PIPELINE_FSA, PIPELINE_STATES, PIPELINE_EVENTS,
#             violations=PIPELINE_VIOLATIONS, agent_name=name
#         )
#
#     def run(self):
#         self._fsa.reset()
#
#         # IDLE → COLLECTING
#         legal, _ = self._fsa.step(0)  # begin
#         assert legal, f"Agent {self.name}: cannot begin from {self._fsa.state_name}"
#
#         artifacts = self.collect()
#
#         # COLLECTING → VALIDATING
#         legal, _ = self._fsa.step(1)  # artifact_in
#         assert legal, f"BLOCKED: {self._fsa.violations[-1].violation_type}"
#
#         # ... integrity check ...
#         legal, _ = self._fsa.step(2)  # integrity_ok
#
#         facts = self.extract(artifacts)
#
#         # EXTRACTING → PROPOSING
#         legal, _ = self._fsa.step(4)  # facts_out
#
#         claims, edges = self.propose(facts)
#
#         # PROPOSING → CITING
#         legal, _ = self._fsa.step(5)  # claim_formed
#
#         # ... attach evidence ...
#         legal, _ = self._fsa.step(6)  # evidence_attached
#
#         self._write_proposals(claims, edges)
#
#         # WRITING → COMPLETE
#         legal, _ = self._fsa.step(7)  # write_ok
#
#         return {"violations": [v.__dict__ for v in self._fsa.violations]}
#
# ======================================================================
# For the MultiAgentEnforcer in pipeline_orchestrator.py:
#
# from fgip_fsa import (
#     MultiAgentEnforcer, PIPELINE_FSA, PIPELINE_STATES, PIPELINE_EVENTS,
#     PIPELINE_VIOLATIONS
# )
#
# class PipelineOrchestrator:
#     def __init__(self, agent_names):
#         self.tracker = MultiAgentEnforcer(
#             agent_names=agent_names,
#             fsa_table=PIPELINE_FSA,
#             state_names=PIPELINE_STATES,
#             event_names=PIPELINE_EVENTS,
#             violations=PIPELINE_VIOLATIONS,
#         )
#
#     def dispatch(self, agent_name, event_id):
#         legal, state = self.tracker.step(agent_name, event_id)
#         if not legal:
#             violations = self.tracker.agents[agent_name].violations
#             log.warning(f"BLOCKED: {agent_name} — {violations[-1].violation_type}")
#         return legal, state
# ======================================================================


def validate_fsa(fsa, state_names, event_names, name="FSA"):
    """Validate FSA table dimensions and properties."""
    n_states = len(state_names)
    n_events = len(event_names)
    assert fsa.shape == (n_states, n_events), \
        f"{name}: shape {fsa.shape} != ({n_states}, {n_events})"

    # Check all transitions are valid state indices or -1
    for s in range(n_states):
        for e in range(n_events):
            ns = fsa[s, e]
            assert ns == -1 or (0 <= ns < n_states), \
                f"{name}: invalid transition [{s},{e}] = {ns}"

    # Count legal/illegal
    n_legal = int((fsa != -1).sum())
    n_total = n_states * n_events
    pct = 100.0 * n_legal / n_total

    # Check terminal states (no outgoing legal transitions)
    terminals = []
    for s in range(n_states):
        if all(fsa[s, e] == -1 for e in range(n_events)):
            terminals.append(state_names[s])

    print(f"  {name}: {n_states} states, {n_events} events, "
          f"{n_legal}/{n_total} legal ({pct:.1f}%), "
          f"terminals: {terminals}")
    return True


if __name__ == '__main__':
    print("FGIP FSA Definitions — Validation\n")

    print("Pipeline FSA:")
    validate_fsa(PIPELINE_FSA, PIPELINE_STATES, PIPELINE_EVENTS, "Pipeline")
    print(f"  Named violations: {len(PIPELINE_VIOLATIONS)}")
    for (s, e), vtype in sorted(PIPELINE_VIOLATIONS.items()):
        print(f"    {PIPELINE_STATES[s]:12s} + {PIPELINE_EVENTS[e]:18s} → {vtype}")

    print(f"\nConviction FSA:")
    validate_fsa(CONVICTION_FSA, CONVICTION_STATES, CONVICTION_EVENTS, "Conviction")
    print(f"  Named violations: {len(CONVICTION_VIOLATIONS)}")
    for (s, e), vtype in sorted(CONVICTION_VIOLATIONS.items()):
        print(f"    {CONVICTION_STATES[s]:15s} + {CONVICTION_EVENTS[e]:18s} → {vtype}")

    # Quick enforcement demo
    print(f"\n--- Quick Enforcement Demo ---")
    enforcer = FSAEnforcer(
        PIPELINE_FSA, PIPELINE_STATES, PIPELINE_EVENTS,
        violations=PIPELINE_VIOLATIONS, agent_name="demo_agent"
    )

    # Legal path: IDLE → COLLECTING → VALIDATING → EXTRACTING → PROPOSING → CITING → WRITING → COMPLETE
    legal_path = [0, 1, 2, 4, 5, 6, 7]  # begin, artifact_in, integrity_ok, facts_out, claim_formed, evidence_attached, write_ok
    print(f"\n  Legal path ({len(legal_path)} steps):")
    for eid in legal_path:
        legal, state = enforcer.step(eid)
        print(f"    {PIPELINE_EVENTS[eid]:18s} → {state:12s} {'OK' if legal else 'BLOCKED'}")
    print(f"  Final: {enforcer.state_name}, violations={len(enforcer.violations)}")

    # Illegal: try to write without citing
    enforcer.reset()
    print(f"\n  Illegal path (skip citation):")
    for eid in [0, 1, 2, 4, 5, 7]:  # missing evidence_attached (6)
        legal, state = enforcer.step(eid)
        status = 'OK' if legal else f'BLOCKED ({enforcer.violations[-1].violation_type})'
        print(f"    {PIPELINE_EVENTS[eid]:18s} → {state:12s} {status}")
    print(f"  Violations: {[v.violation_type for v in enforcer.violations]}")

    print(f"\nAll validations passed.")
