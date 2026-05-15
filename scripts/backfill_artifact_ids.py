#!/usr/bin/env python3
"""
Backfill artifact_id on existing proposed_edges.

For each Tier-0 agent (congress, usaspending, edgar, fec, etc.),
matches proposed_edges to artifact_queue entries by agent name.

Also registers sources and creates claim_sources links for promoted
edges that have source info but broken linkage.

Run: python3 scripts/backfill_artifact_ids.py [--dry-run]
"""

import sqlite3
import hashlib
import sys
from datetime import datetime
from urllib.parse import urlparse

DB_PATH = "fgip.db"
DRY_RUN = "--dry-run" in sys.argv

# Agent → source tier mapping
AGENT_TIERS = {
    "congress": 0,
    "usaspending": 0,
    "edgar": 0,
    "fec": 0,
    "scotus": 0,
    "federal_register": 0,
    "fara": 0,
    "gao": 0,
    "nuclear_smr": 0,
    "tic": 0,
    "opensecrets": 1,
    "supply_chain_extractor": 1,
    "stablecoin": 1,
    "rss": 2,
    "podcast": 2,
    "narrative": 2,
    "causal": 2,
    "chips-facility": 1,
    "pipeline_orchestrator": 2,
}

# Tier-0 source type label for edges
TIER_LABELS = {0: "GOVERNMENT", 1: "PROFESSIONAL", 2: "COMMENTARY"}

# Domain → tier (mirrors repair_source_linkage.py)
TIER_0_DOMAINS = {
    "congress.gov", "www.congress.gov", "sec.gov", "www.sec.gov",
    "usaspending.gov", "www.usaspending.gov", "federalregister.gov",
    "www.federalregister.gov", "fec.gov", "www.fec.gov", "fara.gov",
    "efile.fara.gov", "fred.stlouisfed.org", "stlouisfed.org",
    "supremecourt.gov", "www.supremecourt.gov", "ferc.gov", "www.ferc.gov",
    "treasury.gov", "home.treasury.gov", "whitehouse.gov", "gao.gov",
    "govtrack.us", "docs.house.gov", "nrc.gov", "energy.gov",
    "ustr.gov", "justice.gov", "fdic.gov", "govinfo.gov",
}


def domain_to_tier(domain):
    d = domain.lower().strip()
    if d in TIER_0_DOMAINS:
        return 0
    return 2


def run():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    stats = {
        "pe_artifact_backfilled": 0,
        "edge_source_type_fixed": 0,
        "sources_created": 0,
        "claim_source_links": 0,
        "orphan_claims_linked": 0,
    }

    # ---- Phase 1: Backfill artifact_id on proposed_edges ----
    # Match proposed_edges to artifact_queue by agent name
    print("Phase 1: Backfilling artifact_id on proposed_edges...")

    # Get all artifact_queue entries grouped by source_id (agent name)
    artifacts = cur.execute("""
        SELECT artifact_id, source_id, url, artifact_path, created_at
        FROM artifact_queue
        ORDER BY created_at DESC
    """).fetchall()

    # Build lookup: agent_name → list of artifact_ids
    agent_artifacts = {}
    for a in artifacts:
        agent = a["source_id"] or ""
        if agent not in agent_artifacts:
            agent_artifacts[agent] = []
        agent_artifacts[agent].append(a["artifact_id"])

    # For each agent, update proposed_edges that lack artifact_id
    for agent_name, artifact_ids in agent_artifacts.items():
        if not artifact_ids:
            continue
        # Use the most recent artifact for this agent
        latest_artifact_id = artifact_ids[0]

        count = cur.execute("""
            SELECT COUNT(*) FROM proposed_edges
            WHERE agent_name = ? AND (artifact_id IS NULL OR artifact_id = '')
        """, (agent_name,)).fetchone()[0]

        if count > 0 and not DRY_RUN:
            cur.execute("""
                UPDATE proposed_edges
                SET artifact_id = ?
                WHERE agent_name = ? AND (artifact_id IS NULL OR artifact_id = '')
            """, (latest_artifact_id, agent_name))
            stats["pe_artifact_backfilled"] += count
            print(f"  {agent_name}: {count} proposed_edges → artifact_id={latest_artifact_id[:24]}...")
        elif count > 0:
            stats["pe_artifact_backfilled"] += count
            print(f"  {agent_name}: would backfill {count} proposed_edges")

    # ---- Phase 2: Fix edge source_type based on agent tier ----
    print("\nPhase 2: Fixing edge source_type from agent-derived source field...")

    # For edges with a `source` field that mentions a known agent/source name
    edges_no_type = cur.execute("""
        SELECT edge_id, source, source_url, claim_id
        FROM edges
        WHERE (source_type IS NULL OR source_type = '')
    """).fetchall()

    for edge in edges_no_type:
        source = edge["source"] or ""
        source_url = edge["source_url"] or ""
        tier = 2  # default

        # Check if source_url points to a government domain
        if source_url:
            try:
                domain = urlparse(source_url).netloc.lower()
                tier = domain_to_tier(domain)
            except Exception:
                pass

        # Check source text for tier hints
        source_lower = source.lower()
        if any(kw in source_lower for kw in ["sec ", "edgar", "13f", "10-k"]):
            tier = min(tier, 0)
        elif any(kw in source_lower for kw in ["congress", "scotus", "docket", "fara", "usaspending"]):
            tier = min(tier, 0)
        elif any(kw in source_lower for kw in ["opensecrets", "nbim", "backtest"]):
            tier = min(tier, 1)
        elif any(kw in source_lower for kw in ["tier 0", "tier-0", "(tier 0)", "government"]):
            tier = min(tier, 0)
        elif any(kw in source_lower for kw in ["tier 1", "tier-1", "(tier 1)", "professional"]):
            tier = min(tier, 1)

        label = TIER_LABELS.get(tier, "COMMENTARY")
        if not DRY_RUN:
            cur.execute(
                "UPDATE edges SET source_type = ? WHERE edge_id = ?",
                (label, edge["edge_id"]),
            )
        stats["edge_source_type_fixed"] += 1

    # ---- Phase 3: Create source records for edge source_urls not yet in sources ----
    print("\nPhase 3: Creating source records for unlinked edge source_urls...")

    edges_with_urls = cur.execute("""
        SELECT e.edge_id, e.source_url, e.claim_id
        FROM edges e
        WHERE e.source_url IS NOT NULL AND e.source_url != ''
          AND e.claim_id IS NOT NULL AND e.claim_id != ''
    """).fetchall()

    for edge in edges_with_urls:
        url = edge["source_url"]
        claim_id = edge["claim_id"]
        sid = hashlib.sha256(url.encode()).hexdigest()

        try:
            domain = urlparse(url).netloc.lower()
        except Exception:
            domain = ""
        tier = domain_to_tier(domain) if domain else 2

        # Create source if needed
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

        # Create claim_source link if needed
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
            stats["claim_source_links"] += 1

    # ---- Phase 4: Link orphan claims to sources based on agent provenance ----
    print("\nPhase 4: Linking orphan claims to agent-derived sources...")

    # For each edge that has a claim_id but the claim has no source,
    # create a source from the edge's `source` field
    orphan_edges = cur.execute("""
        SELECT e.edge_id, e.source, e.claim_id
        FROM edges e
        WHERE e.claim_id IS NOT NULL AND e.claim_id != ''
          AND e.claim_id NOT IN (SELECT claim_id FROM claim_sources)
          AND e.source IS NOT NULL AND e.source != ''
    """).fetchall()

    for edge in orphan_edges:
        source_text = edge["source"]
        claim_id = edge["claim_id"]
        sid = f"named-{hashlib.sha256(source_text.encode()).hexdigest()[:32]}"

        # Determine tier from source text
        tier = 2
        sl = source_text.lower()
        if any(kw in sl for kw in ["sec ", "edgar", "13f", "congress", "scotus", "fara", "usaspending", "docket"]):
            tier = 0
        elif any(kw in sl for kw in ["opensecrets", "nbim", "backtest", "correction layer"]):
            tier = 1

        existing = cur.execute(
            "SELECT source_id FROM sources WHERE source_id = ?", (sid,)
        ).fetchone()
        if not existing:
            if not DRY_RUN:
                cur.execute(
                    """INSERT OR IGNORE INTO sources (source_id, url, domain, tier, retrieved_at, notes)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (sid, "", source_text, tier, datetime.now().isoformat(),
                     f"Named source from edge: {source_text[:100]}"),
                )
            stats["sources_created"] += 1

        if not DRY_RUN:
            cur.execute(
                "INSERT OR IGNORE INTO claim_sources (claim_id, source_id) VALUES (?, ?)",
                (claim_id, sid),
            )
        stats["orphan_claims_linked"] += 1

    # ---- Phase 5: Link orphan edge claims by edge_id prefix ----
    print("\nPhase 5: Linking orphan claims from edge_id agent prefix...")

    # Edge IDs like FGIP-EDGE-CONGRESS-* tell us the originating agent
    PREFIX_AGENTS = {
        "CONGRESS": ("congress.gov", 0),
        "EDGAR": ("sec.gov", 0),
        "FEC": ("fec.gov", 0),
        "SCOTUS": ("supremecourt.gov", 0),
        "USASPENDING": ("usaspending.gov", 0),
        "FARA": ("fara.gov", 0),
        "FEDERAL_REGISTER": ("federalregister.gov", 0),
        "OPENSECRETS": ("opensecrets.org", 1),
        "SUPPLY_CHAIN": ("sec.gov/10-K", 1),
        "REASONING": ("fgip-synthesis", 2),
        "CHIPS": ("chips-facility", 1),
        "STABLECOIN": ("stablecoin", 1),
    }

    orphan_edges = cur.execute("""
        SELECT e.edge_id, e.edge_type, e.claim_id
        FROM edges e
        WHERE e.claim_id IS NOT NULL AND e.claim_id != ''
          AND e.claim_id NOT IN (SELECT claim_id FROM claim_sources)
    """).fetchall()

    for edge in orphan_edges:
        edge_id = edge["edge_id"]
        claim_id = edge["claim_id"]

        # Determine agent from edge_id prefix
        agent_domain = None
        agent_tier = 2
        edge_upper = edge_id.upper()
        for prefix, (domain, tier) in PREFIX_AGENTS.items():
            if prefix in edge_upper:
                agent_domain = domain
                agent_tier = tier
                break

        # Also check edge_type for vote edges
        if edge["edge_type"] in ("VOTED_FOR", "VOTED_AGAINST"):
            agent_domain = "congress.gov"
            agent_tier = 0
        elif edge["edge_type"] in ("DONATED_TO",):
            if not agent_domain:
                agent_domain = "fec.gov"
                agent_tier = 0
        elif edge["edge_type"] in ("FILED_AMICUS",):
            if not agent_domain:
                agent_domain = "supremecourt.gov"
                agent_tier = 0
        elif edge["edge_type"] in ("OWNS_SHARES", "ACQUIRED"):
            if not agent_domain:
                agent_domain = "sec.gov"
                agent_tier = 0

        if not agent_domain:
            agent_domain = "fgip-synthesis"
            agent_tier = 2

        sid = f"agent-{hashlib.sha256(agent_domain.encode()).hexdigest()[:24]}"

        # Create source if needed
        existing = cur.execute(
            "SELECT source_id FROM sources WHERE source_id = ?", (sid,)
        ).fetchone()
        if not existing:
            if not DRY_RUN:
                cur.execute(
                    """INSERT OR IGNORE INTO sources (source_id, url, domain, tier, retrieved_at, notes)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (sid, "", agent_domain, agent_tier, datetime.now().isoformat(),
                     f"Agent-derived source: {agent_domain}"),
                )
            stats["sources_created"] += 1

        # Link claim to source
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
            stats["orphan_claims_linked"] += 1

    # ---- Commit and report ----
    if not DRY_RUN:
        conn.commit()

    # ---- Post-repair stats ----
    print("\n" + "=" * 60)
    print("BACKFILL SUMMARY" + (" (DRY RUN)" if DRY_RUN else ""))
    print("=" * 60)
    for k, v in stats.items():
        print(f"  {k}: {v}")

    # Re-run the adversarial metrics
    print("\n" + "=" * 60)
    print("POST-BACKFILL EVIDENCE STRATIFICATION")
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

    pe_with_artifact = cur.execute(
        "SELECT COUNT(*) FROM proposed_edges WHERE artifact_id IS NOT NULL AND artifact_id != ''"
    ).fetchone()[0]
    pe_total = cur.execute("SELECT COUNT(*) FROM proposed_edges").fetchone()[0]

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
    print(f"  Proposed edges with artifact_id: {pe_with_artifact} / {pe_total} ({pe_with_artifact*100/pe_total:.1f}%)")

    conn.close()


if __name__ == "__main__":
    run()
