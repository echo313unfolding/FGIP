#!/usr/bin/env python3
"""
WO-FGIP-MORPHSAT-FSA-01: FGIP Decision Lifecycle FSA Test
==========================================================

Validates the FGIP MorphSAT gate enforces the investment decision lifecycle
correctly. Tests legal paths, illegal transitions, and guardian vows.

Predeclared success criteria:
  F1: Legal thesis lifecycle (IDLE→GATHERING→ANALYZING→DECIDING→EXECUTING→MONITORING→CLOSED) completes
  F2: Skip-to-execute (GATHERING→GATES_PASSED) is guardian-blocked
  F3: Decide-from-idle (IDLE→DECISION_MADE) is guardian-blocked
  F4: Close-without-monitoring (DECIDING→POSITION_CLOSED) is guardian-blocked
  F5: Gate revision loop (DECIDING→GATES_FAILED→ANALYZING→ANALYSIS_COMPLETE→DECIDING) works
  F6: Invalidation loop (MONITORING→INVALIDATION→DECIDING→GATES_PASSED→EXECUTING→MONITORING) works
  F7: 100% catch rate on 50 randomly generated illegal sequences
  F8: classify_fgip_event() correctly maps all agent action types

Receipt: WO-FGIP-MORPHSAT-FSA-01
"""

import json
import sys
import time
import platform
import resource
import hashlib
from pathlib import Path
from collections import Counter

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fgip.fgip_morphsat_gate import (
    FGIPMorphSATGate, FGIPState, FGIPEvent,
    STATE_NAMES, EVENT_NAMES, TRANSITION_TABLE, GUARDIAN_BLOCKED,
    N_STATES, N_EVENTS, N_ILLEGAL, N_LEGAL,
    classify_fgip_event,
)


def test_f1_legal_lifecycle():
    """F1: Full legal thesis lifecycle completes."""
    gate = FGIPMorphSATGate()

    steps = [
        (FGIPEvent.NEW_THESIS,          FGIPState.GATHERING),
        (FGIPEvent.EVIDENCE_COLLECTED,  FGIPState.ANALYZING),
        (FGIPEvent.ANALYSIS_COMPLETE,   FGIPState.DECIDING),
        (FGIPEvent.DECISION_MADE,       FGIPState.DECIDING),
        (FGIPEvent.GATES_PASSED,        FGIPState.EXECUTING),
        (FGIPEvent.DECISION_MADE,       FGIPState.MONITORING),
        (FGIPEvent.POSITION_CLOSED,     FGIPState.CLOSED),
    ]

    for event, expected_state in steps:
        state, legal, action = gate.step(event)
        assert legal, f"F1 FAIL: {EVENT_NAMES[event]} was blocked at {STATE_NAMES[gate.state]}: {action}"
        assert state == expected_state, (
            f"F1 FAIL: after {EVENT_NAMES[event]}, expected {STATE_NAMES[expected_state]}, "
            f"got {STATE_NAMES[state]}"
        )

    assert gate.state == FGIPState.CLOSED
    assert gate.illegal_caught == 0
    assert gate.guardian_caught == 0
    return True, gate.to_receipt()


def test_f2_skip_to_execute():
    """F2: Guardian blocks skip-to-execute (GATHERING→GATES_PASSED)."""
    gate = FGIPMorphSATGate()
    gate.step(FGIPEvent.NEW_THESIS)  # → GATHERING
    assert gate.state == FGIPState.GATHERING

    state, legal, action = gate.step(FGIPEvent.GATES_PASSED)
    assert not legal, "F2 FAIL: skip-to-execute was allowed"
    assert action == "GUARDIAN_BLOCKED", f"F2 FAIL: action was {action}"
    assert gate.guardian_caught == 1
    return True, gate.to_receipt()


def test_f3_decide_from_idle():
    """F3: Guardian blocks deciding from idle."""
    gate = FGIPMorphSATGate()
    state, legal, action = gate.step(FGIPEvent.DECISION_MADE)
    assert not legal, "F3 FAIL: decide from idle was allowed"
    assert action == "GUARDIAN_BLOCKED", f"F3 FAIL: action was {action}"
    return True, gate.to_receipt()


def test_f4_close_without_monitoring():
    """F4: Guardian blocks closing position from DECIDING state."""
    gate = FGIPMorphSATGate()
    gate.step(FGIPEvent.NEW_THESIS)       # → GATHERING
    gate.step(FGIPEvent.EVIDENCE_COLLECTED)  # → ANALYZING
    gate.step(FGIPEvent.ANALYSIS_COMPLETE)   # → DECIDING
    assert gate.state == FGIPState.DECIDING

    state, legal, action = gate.step(FGIPEvent.POSITION_CLOSED)
    assert not legal, "F4 FAIL: close from DECIDING was allowed"
    assert action == "GUARDIAN_BLOCKED", f"F4 FAIL: action was {action}"
    return True, gate.to_receipt()


def test_f5_gate_revision_loop():
    """F5: Gates fail → back to analysis → re-decide."""
    gate = FGIPMorphSATGate()
    gate.step(FGIPEvent.NEW_THESIS)
    gate.step(FGIPEvent.EVIDENCE_COLLECTED)
    gate.step(FGIPEvent.ANALYSIS_COMPLETE)
    assert gate.state == FGIPState.DECIDING

    # Gates fail → back to ANALYZING
    state, legal, _ = gate.step(FGIPEvent.GATES_FAILED)
    assert legal and state == FGIPState.ANALYZING, "F5 FAIL: gates_failed didn't go to ANALYZING"

    # Re-analyze → back to DECIDING
    state, legal, _ = gate.step(FGIPEvent.ANALYSIS_COMPLETE)
    assert legal and state == FGIPState.DECIDING, "F5 FAIL: re-analysis didn't go to DECIDING"

    # Gates pass this time
    state, legal, _ = gate.step(FGIPEvent.GATES_PASSED)
    assert legal and state == FGIPState.EXECUTING, "F5 FAIL: gates_passed didn't go to EXECUTING"

    return True, gate.to_receipt()


def test_f6_invalidation_loop():
    """F6: Monitoring → invalidation → re-decide → re-execute → monitoring."""
    gate = FGIPMorphSATGate()
    # Full path to monitoring
    gate.step(FGIPEvent.NEW_THESIS)
    gate.step(FGIPEvent.EVIDENCE_COLLECTED)
    gate.step(FGIPEvent.ANALYSIS_COMPLETE)
    gate.step(FGIPEvent.GATES_PASSED)
    gate.step(FGIPEvent.DECISION_MADE)
    assert gate.state == FGIPState.MONITORING

    # Invalidation → DECIDING
    state, legal, _ = gate.step(FGIPEvent.INVALIDATION)
    assert legal and state == FGIPState.DECIDING, "F6 FAIL: invalidation didn't go to DECIDING"

    # Re-decide, gates pass, execute, back to monitoring
    gate.step(FGIPEvent.GATES_PASSED)   # → EXECUTING
    gate.step(FGIPEvent.DECISION_MADE)  # → MONITORING
    assert gate.state == FGIPState.MONITORING, "F6 FAIL: didn't return to MONITORING"

    return True, gate.to_receipt()


def test_f7_random_illegal_catch():
    """F7: 100% catch rate on 50 randomly generated illegal sequences."""
    rng = np.random.default_rng(42)
    caught = 0
    total = 50

    for _ in range(total):
        gate = FGIPMorphSATGate()

        # Walk a legal path partway
        legal_prefix = [
            FGIPEvent.NEW_THESIS,
            FGIPEvent.EVIDENCE_COLLECTED,
            FGIPEvent.ANALYSIS_COMPLETE,
        ]
        prefix_len = rng.integers(0, len(legal_prefix) + 1)
        for e in legal_prefix[:prefix_len]:
            gate.step(e)

        # Inject a random event (most will be illegal from partial state)
        random_event = FGIPEvent(rng.integers(0, N_EVENTS))
        state, legal, action = gate.step(random_event)

        if not legal:
            caught += 1
        # If legal, that's OK — random event happened to be legal from this state

    # We want ALL illegal attempts caught. Some random events will be legal.
    # Count only the ones that were actually illegal transitions.
    # Re-run with explicit illegal injection.
    caught_illegal = 0
    total_illegal = 0

    for _ in range(total):
        gate = FGIPMorphSATGate()

        # Pick a state
        legal_paths = {
            FGIPState.IDLE: [],
            FGIPState.GATHERING: [FGIPEvent.NEW_THESIS],
            FGIPState.ANALYZING: [FGIPEvent.NEW_THESIS, FGIPEvent.EVIDENCE_COLLECTED],
            FGIPState.DECIDING: [FGIPEvent.NEW_THESIS, FGIPEvent.EVIDENCE_COLLECTED, FGIPEvent.ANALYSIS_COMPLETE],
        }
        target_state = FGIPState(rng.integers(0, 4))
        for e in legal_paths[target_state]:
            gate.step(e)

        # Find an illegal event from this state
        illegal_events = []
        for ev in FGIPEvent:
            if TRANSITION_TABLE[gate.state, ev] == -1 or (int(gate.state), int(ev)) in GUARDIAN_BLOCKED:
                illegal_events.append(ev)

        if not illegal_events:
            continue

        event = FGIPEvent(rng.choice([int(e) for e in illegal_events]))
        total_illegal += 1
        _, legal, _ = gate.step(event)
        if not legal:
            caught_illegal += 1

    catch_rate = caught_illegal / total_illegal if total_illegal else 1.0
    assert catch_rate == 1.0, f"F7 FAIL: catch rate {catch_rate:.4f} ({caught_illegal}/{total_illegal})"
    return True, {"catch_rate": catch_rate, "caught": caught_illegal, "total": total_illegal}


def test_f8_classify_event():
    """F8: classify_fgip_event() correctly maps agent action types."""
    cases = [
        ("EDGARAgent", "collect", FGIPEvent.EVIDENCE_COLLECTED),
        ("ConvictionEngine", "evaluate", FGIPEvent.ANALYSIS_COMPLETE),
        ("DecisionAgent", "BUY", FGIPEvent.DECISION_MADE),
        ("DecisionAgent", "EXIT", FGIPEvent.DECISION_MADE),
        ("TradePlanAgent", "TRADE_READY", FGIPEvent.GATES_PASSED),
        ("TradePlanAgent", "PASS", FGIPEvent.GATES_FAILED),
        ("PSSHBridge", "continue_gathering", FGIPEvent.NEW_EVIDENCE),
        ("PSSHBridge", "block_action", FGIPEvent.GATES_FAILED),
        ("AgenticReasoningLoop", "conclude", FGIPEvent.ANALYSIS_COMPLETE),
        # Fallback classifications
        ("UnknownAgent", "collect", FGIPEvent.EVIDENCE_COLLECTED),
        ("UnknownAgent", "evaluate", FGIPEvent.ANALYSIS_COMPLETE),
        ("UnknownAgent", "buy", FGIPEvent.DECISION_MADE),
        ("UnknownAgent", "trade_ready", FGIPEvent.GATES_PASSED),
        ("UnknownAgent", "invalidate", FGIPEvent.INVALIDATION),
        ("UnknownAgent", "close", FGIPEvent.POSITION_CLOSED),
        ("UnknownAgent", "reset", FGIPEvent.RESET),
    ]

    failures = []
    for agent, action, expected in cases:
        result = classify_fgip_event(agent, action)
        if result != expected:
            failures.append(f"  ({agent}, {action}): expected {EVENT_NAMES[expected]}, got {EVENT_NAMES[result]}")

    assert not failures, f"F8 FAIL:\n" + "\n".join(failures)
    return True, {"cases_tested": len(cases), "all_correct": True}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    t_start = time.time()
    cpu_start = time.process_time()
    start_iso = time.strftime('%Y-%m-%dT%H:%M:%S')

    print("=" * 70)
    print("  WO-FGIP-MORPHSAT-FSA-01: FGIP Decision Lifecycle FSA")
    print("=" * 70)
    print()
    print(f"FSA: {N_STATES} states, {N_EVENTS} events, {N_ILLEGAL} illegal, {N_LEGAL} legal")
    print(f"Guardian vows: {len(GUARDIAN_BLOCKED)} blocked (state, event) pairs")
    print()

    # Print FSA
    print("Transition table:")
    header = "              " + "  ".join(f"{e.name:>16s}" for e in FGIPEvent)
    print(header)
    for s in FGIPState:
        row = f"  {s.name:>12s}  "
        for e in FGIPEvent:
            val = TRANSITION_TABLE[s, e]
            if val == -1:
                row += f"{'ILLEGAL':>16s}  "
            else:
                row += f"{STATE_NAMES[val]:>16s}  "
        print(row)
    print()

    tests = [
        ("F1", "Legal thesis lifecycle", test_f1_legal_lifecycle),
        ("F2", "Skip-to-execute guardian block", test_f2_skip_to_execute),
        ("F3", "Decide-from-idle guardian block", test_f3_decide_from_idle),
        ("F4", "Close-without-monitoring guardian block", test_f4_close_without_monitoring),
        ("F5", "Gate revision loop", test_f5_gate_revision_loop),
        ("F6", "Invalidation loop", test_f6_invalidation_loop),
        ("F7", "100% random illegal catch", test_f7_random_illegal_catch),
        ("F8", "classify_fgip_event accuracy", test_f8_classify_event),
    ]

    results = {}
    all_pass = True
    for tag, desc, fn in tests:
        try:
            passed, detail = fn()
            results[tag] = {"pass": True, "desc": desc}
            print(f"  {tag}: {desc} [PASS]")
        except Exception as e:
            results[tag] = {"pass": False, "desc": desc, "error": str(e)}
            print(f"  {tag}: {desc} [FAIL] — {e}")
            all_pass = False

    print()
    print(f"  OVERALL: [{'PASS' if all_pass else 'FAIL'}] ({sum(1 for r in results.values() if r['pass'])}/{len(tests)})")
    print()

    cost = {
        'wall_time_s': round(time.time() - t_start, 3),
        'cpu_time_s': round(time.process_time() - cpu_start, 3),
        'peak_memory_mb': round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        'python_version': platform.python_version(),
        'hostname': platform.node(),
        'timestamp_start': start_iso,
        'timestamp_end': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    print(f"  Cost: {cost['wall_time_s']:.1f}s wall, {cost['peak_memory_mb']:.1f} MB peak")

    receipt = {
        'work_order': 'WO-FGIP-MORPHSAT-FSA-01',
        'question': 'Does the FGIP decision lifecycle FSA correctly enforce investment pipeline state?',
        'fsa': {
            'states': STATE_NAMES,
            'events': EVENT_NAMES,
            'n_states': N_STATES,
            'n_events': N_EVENTS,
            'n_illegal': N_ILLEGAL,
            'n_legal': N_LEGAL,
            'n_guardian_vows': len(GUARDIAN_BLOCKED),
        },
        'verdicts': results,
        'overall': all_pass,
        'cost': cost,
    }

    receipt_dir = Path(__file__).parent.parent / 'receipts'
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / f"fgip_morphsat_fsa_{time.strftime('%Y%m%dT%H%M%S')}.json"

    with open(receipt_path, 'w') as f:
        json.dump(receipt, f, indent=2)

    sha = hashlib.sha256(json.dumps(receipt, sort_keys=True).encode()).hexdigest()
    print(f"  Receipt: {receipt_path}")
    print(f"  SHA256:  {sha}")

    return 0 if all_pass else 1


if __name__ == '__main__':
    sys.exit(main())
