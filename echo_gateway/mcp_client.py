"""MCP Client for Echo Gateway - Direct Python calls to FGIP MCP tools.

Extends the echo_hedge pattern with additional graph tools for the chat UI.
"""

import json
from typing import Any
import sys
from pathlib import Path

# Add FGIP root to path
FGIP_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(FGIP_ROOT))


async def mcp_call_async(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """
    Call an MCP tool directly (in-process, async).

    Args:
        tool: Tool name (e.g., 'query_graph', 'search_nodes')
        arguments: Dict of tool arguments

    Returns:
        Parsed JSON response from the tool
    """
    # Import MCP handlers directly
    from mcp_server import (
        query_graph,
        search_nodes,
        explore_connections,
        get_graph_stats,
        get_thesis_score,
        get_both_sides_patterns,
        find_causal_chains,
        get_debt_domestication_metrics,
        run_compression_analysis,
    )

    tool_map = {
        # Core graph tools exposed to Echo
        "query_graph": query_graph,
        "search_nodes": search_nodes,
        "explore_connections": explore_connections,
        "get_graph_stats": get_graph_stats,
        # Analysis tools
        "get_thesis_score": get_thesis_score,
        "get_both_sides_patterns": get_both_sides_patterns,
        "find_causal_chains": find_causal_chains,
        "get_debt_domestication_metrics": get_debt_domestication_metrics,
        "run_compression_analysis": run_compression_analysis,
    }

    if tool not in tool_map:
        return {"error": f"Unknown MCP tool: {tool}", "available": list(tool_map.keys())}

    handler = tool_map[tool]

    # Call the handler - it returns CallToolResult
    # Some handlers take arguments, some don't
    if arguments:
        result = await handler(arguments)
    else:
        result = await handler()

    # Extract text from CallToolResult
    content = result.content
    if not content:
        return {"error": "Empty response from MCP tool"}

    text = content[0].text

    # Parse JSON if possible
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw_text": text}


def get_available_tools() -> list[str]:
    """Return list of available MCP tool names."""
    return [
        "query_graph",
        "search_nodes",
        "explore_connections",
        "get_graph_stats",
        "get_thesis_score",
        "get_both_sides_patterns",
        "find_causal_chains",
        "get_debt_domestication_metrics",
        "run_compression_analysis",
    ]
