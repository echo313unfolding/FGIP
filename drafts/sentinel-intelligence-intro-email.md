# Draft: Intro Email to Sentinel Intelligence

**To:** contact@sentinelintel.org
**From:** [your email]
**Subject:** FGIP — complementary downstream graph, potential integration

---

Hi Sentinel team,

I run the Fifth Generation Institute for Prosperity (FGIP), an open-source forensic evidence graph that traces federal funding chains from appropriation to commodity bottleneck. MIT licensed, SQLite-backed, 2,100+ nodes, 2,800+ edges, 24 ingest agents pulling from the same federal sources you do — Congress.gov, EDGAR, USASpending, FEC, FARA, Federal Register, NRC ADAMS.

I've been studying your work. Two things jumped out:

**1. We're complementary, not competitive.**

Sentinel maps influence flowing INTO Congress — donors, lobbyists, PACs, trades, committee jurisdiction conflicts. FGIP maps capital flowing OUT of Congress — where appropriated money actually goes after a bill passes. We trace the downstream chain across six layers:

```
appropriation → agency → prime contract → sub-tier supplier → commodity input → public ticker
```

Your IES v3.5 scores legislators by influence exposure. Our conviction engine scores funding chains by evidence quality — requiring adversarial counter-theses and control group comparisons before a finding is considered supported. Together those form a full loop: influence in, money out.

**2. Concrete integration points.**

Things FGIP could contribute to Sentinel:

- **Supply chain extractor** — Our `supply_chain_extractor` agent parses 10-K filings for SUPPLIES_TO, DEPENDS_ON, and CUSTOMER_OF relationships. 12,400+ proposed edges so far. This extends your contractor nodes downstream to the commodity layer where the actual physical bottlenecks live (uranium, copper, rare earths, fab capacity).

- **Adversarial testing methodology** — FGIP requires every thesis to survive its own counter-argument before it's considered supported. The most material result: our original thesis that Vanguard/BlackRock/State Street showed coordinated intent via CHIPS Act positioning was tested against a control group — CHIPS recipients (19.6% Big Three ownership) vs. non-CHIPS semiconductors (19.7%). Delta: -0.08%. We killed the intent claim and reframed as passive-indexing-driven structural concentration, consistent with Azar-Schmalz-Tecu's peer-reviewed work. The methodology forced us to abandon an emotionally satisfying claim and replace it with a structurally defensible one. Happy to share the framework for stress-testing IES scores against alternative mechanisms.

- **Funding chain depth** — The Columbia-class submarine program alone traces: NDAA FY2025 ($895.2B) → DoD → General Dynamics (prime) → HII (hull construction) → BWXT (naval reactors) → Cameco (uranium). That's five hops from bill to commodity, all in public records, none visible in a single database.

Things FGIP could use from Sentinel:

- **IES scores** as metadata on our legislator nodes (we have the same members but no influence scoring)
- **Lobbying edges** — your 574K LDA edges far exceed our FARA-only coverage
- **Stock trading edges** — we have a congressional trading thesis but only ~450 FARA edges, not the 16K+ trade records you've ingested
- **Entity resolution** — your 46K SAME_AS edges would help our deduplication

**3. Shared concern.**

Your README notes that Sunlight Foundation (2020), MapLight (2022), ProPublica Represent (2023), and OpenSecrets API (2025) have all shut down. FGIP exists for the same reason you do — the transparency infrastructure gap is widening and someone has to build the replacement with public data. Two MIT-licensed projects building different halves of the same graph seems like an obvious place to at least share schema documentation and discuss a join layer.

**4. One housekeeping note.**

We have a separate project called `echo-sentry` (security monitoring, SSM+Transformer hybrid) — previously named `sentinel-hybrid-stack`. We renamed it specifically to avoid any confusion with your project. Different domain entirely.

---

**Links:**
- FGIP: https://github.com/echo313unfolding/FGIP
- Mission statement: https://github.com/echo313unfolding/FGIP#why-we-exist
- Geospatial layer (new): https://github.com/echo313unfolding/fgip-globe
- HXQ tensor compression: https://github.com/echo313unfolding/helix-substrate

Happy to jump on a call or keep it async. Congratulations on the IC2S2 submission — the IES validation methodology looks solid.

[Your name]
