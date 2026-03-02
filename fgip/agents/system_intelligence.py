#!/usr/bin/env python3
"""FGIP System Intelligence Agent - Meta-agent for self-assessment and work orders.

This agent does NOT collect external data. It analyzes the FGIP system itself:
1. Identifies bottlenecks (pending proposals, parser gaps, API failures)
2. Generates work orders for Claude Code (new modules needed)
3. Synthesizes approval queues for human review
4. Tracks what the system CAN'T do and requests capabilities

This is the "self-aware" layer that tells Claude Code what to build next.
"""

import json
import os
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict

# Add project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class WorkOrder:
    """A request for Claude Code to build something."""
    order_id: str
    priority: str  # CRITICAL, HIGH, MEDIUM, LOW
    category: str  # PARSER, AGENT, API, SCHEMA, UI, FIX
    title: str
    description: str
    blocking: List[str]  # What this blocks
    context: Dict[str, Any]
    created_at: str


@dataclass
class SystemBottleneck:
    """A system limitation that needs addressing."""
    bottleneck_id: str
    bottleneck_type: str  # PENDING_APPROVAL, PARSER_GAP, API_FAILURE, MISSING_AGENT
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    description: str
    affected_agents: List[str]
    data_blocked: int  # How many items are blocked
    suggested_action: str
    details: Dict[str, Any]


@dataclass
class ApprovalQueueItem:
    """An item needing human approval."""
    proposal_id: str
    proposal_type: str  # claim, edge, node
    agent_name: str
    summary: str
    confidence: float
    created_at: str
    recommendation: str  # APPROVE, REVIEW, REJECT


class SystemIntelligenceAgent:
    """Meta-agent that analyzes FGIP system health and generates work orders."""

    def __init__(self, db):
        self.db = db
        self.conn = db.connect()
        self.work_orders: List[WorkOrder] = []
        self.bottlenecks: List[SystemBottleneck] = []
        self.approval_queue: List[ApprovalQueueItem] = []

    def analyze(self) -> Dict[str, Any]:
        """Run full system analysis."""
        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "system_health": "UNKNOWN",
            "bottlenecks": [],
            "work_orders": [],
            "approval_queue": [],
            "agent_status": {},
            "summary": {},
        }

        # Run all analysis phases
        self._analyze_pending_proposals()
        self._analyze_agent_capabilities()
        self._analyze_parser_gaps()
        self._analyze_api_health()
        self._generate_work_orders()

        # Compile report
        report["bottlenecks"] = [asdict(b) for b in self.bottlenecks]
        report["work_orders"] = [asdict(w) for w in self.work_orders]
        report["approval_queue"] = [asdict(a) for a in self.approval_queue]
        report["agent_status"] = self._get_agent_status()

        # Calculate health
        critical_count = sum(1 for b in self.bottlenecks if b.severity == "CRITICAL")
        high_count = sum(1 for b in self.bottlenecks if b.severity == "HIGH")

        if critical_count > 0:
            report["system_health"] = "CRITICAL"
        elif high_count > 3:
            report["system_health"] = "DEGRADED"
        elif len(self.bottlenecks) > 5:
            report["system_health"] = "ATTENTION_NEEDED"
        else:
            report["system_health"] = "HEALTHY"

        # Summary
        report["summary"] = {
            "total_bottlenecks": len(self.bottlenecks),
            "critical_bottlenecks": critical_count,
            "pending_approvals": len(self.approval_queue),
            "work_orders_generated": len(self.work_orders),
            "data_blocked": sum(b.data_blocked for b in self.bottlenecks),
        }

        return report

    def _analyze_pending_proposals(self):
        """Check for pending proposals that need approval."""
        from fgip.staging import get_pending_proposals, get_agent_stats

        pending = get_pending_proposals(self.conn)
        pending_claims = pending.get("claims", [])
        pending_edges = pending.get("edges", [])

        total_pending = len(pending_claims) + len(pending_edges)

        if total_pending > 100:
            self.bottlenecks.append(SystemBottleneck(
                bottleneck_id=f"bottleneck-pending-{datetime.utcnow().strftime('%Y%m%d')}",
                bottleneck_type="PENDING_APPROVAL",
                severity="HIGH" if total_pending > 500 else "MEDIUM",
                description=f"{total_pending} proposals awaiting approval",
                affected_agents=list(set(c.get("agent_name", "unknown") for c in pending_claims + pending_edges)),
                data_blocked=total_pending,
                suggested_action="Run bulk approval or rejection workflow",
                details={
                    "pending_claims": len(pending_claims),
                    "pending_edges": len(pending_edges),
                }
            ))

        # Build approval queue (top 20 highest confidence)
        all_pending = []
        for claim in pending_claims:
            all_pending.append({
                "type": "claim",
                "data": claim,
                "confidence": 0.8,  # Claims don't have confidence field
            })
        for edge in pending_edges:
            all_pending.append({
                "type": "edge",
                "data": edge,
                "confidence": edge.get("confidence", 0.5),
            })

        # Sort by confidence
        all_pending.sort(key=lambda x: x["confidence"], reverse=True)

        for item in all_pending[:20]:
            data = item["data"]
            recommendation = "APPROVE" if item["confidence"] >= 0.9 else "REVIEW" if item["confidence"] >= 0.7 else "REJECT"

            if item["type"] == "claim":
                summary = data.get("claim_text", "")[:100]
            else:
                summary = f"{data.get('from_node', '?')} → {data.get('relationship', '?')} → {data.get('to_node', '?')}"

            self.approval_queue.append(ApprovalQueueItem(
                proposal_id=data.get("proposal_id", "unknown"),
                proposal_type=item["type"],
                agent_name=data.get("agent_name", "unknown"),
                summary=summary,
                confidence=item["confidence"],
                created_at=data.get("created_at", ""),
                recommendation=recommendation,
            ))

    def _analyze_agent_capabilities(self):
        """Check which agents exist and what capabilities are missing."""
        agents_dir = PROJECT_ROOT / "fgip" / "agents"

        # Known agents and their data sources
        expected_agents = {
            "tic": {"source": "Treasury TIC", "data_type": "foreign_holdings"},
            "stablecoin": {"source": "DeFi Llama", "data_type": "market_cap"},
            "edgar": {"source": "SEC EDGAR", "data_type": "13f_filings"},
            "congress": {"source": "Congress.gov", "data_type": "votes"},
            "fec": {"source": "FEC API", "data_type": "campaign_finance"},
            "federal_register": {"source": "Federal Register", "data_type": "rulemaking"},
            "promethean": {"source": "RSS feeds", "data_type": "news_signals"},
            "opensecrets": {"source": "OpenSecrets", "data_type": "lobbying"},
            "fara": {"source": "FARA", "data_type": "foreign_agents"},
            "gao": {"source": "GAO", "data_type": "audits"},
            "usaspending": {"source": "USASpending", "data_type": "contracts"},
        }

        # Missing capabilities (agents that should exist but don't work well)
        missing_capabilities = []

        # Check for agents that exist but can't parse their data
        for agent_name, info in expected_agents.items():
            agent_file = agents_dir / f"{agent_name}.py"
            if not agent_file.exists():
                missing_capabilities.append({
                    "agent": agent_name,
                    "reason": "Agent file does not exist",
                    "source": info["source"],
                })
            else:
                # Check if agent has hardcoded/seeded data (indicates parser gap)
                content = agent_file.read_text()
                if "seeded" in content.lower() or "hardcoded" in content.lower():
                    # Check if it has live data capability
                    if "_fetch_live" not in content and "api" not in content.lower():
                        missing_capabilities.append({
                            "agent": agent_name,
                            "reason": "Uses seeded data, no live API integration",
                            "source": info["source"],
                        })

        if missing_capabilities:
            for cap in missing_capabilities:
                self.bottlenecks.append(SystemBottleneck(
                    bottleneck_id=f"bottleneck-capability-{cap['agent']}",
                    bottleneck_type="MISSING_AGENT",
                    severity="MEDIUM",
                    description=f"Agent '{cap['agent']}' {cap['reason']}",
                    affected_agents=[cap["agent"]],
                    data_blocked=0,
                    suggested_action=f"Build live API integration for {cap['source']}",
                    details=cap,
                ))

    def _analyze_parser_gaps(self):
        """Check for data that exists but can't be parsed."""
        artifacts_dir = PROJECT_ROOT / "data" / "artifacts"

        if not artifacts_dir.exists():
            return

        # Look for unparsed artifacts
        unparsed_count = 0
        unparsed_types = {}

        for subdir in artifacts_dir.iterdir():
            if subdir.is_dir():
                for artifact in subdir.glob("*"):
                    if artifact.suffix in (".html", ".pdf", ".xlsx", ".xml"):
                        # Check if there's a corresponding .json (parsed version)
                        json_version = artifact.with_suffix(".json")
                        if not json_version.exists():
                            unparsed_count += 1
                            ext = artifact.suffix
                            unparsed_types[ext] = unparsed_types.get(ext, 0) + 1

        if unparsed_count > 0:
            self.bottlenecks.append(SystemBottleneck(
                bottleneck_id=f"bottleneck-parser-{datetime.utcnow().strftime('%Y%m%d')}",
                bottleneck_type="PARSER_GAP",
                severity="MEDIUM" if unparsed_count < 50 else "HIGH",
                description=f"{unparsed_count} artifacts without parsers",
                affected_agents=["all"],
                data_blocked=unparsed_count,
                suggested_action="Build parsers for: " + ", ".join(unparsed_types.keys()),
                details={
                    "unparsed_by_type": unparsed_types,
                    "total": unparsed_count,
                }
            ))

    def _analyze_api_health(self):
        """Check recent API failures in logs."""
        log_file = PROJECT_ROOT / "data" / "scheduler.log"

        if not log_file.exists():
            return

        # Check last 100 lines for errors
        try:
            with open(log_file, "r") as f:
                lines = f.readlines()[-100:]

            error_count = 0
            failed_agents = set()

            for line in lines:
                if "error" in line.lower() or "failed" in line.lower():
                    error_count += 1
                    # Try to extract agent name
                    for agent in ["tic", "stablecoin", "edgar", "congress", "fec"]:
                        if agent in line.lower():
                            failed_agents.add(agent)

            if error_count > 10:
                self.bottlenecks.append(SystemBottleneck(
                    bottleneck_id=f"bottleneck-api-{datetime.utcnow().strftime('%Y%m%d')}",
                    bottleneck_type="API_FAILURE",
                    severity="HIGH" if error_count > 50 else "MEDIUM",
                    description=f"{error_count} API errors in recent logs",
                    affected_agents=list(failed_agents) or ["unknown"],
                    data_blocked=error_count,
                    suggested_action="Check API connectivity and rate limits",
                    details={
                        "error_count": error_count,
                        "failed_agents": list(failed_agents),
                    }
                ))

        except Exception as e:
            pass  # Log analysis is best-effort

    def _generate_work_orders(self):
        """Generate work orders from bottlenecks."""
        order_num = 1

        for bottleneck in self.bottlenecks:
            if bottleneck.severity in ("CRITICAL", "HIGH"):
                # Generate work order for Claude Code
                category = {
                    "PENDING_APPROVAL": "UI",
                    "PARSER_GAP": "PARSER",
                    "API_FAILURE": "FIX",
                    "MISSING_AGENT": "AGENT",
                }.get(bottleneck.bottleneck_type, "FIX")

                self.work_orders.append(WorkOrder(
                    order_id=f"WO-{datetime.utcnow().strftime('%Y%m%d')}-{order_num:03d}",
                    priority=bottleneck.severity,
                    category=category,
                    title=bottleneck.description,
                    description=bottleneck.suggested_action,
                    blocking=bottleneck.affected_agents,
                    context=bottleneck.details,
                    created_at=datetime.utcnow().isoformat(),
                ))
                order_num += 1

        # Add standing work orders for known gaps
        standing_orders = [
            {
                "priority": "MEDIUM",
                "category": "AGENT",
                "title": "YouTube Signal Ingestion needs approval workflow",
                "description": "8,678 videos loaded but guests/topics need graph integration",
                "blocking": ["youtube_signal"],
            },
            {
                "priority": "LOW",
                "category": "UI",
                "title": "Approval UI for bulk proposal review",
                "description": "Build web UI for reviewing and approving pending proposals",
                "blocking": ["all_agents"],
            },
        ]

        for order in standing_orders:
            self.work_orders.append(WorkOrder(
                order_id=f"WO-STANDING-{order_num:03d}",
                priority=order["priority"],
                category=order["category"],
                title=order["title"],
                description=order["description"],
                blocking=order["blocking"],
                context={},
                created_at=datetime.utcnow().isoformat(),
            ))
            order_num += 1

    def _get_agent_status(self) -> Dict[str, Any]:
        """Get status of all agents."""
        from fgip.staging import get_agent_stats

        stats = get_agent_stats(self.conn)

        # Add last run times (from artifacts)
        artifacts_dir = PROJECT_ROOT / "data" / "artifacts"
        if artifacts_dir.exists():
            for agent_dir in artifacts_dir.iterdir():
                if agent_dir.is_dir():
                    agent_name = agent_dir.name
                    # Get most recent artifact
                    artifacts = list(agent_dir.glob("*"))
                    if artifacts:
                        latest = max(artifacts, key=lambda p: p.stat().st_mtime)
                        if agent_name not in stats:
                            stats[agent_name] = {}
                        stats[agent_name]["last_run"] = datetime.fromtimestamp(
                            latest.stat().st_mtime
                        ).isoformat()

        return stats

    def get_claude_code_briefing(self, include_work_orders: bool = True, include_health: bool = True) -> str:
        """Generate a briefing for Claude Code about what to work on.

        Args:
            include_work_orders: Include work orders section
            include_health: Include API health and bottleneck details
        """
        report = self.analyze()

        briefing = []
        briefing.append("=" * 70)
        briefing.append("FGIP SYSTEM INTELLIGENCE BRIEFING FOR CLAUDE CODE")
        briefing.append(f"Generated: {report['timestamp']}")
        briefing.append(f"System Health: {report['system_health']}")
        briefing.append("=" * 70)

        # Summary
        summary = report["summary"]
        briefing.append(f"\nSUMMARY:")
        briefing.append(f"  Bottlenecks: {summary['total_bottlenecks']} ({summary['critical_bottlenecks']} critical)")
        briefing.append(f"  Data Blocked: {summary['data_blocked']} items")
        briefing.append(f"  Pending Approvals: {summary['pending_approvals']}")
        briefing.append(f"  Work Orders: {summary['work_orders_generated']}")

        # Work Orders (what Claude Code should do)
        if include_work_orders and report["work_orders"]:
            briefing.append(f"\nWORK ORDERS FOR CLAUDE CODE:")
            briefing.append("-" * 40)
            for wo in report["work_orders"]:
                briefing.append(f"  [{wo['priority']}] {wo['order_id']}: {wo['title']}")
                briefing.append(f"       Category: {wo['category']}")
                briefing.append(f"       Action: {wo['description']}")
                if wo["blocking"]:
                    briefing.append(f"       Blocking: {', '.join(wo['blocking'])}")
                briefing.append("")

        # Approval Queue (what needs human decision)
        if report["approval_queue"]:
            briefing.append(f"\nAPPROVAL QUEUE (Top 10):")
            briefing.append("-" * 40)
            for item in report["approval_queue"][:10]:
                briefing.append(f"  [{item['recommendation']}] {item['proposal_id']}")
                briefing.append(f"       Type: {item['proposal_type']} | Agent: {item['agent_name']}")
                briefing.append(f"       Summary: {item['summary'][:60]}...")
                briefing.append(f"       Confidence: {item['confidence']:.2f}")
                briefing.append("")

        # Bottlenecks (health status)
        if include_health and report["bottlenecks"]:
            briefing.append(f"\nBOTTLENECKS:")
            briefing.append("-" * 40)
            for b in report["bottlenecks"]:
                briefing.append(f"  [{b['severity']}] {b['bottleneck_type']}: {b['description']}")
                briefing.append(f"       Action: {b['suggested_action']}")
                briefing.append("")

        briefing.append("=" * 70)
        briefing.append("END BRIEFING")
        briefing.append("=" * 70)

        return "\n".join(briefing)


def main():
    """Run system intelligence analysis."""
    import argparse

    parser = argparse.ArgumentParser(description="FGIP System Intelligence Agent")
    parser.add_argument("--db", default="fgip.db", help="Database path")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--briefing", action="store_true", help="Output Claude Code briefing")
    args = parser.parse_args()

    os.chdir(PROJECT_ROOT)

    from fgip.db import FGIPDatabase
    db = FGIPDatabase(args.db)

    agent = SystemIntelligenceAgent(db)

    if args.json:
        report = agent.analyze()
        print(json.dumps(report, indent=2))
    elif args.briefing:
        print(agent.get_claude_code_briefing())
    else:
        # Default: print briefing
        print(agent.get_claude_code_briefing())


if __name__ == "__main__":
    main()
