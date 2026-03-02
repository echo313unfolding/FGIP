"""Verification Report Generation.

Generates comprehensive reports on easter egg verification status
and overall pipeline health.

Usage:
    from fgip.verification.verifier import VerificationReport, run_verification

    report = run_verification(conn)
    print(report.to_text())
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any

from .easter_eggs import EASTER_EGGS, check_all_eggs


@dataclass
class VerificationReport:
    """Report of easter egg verification results."""
    timestamp: str
    eggs_total: int
    eggs_found: int
    eggs_missing: List[str]
    by_agent: Dict[str, Dict]
    details: List[Dict]
    pipeline_health: str  # "healthy", "degraded", "broken"

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "eggs_total": self.eggs_total,
            "eggs_found": self.eggs_found,
            "eggs_missing": self.eggs_missing,
            "by_agent": self.by_agent,
            "details": self.details,
            "pipeline_health": self.pipeline_health,
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def to_text(self) -> str:
        """Convert to human-readable text format."""
        lines = []
        lines.append("=== FGIP Verification Report ===")
        lines.append(f"Timestamp: {self.timestamp}")
        lines.append("")

        # Overall status
        pct = (self.eggs_found / self.eggs_total * 100) if self.eggs_total > 0 else 0
        health_icon = {"healthy": "✓", "degraded": "⚠", "broken": "✗"}.get(self.pipeline_health, "?")
        lines.append(f"Pipeline Health: [{health_icon}] {self.pipeline_health.upper()}")
        lines.append(f"Easter Eggs: {self.eggs_found}/{self.eggs_total} found ({pct:.0f}%)")
        lines.append("")

        # By agent breakdown
        lines.append("=== By Agent ===")
        for agent, stats in sorted(self.by_agent.items()):
            agent_pct = (stats["found"] / stats["total"] * 100) if stats["total"] > 0 else 0
            status = "✓" if stats["found"] == stats["total"] else "○"
            lines.append(f"  [{status}] {agent}: {stats['found']}/{stats['total']} ({agent_pct:.0f}%)")
            if stats["missing"]:
                for egg_id in stats["missing"]:
                    lines.append(f"      Missing: {egg_id}")
        lines.append("")

        # Detailed results
        lines.append("=== Detailed Results ===")
        for detail in self.details:
            status = "✓" if detail["found"] else "✗"
            lines.append(f"  [{status}] {detail['egg_id']} ({detail['agent']})")
            lines.append(f"      {detail['description']}")
            if detail["found"]:
                location = "staging" if detail["in_staging"] else "production"
                lines.append(f"      Found in: {location}")
                if detail.get("proposal_id"):
                    lines.append(f"      Proposal: {detail['proposal_id']}")
                if detail.get("edge_id"):
                    lines.append(f"      Edge: {detail['edge_id']}")
            else:
                lines.append("      Status: NOT FOUND")
            lines.append("")

        return "\n".join(lines)


def run_verification(conn, agent_name: Optional[str] = None) -> VerificationReport:
    """Run easter egg verification and generate report.

    Args:
        conn: Database connection
        agent_name: Optional filter by agent

    Returns:
        VerificationReport with results
    """
    results = check_all_eggs(conn, agent_name)

    # Determine pipeline health
    if results["total"] == 0:
        health = "broken"
    elif results["found"] == results["total"]:
        health = "healthy"
    elif results["found"] >= results["total"] * 0.6:  # 60%+ found
        health = "degraded"
    else:
        health = "broken"

    return VerificationReport(
        timestamp=results["timestamp"],
        eggs_total=results["total"],
        eggs_found=results["found"],
        eggs_missing=results["missing"],
        by_agent=results["by_agent"],
        details=results["results"],
        pipeline_health=health,
    )


def save_verification_report(report: VerificationReport, path: str):
    """Save verification report to JSON file.

    Args:
        report: VerificationReport to save
        path: Output file path
    """
    with open(path, "w") as f:
        f.write(report.to_json())


def quick_verify(conn) -> str:
    """Quick verification status string for CLI/logging.

    Returns something like: "Easter Eggs: 6/8 (75%) [degraded]"
    """
    report = run_verification(conn)
    pct = (report.eggs_found / report.eggs_total * 100) if report.eggs_total > 0 else 0
    return f"Easter Eggs: {report.eggs_found}/{report.eggs_total} ({pct:.0f}%) [{report.pipeline_health}]"
