#!/usr/bin/env python3
"""
FGIP Graph Insert — Investment Position Graph
Date: 2026-05-14

Wires the investment stack from data-center-intel.md into the FGIP graph.
Each position is a node with edges to:
  - Thesis nodes (why you own it)
  - Account nodes (where it lives)
  - Risk/exit triggers

Positions from: data-center-intel.md Investment Stack
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
SESSION_ID = "position-graph-20260514"

# ═══════════════════════════════════════════════════════════════════════════════
# CLAIMS
# ═══════════════════════════════════════════════════════════════════════════════

CLAIMS = [
    Claim(
        claim_id="CLAIM-TIMING-CASCADE-BACKTESTED",
        claim_text=(
            "Data center timing cascade (deal → PUC → pipeline → gathering → E&P) "
            "backtested against Virginia 2019-2022. Sequence CONFIRMED. Magnitude was "
            "inflated by gas price supercycle. FERC stage is biggest alpha window — "
            "institutional money blind to cross-referencing FERC capacity filings "
            "with utility data center deals."
        ),
        topic="INVESTMENT_THESIS",
        status=ClaimStatus.EVIDENCED,
        required_tier=1,
        notes="Virginia analog backtest. Sequence confirmed, magnitude overstated.",
    ),
    Claim(
        claim_id="CLAIM-MIDSTREAM-FEE-STRUCTURE",
        claim_text=(
            "Midstream companies (DTM, WMB, MPLX) earn fee-based revenue from pipeline "
            "capacity and gathering. Revenue does NOT depend on gas prices — it depends "
            "on throughput volumes. This is the key risk split: upstream (AR, EQT) needs "
            "gas prices, midstream needs gas to flow regardless of price."
        ),
        topic="INVESTMENT_THESIS",
        status=ClaimStatus.VERIFIED,
        required_tier=1,
        notes="10-K filings for DTM, WMB. Fee-based contracts with minimum volume commitments.",
    ),
    Claim(
        claim_id="CLAIM-EXTRACTION-DEFENSE-PORTFOLIO",
        claim_text=(
            "Portfolio must generate real yield above the 6.3% M2 extraction rate. "
            "Midstream distributions (5-8%), utility dividends (3-5%), and TIPS/I-Bonds "
            "(inflation-indexed) are the primary defense. Net extraction rate = "
            "10.8% - portfolio yield - real capital appreciation. Target: net negative."
        ),
        topic="INVESTMENT_THESIS",
        status=ClaimStatus.EVIDENCED,
        required_tier=1,
        notes="M2 backtest VERIFIED. Portfolio defense is inference from verified finding.",
    ),
]

# ═══════════════════════════════════════════════════════════════════════════════
# POSITION DEFINITIONS
# Layer, ticker, name, description, thesis_link, conviction, risk
# ═══════════════════════════════════════════════════════════════════════════════

POSITIONS = [
    # === Layer 1: Utilities ===
    {
        "id": "pos-DTE", "ticker": "DTE", "name": "DTE Energy",
        "layer": "utility", "conviction": "high",
        "desc": "SE Michigan. 7 GW pipeline, 19-yr Stargate contract. Most direct DC load growth exposure.",
        "entry_trigger": "MPSC approval + construction start",
        "exit_trigger": "Stargate cancellation or >2yr delay",
        "yield_pct": 3.5,
    },
    {
        "id": "pos-SO", "ticker": "SO", "name": "Southern Company",
        "layer": "utility", "conviction": "medium",
        "desc": "Georgia Power parent. Hampton substation confirmed (field observation). Southeast build-out.",
        "entry_trigger": "Hampton field confirmation (DONE)",
        "exit_trigger": "Georgia PSC rate case rejection",
        "yield_pct": 3.8,
    },
    {
        "id": "pos-WEC", "ticker": "WEC", "name": "WEC Energy Group",
        "layer": "utility", "conviction": "medium",
        "desc": "Wisconsin. Microsoft Fairwater 7 GW campus.",
        "entry_trigger": "Wisconsin PSC approval",
        "exit_trigger": "Microsoft withdrawal",
        "yield_pct": 3.6,
    },

    # === Layer 4a: Midstream (HIGHEST CONVICTION) ===
    {
        "id": "pos-DTM", "ticker": "DTM", "name": "DT Midstream",
        "layer": "midstream", "conviction": "highest",
        "desc": "Owns NEXUS pipeline + Ohio Utica gathering. Two fee layers from same deal. Top pick.",
        "entry_trigger": "FERC NEXUS capacity filing",
        "exit_trigger": "Ohio Utica throughput miss 2 consecutive quarters",
        "yield_pct": 5.2,
        "timeline": "18-36 months",
    },
    {
        "id": "pos-WMB", "ticker": "WMB", "name": "Williams Companies",
        "layer": "midstream", "conviction": "high",
        "desc": "Transco (largest US gas pipeline) + Appalachian gathering. Southeast DC feed.",
        "entry_trigger": "Transco expansion approval",
        "exit_trigger": "Regulatory block on Transco",
        "yield_pct": 4.8,
    },
    {
        "id": "pos-MPLX", "ticker": "MPLX", "name": "MPLX LP",
        "layer": "midstream", "conviction": "medium",
        "desc": "Ohio Gathering Company (Belmont, Monroe, Harrison). Quiet Utica play.",
        "entry_trigger": "DTM Ohio earnings confirmation",
        "exit_trigger": "Distribution cut",
        "yield_pct": 8.1,
        "timeline": "24-36 months",
    },

    # === Layer 4b: Upstream E&P ===
    {
        "id": "pos-AR", "ticker": "AR", "name": "Antero Resources",
        "layer": "upstream", "conviction": "medium",
        "desc": "$2.8B Marcellus acquisition, explicitly cited DC demand. #2 Appalachian.",
        "entry_trigger": "PA/WV permit uptick",
        "exit_trigger": "Gas below $3 for 2+ quarters",
        "yield_pct": 0,
        "timeline": "24-48 months",
    },
    {
        "id": "pos-EQT", "ticker": "EQT", "name": "EQT Corporation",
        "layer": "upstream", "conviction": "medium",
        "desc": "Largest Appalachian producer. Feeds NEXUS into Michigan. Volume play.",
        "entry_trigger": "NEXUS throughput increase",
        "exit_trigger": "Gas below $3 sustained",
        "yield_pct": 1.5,
    },

    # === Layer 4c: Nuclear ===
    {
        "id": "pos-CEG", "ticker": "CEG", "name": "Constellation Energy",
        "layer": "nuclear", "conviction": "medium",
        "desc": "Largest US nuclear fleet, existing restarts. Long-duration baseload for DC.",
        "entry_trigger": "PPA with hyperscaler confirmed",
        "exit_trigger": "NRC regulatory action",
        "yield_pct": 0.7,
    },

    # === Inflation Defense ===
    {
        "id": "pos-TIPS", "ticker": "TIPS/I-BONDS", "name": "Treasury Inflation Protected",
        "layer": "inflation_defense", "conviction": "highest",
        "desc": "Direct inflation hedge. I-Bonds ($10K/yr) + TIPS ladder. Zero credit risk. "
                "Most direct defense against the 6.3% M2 extraction.",
        "entry_trigger": "Always (systematic allocation)",
        "exit_trigger": "Never (permanent allocation)",
        "yield_pct": 2.5,  # real yield
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

    # Insert position nodes
    print("\nPOSITIONS:")
    nodes = []
    edges = []

    for pos in POSITIONS:
        node = Node(
            node_id=pos["id"],
            node_type=NodeType.THESIS,
            name=f"{pos['ticker']} — {pos['name']}",
            aliases=[pos["ticker"], pos["name"]],
            description=pos["desc"],
            metadata={
                "ticker": pos["ticker"],
                "layer": pos["layer"],
                "conviction": pos["conviction"],
                "entry_trigger": pos["entry_trigger"],
                "exit_trigger": pos["exit_trigger"],
                "yield_pct": pos["yield_pct"],
                "timeline": pos.get("timeline", "ongoing"),
            },
        )
        nodes.append(node)
        try:
            db.insert_node(node)
            results["nodes_inserted"] += 1
            print(f"  + {pos['ticker']} ({pos['layer']}, {pos['conviction']})")
        except Exception as e:
            if "UNIQUE constraint" in str(e):
                print(f"  = {pos['ticker']} (exists)")
            else:
                results["errors"].append(f"node {pos['id']}: {e}")

        # Edge: position → account (primary brokerage, except TIPS)
        if pos["layer"] == "inflation_defense":
            account_target = "account-treasury-direct"
        else:
            account_target = "account-brokerage-primary"

        edges.append(Edge(
            edge_id=f"E-{pos['id']}-in-account-{SESSION_ID}",
            edge_type=EdgeType.DEPENDS_ON,
            from_node_id=pos["id"],
            to_node_id=account_target,
            claim_id="CLAIM-FDIC-SIPC-LIMITS",
            assertion_level=AssertionLevel.INFERENCE.value,
            source="Portfolio structure",
            confidence=0.90,
            notes=f"{pos['ticker']} held in {account_target}.",
        ))

        # Edge: position → extraction defense
        if pos["yield_pct"] > 0:
            edges.append(Edge(
                edge_id=f"E-{pos['id']}-defends-extraction-{SESSION_ID}",
                edge_type=EdgeType.REDUCES,
                from_node_id=pos["id"],
                to_node_id="extraction-rate-10p8",
                claim_id="CLAIM-EXTRACTION-DEFENSE-PORTFOLIO",
                assertion_level=AssertionLevel.INFERENCE.value,
                source="Portfolio extraction defense",
                confidence=0.80,
                notes=f"{pos['ticker']} yield {pos['yield_pct']}% offsets extraction rate.",
                metadata={"yield_pct": pos["yield_pct"]},
            ))

    # Thesis edges: midstream → cascade thesis
    for pos in POSITIONS:
        if pos["layer"] in ("midstream", "upstream", "utility"):
            edges.append(Edge(
                edge_id=f"E-{pos['id']}-thesis-cascade-{SESSION_ID}",
                edge_type=EdgeType.DERIVES_FROM,
                from_node_id=pos["id"],
                to_node_id="physical-value-hierarchy",
                claim_id="CLAIM-TIMING-CASCADE-BACKTESTED",
                assertion_level=AssertionLevel.INFERENCE.value,
                source="Data center timing cascade",
                confidence=0.85,
                notes=f"{pos['ticker']} positioned on physical value hierarchy ({pos['layer']} layer).",
            ))

    # Midstream-specific: fee structure thesis
    for pos in POSITIONS:
        if pos["layer"] == "midstream":
            edges.append(Edge(
                edge_id=f"E-{pos['id']}-fee-thesis-{SESSION_ID}",
                edge_type=EdgeType.DERIVES_FROM,
                from_node_id=pos["id"],
                to_node_id="energy-intensity-gradient",
                claim_id="CLAIM-MIDSTREAM-FEE-STRUCTURE",
                assertion_level=AssertionLevel.INFERENCE.value,
                source="Fee-based midstream model",
                confidence=0.85,
                notes=f"{pos['ticker']}: fee-based, volume-dependent, gas-price-independent.",
            ))

    # Insert edges
    print("\nEDGES:")
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
            "Investment position graph. 11 positions across 5 layers "
            "(utility, midstream, upstream, nuclear, inflation defense). "
            "Connected to accounts, thesis nodes, and extraction defense."
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
