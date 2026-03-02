#!/usr/bin/env python3
"""FGIP MCP Server - Exposes FGIP tools to Claude Code via Model Context Protocol.

Run with:
    python3 mcp_server.py

Or as a persistent service:
    systemctl --user start fgip-mcp
"""

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any, Optional
from datetime import datetime

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    CallToolResult,
)

# FGIP paths
FGIP_ROOT = Path(__file__).parent
DB_PATH = FGIP_ROOT / "fgip.db"

server = Server("fgip-server")


def get_db_connection() -> sqlite3.Connection:
    """Get database connection with row factory."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ============================================================================
# TOOL DEFINITIONS
# ============================================================================

@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available FGIP tools."""
    return [
        Tool(
            name="query_graph",
            description="Query the FGIP knowledge graph. Returns nodes and edges matching the query.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "SQL WHERE clause or search term for nodes/edges"
                    },
                    "table": {
                        "type": "string",
                        "enum": ["nodes", "edges", "claims", "sources"],
                        "description": "Table to query (default: nodes)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default: 50)"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="get_thesis_score",
            description="Get the current FGIP thesis verification score and breakdown.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_convergence_report",
            description="Get the signal convergence report showing Promethean predictions vs POTUS actions vs market response.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="explore_connections",
            description="Find all connections (edges) for a given node, showing the network around an entity.",
            inputSchema={
                "type": "object",
                "properties": {
                    "node_id": {
                        "type": "string",
                        "description": "Node ID to explore (e.g., 'blackrock', 'chips-act', 'genius-act-2025')"
                    },
                    "depth": {
                        "type": "integer",
                        "description": "How many hops to traverse (default: 1, max: 3)"
                    }
                },
                "required": ["node_id"]
            }
        ),
        Tool(
            name="find_causal_chains",
            description="Find causal chains in the graph connecting problems to corrections.",
            inputSchema={
                "type": "object",
                "properties": {
                    "start_node": {
                        "type": "string",
                        "description": "Optional starting node ID"
                    },
                    "end_node": {
                        "type": "string",
                        "description": "Optional ending node ID"
                    }
                }
            }
        ),
        Tool(
            name="get_both_sides_patterns",
            description="Find entities appearing on both 'problem' and 'correction' sides of the thesis.",
            inputSchema={
                "type": "object",
                "properties": {
                    "min_confidence": {
                        "type": "number",
                        "description": "Minimum confidence threshold (0-1, default: 0.7)"
                    }
                }
            }
        ),
        Tool(
            name="run_agent",
            description="Run an FGIP agent to collect and propose new evidence.",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent": {
                        "type": "string",
                        "enum": [
                            "promethean", "scotus", "tic", "stablecoin",
                            "congress", "fec", "edgar", "gao", "fara",
                            "opensecrets", "usaspending", "federal_register"
                        ],
                        "description": "Agent to run"
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, don't write to database (default: false)"
                    }
                },
                "required": ["agent"]
            }
        ),
        Tool(
            name="get_graph_stats",
            description="Get statistics about the FGIP knowledge graph.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="search_nodes",
            description="Search for nodes by name or description using full-text search.",
            inputSchema={
                "type": "object",
                "properties": {
                    "search_term": {
                        "type": "string",
                        "description": "Text to search for in node names/descriptions"
                    },
                    "node_type": {
                        "type": "string",
                        "description": "Optional filter by node type (ORGANIZATION, PERSON, LEGISLATION, etc.)"
                    }
                },
                "required": ["search_term"]
            }
        ),
        Tool(
            name="get_debt_domestication_metrics",
            description="Get current debt domestication metrics: foreign holdings, stablecoin absorption, leverage reduction.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="run_compression_analysis",
            description="Run compression-based pattern detection to find motifs, similar entities, and anomalies using SHAKE256 fingerprinting.",
            inputSchema={
                "type": "object",
                "properties": {
                    "include_anomalies": {
                        "type": "boolean",
                        "description": "Include anomaly detection (default: true)"
                    },
                    "include_similarity": {
                        "type": "boolean",
                        "description": "Include entity similarity search (default: true)"
                    }
                }
            }
        ),
        Tool(
            name="get_personal_runway",
            description="Calculate personal financial runway using FGIP-validated inflation rates (M2=6.3%, not CPI=2.7%). Shows real savings yield, real debt cost, and runway under different scenarios. No data is stored - pure calculation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "monthly_expenses": {
                        "type": "number",
                        "description": "Monthly expenses/burn rate in USD"
                    },
                    "current_savings": {
                        "type": "number",
                        "description": "Current liquid savings in USD"
                    },
                    "savings_yield": {
                        "type": "number",
                        "description": "Current savings APY as decimal (e.g., 0.045 for 4.5%). Default: 0.045"
                    },
                    "debt_balance": {
                        "type": "number",
                        "description": "Total debt balance in USD (optional, default: 0)"
                    },
                    "debt_apr": {
                        "type": "number",
                        "description": "Weighted average debt APR as decimal (optional, default: 0)"
                    },
                    "income_monthly": {
                        "type": "number",
                        "description": "Monthly income in USD (optional, default: 0)"
                    }
                },
                "required": ["monthly_expenses", "current_savings"]
            }
        ),
        Tool(
            name="get_allocation_candidates",
            description="Get allocation candidates from FGIP graph for portfolio construction. Returns reshoring beneficiaries (CHIPS Act), gold proxy, T-Bills, and optionally mining assets - each with graph metadata (tier, confidence, edge counts). Designed for Echo Hedge integration.",
            inputSchema={
                "type": "object",
                "properties": {
                    "include_mining": {
                        "type": "boolean",
                        "description": "Include mining pool assets from Echo Hedge schema (default: false)"
                    },
                    "base_expected_return": {
                        "type": "number",
                        "description": "Base expected nominal return assumption as decimal (default: 0.10 for 10%)"
                    }
                }
            }
        ),
        Tool(
            name="get_candidate_risk_context",
            description="Get risk context for allocation candidates from FGIP graph neighborhoods. Returns tier distribution, both-sides motif hits, anomaly score, and edge breakdown. Use after get_allocation_candidates to inform position sizing.",
            inputSchema={
                "type": "object",
                "properties": {
                    "candidate_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of node IDs to get risk context for"
                    }
                },
                "required": ["candidate_ids"]
            }
        ),
        Tool(
            name="ingest_youtube_history",
            description="Ingest YouTube watch history from Google Takeout and build signal layer connecting viewing patterns to FGIP thesis. Extracts guests, channels, topics and cross-references against the knowledge graph.",
            inputSchema={
                "type": "object",
                "properties": {
                    "html_path": {
                        "type": "string",
                        "description": "Path to watch-history.html from Google Takeout"
                    }
                },
                "required": ["html_path"]
            }
        ),
        Tool(
            name="get_system_briefing",
            description="Get system intelligence briefing: pending approvals, parser gaps, API health, and work orders for Claude Code. Use this to understand what the FGIP system needs - bottlenecks, missing capabilities, and tasks for you to build.",
            inputSchema={
                "type": "object",
                "properties": {
                    "include_work_orders": {
                        "type": "boolean",
                        "description": "Include work orders for Claude Code (default: true)"
                    },
                    "include_health": {
                        "type": "boolean",
                        "description": "Include API health status (default: true)"
                    }
                }
            }
        ),
    ]


# ============================================================================
# TOOL IMPLEMENTATIONS
# ============================================================================

@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
    """Handle tool calls."""

    if name == "query_graph":
        return await query_graph(arguments)
    elif name == "get_thesis_score":
        return await get_thesis_score()
    elif name == "get_convergence_report":
        return await get_convergence_report()
    elif name == "explore_connections":
        return await explore_connections(arguments)
    elif name == "find_causal_chains":
        return await find_causal_chains(arguments)
    elif name == "get_both_sides_patterns":
        return await get_both_sides_patterns(arguments)
    elif name == "run_agent":
        return await run_agent(arguments)
    elif name == "get_graph_stats":
        return await get_graph_stats()
    elif name == "search_nodes":
        return await search_nodes(arguments)
    elif name == "get_debt_domestication_metrics":
        return await get_debt_domestication_metrics()
    elif name == "run_compression_analysis":
        return await run_compression_analysis(arguments)
    elif name == "get_personal_runway":
        return await get_personal_runway(arguments)
    elif name == "get_allocation_candidates":
        return await get_allocation_candidates(arguments)
    elif name == "get_candidate_risk_context":
        return await get_candidate_risk_context(arguments)
    elif name == "ingest_youtube_history":
        return await ingest_youtube_history(arguments)
    elif name == "get_system_briefing":
        return await get_system_briefing(arguments)
    else:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Unknown tool: {name}")]
        )


async def query_graph(args: dict) -> CallToolResult:
    """Query the knowledge graph."""
    query = args.get("query", "")
    table = args.get("table", "nodes")
    limit = min(args.get("limit", 50), 200)

    # Auto-translate common column aliases for user convenience
    # Schema uses 'node_type' but users naturally query 'type'
    if table == "nodes":
        query = re.sub(r'\btype\s*=', 'node_type =', query, flags=re.IGNORECASE)
        query = re.sub(r'\btype\s+LIKE', 'node_type LIKE', query, flags=re.IGNORECASE)
        query = re.sub(r'\btype\s+IN', 'node_type IN', query, flags=re.IGNORECASE)

    conn = get_db_connection()
    try:
        # Handle simple search vs SQL WHERE clause
        if not any(op in query.upper() for op in ["=", "LIKE", "IN", ">", "<", "AND", "OR"]):
            # Simple search - use LIKE
            if table == "nodes":
                sql = f"SELECT * FROM nodes WHERE name LIKE ? OR node_id LIKE ? LIMIT ?"
                rows = conn.execute(sql, (f"%{query}%", f"%{query}%", limit)).fetchall()
            elif table == "edges":
                sql = f"SELECT * FROM edges WHERE from_node_id LIKE ? OR to_node_id LIKE ? OR edge_type LIKE ? LIMIT ?"
                rows = conn.execute(sql, (f"%{query}%", f"%{query}%", f"%{query}%", limit)).fetchall()
            else:
                sql = f"SELECT * FROM {table} LIMIT ?"
                rows = conn.execute(sql, (limit,)).fetchall()
        else:
            # SQL WHERE clause
            sql = f"SELECT * FROM {table} WHERE {query} LIMIT ?"
            rows = conn.execute(sql, (limit,)).fetchall()

        results = [dict(row) for row in rows]
        return CallToolResult(
            content=[TextContent(
                type="text",
                text=json.dumps({"count": len(results), "results": results}, indent=2)
            )]
        )
    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {str(e)}")]
        )
    finally:
        conn.close()


async def get_thesis_score() -> CallToolResult:
    """Get thesis verification score."""
    conn = get_db_connection()
    try:
        # Count verified edges by type
        problem_types = ("LOBBIED_FOR", "DONATED_TO", "FUNDED_BY", "REGISTERED_AS_AGENT",
                        "FILED_AMICUS", "EMPLOYED", "OWNS_MEDIA", "HAS_LEVERAGE_OVER",
                        "BLOCKS", "HOLDS_TREASURY")
        correction_types = ("AWARDED_GRANT", "BUILT_IN", "FUNDED_PROJECT", "IMPLEMENTED_BY",
                           "RULEMAKING_FOR", "AUTHORIZED_BY", "CORRECTS", "ENABLES",
                           "REDUCES", "FUNDS", "CONTRIBUTES_TO")

        problem_count = conn.execute(
            f"SELECT COUNT(*) FROM edges WHERE edge_type IN ({','.join('?' * len(problem_types))})",
            problem_types
        ).fetchone()[0]

        correction_count = conn.execute(
            f"SELECT COUNT(*) FROM edges WHERE edge_type IN ({','.join('?' * len(correction_types))})",
            correction_types
        ).fetchone()[0]

        total_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        total_nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]

        # Both-sides detection
        both_sides_sql = """
        SELECT DISTINCT e1.from_node_id
        FROM edges e1
        JOIN edges e2 ON e1.from_node_id = e2.from_node_id
        WHERE e1.edge_type IN ('OWNS', 'INVESTED_IN', 'HOLDS')
        AND e2.edge_type IN ('AWARDED_GRANT', 'RECEIVED_FUNDING', 'BUILT_IN')
        """
        both_sides = conn.execute(both_sides_sql).fetchall()

        # Load convergence report if available
        convergence_path = FGIP_ROOT / "data" / "reports" / "convergence_report.json"
        convergence_score = None
        if convergence_path.exists():
            with open(convergence_path) as f:
                convergence = json.load(f)
                convergence_score = convergence.get("convergence_score")

        score = {
            "timestamp": datetime.now().isoformat(),
            "graph_stats": {
                "total_nodes": total_nodes,
                "total_edges": total_edges,
                "problem_edges": problem_count,
                "correction_edges": correction_count,
            },
            "both_sides_entities": len(both_sides),
            "convergence_score": convergence_score,
            "thesis": "Structural capital concentration creates mechanical both-sides exposure across policy pendulum swings."
        }

        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(score, indent=2))]
        )
    finally:
        conn.close()


async def get_convergence_report() -> CallToolResult:
    """Get signal convergence report."""
    report_path = FGIP_ROOT / "data" / "reports" / "convergence_report.json"

    if not report_path.exists():
        return CallToolResult(
            content=[TextContent(type="text", text="Convergence report not found. Run: python3 fgip/analysis/signal_convergence.py")]
        )

    with open(report_path) as f:
        report = json.load(f)

    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(report, indent=2))]
    )


async def explore_connections(args: dict) -> CallToolResult:
    """Explore connections around a node."""
    node_id = args.get("node_id")
    depth = min(args.get("depth", 1), 3)

    if not node_id:
        return CallToolResult(
            content=[TextContent(type="text", text="Error: node_id required")]
        )

    conn = get_db_connection()
    try:
        # Get the node
        node = conn.execute("SELECT * FROM nodes WHERE node_id = ?", (node_id,)).fetchone()
        if not node:
            # Try partial match
            nodes = conn.execute(
                "SELECT * FROM nodes WHERE node_id LIKE ? LIMIT 5",
                (f"%{node_id}%",)
            ).fetchall()
            if nodes:
                return CallToolResult(
                    content=[TextContent(
                        type="text",
                        text=f"Node not found. Did you mean: {[dict(n)['node_id'] for n in nodes]}"
                    )]
                )
            return CallToolResult(
                content=[TextContent(type="text", text=f"Node not found: {node_id}")]
            )

        # BFS to find connections
        visited = {node_id}
        connections = []
        current_level = [node_id]

        for d in range(depth):
            next_level = []
            for nid in current_level:
                # Outgoing edges
                out_edges = conn.execute(
                    "SELECT * FROM edges WHERE from_node_id = ?", (nid,)
                ).fetchall()
                for edge in out_edges:
                    connections.append({
                        "depth": d + 1,
                        "direction": "outgoing",
                        "edge": dict(edge)
                    })
                    if edge["to_node_id"] not in visited:
                        visited.add(edge["to_node_id"])
                        next_level.append(edge["to_node_id"])

                # Incoming edges
                in_edges = conn.execute(
                    "SELECT * FROM edges WHERE to_node_id = ?", (nid,)
                ).fetchall()
                for edge in in_edges:
                    connections.append({
                        "depth": d + 1,
                        "direction": "incoming",
                        "edge": dict(edge)
                    })
                    if edge["from_node_id"] not in visited:
                        visited.add(edge["from_node_id"])
                        next_level.append(edge["from_node_id"])

            current_level = next_level

        result = {
            "node": dict(node),
            "total_connections": len(connections),
            "connections": connections[:100]  # Limit output
        }

        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(result, indent=2))]
        )
    finally:
        conn.close()


async def find_causal_chains(args: dict) -> CallToolResult:
    """Find causal chains connecting problems to corrections."""
    start_node = args.get("start_node")
    end_node = args.get("end_node")

    # Import reasoning agent for chain detection
    import sys
    sys.path.insert(0, str(FGIP_ROOT))

    try:
        from fgip.db import FGIPDatabase
        from fgip.agents.reasoning import ReasoningAgent

        db = FGIPDatabase(str(DB_PATH))
        agent = ReasoningAgent(db)

        chains = agent.find_causal_chains(start_node, end_node) if start_node or end_node else agent.find_causal_chains()

        return CallToolResult(
            content=[TextContent(
                type="text",
                text=json.dumps({"chains_found": len(chains), "chains": chains[:20]}, indent=2)
            )]
        )
    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {str(e)}")]
        )


async def get_both_sides_patterns(args: dict) -> CallToolResult:
    """Find entities on both sides of the thesis."""
    min_confidence = args.get("min_confidence", 0.7)

    conn = get_db_connection()
    try:
        # Problem edge types
        problem_types = ("LOBBIED_FOR", "DONATED_TO", "FUNDED_BY", "REGISTERED_AS_AGENT",
                        "FILED_AMICUS", "OWNS", "INVESTED_IN", "HAS_LEVERAGE_OVER")
        # Correction edge types
        correction_types = ("AWARDED_GRANT", "BUILT_IN", "FUNDED_PROJECT", "RECEIVED_FUNDING",
                           "INVESTED_IN", "ENABLES", "FUNDS")

        # Find entities with edges in both categories
        sql = """
        SELECT
            n.node_id, n.name, n.node_type,
            GROUP_CONCAT(DISTINCT e1.edge_type) as problem_edges,
            GROUP_CONCAT(DISTINCT e2.edge_type) as correction_edges
        FROM nodes n
        JOIN edges e1 ON n.node_id = e1.from_node_id
        JOIN edges e2 ON n.node_id = e2.from_node_id
        WHERE e1.edge_type IN ({}) AND e2.edge_type IN ({})
        GROUP BY n.node_id
        """.format(','.join('?' * len(problem_types)), ','.join('?' * len(correction_types)))

        rows = conn.execute(sql, problem_types + correction_types).fetchall()

        patterns = []
        for row in rows:
            pattern = dict(row)
            pattern["confidence"] = 0.95  # Based on SEC EDGAR data
            if pattern["confidence"] >= min_confidence:
                patterns.append(pattern)

        return CallToolResult(
            content=[TextContent(
                type="text",
                text=json.dumps({"count": len(patterns), "patterns": patterns}, indent=2)
            )]
        )
    finally:
        conn.close()


async def run_agent(args: dict) -> CallToolResult:
    """Run an FGIP agent."""
    agent_name = args.get("agent")
    dry_run = args.get("dry_run", False)

    agent_map = {
        "promethean": "fgip.agents.promethean",
        "scotus": "fgip.agents.scotus",
        "tic": "fgip.agents.tic",
        "stablecoin": "fgip.agents.stablecoin",
        "congress": "fgip.agents.congress",
        "fec": "fgip.agents.fec",
        "edgar": "fgip.agents.edgar",
        "gao": "fgip.agents.gao",
        "fara": "fgip.agents.fara",
        "opensecrets": "fgip.agents.opensecrets",
        "usaspending": "fgip.agents.usaspending",
        "federal_register": "fgip.agents.federal_register",
    }

    if agent_name not in agent_map:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Unknown agent: {agent_name}")]
        )

    import subprocess

    cmd = ["python3", "-m", agent_map[agent_name], str(DB_PATH)]
    if dry_run:
        cmd.append("--dry-run")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(FGIP_ROOT),
            env={"PYTHONPATH": str(FGIP_ROOT)}
        )

        output = result.stdout + result.stderr
        return CallToolResult(
            content=[TextContent(type="text", text=f"Agent {agent_name} completed:\n{output[-2000:]}")]
        )
    except subprocess.TimeoutExpired:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Agent {agent_name} timed out after 120s")]
        )
    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error running agent: {str(e)}")]
        )


async def get_graph_stats() -> CallToolResult:
    """Get graph statistics."""
    conn = get_db_connection()
    try:
        stats = {}

        # Total counts
        stats["total_nodes"] = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        stats["total_edges"] = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        stats["total_claims"] = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
        stats["total_sources"] = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]

        # Node types
        node_types = conn.execute(
            "SELECT node_type, COUNT(*) as count FROM nodes GROUP BY node_type ORDER BY count DESC"
        ).fetchall()
        stats["node_types"] = {row["node_type"]: row["count"] for row in node_types}

        # Edge types
        edge_types = conn.execute(
            "SELECT edge_type, COUNT(*) as count FROM edges GROUP BY edge_type ORDER BY count DESC LIMIT 20"
        ).fetchall()
        stats["edge_types"] = {row["edge_type"]: row["count"] for row in edge_types}

        # Source tiers
        tiers = conn.execute(
            "SELECT tier, COUNT(*) as count FROM sources GROUP BY tier ORDER BY tier"
        ).fetchall()
        stats["source_tiers"] = {f"tier_{row['tier']}": row["count"] for row in tiers}

        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(stats, indent=2))]
        )
    finally:
        conn.close()


async def search_nodes(args: dict) -> CallToolResult:
    """Search nodes by text."""
    search_term = args.get("search_term", "")
    node_type = args.get("node_type")

    conn = get_db_connection()
    try:
        if node_type:
            sql = """
            SELECT * FROM nodes
            WHERE (name LIKE ? OR description LIKE ? OR node_id LIKE ?)
            AND node_type = ?
            LIMIT 50
            """
            rows = conn.execute(sql, (f"%{search_term}%", f"%{search_term}%", f"%{search_term}%", node_type)).fetchall()
        else:
            sql = """
            SELECT * FROM nodes
            WHERE name LIKE ? OR description LIKE ? OR node_id LIKE ?
            LIMIT 50
            """
            rows = conn.execute(sql, (f"%{search_term}%", f"%{search_term}%", f"%{search_term}%")).fetchall()

        results = [dict(row) for row in rows]
        return CallToolResult(
            content=[TextContent(
                type="text",
                text=json.dumps({"count": len(results), "results": results}, indent=2)
            )]
        )
    finally:
        conn.close()


async def get_debt_domestication_metrics() -> CallToolResult:
    """Get debt domestication metrics."""
    # Load from stablecoin agent constants
    metrics = {
        "foreign_holdings": {
            "china": {"holdings_b": 759.0, "is_ally": False},
            "japan": {"holdings_b": 1060.0, "is_ally": True},
            "total_foreign": 8500.0,
            "unit": "$B"
        },
        "stablecoin_absorption": {
            "tether": {"market_cap_b": 120.0, "treasury_holdings_b": 72.0},
            "circle": {"market_cap_b": 45.0, "treasury_holdings_b": 36.0},
            "total_treasury_holdings_b": 115.0,
        },
        "genius_act": {
            "signed": "2025-07-18",
            "holder_yield": 0.0,
            "issuer_yield": 4.5,
            "reserve_requirement": 1.0,
        },
        "domestication_metrics": {
            "current_pct": 1.35,  # 115B / 8500B
            "projected_2028_pct": 23.53,  # 2000B / 8500B
            "leverage_reduction": "23.53% of foreign leverage neutralized at $2T stablecoins"
        },
        "mechanism": "GENIUS Act → stablecoin Treasury absorption → debt domestication → foreign leverage reduction → tariff enablement"
    }

    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(metrics, indent=2))]
    )


async def run_compression_analysis(args: dict) -> CallToolResult:
    """Run compression-based pattern detection."""
    include_anomalies = args.get("include_anomalies", True)
    include_similarity = args.get("include_similarity", True)

    import sys
    sys.path.insert(0, str(FGIP_ROOT))

    try:
        from fgip.analysis.compression_patterns import CompressionPatternAnalyzer

        analyzer = CompressionPatternAnalyzer(str(DB_PATH))
        analyzer.connect()

        report = analyzer.run_full_analysis(
            include_sketches=True,
            include_anomalies=include_anomalies,
            include_similarity=include_similarity,
        )

        # Summarize for output
        summary = {
            "timestamp": report.timestamp,
            "evidence_level": report.evidence_level,
            "total_nodes": report.total_nodes,
            "total_edges": report.total_edges,
            "motif_matches": [
                {
                    "pattern_name": m.pattern_name,
                    "nodes": m.nodes_involved,
                    "confidence": m.confidence,
                    "compression_ratio": m.compression_ratio,
                }
                for m in report.motif_matches[:10]
            ],
            "similar_entities": [
                {
                    "pair": [s.node_a, s.node_b],
                    "similarity": s.similarity,
                    "shared_types": s.shared_edge_types[:3],
                }
                for s in report.similar_entities[:10]
            ],
            "anomalies": [
                {
                    "node": a.node_name,
                    "type": a.node_type,
                    "score": a.anomaly_score,
                    "unusual": a.unusual_edges[:3],
                }
                for a in report.anomalies[:10]
            ],
            "counts": {
                "motifs": len(report.motif_matches),
                "similar_pairs": len(report.similar_entities),
                "anomalies": len(report.anomalies),
            }
        }

        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(summary, indent=2))]
        )
    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {str(e)}")]
        )


async def get_personal_runway(args: dict) -> CallToolResult:
    """Calculate personal financial runway using FGIP-validated inflation."""
    monthly_expenses = args.get("monthly_expenses")
    current_savings = args.get("current_savings")
    savings_yield = args.get("savings_yield", 0.045)
    debt_balance = args.get("debt_balance", 0.0)
    debt_apr = args.get("debt_apr", 0.0)
    income_monthly = args.get("income_monthly", 0.0)

    if not monthly_expenses or not current_savings:
        return CallToolResult(
            content=[TextContent(
                type="text",
                text="Error: monthly_expenses and current_savings are required"
            )]
        )

    import sys
    sys.path.insert(0, str(FGIP_ROOT))

    try:
        from fgip.analysis.purchasing_power import (
            PurchasingPowerAnalyzer,
            PersonalScenario,
        )

        # Build scenario
        scenario = PersonalScenario(
            monthly_expenses=float(monthly_expenses),
            current_savings=float(current_savings),
            savings_yield=float(savings_yield),
            debt_balance=float(debt_balance),
            debt_apr=float(debt_apr),
            income_monthly=float(income_monthly),
        )

        # Run analysis
        analyzer = PurchasingPowerAnalyzer(str(DB_PATH))
        report = analyzer.analyze(scenario)

        return CallToolResult(
            content=[TextContent(type="text", text=report.to_json(indent=2))]
        )
    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {str(e)}")]
        )


async def get_allocation_candidates(args: dict) -> CallToolResult:
    """
    Get allocation candidates from FGIP graph for Echo Hedge integration.

    Returns reshoring beneficiaries (CHIPS Act), gold proxy, T-Bills,
    and optionally mining assets - each with graph metadata.
    """
    include_mining = args.get("include_mining", False)
    base_expected_return = args.get("base_expected_return", 0.10)

    import sys
    sys.path.insert(0, str(FGIP_ROOT))

    try:
        from fgip.analysis.purchasing_power import PurchasingPowerAnalyzer

        analyzer = PurchasingPowerAnalyzer(str(DB_PATH))
        conn = get_db_connection()

        candidates = []

        # 1. Reshoring beneficiaries from graph
        reshoring = analyzer.get_reshoring_beneficiaries(
            base_expected_return=base_expected_return
        )
        for r in reshoring:
            # Use the real node_id from the graph query (no string munging)
            node_id = r.node_id
            edge_info = conn.execute("""
                SELECT
                    COUNT(*) as edge_count,
                    MAX(confidence) as max_confidence,
                    GROUP_CONCAT(DISTINCT assertion_level) as tiers
                FROM edges
                WHERE from_node_id = ? OR to_node_id = ?
            """, (node_id, node_id)).fetchone()

            candidates.append({
                "candidate_id": node_id,
                "name": r.name,
                "category": "reshoring",
                "expected_nominal_return": r.expected_nominal_return,
                "expected_return_is_assumption": r.expected_return_is_assumption,
                "volatility_note": r.volatility_note,
                "liquidity_note": r.liquidity_note,
                "graph_metadata": {
                    "edge_count": edge_info["edge_count"] or 0,
                    "max_confidence": edge_info["max_confidence"] or 0.5,
                    "tiers": (edge_info["tiers"] or "").split(","),
                },
            })

        # 2. Gold proxy
        gold = analyzer.get_gold_assumption()
        candidates.append({
            "candidate_id": gold.node_id,
            "name": gold.name,
            "category": "commodity",
            "expected_nominal_return": gold.expected_nominal_return,
            "expected_return_is_assumption": gold.expected_return_is_assumption,
            "volatility_note": gold.volatility_note,
            "liquidity_note": gold.liquidity_note,
            "graph_metadata": {
                "edge_count": 0,  # Not in graph
                "max_confidence": 0.80,  # M2 correlation is proven
                "tiers": ["EXTERNAL"],
            },
        })

        # 3. T-Bills
        tbill = analyzer.get_tbill_assumption()
        candidates.append({
            "candidate_id": tbill.node_id,
            "name": tbill.name,
            "category": "fixed_income",
            "expected_nominal_return": tbill.expected_nominal_return,
            "expected_return_is_assumption": tbill.expected_return_is_assumption,
            "volatility_note": tbill.volatility_note,
            "liquidity_note": tbill.liquidity_note,
            "graph_metadata": {
                "edge_count": 0,
                "max_confidence": 0.95,  # Treasury is Tier-0
                "tiers": ["TIER_0"],
            },
        })

        # 4. Mining assets (if requested)
        if include_mining:
            mining_sql = """
                SELECT
                    n.node_id,
                    n.name,
                    n.node_type,
                    COUNT(DISTINCT e.edge_id) as edge_count,
                    MAX(e.confidence) as max_confidence,
                    GROUP_CONCAT(DISTINCT e.assertion_level) as tiers,
                    GROUP_CONCAT(DISTINCT e.edge_type) as edge_types
                FROM nodes n
                LEFT JOIN edges e ON n.node_id = e.from_node_id OR n.node_id = e.to_node_id
                WHERE n.node_type IN ('MINING_POOL', 'ASSET')
                GROUP BY n.node_id, n.name, n.node_type
            """
            rows = conn.execute(mining_sql).fetchall()

            for row in rows:
                # Mining has higher volatility, expected returns vary
                if row["node_type"] == "MINING_POOL":
                    expected_return = 0.15  # Higher risk/return
                    volatility = "Very High"
                else:  # ASSET (crypto)
                    expected_return = 0.12
                    volatility = "High"

                candidates.append({
                    "candidate_id": row["node_id"],
                    "name": row["name"],
                    "category": "mining" if row["node_type"] == "MINING_POOL" else "crypto",
                    "expected_nominal_return": expected_return,
                    "volatility_note": volatility,
                    "liquidity_note": "Variable",
                    "graph_metadata": {
                        "edge_count": row["edge_count"] or 0,
                        "max_confidence": row["max_confidence"] or 0.5,
                        "tiers": (row["tiers"] or "").split(",") if row["tiers"] else [],
                        "edge_types": (row["edge_types"] or "").split(",") if row["edge_types"] else [],
                    },
                })

        conn.close()

        result = {
            "timestamp": datetime.now().isoformat(),
            "candidate_count": len(candidates),
            "categories": list(set(c["category"] for c in candidates)),
            "candidates": candidates,
            "warning": "Expected returns are assumptions derived from graph confidence, not predictions. Use for position sizing context only.",
        }

        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(result, indent=2))]
        )
    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {str(e)}")]
        )


async def get_candidate_risk_context(args: dict) -> CallToolResult:
    """
    Get risk context for allocation candidates from FGIP graph neighborhoods.

    Returns tier distribution, both-sides motif hits, anomaly score,
    and edge breakdown for each candidate.
    """
    candidate_ids = args.get("candidate_ids", [])

    if not candidate_ids:
        return CallToolResult(
            content=[TextContent(type="text", text="Error: candidate_ids required")]
        )

    conn = get_db_connection()

    try:
        results = {}

        for cid in candidate_ids:
            # Find matching node
            node = conn.execute(
                "SELECT * FROM nodes WHERE node_id = ? OR node_id LIKE ?",
                (cid, f"%{cid}%")
            ).fetchone()

            if not node:
                results[cid] = {"error": "Node not found", "candidate_id": cid}
                continue

            node_id = node["node_id"]

            # Get all edges for this node
            edges = conn.execute("""
                SELECT
                    edge_type,
                    assertion_level,
                    confidence,
                    from_node_id,
                    to_node_id
                FROM edges
                WHERE from_node_id = ? OR to_node_id = ?
            """, (node_id, node_id)).fetchall()

            # Tier distribution
            tier_counts = {}
            for e in edges:
                tier = e["assertion_level"] or "UNKNOWN"
                tier_counts[tier] = tier_counts.get(tier, 0) + 1

            # Edge type breakdown
            edge_type_counts = {}
            problem_edges = 0
            correction_edges = 0

            problem_types = {"LOBBIED_FOR", "DONATED_TO", "FUNDED_BY", "OWNS",
                           "HAS_LEVERAGE_OVER", "INCREASES_RISK_FOR"}
            correction_types = {"AWARDED_GRANT", "BUILT_IN", "FUNDED_PROJECT",
                               "ENABLES", "REDUCES", "DECREASES_RISK_FOR"}

            for e in edges:
                etype = e["edge_type"]
                edge_type_counts[etype] = edge_type_counts.get(etype, 0) + 1
                if etype in problem_types:
                    problem_edges += 1
                if etype in correction_types:
                    correction_edges += 1

            # Both-sides motif detection
            both_sides_hit = problem_edges > 0 and correction_edges > 0

            # Confidence stats
            confidences = [e["confidence"] for e in edges if e["confidence"]]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5
            min_confidence = min(confidences) if confidences else 0.0

            # Anomaly score: high if unusual edge patterns
            # Low tier distribution + low confidence = higher anomaly
            tier_0_1_ratio = (tier_counts.get("FACT", 0) + tier_counts.get("TIER_0", 0) +
                             tier_counts.get("TIER_1", 0)) / max(len(edges), 1)
            anomaly_score = 1.0 - (tier_0_1_ratio * avg_confidence)

            results[cid] = {
                "candidate_id": cid,
                "node_id": node_id,
                "name": node["name"],
                "node_type": node["node_type"],
                "total_edges": len(edges),
                "tier_distribution": tier_counts,
                "edge_type_breakdown": edge_type_counts,
                "problem_edges": problem_edges,
                "correction_edges": correction_edges,
                "both_sides_motif": both_sides_hit,
                "confidence_stats": {
                    "average": round(avg_confidence, 3),
                    "minimum": round(min_confidence, 3),
                    "edge_count_with_confidence": len(confidences),
                },
                "anomaly_score": round(anomaly_score, 3),
                "risk_level": (
                    "LOW" if anomaly_score < 0.3 else
                    "MODERATE" if anomaly_score < 0.6 else
                    "HIGH"
                ),
            }

        conn.close()

        output = {
            "timestamp": datetime.now().isoformat(),
            "candidates_analyzed": len(results),
            "risk_contexts": results,
            "interpretation": {
                "tier_distribution": "Higher TIER_0/TIER_1/FACT = better evidence backing",
                "both_sides_motif": "True = entity appears on problem AND correction sides (hedge potential)",
                "anomaly_score": "Higher = less evidence backing, more uncertainty",
                "risk_level": "LOW (<0.3), MODERATE (0.3-0.6), HIGH (>0.6)",
            },
        }

        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(output, indent=2))]
        )
    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {str(e)}")]
        )


async def ingest_youtube_history(args: dict) -> CallToolResult:
    """
    Ingest YouTube watch history and build signal layer.

    Parses Google Takeout watch-history.html, extracts guests/channels/topics,
    and cross-references against FGIP graph.
    """
    html_path = args.get("html_path", "")

    if not html_path:
        return CallToolResult(
            content=[TextContent(type="text", text="Error: html_path is required")]
        )

    import sys
    sys.path.insert(0, str(FGIP_ROOT))

    try:
        from fgip.agents.youtube_signal import YouTubeSignalAnalyzer
        from pathlib import Path

        # Resolve path
        path = Path(html_path)
        if not path.is_absolute():
            path = FGIP_ROOT / path

        if not path.exists():
            return CallToolResult(
                content=[TextContent(type="text", text=f"Error: File not found: {path}")]
            )

        analyzer = YouTubeSignalAnalyzer(db_path=str(DB_PATH))
        report = analyzer.ingest_history(str(path))

        # Build summary output
        output = {
            "timestamp": report.timestamp,
            "total_videos": report.total_videos,
            "unique_channels": report.unique_channels,
            "extracted_guests": len(report.extracted_guests),
            "fgip_matches": len(report.fgip_matches),
            "top_fgip_matches": [
                {
                    "node_id": m["node_id"],
                    "node_name": m["node_name"],
                    "video_count": m["video_count"],
                    "match_type": m["match_type"],
                }
                for m in report.fgip_matches[:20]
            ],
            "top_channels": [
                {
                    "channel": p.channel_name,
                    "videos": p.video_count,
                    "fgip_relevance": p.fgip_relevance_score,
                    "topics": p.topics[:3],
                }
                for p in report.channel_profiles[:15]
            ],
            "topic_distribution": report.topic_distribution,
        }

        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(output, indent=2))]
        )
    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {str(e)}")]
        )


async def get_system_briefing(args: dict) -> CallToolResult:
    """
    Get system intelligence briefing for Claude Code.

    Returns pending approvals, parser gaps, API health, and work orders
    that tell you what the system needs built.
    """
    include_work_orders = args.get("include_work_orders", True)
    include_health = args.get("include_health", True)

    import sys
    sys.path.insert(0, str(FGIP_ROOT))

    try:
        from fgip.agents.system_intelligence import SystemIntelligenceAgent
        from fgip.db import FGIPDatabase

        db = FGIPDatabase(str(DB_PATH))
        agent = SystemIntelligenceAgent(db)

        briefing = agent.get_claude_code_briefing(
            include_work_orders=include_work_orders,
            include_health=include_health
        )

        return CallToolResult(
            content=[TextContent(type="text", text=briefing)]
        )
    except ImportError as e:
        # Fall back to basic briefing if agent not fully implemented
        conn = get_db_connection()
        try:
            # Basic system check
            pending_proposals = conn.execute(
                "SELECT COUNT(*) FROM edges WHERE assertion_level = 'PROPOSED'"
            ).fetchone()[0]

            total_nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            total_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]

            # Check for orphan nodes (no edges)
            orphan_nodes = conn.execute("""
                SELECT COUNT(*) FROM nodes n
                WHERE NOT EXISTS (SELECT 1 FROM edges e WHERE e.from_node_id = n.node_id)
                AND NOT EXISTS (SELECT 1 FROM edges e WHERE e.to_node_id = n.node_id)
            """).fetchone()[0]

            briefing = {
                "timestamp": datetime.now().isoformat(),
                "system_status": "BASIC_MODE",
                "note": f"SystemIntelligenceAgent import failed: {e}",
                "basic_metrics": {
                    "total_nodes": total_nodes,
                    "total_edges": total_edges,
                    "pending_proposals": pending_proposals,
                    "orphan_nodes": orphan_nodes,
                },
                "bottlenecks": [
                    {
                        "type": "PENDING_APPROVAL",
                        "count": pending_proposals,
                        "action": "Run approval workflow to promote PROPOSED → VERIFIED"
                    },
                    {
                        "type": "ORPHAN_NODES",
                        "count": orphan_nodes,
                        "action": "Review orphan nodes - may need edges or deletion"
                    }
                ],
                "work_orders": [
                    {
                        "priority": "HIGH",
                        "task": "Implement approval UI in web dashboard",
                        "reason": f"{pending_proposals} proposals awaiting human review"
                    },
                    {
                        "priority": "MEDIUM",
                        "task": "Add parser for missing data sources",
                        "reason": "Expand coverage of government data feeds"
                    }
                ]
            }

            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(briefing, indent=2))]
            )
        finally:
            conn.close()
    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {str(e)}")]
        )


# ============================================================================
# MAIN
# ============================================================================

async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
