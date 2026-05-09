"""Evidence graph FSA — finite-state automata for agent pipeline enforcement.

Domain-agnostic extraction: FSAEnforcer and MultiAgentEnforcer are fully
generic. PIPELINE_FSA is a reusable default for any evidence-collection
agent (collect → validate → extract → propose → cite → write).

Domain-specific FSAs (e.g., investment conviction scoring) should be defined
in their own domain modules, not here.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ======================================================================
# DEFAULT PIPELINE FSA — Generic Evidence Collection
# ======================================================================
# Applies to any agent that: collects artifacts, validates them, extracts
# facts, generates proposals, attaches citations, and writes to staging.
#
# Illegal transitions this blocks:
#   IDLE → PROPOSING          (hallucinated claim — no evidence)
#   COLLECTING → PROPOSING    (uncited claim — skipped integrity)
#   COLLECTING → WRITING      (bypass entire pipeline)
#   EXTRACTING → WRITING      (skip proposal + citation)
#   PROPOSING → WRITING       (skip citation)
#   FAILED → WRITING          (error state producing output)
#   FAILED → PROPOSING        (error state generating claims)

PIPELINE_STATES = [
    'IDLE',         # 0: Agent not running
    'COLLECTING',   # 1: Fetching artifacts
    'VALIDATING',   # 2: Integrity/filter check
    'EXTRACTING',   # 3: Fact extraction
    'PROPOSING',    # 4: Generating claims/edges
    'CITING',       # 5: Attaching source evidence
    'WRITING',      # 6: Persisting to staging tables
    'COMPLETE',     # 7: Run finished (terminal)
    'FAILED',       # 8: Error state (terminal)
]

PIPELINE_EVENTS = [
    'begin',              # 0: Start agent run
    'artifact_in',        # 1: Artifact received
    'integrity_ok',       # 2: Passes integrity filter
    'integrity_fail',     # 3: Fails integrity filter
    'facts_out',          # 4: Extraction complete
    'claim_formed',       # 5: Claim/edge generated
    'evidence_attached',  # 6: Source citation linked
    'write_ok',           # 7: Staging write successful
    'error',              # 8: Error at any stage
]

N_PIPELINE_STATES = len(PIPELINE_STATES)
N_PIPELINE_EVENTS = len(PIPELINE_EVENTS)

# Transition table: PIPELINE_FSA[state, event] → next_state (-1 = ILLEGAL)
PIPELINE_FSA = np.array([
    #  begin art_in int_ok int_fl facts claim  evid write error
    [    1,    -1,    -1,   -1,   -1,   -1,   -1,   -1,   -1],  # IDLE
    [   -1,     2,    -1,   -1,   -1,   -1,   -1,   -1,    8],  # COLLECTING
    [   -1,    -1,     3,    8,   -1,   -1,   -1,   -1,    8],  # VALIDATING
    [   -1,    -1,    -1,   -1,    4,   -1,   -1,   -1,    8],  # EXTRACTING
    [   -1,    -1,    -1,   -1,   -1,    5,   -1,   -1,    8],  # PROPOSING
    [   -1,    -1,    -1,   -1,   -1,   -1,    6,   -1,    8],  # CITING
    [   -1,    -1,    -1,   -1,   -1,   -1,   -1,    7,    8],  # WRITING
    [   -1,    -1,    -1,   -1,   -1,   -1,   -1,   -1,   -1],  # COMPLETE
    [   -1,    -1,    -1,   -1,   -1,   -1,   -1,   -1,   -1],  # FAILED
], dtype=np.int64)

PIPELINE_VIOLATIONS = {
    (0, 5): 'HALLUCINATED_CLAIM',
    (0, 7): 'PHANTOM_WRITE',
    (1, 5): 'UNCITED_CLAIM',
    (1, 7): 'PIPELINE_BYPASS',
    (2, 5): 'UNVALIDATED_CLAIM',
    (2, 7): 'SKIP_EXTRACTION',
    (3, 5): 'SKIP_PROPOSAL',
    (3, 7): 'SKIP_PROPOSE_CITE',
    (4, 7): 'UNCITED_WRITE',
    (5, 7): 'CITE_SKIP_WRITE',
    (8, 5): 'FAILED_CLAIMING',
    (8, 7): 'FAILED_WRITING',
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
    """Runtime FSA enforcer for evidence graph agents.

    Maintains FSA state per agent and blocks illegal transitions.
    Integer state tracking with zero learned parameters.

    Usage:
        enforcer = FSAEnforcer(PIPELINE_FSA, PIPELINE_STATES, PIPELINE_EVENTS,
                               violations=PIPELINE_VIOLATIONS, agent_name="edgar")
        legal, state = enforcer.step(0)  # begin
        legal, state = enforcer.step(1)  # artifact_in
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
        """Attempt a state transition.

        Returns (legal, new_state_name). If illegal, state unchanged
        and a ViolationRecord is logged.
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
                f'ILLEGAL_{self.state_names[self.state]}_{event_name}',
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
                'to': self.state_names[self.state],
                'legal': False,
                'violation': vtype,
            })

        return legal, self.state_names[self.state]

    def reset(self):
        self.state = 0
        self.trace = []
        self.violations = []

    def is_terminal(self) -> bool:
        """Check if current state is absorbing."""
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
    """K parallel agents, each with independent FSA state, sharing
    the same transition table.

    Usage:
        tracker = MultiAgentEnforcer(
            agent_names=['scanner', 'analyzer', 'correlator'],
            fsa_table=PIPELINE_FSA,
            state_names=PIPELINE_STATES,
            event_names=PIPELINE_EVENTS,
            violations=PIPELINE_VIOLATIONS,
        )
        legal, state = tracker.step('scanner', 0)
        legal, state = tracker.step('analyzer', 0)
    """

    def __init__(self, agent_names: List[str], fsa_table: np.ndarray,
                 state_names: list, event_names: list, violations: dict = None):
        self.agents: Dict[str, FSAEnforcer] = {}
        for name in agent_names:
            self.agents[name] = FSAEnforcer(
                fsa_table, state_names, event_names,
                violations=violations, agent_name=name,
            )
        self.n_agents = len(agent_names)

    def step(self, agent_name: str, event_id: int) -> Tuple[bool, str]:
        """Route event to the correct agent's FSA slot."""
        if agent_name not in self.agents:
            raise KeyError(f"Unknown agent: {agent_name}")
        return self.agents[agent_name].step(event_id)

    def get_states(self) -> Dict[str, str]:
        return {name: agent.state_name for name, agent in self.agents.items()}

    def get_all_violations(self) -> List[ViolationRecord]:
        all_v = []
        for agent in self.agents.values():
            all_v.extend(agent.violations)
        return all_v

    def all_terminal(self) -> bool:
        return all(agent.is_terminal() for agent in self.agents.values())

    def summary(self) -> dict:
        states = self.get_states()
        violations = self.get_all_violations()
        return {
            'n_agents': self.n_agents,
            'states': states,
            'n_complete': sum(1 for s in states.values() if s == 'COMPLETE'),
            'n_failed': sum(1 for s in states.values() if s == 'FAILED'),
            'n_in_progress': sum(
                1 for s in states.values()
                if s not in ('COMPLETE', 'FAILED', 'IDLE')
            ),
            'total_violations': len(violations),
            'violation_types': list(set(v.violation_type for v in violations)),
        }


# ======================================================================
# Validation utility
# ======================================================================

def validate_fsa(fsa, state_names, event_names, name="FSA"):
    """Validate FSA table dimensions and properties."""
    n_states = len(state_names)
    n_events = len(event_names)
    assert fsa.shape == (n_states, n_events), \
        f"{name}: shape {fsa.shape} != ({n_states}, {n_events})"

    for s in range(n_states):
        for e in range(n_events):
            ns = fsa[s, e]
            assert ns == -1 or (0 <= ns < n_states), \
                f"{name}: invalid transition [{s},{e}] = {ns}"

    n_legal = int((fsa != -1).sum())
    n_total = n_states * n_events
    pct = 100.0 * n_legal / n_total

    terminals = [
        state_names[s] for s in range(n_states)
        if all(fsa[s, e] == -1 for e in range(n_events))
    ]

    return {
        'name': name,
        'states': n_states,
        'events': n_events,
        'legal': n_legal,
        'total': n_total,
        'legal_pct': round(pct, 1),
        'terminals': terminals,
    }
