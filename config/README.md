# FGIP Configuration

Configuration files for entity normalization and system settings.

## Files

| File | Purpose |
|------|---------|
| `node_aliases.yaml` | Maps common aliases to canonical node IDs |

## Node Aliases

Maps variations of entity names to their canonical `node_id` values.

### Format

```yaml
# alias (lowercase): canonical-node-id
chamber: us-chamber-of-commerce
chamber of commerce: us-chamber-of-commerce
us chamber: us-chamber-of-commerce
```

### Usage

```python
import yaml

with open("config/node_aliases.yaml") as f:
    aliases = yaml.safe_load(f)

# Normalize entity name
raw = "JP Morgan Chase"
canonical = aliases.get(raw.lower(), raw.lower().replace(" ", "-"))
```

### Categories

**Organizations:**
- US Chamber of Commerce
- Cato Institute
- Heritage Foundation
- Federalist Society
- Business Roundtable
- House CCP Committee

**Financial Institutions:**
- JPMorgan Chase → `jpmorgan`
- Goldman Sachs → `goldman-sachs`
- Citibank/Citigroup → `citibank`
- Bank of America → `bofa`
- Morgan Stanley → `morgan-stanley`

**Asset Managers:**
- BlackRock → `blackrock`
- Vanguard → `vanguard`
- State Street → `state-street`

**Companies:**
- Apple/AAPL → `apple`
- Microsoft/MSFT → `microsoft`
- Intel → `intel`
- NVIDIA → `nvidia`

**People:**
- Donald Trump → `trump`
- Marco Rubio → `rubio`
- Scott Bessent → `bessent`

## Adding Aliases

1. Edit `config/node_aliases.yaml`
2. Add lowercase alias → canonical node_id
3. Ensure canonical node_id exists in database
4. Run agents to pick up new aliases

## See Also

- `fgip/agents/citation_loader.py` — Uses aliases for entity normalization
- `fgip/agents/nlp_agent.py` — Entity extraction with alias resolution
