#!/usr/bin/env python3
"""
FGIP Graph Insert — Hampton GA Cross-Reference Completion
Date: 2026-03-15
Source: Field observation 2026-03-09 (Josh / Azuria Water Solutions)

Completes the 2 edges skipped by insert_midstream_dc_supply_chain.py because
the Hampton GA nodes (GEO_HENRY_COUNTY_CORRIDOR, ORG_SOUTHERN_COMPANY) were
originally inserted into ~/fgip/fgip_graph.db, not fgip-engine/fgip.db.

This script:
  1. Inserts GEO_HENRY_COUNTY_CORRIDOR (LOCATION) into fgip.db
  2. Inserts ORG_SOUTHERN_COMPANY (ORGANIZATION) into fgip.db
  3. Inserts the 2 previously-skipped edges:
     - E_henry_county_power_thesis: corridor CONFIRMS power/uranium thesis
     - E_southern_co_bottleneck: Southern Company CONFIRMS structural bottleneck thesis
"""

import sys
import os
import json
import time
import resource
import platform
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fgip.db import FGIPDatabase
from fgip.schema import (
    Node, Edge, Source, Claim, ClaimStatus,
    NodeType, EdgeType, AssertionLevel, compute_sha256
)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fgip.db")
SESSION_DATE = "2026-03-15"
SESSION_ID = "hampton-crossref-completion-20260315"

# ═══════════════════════════════════════════════════════════════════════════════
# NODES (from Hampton GA field intel, adapted to fgip.db schema)
# ═══════════════════════════════════════════════════════════════════════════════

NODES = [
    Node(
        node_id="GEO_HENRY_COUNTY_CORRIDOR",
        node_type=NodeType.LOCATION,
        name="Henry County GA — Data Center Concentration Zone",
        aliases=["Henry County DC Corridor", "Hampton GA DC Cluster"],
        description=(
            "Emerging data center concentration zone in Henry County, Georgia. "
            "Equinix AT10x/AT11x at 1000 Site Parkway, active construction at "
            "1100 Site Parkway (probable Equinix expansion). Dedicated Georgia Power "
            "substation across GA-20 highway. First DC approved March 2025, "
            "multiple sites now active. Supply chain signal: Plateau Excavation "
            "on their 9th DC build (repeat specialized GC)."
        ),
        metadata={
            "state": "GA",
            "county": "Henry County",
            "sites": [
                "1000 Site Parkway (Equinix AT10x/AT11x, confirmed)",
                "1100 Site Parkway (active construction, Equinix probable 90%)",
            ],
            "power_infrastructure": "Dedicated substation across GA-20 (Georgia Power / Southern Company)",
            "concentration_risk": "EMERGING",
            "observation_date": "2026-03-09",
            "source_type": "direct_field_observation",
            "observer": "Josh / Azuria Water Solutions",
            "general_contractor": "Plateau Excavation (9th DC build — supply chain signal)",
            "intelligence_value": "HIGH — repeat GC at 9 builds = leading indicator for unpublished pipeline",
        },
    ),
    Node(
        node_id="ORG_SOUTHERN_COMPANY",
        node_type=NodeType.ORGANIZATION,
        name="Southern Company / Georgia Power",
        aliases=["Southern Company", "Georgia Power", "SO"],
        description=(
            "Regulated utility holding company (ticker: SO). Subsidiary Georgia Power "
            "is building dedicated substations for data center campuses in Henry County GA. "
            "Rate base beneficiary: DC load growth = guaranteed capex return under "
            "Georgia utility regulation."
        ),
        metadata={
            "ticker": "SO",
            "org_type": "regulated_utility",
            "subsidiary": "Georgia Power",
            "hq": "Atlanta, GA",
            "dc_relevance": "Building dedicated substations for DC campuses, rate base growth from DC power demand",
            "observation_date": "2026-03-09",
            "source_type": "direct_field_observation",
        },
    ),
]

# ═══════════════════════════════════════════════════════════════════════════════
# SOURCES
# ═══════════════════════════════════════════════════════════════════════════════

SOURCES = [
    Source(
        source_id="src-hampton-field-obs-20260309",
        url="field://hampton-ga-1100-site-parkway/2026-03-09",
        domain="field-observation",
        tier=0,
        notes=(
            "Hampton GA Field Observation 2026-03-09. "
            "Direct field observation by Josh (Azuria Water Solutions) at "
            "1100 Site Parkway, Hampton GA. GC rep (Plateau Excavation) confirmed "
            "9th DC build, dedicated substation built by Georgia Power."
        ),
    ),
]

# ═══════════════════════════════════════════════════════════════════════════════
# CLAIMS
# ═══════════════════════════════════════════════════════════════════════════════

CLAIMS = [
    Claim(
        claim_id="claim-henry-county-dc-corridor-power",
        claim_text=(
            "Henry County GA data center corridor with dedicated Georgia Power substation "
            "confirms data center power demand driving utility infrastructure investment."
        ),
        status=ClaimStatus.EVIDENCED,
        topic="power-demand-dc-corridor",
        required_tier=0,
        notes="Tier 0 — direct field observation. Dedicated substation = committed capex.",
    ),
    Claim(
        claim_id="claim-southern-co-dc-bottleneck",
        claim_text=(
            "Georgia Power (Southern Company) building dedicated substations for data center "
            "campuses confirms utility rate base growth from DC power demand — structural "
            "bottleneck thesis: power infrastructure is the gating constraint."
        ),
        status=ClaimStatus.EVIDENCED,
        topic="structural-bottleneck-power",
        required_tier=0,
        notes="Tier 0 — field-observed dedicated substation across GA-20 highway.",
    ),
]

# ═══════════════════════════════════════════════════════════════════════════════
# EDGES (the 2 that were previously skipped)
# ═══════════════════════════════════════════════════════════════════════════════

EDGES = [
    Edge(
        edge_id="E_henry_county_power_thesis",
        edge_type=EdgeType.CONFIRMS,
        from_node_id="GEO_HENRY_COUNTY_CORRIDOR",
        to_node_id="thesis-power-uranium-screen",
        claim_id="claim-henry-county-dc-corridor-power",
        assertion_level=AssertionLevel.INFERENCE.value,
        source="Field observation 2026-03-09 + public record",
        confidence=0.80,
        notes="Henry County GA DC corridor (Equinix, dedicated substation) confirms data center power demand",
    ),
    Edge(
        edge_id="E_southern_co_bottleneck",
        edge_type=EdgeType.CONFIRMS,
        from_node_id="ORG_SOUTHERN_COMPANY",
        to_node_id="thesis-structural-bottleneck",
        claim_id="claim-southern-co-dc-bottleneck",
        assertion_level=AssertionLevel.INFERENCE.value,
        source="Hampton GA field observation 2026-03-09",
        confidence=0.80,
        notes="Georgia Power building dedicated substations for DCs = utility rate base growth from DC power demand",
    ),
]


def main():
    start_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    t_start = time.time()
    cpu_start = time.process_time()

    print("=" * 70)
    print("FGIP Graph Insert — Hampton GA Cross-Reference Completion")
    print(f"Date: {SESSION_DATE}  |  DB: {DB_PATH}")
    print("=" * 70)

    db = FGIPDatabase(DB_PATH)

    # ── Insert Nodes ──
    print("\n── NODES ──")
    nodes_inserted = 0
    for node in NODES:
        existing = db.get_node(node.node_id)
        if existing:
            print(f"  [EXISTS] {node.node_id}: {node.name}")
            continue
        try:
            receipt = db.insert_node(node)
            if receipt.success:
                nodes_inserted += 1
                print(f"  [NEW] {node.node_id}: {node.name}")
            else:
                print(f"  [SKIP] {node.node_id}: {node.name}")
        except Exception as e:
            print(f"  [ERR] {node.node_id}: {e}")
    print(f"  Nodes: +{nodes_inserted} new")

    # ── Insert Sources ──
    print("\n── SOURCES ──")
    sources_inserted = 0
    for source in SOURCES:
        try:
            receipt = db.insert_source(source)
            if receipt.success:
                sources_inserted += 1
                print(f"  [NEW] {source.source_id}: {source.name}")
            else:
                print(f"  [EXISTS] {source.source_id}")
        except Exception as e:
            print(f"  [ERR] {source.source_id}: {e}")
    print(f"  Sources: +{sources_inserted} new")

    # ── Insert Claims ──
    print("\n── CLAIMS ──")
    claims_inserted = 0
    for claim in CLAIMS:
        try:
            receipt = db.insert_claim(claim)
            if receipt.success:
                claims_inserted += 1
                print(f"  [NEW] {claim.claim_id}")
            else:
                print(f"  [EXISTS] {claim.claim_id}")
        except Exception as e:
            print(f"  [ERR] {claim.claim_id}: {e}")
    print(f"  Claims: +{claims_inserted} new")

    # ── Insert Edges ──
    print("\n── EDGES ──")
    edges_inserted = 0
    edges_skipped = 0
    for edge in EDGES:
        try:
            from_node = db.get_node(edge.from_node_id)
            to_node = db.get_node(edge.to_node_id)
            if not from_node:
                print(f"  [SKIP] {edge.edge_id}: from_node {edge.from_node_id} not found")
                edges_skipped += 1
                continue
            if not to_node:
                print(f"  [SKIP] {edge.edge_id}: to_node {edge.to_node_id} not found")
                edges_skipped += 1
                continue
            receipt = db.insert_edge(edge)
            if receipt.success:
                edges_inserted += 1
                print(f"  [NEW] {edge.edge_id}: {edge.from_node_id} → {edge.to_node_id}")
            else:
                edges_skipped += 1
                print(f"  [EXISTS] {edge.edge_id}")
        except Exception as e:
            edges_skipped += 1
            print(f"  [ERR] {edge.edge_id}: {e}")
    print(f"  Edges: +{edges_inserted} new, {edges_skipped} skipped")

    # ── Summary ──
    stats = db.get_stats()
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Nodes inserted:   {nodes_inserted}")
    print(f"  Sources inserted: {sources_inserted}")
    print(f"  Claims inserted:  {claims_inserted}")
    print(f"  Edges inserted:   {edges_inserted}")
    print(f"  Edges skipped:    {edges_skipped}")
    print(f"\n  Graph totals: {stats['nodes']} nodes | {stats['edges']} edges | "
          f"{stats['claims']} claims | {stats['sources']} sources")
    print("=" * 70)

    # ── Receipt ──
    cost = {
        "wall_time_s": round(time.time() - t_start, 3),
        "cpu_time_s": round(time.process_time() - cpu_start, 3),
        "peak_memory_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        "python_version": platform.python_version(),
        "hostname": platform.node(),
        "timestamp_start": start_iso,
        "timestamp_end": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }

    receipt_data = {
        "session_id": SESSION_ID,
        "operation": "hampton_crossref_completion",
        "date": SESSION_DATE,
        "purpose": "Insert Hampton GA field intel nodes into fgip.db and complete 2 skipped edges from midstream supply chain insert",
        "nodes_inserted": nodes_inserted,
        "edges_inserted": edges_inserted,
        "edges_skipped": edges_skipped,
        "claims_inserted": claims_inserted,
        "sources_inserted": sources_inserted,
        "graph_totals": stats,
        "edges_completed": [
            {
                "edge_id": "E_henry_county_power_thesis",
                "from": "GEO_HENRY_COUNTY_CORRIDOR",
                "to": "thesis-power-uranium-screen",
                "type": "CONFIRMS",
            },
            {
                "edge_id": "E_southern_co_bottleneck",
                "from": "ORG_SOUTHERN_COMPANY",
                "to": "thesis-structural-bottleneck",
                "type": "CONFIRMS",
            },
        ],
        "cost": cost,
    }

    receipt_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "receipts", "supply_chain_mapping")
    os.makedirs(receipt_dir, exist_ok=True)
    receipt_path = os.path.join(receipt_dir,
                                f"hampton_crossref_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json")
    with open(receipt_path, "w") as f:
        json.dump(receipt_data, f, indent=2, default=str)
    print(f"\nReceipt: {receipt_path}")


if __name__ == "__main__":
    main()
