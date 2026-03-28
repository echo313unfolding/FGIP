"""
Family Cost Index (FCI) - Custom inflation basket tracking real household costs.

Tracks actual expenses vs government CPI to detect hidden inflation.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional
import json


@dataclass
class CostCategory:
    """A tracked expense category with portfolio weight."""
    category_id: str
    name: str
    weight: float  # Portfolio weight (sums to 1.0)


@dataclass
class MonthlyExpense:
    """Actual expense for a category in a month."""
    category_id: str
    month: str  # YYYY-MM format
    amount: float
    notes: Optional[str] = None


# Default category weights (sum to 1.0)
DEFAULT_CATEGORIES = [
    CostCategory("housing", "Housing (rent/mortgage + insurance)", 0.35),
    CostCategory("healthcare", "Healthcare (premiums + OOP)", 0.20),
    CostCategory("food", "Food & Groceries", 0.15),
    CostCategory("transport", "Transportation (gas + maintenance)", 0.10),
    CostCategory("utilities", "Utilities (electric + water + internet)", 0.10),
    CostCategory("other", "Other (insurance + misc)", 0.10),
]


@dataclass
class FamilyCostIndex:
    """Custom inflation basket tracking real household costs."""

    # Categories with weights
    categories: List[CostCategory] = field(
        default_factory=lambda: DEFAULT_CATEGORIES.copy()
    )

    # Monthly expense history
    expenses: List[MonthlyExpense] = field(default_factory=list)

    # Baseline month for index calculation (100 = baseline)
    baseline_month: str = ""  # YYYY-MM

    def add_expense(
        self,
        category_id: str,
        month: str,
        amount: float,
        notes: Optional[str] = None
    ) -> bool:
        """
        Record an expense. Returns True if category exists.

        Args:
            category_id: Category to add expense to
            month: Month in YYYY-MM format
            amount: Dollar amount
            notes: Optional notes
        """
        # Validate category exists
        valid_ids = {c.category_id for c in self.categories}
        if category_id not in valid_ids:
            return False

        self.expenses.append(MonthlyExpense(
            category_id=category_id,
            month=month,
            amount=amount,
            notes=notes
        ))
        return True

    def get_month_expenses(self, month: str) -> Dict[str, float]:
        """Get all expenses for a month by category."""
        result = {}
        for e in self.expenses:
            if e.month == month:
                result[e.category_id] = result.get(e.category_id, 0) + e.amount
        return result

    def _weighted_total(self, month: str) -> float:
        """Compute weighted sum for a month."""
        month_expenses = self.get_month_expenses(month)

        # Build weight map
        weight_map = {c.category_id: c.weight for c in self.categories}

        total = 0.0
        for cat_id, amount in month_expenses.items():
            weight = weight_map.get(cat_id, 0)
            total += amount * weight

        return total

    def compute_index(self, month: str) -> Optional[float]:
        """
        Compute FCI for a month (100 = baseline).

        Returns None if baseline not set or insufficient data.
        """
        if not self.baseline_month:
            return None

        baseline_total = self._weighted_total(self.baseline_month)
        current_total = self._weighted_total(month)

        if baseline_total == 0:
            return None

        return (current_total / baseline_total) * 100

    def compute_yoy_change(self, month: str) -> Optional[float]:
        """
        Compute year-over-year percentage change.

        Args:
            month: Current month in YYYY-MM format

        Returns:
            YoY percentage change, or None if insufficient data
        """
        # Parse month to get prior year
        try:
            year = int(month[:4])
            mon = int(month[5:7])
        except (ValueError, IndexError):
            return None

        prior_month = f"{year - 1}-{mon:02d}"

        prior_total = self._weighted_total(prior_month)
        current_total = self._weighted_total(month)

        if prior_total == 0:
            return None

        return ((current_total - prior_total) / prior_total) * 100

    def check_alert(
        self,
        month: str,
        cpi_yoy: float,
        threshold: float = 2.0
    ) -> Optional[str]:
        """
        Check if FCI exceeds CPI by threshold.

        Args:
            month: Month to check
            cpi_yoy: Official CPI year-over-year change %
            threshold: Alert if FCI exceeds CPI by this many percentage points

        Returns:
            Alert message if triggered, None otherwise
        """
        fci_yoy = self.compute_yoy_change(month)

        if fci_yoy is None:
            return None

        gap = fci_yoy - cpi_yoy

        if gap > threshold:
            return (
                f"ALERT: FCI ({fci_yoy:.1f}%) exceeds CPI ({cpi_yoy:.1f}%) "
                f"by {gap:.1f}pp - hidden inflation detected"
            )

        return None

    def get_category_breakdown(self, month: str) -> Dict[str, dict]:
        """Get detailed breakdown by category for a month."""
        month_expenses = self.get_month_expenses(month)
        weight_map = {c.category_id: c for c in self.categories}

        result = {}
        for cat_id, cat in weight_map.items():
            amount = month_expenses.get(cat_id, 0)
            result[cat_id] = {
                "name": cat.name,
                "weight": cat.weight,
                "amount": amount,
                "weighted_amount": amount * cat.weight,
            }

        return result

    def to_markdown(self, month: str, cpi_yoy: Optional[float] = None) -> str:
        """Render FCI report as markdown for a month."""
        lines = [
            "# Family Cost Index Report",
            "",
            f"**Month:** {month}",
        ]

        if self.baseline_month:
            lines.append(f"**Baseline:** {self.baseline_month}")

        lines.extend(["", "---", ""])

        # Index value
        index = self.compute_index(month)
        if index is not None:
            lines.append(f"## FCI Value: {index:.1f}")
            lines.append("")
            if index > 100:
                lines.append(f"Costs are {index - 100:.1f}% above baseline.")
            elif index < 100:
                lines.append(f"Costs are {100 - index:.1f}% below baseline.")
            else:
                lines.append("Costs are at baseline level.")
        else:
            lines.append("## FCI Value: *Insufficient data*")

        lines.extend(["", "---", ""])

        # YoY change
        yoy = self.compute_yoy_change(month)
        if yoy is not None:
            lines.append(f"## Year-over-Year Change: {yoy:+.1f}%")
            if cpi_yoy is not None:
                gap = yoy - cpi_yoy
                lines.append(f"Official CPI: {cpi_yoy:.1f}%")
                lines.append(f"Gap: {gap:+.1f}pp")

                alert = self.check_alert(month, cpi_yoy)
                if alert:
                    lines.extend(["", f"**{alert}**"])
        else:
            lines.append("## Year-over-Year Change: *Insufficient data*")

        lines.extend(["", "---", ""])

        # Category breakdown
        lines.append("## Category Breakdown")
        lines.append("")
        lines.append("| Category | Weight | Amount | Weighted |")
        lines.append("|----------|--------|--------|----------|")

        breakdown = self.get_category_breakdown(month)
        for cat_id, info in breakdown.items():
            lines.append(
                f"| {info['name']} | {info['weight']*100:.0f}% | "
                f"${info['amount']:,.0f} | ${info['weighted_amount']:,.0f} |"
            )

        total = sum(info['amount'] for info in breakdown.values())
        weighted_total = sum(info['weighted_amount'] for info in breakdown.values())
        lines.append(f"| **Total** | 100% | **${total:,.0f}** | **${weighted_total:,.0f}** |")

        lines.extend([
            "",
            "---",
            "",
            f"*Generated: {date.today().isoformat()}*",
        ])

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "baseline_month": self.baseline_month,
            "categories": [
                {
                    "category_id": c.category_id,
                    "name": c.name,
                    "weight": c.weight,
                }
                for c in self.categories
            ],
            "expenses": [
                {
                    "category_id": e.category_id,
                    "month": e.month,
                    "amount": e.amount,
                    "notes": e.notes,
                }
                for e in self.expenses
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FamilyCostIndex":
        """Create from dictionary."""
        fci = cls(
            baseline_month=data.get("baseline_month", ""),
            categories=[
                CostCategory(
                    category_id=c["category_id"],
                    name=c["name"],
                    weight=c["weight"],
                )
                for c in data.get("categories", [])
            ] or DEFAULT_CATEGORIES.copy(),
            expenses=[
                MonthlyExpense(
                    category_id=e["category_id"],
                    month=e["month"],
                    amount=e["amount"],
                    notes=e.get("notes"),
                )
                for e in data.get("expenses", [])
            ],
        )
        return fci
