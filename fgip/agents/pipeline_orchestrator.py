#!/usr/bin/env python3
"""FGIP Pipeline Orchestrator - Coordinates FilterAgent → NLPAgent → Proposals.

This is the "water treatment plant" that ensures:
1. All artifacts go through integrity triage (FilterAgent)
2. Only FAST_TRACK and HUMAN_REVIEW content reaches NLP extraction
3. DEPRIORITIZE content is skipped without wasting extraction resources
4. Filter metadata propagates to proposals (reviewers see WHY content passed)

Usage:
    from fgip.agents.pipeline_orchestrator import PipelineOrchestrator
    from fgip.db import FGIPDatabase

    db = FGIPDatabase('fgip.db')
    orch = PipelineOrchestrator(db)
    result = orch.process_pending_artifacts(batch_size=100)
"""

import json
import hashlib
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Any, Optional
import sys

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fgip.db import FGIPDatabase


@dataclass
class PipelineStats:
    """Statistics from a pipeline run."""
    artifacts_processed: int
    filtered: int
    fast_track: int
    human_review: int
    deprioritized: int
    extracted: int
    extraction_failed: int
    claims_proposed: int
    edges_proposed: int
    timestamp: str


@dataclass
class QueueStatus:
    """Current state of the artifact queue (compatibility with web/app.py)."""
    pending: int
    filtering: int
    filtered: int
    extracting: int
    extracted: int
    failed: int

    def total(self) -> int:
        return sum([
            self.pending, self.filtering, self.filtered,
            self.extracting, self.extracted, self.failed
        ])


@dataclass
class CycleReport:
    """Report from a single processing cycle (compatibility with web/app.py)."""
    cycle_id: str
    started_at: str
    completed_at: str
    pending_before: int
    artifacts_filtered: int
    artifacts_extracted: int
    artifacts_failed: int
    fast_track_count: int
    human_review_count: int
    deprioritize_count: int
    claims_created: int
    edges_created: int
    errors: List[str]

    def as_dict(self) -> Dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)


class PipelineOrchestrator:
    """Coordinates FilterAgent → NLPAgent → Proposal flow.

    Ensures integrity triage happens before expensive NLP extraction,
    and that filter metadata propagates to reviewers.

    Args:
        db: Either an FGIPDatabase object or a string path to the database.
            Both are supported for backward compatibility.
    """

    def __init__(self, db):
        # Accept either FGIPDatabase or string path
        if isinstance(db, str):
            from fgip.db import FGIPDatabase as FGIPDb
            self.db = FGIPDb(db)
        else:
            self.db = db
        self.conn = None

    def connect(self):
        """Get database connection."""
        if self.conn is None:
            self.conn = self.db.connect()
        return self.conn

    def process_pending_artifacts(self, batch_size: int = 100) -> PipelineStats:
        """
        Process pending artifacts through the full pipeline.

        Steps:
        1. Select artifacts from artifact_queue WHERE status='PENDING'
        2. Run FilterAgent.filter_content() → updates artifact_queue with route/score
        3. Select WHERE route IN ('FAST_TRACK', 'HUMAN_REVIEW')
        4. Run NLPAgent.process_artifact() with filter metadata
        5. Proposals inherit filter_score, route, reason_codes in reasoning field

        Args:
            batch_size: Maximum artifacts to process in this run

        Returns:
            PipelineStats with counts of what was processed
        """
        self.connect()

        stats = PipelineStats(
            artifacts_processed=0,
            filtered=0,
            fast_track=0,
            human_review=0,
            deprioritized=0,
            extracted=0,
            extraction_failed=0,
            claims_proposed=0,
            edges_proposed=0,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # Import agents here to avoid circular imports
        from fgip.agents.filter_agent import FilterAgent
        from fgip.agents.nlp_agent import NLPAgent

        filter_agent = FilterAgent(self.db)
        nlp_agent = NLPAgent(str(self.db.db_path))

        # Step 1: Get pending artifacts
        pending = self.conn.execute("""
            SELECT artifact_id, url, artifact_path, content_type, source_id
            FROM artifact_queue
            WHERE status = 'PENDING'
            ORDER BY created_at ASC
            LIMIT ?
        """, (batch_size,)).fetchall()

        # Even if no PENDING artifacts, we still need to process FILTERED ones
        if pending:
            stats.artifacts_processed = len(pending)
        else:
            stats.artifacts_processed = 0

        # Step 2: Run filter on each
        for row in pending:
            artifact_id = row["artifact_id"]

            # Read content
            content = self._read_artifact_content(
                row["artifact_path"],
                row["url"]
            )

            if not content:
                self._mark_failed(artifact_id, "Could not read content")
                continue

            # Determine source tier from content_type/source
            source_tier = self._infer_source_tier(row["source_id"], row["content_type"])

            # Run filter
            try:
                # Use score_text() which returns IntegrityScore
                result = filter_agent.score_text(
                    text=content,
                    source_url=row["url"] or "",
                )

                # Map IntegrityScore fields to artifact_queue columns
                route = result.get_route()
                priority_score = result.final_score * 100  # Convert 0-1 to 0-100

                # Update artifact_queue with filter results
                self.conn.execute("""
                    UPDATE artifact_queue
                    SET status = 'FILTERED',
                        filter_score = ?,
                        route = ?,
                        reason_codes = ?,
                        manipulation_flags = ?,
                        novelty_score = ?,
                        se_score = ?
                    WHERE artifact_id = ?
                """, (
                    priority_score,
                    route,
                    json.dumps(result.integrity_boosters),
                    json.dumps(result.manipulation_markers),
                    result.novelty_score,
                    result.se_score,
                    artifact_id,
                ))

                stats.filtered += 1

                if route == 'FAST_TRACK':
                    stats.fast_track += 1
                elif route == 'HUMAN_REVIEW':
                    stats.human_review += 1
                else:
                    stats.deprioritized += 1

            except Exception as e:
                self._mark_failed(artifact_id, f"Filter error: {str(e)}")

        self.conn.commit()

        # Step 3: Process FAST_TRACK and HUMAN_REVIEW through NLP
        # Use atomic claiming to prevent double-extraction in concurrent runs
        to_extract = self.conn.execute("""
            SELECT artifact_id, url, artifact_path, filter_score, route,
                   reason_codes, manipulation_flags
            FROM artifact_queue
            WHERE status = 'FILTERED'
            AND route IN ('FAST_TRACK', 'HUMAN_REVIEW')
            ORDER BY filter_score DESC, created_at ASC
            LIMIT ?
        """, (batch_size,)).fetchall()

        # Atomically claim artifacts for extraction
        claimed_artifacts = []
        for row in to_extract:
            artifact_id = row["artifact_id"]

            # Atomically claim: only succeeds if status is still FILTERED
            result = self.conn.execute("""
                UPDATE artifact_queue SET status = 'EXTRACTING'
                WHERE artifact_id = ? AND status = 'FILTERED'
            """, (artifact_id,))

            if result.rowcount > 0:
                # Successfully claimed this artifact
                claimed_artifacts.append(row)

        self.conn.commit()

        for row in claimed_artifacts:
            artifact_id = row["artifact_id"]

            try:
                # Process with NLP agent
                result = self._process_with_filter_context(
                    nlp_agent=nlp_agent,
                    artifact_id=artifact_id,
                    artifact_path=row["artifact_path"],
                    source_url=row["url"],
                    filter_score=row["filter_score"],
                    filter_route=row["route"],
                    reason_codes=json.loads(row["reason_codes"]) if row["reason_codes"] else [],
                    manipulation_flags=json.loads(row["manipulation_flags"]) if row["manipulation_flags"] else [],
                )

                if "error" in result:
                    self._mark_failed(artifact_id, result["error"])
                    stats.extraction_failed += 1
                else:
                    self.conn.execute("""
                        UPDATE artifact_queue
                        SET status = 'EXTRACTED', extracted_at = ?
                        WHERE artifact_id = ?
                    """, (datetime.now(timezone.utc).isoformat(), artifact_id))

                    stats.extracted += 1
                    stats.claims_proposed += result.get("claims", 0)
                    stats.edges_proposed += result.get("edges", 0)

            except Exception as e:
                self._mark_failed(artifact_id, f"Extraction error: {str(e)}")
                stats.extraction_failed += 1

        self.conn.commit()

        # Step 4: Mark DEPRIORITIZE as skipped
        self.skip_deprioritized()

        return stats

    def _process_with_filter_context(
        self,
        nlp_agent,
        artifact_id: str,
        artifact_path: str,
        source_url: str,
        filter_score: float,
        filter_route: str,
        reason_codes: List[str],
        manipulation_flags: List[str],
    ) -> Dict[str, Any]:
        """
        Process artifact with NLP agent, injecting filter context into proposals.

        This is the key integration point - we override the proposal reasoning
        to include filter metadata so reviewers can see WHY content passed triage.
        """
        # Read content
        content = self._read_artifact_content(artifact_path, source_url)
        if not content:
            return {"error": "Could not read content"}

        # Extract using NLP
        extraction = nlp_agent.extract(content)

        if not extraction:
            return {"error": "Extraction returned None"}

        # Enhance extraction with filter context before creating proposals
        # Adjust confidences based on filter route
        for claim in extraction.claims:
            original_conf = claim.confidence

            if filter_route == 'FAST_TRACK':
                # Boost confidence for high-integrity content
                claim.confidence = min(0.95, claim.confidence + 0.1)
            elif filter_route == 'HUMAN_REVIEW':
                # Slight penalty for ambiguous content
                claim.confidence = max(0.3, claim.confidence - 0.05)

            # Add filter context to reasoning
            filter_context = []
            filter_context.append(f"Filter: {filter_route} (score={filter_score:.0f})")
            if reason_codes:
                filter_context.append(f"Evidence: {', '.join(reason_codes[:3])}")
            if manipulation_flags:
                filter_context.append(f"WARN: {', '.join(manipulation_flags)}")

            # Prepend filter context to why
            claim.why = filter_context + claim.why

        for rel in extraction.relations:
            if filter_route == 'FAST_TRACK':
                rel.confidence = min(0.95, rel.confidence + 0.1)
            elif filter_route == 'HUMAN_REVIEW':
                rel.confidence = max(0.3, rel.confidence - 0.05)

            filter_context = [f"Filter: {filter_route} (score={filter_score:.0f})"]
            if reason_codes:
                filter_context.append(f"Evidence: {', '.join(reason_codes[:3])}")
            if manipulation_flags:
                filter_context.append(f"WARN: {', '.join(manipulation_flags)}")

            rel.why = filter_context + rel.why

        # Create proposals with enhanced extraction
        counts = nlp_agent.create_proposals(
            extraction=extraction,
            agent_name="pipeline_orchestrator",
            source_url=source_url or "",
            artifact_path=artifact_path or "",
            artifact_id=artifact_id,
        )

        return counts

    def skip_deprioritized(self) -> int:
        """
        Mark DEPRIORITIZE artifacts as SKIPPED without NLP extraction.

        These are low-integrity content that shouldn't consume extraction resources.
        Returns count of artifacts skipped.
        """
        self.connect()

        result = self.conn.execute("""
            UPDATE artifact_queue
            SET status = 'SKIPPED'
            WHERE status = 'FILTERED'
            AND route = 'DEPRIORITIZE'
        """)

        self.conn.commit()
        return result.rowcount

    def _read_artifact_content(self, artifact_path: str, url: str) -> Optional[str]:
        """Read content from artifact path or URL."""
        if artifact_path:
            try:
                path = Path(artifact_path)
                if path.exists():
                    return path.read_text(encoding='utf-8', errors='ignore')[:50000]
            except Exception:
                pass

        # TODO: Could add URL fetching here if needed
        return None

    def _infer_source_tier(self, source_id: str, content_type: str) -> int:
        """Infer source tier from source_id and content_type."""
        source_id = (source_id or "").lower()
        content_type = (content_type or "").lower()

        # Tier 0: Government primary
        tier0_patterns = ['edgar', 'sec', 'usaspending', 'congress', 'gao',
                          'federal_register', 'tic', 'fec', 'fara', 'scotus']
        if any(p in source_id for p in tier0_patterns):
            return 0

        # Tier 1: Official secondary / journalism
        if content_type in ['rss', 'news'] or 'opensecrets' in source_id:
            return 1

        # Tier 2: Commentary
        if content_type in ['podcast', 'transcript', 'youtube']:
            return 2

        # Default to Tier 2
        return 2

    def _mark_failed(self, artifact_id: str, error_message: str):
        """Mark artifact as failed."""
        self.conn.execute("""
            UPDATE artifact_queue
            SET status = 'FAILED', error_message = ?
            WHERE artifact_id = ?
        """, (error_message[:500], artifact_id))
        self.conn.commit()

    def run(self) -> Dict[str, Any]:
        """Adapter for schedule_runner compatibility.

        Returns results in the same format as FGIPAgent.run().
        """
        stats = self.process_pending_artifacts(batch_size=100)
        return {
            "agent": "pipeline-cycle",
            "artifacts_collected": stats.artifacts_processed,
            "facts_extracted": stats.extracted,
            "claims_proposed": stats.claims_proposed,
            "edges_proposed": stats.edges_proposed,
            "nodes_proposed": 0,
            "errors": [],
            # Pipeline-specific stats
            "filtered": stats.filtered,
            "fast_track": stats.fast_track,
            "human_review": stats.human_review,
            "deprioritized": stats.deprioritized,
            "extraction_failed": stats.extraction_failed,
        }

    def run_with_delta(self) -> Dict[str, Any]:
        """Wrapper for schedule_runner delta tracking.

        PipelineOrchestrator doesn't need delta tracking -
        it processes the artifact_queue which is its own delta mechanism.
        """
        result = self.run()
        result['run_id'] = f"pipeline-cycle-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        result['delta_count'] = result.get('claims_proposed', 0) + result.get('edges_proposed', 0)
        result['delta_hash'] = 'N/A'  # Queue-based, no delta hash needed
        return result

    def get_queue_stats(self) -> Dict[str, Any]:
        """Get current artifact queue statistics."""
        self.connect()

        stats = {}

        # Count by status
        rows = self.conn.execute("""
            SELECT status, COUNT(*) as cnt
            FROM artifact_queue
            GROUP BY status
        """).fetchall()
        stats['by_status'] = {r['status']: r['cnt'] for r in rows}

        # Count by route (for filtered items)
        rows = self.conn.execute("""
            SELECT route, COUNT(*) as cnt
            FROM artifact_queue
            WHERE status = 'FILTERED'
            GROUP BY route
        """).fetchall()
        stats['filtered_by_route'] = {r['route']: r['cnt'] for r in rows}

        # Average filter scores
        row = self.conn.execute("""
            SELECT AVG(filter_score) as avg_score,
                   MIN(filter_score) as min_score,
                   MAX(filter_score) as max_score
            FROM artifact_queue
            WHERE filter_score IS NOT NULL
        """).fetchone()
        stats['filter_scores'] = {
            'avg': row['avg_score'],
            'min': row['min_score'],
            'max': row['max_score'],
        }

        return stats

    def get_queue_status(self) -> QueueStatus:
        """Get current queue status (compatibility method for web/app.py)."""
        self.connect()

        row = self.conn.execute("""
            SELECT
                SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = 'FILTERING' THEN 1 ELSE 0 END) as filtering,
                SUM(CASE WHEN status = 'FILTERED' THEN 1 ELSE 0 END) as filtered,
                SUM(CASE WHEN status = 'EXTRACTING' THEN 1 ELSE 0 END) as extracting,
                SUM(CASE WHEN status = 'EXTRACTED' THEN 1 ELSE 0 END) as extracted,
                SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed
            FROM artifact_queue
        """).fetchone()

        return QueueStatus(
            pending=row['pending'] or 0,
            filtering=row['filtering'] or 0,
            filtered=row['filtered'] or 0,
            extracting=row['extracting'] or 0,
            extracted=row['extracted'] or 0,
            failed=row['failed'] or 0,
        )

    def process_cycle(
        self,
        filter_batch_size: int = 100,
        extract_batch_size: int = 50,
        extract_routes: List[str] = None
    ) -> CycleReport:
        """Run one processing cycle (compatibility method for web/app.py).

        Wraps process_pending_artifacts() with CycleReport return type.
        """
        cycle_id = f"cycle-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        started_at = datetime.now(timezone.utc).isoformat()

        # Get initial state
        status_before = self.get_queue_status()

        # Run the main processing
        batch_size = max(filter_batch_size, extract_batch_size)
        stats = self.process_pending_artifacts(batch_size=batch_size)

        completed_at = datetime.now(timezone.utc).isoformat()

        return CycleReport(
            cycle_id=cycle_id,
            started_at=started_at,
            completed_at=completed_at,
            pending_before=status_before.pending,
            artifacts_filtered=stats.filtered,
            artifacts_extracted=stats.extracted,
            artifacts_failed=stats.extraction_failed,
            fast_track_count=stats.fast_track,
            human_review_count=stats.human_review,
            deprioritize_count=stats.deprioritized,
            claims_created=stats.claims_proposed,
            edges_created=stats.edges_proposed,
            errors=[],
        )


def main():
    """CLI for pipeline orchestrator."""
    import argparse

    parser = argparse.ArgumentParser(description="FGIP Pipeline Orchestrator")
    parser.add_argument("db", type=str, help="Database path")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size")
    parser.add_argument("--stats", action="store_true", help="Show queue stats only")
    parser.add_argument("--json", action="store_true", help="JSON output")

    args = parser.parse_args()

    db = FGIPDatabase(args.db)
    orch = PipelineOrchestrator(db)

    if args.stats:
        stats = orch.get_queue_stats()
        if args.json:
            print(json.dumps(stats, indent=2))
        else:
            print("Artifact Queue Stats:")
            print(f"  By Status: {stats['by_status']}")
            print(f"  Filtered by Route: {stats['filtered_by_route']}")
            print(f"  Filter Scores: {stats['filter_scores']}")
    else:
        result = orch.process_pending_artifacts(batch_size=args.batch_size)
        if args.json:
            print(json.dumps(asdict(result), indent=2))
        else:
            print("=" * 60)
            print("  PIPELINE ORCHESTRATOR RESULTS")
            print("=" * 60)
            print(f"  Artifacts Processed: {result.artifacts_processed}")
            print(f"  Filtered: {result.filtered}")
            print(f"    FAST_TRACK: {result.fast_track}")
            print(f"    HUMAN_REVIEW: {result.human_review}")
            print(f"    DEPRIORITIZE: {result.deprioritized}")
            print(f"  Extracted: {result.extracted}")
            print(f"  Failed: {result.extraction_failed}")
            print(f"  Claims Proposed: {result.claims_proposed}")
            print(f"  Edges Proposed: {result.edges_proposed}")
            print("=" * 60)


if __name__ == "__main__":
    main()
