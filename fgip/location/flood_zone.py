"""
FEMA Flood Zone Scoring.

Scores locations based on FEMA flood zone classification.
"""

from typing import Dict

# FEMA flood zone risk levels
# Zone X: Minimal risk (0.2% annual chance or less)
# Zone A/AE: High risk (1% annual chance)
# Zone VE: Coastal high hazard (1% + wave action)

ZONE_SCORES = {
    "X": 95,      # Minimal flood risk, no insurance required
    "X500": 85,   # 0.2% annual chance, no insurance required
    "B": 85,      # Same as X500
    "C": 95,      # Same as X
    "A": 40,      # High risk, flood insurance required
    "AE": 40,     # High risk with base flood elevation
    "AO": 35,     # Shallow flooding
    "AH": 35,     # Shallow flooding with depth
    "VE": 20,     # Coastal high hazard, very expensive
    "V": 20,      # Coastal high hazard
}

# County-level inland flood risk estimates
# Based on typical inland area zones
COUNTY_INLAND_ZONES = {
    "Marion": {"typical_zone": "X", "inland_score": 90, "notes": ["Mostly Zone X inland"]},
    "Sumter": {"typical_zone": "X", "inland_score": 92, "notes": ["Very low flood risk"]},
    "Polk": {"typical_zone": "X", "inland_score": 75, "notes": ["Some lakefront areas Zone AE"]},
    "Lake": {"typical_zone": "X", "inland_score": 78, "notes": ["Lake areas may be Zone A"]},
    "Highlands": {"typical_zone": "X", "inland_score": 88, "notes": ["Inland, minimal flood risk"]},
    "St. Lucie": {"typical_zone": "AE", "inland_score": 55, "notes": ["Even inland has some flood zones"]},
    "Flagler": {"typical_zone": "X", "inland_score": 65, "notes": ["West areas better, coastal high risk"]},
}


def get_flood_zone_score(lat: float, lon: float, county: str) -> Dict:
    """
    Get flood zone score for a location.

    In production, this would query FEMA NFHL API.
    For now, uses county-level estimates for inland areas.

    Args:
        lat: Latitude
        lon: Longitude
        county: County name

    Returns:
        dict with score (0-100), zone, requires_flood_insurance, notes
        Higher score = lower risk = better
    """
    # Get county baseline
    county_data = COUNTY_INLAND_ZONES.get(county, {
        "typical_zone": "X",
        "inland_score": 70,
        "notes": ["Limited data"],
    })

    zone = county_data["typical_zone"]
    score = county_data["inland_score"]
    requires_insurance = zone in ("A", "AE", "AO", "AH", "V", "VE")

    # Estimate flood insurance cost if required
    estimated_premium = 0
    if requires_insurance:
        if zone.startswith("V"):
            estimated_premium = 4500  # Coastal high hazard
        else:
            estimated_premium = 1800  # Standard flood

    return {
        "score": score,
        "zone": zone,
        "requires_flood_insurance": requires_insurance,
        "estimated_flood_premium": estimated_premium,
        "notes": county_data["notes"],
        "data_source": "FEMA NFHL (county estimate)",
    }


def check_specific_address(address: str) -> Dict:
    """
    Check flood zone for specific address.

    In production: query FEMA NFHL API or use msc.fema.gov.
    Returns placeholder for now.
    """
    return {
        "address": address,
        "zone": "REQUIRES_LOOKUP",
        "notes": ["Use msc.fema.gov or FEMA NFHL API for address-specific lookup"],
        "lookup_url": "https://msc.fema.gov/portal/search",
    }
