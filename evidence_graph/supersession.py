"""Evidence graph supersession — knowledge lifecycle tracking.

Domain-agnostic extraction of fgip/supersession.py.

- Claims can be superseded by newer findings
- Supersession chains are queryable
- Staleness is tracked via last_verified timestamps
- Confidence decays over time for unverified claims
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional

from .schema import compute_sha256


# Migration SQL — adds supersession columns to claims table (idempotent)
SUPERSESSION_MIGRATION = """
ALTER TABLE claims ADD COLUMN superseded_by TEXT DEFAULT NULL;
ALTER TABLE claims ADD COLUMN last_verified TEXT DEFAULT NULL;
ALTER TABLE claims ADD COLUMN decay_days INTEGER DEFAULT NULL;
"""


def migrate_supersession(db):
    """Add supersession columns to claims table (idempotent).

    Args:
        db: Any object with a .connect() method returning a sqlite3 connection.
    """
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
    db,
    old_claim_id: str,
    new_claim_id: str,
    reason: Optional[str] = None,
) -> Optional[str]:
    """Mark old_claim as superseded by new_claim.

    Creates a SUPERSEDES edge and updates the old claim's superseded_by field.
    Returns the edge_id or None on failure.

    Args:
        db: Object with .connect() and .get_claim(claim_id) methods.
    """
    conn = db.connect()
    now = datetime.utcnow().isoformat() + "Z"

    old = db.get_claim(old_claim_id)
    new = db.get_claim(new_claim_id)
    if not old or not new:
        return None

    try:
        conn.execute(
            "UPDATE claims SET superseded_by = ? WHERE claim_id = ?",
            (new_claim_id, old_claim_id),
        )
    except Exception:
        migrate_supersession(db)
        conn.execute(
            "UPDATE claims SET superseded_by = ? WHERE claim_id = ?",
            (new_claim_id, old_claim_id),
        )

    conn.commit()  # Commit claim update before toggling FK pragma

    edge_id = f"supersede-{uuid.uuid4().hex[:12]}"
    notes = reason or f"{new_claim_id} supersedes {old_claim_id}"

    # Supersession edges link claim→claim, not node→node.
    # Temporarily relax FK so claim IDs can go in from/to_node_id.
    conn.execute("PRAGMA foreign_keys = OFF")
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
    conn.execute("PRAGMA foreign_keys = ON")
    return edge_id


def verify_claim(db, claim_id: str) -> bool:
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


def get_supersession_chain(db, claim_id: str) -> list[str]:
    """Walk the supersession chain forward from a claim.

    Returns [claim_id, successor_1, ...] ending at the current version.
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


def get_current_claim(db, claim_id: str) -> str:
    """Get the latest non-superseded version of a claim."""
    chain = get_supersession_chain(db, claim_id)
    return chain[-1]


def get_stale_claims(
    db,
    staleness_days: Optional[int] = None,
) -> list[dict]:
    """Find claims that haven't been verified within their staleness window.

    Args:
        db: Object with .connect() and optionally .registry.default_staleness_days.
        staleness_days: Override staleness threshold. If None, uses
            db.registry.default_staleness_days (or 90 as fallback).
    """
    if staleness_days is None:
        registry = getattr(db, "registry", None)
        if registry is not None:
            staleness_days = registry.default_staleness_days
        else:
            staleness_days = 90

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
                last_dt = datetime.fromisoformat(
                    last.replace("Z", "+00:00").replace("+00:00", "")
                )
                days_stale = (now - last_dt).days
            except Exception:
                days_stale = staleness_days + 1
        else:
            days_stale = staleness_days + 1

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
