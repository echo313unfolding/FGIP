"""GENIUS Act S.394 Section 4(a) - Tier-0 Backed Edge Proposals

Generated from official GPO/GovInfo text extraction.
Source: https://www.govinfo.gov/content/pkg/BILLS-119s394is/html/BILLS-119s394is.htm

These edges are backed by verbatim bill text, not commentary.
"""

from datetime import datetime, timezone

# ============================================================================
# TIER-0 EVIDENCE: Exact quotes from Section 4(a)
# ============================================================================

SECTION_4A_QUOTES = {
    "1_to_1_reserve": {
        "citation": "S.394 Section 4(a)(1)(A)",
        "text": "maintain reserves backing the issuer's payment stablecoins outstanding on an at least 1 to 1 basis",
        "tier": 0,
    },
    "permitted_reserves": {
        "citation": "S.394 Section 4(a)(1)(A)(i-vii)",
        "text": """reserves comprising--
(i) United States coins and currency;
(ii) funds held as demand deposits at insured depository institutions;
(iii) Treasury bills, notes, or bonds with a remaining maturity of 93 days or less;
(iv) repurchase agreements (7 days or less) backed by Treasury bills (90 days or less);
(v) reverse repurchase agreements (7 days or less) collateralized by Treasury securities;
(vi) money market funds invested solely in assets (i) through (iv);
(vii) Central Bank reserve deposits""",
        "tier": 0,
    },
    "rehypothecation_ban": {
        "citation": "S.394 Section 4(a)(2)",
        "text": "Reserves may not be pledged, rehypothecated, or reused, except for the purpose of creating liquidity to meet reasonable expectations of requests to redeem payment stablecoins",
        "tier": 0,
    },
    "monthly_certification": {
        "citation": "S.394 Section 4(a)(3)(B)",
        "text": "Each month, the Chief Executive Officer and Chief Financial Officer shall submit a certification as to the accuracy of the monthly report",
        "tier": 0,
    },
    "criminal_penalty": {
        "citation": "S.394 Section 4(a)(3)(C)",
        "text": "Any person who submits a certification knowing that such certification is false shall be subject to the criminal penalties set forth under section 1350(c) of title 18",
        "tier": 0,
    },
    "activity_limitation": {
        "citation": "S.394 Section 4(a)(6)(A)",
        "text": "A permitted payment stablecoin issuer may only-- (i) issue payment stablecoins; (ii) redeem payment stablecoins; (iii) manage related reserves; (iv) provide custodial services; (v) undertake functions that directly support issuing and redeeming",
        "tier": 0,
    },
}


# ============================================================================
# PROPOSED CLAIMS - Backed by Tier-0 text
# ============================================================================

PROPOSED_CLAIMS = [
    {
        "claim_id": "genius-4a-1to1-reserve",
        "claim_text": "GENIUS Act Section 4(a)(1)(A) requires stablecoin issuers to maintain reserves on at least 1:1 basis",
        "evidence": SECTION_4A_QUOTES["1_to_1_reserve"],
        "status": "PROVEN",
        "confidence": 0.95,
        "topic": "Stablecoin Regulation",
    },
    {
        "claim_id": "genius-4a-treasury-eligible",
        "claim_text": "GENIUS Act permits short-term Treasuries (≤93 days) as reserve assets, but does NOT mandate Treasuries exclusively",
        "evidence": SECTION_4A_QUOTES["permitted_reserves"],
        "status": "PROVEN",
        "notes": "Bill allows cash, deposits, money market funds, and central bank reserves as alternatives to Treasuries",
        "confidence": 0.95,
        "topic": "Stablecoin Regulation",
    },
    {
        "claim_id": "genius-4a-rehypothecation-ban",
        "claim_text": "GENIUS Act bans rehypothecation of stablecoin reserves except for liquidity management",
        "evidence": SECTION_4A_QUOTES["rehypothecation_ban"],
        "status": "PROVEN",
        "confidence": 0.95,
        "topic": "Stablecoin Regulation",
    },
    {
        "claim_id": "genius-4a-ceo-certification",
        "claim_text": "GENIUS Act requires monthly CEO/CFO certification of reserve composition with criminal penalties for false certification",
        "evidence": [SECTION_4A_QUOTES["monthly_certification"], SECTION_4A_QUOTES["criminal_penalty"]],
        "status": "PROVEN",
        "confidence": 0.95,
        "topic": "Stablecoin Regulation",
    },
    {
        "claim_id": "genius-forced-treasury-demand",
        "claim_text": "GENIUS Act creates forced Treasury demand by mandating reserve backing",
        "evidence": SECTION_4A_QUOTES["permitted_reserves"],
        "status": "HEURISTIC",
        "notes": "Treasuries are ONE option, not the only option. Demand depends on issuer choice, yield optimization, and regulatory guidance. Not a mandate.",
        "confidence": 0.60,
        "topic": "Debt Domestication",
    },
]


# ============================================================================
# PROPOSED EDGES - For FGIP Graph
# ============================================================================

PROPOSED_EDGES = [
    # EDGE 1: GENIUS Act → 1:1 Reserve Requirement (PROVEN)
    {
        "edge_id": "genius-to-1to1-reserve",
        "from_node": "genius-act-s394",
        "to_node": "stablecoin-reserve-requirement",
        "edge_type": "REQUIRES",
        "confidence": 0.95,
        "tier": 0,
        "evidence_citation": "S.394 Section 4(a)(1)(A)",
        "evidence_text": SECTION_4A_QUOTES["1_to_1_reserve"]["text"],
        "reasoning": "Direct quote from bill text. No interpretation required.",
        "status": "TIER_0_BACKED",
    },
    # EDGE 2: Reserve Requirement → Permitted Assets (PROVEN)
    {
        "edge_id": "reserve-to-permitted-assets",
        "from_node": "stablecoin-reserve-requirement",
        "to_node": "permitted-reserve-assets",
        "edge_type": "DEFINES",
        "confidence": 0.95,
        "tier": 0,
        "evidence_citation": "S.394 Section 4(a)(1)(A)(i-vii)",
        "evidence_text": "Treasury bills ≤93 days, cash, deposits, repos, money market funds, central bank reserves",
        "reasoning": "Bill enumerates 7 categories of permitted reserves. Treasuries are ONE option.",
        "status": "TIER_0_BACKED",
    },
    # EDGE 3: Permitted Assets → Treasury Demand (HEURISTIC - Weakened)
    {
        "edge_id": "permitted-assets-to-treasury-demand",
        "from_node": "permitted-reserve-assets",
        "to_node": "domestic-treasury-demand",
        "edge_type": "MAY_INCREASE",
        "confidence": 0.55,
        "tier": 2,
        "evidence_citation": "Inference from S.394 + market behavior",
        "evidence_text": "Treasuries are eligible but not mandated. Actual demand depends on issuer yield optimization.",
        "reasoning": "Bill does NOT force Treasury holdings. Issuers may choose deposits, money markets, or Fed reserves instead. Edge is HEURISTIC.",
        "status": "HEURISTIC",
        "adversarial_note": "Current stablecoin issuers (Tether, Circle) already hold significant Treasuries voluntarily. GENIUS Act codifies but may not increase demand materially.",
    },
    # EDGE 4: Rehypothecation Ban → Reserve Integrity (PROVEN)
    {
        "edge_id": "rehypo-ban-to-integrity",
        "from_node": "genius-act-s394",
        "to_node": "stablecoin-reserve-integrity",
        "edge_type": "ENSURES",
        "confidence": 0.90,
        "tier": 0,
        "evidence_citation": "S.394 Section 4(a)(2)",
        "evidence_text": SECTION_4A_QUOTES["rehypothecation_ban"]["text"],
        "reasoning": "Prevents fractional reserve behavior. Reserves cannot be leveraged.",
        "status": "TIER_0_BACKED",
    },
    # EDGE 5: CEO Certification → Enforcement Mechanism (PROVEN)
    {
        "edge_id": "ceo-cert-to-enforcement",
        "from_node": "genius-act-s394",
        "to_node": "stablecoin-enforcement-mechanism",
        "edge_type": "CREATES",
        "confidence": 0.90,
        "tier": 0,
        "evidence_citation": "S.394 Section 4(a)(3)(B-C)",
        "evidence_text": SECTION_4A_QUOTES["criminal_penalty"]["text"],
        "reasoning": "Criminal penalties (18 USC 1350(c)) for false certification creates skin-in-the-game.",
        "status": "TIER_0_BACKED",
    },
]


# ============================================================================
# CHAIN VERDICT UPDATE
# ============================================================================

CHAIN_VERDICT = {
    "chain": "GENIUS Act → domesticate debt → remove foreign leverage → tariffs feasible",
    "edge_1_verdict": {
        "claim": "GENIUS Act mandates Treasury reserves",
        "old_status": "HEURISTIC",
        "new_status": "WEAKENED",
        "reason": "Bill permits Treasuries but does NOT mandate them. 7 asset categories allowed.",
        "confidence_delta": -0.15,
    },
    "overall_confidence": 0.50,  # Downgraded from 0.55
    "weakest_link": "Edge 1 (Treasuries not mandated) and Edge 4 (tariffs already happening)",
    "key_finding": """
CRITICAL: The 'forced Treasury demand' thesis is WEAKER than assumed.

Section 4(a)(1)(A)(i-vii) allows reserves in:
1. Cash/currency
2. Bank deposits (insured)
3. Treasury bills ≤93 days  <-- ONE option, not mandated
4. Repos backed by T-bills
5. Reverse repos with Treasury collateral
6. Money market funds
7. Central Bank reserve deposits

Issuers will OPTIMIZE for yield. If Fed pays higher interest on reserves (IORB)
than T-bills yield, rational issuers park reserves at the Fed, not in Treasuries.

The domestication thesis requires Treasuries to be the DOMINANT reserve choice.
Bill text does not guarantee this.
""",
}


def generate_report():
    """Generate verification report."""
    lines = [
        "=" * 70,
        "GENIUS ACT S.394 SECTION 4(a) - TIER-0 VERIFICATION REPORT",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "=" * 70,
        "",
        "SOURCE: https://www.govinfo.gov/content/pkg/BILLS-119s394is/html/BILLS-119s394is.htm",
        "TIER: 0 (Official GPO/GovInfo)",
        "",
        "-" * 70,
        "CLAIMS VERIFIED BY BILL TEXT",
        "-" * 70,
        "",
    ]

    for claim in PROPOSED_CLAIMS:
        lines.append(f"CLAIM: {claim['claim_text']}")
        lines.append(f"STATUS: {claim['status']}")
        lines.append(f"CONFIDENCE: {claim['confidence']}")
        if 'notes' in claim:
            lines.append(f"NOTES: {claim['notes']}")
        lines.append("")

    lines.extend([
        "-" * 70,
        "CHAIN VERDICT UPDATE",
        "-" * 70,
        "",
        CHAIN_VERDICT["key_finding"],
        "",
        f"Overall Chain Confidence: {CHAIN_VERDICT['overall_confidence']}",
        f"Weakest Link: {CHAIN_VERDICT['weakest_link']}",
    ])

    return "\n".join(lines)


if __name__ == "__main__":
    print(generate_report())
