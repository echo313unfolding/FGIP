#!/usr/bin/env python3
"""FGIP MCP Server (HTTP/SSE) - For claude.ai and remote clients.

Run with:
    python3 mcp_server_http.py [--port 8080]

Then connect claude.ai to:
    http://your-ip:8080/sse
"""

import asyncio
import json
import sqlite3
import argparse
from pathlib import Path
from typing import Any
from datetime import datetime

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse
import uvicorn

# FGIP paths
FGIP_ROOT = Path(__file__).parent
DB_PATH = FGIP_ROOT / "fgip.db"

# Import tool definitions from stdio server
from mcp_server import server, list_tools, call_tool

# Create SSE transport
sse = SseServerTransport("/messages")


async def handle_sse(request):
    """Handle SSE connection from claude.ai"""
    async with sse.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await server.run(
            streams[0], streams[1], server.create_initialization_options()
        )


async def handle_messages(request):
    """Handle POST messages from SSE clients"""
    await sse.handle_post_message(request.scope, request.receive, request._send)


async def health(request):
    """Health check endpoint"""
    return JSONResponse({
        "status": "ok",
        "server": "fgip-mcp",
        "transport": "sse",
        "tools": 16  # Updated: added get_system_briefing
    })


# Starlette app
app = Starlette(
    debug=True,
    routes=[
        Route("/health", health),
        Route("/sse", handle_sse),
        Route("/messages", handle_messages, methods=["POST"]),
    ],
)


def main():
    parser = argparse.ArgumentParser(description="FGIP MCP Server (HTTP/SSE)")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    args = parser.parse_args()

    print(f"Starting FGIP MCP Server (HTTP/SSE)")
    print(f"  Health: http://{args.host}:{args.port}/health")
    print(f"  SSE:    http://{args.host}:{args.port}/sse")
    print(f"  Messages: http://{args.host}:{args.port}/messages")
    print(f"\nFor claude.ai, use: http://YOUR_PUBLIC_IP:{args.port}/sse")

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
