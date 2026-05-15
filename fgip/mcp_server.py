#!/usr/bin/env python3
"""FGIP Evidence Graph MCP Server.

Exposes the FGIP SQLite knowledge graph (2073 nodes, 2753 edges, 32901 claims,
5435 sources) as MCP tools for Claude agents.

Runs as stdio MCP server. Read-only — no graph mutations through MCP.
Mutations go through the proposal pipeline (proposed_claims, proposed_edges).

Usage:
    # Direct
    python3 fgip/mcp_server.py

    # Register with Claude Code
    claude mcp add --scope user fgip_graph python3 /home/voidstr3m33/fgip-engine/fgip/mcp_server.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

# MCP SDK
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("MCP SDK not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)

DB_PATH = os.environ.get("FGIP_DB", str(Path(__file__).parent.parent / "fgip.db"))

server = Server("fgip-graph")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def row_to_dict(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in row.keys()}


def rows_to_list(rows: list[sqlite3.Row]) -> list[dict]:
    return [row_to_dict(r) for r in rows]


# ============================================================
# Tool definitions
# ============================================================

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="query_node",
            description=(
                "Look up an entity in the FGIP graph by name, node_id, or alias. "
                "Returns node properties and all connected edges (1-hop). "
                "Use for: entity profiles, ownership lookup, connection mapping."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Entity name, node_id, or alias to search for",
                    },
                    "node_type": {
                        "type": "string",
                        "description": "Optional: filter by node type (COMPANY, PERSON, AGENCY, LEGISLATION, etc.)",
                    },
                    "include_edges": {
                        "type": "boolean",
                        "description": "Include connected edges (default true)",
                        "default": True,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 10)",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="query_edges",
            description=(
                "Find edges (relationships) in the FGIP graph. Filter by type, "
                "source node, target node, or confidence. Returns edge properties "
                "with source tier and claim backing. "
                "Use for: ownership chains, appointment paths, funding flows."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "edge_type": {
                        "type": "string",
                        "description": "Edge type filter (OWNS, APPOINTED_BY, FUNDED_BY, REGULATES, VOTED_FOR, etc.)",
                    },
                    "from_node": {
                        "type": "string",
                        "description": "Source node name or ID",
                    },
                    "to_node": {
                        "type": "string",
                        "description": "Target node name or ID",
                    },
                    "min_confidence": {
                        "type": "number",
                        "description": "Minimum confidence threshold (0.0-1.0)",
                        "default": 0.0,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 50)",
                        "default": 50,
                    },
                },
            },
        ),
        Tool(
            name="search_claims",
            description=(
                "Full-text search across all 32K+ claims in the FGIP graph. "
                "Returns claim text, topic, status (VERIFIED/EVIDENCED/PARTIAL/MISSING), "
                "and linked sources with tier scores. "
                "Use for: claim verification, finding evidence for/against a thesis."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search text (FTS5 syntax: AND/OR/NOT/phrases supported)",
                    },
                    "status": {
                        "type": "string",
                        "description": "Filter by claim status: VERIFIED, EVIDENCED, PARTIAL, MISSING",
                    },
                    "topic": {
                        "type": "string",
                        "description": "Filter by topic",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 20)",
                        "default": 20,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="search_nodes",
            description=(
                "Full-text search across all nodes (entities) in the FGIP graph. "
                "Searches name and description fields. "
                "Use for: finding entities by keyword when you don't know the exact name."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search text (FTS5 syntax supported)",
                    },
                    "node_type": {
                        "type": "string",
                        "description": "Optional: filter by node type",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 20)",
                        "default": 20,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_neighbors",
            description=(
                "Get all nodes connected to a given node (2-hop neighborhood). "
                "Returns incoming and outgoing edges with their target/source nodes. "
                "Use for: mapping an entity's full network, finding both-sides patterns."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "node_id": {
                        "type": "string",
                        "description": "Node ID to get neighbors for",
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["both", "outgoing", "incoming"],
                        "description": "Edge direction (default: both)",
                        "default": "both",
                    },
                    "edge_type": {
                        "type": "string",
                        "description": "Optional: filter by edge type",
                    },
                    "hops": {
                        "type": "integer",
                        "description": "Number of hops (1 or 2, default 1)",
                        "default": 1,
                        "minimum": 1,
                        "maximum": 2,
                    },
                },
                "required": ["node_id"],
            },
        ),
        Tool(
            name="pattern_match",
            description=(
                "Find structural patterns in the graph: both-sides ownership, "
                "revolving door, regulatory capture, funding loops. "
                "Use for: detecting entities positioned on multiple sides of a policy."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "enum": [
                            "both_sides",
                            "revolving_door",
                            "regulatory_capture",
                            "funding_loop",
                        ],
                        "description": "Pattern type to search for",
                    },
                    "entity": {
                        "type": "string",
                        "description": "Optional: center the pattern search on this entity",
                    },
                    "min_confidence": {
                        "type": "number",
                        "description": "Minimum edge confidence (default 0.5)",
                        "default": 0.5,
                    },
                },
                "required": ["pattern"],
            },
        ),
        Tool(
            name="path_between",
            description=(
                "Find all shortest paths between two nodes in the FGIP graph (BFS). "
                "Returns paths as sequences of nodes and edges with confidence scores. "
                "Use for: tracing causal chains, finding how two entities connect, "
                "discovering indirect relationships up to N hops."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "start": {
                        "type": "string",
                        "description": "Start node ID or name",
                    },
                    "end": {
                        "type": "string",
                        "description": "End node ID or name",
                    },
                    "max_hops": {
                        "type": "integer",
                        "description": "Maximum path length (default 3, max 5)",
                        "default": 3,
                        "minimum": 1,
                        "maximum": 5,
                    },
                    "min_confidence": {
                        "type": "number",
                        "description": "Minimum edge confidence to traverse (default 0.0)",
                        "default": 0.0,
                    },
                    "directed": {
                        "type": "boolean",
                        "description": "Only follow edges in their natural direction (default false)",
                        "default": False,
                    },
                },
                "required": ["start", "end"],
            },
        ),
        Tool(
            name="graph_stats",
            description=(
                "Get summary statistics for the FGIP evidence graph: "
                "node/edge/claim/source counts, type distributions, "
                "evidence coverage, tier-0/1 scores."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="get_sources",
            description=(
                "Get sources backing a claim or edge. Returns URL, domain, tier, "
                "artifact path, and retrieval date. "
                "Use for: verifying source quality, checking tier-0/1 backing."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "claim_id": {
                        "type": "string",
                        "description": "Claim ID to get sources for",
                    },
                    "tier": {
                        "type": "integer",
                        "description": "Optional: filter by source tier (0-3)",
                        "minimum": 0,
                        "maximum": 3,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 20)",
                        "default": 20,
                    },
                },
            },
        ),
    ]


# ============================================================
# Tool implementations
# ============================================================

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    db = get_db()
    try:
        if name == "query_node":
            result = _query_node(db, arguments)
        elif name == "query_edges":
            result = _query_edges(db, arguments)
        elif name == "search_claims":
            result = _search_claims(db, arguments)
        elif name == "search_nodes":
            result = _search_nodes(db, arguments)
        elif name == "get_neighbors":
            result = _get_neighbors(db, arguments)
        elif name == "path_between":
            result = _path_between(db, arguments)
        elif name == "pattern_match":
            result = _pattern_match(db, arguments)
        elif name == "graph_stats":
            result = _graph_stats(db)
        elif name == "get_sources":
            result = _get_sources(db, arguments)
        else:
            result = {"error": f"Unknown tool: {name}"}
    finally:
        db.close()

    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


def _resolve_node_id(db: sqlite3.Connection, query: str) -> list[str]:
    """Resolve a query string to node IDs. Tries exact ID, exact name, alias, then FTS."""
    # Exact node_id match
    row = db.execute("SELECT node_id FROM nodes WHERE node_id = ?", (query,)).fetchone()
    if row:
        return [row["node_id"]]

    # Exact name match (case-insensitive)
    rows = db.execute(
        "SELECT node_id FROM nodes WHERE LOWER(name) = LOWER(?)", (query,)
    ).fetchall()
    if rows:
        return [r["node_id"] for r in rows]

    # Alias match
    rows = db.execute(
        "SELECT node_id, aliases FROM nodes WHERE aliases IS NOT NULL"
    ).fetchall()
    matches = []
    q_lower = query.lower()
    for r in rows:
        try:
            aliases = json.loads(r["aliases"]) if r["aliases"] else []
            if any(q_lower in a.lower() for a in aliases):
                matches.append(r["node_id"])
        except (json.JSONDecodeError, TypeError):
            pass
    if matches:
        return matches[:10]

    # FTS fallback
    try:
        rows = db.execute(
            "SELECT node_id FROM nodes_fts WHERE nodes_fts MATCH ? LIMIT 10",
            (query,)
        ).fetchall()
        return [r["node_id"] for r in rows]
    except sqlite3.OperationalError:
        # FTS query syntax error — try prefix match
        rows = db.execute(
            "SELECT node_id FROM nodes WHERE LOWER(name) LIKE LOWER(?) LIMIT 10",
            (f"%{query}%",)
        ).fetchall()
        return [r["node_id"] for r in rows]


def _query_node(db: sqlite3.Connection, args: dict) -> dict:
    query = args["query"]
    node_type = args.get("node_type")
    include_edges = args.get("include_edges", True)
    limit = min(args.get("limit", 10), 50)

    node_ids = _resolve_node_id(db, query)
    if node_type:
        node_ids_filtered = []
        for nid in node_ids:
            row = db.execute(
                "SELECT node_type FROM nodes WHERE node_id = ?", (nid,)
            ).fetchone()
            if row and row["node_type"].upper() == node_type.upper():
                node_ids_filtered.append(nid)
        node_ids = node_ids_filtered

    if not node_ids:
        return {"matches": [], "count": 0, "query": query, "message": "No nodes found"}

    results = []
    for nid in node_ids[:limit]:
        row = db.execute("SELECT * FROM nodes WHERE node_id = ?", (nid,)).fetchone()
        if not row:
            continue
        node = row_to_dict(row)
        try:
            node["aliases"] = json.loads(node["aliases"]) if node["aliases"] else []
        except (json.JSONDecodeError, TypeError):
            node["aliases"] = []
        try:
            node["metadata"] = json.loads(node["metadata"]) if node["metadata"] else {}
        except (json.JSONDecodeError, TypeError):
            node["metadata"] = {}

        if include_edges:
            out_edges = db.execute(
                """SELECT e.edge_id, e.edge_type, e.to_node_id, n.name as to_name,
                          e.confidence, e.assertion_level, e.claim_id
                   FROM edges e JOIN nodes n ON e.to_node_id = n.node_id
                   WHERE e.from_node_id = ? LIMIT 100""",
                (nid,)
            ).fetchall()
            in_edges = db.execute(
                """SELECT e.edge_id, e.edge_type, e.from_node_id, n.name as from_name,
                          e.confidence, e.assertion_level, e.claim_id
                   FROM edges e JOIN nodes n ON e.from_node_id = n.node_id
                   WHERE e.to_node_id = ? LIMIT 100""",
                (nid,)
            ).fetchall()
            node["outgoing_edges"] = rows_to_list(out_edges)
            node["incoming_edges"] = rows_to_list(in_edges)

        results.append(node)

    return {"matches": results, "count": len(results), "query": query}


def _query_edges(db: sqlite3.Connection, args: dict) -> dict:
    edge_type = args.get("edge_type")
    from_node = args.get("from_node")
    to_node = args.get("to_node")
    min_confidence = args.get("min_confidence", 0.0)
    limit = min(args.get("limit", 50), 200)

    query = """
        SELECT e.*, fn.name as from_name, tn.name as to_name
        FROM edges e
        JOIN nodes fn ON e.from_node_id = fn.node_id
        JOIN nodes tn ON e.to_node_id = tn.node_id
        WHERE e.confidence >= ?
    """
    params: list = [min_confidence]

    if edge_type:
        query += " AND UPPER(e.edge_type) = UPPER(?)"
        params.append(edge_type)

    if from_node:
        from_ids = _resolve_node_id(db, from_node)
        if from_ids:
            placeholders = ",".join("?" for _ in from_ids)
            query += f" AND e.from_node_id IN ({placeholders})"
            params.extend(from_ids)
        else:
            return {"edges": [], "message": f"No node found for '{from_node}'"}

    if to_node:
        to_ids = _resolve_node_id(db, to_node)
        if to_ids:
            placeholders = ",".join("?" for _ in to_ids)
            query += f" AND e.to_node_id IN ({placeholders})"
            params.extend(to_ids)
        else:
            return {"edges": [], "message": f"No node found for '{to_node}'"}

    query += " ORDER BY e.confidence DESC LIMIT ?"
    params.append(limit)

    rows = db.execute(query, params).fetchall()
    return {"edges": rows_to_list(rows), "count": len(rows)}


def _search_claims(db: sqlite3.Connection, args: dict) -> dict:
    query = args["query"]
    status = args.get("status")
    topic = args.get("topic")
    limit = min(args.get("limit", 20), 100)

    try:
        sql = """
            SELECT c.* FROM claims c
            JOIN claims_fts fts ON c.claim_id = fts.claim_id
            WHERE claims_fts MATCH ?
        """
        params: list = [query]

        if status:
            sql += " AND c.status = ?"
            params.append(status)
        if topic:
            sql += " AND c.topic = ?"
            params.append(topic)

        sql += " LIMIT ?"
        params.append(limit)

        rows = db.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        # FTS syntax error — fall back to LIKE
        sql = "SELECT * FROM claims WHERE claim_text LIKE ? "
        params = [f"%{query}%"]
        if status:
            sql += " AND status = ?"
            params.append(status)
        if topic:
            sql += " AND topic = ?"
            params.append(topic)
        sql += " LIMIT ?"
        params.append(limit)
        rows = db.execute(sql, params).fetchall()

    results = []
    for row in rows:
        claim = row_to_dict(row)
        # Get sources for this claim
        sources = db.execute(
            """SELECT s.source_id, s.url, s.domain, s.tier
               FROM sources s
               JOIN claim_sources cs ON s.source_id = cs.source_id
               WHERE cs.claim_id = ?""",
            (claim["claim_id"],)
        ).fetchall()
        claim["sources"] = rows_to_list(sources)
        claim["max_source_tier"] = min((s["tier"] for s in claim["sources"]), default=None)
        results.append(claim)

    return {"claims": results, "count": len(results), "query": query}


def _search_nodes(db: sqlite3.Connection, args: dict) -> dict:
    query = args["query"]
    node_type = args.get("node_type")
    limit = min(args.get("limit", 20), 100)

    try:
        sql = """
            SELECT n.* FROM nodes n
            JOIN nodes_fts fts ON n.node_id = fts.node_id
            WHERE nodes_fts MATCH ?
        """
        params: list = [query]
        if node_type:
            sql += " AND UPPER(n.node_type) = UPPER(?)"
            params.append(node_type)
        sql += " LIMIT ?"
        params.append(limit)
        rows = db.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        sql = "SELECT * FROM nodes WHERE LOWER(name) LIKE LOWER(?)"
        params = [f"%{query}%"]
        if node_type:
            sql += " AND UPPER(node_type) = UPPER(?)"
            params.append(node_type)
        sql += " LIMIT ?"
        params.append(limit)
        rows = db.execute(sql, params).fetchall()

    results = []
    for row in rows:
        node = row_to_dict(row)
        try:
            node["aliases"] = json.loads(node["aliases"]) if node["aliases"] else []
        except (json.JSONDecodeError, TypeError):
            node["aliases"] = []
        results.append(node)

    return {"nodes": results, "count": len(results), "query": query}


def _get_neighbors(db: sqlite3.Connection, args: dict) -> dict:
    node_id = args["node_id"]
    direction = args.get("direction", "both")
    edge_type = args.get("edge_type")
    hops = min(args.get("hops", 1), 2)

    # Verify node exists
    node = db.execute("SELECT * FROM nodes WHERE node_id = ?", (node_id,)).fetchone()
    if not node:
        # Try resolving by name
        ids = _resolve_node_id(db, node_id)
        if ids:
            node_id = ids[0]
            node = db.execute("SELECT * FROM nodes WHERE node_id = ?", (node_id,)).fetchone()
        if not node:
            return {"error": f"Node not found: {node_id}"}

    neighbors = []
    visited = {node_id}

    def _fetch_hop(current_ids: list[str]) -> list[str]:
        next_ids = []
        for nid in current_ids:
            if direction in ("outgoing", "both"):
                sql = """
                    SELECT e.edge_id, e.edge_type, e.confidence, e.assertion_level,
                           e.to_node_id, n.name as neighbor_name, n.node_type as neighbor_type
                    FROM edges e JOIN nodes n ON e.to_node_id = n.node_id
                    WHERE e.from_node_id = ?
                """
                params: list = [nid]
                if edge_type:
                    sql += " AND UPPER(e.edge_type) = UPPER(?)"
                    params.append(edge_type)
                rows = db.execute(sql, params).fetchall()
                for r in rows:
                    neighbors.append({
                        "direction": "outgoing",
                        "edge_id": r["edge_id"],
                        "edge_type": r["edge_type"],
                        "confidence": r["confidence"],
                        "from_node_id": nid,
                        "to_node_id": r["to_node_id"],
                        "neighbor_name": r["neighbor_name"],
                        "neighbor_type": r["neighbor_type"],
                    })
                    if r["to_node_id"] not in visited:
                        visited.add(r["to_node_id"])
                        next_ids.append(r["to_node_id"])

            if direction in ("incoming", "both"):
                sql = """
                    SELECT e.edge_id, e.edge_type, e.confidence, e.assertion_level,
                           e.from_node_id, n.name as neighbor_name, n.node_type as neighbor_type
                    FROM edges e JOIN nodes n ON e.from_node_id = n.node_id
                    WHERE e.to_node_id = ?
                """
                params = [nid]
                if edge_type:
                    sql += " AND UPPER(e.edge_type) = UPPER(?)"
                    params.append(edge_type)
                rows = db.execute(sql, params).fetchall()
                for r in rows:
                    neighbors.append({
                        "direction": "incoming",
                        "edge_id": r["edge_id"],
                        "edge_type": r["edge_type"],
                        "confidence": r["confidence"],
                        "from_node_id": r["from_node_id"],
                        "to_node_id": nid,
                        "neighbor_name": r["neighbor_name"],
                        "neighbor_type": r["neighbor_type"],
                    })
                    if r["from_node_id"] not in visited:
                        visited.add(r["from_node_id"])
                        next_ids.append(r["from_node_id"])

        return next_ids

    current = [node_id]
    for hop in range(hops):
        current = _fetch_hop(current)
        if not current:
            break

    return {
        "center": row_to_dict(node),
        "neighbors": neighbors,
        "count": len(neighbors),
        "hops": hops,
    }


def _path_between(db: sqlite3.Connection, args: dict) -> dict:
    """Find shortest paths between two nodes via BFS."""
    start_query = args["start"]
    end_query = args["end"]
    max_hops = min(args.get("max_hops", 3), 5)
    min_confidence = args.get("min_confidence", 0.0)
    directed = args.get("directed", False)

    # Resolve node IDs
    start_ids = _resolve_node_id(db, start_query)
    end_ids = _resolve_node_id(db, end_query)

    if not start_ids:
        return {"error": f"Start node not found: {start_query}", "paths": [], "count": 0}
    if not end_ids:
        return {"error": f"End node not found: {end_query}", "paths": [], "count": 0}

    start_id = start_ids[0]
    end_id = end_ids[0]

    if start_id == end_id:
        return {"error": "Start and end are the same node", "paths": [], "count": 0}

    # BFS with path tracking
    from collections import deque
    queue = deque()

    start_name = db.execute(
        "SELECT name FROM nodes WHERE node_id = ?", (start_id,)
    ).fetchone()
    end_name = db.execute(
        "SELECT name FROM nodes WHERE node_id = ?", (end_id,)
    ).fetchone()

    queue.append((start_id, [{"node_id": start_id,
                               "node_name": start_name["name"] if start_name else start_id,
                               "edge_id": None, "edge_type": None,
                               "confidence": None, "direction": "start"}]))
    visited = {start_id}
    found_paths = []
    found_depth = None

    while queue:
        current_id, path = queue.popleft()

        if found_depth is not None and len(path) > found_depth:
            break
        if len(path) > max_hops + 1:
            break

        neighbors = []

        # Outgoing
        rows = db.execute(
            """SELECT e.edge_id, e.edge_type, e.to_node_id, e.confidence,
                      e.claim_id, n.name as neighbor_name
               FROM edges e JOIN nodes n ON e.to_node_id = n.node_id
               WHERE e.from_node_id = ? AND e.confidence >= ?""",
            (current_id, min_confidence)
        ).fetchall()
        for r in rows:
            neighbors.append((r["to_node_id"], r["neighbor_name"],
                               r["edge_id"], r["edge_type"],
                               r["confidence"], r["claim_id"], "outgoing"))

        # Incoming (unless directed)
        if not directed:
            rows = db.execute(
                """SELECT e.edge_id, e.edge_type, e.from_node_id, e.confidence,
                          e.claim_id, n.name as neighbor_name
                   FROM edges e JOIN nodes n ON e.from_node_id = n.node_id
                   WHERE e.to_node_id = ? AND e.confidence >= ?""",
                (current_id, min_confidence)
            ).fetchall()
            for r in rows:
                neighbors.append((r["from_node_id"], r["neighbor_name"],
                                   r["edge_id"], r["edge_type"],
                                   r["confidence"], r["claim_id"], "incoming"))

        for nid, nname, eid, etype, conf, claim_id, direction in neighbors:
            step = {"node_id": nid, "node_name": nname,
                    "edge_id": eid, "edge_type": etype,
                    "confidence": conf, "claim_id": claim_id,
                    "direction": direction}

            if nid == end_id:
                found_paths.append(path + [step])
                found_depth = len(path) + 1
            elif nid not in visited:
                visited.add(nid)
                queue.append((nid, path + [step]))

    # Compute path-level stats
    formatted_paths = []
    for p in found_paths[:20]:  # Cap at 20 paths
        edges_in_path = [s for s in p if s["edge_id"] is not None]
        confidences = [s["confidence"] for s in edges_in_path if s["confidence"] is not None]
        formatted_paths.append({
            "hops": len(edges_in_path),
            "min_confidence": min(confidences) if confidences else None,
            "avg_confidence": round(sum(confidences) / len(confidences), 3) if confidences else None,
            "steps": p,
        })

    return {
        "start": {"node_id": start_id, "name": start_name["name"] if start_name else start_id},
        "end": {"node_id": end_id, "name": end_name["name"] if end_name else end_id},
        "paths": formatted_paths,
        "count": len(found_paths),
        "max_hops": max_hops,
        "directed": directed,
    }


def _pattern_match(db: sqlite3.Connection, args: dict) -> dict:
    pattern = args["pattern"]
    entity = args.get("entity")
    min_confidence = args.get("min_confidence", 0.5)

    if pattern == "both_sides":
        return _pattern_both_sides(db, entity, min_confidence)
    elif pattern == "revolving_door":
        return _pattern_revolving_door(db, entity, min_confidence)
    elif pattern == "regulatory_capture":
        return _pattern_regulatory_capture(db, entity, min_confidence)
    elif pattern == "funding_loop":
        return _pattern_funding_loop(db, entity, min_confidence)
    else:
        return {"error": f"Unknown pattern: {pattern}"}


def _pattern_both_sides(db: sqlite3.Connection, entity: str | None,
                        min_conf: float) -> dict:
    """Find entities that appear on both sides of a policy/legislation."""
    sql = """
        SELECT DISTINCT
            owner.node_id as owner_id,
            owner.name as owner_name,
            e1.edge_type as own_type1,
            t1.name as target1,
            t1.node_type as target1_type,
            e2.edge_type as own_type2,
            t2.name as target2,
            t2.node_type as target2_type
        FROM edges e1
        JOIN edges e2 ON e1.from_node_id = e2.from_node_id
            AND e1.to_node_id != e2.to_node_id
        JOIN nodes owner ON e1.from_node_id = owner.node_id
        JOIN nodes t1 ON e1.to_node_id = t1.node_id
        JOIN nodes t2 ON e2.to_node_id = t2.node_id
        WHERE e1.edge_type IN ('OWNS', 'OWNS_SHARES', 'INVESTED_IN', 'FUNDED_BY')
        AND e2.edge_type IN ('OWNS', 'OWNS_SHARES', 'INVESTED_IN', 'FUNDED_BY')
        AND e1.confidence >= ?
        AND e2.confidence >= ?
    """
    params: list = [min_conf, min_conf]

    if entity:
        entity_ids = _resolve_node_id(db, entity)
        if entity_ids:
            placeholders = ",".join("?" for _ in entity_ids)
            sql += f" AND owner.node_id IN ({placeholders})"
            params.extend(entity_ids)

    sql += " LIMIT 100"
    rows = db.execute(sql, params).fetchall()
    return {
        "pattern": "both_sides",
        "matches": rows_to_list(rows),
        "count": len(rows),
    }


def _pattern_revolving_door(db: sqlite3.Connection, entity: str | None,
                            min_conf: float) -> dict:
    """Find person→agency→company→person loops (revolving door)."""
    sql = """
        SELECT DISTINCT
            p.name as person,
            a.name as agency,
            c.name as company,
            e1.edge_type as person_agency_rel,
            e2.edge_type as agency_company_rel,
            e3.edge_type as company_person_rel
        FROM edges e1
        JOIN edges e2 ON e1.to_node_id = e2.from_node_id
        JOIN edges e3 ON e2.to_node_id = e3.from_node_id AND e3.to_node_id = e1.from_node_id
        JOIN nodes p ON e1.from_node_id = p.node_id
        JOIN nodes a ON e1.to_node_id = a.node_id
        JOIN nodes c ON e2.to_node_id = c.node_id
        WHERE p.node_type = 'PERSON'
        AND a.node_type IN ('AGENCY', 'GOVERNMENT_AGENCY', 'REGULATOR')
        AND c.node_type = 'COMPANY'
        AND e1.confidence >= ?
        AND e2.confidence >= ?
        AND e3.confidence >= ?
    """
    params: list = [min_conf, min_conf, min_conf]

    if entity:
        entity_ids = _resolve_node_id(db, entity)
        if entity_ids:
            placeholders = ",".join("?" for _ in entity_ids)
            sql += f" AND (p.node_id IN ({placeholders}) OR a.node_id IN ({placeholders}) OR c.node_id IN ({placeholders}))"
            params.extend(entity_ids * 3)

    sql += " LIMIT 50"
    rows = db.execute(sql, params).fetchall()
    return {
        "pattern": "revolving_door",
        "matches": rows_to_list(rows),
        "count": len(rows),
    }


def _pattern_regulatory_capture(db: sqlite3.Connection, entity: str | None,
                                min_conf: float) -> dict:
    """Find agency→REGULATES→company where company→FUNDED_BY/OWNS→same agency or person."""
    sql = """
        SELECT DISTINCT
            reg.name as regulator,
            comp.name as company,
            e1.edge_type as regulates_rel,
            e2.edge_type as influence_rel,
            e2.from_node_id as influencer_id,
            inf.name as influencer_name
        FROM edges e1
        JOIN edges e2 ON e1.to_node_id = e2.from_node_id
        JOIN nodes reg ON e1.from_node_id = reg.node_id
        JOIN nodes comp ON e1.to_node_id = comp.node_id
        JOIN nodes inf ON e2.to_node_id = inf.node_id
        WHERE e1.edge_type IN ('REGULATES', 'OVERSEES', 'SUPERVISES')
        AND e2.edge_type IN ('FUNDED_BY', 'LOBBIES', 'APPOINTED_BY', 'DONATED_TO')
        AND e1.confidence >= ?
        AND e2.confidence >= ?
    """
    params: list = [min_conf, min_conf]

    if entity:
        entity_ids = _resolve_node_id(db, entity)
        if entity_ids:
            placeholders = ",".join("?" for _ in entity_ids)
            sql += f" AND (reg.node_id IN ({placeholders}) OR comp.node_id IN ({placeholders}))"
            params.extend(entity_ids * 2)

    sql += " LIMIT 50"
    rows = db.execute(sql, params).fetchall()
    return {
        "pattern": "regulatory_capture",
        "matches": rows_to_list(rows),
        "count": len(rows),
    }


def _pattern_funding_loop(db: sqlite3.Connection, entity: str | None,
                          min_conf: float) -> dict:
    """Find A→FUNDED_BY→B→FUNDED_BY→C→...→A loops."""
    sql = """
        SELECT DISTINCT
            a.name as entity_a,
            b.name as entity_b,
            c.name as entity_c,
            e1.edge_type as ab_rel,
            e2.edge_type as bc_rel,
            e3.edge_type as ca_rel
        FROM edges e1
        JOIN edges e2 ON e1.to_node_id = e2.from_node_id
        JOIN edges e3 ON e2.to_node_id = e3.from_node_id AND e3.to_node_id = e1.from_node_id
        JOIN nodes a ON e1.from_node_id = a.node_id
        JOIN nodes b ON e1.to_node_id = b.node_id
        JOIN nodes c ON e2.to_node_id = c.node_id
        WHERE e1.edge_type IN ('FUNDED_BY', 'INVESTED_IN', 'AWARDED_GRANT', 'AWARDED_CONTRACT')
        AND e2.edge_type IN ('FUNDED_BY', 'INVESTED_IN', 'AWARDED_GRANT', 'AWARDED_CONTRACT')
        AND e3.edge_type IN ('FUNDED_BY', 'INVESTED_IN', 'AWARDED_GRANT', 'AWARDED_CONTRACT')
        AND e1.confidence >= ?
    """
    params: list = [min_conf]

    if entity:
        entity_ids = _resolve_node_id(db, entity)
        if entity_ids:
            placeholders = ",".join("?" for _ in entity_ids)
            sql += f" AND a.node_id IN ({placeholders})"
            params.extend(entity_ids)

    sql += " LIMIT 50"
    rows = db.execute(sql, params).fetchall()
    return {
        "pattern": "funding_loop",
        "matches": rows_to_list(rows),
        "count": len(rows),
    }


def _graph_stats(db: sqlite3.Connection) -> dict:
    stats = {}
    stats["nodes"] = db.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    stats["edges"] = db.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    stats["claims"] = db.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
    stats["sources"] = db.execute("SELECT COUNT(*) FROM sources").fetchone()[0]

    stats["node_types"] = {
        r[0]: r[1] for r in
        db.execute("SELECT node_type, COUNT(*) FROM nodes GROUP BY node_type ORDER BY COUNT(*) DESC").fetchall()
    }
    stats["edge_types_top20"] = {
        r[0]: r[1] for r in
        db.execute("SELECT edge_type, COUNT(*) FROM edges GROUP BY edge_type ORDER BY COUNT(*) DESC LIMIT 20").fetchall()
    }
    stats["claim_statuses"] = {
        r[0]: r[1] for r in
        db.execute("SELECT status, COUNT(*) FROM claims GROUP BY status").fetchall()
    }
    stats["source_tiers"] = {
        f"tier_{r[0]}": r[1] for r in
        db.execute("SELECT tier, COUNT(*) FROM sources GROUP BY tier ORDER BY tier").fetchall()
    }

    edges_with_claims = db.execute(
        "SELECT COUNT(*) FROM edges WHERE claim_id IS NOT NULL"
    ).fetchone()[0]
    stats["evidence_coverage"] = round(edges_with_claims / max(stats["edges"], 1) * 100, 1)

    tier01 = db.execute(
        """SELECT COUNT(DISTINCT c.claim_id) FROM claims c
           JOIN claim_sources cs ON c.claim_id = cs.claim_id
           JOIN sources s ON cs.source_id = s.source_id
           WHERE s.tier <= 1"""
    ).fetchone()[0]
    stats["tier_01_claims"] = tier01

    return stats


def _get_sources(db: sqlite3.Connection, args: dict) -> dict:
    claim_id = args.get("claim_id")
    tier = args.get("tier")
    limit = min(args.get("limit", 20), 100)

    if claim_id:
        sql = """
            SELECT s.* FROM sources s
            JOIN claim_sources cs ON s.source_id = cs.source_id
            WHERE cs.claim_id = ?
        """
        params: list = [claim_id]
        if tier is not None:
            sql += " AND s.tier = ?"
            params.append(tier)
        sql += " LIMIT ?"
        params.append(limit)
    else:
        sql = "SELECT * FROM sources"
        params = []
        if tier is not None:
            sql += " WHERE tier = ?"
            params.append(tier)
        sql += " ORDER BY tier ASC LIMIT ?"
        params.append(limit)

    rows = db.execute(sql, params).fetchall()
    return {"sources": rows_to_list(rows), "count": len(rows)}


# ============================================================
# Main
# ============================================================

async def main():
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
