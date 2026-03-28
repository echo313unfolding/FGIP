"""
Property Tax Scoring.

Scores counties based on millage rates and homestead savings.
"""

from typing import Dict

# Florida property tax data by county
# Millage rate = tax per $1000 of assessed value
# Homestead exemption = $50K off assessed value (first $25K + additional $25K for non-school)

COUNTY_TAX_DATA = {
    "Marion": {
        "total_millage": 17.2,
        "school_millage": 7.5,
        "county_millage": 5.8,
        "city_millage_range": "2-4",
        "homestead_exemption": 50000,
        "score": 72,
        "notes": ["Mid-range millage", "Good homestead savings"],
        "example_annual_tax": 3440,  # On $200K home
    },
    "Sumter": {
        "total_millage": 14.8,
        "school_millage": 6.2,
        "county_millage": 4.1,
        "city_millage_range": "1-3",
        "homestead_exemption": 50000,
        "score": 82,
        "notes": ["Lower millage", "The Villages CDDs add fees separately"],
        "example_annual_tax": 2960,
    },
    "Polk": {
        "total_millage": 19.5,
        "school_millage": 8.1,
        "county_millage": 6.4,
        "city_millage_range": "3-5",
        "homestead_exemption": 50000,
        "score": 62,
        "notes": ["Higher millage", "Varies significantly by city"],
        "example_annual_tax": 3900,
    },
    "Lake": {
        "total_millage": 16.8,
        "school_millage": 7.2,
        "county_millage": 5.5,
        "city_millage_range": "2-4",
        "homestead_exemption": 50000,
        "score": 74,
        "notes": ["Moderate millage", "Clermont slightly higher"],
        "example_annual_tax": 3360,
    },
    "Highlands": {
        "total_millage": 18.1,
        "school_millage": 7.8,
        "county_millage": 5.9,
        "city_millage_range": "2-4",
        "homestead_exemption": 50000,
        "score": 68,
        "notes": ["Moderate-high millage", "Lower home values offset"],
        "example_annual_tax": 3620,
    },
    "St. Lucie": {
        "total_millage": 18.8,
        "school_millage": 7.9,
        "county_millage": 6.2,
        "city_millage_range": "3-5",
        "homestead_exemption": 50000,
        "score": 65,
        "notes": ["Moderate-high millage"],
        "example_annual_tax": 3760,
    },
    "Flagler": {
        "total_millage": 15.2,
        "school_millage": 6.5,
        "county_millage": 4.8,
        "city_millage_range": "2-4",
        "homestead_exemption": 50000,
        "score": 78,
        "notes": ["Lower millage", "Palm Coast has CDD fees"],
        "example_annual_tax": 3040,
    },
}

DEFAULT_COUNTY = {
    "total_millage": 17.5,
    "school_millage": 7.5,
    "county_millage": 5.5,
    "city_millage_range": "2-4",
    "homestead_exemption": 50000,
    "score": 70,
    "notes": ["Estimated values"],
    "example_annual_tax": 3500,
}


def get_property_tax_score(county: str) -> Dict:
    """
    Get property tax score for a county.

    Args:
        county: County name

    Returns:
        dict with score (0-100), millage, homestead_exemption, notes
        Higher score = lower taxes = better
    """
    data = COUNTY_TAX_DATA.get(county, DEFAULT_COUNTY)

    return {
        "score": data["score"],
        "total_millage": data["total_millage"],
        "school_millage": data["school_millage"],
        "county_millage": data["county_millage"],
        "city_millage_range": data["city_millage_range"],
        "homestead_exemption": data["homestead_exemption"],
        "example_annual_tax": data["example_annual_tax"],
        "notes": data["notes"],
    }


def estimate_annual_tax(
    home_value: float,
    county: str,
    homestead: bool = True
) -> float:
    """
    Estimate annual property tax.

    Args:
        home_value: Market value of home
        county: County name
        homestead: Whether homestead exemption applies

    Returns:
        Estimated annual tax
    """
    data = COUNTY_TAX_DATA.get(county, DEFAULT_COUNTY)

    assessed_value = home_value
    if homestead:
        assessed_value = max(0, home_value - data["homestead_exemption"])

    # Millage is per $1000
    annual_tax = (assessed_value / 1000) * data["total_millage"]

    return round(annual_tax, 0)
