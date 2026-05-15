# OSINT Agent Landscape — Competitive Intelligence

Last updated: 2026-05-15

## Closest Peers

### Sentinel Intelligence (sentinelintel.org)
**Status: Primary competitor. Worth monitoring.**

Claims 33M+ entities, 7.3M+ connections. Maps campaign donors, federal
contractors, lobbyists, legislators, dark money flows. ML models for
influence pattern detection. Natural-language queries like "Who traded
NVDA before the CHIPS Act?" and "Dark money flows to Senate Banking
Committee."

**Where they're stronger:** Raw entity count (~17x FGIP), influence
pattern ML, public-facing UI.

**Where FGIP is differentiated:**
- Funding-chain-to-commodity-to-ticker depth (6-layer tracing)
- Timing cascade model (backtested against Virginia 2019-2022)
- Adversarial testing built into methodology (3/3 attacks survived)
- Field intelligence integration (HUMINT from construction sites)
- Extraction rate analysis (M2 backtest, 7/7 confirmed)
- Supply chain tracing to commodity bottleneck layer

**Action:** Study their entity/edge ontology. Identify integration
opportunities vs differentiation angles.

### LittleSis (Public Accountability Initiative)
**Status: Ingest as Tier 1 source. Agent built.**

400K+ entities, 1.6M+ relationships. Running since 2009. Open API.
Board memberships, campaign contributions, lobbying ties. Community
curated with editorial review.

- API: https://littlesis.org/api/
- GitHub: github.com/public-accountability/littlesis-rails
- **FGIP agent:** `managed-agents/littlesis-ingest/`

### OCCRP Aleph
**Status: Monitor for cross-border investigations.**

Investigative data platform from the Organized Crime and Corruption
Reporting Project. Millions of leaked + public records, cross-border.
Relevant when FGIP needs to trace ownership chains internationally.

### OpenSanctions
**Status: Ingest as Tier 0 source. Agent built.**

320+ data sources. Sanctions lists, PEP databases, watchlists.
Free for non-commercial use.

- API: https://api.opensanctions.org/
- GitHub: github.com/opensanctions/opensanctions
- **FGIP agent:** `managed-agents/opensanctions-ingest/`

### OpenCorporates
**Status: Ingest as Tier 1 source. Agent built.**

200M+ companies across 140 jurisdictions. Critical for shell LLC
identification (data center developers use shell companies).

- API: https://api.opencorporates.com/
- **FGIP agent:** `managed-agents/corporate-registry/`

## Agent Frameworks (Pattern Sources)

### OpenOSINT (github.com/OpenOSINT/OpenOSINT)
LLM-driven OSINT orchestrator. AI-powered agent with interactive REPL,
MCP server, and CLI. Local OSINT scripts mapped as tools.

**Pattern to adopt:** LLM as reasoning engine, local scripts as tools,
dynamic orchestration where agent pivots based on findings.

### SYNINT (github.com/gs-ai/SYNINT)
46 agents, staged pipeline orchestration, concurrent run-all execution.
Multi-engine collector abstraction with graceful fallback.

**Pattern to adopt:** Staging discipline — collection → entity resolution
→ history → media forensics → infrastructure pivoting → synthesis/export.

### Fackel (github.com/flaviomilan/fackel)
Multi-agent framework using ReAct pattern with HitL approval gates and
LLM-as-judge quality scoring.

**Pattern to adopt:** Conditional routing after each phase based on
quality score. Human approval gate before "active" actions. Markdown-first
skill definitions — same pattern as Anthropic's plugin architecture.

### awesome-osint-mcp-servers (github.com/soxoj/awesome-osint-mcp-servers)
Curated list of OSINT MCP servers. Notable tools:
- **StockScope** — SEC EDGAR financial intelligence, free, no API key
- **CompanyScope** — Company intelligence from 8 public sources
- **OpenOSINT** — OSINT agent with MCP server
- **Voidly** — Internet censorship intelligence (116 tools, 119+ countries)

**Action:** Evaluate StockScope and CompanyScope as MCP tool additions
to FGIP's Claude Code integration.

## Congressional Trading Analysis

### Quiver Quantitative
STOCK Act disclosures structured. Should be a Tier 1 source in FGIP.

### Capitol Trades
Public-facing tracker. Useful for cross-checking extraction quality.

### congressional-trading-system (github.com/tom2tomtomtom)
Z-score anomaly detection for unusual congressional trading volume,
behavioral clustering by member, event-correlation analysis.

**Pattern to adopt:** Statistical methodology for detecting information
channels — directly applicable to FGIP's congressional overlap analysis.

## Anthropic Templates

### claude-for-legal (github.com/anthropics/claude-for-legal)
Published 2026-05-12. 12 plugins, 80+ agents, 20+ MCP connectors.
Apache 2.0. Same SKILL.md pattern as financial-services.

**This is the template for publishing FGIP as an open plugin suite.**
Structure: `plugins/agent-plugins/<slug>/`, `agents/<slug>.md`,
`skills/`, `managed-agent-cookbooks/<slug>/agent.yaml`.

### claude-for-financial-services (github.com/anthropics/financial-services)
Already adapted for FGIP's claim-verifier, tariff-analyzer, entity-screener.

## Integration Priority

| Source | Tier | Agent Status | Priority |
|--------|------|-------------|----------|
| LittleSis | 1 | Built | HIGH — 1.6M relationships |
| OpenSanctions | 0 | Built | HIGH — sanctions screening |
| OpenCorporates | 1 | Built | HIGH — shell LLC tracing |
| Quiver Quantitative | 1 | Not built | MEDIUM — congressional trades |
| StockScope MCP | 1 | Not built | MEDIUM — SEC EDGAR via MCP |
| OCCRP Aleph | 1 | Not built | LOW — cross-border only |
| Sentinel Intelligence | — | Competitor | MONITOR — study ontology |
