"""
HOA Health Scoring.

Scores counties based on HOA reserve requirements, litigation, and assessment history.
Post-Surfside (SB 4-D) requirements have tightened reserve/inspection rules.
"""

from typing import Dict

# HOA health indicators by county
# Based on industry data and FL SB 4-D compliance

COUNTY_HOA_DATA = {
    "Marion": {
        "avg_hoa_fee": 250,
        "avg_condo_hoa_fee": 350,
        "special_assessment_rate": "low",
        "litigation_rate": "low",
        "sb4d_compliance": "moderate",
        "building_age_mix": "newer",
        "score": 75,
        "notes": ["Fewer condos, more single-family HOAs", "Lower assessment risk"],
    },
    "Sumter": {
        "avg_hoa_fee": 450,
        "avg_condo_hoa_fee": 500,
        "special_assessment_rate": "low",
        "litigation_rate": "very low",
        "sb4d_compliance": "high",
        "building_age_mix": "newer",
        "score": 80,
        "notes": ["Villages CDDs well-managed", "Bulk purchasing reduces costs"],
    },
    "Polk": {
        "avg_hoa_fee": 200,
        "avg_condo_hoa_fee": 300,
        "special_assessment_rate": "moderate",
        "litigation_rate": "low",
        "sb4d_compliance": "moderate",
        "building_age_mix": "mixed",
        "score": 70,
        "notes": ["Mix of older and newer communities", "Some underfunded HOAs"],
    },
    "Lake": {
        "avg_hoa_fee": 275,
        "avg_condo_hoa_fee": 375,
        "special_assessment_rate": "low",
        "litigation_rate": "low",
        "sb4d_compliance": "moderate",
        "building_age_mix": "newer",
        "score": 72,
        "notes": ["Growing area, newer HOAs", "Check individual community reserves"],
    },
    "Highlands": {
        "avg_hoa_fee": 180,
        "avg_condo_hoa_fee": 280,
        "special_assessment_rate": "moderate",
        "litigation_rate": "low",
        "sb4d_compliance": "moderate",
        "building_age_mix": "older",
        "score": 65,
        "notes": ["Some older communities", "Lower fees but watch reserves"],
    },
    "St. Lucie": {
        "avg_hoa_fee": 300,
        "avg_condo_hoa_fee": 450,
        "special_assessment_rate": "moderate",
        "litigation_rate": "moderate",
        "sb4d_compliance": "moderate",
        "building_age_mix": "mixed",
        "score": 60,
        "notes": ["Some coastal buildings need SB 4-D work", "Assessments possible"],
    },
    "Flagler": {
        "avg_hoa_fee": 325,
        "avg_condo_hoa_fee": 425,
        "special_assessment_rate": "moderate",
        "litigation_rate": "low",
        "sb4d_compliance": "moderate",
        "building_age_mix": "mixed",
        "score": 68,
        "notes": ["Palm Coast CDDs add fees", "Check individual HOA reserves"],
    },
    # Coastal comparison (for reference - why inland is better)
    "Miami-Dade": {
        "avg_hoa_fee": 550,
        "avg_condo_hoa_fee": 750,
        "special_assessment_rate": "high",
        "litigation_rate": "high",
        "sb4d_compliance": "mixed",
        "building_age_mix": "older",
        "score": 35,
        "notes": ["High assessment risk", "Surfside effect", "Many buildings need work"],
    },
}

DEFAULT_COUNTY = {
    "avg_hoa_fee": 300,
    "avg_condo_hoa_fee": 400,
    "special_assessment_rate": "moderate",
    "litigation_rate": "low",
    "sb4d_compliance": "moderate",
    "building_age_mix": "mixed",
    "score": 65,
    "notes": ["Limited data available"],
}


def get_hoa_health_score(county: str) -> Dict:
    """
    Get HOA health score for a county.

    Args:
        county: County name

    Returns:
        dict with score (0-100), fees, assessment risk, notes
        Higher score = healthier HOAs = better
    """
    data = COUNTY_HOA_DATA.get(county, DEFAULT_COUNTY)

    return {
        "score": data["score"],
        "avg_hoa_fee": data["avg_hoa_fee"],
        "avg_condo_hoa_fee": data["avg_condo_hoa_fee"],
        "special_assessment_rate": data["special_assessment_rate"],
        "litigation_rate": data["litigation_rate"],
        "sb4d_compliance": data["sb4d_compliance"],
        "building_age_mix": data["building_age_mix"],
        "notes": data["notes"],
    }


def get_hoa_due_diligence_checklist() -> list:
    """Return due diligence checklist for evaluating specific HOAs."""
    return [
        "Request last 3 years of HOA meeting minutes",
        "Get reserve study (required for condos 3+ stories post-SB 4-D)",
        "Ask about special assessments in last 5 years",
        "Check for pending litigation (ask for disclosure)",
        "Review SB 4-D structural inspection status (if applicable)",
        "Ask about insurance coverage and recent premium changes",
        "Review budget for reserve funding percentage (30%+ is healthy)",
        "Ask if building has had SIRS (Structural Integrity Reserve Study)",
    ]
