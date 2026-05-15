# Thesis Receipt Schema

Every FGIP thesis that reaches Active status must have a receipt — a structured artifact that records what was believed, why, and what evidence supported it.

## Purpose

A receipt is not a prediction. It is a snapshot of evidence state at a point in time.

Receipts serve three functions:
1. **Audit trail** — Why did the system believe this thesis?
2. **Reproducibility** — Can someone else verify the same evidence?
3. **Falsification** — What would make this thesis wrong, and has that happened?

## Schema

```json
{
  "receipt_version": "1.0",
  "thesis_id": "thesis-defense-primes",
  "timestamp": "2026-05-09T00:00:24Z",
  "generated_by": "fgip-conviction-engine",

  "claim": "Defense primes benefit from NDAA $895B+, Ukraine replenishment ($60B industrial base), AUKUS ($368B subs), Pacific Deterrence ($9.9B), hypersonics.",

  "tickers": ["LMT", "RTX", "NOC", "GD", "HII", "BWXT"],

  "source_edges": [
    {
      "from": "ndaa-fy2025",
      "to": "lockheed-martin",
      "edge_type": "AUTHORIZES_FUNDING",
      "confidence": 0.95,
      "source_url": "https://congress.gov/bill/118th-congress/house-bill/8070",
      "tier": 0
    },
    {
      "from": "ukraine-supplemental-2024",
      "to": "raytheon",
      "edge_type": "FUNDS_REPLENISHMENT",
      "confidence": 0.95,
      "source_url": "https://congress.gov/bill/118th-congress/house-bill/8035",
      "tier": 0
    }
  ],

  "evidence_summary": {
    "confirming_signals": 148,
    "refuting_signals": 9,
    "tier_0_signals": 115,
    "tier_1_signals": 24,
    "tier_2_signals": 9,
    "source_types": ["usaspending", "supply_chain", "market_data", "congress_vote"],
    "triangulation_met": true,
    "triangulation_count": 4
  },

  "funding_chain": [
    "Congress authorizes NDAA ($895.2B)",
    "DoD obligates funds via contracts",
    "Prime contractors receive awards (LMT, RTX, NOC, GD, HII)",
    "Subcontractors supply components (BWXT naval reactors, HWM forgings, TDG parts)",
    "Commodity procurement (copper, steel, rare earths, propellants)"
  ],

  "beneficiaries": [
    {"ticker": "LMT", "role": "F-35, HIMARS, ATACMS, hypersonic (HACM)"},
    {"ticker": "RTX", "role": "Patriot, SM-6, AMRAAM, Pratt engines"},
    {"ticker": "NOC", "role": "B-21, Sentinel ICBM, Triton UAV"},
    {"ticker": "GD", "role": "Columbia-class sub, Abrams, Stryker"},
    {"ticker": "HII", "role": "Aircraft carriers, Virginia-class subs"},
    {"ticker": "BWXT", "role": "Sole-source naval nuclear reactors"}
  ],

  "counter_thesis": [
    {
      "description": "Fiscal hawks force defense cuts in debt ceiling deal",
      "severity": "manageable",
      "likelihood": 0.3,
      "mitigation": "Monitor budget negotiations, scale position if sequestration risk rises"
    },
    {
      "description": "Cost overruns on major programs erode margins",
      "severity": "serious",
      "likelihood": 0.5,
      "mitigation": "Sentinel ICBM already Nunn-McCurdy breached; diversify across primes"
    }
  ],

  "disconfirming_evidence": [
    "Defense budget sequestration or continuing resolution >6 months",
    "Major program cancellation (Sentinel, NGAD)",
    "Peace deal reducing threat perception significantly",
    "Contractor execution failure (cost overrun >50%)"
  ],

  "conviction": {
    "score": 100.0,
    "level": 5,
    "recommendation": "BUY",
    "position_size_pct": 0.20
  },

  "graph_state": "Active",

  "receipt_hash": "sha256:...",

  "cost": {
    "wall_time_s": 9.3,
    "python_version": "3.10.12",
    "hostname": "echo-labs",
    "timestamp_start": "2026-05-09T00:00:15",
    "timestamp_end": "2026-05-09T00:00:24"
  }
}
```

## Field definitions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `receipt_version` | string | yes | Schema version for forward compatibility |
| `thesis_id` | string | yes | Unique thesis identifier matching conviction engine |
| `timestamp` | ISO 8601 | yes | When receipt was generated |
| `generated_by` | string | yes | System that produced the receipt |
| `claim` | string | yes | The thesis statement being evaluated |
| `tickers` | string[] | yes | Public tickers associated with this thesis |
| `source_edges` | object[] | yes | Graph edges supporting the thesis, with source URLs and tiers |
| `evidence_summary` | object | yes | Aggregate signal counts by type and tier |
| `funding_chain` | string[] | yes | Ordered description of how funds flow from source to beneficiary |
| `beneficiaries` | object[] | yes | Companies that benefit, with their role in the chain |
| `counter_thesis` | object[] | yes | Strongest arguments against the thesis |
| `disconfirming_evidence` | string[] | yes | What would prove the thesis wrong |
| `conviction` | object | yes | Score, level, recommendation, and position size |
| `graph_state` | enum | yes | Candidate, Active, or Quarantined |
| `receipt_hash` | string | yes | SHA-256 hash of receipt contents for integrity verification |
| `cost` | object | yes | Compute cost of generating this receipt |

## State transitions

```
Candidate
  → Active    (3+ independent signals, 1+ Tier 0, counter-thesis assessed)
  → Quarantined (disconfirming evidence found, or counter-thesis validated)

Active
  → Quarantined (invalidation trigger fired)
  → Candidate   (key evidence expired or withdrawn)

Quarantined
  → Candidate   (new evidence re-opens investigation)
  → Rejected    (thesis permanently invalidated)
```

## Receipt storage

Receipts are stored in `fgip_receipts/` as JSON files:

```
fgip_receipts/
  thesis-defense-primes_20260509.json
  thesis-power-uranium-screen_20260509.json
  thesis-uranium-screen_20260509.json
```

Each receipt is immutable once generated. New evidence produces a new receipt with a new timestamp, not an edit of the old one.

## Cryptographic verification

Thesis receipts are cryptographic and substrate-agnostic. Each receipt includes SHA256 hashes of its evidence state. Reference implementations exist as flat JSON files and optionally on external registries.

```
FGIP thesis receipt
→ MorphSAT novelty/quality gate
→ Evidence state hash (SHA256)
→ Immutable record of evidence state at time of decision
```

This creates an auditable, tamper-resistant record of what was known and when.
