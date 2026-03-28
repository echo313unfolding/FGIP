"""
CLI entry point for governance tools.

Usage:
    python3 -m fgip.governance --generate-ips
    python3 -m fgip.governance --housing-gate
    python3 -m fgip.governance --monthly-checkin
"""

import argparse
import json
from datetime import date
from pathlib import Path

from .ips import InvestmentPolicyStatement
from .housing_gate import HousingDecisionGate, HousingPhase
from .family_cost_index import FamilyCostIndex
from .monthly_checkin import MonthlyCheckin


def main():
    parser = argparse.ArgumentParser(
        description="FGIP Governance Tools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python3 -m fgip.governance --generate-ips
    python3 -m fgip.governance --housing-gate --location "Florida"
    python3 -m fgip.governance --monthly-checkin --regime NORMAL
        """
    )

    # Mode selection
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--generate-ips", action="store_true",
                      help="Generate IPS document")
    mode.add_argument("--housing-gate", action="store_true",
                      help="Check housing decision gate status")
    mode.add_argument("--monthly-checkin", action="store_true",
                      help="Generate monthly check-in report")

    # IPS options
    parser.add_argument("--beneficiary", default="Mom",
                        help="Beneficiary name (default: Mom)")

    # Housing gate options
    parser.add_argument("--location", default="Florida",
                        help="Target location for housing gate")
    parser.add_argument("--rental-start", type=str,
                        help="Rental start date (YYYY-MM-DD)")

    # Monthly check-in options
    parser.add_argument("--regime", choices=["LOW", "NORMAL", "STRESS", "CRISIS"],
                        default="NORMAL", help="Current regime")
    parser.add_argument("--Se", type=float, default=0.5,
                        help="Regime Se metric")
    parser.add_argument("--cpi-yoy", type=float,
                        help="Official CPI year-over-year for comparison")

    # Output options
    parser.add_argument("--output-dir", default="receipts/governance",
                        help="Output directory")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON to stdout")

    args = parser.parse_args()

    if args.generate_ips:
        _generate_ips(args)
    elif args.housing_gate:
        _housing_gate(args)
    elif args.monthly_checkin:
        _monthly_checkin(args)


def _generate_ips(args):
    """Generate IPS document."""
    ips = InvestmentPolicyStatement(
        beneficiary=args.beneficiary,
        prepared_date=date.today(),
        decision_makers=[args.beneficiary, "Son"],
    )

    if args.json:
        print(json.dumps(ips.to_dict(), indent=2))
    else:
        # Write markdown
        out_path = Path(args.output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        md_path = out_path / "IPS.md"
        md_path.write_text(ips.to_markdown())

        print(f"IPS generated: {md_path}")
        print()
        print(ips.to_markdown())


def _housing_gate(args):
    """Check housing gate status."""
    rental_start = None
    if args.rental_start:
        rental_start = date.fromisoformat(args.rental_start)

    gate = HousingDecisionGate(
        current_phase=HousingPhase.RENTING,
        target_location=args.location,
        rental_start_date=rental_start,
    )

    if args.json:
        print(json.dumps(gate.to_dict(), indent=2))
    else:
        can, reason = gate.can_proceed()
        print(f"Housing Decision Gate: {args.location}")
        print(f"Phase: {gate.current_phase.value.upper()}")
        print(f"Status: {'PROCEED' if can else 'WAIT'}")
        print(f"Reason: {reason}")
        print()
        print(gate.to_markdown())


def _monthly_checkin(args):
    """Generate monthly check-in."""
    # Load or create IPS
    ips = InvestmentPolicyStatement(
        beneficiary=args.beneficiary,
        prepared_date=date.today(),
    )

    # Load or create housing gate
    gate = HousingDecisionGate(
        current_phase=HousingPhase.RENTING,
        target_location="Florida",
    )

    # Load or create FCI
    fci = FamilyCostIndex(baseline_month="2025-03")

    # Create check-in
    checkin = MonthlyCheckin(
        checkin_date=date.today(),
        ips=ips,
        housing_gate=gate,
        fci=fci,
        current_regime=args.regime,
        regime_Se=args.Se,
        cpi_yoy=args.cpi_yoy,
    )

    if args.json:
        print(json.dumps({
            "checkin_date": checkin.checkin_date.isoformat(),
            "regime": checkin.current_regime,
            "housing_gate": gate.get_status_summary(),
            "action_items": checkin.get_action_items(),
        }, indent=2))
    else:
        md_path, json_path = checkin.write_report(
            output_dir=f"{args.output_dir}/checkins"
        )
        print(f"Monthly check-in generated:")
        print(f"  Markdown: {md_path}")
        print(f"  JSON: {json_path}")
        print()
        print(checkin.generate_report())


if __name__ == "__main__":
    main()
