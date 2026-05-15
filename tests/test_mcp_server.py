#!/usr/bin/env python3
"""End-to-end tests for FGIP MCP server tool functions."""

import json
import os
import sqlite3
import sys

# Point DB_PATH before importing
os.environ["FGIP_DB"] = os.path.join(os.path.dirname(__file__), "..", "fgip.db")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fgip.mcp_server import (
    get_db, _query_node, _query_edges, _search_claims, _search_nodes,
    _get_neighbors, _pattern_match, _graph_stats, _get_sources,
)

passed = 0
failed = 0


def test(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  PASS  {name}")
        passed += 1
    else:
        print(f"  FAIL  {name}  {detail}")
        failed += 1


db = get_db()

# ── Test 1: graph_stats ──
print("\n=== graph_stats ===")
stats = _graph_stats(db)
test("nodes > 2000", stats["nodes"] > 2000, f"got {stats['nodes']}")
test("edges > 2000", stats["edges"] > 2000, f"got {stats['edges']}")
test("claims > 30000", stats["claims"] > 30000, f"got {stats['claims']}")
test("sources > 5000", stats["sources"] > 5000, f"got {stats['sources']}")
test("node_types is dict", isinstance(stats["node_types"], dict))
test("edge_types_top20 non-empty", len(stats["edge_types_top20"]) > 0)
test("claim_statuses non-empty", len(stats["claim_statuses"]) > 0)
test("source_tiers non-empty", len(stats["source_tiers"]) > 0)
test("evidence_coverage is number", isinstance(stats["evidence_coverage"], float))
test("tier_01_claims > 0", stats["tier_01_claims"] > 0, f"got {stats['tier_01_claims']}")
print(f"  Top 5 edge types: {dict(list(stats['edge_types_top20'].items())[:5])}")
print(f"  Node types: {stats['node_types']}")

# ── Test 2: query_node ──
print("\n=== query_node ===")
# By name
r = _query_node(db, {"query": "BlackRock", "include_edges": True})
test("BlackRock found", r["count"] > 0)
if r["matches"]:
    n = r["matches"][0]
    test("BlackRock name correct", "blackrock" in n["name"].lower(), n["name"])
    test("has outgoing edges", len(n.get("outgoing_edges", [])) > 0,
         f"got {len(n.get('outgoing_edges', []))}")
    test("has incoming edges", len(n.get("incoming_edges", [])) > 0,
         f"got {len(n.get('incoming_edges', []))}")
    print(f"  Outgoing: {len(n['outgoing_edges'])}, Incoming: {len(n['incoming_edges'])}")
    for e in n["outgoing_edges"][:3]:
        print(f"    -> {e['edge_type']} -> {e['to_name']}")

# By type filter
r2 = _query_node(db, {"query": "Intel", "node_type": "COMPANY"})
test("Intel COMPANY found", r2["count"] > 0)

# Not found
r3 = _query_node(db, {"query": "xyznonexistent12345"})
test("nonexistent returns empty", r3["count"] == 0)

# Without edges
r4 = _query_node(db, {"query": "BlackRock", "include_edges": False})
test("no-edges mode works", r4["count"] > 0 and "outgoing_edges" not in r4["matches"][0])

# ── Test 3: query_edges ──
print("\n=== query_edges ===")
# All edges from BlackRock
r = _query_edges(db, {"from_node": "BlackRock", "limit": 20})
test("edges from BlackRock", r["count"] > 0, f"got {r['count']}")
if r["edges"]:
    types = set(e["edge_type"] for e in r["edges"])
    print(f"  Edge types from BlackRock: {types}")

# Edges by type
r2 = _query_edges(db, {"edge_type": "VOTED_FOR", "limit": 5})
test("VOTED_FOR edges exist", r2["count"] > 0, f"got {r2['count']}")

# Edges with confidence filter
r3 = _query_edges(db, {"min_confidence": 0.9, "limit": 10})
test("high-confidence edges", r3["count"] > 0)

# ── Test 4: search_claims ──
print("\n=== search_claims ===")
r = _search_claims(db, {"query": "tariff", "limit": 5})
test("tariff claims found", r["count"] > 0, f"got {r['count']}")
if r["claims"]:
    c = r["claims"][0]
    test("claim has text", len(c.get("claim_text", "")) > 0)
    test("claim has status", c.get("status") is not None)
    test("claim has sources list", isinstance(c.get("sources"), list))
    print(f"  First claim: [{c['status']}] {c['claim_text'][:80]}...")
    print(f"  Sources: {len(c['sources'])}, max_tier: {c.get('max_source_tier')}")

# With status filter
r2 = _search_claims(db, {"query": "BlackRock", "status": "PARTIAL", "limit": 3})
test("filtered claim search", isinstance(r2["claims"], list))

# ── Test 5: search_nodes ──
print("\n=== search_nodes ===")
r = _search_nodes(db, {"query": "semiconductor", "limit": 5})
test("semiconductor nodes found", r["count"] > 0, f"got {r['count']}")
if r["nodes"]:
    for n in r["nodes"][:3]:
        print(f"  {n['name']} ({n['node_type']})")

# With type filter
r2 = _search_nodes(db, {"query": "Intel", "node_type": "COMPANY", "limit": 5})
test("Intel COMPANY search", r2["count"] > 0)

# ── Test 6: get_neighbors ──
print("\n=== get_neighbors ===")
# First resolve a node_id for BlackRock
br = _query_node(db, {"query": "BlackRock", "include_edges": False})
if br["matches"]:
    br_id = br["matches"][0]["node_id"]
    r = _get_neighbors(db, {"node_id": br_id, "hops": 1})
    test("neighbors found", r["count"] > 0, f"got {r['count']}")
    test("center node returned", r["center"]["node_id"] == br_id)
    dirs = set(n["direction"] for n in r["neighbors"])
    print(f"  Directions: {dirs}, Total neighbors: {r['count']}")

    # By name (should resolve)
    r2 = _get_neighbors(db, {"node_id": "BlackRock", "hops": 1})
    test("name resolution works", r2["count"] > 0)

    # 2-hop
    r3 = _get_neighbors(db, {"node_id": br_id, "hops": 2})
    test("2-hop more than 1-hop", r3["count"] >= r["count"],
         f"1-hop={r['count']}, 2-hop={r3['count']}")

    # Direction filter
    r4 = _get_neighbors(db, {"node_id": br_id, "direction": "outgoing", "hops": 1})
    test("outgoing-only filter", all(n["direction"] == "outgoing" for n in r4["neighbors"]))

# Nonexistent
r5 = _get_neighbors(db, {"node_id": "xyznonexistent12345"})
test("nonexistent returns error", "error" in r5)

# ── Test 7: pattern_match ──
print("\n=== pattern_match ===")
# both_sides
r = _pattern_match(db, {"pattern": "both_sides", "min_confidence": 0.5})
test("both_sides pattern runs", "matches" in r)
print(f"  both_sides matches: {r['count']}")
if r["matches"]:
    m = r["matches"][0]
    print(f"  First: {m['owner_name']} -> {m['target1']} + {m['target2']}")

# both_sides with entity filter
r2 = _pattern_match(db, {"pattern": "both_sides", "entity": "BlackRock"})
test("both_sides entity filter", "matches" in r2)
print(f"  BlackRock both_sides: {r2['count']}")

# revolving_door
r3 = _pattern_match(db, {"pattern": "revolving_door"})
test("revolving_door runs", "matches" in r3)
print(f"  revolving_door matches: {r3['count']}")

# regulatory_capture
r4 = _pattern_match(db, {"pattern": "regulatory_capture"})
test("regulatory_capture runs", "matches" in r4)
print(f"  regulatory_capture matches: {r4['count']}")

# funding_loop
r5 = _pattern_match(db, {"pattern": "funding_loop"})
test("funding_loop runs", "matches" in r5)
print(f"  funding_loop matches: {r5['count']}")

# ── Test 8: get_sources ──
print("\n=== get_sources ===")
# All tier-0 sources
r = _get_sources(db, {"tier": 0, "limit": 5})
test("tier-0 sources found", r["count"] > 0, f"got {r['count']}")
if r["sources"]:
    for s in r["sources"][:3]:
        print(f"  [tier {s['tier']}] {s['domain']}: {s['url'][:60]}...")

# Get sources for a specific claim
claims = _search_claims(db, {"query": "BlackRock", "limit": 1})
if claims["claims"]:
    cid = claims["claims"][0]["claim_id"]
    r2 = _get_sources(db, {"claim_id": cid})
    test(f"sources for claim {cid[:20]}...", isinstance(r2["sources"], list))
    print(f"  Claim sources: {r2['count']}")

# ── Summary ──
db.close()
print(f"\n{'='*50}")
print(f"RESULTS: {passed} passed, {failed} failed, {passed+failed} total")
print(f"{'='*50}")
sys.exit(1 if failed > 0 else 0)
