#!/usr/bin/env python3
"""
FGIP Graph Insert — 5GW Citation Chain in America's Future Brief
Date: 2026-05-02
Source: America's Future amicus brief, SCOTUS No. 24-1287 (filed 2025-09-23)

The America's Future brief (William J. Olson, P.C.) cited:
  1. Modern War Institute at West Point — N. Dockery, "The Domestic Fentanyl
     Crisis in Strategic Context: Part III — Responding to China's Drug Warfare"
     (Apr. 2025). Footnote 3, page 9.
  2. Heritage Foundation defense desk — R. Greenway et al., "A Strategy to
     Revitalize the Defense Industrial Base for the 21st Century" (Apr. 7, 2025).
     Footnote 7, page 9.

This is how the 5GW frame entered the SCOTUS record: through citation in a
non-strategic-establishment filer's brief. The doctrine traveled through
America's Future (conservative legal org), not through MWI directly.

Inserts:
  1. Modern War Institute node (ORGANIZATION)
  2. Heritage Foundation defense desk (already exists? check)
  3. CITES_DOCTRINE edges from America's Future brief to MWI and Heritage
  4. Claim node: 5GW doctrine entered SCOTUS via citation routing
  5. Amends CLAIM-5GW-AMICUS-ABSENCE with corrected framing

Depends on: insert_amicus_5gw_frame.py (must run first)
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
SESSION_DATE = "2026-05-02"
SESSION_ID = "5gw-citation-chain-20260502"

BRIEF_URL = "https://www.supremecourt.gov/DocketPDF/24/24-1287/375629/20250923141437495_Learning%20Resources%20v%20Trump%20Amicus%20Brief.pdf"

# ═══════════════════════════════════════════════════════════════════════════════
# NODES
# ═══════════════════════════════════════════════════════════════════════════════

NODES = [
    Node(
        node_id="modern-war-institute",
        node_type=NodeType.ORGANIZATION,
        name="Modern War Institute at West Point",
        aliases=["MWI", "Modern War Institute"],
        description=(
            "Research center at the United States Military Academy (West Point). "
            "Publishes analysis on modern warfare, strategic competition, and "
            "national security threats. Cited in America's Future amicus brief in "
            "Learning Resources v. Trump for N. Dockery's analysis of China's drug "
            "warfare as strategic context for the fentanyl crisis."
        ),
        metadata={
            "type": "military_research_center",
            "affiliation": "United States Military Academy (West Point)",
            "cited_in": "Learning Resources v. Trump, No. 24-1287",
            "cited_work": "Dockery, 'The Domestic Fentanyl Crisis in Strategic Context: Part III — Responding to China's Drug Warfare' (Apr. 2025)",
            "significance": "5GW / economic warfare frame entered SCOTUS record through this citation",
        },
    ),
    # Dockery as author node
    Node(
        node_id="n-dockery",
        node_type=NodeType.PERSON,
        name="N. Dockery",
        aliases=["Dockery"],
        description=(
            "Author at Modern War Institute at West Point. Wrote 'The Domestic "
            "Fentanyl Crisis in Strategic Context: Part III — Responding to China's "
            "Drug Warfare' (Apr. 2025). This paper frames China's fentanyl precursor "
            "export as a form of drug warfare — an explicit 5GW / economic warfare "
            "framing. Cited in America's Future amicus brief in Learning Resources v. Trump."
        ),
        metadata={
            "affiliation": "Modern War Institute at West Point",
            "key_work": "The Domestic Fentanyl Crisis in Strategic Context: Part III",
            "frame": "China's drug warfare as strategic competition",
        },
    ),
]

# ═══════════════════════════════════════════════════════════════════════════════
# CLAIMS
# ═══════════════════════════════════════════════════════════════════════════════

CLAIMS = [
    Claim(
        claim_id="CLAIM-5GW-CITATION-ROUTING",
        claim_text=(
            "The fifth-generation warfare / economic warfare frame entered the "
            "SCOTUS record in Learning Resources v. Trump through citation routing: "
            "America's Future (conservative legal org, William J. Olson P.C.) cited "
            "N. Dockery's Modern War Institute paper on 'China's Drug Warfare' "
            "(fn. 3, p.9) and Heritage Foundation's 'Strategy to Revitalize the "
            "Defense Industrial Base' (fn. 7, p.9). No defense-strategic institution "
            "filed directly as amicus. The doctrine traveled through a non-strategic "
            "filer. This is itself a structural finding: the 5GW frame reaches the "
            "Court through citation rather than institutional standing, meaning the "
            "strategic-warfare argument is present in the record but orphaned from "
            "the institutional apparatus that produces it."
        ),
        topic="SCOTUS",
        status=ClaimStatus.EVIDENCED,
        required_tier=0,
        notes=(
            "Verified by reading America's Future amicus brief PDF from SCOTUS docket. "
            "Dockery citation at footnote 3 page 9. Greenway/Heritage at footnote 7 page 9. "
            "Brief frames tariffs as response to 'one-sided trade war being waged against "
            "the United States' that 'hollowed out' manufacturing and 'undermined our "
            "defense industrial base.'"
        ),
    ),
]

# ═══════════════════════════════════════════════════════════════════════════════
# EDGES
# ═══════════════════════════════════════════════════════════════════════════════

# Check if heritage-foundation node exists; use edge to reference it
# The brief's argument chain: America's Future -> cites MWI (Dockery) + Heritage (Greenway)
# Both citations support the "defense industrial base hollowed out" + "China's drug warfare" frame

EDGES = [
    # America's Future brief CITES MWI Dockery paper
    # Using REPORTS_ON since there's no CITES_DOCTRINE in schema —
    # REPORTS_ON is the closest: "media_outlet → topic, with framing sentiment"
    # But more accurately, this is a reference/citation relationship.
    # Using metadata to capture the citation specifics.
    Edge(
        edge_id=f"E-af-cites-mwi-{SESSION_ID}",
        edge_type=EdgeType.CONFIRMS,  # America's Future argument CONFIRMS MWI doctrine
        from_node_id="americas-future",
        to_node_id="modern-war-institute",
        claim_id="CLAIM-5GW-CITATION-ROUTING",
        assertion_level=AssertionLevel.FACT.value,
        source="America's Future amicus brief, fn. 3, p.9",
        source_url=BRIEF_URL,
        date_occurred="2025-09-23",
        confidence=1.0,
        notes=(
            "America's Future amicus brief cites MWI paper: N. Dockery, 'The Domestic "
            "Fentanyl Crisis in Strategic Context: Part III — Responding to China's "
            "Drug Warfare,' Modern War Institute at West Point (Apr. 2025). Footnote 3, "
            "page 9. This is how the 5GW/economic warfare frame entered the SCOTUS record."
        ),
        metadata={
            "citation_type": "amicus_brief_cites_research",
            "cited_author": "N. Dockery",
            "cited_work": "The Domestic Fentanyl Crisis in Strategic Context: Part III — Responding to China's Drug Warfare",
            "cited_institution": "Modern War Institute at West Point",
            "cited_date": "2025-04",
            "footnote": 3,
            "page": 9,
            "doctrinal_frame": "5GW / China drug warfare as strategic competition",
        },
    ),
    # MWI Dockery paper CONFIRMS fentanyl pipeline as warfare
    Edge(
        edge_id=f"E-mwi-confirms-fentanyl-{SESSION_ID}",
        edge_type=EdgeType.CONFIRMS,
        from_node_id="modern-war-institute",
        to_node_id="crime-fentanyl-pipeline",
        claim_id="CLAIM-5GW-CITATION-ROUTING",
        assertion_level=AssertionLevel.INFERENCE.value,
        source="MWI paper: Dockery, 'China's Drug Warfare' (Apr. 2025)",
        source_url=BRIEF_URL,
        date_occurred="2025-04-01",
        confidence=0.9,
        notes=(
            "MWI frames China's fentanyl precursor export as 'drug warfare' — "
            "an explicit 5GW / strategic competition framing of the fentanyl crisis. "
            "This connects the FGIP fentanyl pipeline node to the defense-strategic "
            "intellectual framework."
        ),
        metadata={
            "doctrinal_frame": "fentanyl_as_drug_warfare",
            "source_institution": "Modern War Institute at West Point",
        },
    ),
    # Dockery EMPLOYED by MWI
    Edge(
        edge_id=f"E-dockery-mwi-{SESSION_ID}",
        edge_type=EdgeType.EMPLOYED,
        from_node_id="n-dockery",
        to_node_id="modern-war-institute",
        assertion_level=AssertionLevel.FACT.value,
        source="MWI publication byline",
        source_url=BRIEF_URL,
        date_occurred="2025-04-01",
        confidence=0.9,
        notes="Author of MWI paper cited in America's Future amicus brief.",
    ),
]


def main():
    t_start = time.time()
    cpu_start = time.process_time()
    start_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

    db = FGIPDatabase(DB_PATH)
    results = {"nodes_inserted": 0, "edges_inserted": 0, "claims_inserted": 0,
               "claim_updates": 0, "errors": []}

    # Insert claims
    for claim in CLAIMS:
        try:
            db.insert_claim(claim)
            results["claims_inserted"] += 1
            print(f"  CLAIM: {claim.claim_id}")
        except Exception as e:
            if "UNIQUE constraint" in str(e):
                print(f"  CLAIM EXISTS: {claim.claim_id}")
            else:
                results["errors"].append(f"claim {claim.claim_id}: {e}")
                print(f"  ERROR: {claim.claim_id}: {e}")

    # Insert nodes
    for node in NODES:
        try:
            receipt = db.insert_node(node)
            results["nodes_inserted"] += 1
            print(f"  NODE: {node.node_id} ({node.name})")
        except Exception as e:
            if "UNIQUE constraint" in str(e):
                print(f"  NODE EXISTS: {node.node_id}")
            else:
                results["errors"].append(f"node {node.node_id}: {e}")
                print(f"  ERROR: {node.node_id}: {e}")

    # Insert edges
    for edge in EDGES:
        try:
            receipt = db.insert_edge(edge)
            results["edges_inserted"] += 1
            print(f"  EDGE: {edge.from_node_id} --[{edge.edge_type.value}]--> {edge.to_node_id}")
        except Exception as e:
            if "UNIQUE constraint" in str(e):
                print(f"  EDGE EXISTS: {edge.edge_id}")
            else:
                results["errors"].append(f"edge {edge.edge_id}: {e}")
                print(f"  ERROR: {edge.edge_id}: {e}")

    # Update the original CLAIM-5GW-AMICUS-ABSENCE with corrected notes
    print("\nAmending CLAIM-5GW-AMICUS-ABSENCE with corrected framing...")
    try:
        db.conn.execute(
            "UPDATE claims SET notes = ? WHERE claim_id = 'CLAIM-5GW-AMICUS-ABSENCE'",
            (
                "CORRECTED 2026-05-02: No defense-strategic institution filed directly as "
                "amicus. However, the 5GW frame IS in the record through citation: America's "
                "Future brief cited MWI (Dockery, 'China's Drug Warfare') at fn.3 p.9 and "
                "Heritage defense desk (Greenway, 'Defense Industrial Base') at fn.7 p.9. "
                "The orphaning thesis partially survives — no defense institution filed "
                "directly — but the doctrine reached the Court through citation routing "
                "via a non-strategic filer. See CLAIM-5GW-CITATION-ROUTING.",
            )
        )
        db.conn.commit()
        results["claim_updates"] += 1
        print("  UPDATED: CLAIM-5GW-AMICUS-ABSENCE notes amended")
    except Exception as e:
        results["errors"].append(f"claim update: {e}")
        print(f"  ERROR updating claim: {e}")

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
            "5GW citation chain: America's Future brief cited MWI (Dockery, "
            "'China's Drug Warfare') and Heritage defense desk (Greenway, "
            "'Defense Industrial Base'). This is how the 5GW frame entered the "
            "SCOTUS record — through citation routing via a non-strategic filer."
        ),
        "key_finding": (
            "The America's Future amicus brief (William J. Olson, P.C.) is the "
            "vehicle that carried the 5GW / economic warfare frame into the "
            "Learning Resources v. Trump SCOTUS record. It cited MWI at West Point "
            "(Dockery, fn.3 p.9) for 'China's Drug Warfare' framing and Heritage "
            "Foundation (Greenway, fn.7 p.9) for defense industrial base argument. "
            "No defense-strategic institution filed directly as amicus, but the "
            "doctrine IS in the record through this citation chain."
        ),
        "brief_carrier": {
            "filer": "America's Future",
            "counsel": "William J. Olson, P.C.",
            "filed": "2025-09-23",
            "position": "pro-tariff (supporting government)",
            "citations": [
                {
                    "author": "N. Dockery",
                    "title": "The Domestic Fentanyl Crisis in Strategic Context: Part III — Responding to China's Drug Warfare",
                    "institution": "Modern War Institute at West Point",
                    "date": "Apr. 2025",
                    "footnote": 3,
                    "page": 9,
                    "frame": "5GW / China drug warfare",
                },
                {
                    "author": "R. Greenway et al.",
                    "title": "A Strategy to Revitalize the Defense Industrial Base for the 21st Century",
                    "institution": "The Heritage Foundation",
                    "date": "Apr. 7, 2025",
                    "footnote": 7,
                    "page": 9,
                    "frame": "defense industrial base revitalization",
                },
            ],
        },
        "results": results,
        "cost": cost,
        "articulation": "articulations/learning_resources_v_trump_5gw_frame.md",
        "source": BRIEF_URL,
    }

    receipt_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "receipts", f"{SESSION_ID}.json"
    )
    with open(receipt_path, "w") as f:
        json.dump(receipt, f, indent=2)

    print(f"\n{'='*60}")
    print(f"Session: {SESSION_ID}")
    print(f"Nodes inserted: {results['nodes_inserted']}")
    print(f"Edges inserted: {results['edges_inserted']}")
    print(f"Claims inserted: {results['claims_inserted']}")
    print(f"Claim updates: {results['claim_updates']}")
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
