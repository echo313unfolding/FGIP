"""Evidence graph staging — CRUD for proposed claims/edges and human review.

Domain-agnostic extraction of fgip/staging.py. All domain-specific behavior
(ID prefixes, inferential edge classification, bypass agents) is delegated
to a DomainRegistry passed at call sites.

Key principle: Agents are scribes, not judges.
- "accept" means "safe to store" not "true"
- Inferential edges always start at HYPOTHESIS
- Promotion to INFERENCE/FACT requires explicit action with receipts
"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Any
import sqlite3

from .schema import Claim, ClaimStatus, Source, compute_sha256
from .registry import DomainRegistry


# =============================================================================
# PROVENANCE LOCK - Approval Valve
# =============================================================================

def validate_proposal_provenance(
    proposal: Dict[str, Any],
    proposal_type: str,
    conn: sqlite3.Connection,
    bypass_agents: set[str] | None = None,
    strict: bool = True,
) -> tuple[bool, List[str]]:
    """
    Provenance lock — reject malformed proposals.

    Args:
        proposal: The proposal dict from get_proposal_by_id
        proposal_type: "claim" or "edge"
        conn: Database connection for node existence checks
        bypass_agents: Set of agent names allowed to bypass provenance
        strict: If False, only warn but don't block

    Returns:
        (is_valid, list_of_violations)
    """
    violations = []
    bypass_agents = bypass_agents or set()

    # Check if this is an allowed bypass
    agent_name = proposal.get("agent_name", "").lower()
    bypass_flag = proposal.get("bypass_pipeline", 0)

    if agent_name in bypass_agents or bypass_flag == 1:
        return (True, [f"BYPASS: {agent_name}"])

    # Check evidence_span (required unless PRIMARY_DOC_LINK_ONLY reason)
    evidence_span = proposal.get("evidence_span")
    reason_codes = proposal.get("reason_codes", "")

    if not evidence_span:
        if reason_codes and "PRIMARY_DOC_LINK_ONLY" in reason_codes:
            pass  # Direct link to primary doc is sufficient
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


def get_next_proposal_id(
    conn: sqlite3.Connection,
    registry: DomainRegistry,
    agent_name: str = "manual",
    content_hash: Optional[str] = None,
) -> str:
    """Get deterministic proposal ID with domain prefix.

    Format: {PREFIX}-PROPOSED-{AGENT}-{YYYYMMDD}-{shortsha}
    """
    date_str = datetime.utcnow().strftime("%Y%m%d")

    if content_hash:
        short_sha = content_hash[:10]
    else:
        row = conn.execute(
            "SELECT next_proposal_num FROM proposal_counter WHERE id = 1"
        ).fetchone()
        num = row[0] if row else 1
        conn.execute(
            "UPDATE proposal_counter SET next_proposal_num = ? WHERE id = 1",
            (num + 1,),
        )
        conn.commit()
        short_sha = f"{num:06d}"

    return registry.format_proposal_id(agent_name, date_str, short_sha)


def compute_proposal_hash(proposal_data: Dict[str, Any]) -> str:
    """Compute content hash for a proposal to detect duplicates."""
    content_fields = {
        k: v for k, v in proposal_data.items()
        if k not in ("proposal_id", "created_at", "resolved_at", "status",
                     "resolved_claim_id", "resolved_edge_id", "reviewer_notes")
    }
    return compute_sha256(content_fields)


def get_pending_proposals(
    conn: sqlite3.Connection,
    agent_name: Optional[str] = None,
    proposal_type: Optional[str] = None,
) -> Dict[str, List[Dict]]:
    """Get all pending proposals, optionally filtered by agent or type."""
    result = {"claims": [], "edges": []}

    if proposal_type is None or proposal_type == "claim":
        query = "SELECT * FROM proposed_claims WHERE status = 'PENDING'"
        params = []
        if agent_name:
            query += " AND agent_name = ?"
            params.append(agent_name)
        query += " ORDER BY created_at DESC"
        rows = conn.execute(query, params).fetchall()
        result["claims"] = [dict(row) for row in rows]

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


def get_all_proposals(
    conn: sqlite3.Connection,
    agent_name: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, List[Dict]]:
    """Get all proposals with optional filters."""
    result = {"claims": [], "edges": []}

    for table, key in [("proposed_claims", "claims"), ("proposed_edges", "edges")]:
        query = f"SELECT * FROM {table} WHERE 1=1"
        params = []
        if agent_name:
            query += " AND agent_name = ?"
            params.append(agent_name)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"
        rows = conn.execute(query, params).fetchall()
        result[key] = [dict(row) for row in rows]

    return result


def get_proposal_by_id(
    conn: sqlite3.Connection, proposal_id: str
) -> Optional[Dict]:
    """Get a proposal by its ID. Returns dict with 'type' field or None."""
    row = conn.execute(
        "SELECT * FROM proposed_claims WHERE proposal_id = ?",
        (proposal_id,),
    ).fetchone()
    if row:
        data = dict(row)
        data["type"] = "claim"
        return data

    row = conn.execute(
        "SELECT * FROM proposed_edges WHERE proposal_id = ?",
        (proposal_id,),
    ).fetchone()
    if row:
        data = dict(row)
        data["type"] = "edge"
        return data

    return None


def accept_claim(
    conn: sqlite3.Connection,
    registry: DomainRegistry,
    proposal_id: str,
    reviewer_notes: Optional[str] = None,
    reviewer: Optional[str] = None,
    bypass_agents: set[str] | None = None,
    skip_provenance_check: bool = False,
) -> Optional[str]:
    """Accept a proposed claim and promote to production.

    Returns new claim_id if successful, None otherwise.
    Raises ValueError if proposal fails provenance validation.
    """
    proposal = get_proposal_by_id(conn, proposal_id)
    if not proposal or proposal["type"] != "claim":
        return None
    if proposal["status"] != "PENDING":
        return None

    # PROVENANCE LOCK
    if not skip_provenance_check:
        is_valid, violations = validate_proposal_provenance(
            proposal, "claim", conn, bypass_agents=bypass_agents
        )
        if not is_valid:
            conn.execute(
                """INSERT INTO review_audit
                   (proposal_type, proposal_id, decision, reviewer, notes, timestamp)
                   VALUES ('claim', ?, 'REJECTED', 'provenance_lock', ?, ?)""",
                (proposal_id, f"Provenance violations: {violations}",
                 datetime.utcnow().isoformat() + "Z"),
            )
            conn.commit()
            raise ValueError(f"Proposal failed provenance lock: {violations}")

    # Get next claim ID via registry prefix
    row = conn.execute(
        "SELECT next_claim_num FROM claim_counter WHERE id = 1"
    ).fetchone()
    num = row[0] if row else 1
    conn.execute(
        "UPDATE claim_counter SET next_claim_num = ? WHERE id = 1", (num + 1,)
    )
    claim_id = registry.format_claim_id(num)

    # Determine claim status
    status = "PARTIAL"
    if proposal.get("source_url"):
        status = "PARTIAL"
        if proposal.get("artifact_path") and proposal.get("artifact_hash"):
            status = "EVIDENCED"

    now = datetime.utcnow().isoformat() + "Z"

    conn.execute(
        """INSERT INTO claims
           (claim_id, claim_text, topic, status, required_tier, created_at, notes)
           VALUES (?, ?, ?, ?, 1, ?, ?)""",
        (claim_id, proposal["claim_text"], proposal["topic"], status,
         now,
         f"Promoted from {proposal_id}. Agent: {proposal['agent_name']}. {reviewer_notes or ''}"),
    )

    # Create source if URL exists
    if proposal.get("source_url"):
        source_id = compute_sha256(proposal["source_url"])
        conn.execute(
            """INSERT OR IGNORE INTO sources
               (source_id, url, domain, tier, retrieved_at, artifact_path, artifact_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (source_id, proposal["source_url"], None, 2,
             now, proposal.get("artifact_path"), proposal.get("artifact_hash")),
        )
        conn.execute(
            "INSERT OR IGNORE INTO claim_sources (claim_id, source_id) VALUES (?, ?)",
            (claim_id, source_id),
        )

    conn.execute(
        """UPDATE proposed_claims
           SET status = 'APPROVED', resolved_claim_id = ?, resolved_at = ?, reviewer_notes = ?
           WHERE proposal_id = ?""",
        (claim_id, now, reviewer_notes, proposal_id),
    )

    conn.execute(
        """INSERT INTO review_audit
           (proposal_type, proposal_id, decision, reviewer, notes, timestamp)
           VALUES ('claim', ?, 'APPROVED', ?, ?, ?)""",
        (proposal_id, reviewer, reviewer_notes, now),
    )

    conn.commit()
    return claim_id


def accept_edge(
    conn: sqlite3.Connection,
    registry: DomainRegistry,
    proposal_id: str,
    reviewer_notes: Optional[str] = None,
    reviewer: Optional[str] = None,
    bypass_agents: set[str] | None = None,
    skip_provenance_check: bool = False,
) -> Optional[int]:
    """Accept a proposed edge and promote to production.

    "Accept" means "safe to store," NOT "true."
    - Inferential edge types are ALWAYS created as HYPOTHESIS
    - Factual edge types are created as FACT (if backed by claim)
    - To upgrade HYPOTHESIS -> INFERENCE -> FACT, use promote_edge()

    Returns new edge_id (rowid) if successful, None otherwise.
    """
    proposal = get_proposal_by_id(conn, proposal_id)
    if not proposal or proposal["type"] != "edge":
        return None
    if proposal["status"] != "PENDING":
        return None

    # PROVENANCE LOCK
    if not skip_provenance_check:
        is_valid, violations = validate_proposal_provenance(
            proposal, "edge", conn, bypass_agents=bypass_agents
        )
        if not is_valid:
            conn.execute(
                """INSERT INTO review_audit
                   (proposal_type, proposal_id, decision, reviewer, notes, timestamp)
                   VALUES ('edge', ?, 'REJECTED', 'provenance_lock', ?, ?)""",
                (proposal_id, f"Provenance violations: {violations}",
                 datetime.utcnow().isoformat() + "Z"),
            )
            conn.commit()
            raise ValueError(f"Proposal failed provenance lock: {violations}")

    # Resolve backing claim
    claim_id = None
    if proposal.get("proposed_claim_id"):
        claim_proposal = get_proposal_by_id(conn, proposal["proposed_claim_id"])
        if claim_proposal and claim_proposal["status"] == "APPROVED":
            claim_id = claim_proposal.get("resolved_claim_id")
        elif claim_proposal and claim_proposal["status"] == "PENDING":
            claim_id = accept_claim(
                conn, registry, proposal["proposed_claim_id"],
                reviewer_notes, reviewer, bypass_agents,
            )

    # Generate edge ID
    edge_id = (
        f"edge_{proposal['relationship'].lower()}_"
        f"{proposal['from_node'][:15]}_{proposal['to_node'][:15]}"
    )

    # Assertion level via registry (not hardcoded enum set)
    relationship = proposal["relationship"]
    if registry.is_inferential(relationship):
        assertion_level = "HYPOTHESIS"
    else:
        assertion_level = "FACT" if claim_id else "HYPOTHESIS"

    now = datetime.utcnow().isoformat() + "Z"

    existing = conn.execute(
        "SELECT rowid FROM edges WHERE edge_id = ?", (edge_id,)
    ).fetchone()

    if existing:
        resolved_edge_id = existing[0]
    else:
        conn.execute(
            """INSERT INTO edges
               (edge_id, edge_type, from_node_id, to_node_id, claim_id, assertion_level,
                confidence, notes, metadata, created_at, sha256)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (edge_id, relationship, proposal["from_node"], proposal["to_node"],
             claim_id, assertion_level, proposal["confidence"],
             f"Promoted from {proposal_id}. Agent: {proposal['agent_name']}. {reviewer_notes or ''}",
             json.dumps({"agent": proposal["agent_name"], "detail": proposal.get("detail"),
                         "original_assertion": "HYPOTHESIS"}),
             now,
             compute_sha256(edge_id + proposal["from_node"] + proposal["to_node"])),
        )
        row = conn.execute("SELECT last_insert_rowid()").fetchone()
        resolved_edge_id = row[0] if row else None

    conn.execute(
        """UPDATE proposed_edges
           SET status = 'APPROVED', resolved_edge_id = ?, resolved_at = ?, reviewer_notes = ?
           WHERE proposal_id = ?""",
        (resolved_edge_id, now, reviewer_notes, proposal_id),
    )

    conn.execute(
        """INSERT INTO review_audit
           (proposal_type, proposal_id, decision, reviewer, notes, timestamp)
           VALUES ('edge', ?, 'APPROVED', ?, ?, ?)""",
        (proposal_id, reviewer, reviewer_notes, now),
    )

    conn.commit()
    return resolved_edge_id


def promote_edge(
    conn: sqlite3.Connection,
    registry: DomainRegistry,
    edge_id: str,
    to_level: str,
    claim_id: str,
    receipt_hash: Optional[str] = None,
    reviewer: Optional[str] = None,
    notes: Optional[str] = None,
) -> bool:
    """Promote an edge to a higher assertion level.

    Promotion path: HYPOTHESIS -> INFERENCE -> FACT
    """
    if to_level not in ("INFERENCE", "FACT"):
        return False

    row = conn.execute(
        "SELECT edge_id, assertion_level, edge_type, claim_id FROM edges WHERE edge_id = ?",
        (edge_id,),
    ).fetchone()
    if not row:
        return False

    current_level = row["assertion_level"]
    edge_type = row["edge_type"]

    level_order = {"HYPOTHESIS": 0, "INFERENCE": 1, "FACT": 2}
    if level_order.get(to_level, 0) <= level_order.get(current_level, 0):
        return False

    # FACT promotion for inferential edges requires receipt
    if to_level == "FACT" and registry.is_inferential(edge_type):
        if not receipt_hash:
            return False

    claim_row = conn.execute(
        "SELECT status FROM claims WHERE claim_id = ?", (claim_id,)
    ).fetchone()
    if not claim_row:
        return False

    if to_level == "FACT" and claim_row["status"] not in ("EVIDENCED", "VERIFIED"):
        return False

    conn.execute(
        """UPDATE edges
           SET assertion_level = ?, claim_id = ?,
               notes = COALESCE(notes, '') || '\n[PROMOTED ' || ? || ' → ' || ? || '] ' || ?
           WHERE edge_id = ?""",
        (to_level, claim_id, current_level, to_level, notes or "", edge_id),
    )

    conn.execute(
        """INSERT INTO review_audit
           (proposal_type, proposal_id, decision, reviewer, notes, timestamp)
           VALUES ('edge_promotion', ?, ?, ?, ?, ?)""",
        (edge_id, f"PROMOTED:{current_level}→{to_level}",
         reviewer, f"claim={claim_id}, receipt={receipt_hash}, {notes or ''}",
         datetime.utcnow().isoformat() + "Z"),
    )

    conn.commit()
    return True


def reject_proposal(
    conn: sqlite3.Connection,
    proposal_id: str,
    reason: str,
    reviewer: Optional[str] = None,
) -> bool:
    """Reject a proposal with explanation."""
    proposal = get_proposal_by_id(conn, proposal_id)
    if not proposal:
        return False
    if proposal["status"] != "PENDING":
        return False

    table = "proposed_claims" if proposal["type"] == "claim" else "proposed_edges"
    now = datetime.utcnow().isoformat() + "Z"

    conn.execute(
        f"""UPDATE {table}
            SET status = 'REJECTED', resolved_at = ?, reviewer_notes = ?
            WHERE proposal_id = ?""",
        (now, reason, proposal_id),
    )

    conn.execute(
        """INSERT INTO review_audit
           (proposal_type, proposal_id, decision, reviewer, notes, timestamp)
           VALUES (?, ?, 'REJECTED', ?, ?, ?)""",
        (proposal["type"], proposal_id, reviewer, reason, now),
    )

    conn.commit()
    return True


def compute_correlation_metrics(
    conn: sqlite3.Connection, proposal_id: str
) -> Dict[str, Any]:
    """Compute correlation metrics for a proposal.

    Metrics: source_overlap, path_distance, convergence_score.
    """
    proposal = get_proposal_by_id(conn, proposal_id)
    if not proposal:
        return {"error": "Proposal not found"}

    metrics = {
        "proposal_id": proposal_id,
        "proposal_type": proposal["type"],
        "metrics": {},
    }

    now = datetime.utcnow().isoformat() + "Z"

    if proposal["type"] == "edge":
        from_node = proposal["from_node"]
        to_node = proposal["to_node"]

        overlap_count = conn.execute(
            """SELECT COUNT(DISTINCT e1.claim_id) FROM edges e1
               JOIN edges e2 ON e1.claim_id = e2.claim_id
               WHERE e1.from_node_id = ? AND e2.from_node_id = ?""",
            (from_node, to_node),
        ).fetchone()[0]

        total_claims_from = conn.execute(
            "SELECT COUNT(DISTINCT claim_id) FROM edges WHERE from_node_id = ? OR to_node_id = ?",
            (from_node, from_node),
        ).fetchone()[0]

        source_overlap = overlap_count / max(total_claims_from, 1)
        metrics["metrics"]["source_overlap"] = round(source_overlap, 3)

        path_distance = _compute_path_distance(conn, from_node, to_node)
        metrics["metrics"]["path_distance"] = path_distance

        edge_types = conn.execute(
            """SELECT COUNT(DISTINCT edge_type) FROM edges
               WHERE (from_node_id = ? AND to_node_id = ?)
                  OR (from_node_id = ? AND to_node_id = ?)""",
            (from_node, to_node, to_node, from_node),
        ).fetchone()[0]
        metrics["metrics"]["convergence_score"] = edge_types

        for metric_type, value in metrics["metrics"].items():
            conn.execute(
                """INSERT INTO correlation_metrics
                   (proposal_id, metric_type, metric_value, details, computed_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (proposal_id, metric_type, value,
                 json.dumps({"from_node": from_node, "to_node": to_node}), now),
            )
        conn.commit()

    elif proposal["type"] == "claim":
        claim_text = proposal["claim_text"]
        words = claim_text.lower().split()[:5]
        pattern = "%".join(words)

        similar_count = conn.execute(
            "SELECT COUNT(*) FROM claims WHERE claim_text LIKE ?",
            (f"%{pattern}%",),
        ).fetchone()[0]
        metrics["metrics"]["similar_claims"] = similar_count

        conn.execute(
            """INSERT INTO correlation_metrics
               (proposal_id, metric_type, metric_value, details, computed_at)
               VALUES (?, 'similar_claims', ?, ?, ?)""",
            (proposal_id, similar_count, json.dumps({"pattern": pattern}), now),
        )
        conn.commit()

    return metrics


def _compute_path_distance(
    conn: sqlite3.Connection, from_node: str, to_node: str, max_depth: int = 6
) -> int:
    """Shortest path distance between two nodes via BFS. -1 if not found."""
    if from_node == to_node:
        return 0

    visited = {from_node}
    queue = [(from_node, 0)]

    while queue:
        current, depth = queue.pop(0)
        if depth >= max_depth:
            continue

        neighbors = conn.execute(
            """SELECT DISTINCT to_node_id FROM edges WHERE from_node_id = ?
               UNION
               SELECT DISTINCT from_node_id FROM edges WHERE to_node_id = ?""",
            (current, current),
        ).fetchall()

        for (neighbor,) in neighbors:
            if neighbor == to_node:
                return depth + 1
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, depth + 1))

    return -1


def get_agent_stats(conn: sqlite3.Connection) -> Dict[str, Dict[str, int]]:
    """Get proposal statistics grouped by agent."""
    stats = {}

    for table, suffix in [("proposed_claims", "claims"), ("proposed_edges", "edges")]:
        rows = conn.execute(
            f"""SELECT agent_name, status, COUNT(*) as count
                FROM {table} GROUP BY agent_name, status"""
        ).fetchall()

        for row in rows:
            agent = row["agent_name"]
            if agent not in stats:
                stats[agent] = {
                    "pending_claims": 0, "approved_claims": 0, "rejected_claims": 0,
                    "pending_edges": 0, "approved_edges": 0, "rejected_edges": 0,
                }
            status_key = f"{row['status'].lower()}_{suffix}"
            stats[agent][status_key] = row["count"]

    return stats
