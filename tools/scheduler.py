#!/usr/bin/env python3
"""FGIP Agent Scheduler - Runs agents on schedule and sends alerts.

Usage:
    python3 tools/scheduler.py              # Run all agents once
    python3 tools/scheduler.py --agent tic  # Run specific agent
    python3 tools/scheduler.py --daemon     # Run as daemon (hourly)

Designed to be called by systemd timer or cron.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fgip.db import FGIPDatabase

# Alert configuration
ALERT_FILE = PROJECT_ROOT / "data" / "alerts.jsonl"
ALERT_WEBHOOK_URL = os.environ.get("FGIP_ALERT_WEBHOOK")  # Optional Discord/Slack webhook


def send_alert(alert_type: str, message: str, data: dict = None):
    """Send an alert via configured channels."""
    alert = {
        "timestamp": datetime.utcnow().isoformat(),
        "type": alert_type,
        "message": message,
        "data": data or {},
    }

    # Always write to file
    ALERT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(ALERT_FILE, "a") as f:
        f.write(json.dumps(alert) + "\n")

    print(f"[ALERT] {alert_type}: {message}")

    # Try webhook if configured
    if ALERT_WEBHOOK_URL:
        try:
            import urllib.request
            payload = json.dumps({"content": f"**{alert_type}**: {message}"}).encode()
            req = urllib.request.Request(
                ALERT_WEBHOOK_URL,
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=10)
        except Exception as e:
            print(f"[ALERT] Webhook failed: {e}")

    # Desktop notification (if available)
    try:
        os.system(f'notify-send "FGIP Alert: {alert_type}" "{message}" 2>/dev/null')
    except:
        pass


def run_agent(db, agent_name: str) -> dict:
    """Run a single agent and return results."""
    results = {"agent": agent_name, "status": "unknown", "data": {}}

    try:
        if agent_name == "tic":
            from fgip.agents.tic import TICAgent
            agent = TICAgent(db)
        elif agent_name == "stablecoin":
            from fgip.agents.stablecoin import StablecoinAgent
            agent = StablecoinAgent(db)
        elif agent_name == "edgar":
            from fgip.agents.edgar import EDGARAgent
            agent = EDGARAgent(db)
        elif agent_name == "federal_register":
            from fgip.agents.federal_register import FederalRegisterAgent
            agent = FederalRegisterAgent(db)
        elif agent_name == "congress":
            from fgip.agents.congress import CongressAgent
            agent = CongressAgent(db)
        elif agent_name == "promethean":
            from fgip.agents.promethean import PrometheanAgent
            agent = PrometheanAgent(db)
        elif agent_name == "system_intelligence":
            from fgip.agents.system_intelligence import SystemIntelligenceAgent
            agent = SystemIntelligenceAgent(db)
            # System intelligence doesn't have a run() method, use analyze()
            run_results = agent.analyze()
            results["status"] = "success"
            results["data"] = {
                "system_health": run_results.get("system_health"),
                "bottlenecks": len(run_results.get("bottlenecks", [])),
                "work_orders": len(run_results.get("work_orders", [])),
            }
            return results
        else:
            results["status"] = "error"
            results["error"] = f"Unknown agent: {agent_name}"
            return results

        run_results = agent.run()
        results["status"] = "success"
        results["data"] = run_results

        # Check for alert conditions
        if agent_name == "tic":
            # Alert if China dumps >$10B in a month
            # (would need historical comparison - placeholder for now)
            pass

        elif agent_name == "stablecoin":
            # Alert if market cap changes >5%
            pass

    except Exception as e:
        results["status"] = "error"
        results["error"] = str(e)
        send_alert("AGENT_ERROR", f"{agent_name} failed: {e}")

    return results


def run_all_agents(db) -> list:
    """Run all agents and collect results."""
    agents = ["tic", "stablecoin", "edgar", "promethean"]
    results = []

    print(f"\n{'='*60}")
    print(f"FGIP Scheduled Agent Run - {datetime.utcnow().isoformat()}")
    print(f"{'='*60}\n")

    for agent_name in agents:
        print(f"Running {agent_name}...")
        result = run_agent(db, agent_name)
        results.append(result)

        if result["status"] == "success":
            data = result.get("data", {})
            print(f"  ✓ {agent_name}: {data.get('artifacts_collected', 0)} artifacts, "
                  f"{data.get('claims_proposed', 0)} claims")
        else:
            print(f"  ✗ {agent_name}: {result.get('error', 'unknown error')}")

    # Summary
    successful = sum(1 for r in results if r["status"] == "success")
    print(f"\n{'='*60}")
    print(f"Completed: {successful}/{len(agents)} agents successful")
    print(f"{'='*60}\n")

    # Send summary alert if any failed
    failed = [r["agent"] for r in results if r["status"] != "success"]
    if failed:
        send_alert("AGENT_RUN_PARTIAL", f"{len(failed)} agents failed: {', '.join(failed)}")
    else:
        # Write success log
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "agents_run": len(agents),
            "all_successful": True,
        }
        log_file = PROJECT_ROOT / "data" / "scheduler.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

    return results


def daemon_mode(db, interval_minutes: int = 60):
    """Run agents periodically."""
    print(f"Starting FGIP scheduler daemon (interval: {interval_minutes}m)")
    send_alert("SCHEDULER_START", f"Daemon started, interval: {interval_minutes}m")

    while True:
        try:
            run_all_agents(db)
        except Exception as e:
            send_alert("SCHEDULER_ERROR", f"Daemon error: {e}")

        print(f"Sleeping {interval_minutes} minutes...")
        time.sleep(interval_minutes * 60)


def main():
    parser = argparse.ArgumentParser(description="FGIP Agent Scheduler")
    parser.add_argument("--db", default="fgip.db", help="Database path")
    parser.add_argument("--agent", help="Run specific agent")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon")
    parser.add_argument("--interval", type=int, default=60, help="Daemon interval (minutes)")
    args = parser.parse_args()

    # Change to project root
    os.chdir(PROJECT_ROOT)

    db = FGIPDatabase(args.db)

    if args.daemon:
        daemon_mode(db, args.interval)
    elif args.agent:
        result = run_agent(db, args.agent)
        print(json.dumps(result, indent=2))
    else:
        run_all_agents(db)


if __name__ == "__main__":
    main()
