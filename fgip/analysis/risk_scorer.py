"""FGIP Risk Management Layer.

Three scoring systems:
1. thesis_risk_score - How confident is the thesis (0-100, higher = more confident)
2. investment_risk_score - Investment risk for a company (0-100, higher = more risky)
3. signal_convergence - How many independent signals confirm (0-6)

Combined these answer: "Is the thesis correct?" and "Should I hold/buy/sell?"
"""

import json
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum


class SignalCategory(Enum):
    """Categories of independent signals."""
    GOVERNMENT = "government"  # Officials validating (Rubio, Trump EOs)
    INDEPENDENT_MEDIA = "independent_media"  # SRS, JRE, Breaking Points
    ACADEMIC = "academic"  # Pierce & Schott, Autor/Dorn/Hanson
    MARKET_DATA = "market_data"  # Great Rotation, ETF inflows
    CRIMINAL_CASES = "criminal_cases"  # Fraud proves system failure
    INDUSTRY_INSIDER = "industry_insider"  # Palantir, defense CEOs


@dataclass
class ThesisRiskResult:
    """Result of thesis risk scoring."""
    score: int  # 0-100, higher = more confident
    tier_score: int
    validation_count: int
    signal_confirmations: int
    accountability_confirmations: int
    contradictions: int
    time_consistency: bool
    factors: List[str]


@dataclass
class InvestmentRiskResult:
    """Result of investment risk scoring."""
    score: int  # 0-100, higher = more risky
    risk_factors: List[Tuple[str, int]]  # (factor, delta)
    protection_factors: List[Tuple[str, int]]
    scotus_impact: str  # "high", "medium", "low", "none"
    recommendation: str  # "hold", "buy", "reduce", "avoid"


@dataclass
class SignalConvergenceResult:
    """Result of signal convergence analysis."""
    score: int  # 0-6
    categories_confirmed: List[SignalCategory]
    confidence_level: str  # "extreme", "high", "medium", "low"
    details: Dict[str, List[str]]


class RiskScorer:
    """Risk Management scoring engine."""

    def __init__(self, db):
        """Initialize with database connection."""
        self.db = db

    def thesis_risk_score(self, claim_id: str = None, path_nodes: List[str] = None) -> ThesisRiskResult:
        """Score thesis confidence for a claim or causal path.

        Args:
            claim_id: Optional specific claim to score
            path_nodes: Optional list of node_ids forming a causal path

        Returns:
            ThesisRiskResult with 0-100 score (100 = highest confidence)
        """
        conn = self.db.connect()
        factors = []
        score = 0

        # If scoring a specific claim
        if claim_id:
            claim = conn.execute(
                "SELECT * FROM claims WHERE claim_id = ?", (claim_id,)
            ).fetchone()

            if claim:
                # Get sources for this claim
                sources = conn.execute(
                    """SELECT s.tier FROM sources s
                       JOIN claim_sources cs ON s.source_id = cs.source_id
                       WHERE cs.claim_id = ?""",
                    (claim_id,)
                ).fetchall()

                # Score based on source tiers
                tier_score = 0
                for source in sources:
                    if source["tier"] == 0:
                        tier_score += 30
                    elif source["tier"] == 1:
                        tier_score += 20
                    else:
                        tier_score += 5

                tier_score = min(tier_score, 50)  # Cap at 50
                score += tier_score
                factors.append(f"Source tier score: +{tier_score}")

        # If scoring a causal path
        if path_nodes:
            # Count edges with high confidence
            edge_count = 0
            for i in range(len(path_nodes) - 1):
                edge = conn.execute(
                    """SELECT confidence FROM edges
                       WHERE from_node_id = ? AND to_node_id = ?""",
                    (path_nodes[i], path_nodes[i + 1])
                ).fetchone()
                if edge and edge["confidence"] >= 0.8:
                    edge_count += 1

            if edge_count > 0:
                path_score = min(edge_count * 10, 30)
                score += path_score
                factors.append(f"Path coherence ({edge_count} strong edges): +{path_score}")

        # Independent validation count
        validation_count = self._count_independent_validations(conn)
        validation_score = min(validation_count * 5, 20)
        score += validation_score
        factors.append(f"Independent validations ({validation_count}): +{validation_score}")

        # Signal layer confirmation
        signal_nodes = conn.execute(
            """SELECT COUNT(*) as cnt FROM nodes
               WHERE metadata LIKE '%signal_type%'"""
        ).fetchone()
        signal_count = signal_nodes["cnt"] if signal_nodes else 0
        signal_score = min(signal_count * 2, 15)
        score += signal_score
        factors.append(f"Signal layer nodes ({signal_count}): +{signal_score}")

        # Accountability confirmation (crime nodes prove system failure)
        crime_nodes = conn.execute(
            """SELECT COUNT(*) as cnt FROM nodes
               WHERE node_id LIKE 'crime_%' OR metadata LIKE '%fraud%'"""
        ).fetchone()
        crime_count = crime_nodes["cnt"] if crime_nodes else 0
        crime_score = min(crime_count * 5, 15)
        score += crime_score
        factors.append(f"Accountability nodes ({crime_count}): +{crime_score}")

        score = min(score, 100)

        return ThesisRiskResult(
            score=score,
            tier_score=tier_score if claim_id else 0,
            validation_count=validation_count,
            signal_confirmations=signal_count,
            accountability_confirmations=crime_count,
            contradictions=0,  # TODO: implement contradiction detection
            time_consistency=True,  # TODO: implement time consistency check
            factors=factors
        )

    def _count_independent_validations(self, conn) -> int:
        """Count independent source validations."""
        # Count distinct Tier 0/1 sources
        result = conn.execute(
            "SELECT COUNT(DISTINCT source_id) as cnt FROM sources WHERE tier <= 1"
        ).fetchone()
        return result["cnt"] if result else 0

    def investment_risk_score(self, company_node_id: str) -> InvestmentRiskResult:
        """Score investment risk for a correction portfolio company.

        Args:
            company_node_id: Node ID of the company

        Returns:
            InvestmentRiskResult with 0-100 risk score (100 = highest risk)
        """
        conn = self.db.connect()
        risk_factors = []
        protection_factors = []
        score = 50  # Start at medium

        # Get company node
        company = conn.execute(
            "SELECT * FROM nodes WHERE node_id = ?", (company_node_id,)
        ).fetchone()

        if not company:
            return InvestmentRiskResult(
                score=50,
                risk_factors=[("company_not_found", 0)],
                protection_factors=[],
                scotus_impact="unknown",
                recommendation="research"
            )

        metadata = json.loads(company["metadata"]) if company["metadata"] else {}

        # RISK UP FACTORS

        # Check if company filed anti-tariff amicus
        amicus_edge = conn.execute(
            """SELECT * FROM edges
               WHERE from_node_id = ? AND edge_type = 'FILED_AMICUS'
               AND notes LIKE '%anti-tariff%'""",
            (company_node_id,)
        ).fetchone()
        if amicus_edge:
            score += 30
            risk_factors.append(("filed_anti_tariff_amicus", 30))

        # Check if BlackRock/Vanguard are top shareholders
        ownership_edges = conn.execute(
            """SELECT from_node_id FROM edges
               WHERE to_node_id = ? AND edge_type = 'OWNS_SHARES'""",
            (company_node_id,)
        ).fetchall()
        bv_owners = [e["from_node_id"] for e in ownership_edges
                     if "blackrock" in e["from_node_id"].lower()
                     or "vanguard" in e["from_node_id"].lower()]
        if bv_owners:
            score += 10
            risk_factors.append(("blackrock_vanguard_ownership", 10))

        # China trade dependency (from metadata or edges)
        if metadata.get("china_revenue_pct", 0) > 20:
            score += 20
            risk_factors.append(("china_revenue_dependency", 20))

        # Single customer concentration
        if metadata.get("single_customer_concentration", False):
            score += 10
            risk_factors.append(("customer_concentration", 10))

        # RISK DOWN FACTORS (protection)

        # Government equity stake
        gov_stake = metadata.get("government_equity_stake", 0)
        if gov_stake > 5:
            reduction = min(gov_stake * 2, 25)
            score -= reduction
            protection_factors.append(("government_equity_stake", -reduction))

        # CHIPS Act / legislative support
        chips_edge = conn.execute(
            """SELECT * FROM edges
               WHERE to_node_id = ? AND edge_type IN ('AWARDED_GRANT', 'FUNDED_PROJECT')
               AND from_node_id LIKE '%chips%'""",
            (company_node_id,)
        ).fetchone()
        if chips_edge:
            score -= 15
            protection_factors.append(("chips_act_funding", -15))

        # Physical assets (facilities built)
        facility_edges = conn.execute(
            """SELECT COUNT(*) as cnt FROM edges
               WHERE from_node_id = ? AND edge_type IN ('BUILT_IN', 'OPENED_FACILITY')""",
            (company_node_id,)
        ).fetchone()
        if facility_edges and facility_edges["cnt"] > 0:
            score -= 15
            protection_factors.append(("physical_assets_built", -15))

        # Domestic supply chain
        if metadata.get("domestic_supply_chain_pct", 0) > 80:
            score -= 10
            protection_factors.append(("domestic_supply_chain", -10))

        # Clamp score
        score = max(0, min(100, score))

        # Determine SCOTUS impact
        scotus_impact = "low"
        if any(f[0] == "filed_anti_tariff_amicus" for f in risk_factors):
            scotus_impact = "high"
        elif any(f[0] == "chips_act_funding" for f in protection_factors):
            scotus_impact = "none"  # Legislative, not executive

        # Determine recommendation
        if score < 30:
            recommendation = "buy"
        elif score < 50:
            recommendation = "hold"
        elif score < 70:
            recommendation = "reduce"
        else:
            recommendation = "avoid"

        return InvestmentRiskResult(
            score=score,
            risk_factors=risk_factors,
            protection_factors=protection_factors,
            scotus_impact=scotus_impact,
            recommendation=recommendation
        )

    def signal_convergence(self, topic: str) -> SignalConvergenceResult:
        """Score how many independent signal categories confirm a topic.

        Args:
            topic: Topic node_id or keyword

        Returns:
            SignalConvergenceResult with 0-6 score
        """
        conn = self.db.connect()
        confirmed = []
        details = {}

        # 1. Government validation (nodes with government officials)
        gov_nodes = conn.execute(
            """SELECT name FROM nodes
               WHERE (metadata LIKE '%government_official%' OR metadata LIKE '%Secretary%')
               AND (name LIKE ? OR metadata LIKE ?)""",
            (f"%{topic}%", f"%{topic}%")
        ).fetchall()
        if gov_nodes:
            confirmed.append(SignalCategory.GOVERNMENT)
            details["government"] = [n["name"] for n in gov_nodes]

        # 2. Independent media (signal_type = independent)
        media_nodes = conn.execute(
            """SELECT name FROM nodes
               WHERE metadata LIKE '%signal_type%' AND metadata LIKE '%independent%'
               AND metadata LIKE ?""",
            (f"%{topic}%",)
        ).fetchall()
        if media_nodes:
            confirmed.append(SignalCategory.INDEPENDENT_MEDIA)
            details["independent_media"] = [n["name"] for n in media_nodes]

        # 3. Academic research (sources with academic domain)
        academic_sources = conn.execute(
            """SELECT url FROM sources
               WHERE tier = 1 AND (url LIKE '%edu%' OR url LIKE '%doi.org%')
               LIMIT 10"""
        ).fetchall()
        if academic_sources:
            confirmed.append(SignalCategory.ACADEMIC)
            details["academic"] = [s["url"] for s in academic_sources[:3]]

        # 4. Market data (edges showing market signals)
        market_edges = conn.execute(
            """SELECT from_node_id, to_node_id FROM edges
               WHERE edge_type IN ('INVESTED_IN', 'INCREASED_POSITION', 'RESHORING_SIGNAL')
               LIMIT 10"""
        ).fetchall()
        if market_edges:
            confirmed.append(SignalCategory.MARKET_DATA)
            details["market_data"] = [f"{e['from_node_id']} -> {e['to_node_id']}"
                                      for e in market_edges[:3]]

        # 5. Criminal cases (crime nodes)
        crime_nodes = conn.execute(
            """SELECT name FROM nodes WHERE node_id LIKE 'crime_%' LIMIT 5"""
        ).fetchall()
        if crime_nodes:
            confirmed.append(SignalCategory.CRIMINAL_CASES)
            details["criminal_cases"] = [n["name"] for n in crime_nodes]

        # 6. Industry insiders
        insider_nodes = conn.execute(
            """SELECT name FROM nodes
               WHERE metadata LIKE '%industry_insider%' OR metadata LIKE '%insider%'"""
        ).fetchall()
        if insider_nodes:
            confirmed.append(SignalCategory.INDUSTRY_INSIDER)
            details["industry_insider"] = [n["name"] for n in insider_nodes]

        score = len(confirmed)

        # Determine confidence level
        if score >= 5:
            confidence = "extreme"
        elif score >= 3:
            confidence = "high"
        elif score >= 1:
            confidence = "medium"
        else:
            confidence = "low"

        return SignalConvergenceResult(
            score=score,
            categories_confirmed=confirmed,
            confidence_level=confidence,
            details=details
        )

    def portfolio_risk_summary(self) -> Dict[str, Any]:
        """Generate risk summary for all correction portfolio companies."""
        conn = self.db.connect()

        # Get all COMPANY nodes
        companies = conn.execute(
            """SELECT node_id, name FROM nodes
               WHERE node_type = 'COMPANY'"""
        ).fetchall()

        results = []
        for company in companies:
            risk = self.investment_risk_score(company["node_id"])
            results.append({
                "node_id": company["node_id"],
                "name": company["name"],
                "risk_score": risk.score,
                "recommendation": risk.recommendation,
                "scotus_impact": risk.scotus_impact,
            })

        # Sort by risk score
        results.sort(key=lambda x: x["risk_score"])

        return {
            "total_companies": len(results),
            "low_risk": len([r for r in results if r["risk_score"] < 40]),
            "medium_risk": len([r for r in results if 40 <= r["risk_score"] < 70]),
            "high_risk": len([r for r in results if r["risk_score"] >= 70]),
            "companies": results,
        }

    def weekly_briefing(self) -> Dict[str, Any]:
        """Generate weekly thesis update briefing."""
        conn = self.db.connect()

        # Get new sources this week
        # (simplified - in production would filter by date)
        new_sources = conn.execute(
            "SELECT COUNT(*) as cnt FROM sources"
        ).fetchone()

        # Get thesis confidence
        thesis = self.thesis_risk_score()

        # Get signal convergence on key topics
        topics = ["reshoring", "tariff", "chips", "lobbying"]
        convergence = {}
        for topic in topics:
            conv = self.signal_convergence(topic)
            convergence[topic] = {
                "score": conv.score,
                "confidence": conv.confidence_level,
            }

        # Get portfolio summary
        portfolio = self.portfolio_risk_summary()

        return {
            "thesis_confidence": thesis.score,
            "thesis_factors": thesis.factors,
            "signal_convergence": convergence,
            "portfolio_summary": {
                "total": portfolio["total_companies"],
                "low_risk": portfolio["low_risk"],
                "high_risk": portfolio["high_risk"],
            },
            "sources_in_database": new_sources["cnt"] if new_sources else 0,
            "recommendations": self._generate_recommendations(thesis, portfolio),
        }

    def _generate_recommendations(self, thesis: ThesisRiskResult, portfolio: Dict) -> List[str]:
        """Generate actionable recommendations from analysis."""
        recs = []

        if thesis.score >= 80:
            recs.append("Thesis confidence is HIGH (80+). Maintain positions.")
        elif thesis.score >= 60:
            recs.append("Thesis confidence is MEDIUM. Monitor for new signals.")
        else:
            recs.append("Thesis confidence is LOW. Additional validation needed.")

        if portfolio["high_risk"] > 0:
            recs.append(f"{portfolio['high_risk']} high-risk positions identified. Review exposure.")

        if thesis.signal_confirmations >= 5:
            recs.append("Strong signal convergence across multiple categories.")

        return recs
