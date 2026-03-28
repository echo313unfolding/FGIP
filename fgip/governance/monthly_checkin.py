"""
Monthly Check-in Report Generator.

Combines IPS, Housing Gate, and FCI into a single monthly review.
"""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, Optional, Tuple
import json

from .ips import InvestmentPolicyStatement
from .housing_gate import HousingDecisionGate
from .family_cost_index import FamilyCostIndex


@dataclass
class MonthlyCheckin:
    """Monthly review generator combining all governance inputs."""

    checkin_date: date
    ips: InvestmentPolicyStatement
    housing_gate: HousingDecisionGate
    fci: FamilyCostIndex

    # Current regime context (from latest directive)
    current_regime: str = "NORMAL"
    regime_Se: float = 0.5

    # Allocation tracking
    actual_allocation: Optional[Dict[str, float]] = None
    target_allocation: Optional[Dict[str, float]] = None

    # CPI for comparison
    cpi_yoy: Optional[float] = None

    def compute_drift(self) -> Dict[str, dict]:
        """
        Compute drift from target allocation.

        Returns:
            Dict of {bucket_id: {target, actual, drift_pct, needs_rebalance}}
        """
        if not self.actual_allocation or not self.target_allocation:
            return {}

        drift = {}
        for bucket, target in self.target_allocation.items():
            actual = self.actual_allocation.get(bucket, 0)
            drift_pct = (actual - target) * 100
            needs_rebalance = abs(drift_pct) > self.ips.drift_threshold_pct

            drift[bucket] = {
                "target": target,
                "actual": actual,
                "drift_pct": drift_pct,
                "needs_rebalance": needs_rebalance,
            }

        return drift

    def get_action_items(self) -> list:
        """Generate action items based on current state."""
        items = []

        # Check allocation drift
        drift = self.compute_drift()
        buckets_need_rebalance = [k for k, v in drift.items() if v.get("needs_rebalance")]
        if buckets_need_rebalance:
            items.append(f"Rebalance: {', '.join(buckets_need_rebalance)} exceed drift threshold")

        # Check housing gate
        can_proceed, _ = self.housing_gate.can_proceed()
        if self.housing_gate.current_phase.value == "renting":
            unmet = [g.condition_id for g in self.housing_gate.green_lights if not g.is_met]
            if unmet:
                items.append(f"Housing gate: {len(unmet)} green lights not yet met")

        # Check FCI alert
        if self.cpi_yoy is not None:
            fci_month = self.checkin_date.strftime("%Y-%m")
            alert = self.fci.check_alert(fci_month, self.cpi_yoy)
            if alert:
                items.append("FCI alert: Real costs exceeding CPI - review TIPS allocation")

        # Check regime
        if self.current_regime in ("STRESS", "CRISIS"):
            items.append(f"Regime is {self.current_regime} - review defensive posture")

        # Standard monthly items
        items.extend([
            "Update FCI with this month's expenses",
            "Verify no cooling period violations",
            "Confirm regime status from latest data",
        ])

        return items

    def generate_report(self) -> str:
        """Generate monthly check-in report as markdown."""
        month_str = self.checkin_date.strftime("%B %Y")
        fci_month = self.checkin_date.strftime("%Y-%m")

        # Compute states
        drift = self.compute_drift()
        needs_rebalance = any(d.get("needs_rebalance") for d in drift.values())
        can_proceed, housing_reason = self.housing_gate.can_proceed()
        fci_value = self.fci.compute_index(fci_month)
        fci_yoy = self.fci.compute_yoy_change(fci_month)

        lines = [
            f"# Monthly Check-in: {month_str}",
            "",
            f"**Date:** {self.checkin_date.isoformat()}",
            f"**Regime:** {self.current_regime} (Se={self.regime_Se:.2f})",
            f"**Beneficiary:** {self.ips.beneficiary}",
            "",
            "---",
            "",
            "## 1. Allocation Status",
            "",
        ]

        if drift:
            lines.append("| Bucket | Target | Actual | Drift | Action |")
            lines.append("|--------|--------|--------|-------|--------|")
            for bucket, d in drift.items():
                action = "REBALANCE" if d["needs_rebalance"] else "OK"
                lines.append(
                    f"| {bucket.replace('_', ' ').title()} | "
                    f"{d['target']*100:.1f}% | {d['actual']*100:.1f}% | "
                    f"{d['drift_pct']:+.1f}% | {action} |"
                )
            lines.append("")

            if needs_rebalance:
                lines.append("**Status:** Rebalance required - some buckets exceed drift threshold")
            else:
                lines.append("**Status:** OK - all buckets within drift tolerance")
        else:
            lines.append("*No allocation data available - update actual holdings*")

        lines.extend([
            "",
            "---",
            "",
            "## 2. Housing Decision Gate",
            "",
            f"**Phase:** {self.housing_gate.current_phase.value.upper()}",
            f"**Location:** {self.housing_gate.target_location or 'Not specified'}",
            f"**Status:** {'PROCEED OK' if can_proceed else 'WAIT'}",
            "",
        ])

        # Green lights summary
        green_met = sum(1 for g in self.housing_gate.green_lights if g.is_met)
        green_total = len(self.housing_gate.green_lights)
        lines.append(f"Green lights: {green_met}/{green_total} met")

        # Red lights summary
        red_triggered = sum(1 for r in self.housing_gate.red_lights if r.is_triggered)
        red_total = len(self.housing_gate.red_lights)
        lines.append(f"Red lights: {red_triggered}/{red_total} triggered")
        lines.append("")
        lines.append(f"**Assessment:** {housing_reason}")

        lines.extend([
            "",
            "---",
            "",
            "## 3. Family Cost Index",
            "",
        ])

        if fci_value is not None:
            lines.append(f"**FCI ({fci_month}):** {fci_value:.1f} (baseline=100)")
        else:
            lines.append("**FCI:** *Insufficient data*")

        if fci_yoy is not None:
            lines.append(f"**Year-over-Year Change:** {fci_yoy:+.1f}%")
            if self.cpi_yoy is not None:
                gap = fci_yoy - self.cpi_yoy
                lines.append(f"**Official CPI:** {self.cpi_yoy:.1f}%")
                lines.append(f"**Gap (FCI - CPI):** {gap:+.1f}pp")

                if gap > 2:
                    lines.append("")
                    lines.append("**ALERT:** Real costs exceeding official inflation - review TIPS allocation")
        else:
            lines.append("**Year-over-Year Change:** *Insufficient data*")

        lines.extend([
            "",
            "---",
            "",
            "## 4. Circuit Breaker Status",
            "",
            f"**Cooling Period:** {self.ips.cooling_period_hours} hours for changes >{self.ips.cooling_applies_to_pct}%",
            "**Violations This Month:** None recorded",
            "",
            "---",
            "",
            "## 5. Action Items",
            "",
        ])

        for item in self.get_action_items():
            lines.append(f"- [ ] {item}")

        lines.extend([
            "",
            "---",
            "",
            f"*Next check-in: 1st of next month*",
            "",
            f"*Generated: {date.today().isoformat()}*",
        ])

        return "\n".join(lines)

    def write_report(
        self,
        output_dir: str = "receipts/governance/checkins"
    ) -> Tuple[str, str]:
        """
        Write check-in report to file.

        Returns:
            (markdown_path, json_path) tuple
        """
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        # Generate filenames
        month_str = self.checkin_date.strftime("%Y%m")
        md_filename = f"checkin-{month_str}.md"
        json_filename = f"checkin-{month_str}.json"

        # Write markdown
        md_path = out_path / md_filename
        md_path.write_text(self.generate_report())

        # Write JSON
        json_path = out_path / json_filename
        json_data = {
            "checkin_date": self.checkin_date.isoformat(),
            "regime": {
                "current": self.current_regime,
                "Se": self.regime_Se,
            },
            "allocation": {
                "drift": self.compute_drift(),
                "needs_rebalance": any(
                    d.get("needs_rebalance") for d in self.compute_drift().values()
                ),
            },
            "housing_gate": self.housing_gate.get_status_summary(),
            "fci": {
                "month": self.checkin_date.strftime("%Y-%m"),
                "index": self.fci.compute_index(self.checkin_date.strftime("%Y-%m")),
                "yoy_change": self.fci.compute_yoy_change(self.checkin_date.strftime("%Y-%m")),
                "cpi_yoy": self.cpi_yoy,
            },
            "action_items": self.get_action_items(),
        }

        with json_path.open("w") as f:
            json.dump(json_data, f, indent=2)

        return str(md_path), str(json_path)
