"""
Florida Location Scorer - Core scoring engine.

Scores and ranks Florida areas on hidden costs, risks, and quality of life.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json


@dataclass
class AreaDefinition:
    """Definition of a scorable Florida area."""
    area_id: str           # e.g., "ocala"
    area_name: str         # e.g., "Ocala"
    county: str            # e.g., "Marion"
    lat: float             # Center latitude
    lon: float             # Center longitude
    description: str = ""  # Why this area is being considered
    is_55_plus: bool = False
    has_gated_options: bool = False


@dataclass
class ComponentScore:
    """Score for a single component with provenance."""
    factor: str            # e.g., "flood_zone"
    score: float           # 0-100
    weight: float          # Weight applied
    weighted_score: float  # score * weight
    data: dict             # Raw data that produced score
    source: str            # Data source
    notes: List[str] = field(default_factory=list)


@dataclass
class LocationScore:
    """Complete score for a Florida area."""
    area_id: str
    area_name: str
    county: str
    overall_score: float   # 0-100 weighted
    component_scores: Dict[str, ComponentScore]
    red_flags: List[str]
    data_sources: List[str]
    scored_at: str = ""

    def __post_init__(self):
        if not self.scored_at:
            self.scored_at = datetime.now(timezone.utc).isoformat()

    def has_red_flags(self) -> bool:
        return len(self.red_flags) > 0

    def to_dict(self) -> dict:
        return {
            "area_id": self.area_id,
            "area_name": self.area_name,
            "county": self.county,
            "overall_score": round(self.overall_score, 1),
            "component_scores": {
                k: {
                    "factor": v.factor,
                    "score": round(v.score, 1),
                    "weight": v.weight,
                    "weighted_score": round(v.weighted_score, 2),
                    "data": v.data,
                    "source": v.source,
                    "notes": v.notes,
                }
                for k, v in self.component_scores.items()
            },
            "red_flags": self.red_flags,
            "data_sources": self.data_sources,
            "scored_at": self.scored_at,
        }


@dataclass
class ScoringWeights:
    """Configurable weights for scoring factors."""
    insurance_risk: float = 0.20    # Hurricane/insurance exposure
    flood_zone: float = 0.20        # FEMA flood zone risk
    hoa_health: float = 0.15        # HOA reserve/litigation
    healthcare_access: float = 0.15 # Hospital quality/distance
    property_tax: float = 0.10      # Millage rates
    cost_of_living: float = 0.10    # Regional COL
    crime_rate: float = 0.10        # Safety

    def validate(self) -> bool:
        """Verify weights sum to 1.0."""
        total = (
            self.insurance_risk +
            self.flood_zone +
            self.hoa_health +
            self.healthcare_access +
            self.property_tax +
            self.cost_of_living +
            self.crime_rate
        )
        return abs(total - 1.0) < 0.01

    def to_dict(self) -> dict:
        return {
            "insurance_risk": self.insurance_risk,
            "flood_zone": self.flood_zone,
            "hoa_health": self.hoa_health,
            "healthcare_access": self.healthcare_access,
            "property_tax": self.property_tax,
            "cost_of_living": self.cost_of_living,
            "crime_rate": self.crime_rate,
        }


# Target areas for Mom's requirements:
# - Inland preferred (lower insurance/flood risk)
# - Gated/private community options
# - $200K-$300K budget
# - Healthcare within 45 min

TARGET_AREAS = [
    AreaDefinition(
        area_id="ocala",
        area_name="Ocala",
        county="Marion",
        lat=29.1872,
        lon=-82.1401,
        description="Inland, affordable, growing - horse country",
        has_gated_options=True,
    ),
    AreaDefinition(
        area_id="the-villages",
        area_name="The Villages",
        county="Sumter",
        lat=28.9005,
        lon=-81.9878,
        description="Massive 55+ community, inland, very social",
        is_55_plus=True,
        has_gated_options=True,
    ),
    AreaDefinition(
        area_id="lakeland",
        area_name="Lakeland",
        county="Polk",
        lat=28.0395,
        lon=-81.9498,
        description="Central FL, affordable, Tampa access",
        has_gated_options=True,
    ),
    AreaDefinition(
        area_id="clermont",
        area_name="Clermont",
        county="Lake",
        lat=28.5494,
        lon=-81.7729,
        description="Orlando access, hilly, inland",
        has_gated_options=True,
    ),
    AreaDefinition(
        area_id="winter-haven",
        area_name="Winter Haven",
        county="Polk",
        lat=28.0222,
        lon=-81.7329,
        description="Chain of lakes, affordable, quiet",
        has_gated_options=True,
    ),
    AreaDefinition(
        area_id="sebring",
        area_name="Sebring",
        county="Highlands",
        lat=27.4953,
        lon=-81.4409,
        description="Very affordable, inland, quieter",
        has_gated_options=True,
    ),
    AreaDefinition(
        area_id="port-st-lucie-west",
        area_name="Port St. Lucie (West)",
        county="St. Lucie",
        lat=27.2939,
        lon=-80.3900,
        description="Growing, some inland gated options",
        has_gated_options=True,
    ),
    AreaDefinition(
        area_id="palm-coast-west",
        area_name="Palm Coast (West)",
        county="Flagler",
        lat=29.5844,
        lon=-81.2419,
        description="Some inland areas, planned community",
        has_gated_options=True,
    ),
]


class FloridaLocationScorer:
    """Main scoring engine for Florida locations."""

    def __init__(self, weights: Optional[ScoringWeights] = None):
        self.weights = weights or ScoringWeights()
        if not self.weights.validate():
            raise ValueError("Scoring weights must sum to 1.0")
        self.areas = {a.area_id: a for a in TARGET_AREAS}

    def score_area(self, area_id: str) -> LocationScore:
        """Score a single area on all factors."""
        if area_id not in self.areas:
            raise ValueError(f"Unknown area: {area_id}")

        area = self.areas[area_id]
        components = {}
        red_flags = []
        data_sources = []

        # Score each component
        from .insurance_risk import get_insurance_risk_score
        from .flood_zone import get_flood_zone_score
        from .healthcare_access import get_healthcare_score
        from .property_tax import get_property_tax_score
        from .crime_rate import get_crime_score
        from .hoa_health import get_hoa_health_score
        from .cost_of_living import get_col_score

        # Insurance risk
        ins = get_insurance_risk_score(area.county)
        components["insurance_risk"] = ComponentScore(
            factor="insurance_risk",
            score=ins["score"],
            weight=self.weights.insurance_risk,
            weighted_score=ins["score"] * self.weights.insurance_risk,
            data=ins,
            source="Florida OIR / industry data",
            notes=ins.get("notes", []),
        )
        if ins["score"] < 50:
            red_flags.append(f"High insurance risk in {area.county} County")
        data_sources.append("Florida OIR")

        # Flood zone
        flood = get_flood_zone_score(area.lat, area.lon, area.county)
        components["flood_zone"] = ComponentScore(
            factor="flood_zone",
            score=flood["score"],
            weight=self.weights.flood_zone,
            weighted_score=flood["score"] * self.weights.flood_zone,
            data=flood,
            source="FEMA NFHL",
            notes=flood.get("notes", []),
        )
        if flood["requires_flood_insurance"]:
            red_flags.append(f"Flood insurance required (Zone {flood['zone']})")
        data_sources.append("FEMA NFHL")

        # HOA health
        hoa = get_hoa_health_score(area.county)
        components["hoa_health"] = ComponentScore(
            factor="hoa_health",
            score=hoa["score"],
            weight=self.weights.hoa_health,
            weighted_score=hoa["score"] * self.weights.hoa_health,
            data=hoa,
            source="FL SB 4-D / county records",
            notes=hoa.get("notes", []),
        )
        data_sources.append("FL county records")

        # Healthcare access
        health = get_healthcare_score(area.lat, area.lon)
        components["healthcare_access"] = ComponentScore(
            factor="healthcare_access",
            score=health["score"],
            weight=self.weights.healthcare_access,
            weighted_score=health["score"] * self.weights.healthcare_access,
            data=health,
            source="CMS Hospital Compare",
            notes=health.get("notes", []),
        )
        if health["distance_miles"] > 45:
            red_flags.append(f"Healthcare too far: {health['distance_miles']:.0f} miles to nearest hospital")
        data_sources.append("CMS Hospital Compare")

        # Property tax
        tax = get_property_tax_score(area.county)
        components["property_tax"] = ComponentScore(
            factor="property_tax",
            score=tax["score"],
            weight=self.weights.property_tax,
            weighted_score=tax["score"] * self.weights.property_tax,
            data=tax,
            source="County assessor",
            notes=tax.get("notes", []),
        )
        data_sources.append(f"{area.county} County Assessor")

        # Crime rate
        crime = get_crime_score(area.county)
        components["crime_rate"] = ComponentScore(
            factor="crime_rate",
            score=crime["score"],
            weight=self.weights.crime_rate,
            weighted_score=crime["score"] * self.weights.crime_rate,
            data=crime,
            source="FBI UCR",
            notes=crime.get("notes", []),
        )
        if crime["score"] < 40:
            red_flags.append(f"Crime rate concern in {area.county} County")
        data_sources.append("FBI UCR")

        # Cost of living
        col = get_col_score(area.county)
        components["cost_of_living"] = ComponentScore(
            factor="cost_of_living",
            score=col["score"],
            weight=self.weights.cost_of_living,
            weighted_score=col["score"] * self.weights.cost_of_living,
            data=col,
            source="BLS / regional data",
            notes=col.get("notes", []),
        )
        data_sources.append("BLS")

        # Compute overall score
        overall = sum(c.weighted_score for c in components.values())

        return LocationScore(
            area_id=area.area_id,
            area_name=area.area_name,
            county=area.county,
            overall_score=overall,
            component_scores=components,
            red_flags=red_flags,
            data_sources=list(set(data_sources)),
        )

    def score_all_areas(self) -> List[LocationScore]:
        """Score all target areas and return sorted by overall score."""
        scores = [self.score_area(area_id) for area_id in self.areas.keys()]
        return sorted(scores, key=lambda s: s.overall_score, reverse=True)

    def get_shortlist(self, top_n: int = 5, exclude_red_flags: bool = False) -> List[LocationScore]:
        """Get top N areas, optionally excluding those with red flags."""
        scores = self.score_all_areas()

        if exclude_red_flags:
            scores = [s for s in scores if not s.has_red_flags()]

        return scores[:top_n]

    def generate_report(self, scores: Optional[List[LocationScore]] = None) -> str:
        """Generate human-readable report."""
        if scores is None:
            scores = self.score_all_areas()

        lines = [
            "# Florida Location Scores",
            "",
            f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
            f"**Areas Scored:** {len(scores)}",
            "",
            "---",
            "",
            "## Rankings",
            "",
            "| Rank | Area | County | Score | Red Flags |",
            "|------|------|--------|-------|-----------|",
        ]

        for i, score in enumerate(scores, 1):
            flags = len(score.red_flags)
            flag_str = f"{flags} flags" if flags else "None"
            lines.append(
                f"| {i} | {score.area_name} | {score.county} | "
                f"{score.overall_score:.1f} | {flag_str} |"
            )

        lines.extend([
            "",
            "---",
            "",
            "## Detailed Scores",
            "",
        ])

        for score in scores:
            lines.extend([
                f"### {score.area_name} ({score.county} County)",
                "",
                f"**Overall Score:** {score.overall_score:.1f}/100",
                "",
            ])

            if score.red_flags:
                lines.append("**Red Flags:**")
                for flag in score.red_flags:
                    lines.append(f"- {flag}")
                lines.append("")

            lines.append("**Component Scores:**")
            lines.append("")
            lines.append("| Factor | Score | Weight | Weighted |")
            lines.append("|--------|-------|--------|----------|")

            for comp in score.component_scores.values():
                lines.append(
                    f"| {comp.factor.replace('_', ' ').title()} | "
                    f"{comp.score:.1f} | {comp.weight:.0%} | {comp.weighted_score:.1f} |"
                )

            lines.extend(["", "---", ""])

        lines.extend([
            "",
            "## Scoring Weights Used",
            "",
        ])
        for factor, weight in self.weights.to_dict().items():
            lines.append(f"- {factor.replace('_', ' ').title()}: {weight:.0%}")

        lines.extend([
            "",
            "---",
            "",
            "*Generated by FGIP Location Scorer*",
        ])

        return "\n".join(lines)

    def write_results(
        self,
        output_dir: str = "receipts/location",
        scores: Optional[List[LocationScore]] = None,
    ) -> Tuple[str, str, str]:
        """Write scoring results to files."""
        if scores is None:
            scores = self.score_all_areas()

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = Path(output_dir) / f"score-run-{ts}"
        out_path.mkdir(parents=True, exist_ok=True)

        # Write JSON scores
        json_path = out_path / "LOCATION_SCORES.json"
        with json_path.open("w") as f:
            json.dump({
                "score_run_id": f"score-run-{ts}",
                "scored_at": datetime.now(timezone.utc).isoformat(),
                "weights": self.weights.to_dict(),
                "scores": [s.to_dict() for s in scores],
            }, f, indent=2)

        # Write markdown report
        md_path = out_path / "LOCATION_REPORT.md"
        md_path.write_text(self.generate_report(scores))

        # Write red flags summary
        flags_path = out_path / "RED_FLAGS.json"
        red_flag_areas = [s for s in scores if s.has_red_flags()]
        with flags_path.open("w") as f:
            json.dump({
                "areas_with_red_flags": len(red_flag_areas),
                "details": [
                    {"area": s.area_name, "county": s.county, "flags": s.red_flags}
                    for s in red_flag_areas
                ],
            }, f, indent=2)

        # Write shortlist
        shortlist_path = out_path / "TOP_5_SHORTLIST.md"
        shortlist = self.get_shortlist(5, exclude_red_flags=False)
        shortlist_md = self._generate_shortlist_md(shortlist)
        shortlist_path.write_text(shortlist_md)

        return str(json_path), str(md_path), str(shortlist_path)

    def _generate_shortlist_md(self, shortlist: List[LocationScore]) -> str:
        """Generate focused shortlist markdown."""
        lines = [
            "# Top 5 Florida Locations for Mom",
            "",
            f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
            "",
            "---",
            "",
        ]

        for i, score in enumerate(shortlist, 1):
            area = self.areas[score.area_id]
            lines.extend([
                f"## #{i}: {score.area_name}",
                "",
                f"**County:** {score.county}",
                f"**Score:** {score.overall_score:.1f}/100",
                f"**Description:** {area.description}",
                "",
            ])

            if area.has_gated_options:
                lines.append("- Has gated community options")
            if area.is_55_plus:
                lines.append("- 55+ community")

            lines.append("")

            if score.red_flags:
                lines.append("**Concerns:**")
                for flag in score.red_flags:
                    lines.append(f"- {flag}")
            else:
                lines.append("**Concerns:** None identified")

            # Key metrics
            lines.extend([
                "",
                "**Key Metrics:**",
            ])
            for key_factor in ["insurance_risk", "flood_zone", "healthcare_access"]:
                if key_factor in score.component_scores:
                    comp = score.component_scores[key_factor]
                    lines.append(f"- {comp.factor.replace('_', ' ').title()}: {comp.score:.0f}/100")

            lines.extend(["", "---", ""])

        lines.append("*Review full report for detailed component scores.*")
        return "\n".join(lines)
