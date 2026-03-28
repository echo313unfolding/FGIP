"""
CLI entry point for Florida Location Scorer.

Usage:
    python3 -m fgip.location --score-all
    python3 -m fgip.location --area ocala --detailed
    python3 -m fgip.location --shortlist 5
"""

import argparse
import json
from datetime import datetime, timezone

from .scorer import FloridaLocationScorer, ScoringWeights, TARGET_AREAS


def main():
    parser = argparse.ArgumentParser(
        description="FGIP Florida Location Scorer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python3 -m fgip.location --score-all
    python3 -m fgip.location --area ocala --detailed
    python3 -m fgip.location --shortlist 5 --exclude-red-flags
    python3 -m fgip.location --list-areas
        """
    )

    # Mode selection
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--score-all", action="store_true",
                      help="Score all target areas")
    mode.add_argument("--area", type=str,
                      help="Score specific area (e.g., 'ocala')")
    mode.add_argument("--shortlist", type=int, metavar="N",
                      help="Get top N areas")
    mode.add_argument("--list-areas", action="store_true",
                      help="List all target areas")
    mode.add_argument("--red-flags", action="store_true",
                      help="Show only areas with red flags")

    # Options
    parser.add_argument("--detailed", action="store_true",
                        help="Show detailed component scores")
    parser.add_argument("--exclude-red-flags", action="store_true",
                        help="Exclude areas with red flags from shortlist")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON")
    parser.add_argument("--output", type=str,
                        help="Output directory for reports")

    args = parser.parse_args()

    scorer = FloridaLocationScorer()

    if args.list_areas:
        _list_areas(args)
    elif args.score_all:
        _score_all(scorer, args)
    elif args.area:
        _score_area(scorer, args)
    elif args.shortlist:
        _shortlist(scorer, args)
    elif args.red_flags:
        _red_flags(scorer, args)


def _list_areas(args):
    """List all target areas."""
    if args.json:
        print(json.dumps([{
            "area_id": a.area_id,
            "area_name": a.area_name,
            "county": a.county,
            "description": a.description,
        } for a in TARGET_AREAS], indent=2))
    else:
        print("Target Areas for Scoring:")
        print()
        for area in TARGET_AREAS:
            flags = []
            if area.is_55_plus:
                flags.append("55+")
            if area.has_gated_options:
                flags.append("gated")
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            print(f"  {area.area_id}: {area.area_name} ({area.county} County){flag_str}")
            print(f"    {area.description}")
            print()


def _score_all(scorer: FloridaLocationScorer, args):
    """Score all target areas."""
    scores = scorer.score_all_areas()

    if args.output:
        json_path, md_path, shortlist_path = scorer.write_results(args.output, scores)
        print(f"Results written to {args.output}:")
        print(f"  JSON: {json_path}")
        print(f"  Report: {md_path}")
        print(f"  Shortlist: {shortlist_path}")
        print()

    if args.json:
        print(json.dumps([s.to_dict() for s in scores], indent=2))
    else:
        print(scorer.generate_report(scores))


def _score_area(scorer: FloridaLocationScorer, args):
    """Score a specific area."""
    try:
        score = scorer.score_area(args.area)
    except ValueError as e:
        print(f"Error: {e}")
        print("Use --list-areas to see available areas")
        return

    if args.json:
        print(json.dumps(score.to_dict(), indent=2))
    else:
        print(f"# {score.area_name} ({score.county} County)")
        print()
        print(f"**Overall Score:** {score.overall_score:.1f}/100")
        print()

        if score.red_flags:
            print("**Red Flags:**")
            for flag in score.red_flags:
                print(f"- {flag}")
            print()

        if args.detailed:
            print("**Component Scores:**")
            print()
            print("| Factor | Score | Weight | Weighted |")
            print("|--------|-------|--------|----------|")
            for comp in score.component_scores.values():
                print(
                    f"| {comp.factor.replace('_', ' ').title()} | "
                    f"{comp.score:.1f} | {comp.weight:.0%} | {comp.weighted_score:.1f} |"
                )
            print()

            print("**Component Details:**")
            print()
            for comp in score.component_scores.values():
                print(f"*{comp.factor.replace('_', ' ').title()}*")
                for key, val in comp.data.items():
                    if key not in ("score", "notes"):
                        print(f"  - {key}: {val}")
                if comp.notes:
                    for note in comp.notes:
                        print(f"  - Note: {note}")
                print()


def _shortlist(scorer: FloridaLocationScorer, args):
    """Get top N areas."""
    shortlist = scorer.get_shortlist(args.shortlist, args.exclude_red_flags)

    if args.json:
        print(json.dumps([s.to_dict() for s in shortlist], indent=2))
    else:
        print(f"# Top {args.shortlist} Florida Locations")
        print()

        for i, score in enumerate(shortlist, 1):
            flags_str = f" [{len(score.red_flags)} red flags]" if score.red_flags else ""
            print(f"{i}. **{score.area_name}** ({score.county}) - {score.overall_score:.1f}/100{flags_str}")

            if args.detailed:
                print()
                for key_factor in ["insurance_risk", "flood_zone", "healthcare_access"]:
                    if key_factor in score.component_scores:
                        comp = score.component_scores[key_factor]
                        print(f"   - {comp.factor.replace('_', ' ').title()}: {comp.score:.0f}")
                print()


def _red_flags(scorer: FloridaLocationScorer, args):
    """Show areas with red flags."""
    scores = scorer.score_all_areas()
    flagged = [s for s in scores if s.has_red_flags()]

    if args.json:
        print(json.dumps([{
            "area": s.area_name,
            "county": s.county,
            "score": s.overall_score,
            "red_flags": s.red_flags,
        } for s in flagged], indent=2))
    else:
        if not flagged:
            print("No areas have red flags.")
            return

        print(f"# Areas with Red Flags ({len(flagged)})")
        print()

        for score in flagged:
            print(f"## {score.area_name} ({score.county}) - {score.overall_score:.1f}/100")
            print()
            for flag in score.red_flags:
                print(f"- {flag}")
            print()


if __name__ == "__main__":
    main()
