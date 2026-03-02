# FGIP Database — Add Signal, Accountability & Risk Layers

## Context

The database at ~/fgip-engine/ has 53 nodes and 40 edges covering the 
institutional layer (lobbying, ownership, judicial pipeline, correction 
companies). Now we need three new layers:

1. **Signal Layer** — Independent media sources validating pieces of the thesis
2. **Accountability Layer** — Documented fraud/crime connected to the causality chain
3. **Risk Management Layer** — Scoring system for thesis confidence + investment risk

---

## STEP 1: New Node Types to Add

### Independent Media / Signal Sources

Add these as MEDIA_OUTLET or PERSON nodes with a new metadata field: 
`"signal_type": "independent"` to distinguish from captured media.

```json
[
  {
    "node_id": "media_shawn_ryan_show",
    "node_type": "MEDIA_OUTLET",
    "name": "Shawn Ryan Show",
    "aliases": ["SRS"],
    "description": "Former Navy SEAL hosting long-form interviews on defense, intelligence, national security. Covered defense industrial base collapse, CIA intelligence gaps, fentanyl crisis. Audience reach: millions per episode.",
    "metadata": {
      "platform": "youtube",
      "host": "Shawn Ryan",
      "signal_type": "independent",
      "topics_covered": ["defense_industrial_base", "intelligence_gaps", "fentanyl", "china_threat"],
      "url": "https://youtube.com/@ShawnRyanShow"
    }
  },
  {
    "node_id": "person_sarah_adams",
    "node_type": "PERSON",
    "name": "Sarah Adams",
    "aliases": [],
    "description": "CIA targeter who appeared on Shawn Ryan Show. Discussed FBI uncovering secret biolab, intelligence gaps, China-connected threats on US soil.",
    "metadata": {
      "role": "CIA targeter",
      "signal_type": "whistleblower",
      "appeared_on": "media_shawn_ryan_show"
    }
  },
  {
    "node_id": "media_tucker_carlson",
    "node_type": "MEDIA_OUTLET",
    "name": "Tucker Carlson Network",
    "aliases": ["TCN"],
    "description": "Independent media platform after Fox News departure. Covers institutional capture, immigration policy, foreign influence.",
    "metadata": {
      "platform": "youtube/x",
      "signal_type": "independent",
      "topics_covered": ["institutional_capture", "immigration", "foreign_influence"]
    }
  },
  {
    "node_id": "media_joe_rogan",
    "node_type": "MEDIA_OUTLET",
    "name": "Joe Rogan Experience",
    "aliases": ["JRE"],
    "description": "Largest podcast globally. Platform for whistleblowers, defense/intelligence figures, independent researchers. Signal amplifier.",
    "metadata": {
      "platform": "spotify/youtube",
      "signal_type": "independent",
      "topics_covered": ["censorship", "institutional_capture", "tech_policy"]
    }
  },
  {
    "node_id": "media_breaking_points",
    "node_type": "MEDIA_OUTLET",
    "name": "Breaking Points",
    "aliases": ["BP"],
    "description": "Independent political news. Krystal Ball and Saagar Enjeti. Covers populist economics, reshoring, institutional failures across partisan lines.",
    "metadata": {
      "platform": "youtube",
      "hosts": ["Krystal Ball", "Saagar Enjeti"],
      "signal_type": "independent",
      "topics_covered": ["populist_economics", "reshoring", "institutional_failure"]
    }
  },
  {
    "node_id": "media_all_in_podcast",
    "node_type": "MEDIA_OUTLET",
    "name": "All-In Podcast",
    "aliases": ["All-In"],
    "description": "Tech/finance podcast. Chamath Palihapitiya, Jason Calacanis, David Sacks, David Friedberg. Covers macro, tariffs, reshoring economics from investor perspective.",
    "metadata": {
      "platform": "youtube",
      "hosts": ["Chamath Palihapitiya", "Jason Calacanis", "David Sacks", "David Friedberg"],
      "signal_type": "independent",
      "topics_covered": ["macro_economics", "tariffs", "reshoring", "tech_policy"]
    }
  },
  {
    "node_id": "media_palantir_foundry",
    "node_type": "MEDIA_OUTLET",
    "name": "Palantir / Palmer Luckey Public Statements",
    "aliases": [],
    "description": "Defense tech executives publicly validating defense industrial base collapse thesis. Luckey stated defense supply chain is broken. Palantir = classified version of what FGIP builds publicly.",
    "metadata": {
      "signal_type": "industry_insider",
      "topics_covered": ["defense_industrial_base", "supply_chain", "china_threat"]
    }
  },
  {
    "node_id": "media_marco_rubio",
    "node_type": "PERSON",
    "name": "Marco Rubio",
    "aliases": ["Secretary Rubio"],
    "description": "Secretary of State. Publicly stated America must direct economy to counter China. Munich Security Conference speech Feb 2026. Validates reshoring thesis from government position.",
    "metadata": {
      "position": "Secretary of State",
      "signal_type": "government_official",
      "topics_covered": ["reshoring", "china_threat", "critical_minerals", "economic_sovereignty"]
    }
  }
]
```

### Substack / Independent Journalism Nodes

```json
[
  {
    "node_id": "media_substack_ecosystem",
    "node_type": "MEDIA_OUTLET",
    "name": "Substack Independent Journalism Ecosystem",
    "aliases": ["Substack journalists"],
    "description": "Decentralized journalism platform. Multiple independent writers covering pieces of the FGIP thesis that legacy media won't synthesize. Axios reported Substack disrupting news industry.",
    "metadata": {
      "platform": "substack",
      "signal_type": "independent",
      "key_writers": [
        "manufacturingtalks - industrial decline",
        "urbanomics - chronicle of industrial decline", 
        "profstevekeen - Ricardo deception",
        "libertyordeath101 - 50-year plot against American worker",
        "adastraperaspera - US industrial policy revival",
        "freemarketfuturist - free market industrial policy",
        "postliberalnews - future of work"
      ]
    }
  }
]
```

### Reddit Communities as Signal Sources

```json
[
  {
    "node_id": "media_reddit_wallstreetbets",
    "node_type": "MEDIA_OUTLET",
    "name": "r/wallstreetbets",
    "aliases": ["WSB"],
    "description": "Reddit community. 15M+ members. Early signal on retail investor awareness of reshoring thesis, Great Rotation discussion, anti-institutional sentiment.",
    "metadata": {
      "platform": "reddit",
      "signal_type": "crowd_intelligence",
      "members": 15000000,
      "topics_covered": ["retail_investing", "great_rotation", "reshoring_etfs"]
    }
  },
  {
    "node_id": "media_reddit_manufacturing",
    "node_type": "MEDIA_OUTLET",
    "name": "Manufacturing/Reshoring Reddit Communities",
    "aliases": [],
    "description": "Multiple subreddits tracking reshoring activity: r/manufacturing, r/supplychain, r/economics. Ground-level signal on factory openings, hiring, supply chain shifts.",
    "metadata": {
      "platform": "reddit",
      "signal_type": "crowd_intelligence",
      "topics_covered": ["factory_openings", "hiring", "supply_chain"]
    }
  }
]
```

---

## STEP 2: Accountability Layer — Crime/Fraud Nodes

These are documented criminal cases that connect to the causality chain. 
Each represents a point where the system's failures generated prosecutable fraud.

```json
[
  {
    "node_id": "crime_feeding_our_future",
    "node_type": "ECONOMIC_EVENT",
    "name": "Feeding Our Future Fraud (Minnesota)",
    "aliases": ["Minnesota food fraud", "FOF fraud"],
    "description": "Largest pandemic fraud scheme in US. 70+ defendants. $250M+ stolen from federal child nutrition programs. Connected to refugee resettlement networks and nonprofit oversight failures.",
    "metadata": {
      "type": "fraud",
      "location": "Minnesota",
      "amount_stolen": 250000000,
      "defendants": 70,
      "status": "prosecutions ongoing",
      "source_urls": [
        "https://en.wikipedia.org/wiki/Feeding_Our_Future",
        "https://en.wikipedia.org/wiki/2020s_Minnesota_fraud_scandals",
        "https://www.cbsnews.com/news/minnesota-fraud-schemes-what-we-know/",
        "https://www.cnn.com/2025/12/29/us/minnesota-day-care-fraud-what-we-know"
      ]
    }
  },
  {
    "node_id": "crime_minnesota_daycare",
    "node_type": "ECONOMIC_EVENT",
    "name": "Minnesota Daycare Fraud Schemes",
    "aliases": [],
    "description": "Multiple daycare fraud schemes in Minnesota connected to immigrant communities exploiting gaps in federal oversight. Part of broader pattern of nonprofit/government program fraud.",
    "metadata": {
      "type": "fraud",
      "location": "Minnesota",
      "status": "prosecutions ongoing"
    }
  },
  {
    "node_id": "crime_hsbc_laundering",
    "node_type": "ECONOMIC_EVENT",
    "name": "HSBC Money Laundering ($1.92B Fine)",
    "aliases": [],
    "description": "HSBC paid $1.92B fine for laundering drug cartel money and hiding $19.4B in transactions with Iran. Same HSBC that owns 6.1% of NY Fed. No executives imprisoned.",
    "metadata": {
      "type": "money_laundering",
      "fine": 1920000000,
      "iran_hidden": 19400000000,
      "executives_imprisoned": 0,
      "year": 2012,
      "source_url": "https://en.wikipedia.org/wiki/HSBC"
    }
  },
  {
    "node_id": "crime_fentanyl_pipeline",
    "node_type": "ECONOMIC_EVENT",
    "name": "Fentanyl Precursor Pipeline (China → US)",
    "aliases": ["Fentanyl crisis"],
    "description": "Chinese chemical companies supply fentanyl precursors to Mexican cartels. ~100,000 US deaths/year. Enabled by PNTR trade normalization and weak supply chain enforcement. State Dept mandatory report documents China's role.",
    "metadata": {
      "type": "narcotics_trafficking",
      "deaths_per_year": 100000,
      "precursor_source": "China",
      "enabled_by": "leg_pntr_2000",
      "source_urls": [
        "https://www.brookings.edu/articles/the-fentanyl-pipeline-and-chinas-role-in-the-us-opioid-crisis/",
        "https://www.cfr.org/expert-brief/what-chinas-role-combating-illegal-fentanyl-trade",
        "https://www.npr.org/2024/08/29/nx-s1-5089978/fentanyl-china-precursors",
        "https://www.state.gov/wp-content/uploads/2025/09/Tab-1-Mandatory-Congressional-Report-on-China-Narcotics-Accessible-9.17.2025.pdf"
      ]
    }
  },
  {
    "node_id": "crime_forced_labor_xinjiang",
    "node_type": "ECONOMIC_EVENT",
    "name": "Xinjiang Forced Labor (Uyghur)",
    "aliases": ["Uyghur forced labor"],
    "description": "Documented forced labor in Xinjiang supplying US consumer goods supply chains. Congress passed UFLPA. BlackRock/Vanguard invested in companies using forced labor per House CCP Committee.",
    "metadata": {
      "type": "human_rights_abuse",
      "legislation_response": "policy_uflpa",
      "source_url": "https://www.cfr.org/blog/chinas-use-forced-labor-xinjiang-wake-call-heard-round-world"
    }
  },
  {
    "node_id": "crime_censorship_infrastructure",
    "node_type": "ECONOMIC_EVENT", 
    "name": "Government Censorship Infrastructure (2021-2024)",
    "aliases": ["Biden censorship", "Disinformation Governance Board"],
    "description": "Documented federal government coordination with social media platforms to suppress speech. House Judiciary investigation produced multiple reports. CISA involved. Extended to AI training influence.",
    "metadata": {
      "type": "government_overreach",
      "investigating_body": "House Judiciary Committee",
      "source_urls": [
        "https://judiciary.house.gov/sites/evo-subsites/republicans-judiciary.house.gov/files/evo-media-document/Biden-WH-Censorship-Report-final.pdf",
        "https://judiciary.house.gov/sites/evo-subsites/republicans-judiciary.house.gov/files/evo-media-document/12.18.24%20Censorships%20Next%20Frontier%20The%20Federal%20Governments%20Attempt%20to%20Control%20Artificial%20Intelligence%20to%20Suppress%20Free%20Speech.pdf",
        "https://judiciary.house.gov/sites/evo-subsites/republicans-judiciary.house.gov/files/evo-media-document/cisa-staff-report6-26-23.pdf"
      ]
    }
  },
  {
    "node_id": "crime_frances_haugen_coordination",
    "node_type": "ECONOMIC_EVENT",
    "name": "Frances Haugen Testimony Coordination",
    "aliases": ["Facebook whistleblower"],
    "description": "Frances Haugen's 'whistleblower' testimony timing coordinated with Biden administration censorship campaign per House Judiciary investigation. Created public pressure for platform content regulation.",
    "metadata": {
      "type": "coordinated_narrative",
      "date": "2021-10",
      "source_urls": [
        "https://en.wikipedia.org/wiki/Frances_Haugen",
        "https://www.npr.org/2021/10/05/1043377310/facebook-whistleblower-frances-haugen-congress",
        "https://abcnews.go.com/Politics/key-takeaways-facebook-whistleblower-frances-haugens-senate-testimony/story?id=80419357"
      ]
    }
  },
  {
    "node_id": "crime_refugee_resettlement_fraud",
    "node_type": "ECONOMIC_EVENT",
    "name": "Refugee Resettlement Industry Fraud",
    "aliases": [],
    "description": "Pattern of fraud in federally-funded refugee resettlement programs. Government contracts creating perverse incentives. Connected to immigration lobbying by Chamber of Commerce.",
    "metadata": {
      "type": "fraud",
      "source_urls": [
        "https://capitalresearch.org/article/refugee-resettlement-the-lucrative-business-of-serving-immigrants",
        "https://www.npr.org/2025/02/12/nx-s1-5288819/refugee-agencies-federal-funds-layoffs"
      ]
    }
  }
]
```

---

## STEP 3: New Edge Types for These Layers

```json
[
  {"edge_type": "REPORTS_ON", "description": "Media/person covers a topic or entity"},
  {"edge_type": "VALIDATES", "description": "Independent source confirms a claim in the thesis"},
  {"edge_type": "ENABLED", "description": "Policy/legislation enabled a crime/fraud"},
  {"edge_type": "PROFITED_FROM", "description": "Entity profited from a crime or harmful activity"},
  {"edge_type": "INVESTIGATED", "description": "Body investigated a crime/entity"},
  {"edge_type": "COORDINATED_WITH", "description": "Entities coordinated actions"}
]
```

### Key Edges to Create

```json
[
  {
    "edge_id": "reports_srs_defense",
    "edge_type": "REPORTS_ON",
    "from_node_id": "media_shawn_ryan_show",
    "to_node_id": "event_pntr_passage",
    "source": "Shawn Ryan Show episodes",
    "source_type": "journalism",
    "confidence": 0.9,
    "notes": "Multiple episodes covering defense industrial base collapse, fentanyl, intelligence gaps - all downstream of PNTR/offshoring"
  },
  {
    "edge_id": "validates_rubio_reshoring",
    "edge_type": "VALIDATES",
    "from_node_id": "media_marco_rubio",
    "to_node_id": "policy_section_301_tariffs",
    "source": "State Dept",
    "source_url": "https://foreignpolicy.com/2026/02/14/rubio-munich-security-conference-speech/",
    "source_type": "gov_filing",
    "confidence": 1.0,
    "notes": "Secretary of State publicly validates reshoring thesis and tariff correction at Munich Security Conference"
  },
  {
    "edge_id": "validates_palantir_defense",
    "edge_type": "VALIDATES",
    "from_node_id": "media_palantir_foundry",
    "to_node_id": "event_pntr_passage",
    "source": "Public statements",
    "source_type": "journalism",
    "confidence": 0.85,
    "notes": "Palmer Luckey and Palantir publicly stated defense supply chain is broken - validates FGIP thesis from industry insider position"
  },
  {
    "edge_id": "enabled_pntr_fentanyl",
    "edge_type": "ENABLED",
    "from_node_id": "leg_pntr_2000",
    "to_node_id": "crime_fentanyl_pipeline",
    "source": "State Dept mandatory report",
    "source_url": "https://www.state.gov/wp-content/uploads/2025/09/Tab-1-Mandatory-Congressional-Report-on-China-Narcotics-Accessible-9.17.2025.pdf",
    "source_type": "gov_filing",
    "confidence": 0.95,
    "notes": "PNTR normalized trade with China → enabled chemical precursor supply chains → fentanyl crisis. ~100K deaths/year."
  },
  {
    "edge_id": "enabled_pntr_forced_labor",
    "edge_type": "ENABLED",
    "from_node_id": "leg_pntr_2000",
    "to_node_id": "crime_forced_labor_xinjiang",
    "source": "CFR",
    "source_url": "https://www.cfr.org/blog/chinas-use-forced-labor-xinjiang-wake-call-heard-round-world",
    "source_type": "journalism",
    "confidence": 0.9,
    "notes": "PNTR enabled supply chains dependent on Xinjiang forced labor"
  },
  {
    "edge_id": "profited_hsbc_laundering",
    "edge_type": "PROFITED_FROM",
    "from_node_id": "fin_hsbc",
    "to_node_id": "crime_hsbc_laundering",
    "source": "DOJ settlement",
    "source_url": "https://en.wikipedia.org/wiki/HSBC",
    "source_type": "gov_filing",
    "confidence": 1.0,
    "notes": "HSBC (6.1% NY Fed owner) laundered drug cartel money. $1.92B fine. Zero executives imprisoned."
  },
  {
    "edge_id": "profited_bv_forced_labor",
    "edge_type": "PROFITED_FROM",
    "from_node_id": "fin_blackrock",
    "to_node_id": "crime_forced_labor_xinjiang",
    "source": "House Select Committee on CCP",
    "source_url": "https://selectcommitteeontheccp.house.gov/sites/evo-subsites/selectcommitteeontheccp.house.gov/files/evo-media-document/4.18.24%20How%20Americsan%20Financial%20Institutions%20Provide%20Billions%20of%20Dollars%20to%20PRC%20Companies%20Committing%20Human%20Rights%20Abuses%20and%20Fueling%20the%20PRCs%20Military.pdf",
    "source_type": "gov_filing",
    "confidence": 1.0,
    "notes": "$1.9B invested in 63 blacklisted Chinese companies committing human rights abuses per House CCP Committee"
  },
  {
    "edge_id": "enabled_immigration_fraud",
    "edge_type": "ENABLED",
    "from_node_id": "org_us_chamber_of_commerce",
    "to_node_id": "crime_refugee_resettlement_fraud",
    "source": "Capital Research / CIS",
    "source_url": "https://capitalresearch.org/article/refugee-resettlement-the-lucrative-business-of-serving-immigrants",
    "source_type": "journalism",
    "confidence": 0.7,
    "notes": "Chamber lobbied for expanded immigration/refugee programs ($1.5B lobbying) → created scale that enabled oversight gaps → fraud"
  },
  {
    "edge_id": "coordinated_haugen_censorship",
    "edge_type": "COORDINATED_WITH",
    "from_node_id": "crime_frances_haugen_coordination",
    "to_node_id": "crime_censorship_infrastructure",
    "source": "House Judiciary Committee investigation",
    "source_url": "https://judiciary.house.gov/sites/evo-subsites/republicans-judiciary.house.gov/files/evo-media-document/Biden-WH-Censorship-Report-final.pdf",
    "source_type": "gov_filing",
    "confidence": 0.8,
    "notes": "Haugen testimony timing aligned with Biden administration push for platform content regulation. House Judiciary documented coordination."
  },
  {
    "edge_id": "investigated_judiciary_censorship",
    "edge_type": "INVESTIGATED",
    "from_node_id": "crime_censorship_infrastructure",
    "to_node_id": "crime_censorship_infrastructure",
    "source": "House Judiciary Weaponization Subcommittee",
    "source_url": "https://judiciary.house.gov/media/press-releases/weaponization-committee-exposes-biden-white-house-censorship-regime-new-report",
    "source_type": "gov_filing",
    "confidence": 1.0,
    "notes": "Multiple House Judiciary reports documenting censorship infrastructure including extension to AI training"
  }
]
```

---

## STEP 4: Risk Management Scoring

Add a new analysis module: `analysis/risk_scorer.py`

This scores BOTH thesis risk and investment risk:

### Thesis Risk Score (how likely is the thesis correct)

For any claim or path in the graph:

```python
def thesis_risk_score(claim_or_path):
    """
    Score 0-100 where 100 = highest confidence thesis is correct
    
    Factors:
    - Source tier (Tier 0 gov docs = +30, Tier 1 journalism = +20, Tier 2 = +5)
    - Independent validation count (how many independent sources confirm)
    - Signal layer confirmation (independent media covering same thesis = +10 each)
    - Accountability confirmation (criminal cases downstream = +15 each, 
      proves the system failure was real enough to prosecute)
    - Contradiction check (if entity contradicts itself = +10, 
      because spending money to fight something confirms it's real)
    - Time consistency (claims verified across multiple years = +10)
    """
```

### Investment Risk Score (for portfolio companies)

```python
def investment_risk_score(company):
    """
    Score 0-100 where 100 = highest risk
    
    Risk UP factors:
    - Company filed anti-tariff amicus (+30 = fighting the correction)
    - BlackRock/Vanguard are top shareholders (+10 = exposed to ownership loop pressure)
    - Revenue dependent on China trade (+20)
    - SCOTUS ruling creates uncertainty for tariff-dependent thesis (+15)
    - Single customer/contract concentration (+10)
    
    Risk DOWN factors:
    - Government equity stake (Intel 9.9% = -20, too big to let fail)
    - Bipartisan support for correction (-15)
    - Physical assets already built/building (-15, can't un-pour concrete)
    - Multiple independent revenue streams (-10)
    - Domestic supply chain (-10)
    - Independent media coverage validating demand (-5)
    
    Special: SCOTUS tariff ruling (Feb 20, 2026)
    - Section 301 tariffs MAY be affected
    - But OBBBA tax incentives are LEGISLATIVE not executive
    - CHIPS Act is LEGISLATIVE not executive  
    - Physical factories already built
    - Score should reflect: executive tariffs at risk, 
      legislative corrections stable, physical economy irreversible
    """
```

### Signal Convergence Score

```python
def signal_convergence(topic):
    """
    How many independent signals point at the same conclusion?
    
    For any topic node, count:
    - Government officials validating (Rubio, Trump EOs)
    - Independent media covering (SRS, JRE, Breaking Points, All-In)
    - Academic research confirming (Pierce & Schott, Autor/Dorn/Hanson)
    - Market data confirming (Great Rotation, ETF inflows)
    - Criminal cases confirming (fraud proves system failure was real)
    - Industry insiders confirming (Palantir, defense CEOs)
    
    Score = count of independent signal categories confirming
    Max = 6 (all categories)
    
    If 5-6: extremely high confidence
    If 3-4: high confidence  
    If 1-2: thesis exists but needs more validation
    If 0: speculation, not in database
    """
```

---

## STEP 5: New CLI Commands

```
# Signal layer
fgip signal list                          # Show all independent media nodes
fgip signal convergence <topic>           # How many independent signals confirm
fgip signal who-covers <entity>           # Which media covers this entity/topic

# Accountability layer  
fgip crime list                           # Show all crime/fraud nodes
fgip crime trace <crime_node>             # Trace what enabled this crime
fgip crime downstream <legislation>       # What crimes did this legislation enable

# Risk management
fgip risk thesis <claim_or_path>          # Thesis confidence score
fgip risk investment <company>            # Investment risk score
fgip risk portfolio                       # Score all correction companies
fgip risk scotus-impact                   # How Feb 20 ruling affects each company

# Combined
fgip briefing weekly                      # Generate weekly thesis update:
                                          # - New signals detected
                                          # - Risk score changes
                                          # - Contradiction alerts
                                          # - Portfolio impact assessment
```

---

## WHY THIS MATTERS FOR RISK MANAGEMENT

The SCOTUS tariff ruling (Feb 20, 2026) is exactly the kind of event 
that separates people who mapped the system from people who gambled.

Without this risk layer:
"Tariffs struck down → reshoring thesis dead → panic sell"

With this risk layer:
"Tariffs struck down BUT:
 - Signal convergence = 6/6 (all categories confirm reshoring)
 - Legislative corrections (OBBBA, CHIPS) unaffected by ruling
 - Physical factories already built (irreversible)
 - 37 amicus briefs cost real money = confirmation correction was working
 - Fentanyl crisis still killing 100K/year = political pressure continues
 - Investment risk: Intel 45/100, Caterpillar 35/100 (low risk)
 → Thesis intact. Ruling affects executive tariffs only. 
   Hold positions. Court ruling creates buying opportunity."

THAT'S risk management. Not vibes. Scored, sourced, queryable.
