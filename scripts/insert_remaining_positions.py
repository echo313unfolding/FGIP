#!/usr/bin/env python3
"""
FGIP Graph Insert — Remaining Investment Positions
Date: 2026-05-14

Adds positions from data-center-intel.md NOT already in the graph:
  Layer 1 (Utilities): CMS, DUK, D
  Layer 2 (REITs): EQIX, DLR, IRM
  Layer 4 (Gas Turbines): GEV, SMNEY
  Layer 4 (Midstream): KMI, UGI, CPK
  Layer 4 (Upstream): RRC, CNX, CTRA
  Layer 4 (Nuclear): VST, OKLO, SMR, BWXT
  Layer 4 (Uranium): LEU, CCJ

Connects each to accounts, thesis nodes, extraction defense, and cascade stages.
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
SESSION_ID = "remaining-positions-20260514"

POSITIONS = [
    # === Layer 1: Utilities (remaining) ===
    {
        "id": "pos-CMS", "ticker": "CMS", "name": "CMS Energy",
        "layer": "utility", "conviction": "medium",
        "desc": "W/Central Michigan. Undisclosed 1 GW deal. Grand Rapids corridor. Microsoft shell LLC 'Franklin Lowell LLC.'",
        "entry_trigger": "Michigan PSC approval for undisclosed deal",
        "exit_trigger": "Deal cancellation or capacity reduction",
        "yield_pct": 3.3,
    },
    {
        "id": "pos-DUK", "ticker": "DUK", "name": "Duke Energy",
        "layer": "utility", "conviction": "medium",
        "desc": "Carolinas. Amazon/Meta corridor. Large regulated utility with DC load growth.",
        "entry_trigger": "NC/SC PSC rate case for DC load",
        "exit_trigger": "Regulatory block on rate base expansion",
        "yield_pct": 3.9,
    },
    {
        "id": "pos-D", "ticker": "D", "name": "Dominion Energy",
        "layer": "utility", "conviction": "medium",
        "desc": "Virginia. Data Center Alley overflow. Largest DC corridor in US (Ashburn/Loudoun).",
        "entry_trigger": "Virginia SCC capacity filing",
        "exit_trigger": "Grid constraint preventing new connections",
        "yield_pct": 4.8,
    },

    # === Layer 2: Data Center REITs ===
    {
        "id": "pos-EQIX", "ticker": "EQIX", "name": "Equinix",
        "layer": "reit", "conviction": "medium",
        "desc": "Confirmed at Hampton GA (field observation). $80B REIT. Global colo leader.",
        "entry_trigger": "Hampton field confirmation (DONE)",
        "exit_trigger": "Vacancy rate >15% or cap rate compression reversal",
        "yield_pct": 2.1,
    },
    {
        "id": "pos-DLR", "ticker": "DLR", "name": "Digital Realty",
        "layer": "reit", "conviction": "low",
        "desc": "Second largest DC REIT. Hyperscale + colo mix.",
        "entry_trigger": "New hyperscale lease announcement",
        "exit_trigger": "Power cost pass-through failure",
        "yield_pct": 3.2,
    },
    {
        "id": "pos-IRM", "ticker": "IRM", "name": "Iron Mountain",
        "layer": "reit", "conviction": "low",
        "desc": "Converted from document storage to DC. Growing fast but late entrant.",
        "entry_trigger": "DC revenue >50% of total",
        "exit_trigger": "Leverage >7x or credit downgrade",
        "yield_pct": 3.8,
    },

    # === Gas Turbines ===
    {
        "id": "pos-GEV", "ticker": "GEV", "name": "GE Vernova",
        "layer": "gas_turbine", "conviction": "medium",
        "desc": "Behind-the-meter power plants for data centers. Trump EO covers gas turbines. Key equipment supplier.",
        "entry_trigger": "Behind-the-meter contract announcements",
        "exit_trigger": "Renewable-only mandates at state level",
        "yield_pct": 0.3,
    },
    {
        "id": "pos-SMNEY", "ticker": "SMNEY", "name": "Siemens Energy",
        "layer": "gas_turbine", "conviction": "low",
        "desc": "Competitor to GEV. US ADR. Global gas turbine market share.",
        "entry_trigger": "US order book growth",
        "exit_trigger": "ADR liquidity issues or EU regulatory headwinds",
        "yield_pct": 0.0,
    },

    # === Midstream (remaining) ===
    {
        "id": "pos-KMI", "ticker": "KMI", "name": "Kinder Morgan",
        "layer": "midstream", "conviction": "medium",
        "desc": "Tennessee Gas Pipeline through Michigan. Also Southern Natural Gas to Southeast.",
        "entry_trigger": "Tennessee Gas expansion filing",
        "exit_trigger": "Distribution cut or leverage >5x",
        "yield_pct": 5.8,
    },
    {
        "id": "pos-UGI", "ticker": "UGI", "name": "UGI Corporation",
        "layer": "midstream", "conviction": "low",
        "desc": "Bought Columbia Midstream ($1.275B). Eastern OH/WV/PA gathering. Quiet Appalachian play.",
        "entry_trigger": "Columbia Midstream throughput growth",
        "exit_trigger": "LDC business drag or divestiture",
        "yield_pct": 6.2,
    },
    {
        "id": "pos-CPK", "ticker": "CPK", "name": "Chesapeake Utilities",
        "layer": "midstream", "conviction": "low",
        "desc": "Original Columbia Gas Ohio gathering legacy (NOT Chesapeake Energy). Small-cap gathering.",
        "entry_trigger": "Ohio throughput increase",
        "exit_trigger": "Acquisition or strategic review",
        "yield_pct": 2.0,
    },

    # === Upstream E&P (remaining) ===
    {
        "id": "pos-RRC", "ticker": "RRC", "name": "Range Resources",
        "layer": "upstream", "conviction": "low",
        "desc": "SW Marcellus, Washington County PA. Pure Appalachian gas.",
        "entry_trigger": "PA permit uptick in Washington County",
        "exit_trigger": "Gas below $3 sustained",
        "yield_pct": 0.0,
    },
    {
        "id": "pos-CNX", "ticker": "CNX", "name": "CNX Resources",
        "layer": "upstream", "conviction": "low",
        "desc": "Pure Appalachian, second largest leaseholder. Focused on free cash flow.",
        "entry_trigger": "Acreage dedication increase",
        "exit_trigger": "Gas below $3 sustained or hedging losses",
        "yield_pct": 0.0,
    },
    {
        "id": "pos-CTRA", "ticker": "CTRA", "name": "Coterra Energy",
        "layer": "upstream", "conviction": "low",
        "desc": "Marcellus + Permian dual basin. Diversified E&P.",
        "entry_trigger": "Marcellus production growth guidance",
        "exit_trigger": "Permian oil focus dilutes gas thesis",
        "yield_pct": 2.5,
    },

    # === Nuclear ===
    {
        "id": "pos-VST", "ticker": "VST", "name": "Vistra Corp",
        "layer": "nuclear", "conviction": "medium",
        "desc": "Second largest US nuclear fleet. ERCOT exposure. Texas DC load growth.",
        "entry_trigger": "PPA with hyperscaler",
        "exit_trigger": "NRC action or ERCOT capacity surplus",
        "yield_pct": 0.8,
    },
    {
        "id": "pos-OKLO", "ticker": "OKLO", "name": "Oklo Inc",
        "layer": "nuclear", "conviction": "low",
        "desc": "SMR startup, 14 GW pipeline, Sam Altman backed. Pre-revenue. 2028-2030 earliest.",
        "entry_trigger": "NRC construction permit",
        "exit_trigger": "NRC rejection or >3yr delay",
        "yield_pct": 0.0,
        "timeline": "48-72 months",
    },
    {
        "id": "pos-SMR", "ticker": "SMR", "name": "NuScale Power",
        "layer": "nuclear", "conviction": "low",
        "desc": "First NRC-certified SMR design. UAMPS project cancelled but design certified.",
        "entry_trigger": "New utility customer signed",
        "exit_trigger": "Cash burn >50% of runway",
        "yield_pct": 0.0,
        "timeline": "48-72 months",
    },
    {
        "id": "pos-BWXT", "ticker": "BWXT", "name": "BWX Technologies",
        "layer": "nuclear", "conviction": "medium",
        "desc": "Nuclear fuel/components manufacturer. Sole-source Navy reactor fuel. SMR component supplier.",
        "entry_trigger": "SMR component order",
        "exit_trigger": "Defense budget cut or nuclear policy reversal",
        "yield_pct": 1.0,
    },

    # === Uranium ===
    {
        "id": "pos-LEU", "ticker": "LEU", "name": "Centrus Energy",
        "layer": "uranium", "conviction": "low",
        "desc": "Only US uranium enrichment capability. HALEU production for SMRs.",
        "entry_trigger": "HALEU contract from DOE or SMR builder",
        "exit_trigger": "Russian enrichment ban lifted or alternative supplier",
        "yield_pct": 0.0,
        "timeline": "36-60 months",
    },
    {
        "id": "pos-CCJ", "ticker": "CCJ", "name": "Cameco Corporation",
        "layer": "uranium", "conviction": "medium",
        "desc": "Largest Western uranium miner. McArthur River restart. Long-term supply contracts.",
        "entry_trigger": "Uranium spot >$80/lb sustained",
        "exit_trigger": "Kazatomprom flooding market or reactor cancellations",
        "yield_pct": 0.3,
    },
]


def main():
    t_start = time.time()
    cpu_start = time.process_time()
    start_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

    db = FGIPDatabase(DB_PATH)
    results = {"nodes_inserted": 0, "edges_inserted": 0, "errors": []}

    # Insert position nodes
    print("REMAINING POSITIONS:")
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
        try:
            db.insert_node(node)
            results["nodes_inserted"] += 1
            print(f"  + {pos['ticker']} ({pos['layer']}, {pos['conviction']})")
        except Exception as e:
            if "UNIQUE constraint" in str(e):
                print(f"  = {pos['ticker']} (exists)")
            else:
                results["errors"].append(f"node {pos['id']}: {e}")

        # Edge: position → account
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

        # Edge: position → extraction defense (if yield > 0)
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

    # Thesis edges: energy chain positions → cascade thesis
    for pos in POSITIONS:
        if pos["layer"] in ("midstream", "upstream", "utility", "gas_turbine"):
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

    # Nuclear/uranium → long-duration baseload thesis
    for pos in POSITIONS:
        if pos["layer"] in ("nuclear", "uranium"):
            edges.append(Edge(
                edge_id=f"E-{pos['id']}-baseload-thesis-{SESSION_ID}",
                edge_type=EdgeType.DERIVES_FROM,
                from_node_id=pos["id"],
                to_node_id="physical-value-hierarchy",
                claim_id="CLAIM-TIMING-CASCADE-BACKTESTED",
                assertion_level=AssertionLevel.INFERENCE.value,
                source="Nuclear baseload for data centers",
                confidence=0.70,
                notes=f"{pos['ticker']}: nuclear/uranium layer, longest timeline in cascade.",
            ))

    # REIT → corridor clustering
    for pos in POSITIONS:
        if pos["layer"] == "reit":
            edges.append(Edge(
                edge_id=f"E-{pos['id']}-corridor-thesis-{SESSION_ID}",
                edge_type=EdgeType.DERIVES_FROM,
                from_node_id=pos["id"],
                to_node_id="physical-value-hierarchy",
                claim_id="CLAIM-TIMING-CASCADE-BACKTESTED",
                assertion_level=AssertionLevel.INFERENCE.value,
                source="Data center corridor clustering",
                confidence=0.75,
                notes=f"{pos['ticker']}: REIT layer, benefits from corridor formation.",
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
            f"Remaining investment positions. {len(POSITIONS)} positions across "
            "8 layers (utility, reit, gas_turbine, midstream, upstream, nuclear, uranium). "
            "Connected to accounts, thesis nodes, extraction defense, and cascade stages."
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
    print(f"Nodes: {results['nodes_inserted']}, Edges: {results['edges_inserted']}")
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
