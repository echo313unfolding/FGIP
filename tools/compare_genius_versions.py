#!/usr/bin/env python3
"""Compare GENIUS Act S.394 (introduced) vs Enacted (12 USC 5903).

Generates:
- docs/genius_4a_diff.md - Human-readable diff report
- Proposed edge updates for FGIP graph

Usage:
    python3 tools/compare_genius_versions.py
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path


def load_section(path: str) -> str:
    """Load section text, skipping header."""
    content = Path(path).read_text()
    # Skip header lines
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("====="):
            return "\n".join(lines[i+1:])
    return content


def extract_reserve_clauses(text: str) -> dict:
    """Extract individual reserve clauses."""
    clauses = {}

    # Normalize text
    text = re.sub(r'\s+', ' ', text)

    # Pattern for main clauses (i), (ii), etc.
    pattern = r'\(([ivx]+)\)\s*([^(]+?)(?=\([ivx]+\)|$)'
    matches = re.findall(pattern, text, flags=re.IGNORECASE)

    for num, content in matches:
        content = content.strip().rstrip(';').strip()
        if len(content) > 5:
            clauses[num.lower()] = content

    return clauses


# ============================================================================
# S.394 (Introduced) - Key Reserve Provisions
# ============================================================================

S394_RESERVES = {
    "i": "United States coins and currency (including Federal reserve notes)",
    "ii": "funds held as demand deposits at insured depository institutions, regulated foreign depository institutions, or insured shares at insured depository institutions",
    "iii": "Treasury bills, notes, or bonds with a remaining maturity of 93 days or less; or issued with a maturity of 93 days or less",
    "iv": "repurchase agreements with a maturity of 7 days or less that are backed by Treasury bills with a maturity of 90 days or less",
    "v": "reverse repurchase agreements with a maturity of 7 days or less that are collateralized by Treasury notes, bills, or bonds on an overnight basis",
    "vi": "money market funds, invested solely in underlying assets described in clauses (i) through (iv)",
    "vii": "Central Bank reserve deposits",
}

# ============================================================================
# Enacted (12 USC 5903) - Key Reserve Provisions
# ============================================================================

ENACTED_RESERVES = {
    "i": "United States coins and currency (including Federal Reserve notes) OR MONEY STANDING TO THE CREDIT OF AN ACCOUNT WITH A FEDERAL RESERVE BANK",
    "ii": "funds held as demand deposits or insured shares at an insured depository institution (including any foreign branches or agents)",
    "iii": "Treasury bills, notes, or bonds with a remaining maturity of 93 days or less; or issued with a maturity of 93 days or less",
    "iv": "money received under repurchase agreements, with OVERNIGHT MATURITY, backed by Treasury bills with maturity of 93 days or less",
    "v": "reverse repurchase agreements, with OVERNIGHT MATURITY, collateralized by Treasury notes, bills, or bonds",
    "vi": "securities issued by an investment company registered under section 80a-8(a) of title 15, or other registered Government money market fund",
    "vii": "ANY OTHER SIMILARLY LIQUID FEDERAL GOVERNMENT-ISSUED ASSET approved by the primary Federal payment stablecoin regulator",
    "viii": "ANY RESERVE described in (i)-(iii) or (vi)-(vii) IN TOKENIZED FORM",
}


def generate_diff_report() -> str:
    """Generate human-readable diff report."""
    lines = [
        "# GENIUS Act Section 4(a) - Version Comparison",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Sources",
        "",
        "| Version | Source | Tier |",
        "|---------|--------|------|",
        "| S.394 (Introduced) | GovInfo BILLS-119s394is | 0 |",
        "| Enacted (12 USC 5903) | uscode.house.gov | 0 |",
        "",
        "---",
        "",
        "## Reserve Asset Comparison",
        "",
        "| Clause | S.394 (Introduced) | Enacted (12 USC 5903) | Change |",
        "|--------|-------------------|----------------------|--------|",
    ]

    all_clauses = sorted(set(S394_RESERVES.keys()) | set(ENACTED_RESERVES.keys()),
                         key=lambda x: ['i','ii','iii','iv','v','vi','vii','viii','ix','x'].index(x) if x in ['i','ii','iii','iv','v','vi','vii','viii','ix','x'] else 99)

    for clause in all_clauses:
        s394 = S394_RESERVES.get(clause, "—")
        enacted = ENACTED_RESERVES.get(clause, "—")

        # Determine change type
        if clause not in S394_RESERVES:
            change = "**NEW**"
        elif clause not in ENACTED_RESERVES:
            change = "REMOVED"
        elif s394.upper() != enacted.upper():
            change = "MODIFIED"
        else:
            change = "Same"

        # Truncate for table
        s394_short = s394[:40] + "..." if len(s394) > 40 else s394
        enacted_short = enacted[:40] + "..." if len(enacted) > 40 else enacted

        lines.append(f"| ({clause}) | {s394_short} | {enacted_short} | {change} |")

    lines.extend([
        "",
        "---",
        "",
        "## Key Changes (Material for Thesis)",
        "",
        "### 1. Fed Account Reserves EXPLICITLY Added",
        "",
        "**S.394 (i):** `United States coins and currency`",
        "",
        "**Enacted (i):** `United States coins and currency ... OR MONEY STANDING TO THE CREDIT OF AN ACCOUNT WITH A FEDERAL RESERVE BANK`",
        "",
        "**Impact:** Issuers can now park reserves directly at the Fed instead of buying Treasuries. If Fed pays IORB > T-bill yield, rational issuers choose Fed account.",
        "",
        "### 2. Repo/Reverse Repo Terms Tightened to OVERNIGHT",
        "",
        "**S.394:** 7 days or less",
        "",
        "**Enacted:** OVERNIGHT maturity",
        "",
        "**Impact:** More restrictive but more liquid. Reduces Treasury demand via repo channel.",
        "",
        "### 3. NEW Catch-All Clause (vii)",
        "",
        "**Enacted (vii):** `any other similarly liquid Federal Government-issued asset approved by the primary Federal payment stablecoin regulator`",
        "",
        "**Impact:** Regulator can approve additional reserve types without legislation. Future-proofs away from Treasury-only.",
        "",
        "### 4. NEW Tokenized Reserves Clause (viii)",
        "",
        "**Enacted (viii):** `any reserve described in (i)-(iii) or (vi)-(vii) in tokenized form`",
        "",
        "**Impact:** Opens door to tokenized T-bills, tokenized money market funds, etc. Doesn't change Treasury demand directly but enables DeFi integration.",
        "",
        "---",
        "",
        "## Chain Verdict Update",
        "",
        "| Edge | S.394 Assessment | Enacted Assessment | Delta |",
        "|------|-----------------|-------------------|-------|",
        "| GENIUS → Treasury reserves | HEURISTIC (permitted) | **WEAKER** (alternatives expanded) | -0.10 |",
        "| Treasury demand → Domestication | HEURISTIC (scale) | **WEAKER** (Fed account option) | -0.15 |",
        "| Foreign leverage reduction | UNTESTED | UNTESTED | 0 |",
        "| Leverage → Tariff feasibility | UNTESTED | UNTESTED | 0 |",
        "",
        "**New Chain Confidence:** 50% → **40%**",
        "",
        "**Key Finding:**",
        "",
        "```",
        "The enacted GENIUS Act WEAKENS the 'forced Treasury demand' thesis.",
        "",
        "Clause (i) explicitly allows Fed account reserves as PRIMARY option.",
        "Clause (vii) allows regulator to approve non-Treasury assets.",
        "Clause (viii) allows tokenized reserves.",
        "",
        "Issuers will OPTIMIZE for yield:",
        "  - If IORB (Fed interest on reserves) > T-bill yield → Park at Fed",
        "  - If T-bill yield > IORB → Buy Treasuries",
        "",
        "The domestication thesis requires Treasuries to be the DOMINANT choice.",
        "Enacted text provides multiple escape hatches.",
        "```",
        "",
        "---",
        "",
        "## Proposed Edge Updates",
        "",
        "```python",
        "# DISPROVE: Treasuries mandated",
        "{",
        '    "edge_id": "genius-treasury-mandate",',
        '    "status": "DISPROVEN",',
        '    "tier": 0,',
        '    "evidence": "12 USC 5903(a)(1)(A) permits 8 reserve types including Fed account"',
        "}",
        "",
        "# DOWNGRADE: Forced Treasury demand",
        "{",
        '    "edge_id": "genius-forced-treasury-demand",',
        '    "old_confidence": 0.55,',
        '    "new_confidence": 0.35,',
        '    "tier": 0,',
        '    "evidence": "Fed account reserves (clause i) provide yield-competitive alternative"',
        "}",
        "",
        "# NEW EDGE: Fed account reserves enabled",
        "{",
        '    "edge_id": "genius-enables-fed-reserves",',
        '    "from_node": "genius-act-enacted",',
        '    "to_node": "fed-account-reserves",',
        '    "edge_type": "ENABLES",',
        '    "confidence": 0.95,',
        '    "tier": 0,',
        '    "evidence": "12 USC 5903(a)(1)(A)(i): money standing to the credit of an account with a Federal Reserve Bank"',
        "}",
        "```",
    ])

    return "\n".join(lines)


def generate_edge_updates() -> list:
    """Generate structured edge updates for FGIP."""
    return [
        {
            "action": "UPDATE",
            "edge_id": "genius-to-treasury-demand",
            "field": "status",
            "old_value": "HEURISTIC",
            "new_value": "WEAKENED",
            "evidence_citation": "12 USC 5903(a)(1)(A)",
            "reason": "Enacted text permits Fed account reserves (clause i) and regulator-approved assets (clause vii)",
        },
        {
            "action": "UPDATE",
            "edge_id": "genius-forced-treasury-demand",
            "field": "confidence",
            "old_value": 0.55,
            "new_value": 0.35,
            "evidence_citation": "12 USC 5903(a)(1)(A)(i)",
            "reason": "Fed account option provides yield-competitive alternative to Treasuries",
        },
        {
            "action": "CREATE",
            "edge_id": "genius-enables-fed-reserves",
            "from_node": "genius-act-enacted",
            "to_node": "fed-account-reserves",
            "edge_type": "ENABLES",
            "confidence": 0.95,
            "tier": 0,
            "evidence_citation": "12 USC 5903(a)(1)(A)(i)",
            "evidence_text": "money standing to the credit of an account with a Federal Reserve Bank",
        },
        {
            "action": "CREATE",
            "edge_id": "genius-enables-regulator-approved",
            "from_node": "genius-act-enacted",
            "to_node": "regulator-approved-reserves",
            "edge_type": "ENABLES",
            "confidence": 0.90,
            "tier": 0,
            "evidence_citation": "12 USC 5903(a)(1)(A)(vii)",
            "evidence_text": "any other similarly liquid Federal Government-issued asset approved by the primary Federal payment stablecoin regulator",
        },
    ]


def main():
    # Generate diff report
    report = generate_diff_report()
    diff_path = Path("docs/genius_4a_diff.md")
    diff_path.write_text(report)
    print(f"Wrote: {diff_path}")

    # Generate edge updates JSON
    updates = generate_edge_updates()
    updates_path = Path("docs/genius_edge_updates.json")
    updates_path.write_text(json.dumps(updates, indent=2))
    print(f"Wrote: {updates_path}")

    # Print summary
    print("\n" + "="*70)
    print("GENIUS ACT VERSION COMPARISON - SUMMARY")
    print("="*70)
    print()
    print("KEY CHANGES (S.394 → Enacted):")
    print()
    print("  1. Fed account reserves EXPLICITLY ADDED (clause i)")
    print("     → Issuers can park at Fed instead of buying Treasuries")
    print()
    print("  2. Repo terms TIGHTENED to OVERNIGHT (clauses iv, v)")
    print("     → More liquid but less Treasury exposure")
    print()
    print("  3. Catch-all clause ADDED (clause vii)")
    print("     → Regulator can approve non-Treasury assets")
    print()
    print("  4. Tokenized reserves ADDED (clause viii)")
    print("     → Future-proofs for DeFi integration")
    print()
    print("-"*70)
    print()
    print("CHAIN VERDICT:")
    print()
    print("  'Forced Treasury demand' thesis: WEAKENED (55% → 35%)")
    print("  Domestication mechanism: UNCERTAIN (Fed account is escape hatch)")
    print()
    print("  The enacted GENIUS Act is more plausibly:")
    print("    'Stablecoin safety + regulatory channel'")
    print("  NOT:")
    print("    'Mandatory Treasury absorption engine'")
    print()


if __name__ == "__main__":
    main()
