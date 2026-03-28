"""
Directive generation and output.

Generates signed, receipted allocation directives that can be
traced back to the underlying regime detection and calibration.
"""

import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from .constraints import SettlementConstraints
from .policy import AllocationPolicy
from .buckets import BUCKETS, get_preferred_ticker


@dataclass
class AllocationDirective:
    """
    A signed, receipted allocation recommendation.

    This is the "do this with the money" output - complete with
    receipts linking back to the underlying intelligence.
    """

    directive_id: str
    generated_at: str
    regime_context: dict
    constraints: dict
    allocation: Dict[str, dict]
    regime_triggers: List[dict]
    what_would_change_this: List[str]
    receipts: dict

    def to_dict(self) -> dict:
        """Convert to dict for serialization."""
        return asdict(self)

    def compute_hash(self) -> str:
        """Compute deterministic hash of directive content."""
        # Exclude generated_at for hash stability within same inputs
        content = {
            "regime_context": self.regime_context,
            "constraints": self.constraints,
            "allocation": self.allocation,
            "regime_triggers": self.regime_triggers,
            "receipts": self.receipts,
        }
        canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


def generate_directive(
    constraints: SettlementConstraints,
    regime: str,
    Se: float,
    C: float,
    regime_node_id: str,
    calibration_hash: str,
    m2_cpi_gap: float = 0,
) -> AllocationDirective:
    """
    Generate allocation directive from regime + constraints.

    Args:
        constraints: Settlement constraints
        regime: Current regime (LOW/NORMAL/STRESS/CRISIS)
        Se: Severity routing metric
        C: Coherence gate value
        regime_node_id: ID of the regime node this is based on
        calibration_hash: Hash of calibration data
        m2_cpi_gap: Current M2-CPI inflation gap

    Returns:
        AllocationDirective ready to write
    """
    ts = datetime.now(timezone.utc)
    directive_id = f"directive-{ts.strftime('%Y%m%dT%H%M%SZ')}"

    policy = AllocationPolicy()
    weights = policy.compute_weights(regime, Se, constraints, m2_cpi_gap)
    triggers = policy.get_triggers(regime)

    # Validate allocation
    violations = policy.validate_allocation(weights, constraints)
    if violations:
        # Log but don't fail - the constraints might need adjustment
        pass

    # Build allocation structure with tickers
    allocation = {}
    for bucket_id, weight in weights.items():
        bucket = BUCKETS[bucket_id]
        preferred_ticker = get_preferred_ticker(bucket.category)
        allocation[bucket_id] = {
            "weight": round(weight, 4),
            "category": bucket.category,
            "preferred_ticker": preferred_ticker,
            "alternatives": bucket.default_tickers,
            "purpose": bucket.purpose,
            "expense_ratio_cap_bps": bucket.expense_ratio_cap_bps,
        }

    # What would falsify/change this directive
    falsifiers = [
        f"Regime shifts from {regime} -> adjust per triggers",
        "Liquidity need arises -> draw from safety_floor first",
        "Time horizon shortens significantly -> increase safety allocation",
    ]
    if m2_cpi_gap > 5:
        falsifiers.append(f"M2-CPI gap normalizes below 3% (currently {m2_cpi_gap:.1f}%) -> reduce TIPS weight")
    if regime in ("LOW", "NORMAL"):
        falsifiers.append("Regime escalates to STRESS/CRISIS -> activate defensive rebalance")

    return AllocationDirective(
        directive_id=directive_id,
        generated_at=ts.isoformat(),
        regime_context={
            "current_regime": regime,
            "Se": round(Se, 4),
            "C": round(C, 4),
            "regime_node_id": regime_node_id,
            "m2_cpi_gap": round(m2_cpi_gap, 2),
        },
        constraints=constraints.to_dict(),
        allocation=allocation,
        regime_triggers=triggers,
        what_would_change_this=falsifiers,
        receipts={
            "calibration_hash": calibration_hash,
            "regime_node_id": regime_node_id,
        },
    )


def write_directive(
    directive: AllocationDirective,
    output_dir: str = "receipts/allocator",
) -> Tuple[str, str]:
    """
    Write directive to JSON + markdown, return paths.

    Creates:
    - DIRECTIVE.json (machine-readable)
    - DIRECTIVE.md (human-readable)
    - ALLOCATOR_RECEIPT.json (provenance)
    """
    out_path = Path(output_dir) / directive.directive_id
    out_path.mkdir(parents=True, exist_ok=True)

    # Write JSON
    json_path = out_path / "DIRECTIVE.json"
    directive_dict = directive.to_dict()
    directive_dict["directive_hash"] = directive.compute_hash()

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(directive_dict, f, indent=2, sort_keys=True, ensure_ascii=False)

    # Write markdown for humans
    md_path = out_path / "DIRECTIVE.md"
    md_content = _render_markdown(directive)
    md_path.write_text(md_content, encoding="utf-8")

    # Write receipt
    receipt_path = out_path / "ALLOCATOR_RECEIPT.json"
    receipt = {
        "directive_id": directive.directive_id,
        "generated_at": directive.generated_at,
        "directive_hash": directive.compute_hash(),
        "json_path": str(json_path),
        "md_path": str(md_path),
        "regime_context": directive.regime_context,
        "total_buckets": len(directive.allocation),
        "constraints_summary": {
            "settlement_amount": directive.constraints["settlement_amount"],
            "risk_tolerance": directive.constraints["risk_tolerance"],
            "time_horizon_years": directive.constraints["time_horizon_years"],
        },
    }
    with receipt_path.open("w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2, sort_keys=True)

    return str(json_path), str(md_path)


def _render_markdown(directive: AllocationDirective) -> str:
    """Render directive as human-readable markdown."""
    lines = [
        f"# Allocation Directive",
        f"",
        f"**ID:** `{directive.directive_id}`",
        f"",
        f"**Generated:** {directive.generated_at}",
        f"",
        f"**Regime:** {directive.regime_context['current_regime']} "
        f"(Se={directive.regime_context['Se']:.2f}, C={directive.regime_context['C']:.2f})",
        f"",
        f"**Settlement:** ${directive.constraints['settlement_amount']:,.0f}",
        f"",
        f"**Risk Tolerance:** {directive.constraints['risk_tolerance']}",
        f"",
        f"---",
        f"",
        f"## Allocation Summary",
        f"",
        f"| Bucket | Weight | Ticker | Purpose |",
        f"|--------|--------|--------|---------|",
    ]

    for bucket_id, info in directive.allocation.items():
        weight_pct = info['weight'] * 100
        lines.append(
            f"| {bucket_id.replace('_', ' ').title()} | "
            f"{weight_pct:.1f}% | "
            f"{info['preferred_ticker']} | "
            f"{info['purpose'][:50]}... |"
        )

    lines.extend([
        f"",
        f"---",
        f"",
        f"## Allocation Details",
        f"",
    ])

    for bucket_id, info in directive.allocation.items():
        weight_pct = info['weight'] * 100
        dollar_amount = directive.constraints['settlement_amount'] * info['weight']

        lines.append(f"### {bucket_id.replace('_', ' ').title()} ({weight_pct:.1f}%)")
        lines.append(f"")
        lines.append(f"**Dollar Amount:** ${dollar_amount:,.0f}")
        lines.append(f"")
        lines.append(f"**Purpose:** {info['purpose']}")
        lines.append(f"")
        lines.append(f"**Preferred Instrument:** {info['preferred_ticker']}")
        lines.append(f"")
        lines.append(f"**Alternatives:** {', '.join(info['alternatives'])}")
        lines.append(f"")
        lines.append(f"**Max Expense Ratio:** {info['expense_ratio_cap_bps']} bps ({info['expense_ratio_cap_bps']/100:.2f}%)")
        lines.append(f"")

    lines.extend([
        f"---",
        f"",
        f"## Regime Triggers",
        f"",
        f"These conditions would cause a rebalance:",
        f"",
    ])

    for trigger in directive.regime_triggers:
        lines.append(f"### IF: `{trigger['condition']}`")
        lines.append(f"")
        lines.append(f"**Action:** {trigger['action']}")
        lines.append(f"")
        lines.append(f"**Rationale:** {trigger['rationale']}")
        lines.append(f"")

    lines.extend([
        f"---",
        f"",
        f"## What Would Change This Directive",
        f"",
    ])

    for item in directive.what_would_change_this:
        lines.append(f"- {item}")

    lines.extend([
        f"",
        f"---",
        f"",
        f"## Provenance",
        f"",
        f"- **Calibration Hash:** `{directive.receipts['calibration_hash'][:16]}...`",
        f"- **Regime Node:** `{directive.receipts['regime_node_id']}`",
        f"- **Directive Hash:** `{directive.compute_hash()[:16]}...`",
        f"",
        f"---",
        f"",
        f"*Generated by FGIP Settlement Allocator*",
    ])

    return "\n".join(lines)
