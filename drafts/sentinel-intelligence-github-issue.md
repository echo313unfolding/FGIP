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

**Honest evidence stratification (v0.1.0):**
- 13,883 claims (including proposed-edge candidates in staging)
- 87.9% have at least one cited source (any tier)
- 10.5% backed by ≥1 Tier-0 or Tier-1 government/professional source
- Triangulation (3+ independent source domains, ≥1 Tier-0) is aspirational — zero claims currently pass this bar in the database
- Source breakdown: 96 Tier-0, 120 Tier-1, 5,293 Tier-2 (3.9% strong tier)
- Edges decreased from 3,390 to 2,894 in v0.1.0 cut (deduplication discipline, not accumulation)

We publish the low numbers because publishing them is the point. Methodology documented in `docs/EVIDENCE_TIERS.md` and `docs/THESIS_RECEIPT_SCHEMA.md`.

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
| Edges | 7,341,318 | 2,894 verified + 69K proposed |
| AI model | Qwen2.5-14B (LoRA, Cypher) | 24 Python ingest agents |
| Provenance | XRPL blockchain | SHA256 per edge + source URL |
| License | MIT | MIT |
| Focus | Influence INTO Congress | Capital OUT of Congress |

## About FGIP

- **Repo:** https://github.com/echo313unfolding/FGIP
- **Mission:** https://github.com/echo313unfolding/FGIP#why-we-exist
- **Geospatial layer:** https://github.com/echo313unfolding/fgip-globe
- **Graph stats:** 2,100+ nodes, 2,800+ edges, 69K+ proposed edges, 24 ingest agents
- **Key findings:** Structural capital concentration (Big Three -0.08% delta, intent claim killed → reframed as passive indexing), M2 real inflation backtest (7/7, 3/3 adversarial attacks survived), defense funding chain tracing (NDAA → 5 hops → commodity)

We're not proposing a merge — the architectures and focus areas are different enough that they should remain separate projects. We're proposing a defined integration layer so that users of either graph can query across both.

Happy to discuss schema alignment in this thread or async.
