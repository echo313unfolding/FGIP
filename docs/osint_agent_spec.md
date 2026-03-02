# FGIP OSINT Agent Expansion — Build Specification

## Priority 1: FARA Agent (foreign lobbying — fills biggest gap)
**Source:** fara.gov/search
**Data:** Foreign principal registrations, lobbying activities, foreign agent registrations
**Tier:** 0 (government filing)
**What it catches:** The 90 former lawmakers who became foreign lobbyists. Boustany → Chinese government. Vitter → Hikvision. Every undisclosed foreign lobbying relationship.
**Edge types:** LOBBIED_FOR (foreign), EMPLOYED (revolving door), REGISTERED_AS_AGENT
**Implementation:** HTML scraping (no API, but structured search results). Weekly poll.

## Priority 2: OpenSecrets Bulk Agent (lobbying + campaign finance)
**Source:** opensecrets.org/bulk-data (or API)
**Data:** Lobbying disclosures, campaign contributions, revolving door, 527 orgs
**Tier:** 1 (structured journalism/nonprofit)
**What it catches:** Dollar amounts on every lobbying relationship. PAC → candidate → vote chains. The full $1.8B Chamber spend broken down by year, issue, and target.
**Edge types:** LOBBIED_FOR (with dollar amounts), DONATED_TO (campaign), EMPLOYED (revolving door)
**Implementation:** Bulk CSV download, parse, cross-reference against nodes table. Monthly refresh.

## Priority 3: ProPublica APIs Agent (nonprofit + congressional)
**Source:** projects.propublica.org/nonprofits/ (990 filings), propublica.org/datastore/
**Data:** Think tank/nonprofit funding (990 forms), congressional voting records
**Tier:** 0 (IRS filings) / 1 (ProPublica analysis)
**What it catches:** Koch → Cato $5.27M, Bradley → Heritage, Donors Trust pipeline. Congressional votes matched to donor profiles.
**Edge types:** DONATED_TO (foundation → think tank), VOTED_FOR/AGAINST (legislator → bill)
**Implementation:** JSON API. Quarterly refresh on 990s, real-time on votes.

## Priority 4: USASpending Agent (federal contracts/grants)
**Source:** usaspending.gov/api
**Data:** Federal contracts, grants, sub-awards
**Tier:** 0 (government)
**What it catches:** CHIPS Act disbursements to Intel, TSMC, etc. Defense contracts flowing to the 5 remaining primes. Federal grants to entities in the graph.
**Edge types:** AWARDED_CONTRACT, RECEIVED_GRANT
**Implementation:** REST API, well-documented. Weekly poll on entities in nodes table.

## Priority 5: FEC Agent (campaign finance)
**Source:** api.open.fec.gov
**Data:** Individual contributions, PAC contributions, independent expenditures
**Tier:** 0 (government)
**What it catches:** Complete donor → PAC → candidate → vote chain. Club for Growth scorecards. Chamber PAC spending on specific races.
**Edge types:** DONATED_TO (campaign), SUPPORTED/OPPOSED (independent expenditure)
**Implementation:** REST API with API key. Event-driven (new filings trigger proposals).

## Priority 6: PACER/RECAP Agent (federal court filings)
**Source:** courtlistener.com/api (free RECAP archive of PACER)
**Data:** Federal case filings, dockets, opinions
**Tier:** 0 (court records)
**What it catches:** Every amicus brief filing (the 37 anti-tariff briefs), consent decrees, settlement agreements, criminal indictments (Feeding Our Future, HSBC).
**Edge types:** FILED_AMICUS, INDICTED, SETTLED, RULED_ON
**Implementation:** CourtListener API (free, comprehensive). Daily poll on tracked cases.

## Priority 7: Federal Register Agent (regulations/executive orders)
**Source:** federalregister.gov/api
**Data:** Executive orders, proposed rules, agency actions, public comments
**Tier:** 0 (government)
**What it catches:** Tariff modifications, CHIPS Act implementation rules, immigration policy changes, any regulatory action touching thesis.
**Edge types:** ISSUED_ORDER, PROPOSED_RULE, COMMENTED_ON
**Implementation:** REST API, excellent documentation. Daily RSS poll.

## Entity-Driven Monitoring Pattern

```python
class EntityWatchAgent(FGIPAgent):
    """Monitors all OSINT sources for activity on tracked entities."""
    
    def collect(self):
        # Get all nodes from database
        nodes = self.db.get_all_nodes()
        
        for node in nodes:
            # Check each OSINT source for mentions
            fara_hits = self.check_fara(node)
            opensecrets_hits = self.check_opensecrets(node)  
            fec_hits = self.check_fec(node)
            usaspending_hits = self.check_usaspending(node)
            courtlistener_hits = self.check_courtlistener(node)
            
            # Combine all hits as artifacts
            yield from fara_hits + opensecrets_hits + fec_hits + ...

    def extract(self, artifacts):
        # Entity resolution: match OSINT hits to existing nodes
        # Propose new nodes for unmatched entities
        # Extract relationships from structured data
        pass

    def propose(self, facts):
        # Generate HYPOTHESIS claims/edges
        # Compute convergence: if 3+ sources mention same connection → high confidence
        # Flag for human review
        pass
```

## Signal Convergence Auto-Detection

When multiple independent sources confirm the same entity-to-entity connection:
- 1 source: HYPOTHESIS (confidence 0.3)
- 2 sources, same tier: HYPOTHESIS (confidence 0.5)  
- 2 sources, different tiers: INFERENCE candidate (confidence 0.7)
- 3+ sources, 2+ tiers: Strong INFERENCE candidate (confidence 0.85)
- Government filing + journalism + criminal case: Near-FACT (confidence 0.95)

Human still approves. But the system tells you WHERE to look.

## Investigative Journalism Integration

### Structured Sources (API/bulk available)
- ProPublica Nonprofit Explorer → 990 filings
- ICIJ Offshore Leaks → entity search API
- DocumentCloud → source document search
- MuckRock → completed FOIA requests

### Curated RSS (your existing RSS agent, expanded)
- ProPublica (investigations)
- The Intercept (national security)
- OCCRP (financial crime)  
- Reuters Investigations
- AP Investigations
- Bellingcat (methodology/verification)
- POGO (Project on Government Oversight)
- Brennan Center (judicial/democracy)
- Sunlight Foundation archives

### Keyword Watchlist (cross-reference against topics)
Topics already in database:
- Lobbying, Judicial, Ownership, Downstream, Censorship
- Reshoring, ThinkTank, IndependentMedia, Fraud, Stablecoin, ForeignPolicy

Add topic-specific keyword sets:
- Lobbying: "lobbying disclosure", "revolving door", "foreign agent", "FARA filing"
- Judicial: "amicus brief", "recusal", "financial disclosure", "ethics complaint"
- Ownership: "13F filing", "beneficial ownership", "cross-ownership", "proxy voting"
- Downstream: "reshoring", "supply chain", "domestic manufacturing", "CHIPS Act"
- Fraud: "indictment", "wire fraud", "money laundering", "deferred prosecution"
