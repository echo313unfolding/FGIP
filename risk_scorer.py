"""
FGIP Risk Scorer - Thesis confidence, investment risk, and signal convergence.

Three scoring systems:
1. thesis_risk_score() - How confident is the thesis (0-100, higher = more confident)
2. investment_risk_score() - How risky is a company investment (0-100, higher = more risk)
3. signal_convergence() - How many independent signal categories confirm a topic (0-6)
"""

import sqlite3
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


# Signal categories for convergence scoring
SIGNAL_CATEGORIES = {
    'government_official': 'Government validation (Rubio, Trump EOs, State Dept)',
    'independent_media': 'Independent media coverage (SRS, JRE, Breaking Points)',
    'academic': 'Academic research (Pierce & Schott, Autor/Dorn/Hanson)',
    'market_data': 'Market data confirmation (Great Rotation, ETF inflows)',
    'criminal_case': 'Criminal cases proving system failure',
    'industry_insider': 'Industry insider validation (Palantir, defense CEOs)',
}

# Tier 0 domains for source quality scoring
TIER_0_WEIGHT = 30
TIER_1_WEIGHT = 20
TIER_2_WEIGHT = 5

# Topic-to-related-nodes mapping for convergence
TOPIC_KEYWORDS = {
    'reshoring': ['reshoring', 'manufacturing', 'domestic', 'onshoring', 'chips', 'tariff'],
    'china_threat': ['china', 'ccp', 'prc', 'beijing', 'xinjiang', 'fentanyl'],
    'defense_industrial_base': ['defense', 'military', 'pentagon', 'dod', 'munitions'],
    'institutional_capture': ['chamber', 'lobby', 'blackrock', 'vanguard', 'fed'],
    'correction': ['correction', 'reshoring', 'tariff', 'chips', 'obbba'],
}


@dataclass
class ThesisRiskResult:
    """Result of thesis risk scoring."""
    score: int  # 0-100, higher = more confident
    source_quality_score: int
    validation_count: int
    signal_categories: List[str]
    accountability_confirmations: int
    contradictions_found: int
    breakdown: Dict[str, int]


@dataclass
class InvestmentRiskResult:
    """Result of investment risk scoring."""
    score: int  # 0-100, higher = more risky
    company: str
    risk_factors: List[Tuple[str, int]]  # (factor, points)
    mitigating_factors: List[Tuple[str, int]]
    scotus_exposure: str  # 'high', 'medium', 'low', 'none'
    breakdown: Dict[str, int]


@dataclass
class SignalConvergenceResult:
    """Result of signal convergence analysis."""
    score: int  # 0-6 categories
    categories_confirmed: List[str]
    signals_by_category: Dict[str, List[Dict]]
    confidence_level: str  # 'extreme', 'high', 'moderate', 'low', 'speculation'


def thesis_risk_score(
    conn: sqlite3.Connection,
    claim_id: Optional[str] = None,
    path_edges: Optional[List[int]] = None,
) -> ThesisRiskResult:
    """
    Score thesis confidence for a claim or path.

    Score 0-100 where 100 = highest confidence thesis is correct.

    Factors:
    - Source tier (Tier 0 gov docs = +30, Tier 1 journalism = +20, Tier 2 = +5)
    - Independent validation count (how many independent sources confirm)
    - Signal layer confirmation (independent media covering same thesis)
    - Accountability confirmation (criminal cases downstream)
    - Contradiction check (entities fighting the correction)
    """
    cursor = conn.cursor()
    score = 0
    breakdown = {}

    # Get claims to analyze
    claim_ids = []
    if claim_id:
        claim_ids = [claim_id]
    elif path_edges:
        cursor.execute(f"""
            SELECT DISTINCT claim_id FROM edges
            WHERE edge_id IN ({','.join('?' * len(path_edges))})
        """, path_edges)
        claim_ids = [row['claim_id'] for row in cursor.fetchall() if row['claim_id']]

    if not claim_ids:
        return ThesisRiskResult(
            score=0,
            source_quality_score=0,
            validation_count=0,
            signal_categories=[],
            accountability_confirmations=0,
            contradictions_found=0,
            breakdown={'error': 'No claims to analyze'},
        )

    # Source tier scoring
    source_score = 0
    for cid in claim_ids:
        cursor.execute("""
            SELECT MIN(s.tier) as best_tier
            FROM claim_sources cs
            JOIN sources s ON cs.source_id = s.source_id
            WHERE cs.claim_id = ?
        """, (cid,))
        row = cursor.fetchone()
        if row and row['best_tier'] is not None:
            tier = row['best_tier']
            if tier == 0:
                source_score += TIER_0_WEIGHT
            elif tier == 1:
                source_score += TIER_1_WEIGHT
            else:
                source_score += TIER_2_WEIGHT

    # Average across claims
    source_score = min(source_score // len(claim_ids), 30) if claim_ids else 0
    breakdown['source_quality'] = source_score
    score += source_score

    # Independent validation count
    validation_count = 0
    for cid in claim_ids:
        cursor.execute("""
            SELECT COUNT(DISTINCT s.domain) as domains
            FROM claim_sources cs
            JOIN sources s ON cs.source_id = s.source_id
            WHERE cs.claim_id = ?
        """, (cid,))
        validation_count += cursor.fetchone()['domains'] or 0

    validation_score = min(validation_count * 5, 20)
    breakdown['independent_validation'] = validation_score
    score += validation_score

    # Signal layer confirmation
    signal_cats = []
    cursor.execute("""
        SELECT DISTINCT json_extract(n.metadata, '$.signal_type') as signal_type
        FROM nodes n
        JOIN edges e ON n.node_id = e.from_node
        WHERE e.relationship IN ('REPORTS_ON', 'VALIDATES')
        AND json_extract(n.metadata, '$.signal_type') IS NOT NULL
    """)
    for row in cursor.fetchall():
        if row['signal_type']:
            signal_cats.append(row['signal_type'])

    signal_score = min(len(set(signal_cats)) * 10, 20)
    breakdown['signal_confirmation'] = signal_score
    score += signal_score

    # Accountability confirmation (criminal cases proving system failure)
    cursor.execute("""
        SELECT COUNT(*) as count FROM nodes
        WHERE json_extract(metadata, '$.type') IN ('fraud', 'money_laundering', 'narcotics_trafficking', 'human_rights_abuse')
    """)
    acc_count = cursor.fetchone()['count'] or 0
    acc_score = min(acc_count * 5, 15)
    breakdown['accountability_confirmation'] = acc_score
    score += acc_score

    # Contradiction check (entities fighting correction = confirmation it's real)
    cursor.execute("""
        SELECT COUNT(*) as count FROM edges
        WHERE relationship = 'FILED_AMICUS'
    """)
    contradiction_count = cursor.fetchone()['count'] or 0
    contradiction_score = min(contradiction_count * 3, 10)
    breakdown['contradiction_confirmation'] = contradiction_score
    score += contradiction_score

    return ThesisRiskResult(
        score=min(score, 100),
        source_quality_score=source_score,
        validation_count=validation_count,
        signal_categories=list(set(signal_cats)),
        accountability_confirmations=acc_count,
        contradictions_found=contradiction_count,
        breakdown=breakdown,
    )


def investment_risk_score(
    conn: sqlite3.Connection,
    company: str,
) -> InvestmentRiskResult:
    """
    Score investment risk for a company.

    Score 0-100 where 100 = highest risk.

    Risk UP:
    - Filed anti-tariff amicus (+30)
    - BlackRock/Vanguard top shareholders (+10)
    - China trade dependent (+20)
    - SCOTUS tariff uncertainty (+15)

    Risk DOWN:
    - Government equity stake (-20)
    - Bipartisan support (-15)
    - Physical assets built (-15)
    - Domestic supply chain (-10)
    """
    cursor = conn.cursor()

    # Find company node
    cursor.execute("""
        SELECT node_id, name, metadata FROM nodes
        WHERE LOWER(name) LIKE LOWER(?) OR node_id = ?
    """, (f'%{company}%', company.lower().replace(' ', '-')))
    node = cursor.fetchone()

    if not node:
        return InvestmentRiskResult(
            score=50,  # Unknown = medium risk
            company=company,
            risk_factors=[('Company not found in database', 0)],
            mitigating_factors=[],
            scotus_exposure='unknown',
            breakdown={'error': 'Company not found'},
        )

    node_id = node['node_id']
    risk_factors = []
    mitigating_factors = []
    score = 50  # Start neutral

    # Check if filed anti-tariff amicus
    cursor.execute("""
        SELECT COUNT(*) as count FROM edges
        WHERE from_node = ? AND relationship = 'FILED_AMICUS'
        AND (LOWER(detail) LIKE '%tariff%' OR LOWER(detail) LIKE '%against%')
    """, (node_id,))
    if cursor.fetchone()['count'] > 0:
        risk_factors.append(('Filed anti-tariff amicus brief', 30))
        score += 30

    # Check BlackRock/Vanguard ownership
    cursor.execute("""
        SELECT from_node FROM edges
        WHERE to_node = ? AND relationship = 'OWNS_SHARES'
        AND from_node IN ('blackrock', 'vanguard', 'state-street')
    """, (node_id,))
    bv_owners = [row['from_node'] for row in cursor.fetchall()]
    if bv_owners:
        risk_factors.append((f"Owned by {', '.join(bv_owners)}", 10))
        score += 10

    # Check for government stake (risk reduction)
    cursor.execute("""
        SELECT detail FROM edges
        WHERE to_node = ? AND from_node LIKE '%government%'
        AND relationship = 'OWNS_SHARES'
    """, (node_id,))
    gov_stake = cursor.fetchone()
    if gov_stake:
        mitigating_factors.append(('Government equity stake', -20))
        score -= 20

    # Check for reshoring/correction involvement (risk reduction)
    cursor.execute("""
        SELECT COUNT(*) as count FROM edges e
        JOIN claims c ON e.claim_id = c.claim_id
        WHERE (e.from_node = ? OR e.to_node = ?)
        AND c.topic = 'Reshoring'
    """, (node_id, node_id))
    if cursor.fetchone()['count'] > 0:
        mitigating_factors.append(('Active reshoring investment', -15))
        score -= 15

    # SCOTUS exposure assessment
    scotus_exposure = 'low'
    if any('tariff' in f[0].lower() for f in risk_factors):
        scotus_exposure = 'high'
    elif any('reshoring' in f[0].lower() for f in mitigating_factors):
        scotus_exposure = 'medium'  # Legislative protections help

    # Known correction companies get risk reduction
    correction_companies = ['intel', 'caterpillar', 'nucor', 'cleveland-cliffs', 'us-steel']
    if node_id in correction_companies:
        mitigating_factors.append(('Known correction beneficiary', -10))
        score -= 10

    score = max(0, min(100, score))

    return InvestmentRiskResult(
        score=score,
        company=node['name'],
        risk_factors=risk_factors,
        mitigating_factors=mitigating_factors,
        scotus_exposure=scotus_exposure,
        breakdown={
            'base': 50,
            'risk_up': sum(f[1] for f in risk_factors),
            'risk_down': sum(f[1] for f in mitigating_factors),
        },
    )


def signal_convergence(
    conn: sqlite3.Connection,
    topic: str,
) -> SignalConvergenceResult:
    """
    Count how many independent signal categories confirm a topic.

    Categories:
    1. government_official - Rubio, Trump EOs, State Dept
    2. independent_media - SRS, JRE, Breaking Points, All-In
    3. academic - Pierce & Schott, Autor/Dorn/Hanson
    4. market_data - Great Rotation, ETF inflows
    5. criminal_case - Fraud/crime proving system failure
    6. industry_insider - Palantir, defense CEOs

    Returns 0-6 where 6 = all categories confirm.
    """
    cursor = conn.cursor()
    topic_lower = topic.lower()

    # Get keywords for this topic
    keywords = TOPIC_KEYWORDS.get(topic_lower, [topic_lower])

    confirmed_categories = {}
    signals_by_cat = {}

    # Check each signal category
    for cat, description in SIGNAL_CATEGORIES.items():
        signals_by_cat[cat] = []

        # Find signal nodes of this type
        cursor.execute("""
            SELECT n.node_id, n.name, n.metadata
            FROM nodes n
            WHERE json_extract(n.metadata, '$.signal_type') = ?
        """, (cat,))

        for node in cursor.fetchall():
            # Check if this signal covers our topic
            metadata = node['metadata'] or '{}'
            topics_covered = []

            try:
                import json
                meta = json.loads(metadata)
                topics_covered = meta.get('topics_covered', [])
            except:
                pass

            # Check topic match
            matches = any(
                any(kw in tc.lower() for kw in keywords)
                for tc in topics_covered
            )

            if matches:
                signals_by_cat[cat].append({
                    'node_id': node['node_id'],
                    'name': node['name'],
                })
                confirmed_categories[cat] = True

    # Check for criminal cases related to topic
    cursor.execute("""
        SELECT n.node_id, n.name, n.metadata
        FROM nodes n
        WHERE json_extract(n.metadata, '$.type') IN
            ('fraud', 'money_laundering', 'narcotics_trafficking', 'human_rights_abuse')
    """)
    for node in cursor.fetchall():
        metadata = node['metadata'] or '{}'
        # Check if crime connects to topic
        if any(kw in metadata.lower() or kw in node['name'].lower() for kw in keywords):
            signals_by_cat['criminal_case'].append({
                'node_id': node['node_id'],
                'name': node['name'],
            })
            confirmed_categories['criminal_case'] = True

    # Check for academic sources
    cursor.execute("""
        SELECT DISTINCT s.domain FROM sources s
        WHERE s.tier = 1 AND s.domain LIKE '%.edu'
    """)
    academic_domains = [row['domain'] for row in cursor.fetchall()]
    if academic_domains:
        for domain in academic_domains[:3]:
            signals_by_cat['academic'].append({
                'node_id': f'source_{domain}',
                'name': domain,
            })
        confirmed_categories['academic'] = True

    # Calculate score
    score = len(confirmed_categories)

    # Confidence level
    if score >= 5:
        confidence = 'extreme'
    elif score >= 4:
        confidence = 'high'
    elif score >= 3:
        confidence = 'moderate'
    elif score >= 1:
        confidence = 'low'
    else:
        confidence = 'speculation'

    return SignalConvergenceResult(
        score=score,
        categories_confirmed=list(confirmed_categories.keys()),
        signals_by_category=signals_by_cat,
        confidence_level=confidence,
    )


def scotus_impact_assessment(conn: sqlite3.Connection) -> Dict:
    """
    Assess impact of SCOTUS tariff ruling (Feb 20, 2026) on portfolio.

    Returns assessment of what's at risk vs protected.
    """
    cursor = conn.cursor()

    assessment = {
        'ruling_date': '2026-02-20',
        'ruling_summary': 'Court struck down executive tariff authority under IEEPA',
        'at_risk': [],
        'protected': [],
        'irreversible': [],
        'confirmation_signals': [],
    }

    # Executive tariffs at risk
    cursor.execute("""
        SELECT n.name, n.node_id FROM nodes n
        WHERE n.node_type = 'LEGISLATION'
        AND (LOWER(n.name) LIKE '%tariff%' OR LOWER(n.name) LIKE '%301%')
    """)
    for row in cursor.fetchall():
        assessment['at_risk'].append({
            'name': row['name'],
            'node_id': row['node_id'],
            'reason': 'Executive tariff authority challenged by SCOTUS ruling',
        })

    # Legislative corrections protected
    legislative_protected = ['CHIPS Act', 'OBBBA', 'IRA', 'Infrastructure Act']
    for leg in legislative_protected:
        cursor.execute("""
            SELECT node_id, name FROM nodes
            WHERE LOWER(name) LIKE LOWER(?) AND node_type = 'LEGISLATION'
        """, (f'%{leg}%',))
        row = cursor.fetchone()
        if row:
            assessment['protected'].append({
                'name': row['name'],
                'node_id': row['node_id'],
                'reason': 'Legislative action - not affected by executive authority ruling',
            })

    # Physical assets irreversible
    cursor.execute("""
        SELECT DISTINCT n.name, n.node_id FROM nodes n
        JOIN edges e ON n.node_id = e.from_node
        WHERE n.node_type = 'COMPANY'
        AND e.relationship IN ('INVESTED_IN', 'BUILT', 'ANNOUNCED')
    """)
    for row in cursor.fetchall():
        assessment['irreversible'].append({
            'name': row['name'],
            'node_id': row['node_id'],
            'reason': 'Physical factories already built/building - cannot un-pour concrete',
        })

    # Amicus briefs as confirmation signal
    cursor.execute("""
        SELECT COUNT(DISTINCT from_node) as count FROM edges
        WHERE relationship = 'FILED_AMICUS'
    """)
    amicus_count = cursor.fetchone()['count']
    if amicus_count > 0:
        assessment['confirmation_signals'].append({
            'signal': f'{amicus_count} organizations filed amicus briefs',
            'interpretation': 'Real money spent fighting correction = confirmation it was working',
        })

    return assessment


def portfolio_risk_summary(conn: sqlite3.Connection) -> List[Dict]:
    """
    Score all correction companies for investment risk.
    """
    cursor = conn.cursor()

    # Find correction-related companies
    cursor.execute("""
        SELECT DISTINCT n.node_id, n.name FROM nodes n
        WHERE n.node_type = 'COMPANY'
        AND n.node_id IN (
            SELECT from_node FROM edges WHERE relationship IN ('INVESTED_IN', 'BUILT', 'ANNOUNCED')
            UNION
            SELECT to_node FROM edges WHERE relationship = 'SUPPLIES'
        )
    """)

    results = []
    for row in cursor.fetchall():
        risk = investment_risk_score(conn, row['node_id'])
        results.append({
            'company': risk.company,
            'node_id': row['node_id'],
            'risk_score': risk.score,
            'scotus_exposure': risk.scotus_exposure,
            'risk_factors': len(risk.risk_factors),
            'mitigating_factors': len(risk.mitigating_factors),
        })

    # Sort by risk score
    results.sort(key=lambda x: x['risk_score'], reverse=True)
    return results
