# Draft: GitHub Issue for Sentinel-Intelligence/sentinel-public

**Title:** Integration proposal: FGIP downstream funding chain graph

---

## Summary

[FGIP](https://github.com/echo313unfolding/FGIP) (Fifth Generation Institute for Prosperity) is an MIT-licensed forensic evidence graph that traces federal funding chains from congressional appropriation down to commodity bottleneck and public ticker. We ingest from many of the same Tier-0 sources Sentinel uses (Congress.gov, EDGAR, USASpending, FEC, FARA, Federal Register) and see a natural integration point between the two projects.

**Sentinel traces influence flowing into Congress. FGIP traces capital flowing out of Congress.** The shared join layer is legislators, bills, appropriations, and committees.

## What FGIP adds

### 1. Downstream funding chain depth (6 layers)

Sentinel's graph terminates at the contractor/company level via USASpending edges. FGIP extends that chain further:

```
appropriation → agency → prime contract → sub-tier supplier → commodity input → public ticker
```

Example: NDAA FY2025 → DoD → General Dynamics → HII → BWXT → Cameco (uranium). Five hops from bill to commodity, all from public records.

### 2. Supply chain extractor (10-K parsing)

Our `supply_chain_extractor` agent parses SEC 10-K filings to produce SUPPLIES_TO, DEPENDS_ON, and CUSTOMER_OF edges. 12,400+ proposed edges across defense, energy, semiconductor, and critical minerals sectors. These edges connect Sentinel's contractor nodes to the physical supply chain layer.

### 3. Adversarial testing methodology

FGIP requires every thesis to survive its own counter-argument and a control group comparison before it's considered supported. The most material result so far: our original thesis that Big Three (Vanguard/BlackRock/State Street) showed coordinated intent via CHIPS Act positioning was tested against a non-CHIPS semiconductor control group. CHIPS recipients showed 19.6% common ownership vs. 19.7% for the control group — delta of -0.08%. The intent claim was killed and reframed as passive-indexing-driven structural concentration, consistent with Azar-Schmalz-Tecu's peer-reviewed work on anticompetitive coordination via index-fund concentration.

Separately, congressional overlap on CHIPS-related committees (32 members) was found to be *below* statistical expectation (70.1) — thesis killed.

The methodology forced us to abandon emotionally satisfying claims and replace them with structurally defensible ones. This adversarial framework could be applied to validate IES scores against alternative explanations.

**Honest evidence stratification (v0.1.1, post-provenance fix `d937b87`):**

During pre-publication adversarial review, we identified and fixed a source-provenance bug affecting 23 agents — the propose() pipeline was dropping artifact linkage, causing most claims to show "has a source" while losing tier classification. A subsequent domain-extraction repair recovered 437 Tier-0 and 2,388 Tier-1 sources whose URLs were present but unparsed. Stratified numbers below are computed against the post-fix pipeline. Pre-fix numbers from the v0.1.0 release notes are superseded.

The graph has two layers with different evidence profiles:

**Analytical layer** (6,971 claims — congressional voting, campaign finance, securities, supply chain, trade):
- 75.8% have at least one cited source
- 61.5% backed by ≥1 Tier-0 (government primary) or Tier-1 (professional journalism/research) source
- Strongest corridors: securities 100%, trade 100%, congressional voting 50.5%, campaign finance 50.3%
- Weakest: supply chain 0.5%, DEBT_DOMESTICATION 0% (both need Tier-0 backfill)

**Media signal layer** (6,912 claims — RSS/news-to-entity matching for real-time monitoring):
- 100% have a cited source (by construction — each is an RSS item)
- 66.0% backed by Tier-1 professional sources (NYT, BBC, Politico, The Hill, WSJ)
- These are signal claims ("The Hill reports on [Company]: [headline]"), not analytical findings

**Combined:**
- 13,883 total claims, 87.9% source-linked
- Source breakdown: 533 Tier-0, 2,508 Tier-1, 2,468 Tier-2 (55.2% strong tier)
- 63.8% of all claims backed by ≥1 Tier-0 or Tier-1 source
- Triangulation (3+ independent source domains with ≥1 Tier-0) remains aspirational — 0 claims pass this bar. Median sources per claim is 1. Source depth, not breadth, is the current gap.
- 2,894 verified edges (down from 3,390 pre-dedup) + 80K proposed edges in staging pipeline
- 30.3% of claims backed by Tier-0 government primary sources alone

We publish the stratified numbers — including the zeros — because publishing them is the point. Methodology: `docs/EVIDENCE_TIERS.md`, `docs/THESIS_RECEIPT_SCHEMA.md`.

### 4. Commodity bottleneck layer

FGIP maps physical resource dependencies that create structural exposure:
- Uranium: Cameco sole-source for naval reactors
- Copper: FCX supplies grid modernization contractors
- Rare earths: MP Materials sole domestic source
- Semiconductor fabs: TSMC/Intel/Micron CHIPS recipients

These bottlenecks determine which funding chains have pricing power and which are structurally fragile.

## What Sentinel adds to FGIP

- **IES v3.5 scores** — FGIP has legislator nodes but no influence scoring. IES as node metadata would immediately enrich our conviction engine.
- **Lobbying edges (574K+ LDA)** — FGIP currently has FARA coverage only (~450 edges). Your LDA ingest would fill a major gap.
- **Stock trading edges (16K+)** — Directly relevant to our congressional trading thesis.
- **Entity resolution (46K SAME_AS edges)** — Our deduplication is manual; your SAME_AS methodology would help.

## Proposed integration approach

1. **Schema alignment** — Compare your 67 node labels / 104 relationship types against FGIP's ontology. Identify shared entity types and edge types. Publish a mapping document.
2. **Join layer definition** — Define the shared entities (legislators, bills, committees, agencies, companies) and agree on canonical identifiers.
3. **Bidirectional edge export** — FGIP exports downstream funding chain edges in a format Sentinel can ingest (Cypher or CSV). Sentinel exports IES scores + lobbying edges in a format FGIP can ingest (JSONL or SQLite).
4. **Cross-citation** — Each project cites the other as a complementary data source in documentation and papers.

## Technical details

| | Sentinel | FGIP |
|--|----------|------|
| Graph DB | Neo4j (Cypher) | SQLite + FTS5 |
| Nodes | 465,263 | 2,100+ |
| Edges | 7,341,318 | 2,894 verified + 80K proposed |
| AI model | Qwen2.5-14B (LoRA, Cypher) | 24 Python ingest agents |
| Provenance | XRPL blockchain | SHA256 per edge + source URL |
| License | MIT | MIT |
| Focus | Influence INTO Congress | Capital OUT of Congress |

## About FGIP

- **Repo:** https://github.com/echo313unfolding/FGIP
- **Mission:** https://github.com/echo313unfolding/FGIP#why-we-exist
- **Geospatial layer:** https://github.com/echo313unfolding/fgip-globe
- **Graph stats:** 2,100+ nodes, 2,800+ edges, 80K+ proposed edges, 24 ingest agents
- **Key findings:** Structural capital concentration (Big Three -0.08% delta, intent claim killed → reframed as passive indexing), M2 real inflation backtest (7/7, 3/3 adversarial attacks survived), defense funding chain tracing (NDAA → 5 hops → commodity)

We're not proposing a merge — the architectures and focus areas are different enough that they should remain separate projects. We're proposing a defined integration layer so that users of either graph can query across both.

Happy to discuss schema alignment in this thread or async.
