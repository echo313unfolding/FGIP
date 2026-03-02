#!/usr/bin/env python3
"""FGIP Schedule Runner - Orchestrates agent runs with delta tracking.

Usage:
    python3 tools/schedule_runner.py --agent edgar
    python3 tools/schedule_runner.py --tier 0
    python3 tools/schedule_runner.py --all
    python3 tools/schedule_runner.py --list-agents

Each run creates a receipt in receipts/schedule/ with:
- Run ID, timestamps, status
- Delta hash (what changed)
- Proposal counts
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fgip.db import FGIPDatabase

# Agent registry with tier mappings
AGENT_REGISTRY = {
    # Tier 0.5 - Pipeline orchestration (runs AFTER ingest, BEFORE approval)
    "pipeline-cycle": {
        "tier": 0.5,
        "module": "fgip.agents.pipeline_orchestrator",
        "class": "PipelineOrchestrator",
        "special": True,  # Not a standard FGIPAgent
    },

    # Tier 0 - Government primary sources
    "edgar": {"tier": 0, "module": "fgip.agents.edgar", "class": "EDGARAgent"},
    "usaspending": {"tier": 0, "module": "fgip.agents.usaspending", "class": "USASpendingAgent"},
    "gao": {"tier": 0, "module": "fgip.agents.gao", "class": "GAOAgent"},
    "federal-register": {"tier": 0, "module": "fgip.agents.federal_register", "class": "FederalRegisterAgent"},
    "tic": {"tier": 0, "module": "fgip.agents.tic", "class": "TICAgent"},
    "scotus": {"tier": 0, "module": "fgip.agents.scotus", "class": "SCOTUSAgent"},
    "fara": {"tier": 0, "module": "fgip.agents.fara", "class": "FARAAgent"},
    "fec": {"tier": 0, "module": "fgip.agents.fec", "class": "FECAgent"},
    "congress": {"tier": 0, "module": "fgip.agents.congress", "class": "CongressAgent"},
    "chips-facility": {"tier": 0, "module": "fgip.agents.chips_facility", "class": "CHIPSFacilityAgent"},
    "nuclear-smr": {"tier": 0, "module": "fgip.agents.nuclear_smr", "class": "NuclearSMRAgent"},

    # Tier 1 - Journalism & Smart Money
    "rss": {"tier": 1, "module": "fgip.agents.rss_signal", "class": "RSSSignalAgent"},
    "opensecrets": {"tier": 1, "module": "fgip.agents.opensecrets", "class": "OpenSecretsAgent"},
    "options-flow": {"tier": 1, "module": "fgip.agents.options_flow", "class": "OptionsFlowAgent"},

    # Tier 2 - Commentary/Analysis
    "promethean": {"tier": 2, "module": "fgip.agents.promethean", "class": "PrometheanAgent"},
    "youtube": {"tier": 2, "module": "fgip.agents.youtube_signal", "class": "YouTubeSignalAgent"},

    # Tier 3 - Meta-analysis (run after data agents)
    "gap-detector": {"tier": 3, "module": "fgip.agents.gap_detector", "class": "GapDetectorAgent"},
    "supply-chain-extractor": {"tier": 3, "module": "fgip.agents.supply_chain_extractor", "class": "SupplyChainExtractor"},
    "causal": {"tier": 3, "module": "fgip.agents.causal_agent", "class": "CausalAgent"},
    "coverage-probe": {"tier": 3, "module": "fgip.agents.coverage_probe", "class": "CoverageProbeAgent"},
    "coverage-analyzer": {"tier": 3, "module": "fgip.agents.coverage_analyzer", "class": "CoverageAnalyzer"},
    "signal-gap-ecosystem": {"tier": 3, "module": "fgip.agents.signal_gap_ecosystem", "class": "SignalGapEcosystemAgent"},

    # Tier 4 - Conviction Analysis (run AFTER all data agents)
    "conviction-engine": {"tier": 4, "module": "fgip.agents.conviction_engine", "class": "ConvictionEngine"},

    # Tier 5 - Calibration Pipeline (run AFTER conviction, produces calibrated outputs)
    "filter-agent": {"tier": 5, "module": "fgip.agents.filter_agent", "class": "FilterAgent"},
    "nlp-agent": {"tier": 5, "module": "fgip.agents.nlp_agent", "class": "NLPAgent"},
    "forecast-agent": {"tier": 5, "module": "fgip.agents.forecast_agent", "class": "ForecastAgent"},
    "decision-agent": {"tier": 5, "module": "fgip.agents.decision_agent", "class": "DecisionAgent"},

    # Tier 5.5 - Adversarial Verification (run AFTER calibration, verifies pipeline)
    "kat-harness": {
        "tier": 5.5,
        "module": "fgip.tests.kat.runner",
        "class": "KATHarness",
        "special": True,  # Uses run_with_delta() not standard run()
    },
}

# Receipts directory
RECEIPTS_DIR = PROJECT_ROOT / "receipts" / "schedule"


def ensure_receipts_dir():
    """Ensure receipts directory exists."""
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)


def load_agent(name: str, db: FGIPDatabase):
    """Dynamically load an agent by name."""
    if name not in AGENT_REGISTRY:
        raise ValueError(f"Unknown agent: {name}. Use --list-agents to see available agents.")

    info = AGENT_REGISTRY[name]
    module = __import__(info["module"], fromlist=[info["class"]])
    agent_class = getattr(module, info["class"])
    return agent_class(db)


def run_agent(name: str, db: FGIPDatabase) -> Dict[str, Any]:
    """Run a single agent with delta tracking and receipt generation."""
    if name not in AGENT_REGISTRY:
        return {
            "success": False,
            "agent_name": name,
            "error": f"Unknown agent: {name}",
            "tier": -1,
        }

    info = AGENT_REGISTRY[name]

    try:
        # Special handling for non-standard agents (like pipeline-cycle)
        if info.get("special"):
            module = __import__(info["module"], fromlist=[info["class"]])
            agent_class = getattr(module, info["class"])
            agent = agent_class(db)
            result = agent.run_with_delta()
        else:
            # Standard FGIPAgent path
            agent = load_agent(name, db)
            result = agent.run_with_delta()

        result["success"] = True
        result["agent_name"] = name
        result["tier"] = info["tier"]
    except Exception as e:
        result = {
            "success": False,
            "agent_name": name,
            "error": str(e),
            "tier": info.get("tier", -1),
        }
    return result


def write_receipt(
    results: List[Dict[str, Any]],
    invariant_check: Dict[str, Any] = None,
    bypass_warning: Dict[str, Any] = None,
    pipeline_cycle: Dict[str, Any] = None,
    kat_summary: Dict[str, Any] = None,
) -> str:
    """Write receipt file for the run."""
    ensure_receipts_dir()

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    receipt_path = RECEIPTS_DIR / f"run_{timestamp}.json"

    receipt = {
        "timestamp": timestamp,
        "agents_run": len(results),
        "successful": sum(1 for r in results if r.get("success")),
        "failed": sum(1 for r in results if not r.get("success")),
        "total_proposals": sum(r.get("claims_proposed", 0) + r.get("edges_proposed", 0) for r in results),
        "total_deltas": sum(r.get("delta_count", 0) for r in results),
        "results": results,
    }

    # Add pipeline-cycle stats if present
    if pipeline_cycle:
        receipt["pipeline_cycle"] = pipeline_cycle

    # Add invariant check results if present
    if invariant_check:
        receipt["invariant_check"] = invariant_check

    # Add bypass warning if detected
    if bypass_warning:
        receipt["bypass_warning"] = bypass_warning

    # Add KAT summary if present
    if kat_summary:
        receipt["kat_summary"] = kat_summary

    with open(receipt_path, "w") as f:
        json.dump(receipt, f, indent=2)

    return str(receipt_path)


def main():
    parser = argparse.ArgumentParser(description="FGIP Schedule Runner")
    parser.add_argument("--agent", type=str, help="Run a specific agent")
    parser.add_argument("--tier", type=float, choices=[0, 0.5, 1, 2, 3, 4, 5, 5.5], help="Run all agents of a specific tier")
    parser.add_argument("--all", action="store_true", help="Run all agents")
    parser.add_argument("--list-agents", action="store_true", help="List available agents")
    parser.add_argument("--db", type=str, default="fgip.db", help="Database path")
    parser.add_argument("--quiet", action="store_true", help="Minimal output")
    parser.add_argument(
        "--strict-kat",
        action="store_true",
        help="Exit 2 if KAT tests fail (like CRITICAL/HIGH invariants)"
    )

    args = parser.parse_args()

    if args.list_agents:
        print("Available agents:")
        tier_names = {
            0: "Government primary",
            0.5: "Pipeline orchestration",
            1: "Journalism & Smart Money",
            2: "Commentary",
            3: "Meta-analysis",
            4: "Conviction",
            5: "Calibration Pipeline",
            5.5: "Adversarial Verification",
        }
        for tier in [0, 0.5, 1, 2, 3, 4, 5, 5.5]:
            print(f"\n  Tier {tier} ({tier_names.get(tier, '')}):")
            for name, info in AGENT_REGISTRY.items():
                if info["tier"] == tier:
                    special = " [special]" if info.get("special") else ""
                    print(f"    {name}{special}")
        return

    # Determine which agents to run
    agents_to_run = []
    if args.agent:
        agents_to_run = [args.agent]
    elif args.tier is not None:
        agents_to_run = [name for name, info in AGENT_REGISTRY.items() if info["tier"] == args.tier]
    elif args.all:
        agents_to_run = list(AGENT_REGISTRY.keys())
    else:
        parser.print_help()
        return

    # Connect to database
    db = FGIPDatabase(args.db)
    db.connect()

    # Capture run start time for bypass detection (ISO format)
    run_started_at = datetime.utcnow().isoformat() + "Z"

    # Run agents
    results = []
    for name in agents_to_run:
        if not args.quiet:
            print(f"Running {name}...", end=" ", flush=True)

        result = run_agent(name, db)
        results.append(result)

        if not args.quiet:
            if result.get("success"):
                print(f"OK (delta={result.get('delta_count', 0)}, proposals={result.get('claims_proposed', 0) + result.get('edges_proposed', 0)})")
            else:
                print(f"FAILED: {result.get('error', 'unknown')}")

    # Extract pipeline-cycle stats if it ran
    pipeline_cycle_stats = None
    for r in results:
        if r.get("agent_name") == "pipeline-cycle" and r.get("success"):
            pipeline_cycle_stats = {
                "filtered": r.get("filtered", 0),
                "fast_track": r.get("fast_track", 0),
                "human_review": r.get("human_review", 0),
                "deprioritized": r.get("deprioritized", 0),
                "extracted": r.get("facts_extracted", 0),
                "proposals_created": r.get("claims_proposed", 0) + r.get("edges_proposed", 0),
                "extraction_failed": r.get("extraction_failed", 0),
            }
            break

    # Run invariants check after pipeline-cycle (or if --all)
    invariant_check = None
    invariant_failure = False
    if "pipeline-cycle" in agents_to_run or args.all:
        if not args.quiet:
            print("\nRunning invariants check...", end=" ", flush=True)

        try:
            # Import here to avoid circular imports
            sys.path.insert(0, str(PROJECT_ROOT / "tools"))
            from check_invariants import InvariantChecker

            checker = InvariantChecker(db)
            report = checker.run_all()

            invariant_check = {
                "critical": report.critical_count,
                "high": report.high_count,
                "medium": report.medium_count,
                "low": report.low_count,
                "exit_code": report.exit_code,
            }

            if not args.quiet:
                print(f"CRITICAL={report.critical_count}, HIGH={report.high_count}, MEDIUM={report.medium_count}, LOW={report.low_count}")

            # FAIL on CRITICAL or HIGH
            if report.critical_count > 0 or report.high_count > 0:
                invariant_failure = True
                if not args.quiet:
                    print(f"\n⚠️  INVARIANT FAILURE: {report.critical_count} CRITICAL, {report.high_count} HIGH violations!")
                    for v in report.violations[:10]:
                        if v.severity in ("CRITICAL", "HIGH"):
                            print(f"    [{v.severity}] {v.invariant}: {v.message[:60]}")

        except Exception as e:
            if not args.quiet:
                print(f"FAILED: {e}")
            invariant_check = {"error": str(e)}

    # KAT strict gate check
    kat_summary = None
    kat_failure = False
    kat_result = next((r for r in results if r.get("agent_name") == "kat-harness"), None)
    if kat_result:
        kat_summary = {
            "passed": kat_result.get("tests_passed", 0),
            "failed": kat_result.get("tests_failed", 0),
            "total": kat_result.get("tests_total", 0),
            "pass_rate": kat_result.get("pass_rate", 0),
        }
        if args.strict_kat and not kat_result.get("success"):
            kat_failure = True
            if not args.quiet:
                print(f"\n⚠️  KAT FAILURE: {kat_summary['failed']} tests failed!")

    # Bypass detection: check if proposals were created without going through queue
    bypass_warning = None
    if "pipeline-cycle" in agents_to_run or args.all:
        try:
            conn = db.connect()

            # Count proposals created during this run by agents OTHER than pipeline/nlp
            # Using run_started_at captured at beginning of main() (ISO format)
            direct_proposals = conn.execute("""
                SELECT COUNT(*) FROM proposed_edges
                WHERE created_at > ?
                AND agent_name NOT IN ('pipeline_orchestrator', 'nlp_agent', 'nlp-agent')
            """, (run_started_at,)).fetchone()[0]

            # Check if queue was empty (nothing queued for processing)
            queue_count = conn.execute(
                "SELECT COUNT(*) FROM artifact_queue WHERE status = 'PENDING'"
            ).fetchone()[0]

            # Also count artifacts that were queued during this run
            queued_this_run = sum(r.get("artifacts_queued", 0) for r in results)

            # Bypass detected: direct proposals but nothing queued
            if direct_proposals > 0 and queued_this_run == 0:
                bypass_warning = {
                    "direct_proposals": direct_proposals,
                    "queue_empty": queue_count == 0,
                    "message": f"⚠️ {direct_proposals} proposals created without going through artifact_queue",
                }
                if not args.quiet:
                    print(f"\n⚠️  BYPASS DETECTED: {direct_proposals} proposals created without queue")

        except Exception as e:
            if not args.quiet:
                print(f"Bypass detection error: {e}")

    # Write receipt
    receipt_path = write_receipt(
        results,
        invariant_check=invariant_check,
        bypass_warning=bypass_warning,
        pipeline_cycle=pipeline_cycle_stats,
        kat_summary=kat_summary,
    )

    # Summary
    if not args.quiet:
        print()
        print("=" * 50)
        print(f"  Agents run: {len(results)}")
        print(f"  Successful: {sum(1 for r in results if r.get('success'))}")
        print(f"  Failed: {sum(1 for r in results if not r.get('success'))}")
        print(f"  Total proposals: {sum(r.get('claims_proposed', 0) + r.get('edges_proposed', 0) for r in results)}")
        if pipeline_cycle_stats:
            print(f"  Pipeline: filtered={pipeline_cycle_stats['filtered']}, extracted={pipeline_cycle_stats['extracted']}")
        if invariant_check and not invariant_check.get("error"):
            status = "PASS" if not invariant_failure else "FAIL"
            print(f"  Invariants: {status} (C={invariant_check['critical']}, H={invariant_check['high']})")
        if bypass_warning:
            print(f"  Bypass: {bypass_warning['direct_proposals']} proposals bypassed queue!")
        if kat_summary:
            status = "PASS" if not kat_failure else "FAIL"
            print(f"  KAT: {status} ({kat_summary['passed']}/{kat_summary['total']} passed)")
        print(f"  Receipt: {receipt_path}")
        print("=" * 50)

    # Exit with error code if invariants or KAT failed
    if invariant_failure or kat_failure:
        sys.exit(2)


if __name__ == "__main__":
    main()
