#!/usr/bin/env python3
"""
FGIP Graph Insert — Learning Resources v. Trump Amicus Completion + Kavanaugh Dissent
Date: 2026-05-02
Source: SCOTUS docket No. 24-1287, SCOTUSblog, Lawfare, Legalytics analysis

Inserts:
  1. Missing pro-tariff amicus filer nodes (AFPI, ACLJ, America's Future,
     Rep. Issa, Prof. Squitieri, Jill Homan)
  2. FILED_AMICUS edges for all 6 pro-tariff filers
  3. Position metadata on ALL amicus edges (pro-tariff / anti-tariff)
  4. Kavanaugh node + RULED_ON edge with dissent metadata
  5. Claim: 5GW frame absent from amicus record (the key finding)

Does NOT insert:
  - SWF nodes (queued for separate insert)
  - 5GW intellectual framework nodes (queued MEDIUM priority)
  - Full anti-tariff amicus list (13/37 already in graph, rest are queue)

Articulation anchor: articulations/learning_resources_v_trump_5gw_frame.md
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
SESSION_ID = "amicus-5gw-frame-20260502"

SCOTUS_DOCKET_URL = "https://www.supremecourt.gov/search.aspx?filename=/docket/docketfiles/html/public/24-1287.html"
SCOTUSBLOG_URL = "https://www.scotusblog.com/cases/case-files/learning-resources-inc-v-trump/"

# ═══════════════════════════════════════════════════════════════════════════════
# NODES
# ═══════════════════════════════════════════════════════════════════════════════

NODES = [
    # Pro-tariff amicus filers (missing from graph)
    Node(
        node_id="america-first-policy-institute",
        node_type=NodeType.ORGANIZATION,
        name="America First Policy Institute",
        aliases=["AFPI"],
        description=(
            "Trump-aligned policy institute. Filed amicus in Learning Resources v. Trump "
            "supporting government's tariff authority under IEEPA. Argued Congress expressly "
            "granted broad presidential discretion to regulate imports."
        ),
        metadata={
            "type": "policy_institute",
            "alignment": "Trump administration",
            "amicus_position": "pro-tariff",
            "case": "Learning Resources v. Trump, No. 24-1287",
        },
    ),
    Node(
        node_id="american-center-for-law-and-justice",
        node_type=NodeType.ORGANIZATION,
        name="American Center for Law and Justice",
        aliases=["ACLJ"],
        description=(
            "Religious conservative legal organization (Jay Sekulow). Filed amicus in "
            "Learning Resources v. Trump supporting government. Argued judicial deference "
            "in foreign affairs is essential — courts lack access to confidential executive "
            "branch information underlying foreign policy decisions."
        ),
        metadata={
            "type": "legal_organization",
            "alignment": "religious conservative",
            "amicus_position": "pro-tariff",
            "case": "Learning Resources v. Trump, No. 24-1287",
            "argument_frame": "foreign_affairs_deference",
        },
    ),
    Node(
        node_id="americas-future",
        node_type=NodeType.ORGANIZATION,
        name="America's Future",
        aliases=[],
        description=(
            "Conservative legal organization. Filed amicus in Learning Resources v. Trump "
            "supporting government's tariff authority. Represented by William J. Olson, P.C."
        ),
        metadata={
            "type": "legal_organization",
            "alignment": "conservative",
            "amicus_position": "pro-tariff",
            "case": "Learning Resources v. Trump, No. 24-1287",
        },
    ),
    Node(
        node_id="rep-darrell-issa",
        node_type=NodeType.PERSON,
        name="U.S. Representative Darrell Issa",
        aliases=["Darrell Issa"],
        description=(
            "U.S. Representative (R-CA). Filed amicus brief (with others) in Learning "
            "Resources v. Trump supporting government's tariff authority under IEEPA."
        ),
        metadata={
            "party": "Republican",
            "state": "CA",
            "amicus_position": "pro-tariff",
            "case": "Learning Resources v. Trump, No. 24-1287",
        },
    ),
    Node(
        node_id="prof-chad-squitieri",
        node_type=NodeType.PERSON,
        name="Professor Chad Squitieri",
        aliases=["Chad Squitieri"],
        description=(
            "Law professor (Catholic University). Filed amicus in Learning Resources v. Trump "
            "supporting government on statutory interpretation grounds."
        ),
        metadata={
            "institution": "Catholic University of America",
            "amicus_position": "pro-tariff",
            "case": "Learning Resources v. Trump, No. 24-1287",
        },
    ),
    Node(
        node_id="jill-homan",
        node_type=NodeType.PERSON,
        name="Jill Homan",
        aliases=[],
        description=(
            "Individual filer (Trump policy advisor). Filed amicus in Learning Resources v. Trump "
            "supporting government's tariff authority."
        ),
        metadata={
            "amicus_position": "pro-tariff",
            "case": "Learning Resources v. Trump, No. 24-1287",
        },
    ),
    # Kavanaugh — key dissenter
    Node(
        node_id="justice-kavanaugh",
        node_type=NodeType.PERSON,
        name="Justice Brett Kavanaugh",
        aliases=["Brett Kavanaugh", "Kavanaugh"],
        description=(
            "Associate Justice, Supreme Court. Authored 63-page dissent in Learning Resources "
            "v. Trump (joined by Thomas and Alito). Argued IEEPA plainly authorizes tariffs "
            "and the major questions doctrine should not apply in foreign affairs contexts. "
            "Cited Youngstown Category One, Dames & Moore, Hamdi, and Nixon's 1971 TWEA tariff "
            "as precedent. The only place in the case record where the strategic-competition / "
            "foreign-affairs-deference frame appears at the Supreme Court level."
        ),
        metadata={
            "role": "Associate Justice, SCOTUS",
            "appointed_by": "Trump",
            "dissent_case": "Learning Resources v. Trump, No. 24-1287",
            "dissent_joined_by": ["Thomas", "Alito"],
            "dissent_frame": "foreign_affairs_exception_to_MQD",
        },
    ),
]

# ═══════════════════════════════════════════════════════════════════════════════
# CLAIMS
# ═══════════════════════════════════════════════════════════════════════════════

CLAIMS = [
    Claim(
        claim_id="CLAIM-5GW-AMICUS-ABSENCE",
        claim_text=(
            "In Learning Resources v. Trump (No. 24-1287), zero pro-tariff amicus briefs "
            "came from defense-strategic institutions (MWI, CSIS, FDD, AWC, NWC, AEI defense "
            "desk, Heritage defense desk). The 5GW / economic-warfare frame had no amicus "
            "representation on the pro-tariff side. The national security establishment "
            "(former CIA director, NSA director, ambassadors, military officials) filed "
            "ANTI-tariff. The orphaning of the strategic-competition frame in the legal "
            "record is isomorphic to its orphaning in the policy apparatus."
        ),
        topic="SCOTUS",
        status=ClaimStatus.EVIDENCED,
        required_tier=0,
        notes=(
            "Verified from SCOTUS docket and SCOTUSblog. 44 briefs total: 37 anti-tariff, "
            "6 pro-tariff (AFPI, ACLJ, America's Future, Issa, Squitieri, Homan), 1 neither. "
            "AEI filed anti-tariff. Former Senior Military Officials filed anti-tariff."
        ),
    ),
    Claim(
        claim_id="CLAIM-KAVANAUGH-FOREIGN-AFFAIRS-MQD",
        claim_text=(
            "Kavanaugh's dissent in Learning Resources v. Trump argued the major questions "
            "doctrine should not apply to foreign affairs statutes. Congress intentionally "
            "grants broad presidential discretion in foreign affairs, so demanding clear "
            "authorization misreads congressional intent. Cited Youngstown, Dames & Moore, "
            "Hamdi. This is the only place in the case record where the strategic-competition "
            "frame appears, though expressed as constitutional deference rather than explicit "
            "5GW doctrine."
        ),
        topic="SCOTUS",
        status=ClaimStatus.EVIDENCED,
        required_tier=0,
        notes="Verified from Lawfare, Legalytics, Yale JReg analysis of opinion.",
    ),
]

# ═══════════════════════════════════════════════════════════════════════════════
# EDGES
# ═══════════════════════════════════════════════════════════════════════════════

EDGES = [
    # Pro-tariff FILED_AMICUS edges
    Edge(
        edge_id=f"E-amicus-afpi-lrt-{SESSION_ID}",
        edge_type=EdgeType.FILED_AMICUS,
        from_node_id="america-first-policy-institute",
        to_node_id="learning-resources-v-trump",
        claim_id="CLAIM-5GW-AMICUS-ABSENCE",
        assertion_level=AssertionLevel.FACT.value,
        source="SCOTUS docket No. 24-1287",
        source_url=SCOTUS_DOCKET_URL,
        date_occurred="2025-09-23",
        confidence=1.0,
        notes="Pro-tariff. Supporting government. IEEPA grants broad authority.",
        metadata={"position": "pro-tariff", "side": "government"},
    ),
    Edge(
        edge_id=f"E-amicus-aclj-lrt-{SESSION_ID}",
        edge_type=EdgeType.FILED_AMICUS,
        from_node_id="american-center-for-law-and-justice",
        to_node_id="learning-resources-v-trump",
        claim_id="CLAIM-5GW-AMICUS-ABSENCE",
        assertion_level=AssertionLevel.FACT.value,
        source="SCOTUS docket No. 24-1287",
        source_url=SCOTUS_DOCKET_URL,
        date_occurred="2025-09-23",
        confidence=1.0,
        notes="Pro-tariff. Supporting government. Foreign affairs deference argument.",
        metadata={"position": "pro-tariff", "side": "government"},
    ),
    Edge(
        edge_id=f"E-amicus-af-lrt-{SESSION_ID}",
        edge_type=EdgeType.FILED_AMICUS,
        from_node_id="americas-future",
        to_node_id="learning-resources-v-trump",
        claim_id="CLAIM-5GW-AMICUS-ABSENCE",
        assertion_level=AssertionLevel.FACT.value,
        source="SCOTUS docket No. 24-1287",
        source_url=SCOTUS_DOCKET_URL,
        date_occurred="2025-09-23",
        confidence=1.0,
        notes="Pro-tariff. Supporting government. Presidential authority.",
        metadata={"position": "pro-tariff", "side": "government"},
    ),
    Edge(
        edge_id=f"E-amicus-issa-lrt-{SESSION_ID}",
        edge_type=EdgeType.FILED_AMICUS,
        from_node_id="rep-darrell-issa",
        to_node_id="learning-resources-v-trump",
        claim_id="CLAIM-5GW-AMICUS-ABSENCE",
        assertion_level=AssertionLevel.FACT.value,
        source="SCOTUS docket No. 24-1287",
        source_url=SCOTUS_DOCKET_URL,
        date_occurred="2025-09-23",
        confidence=1.0,
        notes="Pro-tariff. Supporting government. Legislative intent.",
        metadata={"position": "pro-tariff", "side": "government"},
    ),
    Edge(
        edge_id=f"E-amicus-squitieri-lrt-{SESSION_ID}",
        edge_type=EdgeType.FILED_AMICUS,
        from_node_id="prof-chad-squitieri",
        to_node_id="learning-resources-v-trump",
        claim_id="CLAIM-5GW-AMICUS-ABSENCE",
        assertion_level=AssertionLevel.FACT.value,
        source="SCOTUS docket No. 24-1287",
        source_url=SCOTUS_DOCKET_URL,
        date_occurred="2025-09-23",
        confidence=1.0,
        notes="Pro-tariff. Supporting government. Statutory interpretation.",
        metadata={"position": "pro-tariff", "side": "government"},
    ),
    Edge(
        edge_id=f"E-amicus-homan-lrt-{SESSION_ID}",
        edge_type=EdgeType.FILED_AMICUS,
        from_node_id="jill-homan",
        to_node_id="learning-resources-v-trump",
        claim_id="CLAIM-5GW-AMICUS-ABSENCE",
        assertion_level=AssertionLevel.FACT.value,
        source="SCOTUS docket No. 24-1287",
        source_url=SCOTUS_DOCKET_URL,
        date_occurred="2025-09-23",
        confidence=1.0,
        notes="Pro-tariff. Supporting government. Executive authority.",
        metadata={"position": "pro-tariff", "side": "government"},
    ),
    # Kavanaugh dissent edge
    Edge(
        edge_id=f"E-kavanaugh-dissent-lrt-{SESSION_ID}",
        edge_type=EdgeType.RULED_ON,
        from_node_id="justice-kavanaugh",
        to_node_id="learning-resources-v-trump",
        claim_id="CLAIM-KAVANAUGH-FOREIGN-AFFAIRS-MQD",
        assertion_level=AssertionLevel.FACT.value,
        source="607 U.S. ___ (2026), Kavanaugh dissent",
        source_url="https://www.supremecourt.gov/opinions/25pdf/24-1287_4gcj.pdf",
        date_occurred="2026-02-20",
        confidence=1.0,
        notes=(
            "DISSENT (63 pages). Joined by Thomas and Alito. IEEPA plainly authorizes "
            "tariffs. MQD should not apply in foreign affairs. Cited Youngstown Cat. 1, "
            "Dames & Moore, Hamdi, Nixon 1971 TWEA tariff. Only place in case record "
            "where strategic-competition / foreign-affairs-deference frame appears."
        ),
        metadata={
            "vote": "dissent",
            "joined_by": ["Thomas", "Alito"],
            "pages": 63,
            "frame": "foreign_affairs_exception_to_MQD",
            "key_precedents": ["Youngstown", "Dames & Moore", "Hamdi", "Nixon 1971 TWEA"],
        },
    ),
]

# ═══════════════════════════════════════════════════════════════════════════════
# Position tag updates for existing amicus edges
# ═══════════════════════════════════════════════════════════════════════════════

# These are the 13 existing FILED_AMICUS edges that need position metadata added
EXISTING_AMICUS_POSITION_UPDATES = [
    # Anti-tariff (supporting challengers) — exact node IDs from graph
    ("us-chamber-of-commerce", "anti-tariff"),
    ("cato-institute", "anti-tariff"),
    ("john-danforth", "anti-tariff"),
    ("trilateral-commission", "anti-tariff"),
    ("new-york", "anti-tariff"),
    ("company-linde", "anti-tariff"),
    ("brennan-center", "anti-tariff"),
    ("sec", "anti-tariff"),
    # Pro-tariff (these are in existing graph but had no position tag from bulk approve)
    ("antero-midstream", "pro-tariff"),
    ("teradyne", "pro-tariff"),
    ("ORG_SOUTHERN_COMPANY", "pro-tariff"),
    ("azz-inc", "pro-tariff"),
    ("first-majestic-silver", "pro-tariff"),
]


def main():
    t_start = time.time()
    cpu_start = time.process_time()
    start_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

    db = FGIPDatabase(DB_PATH)
    results = {"nodes_inserted": 0, "edges_inserted": 0, "claims_inserted": 0,
               "position_updates": 0, "errors": []}

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

    # Update position metadata on existing amicus edges
    print("\nUpdating position tags on existing amicus edges...")
    for from_id, position in EXISTING_AMICUS_POSITION_UPDATES:
        try:
            # Find the edge and update its metadata
            rows = db.conn.execute(
                "SELECT edge_id, metadata FROM edges WHERE from_node_id = ? "
                "AND to_node_id = 'learning-resources-v-trump' AND edge_type = 'FILED_AMICUS'",
                (from_id,)
            ).fetchall()
            for row in rows:
                edge_id = row[0]
                existing_meta = json.loads(row[1]) if row[1] else {}
                existing_meta["position"] = position
                existing_meta["side"] = "challengers" if position == "anti-tariff" else "government"
                db.conn.execute(
                    "UPDATE edges SET metadata = ? WHERE edge_id = ?",
                    (json.dumps(existing_meta), edge_id)
                )
                results["position_updates"] += 1
                print(f"  UPDATED: {from_id} -> position={position}")
            if not rows:
                # Try with alternate node IDs
                alt_rows = db.conn.execute(
                    "SELECT edge_id, from_node_id FROM edges "
                    "WHERE to_node_id = 'learning-resources-v-trump' AND edge_type = 'FILED_AMICUS' "
                    "AND from_node_id LIKE ?",
                    (f"%{from_id.split('-')[0]}%",)
                ).fetchall()
                if alt_rows:
                    print(f"  NOTE: {from_id} not found, but similar: {[r[1] for r in alt_rows]}")
                else:
                    print(f"  SKIP: {from_id} — edge not found in graph")
        except Exception as e:
            results["errors"].append(f"update {from_id}: {e}")
            print(f"  ERROR updating {from_id}: {e}")

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
            "Learning Resources v. Trump amicus completion + Kavanaugh dissent. "
            "Key finding: 5GW frame had ZERO amicus representation on pro-tariff side. "
            "National security establishment filed ANTI-tariff."
        ),
        "results": results,
        "cost": cost,
        "articulation": "articulations/learning_resources_v_trump_5gw_frame.md",
        "sources": [SCOTUS_DOCKET_URL, SCOTUSBLOG_URL],
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
    print(f"Nodes inserted: {results['nodes_inserted']}")
    print(f"Edges inserted: {results['edges_inserted']}")
    print(f"Claims inserted: {results['claims_inserted']}")
    print(f"Position updates: {results['position_updates']}")
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
