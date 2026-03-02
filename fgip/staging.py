"""FGIP Staging - CRUD operations for proposed claims/edges and human review.

This module handles:
- Listing pending proposals
- Accepting proposals (promoting to production tables)
- Rejecting proposals (with audit trail)
- Computing correlation metrics
- Promoting edges to higher assertion levels

Key principle: Agents are scribes, not judges.
- "accept" means "safe to store" not "true"
- Inferential edges always start at HYPOTHESIS
- Promotion to INFERENCE/FACT requires explicit action with receipts
"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Any
import sqlite3

from .schema import Claim, ClaimStatus, Source, compute_sha256, INFERENTIAL_EDGE_TYPES


# =============================================================================
# PROVENANCE LOCK - Approval Valve
# =============================================================================

# Agents that are allowed to bypass the provenance lock (intentional bypasses)
BYPASS_ALLOWED_AGENTS = {
    "reasoning-agent",      # Graph inference - no artifact source
    "genius-edge-stager",   # Manual staging tool
    "correction-loader",    # Correction manifest loader
    "gapfill-loader",       # Gap fill manifest loader
}


def validate_proposal_provenance(
    proposal: Dict[str, Any],
    proposal_type: str,
    conn: sqlite3.Connection,
    strict: bool = True
) -> tuple[bool, List[str]]:
    """
    Provenance lock - reject malformed proposals.

    This is the "approval valve" - prevents junk from entering the graph.
    Proposals must have evidence to be approved.

    Args:
        proposal: The proposal dict from get_proposal_by_id
        proposal_type: "claim" or "edge"
        conn: Database connection for node existence checks
        strict: If False, only warn but don't block

    Returns:
        (is_valid, list_of_violations)
    """
    violations = []

    # Check if this is an allowed bypass
    agent_name = proposal.get("agent_name", "").lower()
    bypass_flag = proposal.get("bypass_pipeline", 0)

    if agent_name in BYPASS_ALLOWED_AGENTS or bypass_flag == 1:
        # Intentional bypass - still log but allow
        return (True, [f"BYPASS: {agent_name}"])

    # Check evidence_span (required unless PRIMARY_DOC_LINK_ONLY reason)
    evidence_span = proposal.get("evidence_span")
    reason_codes = proposal.get("reason_codes", "")

    if not evidence_span:
        # Check if PRIMARY_DOC_LINK_ONLY is in reason_codes
        if reason_codes and "PRIMARY_DOC_LINK_ONLY" in reason_codes:
            pass  # Allowed - direct link to primary doc is sufficient
        else:
            violations.append("Missing evidence_span without PRIMARY_DOC_LINK_ONLY reason")

    # Check reason_codes (required for provenance)
    if not reason_codes:
        violations.append("Missing reason_codes")

    # Check se_score (required for quality assessment)
    se_score = proposal.get("se_score")
    if se_score is None:
        violations.append("Missing se_score")
    elif not (0.0 <= float(se_score) <= 1.0):
        violations.append(f"se_score out of range: {se_score}")

    # Check confidence range
    confidence = proposal.get("confidence")
    if confidence is not None:
        try:
            conf_val = float(confidence)
            if not (0.0 <= conf_val <= 1.0):
                violations.append(f"confidence out of range: {confidence}")
        except (TypeError, ValueError):
            violations.append(f"Invalid confidence value: {confidence}")

    # Edge-specific validation
    if proposal_type == "edge":
        from_node = proposal.get("from_node", "")
        to_node = proposal.get("to_node", "")

        if not from_node:
            violations.append("Missing from_node")
        if not to_node:
            violations.append("Missing to_node")

        # Check if nodes exist (prevent orphan creation)
        if from_node:
            row = conn.execute(
                "SELECT node_id FROM nodes WHERE node_id = ?", (from_node,)
            ).fetchone()
            if not row:
                violations.append(f"from_node does not exist: {from_node}")

        if to_node:
            row = conn.execute(
                "SELECT node_id FROM nodes WHERE node_id = ?", (to_node,)
            ).fetchone()
            if not row:
                violations.append(f"to_node does not exist: {to_node}")

    is_valid = len(violations) == 0
    return (is_valid, violations)


def get_next_proposal_id(conn: sqlite3.Connection, agent_name: str = "manual",
                         content_hash: Optional[str] = None) -> str:
    """Get deterministic proposal ID with agent name and content hash.

    Format: FGIP-PROPOSED-{agent}-{YYYYMMDD}-{shortsha}

    Args:
        conn: Database connection
        agent_name: Name of the proposing agent
        content_hash: SHA256 of canonical proposal content (prevents duplicates)

    Returns:
        Unique proposal ID
    """
    date_str = datetime.utcnow().strftime("%Y%m%d")

    if content_hash:
        short_sha = content_hash[:10]
    else:
        # Fallback to counter-based ID
        row = conn.execute("SELECT next_proposal_num FROM proposal_counter WHERE id = 1").fetchone()
        num = row[0] if row else 1
        conn.execute("UPDATE proposal_counter SET next_proposal_num = ? WHERE id = 1", (num + 1,))
        conn.commit()
        short_sha = f"{num:06d}"

    return f"FGIP-PROPOSED-{agent_name.upper()}-{date_str}-{short_sha}"


def compute_proposal_hash(proposal_data: Dict[str, Any]) -> str:
    """Compute content hash for a proposal to detect duplicates.

    Args:
        proposal_data: Dict with proposal fields

    Returns:
        SHA256 hash of canonical JSON
    """
    # Extract only the content fields, not metadata
    content_fields = {
        k: v for k, v in proposal_data.items()
        if k not in ("proposal_id", "created_at", "resolved_at", "status",
                     "resolved_claim_id", "resolved_edge_id", "reviewer_notes")
    }
    return compute_sha256(content_fields)


def get_pending_proposals(conn: sqlite3.Connection, agent_name: Optional[str] = None,
                          proposal_type: Optional[str] = None) -> Dict[str, List[Dict]]:
    """Get all pending proposals, optionally filtered by agent or type.

    Args:
        conn: Database connection
        agent_name: Filter by agent name (optional)
        proposal_type: Filter by 'claim' or 'edge' (optional)

    Returns:
        Dict with 'claims' and 'edges' lists
    """
    result = {"claims": [], "edges": []}

    # Get pending claims
    if proposal_type is None or proposal_type == "claim":
        query = "SELECT * FROM proposed_claims WHERE status = 'PENDING'"
        params = []
        if agent_name:
            query += " AND agent_name = ?"
            params.append(agent_name)
        query += " ORDER BY created_at DESC"

        rows = conn.execute(query, params).fetchall()
        result["claims"] = [dict(row) for row in rows]

    # Get pending edges
    if proposal_type is None or proposal_type == "edge":
        query = "SELECT * FROM proposed_edges WHERE status = 'PENDING'"
        params = []
        if agent_name:
            query += " AND agent_name = ?"
            params.append(agent_name)
        query += " ORDER BY created_at DESC"

        rows = conn.execute(query, params).fetchall()
        result["edges"] = [dict(row) for row in rows]

    return result


def get_all_proposals(conn: sqlite3.Connection, agent_name: Optional[str] = None,
                      status: Optional[str] = None) -> Dict[str, List[Dict]]:
    """Get all proposals with optional filters.

    Args:
        conn: Database connection
        agent_name: Filter by agent name (optional)
        status: Filter by status (PENDING, APPROVED, REJECTED)

    Returns:
        Dict with 'claims' and 'edges' lists
    """
    result = {"claims": [], "edges": []}

    # Get claims
    query = "SELECT * FROM proposed_claims WHERE 1=1"
    params = []
    if agent_name:
        query += " AND agent_name = ?"
        params.append(agent_name)
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC"

    rows = conn.execute(query, params).fetchall()
    result["claims"] = [dict(row) for row in rows]

    # Get edges
    query = "SELECT * FROM proposed_edges WHERE 1=1"
    params = []
    if agent_name:
        query += " AND agent_name = ?"
        params.append(agent_name)
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC"

    rows = conn.execute(query, params).fetchall()
    result["edges"] = [dict(row) for row in rows]

    return result


def get_proposal_by_id(conn: sqlite3.Connection, proposal_id: str) -> Optional[Dict]:
    """Get a proposal by its ID.

    Args:
        conn: Database connection
        proposal_id: The proposal ID

    Returns:
        Dict with proposal data and 'type' field ('claim' or 'edge'), or None
    """
    # Check claims first
    row = conn.execute(
        "SELECT * FROM proposed_claims WHERE proposal_id = ?",
        (proposal_id,)
    ).fetchone()
    if row:
        data = dict(row)
        data["type"] = "claim"
        return data

    # Check edges
    row = conn.execute(
        "SELECT * FROM proposed_edges WHERE proposal_id = ?",
        (proposal_id,)
    ).fetchone()
    if row:
        data = dict(row)
        data["type"] = "edge"
        return data

    return None


def accept_claim(conn: sqlite3.Connection, proposal_id: str,
                 reviewer_notes: Optional[str] = None,
                 reviewer: Optional[str] = None,
                 skip_provenance_check: bool = False) -> Optional[str]:
    """Accept a proposed claim and promote to production.

    Args:
        conn: Database connection
        proposal_id: The proposal to accept
        reviewer_notes: Notes from the reviewer
        reviewer: Reviewer identifier
        skip_provenance_check: If True, bypass provenance validation (use sparingly)

    Returns:
        New claim_id if successful, None otherwise

    Raises:
        ValueError: If proposal fails provenance validation
    """
    # Get the proposal
    proposal = get_proposal_by_id(conn, proposal_id)
    if not proposal or proposal["type"] != "claim":
        return None
    if proposal["status"] != "PENDING":
        return None

    # PROVENANCE LOCK: Validate before approval
    if not skip_provenance_check:
        is_valid, violations = validate_proposal_provenance(proposal, "claim", conn)
        if not is_valid:
            # Log the rejection to audit trail
            conn.execute(
                """INSERT INTO review_audit
                   (proposal_type, proposal_id, decision, reviewer, notes, timestamp)
                   VALUES ('claim', ?, 'REJECTED', 'provenance_lock', ?, ?)""",
                (proposal_id, f"Provenance violations: {violations}",
                 datetime.utcnow().isoformat() + "Z")
            )
            conn.commit()
            raise ValueError(f"Proposal failed provenance lock: {violations}")

    # Get next claim ID
    row = conn.execute("SELECT next_claim_num FROM claim_counter WHERE id = 1").fetchone()
    num = row[0] if row else 1
    conn.execute("UPDATE claim_counter SET next_claim_num = ? WHERE id = 1", (num + 1,))
    claim_id = f"FGIP-{num:06d}"

    # Determine claim status based on source
    status = "PARTIAL"
    if proposal["source_url"]:
        status = "PARTIAL"
        if proposal["artifact_path"] and proposal["artifact_hash"]:
            status = "EVIDENCED"

    # Insert into production claims table
    conn.execute(
        """INSERT INTO claims
           (claim_id, claim_text, topic, status, required_tier, created_at, notes)
           VALUES (?, ?, ?, ?, 1, ?, ?)""",
        (claim_id, proposal["claim_text"], proposal["topic"], status,
         datetime.utcnow().isoformat() + "Z",
         f"Promoted from {proposal_id}. Agent: {proposal['agent_name']}. {reviewer_notes or ''}")
    )

    # If source URL exists, create source and link
    if proposal["source_url"]:
        source_id = compute_sha256(proposal["source_url"])
        conn.execute(
            """INSERT OR IGNORE INTO sources
               (source_id, url, domain, tier, retrieved_at, artifact_path, artifact_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (source_id, proposal["source_url"], None, 2,
             datetime.utcnow().isoformat() + "Z",
             proposal["artifact_path"], proposal["artifact_hash"])
        )
        conn.execute(
            "INSERT OR IGNORE INTO claim_sources (claim_id, source_id) VALUES (?, ?)",
            (claim_id, source_id)
        )

    # Update proposal status
    conn.execute(
        """UPDATE proposed_claims
           SET status = 'APPROVED', resolved_claim_id = ?, resolved_at = ?, reviewer_notes = ?
           WHERE proposal_id = ?""",
        (claim_id, datetime.utcnow().isoformat() + "Z", reviewer_notes, proposal_id)
    )

    # Record audit trail
    conn.execute(
        """INSERT INTO review_audit
           (proposal_type, proposal_id, decision, reviewer, notes, timestamp)
           VALUES ('claim', ?, 'APPROVED', ?, ?, ?)""",
        (proposal_id, reviewer, reviewer_notes, datetime.utcnow().isoformat() + "Z")
    )

    conn.commit()
    return claim_id


def accept_edge(conn: sqlite3.Connection, proposal_id: str,
                reviewer_notes: Optional[str] = None,
                reviewer: Optional[str] = None,
                skip_provenance_check: bool = False) -> Optional[int]:
    """Accept a proposed edge and promote to production.

    IMPORTANT: "Accept" means "safe to store," NOT "true."
    - Inferential edge types (ENABLED, CAUSED, etc.) are ALWAYS created as HYPOTHESIS
    - Factual edge types (OWNS_SHARES, MARRIED_TO, etc.) are created as FACT
    - To upgrade HYPOTHESIS → INFERENCE → FACT, use promote_edge()

    Args:
        conn: Database connection
        proposal_id: The proposal to accept
        reviewer_notes: Notes from the reviewer
        reviewer: Reviewer identifier
        skip_provenance_check: If True, bypass provenance validation (use sparingly)

    Returns:
        New edge_id if successful, None otherwise

    Raises:
        ValueError: If proposal fails provenance validation
    """
    # Get the proposal
    proposal = get_proposal_by_id(conn, proposal_id)
    if not proposal or proposal["type"] != "edge":
        return None
    if proposal["status"] != "PENDING":
        return None

    # PROVENANCE LOCK: Validate before approval
    if not skip_provenance_check:
        is_valid, violations = validate_proposal_provenance(proposal, "edge", conn)
        if not is_valid:
            # Log the rejection to audit trail
            conn.execute(
                """INSERT INTO review_audit
                   (proposal_type, proposal_id, decision, reviewer, notes, timestamp)
                   VALUES ('edge', ?, 'REJECTED', 'provenance_lock', ?, ?)""",
                (proposal_id, f"Provenance violations: {violations}",
                 datetime.utcnow().isoformat() + "Z")
            )
            conn.commit()
            raise ValueError(f"Proposal failed provenance lock: {violations}")

    # Resolve the backing claim if it's a proposed claim
    claim_id = None
    if proposal["proposed_claim_id"]:
        claim_proposal = get_proposal_by_id(conn, proposal["proposed_claim_id"])
        if claim_proposal and claim_proposal["status"] == "APPROVED":
            claim_id = claim_proposal.get("resolved_claim_id")
        elif claim_proposal and claim_proposal["status"] == "PENDING":
            # Auto-accept the backing claim
            claim_id = accept_claim(conn, proposal["proposed_claim_id"], reviewer_notes, reviewer)

    # Generate edge ID
    edge_id = f"edge_{proposal['relationship'].lower()}_{proposal['from_node'][:15]}_{proposal['to_node'][:15]}"

    # CRITICAL: Determine assertion level based on edge type
    # Inferential edges MUST start as HYPOTHESIS (agents are scribes, not judges)
    # Factual edges can be FACT if the relationship is inherently factual
    relationship = proposal["relationship"]
    if relationship in INFERENTIAL_EDGE_TYPES:
        assertion_level = "HYPOTHESIS"
    else:
        # Factual edge types (OWNS_SHARES, MARRIED_TO, etc.) can be FACT
        # but only if backed by a claim - otherwise still HYPOTHESIS
        assertion_level = "FACT" if claim_id else "HYPOTHESIS"

    # Insert into production edges table
    conn.execute(
        """INSERT INTO edges
           (edge_id, edge_type, from_node_id, to_node_id, claim_id, assertion_level,
            confidence, notes, metadata, created_at, sha256)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (edge_id, relationship, proposal["from_node"], proposal["to_node"],
         claim_id, assertion_level, proposal["confidence"],
         f"Promoted from {proposal_id}. Agent: {proposal['agent_name']}. {reviewer_notes or ''}",
         json.dumps({"agent": proposal["agent_name"], "detail": proposal["detail"],
                     "original_assertion": "HYPOTHESIS"}),
         datetime.utcnow().isoformat() + "Z",
         compute_sha256(edge_id + proposal["from_node"] + proposal["to_node"]))
    )

    # Get the rowid
    row = conn.execute("SELECT last_insert_rowid()").fetchone()
    resolved_edge_id = row[0] if row else None

    # Update proposal status
    conn.execute(
        """UPDATE proposed_edges
           SET status = 'APPROVED', resolved_edge_id = ?, resolved_at = ?, reviewer_notes = ?
           WHERE proposal_id = ?""",
        (resolved_edge_id, datetime.utcnow().isoformat() + "Z", reviewer_notes, proposal_id)
    )

    # Record audit trail
    conn.execute(
        """INSERT INTO review_audit
           (proposal_type, proposal_id, decision, reviewer, notes, timestamp)
           VALUES ('edge', ?, 'APPROVED', ?, ?, ?)""",
        (proposal_id, reviewer, reviewer_notes, datetime.utcnow().isoformat() + "Z")
    )

    conn.commit()
    return resolved_edge_id


def promote_edge(conn: sqlite3.Connection, edge_id: str, to_level: str,
                 claim_id: str, receipt_hash: Optional[str] = None,
                 reviewer: Optional[str] = None,
                 notes: Optional[str] = None) -> bool:
    """Promote an edge to a higher assertion level.

    This is a deliberate action requiring explicit justification.
    Promotion path: HYPOTHESIS → INFERENCE → FACT

    Args:
        conn: Database connection
        edge_id: The edge to promote
        to_level: Target assertion level (INFERENCE or FACT)
        claim_id: Claim ID that justifies the promotion
        receipt_hash: Optional receipt/artifact hash as proof
        reviewer: Who is doing the promotion
        notes: Justification notes

    Returns:
        True if successful, False otherwise
    """
    if to_level not in ("INFERENCE", "FACT"):
        return False

    # Get current edge
    row = conn.execute(
        "SELECT edge_id, assertion_level, edge_type, claim_id FROM edges WHERE edge_id = ?",
        (edge_id,)
    ).fetchone()

    if not row:
        return False

    current_level = row["assertion_level"]
    edge_type = row["edge_type"]

    # Validate promotion path
    level_order = {"HYPOTHESIS": 0, "INFERENCE": 1, "FACT": 2}
    if level_order.get(to_level, 0) <= level_order.get(current_level, 0):
        return False  # Can't demote or stay same

    # FACT promotion for inferential edges requires explicit override
    if to_level == "FACT" and edge_type in INFERENTIAL_EDGE_TYPES:
        if not receipt_hash:
            return False  # Require artifact hash for FACT on inferential edges

    # Verify the claim exists and has adequate sourcing
    claim_row = conn.execute(
        "SELECT status FROM claims WHERE claim_id = ?",
        (claim_id,)
    ).fetchone()

    if not claim_row:
        return False

    # For FACT promotion, claim should be at least EVIDENCED
    if to_level == "FACT" and claim_row["status"] not in ("EVIDENCED", "VERIFIED"):
        return False

    # Update edge
    conn.execute(
        """UPDATE edges
           SET assertion_level = ?, claim_id = ?,
               notes = COALESCE(notes, '') || '\n[PROMOTED ' || ? || ' → ' || ? || '] ' || ?
           WHERE edge_id = ?""",
        (to_level, claim_id, current_level, to_level, notes or "", edge_id)
    )

    # Record audit trail
    conn.execute(
        """INSERT INTO review_audit
           (proposal_type, proposal_id, decision, reviewer, notes, timestamp)
           VALUES ('edge_promotion', ?, ?, ?, ?, ?)""",
        (edge_id, f"PROMOTED:{current_level}→{to_level}",
         reviewer, f"claim={claim_id}, receipt={receipt_hash}, {notes or ''}",
         datetime.utcnow().isoformat() + "Z")
    )

    conn.commit()
    return True


def reject_proposal(conn: sqlite3.Connection, proposal_id: str,
                    reason: str, reviewer: Optional[str] = None) -> bool:
    """Reject a proposal with explanation.

    Args:
        conn: Database connection
        proposal_id: The proposal to reject
        reason: Reason for rejection (required)
        reviewer: Reviewer identifier

    Returns:
        True if successful, False otherwise
    """
    proposal = get_proposal_by_id(conn, proposal_id)
    if not proposal:
        return False
    if proposal["status"] != "PENDING":
        return False

    table = "proposed_claims" if proposal["type"] == "claim" else "proposed_edges"

    conn.execute(
        f"""UPDATE {table}
            SET status = 'REJECTED', resolved_at = ?, reviewer_notes = ?
            WHERE proposal_id = ?""",
        (datetime.utcnow().isoformat() + "Z", reason, proposal_id)
    )

    # Record audit trail
    conn.execute(
        """INSERT INTO review_audit
           (proposal_type, proposal_id, decision, reviewer, notes, timestamp)
           VALUES (?, ?, 'REJECTED', ?, ?, ?)""",
        (proposal["type"], proposal_id, reviewer, reason, datetime.utcnow().isoformat() + "Z")
    )

    conn.commit()
    return True


def compute_correlation_metrics(conn: sqlite3.Connection, proposal_id: str) -> Dict[str, Any]:
    """Compute correlation metrics for a proposal.

    Metrics computed:
    - source_overlap: Do entities repeatedly appear in same sources? (0-1)
    - temporal_proximity: Did events occur in tight window? (days apart)
    - path_distance: Graph distance between entities (hops)
    - convergence_score: How many signal categories confirm? (0-6)

    Args:
        conn: Database connection
        proposal_id: The proposal to analyze

    Returns:
        Dict with computed metrics
    """
    proposal = get_proposal_by_id(conn, proposal_id)
    if not proposal:
        return {"error": "Proposal not found"}

    metrics = {
        "proposal_id": proposal_id,
        "proposal_type": proposal["type"],
        "metrics": {}
    }

    if proposal["type"] == "edge":
        from_node = proposal["from_node"]
        to_node = proposal["to_node"]

        # Source overlap: Check if both nodes appear in same claims
        overlap_count = conn.execute(
            """SELECT COUNT(DISTINCT e1.claim_id) FROM edges e1
               JOIN edges e2 ON e1.claim_id = e2.claim_id
               WHERE e1.from_node_id = ? AND e2.from_node_id = ?""",
            (from_node, to_node)
        ).fetchone()[0]

        total_claims_from = conn.execute(
            "SELECT COUNT(DISTINCT claim_id) FROM edges WHERE from_node_id = ? OR to_node_id = ?",
            (from_node, from_node)
        ).fetchone()[0]

        source_overlap = overlap_count / max(total_claims_from, 1)
        metrics["metrics"]["source_overlap"] = round(source_overlap, 3)

        # Path distance: BFS to find shortest path
        path_distance = _compute_path_distance(conn, from_node, to_node)
        metrics["metrics"]["path_distance"] = path_distance

        # Convergence score: Count unique edge types between nodes
        edge_types = conn.execute(
            """SELECT COUNT(DISTINCT edge_type) FROM edges
               WHERE (from_node_id = ? AND to_node_id = ?)
                  OR (from_node_id = ? AND to_node_id = ?)""",
            (from_node, to_node, to_node, from_node)
        ).fetchone()[0]

        metrics["metrics"]["convergence_score"] = edge_types

        # Store metrics
        for metric_type, value in metrics["metrics"].items():
            conn.execute(
                """INSERT INTO correlation_metrics
                   (proposal_id, metric_type, metric_value, details, computed_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (proposal_id, metric_type, value,
                 json.dumps({"from_node": from_node, "to_node": to_node}),
                 datetime.utcnow().isoformat() + "Z")
            )

        conn.commit()

    elif proposal["type"] == "claim":
        # For claims, compute simpler metrics
        # Check if similar claims exist
        claim_text = proposal["claim_text"]
        words = claim_text.lower().split()[:5]  # First 5 words
        pattern = "%".join(words)

        similar_count = conn.execute(
            "SELECT COUNT(*) FROM claims WHERE claim_text LIKE ?",
            (f"%{pattern}%",)
        ).fetchone()[0]

        metrics["metrics"]["similar_claims"] = similar_count

        # Store metric
        conn.execute(
            """INSERT INTO correlation_metrics
               (proposal_id, metric_type, metric_value, details, computed_at)
               VALUES (?, 'similar_claims', ?, ?, ?)""",
            (proposal_id, similar_count,
             json.dumps({"pattern": pattern}),
             datetime.utcnow().isoformat() + "Z")
        )

        conn.commit()

    return metrics


def _compute_path_distance(conn: sqlite3.Connection, from_node: str, to_node: str,
                           max_depth: int = 6) -> int:
    """Compute shortest path distance between two nodes using BFS.

    Returns:
        Number of hops, or -1 if no path found within max_depth
    """
    if from_node == to_node:
        return 0

    visited = {from_node}
    queue = [(from_node, 0)]

    while queue:
        current, depth = queue.pop(0)

        if depth >= max_depth:
            continue

        # Get all neighbors
        neighbors = conn.execute(
            """SELECT DISTINCT to_node_id FROM edges WHERE from_node_id = ?
               UNION
               SELECT DISTINCT from_node_id FROM edges WHERE to_node_id = ?""",
            (current, current)
        ).fetchall()

        for (neighbor,) in neighbors:
            if neighbor == to_node:
                return depth + 1
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, depth + 1))

    return -1  # No path found


def get_agent_stats(conn: sqlite3.Connection) -> Dict[str, Dict[str, int]]:
    """Get proposal statistics grouped by agent.

    Returns:
        Dict mapping agent_name to counts by status
    """
    stats = {}

    # Claims by agent
    rows = conn.execute(
        """SELECT agent_name, status, COUNT(*) as count
           FROM proposed_claims
           GROUP BY agent_name, status"""
    ).fetchall()

    for row in rows:
        agent = row["agent_name"]
        if agent not in stats:
            stats[agent] = {"pending_claims": 0, "approved_claims": 0, "rejected_claims": 0,
                           "pending_edges": 0, "approved_edges": 0, "rejected_edges": 0}
        status_key = f"{row['status'].lower()}_claims"
        stats[agent][status_key] = row["count"]

    # Edges by agent
    rows = conn.execute(
        """SELECT agent_name, status, COUNT(*) as count
           FROM proposed_edges
           GROUP BY agent_name, status"""
    ).fetchall()

    for row in rows:
        agent = row["agent_name"]
        if agent not in stats:
            stats[agent] = {"pending_claims": 0, "approved_claims": 0, "rejected_claims": 0,
                           "pending_edges": 0, "approved_edges": 0, "rejected_edges": 0}
        status_key = f"{row['status'].lower()}_edges"
        stats[agent][status_key] = row["count"]

    return stats
