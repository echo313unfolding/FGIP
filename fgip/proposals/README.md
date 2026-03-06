# FGIP Proposals

Tier-0 backed edge proposals for graph modifications.

## Contents

| File | Purpose |
|------|---------|
| `genius_act_edges.py` | GENIUS Act S.394 Section 4(a) edge proposals |

## GENIUS Act Edges

Edge proposals backed by verbatim bill text from GPO/GovInfo.

```python
from fgip.proposals.genius_act_edges import PROPOSED_CLAIMS, PROPOSED_EDGES, SECTION_4A_QUOTES
```

### Source

```
https://www.govinfo.gov/content/pkg/BILLS-119s394is/html/BILLS-119s394is.htm
```

### Evidence Quotes (Tier-0)

| Quote ID | Citation | Summary |
|----------|----------|---------|
| `1_to_1_reserve` | S.394 Section 4(a)(1)(A) | 1:1 reserve requirement |
| `permitted_reserves` | S.394 Section 4(a)(1)(A)(i-vii) | Eligible reserve assets |
| `rehypothecation_ban` | S.394 Section 4(a)(2) | Reserves cannot be rehypothecated |
| `monthly_certification` | S.394 Section 4(a)(3)(B) | CEO/CFO monthly certification |
| `criminal_penalty` | S.394 Section 4(a)(3)(C) | False certification = 18 USC 1350(c) |
| `activity_limitation` | S.394 Section 4(a)(6)(A) | Permitted issuer activities |

### Proposed Claims

Claims backed by exact bill text with confidence 0.95:

- `genius-4a-1to1-reserve` — 1:1 reserve requirement
- `genius-4a-treasury-eligible` — Short-term Treasuries permitted
- `genius-4a-rehypothecation-ban` — Rehypothecation banned
- `genius-4a-ceo-cfo-certification` — Monthly officer certification
- `genius-4a-criminal-penalty` — False certification criminal penalty
- `genius-4a-activity-limitation` — Issuer activity restrictions

### Usage

```python
# Load into staging
from fgip.proposals.genius_act_edges import stage_genius_edges

staged = stage_genius_edges("fgip.db")
print(f"Staged {staged} edges")
```

## Adding New Proposals

1. Create a new file in this directory
2. Include exact citations to Tier-0 sources
3. Set `status: "PROVEN"` only for verbatim quotes
4. Use `status: "HYPOTHESIS"` for inferences
5. Run staging tool to load into database
