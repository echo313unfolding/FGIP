# Digital Asset Rails

FGIP models crypto/blockchain/stablecoin/tokenization as a funding-and-settlement rail layer — not as crypto speculation, but as regulated digital-asset infrastructure that connects to existing banking, Treasury, and compliance systems.

## The model

```
law / regulator
→ permitted issuer
→ reserve asset
→ stablecoin / tokenized asset
→ settlement rail
→ bank / broker / transfer agent / exchange
→ liquidity access
→ beneficiary / bottleneck / risk
```

## Layer structure

| Layer | What | Examples |
|-------|------|---------|
| 0 | Law | GENIUS Act, SEC tokenized securities guidance, OCC interpretive letters |
| 1 | Regulators | OCC, FDIC, Federal Reserve, SEC, CFTC, Treasury |
| 2 | Issuers / banks | Permitted payment stablecoin issuers, national banks, bank subsidiaries |
| 3 | Reserve assets | Cash, Treasury bills, repo, bank deposits |
| 4 | Settlement tokens | USDC, PYUSD, bank-issued stablecoins, tokenized deposits |
| 5 | Tokenized assets | Tokenized Treasuries, tokenized money-market funds, tokenized securities |
| 6 | Liquidity venues | Exchanges, transfer agents, broker-dealers, custodians |
| 7 | Beneficiaries / bottlenecks | Compliance vendors, chain infrastructure, custodians |

## Key sources (all Tier 0/1)

- **GENIUS Act** (Tier 0): Creates permitted payment stablecoin issuer framework. Requires 100% reserve backing with liquid assets.
- **OCC rulemaking** (Tier 0): Proposed rules for national bank stablecoin activities.
- **OCC Interpretive Letter 1186** (Tier 0): Confirms bank authority to hold crypto-assets.
- **Treasury AML/CFT proposal** (Tier 0): PPSIs treated as financial institutions under BSA.
- **Federal Reserve analysis** (Tier 0): Payment stablecoins and cross-border payment implications.
- **Richmond Fed** (Tier 0): Stablecoin adoption raises demand for Treasuries and dollar safe assets.
- **SEC tokenized securities statement** (Tier 0): Tokenized securities remain securities under federal law.
- **FDIC** (Tier 0): Payment stablecoins NOT FDIC insured.
- **DTCC tokenization** (Tier 1): Extending market infrastructure into digital assets.
- **WSJ / Bullish-Equiniti** (Tier 1): $4.2B transfer-agent acquisition for tokenization.

## Edge types

| Edge type | Meaning |
|-----------|---------|
| AUTHORIZES_FRAMEWORK_FOR | Law creates regulatory permission |
| REQUIRES_RESERVES | Issuer must hold backing assets |
| BACKED_BY | Token backed by specific reserve asset |
| CREATES_DEMAND_FOR | Activity generates demand for asset |
| ENABLES_PROGRAMMABLE_SETTLEMENT | Rail allows programmable dollar transfer |
| DEPENDS_ON_BANKING_RAILS | Still requires banks for reserves/redemption/compliance |
| BYPASSES_LEGACY_SETTLEMENT | Faster than legacy ACH/wire timing |
| SUBJECT_TO_AML_CFT | Must comply with AML/sanctions obligations |
| NOT_COVERED_BY | Explicitly excluded from protection (e.g., FDIC) |
| TOKENIZES | Represents real-world asset on blockchain |
| SERVES_AS_TRANSFER_AGENT_FOR | Maintains records for tokenized securities |
| ACQUIRES | Corporate acquisition |
| EXPOSES_TO_RUN_RISK | Creates potential run/convertibility risk |
| REGULATES | Regulatory authority over activity |
| IMPLEMENTS | Rulemaking implements statute |

## What stablecoins are in FGIP terms

Stablecoins are not "outside the system." They are:

```
programmable dollar settlement rails
backed by regulated reserves
inside U.S. compliance rails
moving faster than legacy bank settlement
```

The old system:
```
bank account → bank permission → ACH/wire/card → settlement delay → limited access
```

The emerging system:
```
regulated stablecoin issuer → dollar-backed token → blockchain settlement → bank custody/reserves/compliance → faster liquidity movement
```

Important contradiction:
```
Stablecoins bypass parts of bank-controlled access.
Stablecoins do not escape the banking system entirely.
Reserves, custody, redemption, and compliance still run through banks.
```

## What NOT to claim

- Do not claim Vanguard/BlackRock own the Federal Reserve. The Fed Board is a federal agency accountable to Congress.
- Do not claim the Fed is the only place Treasuries exchange. Treasuries trade in a deep secondary market with primary dealers as key intermediaries.
- Do not claim stablecoins pay down debt directly. They may create additional demand for short-term Treasury obligations.
- Do not claim China can instantly kill the dollar by dumping Treasuries. Foreign selling is a pressure vector, not an instant kill switch. Total foreign holdings hit record highs in Feb 2026.
- Do not claim tokenization escapes regulation. SEC: tokenized securities remain securities.

## Graph nodes

```
genius-act
occ
fdic
federal-reserve
sec
treasury
permitted-payment-stablecoin-issuers
stablecoin-reserves
short-term-treasuries
tokenized-securities
payment-stablecoins
programmable-dollar-settlement
legacy-bank-settlement
banking-system
aml-sanctions-compliance
primary-dealers
treasury-auctions
treasury-secondary-market
new-york-fed
foreign-treasury-holders
dtcc
bullish
equiniti
financial-stability-risk
```

## Related theses

- `thesis-dollar-resilience-rails` — Stablecoin reserves as dollar-demand channel
- `thesis-digital-asset-rails` — Infrastructure layer: who controls settlement, custody, compliance

## Data files

```
data/sources/digital_asset_sources.jsonl    # 17 source citations
data/extracted/digital_asset_facts.jsonl    # 18 extracted facts
data/edges/digital_asset_edges_examples.jsonl # 21 candidate edges
```
