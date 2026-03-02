# GENIUS Act Section 4(a) - Version Comparison

Generated: 2026-02-24T15:48:38.858968+00:00

## Sources

| Version | Source | Tier |
|---------|--------|------|
| S.394 (Introduced) | GovInfo BILLS-119s394is | 0 |
| Enacted (12 USC 5903) | uscode.house.gov | 0 |

---

## Reserve Asset Comparison

| Clause | S.394 (Introduced) | Enacted (12 USC 5903) | Change |
|--------|-------------------|----------------------|--------|
| (i) | United States coins and currency (includ... | United States coins and currency (includ... | MODIFIED |
| (ii) | funds held as demand deposits at insured... | funds held as demand deposits or insured... | MODIFIED |
| (iii) | Treasury bills, notes, or bonds with a r... | Treasury bills, notes, or bonds with a r... | Same |
| (iv) | repurchase agreements with a maturity of... | money received under repurchase agreemen... | MODIFIED |
| (v) | reverse repurchase agreements with a mat... | reverse repurchase agreements, with OVER... | MODIFIED |
| (vi) | money market funds, invested solely in u... | securities issued by an investment compa... | MODIFIED |
| (vii) | Central Bank reserve deposits | ANY OTHER SIMILARLY LIQUID FEDERAL GOVER... | MODIFIED |
| (viii) | — | ANY RESERVE described in (i)-(iii) or (v... | **NEW** |

---

## Key Changes (Material for Thesis)

### 1. Fed Account Reserves EXPLICITLY Added

**S.394 (i):** `United States coins and currency`

**Enacted (i):** `United States coins and currency ... OR MONEY STANDING TO THE CREDIT OF AN ACCOUNT WITH A FEDERAL RESERVE BANK`

**Impact:** Issuers can now park reserves directly at the Fed instead of buying Treasuries. If Fed pays IORB > T-bill yield, rational issuers choose Fed account.

### 2. Repo/Reverse Repo Terms Tightened to OVERNIGHT

**S.394:** 7 days or less

**Enacted:** OVERNIGHT maturity

**Impact:** More restrictive but more liquid. Reduces Treasury demand via repo channel.

### 3. NEW Catch-All Clause (vii)

**Enacted (vii):** `any other similarly liquid Federal Government-issued asset approved by the primary Federal payment stablecoin regulator`

**Impact:** Regulator can approve additional reserve types without legislation. Future-proofs away from Treasury-only.

### 4. NEW Tokenized Reserves Clause (viii)

**Enacted (viii):** `any reserve described in (i)-(iii) or (vi)-(vii) in tokenized form`

**Impact:** Opens door to tokenized T-bills, tokenized money market funds, etc. Doesn't change Treasury demand directly but enables DeFi integration.

---

## Chain Verdict Update

| Edge | S.394 Assessment | Enacted Assessment | Delta |
|------|-----------------|-------------------|-------|
| GENIUS → Treasury reserves | HEURISTIC (permitted) | **WEAKER** (alternatives expanded) | -0.10 |
| Treasury demand → Domestication | HEURISTIC (scale) | **WEAKER** (Fed account option) | -0.15 |
| Foreign leverage reduction | UNTESTED | UNTESTED | 0 |
| Leverage → Tariff feasibility | UNTESTED | UNTESTED | 0 |

**New Chain Confidence:** 50% → **40%**

**Key Finding:**

```
The enacted GENIUS Act WEAKENS the 'forced Treasury demand' thesis.

Clause (i) explicitly allows Fed account reserves as PRIMARY option.
Clause (vii) allows regulator to approve non-Treasury assets.
Clause (viii) allows tokenized reserves.

Issuers will OPTIMIZE for yield:
  - If IORB (Fed interest on reserves) > T-bill yield → Park at Fed
  - If T-bill yield > IORB → Buy Treasuries

The domestication thesis requires Treasuries to be the DOMINANT choice.
Enacted text provides multiple escape hatches.
```

---

## Proposed Edge Updates

```python
# DISPROVE: Treasuries mandated
{
    "edge_id": "genius-treasury-mandate",
    "status": "DISPROVEN",
    "tier": 0,
    "evidence": "12 USC 5903(a)(1)(A) permits 8 reserve types including Fed account"
}

# DOWNGRADE: Forced Treasury demand
{
    "edge_id": "genius-forced-treasury-demand",
    "old_confidence": 0.55,
    "new_confidence": 0.35,
    "tier": 0,
    "evidence": "Fed account reserves (clause i) provide yield-competitive alternative"
}

# NEW EDGE: Fed account reserves enabled
{
    "edge_id": "genius-enables-fed-reserves",
    "from_node": "genius-act-enacted",
    "to_node": "fed-account-reserves",
    "edge_type": "ENABLES",
    "confidence": 0.95,
    "tier": 0,
    "evidence": "12 USC 5903(a)(1)(A)(i): money standing to the credit of an account with a Federal Reserve Bank"
}
```