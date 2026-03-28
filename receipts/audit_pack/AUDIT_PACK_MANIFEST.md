# FGIP Audit Pack Manifest
Generated: 2026-02-24T15:50:00Z

## Database Snapshot
- **File**: `fgip.db.snapshot`
- **SHA256**: `ae7303df60e6ba537114c4febfdf5d0668b0d1e931cd8343a9da4a61ede226a1`

## Graph Statistics
| Metric | Value |
|--------|-------|
| Total Nodes | 1,146 |
| Total Edges | 1,284 |
| Problem Edges | 97 |
| Correction Edges | 64 |
| Both-Sides Patterns | 7 |
| Convergence Score | 72.7% |
| Dynamic Thesis Score | 74.6% |

## Source Quality Distribution
| Tier | Sources | Description |
|------|---------|-------------|
| 0 | 67 | Government Primary (congress.gov, treasury.gov, etc.) |
| 1 | 118 | Regulated Filings (SEC, FEC, FARA) |
| 2 | 557 | Quality Secondary (news, academic) |

## Claims by Tier
| Tier | Confirmed | Evidenced | Partial | Missing |
|------|-----------|-----------|---------|---------|
| 0 | 11 | 15 | 86 | 0 |
| 1 | 1 | 1 | 98 | 0 |
| 2 | 0 | 37 | 185 | 67 |

## GENIUS Act Debt Domestication Chain (VERIFIED)
```
genius-act-2025 --ENABLES--> debt-domestication     [100%] congress.gov
debt-domestication --REDUCES--> foreign-leverage   [100%] treasury.gov
foreign-leverage --BLOCKS--> tariff-enablement     [100%] historical analysis
tariff-enablement --FUNDS--> reshoring-2025        [100%] ustr.gov
reshoring-2025 --IMPLEMENTED_BY--> chips-act       [100%] commerce.gov
chips-act --REDUCES--> trade-deficit               [100%] census.gov
```

## Key Findings

### Both-Sides Patterns (95% confidence)
1. **Intel** - 7 problem edges, 6 correction edges
2. **Micron** - 3 problem edges, 2 correction edges
3. **Vanguard Group** - 5 problem edges, 3 correction edges
4. **State Street** - 5 problem edges, 3 correction edges
5. **BlackRock** - 5 problem edges, 3 correction edges

### Dynamic Scenarios
| Scenario | Extraction Change | Thesis Boost |
|----------|-------------------|--------------|
| chips-act-reshoring | 10.8% → 10.5% | +0.6 |
| genius-act-partial | 10.8% → 9.5% | +2.5 |
| genius-act-full | 10.8% → 6.7% | +5.7 |

## GENIUS Act Version Diff (Key Finding)
The enacted GENIUS Act (S.394) includes:
- **Fed account reserves**: Issuers can hold reserves at Fed earning IORB
- **Catch-all clause**: Treasury Secretary can approve alternative reserves
- **Tokenized reserves**: Explicitly allowed as backing

**Implication**: "Forced Treasury demand" is NOT structurally guaranteed by law.
Issuers may rationally choose Fed accounts over T-bills depending on IORB vs bill yields.

## Weakest Links Requiring Tier-0/1 Upgrade

1. `chips-act --AWARDED_GRANT--> intel` - Source: MISSING (should be commerce.gov award)
2. `genius-act-2025 --CORRECTS--> stablecoin-framework-us` - Source: correction_loader (not statute text)
3. Many BENEFITS_FROM edges are inferences, not primary source claims

## Files in This Pack

| File | SHA256 |
|------|--------|
| schema.sql | `b14f932eb9df957c...` |
| causal_chains.txt | `8a4abb03d81ad81b...` |
| source_quality_report.txt | `4381a5c6cc3a5ed7...` |

## Audit Commands

```bash
# Verify database integrity
sha256sum receipts/audit_pack/fgip.db.snapshot

# Query specific chains
sqlite3 receipts/audit_pack/fgip.db.snapshot "
SELECT * FROM edges 
WHERE from_node_id = 'genius-act-2025' OR to_node_id = 'genius-act-2025'
"

# Check source tiers for any edge
sqlite3 receipts/audit_pack/fgip.db.snapshot "
SELECT e.*, s.tier 
FROM edges e 
LEFT JOIN claims c ON e.claim_id = c.claim_id
LEFT JOIN claim_sources cs ON c.claim_id = cs.claim_id
LEFT JOIN sources s ON cs.source_id = s.source_id
WHERE e.edge_id = 'genius-enables-domestication'
"
```
