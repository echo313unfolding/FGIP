"""
Florida Insurance Risk Scoring.

Scores counties based on hurricane exposure, Citizens market share,
and insurance market health.
"""

from typing import Dict, List

# Florida insurance market data by county
# Sources: Florida OIR, industry reports
# Higher Citizens share = stressed private market
# Higher hurricane exposure = higher premiums

COUNTY_INSURANCE_DATA = {
    # Inland counties (lower risk, better scores)
    "Marion": {
        "citizens_share_pct": 8.2,
        "avg_premium": 2100,
        "hurricane_exposure": "low",
        "market_health": "good",
        "score": 78,
        "notes": ["Inland location reduces hurricane exposure", "Healthy private market"],
    },
    "Sumter": {
        "citizens_share_pct": 7.5,
        "avg_premium": 1950,
        "hurricane_exposure": "low",
        "market_health": "good",
        "score": 82,
        "notes": ["Very inland", "The Villages has bulk insurance programs"],
    },
    "Polk": {
        "citizens_share_pct": 12.1,
        "avg_premium": 2400,
        "hurricane_exposure": "moderate",
        "market_health": "moderate",
        "score": 68,
        "notes": ["Central FL, some hurricane exposure", "Moderate market stress"],
    },
    "Lake": {
        "citizens_share_pct": 10.3,
        "avg_premium": 2250,
        "hurricane_exposure": "low-moderate",
        "market_health": "good",
        "score": 72,
        "notes": ["Inland but closer to Orlando metro"],
    },
    "Highlands": {
        "citizens_share_pct": 9.8,
        "avg_premium": 2000,
        "hurricane_exposure": "low",
        "market_health": "moderate",
        "score": 75,
        "notes": ["Very inland, affordable", "Smaller market, fewer options"],
    },
    "St. Lucie": {
        "citizens_share_pct": 22.5,
        "avg_premium": 3800,
        "hurricane_exposure": "high",
        "market_health": "stressed",
        "score": 45,
        "notes": ["Coastal exposure", "High Citizens dependency", "Recent claims history"],
    },
    "Flagler": {
        "citizens_share_pct": 18.2,
        "avg_premium": 3200,
        "hurricane_exposure": "moderate-high",
        "market_health": "stressed",
        "score": 52,
        "notes": ["Coastal areas have high exposure", "Inland areas better"],
    },
    # Coastal reference (for comparison)
    "Miami-Dade": {
        "citizens_share_pct": 35.0,
        "avg_premium": 6500,
        "hurricane_exposure": "very high",
        "market_health": "critical",
        "score": 25,
        "notes": ["Severe market stress", "Many insurers exited"],
    },
    "Pinellas": {
        "citizens_share_pct": 28.0,
        "avg_premium": 4800,
        "hurricane_exposure": "high",
        "market_health": "stressed",
        "score": 35,
        "notes": ["Peninsula exposure", "Flood + wind risk"],
    },
}

# Default for unknown counties
DEFAULT_COUNTY = {
    "citizens_share_pct": 15.0,
    "avg_premium": 2800,
    "hurricane_exposure": "moderate",
    "market_health": "moderate",
    "score": 60,
    "notes": ["Limited data available"],
}


def get_insurance_risk_score(county: str) -> Dict:
    """
    Get insurance risk score for a Florida county.

    Args:
        county: County name (e.g., "Marion")

    Returns:
        dict with score (0-100), citizens_share, avg_premium, notes
        Higher score = lower risk = better
    """
    data = COUNTY_INSURANCE_DATA.get(county, DEFAULT_COUNTY)

    return {
        "score": data["score"],
        "citizens_share_pct": data["citizens_share_pct"],
        "avg_premium": data["avg_premium"],
        "hurricane_exposure": data["hurricane_exposure"],
        "market_health": data["market_health"],
        "notes": data["notes"],
    }


def get_insurance_comparison(counties: List[str]) -> List[Dict]:
    """Compare insurance risk across multiple counties."""
    results = []
    for county in counties:
        data = get_insurance_risk_score(county)
        data["county"] = county
        results.append(data)

    return sorted(results, key=lambda x: x["score"], reverse=True)
