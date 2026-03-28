"""
CLI entry point for FGIP Settlement Allocator.

Usage:
    python3 -m fgip.allocator --settlement 250000
    python3 -m fgip.allocator --settlement 250000 --regime NORMAL --json
"""

import argparse
import json
import sys
from pathlib import Path

from .constraints import SettlementConstraints, RiskTolerance
from .directive import generate_directive, write_directive


def main():
    parser = argparse.ArgumentParser(
        description="FGIP Settlement Allocator - Generate regime-driven allocation directives",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Auto-detect regime from latest export
  python3 -m fgip.allocator --settlement 250000

  # Explicit regime override
  python3 -m fgip.allocator --settlement 250000 --regime NORMAL

  # Conservative allocation
  python3 -m fgip.allocator --settlement 250000 --risk-tolerance conservative

  # Output JSON to stdout
  python3 -m fgip.allocator --settlement 250000 --json
        """,
    )

    # Required
    parser.add_argument(
        "--settlement", type=float, required=True,
        help="Settlement amount in dollars"
    )

    # Constraints
    parser.add_argument(
        "--runway-months", type=int, default=18,
        help="Liquidity runway in months (default: 18)"
    )
    parser.add_argument(
        "--horizon-years", type=int, default=10,
        help="Investment horizon in years (default: 10)"
    )
    parser.add_argument(
        "--risk-tolerance",
        choices=["conservative", "moderate", "growth"],
        default="moderate",
        help="Risk tolerance (default: moderate)"
    )
    parser.add_argument(
        "--max-er-bps", type=int, default=20,
        help="Max expense ratio in basis points (default: 20 = 0.20%%)"
    )
    parser.add_argument(
        "--income-monthly", type=float, default=0,
        help="Monthly income need in dollars (default: 0)"
    )

    # Regime context
    parser.add_argument(
        "--regime",
        choices=["LOW", "NORMAL", "STRESS", "CRISIS"],
        help="Override current regime (auto-detect if not provided)"
    )
    parser.add_argument(
        "--export-dir", type=str,
        help="Path to regime export for auto-detection"
    )
    parser.add_argument(
        "--m2-cpi-gap", type=float, default=0,
        help="Current M2-CPI gap %% (for inflation hedge adjustment)"
    )

    # Output
    parser.add_argument(
        "--output-dir", default="receipts/allocator",
        help="Output directory for directive (default: receipts/allocator)"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output JSON to stdout instead of writing files"
    )

    args = parser.parse_args()

    # Build constraints
    constraints = SettlementConstraints(
        settlement_amount=args.settlement,
        liquidity_runway_months=args.runway_months,
        time_horizon_years=args.horizon_years,
        risk_tolerance=RiskTolerance(args.risk_tolerance),
        max_expense_ratio_bps=args.max_er_bps,
        income_need_monthly=args.income_monthly,
    )

    # Validate constraints
    errors = constraints.validate()
    if errors:
        print("Constraint validation errors:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    # Get regime context
    try:
        regime, Se, C, regime_node_id, calibration_hash = _get_regime_context(args)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Generate directive
    directive = generate_directive(
        constraints=constraints,
        regime=regime,
        Se=Se,
        C=C,
        regime_node_id=regime_node_id,
        calibration_hash=calibration_hash,
        m2_cpi_gap=args.m2_cpi_gap,
    )

    if args.json:
        output = directive.to_dict()
        output["directive_hash"] = directive.compute_hash()
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        json_path, md_path = write_directive(directive, args.output_dir)

        print(f"Directive generated: {directive.directive_id}")
        print(f"")
        print(f"  Regime:     {regime} (Se={Se:.2f}, C={C:.2f})")
        print(f"  Settlement: ${args.settlement:,.0f}")
        print(f"  Risk:       {args.risk_tolerance}")
        print(f"")
        print(f"Allocation:")

        for bucket_id, info in directive.allocation.items():
            weight_pct = info['weight'] * 100
            dollar_amt = args.settlement * info['weight']
            ticker = info['preferred_ticker']
            print(f"  {bucket_id:20s} {weight_pct:5.1f}%  ${dollar_amt:>10,.0f}  ({ticker})")

        print(f"")
        print(f"Files:")
        print(f"  JSON:     {json_path}")
        print(f"  Markdown: {md_path}")
        print(f"")
        print(f"Hash: {directive.compute_hash()[:16]}...")


def _get_regime_context(args):
    """
    Extract regime context from args or latest export (with fallback).

    Returns: (regime, Se, C, regime_node_id, calibration_hash)
    """
    # Priority 1: Explicit override
    if args.regime:
        return (args.regime, 0.5, 0.8, "manual-override", "manual")

    # Priority 2: Auto-detect from specified or latest export
    export_dir = args.export_dir
    if not export_dir:
        # Find latest export
        exports_root = Path("receipts/regime/exports")
        if exports_root.exists():
            exports = sorted(exports_root.glob("full-graph-export-*"))
            if exports:
                export_dir = str(exports[-1])

    if export_dir:
        export_path = Path(export_dir)
        manifest_path = export_path / "EXPORT_MANIFEST.json"

        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())

            # Load latest regime node (sorted by date, last is most recent)
            regime_nodes_path = export_path / "regime_nodes.jsonl"
            if regime_nodes_path.exists():
                with regime_nodes_path.open() as f:
                    lines = list(f)
                    if lines:
                        # Last line is most recent (sorted by date in export)
                        latest = json.loads(lines[-1])
                        meta_str = latest.get("metadata", "{}")
                        meta = json.loads(meta_str) if isinstance(meta_str, str) else meta_str

                        return (
                            meta.get("regime", "NORMAL"),
                            meta.get("Se", 0.5),
                            meta.get("C", 0.8),
                            latest.get("node_id", "unknown"),
                            manifest.get("inputs", {}).get("calibration_hash", "unknown"),
                        )

    # Fallback: require explicit input
    raise ValueError(
        "No regime context available. Either:\n"
        "  1. Provide --regime LOW|NORMAL|STRESS|CRISIS\n"
        "  2. Provide --export-dir /path/to/export\n"
        "  3. Run a regime export first:\n"
        "     python3 -m fgip.regime.jsonl_bridge --include-hypotheses"
    )


if __name__ == "__main__":
    main()
