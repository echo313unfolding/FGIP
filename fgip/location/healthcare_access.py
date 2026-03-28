"""
Healthcare Access Scoring.

Scores locations based on proximity to quality hospitals.
Source: CMS Hospital Compare ratings.
"""

from typing import Dict, List
from math import radians, sin, cos, sqrt, atan2

# Major Florida hospitals with CMS ratings (1-5 stars)
# Format: (name, lat, lon, rating, level1_trauma, specialties)
FLORIDA_HOSPITALS = [
    # Central Florida
    ("AdventHealth Orlando", 28.5577, -81.3649, 4, True, ["cardiac", "neuro", "trauma"]),
    ("Orlando Regional Medical Center", 28.5240, -81.3827, 4, True, ["trauma", "burn"]),
    ("AdventHealth Ocala", 29.1614, -82.0934, 3, False, ["general"]),
    ("Ocala Regional Medical Center", 29.1784, -82.1543, 3, False, ["general", "cardiac"]),
    ("The Villages Regional Hospital", 28.8949, -81.9726, 3, False, ["general"]),
    ("Lakeland Regional Health", 28.0476, -81.9379, 4, True, ["cardiac", "trauma"]),
    ("Winter Haven Hospital", 28.0137, -81.7286, 3, False, ["general"]),
    ("AdventHealth Sebring", 27.4735, -81.4452, 2, False, ["general"]),
    ("AdventHealth Lake Placid", 27.2897, -81.3625, 2, False, ["small"]),

    # Tampa Bay
    ("Tampa General Hospital", 27.9379, -82.4565, 5, True, ["transplant", "trauma", "cardiac"]),
    ("St. Joseph's Hospital", 28.0175, -82.4618, 4, False, ["cardiac"]),
    ("Bayfront Health St. Petersburg", 27.7692, -82.6329, 3, True, ["trauma"]),

    # East Coast
    ("Cleveland Clinic Indian River", 27.6432, -80.4058, 4, False, ["cardiac"]),
    ("Lawnwood Regional Medical Center", 27.4454, -80.3522, 3, True, ["trauma"]),
    ("AdventHealth Palm Coast", 29.4714, -81.2281, 3, False, ["general"]),

    # South Florida (reference)
    ("Jackson Memorial Hospital", 25.7903, -80.2108, 4, True, ["trauma", "transplant"]),
]


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in miles."""
    R = 3959  # Earth's radius in miles

    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))

    return R * c


def get_healthcare_score(lat: float, lon: float) -> Dict:
    """
    Score healthcare access for a location.

    Args:
        lat: Latitude
        lon: Longitude

    Returns:
        dict with score (0-100), nearest_hospital, distance, rating, notes
        Higher score = better access
    """
    # Find nearest hospitals
    hospitals_with_distance = []
    for name, h_lat, h_lon, rating, trauma, specialties in FLORIDA_HOSPITALS:
        dist = haversine_distance(lat, lon, h_lat, h_lon)
        hospitals_with_distance.append({
            "name": name,
            "distance_miles": dist,
            "rating": rating,
            "level1_trauma": trauma,
            "specialties": specialties,
        })

    # Sort by distance
    hospitals_with_distance.sort(key=lambda x: x["distance_miles"])

    nearest = hospitals_with_distance[0]
    nearest_trauma = next(
        (h for h in hospitals_with_distance if h["level1_trauma"]),
        None
    )

    # Score based on distance and quality
    # < 15 miles to 4+ star: 90-100
    # < 30 miles to 3+ star: 70-89
    # < 45 miles to any: 50-69
    # > 45 miles: 0-49

    distance = nearest["distance_miles"]
    rating = nearest["rating"]

    if distance <= 15 and rating >= 4:
        score = 95
    elif distance <= 15 and rating >= 3:
        score = 85
    elif distance <= 30 and rating >= 4:
        score = 80
    elif distance <= 30 and rating >= 3:
        score = 70
    elif distance <= 45:
        score = 55
    else:
        score = max(10, 45 - (distance - 45))

    notes = []
    if rating >= 4:
        notes.append(f"Nearest hospital has {rating}-star CMS rating")
    if nearest_trauma and nearest_trauma["distance_miles"] <= 45:
        notes.append(f"Level 1 trauma center within {nearest_trauma['distance_miles']:.0f} miles")
    if distance > 30:
        notes.append("Consider proximity for emergencies")

    return {
        "score": score,
        "nearest_hospital": nearest["name"],
        "distance_miles": round(distance, 1),
        "hospital_rating": rating,
        "nearest_trauma_center": nearest_trauma["name"] if nearest_trauma else None,
        "trauma_distance_miles": round(nearest_trauma["distance_miles"], 1) if nearest_trauma else None,
        "notes": notes,
    }


def get_hospitals_near(lat: float, lon: float, radius_miles: float = 50) -> List[Dict]:
    """Get all hospitals within radius."""
    results = []
    for name, h_lat, h_lon, rating, trauma, specialties in FLORIDA_HOSPITALS:
        dist = haversine_distance(lat, lon, h_lat, h_lon)
        if dist <= radius_miles:
            results.append({
                "name": name,
                "distance_miles": round(dist, 1),
                "rating": rating,
                "level1_trauma": trauma,
                "specialties": specialties,
            })

    return sorted(results, key=lambda x: x["distance_miles"])
