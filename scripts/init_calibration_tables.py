#!/usr/bin/env python3
"""
Initialize Calibration Tables for FGIP Calibrated Decision Pipeline.

Creates tables for:
- forecasts: Scenario trees with outcomes for Brier score tracking
- calibration_metrics: Rolling calibration scores per agent
- integrity_scores: Hughes-style integrity scores per artifact

Usage:
    python3 scripts/init_calibration_tables.py fgip.db
    python3 scripts/init_calibration_tables.py fgip.db --dry-run
"""

import argparse
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List


CALIBRATION_SCHEMA = """
-- Note: forecasts table may already exist from forecast_agent.py
-- We add missing columns if needed via migrate_forecasts_table()

-- Index for existing forecasts table (thesis_id should exist)
CREATE INDEX IF NOT EXISTS idx_forecasts_thesis ON forecasts(thesis_id);

-- Rolling calibration metrics per agent/time window
CREATE TABLE IF NOT EXISTS calibration_metrics (
    agent_name TEXT NOT NULL,
    time_window TEXT NOT NULL,           -- 'all_time', '30d', '90d', '1y'
    brier_score REAL,                    -- Average Brier score (0=perfect, 0.25=random)
    log_score REAL,                      -- Average log score
    overconfidence_ratio REAL,           -- >1 means overconfident, <1 underconfident
    underconfidence_ratio REAL,          -- Inverse of overconfidence
    sample_size INTEGER,                 -- Number of resolved forecasts
    mean_confidence REAL,                -- Average predicted probability
    hit_rate REAL,                       -- Actual success rate
    calibration_error REAL,              -- |mean_confidence - hit_rate|
    computed_at TEXT NOT NULL,
    PRIMARY KEY (agent_name, time_window)
);

CREATE INDEX IF NOT EXISTS idx_calibration_agent ON calibration_metrics(agent_name);

-- Integrity scores per artifact (Hughes-style triage)
CREATE TABLE IF NOT EXISTS integrity_scores (
    artifact_id TEXT PRIMARY KEY,
    source_url TEXT,
    source_tier TEXT,                    -- 'TIER_0', 'TIER_1', 'TIER_2', 'TIER_3'
    base_score REAL,                     -- Source tier weight (1.0, 0.85, 0.70, 0.50)
    adjustments TEXT,                    -- JSON: list of {marker, adjustment, reason}
    final_score REAL,                    -- Clamped to [0.0, 1.0]
    flags TEXT,                          -- JSON: list of red flags that block propagation
    manipulation_markers TEXT,           -- JSON: detected manipulation patterns
    integrity_boosters TEXT,             -- JSON: positive integrity signals
    scored_at TEXT,
    agent_name TEXT DEFAULT 'filter-agent'
);

CREATE INDEX IF NOT EXISTS idx_integrity_score ON integrity_scores(final_score);
CREATE INDEX IF NOT EXISTS idx_integrity_tier ON integrity_scores(source_tier);

-- Scenario probability tracking (for calibration curves)
CREATE TABLE IF NOT EXISTS forecast_probabilities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    forecast_id TEXT NOT NULL,
    scenario_name TEXT NOT NULL,         -- 'base_case', 'bull_case', 'bear_case', 'tail_risk'
    predicted_probability REAL NOT NULL, -- 0.0 to 1.0
    occurred INTEGER,                    -- 1 if this scenario occurred, 0 otherwise, NULL if unresolved
    confidence_interval_low REAL,
    confidence_interval_high REAL,
    FOREIGN KEY (forecast_id) REFERENCES forecasts(id)
);

CREATE INDEX IF NOT EXISTS idx_forecast_probs_forecast ON forecast_probabilities(forecast_id);
CREATE INDEX IF NOT EXISTS idx_forecast_probs_scenario ON forecast_probabilities(scenario_name);

-- Decision recommendations (policy-bounded sizing output)
CREATE TABLE IF NOT EXISTS decision_recommendations (
    id TEXT PRIMARY KEY,
    thesis_id TEXT NOT NULL,
    forecast_id TEXT,                    -- Links to forecasts table
    action TEXT NOT NULL,                -- 'BUY', 'HOLD', 'REDUCE', 'EXIT', 'AVOID'
    position_size REAL,                  -- 0.0 to max_single_position
    confidence REAL,                     -- Agent's confidence in recommendation
    kelly_fraction REAL,                 -- Raw Kelly before policy caps
    policy_caps_applied TEXT,            -- JSON: which policy limits kicked in
    reasoning TEXT,                      -- JSON: list of reasons
    risk_factors TEXT,                   -- JSON: identified risks
    hedge_recommendations TEXT,          -- JSON: suggested hedges
    review_triggers TEXT,                -- JSON: what would change recommendation
    created_at TEXT NOT NULL,
    expires_at TEXT,                     -- When this recommendation is stale
    agent_name TEXT DEFAULT 'decision-agent',
    FOREIGN KEY (forecast_id) REFERENCES forecasts(id)
);

CREATE INDEX IF NOT EXISTS idx_decisions_thesis ON decision_recommendations(thesis_id);
CREATE INDEX IF NOT EXISTS idx_decisions_action ON decision_recommendations(action);
CREATE INDEX IF NOT EXISTS idx_decisions_created ON decision_recommendations(created_at);

-- Counter-evidence tracking (from NLP extraction)
CREATE TABLE IF NOT EXISTS counter_evidence (
    id TEXT PRIMARY KEY,
    claim_id TEXT,                       -- Which claim this counters
    counter_claim TEXT NOT NULL,         -- The contradicting statement
    evidence_span TEXT,                  -- Exact text supporting counter
    source_url TEXT,
    source_integrity REAL,               -- Integrity score of counter-evidence source
    severity TEXT,                       -- 'fatal', 'serious', 'manageable', 'weak'
    detected_at TEXT NOT NULL,
    resolved_at TEXT,                    -- When counter-evidence was addressed
    resolution TEXT,                     -- How it was resolved: 'refuted', 'incorporated', 'superseded'
    agent_name TEXT DEFAULT 'nlp-agent'
);

CREATE INDEX IF NOT EXISTS idx_counter_claim ON counter_evidence(claim_id);
CREATE INDEX IF NOT EXISTS idx_counter_severity ON counter_evidence(severity);

-- NLP extraction cache (entities, relations)
CREATE TABLE IF NOT EXISTS nlp_extractions (
    id TEXT PRIMARY KEY,
    artifact_id TEXT,
    extraction_type TEXT NOT NULL,       -- 'entity', 'relation', 'evidence_span'
    subject_text TEXT,
    subject_type TEXT,                   -- 'PERSON', 'ORG', 'TICKER', 'AMOUNT', 'DATE', 'POLICY'
    predicate TEXT,                      -- For relations: 'FUNDS', 'LICENSES', 'OWNS', etc.
    object_text TEXT,
    object_type TEXT,
    evidence_span TEXT,                  -- Exact text supporting extraction
    span_start INTEGER,
    span_end INTEGER,
    confidence REAL,
    is_negation INTEGER DEFAULT 0,       -- 1 if "does NOT" pattern detected
    source_integrity REAL,               -- Propagated from artifact
    extracted_at TEXT NOT NULL,
    agent_name TEXT DEFAULT 'nlp-agent'
);

CREATE INDEX IF NOT EXISTS idx_nlp_artifact ON nlp_extractions(artifact_id);
CREATE INDEX IF NOT EXISTS idx_nlp_type ON nlp_extractions(extraction_type);
CREATE INDEX IF NOT EXISTS idx_nlp_subject ON nlp_extractions(subject_text);

-- Paper trade positions (simulated portfolio)
CREATE TABLE IF NOT EXISTS paper_positions (
    id TEXT PRIMARY KEY,
    thesis_id TEXT NOT NULL,
    ticker TEXT,
    recommendation_id TEXT,           -- Links to decision_recommendations
    entry_date TEXT NOT NULL,
    entry_price REAL,
    target_size REAL,                 -- From PositionRecommendation (0.0-1.0)
    actual_size REAL,                 -- Simulated fill (may differ)
    shares REAL,                      -- Number of shares
    exit_date TEXT,
    exit_price REAL,
    exit_reason TEXT,                 -- 'target', 'stop', 'time', 'manual', 'recommendation'
    realized_pnl REAL,
    realized_pnl_pct REAL,
    status TEXT DEFAULT 'OPEN',       -- OPEN, CLOSED
    created_at TEXT NOT NULL,
    FOREIGN KEY (recommendation_id) REFERENCES decision_recommendations(id)
);

CREATE INDEX IF NOT EXISTS idx_paper_positions_thesis ON paper_positions(thesis_id);
CREATE INDEX IF NOT EXISTS idx_paper_positions_ticker ON paper_positions(ticker);
CREATE INDEX IF NOT EXISTS idx_paper_positions_status ON paper_positions(status);

-- Paper trade portfolio history (time series snapshots)
CREATE TABLE IF NOT EXISTS paper_portfolio_history (
    timestamp TEXT NOT NULL,
    total_value REAL,
    cash REAL,
    positions_value REAL,
    unrealized_pnl REAL,
    realized_pnl_cumulative REAL,
    max_drawdown REAL,
    sharpe_ratio REAL,               -- Rolling
    position_count INTEGER,
    PRIMARY KEY (timestamp)
);

CREATE INDEX IF NOT EXISTS idx_paper_history_timestamp ON paper_portfolio_history(timestamp);

-- KAT (Known Answer Test) results tracking
CREATE TABLE IF NOT EXISTS kat_results (
    id TEXT PRIMARY KEY,
    run_timestamp TEXT NOT NULL,
    test_id TEXT NOT NULL,
    test_type TEXT NOT NULL,          -- 'easter_egg', 'adversarial'
    expected_result TEXT,             -- JSON
    actual_result TEXT,               -- JSON
    passed INTEGER NOT NULL,          -- 1=pass, 0=fail
    details TEXT,                     -- Error message or extra info
    duration_ms REAL
);

CREATE INDEX IF NOT EXISTS idx_kat_timestamp ON kat_results(run_timestamp);
CREATE INDEX IF NOT EXISTS idx_kat_test_id ON kat_results(test_id);
CREATE INDEX IF NOT EXISTS idx_kat_passed ON kat_results(passed);
"""


def migrate_forecasts_table(conn, dry_run: bool = False) -> List[str]:
    """Add missing columns to existing forecasts table."""
    added_columns = []

    # Columns we want in forecasts table
    desired_columns = [
        ("scenario_tree", "TEXT"),
        ("time_horizon", "TEXT"),
        ("agent_name", "TEXT"),
        ("brier_score", "REAL"),
        ("log_score", "REAL"),
        ("metadata", "TEXT"),
    ]

    # Get existing columns
    existing = set()
    for row in conn.execute("PRAGMA table_info(forecasts)").fetchall():
        existing.add(row[1])

    for col_name, col_type in desired_columns:
        if col_name not in existing:
            if not dry_run:
                try:
                    conn.execute(f"ALTER TABLE forecasts ADD COLUMN {col_name} {col_type}")
                except Exception:
                    pass
            added_columns.append(col_name)
            print(f"  ADD COLUMN: forecasts.{col_name}")

    return added_columns


def init_calibration_tables(db_path: Path, dry_run: bool = False) -> dict:
    """Initialize calibration tables.

    Returns:
        dict with tables_created, existing_tables counts
    """
    result = {
        "tables_created": 0,
        "existing_tables": 0,
        "columns_added": 0,
        "errors": [],
    }

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Check which tables already exist
    existing = set()
    for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        existing.add(row[0])

    new_tables = {
        "calibration_metrics", "integrity_scores",
        "forecast_probabilities", "decision_recommendations",
        "counter_evidence", "nlp_extractions",
        "paper_positions", "paper_portfolio_history", "kat_results"
    }

    # Handle forecasts table specially - it may already exist
    if "forecasts" in existing:
        print("  EXISTS: forecasts (checking columns...)")
        result["existing_tables"] += 1
        added = migrate_forecasts_table(conn, dry_run)
        result["columns_added"] = len(added)
    else:
        print("  CREATE: forecasts")
        result["tables_created"] += 1

    for table in new_tables:
        if table in existing:
            print(f"  EXISTS: {table}")
            result["existing_tables"] += 1
        else:
            print(f"  CREATE: {table}")
            result["tables_created"] += 1

    if dry_run:
        print("\n(DRY RUN - no changes made)")
        conn.close()
        return result

    try:
        conn.executescript(CALIBRATION_SCHEMA)
        conn.commit()
        print("\nSchema applied successfully.")
    except Exception as e:
        result["errors"].append(str(e))
        print(f"\nERROR: {e}")

    conn.close()
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Initialize Calibration Tables for FGIP"
    )
    parser.add_argument("db_path", help="Path to FGIP database")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be created")
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}")
        print("Create it first with: python3 -m fgip.cli init")
        return 1

    print("=" * 60)
    print("FGIP CALIBRATION TABLES INITIALIZATION")
    print("=" * 60)
    print(f"\nDatabase: {db_path}")
    print(f"Time: {datetime.utcnow().isoformat()}Z")
    print()

    result = init_calibration_tables(db_path, args.dry_run)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Tables created: {result['tables_created']}")
    print(f"Tables existing: {result['existing_tables']}")

    if result["errors"]:
        print(f"Errors: {len(result['errors'])}")
        for err in result["errors"]:
            print(f"  - {err}")
        return 1

    print("\nCalibration tables ready:")
    print("  - forecasts: Scenario trees with Brier/log scoring")
    print("  - calibration_metrics: Rolling accuracy per agent")
    print("  - integrity_scores: Hughes-style source triage")
    print("  - forecast_probabilities: Per-scenario probability tracking")
    print("  - decision_recommendations: Policy-bounded position sizing")
    print("  - counter_evidence: NLP-detected contradictions")
    print("  - nlp_extractions: Entity/relation extraction cache")
    print("  - paper_positions: Simulated portfolio positions")
    print("  - paper_portfolio_history: Portfolio time series snapshots")
    print("  - kat_results: Known Answer Test run tracking")

    return 0


if __name__ == "__main__":
    exit(main())
