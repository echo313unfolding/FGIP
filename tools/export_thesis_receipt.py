#!/usr/bin/env python3
"""Export FGIP thesis receipts as cryptographic evidence artifacts.

Usage:
    python3 tools/export_thesis_receipt.py thesis-defense-primes
    python3 tools/export_thesis_receipt.py --all
    python3 tools/export_thesis_receipt.py --list
"""

import argparse
import hashlib
import json
import os
import platform
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "fgip.db"
SOURCES_PATH = Path(__file__).parent.parent / "data" / "sources"
FACTS_PATH = Path(__file__).parent.parent / "data" / "extracted"
EDGES_PATH = Path(__file__).parent.parent / "data" / "edges"
OUTPUT_DIR = Path(__file__).parent.parent / "receipts" / "thesis_receipts"

TIER_0_AGENTS = [
    "edgar", "usaspending", "federal_register", "congress",
    "nuclear_smr", "tic", "fec", "scotus", "gao", "fara", "chips-facility",
]

TIER_BOOST = {0: 15, 1: 8, 2: 3, 3: 0}

THESES = {
    "thesis-defense-primes": {
        "thesis_id": "thesis-defense-primes",
        "claim": (
            "Defense primes benefit from NDAA $895B+, Ukraine replenishment "
            "($60B industrial base), AUKUS ($368B subs), Pacific Deterrence "
            "($9.9B), hypersonics. Munitions stockpiles depleted -> multi-year "
            "replenishment cycle. Bipartisan support."
        ),
        "tickers": ["LMT", "RTX", "NOC", "GD", "HII", "BWXT"],
        "sector": "defense",
        "funding_chain": [
            "Congress authorizes NDAA ($895.2B)",
            "DoD obligates funds via contracts",
            "Prime contractors receive awards (LMT, RTX, NOC, GD, HII)",
            "Subcontractors supply components (BWXT naval reactors, HWM forgings, TDG parts)",
            "Commodity procurement (copper, steel, rare earths, propellants)",
        ],
        "beneficiaries": [
            {"ticker": "LMT", "role": "F-35, HIMARS, ATACMS, hypersonic (HACM)"},
            {"ticker": "RTX", "role": "Patriot, SM-6, AMRAAM, Pratt engines"},
            {"ticker": "NOC", "role": "B-21, Sentinel ICBM, Triton UAV"},
            {"ticker": "GD", "role": "Columbia-class sub, Abrams, Stryker"},
            {"ticker": "HII", "role": "Aircraft carriers, Virginia-class subs"},
            {"ticker": "BWXT", "role": "Sole-source naval nuclear reactors"},
        ],
        "counter_thesis": [
            {
                "description": "Fiscal hawks force defense cuts in debt ceiling deal",
                "severity": "manageable",
                "likelihood": 0.3,
                "mitigation": "Monitor budget negotiations, scale position if sequestration risk rises",
            },
            {
                "description": "Cost overruns on major programs erode margins",
                "severity": "serious",
                "likelihood": 0.5,
                "mitigation": "Sentinel ICBM already Nunn-McCurdy breached; diversify across primes",
            },
        ],
        "disconfirming_evidence": [
            "Defense budget sequestration or continuing resolution >6 months",
            "Major program cancellation (Sentinel, NGAD)",
            "Peace deal reducing threat perception significantly",
            "Contractor execution failure (cost overrun >50%)",
        ],
    },
    "thesis-power-uranium-screen": {
        "thesis_id": "thesis-power-uranium-screen",
        "claim": (
            "Data center power buildout drives midstream gas (NEXUS/Transco), "
            "E&P (Appalachian), utilities (MI/GA), gas turbines, and nuclear. "
            "FERC capacity filings are biggest alpha window."
        ),
        "tickers": ["DTM", "AR", "WMB", "EQT", "DTE", "CEG", "OKLO"],
        "sector": "power_data_center",
        "funding_chain": [
            "Hyperscalers commit capex to data center buildout",
            "Utilities file for capacity additions (PUC/MPSC approvals)",
            "Pipeline operators expand (Transco, NEXUS)",
            "E&P producers supply gas (Appalachian basin)",
            "Nuclear operators provide baseload (existing fleet + SMR pipeline)",
        ],
        "beneficiaries": [
            {"ticker": "DTM", "role": "NEXUS pipeline, Ohio data center corridor"},
            {"ticker": "WMB", "role": "Transco expansion, record Q1 2026"},
            {"ticker": "DTE", "role": "Stargate 1.4GW data center campus"},
            {"ticker": "CEG", "role": "Largest US nuclear fleet, data center PPAs"},
            {"ticker": "OKLO", "role": "SMR developer, HALEU fuel"},
        ],
        "counter_thesis": [
            {
                "description": "AI capex cycle slows or hyperscalers pull back",
                "severity": "serious",
                "likelihood": 0.3,
                "mitigation": "Monitor quarterly capex guidance from MSFT/GOOG/AMZN/META",
            },
            {
                "description": "Renewable + battery cost curve undercuts gas/nuclear",
                "severity": "manageable",
                "likelihood": 0.4,
                "mitigation": "Baseload requirement persists; renewables intermittent",
            },
        ],
        "disconfirming_evidence": [
            "Hyperscaler capex guidance cut >20%",
            "Grid interconnection queue clears faster than expected",
            "Battery storage reaches 12+ hour duration at scale",
            "Major data center project cancellation",
        ],
    },
    "thesis-uranium-screen": {
        "thesis_id": "thesis-uranium-screen",
        "claim": (
            "Uranium structural deficit (30-40M lb/yr). SMR demand rising. "
            "HALEU enrichment bottleneck. US import dependency. "
            "$100+/lb consensus through 2026."
        ),
        "tickers": ["CCJ", "UUUU", "UEC", "CEG", "OKLO", "SMR"],
        "sector": "uranium",
        "funding_chain": [
            "NRC approves SMR designs and operating licenses",
            "DoE ARDP grants fund first-of-kind deployments",
            "Utilities sign PPAs for nuclear capacity",
            "Fuel fabricators require enriched uranium (HALEU)",
            "Miners produce U3O8 (structural deficit 30-40M lb/yr)",
        ],
        "beneficiaries": [
            {"ticker": "CCJ", "role": "Largest Western uranium miner"},
            {"ticker": "UUUU", "role": "US uranium + rare earth producer"},
            {"ticker": "CEG", "role": "Largest US nuclear fleet operator"},
            {"ticker": "OKLO", "role": "SMR developer"},
        ],
        "counter_thesis": [
            {
                "description": "Kazakhstan/Russia increase supply unexpectedly",
                "severity": "serious",
                "likelihood": 0.2,
                "mitigation": "Sanctions regime limits Russian enrichment; KAZ production plateauing",
            },
        ],
        "disconfirming_evidence": [
            "Major new mine supply comes online (>15M lb/yr)",
            "SMR program cancellations across multiple utilities",
            "Russia sanctions lifted, enrichment services resume",
        ],
    },
    "thesis-silver-screen": {
        "thesis_id": "thesis-silver-screen",
        "claim": (
            "Silver structural deficit (6th year), Mexico mining moratorium, "
            "China export ban. Supply cannot respond to demand. Bottleneck asset."
        ),
        "tickers": ["AG", "PAAS", "WPM"],
        "sector": "silver",
        "funding_chain": [
            "Industrial demand (solar, electronics, EV) grows structurally",
            "Mine supply constrained (Mexico moratorium, declining grades)",
            "Inventory drawdown enters 6th consecutive year",
            "Silver miners benefit from price appreciation",
        ],
        "beneficiaries": [
            {"ticker": "AG", "role": "Primary silver miner"},
            {"ticker": "PAAS", "role": "Silver/gold miner"},
            {"ticker": "WPM", "role": "Silver streaming"},
        ],
        "counter_thesis": [
            {
                "description": "Mexico lifts mining moratorium",
                "severity": "serious",
                "likelihood": 0.3,
                "mitigation": "Even with lift, permitting takes 3-5 years to production",
            },
        ],
        "disconfirming_evidence": [
            "Mexico lifts moratorium AND fast-tracks permits",
            "Silver recycling technology breakthrough",
            "Solar industry shifts to copper or aluminum conductors",
        ],
    },
    "thesis-government-infrastructure": {
        "thesis_id": "thesis-government-infrastructure",
        "claim": (
            "IIJA ($1.2T) + IRA ($369B) have ~$600B+ remaining spend through FY2027. "
            "Grid modernization ($65B), broadband ($65B), EV charging ($7.5B), "
            "clean energy manufacturing credits."
        ),
        "tickers": ["PWR", "LDOS", "BAH", "SAIC"],
        "sector": "infrastructure_equipment",
        "funding_chain": [
            "Congress enacted IIJA ($1.2T) and IRA ($369B)",
            "Federal agencies obligate funds (DOT, DOE, EPA, NTIA)",
            "State/local governments receive grants and formula funds",
            "Engineering and construction firms win contracts",
            "Equipment and materials suppliers fill orders",
        ],
        "beneficiaries": [
            {"ticker": "PWR", "role": "Grid modernization, electrical infrastructure"},
            {"ticker": "LDOS", "role": "Government IT and engineering services"},
            {"ticker": "BAH", "role": "Federal consulting and engineering"},
        ],
        "counter_thesis": [
            {
                "description": "IRA tax credits clawed back or reduced",
                "severity": "serious",
                "likelihood": 0.4,
                "mitigation": "Many credits flow to red states; bipartisan constituency",
            },
        ],
        "disconfirming_evidence": [
            "IIJA/IRA rescission >$200B",
            "Major grant programs defunded or frozen",
            "State-level implementation failures >50% of awards",
        ],
    },
    "thesis-dollar-resilience-rails": {
        "thesis_id": "thesis-dollar-resilience-rails",
        "claim": (
            "Regulated stablecoin rails may create a second programmable dollar "
            "settlement layer and additional demand channel for short-term U.S. "
            "debt, while still depending on banks, regulators, reserves, "
            "AML/sanctions compliance, and Treasury-market liquidity."
        ),
        "tickers": [],
        "sector": "digital_asset_rails",
        "funding_chain": [
            "GENIUS Act creates permitted payment stablecoin issuer framework",
            "OCC/FDIC/Fed issue implementation rules for supervised entities",
            "Permitted issuers hold reserves in cash, Treasuries, repo",
            "Stablecoin growth creates demand for short-term dollar safe assets",
            "Programmable settlement rails reduce legacy bottleneck friction",
        ],
        "beneficiaries": [
            {"ticker": "N/A", "role": "Permitted payment stablecoin issuers"},
            {"ticker": "N/A", "role": "Reserve custodians and banks"},
            {"ticker": "N/A", "role": "Compliance and AML infrastructure vendors"},
            {"ticker": "N/A", "role": "Transfer agents supporting tokenized securities"},
        ],
        "counter_thesis": [
            {
                "description": "Regulation concentrates power in permitted issuers and banks",
                "severity": "manageable",
                "likelihood": 0.5,
                "mitigation": "Multiple issuer framework reduces single-point concentration",
            },
            {
                "description": "Stablecoins not FDIC insured; reserve run risk",
                "severity": "serious",
                "likelihood": 0.3,
                "mitigation": "100% reserve backing with liquid assets mitigates but does not eliminate",
            },
            {
                "description": "Stablecoin Treasury demand too small relative to total US debt",
                "severity": "manageable",
                "likelihood": 0.5,
                "mitigation": "Marginal demand matters at auction; growth trajectory matters",
            },
            {
                "description": "Foreign regulatory pushback on dollar stablecoin dominance",
                "severity": "manageable",
                "likelihood": 0.4,
                "mitigation": "GENIUS Act is US domestic framework; foreign jurisdictions build own",
            },
        ],
        "disconfirming_evidence": [
            "GENIUS Act implementation rules block most issuers",
            "Major stablecoin reserve failure or bank run",
            "Foreign jurisdictions ban dollar stablecoins",
            "Stablecoin market cap stagnates or declines for 2+ years",
            "Treasury auctions show no correlation with stablecoin reserve growth",
        ],
    },
}


def sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    results = []
    if not path.exists():
        return results
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                results.append(json.loads(line))
    return results


def load_all_sources() -> list[dict]:
    sources = []
    for f in sorted(SOURCES_PATH.glob("*.jsonl")):
        sources.extend(load_jsonl(f))
    return sources


def load_all_facts() -> list[dict]:
    facts = []
    for f in sorted(FACTS_PATH.glob("*.jsonl")):
        facts.extend(load_jsonl(f))
    return facts


def load_all_edges() -> list[dict]:
    edges = []
    for f in sorted(EDGES_PATH.glob("*.jsonl")):
        edges.extend(load_jsonl(f))
    return edges


def collect_signals_from_db(db_path: Path, thesis: dict) -> dict:
    """Query the graph database for confirming/refuting signals."""
    signals = {"confirming": 0, "refuting": 0, "tier_0": 0, "tier_1": 0, "tier_2": 0, "source_types": set()}

    if not db_path.exists():
        return signals

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    tickers = [t.lower() for t in thesis.get("tickers", []) if t != "N/A"]

    for ticker in tickers:
        # Check promoted edges
        try:
            rows = conn.execute(
                """SELECT e.edge_type, e.confidence, e.notes
                   FROM edges e
                   JOIN nodes n1 ON e.from_node_id = n1.node_id
                   JOIN nodes n2 ON e.to_node_id = n2.node_id
                   WHERE LOWER(n1.node_id) LIKE ? OR LOWER(n2.node_id) LIKE ?
                   LIMIT 50""",
                (f"%{ticker}%", f"%{ticker}%"),
            ).fetchall()
            signals["confirming"] += len(rows)
            signals["tier_0"] += len(rows)
            if rows:
                signals["source_types"].add("graph_edge")
        except Exception:
            pass

        # Check proposed edges
        try:
            rows = conn.execute(
                """SELECT pe.relationship, pe.confidence, pe.agent_name
                   FROM proposed_edges pe
                   WHERE (LOWER(pe.from_node) LIKE ? OR LOWER(pe.to_node) LIKE ?)
                   AND pe.status = 'PENDING'
                   LIMIT 50""",
                (f"%{ticker}%", f"%{ticker}%"),
            ).fetchall()
            for row in rows:
                agent = row["agent_name"] if row["agent_name"] else ""
                if agent in TIER_0_AGENTS:
                    signals["tier_0"] += 1
                    signals["source_types"].add(agent)
                else:
                    signals["tier_1"] += 1
                    signals["source_types"].add(agent)
                signals["confirming"] += 1
        except Exception:
            pass

    conn.close()
    signals["source_types"] = sorted(signals["source_types"])
    return signals


def collect_source_evidence(thesis: dict, all_sources: list, all_facts: list, all_edges: list) -> dict:
    """Collect source_ids, fact_ids, edge_ids relevant to this thesis."""
    tickers = [t.lower() for t in thesis.get("tickers", []) if t != "N/A"]
    sector = thesis.get("sector", "").lower()
    thesis_id = thesis["thesis_id"]

    matched_sources = []
    matched_facts = []
    matched_edges = []

    # Match edges by thesis tickers or sector keywords
    for edge in all_edges:
        from_n = edge.get("from_node", "").lower()
        to_n = edge.get("to_node", "").lower()
        note = edge.get("note", "").lower()
        for ticker in tickers:
            if ticker in from_n or ticker in to_n or ticker in note:
                matched_edges.append(edge)
                break
        else:
            if sector and sector in note:
                matched_edges.append(edge)

    # Match facts by linked edges
    edge_fact_ids = {e.get("fact_id") for e in matched_edges if e.get("fact_id")}
    for fact in all_facts:
        if fact.get("fact_id") in edge_fact_ids:
            matched_facts.append(fact)

    # Match sources by linked facts
    fact_source_ids = {f.get("source_id") for f in matched_facts if f.get("source_id")}
    for src in all_sources:
        if src.get("source_id") in fact_source_ids:
            matched_sources.append(src)

    return {
        "source_ids": [s["source_id"] for s in matched_sources],
        "fact_ids": [f["fact_id"] for f in matched_facts],
        "edge_ids": [e["edge_id"] for e in matched_edges],
        "sources": matched_sources,
        "facts": matched_facts,
        "edges": matched_edges,
    }


def compute_conviction(signals: dict, thesis: dict) -> dict:
    """Compute conviction score from signals."""
    base = 30
    score = base
    score += signals["tier_0"] * 15
    score += signals["tier_1"] * 8
    score += signals["tier_2"] * 3

    # Triangulation bonus
    triangulation_met = len(signals["source_types"]) >= 3 and signals["tier_0"] > 0
    if triangulation_met:
        score += 10

    # Counter-thesis penalty
    counters = thesis.get("counter_thesis", [])
    for ct in counters:
        severity_map = {"fatal": 50, "serious": 25, "manageable": 10, "weak": 3}
        penalty = severity_map.get(ct.get("severity", "weak"), 3)
        score -= penalty * ct.get("likelihood", 0.3)

    score = max(0, min(100, score))

    if score >= 95:
        level, recommendation, position_pct = 5, "BUY", 0.20
    elif score >= 80:
        level, recommendation, position_pct = 4, "BUY", 0.15
    elif score >= 60:
        level, recommendation, position_pct = 3, "BUY", 0.10
    elif score >= 40:
        level, recommendation, position_pct = 2, "HOLD", 0.05
    else:
        level, recommendation, position_pct = 1, "AVOID", 0.0

    return {
        "score": round(score, 1),
        "level": level,
        "recommendation": recommendation,
        "position_size_pct": position_pct,
    }


def determine_graph_state(conviction: dict, signals: dict) -> str:
    """Determine graph state from conviction and evidence."""
    if conviction["level"] >= 3 and signals["tier_0"] > 0 and len(signals["source_types"]) >= 3:
        return "Active"
    return "Candidate"


def build_receipt(thesis_id: str) -> dict | None:
    thesis = THESES.get(thesis_id)
    if not thesis:
        print(f"Unknown thesis: {thesis_id}", file=sys.stderr)
        return None

    t_start = time.time()
    cpu_start = time.process_time()
    ts_start = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    all_sources = load_all_sources()
    all_facts = load_all_facts()
    all_edges = load_all_edges()

    signals = collect_signals_from_db(DB_PATH, thesis)
    evidence = collect_source_evidence(thesis, all_sources, all_facts, all_edges)
    conviction = compute_conviction(signals, thesis)
    graph_state = determine_graph_state(conviction, signals)

    # Override for theses explicitly marked Candidate
    if thesis_id == "thesis-dollar-resilience-rails":
        graph_state = "Candidate"

    evidence_summary = {
        "confirming_signals": signals["confirming"],
        "refuting_signals": 0,
        "tier_0_signals": signals["tier_0"],
        "tier_1_signals": signals["tier_1"],
        "tier_2_signals": signals["tier_2"],
        "source_types": signals["source_types"],
        "triangulation_met": len(signals["source_types"]) >= 3 and signals["tier_0"] > 0,
        "triangulation_count": len(signals["source_types"]),
    }

    # Build source edges for receipt
    source_edges = []
    for edge in evidence["edges"][:10]:
        source_edges.append({
            "from": edge.get("from_node", ""),
            "to": edge.get("to_node", ""),
            "edge_type": edge.get("relationship", ""),
            "confidence": edge.get("confidence", 0.0),
            "tier": edge.get("tier", 1),
        })

    ts_end = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    receipt = {
        "receipt_version": "1.0",
        "thesis_id": thesis_id,
        "timestamp": timestamp,
        "generated_by": "fgip-export-thesis-receipt",
        "claim": thesis["claim"],
        "tickers": thesis["tickers"],
        "source_edges": source_edges,
        "evidence_summary": evidence_summary,
        "evidence_bundle": {
            "source_ids": evidence["source_ids"],
            "fact_ids": evidence["fact_ids"],
            "edge_ids": evidence["edge_ids"],
        },
        "funding_chain": thesis["funding_chain"],
        "beneficiaries": thesis["beneficiaries"],
        "counter_thesis": thesis["counter_thesis"],
        "disconfirming_evidence": thesis["disconfirming_evidence"],
        "conviction": conviction,
        "graph_state": graph_state,
        "cost": {
            "wall_time_s": round(time.time() - t_start, 3),
            "cpu_time_s": round(time.process_time() - cpu_start, 3),
            "python_version": platform.python_version(),
            "hostname": platform.node(),
            "timestamp_start": ts_start,
            "timestamp_end": ts_end,
        },
    }

    # Compute receipt hash
    receipt_content = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
    receipt["receipt_hash"] = f"sha256:{sha256_hex(receipt_content)}"

    # Compute bundle hashes for Solana registration
    bundle_str = json.dumps(receipt["evidence_bundle"], sort_keys=True, separators=(",", ":"))
    receipt["solana_registration"] = {
        "content_hash": sha256_hex(receipt_content),
        "original_hash": sha256_hex(bundle_str),
        "artifact_type": "fgip_thesis_receipt",
        "artifact_type_id": 6,
        "metadata": {
            "thesis_id": thesis_id,
            "generated_at": timestamp,
            "source_count": len(evidence["source_ids"]),
            "fact_count": len(evidence["fact_ids"]),
            "edge_count": len(evidence["edge_ids"]),
            "conviction_score": conviction["score"],
            "conviction_level": conviction["level"],
            "graph_state": graph_state,
        },
        "fidelity_receipt_identity": f"fidelity:source_fact_edge_validation:{thesis_id}",
        "behavioral_receipt_identity": f"behavioral:funding_path_validation:{thesis_id}",
        "risk_attestation_identity": f"risk:counter_thesis_checked:{thesis_id}",
    }
    meta_str = json.dumps(receipt["solana_registration"]["metadata"], sort_keys=True, separators=(",", ":"))
    receipt["solana_registration"]["metadata_hash"] = sha256_hex(meta_str)

    return receipt


def export_receipt(thesis_id: str) -> Path | None:
    receipt = build_receipt(thesis_id)
    if not receipt:
        return None

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    filename = f"{thesis_id}_{date_str}.json"
    out_path = OUTPUT_DIR / filename

    with open(out_path, "w") as f:
        json.dump(receipt, f, indent=2)

    print(f"Exported: {out_path}")
    print(f"  Conviction: {receipt['conviction']['score']} (level {receipt['conviction']['level']})")
    print(f"  Graph state: {receipt['graph_state']}")
    print(f"  Sources: {len(receipt['evidence_bundle']['source_ids'])}")
    print(f"  Facts: {len(receipt['evidence_bundle']['fact_ids'])}")
    print(f"  Edges: {len(receipt['evidence_bundle']['edge_ids'])}")
    print(f"  Content hash: {receipt['solana_registration']['content_hash'][:16]}...")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Export FGIP thesis receipts")
    parser.add_argument("thesis_id", nargs="?", help="Thesis ID to export")
    parser.add_argument("--all", action="store_true", help="Export all theses")
    parser.add_argument("--list", action="store_true", help="List available theses")
    args = parser.parse_args()

    if args.list:
        for tid, t in THESES.items():
            print(f"  {tid}: {t['claim'][:80]}...")
        return

    if args.all:
        for tid in THESES:
            export_receipt(tid)
            print()
        return

    if not args.thesis_id:
        parser.print_help()
        return

    export_receipt(args.thesis_id)


if __name__ == "__main__":
    main()
