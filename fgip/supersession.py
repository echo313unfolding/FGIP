"""Supersession tracking for FGIP claims and edges.

Implements Karpathy-style knowledge lifecycle:
- Claims can be superseded by newer findings
- Supersession chains are queryable
- Staleness is tracked via last_verified timestamps
- Confidence decays over time for unverified claims

Adapted for FGIP's existing graph structure (SUPERSEDES, INVALIDATES,
CONFIRMS, WEAKENS edge types already in schema.py).
"""

import json
import uuid
from datetime import datetime, timedelta
from typing import Optional

from .db import FGIPDatabase
from .schema import (
    Claim, ClaimStatus, Edge, EdgeType, AssertionLevel,
    compute_sha256,
)


# Default staleness threshold: claims older than this without re-verification
# are flagged as potentially stale
DEFAULT_STALENESS_DAYS = 90


SUPERSESSION_MIGRATION = """
-- Supersession columns on claims (idempotent)
-- superseded_by: claim_id of the replacement claim
-- last_verified: when this claim was last confirmed still valid
-- decay_days: how many days before this claim goes stale (NULL = default 90)

ALTER TABLE claims ADD COLUMN superseded_by TEXT DEFAULT NULL;
ALTER TABLE claims ADD COLUMN last_verified TEXT DEFAULT NULL;
ALTER TABLE claims ADD COLUMN decay_days INTEGER DEFAULT NULL;
"""


def migrate_supersession(db: FGIPDatabase):
    """Add supersession columns to claims table (idempotent)."""
    conn = db.connect()
    for line in SUPERSESSION_MIGRATION.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("--"):
            continue
        try:
            conn.execute(line)
        except Exception:
            pass  # Column already exists
    conn.commit()


def supersede_claim(
    db: FGIPDatabase,
    old_claim_id: str,
    new_claim_id: str,
    reason: Optional[str] = None,
) -> Optional[str]:
    """Mark old_claim as superseded by new_claim.

    Creates a SUPERSEDES edge and updates the old claim's superseded_by field.
    Returns the edge_id or None on failure.
    """
    conn = db.connect()
    now = datetime.utcnow().isoformat() + "Z"

    # Verify both claims exist
    old = db.get_claim(old_claim_id)
    new = db.get_claim(new_claim_id)
    if not old or not new:
        return None

    # Update old claim
    try:
        conn.execute(
            "UPDATE claims SET superseded_by = ? WHERE claim_id = ?",
            (new_claim_id, old_claim_id),
        )
    except Exception:
        # Column might not exist yet
        migrate_supersession(db)
        conn.execute(
            "UPDATE claims SET superseded_by = ? WHERE claim_id = ?",
            (new_claim_id, old_claim_id),
        )

    # Create SUPERSEDES edge (new supersedes old)
    edge_id = f"supersede-{uuid.uuid4().hex[:12]}"
    notes = reason or f"{new_claim_id} supersedes {old_claim_id}"

    conn.execute(
        """INSERT INTO edges
           (edge_id, edge_type, from_node_id, to_node_id, claim_id,
            assertion_level, confidence, notes, metadata, created_at, sha256)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            edge_id, "SUPERSEDES", new_claim_id, old_claim_id,
            new_claim_id, "FACT", 1.0, notes, "{}",
            now, compute_sha256({"edge_id": edge_id}),
        ),
    )
    conn.commit()
    return edge_id


def verify_claim(db: FGIPDatabase, claim_id: str) -> bool:
    """Mark a claim as re-verified now. Resets its staleness clock."""
    conn = db.connect()
    now = datetime.utcnow().isoformat() + "Z"
    try:
        conn.execute(
            "UPDATE claims SET last_verified = ? WHERE claim_id = ?",
            (now, claim_id),
        )
        conn.commit()
        return True
    except Exception:
        migrate_supersession(db)
        conn.execute(
            "UPDATE claims SET last_verified = ? WHERE claim_id = ?",
            (now, claim_id),
        )
        conn.commit()
        return True


def get_supersession_chain(db: FGIPDatabase, claim_id: str) -> list[str]:
    """Walk the supersession chain forward from a claim.

    Returns [claim_id, successor_1, successor_2, ...] ending at the
    current (non-superseded) version.
    """
    conn = db.connect()
    chain = [claim_id]
    current = claim_id
    seen = {claim_id}

    while True:
        try:
            row = conn.execute(
                "SELECT superseded_by FROM claims WHERE claim_id = ?",
                (current,),
            ).fetchone()
        except Exception:
            break

        if not row or not row[0]:
            break

        successor = row[0]
        if successor in seen:
            break  # Cycle protection
        seen.add(successor)
        chain.append(successor)
        current = successor

    return chain


def get_current_claim(db: FGIPDatabase, claim_id: str) -> str:
    """Get the latest non-superseded version of a claim."""
    chain = get_supersession_chain(db, claim_id)
    return chain[-1]


def get_stale_claims(
    db: FGIPDatabase,
    staleness_days: int = DEFAULT_STALENESS_DAYS,
) -> list[dict]:
    """Find claims that haven't been verified within their staleness window.

    Returns list of {claim_id, claim_text, topic, status, created_at,
    last_verified, days_stale, superseded_by}.
    """
    conn = db.connect()
    now = datetime.utcnow()
    cutoff = (now - timedelta(days=staleness_days)).isoformat() + "Z"

    try:
        rows = conn.execute(
            """SELECT claim_id, claim_text, topic, status, created_at,
                      last_verified, decay_days, superseded_by
               FROM claims
               WHERE superseded_by IS NULL
                 AND (last_verified IS NULL OR last_verified < ?)
               ORDER BY created_at ASC""",
            (cutoff,),
        ).fetchall()
    except Exception:
        # Columns don't exist yet — all claims without last_verified are stale
        migrate_supersession(db)
        rows = conn.execute(
            """SELECT claim_id, claim_text, topic, status, created_at,
                      last_verified, decay_days, superseded_by
               FROM claims
               WHERE superseded_by IS NULL
                 AND (last_verified IS NULL OR last_verified < ?)
               ORDER BY created_at ASC""",
            (cutoff,),
        ).fetchall()

    results = []
    for r in rows:
        last = r["last_verified"] or r["created_at"]
        if last:
            try:
                last_dt = datetime.fromisoformat(last.replace("Z", "+00:00").replace("+00:00", ""))
                days_stale = (now - last_dt).days
            except Exception:
                days_stale = staleness_days + 1
        else:
            days_stale = staleness_days + 1

        # Use per-claim decay_days if set, else default
        threshold = r["decay_days"] if r["decay_days"] else staleness_days
        if days_stale >= threshold:
            results.append({
                "claim_id": r["claim_id"],
                "claim_text": r["claim_text"][:120],
                "topic": r["topic"],
                "status": r["status"],
                "created_at": r["created_at"],
                "last_verified": r["last_verified"],
                "days_stale": days_stale,
            })

    return results
