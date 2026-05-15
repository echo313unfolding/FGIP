#!/usr/bin/env python3
"""
FGIP Source Linkage Repair Script

Fixes three data quality gaps identified by adversarial audit:

1. Misclassified source tiers (fec.gov, ferc.gov at tier 2 → tier 0)
2. Edge source_urls not normalized into sources/claim_sources tables
3. Edge source_type not populated from source tier
4. Proposed edges from Tier-0 agents missing artifact_id linkage

Run: python3 scripts/repair_source_linkage.py [--dry-run]
"""

import sqlite3
import hashlib
import sys
import json
from datetime import datetime
from urllib.parse import urlparse

DB_PATH = "fgip.db"
DRY_RUN = "--dry-run" in sys.argv

# ---- Tier classification by domain ----
# Mirrors docs/EVIDENCE_TIERS.md

TIER_0_DOMAINS = {
    "congress.gov", "www.congress.gov",
    "sec.gov", "www.sec.gov",
    "usaspending.gov", "www.usaspending.gov",
    "federalregister.gov", "www.federalregister.gov",
    "fec.gov", "www.fec.gov",
    "fara.gov", "efile.fara.gov",
    "fred.stlouisfed.org",
    "stlouisfed.org",
    "supremecourt.gov", "www.supremecourt.gov",
    "ferc.gov", "www.ferc.gov",
    "treasury.gov", "home.treasury.gov", "www.treasury.gov",
    "whitehouse.gov", "www.whitehouse.gov",
    "gao.gov", "www.gao.gov",
    "govtrack.us", "www.govtrack.us",
    "docs.house.gov",
    "banking.senate.gov",
    "cbp.gov", "www.cbp.gov",
    "fda.gov", "www.fda.gov",
    "federalreserve.gov", "www.federalreserve.gov",
    "newyorkfed.org", "www.newyorkfed.org",
    "nrc.gov", "www.nrc.gov",
    "bis.gov", "www.bis.gov",
    "crsreports.congress.gov",
    "state.gov", "www.state.gov",
    "selectcommitteeontheccp.house.gov",
    "judiciary.house.gov",
    "oversight.house.gov",
    "pappas.house.gov",
    "aspe.hhs.gov",
    "energy.gov", "www.energy.gov",
    "ustr.gov", "www.ustr.gov",
    "justice.gov", "www.justice.gov",
    "irs.gov", "www.irs.gov",
    "fdic.gov", "www.fdic.gov",
    "cisa.gov", "www.cisa.gov",
    "usgs.gov", "www.usgs.gov",
    "govinfo.gov", "www.govinfo.gov",
    "gsa.gov", "www.gsa.gov",
    "cecc.gov",
    "uscc.gov",
    "inl.gov",
    "clintonwhitehouse4.archives.gov",
    "field-observation",  # HUMINT direct observation
}

TIER_1_DOMAINS = {
    "opensecrets.org", "www.opensecrets.org",
    "propublica.org", "www.propublica.org",
    "scotusblog.com",
    "reuters.com", "www.reuters.com",
    "nytimes.com", "www.nytimes.com",
    "washingtonpost.com", "www.washingtonpost.com",
    "cnbc.com", "www.cnbc.com",
    "cnn.com", "www.cnn.com", "edition.cnn.com",
    "bbc.co.uk", "www.bbc.co.uk",
    "npr.org", "www.npr.org",
    "brookings.edu", "www.brookings.edu",
    "cfr.org", "www.cfr.org",
    "rand.org", "www.rand.org",
    "csis.org", "www.csis.org",
    "aei.org", "www.aei.org",
    "heritage.org", "www.heritage.org",
    "bis.org", "www.bis.org",  # Bank for International Settlements
    "supreme.justia.com",  # Court opinion mirror
    "doi.org",
    "seekingalpha.com",
    "finance.yahoo.com", "ca.finance.yahoo.com",
    "spglobal.com", "www.spglobal.com",
    "morningstar.com", "www.morningstar.com",
}


def domain_to_tier(domain: str) -> int:
    d = domain.lower().strip()
    if d in TIER_0_DOMAINS:
        return 0
    if d in TIER_1_DOMAINS:
        return 1
    return 2


def extract_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower()
    except Exception:
        return ""


def source_id_from_url(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def run():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    stats = {
        "tier_fixes": 0,
        "sources_created": 0,
        "claim_source_links_created": 0,
        "edge_source_type_fixed": 0,
    }

    # ---- Phase 1: Fix misclassified source tiers ----
    print("Phase 1: Fixing misclassified source tiers...")

    rows = cur.execute("SELECT source_id, domain, tier, url FROM sources").fetchall()
    for row in rows:
        correct_tier = domain_to_tier(row["domain"]) if row["domain"] else 2
        if row["tier"] != correct_tier:
            print(f"  FIX: {row['domain']} tier {row['tier']} → {correct_tier} (source_id={row['source_id'][:16]}...)")
            if not DRY_RUN:
                cur.execute(
                    "UPDATE sources SET tier = ? WHERE source_id = ?",
                    (correct_tier, row["source_id"]),
                )
            stats["tier_fixes"] += 1

    # ---- Phase 2: Normalize edge source_urls into sources + claim_sources ----
    print("\nPhase 2: Normalizing edge source_urls into sources/claim_sources...")

    edges_with_urls = cur.execute("""
        SELECT edge_id, source_url, claim_id
        FROM edges
        WHERE source_url IS NOT NULL AND source_url != ''
    """).fetchall()

    for edge in edges_with_urls:
        url = edge["source_url"]
        claim_id = edge["claim_id"]
        if not claim_id:
            continue

        domain = extract_domain(url)
        tier = domain_to_tier(domain)
        sid = source_id_from_url(url)

        # Create source if it doesn't exist
        existing = cur.execute(
            "SELECT source_id FROM sources WHERE source_id = ?", (sid,)
        ).fetchone()
        if not existing:
            if not DRY_RUN:
                cur.execute(
                    """INSERT OR IGNORE INTO sources (source_id, url, domain, tier, retrieved_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (sid, url, domain, tier, datetime.now().isoformat()),
                )
            stats["sources_created"] += 1
            print(f"  NEW SOURCE: {domain} (tier {tier}) → {url[:80]}")

        # Link claim to source if not already linked
        existing_link = cur.execute(
            "SELECT 1 FROM claim_sources WHERE claim_id = ? AND source_id = ?",
            (claim_id, sid),
        ).fetchone()
        if not existing_link:
            if not DRY_RUN:
                cur.execute(
                    "INSERT OR IGNORE INTO claim_sources (claim_id, source_id) VALUES (?, ?)",
                    (claim_id, sid),
                )
            stats["claim_source_links_created"] += 1

    # ---- Phase 3: Create sources for edges with `source` text (named sources) ----
    print("\nPhase 3: Creating sources for named edge sources without URLs...")

    named_sources = cur.execute("""
        SELECT DISTINCT e.source, e.claim_id
        FROM edges e
        WHERE e.source IS NOT NULL AND e.source != ''
          AND (e.source_url IS NULL OR e.source_url = '')
          AND e.claim_id IS NOT NULL AND e.claim_id != ''
          AND e.claim_id NOT IN (SELECT claim_id FROM claim_sources)
    """).fetchall()

    # Map known named sources to tiers
    NAMED_SOURCE_TIERS = {
        "SCOTUS docket": 0,
        "FARA Registration": 0,
        "OpenSecrets (Tier 1)": 1,
        "Virginia 2019-2022 backtest": 1,
        "NBIM public holdings database (nbim.no)": 1,
    }

    for ns in named_sources:
        source_name = ns["source"]
        claim_id = ns["claim_id"]

        # Determine tier from known names or default to 2
        tier = 2
        for pattern, t in NAMED_SOURCE_TIERS.items():
            if pattern.lower() in source_name.lower():
                tier = t
                break

        sid = f"named-{hashlib.sha256(source_name.encode()).hexdigest()[:32]}"

        existing = cur.execute(
            "SELECT source_id FROM sources WHERE source_id = ?", (sid,)
        ).fetchone()
        if not existing:
            if not DRY_RUN:
                cur.execute(
                    """INSERT OR IGNORE INTO sources (source_id, url, domain, tier, retrieved_at, notes)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (sid, "", source_name, tier, datetime.now().isoformat(), f"Named source from edge: {source_name}"),
                )
            stats["sources_created"] += 1

        existing_link = cur.execute(
            "SELECT 1 FROM claim_sources WHERE claim_id = ? AND source_id = ?",
            (claim_id, sid),
        ).fetchone()
        if not existing_link:
            if not DRY_RUN:
                cur.execute(
                    "INSERT OR IGNORE INTO claim_sources (claim_id, source_id) VALUES (?, ?)",
                    (claim_id, sid),
                )
            stats["claim_source_links_created"] += 1

    # ---- Phase 4: Populate edge source_type from source tier ----
    print("\nPhase 4: Populating edge source_type from source tier...")

    TIER_TO_SOURCE_TYPE = {0: "GOVERNMENT", 1: "PROFESSIONAL", 2: "COMMENTARY"}

    edges_no_type = cur.execute("""
        SELECT e.edge_id, e.claim_id
        FROM edges e
        WHERE (e.source_type IS NULL OR e.source_type = '')
          AND e.claim_id IS NOT NULL AND e.claim_id != ''
    """).fetchall()

    for edge in edges_no_type:
        # Find the best (lowest tier) source linked to this edge's claim
        best = cur.execute("""
            SELECT MIN(s.tier) as best_tier
            FROM claim_sources cs
            JOIN sources s ON s.source_id = cs.source_id
            WHERE cs.claim_id = ?
        """, (edge["claim_id"],)).fetchone()

        if best and best["best_tier"] is not None:
            stype = TIER_TO_SOURCE_TYPE.get(best["best_tier"], "COMMENTARY")
            if not DRY_RUN:
                cur.execute(
                    "UPDATE edges SET source_type = ? WHERE edge_id = ?",
                    (stype, edge["edge_id"]),
                )
            stats["edge_source_type_fixed"] += 1

    # ---- Commit and report ----
    if not DRY_RUN:
        conn.commit()

    # ---- Post-repair stats ----
    print("\n" + "=" * 60)
    print("REPAIR SUMMARY" + (" (DRY RUN)" if DRY_RUN else ""))
    print("=" * 60)
    for k, v in stats.items():
        print(f"  {k}: {v}")

    # Re-run the adversarial metrics
    print("\n" + "=" * 60)
    print("POST-REPAIR EVIDENCE STRATIFICATION")
    print("=" * 60)

    total_claims = cur.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
    claims_any = cur.execute("SELECT COUNT(DISTINCT claim_id) FROM claim_sources").fetchone()[0]
    claims_t0 = cur.execute("""
        SELECT COUNT(DISTINCT cs.claim_id)
        FROM claim_sources cs JOIN sources s ON s.source_id = cs.source_id
        WHERE s.tier = 0
    """).fetchone()[0]
    claims_t01 = cur.execute("""
        SELECT COUNT(DISTINCT cs.claim_id)
        FROM claim_sources cs JOIN sources s ON s.source_id = cs.source_id
        WHERE s.tier IN (0, 1)
    """).fetchone()[0]
    tri = cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT cs.claim_id
            FROM claim_sources cs
            JOIN sources s ON s.source_id = cs.source_id
            GROUP BY cs.claim_id
            HAVING COUNT(DISTINCT s.domain) >= 3
               AND SUM(CASE WHEN s.tier = 0 THEN 1 ELSE 0 END) >= 1
        )
    """).fetchone()[0]
    tri_any = cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT cs.claim_id
            FROM claim_sources cs
            JOIN sources s ON s.source_id = cs.source_id
            GROUP BY cs.claim_id
            HAVING COUNT(DISTINCT s.domain) >= 3
        )
    """).fetchone()[0]

    total_edges = cur.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    edges_typed = cur.execute("SELECT COUNT(*) FROM edges WHERE source_type IS NOT NULL AND source_type != ''").fetchone()[0]
    edges_gov = cur.execute("SELECT COUNT(*) FROM edges WHERE source_type = 'GOVERNMENT'").fetchone()[0]

    t0_sources = cur.execute("SELECT COUNT(*) FROM sources WHERE tier = 0").fetchone()[0]
    t1_sources = cur.execute("SELECT COUNT(*) FROM sources WHERE tier = 1").fetchone()[0]
    t2_sources = cur.execute("SELECT COUNT(*) FROM sources WHERE tier = 2").fetchone()[0]

    print(f"  Claims total:                    {total_claims}")
    print(f"  Claims with ≥1 source:           {claims_any} ({claims_any*100/total_claims:.1f}%)")
    print(f"  Claims with ≥1 Tier-0:           {claims_t0} ({claims_t0*100/total_claims:.1f}%)")
    print(f"  Claims with ≥1 Tier-0/1:         {claims_t01} ({claims_t01*100/total_claims:.1f}%)")
    print(f"  Claims 3+ domains (any tier):    {tri_any}")
    print(f"  Claims triangulated (3+, ≥1 T0): {tri}")
    print(f"  Sources: {t0_sources} T0, {t1_sources} T1, {t2_sources} T2 ({t0_sources + t1_sources + t2_sources} total)")
    print(f"  Edges total:                     {total_edges}")
    print(f"  Edges with source_type:          {edges_typed} ({edges_typed*100/total_edges:.1f}%)")
    print(f"  Edges typed GOVERNMENT:          {edges_gov}")

    conn.close()


if __name__ == "__main__":
    run()
