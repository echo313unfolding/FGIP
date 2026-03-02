"""FGIP Allocator - Deterministic position sizing from graph evidence.

Key principles:
- Confidence scales sizing, NOT expected return
- Expected returns are labeled assumptions, not predictions
- Both-sides motif = hedge potential
- Low anomaly score = more evidence backing
- Category caps prevent high-vol sleeves from hijacking portfolio
"""

import hashlib
import json
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

from .mcp_client import mcp_call


@dataclass
class Allocation:
    """A position allocation with rationale."""
    candidate_id: str
    name: str
    category: str
    weight: float  # 0-1, fraction of portfolio
    rationale: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _sha256(obj: Any) -> str:
    """Compute SHA256 hash of JSON-serializable object."""
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def compute_evidence_score(risk_context: Dict[str, Any]) -> float:
    """
    Compute evidence score from risk context.

    Higher score = better evidence backing = larger position.

    Components:
    - Low anomaly score = good
    - Both-sides motif = hedge potential bonus
    - More edges = more validation
    - Higher confidence = better
    """
    anomaly = float(risk_context.get("anomaly_score", 0.7))
    both_sides = bool(risk_context.get("both_sides_motif", False))
    total_edges = float(risk_context.get("total_edges", 0))
    conf_stats = risk_context.get("confidence_stats", {})
    avg_confidence = float(conf_stats.get("average", 0.5))

    # Base score: inverse of anomaly (lower anomaly = higher score)
    score = 1.0 / (1.0 + anomaly)

    # Bonus for both-sides motif (hedge potential)
    if both_sides:
        score *= 1.15

    # Bonus for more edges (more validation)
    score *= (1.0 + min(total_edges, 30.0) / 100.0)

    # Bonus for higher average confidence
    score *= (0.8 + avg_confidence * 0.4)

    return score


def allocate_portfolio(
    include_mining: bool = False,
    base_expected_return: float = 0.10,
    monthly_expenses: float = 5000.0,
    current_savings: float = 50000.0,
    max_single_position: float = 0.20,
    max_category_weight: Optional[Dict[str, float]] = None,
    save_receipt: bool = True,
) -> Dict[str, Any]:
    """
    Compute portfolio allocations using FGIP graph evidence.

    Deterministic sizing based on:
    - Graph evidence quality (anomaly score, edges, confidence)
    - Both-sides motif presence
    - Category constraints (prevent high-vol hijacking)
    - Runway/leak as reality anchor

    Args:
        include_mining: Include mining pool assets
        base_expected_return: Base return assumption (labeled as assumption)
        monthly_expenses: For runway calculation
        current_savings: For runway calculation
        max_single_position: Max weight for any single position
        max_category_weight: Category caps (default: reshoring=70%, etc.)
        save_receipt: Write receipt to receipts/echo_hedge/

    Returns:
        Dict with allocations, hashes, and runway context
    """
    if max_category_weight is None:
        max_category_weight = {
            "reshoring": 0.70,
            "fixed_income": 0.60,
            "commodity": 0.30,
            "crypto": 0.10,
            "mining": 0.05,
        }

    # 1. Fetch candidates from graph
    candidates = mcp_call("get_allocation_candidates", {
        "include_mining": include_mining,
        "base_expected_return": base_expected_return,
    })
    cand_list = candidates.get("candidates", [])

    # 2. Fetch risk contexts for all candidates
    ids = [c["candidate_id"] for c in cand_list]
    risk = mcp_call("get_candidate_risk_context", {"candidate_ids": ids})
    risk_map = risk.get("risk_contexts", {})

    # 3. Fetch runway/leak as reality anchor
    runway = mcp_call("get_personal_runway", {
        "monthly_expenses": monthly_expenses,
        "current_savings": current_savings,
    })

    # 4. Score each candidate based on evidence quality
    scored = []
    for c in cand_list:
        cid = c["candidate_id"]
        rc = risk_map.get(cid, {})

        # Skip candidates with errors in risk context
        if "error" in rc:
            continue

        # Compute evidence-based score
        score = compute_evidence_score(rc)

        # Category penalties for high-vol assets
        cat = c["category"]
        if cat == "crypto":
            score *= 0.35
        elif cat == "mining":
            score *= 0.25

        scored.append((cid, score, c, rc))

    # Sort by score (highest first)
    scored.sort(key=lambda x: x[1], reverse=True)

    # 5. Convert scores to weights with caps
    total_score = sum(s for _, s, *_ in scored) or 1.0
    raw_weights = [(cid, s / total_score, c, rc) for cid, s, c, rc in scored]

    # Apply category caps and single-position cap
    cat_used: Dict[str, float] = {k: 0.0 for k in max_category_weight}
    allocations: List[Allocation] = []

    for cid, w, c, rc in raw_weights:
        cat = c["category"]
        cap_cat = max_category_weight.get(cat, 0.20)
        cap_single = max_single_position

        # Apply caps
        w = min(w, cap_single)
        remaining_cat = max(0.0, cap_cat - cat_used.get(cat, 0.0))
        w = min(w, remaining_cat)

        if w <= 0.001:  # Skip negligible allocations
            continue

        cat_used[cat] = cat_used.get(cat, 0.0) + w

        allocations.append(Allocation(
            candidate_id=cid,
            name=c["name"],
            category=cat,
            weight=round(w, 6),
            rationale={
                "evidence_score": round(compute_evidence_score(rc), 4),
                "anomaly_score": rc.get("anomaly_score"),
                "both_sides_motif": rc.get("both_sides_motif"),
                "total_edges": rc.get("total_edges"),
                "confidence_avg": (rc.get("confidence_stats") or {}).get("average"),
                "tier_distribution": rc.get("tier_distribution"),
                "risk_level": rc.get("risk_level"),
                "expected_return_is_assumption": c.get("expected_return_is_assumption", True),
            }
        ))

    # Normalize to sum to 1.0
    weight_sum = sum(a.weight for a in allocations) or 1.0
    for a in allocations:
        a.weight = round(a.weight / weight_sum, 6)

    # 6. Build output
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "inputs_hash": _sha256({
            "candidates": candidates,
            "risk": risk,
            "runway": runway,
        }),
        "parameters": {
            "include_mining": include_mining,
            "base_expected_return": base_expected_return,
            "max_single_position": max_single_position,
            "max_category_weight": max_category_weight,
        },
        "allocations": [a.to_dict() for a in allocations],
        "category_totals": {k: round(v / weight_sum, 4) for k, v in cat_used.items() if v > 0},
        "runway_anchor": {
            "leak_per_year": runway.get("runway", {}).get("real_rate_leak_per_year"),
            "inflation_adjusted_months": runway.get("runway", {}).get("inflation_adjusted_months"),
            "hidden_extraction": runway.get("real_rates", {}).get("hidden_extraction"),
        },
        "warning": "Allocations based on graph evidence quality. Expected returns are labeled assumptions, not predictions.",
    }
    output["outputs_hash"] = _sha256(output["allocations"])

    # 7. Save receipt
    if save_receipt:
        receipt_dir = Path(__file__).parent.parent / "receipts" / "echo_hedge"
        receipt_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        receipt_path = receipt_dir / f"allocation_{timestamp}.json"

        with open(receipt_path, "w") as f:
            json.dump(output, f, indent=2)

        output["receipt_path"] = str(receipt_path)

    return output


def print_allocation_report(result: Dict[str, Any]):
    """Print a human-readable allocation report."""
    print("=" * 60)
    print("  ECHO HEDGE ALLOCATION REPORT")
    print("=" * 60)
    print(f"\n  Timestamp: {result['timestamp']}")
    print(f"  Inputs Hash: {result['inputs_hash'][:16]}...")
    print(f"  Outputs Hash: {result['outputs_hash'][:16]}...")

    print("\n  ALLOCATIONS:")
    for a in result["allocations"]:
        pct = a["weight"] * 100
        rationale = a["rationale"]
        print(f"    {a['name']}: {pct:.1f}%")
        print(f"      Category: {a['category']}")
        print(f"      Evidence Score: {rationale.get('evidence_score', 'N/A')}")
        print(f"      Both-Sides Motif: {rationale.get('both_sides_motif', False)}")
        print(f"      Risk Level: {rationale.get('risk_level', 'N/A')}")
        print()

    print("  CATEGORY TOTALS:")
    for cat, total in result.get("category_totals", {}).items():
        print(f"    {cat}: {total * 100:.1f}%")

    print("\n  RUNWAY ANCHOR:")
    anchor = result.get("runway_anchor", {})
    print(f"    Leak per year: ${anchor.get('leak_per_year', 0):,.0f}")
    print(f"    Inflation-adjusted runway: {anchor.get('inflation_adjusted_months', 0):.0f} months")
    print(f"    Hidden extraction: {(anchor.get('hidden_extraction', 0) or 0) * 100:.1f}%")

    print("\n  " + result.get("warning", ""))
    print()

    if "receipt_path" in result:
        print(f"  Receipt: {result['receipt_path']}")
    print("=" * 60)


if __name__ == "__main__":
    import sys

    # Parse optional arguments
    include_mining = "--mining" in sys.argv
    save_receipt = "--no-receipt" not in sys.argv

    result = allocate_portfolio(
        include_mining=include_mining,
        save_receipt=save_receipt,
    )

    print_allocation_report(result)
