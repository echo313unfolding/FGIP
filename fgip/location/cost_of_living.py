"""
Cost of Living Scoring.

Scores counties based on regional cost of living indices.
"""

from typing import Dict

# Florida county cost of living data
# 100 = national average
# Based on BLS and regional cost comparisons

COUNTY_COL_DATA = {
    "Marion": {
        "col_index": 91,
        "housing_index": 78,
        "utilities_index": 98,
        "groceries_index": 95,
        "healthcare_index": 94,
        "transportation_index": 92,
        "score": 78,
        "notes": ["Below average COL", "Housing very affordable"],
    },
    "Sumter": {
        "col_index": 95,
        "housing_index": 92,
        "utilities_index": 97,
        "groceries_index": 96,
        "healthcare_index": 95,
        "transportation_index": 94,
        "score": 72,
        "notes": ["Slightly below average", "Villages amenity fees add cost"],
    },
    "Polk": {
        "col_index": 93,
        "housing_index": 82,
        "utilities_index": 99,
        "groceries_index": 96,
        "healthcare_index": 96,
        "transportation_index": 95,
        "score": 75,
        "notes": ["Below average COL", "Housing affordable"],
    },
    "Lake": {
        "col_index": 97,
        "housing_index": 95,
        "utilities_index": 98,
        "groceries_index": 97,
        "healthcare_index": 95,
        "transportation_index": 96,
        "score": 68,
        "notes": ["Near average", "Orlando proximity raises prices"],
    },
    "Highlands": {
        "col_index": 88,
        "housing_index": 72,
        "utilities_index": 96,
        "groceries_index": 94,
        "healthcare_index": 92,
        "transportation_index": 90,
        "score": 82,
        "notes": ["Well below average COL", "Very affordable"],
    },
    "St. Lucie": {
        "col_index": 99,
        "housing_index": 98,
        "utilities_index": 100,
        "groceries_index": 98,
        "healthcare_index": 97,
        "transportation_index": 98,
        "score": 62,
        "notes": ["Near average", "Coastal premium"],
    },
    "Flagler": {
        "col_index": 96,
        "housing_index": 90,
        "utilities_index": 99,
        "groceries_index": 97,
        "healthcare_index": 96,
        "transportation_index": 97,
        "score": 70,
        "notes": ["Slightly below average", "Growing area"],
    },
    # Reference: expensive areas
    "Miami-Dade": {
        "col_index": 118,
        "housing_index": 145,
        "utilities_index": 102,
        "groceries_index": 108,
        "healthcare_index": 105,
        "transportation_index": 110,
        "score": 35,
        "notes": ["Well above average", "Housing very expensive"],
    },
}

DEFAULT_COUNTY = {
    "col_index": 95,
    "housing_index": 90,
    "utilities_index": 98,
    "groceries_index": 96,
    "healthcare_index": 95,
    "transportation_index": 95,
    "score": 70,
    "notes": ["Estimated values"],
}


def get_col_score(county: str) -> Dict:
    """
    Get cost of living score for a county.

    Args:
        county: County name

    Returns:
        dict with score (0-100), indices, notes
        Higher score = lower COL = better
    """
    data = COUNTY_COL_DATA.get(county, DEFAULT_COUNTY)

    return {
        "score": data["score"],
        "col_index": data["col_index"],
        "housing_index": data["housing_index"],
        "utilities_index": data["utilities_index"],
        "groceries_index": data["groceries_index"],
        "healthcare_index": data["healthcare_index"],
        "transportation_index": data["transportation_index"],
        "notes": data["notes"],
        "vs_national_avg": data["col_index"] - 100,
    }


def estimate_monthly_costs(county: str, base_monthly: float = 3000) -> Dict:
    """
    Estimate adjusted monthly costs based on COL.

    Args:
        county: County name
        base_monthly: Base monthly expenses at national average

    Returns:
        Adjusted monthly cost estimate
    """
    data = COUNTY_COL_DATA.get(county, DEFAULT_COUNTY)

    adjusted = base_monthly * (data["col_index"] / 100)

    return {
        "county": county,
        "base_monthly": base_monthly,
        "adjusted_monthly": round(adjusted, 0),
        "col_index": data["col_index"],
        "monthly_savings_vs_national": round(base_monthly - adjusted, 0),
    }
