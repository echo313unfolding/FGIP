"""MCP Client for Echo Hedge - Direct Python calls to FGIP MCP tools.

Instead of subprocess/JSON-RPC, we directly import and call the async handlers.
This avoids the complexity of stdin/stdout JSON-RPC when running in-process.
"""

import asyncio
import json
from typing import Any, Dict
import sys
from pathlib import Path

# Add FGIP root to path
FGIP_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(FGIP_ROOT))


def mcp_call(tool: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Call an MCP tool directly (in-process, not via subprocess).

    Args:
        tool: Tool name (e.g., 'get_allocation_candidates')
        arguments: Dict of tool arguments

    Returns:
        Parsed JSON response from the tool
    """
    return asyncio.run(_async_mcp_call(tool, arguments))


async def _async_mcp_call(tool: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Async implementation of MCP call."""
    # Import MCP handlers directly
    from mcp_server import (
        get_allocation_candidates,
        get_candidate_risk_context,
        get_personal_runway,
        get_thesis_score,
        get_graph_stats,
        run_compression_analysis,
    )

    tool_map = {
        "get_allocation_candidates": get_allocation_candidates,
        "get_candidate_risk_context": get_candidate_risk_context,
        "get_personal_runway": get_personal_runway,
        "get_thesis_score": get_thesis_score,
        "get_graph_stats": get_graph_stats,
        "run_compression_analysis": run_compression_analysis,
    }

    if tool not in tool_map:
        raise ValueError(f"Unknown MCP tool: {tool}. Available: {list(tool_map.keys())}")

    handler = tool_map[tool]
    result = await handler(arguments)

    # Extract text from CallToolResult
    content = result.content
    if not content:
        return {"error": "Empty response"}

    text = content[0].text

    # Parse JSON if possible
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw_text": text}


def get_candidates(include_mining: bool = False, base_expected_return: float = 0.10) -> Dict[str, Any]:
    """Convenience wrapper for get_allocation_candidates."""
    return mcp_call("get_allocation_candidates", {
        "include_mining": include_mining,
        "base_expected_return": base_expected_return,
    })


def get_risk_context(candidate_ids: list) -> Dict[str, Any]:
    """Convenience wrapper for get_candidate_risk_context."""
    return mcp_call("get_candidate_risk_context", {
        "candidate_ids": candidate_ids,
    })


def get_runway(monthly_expenses: float, current_savings: float, **kwargs) -> Dict[str, Any]:
    """Convenience wrapper for get_personal_runway."""
    args = {
        "monthly_expenses": monthly_expenses,
        "current_savings": current_savings,
    }
    args.update(kwargs)
    return mcp_call("get_personal_runway", args)


if __name__ == "__main__":
    # Quick test
    print("Testing MCP client...")

    candidates = get_candidates(include_mining=False)
    print(f"Candidates: {candidates.get('candidate_count', 0)}")

    if candidates.get("candidates"):
        ids = [c["candidate_id"] for c in candidates["candidates"][:3]]
        risk = get_risk_context(ids)
        print(f"Risk contexts: {risk.get('candidates_analyzed', 0)}")
