# FGIP Analysis

Risk scoring, intelligence analysis, gap detection, and economic modeling for the FGIP knowledge graph.

## Modules Overview

| Module | Purpose |
|--------|---------|
| `risk_scorer.py` | Thesis confidence, investment risk, signal convergence |
| `gap_detector.py` | Missing edges, agent suggestions |
| `industrial_base_scorer.py` | Domestic capacity, supplier concentration, reshoring momentum |
| `bottleneck_registry.py` | Supply chain vulnerabilities |
| `purchasing_power.py` | Personal financial exposure analysis |
| `economic_model.py` | Dynamic variable tracking, policy mechanism modeling |
| `signal_convergence.py` | Multi-source signal verification |
| `provenance_tracker.py` | Knowledge origin tracking (YouTube, RSS, search) |
| `provenance.py` | Data source verifiability gating |
| `compression_patterns.py` | Information-theoretic pattern detection |
| `adversarial.py` | Stress-testing framework |

---

## Risk Scoring

### Thesis Risk Score (0-100, higher = more confident)

```python
from fgip.analysis import RiskScorer

scorer = RiskScorer("fgip.db")
result = scorer.thesis_risk_score(path_nodes=["blackrock", "chips-act", "intel"])
print(f"Thesis confidence: {result.score}%")
```

**Components:**
- Source tier scoring: Tier-0 (+30), Tier-1 (+20), Tier-2 (+5) — max 50 pts
- Path coherence: High-confidence edges (+10 each) — max 30 pts
- Independent validations: Tier 0/1 sources (+5 each) — max 20 pts
- Signal layer nodes (+2 each) — max 15 pts
- Accountability/crime nodes (+5 each) — max 15 pts

### Investment Risk Score (0-100, higher = riskier)

```python
result = scorer.investment_risk_score("intel")
print(f"Risk: {result.score} → {result.recommendation}")
```

**Risk UP factors:**
- Anti-tariff amicus briefs (+30)
- BlackRock/Vanguard ownership (+10)
- China dependency (+20)
- Customer concentration (+10)

**Risk DOWN factors:**
- Government equity stake (-2x stake, max -25)
- CHIPS funding (-15)
- Domestic facility built (-15)
- Domestic supply chain (-10)

**Recommendations:** buy (<30), hold (30-50), reduce (50-70), avoid (>70)

### Signal Convergence (0-6)

```python
result = scorer.signal_convergence("reshoring")
print(f"Convergence: {result.score}/6 → {result.confidence}")
```

**Categories checked:**
1. Government — Officials validating
2. Independent Media — SRS, JRE, Breaking Points
3. Academic — Trade economists
4. Market Data — ETF flows, Great Rotation
5. Criminal Cases — Fraud proving system failure
6. Industry Insider — Defense/tech CEOs

**Confidence levels:** extreme (5-6), high (3-4), medium (1-2), low (0)

---

## Gap Detection

Identifies missing edges and suggests which agents to run.

```python
from fgip.analysis import GapDetector

detector = GapDetector("fgip.db")
report = detector.generate_report()

# Get prioritized agent suggestions
suggestions = detector.suggest_agent_runs(limit=10)
for s in suggestions:
    print(f"{s.agent_name}: {s.priority} — {s.reason}")
```

### Gap Types Detected

| Gap Type | What It Finds |
|----------|---------------|
| Missing Ownership | COMPANY without OWNS_SHARES edges |
| Missing Lobbying | ORGANIZATION without LOBBIED_FOR edges |
| Missing Rulemakings | LEGISLATION without RULEMAKING_FOR edges |
| Missing Awards | CHIPS recipients without AWARDED_GRANT edges |
| Orphan Nodes | Nodes with zero edges |
| Source Coverage | Edges with only Tier-2 sources |
| Temporal Gaps | Nodes inactive >6 months |
| Missing Reciprocals | Asymmetric relationships |

### Node Type Expectations

```
COMPANY: OWNS_SHARES, SUPPLIES, AWARDED_CONTRACT, AWARDED_GRANT
ORGANIZATION: LOBBIED_FOR, DONATED_TO, MEMBER_OF
LEGISLATION: RULEMAKING_FOR, IMPLEMENTED_BY, AUTHORIZED_BY
FINANCIAL_INST: OWNS_SHARES, INVESTED_IN, SITS_ON_BOARD
AGENCY: RULEMAKING_FOR, IMPLEMENTED_BY, RULED_ON
PERSON: EMPLOYED, SITS_ON_BOARD, APPOINTED_BY
```

---

## Industrial Base Scoring

Measurable domestic manufacturing capacity metrics.

```python
from fgip.analysis import IndustrialBaseScorer

scorer = IndustrialBaseScorer("fgip.db")
report = scorer.generate_full_report()
```

### Four Core Scores (0-100)

**1. Domestic Capacity Score**
- Facilities by status: Operational (1.0), Construction (0.6), Announced (0.3), Planned (0.1)
- Investment amount: $100B = max 30 pts
- Operational capacity: 200k wafers/month = max 20 pts

**2. Supplier Concentration Risk** (higher = worse)
- Single-source dependencies
- Supplier diversity: <5 suppliers = 30 pts risk
- Geographic concentration: >50% in one location = 30 pts

**3. Reshoring Momentum Score**
- Facility additions: 6 pts per facility
- FUNDED_PROJECT edges: 3 pts per
- AWARDED_GRANT edges: 2 pts per

**4. Bottleneck Severity Score** (higher = worse)
- Supplier in-degree concentration
- DEPENDS_ON edges
- Explicit BOTTLENECK_AT edges

**5. Overall Health Score (composite)**
```
30% Capacity + 30% Momentum + 20% (100 - Concentration) + 20% (100 - Bottleneck)
```

---

## Bottleneck Registry

Documented supply chain vulnerabilities.

```python
from fgip.analysis import BottleneckRegistry, SeverityLevel

registry = BottleneckRegistry()
critical = registry.get_critical()
```

### Registered Bottlenecks (14 total)

| Bottleneck | Type | Severity |
|------------|------|----------|
| Spruce Pine Ultra-High-Purity Quartz | SINGLE_SOURCE | CRITICAL |
| EUV Lithography (ASML) | MONOPOLY | CRITICAL |
| US Advanced Packaging | CAPACITY_CONSTRAINED | HIGH |
| HALEU Uranium Enrichment | CAPACITY_CONSTRAINED | HIGH |
| Large Power Transformers | CAPACITY_CONSTRAINED | HIGH |
| Rare Earth Processing | GEOGRAPHIC_CONCENTRATION | HIGH |
| Semiconductor-Grade Neon | GEOPOLITICAL_RISK | MEDIUM |

---

## Purchasing Power Analysis

Personal financial exposure to M2 inflation.

```python
from fgip.analysis import PurchasingPowerAnalyzer, PersonalScenario

analyzer = PurchasingPowerAnalyzer("fgip.db")
scenario = PersonalScenario(
    monthly_expenses=5000,
    current_savings=100000,
    savings_yield=0.045,
    debt_balance=0,
    debt_apr=0,
    income_monthly=8000,
)
report = analyzer.analyze(scenario)
print(report.to_json())
```

### Key Economic Parameters

| Metric | Value | Source |
|--------|-------|--------|
| Real Inflation (M2) | 6.3% | FRED M2SL, 25-year backtest |
| Official CPI | 2.7% | BLS |
| Hidden Extraction | 3.6% | M2 - CPI gap |
| Treasury Yield (4-week) | 4.5% | Treasury Direct |

### Core Calculations

```
Real Savings Yield = Nominal Yield - M2 Inflation
Real Debt Rate = Nominal APR - M2 Inflation
Purchasing Power Leak = Savings × (Inflation - Yield)
```

### Scenario Shocks Modeled

| Scenario | M2 Rate | Notes |
|----------|---------|-------|
| current_m2 | 6.3% | Baseline |
| fed_normalization | 3.0% | Fed achieves target |
| crisis_10pct | 10.0% | Emergency printing |
| genius_act | 4.5% | Stablecoin corridor replaces Fed |

---

## Economic Modeling

Dynamic variable tracking and policy mechanism propagation.

```python
from fgip.analysis import EconomicModel, CorrectionMechanism

model = EconomicModel.get_baseline_model()
genius = CorrectionMechanism(
    mechanism_id="genius-act",
    affects_variables=["fed_treasury_purchases", "m2_growth_rate"],
    # ...
)
result = model.propagate_effect(genius)
```

### Key Insight

> Static analysis shows 10.8% extraction. But 6.3% is M2-based inflation CAUSED BY Fed printing. GENIUS Act replaces Fed printing → M2 drops → inflation drops → extraction converges to 4.5%.

**Cannot use the disease as argument against the cure.** Dynamic modeling required.

### Baseline Variables Tracked

| Variable | Baseline | Unit |
|----------|----------|------|
| Fed Treasury Purchases | 100% | % of issuance |
| M2 Growth Rate | 6.3% | % annual |
| Real Inflation | 6.3% | % annual |
| Treasury Yield 4-week | 4.5% | % annual |
| Hidden Extraction | 3.6% | % annual |

---

## Signal Convergence

Compares independent signals from multiple categories.

```python
from fgip.analysis import SignalConvergenceAnalyzer

analyzer = SignalConvergenceAnalyzer("fgip.db")
report = analyzer.generate_convergence_report()
```

### Promethean Action Claims Verified

| Claim | Status | FRED Series |
|-------|--------|-------------|
| PA-001: 136 factories breaking ground | Verified | MANEMP |
| PA-002: Trade deficits plunging | Verified | BOPGSTB |
| PA-003: Federal deficit cut by $390B | Verified | — |
| PA-004: Kevin Warsh nominated Fed Chair | Verified | — |
| PA-005: Bessent invokes Hamilton at Davos | Verified | — |

### FRED Series Tracked

- `BOPGSTB` — Trade Balance
- `MANEMP` — Manufacturing Employment
- `INDPRO` — Industrial Production Index
- `M2SL` — M2 Money Supply
- `CPIAUCSL` — Consumer Price Index
- `PNFI` — Business Investment

---

## Provenance Tracking

Maps knowledge graph edges back to originating signals.

```python
from fgip.analysis import ProvenanceTracker

tracker = ProvenanceTracker("fgip.db")
timeline = tracker.get_knowledge_timeline()

# Find what signals preceded an edge
precursors = tracker.find_signal_precursors(edge, days_before=30)
```

### Artifact Sources

- YouTube watch history (`data/artifacts/youtube_takeout/`)
- YouTube search history
- RSS articles (`data/artifacts/rss/`)

---

## Compression Patterns

Information-theoretic pattern detection using SHAKE256 fingerprinting.

```python
from fgip.analysis import CompressionPatternAnalyzer

analyzer = CompressionPatternAnalyzer("fgip.db")
report = analyzer.generate_report()

# Find similar nodes by neighborhood structure
similar = analyzer.find_similar_nodes("blackrock", limit=10)

# Detect anomalies
anomalies = analyzer.detect_anomalies(cohort_size=30)
```

### Key Principle

> Real causal chains compress better than random paths because they have structural regularity.

### Detection Constraints

1. **Deterministic** — All operations reproducible from seed
2. **Baseline-corrected** — Compare against degree-matched random
3. **Auditable** — JSON receipts with determinism seals
4. **Scalable** — Cache results, avoid O(n²)
5. **Hypothesis generator** — NOT proof (mark as HYPOTHESIS)

---

## Adversarial Testing

Stress-tests every finding with three attack types.

```python
from fgip.analysis import AdversarialAgent

agent = AdversarialAgent("fgip.db")
result = agent.test_inflation_rate()
print(f"Status: {result.status}")  # VERIFIED, WEAKENED, or REFUTED
```

### Three Attack Types

| Attack | Question |
|--------|----------|
| Statistical | Is this significant or random chance? |
| Scale | Is this material or noise? |
| Alternative Explanation | Is there a simpler explanation? |

### Finding Status

| Status | Meaning |
|--------|---------|
| VERIFIED | Survived all attacks |
| WEAKENED | Failed some attacks |
| REFUTED | Failed all attacks |
| UNTESTED | No tests run yet |

### Validated Findings

| Finding | Status | Attacks Survived |
|---------|--------|------------------|
| M2 = 6.3% real inflation | VERIFIED | 3/3 |
| Ownership both sides | VERIFIED (refined) | Passive indexing |
| Congress overlap | WEAKENED | Below statistical expectation |
| GENIUS Act extraction | UNTESTED | Needs scale threshold |

---

## CLI Usage

```bash
# Gap detection
python3 -m fgip.cli gaps detect
python3 -m fgip.cli gaps suggest-agents

# Risk scoring
python3 -m fgip.cli risk thesis
python3 -m fgip.cli risk investment intel

# Industrial base
python3 -m fgip.cli industrial-base report

# Adversarial testing
python3 -m fgip.analysis.adversarial
```

---

## API Endpoints

If running the web server:

```bash
# Thesis score
curl http://localhost:5000/api/risk/thesis

# Gap detection
curl http://localhost:5000/api/gaps

# Economic scenarios
curl http://localhost:5000/api/scenarios
```

---

## File Index

| File | Key Classes |
|------|-------------|
| `risk_scorer.py` | RiskScorer, ThesisRiskResult, InvestmentRiskResult |
| `gap_detector.py` | GapDetector, Gap, AgentSuggestion, GapReport |
| `industrial_base_scorer.py` | IndustrialBaseScorer, ScoreResult |
| `bottleneck_registry.py` | BottleneckRegistry, SupplyChainBottleneck |
| `purchasing_power.py` | PurchasingPowerAnalyzer, PersonalScenario, PurchasingPowerReport |
| `economic_model.py` | EconomicModel, CorrectionMechanism, DynamicScenario |
| `signal_convergence.py` | SignalConvergenceAnalyzer |
| `provenance_tracker.py` | ProvenanceTracker, EdgeProvenance, KnowledgeTimeline |
| `provenance.py` | DataProvenance |
| `compression_patterns.py` | CompressionPatternAnalyzer, MotifMatch, AnomalyResult |
| `adversarial.py` | AdversarialAgent, AdversarialTest, AdversarialAttack |
