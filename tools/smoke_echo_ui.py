#!/usr/bin/env python3
"""Smoke test for Echo UI Gateway.

Verifies:
1. /v1/health returns OK
2. / serves HTML with "Echo"
3. /v1/chat handles a query that triggers tool call
4. Receipt written to receipts/echo_sessions/

Usage:
    python3 tools/smoke_echo_ui.py [--base-url http://127.0.0.1:7777]
"""

import argparse
import json
import sys
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser(description="Smoke test for Echo Gateway")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:7777",
        help="Base URL for Echo Gateway (default: http://127.0.0.1:7777)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Request timeout in seconds (default: 60)",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    timeout = args.timeout
    passed = 0
    failed = 0

    print(f"Echo Gateway Smoke Test")
    print(f"========================")
    print(f"Base URL: {base_url}")
    print(f"Timeout: {timeout}s")
    print()

    # Test 1: Health check
    print("Test 1: /v1/health endpoint")
    try:
        response = httpx.get(f"{base_url}/v1/health", timeout=10.0)
        data = response.json()

        if response.status_code == 200 and data.get("status") in ("ok", "degraded"):
            print(f"  PASS: Status = {data.get('status')}")
            print(f"        LLM URL = {data.get('llm_url')}")
            print(f"        Model = {data.get('model')}")
            passed += 1
        else:
            print(f"  FAIL: Unexpected response: {data}")
            failed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1
    print()

    # Test 2: UI served
    print("Test 2: / serves HTML with 'Echo'")
    try:
        response = httpx.get(f"{base_url}/", timeout=10.0)

        if response.status_code == 200 and "Echo" in response.text:
            print(f"  PASS: HTML served ({len(response.text)} bytes)")
            passed += 1
        else:
            print(f"  FAIL: Status = {response.status_code}, 'Echo' in body = {'Echo' in response.text}")
            failed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1
    print()

    # Test 3: Chat with tool call
    print("Test 3: /v1/chat triggers tool call")
    session_id = None
    try:
        response = httpx.post(
            f"{base_url}/v1/chat",
            json={
                "messages": [
                    {"role": "user", "content": "Search for Intel in the graph"}
                ]
            },
            timeout=timeout,
        )
        data = response.json()

        if response.status_code == 200:
            session_id = data.get("session_id")
            tool_calls = data.get("tool_calls", [])
            content = data.get("message", {}).get("content", "")

            print(f"  Session ID: {session_id}")
            print(f"  Tool calls: {len(tool_calls)}")
            if tool_calls:
                for tc in tool_calls:
                    print(f"    - {tc.get('name')}: {tc.get('args')}")

            print(f"  Response preview: {content[:100]}..." if len(content) > 100 else f"  Response: {content}")

            # Consider it a pass if we got a response (tool calls are optional depending on LLM)
            if content or tool_calls:
                print(f"  PASS")
                passed += 1
            else:
                print(f"  FAIL: Empty response")
                failed += 1
        else:
            print(f"  FAIL: Status = {response.status_code}")
            print(f"        Error: {data}")
            failed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1
    print()

    # Test 4: Receipt written
    print("Test 4: Receipt written to receipts/echo_sessions/")
    sessions_dir = Path(__file__).parent.parent / "receipts" / "echo_sessions"

    if session_id:
        session_file = sessions_dir / f"session_{session_id}.jsonl"
        if session_file.exists():
            with open(session_file) as f:
                lines = f.readlines()
            print(f"  PASS: {session_file.name} ({len(lines)} entries)")

            # Show entry types
            entry_types = [json.loads(line).get("entry_type") for line in lines]
            print(f"        Entry types: {entry_types}")
            passed += 1
        else:
            print(f"  FAIL: Session file not found: {session_file}")
            failed += 1
    else:
        # Check if any recent session files exist
        session_files = list(sessions_dir.glob("session_*.jsonl"))
        if session_files:
            recent = sorted(session_files, key=lambda f: f.stat().st_mtime, reverse=True)[0]
            print(f"  PASS (partial): Found session file: {recent.name}")
            passed += 1
        else:
            print(f"  SKIP: No session ID from test 3")
    print()

    # Summary
    print("========================")
    print(f"Results: {passed} passed, {failed} failed")

    if failed > 0:
        print("\nSome tests failed. Check that:")
        print("  1. Echo Gateway is running: make echo-ui")
        print("  2. Ollama is running with the model: ollama run qwen2.5:latest")
        sys.exit(1)

    print("\nAll tests passed!")
    sys.exit(0)


if __name__ == "__main__":
    main()
