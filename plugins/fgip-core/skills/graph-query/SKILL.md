---
name: graph-query
description: Query the FGIP evidence graph for entities, edges, claims, and patterns. Use when investigating ownership structures, policy connections, funding flows, or appointment chains.
---

# FGIP Graph Query

You query the forensic evidence graph to find connections between entities (people, companies, agencies, policies) and verify claims with tier-scored sources.

## Available MCP Tools

- **`mcp__fgip_graph__query_node`** — Look up an entity by name or alias. Returns node properties, tier-0/1 sources, and connected edges.
- **`mcp__fgip_graph__query_edges`** — Find edges of a given type (OWNS, APPOINTED_BY, FUNDED_BY, CAUSED, VOTED_FOR). Returns source tier and confidence.
- **`mcp__fgip_graph__search_claims`** — FTS5 full-text search across all claims in the graph. Returns claim_id, statement, sources, confidence.
- **`mcp__fgip_graph__pattern_match`** — Find structural patterns (both-sides ownership, revolving door, funding loops). Returns matched subgraphs.

## Query Patterns

1. **Entity lookup:** Start with a name → get all edges → follow highest-confidence paths
2. **Ownership chain:** Entity → OWNS edges → target entities → their OWNS edges (2-hop)
3. **Appointment chain:** Person → APPOINTED_BY → Agency → REGULATES → Company → OWNS → same Person?
4. **Claim verification:** Search claim text → check source tiers → verify against tier-0 data
5. **Both-sides test:** Entity → all OWNS edges → partition by policy position → measure overlap

## Source Tiers

| Tier | Meaning | Examples |
|------|---------|---------|
| 0 | Government primary | SEC EDGAR 13F, Congress.gov votes, Treasury TIC, FRED |
| 1 | Authoritative secondary | Court filings, GAO reports, CRS, academic peer-reviewed |
| 2 | Quality journalism | Reuters, Bloomberg, AP with named sources |
| 3 | Analysis/opinion | Think tank reports, editorial, analyst notes |

Only tier-0 and tier-1 edges count toward PROVEN verdicts.
