#!/usr/bin/env python3
"""
FGIP Graph Insert — 10.8% Extraction Rate ↔ Tariff Three-Layer Chain
Date: 2026-05-14
Source: FRED M2SL, USTR Section 301, EIA MECS 2018, receipts/fgip_tariff_sanctions_test{1,2}.json

Inserts:
  1. Extraction rate node (10.8% = Treasury 4.5% + M2 6.3% - Holder 0%)
  2. Energy intensity gradient node (r=0.709, receipted)
  3. Physical value hierarchy node
  4. M2→deficit causal link
  5. Extraction→tariff formula edge (extraction generates the deficit input)
  6. Energy gradient→tariff gradient edge (product-level mechanism)
  7. Sanctions lever→gradient edge (compliance adjusts energy cost advantage)
  8. GENIUS Act→extraction convergence edge (dynamic correction)
  9. Claims for each receipted finding

Connects existing nodes: tariff-enablement, genius-act-enacted,
stablecoin-treasury-absorption, methodology-asset-protection,
thesis-fertilizer-inflation
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
SESSION_ID = "extraction-tariff-chain-20260514"

# Sources
FRED_M2_URL = "https://fred.stlouisfed.org/series/M2SL"
USTR_301_URL = "https://ustr.gov/issue-areas/enforcement/section-301-investigations"
EIA_MECS_URL = "https://www.eia.gov/consumption/manufacturing/"
RECEIPT_TEST1 = "receipts/fgip_tariff_sanctions_test1.json"
RECEIPT_TEST2 = "receipts/fgip_tariff_sanctions_test2.json"

# ═══════════════════════════════════════════════════════════════════════════════
# NODES
# ═══════════════════════════════════════════════════════════════════════════════

NODES = [
    Node(
        node_id="extraction-rate-10p8",
        node_type=NodeType.ECONOMIC_EVENT,
        name="10.8% Extraction Rate (Static)",
        aliases=["extraction rate", "hidden tax", "10.8% extraction"],
        description=(
            "Static extraction rate on dollar holders: Treasury Yield (4.5%) + "
            "Real Inflation via M2 (6.3%) - Holder Yield (0%) = 10.8%. "
            "The 3.6% gap between M2 (6.3%) and CPI (2.7%) IS the hidden wealth transfer. "
            "Dynamic analysis: 6.3% inflation is CAUSED BY Fed printing to fund Treasury purchases. "
            "GENIUS Act replaces Fed printing with stablecoin demand → M2 drops → "
            "extraction converges to ~4.5% (issuer spread only)."
        ),
        metadata={
            "formula": "Treasury_Yield(4.5%) + M2_Real_Inflation(6.3%) - Holder_Yield(0%)",
            "static_rate": 10.8,
            "dynamic_convergence": 4.5,
            "m2_source": "FRED M2SL",
            "cpi_source": "BLS",
            "backtest": "7/7 predictions confirmed against FRED data",
            "adversarial": "3/3 attacks survived",
        },
    ),
    Node(
        node_id="energy-intensity-gradient",
        node_type=NodeType.THESIS,
        name="Tariff Energy Intensity Gradient",
        aliases=["energy gradient", "tariff gradient layer 2"],
        description=(
            "Product-level tariff rates on China correlate with energy intensity "
            "(r=0.709, p<0.01, R²=0.502). HIGH energy sectors: 44% avg tariff. "
            "LOW energy: 7.5%. Gap: 37pp. Steel/copper/aluminum/EVs/solar/semis "
            "get extra surcharges. The gradient maps onto the energy cost advantage "
            "from sanctioned crude ($10-20/bbl discount)."
        ),
        metadata={
            "pearson_r": 0.709,
            "r_squared": 0.502,
            "p_value": "<0.01",
            "high_energy_tariff_pct": 44.23,
            "low_energy_tariff_pct": 7.5,
            "gap_pp": 36.73,
            "n_categories": 26,
            "receipt": RECEIPT_TEST2,
            "data_sources": [
                "USTR Section 301 tariff lists",
                "EIA MECS 2018",
                "Section 232 proclamations",
            ],
        },
    ),
    Node(
        node_id="physical-value-hierarchy",
        node_type=NodeType.THESIS,
        name="Physical Value Hierarchy",
        aliases=["value hierarchy", "energy-first hierarchy"],
        description=(
            "Energy (primary) → Minerals → Manufacturing → Services/Software → "
            "Financial instruments → Tokenized assets. Each layer derives value "
            "from the one below. When the physical layer constrains (50% DC delayed, "
            "power bottleneck), all layers above reprice. The M2 gap (6.3% vs 2.7%) "
            "= financial claims outrunning physical output. Tariff energy gradient "
            "(r=0.709) = reconnection mechanism. The dollar's value bottoms out at "
            "energy production capacity."
        ),
        metadata={
            "layers": [
                "energy", "minerals", "manufacturing",
                "services", "financial", "tokenized",
            ],
            "key_insight": "financial layer reconnecting to physical layer after decades of decoupling",
        },
    ),
    Node(
        node_id="sanctions-energy-arbitrage",
        node_type=NodeType.ECONOMIC_EVENT,
        name="Sanctions Energy Arbitrage",
        aliases=["sanctioned crude discount", "energy cost advantage"],
        description=(
            "China and India purchase sanctioned Russian/Iranian crude at $10-20/bbl "
            "discount. China converts sanctioned energy into energy-intensive manufactured "
            "goods (steel, aluminum, EVs, solar) at prices domestic producers can't match. "
            "Sanctions evasion does NOT explain tariff rates as a formula (r=0.016, DISPROVEN), "
            "but DOES create the energy cost advantage that the tariff gradient (r=0.709) "
            "is calibrated against. India proof case: tariff dropped 25%→18% after "
            "Russian oil compliance concession (Feb 2026)."
        ),
        metadata={
            "discount_range": "$10-20/bbl",
            "test1_r": 0.016,
            "test1_verdict": "DISPROVEN as formula",
            "test2_r": 0.709,
            "test2_verdict": "SUPPORTED as gradient",
            "india_drop": "25% → 18%",
            "receipt_test1": RECEIPT_TEST1,
            "receipt_test2": RECEIPT_TEST2,
        },
    ),
    Node(
        node_id="m2-deficit-mechanism",
        node_type=NodeType.THESIS,
        name="M2 → Trade Deficit Mechanism",
        aliases=["monetary deficit link"],
        description=(
            "M2 growth at 6.3% inflates dollar-denominated demand. Imports become "
            "cheaper relative to domestic production (especially energy-intensive goods). "
            "Deficit widens. The trade deficit that feeds the tariff formula (Layer 1) "
            "is downstream of the same M2 expansion that creates the 10.8% extraction rate. "
            "The extraction rate and the tariff formula share the same root cause."
        ),
        metadata={
            "m2_growth": "6.3%",
            "mechanism": "M2 expansion → dollar demand inflated → imports cheap → deficit widens",
        },
    ),
]

# ═══════════════════════════════════════════════════════════════════════════════
# CLAIMS
# ═══════════════════════════════════════════════════════════════════════════════

CLAIMS = [
    Claim(
        claim_id="CLAIM-EXTRACTION-RATE-10P8",
        claim_text=(
            "Dollar holders face a 10.8% annual extraction rate: Treasury yield (4.5%) "
            "earned by government + real inflation via M2 (6.3%) eroding purchasing power "
            "- holder yield (0%). The 3.6% gap between M2 (6.3%) and CPI (2.7%) is the "
            "hidden wealth transfer. 7/7 backtest predictions confirmed against FRED data. "
            "3/3 adversarial attacks survived."
        ),
        topic="EXTRACTION_MECHANISM",
        status=ClaimStatus.VERIFIED,
        required_tier=0,
        notes="FRED M2SL backtest, 25-year verification. See data-center-intel.md.",
    ),
    Claim(
        claim_id="CLAIM-ENERGY-GRADIENT-R0709",
        claim_text=(
            "China tariff rates correlate with product energy intensity at r=0.709 "
            "(p<0.01, R²=0.502). High-energy sectors face 44% avg tariff vs 7.5% for "
            "low-energy. 37pp gap. The tariff gradient maps onto energy cost advantages "
            "from sanctioned crude discounts."
        ),
        topic="TARIFF_MECHANISM",
        status=ClaimStatus.VERIFIED,
        required_tier=1,
        notes=f"Receipt: {RECEIPT_TEST2}. 26 product categories, OLS regression.",
    ),
    Claim(
        claim_id="CLAIM-SANCTIONS-NOT-FORMULA",
        claim_text=(
            "Sanctions evasion does NOT explain tariff rates as a systematic formula "
            "(r=0.016, F=0.004). Cross-country residual analysis on 18 countries shows "
            "no statistical relationship. BUT sanctions compliance IS a bilateral lever: "
            "India tariff dropped 25%→18% after Russian oil concession (Feb 2026)."
        ),
        topic="TARIFF_MECHANISM",
        status=ClaimStatus.VERIFIED,
        required_tier=1,
        notes=f"Receipt: {RECEIPT_TEST1}. Refined hypothesis: formula ≠ lever.",
    ),
    Claim(
        claim_id="CLAIM-EXTRACTION-TARIFF-LOOP",
        claim_text=(
            "The 10.8% extraction rate and the tariff three-layer instrument share a "
            "common root: M2 expansion. M2 at 6.3% generates both the purchasing power "
            "loss (extraction) and the trade deficit (tariff formula input). The tariff "
            "energy gradient (r=0.709) targets the products where sanctioned-crude energy "
            "arbitrage gives China the largest cost advantage. GENIUS Act stablecoin "
            "absorption replacing Fed Treasury purchases would reduce M2 growth, "
            "converging extraction to ~4.5% and shrinking the deficit that feeds "
            "the tariff formula."
        ),
        topic="UNIFIED_MECHANISM",
        status=ClaimStatus.EVIDENCED,
        required_tier=1,
        notes=(
            "Synthesis of receipted findings: M2 backtest (VERIFIED), "
            "Test 1 (sanctions formula DISPROVEN), Test 2 (energy gradient VERIFIED), "
            "India lever case, GENIUS Act mechanism. Dynamic convergence is UNTESTED."
        ),
    ),
]

# ═══════════════════════════════════════════════════════════════════════════════
# EDGES
# ═══════════════════════════════════════════════════════════════════════════════

EDGES = [
    # === M2 → Extraction Rate ===
    Edge(
        edge_id=f"E-m2-causes-extraction-{SESSION_ID}",
        edge_type=EdgeType.CAUSED,
        from_node_id="m2-deficit-mechanism",
        to_node_id="extraction-rate-10p8",
        claim_id="CLAIM-EXTRACTION-RATE-10P8",
        assertion_level=AssertionLevel.FACT.value,
        source="FRED M2SL",
        source_url=FRED_M2_URL,
        confidence=0.95,
        notes="M2 growth at 6.3% is the inflation component of the 10.8% extraction rate.",
    ),

    # === M2 → Trade Deficit → Tariff Formula (Layer 1) ===
    Edge(
        edge_id=f"E-m2-causes-deficit-{SESSION_ID}",
        edge_type=EdgeType.CAUSED,
        from_node_id="m2-deficit-mechanism",
        to_node_id="tariff-enablement",
        claim_id="CLAIM-EXTRACTION-TARIFF-LOOP",
        assertion_level=AssertionLevel.INFERENCE.value,
        source="FRED M2SL + Census trade data",
        source_url=FRED_M2_URL,
        confidence=0.80,
        notes=(
            "M2 expansion inflates dollar demand → imports cheaper → deficit widens → "
            "tariff formula rate rises. The same M2 that creates extraction creates "
            "the deficit input to the tariff formula."
        ),
    ),

    # === Extraction Rate shares root with Tariff Formula ===
    Edge(
        edge_id=f"E-extraction-correlates-tariff-{SESSION_ID}",
        edge_type=EdgeType.CORRELATES,
        from_node_id="extraction-rate-10p8",
        to_node_id="tariff-enablement",
        claim_id="CLAIM-EXTRACTION-TARIFF-LOOP",
        assertion_level=AssertionLevel.INFERENCE.value,
        source="FGIP synthesis",
        confidence=0.85,
        notes=(
            "Extraction rate and tariff formula share common cause (M2 expansion). "
            "Not direct causation — correlation via shared root."
        ),
    ),

    # === Sanctions Arbitrage → Energy Gradient (Layer 2) ===
    Edge(
        edge_id=f"E-sanctions-creates-gradient-{SESSION_ID}",
        edge_type=EdgeType.CAUSED,
        from_node_id="sanctions-energy-arbitrage",
        to_node_id="energy-intensity-gradient",
        claim_id="CLAIM-ENERGY-GRADIENT-R0709",
        assertion_level=AssertionLevel.INFERENCE.value,
        source="USTR Section 301 + EIA MECS",
        source_url=USTR_301_URL,
        confidence=0.85,
        notes=(
            "Sanctioned crude discount ($10-20/bbl) gives China cost advantage in "
            "energy-intensive manufacturing. Tariff gradient (r=0.709) calibrated "
            "against this advantage."
        ),
    ),

    # === Energy Gradient → Tariff Enablement ===
    Edge(
        edge_id=f"E-gradient-modulates-tariff-{SESSION_ID}",
        edge_type=EdgeType.MODULATES,
        from_node_id="energy-intensity-gradient",
        to_node_id="tariff-enablement",
        claim_id="CLAIM-ENERGY-GRADIENT-R0709",
        assertion_level=AssertionLevel.FACT.value,
        source="USTR Section 301 tariff lists",
        source_url=USTR_301_URL,
        confidence=0.90,
        notes=(
            "Energy intensity gradient modulates tariff rates at product level. "
            "High energy: 44% avg. Low energy: 7.5%. 37pp gap. r=0.709."
        ),
    ),

    # === Physical Value Hierarchy → Energy Gradient ===
    Edge(
        edge_id=f"E-hierarchy-derives-gradient-{SESSION_ID}",
        edge_type=EdgeType.DERIVES_FROM,
        from_node_id="energy-intensity-gradient",
        to_node_id="physical-value-hierarchy",
        claim_id="CLAIM-EXTRACTION-TARIFF-LOOP",
        assertion_level=AssertionLevel.INFERENCE.value,
        source="FGIP synthesis",
        confidence=0.80,
        notes=(
            "The tariff energy gradient is an expression of the physical value hierarchy: "
            "energy-intensive products sit lower in the hierarchy and face higher tariffs."
        ),
    ),

    # === Physical Value Hierarchy → Extraction Rate ===
    Edge(
        edge_id=f"E-hierarchy-explains-extraction-{SESSION_ID}",
        edge_type=EdgeType.DERIVES_FROM,
        from_node_id="extraction-rate-10p8",
        to_node_id="physical-value-hierarchy",
        claim_id="CLAIM-EXTRACTION-TARIFF-LOOP",
        assertion_level=AssertionLevel.INFERENCE.value,
        source="FGIP synthesis",
        confidence=0.75,
        notes=(
            "M2 gap (6.3% vs 2.7%) = financial claims outrunning physical output. "
            "Extraction rate is the cost of the financial/physical disconnect."
        ),
    ),

    # === GENIUS Act → Reduces Extraction (Dynamic Correction) ===
    Edge(
        edge_id=f"E-genius-reduces-extraction-{SESSION_ID}",
        edge_type=EdgeType.REDUCES,
        from_node_id="genius-act-enacted",
        to_node_id="extraction-rate-10p8",
        claim_id="CLAIM-EXTRACTION-TARIFF-LOOP",
        assertion_level=AssertionLevel.INFERENCE.value,
        source="GENIUS Act mechanism analysis",
        confidence=0.70,
        notes=(
            "GENIUS Act stablecoin absorption replaces Fed printing as Treasury buyer → "
            "M2 growth drops → real inflation drops → extraction converges to ~4.5%. "
            "UNTESTED: requires scale threshold modeling (stablecoin market cap needed)."
        ),
    ),

    # === GENIUS Act → Reduces Deficit Pressure ===
    Edge(
        edge_id=f"E-genius-reduces-deficit-{SESSION_ID}",
        edge_type=EdgeType.REDUCES,
        from_node_id="genius-act-enacted",
        to_node_id="m2-deficit-mechanism",
        claim_id="CLAIM-EXTRACTION-TARIFF-LOOP",
        assertion_level=AssertionLevel.INFERENCE.value,
        source="GENIUS Act mechanism analysis",
        confidence=0.65,
        notes=(
            "If stablecoin absorption reduces M2 growth, deficit pressure decreases, "
            "tariff formula rates would moderate. Dynamic, UNTESTED."
        ),
    ),

    # === Sanctions Arbitrage → India Lever (Layer 3 proof case) ===
    Edge(
        edge_id=f"E-sanctions-lever-india-{SESSION_ID}",
        edge_type=EdgeType.MODULATES,
        from_node_id="sanctions-energy-arbitrage",
        to_node_id="tariff-enablement",
        claim_id="CLAIM-SANCTIONS-NOT-FORMULA",
        assertion_level=AssertionLevel.FACT.value,
        source="Trump administration India tariff adjustment",
        confidence=0.90,
        notes=(
            "Layer 3 lever: India tariff dropped 25%→18% after Russian oil compliance "
            "concession (Feb 2026). Not a formula input (r=0.016), but a bilateral "
            "negotiation tool. Countries that stop feeding energy arbitrage get relief."
        ),
        metadata={
            "layer": 3,
            "proof_case": "India",
            "tariff_before": 25,
            "tariff_after": 18,
            "mechanism": "bilateral_lever",
        },
    ),

    # === Fertilizer thesis connects to hierarchy ===
    Edge(
        edge_id=f"E-fertilizer-derives-hierarchy-{SESSION_ID}",
        edge_type=EdgeType.DERIVES_FROM,
        from_node_id="thesis-fertilizer-inflation",
        to_node_id="physical-value-hierarchy",
        claim_id="CLAIM-EXTRACTION-TARIFF-LOOP",
        assertion_level=AssertionLevel.INFERENCE.value,
        source="FGIP synthesis",
        confidence=0.80,
        notes=(
            "Gas feedstock → nitrogen cost → food price → real inflation. "
            "Fertilizer thesis is a specific instance of energy→manufacturing "
            "value chain in the physical hierarchy."
        ),
    ),

    # === Extraction rate linked to existing asset protection methodology ===
    Edge(
        edge_id=f"E-extraction-informs-protection-{SESSION_ID}",
        edge_type=EdgeType.MODULATES,
        from_node_id="extraction-rate-10p8",
        to_node_id="methodology-asset-protection",
        claim_id="CLAIM-EXTRACTION-RATE-10P8",
        assertion_level=AssertionLevel.INFERENCE.value,
        source="FGIP synthesis",
        confidence=0.85,
        notes=(
            "The 10.8% extraction rate is the threat model for the asset protection "
            "framework. L6 (Inflation Hedge) addresses this directly."
        ),
    ),
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
                print(f"  ! {claim.claim_id}: {e}")

    # Insert nodes
    print("\nNODES:")
    for node in NODES:
        try:
            db.insert_node(node)
            results["nodes_inserted"] += 1
            print(f"  + {node.node_id} ({node.name})")
        except Exception as e:
            if "UNIQUE constraint" in str(e):
                print(f"  = {node.node_id} (exists)")
            else:
                results["errors"].append(f"node {node.node_id}: {e}")
                print(f"  ! {node.node_id}: {e}")

    # Insert edges
    print("\nEDGES:")
    for edge in EDGES:
        try:
            db.insert_edge(edge)
            results["edges_inserted"] += 1
            print(f"  + {edge.from_node_id} --[{edge.edge_type.value}]--> {edge.to_node_id}")
        except Exception as e:
            if "UNIQUE constraint" in str(e):
                print(f"  = {edge.edge_id} (exists)")
            else:
                results["errors"].append(f"edge {edge.edge_id}: {e}")
                print(f"  ! {edge.edge_id}: {e}")

    db.conn.commit()

    # Cost block
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
            "10.8% extraction rate ↔ tariff three-layer chain. "
            "5 nodes, 12 edges, 4 claims. Connects extraction rate through "
            "M2 mechanism to tariff formula (L1), energy gradient (L2, r=0.709), "
            "and sanctions lever (L3, India proof case). GENIUS Act as dynamic "
            "correction reducing both extraction and tariff pressure."
        ),
        "results": results,
        "nodes": [n.node_id for n in NODES],
        "edges": [e.edge_id for e in EDGES],
        "claims": [c.claim_id for c in CLAIMS],
        "receipts_referenced": [RECEIPT_TEST1, RECEIPT_TEST2],
        "cost": cost,
    }

    receipt_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "receipts", f"{SESSION_ID}.json"
    )
    os.makedirs(os.path.dirname(receipt_path), exist_ok=True)
    with open(receipt_path, "w") as f:
        json.dump(receipt, f, indent=2)

    print(f"\n{'='*60}")
    print(f"Session: {SESSION_ID}")
    print(f"Nodes: {results['nodes_inserted']}")
    print(f"Edges: {results['edges_inserted']}")
    print(f"Claims: {results['claims_inserted']}")
    print(f"Errors: {len(results['errors'])}")
    print(f"Receipt: {receipt_path}")
    print(f"Wall time: {cost['wall_time_s']}s")
    print(f"{'='*60}")

    if results["errors"]:
        print("\nERRORS:")
        for e in results["errors"]:
            print(f"  - {e}")

    db.close()
    return 0 if not results["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
