#!/usr/bin/env python3
"""
FGIP Domain Extraction & Tier Reclassification

Fixes NULL-domain sources by extracting domain from URL, then reclassifying
tier using the canonical domain→tier map from repair_source_linkage.py.

Found by adversarial audit 2026-05-15:
  - 4,689 tier-2 sources have NULL domain (domain extraction never ran)
  - 443 of those are .gov URLs (sec.gov, federalregister.gov, usaspending.gov, etc.)
  - Reclassifying would upgrade ~2,832 claims from tier-2-only to tier-0/1

Run: python3 scripts/repair_null_domains.py [--dry-run]
"""

import sqlite3
import json
import sys
import time
import resource
import platform
from datetime import datetime
from urllib.parse import urlparse

DB_PATH = "fgip.db"
DRY_RUN = "--dry-run" in sys.argv

# ---- Tier classification by domain (mirrors repair_source_linkage.py) ----

TIER_0_DOMAINS = {
    "congress.gov", "www.congress.gov",
    "sec.gov", "www.sec.gov", "efts.sec.gov",
    "usaspending.gov", "www.usaspending.gov",
    "federalregister.gov", "www.federalregister.gov",
    "fec.gov", "www.fec.gov",
    "fara.gov", "efile.fara.gov",
    "fred.stlouisfed.org", "stlouisfed.org",
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
    "cecc.gov", "uscc.gov", "inl.gov",
    "commerce.gov", "www.commerce.gov",
    "bls.gov", "www.bls.gov",
    "bea.gov", "www.bea.gov",
    "census.gov", "www.census.gov",
    "defense.gov", "www.defense.gov",
    "epa.gov", "www.epa.gov",
    "dot.gov", "www.dot.gov",
    "ed.gov", "www.ed.gov",
    "hhs.gov", "www.hhs.gov",
    "dhs.gov", "www.dhs.gov",
    "opm.gov", "www.opm.gov",
    "ssa.gov", "www.ssa.gov",
    "va.gov", "www.va.gov",
    "sba.gov", "www.sba.gov",
}

TIER_1_DOMAINS = {
    "opensecrets.org", "www.opensecrets.org",
    "propublica.org", "www.propublica.org",
    "scotusblog.com",
    "reuters.com", "www.reuters.com",
    "nytimes.com", "www.nytimes.com",
    "washingtonpost.com", "www.washingtonpost.com",
    "wsj.com", "www.wsj.com",
    "cnbc.com", "www.cnbc.com",
    "cnn.com", "www.cnn.com", "edition.cnn.com",
    "bbc.co.uk", "www.bbc.co.uk", "bbc.com", "www.bbc.com",
    "npr.org", "www.npr.org",
    "apnews.com", "www.apnews.com",
    "ft.com", "www.ft.com",
    "bloomberg.com", "www.bloomberg.com",
    "brookings.edu", "www.brookings.edu",
    "cfr.org", "www.cfr.org",
    "rand.org", "www.rand.org",
    "csis.org", "www.csis.org",
    "aei.org", "www.aei.org",
    "heritage.org", "www.heritage.org",
    "bis.org", "www.bis.org",
    "supreme.justia.com",
    "doi.org",
    "seekingalpha.com",
    "finance.yahoo.com", "ca.finance.yahoo.com",
    "spglobal.com", "www.spglobal.com",
    "morningstar.com", "www.morningstar.com",
    "politico.com", "www.politico.com",
    "thehill.com",
    "forbes.com", "www.forbes.com",
}


def extract_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower().strip()
    except Exception:
        return ""


def domain_to_tier(domain: str) -> int:
    d = domain.lower().strip()
    if d in TIER_0_DOMAINS:
        return 0
    if d in TIER_1_DOMAINS:
        return 1
    return 2


def run():
    t_start = time.time()
    cpu_start = time.process_time()
    start_iso = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # ---- Snapshot before ----
    before = {}
    before['tier_0'] = cur.execute("SELECT COUNT(*) FROM sources WHERE tier=0").fetchone()[0]
    before['tier_1'] = cur.execute("SELECT COUNT(*) FROM sources WHERE tier=1").fetchone()[0]
    before['tier_2'] = cur.execute("SELECT COUNT(*) FROM sources WHERE tier=2").fetchone()[0]
    before['null_domain'] = cur.execute("SELECT COUNT(*) FROM sources WHERE domain IS NULL").fetchone()[0]
    before['tier01_claims'] = cur.execute("""
        SELECT COUNT(DISTINCT cs.claim_id)
        FROM claim_sources cs JOIN sources s ON s.source_id = cs.source_id
        WHERE s.tier <= 1
    """).fetchone()[0]

    stats = {
        "domains_extracted": 0,
        "tier_upgrades_0": 0,
        "tier_upgrades_1": 0,
        "domains_by_new_tier": {"0": {}, "1": {}},
    }

    # ---- Phase 1: Extract domain for NULL-domain sources ----
    print("Phase 1: Extracting domains from NULL-domain source URLs...")

    rows = cur.execute(
        "SELECT source_id, url, tier FROM sources WHERE domain IS NULL AND url IS NOT NULL"
    ).fetchall()

    for row in rows:
        domain = extract_domain(row["url"])
        if not domain:
            continue

        new_tier = domain_to_tier(domain)

        if not DRY_RUN:
            cur.execute(
                "UPDATE sources SET domain = ?, tier = ? WHERE source_id = ?",
                (domain, new_tier, row["source_id"])
            )

        stats["domains_extracted"] += 1

        if new_tier < row["tier"]:
            if new_tier == 0:
                stats["tier_upgrades_0"] += 1
                stats["domains_by_new_tier"]["0"][domain] = \
                    stats["domains_by_new_tier"]["0"].get(domain, 0) + 1
            elif new_tier == 1:
                stats["tier_upgrades_1"] += 1
                stats["domains_by_new_tier"]["1"][domain] = \
                    stats["domains_by_new_tier"]["1"].get(domain, 0) + 1

    if not DRY_RUN:
        conn.commit()

    # ---- Snapshot after ----
    after = {}
    after['tier_0'] = cur.execute("SELECT COUNT(*) FROM sources WHERE tier=0").fetchone()[0]
    after['tier_1'] = cur.execute("SELECT COUNT(*) FROM sources WHERE tier=1").fetchone()[0]
    after['tier_2'] = cur.execute("SELECT COUNT(*) FROM sources WHERE tier=2").fetchone()[0]
    after['null_domain'] = cur.execute("SELECT COUNT(*) FROM sources WHERE domain IS NULL").fetchone()[0]
    after['tier01_claims'] = cur.execute("""
        SELECT COUNT(DISTINCT cs.claim_id)
        FROM claim_sources cs JOIN sources s ON s.source_id = cs.source_id
        WHERE s.tier <= 1
    """).fetchone()[0]

    # ---- Full stratified recount ----
    total_claims = cur.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
    any_source = cur.execute("SELECT COUNT(DISTINCT claim_id) FROM claim_sources").fetchone()[0]
    analytical = cur.execute("SELECT COUNT(*) FROM claims WHERE topic != 'SIGNAL_LAYER'").fetchone()[0]
    analytical_source = cur.execute("""
        SELECT COUNT(DISTINCT cs.claim_id)
        FROM claim_sources cs JOIN claims c ON c.claim_id = cs.claim_id
        WHERE c.topic != 'SIGNAL_LAYER'
    """).fetchone()[0]
    analytical_tier01 = cur.execute("""
        SELECT COUNT(DISTINCT cs.claim_id)
        FROM claim_sources cs
        JOIN sources s ON s.source_id = cs.source_id
        JOIN claims c ON c.claim_id = cs.claim_id
        WHERE c.topic != 'SIGNAL_LAYER' AND s.tier <= 1
    """).fetchone()[0]

    conn.close()

    # ---- Cost block ----
    cost = {
        'wall_time_s': round(time.time() - t_start, 3),
        'cpu_time_s': round(time.process_time() - cpu_start, 3),
        'peak_memory_mb': round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        'python_version': platform.python_version(),
        'hostname': platform.node(),
        'timestamp_start': start_iso,
        'timestamp_end': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
    }

    # ---- Receipt ----
    receipt = {
        "operation": "repair_null_domains",
        "dry_run": DRY_RUN,
        "before": before,
        "after": after if not DRY_RUN else "(dry run — no changes)",
        "stats": stats,
        "stratified_recount": {
            "total_claims": total_claims,
            "any_source_pct": round(any_source * 100.0 / total_claims, 1),
            "tier01_claims": after['tier01_claims'],
            "tier01_pct": round(after['tier01_claims'] * 100.0 / total_claims, 1),
            "analytical_claims": analytical,
            "analytical_source_pct": round(analytical_source * 100.0 / analytical, 1),
            "analytical_tier01": analytical_tier01,
            "analytical_tier01_pct": round(analytical_tier01 * 100.0 / analytical, 1),
        },
        "cost": cost,
    }

    # ---- Report ----
    print(f"\n{'=== DRY RUN ===' if DRY_RUN else '=== APPLIED ==='}")
    print(f"Domains extracted:  {stats['domains_extracted']}")
    print(f"Tier upgrades → 0: {stats['tier_upgrades_0']}")
    print(f"Tier upgrades → 1: {stats['tier_upgrades_1']}")
    print(f"\nBefore: tier-0={before['tier_0']}, tier-1={before['tier_1']}, "
          f"tier-2={before['tier_2']}, null-domain={before['null_domain']}")
    if not DRY_RUN:
        print(f"After:  tier-0={after['tier_0']}, tier-1={after['tier_1']}, "
              f"tier-2={after['tier_2']}, null-domain={after['null_domain']}")
    print(f"\nTier-0/1 claims: {before['tier01_claims']} → {after['tier01_claims']}")
    print(f"\n--- Stratified Recount ---")
    sc = receipt["stratified_recount"]
    print(f"Total claims:          {sc['total_claims']}")
    print(f"Any source:            {sc['any_source_pct']}%")
    print(f"Tier-0/1 (all):        {sc['tier01_claims']} ({sc['tier01_pct']}%)")
    print(f"Analytical claims:     {sc['analytical_claims']}")
    print(f"Analytical sourced:    {sc['analytical_source_pct']}%")
    print(f"Analytical tier-0/1:   {sc['analytical_tier01']} ({sc['analytical_tier01_pct']}%)")

    if stats["domains_by_new_tier"]["0"]:
        print(f"\nTier-0 upgrades by domain:")
        for d, c in sorted(stats["domains_by_new_tier"]["0"].items(), key=lambda x: -x[1]):
            print(f"  {d}: {c}")
    if stats["domains_by_new_tier"]["1"]:
        print(f"\nTier-1 upgrades by domain:")
        for d, c in sorted(stats["domains_by_new_tier"]["1"].items(), key=lambda x: -x[1]):
            print(f"  {d}: {c}")

    # ---- Write receipt ----
    receipt_path = f"receipts/repair_null_domains_{datetime.now().strftime('%Y%m%dT%H%M%SZ')}.json"
    import os
    os.makedirs("receipts", exist_ok=True)
    with open(receipt_path, "w") as f:
        json.dump(receipt, f, indent=2)
    print(f"\nReceipt: {receipt_path}")


if __name__ == "__main__":
    run()
