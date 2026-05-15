#!/usr/bin/env python3
"""
FGIP Temporal Edges — Timing Cascade
Date: 2026-05-14

Wires the timing cascade from data-center-intel.md into the graph.
Uses PRECEDES edges with lag metadata for the sequence:
  Deal → PUC → Gas Contract → FERC → Gathering → Permits → Wells

Also wires Michigan-specific temporal sequence (Stargate timeline).
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
    Node, Edge, Claim, ClaimStatus,
    NodeType, EdgeType, AssertionLevel, compute_sha256
)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fgip.db")
SESSION_DATE = "2026-05-14"
SESSION_ID = "temporal-cascade-20260514"

# ═══════════════════════════════════════════════════════════════════════════════
# CLAIMS
# ═══════════════════════════════════════════════════════════════════════════════

CLAIMS = [
    Claim(
        claim_id="CLAIM-TIMING-CASCADE-SEQUENCE",
        claim_text=(
            "Data center power demand creates a temporal cascade: "
            "Deal announcement → PUC/MPSC filing (D+0) → PUC approval (D+30-90) → "
            "Gas supply contract (D+90-180) → FERC capacity reservation (D+90-270) → "
            "Gathering acreage dedications (D+120-365) → E&P drilling permit surge "
            "(D+180-540) → Wells online (D+365-730). Backtested against Virginia "
            "2019-2022. FERC stage is biggest alpha window."
        ),
        topic="INVESTMENT_THESIS",
        status=ClaimStatus.EVIDENCED,
        required_tier=1,
        notes="Virginia analog backtest confirmed sequence. See data-center-intel.md.",
    ),
    Claim(
        claim_id="CLAIM-STARGATE-TIMELINE",
        claim_text=(
            "Stargate Michigan timeline: OpenAI/Oracle announcement → MPSC approved "
            "Dec 18 2025 → AG Nessel motion pending March 12 2026 → DTE 7 GW pipeline "
            "→ 19-year contract. Saline Township, Washtenaw County. 1.4 GW initial."
        ),
        topic="INVESTMENT_THESIS",
        status=ClaimStatus.EVIDENCED,
        required_tier=1,
        notes="MPSC docket. DTE investor relations.",
    ),
]

# ═══════════════════════════════════════════════════════════════════════════════
# CASCADE STAGE NODES
# ═══════════════════════════════════════════════════════════════════════════════

STAGES = [
    {
        "id": "cascade-stage-deal", "name": "Deal Announcement",
        "desc": "Data center deal announced or filed. D+0. Observable: State PUC/MPSC docket.",
        "lag_days": 0, "observable": "State PUC livestream, press release",
    },
    {
        "id": "cascade-stage-puc", "name": "PUC/PSC Approval",
        "desc": "Public utility commission approves rate base / capacity plan. D+30-90.",
        "lag_days": 60, "observable": "Commission meeting, docket ruling",
    },
    {
        "id": "cascade-stage-gas-contract", "name": "Gas Supply Contract",
        "desc": "Utility signs gas supply agreement for data center load. D+90-180.",
        "lag_days": 135, "observable": "Utility earnings call language",
    },
    {
        "id": "cascade-stage-ferc", "name": "FERC Capacity Reservation",
        "desc": "Pipeline capacity reserved at FERC. BIGGEST ALPHA WINDOW. D+90-270. "
                "Institutional money blind to cross-referencing FERC + utility DC deals.",
        "lag_days": 180, "observable": "FERC eLibrary filings",
    },
    {
        "id": "cascade-stage-gathering", "name": "Gathering Acreage Dedications",
        "desc": "Midstream companies sign gathering contracts. D+120-365. "
                "Observable in midstream earnings throughput guidance.",
        "lag_days": 240, "observable": "DTM/MPLX quarterly earnings",
    },
    {
        "id": "cascade-stage-permits", "name": "E&P Drilling Permit Surge",
        "desc": "Upstream producers file drilling permits. D+180-540. "
                "Observable in weekly state permit reports (PA DEP, WV DEP, OH DNR).",
        "lag_days": 360, "observable": "State DEP weekly permit reports",
    },
    {
        "id": "cascade-stage-wells", "name": "Wells Online / Production",
        "desc": "New wells come online, gas flows. D+365-730. "
                "Observable in EIA monthly production data.",
        "lag_days": 540, "observable": "EIA Natural Gas Monthly",
    },
]


def main():
    t_start = time.time()
    cpu_start = time.process_time()
    start_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

    db = FGIPDatabase(DB_PATH)
    results = {"nodes_inserted": 0, "edges_inserted": 0, "claims_inserted": 0,
               "errors": []}

    # Insert claims
    print("CLAIMS:")
    for claim in CLAIMS:
        try:
            db.insert_claim(claim)
            results["claims_inserted"] += 1
            print(f"  + {claim.claim_id}")
        except Exception as e:
            if "UNIQUE constraint" in str(e):
                print(f"  = {claim.claim_id} (exists)")
            else:
                results["errors"].append(f"claim {claim.claim_id}: {e}")

    # Insert stage nodes
    print("\nCASCADE STAGES:")
    for stage in STAGES:
        node = Node(
            node_id=stage["id"],
            node_type=NodeType.ECONOMIC_EVENT,
            name=stage["name"],
            aliases=[],
            description=stage["desc"],
            metadata={
                "lag_days_from_deal": stage["lag_days"],
                "observable_trigger": stage["observable"],
                "cascade_type": "dc_timing",
            },
        )
        try:
            db.insert_node(node)
            results["nodes_inserted"] += 1
            print(f"  + {stage['name']} (D+{stage['lag_days']})")
        except Exception as e:
            if "UNIQUE constraint" in str(e):
                print(f"  = {stage['name']} (exists)")
            else:
                results["errors"].append(f"node {stage['id']}: {e}")

    # PRECEDES edges between consecutive stages
    print("\nTEMPORAL EDGES:")
    edges = []
    for i in range(len(STAGES) - 1):
        s_from = STAGES[i]
        s_to = STAGES[i + 1]
        lag = s_to["lag_days"] - s_from["lag_days"]

        edges.append(Edge(
            edge_id=f"E-{s_from['id']}-precedes-{s_to['id']}-{SESSION_ID}",
            edge_type=EdgeType.PRECEDES,
            from_node_id=s_from["id"],
            to_node_id=s_to["id"],
            claim_id="CLAIM-TIMING-CASCADE-SEQUENCE",
            assertion_level=AssertionLevel.FACT.value,
            source="Virginia 2019-2022 backtest",
            confidence=0.85,
            notes=f"{s_from['name']} precedes {s_to['name']} by ~{lag} days.",
            metadata={"lag_days": lag, "lag_range_days": f"{lag-30}-{lag+60}"},
        ))

    # Connect cascade to existing thesis nodes
    # FERC stage → physical value hierarchy (biggest alpha)
    edges.append(Edge(
        edge_id=f"E-ferc-alpha-physical-hierarchy-{SESSION_ID}",
        edge_type=EdgeType.DERIVES_FROM,
        from_node_id="cascade-stage-ferc",
        to_node_id="physical-value-hierarchy",
        claim_id="CLAIM-TIMING-CASCADE-SEQUENCE",
        assertion_level=AssertionLevel.INFERENCE.value,
        source="FERC alpha window analysis",
        confidence=0.85,
        notes="FERC capacity reservation is biggest alpha window in timing cascade.",
    ))

    # Connect positions to their relevant cascade stages
    POSITION_STAGE_MAP = [
        ("pos-DTE", "cascade-stage-deal", "DTE is the utility at deal stage (Stargate)"),
        ("pos-DTE", "cascade-stage-puc", "DTE received MPSC approval Dec 2025"),
        ("pos-SO", "cascade-stage-deal", "Southern Company Hampton substation confirmed"),
        ("pos-WEC", "cascade-stage-deal", "WEC Microsoft Fairwater 7 GW"),
        ("pos-DTM", "cascade-stage-ferc", "DTM NEXUS pipeline FERC capacity"),
        ("pos-DTM", "cascade-stage-gathering", "DTM Ohio Utica gathering contracts"),
        ("pos-WMB", "cascade-stage-ferc", "WMB Transco expansion at FERC"),
        ("pos-WMB", "cascade-stage-gathering", "WMB Appalachian gathering"),
        ("pos-MPLX", "cascade-stage-gathering", "MPLX Ohio Gathering Company"),
        ("pos-AR", "cascade-stage-permits", "AR drilling permits Marcellus"),
        ("pos-EQT", "cascade-stage-permits", "EQT largest Appalachian producer"),
        ("pos-EQT", "cascade-stage-wells", "EQT feeds NEXUS into Michigan"),
    ]

    for pos_id, stage_id, note in POSITION_STAGE_MAP:
        edges.append(Edge(
            edge_id=f"E-{pos_id}-at-{stage_id}-{SESSION_ID}",
            edge_type=EdgeType.DEPENDS_ON,
            from_node_id=pos_id,
            to_node_id=stage_id,
            claim_id="CLAIM-TIMING-CASCADE-SEQUENCE",
            assertion_level=AssertionLevel.INFERENCE.value,
            source="Timing cascade position mapping",
            confidence=0.80,
            notes=note,
        ))

    # Stargate-specific timeline edges
    stargate_edges = [
        ("pos-DTE", "cascade-stage-puc",
         "Stargate MPSC approved Dec 18 2025. AG Nessel motion pending.",
         "CLAIM-STARGATE-TIMELINE"),
    ]
    for from_id, to_id, note, claim_id in stargate_edges:
        edges.append(Edge(
            edge_id=f"E-stargate-{from_id}-{to_id}-{SESSION_ID}",
            edge_type=EdgeType.CONFIRMS,
            from_node_id=from_id,
            to_node_id=to_id,
            claim_id=claim_id,
            assertion_level=AssertionLevel.FACT.value,
            source="MPSC docket",
            confidence=0.95,
            notes=note,
        ))

    # Insert edges
    for edge in edges:
        try:
            db.insert_edge(edge)
            results["edges_inserted"] += 1
            print(f"  + {edge.from_node_id} --[{edge.edge_type.value}]--> {edge.to_node_id}")
        except Exception as e:
            if "UNIQUE constraint" in str(e):
                print(f"  = {edge.edge_id[:60]} (exists)")
            else:
                results["errors"].append(f"edge {edge.edge_id}: {e}")

    db.conn.commit()

    cost = {
        "wall_time_s": round(time.time() - t_start, 3),
        "cpu_time_s": round(time.process_time() - cpu_start, 3),
        "peak_memory_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        "python_version": platform.python_version(),
        "hostname": platform.node(),
        "timestamp_start": start_iso,
        "timestamp_end": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
    }

    receipt = {
        "receipt_id": SESSION_ID,
        "operation": "graph_insert",
        "session_date": SESSION_DATE,
        "description": (
            "Timing cascade temporal edges. 7 cascade stage nodes (deal → wells). "
            "6 PRECEDES edges for sequence. 12 position-to-stage edges. "
            "Stargate-specific timeline. Connected to physical value hierarchy."
        ),
        "results": results,
        "cost": cost,
    }

    receipt_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "receipts")
    os.makedirs(receipt_dir, exist_ok=True)
    receipt_path = os.path.join(receipt_dir, f"{SESSION_ID}.json")
    with open(receipt_path, "w") as f:
        json.dump(receipt, f, indent=2)

    print(f"\n{'='*60}")
    print(f"Nodes: {results['nodes_inserted']}, Edges: {results['edges_inserted']}, Claims: {results['claims_inserted']}")
    print(f"Errors: {len(results['errors'])}")
    print(f"Receipt: {receipt_path}")
    print(f"{'='*60}")

    if results["errors"]:
        for e in results["errors"]:
            print(f"  ! {e}")

    db.close()
    return 0 if not results["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
