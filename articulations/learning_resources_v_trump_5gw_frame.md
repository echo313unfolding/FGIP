# The Amicus Asymmetry and the Fifth-Generation Warfare Frame

**Date:** 2026-05-02
**Status:** Working document. Claims tagged EVIDENCED / GAP.
**Graph anchor:** `learning-resources-v-trump` (node exists)
**Case:** Learning Resources, Inc. v. Trump, 607 U.S. ___ (2026), No. 24-1287

---

## 1. The Case

On February 20, 2026, the Supreme Court held 6-3 that IEEPA does not authorize
the President to impose tariffs. The majority (Roberts, joined by Sotomayor,
Kagan, Gorsuch, Barrett, Jackson on core holding) ruled on statutory
interpretation grounds. A Roberts/Gorsuch/Barrett plurality applied the major
questions doctrine. Kagan/Sotomayor/Jackson concurred on statutory text alone,
declining to invoke MQD.

Kavanaugh dissented (joined by Thomas and Alito), arguing IEEPA plainly
authorizes tariffs and the MQD should not apply in foreign affairs contexts.

**EVIDENCED.** Verified from SCOTUSblog, Lawfare, Justia, opinion PDF.

---

## 2. The 37-6-1 Asymmetry

44 amicus briefs filed at merits stage:

- **37 supporting challengers** (anti-tariff)
- **6 supporting government** (pro-tariff)
- **1 supporting neither** (Prof. Aditya Bamzai)

### Pro-tariff filers (supporting government):

| Filer | Type | Frame |
|---|---|---|
| America First Policy Institute (AFPI) | Trump-aligned policy institute | IEEPA grants broad authority; congressional intent |
| American Center for Law and Justice (ACLJ) | Religious conservative legal org | Separation of powers; judicial deference in foreign affairs |
| America's Future | Conservative legal org | Presidential authority |
| U.S. Representative Darrell Issa, et al. | Congressional members | Legislative intent |
| Professor Chad Squitieri | Law professor (Catholic University) | Statutory interpretation |
| Jill Homan | Individual (Trump policy advisor) | Executive authority |

### How the 5GW frame reached the Court

No defense-strategic institution filed directly as amicus — but that's
structurally expected. MWI, Army War College, Naval War College are research
centers; they publish analysis, they don't file briefs. The pipeline is:
research institution publishes → litigant cites. That's exactly what happened.

**America's Future** (William J. Olson, P.C.) carried the 5GW frame into the
record by citing:
- **N. Dockery, "The Domestic Fentanyl Crisis in Strategic Context: Part III —
  Responding to China's Drug Warfare," Modern War Institute at West Point
  (Apr. 2025).** Footnote 3, page 9.
- **R. Greenway, et al., "A Strategy to Revitalize the Defense Industrial
  Base for the 21st Century," The Heritage Foundation (Apr. 7, 2025).**
  Footnote 7, page 9.

The brief frames tariffs as response to "a one-sided trade war being waged
against the United States" that "hollowed out" manufacturing and "undermined
our defense industrial base." It uses the language of warfare ("China's Drug
Warfare") via the MWI citation. This is the standard channel: research
produces the facts, litigants carry them into court.

### The directional split in the security establishment

Two national-security-focused briefs were filed — both ANTI-tariff:

1. **"Former Senior Military, National Security, and Foreign Policy Government
   Officials"** — Former CIA director, NSA director, ambassadors, White House
   counsel, deputy secretary of state, acting attorney general. Filed supporting
   challengers.

2. **"National Security Officials"** — Filed supporting challengers.

The security establishment's former leadership filed against the tariffs on
statutory/separation-of-powers grounds. The defense-intellectual output (MWI's
analysis of China's drug warfare, Heritage's defense industrial base strategy)
supported the tariff rationale. The same national security apparatus produced
analysis supporting the strategic logic AND filed briefs opposing the legal
mechanism. That split — agreeing on the problem, disagreeing on the tool — is
the actual structural finding.

**EVIDENCED.** Full filer list verified from SCOTUS docket. America's Future
brief PDF read directly — MWI citation at fn. 3 p. 9, Heritage at fn. 7 p. 9.

---

## 3. Kavanaugh's Dissent

Kavanaugh's 63-page dissent is where the strategic-competition frame appears
at the Justice level. It's expressed as
constitutional deference rather than explicit 5GW doctrine:

- **Foreign affairs exception to MQD:** "The major questions doctrine has never
  been applied to a foreign affairs statute." Congress intentionally grants
  broad presidential discretion in foreign affairs, so demanding clear
  authorization misreads congressional intent in this domain.

- **Youngstown Category One:** The President acted with express congressional
  authorization (IEEPA's text). Jackson's *Youngstown* concurrence
  acknowledged "the unwisdom of requiring Congress to lay down narrowly
  definite standards in the field of foreign affairs."

- **Precedential warning:** Applying the majority's approach would have altered
  outcomes in *Dames & Moore v. Regan* (Iranian hostage crisis) and *Hamdi v.
  Rumsfeld* (enemy combatant detention).

- **Nixon precedent:** In 1971, President Nixon used identical TWEA language
  to impose a 10% worldwide tariff, upheld by the Court of Customs and
  Patent Appeals.

The dissent does NOT explicitly invoke fifth-generation warfare, economic
warfare with China, Unrestricted Warfare (Qiao/Wang 1999), or
industrial-base protection. It argues foreign-affairs deference as
constitutional principle, not as strategic necessity. But it is the closest
thing in the record to the frame T3's articulation identifies.

**EVIDENCED.** Kavanaugh dissent verified from Lawfare analysis, Legalytics
breakdown, Yale Journal on Regulation analysis.

---

## 4. The Structural Mechanism (What the Graph Already Proves)

### 4a. Common ownership concentration

The FGIP graph contains 40+ OWNS_SHARES edges from BlackRock, Vanguard, and
State Street into both problem-layer and correction-layer companies. SEC 13F
sourced.

**Adversarial test result (from FGIP CLAUDE.md):**

| Group | Big Three Ownership |
|---|---|
| CHIPS recipients (Intel, Micron, GF, TI) | 19.6% |
| Control group (AMD, NVIDIA, Qualcomm, Broadcom) | 19.7% |
| Problem layer (Apple, Google, Microsoft, Amazon) | 18.0% |

CHIPS vs Control delta: -0.08%. **Verdict: passive indexing**, not strategic
positioning. This is STRONGER than the intent claim because it identifies a
structural mechanism that's defensible and not dismissable as conspiracy.

**EVIDENCED.** Graph edges + adversarial test documented in
`fgip-engine/CLAUDE.md`.

### 4b. The 401(k) accounting fraud

If common ownership concentration makes corporate political positioning align
with shareholder returns regardless of national interest, and if citizens are
shareholders through 401(k)s and pension funds, then the citizen-as-shareholder
appears to benefit from the dynamic that hollows out the citizen-as-worker and
citizen-as-community-member.

- 401(k) goes up. Factory closes. Town dies. Index return is positive.
- Median American household has negative net wealth ex-housing.
- 401(k) balance is a rounding error against a single year of healthcare
  costs in old age.

The system measures wealth in a way that hides immiseration as long as the
equity index climbs. This is unsustainable: shareholder-return optimization
that closes factories eventually runs out of factories to close.

**GAP.** This is a framing claim, not a graph edge. Needs: (a) median
household net wealth data (FRED/Census — Tier 0), (b) 401(k) balance
distribution data (ICI/Vanguard — Tier 1), (c) healthcare cost data
(KFF/CMS — Tier 0). Could be inserted as claim nodes with source edges.

### 4c. Who benefits from the structural arrangement

| Actor Class | Mechanism | Graph Status |
|---|---|---|
| Sovereign wealth funds (Norway GPFG, Saudi PIF, CIC, GIC, Temasek) | State actors with strategic national interests investing passively in US firms; same position as Big Three but with explicit national alignment | **INSERTED.** 5 SWF nodes + 18 OWNS_SHARES edges. Norway GPFG ($2.2T, 1.5% global equities, 52.9% US), Saudi PIF ($1.15T), China CIC ($1.33T), Singapore GIC ($936B), Temasek ($320B). Total: $5.94T sovereign capital mapped. |
| Tax-haven intermediation (Cayman, BVI, Luxembourg, Delaware, City of London) | Capture spreads on transaction complexity, not productivity | **GAP.** No jurisdiction nodes as extraction architecture. |
| Adversary state asymmetric players (China industrial policy + passive US investment) | Subsidize domestic production with state power, extract returns from US firms through market-rule investment | **PARTIAL → IMPROVED.** PRC, CUSEF, China Shock nodes exist. HOLDS_TREASURY edge exists. China CIC node now inserted with OWNS_SHARES edges to Apple, Microsoft, Intel. Military-Civil Fusion doctrine still absent. |
| Domestic financial engineers (PE, hedge funds, IBD pipeline) | Roll up productive companies, extract fees, load debt, exit | **GAP.** No PE mechanism edges. |

### 4d. Fifth-generation warfare intellectual framework

The actors who understand economic-information-narrative warfare capture
systemic position by exploiting an open system that assumes good-faith
participation. China explicitly theorizes this:

- Qiao Liang & Wang Xiangsui, *Unrestricted Warfare* (1999)
- PLA strategic literature on Military-Civil Fusion
- Belt and Road as infrastructure leverage

US intellectual allies who see the same structural problem:
Robert Lighthizer, Oren Cass (American Compass), Elbridge Colby (Marathon
Initiative), J.D. Vance policy team, MWI/SSI at West Point, parts of Naval
War College, China-hawk wings of both parties.

**GAP.** No nodes for any of these thinkers, institutions, or doctrinal
documents. The graph has the economic substrate (ownership, trade flows,
lobbying) but not the strategic-competition interpretive layer.

---

## 5. The Synthesis

The Trump administration's tariff push was an attempt to reassert national
industrial-policy authority against a structural arrangement that had captured
corporate political positioning. The Court ruled it had to go through Congress.
The ruling is legally correct under separation of powers.

But the underlying problem the tariffs were responding to — captured policy,
hollowed productive base, common-ownership-driven anti-national alignment of
corporate behavior — is real and is not resolved by the Court's ruling.

The fix requires:
1. **Legislation** explicitly authorizing industrial policy (Congress, not
   executive emergency powers)
2. **Antitrust enforcement** addressing common ownership concentration
   (FTC/DOJ have the authority)
3. **Reshoring policy** rebuilding the productive base over time (CHIPS Act,
   IRA, IIJA are early moves)

The FGIP graph captures the empirical substrate of this argument. The
institutional-capture documentation is the evidence base for the
strategic-vulnerability claim. When you can show that common ownership makes
corporate political positioning structurally hostile to national industrial
policy, and that the actors benefiting include sovereign wealth funds aligned
with adversary states, you have a specific, evidenced, falsifiable claim with
policy implications.

**Status:** The graph has the ownership substrate and the institutional-capture
edges. It is missing the SWF layer, the 5GW intellectual framework, and the
full amicus mapping with position tags.

---

## 6. Graph Gaps (Prioritized)

### HIGH — Do next

| Gap | What to Insert | Data Source |
|---|---|---|
| Missing pro-tariff amicus filers | AFPI, ACLJ, America's Future, Issa, Squitieri, Homan nodes + FILED_AMICUS edges with position=pro-tariff | SCOTUS docket |
| Position tags on existing amicus edges | Tag all 13 existing FILED_AMICUS edges with position=anti-tariff or pro-tariff | SCOTUS docket |
| Kavanaugh dissent node | Node for Kavanaugh + DISSENTED_IN edge to case + claim node for foreign-affairs MQD exception argument | Opinion PDF |
| National security briefs anti-tariff | Explicit documentation that defense/natsec establishment filed AGAINST tariffs | SCOTUS docket |

### MEDIUM — Next week

| Gap | What to Insert | Data Source |
|---|---|---|
| Sovereign wealth fund nodes | Norway GPFG, Saudi PIF, CIC, GIC, Temasek + OWNS_SHARES edges to US firms | GPFG public holdings, SWF Institute |
| 5GW intellectual framework | Qiao/Wang *Unrestricted Warfare*, Military-Civil Fusion, strategic thinker nodes | Published doctrine |
| Strategic thinker nodes | Lighthizer, Cass, Colby + ADVOCATES edge to industrial-policy thesis | Public positions |

### LOW — When time allows

| Gap | What to Insert | Data Source |
|---|---|---|
| 401(k) accounting fraud claim | Claim node with median net wealth, 401(k) distribution, healthcare cost data | FRED, ICI, KFF (Tier 0) |
| Tax-haven intermediation | Jurisdiction nodes as extraction architecture | Academic literature |
| PE extraction mechanism | Private equity roll-up → fee extraction → debt loading edges | SEC filings, academic |
| Full amicus completion | All 44 filers with position tags, argument summaries | SCOTUS docket PDFs |

---

## 7. The Citation Chain (Corrected Finding)

**Original hypothesis:** An MWI-adjacent defense-strategic institution filed
pro-tariff. **Wrong — no defense institution filed directly.**

**Corrected finding:** The 5GW frame IS in the SCOTUS record, but it got
there through **citation routing** — the doctrine traveled through a
non-strategic filer.

### The carrier: America's Future

The **America's Future** amicus brief (William J. Olson, P.C., filed
2025-09-23) cited:

1. **N. Dockery, "The Domestic Fentanyl Crisis in Strategic Context: Part III
   — Responding to China's Drug Warfare," Modern War Institute at West Point
   (Apr. 2025).** Footnote 3, page 9.

2. **R. Greenway, et al., "A Strategy to Revitalize the Defense Industrial
   Base for the 21st Century," The Heritage Foundation (Apr. 7, 2025).**
   Footnote 7, page 9.

The brief frames tariffs as a response to "a one-sided trade war being waged
against the United States" that has "hollowed out" American manufacturing and
"undermined our defense industrial base." It explicitly uses the language of
warfare ("China's Drug Warfare") via the MWI citation.

### What this means structurally

The 5GW doctrine reached the Supreme Court, but only through a conservative
legal org (America's Future) citing a West Point research paper and a Heritage
Foundation policy brief. No defense-strategic institution — not MWI, not CSIS,
not FDD, not the Army War College — filed directly as amicus.

The orphaning thesis **partially survives** in corrected form: the institutions
that produce the 5GW analysis (MWI, Heritage defense desk) did not show up as
litigants. Their work entered the record through a non-strategic vehicle. This
is itself a structural finding about how the defense-intellectual current
reaches US legal-policy spaces: through citation chains rather than
institutional standing.

The national security establishment that DID file directly — former CIA
director, NSA director, ambassadors, military officials — filed
**anti-tariff**. The strategic-warfare frame and the security-establishment
consensus pointed in opposite directions on this case.

**EVIDENCED.** Verified by reading America's Future amicus brief PDF from
SCOTUS docket. Graph nodes: `modern-war-institute`, `americas-future`,
`n-dockery`. Graph claims: `CLAIM-5GW-CITATION-ROUTING`,
`CLAIM-5GW-AMICUS-ABSENCE` (amended).

---

## 8. Graph Gaps (Updated)

### DONE (this session)

| Item | Status |
|---|---|
| Pro-tariff amicus filers (AFPI, ACLJ, America's Future, Issa, Squitieri, Homan) | INSERTED |
| Position tags on all 19 amicus edges | INSERTED |
| Kavanaugh dissent node + RULED_ON edge | INSERTED |
| MWI node + citation chain from America's Future | INSERTED |
| 5GW citation routing claim | INSERTED |
| Sovereign wealth fund nodes (5 SWFs, 18 OWNS_SHARES edges, 1 claim) | INSERTED |

### MEDIUM — Next week

| Gap | What to Insert | Data Source |
|---|---|---|
| Strategic thinker nodes | Lighthizer, Cass, Colby + ADVOCATES edge to industrial-policy thesis | Public positions |
| Heritage Foundation defense desk | Greenway paper node + citation edge from America's Future brief | Heritage website |
| SWF holdings precision | Replace "undisclosed" ownership pct with actual 13F/annual report figures | NBIM database, PIF 13F, CIC annual report |

### LOW — When time allows

| Gap | What to Insert | Data Source |
|---|---|---|
| 401(k) accounting fraud claim | Claim node with median net wealth, 401(k) distribution, healthcare cost data | FRED, ICI, KFF (Tier 0) |
| Tax-haven intermediation | Jurisdiction nodes as extraction architecture | Academic literature |
| PE extraction mechanism | Private equity roll-up → fee extraction → debt loading edges | SEC filings, academic |
| Full amicus completion | All 44 filers with position tags, argument summaries | SCOTUS docket PDFs |
| Qiao/Wang *Unrestricted Warfare* | Doctrinal source node + CONFIRMS edges to China warfare framing | Published text |

---

## Sources

- [SCOTUSblog case page](https://www.scotusblog.com/cases/case-files/learning-resources-inc-v-trump/)
- [SCOTUS docket](https://www.supremecourt.gov/search.aspx?filename=/docket/docketfiles/html/public/24-1287.html)
- [America's Future amicus brief PDF](https://www.supremecourt.gov/DocketPDF/24/24-1287/375629/20250923141437495_Learning%20Resources%20v%20Trump%20Amicus%20Brief.pdf) — **the carrier brief**
- [Lawfare MQD analysis](https://www.lawfaremedia.org/article/article-i-and-the-major-questions-doctrine-after-learning-resources)
- [Legalytics empirical breakdown](https://legalytics.substack.com/p/learning-resources-inc-v-trump-an)
- [Yale Journal on Regulation MQD analysis](https://www.yalejreg.com/nc/tallying-the-votes-from-learning-resources-the-major-questions-doctrine-remains-relatively-confined/)
- [AEI amicus brief (anti-tariff)](https://www.aei.org/articles/amicus-brief-in-learning-resources-inc-v-trump-and-trump-v-v-o-s-selections-inc/)
- [AFPI response to ruling](https://www.americafirstpolicy.com/issues/afpi-responds-to-scotus-ruling-in-learning-resources-v-trump)
- FGIP graph: `fgip.db` nodes `learning-resources-v-trump`, `modern-war-institute`, `americas-future`, `n-dockery`, `justice-kavanaugh`, `crime-fentanyl-pipeline`
- Graph receipts: `receipts/amicus-5gw-frame-20260502.json`, `receipts/5gw-citation-chain-20260502.json`, `receipts/swf-nodes-20260502.json`
- FGIP graph: SWF nodes `norway-gpfg`, `saudi-pif`, `china-cic`, `singapore-gic`, `singapore-temasek`
