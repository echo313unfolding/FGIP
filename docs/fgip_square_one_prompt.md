# FGIP Database — Square One Build Instructions for Claude Code

## Context

You have three files in ~/Downloads/ (search for anything with "fgip" in the name):

1. **fgip_claude_code_spec.md** — Full project architecture and seed data
2. **fgip_citation_database.md** — Sourced claims organized by category  
3. **fgip_all_source_urls.txt** — 698 unique source URLs

Read all three. The spec is your blueprint. But before you build the graph, 
you need to build the FOUNDATION layer first. Don't jump to edges yet.

---

## BUILD ORDER (Do these in sequence)

### Step 1: Create the SQLite database with these tables

```sql
-- Every source URL gets an entry
CREATE TABLE sources (
    source_id TEXT PRIMARY KEY,        -- sha256(url)
    url TEXT NOT NULL,
    domain TEXT,                        -- extracted from URL
    tier INTEGER DEFAULT 2,            -- 0=primary doc, 1=journalism citing primary, 2=commentary/blog/wiki
    retrieved_at TEXT,                  -- when we first found it
    artifact_path TEXT DEFAULT NULL,    -- local PDF/HTML snapshot path (null until captured)
    artifact_hash TEXT DEFAULT NULL,    -- sha256 of saved file (null until captured)
    notes TEXT DEFAULT NULL
);

-- Every factual claim gets an entry  
CREATE TABLE claims (
    claim_id TEXT PRIMARY KEY,          -- FGIP-000001, FGIP-000002, etc.
    claim_text TEXT NOT NULL,           -- the actual claim
    topic TEXT NOT NULL,                -- Lobbying, Judicial, Ownership, Downstream, Censorship, Reshoring, etc.
    status TEXT DEFAULT 'PARTIAL',      -- MISSING (placeholder only), PARTIAL (has URL not artifact), EVIDENCED (artifact captured), VERIFIED (Tier 0/1 artifact attached)
    required_tier INTEGER DEFAULT 1,   -- what tier is needed to consider this verified
    created_at TEXT DEFAULT (datetime('now')),
    notes TEXT DEFAULT NULL
);

-- Many-to-many: which sources support which claims
CREATE TABLE claim_sources (
    claim_id TEXT REFERENCES claims(claim_id),
    source_id TEXT REFERENCES sources(source_id),
    PRIMARY KEY (claim_id, source_id)
);

-- ONLY AFTER claims and sources are loaded, build the graph layer
CREATE TABLE nodes (
    node_id TEXT PRIMARY KEY,           -- slugified name: "us-chamber-of-commerce"
    name TEXT NOT NULL,                 -- "US Chamber of Commerce"
    node_type TEXT NOT NULL,            -- ORGANIZATION, PERSON, LEGISLATION, COURT_CASE, COMPANY, etc.
    metadata TEXT DEFAULT NULL,         -- JSON blob for extra fields
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE edges (
    edge_id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_node TEXT REFERENCES nodes(node_id),
    to_node TEXT REFERENCES nodes(node_id),
    relationship TEXT NOT NULL,         -- LOBBIED_FOR, OWNS_SHARES, FILED_AMICUS, etc.
    detail TEXT DEFAULT NULL,           -- "42.8% (87.9M shares, 2018)"
    claim_id TEXT REFERENCES claims(claim_id),  -- which claim supports this edge
    date_occurred TEXT DEFAULT NULL,
    confidence TEXT DEFAULT 'medium',   -- high, medium, low
    created_at TEXT DEFAULT (datetime('now'))
);
```

### Step 2: Load sources from fgip_all_source_urls.txt

For each URL in the file:
- Generate source_id = sha256 of the URL
- Extract domain from URL
- Auto-assign tier based on domain:

```python
TIER_0_DOMAINS = [
    'congress.gov', 'house.gov', 'senate.gov', 'whitehouse.gov', 
    'gao.gov', 'sec.gov', 'supremecourt.gov', 'justia.com',
    'federalreserve.gov', 'treasury.gov', 'state.gov', 'commerce.gov',
    'ncua.gov', 'archives.gov', 'govtrack.us', 'crsreports.congress.gov',
    'hhs.gov', 'bis.org'
]

TIER_1_DOMAINS = [
    'reuters.com', 'npr.org', 'propublica.org', 'opensecrets.org',
    'theintercept.com', 'scotusblog.com', 'cnn.com', 'washingtonpost.com',
    'nytimes.com', 'bbc.co.uk', 'apnews.com', 'fortune.com',
    'influencewatch.org', 'brookings.edu', 'cfr.org', 'rand.org',
    'aei.org', 'harvard.edu', 'columbia.edu', 'unc.edu',
    'ucdavis.edu', 'doi.org'
]

# Everything else defaults to TIER_2
```

### Step 3: Parse claims from fgip_citation_database.md

The citation database is organized in markdown tables. For each row:
- Generate sequential claim_id (FGIP-000001, FGIP-000002...)
- Extract claim_text from the "Claim" column
- Extract topic from the section header (I, II, III... maps to topic)
- Extract source URL(s) from the "Source" column
- Set status:
  - **MISSING** if source column has no URL (just text like "Public record" or "Earnings calls")
  - **PARTIAL** if source column has a URL
  - Status upgrades to EVIDENCED/VERIFIED later when artifacts are captured
- Set required_tier:
  - Ownership percentages → requires Tier 0 (SEC/FOIA)
  - Dollar amounts (lobbying spend, fines) → requires Tier 0
  - Legislative outcomes → requires Tier 0 (congress.gov)
  - Court rulings → requires Tier 0 (court docket)
  - Market performance claims → requires Tier 1 (financial data)
  - Interpretive/analytical claims → Tier 2 acceptable
- Link claim to source(s) via claim_sources table

### Step 4: Build nodes from claims

Scan all claims and extract unique entities. Create a node for each:

**Node types to extract:**
- ORGANIZATION: US Chamber of Commerce, BlackRock, Vanguard, Heritage Foundation, Cato Institute, BIS, etc.
- PERSON: Ginni Thomas, Clarence Thomas, Harlan Crow, Larry Fink, etc.
- LEGISLATION: PNTR (2000), CHIPS Act, OBBBA, GENIUS Act, Anti-CBDC Act, etc.
- COURT_CASE: Learning Resources v. Trump, V.O.S. Selections v. Trump, etc.
- COMPANY: Caterpillar, Intel, Nucor, Eaton, Constellation Energy, HSBC, JPMorgan, etc.
- FINANCIAL_INST: NY Fed, Federal Reserve, BIS, credit unions (as category)
- MEDIA_OUTLET: Gannett, Sinclair, Graham Media, Bloomberg
- ECONOMIC_EVENT: PNTR passage, China Shock, Great Rotation 2026, etc.

### Step 5: Build edges from claims

For each claim, determine the relationship it documents and create an edge:
- "Citibank owns 42.8% of NY Fed" → edge(citibank, ny-fed, OWNS_SHARES, "42.8%", claim_id=FGIP-000XXX)
- "Chamber lobbied for PNTR" → edge(us-chamber, pntr-2000, LOBBIED_FOR, "$1.8B+", claim_id=FGIP-000XXX)
- Every edge MUST reference a claim_id. No orphan edges.

### Step 6: Build the CLI

Simple command-line interface:

```
fgip> query "Chamber of Commerce"
  → Shows all edges connected to this node with claim status

fgip> trace "US Chamber of Commerce" → "Caterpillar"  
  → Finds all paths between these two nodes through the graph
  → Shows evidence quality: "This chain is 85% Tier 0/1 evidenced"

fgip> status
  → Summary: X claims total, Y VERIFIED, Z PARTIAL, W MISSING
  → "Evidence coverage: 72% of edges have Tier 0/1 sources"

fgip> missing
  → Lists all MISSING claims that need source URLs

fgip> upgrade FGIP-000042
  → Prompts to add artifact path + hash for a specific claim

fgip> add-node "New Entity" --type COMPANY
fgip> add-edge "New Entity" → "Existing Entity" --rel SUPPLIES --claim FGIP-000XXX
fgip> add-claim "New factual claim" --topic Reshoring --source https://example.com
```

---

## IMPORTANT PRINCIPLES

1. **Claims before edges.** No edge exists without a claim_id backing it.

2. **Honesty over completeness.** A claim marked PARTIAL is more valuable 
   than a claim marked VERIFIED without proof. The system tracks what's 
   proven vs what's pending. That's the credibility moat.

3. **Tier auto-assignment is a starting point.** I'll manually upgrade/downgrade 
   as I verify sources.

4. **Append-only.** Never delete. Mark things as superseded if needed.

5. **The evidence coverage score is the product.** When the system can say 
   "This causality chain from Chamber lobbying to manufacturing job loss 
   is 92% Tier 0/1 evidenced" — that's what no other think tank has.

---

## WHAT SUCCESS LOOKS LIKE AFTER STEP 6

I should be able to run:

```
fgip> trace "US Chamber of Commerce" → "fentanyl crisis"
```

And get back something like:

```
Path found (4 hops, 78% Tier 0/1 evidenced):

1. US Chamber of Commerce --LOBBIED_FOR--> PNTR (2000)
   Claim: FGIP-000003 [VERIFIED, Tier 0] 
   Source: congress.gov/bill/106th-congress/house-bill/4444

2. PNTR (2000) --CAUSED--> Manufacturing job loss (2.4M)
   Claim: FGIP-000012 [PARTIAL, Tier 1]
   Source: doi.org/10.1111/ajps.12485 (Pierce & Schott)

3. Manufacturing job loss --CAUSED--> Supply chain offshoring to China
   Claim: FGIP-000015 [PARTIAL, Tier 1]
   Source: Autor, Dorn, Hanson research

4. Supply chain offshoring --ENABLED--> Fentanyl precursor pipeline
   Claim: FGIP-000089 [VERIFIED, Tier 0]
   Source: state.gov mandatory report on China narcotics
```

That's the engine. Build it.
