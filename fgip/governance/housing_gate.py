"""
Housing Decision Gate for major purchase decisions.

Binary green/red light framework to prevent emotional decisions.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Tuple
from enum import Enum


class HousingPhase(str, Enum):
    """Current phase in housing decision lifecycle."""
    RENTING = "renting"           # Data collection phase
    CONSIDERING = "considering"   # Active evaluation
    COMMITTED = "committed"       # Purchase in progress
    OWNING = "owning"            # Post-purchase


@dataclass
class GreenLight:
    """A condition that must be true to proceed with purchase."""
    condition_id: str
    description: str
    is_met: bool
    evidence: Optional[str] = None
    checked_date: Optional[date] = None


@dataclass
class RedLight:
    """A condition that blocks proceeding if true."""
    condition_id: str
    description: str
    is_triggered: bool
    evidence: Optional[str] = None
    checked_date: Optional[date] = None


@dataclass
class HousingDecisionGate:
    """Structured decision framework for housing purchase."""

    current_phase: HousingPhase
    rental_start_date: Optional[date] = None
    target_location: str = ""

    green_lights: List[GreenLight] = field(default_factory=list)
    red_lights: List[RedLight] = field(default_factory=list)

    def __post_init__(self):
        """Initialize default conditions if not provided."""
        if not self.green_lights:
            self.green_lights = self._default_green_lights()
        if not self.red_lights:
            self.red_lights = self._default_red_lights()

    def _default_green_lights(self) -> List[GreenLight]:
        """Default green light conditions (all must be met)."""
        return [
            GreenLight(
                "rental_experience",
                "12+ months rental experience in area",
                False
            ),
            GreenLight(
                "regime_stable",
                "Regime is LOW or NORMAL (not STRESS/CRISIS)",
                False
            ),
            GreenLight(
                "safety_buffer",
                "Safety floor can absorb 20% home value drop",
                False
            ),
            GreenLight(
                "housing_ratio",
                "Monthly housing cost (PITI + HOA + maintenance) < 35% of income",
                False
            ),
            GreenLight(
                "life_stable",
                "No major life changes expected in next 3 years",
                False
            ),
        ]

    def _default_red_lights(self) -> List[RedLight]:
        """Default red light conditions (any = wait)."""
        return [
            RedLight(
                "regime_stress",
                "Regime is STRESS or CRISIS",
                False
            ),
            RedLight(
                "hidden_inflation",
                "M2-CPI gap > 5% (hidden inflation eating purchasing power)",
                False
            ),
            RedLight(
                "low_emergency",
                "Emergency fund < 12 months expenses",
                False
            ),
            RedLight(
                "emotional",
                "Decision feels emotion-driven ('I just feel like it's time')",
                False
            ),
        ]

    def update_green_light(
        self,
        condition_id: str,
        is_met: bool,
        evidence: Optional[str] = None
    ) -> bool:
        """Update a green light condition. Returns True if found."""
        for g in self.green_lights:
            if g.condition_id == condition_id:
                g.is_met = is_met
                g.evidence = evidence
                g.checked_date = date.today()
                return True
        return False

    def update_red_light(
        self,
        condition_id: str,
        is_triggered: bool,
        evidence: Optional[str] = None
    ) -> bool:
        """Update a red light condition. Returns True if found."""
        for r in self.red_lights:
            if r.condition_id == condition_id:
                r.is_triggered = is_triggered
                r.evidence = evidence
                r.checked_date = date.today()
                return True
        return False

    def can_proceed(self) -> Tuple[bool, str]:
        """
        Check if purchase consideration is allowed.

        Returns:
            (can_proceed, reason) tuple
        """
        # Any red light = stop immediately
        triggered_reds = [r for r in self.red_lights if r.is_triggered]
        if triggered_reds:
            red_ids = [r.condition_id for r in triggered_reds]
            return False, f"Red lights triggered: {red_ids}"

        # All green lights must be met
        unmet_greens = [g for g in self.green_lights if not g.is_met]
        if unmet_greens:
            green_ids = [g.condition_id for g in unmet_greens]
            return False, f"Green lights not met: {green_ids}"

        return True, "All conditions satisfied - may proceed with caution"

    def get_status_summary(self) -> dict:
        """Get summary status for reporting."""
        can, reason = self.can_proceed()

        green_met = sum(1 for g in self.green_lights if g.is_met)
        green_total = len(self.green_lights)
        red_triggered = sum(1 for r in self.red_lights if r.is_triggered)
        red_total = len(self.red_lights)

        return {
            "can_proceed": can,
            "reason": reason,
            "phase": self.current_phase.value,
            "location": self.target_location,
            "green_lights": f"{green_met}/{green_total} met",
            "red_lights": f"{red_triggered}/{red_total} triggered",
        }

    def to_markdown(self) -> str:
        """Render gate status as markdown."""
        can, reason = self.can_proceed()
        status = "PROCEED WITH CAUTION" if can else "WAIT"
        status_emoji = "" if can else ""  # No emojis per instructions

        lines = [
            "# Housing Decision Gate",
            "",
            f"**Current Phase:** {self.current_phase.value.upper()}",
            f"**Location:** {self.target_location or 'Not specified'}",
            f"**Status:** {status}",
            "",
        ]

        if self.rental_start_date:
            days_renting = (date.today() - self.rental_start_date).days
            months_renting = days_renting / 30
            lines.append(f"**Time Renting:** {months_renting:.1f} months")
            lines.append("")

        lines.extend([
            "---",
            "",
            "## Green Lights (all must be met)",
            "",
        ])

        for g in self.green_lights:
            check = "x" if g.is_met else " "
            lines.append(f"- [{check}] {g.description}")
            if g.evidence:
                lines.append(f"  - Evidence: {g.evidence}")
            if g.checked_date:
                lines.append(f"  - Last checked: {g.checked_date.isoformat()}")

        lines.extend([
            "",
            "## Red Lights (any one = wait)",
            "",
        ])

        for r in self.red_lights:
            flag = "TRIGGERED" if r.is_triggered else "clear"
            lines.append(f"- **[{flag}]** {r.description}")
            if r.evidence:
                lines.append(f"  - Evidence: {r.evidence}")
            if r.checked_date:
                lines.append(f"  - Last checked: {r.checked_date.isoformat()}")

        lines.extend([
            "",
            "---",
            "",
            f"**Assessment:** {reason}",
            "",
            "---",
            "",
            "*Updated: " + date.today().isoformat() + "*",
        ])

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "current_phase": self.current_phase.value,
            "rental_start_date": self.rental_start_date.isoformat() if self.rental_start_date else None,
            "target_location": self.target_location,
            "green_lights": [
                {
                    "condition_id": g.condition_id,
                    "description": g.description,
                    "is_met": g.is_met,
                    "evidence": g.evidence,
                    "checked_date": g.checked_date.isoformat() if g.checked_date else None,
                }
                for g in self.green_lights
            ],
            "red_lights": [
                {
                    "condition_id": r.condition_id,
                    "description": r.description,
                    "is_triggered": r.is_triggered,
                    "evidence": r.evidence,
                    "checked_date": r.checked_date.isoformat() if r.checked_date else None,
                }
                for r in self.red_lights
            ],
            "can_proceed": self.can_proceed()[0],
        }
