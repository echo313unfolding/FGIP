"""FGIP Portfolio Scorer - Score companies by correction alignment."""

from dataclasses import dataclass, field
from typing import Optional

from fgip.db import FGIPDatabase
from fgip.schema import Node, Edge


@dataclass
class CorrectionScore:
    """Correction alignment score for a company."""
    company: Node
    total_score: float
    factors: dict = field(default_factory=dict)
    positive_signals: list[str] = field(default_factory=list)
    negative_signals: list[str] = field(default_factory=list)

    def _get_grade(self) -> str:
        """Convert score to letter grade."""
        if self.total_score >= 90:
            return "A+"
        elif self.total_score >= 80:
            return "A"
        elif self.total_score >= 70:
            return "B"
        elif self.total_score >= 60:
            return "C"
        elif self.total_score >= 50:
            return "D"
        else:
            return "F"


def calculate_correction_score(db: FGIPDatabase, company_id: str) -> CorrectionScore:
    """
    Calculate correction alignment score (0-100) for a company.

    Factors:
    - reshoring_actions (25 pts): CORRECTS edges
    - domestic_supply_chain (20 pts): US suppliers
    - no_anti_tariff_amicus (20 pts): No FILED_AMICUS against tariffs
    - us_manufacturing (20 pts): Manufacturing investment announcements
    - evidence_quality (15 pts): Tier 0/1 source coverage

    Returns CorrectionScore with breakdown.
    """
    company = db.get_node(company_id)
    if not company:
        return CorrectionScore(
            company=Node(node_id=company_id, node_type="COMPANY", name=company_id),
            total_score=0,
            factors={},
            positive_signals=["Entity not found"],
            negative_signals=[],
        )

    factors = {}
    positive_signals = []
    negative_signals = []

    # Get all edges for this company
    edges = db.list_edges(from_node_id=company_id, limit=1000)

    # 1. Reshoring actions (25 pts)
    corrects_edges = [e for e in edges if e.edge_type.value == "CORRECTS"]
    if corrects_edges:
        factors["reshoring_actions"] = min(25, len(corrects_edges) * 12.5)
        for e in corrects_edges:
            target = db.get_node(e.to_node_id)
            if target:
                positive_signals.append(f"Reshoring: {target.name}")
    else:
        factors["reshoring_actions"] = 0

    # 2. Domestic supply chain (20 pts)
    supplies_edges = [e for e in edges if e.edge_type.value == "SUPPLIES"]
    # Check if supplies to/from US companies
    domestic_supply = 0
    for e in supplies_edges:
        target = db.get_node(e.to_node_id)
        if target and "US" in str(target.metadata) or target.name.startswith("US"):
            domestic_supply += 10

    factors["domestic_supply_chain"] = min(20, domestic_supply)
    if domestic_supply > 0:
        positive_signals.append(f"Domestic supply chain links: {len(supplies_edges)}")

    # 3. No anti-tariff amicus (20 pts)
    amicus_edges = [e for e in edges if e.edge_type.value == "FILED_AMICUS"]
    anti_tariff = False
    for e in amicus_edges:
        target = db.get_node(e.to_node_id)
        if target and "tariff" in target.name.lower():
            anti_tariff = True
            negative_signals.append(f"Filed anti-tariff amicus: {target.name}")

    factors["no_anti_tariff_amicus"] = 0 if anti_tariff else 20

    # 4. US manufacturing investment (20 pts)
    # Check for CAUSED or CORRECTS edges with manufacturing events
    manufacturing_signals = 0
    for e in edges:
        if e.notes:
            if any(term in e.notes.lower() for term in ["manufacturing", "factory", "jobs", "expansion", "investment"]):
                manufacturing_signals += 10
                positive_signals.append(f"Manufacturing signal: {e.notes[:50]}")

    factors["us_manufacturing"] = min(20, manufacturing_signals)

    # 5. Evidence quality (15 pts)
    tier_01_count = 0
    for e in edges:
        if e.claim_id:
            sources = db.get_claim_sources(e.claim_id)
            if sources:
                best_tier = min(s.tier for s in sources)
                if best_tier <= 1:
                    tier_01_count += 1

    total_edges = len(edges)
    if total_edges > 0:
        evidence_pct = tier_01_count / total_edges
        factors["evidence_quality"] = evidence_pct * 15
    else:
        factors["evidence_quality"] = 0

    # Calculate total
    total_score = sum(factors.values())

    return CorrectionScore(
        company=company,
        total_score=total_score,
        factors=factors,
        positive_signals=positive_signals,
        negative_signals=negative_signals,
    )


def rank_portfolio(db: FGIPDatabase, company_ids: list[str]) -> list[CorrectionScore]:
    """Rank multiple companies by correction score."""
    scores = [calculate_correction_score(db, cid) for cid in company_ids]
    scores.sort(key=lambda s: s.total_score, reverse=True)
    return scores
