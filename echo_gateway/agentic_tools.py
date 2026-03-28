"""
Extended tool schemas for agentic reasoning.

WO-AGENTIC-REASONER-01

Adds reasoning-specific tools on top of the base graph tools.
"""

import json
import re
import sqlite3
from typing import Any, Dict, List, Optional

# Import base tools
from .tools import TOOL_SCHEMAS as BASE_TOOL_SCHEMAS


# Additional tools for agentic reasoning
AGENTIC_TOOL_SCHEMAS = [
    # Calculator for math
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Perform mathematical calculations. Use for percentages, ratios, growth rates, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Math expression to evaluate (e.g., '(100-80)/80 * 100' for percentage change)"
                    }
                },
                "required": ["expression"]
            }
        }
    },
    # Find causal chains (multi-hop paths)
    {
        "type": "function",
        "function": {
            "name": "find_causal_chain",
            "description": "Find multi-hop causal paths between two nodes. Returns scored chains showing how A leads to B.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_node": {
                        "type": "string",
                        "description": "Starting node ID (e.g., 'fed-policy')"
                    },
                    "end_node": {
                        "type": "string",
                        "description": "Ending node ID (e.g., 'asset-inflation')"
                    },
                    "max_hops": {
                        "type": "integer",
                        "description": "Maximum path length (default: 4)"
                    }
                },
                "required": ["start_node", "end_node"]
            }
        }
    },
    # Both-sides pattern detection
    {
        "type": "function",
        "function": {
            "name": "find_both_sides_patterns",
            "description": "Find actors positioned on both sides of a policy (problem layer AND correction layer). Returns ownership overlaps.",
            "parameters": {
                "type": "object",
                "properties": {
                    "policy_node": {
                        "type": "string",
                        "description": "Policy node ID (e.g., 'chips-act')"
                    },
                    "min_confidence": {
                        "type": "number",
                        "description": "Minimum confidence threshold (default: 0.7)"
                    }
                },
                "required": ["policy_node"]
            }
        }
    },
    # Scratchpad write
    {
        "type": "function",
        "function": {
            "name": "scratchpad_write",
            "description": "Store an intermediate result in the scratchpad for later reference.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Key to store under (e.g., 'intel_owners')"
                    },
                    "value": {
                        "type": "string",
                        "description": "Value to store (can be JSON string)"
                    }
                },
                "required": ["key", "value"]
            }
        }
    },
    # Scratchpad read
    {
        "type": "function",
        "function": {
            "name": "scratchpad_read",
            "description": "Read a value from the scratchpad that was stored earlier.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Key to read"
                    }
                },
                "required": ["key"]
            }
        }
    },
    # Get thesis score
    {
        "type": "function",
        "function": {
            "name": "get_thesis_score",
            "description": "Get the current FGIP thesis verification score and breakdown. Shows overall confidence and component scores.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
]


def get_all_agentic_tools() -> List[Dict]:
    """Get combined base + agentic tool schemas."""
    return BASE_TOOL_SCHEMAS + AGENTIC_TOOL_SCHEMAS


class AgenticToolDispatcher:
    """
    Dispatch agentic tool calls.

    Handles both base graph tools and reasoning-specific tools.
    """

    def __init__(self, db_path: str = "fgip.db"):
        self.db_path = db_path
        self._scratchpad: Dict[str, str] = {}

    async def dispatch(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dispatch a tool call and return results.

        Args:
            tool_name: Name of the tool
            args: Tool arguments

        Returns:
            Tool result as dict
        """
        # Reasoning-specific tools
        if tool_name == "calculate":
            return self._calculate(args.get("expression", ""))

        elif tool_name == "find_causal_chain":
            return await self._find_causal_chain(
                args.get("start_node", ""),
                args.get("end_node", ""),
                args.get("max_hops", 4)
            )

        elif tool_name == "find_both_sides_patterns":
            return await self._find_both_sides_patterns(
                args.get("policy_node", ""),
                args.get("min_confidence", 0.7)
            )

        elif tool_name == "scratchpad_write":
            return self._scratchpad_write(
                args.get("key", ""),
                args.get("value", "")
            )

        elif tool_name == "scratchpad_read":
            return self._scratchpad_read(args.get("key", ""))

        elif tool_name == "get_thesis_score":
            return await self._get_thesis_score()

        # Base graph tools - delegate to MCP
        else:
            from .mcp_client import mcp_call_async
            return await mcp_call_async(tool_name, args)

    def _calculate(self, expression: str) -> Dict[str, Any]:
        """Safely evaluate a math expression."""
        try:
            # Only allow safe math operations
            allowed_chars = set("0123456789+-*/.() ")
            if not all(c in allowed_chars for c in expression):
                return {
                    "error": "Invalid characters in expression",
                    "allowed": "numbers, +, -, *, /, (, ), ."
                }

            result = eval(expression)
            return {
                "expression": expression,
                "result": result,
                "formatted": f"{result:.4f}" if isinstance(result, float) else str(result)
            }
        except Exception as e:
            return {"error": str(e)}

    async def _find_causal_chain(
        self,
        start_node: str,
        end_node: str,
        max_hops: int
    ) -> Dict[str, Any]:
        """Find causal paths between two nodes using BFS."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # BFS to find paths
            causal_types = ['CAUSED', 'ENABLED', 'CONTRIBUTED_TO', 'FUNDED_BY', 'LEADS_TO']

            paths = []
            visited = set()
            queue = [(start_node, [start_node], [])]  # (node, path, edges)

            while queue and len(paths) < 10:
                current, path, edges = queue.pop(0)

                if current == end_node:
                    paths.append({"nodes": path, "edges": edges})
                    continue

                if len(path) > max_hops:
                    continue

                if current in visited:
                    continue
                visited.add(current)

                # Find outgoing causal edges
                cursor.execute("""
                    SELECT to_node_id, edge_type, confidence
                    FROM edges
                    WHERE from_node_id = ? AND edge_type IN ({})
                """.format(",".join("?" * len(causal_types))),
                    [current] + causal_types
                )

                for row in cursor.fetchall():
                    new_path = path + [row["to_node_id"]]
                    new_edges = edges + [{
                        "from": current,
                        "to": row["to_node_id"],
                        "type": row["edge_type"],
                        "confidence": row["confidence"]
                    }]
                    queue.append((row["to_node_id"], new_path, new_edges))

            conn.close()

            # Score paths by confidence
            for p in paths:
                if p["edges"]:
                    confidences = [e["confidence"] for e in p["edges"]]
                    p["score"] = sum(confidences) / len(confidences)
                else:
                    p["score"] = 0

            paths.sort(key=lambda x: x["score"], reverse=True)

            return {
                "start": start_node,
                "end": end_node,
                "paths_found": len(paths),
                "paths": paths[:5]  # Top 5
            }

        except Exception as e:
            return {"error": str(e)}

    async def _find_both_sides_patterns(
        self,
        policy_node: str,
        min_confidence: float
    ) -> Dict[str, Any]:
        """Find actors on both sides of a policy."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Find problem layer (lobbied for, funded)
            cursor.execute("""
                SELECT DISTINCT from_node_id as actor
                FROM edges
                WHERE to_node_id = ? AND edge_type IN ('LOBBIED_FOR', 'FUNDED')
            """, [policy_node])
            problem_actors = set(row["actor"] for row in cursor.fetchall())

            # Find correction layer (funded by, granted to)
            cursor.execute("""
                SELECT DISTINCT to_node_id as beneficiary
                FROM edges
                WHERE from_node_id = ? AND edge_type IN ('FUNDED_BY', 'GRANTED_TO')
            """, [policy_node])
            correction_beneficiaries = set(row["beneficiary"] for row in cursor.fetchall())

            # Find ownership overlaps
            both_sides = []
            for actor in problem_actors:
                # Check if actor owns shares in any beneficiary
                cursor.execute("""
                    SELECT to_node_id, confidence
                    FROM edges
                    WHERE from_node_id = ? AND edge_type = 'OWNS_SHARES'
                    AND to_node_id IN ({})
                    AND confidence >= ?
                """.format(",".join("?" * len(correction_beneficiaries))),
                    [actor] + list(correction_beneficiaries) + [min_confidence]
                )

                for row in cursor.fetchall():
                    both_sides.append({
                        "actor": actor,
                        "owns": row["to_node_id"],
                        "confidence": row["confidence"],
                        "pattern": "problem_layer_owns_correction_beneficiary"
                    })

            conn.close()

            return {
                "policy": policy_node,
                "problem_actors": list(problem_actors),
                "correction_beneficiaries": list(correction_beneficiaries),
                "both_sides_patterns": both_sides,
                "pattern_count": len(both_sides)
            }

        except Exception as e:
            return {"error": str(e)}

    def _scratchpad_write(self, key: str, value: str) -> Dict[str, Any]:
        """Write to scratchpad."""
        self._scratchpad[key] = value
        return {
            "status": "stored",
            "key": key,
            "scratchpad_size": len(self._scratchpad)
        }

    def _scratchpad_read(self, key: str) -> Dict[str, Any]:
        """Read from scratchpad."""
        if key in self._scratchpad:
            return {
                "key": key,
                "value": self._scratchpad[key],
                "found": True
            }
        return {
            "key": key,
            "found": False,
            "available_keys": list(self._scratchpad.keys())
        }

    async def _get_thesis_score(self) -> Dict[str, Any]:
        """Get thesis verification score."""
        try:
            from .mcp_client import mcp_call_async
            return await mcp_call_async("get_thesis_score", {})
        except Exception as e:
            return {"error": str(e)}

    def clear_scratchpad(self):
        """Clear the scratchpad."""
        self._scratchpad.clear()
