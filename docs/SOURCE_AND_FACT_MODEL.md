# Source and Fact Model

FGIP separates citations, extracted facts, and graph edges into distinct layers. Each layer has a different purpose and a different consumer.

## The three layers

```
sources.jsonl        → Who said it, when, where (human-readable citation)
facts.jsonl          → What was said, structured (machine-readable claim)
proposed_edges.jsonl → How it connects to the graph (candidate relationship)
```

### Layer 1: Sources (`data/sources/sources.jsonl`)

A source is a citable document. It has a publisher, a URL, a publication date, and a tier.

```json
{
  "source_id": "congress_ndaa_fy2025_hr8070",
  "tier": 0,
  "source_type": "legislation",
  "publisher": "Congress.gov",
  "title": "National Defense Authorization Act for Fiscal Year 2025",
  "url": "https://congress.gov/bill/118th-congress/house-bill/8070",
  "published_at": "2024-12-23",
  "accessed_at": "2026-05-09"
}
```

**Purpose:** Audit trail. Anyone can click the URL and verify the document exists.

**Tier assignment:**
- Tier 0: Government records (Congress.gov, EDGAR, USASpending, Federal Register, NRC, FERC, state PUCs)
- Tier 1: Professional sources (Reuters, company press releases, earnings reports, industry associations)
- Tier 2: Commentary (news articles, podcasts, social media)
- Tier 3: Hypothesis (AI analysis, user observations, cross-reference inferences)

See [EVIDENCE_TIERS.md](EVIDENCE_TIERS.md) for full tier definitions.

### Layer 2: Extracted facts (`data/extracted/facts.jsonl`)

A fact is a structured claim extracted from a source. One source can produce multiple facts.

```json
{
  "fact_id": "fact_ndaa_fy2025_enacted",
  "source_id": "congress_ndaa_fy2025_hr8070",
  "fact_type": "legislation",
  "subject": "Congress",
  "predicate": "ENACTED",
  "object": "NDAA FY2025",
  "value_usd": 895200000000,
  "date": "2024-12-23",
  "confidence": 1.0,
  "note": "$895.2B defense authorization. 5.2% military pay raise."
}
```

**Purpose:** Machine-readable claims. The graph doesn't read articles — it reads facts.

**Fields:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `fact_id` | string | yes | Unique identifier |
| `source_id` | string | yes | Links back to source citation |
| `fact_type` | string | yes | Category (legislation, procurement, earnings, supply_demand, etc.) |
| `subject` | string | yes | Who/what is acting |
| `predicate` | string | yes | The action or relationship |
| `object` | string | yes | Who/what is acted upon |
| `quantity` | number | no | Numeric value if applicable |
| `unit` | string | no | Unit of quantity |
| `value_usd` | number | no | Dollar value if applicable |
| `date` | string | yes | When the fact applies |
| `confidence` | float | yes | 0.0 to 1.0 |
| `note` | string | no | Context for human readers |

### Layer 3: Proposed edges (`data/edges/proposed_edges_examples.jsonl`)

A proposed edge is a candidate relationship for the graph. It references a fact and maps it to graph node IDs.

```json
{
  "edge_id": "edge_ndaa_fy2025_lmt",
  "fact_id": "fact_ndaa_fy2025_enacted",
  "from_node": "ndaa-fy2025",
  "to_node": "lockheed-martin",
  "relationship": "AUTHORIZES_FUNDING",
  "confidence": 0.95,
  "agent_name": "congress",
  "tier": 0,
  "note": "$895.2B authorization. F-35, HIMARS, ATACMS, hypersonic programs."
}
```

**Purpose:** Staging area for graph insertion. Edges sit here until reviewed and promoted.

**Promotion rules:**
- Tier 0 agent edges self-certify (the data IS the evidence)
- Tier 1 agent edges require artifact evidence
- Tier 2+ edges require manual review or triangulation

## How the layers connect

```
Source (sources.jsonl)
  ↓ source_id
Fact (facts.jsonl)
  ↓ fact_id
Proposed Edge (proposed_edges_examples.jsonl)
  ↓ promotion
Graph Edge (fgip.db edges table)
  ↓ conviction engine
Thesis Receipt (fgip_receipts/*.json)
```

One source can produce many facts. One fact can produce many edges. The conviction engine queries edges (both promoted and proposed) to score theses.

## Example: Defense funding chain

**Source:** Congress.gov, H.R.8070, NDAA FY2025

**Facts extracted:**
- Congress ENACTED NDAA FY2025 ($895.2B)
- 5.2% military pay raise authorized

**Edges proposed:**
- `ndaa-fy2025` → `lockheed-martin` (AUTHORIZES_FUNDING, 0.95)
- `ndaa-fy2025` → `raytheon` (AUTHORIZES_FUNDING, 0.95)
- `ndaa-fy2025` → `northrop-grumman` (AUTHORIZES_FUNDING, 0.95)
- `ndaa-fy2025` → `general-dynamics` (AUTHORIZES_FUNDING, 0.95)
- `ndaa-fy2025` → `huntington-ingalls` (AUTHORIZES_FUNDING, 0.95)
- `ndaa-fy2025` → `bwxt` (AUTHORIZES_FUNDING, 0.95)

**Thesis receipt:** `thesis-defense-primes` — 148 confirming signals, 115 Tier 0, conviction level 5.

## Design principles

1. **Citations are for humans.** A source entry lets anyone verify the original document.
2. **Extracted facts are for the graph.** Structured claims that agents can query.
3. **Proposed edges are for staging.** Claims wait for review before becoming graph edges.
4. **Receipts are for trust.** A receipt records what was believed, why, and what would falsify it.

Each layer has a different audience and a different standard of proof. Mixing them produces documents that are neither verifiable nor queryable.
