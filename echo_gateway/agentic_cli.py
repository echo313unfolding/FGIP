#!/usr/bin/env python3
"""
Agentic Reasoning CLI.

WO-AGENTIC-REASONER-01

Usage:
    python -m echo_gateway.agentic_cli "Who owns Intel?"
    python -m echo_gateway.agentic_cli --task "Find causal chain from Fed policy to inflation"
    python -m echo_gateway.agentic_cli --task "What is the both-sides ownership pattern?" --max-iterations 15
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from echo_gateway.llm_client import LLMClient
from echo_gateway.agentic_loop import AgenticReasoningLoop


# Configuration from environment
LLM_BASE_URL = os.environ.get("ECHO_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
LLM_MODEL = os.environ.get("ECHO_MODEL", "qwen2.5:3b")
DB_PATH = os.environ.get("FGIP_DB_PATH", "fgip.db")


def print_step(step: dict, verbose: bool = False) -> None:
    """Print a reasoning step."""
    step_type = step.get("step_type", "unknown")
    content = step.get("content", "")

    # Color codes
    colors = {
        "think": "\033[94m",    # Blue
        "action": "\033[93m",   # Yellow
        "observation": "\033[92m",  # Green
        "reflection": "\033[95m",  # Magenta
        "error": "\033[91m",    # Red
    }
    reset = "\033[0m"

    color = colors.get(step_type, "")

    if verbose:
        print(f"\n{color}[{step_type.upper()}]{reset}")
        print(content[:500] + "..." if len(content) > 500 else content)
    else:
        # Compact output
        if step_type == "think":
            # Extract first line of thought
            first_line = content.split("\n")[0][:80]
            print(f"  {color}💭{reset} {first_line}...")
        elif step_type == "observation":
            print(f"  {color}👁{reset} Tool result received")
        elif step_type == "reflection":
            print(f"  {color}🔍{reset} Self-reflection")
        elif step_type == "error":
            print(f"  {color}❌{reset} Error: {content[:60]}...")


def print_tool_call(tool: dict) -> None:
    """Print a tool call."""
    name = tool.get("tool_name", "unknown")
    args = tool.get("tool_args", {})
    print(f"  \033[93m🔧{reset} {name}({json.dumps(args)[:60]}...)")


async def run_agentic(
    task: str,
    max_iterations: int = 10,
    require_reflection: bool = True,
    verbose: bool = False,
    output_json: bool = False,
) -> int:
    """Run the agentic reasoning loop."""

    # Initialize LLM client
    print(f"Connecting to LLM at {LLM_BASE_URL}...")
    llm_client = LLMClient(base_url=LLM_BASE_URL, model=LLM_MODEL)

    # Warmup
    warmup = await llm_client.warmup()
    if warmup.get("status") != "warmed":
        print(f"Warning: LLM warmup status: {warmup.get('status')}")

    # Initialize reasoning loop
    loop = AgenticReasoningLoop(
        llm_client=llm_client,
        db_path=DB_PATH,
    )

    print(f"\n{'='*60}")
    print(f"Task: {task}")
    print(f"Max iterations: {max_iterations}")
    print(f"{'='*60}\n")

    # Run reasoning
    try:
        state = await loop.run(
            task=task,
            max_iterations=max_iterations,
            require_reflection=require_reflection,
        )
    except Exception as e:
        print(f"\n\033[91mError: {e}\033[0m")
        await llm_client.close()
        return 1

    # Output results
    if output_json:
        print(json.dumps(state.to_dict(), indent=2, default=str))
    else:
        # Print reasoning trace
        print("Reasoning Trace:")
        print("-" * 40)

        for step in state.scratchpad:
            print_step(step.to_dict(), verbose)

        # Print tool calls
        if state.tool_results:
            print(f"\nTool Calls ({len(state.tool_results)}):")
            for tool in state.tool_results:
                print_tool_call(tool.to_dict())

        # Print reflections
        if state.reflections:
            print(f"\nReflections ({len(state.reflections)}):")
            for ref in state.reflections:
                assessment = ref.assessment
                if assessment == "sound":
                    icon = "✓"
                elif assessment == "error":
                    icon = "⚠"
                else:
                    icon = "?"
                print(f"  {icon} {assessment}: {ref.critique[:60]}...")

        # Print cognitive state
        if state.se_state:
            se = state.se_state
            print(f"\nSe State (Signal Entropy):")
            print(f"  H (Entropy):   {se.get('H', 0):.3f}")
            print(f"  C (Coherence): {se.get('C', 0):.3f}")
            print(f"  D (Depth):     {se.get('D', 0):.3f}")
            print(f"  Se (Routing):  {se.get('Se', 0):.3f}")

        # Print adversarial results
        if state.attacks_total > 0:
            survival_rate = state.attacks_survived / state.attacks_total
            color = "\033[92m" if survival_rate >= 0.7 else "\033[93m" if survival_rate >= 0.5 else "\033[91m"
            print(f"\nAdversarial Testing:")
            print(f"  Attacks: {state.attacks_survived}/{state.attacks_total} survived ({color}{survival_rate*100:.0f}%\033[0m)")

        # Print triangulation
        if state.triangulation:
            tri = state.triangulation
            status = "\033[92m\u2713\033[0m" if tri.get("triangulated") else "\033[93m\u2717\033[0m"
            print(f"\nTriangulation: {status}")
            if tri.get("supporting_sources"):
                print(f"  Supporting: {', '.join(tri['supporting_sources'][:3])}")

        # Print PSSH bridge decisions
        if state.bridge_receipts:
            print(f"\nPSSH Bridge ({len(state.bridge_receipts)} decisions):")
            # Show last decision (most important)
            last_receipt = state.bridge_receipts[-1]
            decision = last_receipt.get("decision", "unknown")
            rule = last_receipt.get("rule_fired", "unknown")

            # Color based on outcome
            if decision == "allow_conclude":
                color = "\033[92m"  # Green
                icon = "\u2713"
            elif decision == "downgrade_confidence":
                color = "\033[93m"  # Yellow
                icon = "\u26A0"
            elif decision in ("continue_gathering", "require_reflection"):
                color = "\033[93m"  # Yellow
                icon = "\u21BB"
            elif decision == "block_action":
                color = "\033[91m"  # Red
                icon = "\u2717"
            else:
                color = "\033[0m"
                icon = "?"

            print(f"  {color}{icon} {decision}\033[0m (rule: {rule})")

            if last_receipt.get("reasons"):
                for reason in last_receipt["reasons"][:2]:
                    print(f"    - {reason}")

            # Show confidence adjustment
            proposed = last_receipt.get("proposed_confidence", 0)
            adjusted = last_receipt.get("adjusted_confidence", 0)
            if proposed != adjusted:
                print(f"  Confidence: {proposed:.2f} → {adjusted:.2f}")

        # Print final answer
        print(f"\n{'='*60}")
        print(f"Status: {state.status}")
        print(f"Iterations: {state.iteration}/{max_iterations}")
        print(f"Confidence: {state.confidence:.2f}")
        print(f"Receipt: {state.receipt_id}")
        print(f"{'='*60}")

        if state.final_answer:
            print(f"\n\033[92mFinal Answer:\033[0m")
            print(state.final_answer)
        else:
            print(f"\n\033[93mNo conclusion reached.\033[0m")

    await llm_client.close()
    return 0 if state.status == "complete" else 1


def main():
    parser = argparse.ArgumentParser(
        description="Agentic Reasoning CLI - Think, Act, Observe, Reflect",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m echo_gateway.agentic_cli "Who owns Intel?"
    python -m echo_gateway.agentic_cli --task "Find the both-sides pattern" --max-iterations 15
    python -m echo_gateway.agentic_cli "What is the thesis score?" --verbose
    python -m echo_gateway.agentic_cli "Causal chain from Fed to inflation" --json
        """,
    )

    parser.add_argument(
        "task",
        nargs="?",
        help="The task/question to solve",
    )
    parser.add_argument(
        "--task", "-t",
        dest="task_flag",
        help="Alternative way to specify task",
    )
    parser.add_argument(
        "--max-iterations", "-n",
        type=int,
        default=10,
        help="Maximum reasoning iterations (default: 10)",
    )
    parser.add_argument(
        "--no-reflection",
        action="store_true",
        help="Disable periodic self-reflection",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show full reasoning output",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON",
    )

    args = parser.parse_args()

    # Get task from positional or flag
    task = args.task or args.task_flag
    if not task:
        parser.print_help()
        sys.exit(1)

    # Run
    exit_code = asyncio.run(run_agentic(
        task=task,
        max_iterations=args.max_iterations,
        require_reflection=not args.no_reflection,
        verbose=args.verbose,
        output_json=args.json,
    ))

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
