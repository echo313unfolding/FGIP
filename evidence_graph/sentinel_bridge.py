"""Sentinel ↔ Evidence Graph bridge.

Converts Sentinel classifier outputs into receipted evidence graph entries.
This is the integration proof: model predictions become HYPOTHESIS claims
backed by the model's confidence, queryable and promotable through the
standard staging pipeline.

Flow:
    security event text
      → Mamba classifier → (class_label, confidence, hidden_state[768])
      → bridge.process_event()
        → create claim from classification
        → query graph for related context (CVEs, prior events, techniques)
        → insert HYPOTHESIS edge linking event to threat context
        → return verdict dict with provenance chain

The bridge does NOT import torch or the model. It takes pre-computed
predictions as input. This keeps the graph layer model-agnostic.
"""

import json
import uuid
from datetime import datetime
from typing import Optional

from .schema import Node, Edge, Claim, Source, compute_sha256
from .db import EvidenceGraphDB
from .registry import DomainRegistry


# Maps classifier output classes to evidence graph node types and edge types
DEFAULT_CLASS_MAP = {
    # Benign classes — log but don't create threat edges
    "BENIGN_NORMAL": {"threat": False, "edge_type": None},
    "BENIGN_EXPECTED": {"threat": False, "edge_type": None},

    # Suspicious classes — create HYPOTHESIS edges
    "SUSP_BRUTE_FORCE": {
        "threat": True,
        "edge_type": "SUGGESTS",
        "technique": "T1110",  # MITRE ATT&CK
        "tactic": "Credential Access",
    },
    "SUSP_PRIVESC": {
        "threat": True,
        "edge_type": "SUGGESTS",
        "technique": "T1068",
        "tactic": "Privilege Escalation",
    },
    "SUSP_EXFIL": {
        "threat": True,
        "edge_type": "SUGGESTS",
        "technique": "T1041",
        "tactic": "Exfiltration",
    },
    "SUSP_PERSISTENCE": {
        "threat": True,
        "edge_type": "SUGGESTS",
        "technique": "T1547",
        "tactic": "Persistence",
    },
    "SUSP_EXECUTION": {
        "threat": True,
        "edge_type": "SUGGESTS",
        "technique": "T1059",
        "tactic": "Execution",
    },
    "SUSP_MALWARE": {
        "threat": True,
        "edge_type": "SUGGESTS",
        "technique": "T1204",
        "tactic": "Execution",
    },
    "SUSP_RECON": {
        "threat": True,
        "edge_type": "SUGGESTS",
        "technique": "T1046",
        "tactic": "Discovery",
    },
    "SUSP_SUPPLY_CHAIN": {
        "threat": True,
        "edge_type": "SUGGESTS",
        "technique": "T1195",
        "tactic": "Initial Access",
    },
    "SUSP_DATA_ACCESS": {
        "threat": True,
        "edge_type": "SUGGESTS",
        "technique": "T1005",
        "tactic": "Collection",
    },
    "SUSP_EVASION": {
        "threat": True,
        "edge_type": "SUGGESTS",
        "technique": "T1070",
        "tactic": "Defense Evasion",
    },
    "SUSP_UNKNOWN": {
        "threat": True,
        "edge_type": "SUGGESTS",
        "technique": None,
        "tactic": None,
    },

    # Escalation / meta classes
    "ESCALATE_CRITICAL": {
        "threat": True,
        "edge_type": "SUGGESTS",
        "technique": None,
        "tactic": None,
    },
    "INSUFFICIENT_CONTEXT": {"threat": False, "edge_type": None},
    "FALSE_POSITIVE_LIKELY": {"threat": False, "edge_type": None},
}


class SentinelBridge:
    """Bridge between Sentinel classifier and the evidence graph.

    Usage:
        db = EvidenceGraphDB("sentinel.db", registry=sec_registry)
        db.init_schema()
        bridge = SentinelBridge(db)

        verdict = bridge.process_event(
            event_text="sshd: Failed password for root from 192.168.1.100",
            predicted_class="SUSP_BRUTE_FORCE",
            confidence=0.87,
            source_host="webserver-01",
        )
        # verdict = {
        #     "claim_id": "SEC-000042",
        #     "class": "SUSP_BRUTE_FORCE",
        #     "confidence": 0.87,
        #     "assertion_level": "HYPOTHESIS",
        #     "related_context": [...],
        #     "edges_created": [...],
        # }
    """

    def __init__(
        self,
        db: EvidenceGraphDB,
        class_map: dict | None = None,
        agent_name: str = "sentinel-mamba-130m",
    ):
        self.db = db
        self.class_map = class_map or DEFAULT_CLASS_MAP
        self.agent_name = agent_name

    def process_event(
        self,
        event_text: str,
        predicted_class: str,
        confidence: float,
        source_host: str | None = None,
        event_metadata: dict | None = None,
    ) -> dict:
        """Process a classified security event into the evidence graph.

        Args:
            event_text: Raw event window text
            predicted_class: Classifier output (one of 16 classes)
            confidence: Softmax probability for the predicted class
            source_host: Hostname where event originated
            event_metadata: Optional extra metadata (PIDs, IPs, etc.)

        Returns:
            Verdict dict with claim_id, assertion_level, related context
        """
        now = datetime.utcnow().isoformat() + "Z"
        class_info = self.class_map.get(predicted_class, {"threat": False})

        # Always create a claim for the classification
        claim_id = self.db.get_next_claim_id()
        claim_text = (
            f"Sentinel classified event as {predicted_class} "
            f"with {confidence:.1%} confidence"
        )
        if source_host:
            claim_text += f" on host {source_host}"

        self.db.insert_claim(Claim(
            claim_id=claim_id,
            claim_text=claim_text,
            topic="sentinel-triage",
            status="PARTIAL",  # No external source — model-generated
            notes=json.dumps({
                "agent": self.agent_name,
                "predicted_class": predicted_class,
                "confidence": confidence,
                "event_hash": compute_sha256(event_text)[:16],
            }),
        ))

        verdict = {
            "claim_id": claim_id,
            "class": predicted_class,
            "confidence": confidence,
            "assertion_level": "HYPOTHESIS",
            "is_threat": class_info.get("threat", False),
            "edges_created": [],
            "related_context": [],
            "timestamp": now,
        }

        if not class_info.get("threat"):
            # Benign / insufficient — log claim but no threat edges
            return verdict

        # Ensure source host node exists
        if source_host:
            host_node = self.db.get_node(source_host)
            if not host_node:
                self.db.insert_node(Node(
                    node_id=source_host,
                    node_type="ASSET",
                    name=source_host,
                    metadata=event_metadata or {},
                ))

        # Create a LOG_EVENT node for this specific event
        event_id = f"evt-{compute_sha256(event_text)[:12]}"
        event_node = self.db.get_node(event_id)
        if not event_node:
            self.db.insert_node(Node(
                node_id=event_id,
                node_type="LOG_EVENT",
                name=f"{predicted_class} event",
                metadata={
                    "event_hash": compute_sha256(event_text)[:16],
                    "source_host": source_host,
                    "classifier_confidence": confidence,
                    **(event_metadata or {}),
                },
            ))

        # Link event to host
        if source_host:
            host_edge_id = f"produced-{event_id}-{source_host}"
            self.db.insert_edge(Edge(
                edge_id=host_edge_id,
                edge_type="PRODUCED_BY",
                from_node_id=event_id,
                to_node_id=source_host,
                claim_id=claim_id,
                confidence=confidence,
            ))
            verdict["edges_created"].append(host_edge_id)

        # Query graph for related context
        related = self._find_related_context(
            predicted_class, class_info, source_host
        )
        verdict["related_context"] = related

        # If we have a MITRE technique match, link to it
        technique_id = class_info.get("technique")
        if technique_id:
            technique_node = self.db.get_node(technique_id)
            if technique_node:
                # Link event to known technique
                tech_edge_id = f"suggests-{event_id}-{technique_id}"
                edge_type = class_info.get("edge_type", "SUGGESTS")
                self.db.insert_edge(Edge(
                    edge_id=tech_edge_id,
                    edge_type=edge_type,
                    from_node_id=event_id,
                    to_node_id=technique_id,
                    claim_id=claim_id,
                    confidence=confidence,
                    metadata={"tactic": class_info.get("tactic")},
                ))
                verdict["edges_created"].append(tech_edge_id)

        # Create HYPOTHESIS node if confidence is high enough
        if confidence >= 0.7:
            hyp_id = f"hyp-{uuid.uuid4().hex[:10]}"
            self.db.insert_node(Node(
                node_id=hyp_id,
                node_type="HYPOTHESIS",
                name=f"{predicted_class} on {source_host or 'unknown'}",
                metadata={
                    "class": predicted_class,
                    "confidence": confidence,
                    "claim_id": claim_id,
                    "technique": technique_id,
                },
            ))
            # Link event SUGGESTS hypothesis
            hyp_edge_id = f"suggests-{event_id}-{hyp_id}"
            self.db.insert_edge(Edge(
                edge_id=hyp_edge_id,
                edge_type="SUGGESTS",
                from_node_id=event_id,
                to_node_id=hyp_id,
                claim_id=claim_id,
                confidence=confidence,
            ))
            verdict["edges_created"].append(hyp_edge_id)
            verdict["hypothesis_id"] = hyp_id

        return verdict

    def _find_related_context(
        self,
        predicted_class: str,
        class_info: dict,
        source_host: str | None,
    ) -> list[dict]:
        """Query the graph for context related to this classification."""
        related = []
        conn = self.db.connect()

        # Find prior events on the same host
        if source_host:
            rows = conn.execute(
                """SELECT e.edge_id, e.edge_type, e.from_node_id,
                          e.assertion_level, e.confidence, e.created_at
                   FROM edges e
                   WHERE e.to_node_id = ?
                   ORDER BY e.created_at DESC LIMIT 10""",
                (source_host,),
            ).fetchall()
            for r in rows:
                related.append({
                    "type": "prior_event_on_host",
                    "edge_id": r["edge_id"],
                    "edge_type": r["edge_type"],
                    "from_node": r["from_node_id"],
                    "assertion_level": r["assertion_level"],
                    "confidence": r["confidence"],
                })

        # Find known techniques matching this class
        technique_id = class_info.get("technique")
        if technique_id:
            rows = conn.execute(
                """SELECT n.node_id, n.name, n.metadata
                   FROM nodes n WHERE n.node_id = ?""",
                (technique_id,),
            ).fetchall()
            for r in rows:
                related.append({
                    "type": "known_technique",
                    "node_id": r["node_id"],
                    "name": r["name"],
                })

            # Find threat actors associated with this technique
            rows = conn.execute(
                """SELECT n.node_id, n.name, e.assertion_level
                   FROM edges e
                   JOIN nodes n ON n.node_id = e.from_node_id
                   WHERE e.to_node_id = ? AND e.edge_type = 'USES_TECHNIQUE'
                   LIMIT 5""",
                (technique_id,),
            ).fetchall()
            for r in rows:
                related.append({
                    "type": "associated_threat_actor",
                    "node_id": r["node_id"],
                    "name": r["name"],
                    "assertion_level": r["assertion_level"],
                })

        return related

    def get_host_threat_summary(self, host_id: str) -> dict:
        """Get a summary of all threat activity for a host.

        Returns recent events, active hypotheses, and overall threat level.
        """
        conn = self.db.connect()

        # Count events by class
        events = conn.execute(
            """SELECT n.metadata, e.confidence, e.created_at
               FROM edges e
               JOIN nodes n ON n.node_id = e.from_node_id
               WHERE e.to_node_id = ? AND e.edge_type = 'PRODUCED_BY'
               ORDER BY e.created_at DESC LIMIT 50""",
            (host_id,),
        ).fetchall()

        class_counts = {}
        total_confidence = 0.0
        for evt in events:
            try:
                meta = json.loads(evt["metadata"]) if evt["metadata"] else {}
            except (json.JSONDecodeError, TypeError):
                meta = {}
            cls = meta.get("classifier_confidence", 0)
            total_confidence += evt["confidence"] or 0
            # Count by event name pattern
            class_counts[meta.get("source_host", "unknown")] = (
                class_counts.get(meta.get("source_host", "unknown"), 0) + 1
            )

        # Active hypotheses
        hypotheses = conn.execute(
            """SELECT n.node_id, n.name, n.metadata
               FROM nodes n
               WHERE n.node_type = 'HYPOTHESIS'
                 AND n.metadata LIKE ?
               ORDER BY n.created_at DESC LIMIT 10""",
            (f'%"{host_id}"%',),
        ).fetchall()

        return {
            "host_id": host_id,
            "total_events": len(events),
            "active_hypotheses": len(hypotheses),
            "avg_confidence": (
                round(total_confidence / len(events), 3) if events else 0
            ),
            "hypotheses": [
                {"id": h["node_id"], "name": h["name"]}
                for h in hypotheses
            ],
        }

    def bulk_load_mitre(self, techniques: list[dict]):
        """Pre-populate the graph with MITRE ATT&CK technique nodes.

        Args:
            techniques: List of dicts with at minimum:
                {"technique_id": "T1110", "name": "Brute Force",
                 "tactic": "Credential Access"}
        """
        for t in techniques:
            tid = t["technique_id"]
            existing = self.db.get_node(tid)
            if not existing:
                self.db.insert_node(Node(
                    node_id=tid,
                    node_type="TECHNIQUE",
                    name=t.get("name", tid),
                    metadata={
                        "mitre_id": tid,
                        "tactic": t.get("tactic"),
                        "platform": t.get("platform"),
                    },
                ))
