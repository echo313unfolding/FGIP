"""Tool schemas and dispatcher for Echo Gateway.

Defines OpenAI-format tool schemas that map to MCP tools.
"""

from typing import Any

from .mcp_client import mcp_call_async


# OpenAI-format tool definitions for the LLM
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "graph_query",
            "description": "Query the FGIP knowledge graph with SQL WHERE clauses. Returns nodes or edges matching the query. Use for filtering by type, finding specific entities, or exploring relationships.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "SQL WHERE clause or search term. Examples: \"node_type = 'ORGANIZATION'\", \"name LIKE '%Intel%'\", \"edge_type = 'LOBBIED_FOR'\""
                    },
                    "table": {
                        "type": "string",
                        "enum": ["nodes", "edges", "claims", "sources"],
                        "description": "Table to query. Default: nodes"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default 50, max 200)"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "graph_search_nodes",
            "description": "Full-text search for nodes by name or description. Use when looking for entities by keyword without knowing exact IDs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_term": {
                        "type": "string",
                        "description": "Text to search for in node names and descriptions"
                    },
                    "node_type": {
                        "type": "string",
                        "description": "Optional filter by node type (ORGANIZATION, PERSON, LEGISLATION, COMPANY, etc.)"
                    }
                },
                "required": ["search_term"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "graph_get_node",
            "description": "Get details about a specific node and its connections. Use when you have a node_id and want to explore its neighborhood.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {
                        "type": "string",
                        "description": "The node ID to look up (e.g., 'blackrock', 'chips-act', 'intel')"
                    },
                    "depth": {
                        "type": "integer",
                        "description": "How many hops to traverse (1-3, default 1)"
                    }
                },
                "required": ["node_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "graph_get_stats",
            "description": "Get statistics about the knowledge graph: total nodes, edges, node type distribution, edge type distribution, source tier breakdown.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]


# Mapping from OpenAI tool names to MCP tool names + argument transforms
TOOL_MAPPING = {
    "graph_query": {
        "mcp_tool": "query_graph",
        "transform": lambda args: args  # Pass through as-is
    },
    "graph_search_nodes": {
        "mcp_tool": "search_nodes",
        "transform": lambda args: args
    },
    "graph_get_node": {
        "mcp_tool": "explore_connections",
        "transform": lambda args: args
    },
    "graph_get_stats": {
        "mcp_tool": "get_graph_stats",
        "transform": lambda args: {}  # No args needed
    }
}


async def dispatch_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """
    Dispatch a tool call to the appropriate MCP handler.

    Args:
        tool_name: OpenAI tool name from the LLM response
        arguments: Tool arguments from the LLM

    Returns:
        Tool result as a dict
    """
    if tool_name not in TOOL_MAPPING:
        return {"error": f"Unknown tool: {tool_name}"}

    mapping = TOOL_MAPPING[tool_name]
    mcp_tool = mapping["mcp_tool"]
    mcp_args = mapping["transform"](arguments)

    try:
        result = await mcp_call_async(mcp_tool, mcp_args)
        return result
    except Exception as e:
        return {"error": f"Tool execution failed: {str(e)}"}


def get_tool_schemas() -> list[dict[str, Any]]:
    """Return the tool schemas for the LLM."""
    return TOOL_SCHEMAS
