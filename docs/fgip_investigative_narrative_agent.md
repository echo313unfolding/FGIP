# FGIP Investigative Intelligence & Narrative Divergence Agent
## "The journalists are finding the edges. The lobbyists are manufacturing the counter-narrative. Track both."

---

## THE CORE INSIGHT

Independent investigative journalists are the FASTEST edge-detection system that exists.

- Charlie LeDuff found Kornak embezzlement (Summer 2022) → charges came 3.5 YEARS later (Jan 2026)
- ProPublica found Feeding Our Future fraud patterns → DOJ indicted 47 people
- ICIJ found Panama Papers → led to charges/resignations worldwide
- Bridge Michigan found Beydoun $20M misuse → MEDC clawback followed
- The Intercept found NSA surveillance programs → policy changes followed
- OCCRP found Troika Laundromat → sanctions followed
- Bellingcat found MH17 shooters → ICC charges followed

In EVERY case, the journalism preceded the official action by months or years.
If the graph waits for indictments and SEC filings, it's BEHIND the curve.
If the graph ingests investigative journalism in real time, it's ON the curve.
And if it cross-references that journalism against lobbying-funded counter-narratives,
it's AHEAD of the curve — because you can see the correction AND the resistance simultaneously.

---

## AGENT ARCHITECTURE: TWO STREAMS, ONE GRAPH

```
STREAM A: INVESTIGATIVE SIGNAL                STREAM B: LOBBY RHETORIC
(Independent journalism finding truth)         (Manufactured narrative defending status quo)
                                              
┌──────────────────────────┐                  ┌──────────────────────────┐
│ ProPublica                │                  │ Heritage Foundation       │
│ Bridge Michigan           │                  │ Chamber of Commerce       │
│ The Intercept             │                  │ Cato Institute            │
│ OCCRP                     │                  │ Industry trade groups     │
│ ICIJ                      │                  │ Lobbying firm white papers│
│ Bellingcat                │                  │ Placed op-eds             │
│ POGO                      │                  │ Astroturf "grassroots"    │
│ MuckRock (FOIA results)   │                  │ Think tank "research"     │
│ Charlie LeDuff            │                  │ PR firm media placements  │
│ Local investigative units │                  │ Congressional testimony   │
│ Court reporters           │                  │ (by lobby-funded experts) │
│ Whistleblower filings     │                  │ Social media campaigns    │
└───────────┬──────────────┘                  └───────────┬──────────────┘
            │                                             │
            ▼                                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│                         FGIP GRAPH                                    │
│                                                                       │
│  Investigative edge:                    Rhetoric edge:                │
│  "Kornak embezzled $419K from           "Nessel's office stated       │
│   vulnerable adult" (Tier 1,            investigation found no         │
│   LeDuff, June 2022)                   wrongdoing" (Tier 2,          │
│                                         AG press release, Dec 2022)   │
│                                                                       │
│  ──── DIVERGENCE DETECTED ────                                       │
│  Same entity, opposite claims,                                        │
│  3+ year gap before resolution                                        │
│  Resolution: Journalism was correct (charges filed Jan 2026)          │
└──────────────────────────────────────────────────────────────────────┘
```

---

## STREAM A: INVESTIGATIVE JOURNALISM INGESTION ENGINE

### Tier 1: Elite Investigative Outlets (Highest Signal-to-Noise)

These outlets have dedicated investigative teams, FOIA capabilities, and track records 
of findings that lead to official action. Their output is the highest-value non-government 
source for the graph.

**National — Corruption / Finance / Government:**
| Outlet | RSS/API | Focus Area | Why Critical |
|---|---|---|---|
| ProPublica | RSS + API (propublica.org/feeds) | Government accountability, nonprofits, corporate fraud | Nonprofit Explorer, FOIA machine, Tier 0 data analysis |
| The Intercept | RSS | National security, surveillance, corporate influence | Leaked documents, FOIA, adversarial journalism |
| OCCRP (Organized Crime & Corruption Reporting Project) | RSS + API | Cross-border financial crime, money laundering | Global networks, Aleph data platform |
| ICIJ (International Consortium of Investigative Journalists) | RSS + Offshore Leaks DB | Tax havens, offshore finance, cross-border corruption | Panama Papers, Pandora Papers — structured leak databases |
| POGO (Project on Government Oversight) | RSS | Federal spending, military contracting, revolving door | Contractor misconduct database, federal oversight gaps |
| Bellingcat | RSS | Open-source investigation methodology | Verification techniques, geolocation, digital forensics |
| MuckRock | API | FOIA requests and results | Completed FOIA database — actual government documents released |
| Marshall Project | RSS | Criminal justice system | Prosecution data, sentencing disparities |
| Reveal (Center for Investigative Reporting) | RSS + podcast | Corporate abuse, environmental, labor | Long-form investigation with data |
| 100Reporters | RSS | State-level corruption | Under-covered state government investigations |
| APM Reports | RSS | Data-driven investigations | Deep analysis, less frequent but high-value |

**State-Level — Michigan (Template, Replicate per State):**
| Outlet | Focus | Why Critical |
|---|---|---|
| Bridge Michigan | State government, policy, education, economy | Best investigative outlet in MI, nonprofit, Beydoun/dark money coverage |
| Deadline Detroit (Charlie LeDuff) | Detroit politics, corruption, street-level reporting | Broke Kornak story, adversarial, independent |
| Michigan Advance | State capitol, legislation, campaigns | Daily coverage of legislative process |
| Michigan Radio / NPR | State government, environmental | FOIA-driven investigations |
| Detroit Free Press (investigative team) | When they do deep dives, high quality | Limited by Gannett corporate ownership |
| MLive (investigative projects) | Regional/statewide | Part of Advance Publications — note ownership |
| Flint Beat / Outlier Media / Detour Detroit | Hyperlocal | Community-level stories that reveal systemic issues |

**Finance / Markets / Corporate:**
| Outlet | Focus | Why Critical |
|---|---|---|
| Matt Taibbi (Racket News) | Wall Street, finance, regulatory capture | Goldman Sachs "vampire squid," financial system deep dives |
| The Lever (David Sirota) | Corporate influence on policy | Tracks money → policy connections |
| Semafor (business investigations) | Corporate, international business | Former FT/Bloomberg investigative reporters |
| Capitol Forum | Antitrust, regulatory, telecom | Deep regulatory analysis (paid, but signals extractable) |
| American Prospect (investigative) | Corporate power, monopoly, labor | Robert Kuttner, David Dayen — financial regulation experts |

**International (for trade/supply chain thesis):**
| Outlet | Focus | Why Critical |
|---|---|---|
| Reuters Investigations | Global corporate/government | Gold standard for sourced international investigations |
| Financial Times (Alphaville + investigations) | Financial markets, corporate fraud | Wirecard exposé — corporate fraud detection |
| Nikkei Asia | Asian supply chain, semiconductor industry | First to report on TSMC/Samsung capacity moves |
| Caixin (China) | Chinese economy, financial system | Best English-language source on Chinese corporate data |
| Global Witness | Resource extraction, corruption | Follows natural resource money across borders |

### How It Works: Entity & Relationship Extraction

```python
class InvestigativeIngestionAgent:
    """
    Continuously monitors investigative journalism sources.
    Extracts entities, relationships, claims, and evidence.
    Proposes new graph edges at Tier 1 confidence.
    """
    
    def __init__(self):
        self.sources = self.load_source_registry()  # All outlets above
        self.graph = self.connect_to_fgip_graph()
        self.entity_resolver = EntityResolver()  # Matches names to existing nodes
        self.claim_extractor = ClaimExtractor()   # NLP pipeline for factual claims
    
    def ingest_article(self, article):
        """Process a single investigative article."""
        
        # Step 1: Extract ALL named entities
        entities = self.extract_entities(article)
        # Returns: people, companies, organizations, government bodies,
        #          dollar amounts, dates, locations, legislation
        
        # Step 2: Resolve against existing graph nodes
        for entity in entities:
            match = self.entity_resolver.find_in_graph(entity)
            if match:
                entity.graph_node = match  # Link to existing node
            else:
                entity.proposed_node = True  # Propose new node
        
        # Step 3: Extract factual claims (not opinions, not framing)
        claims = self.claim_extractor.extract(article)
        # Filters for:
        #   - Assertions with specific dollar amounts
        #   - Named actions (filed, charged, donated, received, appointed)
        #   - Dated events
        #   - Document references (FOIA results, court filings, financial records)
        #   - Direct quotes from named sources
        
        # Step 4: Generate proposed edges
        edges = []
        for claim in claims:
            edge = {
                "source_node": claim.subject,    # Who/what did it
                "target_node": claim.object,     # To whom/what
                "edge_type": claim.action,       # What happened
                "evidence": {
                    "article_url": article.url,
                    "article_date": article.date,
                    "outlet": article.outlet,
                    "outlet_tier": 1,            # Investigative journalism
                    "claim_text": claim.text,
                    "supporting_documents": claim.referenced_docs,
                    "confidence": self.score_confidence(claim)
                },
                "status": "PROPOSED"             # Human reviews before ACCEPTED
            }
            edges.append(edge)
        
        # Step 5: Check for DIVERGENCE against existing rhetoric edges
        for edge in edges:
            contradictions = self.graph.find_contradicting_edges(edge)
            if contradictions:
                edge["divergence_flag"] = True
                edge["contradicts"] = contradictions
                # This is the HIGHEST VALUE signal:
                # Investigative finding directly contradicts lobby-funded narrative
        
        return edges
    
    def score_confidence(self, claim):
        """Score claim confidence based on evidence quality."""
        score = 0.3  # Base: journalist assertion
        
        if claim.cites_government_document:
            score += 0.3  # References FOIA result, court filing, financial disclosure
        if claim.has_named_source:
            score += 0.1  # On-record source
        if claim.has_dollar_amount:
            score += 0.1  # Specific financial figure (verifiable)
        if claim.corroborated_by_existing_node:
            score += 0.1  # Other evidence in graph already supports this
        if claim.outlet_has_correction_track_record < 0.02:
            score += 0.1  # Outlet rarely issues corrections (high reliability)
        
        return min(score, 0.95)  # Cap at 0.95; only Tier 0 gets 1.0


class ClaimExtractor:
    """
    NLP pipeline that distinguishes FACTUAL CLAIMS from opinions/framing.
    Only factual claims become graph edges.
    """
    
    CLAIM_INDICATORS = [
        # Financial actions
        r"(donated|contributed|spent|paid|received|earned|embezzled|misappropriated)\s+\$[\d,]+",
        # Official actions  
        r"(filed|charged|indicted|sued|appointed|nominated|confirmed|resigned|fired)",
        # Document references
        r"(according to|records show|documents reveal|filings indicate|FOIA|obtained by)",
        # Contractual
        r"(signed|awarded|contracted|subcontracted|procured)",
        # Relationships
        r"(employed by|lobbied for|registered as|served on|donated to|funded by)",
    ]
    
    OPINION_INDICATORS = [
        # Subjective framing (extract separately as NARRATIVE, not FACT)
        r"(arguably|seemingly|appears to|critics say|supporters claim|controversial)",
        r"(could|might|may|potentially|possibly|likely)",
        r"(experts say|analysts believe|observers note)",  # Unless named + quoted
    ]
    
    def extract(self, article):
        """Return only factual claims with evidence markers."""
        # Parse article into sentences
        # Score each sentence for claim vs opinion indicators
        # Return sentences scoring > threshold as claims
        # Include context window (surrounding sentences) for each claim
        pass
```

### Real Example: How the Agent Would Have Caught Kornak

```
Timeline of what the agent would have detected:

June 2022: Charlie LeDuff publishes investigation
├── AGENT EXTRACTS:
│   ├── ENTITY: Traci Kornak (person) → RESOLVES TO: existing node (MI Dem Party treasurer)
│   ├── ENTITY: Rosalene Burd (person) → NEW NODE proposed (vulnerable adult)
│   ├── ENTITY: Dana Nessel (person) → RESOLVES TO: existing node (MI AG)
│   ├── CLAIM: "Kornak → EMBEZZLED_FROM → Burd ($123K)" [confidence: 0.7]
│   │   └── Evidence: financial records cited, named sources, specific dollar amounts
│   ├── CLAIM: "Nessel office → OPENED_INVESTIGATION → Kornak" [confidence: 0.6]
│   └── CLAIM: "Kornak → SERVES_ON → Nessel transition team" [confidence: 0.8]
│       └── Evidence: public record, verifiable
│
├── AGENT FLAGS:
│   ├── DIVERGENCE: Kornak is MI Dem Party treasurer (existing node)
│   │   AND subject of embezzlement investigation by AG whose transition team she served on
│   │   → CONFLICT OF INTEREST pattern detected
│   ├── CROSS-REFERENCE: Kornak also max donor to Whitmer (FEC data in graph)
│   │   → DONOR_NETWORK pattern detected
│   └── PRIORITY: HIGH — multiple graph connections to political power network

December 2022: Nessel closes investigation (AG press release)
├── AGENT EXTRACTS:
│   ├── CLAIM: "AG office → CLOSED_INVESTIGATION → Kornak" [confidence: 0.9]
│   │   └── Official government communication
│   ├── DIVERGENCE DETECTED:
│   │   Stream A (LeDuff investigation): Kornak embezzled $123K+ with financial evidence
│   │   Stream B (AG press release): No charges, investigation closed
│   │   → NARRATIVE DIVERGENCE SCORE: 0.92 (very high)
│   │   → FLAG: "Investigation closed by AG with documented conflict of interest"
│   │   → This exact pattern matches Ohio FirstEnergy template

[Agent continues monitoring for 3 years]

January 2026: Kent County Prosecutor files charges
├── AGENT EXTRACTS:
│   ├── CLAIM: "Kent County → CHARGED → Kornak (embezzlement $50K-$100K)" [confidence: 0.95]
│   │   └── Government filing, Tier 0
│   ├── RESOLUTION: Stream A (investigative journalism) was CORRECT
│   │   Stream B (AG press release) was INCORRECT/MISLEADING
│   ├── DIVERGENCE RESOLVED: Investigation → 3.5 year lag → charges
│   └── PATTERN CONFIRMED: AG-with-conflict-of-interest → closed investigation →
│       independent prosecutor eventually acts

THE AGENT WOULD HAVE FLAGGED THIS IN JUNE 2022.
The graph would have shown the conflict of interest from DAY ONE.
Anyone looking at the graph would have seen:
  - Kornak → transition team → Nessel (edge)
  - Kornak → embezzlement evidence → (LeDuff investigation, Tier 1)
  - Nessel → AG has jurisdiction → Kornak investigation (edge)
  - CONFLICT OF INTEREST detected automatically from edge overlap
```

---

## STREAM B: LOBBY RHETORIC TRACKING ENGINE

### What It Monitors

The other side of the coin. For every issue in the graph, there are organizations 
MANUFACTURING narratives to protect the status quo. This stream tracks that output 
and connects it to funding sources.

**Lobby-Adjacent Content Sources:**

| Source Type | Examples | What It Reveals |
|---|---|---|
| Think tank publications | Heritage, Cato, Brookings, AEI, Manhattan Institute | Policy positions traceable to funders via 990s |
| Industry trade group reports | Chamber of Commerce, PhRMA, API, AHIP, NAM | Lobbying positions dressed as "research" |
| Placed op-eds | Named author + undisclosed affiliation | Track who placed it (PR firm), who funded the author |
| Astroturf organizations | "Americans for Prosperity," "60 Plus Association" | Front groups with populist names, corporate funding |
| Congressional testimony | Expert witnesses at hearings | Who invited them? Who funds their organization? |
| PR firm output | Edelman, Weber Shandwick, FTI Consulting | Trace client → PR firm → media placement |
| Social media campaigns | Coordinated messaging, identical talking points | Sinclair-style repetition at scale |
| Comment letters (Federal Register) | Public comments on proposed regulations | Industry groups submitting identical/similar comments |
| Sponsored academic research | University studies funded by interested parties | Funding disclosure (or lack thereof) |

### How It Works: The Rhetoric Graph

```python
class LobbyRhetoricTracker:
    """
    Tracks lobby-funded narrative output and connects it to funding sources.
    """
    
    def process_think_tank_publication(self, publication):
        """
        When Heritage/Cato/AEI/etc. publishes a policy paper:
        1. Extract the policy POSITION (what they're arguing for/against)
        2. Look up the organization's 990 filing
        3. Identify top funders
        4. Check if funders have financial interest in the policy position
        5. Check if same position appears in lobbying disclosures
        """
        
        position = self.extract_policy_position(publication)
        org = publication.organization
        
        # Get funding from IRS 990
        funders = self.get_990_funders(org)  # ProPublica Nonprofit Explorer
        
        # Check if funders benefit from the position
        for funder in funders:
            if self.funder_benefits_from_position(funder, position):
                yield {
                    "type": "FUNDED_ADVOCACY",
                    "funder": funder,
                    "think_tank": org,
                    "position": position,
                    "publication": publication.url,
                    "funding_amount": funder.amount,  # From 990
                    "financial_interest": self.describe_interest(funder, position),
                    "confidence": 0.8  # High: documented funding + documented position
                }
        
        # Check if position matches lobbying disclosure
        matching_lobbying = self.find_matching_lobby_disclosure(position)
        for lobby in matching_lobbying:
            yield {
                "type": "LOBBY_THINK_TANK_ALIGNMENT",
                "lobby_client": lobby.client,
                "lobby_firm": lobby.registrant,
                "think_tank": org,
                "aligned_position": position,
                "lobby_spend": lobby.amount,
                "confidence": 0.85  # Very high: same position in both channels
            }
    
    def detect_placed_oped(self, article):
        """
        Detect op-eds that are likely placed by PR firms or lobby groups.
        
        Signals:
        - Author is affiliated with think tank / industry group
        - Author affiliation not disclosed in byline
        - Talking points match recent lobbying disclosure language
        - Multiple similar op-eds appear in different outlets same week
        - Author has no other journalism history (one-time contributor)
        """
        
        author = article.author
        author_affiliations = self.lookup_affiliations(author)
        # Check: LinkedIn, think tank staff pages, lobbying registrations,
        #        corporate board memberships, campaign finance donor records
        
        undisclosed = []
        for affiliation in author_affiliations:
            if affiliation not in article.disclosed_affiliations:
                undisclosed.append(affiliation)
        
        if undisclosed:
            yield {
                "type": "UNDISCLOSED_AFFILIATION",
                "author": author,
                "outlet": article.outlet,
                "disclosed": article.disclosed_affiliations,
                "undisclosed": undisclosed,
                "position_argued": self.extract_position(article),
                "financial_interest": self.check_interest(undisclosed, article)
            }
        
        # Check for coordinated placement
        similar_opeds = self.find_similar_content(article, window_days=14)
        if len(similar_opeds) >= 2:
            yield {
                "type": "COORDINATED_PLACEMENT",
                "articles": [article] + similar_opeds,
                "shared_language": self.extract_shared_phrases(article, similar_opeds),
                "likely_source": self.identify_common_funder(article, similar_opeds),
                # This is the Sinclair script detection applied to op-eds
            }
    
    def track_astroturf(self, organization):
        """
        Identify organizations that appear grassroots but are industry-funded.
        
        Signals:
        - Name sounds populist ("Americans for...", "Citizens for...", "Alliance for...")
        - 990 shows 80%+ funding from <5 sources
        - Registered address matches lobbying firm
        - Officers are lobbyists or former industry executives
        - Formed within 12 months of relevant legislation/regulation
        """
        
        filing_990 = self.get_latest_990(organization)
        
        signals = {
            "populist_name": self.has_populist_name_pattern(organization.name),
            "concentrated_funding": filing_990.top_5_donors_pct > 0.80,
            "lobby_firm_address": self.address_matches_lobby_firm(organization.address),
            "officer_affiliations": self.check_officer_backgrounds(filing_990.officers),
            "formation_timing": self.formed_near_legislation(organization.formation_date),
            "minimal_operations": filing_990.program_expenses < filing_990.total_revenue * 0.3,
        }
        
        astroturf_score = sum(1 for v in signals.values() if v) / len(signals)
        
        if astroturf_score > 0.5:
            yield {
                "type": "PROBABLE_ASTROTURF",
                "organization": organization.name,
                "score": astroturf_score,
                "signals": {k: v for k, v in signals.items() if v},
                "actual_funders": filing_990.top_donors,
                "positions_advocated": self.get_public_positions(organization),
                "benefits_whom": self.who_benefits(organization)
            }


class FederalRegisterCommentAnalyzer:
    """
    Track coordinated comment campaigns on proposed regulations.
    
    When industry groups organize mass comments on regulations,
    the comments often share identical or near-identical language.
    This is the regulatory equivalent of the Sinclair script.
    """
    
    def analyze_comment_period(self, regulation_id):
        """Pull all public comments on a proposed rule, detect coordination."""
        
        comments = self.fetch_comments(regulation_id)  # regulations.gov API
        
        # Cluster comments by textual similarity
        clusters = self.cluster_by_similarity(comments, threshold=0.85)
        
        for cluster in clusters:
            if len(cluster) > 10:  # Coordinated campaign threshold
                # Identify the likely source of the template language
                template_source = self.identify_template_origin(cluster)
                
                yield {
                    "type": "COORDINATED_COMMENT_CAMPAIGN",
                    "regulation": regulation_id,
                    "comment_count": len(cluster),
                    "template_source": template_source,  # Often a trade group or lobbying firm
                    "sample_language": cluster[0].text[:500],
                    "submitters": self.analyze_submitters(cluster),
                    "position": self.extract_position(cluster[0]),
                    "who_benefits": self.identify_beneficiaries(regulation_id, cluster[0])
                }
```

---

## DIVERGENCE DETECTION: WHERE THE REAL INTELLIGENCE LIVES

The most valuable output isn't from either stream alone — it's from the DIVERGENCE between them.

### Divergence Types

```
TYPE 1: FINDING vs. DENIAL
─────────────────────────
Stream A (journalism): "Entity X did [specific bad thing] — here's the evidence"
Stream B (rhetoric):   "Entity X categorically denies wrongdoing"
RESOLUTION TIMELINE: Track until official action confirms one side
HISTORICAL ACCURACY: In our graph, journalism confirmed by official action: ~85%+
EXAMPLE: LeDuff vs. Nessel's office on Kornak

TYPE 2: EVIDENCE vs. FRAMING
────────────────────────────
Stream A (journalism): "This policy cost X jobs" (cites BLS data)
Stream B (rhetoric):   "This policy created economic growth" (cites GDP, different metric)
DIVERGENCE: Both technically cite data, but select different metrics
RESOLUTION: Graph shows BOTH metrics with sources, user sees the full picture
EXAMPLE: PNTR with China — GDP grew, but 3.7M manufacturing jobs lost

TYPE 3: COVERAGE vs. SILENCE
────────────────────────────
Stream A (journalism): Investigative outlet publishes major finding
Stream B (rhetoric):   No response, no coverage, story dies
DIVERGENCE: The most dangerous type — no counter-narrative needed if nobody amplifies
RESOLUTION: Graph tracks which stories get picked up and which don't
CONNECT TO: Media consolidation data — does the outlet that SHOULD cover it share 
            ownership with the entity being investigated?
EXAMPLE: How many outlets covered Kornak vs. how many covered Nessel's other 
         cases? Coverage ratio = editorial bias measurement.

TYPE 4: TIMING DIVERGENCE
─────────────────────────
Stream A (journalism): Investigation published [date]
Stream B (rhetoric):   Counter-narrative published [date + X days]
ANALYSIS: Short lag = organized response (PR firm). Long lag = organic pushback.
Track which PR firms respond to which investigations on behalf of which clients.
EXAMPLE: Industry group publishes "rebuttal" to ProPublica investigation 
         within 48 hours — they had advance notice or standing opposition research.

TYPE 5: SOURCE QUALITY DIVERGENCE  
──────────────────────────────────
Stream A (journalism): Cites FOIA documents, court filings, financial records (Tier 0-1)
Stream B (rhetoric):   Cites "experts say," "studies show" without linking primary source
DIVERGENCE: Evidence quality gap reveals which side is doing real work
MEASUREMENT: Average source tier of investigative claims vs. rhetoric claims
             on the same topic
```

### Divergence Dashboard Output

```
TOPIC: Michigan Attorney General Conflict of Interest

INVESTIGATIVE FINDINGS (Stream A):
├── LeDuff (June 2022): Kornak embezzled $123K+ from vulnerable adult
│   ├── Evidence tier: 1 (investigative, cites financial records)
│   ├── Confidence: 0.8
│   └── Status: CONFIRMED by charges (Jan 2026)
├── Bridge Michigan (2023): Bipartisan Solutions dark money to Nessel's wife's committee
│   ├── Evidence tier: 1 (cites SOS determination)
│   ├── Confidence: 0.85
│   └── Status: UNRESOLVED — AG declined to investigate
├── House Oversight (2025): Email showing Nessel breached firewall on Kornak case
│   ├── Evidence tier: 0 (government document, subpoenaed)
│   ├── Confidence: 0.95
│   └── Status: CONFIRMED — contempt recommendation advanced
└── COMPOSITE INVESTIGATIVE SIGNAL: Strong (0.87 avg confidence)

LOBBY/INSTITUTIONAL RHETORIC (Stream B):
├── Nessel's office (Dec 2022): "Investigation found insufficient evidence"
│   ├── Evidence tier: 2 (press statement, no supporting documents released)
│   ├── Contradicts: LeDuff findings, later Kent County charges
│   └── Status: DISPROVEN
├── MI Democratic Party (2023): No statement on Kornak despite being their treasurer
│   ├── Type: SILENCE (Type 3 divergence)
│   └── Kornak remained treasurer until April 2025
├── [No think tank or advocacy group defended Nessel's handling]
│   └── Type: SILENCE — even allies didn't want to be on record defending this
└── COMPOSITE RHETORIC SIGNAL: Weak defense / strategic silence

DIVERGENCE SCORE: 0.92 (very high — investigative stream overwhelmingly confirmed)
RESOLUTION: Journalism was correct. Institutional response was defensive/misleading.
PATTERN MATCH: Ohio FirstEnergy (0.87 similarity), Illinois Rod Blagojevich (0.72 similarity)
```

---

## CONTINUOUS MONITORING: THE RSS/API BACKBONE

### Feed Architecture

```python
class InvestigativeRSSMonitor:
    """
    Polls all investigative sources at appropriate intervals.
    Extracts new articles, deduplicates, and sends to ingestion pipeline.
    """
    
    # Tier 1 investigative outlets — poll every 15 minutes
    TIER_1_FEEDS = {
        # National investigative
        "propublica": "https://www.propublica.org/feeds/propublica/main",
        "intercept": "https://theintercept.com/feed/?rss",
        "pogo": "https://www.pogo.org/feed",
        "reveal": "https://revealnews.org/feed/",
        "marshall_project": "https://www.themarshallproject.org/rss/fischer",
        "100reporters": "https://100r.org/feed/",
        
        # State-level (Michigan template — replicate per state)
        "bridge_michigan": "https://www.bridgemi.com/rss.xml",
        "michigan_advance": "https://michiganadvance.com/feed/",
        "deadline_detroit": "https://deadlinedetroit.com/feed",
        
        # Financial/corporate investigation
        "the_lever": "https://www.levernews.com/rss/",
        "american_prospect": "https://prospect.org/api/rss/content.rss",
        
        # International
        "occrp": "https://www.occrp.org/en/rss",
        "icij": "https://www.icij.org/feed/",
        "global_witness": "https://www.globalwitness.org/en/feed/",
        "bellingcat": "https://www.bellingcat.com/feed/",
    }
    
    # Think tank / lobby output — poll every hour  
    RHETORIC_FEEDS = {
        "heritage": "https://www.heritage.org/rss/all-research",
        "cato": "https://www.cato.org/rss/recent-opeds",
        "brookings": "https://www.brookings.edu/feed/",
        "aei": "https://www.aei.org/feed/",
        "manhattan_institute": "https://www.manhattan-institute.org/feed",
        "chamber_above_the_fold": "https://www.uschamber.com/rss",
        "nam": "https://www.nam.org/feed/",  # National Association of Manufacturers
        "api_energy": "https://www.api.org/rss",  # American Petroleum Institute
    }
    
    # Government sources — poll every 30 minutes
    GOVERNMENT_FEEDS = {
        "federal_register": "https://www.federalregister.gov/api/v1/articles",
        "doj_press": "https://www.justice.gov/feeds/opa/justice-news.xml",
        "sec_enforcement": "https://www.sec.gov/rss/litigation/litreleases.xml",
        "gao_reports": "https://www.gao.gov/rss/reports.xml",
        "cbo_reports": "https://www.cbo.gov/rss",
        "ig_reports": "https://www.ignet.gov/rss",  # Inspector General community
    }
    
    # FOIA results — poll daily
    FOIA_FEEDS = {
        "muckrock": "https://www.muckrock.com/news/feeds/latest/",
        # MuckRock also has API: https://www.muckrock.com/api_v1/
        # Completed FOIA requests searchable by agency, topic
    }
    
    def poll_all(self):
        """Main polling loop."""
        for feed_name, feed_url in {**self.TIER_1_FEEDS, **self.RHETORIC_FEEDS, 
                                     **self.GOVERNMENT_FEEDS, **self.FOIA_FEEDS}.items():
            new_articles = self.fetch_new(feed_url)
            for article in new_articles:
                # Classify: investigative vs. rhetoric vs. government
                stream = self.classify_stream(article, feed_name)
                
                # Extract entities and claims
                if stream == "investigative":
                    edges = self.investigative_agent.ingest_article(article)
                elif stream == "rhetoric":
                    edges = self.rhetoric_tracker.process_publication(article)
                elif stream == "government":
                    edges = self.government_agent.process_filing(article)
                
                # Check for divergence against existing graph
                for edge in edges:
                    divergences = self.divergence_detector.check(edge)
                    if divergences:
                        edge.divergence_flags = divergences
                        edge.priority = "HIGH"
                
                # Submit all edges as proposals
                self.graph.submit_proposals(edges)


class MuckRockFOIAMonitor:
    """
    Special handler for FOIA results — these are PRIMARY DOCUMENTS
    released by government agencies. Highest possible non-court evidence.
    """
    
    def process_foia_result(self, foia_request):
        """
        When a FOIA request is completed:
        1. Download released documents
        2. OCR if needed
        3. Extract entities and claims from GOVERNMENT DOCUMENTS
        4. These are Tier 0 evidence — government's own records
        5. Cross-reference against existing graph
        """
        
        documents = self.download_documents(foia_request)
        
        for doc in documents:
            # These are government documents — Tier 0
            entities = self.extract_entities(doc)
            claims = self.extract_claims(doc)
            
            for claim in claims:
                claim.evidence_tier = 0  # Government document
                claim.foia_request_id = foia_request.id
                claim.releasing_agency = foia_request.agency
                
                # Check if this confirms or contradicts existing edges
                existing = self.graph.find_related_edges(claim)
                if existing:
                    for edge in existing:
                        if self.confirms(claim, edge):
                            edge.upgrade_confidence(claim)
                            # FOIA result confirming journalist claim = 
                            # very high confidence
                        elif self.contradicts(claim, edge):
                            edge.flag_contradiction(claim)
```

---

## THE INVESTIGATIVE JOURNALISM TRUST SCORE

Not all journalism is equal. The agent needs to weight sources by track record.

### Scoring Methodology

```python
class OutletTrustScore:
    """
    Track record scoring for investigative outlets.
    Based on: How often do their findings lead to official action?
    """
    
    def calculate(self, outlet):
        # Historical accuracy: claims that were later confirmed by Tier 0 sources
        confirmed_claims = self.count_confirmed(outlet)
        total_claims = self.count_total(outlet)
        accuracy_rate = confirmed_claims / total_claims if total_claims > 0 else 0
        
        # Correction rate: how often does outlet issue corrections?
        corrections = self.count_corrections(outlet)
        correction_rate = corrections / total_claims
        
        # Impact score: how often do investigations lead to action?
        # (charges, policy changes, resignations, reforms)
        actions_triggered = self.count_downstream_actions(outlet)
        impact_rate = actions_triggered / total_claims
        
        # Independence score: funding diversification
        # (fewer concentrated funders = more independent)
        funding_concentration = self.get_funding_hhi(outlet)
        independence = 1 - funding_concentration
        
        # Methodology score: does outlet show its work?
        # (publishes source documents, FOIA results, data)
        methodology_transparency = self.assess_methodology(outlet)
        
        return {
            "outlet": outlet.name,
            "accuracy_rate": accuracy_rate,
            "correction_rate": correction_rate,  # Low is good
            "impact_rate": impact_rate,
            "independence_score": independence,
            "methodology_score": methodology_transparency,
            "composite_trust": self.weighted_composite(
                accuracy_rate, correction_rate, impact_rate, 
                independence, methodology_transparency
            ),
            "claims_in_graph": total_claims,
            "confirmed_in_graph": confirmed_claims
        }
    
    # Example output:
    # ProPublica:      trust=0.91, accuracy=0.88, impact=0.34, independence=0.92
    # Bridge Michigan: trust=0.85, accuracy=0.82, impact=0.28, independence=0.89
    # Charlie LeDuff:  trust=0.78, accuracy=0.80, impact=0.22, independence=0.95
    # Heritage Found:  trust=0.45, accuracy=0.52, impact=0.15, independence=0.31
    #                  (independence low because Koch/Bradley/Scaife funding concentration)
```

---

## OUTPUT: WHAT THE USER SEES

### The Investigative Feed (Real-Time)

```
[HIGH PRIORITY — DIVERGENCE DETECTED]
Bridge Michigan (Feb 23, 2026):
"MEDC demands $8.2M back from Beydoun's Global Link International"
├── New edges proposed:
│   ├── MEDC → CLAWBACK_DEMAND → Global Link International ($8.2M)
│   ├── Global Link International → SPENT → $4,526 diamond coffeemaker
│   └── Whitmer → SIGNED_BUDGET → containing $20M earmark → Beydoun entity
├── Divergence with existing rhetoric:
│   ├── Beydoun (2022): "This investment will attract 25 startups" → ZERO attracted
│   └── Whitmer office (2022): Budget signing praised economic development spending
├── Pattern match: Kornak template (donor → appointment → steal → slow response)
└── Confidence: 0.88 (Tier 1 journalism citing Tier 0 government records)

[MEDIUM PRIORITY — NEW SUPPLY CHAIN INTELLIGENCE]
Nikkei Asia (Feb 23, 2026):
"TSMC Arizona fab reaches yield milestone, begins volume production"
├── New edges proposed:
│   ├── TSMC Arizona → PRODUCTION_MILESTONE → 4nm chips
│   ├── CHIPS_Act → FUNDED → TSMC Arizona ($6.6B)
│   └── Apple → CUSTOMER_OF → TSMC Arizona (per 10-K)
├── Investment signal: Domestic semiconductor production capacity expanding
├── Connect to: Equipment suppliers (Applied Materials, ASML, Lam Research)
└── Confidence: 0.82 (Tier 1 journalism, specific technical claim)

[LOW PRIORITY — RHETORIC TRACKING]
Heritage Foundation (Feb 22, 2026):
"New report argues tariff costs outweigh manufacturing job gains"
├── RHETORIC classification (not investigative finding)
├── Authors: [Name] — previously at [Industry Trade Group]
├── Funding: Heritage 990 shows $XX million from [corporate foundations]
├── Position aligns with: Chamber of Commerce lobbying disclosure (LDA filing)
├── Contradicts: BLS data showing manufacturing employment +XXK since tariffs
├── Contradicts: EPI analysis showing wage gains in protected sectors
└── Divergence score: 0.73 (rhetoric contradicts government data)
```

### The Divergence Scorecard (Weekly Summary)

```
FGIP NARRATIVE DIVERGENCE REPORT — Week of Feb 17-23, 2026

TOPICS WITH HIGHEST DIVERGENCE (investigative findings vs. institutional narrative):

1. Michigan AG Office (Divergence: 0.92)
   Investigative: Documented firewall breach, closed investigation on ally, dark money probe buried
   Institutional: "Our office follows all ethics procedures"
   Resolution status: House Oversight subpoenas pending, contempt advanced

2. PNTR China Impact (Divergence: 0.84)
   Investigative: 3.7M manufacturing jobs lost, $37B/yr wage suppression (BLS/EPI data)
   Institutional: "Trade liberalization benefits consumers" (think tanks, most major outlets)
   Resolution status: Tariff policy reversal underway, reshoring data confirming damage thesis

3. Media Consolidation Impact (Divergence: 0.78)
   Investigative: 6 companies control 90% of media, Sinclair forced identical scripts
   Institutional: "Free market media serves diverse audiences"
   Resolution status: No regulatory action, but independent media growing

TOPICS WITH LOW DIVERGENCE (consensus between streams):
1. CHIPS Act implementation (Divergence: 0.12) — both sides agree it's happening
2. Cryptocurrency regulation need (Divergence: 0.18) — broad agreement
3. Infrastructure spending (Divergence: 0.15) — bipartisan support reflected in both streams

DIVERGENCE TREND: Overall divergence INCREASING on regulatory capture topics,
DECREASING on bipartisan economic topics. The gap between what independent journalists
find and what institutional narratives say is WIDENING on corruption/influence topics.
```

---

## WHY THIS IS THE MISSING AGENT

The Deep Intelligence Agents (DI-1 through DI-11) collect DATA from structured sources.
This agent — the Investigative Intelligence agent — collects INTERPRETATION from humans 
who are doing the work of connecting the dots that automated systems miss.

Journalists do things algorithms can't:
- Cultivate sources who leak internal documents
- File FOIA requests based on hunches and insider tips
- Sit in courtrooms and observe what's not in the transcript
- Knock on doors and get people to talk on record
- Follow money trails that cross jurisdictions and entity types
- Apply judgment about what MATTERS, not just what's DETECTABLE

The agent doesn't replace journalists. It AMPLIFIES them.
Every investigation that any independent journalist publishes gets:
- Immediately parsed for entities and relationships
- Cross-referenced against the entire graph
- Checked for divergence against institutional narratives
- Connected to financial data, lobbying records, and government filings
- Preserved and tracked until resolution (charges, policy change, or ongoing)

The journalists find the edge. The agent makes sure the edge never disappears.
The lobby manufactures the counter-narrative. The agent makes sure both are visible.
The graph shows all of it. And the user — investor, citizen, policymaker — 
sees the full picture for the first time.
