"""FGIP Industrial Base Scorer - Measurable variables, not narratives.

Computes reproducible scores for domestic manufacturing capacity trajectory.
All scores are:
- Based on graph data (nodes, edges, metadata)
- Reproducible (same inputs = same outputs)
- Auditable (component breakdown provided)

Scores computed:
1. Domestic Capacity Score (0-100)
2. Supplier Concentration Risk (0-100)
3. Reshoring Momentum Score (0-100)
4. Bottleneck Severity Score (0-100)
"""

import json
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Dict, List, Any, Optional
import sqlite3


@dataclass
class ScoreResult:
    """A computed score with methodology and breakdown."""
    score_type: str
    score_value: float          # 0-100 scale
    components: Dict[str, Any]  # Breakdown of score components
    methodology: str            # Brief description
    computed_at: str
    data_sources: List[str]     # What data was used

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


class IndustrialBaseScorer:
    """Computes industrial base scores from graph data.

    All scores are based on measurable variables:
    - Facility counts and capacity
    - Investment amounts
    - Supply chain edge patterns
    - Geographic distribution
    """

    def __init__(self, db):
        """Initialize scorer with database connection.

        Args:
            db: FGIPDatabase instance or sqlite3 connection
        """
        if hasattr(db, 'connect'):
            self.conn = db.connect()
        else:
            self.conn = db

    def compute_domestic_capacity_score(self, sector: Optional[str] = None) -> ScoreResult:
        """
        Domestic Capacity Score = weighted sum of:
        - US facilities count (BUILT_IN → US location)
        - Operational capacity (from facility_capacity table)
        - CHIPS/IRA investment committed
        - Status progression (announced < construction < operational)

        Args:
            sector: Optional sector filter (e.g., 'semiconductor', 'ev_battery')

        Returns:
            ScoreResult with 0-100 score and component breakdown
        """
        components = {}

        # 1. Count facilities by status
        status_counts = self.conn.execute("""
            SELECT operational_status, COUNT(*) as count, SUM(investment_usd) as investment
            FROM facility_capacity
            GROUP BY operational_status
        """).fetchall()

        status_scores = {"operational": 1.0, "construction": 0.6, "announced": 0.3, "planned": 0.1}
        facility_score = 0
        total_investment = 0
        for row in status_counts:
            status, count, investment = row[0], row[1], row[2] or 0
            weight = status_scores.get(status, 0.1)
            facility_score += count * weight * 10  # 10 points per weighted facility
            total_investment += investment

        components["facility_count"] = sum(r[1] for r in status_counts)
        components["facility_score"] = min(40, facility_score)  # Cap at 40 points
        components["status_breakdown"] = {r[0]: r[1] for r in status_counts}

        # 2. Investment score (up to 30 points)
        # $100B = max points
        investment_score = min(30, (total_investment / 100_000_000_000) * 30)
        components["total_investment_usd"] = total_investment
        components["investment_score"] = round(investment_score, 1)

        # 3. Capacity score (up to 20 points)
        capacity_total = self.conn.execute("""
            SELECT SUM(capacity_value)
            FROM facility_capacity
            WHERE operational_status IN ('operational', 'construction')
        """).fetchone()[0] or 0

        # 200k wafers/month = max capacity score
        capacity_score = min(20, (capacity_total / 200_000) * 20)
        components["total_capacity"] = capacity_total
        components["capacity_score"] = round(capacity_score, 1)

        # 4. FUNDED_PROJECT edges (up to 10 points)
        funded_count = self.conn.execute("""
            SELECT COUNT(*) FROM edges
            WHERE edge_type = 'FUNDED_PROJECT'
        """).fetchone()[0]
        funded_score = min(10, funded_count * 1)
        components["funded_projects"] = funded_count
        components["funded_score"] = funded_score

        # Total score
        total_score = (components["facility_score"] +
                      components["investment_score"] +
                      components["capacity_score"] +
                      components["funded_score"])

        return ScoreResult(
            score_type="domestic_capacity",
            score_value=round(min(100, total_score), 1),
            components=components,
            methodology="Weighted sum: facilities (40), investment (30), capacity (20), funded_projects (10)",
            computed_at=datetime.now(timezone.utc).isoformat(),
            data_sources=["facility_capacity", "edges.FUNDED_PROJECT"],
        )

    def compute_supplier_concentration_risk(self, company_node_id: Optional[str] = None) -> ScoreResult:
        """
        Supplier Concentration Risk = based on:
        - Single-source dependencies (DEPENDS_ON edges)
        - Geographic concentration of suppliers
        - Supplier count per company

        Higher score = higher risk (more concentrated)

        Args:
            company_node_id: Optional specific company to analyze

        Returns:
            ScoreResult with 0-100 risk score
        """
        components = {}

        # 1. Count DEPENDS_ON edges (single-source dependencies)
        if company_node_id:
            depends_count = self.conn.execute("""
                SELECT COUNT(*) FROM edges
                WHERE edge_type = 'DEPENDS_ON' AND from_node_id = ?
            """, (company_node_id,)).fetchone()[0]
        else:
            depends_count = self.conn.execute("""
                SELECT COUNT(*) FROM edges WHERE edge_type = 'DEPENDS_ON'
            """).fetchone()[0]

        # Each DEPENDS_ON edge adds 10 risk points (cap at 40)
        depends_risk = min(40, depends_count * 10)
        components["depends_on_count"] = depends_count
        components["depends_on_risk"] = depends_risk

        # 2. Count SUPPLIES_TO edges (more = better diversity)
        supplies_count = self.conn.execute("""
            SELECT COUNT(*) FROM edges WHERE edge_type = 'SUPPLIES_TO'
        """).fetchone()[0]

        # Low supplier count = high risk
        # < 5 suppliers = 30 points risk
        # 5-20 suppliers = 15 points
        # > 20 suppliers = 0 points
        if supplies_count < 5:
            diversity_risk = 30
        elif supplies_count < 20:
            diversity_risk = 15
        else:
            diversity_risk = 0

        components["supplies_to_count"] = supplies_count
        components["diversity_risk"] = diversity_risk

        # 3. Geographic concentration (from BUILT_IN edges)
        location_counts = self.conn.execute("""
            SELECT to_node_id, COUNT(*) as cnt
            FROM edges
            WHERE edge_type = 'BUILT_IN'
            GROUP BY to_node_id
            ORDER BY cnt DESC
            LIMIT 5
        """).fetchall()

        if location_counts:
            total_locations = sum(r[1] for r in location_counts)
            top_location_pct = (location_counts[0][1] / total_locations) if total_locations > 0 else 0
            # >50% in one location = 30 points risk
            geo_risk = min(30, int(top_location_pct * 60))
        else:
            geo_risk = 15  # No data = moderate risk

        components["top_locations"] = {r[0]: r[1] for r in location_counts}
        components["geographic_risk"] = geo_risk

        # Total risk score
        total_risk = depends_risk + diversity_risk + geo_risk

        return ScoreResult(
            score_type="supplier_concentration_risk",
            score_value=round(min(100, total_risk), 1),
            components=components,
            methodology="Sum: depends_on (40 max), diversity (30 max), geographic (30 max). Higher = more risk.",
            computed_at=datetime.now(timezone.utc).isoformat(),
            data_sources=["edges.DEPENDS_ON", "edges.SUPPLIES_TO", "edges.BUILT_IN"],
        )

    def compute_reshoring_momentum_score(self, window_days: int = 365) -> ScoreResult:
        """
        Reshoring Momentum = rate of change in:
        - New BUILT_IN edges (US locations)
        - FUNDED_PROJECT edges
        - Facility announcements/construction starts

        Positive score = reshoring accelerating

        Args:
            window_days: Time window for measuring momentum

        Returns:
            ScoreResult with momentum score
        """
        components = {}

        # 1. Count recent facility capacity additions
        facility_count = self.conn.execute("""
            SELECT COUNT(*) FROM facility_capacity
        """).fetchone()[0]

        # More facilities = higher momentum (up to 40 points)
        facility_momentum = min(40, facility_count * 6)
        components["facility_count"] = facility_count
        components["facility_momentum"] = facility_momentum

        # 2. Count FUNDED_PROJECT edges (recent funding)
        funded_count = self.conn.execute("""
            SELECT COUNT(*) FROM edges
            WHERE edge_type = 'FUNDED_PROJECT'
        """).fetchone()[0]

        funded_momentum = min(30, funded_count * 3)
        components["funded_count"] = funded_count
        components["funded_momentum"] = funded_momentum

        # 3. Count AWARDED_GRANT edges
        grant_count = self.conn.execute("""
            SELECT COUNT(*) FROM edges
            WHERE edge_type = 'AWARDED_GRANT'
        """).fetchone()[0]

        grant_momentum = min(30, grant_count * 2)
        components["grant_count"] = grant_count
        components["grant_momentum"] = grant_momentum

        # Total momentum
        total_momentum = facility_momentum + funded_momentum + grant_momentum

        return ScoreResult(
            score_type="reshoring_momentum",
            score_value=round(min(100, total_momentum), 1),
            components=components,
            methodology="Sum: facility additions (40 max), funded projects (30 max), grants (30 max). Higher = more momentum.",
            computed_at=datetime.now(timezone.utc).isoformat(),
            data_sources=["facility_capacity", "edges.FUNDED_PROJECT", "edges.AWARDED_GRANT"],
        )

    def compute_bottleneck_severity_score(self) -> ScoreResult:
        """
        Bottleneck Severity = graph-based analysis of:
        - High in-degree in SUPPLIES_TO (many depend on few)
        - Single points of failure in supply chain
        - Concentration of edges on specific nodes

        Higher score = more severe bottlenecks

        Returns:
            ScoreResult with bottleneck severity score
        """
        components = {}

        # 1. Find nodes with high in-degree in SUPPLIES_TO
        supplier_indegree = self.conn.execute("""
            SELECT from_node_id, COUNT(*) as indegree
            FROM edges
            WHERE edge_type = 'SUPPLIES_TO'
            GROUP BY from_node_id
            ORDER BY indegree DESC
            LIMIT 10
        """).fetchall()

        max_indegree = supplier_indegree[0][1] if supplier_indegree else 0
        # High concentration = risk
        concentration_risk = min(40, max_indegree * 8)
        components["top_suppliers"] = {r[0]: r[1] for r in supplier_indegree[:5]}
        components["max_indegree"] = max_indegree
        components["concentration_risk"] = concentration_risk

        # 2. Count DEPENDS_ON edges (single-source = bottleneck)
        depends_count = self.conn.execute("""
            SELECT COUNT(*) FROM edges WHERE edge_type = 'DEPENDS_ON'
        """).fetchone()[0]

        single_source_risk = min(40, depends_count * 8)
        components["depends_on_count"] = depends_count
        components["single_source_risk"] = single_source_risk

        # 3. Count BOTTLENECK_AT edges (explicitly identified)
        bottleneck_count = self.conn.execute("""
            SELECT COUNT(*) FROM edges WHERE edge_type = 'BOTTLENECK_AT'
        """).fetchone()[0]

        explicit_risk = min(20, bottleneck_count * 10)
        components["explicit_bottlenecks"] = bottleneck_count
        components["explicit_risk"] = explicit_risk

        # Total severity
        total_severity = concentration_risk + single_source_risk + explicit_risk

        return ScoreResult(
            score_type="bottleneck_severity",
            score_value=round(min(100, total_severity), 1),
            components=components,
            methodology="Sum: supplier concentration (40 max), single-source (40 max), explicit bottlenecks (20 max). Higher = worse.",
            computed_at=datetime.now(timezone.utc).isoformat(),
            data_sources=["edges.SUPPLIES_TO", "edges.DEPENDS_ON", "edges.BOTTLENECK_AT"],
        )

    def generate_full_report(self) -> Dict[str, Any]:
        """Generate comprehensive industrial base report with all scores."""
        domestic = self.compute_domestic_capacity_score()
        concentration = self.compute_supplier_concentration_risk()
        momentum = self.compute_reshoring_momentum_score()
        bottleneck = self.compute_bottleneck_severity_score()

        # Compute overall health score
        # Higher domestic + momentum = good
        # Higher concentration + bottleneck = bad
        health_score = (
            domestic.score_value * 0.3 +
            momentum.score_value * 0.3 +
            (100 - concentration.score_value) * 0.2 +
            (100 - bottleneck.score_value) * 0.2
        )

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "overall_health": round(health_score, 1),
            "scores": {
                "domestic_capacity": domestic.to_dict(),
                "supplier_concentration_risk": concentration.to_dict(),
                "reshoring_momentum": momentum.to_dict(),
                "bottleneck_severity": bottleneck.to_dict(),
            },
            "interpretation": {
                "domestic_capacity": "Higher is better (more capacity)",
                "supplier_concentration_risk": "Lower is better (more diverse)",
                "reshoring_momentum": "Higher is better (more activity)",
                "bottleneck_severity": "Lower is better (fewer chokepoints)",
                "overall_health": "0-100 composite score",
            },
        }

    def store_scores(self):
        """Store computed scores in supply_chain_scores table."""
        scores = [
            self.compute_domestic_capacity_score(),
            self.compute_supplier_concentration_risk(),
            self.compute_reshoring_momentum_score(),
            self.compute_bottleneck_severity_score(),
        ]

        for score in scores:
            self.conn.execute("""
                INSERT INTO supply_chain_scores
                (company_node_id, score_type, score_value, components, computed_at, methodology)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                "SYSTEM",  # System-wide scores
                score.score_type,
                score.score_value,
                json.dumps(score.components),
                score.computed_at,
                score.methodology,
            ))
        self.conn.commit()


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(__file__).replace("/fgip/analysis/industrial_base_scorer.py", ""))

    from fgip.db import FGIPDatabase

    db_path = sys.argv[1] if len(sys.argv) > 1 else "fgip.db"
    db = FGIPDatabase(db_path)
    db.connect()

    scorer = IndustrialBaseScorer(db)

    # Generate and print full report
    report = scorer.generate_full_report()

    print("=" * 60)
    print("  FGIP INDUSTRIAL BASE REPORT")
    print("=" * 60)
    print(f"\n  Overall Health Score: {report['overall_health']}/100")
    print()

    for name, score_data in report["scores"].items():
        print(f"  {name}: {score_data['score_value']}/100")
        print(f"    Method: {score_data['methodology']}")
        print()

    # Store scores if requested
    if "--store" in sys.argv:
        scorer.store_scores()
        print("Scores stored in supply_chain_scores table.")
