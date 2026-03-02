"""FGIP Web UI - Interactive Graph Visualization.

Features:
- Interactive Cytoscape.js graph
- Node click-through to sources
- Signal convergence dashboard
- Risk scoring display

Run: python3 web/app.py
"""

import json
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, render_template, jsonify, request
from fgip.db import FGIPDatabase
from fgip.analysis.risk_scorer import RiskScorer
from fgip.analysis.gap_detector import GapDetector
from fgip.verification import run_verification, quick_verify

app = Flask(__name__,
            template_folder='templates',
            static_folder='static')

DB_PATH = "fgip.db"


def get_db():
    """Get database connection."""
    return FGIPDatabase(DB_PATH)


@app.route('/')
def index():
    """Main dashboard."""
    return render_template('index.html')


@app.route('/api/graph')
def api_graph():
    """Return graph data in Cytoscape.js format."""
    db = get_db()
    conn = db.connect()

    # Get all nodes
    nodes_rows = conn.execute("""
        SELECT node_id, name, node_type, metadata FROM nodes
    """).fetchall()

    nodes = []
    for row in nodes_rows:
        metadata = json.loads(row["metadata"]) if row["metadata"] else {}
        signal_type = metadata.get("signal_type", "")

        # Determine node class for styling
        node_class = row["node_type"].lower()
        if signal_type:
            node_class = f"{node_class} signal-{signal_type.replace('_', '-')}"
        if row["node_id"].startswith("crime-"):
            node_class = f"{node_class} crime"

        nodes.append({
            "data": {
                "id": row["node_id"],
                "label": row["name"],
                "type": row["node_type"],
                "metadata": metadata,
            },
            "classes": node_class
        })

    # Get all edges
    edges_rows = conn.execute("""
        SELECT from_node_id, to_node_id, edge_type, notes, confidence, assertion_level
        FROM edges
    """).fetchall()

    edges = []
    for row in edges_rows:
        edge_class = row["edge_type"].lower().replace("_", "-")
        if row["assertion_level"]:
            edge_class += f" {row['assertion_level'].lower()}"

        edges.append({
            "data": {
                "source": row["from_node_id"],
                "target": row["to_node_id"],
                "type": row["edge_type"],
                "detail": row["notes"] or "",
                "confidence": row["confidence"],
                "assertion_level": row["assertion_level"],
            },
            "classes": edge_class
        })

    return jsonify({
        "nodes": nodes,
        "edges": edges
    })


@app.route('/api/node/<node_id>')
def api_node_detail(node_id):
    """Get detailed info for a node including sources."""
    db = get_db()
    conn = db.connect()

    # Get node
    node = conn.execute("""
        SELECT * FROM nodes WHERE node_id = ?
    """, (node_id,)).fetchone()

    if not node:
        return jsonify({"error": "Node not found"}), 404

    # Get related claims
    claims = conn.execute("""
        SELECT c.* FROM claims c
        JOIN edges e ON c.claim_id = e.claim_id
        WHERE e.from_node_id = ? OR e.to_node_id = ?
        LIMIT 20
    """, (node_id, node_id)).fetchall()

    # Get sources for these claims
    claim_ids = [c["claim_id"] for c in claims]
    sources = []
    if claim_ids:
        placeholders = ",".join("?" * len(claim_ids))
        sources = conn.execute(f"""
            SELECT DISTINCT s.* FROM sources s
            JOIN claim_sources cs ON s.source_id = cs.source_id
            WHERE cs.claim_id IN ({placeholders})
        """, claim_ids).fetchall()

    # Get edges
    edges = conn.execute("""
        SELECT e.*,
               fn.name as from_name,
               tn.name as to_name
        FROM edges e
        JOIN nodes fn ON e.from_node_id = fn.node_id
        JOIN nodes tn ON e.to_node_id = tn.node_id
        WHERE e.from_node_id = ? OR e.to_node_id = ?
    """, (node_id, node_id)).fetchall()

    return jsonify({
        "node": {
            "node_id": node["node_id"],
            "name": node["name"],
            "node_type": node["node_type"],
            "metadata": json.loads(node["metadata"]) if node["metadata"] else {},
        },
        "claims": [dict(c) for c in claims],
        "sources": [{"url": s["url"], "tier": s["tier"], "domain": s["domain"]} for s in sources],
        "edges": [dict(e) for e in edges],
    })


@app.route('/api/stats')
def api_stats():
    """Get database statistics."""
    db = get_db()
    conn = db.connect()

    stats = {
        "nodes": conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0],
        "edges": conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0],
        "sources": conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
        "claims": conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0],
    }

    # Node types breakdown
    node_types = conn.execute("""
        SELECT node_type, COUNT(*) as count
        FROM nodes GROUP BY node_type ORDER BY count DESC
    """).fetchall()
    stats["node_types"] = {row["node_type"]: row["count"] for row in node_types}

    # Edge types breakdown
    edge_types = conn.execute("""
        SELECT edge_type, COUNT(*) as count
        FROM edges GROUP BY edge_type ORDER BY count DESC
    """).fetchall()
    stats["edge_types"] = {row["edge_type"]: row["count"] for row in edge_types}

    # Source tiers
    tiers = conn.execute("""
        SELECT tier, COUNT(*) as count
        FROM sources GROUP BY tier ORDER BY tier
    """).fetchall()
    stats["source_tiers"] = {f"Tier {row['tier']}": row["count"] for row in tiers}

    # Signal nodes
    stats["signal_nodes"] = conn.execute("""
        SELECT COUNT(*) FROM nodes WHERE metadata LIKE '%signal_type%'
    """).fetchone()[0]

    # Crime nodes
    stats["crime_nodes"] = conn.execute("""
        SELECT COUNT(*) FROM nodes WHERE node_id LIKE 'crime-%'
    """).fetchone()[0]

    return jsonify(stats)


@app.route('/api/risk/thesis')
def api_risk_thesis():
    """Get thesis risk score."""
    db = get_db()
    scorer = RiskScorer(db)

    result = scorer.thesis_risk_score()

    return jsonify({
        "score": result.score,
        "factors": result.factors,
        "signal_confirmations": result.signal_confirmations,
        "accountability_confirmations": result.accountability_confirmations,
    })


@app.route('/api/risk/portfolio')
def api_risk_portfolio():
    """Get portfolio risk summary."""
    db = get_db()
    scorer = RiskScorer(db)

    result = scorer.portfolio_risk_summary()

    return jsonify(result)


@app.route('/api/both-sides')
def api_both_sides():
    """Find entities appearing on both problem and correction sides."""
    db = get_db()
    conn = db.connect()

    # Problem and correction edge types
    problem_types = ('LOBBIED_FOR', 'DONATED_TO', 'FUNDED_BY', 'REGISTERED_AS_AGENT',
                    'FILED_AMICUS', 'OWNS', 'INVESTED_IN', 'HAS_LEVERAGE_OVER')
    correction_types = ('AWARDED_GRANT', 'BUILT_IN', 'FUNDED_PROJECT', 'RECEIVED_FUNDING',
                       'INVESTED_IN', 'ENABLES', 'FUNDS')

    # Find entities with edges in both categories
    sql = """
    SELECT
        n.node_id, n.name, n.node_type,
        GROUP_CONCAT(DISTINCT e1.edge_type) as problem_edges,
        GROUP_CONCAT(DISTINCT e2.edge_type) as correction_edges,
        COUNT(DISTINCT e1.edge_id) as problem_count,
        COUNT(DISTINCT e2.edge_id) as correction_count
    FROM nodes n
    JOIN edges e1 ON n.node_id = e1.from_node_id
    JOIN edges e2 ON n.node_id = e2.from_node_id
    WHERE e1.edge_type IN ({}) AND e2.edge_type IN ({})
    GROUP BY n.node_id
    ORDER BY (COUNT(DISTINCT e1.edge_id) + COUNT(DISTINCT e2.edge_id)) DESC
    """.format(','.join('?' * len(problem_types)), ','.join('?' * len(correction_types)))

    rows = conn.execute(sql, problem_types + correction_types).fetchall()

    patterns = []
    for row in rows:
        patterns.append({
            "node_id": row["node_id"],
            "name": row["name"],
            "node_type": row["node_type"],
            "problem_edges": row["problem_edges"],
            "correction_edges": row["correction_edges"],
            "problem_count": row["problem_count"],
            "correction_count": row["correction_count"],
        })

    return jsonify({
        "count": len(patterns),
        "patterns": patterns
    })


@app.route('/api/runway', methods=['POST'])
def api_runway():
    """Personal purchasing power runway calculator.

    Uses FGIP-validated inflation (M2=6.3%) to calculate real savings yield,
    real debt cost, and financial runway under different scenarios.

    Request body (JSON):
        monthly_expenses: Monthly burn rate in USD (required)
        current_savings: Current liquid savings in USD (required)
        savings_yield: Savings APY as decimal (default: 0.045)
        debt_balance: Total debt in USD (default: 0)
        debt_apr: Weighted average APR as decimal (default: 0)
        income_monthly: Monthly income in USD (default: 0)

    Returns:
        JSON with real rates, runway calculations, scenario shocks,
        thesis connection, and actionable insights.
    """
    from fgip.analysis.purchasing_power import (
        PurchasingPowerAnalyzer,
        PersonalScenario,
    )

    data = request.json or {}

    # Validate required fields
    if 'monthly_expenses' not in data or 'current_savings' not in data:
        return jsonify({
            "error": "monthly_expenses and current_savings are required"
        }), 400

    try:
        scenario = PersonalScenario(
            monthly_expenses=float(data['monthly_expenses']),
            current_savings=float(data['current_savings']),
            savings_yield=float(data.get('savings_yield', 0.045)),
            debt_balance=float(data.get('debt_balance', 0.0)),
            debt_apr=float(data.get('debt_apr', 0.0)),
            income_monthly=float(data.get('income_monthly', 0.0)),
        )

        analyzer = PurchasingPowerAnalyzer(DB_PATH)
        report = analyzer.analyze(scenario)

        return jsonify(report.to_dict())

    except ValueError as e:
        return jsonify({"error": f"Invalid input: {str(e)}"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/signal/convergence/<topic>')
def api_signal_convergence(topic):
    """Get signal convergence for a topic."""
    db = get_db()
    scorer = RiskScorer(db)

    result = scorer.signal_convergence(topic)

    return jsonify({
        "score": result.score,
        "categories_confirmed": [c.value for c in result.categories_confirmed],
        "confidence_level": result.confidence_level,
        "details": result.details,
    })


@app.route('/api/search')
def api_search():
    """Search nodes and claims."""
    query = request.args.get('q', '').strip()
    if not query or len(query) < 2:
        return jsonify({"results": []})

    db = get_db()
    conn = db.connect()

    # Search nodes (use FTS if available, otherwise LIKE)
    try:
        nodes = conn.execute("""
            SELECT node_id, name, node_type FROM nodes
            WHERE node_id IN (
                SELECT node_id FROM nodes_fts WHERE nodes_fts MATCH ?
            )
            LIMIT 20
        """, (query + "*",)).fetchall()
    except:
        nodes = conn.execute("""
            SELECT node_id, name, node_type FROM nodes
            WHERE name LIKE ? OR node_id LIKE ?
            LIMIT 20
        """, (f"%{query}%", f"%{query}%")).fetchall()

    return jsonify({
        "results": [
            {"type": "node", "id": n["node_id"], "name": n["name"], "node_type": n["node_type"]}
            for n in nodes
        ]
    })


@app.route('/api/gaps')
def api_gaps():
    """Get gap analysis and agent run suggestions.

    Returns:
        JSON with gaps, suggestions, and coverage statistics.

    Query params:
        limit: Maximum number of gaps to return (default 100)
        type: Filter by gap type (e.g., missing_ownership)
    """
    db = get_db()
    detector = GapDetector(db)

    # Get filter parameters
    limit = request.args.get('limit', 100, type=int)
    gap_type = request.args.get('type', None)

    # Generate full report
    report = detector.generate_report()

    # Filter gaps if type specified
    gaps = report.gaps
    if gap_type:
        gaps = [g for g in gaps if g.gap_type == gap_type]

    # Limit gaps
    gaps = gaps[:limit]

    return jsonify({
        "timestamp": report.timestamp,
        "summary": {
            "total_nodes": report.total_nodes,
            "total_edges": report.total_edges,
            "total_gaps": len(report.gaps),
            "connectivity_rate": report.coverage_stats.get("connectivity_rate", 0),
            "evidence_rate": report.coverage_stats.get("evidence_rate", 0),
        },
        "gaps_by_type": report.gap_by_type,
        "gaps": [
            {
                "gap_type": g.gap_type,
                "node_id": g.node_id,
                "node_name": g.node_name,
                "node_type": g.node_type,
                "expected_edge_type": g.expected_edge_type,
                "description": g.description,
                "priority": g.priority,
                "suggested_agent": g.suggested_agent,
            }
            for g in gaps
        ],
        "suggestions": [
            {
                "agent": s.agent,
                "targets": s.targets[:10],
                "reason": s.reason,
                "gap_count": s.gap_count,
                "priority": s.priority,
            }
            for s in report.suggestions
        ],
        "coverage": report.coverage_stats,
    })


@app.route('/api/gaps/summary')
def api_gaps_summary():
    """Get quick gap summary without full details.

    Returns:
        Condensed gap counts and top suggestions.
    """
    db = get_db()
    detector = GapDetector(db)

    stats = detector.get_coverage_stats()
    suggestions = detector.suggest_agent_runs(limit=5)

    # Quick gap counts
    gaps = detector.detect_all_gaps()
    gap_counts = {}
    for g in gaps:
        if g.gap_type not in gap_counts:
            gap_counts[g.gap_type] = 0
        gap_counts[g.gap_type] += 1

    return jsonify({
        "total_gaps": len(gaps),
        "gaps_by_type": gap_counts,
        "connectivity_rate": stats.get("connectivity_rate", 0),
        "orphan_nodes": stats.get("orphan_nodes", 0),
        "top_suggestions": [
            {"agent": s.agent, "gap_count": s.gap_count, "priority": s.priority}
            for s in suggestions[:3]
        ],
    })


@app.route('/api/verify')
def api_verify():
    """Get easter egg verification status.

    Returns:
        JSON with verification report: eggs found/total, by agent, details.
    """
    db = get_db()
    conn = db.connect()

    report = run_verification(conn)

    return jsonify({
        "timestamp": report.timestamp,
        "pipeline_health": report.pipeline_health,
        "eggs_total": report.eggs_total,
        "eggs_found": report.eggs_found,
        "eggs_missing": report.eggs_missing,
        "pass_rate": report.eggs_found / report.eggs_total if report.eggs_total > 0 else 0,
        "by_agent": report.by_agent,
        "details": report.details,
    })


@app.route('/api/health')
def api_health():
    """Get system health overview.

    Combines DB stats, easter egg verification, and gap analysis.

    Returns:
        JSON with overall system health assessment.
    """
    db = get_db()
    conn = db.connect()

    # Basic stats
    stats = {
        "nodes": conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0],
        "edges": conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0],
        "sources": conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
        "claims": conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0],
    }

    # Easter egg verification
    verify_report = run_verification(conn)
    verification = {
        "pipeline_health": verify_report.pipeline_health,
        "eggs_found": verify_report.eggs_found,
        "eggs_total": verify_report.eggs_total,
        "pass_rate": verify_report.eggs_found / verify_report.eggs_total if verify_report.eggs_total > 0 else 0,
        "missing": verify_report.eggs_missing,
    }

    # Gap analysis
    detector = GapDetector(db)
    gap_stats = detector.get_coverage_stats()
    gaps = detector.detect_all_gaps(include_temporal=False, include_reciprocal=False)
    gap_counts = {}
    for g in gaps:
        if g.gap_type not in gap_counts:
            gap_counts[g.gap_type] = 0
        gap_counts[g.gap_type] += 1

    gap_summary = {
        "total_gaps": len(gaps),
        "gaps_by_type": gap_counts,
        "connectivity_rate": gap_stats.get("connectivity_rate", 0),
        "evidence_rate": gap_stats.get("evidence_rate", 0),
        "orphan_nodes": gap_stats.get("orphan_nodes", 0),
    }

    # Overall health assessment
    issues = []
    if verify_report.pipeline_health == "broken":
        issues.append("Pipeline broken (easter eggs failing)")
    elif verify_report.pipeline_health == "degraded":
        issues.append("Pipeline degraded (some easter eggs missing)")
    if gap_stats.get("orphan_nodes", 0) > stats["nodes"] * 0.2:
        issues.append(f"High orphan rate ({gap_stats['orphan_nodes']} nodes)")
    if gap_stats.get("evidence_rate", 0) < 0.5:
        issues.append(f"Low evidence rate ({gap_stats['evidence_rate']:.0%})")

    overall = "healthy" if not issues else ("degraded" if len(issues) <= 2 else "critical")

    return jsonify({
        "overall_health": overall,
        "issues": issues,
        "stats": stats,
        "verification": verification,
        "gaps": gap_summary,
    })


@app.route('/api/agent-requests')
def api_agent_requests():
    """Get auto-generated agent capability requests.

    Returns:
        JSON list of structured agent requests based on detected gaps.
    """
    db = get_db()
    detector = GapDetector(db)

    requests = detector.generate_agent_requests(limit=10)

    return jsonify({
        "count": len(requests),
        "requests": [
            {
                "request_id": r.request_id,
                "gap_type": r.gap_type,
                "description": r.description,
                "target_entities": r.target_entities,
                "suggested_api": r.suggested_api,
                "priority": r.priority,
                "estimated_edges": r.estimated_edges,
            }
            for r in requests
        ],
    })


@app.route('/api/scenarios')
def api_scenarios():
    """Get dynamic economic scenario modeling results.

    Models how correction mechanisms (GENIUS Act, CHIPS Act) affect
    economic variables like M2 growth, inflation, and extraction rates.

    Returns:
        JSON with static/dynamic thesis scores and scenario details.
    """
    try:
        from fgip.analysis.economic_model import (
            EconomicModel, KNOWN_MECHANISMS, get_baseline_model
        )
    except ImportError:
        return jsonify({
            "error": "Economic model not available",
            "static_score": None,
            "dynamic_score": None,
            "scenarios": [],
        })

    model = get_baseline_model()

    # Model all known mechanisms
    scenarios = []
    for mech_id, mechanism in KNOWN_MECHANISMS.items():
        scenario = model.model_scenario(mechanism)
        scenarios.append({
            "scenario_id": scenario.scenario_id,
            "mechanism_id": mechanism.mechanism_id,
            "policy": mechanism.policy_node_id,
            "effect": mechanism.narrative,
            "target_variable": mechanism.target_variable,
            "expected_delta": mechanism.expected_delta,
            "confidence": mechanism.confidence,
            "extraction_before": scenario.extraction_before,
            "extraction_after": scenario.extraction_after,
            "thesis_delta": scenario.thesis_delta,
            "variable_chain": scenario.variable_chain,
        })

    # Get current variables
    variables = {
        var_id: {
            "name": var.name,
            "value": var.current_value,
            "unit": var.unit,
            "source": var.data_source,
        }
        for var_id, var in model.variables.items()
    }

    return jsonify({
        "baseline_extraction": model.compute_extraction_rate(),
        "variables": variables,
        "scenarios": scenarios,
        "key_insight": (
            "The static extraction rate includes inflation CAUSED BY Fed printing. "
            "When correction mechanisms reduce Fed printing, M2 drops, inflation drops, "
            "and extraction drops. You can't use the disease as the argument against the cure."
        ),
    })


# ============================================================================
# APPROVAL WORKFLOW ENDPOINTS
# ============================================================================

@app.route('/api/approvals')
def api_approvals():
    """Get pending proposals for approval."""
    import sqlite3 as sql
    # Use a separate connection for listing to avoid affecting approval operations
    conn = sql.connect(DB_PATH)
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

    # Get filter params
    agent = request.args.get('agent')
    proposal_type = request.args.get('type')  # 'claim' or 'edge'
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    offset = (page - 1) * per_page

    result = {"claims": [], "edges": [], "stats": {}}

    # Get pending claims
    if proposal_type is None or proposal_type == 'claim':
        query = "SELECT * FROM proposed_claims WHERE status = 'PENDING'"
        params = []
        if agent:
            query += " AND agent_name = ?"
            params.append(agent)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([per_page, offset])

        rows = conn.execute(query, params).fetchall()
        result["claims"] = rows

    # Get pending edges
    if proposal_type is None or proposal_type == 'edge':
        query = "SELECT * FROM proposed_edges WHERE status = 'PENDING'"
        params = []
        if agent:
            query += " AND agent_name = ?"
            params.append(agent)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([per_page, offset])

        rows = conn.execute(query, params).fetchall()
        result["edges"] = rows

    # Get stats
    result["stats"] = {
        "total_pending_claims": conn.execute(
            "SELECT COUNT(*) FROM proposed_claims WHERE status = 'PENDING'"
        ).fetchone()["COUNT(*)"],
        "total_pending_edges": conn.execute(
            "SELECT COUNT(*) FROM proposed_edges WHERE status = 'PENDING'"
        ).fetchone()["COUNT(*)"],
        "agents": [row["agent_name"] for row in conn.execute(
            "SELECT DISTINCT agent_name FROM proposed_claims WHERE status = 'PENDING' "
            "UNION SELECT DISTINCT agent_name FROM proposed_edges WHERE status = 'PENDING'"
        ).fetchall()],
    }

    conn.close()
    return jsonify(result)


@app.route('/api/approvals/approve', methods=['POST'])
def api_approve():
    """Approve one or more proposals."""
    from fgip.staging import accept_claim, accept_edge

    data = request.json or {}
    proposal_ids = data.get('proposal_ids', [])
    reviewer_notes = data.get('notes', 'Approved via web UI')

    if not proposal_ids:
        return jsonify({"error": "proposal_ids required"}), 400

    db = get_db()
    conn = db.connect()
    # Keep sqlite3.Row factory - staging module needs it

    results = []
    for pid in proposal_ids:
        try:
            # Determine if claim or edge
            claim = conn.execute(
                "SELECT proposal_id FROM proposed_claims WHERE proposal_id = ?", (pid,)
            ).fetchone()

            if claim:
                result = accept_claim(conn, pid, reviewer_notes, "web_ui")
                if result:
                    results.append({"proposal_id": pid, "status": "approved", "result": result})
                else:
                    results.append({"proposal_id": pid, "status": "error", "error": "Accept failed"})
            else:
                edge = conn.execute(
                    "SELECT proposal_id FROM proposed_edges WHERE proposal_id = ?", (pid,)
                ).fetchone()
                if edge:
                    result = accept_edge(conn, pid, reviewer_notes, "web_ui")
                    if result:
                        results.append({"proposal_id": pid, "status": "approved", "result": result})
                    else:
                        results.append({"proposal_id": pid, "status": "error", "error": "Accept failed"})
                else:
                    results.append({"proposal_id": pid, "status": "error", "error": "Not found"})

        except Exception as e:
            results.append({"proposal_id": pid, "status": "error", "error": str(e)})

    return jsonify({
        "approved": sum(1 for r in results if r["status"] == "approved"),
        "errors": sum(1 for r in results if r["status"] == "error"),
        "results": results
    })


@app.route('/api/approvals/reject', methods=['POST'])
def api_reject():
    """Reject one or more proposals."""
    from fgip.staging import reject_proposal

    data = request.json or {}
    proposal_ids = data.get('proposal_ids', [])
    reason = data.get('reason', 'Rejected via web UI')

    if not proposal_ids:
        return jsonify({"error": "proposal_ids required"}), 400

    db = get_db()
    conn = db.connect()

    results = []
    for pid in proposal_ids:
        try:
            reject_proposal(conn, pid, reason)
            results.append({"proposal_id": pid, "status": "rejected"})
        except Exception as e:
            results.append({"proposal_id": pid, "status": "error", "error": str(e)})

    conn.commit()

    return jsonify({
        "rejected": sum(1 for r in results if r["status"] == "rejected"),
        "errors": sum(1 for r in results if r["status"] == "error"),
        "results": results
    })


@app.route('/api/approvals/bulk-approve', methods=['POST'])
def api_bulk_approve():
    """Bulk approve proposals by agent or confidence threshold."""
    from fgip.staging import accept_claim, accept_edge

    data = request.json or {}
    agent_name = data.get('agent')
    min_confidence = float(data.get('min_confidence', 0.9))
    limit = int(data.get('limit', 100))

    db = get_db()
    conn = db.connect()
    # Keep sqlite3.Row factory - staging module needs it

    approved = 0
    errors = 0

    # Bulk approve claims
    query = "SELECT proposal_id FROM proposed_claims WHERE status = 'PENDING'"
    params = []
    if agent_name:
        query += " AND agent_name = ?"
        params.append(agent_name)
    query += " LIMIT ?"
    params.append(limit)

    claims = conn.execute(query, params).fetchall()
    for claim in claims:
        try:
            result = accept_claim(conn, claim["proposal_id"], f"Bulk approved (agent={agent_name})", "web_ui_bulk")
            if result:
                approved += 1
            else:
                errors += 1
        except Exception:
            errors += 1

    # Bulk approve edges with confidence threshold
    query = "SELECT proposal_id FROM proposed_edges WHERE status = 'PENDING' AND confidence >= ?"
    params = [min_confidence]
    if agent_name:
        query += " AND agent_name = ?"
        params.append(agent_name)
    query += " LIMIT ?"
    params.append(limit)

    edges = conn.execute(query, params).fetchall()
    for edge in edges:
        try:
            result = accept_edge(conn, edge["proposal_id"], f"Bulk approved (conf>={min_confidence})", "web_ui_bulk")
            if result:
                approved += 1
            else:
                errors += 1
        except Exception:
            errors += 1

    return jsonify({
        "approved": approved,
        "errors": errors,
        "message": f"Bulk approved {approved} proposals"
    })


@app.route('/api/system/briefing')
def api_system_briefing():
    """Get system intelligence briefing."""
    try:
        from fgip.agents.system_intelligence import SystemIntelligenceAgent

        db = get_db()
        agent = SystemIntelligenceAgent(db)
        report = agent.analyze()

        return jsonify(report)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================================
# TRADE MEMO API
# =============================================================================

@app.route('/api/trade/memo', methods=['POST'])
def api_generate_trade_memo():
    """Generate a trade memo for a thesis."""
    try:
        from fgip.agents.trade_plan_agent import TradePlanAgent

        data = request.json or {}
        thesis_id = data.get('thesis_id', 'default-thesis')
        symbol = data.get('symbol')
        direction = data.get('direction', 'BULLISH')
        time_horizon = data.get('time_horizon_days', 90)

        agent = TradePlanAgent(DB_PATH)
        memo = agent.generate_memo(
            thesis_id=thesis_id,
            symbol=symbol,
            thesis_direction=direction,
            time_horizon_days=time_horizon
        )

        # Convert to JSON-serializable format
        gates_data = [
            {
                "gate_name": g.gate_name,
                "passed": g.passed,
                "score": g.score,
                "reason": g.reason
            }
            for g in memo.gates
        ]

        return jsonify({
            "memo_id": memo.memo_id,
            "thesis_id": memo.thesis_id,
            "symbol": memo.symbol,
            "created_at": memo.created_at,
            "mechanism_layer": memo.mechanism_layer,
            "market_layer": memo.market_layer,
            "forecast_layer": memo.forecast_layer,
            "gates": gates_data,
            "gates_passed": memo.gates_passed,
            "gates_total": memo.gates_total,
            "decision": memo.decision,
            "decision_confidence": memo.decision_confidence,
            "position_sizing": memo.position_sizing,
            "risks": memo.risks,
            "counter_thesis": memo.counter_thesis,
            "invalidation_criteria": memo.invalidation_criteria,
            "evidence_count": memo.evidence_count,
            "tier_0_count": memo.tier_0_count
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/trade/memos')
def api_list_trade_memos():
    """List recent trade memos."""
    try:
        from fgip.agents.trade_plan_agent import TradePlanAgent

        limit = request.args.get('limit', 10, type=int)

        agent = TradePlanAgent(DB_PATH)
        memos = agent.get_recent_memos(limit=limit)

        return jsonify({"memos": memos})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/trade/forecast', methods=['POST'])
def api_generate_forecast():
    """Generate a forecast for a thesis."""
    try:
        from fgip.agents.forecast_agent import ForecastAgent

        data = request.json or {}
        thesis_id = data.get('thesis_id', 'default-thesis')
        symbol = data.get('symbol')
        conviction = data.get('conviction_level', 3)
        confidence = data.get('thesis_confidence', 0.5)
        time_horizon = data.get('time_horizon_days', 90)

        agent = ForecastAgent(DB_PATH)
        forecast = agent.generate_forecast(
            thesis_id=thesis_id,
            symbol=symbol,
            conviction_level=conviction,
            thesis_confidence=confidence,
            time_horizon_days=time_horizon
        )

        return jsonify({
            "forecast_id": forecast.forecast_id,
            "thesis_id": forecast.thesis_id,
            "symbol": forecast.symbol,
            "return_distribution": {
                "p10": forecast.return_distribution.p10,
                "p50": forecast.return_distribution.p50,
                "p90": forecast.return_distribution.p90,
                "unit": forecast.return_distribution.unit
            },
            "drawdown_distribution": {
                "p10": forecast.drawdown_distribution.p10,
                "p50": forecast.drawdown_distribution.p50,
                "p90": forecast.drawdown_distribution.p90,
                "unit": forecast.drawdown_distribution.unit
            },
            "probability_of_loss": forecast.probability_of_loss,
            "probability_of_thesis": forecast.probability_of_thesis,
            "probability_of_timing": forecast.probability_of_timing,
            "time_horizon_days": forecast.time_horizon_days,
            "confidence_in_forecast": forecast.confidence_in_forecast,
            "data_quality_score": forecast.data_quality_score,
            "prior_forecasts": forecast.prior_forecasts,
            "prior_accuracy": forecast.prior_accuracy,
            "created_at": forecast.created_at
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/trade/tape/<symbol>')
def api_market_tape(symbol):
    """Get market tape for a symbol."""
    try:
        from fgip.agents.market_tape import MarketTapeAgent

        agent = MarketTapeAgent(DB_PATH)
        tape = agent.fetch_tape(symbol.upper())

        if not tape:
            return jsonify({"error": f"No tape data for {symbol}"}), 404

        return jsonify({
            "symbol": tape.symbol,
            "snapshot": {
                "price": tape.snapshot.price,
                "prev_close": tape.snapshot.prev_close,
                "day_change_pct": tape.snapshot.day_change_pct,
                "volume": tape.snapshot.volume,
                "avg_volume": tape.snapshot.avg_volume,
                "fifty_two_week_high": tape.snapshot.fifty_two_week_high,
                "fifty_two_week_low": tape.snapshot.fifty_two_week_low,
                "pct_from_high": tape.snapshot.pct_from_high,
                "pct_from_low": tape.snapshot.pct_from_low
            },
            "technicals": {
                "sma_20": tape.technicals.sma_20,
                "sma_50": tape.technicals.sma_50,
                "sma_200": tape.technicals.sma_200,
                "rsi_14": tape.technicals.rsi_14,
                "volume_ratio": tape.technicals.volume_ratio,
                "trend": tape.technicals.trend,
                "signals": tape.technicals.signals
            },
            "events": [
                {
                    "event_type": e.event_type,
                    "description": e.description,
                    "magnitude": e.magnitude
                }
                for e in tape.events
            ],
            "tape_verdict": tape.tape_verdict,
            "confidence": tape.confidence,
            "analysis_time": tape.analysis_time
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/trade/kalshi', methods=['POST'])
def api_kalshi_signal():
    """Get prediction market signal for a thesis."""
    try:
        from fgip.agents.kalshi_signal import KalshiSignalAgent

        data = request.json or {}
        thesis_id = data.get('thesis_id', 'default-thesis')
        keywords = data.get('keywords', ['fed'])
        direction = data.get('direction', 'BULLISH')

        agent = KalshiSignalAgent(DB_PATH)
        signal = agent.get_thesis_signal(thesis_id, keywords, direction)

        if not signal:
            return jsonify({"error": "No relevant prediction markets found"}), 404

        return jsonify({
            "market_id": signal.market_id,
            "thesis_relevance": signal.thesis_relevance,
            "implied_probability": signal.implied_probability,
            "confidence": signal.confidence,
            "direction": signal.direction,
            "timestamp": signal.timestamp
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/trade/calibration')
def api_calibration_report():
    """Get forecast calibration report."""
    try:
        from fgip.agents.forecast_agent import ForecastAgent

        agent = ForecastAgent(DB_PATH)
        report = agent.get_calibration_report()

        return jsonify(report)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================================
# PIPELINE HEALTH API
# =============================================================================

@app.route('/api/pipeline/health')
def api_pipeline_health():
    """Get pipeline health including leak detection."""
    try:
        from fgip.pipeline.leak_detector import LeakDetector
        from fgip.agents.pipeline_orchestrator import PipelineOrchestrator

        detector = LeakDetector(DB_PATH)
        report = detector.check_invariants()

        orchestrator = PipelineOrchestrator(DB_PATH)
        queue_status = orchestrator.get_queue_status()

        return jsonify({
            "health_status": report.health_status,
            "total_leaks": report.total_leaks,
            "leak_breakdown": {
                "no_evidence": report.leak_1_no_evidence,
                "no_reason_codes": report.leak_2_no_reason_codes,
                "orphan_artifacts": report.leak_3_orphan_proposals,
                "bypass_writes": report.leak_4_bypass_writes,
                "fk_violations": report.leak_5_fk_violations
            },
            "queue_status": {
                "pending": queue_status.pending,
                "filtering": queue_status.filtering,
                "filtered": queue_status.filtered,
                "extracting": queue_status.extracting,
                "extracted": queue_status.extracted,
                "failed": queue_status.failed,
                "total": queue_status.total()
            },
            "proposals_checked": report.total_proposals_checked,
            "timestamp": report.timestamp
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/pipeline/cycle', methods=['POST'])
def api_pipeline_cycle():
    """Run one processing cycle."""
    try:
        from fgip.agents.pipeline_orchestrator import PipelineOrchestrator

        data = request.json or {}
        filter_batch = data.get('filter_batch_size', 100)
        extract_batch = data.get('extract_batch_size', 50)

        orchestrator = PipelineOrchestrator(DB_PATH)
        report = orchestrator.process_cycle(
            filter_batch_size=filter_batch,
            extract_batch_size=extract_batch
        )

        return jsonify({
            "cycle_id": report.cycle_id,
            "started_at": report.started_at,
            "completed_at": report.completed_at,
            "pending_before": report.pending_before,
            "artifacts_filtered": report.artifacts_filtered,
            "artifacts_extracted": report.artifacts_extracted,
            "artifacts_failed": report.artifacts_failed,
            "routing": {
                "fast_track": report.fast_track_count,
                "human_review": report.human_review_count,
                "deprioritize": report.deprioritize_count
            },
            "proposals_created": {
                "claims": report.claims_created,
                "edges": report.edges_created
            },
            "errors": report.errors[:10] if report.errors else []
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/pipeline/queue')
def api_pipeline_queue():
    """Get artifact queue status."""
    try:
        from fgip.agents.pipeline_orchestrator import PipelineOrchestrator

        orchestrator = PipelineOrchestrator(DB_PATH)
        status = orchestrator.get_queue_status()

        return jsonify({
            "pending": status.pending,
            "filtering": status.filtering,
            "filtered": status.filtered,
            "extracting": status.extracting,
            "extracted": status.extracted,
            "failed": status.failed,
            "total": status.total()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    print("Starting FGIP Web UI...")
    print("Open http://localhost:5000 in your browser")
    app.run(debug=True, host='0.0.0.0', port=5000)
