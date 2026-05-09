"""
FGIP Cascade Detector — Timing cascade stage tracker.

Monitors the deal → PUC → FERC → gathering → permits → production cascade.
Each stage advancement is an alpha signal.

The cascade model was backtested against Virginia 2019-2022 and confirmed
the sequence (magnitude inflated by gas supercycle, but order correct).

Stages:
    0: No activity
    1: Deal announced / PUC filing
    2: PUC approval
    3: Gas supply contract (earnings language)
    4: FERC capacity reservation  ← BIGGEST ALPHA WINDOW
    5: Gathering acreage dedications (midstream throughput guidance)
    6: E&P drilling permit surge
    7: Wells online (EIA production data)
"""

import json
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional


STAGE_LABELS = {
    0: "NO_ACTIVITY",
    1: "DEAL_FILED",
    2: "PUC_APPROVED",
    3: "GAS_CONTRACT",
    4: "FERC_CAPACITY",
    5: "GATHERING_DEDICATED",
    6: "PERMIT_SURGE",
    7: "WELLS_ONLINE",
}

# Edge types in the FGIP graph that signal each stage
STAGE_EDGE_PATTERNS = {
    1: ["FILED_PUC", "ANNOUNCED_DEAL", "FILED_APPLICATION"],
    2: ["PUC_APPROVED", "COMMISSION_ORDER"],
    3: ["SIGNED_CONTRACT", "EARNINGS_MENTION"],
    4: ["FERC_CAPACITY", "FILED_FERC", "CAPACITY_RESERVATION"],
    5: ["DEDICATED_ACREAGE", "GATHERING_CONTRACT", "THROUGHPUT_GUIDANCE"],
    6: ["DRILLING_PERMIT", "PERMIT_SURGE", "WELL_PERMIT"],
    7: ["WELL_ONLINE", "PRODUCTION_DATA", "EIA_REPORT"],
}


@dataclass
class CascadeState:
    """Current state of a thesis in the timing cascade."""
    thesis_id: str
    current_stage: int
    stage_label: str
    stages_detected: Dict[int, List[str]]  # stage -> list of edge_ids
    last_advancement: Optional[str]  # ISO timestamp
    alpha_window: bool  # True if in stage 3-5 (highest alpha)
    notes: str = ""
    checked_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CascadeDetector:
    """
    Detect timing cascade stage advancement from FGIP graph edges.

    Reads the graph to find edges matching each cascade stage pattern,
    determines the current stage, and flags alpha windows.
    """

    def __init__(self, db_path: str = "fgip.db"):
        self.db_path = db_path

    def _get_db(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def check_stage(self, thesis_id: str) -> CascadeState:
        """
        Determine what stage a thesis is at in the timing cascade.

        Scans graph edges connected to the thesis node for patterns
        matching each cascade stage.
        """
        conn = self._get_db()

        # Find all edges connected to this thesis or its related nodes
        stages_detected: Dict[int, List[str]] = {}
        max_stage = 0

        for stage, patterns in STAGE_EDGE_PATTERNS.items():
            matching_edges = []
            for pattern in patterns:
                rows = conn.execute(
                    """SELECT edge_id, edge_type, from_node_id, to_node_id, date_documented
                       FROM edges
                       WHERE edge_type LIKE ?
                       AND (from_node_id = ? OR to_node_id = ?
                            OR from_node_id IN (
                                SELECT to_node_id FROM edges WHERE from_node_id = ?
                            ))
                       ORDER BY date_documented DESC""",
                    (f"%{pattern}%", thesis_id, thesis_id, thesis_id)
                ).fetchall()
                for row in rows:
                    matching_edges.append(row[0])

            if matching_edges:
                stages_detected[stage] = matching_edges
                max_stage = max(max_stage, stage)

        conn.close()

        # Determine alpha window (stages 3-5)
        alpha_window = max_stage in (3, 4, 5)

        last_advancement = None
        if stages_detected:
            # Get most recent date from highest stage edges
            conn = self._get_db()
            highest_edges = stages_detected.get(max_stage, [])
            if highest_edges:
                placeholders = ",".join("?" * len(highest_edges))
                row = conn.execute(
                    f"SELECT MAX(date_documented) FROM edges WHERE edge_id IN ({placeholders})",
                    highest_edges
                ).fetchone()
                if row and row[0]:
                    last_advancement = row[0]
            conn.close()

        return CascadeState(
            thesis_id=thesis_id,
            current_stage=max_stage,
            stage_label=STAGE_LABELS.get(max_stage, "UNKNOWN"),
            stages_detected=stages_detected,
            last_advancement=last_advancement,
            alpha_window=alpha_window,
        )

    def check_all_theses(self, thesis_ids: List[str]) -> List[CascadeState]:
        """Check cascade state for multiple theses."""
        return [self.check_stage(tid) for tid in thesis_ids]

    def detect_advancement(
        self,
        thesis_id: str,
        previous_stage: int
    ) -> Optional[CascadeState]:
        """
        Check if a thesis has advanced past a known previous stage.

        Returns CascadeState if advanced, None if unchanged.
        """
        current = self.check_stage(thesis_id)
        if current.current_stage > previous_stage:
            current.notes = f"ADVANCED: stage {previous_stage} -> {current.current_stage}"
            return current
        return None
