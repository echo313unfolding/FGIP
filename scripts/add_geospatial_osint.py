#!/usr/bin/env python3
"""
Add Geospatial OSINT platforms to FGIP graph.

These are real-time geospatial intelligence tools — where things are physically
right now. FGIP is forensic financial-political graph — where money flows
through institutions. The integration is the Palantir trinity: graph +
geospatial + timeline, all cross-selected.
"""

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path


NODES = [
    {
        "node_id": "tool-worldview-kevtoe",
        "name": "WorldView (kevtoe)",
        "node_type": "TOOL",
        "description": "Real-time tactical intelligence platform — CesiumJS globe with flights, satellites, earthquakes, traffic & CCTV overlays. MAVEN-style dark tactical UI with GLSL post-processing (CRT scanlines, NVG, FLIR). Imperative Cesium primitives for 27K+ entities at 60fps. Architecture reference for FGIP geospatial layer.",
        "aliases": ["worldview-kevtoe", "kevtoe/worldview"],
        "metadata": {
            "role": "architecture_reference",
            "github": "github.com/kevtoe/worldview",
            "stack": "React 19, TypeScript 5.9, CesiumJS 1.138, Resium, Tailwind v4, Vite 7, Express 5, WebSocket",
            "license": "Educational/demo only — no commercial use",
            "key_pattern": "hook + layer component + proxy endpoint per data type",
            "performance": "BillboardCollection/PointPrimitiveCollection (not JSX Entity), dead-reckoning, CallbackProperty"
        }
    },
    {
        "node_id": "tool-worldview-imparpaulo",
        "name": "WorldView (imparpaulo01)",
        "node_type": "TOOL",
        "description": "Browser-based geospatial intelligence dashboard — CesiumJS + Google Photorealistic 3D Tiles, live flight & satellite tracking, GLSL visual filters. React 19, TypeScript, CesiumJS 1.124, Tailwind v4, Express with background AIS/GDELT/MeteoAlarm/RSS collectors.",
        "aliases": ["worldview-imparpaulo", "imparpaulo01/worldview"],
        "metadata": {
            "role": "architecture_reference",
            "github": "github.com/imparpaulo01/worldview",
            "stack": "React 19, TypeScript, CesiumJS 1.124, Google 3D Tiles, Tailwind v4, Express",
            "differentiator": "Google Photorealistic 3D Tiles for globe rendering"
        }
    },
    {
        "node_id": "tool-shadowbroker",
        "name": "Shadowbroker",
        "node_type": "TOOL",
        "description": "MapLibre GL OSINT dashboard — Next.js + FastAPI, 15+ public feeds, GPS jamming detection via aircraft NAC-P values, KiwiSDR integration for live SDR tuning, private jet ownership cards. Most polished Hollywood-hacker aesthetic. 300+ HN points.",
        "aliases": ["BigBodyCobain/Shadowbroker"],
        "metadata": {
            "role": "reference",
            "github": "github.com/BigBodyCobain/Shadowbroker",
            "stack": "MapLibre GL, Next.js, FastAPI",
            "unique": "GPS jamming detection, KiwiSDR SDR integration"
        }
    },
    {
        "node_id": "tool-osiris",
        "name": "OSIRIS",
        "node_type": "TOOL",
        "description": "Open Source Global Intelligence Platform — 'A Palantir Alternative.' Next.js 15 + MapLibre GL, Vercel one-click deploy.",
        "aliases": ["simplifaisoul/osiris"],
        "metadata": {
            "role": "reference",
            "github": "github.com/simplifaisoul/osiris",
            "stack": "Next.js 15, MapLibre GL, Vercel"
        }
    },
    {
        "node_id": "tool-osint-war-room",
        "name": "OSINT War Room",
        "node_type": "TOOL",
        "description": "War Tactical dashboard — GDELT conflict events, OpenSky aircraft, AISStream ships, Pentagon Pizza Index, Polymarket bets, VIX, CCTV feeds. FastAPI backend. Impressive data source variety.",
        "aliases": ["Hue-Jhan/OSINT-War-Room"],
        "metadata": {
            "role": "reference",
            "github": "github.com/Hue-Jhan/OSINT-War-Room",
            "stack": "FastAPI",
            "unique": "Pentagon Pizza Index, Polymarket integration"
        }
    },
    {
        "node_id": "concept-fgip-globe",
        "name": "FGIP Globe (planned)",
        "node_type": "CONCEPT",
        "description": "Planned geospatial rendering layer for FGIP. React 19 + CesiumJS using WorldView layer pattern. FGIP-specific layers: FacilityLayer, FundingChainLayer, DistrictLayer, CommodityFlowLayer, ContractLayer, LobbyingLayer. Cross-view selection between graph and globe.",
        "aliases": ["fgip-globe"],
        "metadata": {
            "status": "PLANNED",
            "layers": [
                "FacilityLayer — contractor HQs, mines, refineries, plants, data centers",
                "FundingChainLayer — animated money-flow arcs, color by conviction tier",
                "DistrictLayer — 435 congressional districts by IES score",
                "CommodityFlowLayer — pipelines, shipping lanes, rail, transmission",
                "ContractLayer — USASpending place-of-performance pins",
                "LobbyingLayer — LDA filing density heatmap, FARA agent pins"
            ],
            "integration": "Palantir trinity: graph + geospatial + timeline, cross-selected"
        }
    }
]

EDGES = [
    # WorldView (kevtoe) is the primary architecture reference
    ("concept-fgip-globe", "tool-worldview-kevtoe", "DERIVES_FROM", 0.85,
     "FGIP Globe layer pattern derived from WorldView's hook+layer+proxy architecture"),
    ("concept-fgip-globe", "tool-worldview-imparpaulo", "DERIVES_FROM", 0.70,
     "Google 3D Tiles variant as alternative rendering reference"),
    # FGIP Globe connects to FGIP core
    ("concept-fgip-globe", "concept-palantir-trinity", "IMPLEMENTS", 0.90,
     "Graph + geospatial + timeline cross-selection — the Karp 'ontology made physical' pitch"),
    # Competitive landscape edges
    ("tool-shadowbroker", "tool-worldview-kevtoe", "COMPETES_WITH", 0.60,
     "Both are open-source OSINT dashboards; Shadowbroker uses MapLibre (flat), WorldView uses CesiumJS (globe)"),
    ("tool-osiris", "tool-worldview-kevtoe", "COMPETES_WITH", 0.50,
     "Both position as open-source intelligence platforms"),
]

CLAIMS = [
    {
        "claim_id": "geospatial-osint-integration",
        "statement": "FGIP forensic financial graph + WorldView-style geospatial rendering creates the Palantir Gotham trinity: graph view + geospatial view + timeline view, all cross-selected. Click an entity in one view, it highlights in the other two.",
        "topic": "fgip_architecture",
        "status": "PARTIAL",
        "confidence": 0.75,
        "sources": ["github.com/kevtoe/worldview", "github.com/imparpaulo01/worldview"]
    },
    {
        "claim_id": "worldview-performance-pattern",
        "statement": "WorldView achieves 27K+ entities at 60fps by using imperative Cesium primitives (BillboardCollection, PointPrimitiveCollection) instead of Resium JSX Entity components, with dead-reckoning between API ticks and CallbackProperty for positions.",
        "topic": "geospatial_architecture",
        "status": "EVIDENCED",
        "confidence": 0.90,
        "sources": ["github.com/kevtoe/worldview README"]
    },
    {
        "claim_id": "fgip-funding-chain-geospatial",
        "statement": "NDAA → Lockheed → Howmet → copper → FCX chain can be rendered geospatially: glow on Capitol Hill (appropriation source), arcs to Lockheed Fort Worth, Howmet Pittsburgh, FCX Arizona/Indonesia. Animated dashes show flow direction. Dollar amounts as arc height.",
        "topic": "fgip_architecture",
        "status": "PARTIAL",
        "confidence": 0.70,
        "sources": []
    }
]


def main():
    db_path = Path(__file__).parent.parent / "fgip.db"
    if not db_path.exists():
        print(f"ERROR: {db_path} not found")
        return

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    errors = []
    n_nodes = 0
    n_edges = 0
    n_claims = 0

    # Insert nodes
    for node in NODES:
        try:
            sha = hashlib.sha256(json.dumps(node, sort_keys=True).encode()).hexdigest()
            cur.execute("""
                INSERT OR IGNORE INTO nodes (node_id, name, node_type, description, aliases, metadata, created_at, sha256)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                node["node_id"], node["name"], node["node_type"],
                node["description"], json.dumps(node.get("aliases", [])),
                json.dumps(node.get("metadata", {})), now, sha
            ))
            if cur.rowcount > 0:
                n_nodes += 1
        except Exception as e:
            errors.append(f"Node {node['node_id']}: {e}")

    # Insert concept node for Palantir trinity if not exists
    trinity_data = {
        "node_id": "concept-palantir-trinity",
        "name": "Palantir Trinity (Graph + Geo + Timeline)",
        "node_type": "CONCEPT",
        "description": "The three-view cross-selection pattern that defines Palantir Gotham: graph view, geospatial view, and timeline view. Click an entity in one view, it highlights in the other two. Karp's 'ontology made physical.'",
    }
    sha = hashlib.sha256(json.dumps(trinity_data, sort_keys=True).encode()).hexdigest()
    cur.execute("""
        INSERT OR IGNORE INTO nodes (node_id, name, node_type, description, aliases, metadata, created_at, sha256)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "concept-palantir-trinity", "Palantir Trinity (Graph + Geo + Timeline)",
        "CONCEPT",
        trinity_data["description"],
        json.dumps(["palantir-gotham-trinity", "graph-geo-timeline"]),
        json.dumps({"role": "architectural_pattern", "origin": "Palantir Technologies"}),
        now, sha
    ))
    if cur.rowcount > 0:
        n_nodes += 1

    # Insert edges (schema: edge_id, edge_type, from_node_id, to_node_id, confidence, notes, created_at, sha256)
    for from_id, to_id, rel, conf, desc in EDGES:
        edge_id = hashlib.sha256(f"{from_id}-{rel}-{to_id}".encode()).hexdigest()[:16]
        sha = hashlib.sha256(f"{edge_id}-{now}".encode()).hexdigest()
        try:
            cur.execute("""
                INSERT OR IGNORE INTO edges (edge_id, edge_type, from_node_id, to_node_id, confidence, notes,
                    assertion_level, source, source_type, date_documented, created_at, sha256)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (edge_id, rel, from_id, to_id, conf, desc,
                  "INFERENCE", "OSINT landscape analysis", "tier2", now, now, sha))
            if cur.rowcount > 0:
                n_edges += 1
        except Exception as e:
            errors.append(f"Edge {from_id}->{to_id}: {e}")

    # Insert claims (schema: claim_id, claim_text, topic, status, created_at, notes)
    for claim in CLAIMS:
        try:
            cur.execute("""
                INSERT OR IGNORE INTO claims (claim_id, claim_text, topic, status, required_tier, created_at, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                claim["claim_id"], claim["statement"], claim["topic"],
                claim["status"], 2, now,
                json.dumps({"sources": claim.get("sources", []), "confidence": claim["confidence"]})
            ))
            if cur.rowcount > 0:
                n_claims += 1
        except Exception as e:
            errors.append(f"Claim {claim['claim_id']}: {e}")

    conn.commit()
    conn.close()

    print(f"Inserted: {n_nodes} nodes, {n_edges} edges, {n_claims} claims")
    if errors:
        print(f"Errors ({len(errors)}):")
        for e in errors:
            print(f"  {e}")
    else:
        print("0 errors")


if __name__ == "__main__":
    main()
