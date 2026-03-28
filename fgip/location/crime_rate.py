"""
Crime Rate Scoring.

Scores counties based on FBI UCR crime statistics.
"""

from typing import Dict

# Florida county crime data
# Based on FBI UCR and FDLE reports
# Per 100,000 residents

COUNTY_CRIME_DATA = {
    "Marion": {
        "violent_crime_rate": 485,
        "property_crime_rate": 2150,
        "total_crime_rate": 2635,
        "national_comparison": "slightly above average",
        "score": 62,
        "notes": ["Ocala metro has higher rates", "Rural areas safer"],
    },
    "Sumter": {
        "violent_crime_rate": 180,
        "property_crime_rate": 1100,
        "total_crime_rate": 1280,
        "national_comparison": "below average",
        "score": 85,
        "notes": ["Very low crime", "55+ community effect"],
    },
    "Polk": {
        "violent_crime_rate": 520,
        "property_crime_rate": 2400,
        "total_crime_rate": 2920,
        "national_comparison": "above average",
        "score": 55,
        "notes": ["Lakeland has higher rates", "Some areas vary significantly"],
    },
    "Lake": {
        "violent_crime_rate": 380,
        "property_crime_rate": 1850,
        "total_crime_rate": 2230,
        "national_comparison": "average",
        "score": 70,
        "notes": ["Moderate crime rates", "Clermont area lower"],
    },
    "Highlands": {
        "violent_crime_rate": 450,
        "property_crime_rate": 2050,
        "total_crime_rate": 2500,
        "national_comparison": "slightly above average",
        "score": 64,
        "notes": ["Rural poverty factor", "Property crime higher"],
    },
    "St. Lucie": {
        "violent_crime_rate": 540,
        "property_crime_rate": 2200,
        "total_crime_rate": 2740,
        "national_comparison": "above average",
        "score": 58,
        "notes": ["Port St. Lucie varies by neighborhood"],
    },
    "Flagler": {
        "violent_crime_rate": 320,
        "property_crime_rate": 1650,
        "total_crime_rate": 1970,
        "national_comparison": "below average",
        "score": 75,
        "notes": ["Palm Coast relatively safe", "Lower than state average"],
    },
}

DEFAULT_COUNTY = {
    "violent_crime_rate": 450,
    "property_crime_rate": 2100,
    "total_crime_rate": 2550,
    "national_comparison": "average",
    "score": 60,
    "notes": ["Estimated values"],
}

# Florida statewide average for reference
FL_STATE_AVERAGE = {
    "violent_crime_rate": 384,
    "property_crime_rate": 1948,
    "total_crime_rate": 2332,
}


def get_crime_score(county: str) -> Dict:
    """
    Get crime rate score for a county.

    Args:
        county: County name

    Returns:
        dict with score (0-100), crime rates, notes
        Higher score = lower crime = better
    """
    data = COUNTY_CRIME_DATA.get(county, DEFAULT_COUNTY)

    return {
        "score": data["score"],
        "violent_crime_rate": data["violent_crime_rate"],
        "property_crime_rate": data["property_crime_rate"],
        "total_crime_rate": data["total_crime_rate"],
        "national_comparison": data["national_comparison"],
        "vs_fl_average": {
            "violent": data["violent_crime_rate"] - FL_STATE_AVERAGE["violent_crime_rate"],
            "property": data["property_crime_rate"] - FL_STATE_AVERAGE["property_crime_rate"],
            "total": data["total_crime_rate"] - FL_STATE_AVERAGE["total_crime_rate"],
        },
        "notes": data["notes"],
    }
