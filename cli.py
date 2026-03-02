#!/usr/bin/env python3
"""
FGIP CLI - Conversational interface for the claims-first knowledge graph.

Commands:
  query <entity>        - Show all edges connected to a node
  trace <from> → <to>   - Find paths between nodes with evidence quality
  status                - Summary of claims and evidence coverage
  missing               - List claims that need source URLs
  upgrade <claim_id>    - Add artifact for a claim
  add-node <name> --type TYPE
  add-edge <from> → <to> --rel RELATIONSHIP --claim CLAIM_ID
  add-claim <text> --topic TOPIC [--source URL]
  help                  - Show this help
  quit/exit             - Exit the CLI
"""

import cmd
import sqlite3
import sys
import re
from pathlib import Path
from typing import Optional

from schema import init_db
from loader import load_all
from extractor import build_graph, add_node, add_edge, add_claim
from query import (
    trace_causality, ownership_loop, contradiction_check,
    correction_score, get_claim_status, get_status_summary,
    normalize_node_id
)
from signal_layer import (
    load_signal_layer, get_signal_sources, get_accountability_cases,
    trace_crime_enablers, crime_downstream
)
from risk_scorer import (
    thesis_risk_score, investment_risk_score, signal_convergence,
    scotus_impact_assessment, portfolio_risk_summary, SIGNAL_CATEGORIES
)


class FGIPShell(cmd.Cmd):
    """Interactive shell for FGIP knowledge graph."""

    intro = """
╔═══════════════════════════════════════════════════════════════════╗
║  FGIP Engine - Claims-First Causality Graph                      ║
║  Type 'help' for commands, 'quit' to exit                        ║
╚═══════════════════════════════════════════════════════════════════╝
"""
    prompt = 'fgip> '

    def __init__(self, db_path: str = 'fgip.db'):
        super().__init__()
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self._connect()

    def _connect(self):
        """Connect to database, initialize if needed."""
        db_exists = Path(self.db_path).exists()
        self.conn = init_db(self.db_path)
        if not db_exists:
            print(f"Initialized new database: {self.db_path}")

    def _ensure_conn(self) -> sqlite3.Connection:
        """Ensure we have a valid connection."""
        if self.conn is None:
            self._connect()
        return self.conn

    # ─────────────────────────────────────────────────────────────────
    # Query Command
    # ─────────────────────────────────────────────────────────────────

    def do_query(self, arg: str):
        """Query edges connected to an entity: query <entity name>"""
        if not arg.strip():
            print("Usage: query <entity name>")
            return

        conn = self._ensure_conn()
        cursor = conn.cursor()

        # Normalize the node (strip quotes)
        entity = arg.strip().strip('"\'')
        node_id = normalize_node_id(cursor, entity)
        if not node_id:
            print(f"Entity not found: {arg}")
            return

        # Get node info
        cursor.execute("SELECT * FROM nodes WHERE node_id = ?", (node_id,))
        node = cursor.fetchone()
        print(f"\n═══ {node['name']} ({node['node_type']}) ═══")

        # Get all edges involving this node
        cursor.execute("""
            SELECT e.*, c.claim_text, c.status as claim_status, c.topic,
                   fn.name as from_name, tn.name as to_name
            FROM edges e
            LEFT JOIN claims c ON e.claim_id = c.claim_id
            LEFT JOIN nodes fn ON e.from_node = fn.node_id
            LEFT JOIN nodes tn ON e.to_node = tn.node_id
            WHERE e.from_node = ? OR e.to_node = ?
            ORDER BY e.created_at
        """, (node_id, node_id))

        edges = cursor.fetchall()
        if not edges:
            print("No edges found.")
            return

        print(f"\nFound {len(edges)} edges:\n")

        for i, edge in enumerate(edges, 1):
            direction = "→" if edge['from_node'] == node_id else "←"
            other = edge['to_name'] if edge['from_node'] == node_id else edge['from_name']
            rel = edge['relationship']
            detail = f" ({edge['detail']})" if edge['detail'] else ""

            status_icon = {
                'VERIFIED': '✓',
                'EVIDENCED': '◐',
                'PARTIAL': '○',
                'MISSING': '✗',
            }.get(edge['claim_status'], '?')

            print(f"  {i}. {direction} {other}")
            print(f"     Relationship: {rel}{detail}")
            print(f"     Claim: {edge['claim_id']} [{status_icon} {edge['claim_status']}]")
            if edge['claim_text']:
                # Truncate long claims
                text = edge['claim_text'][:80] + "..." if len(edge['claim_text']) > 80 else edge['claim_text']
                print(f"     \"{text}\"")
            print()

    # ─────────────────────────────────────────────────────────────────
    # Trace Command
    # ─────────────────────────────────────────────────────────────────

    def do_trace(self, arg: str):
        """Trace causality between two entities: trace <from> → <to>"""
        # Parse "from → to" or "from -> to" or "from to"
        parts = re.split(r'\s*[→\->]+\s*', arg.strip())
        if len(parts) < 2:
            parts = arg.strip().split(maxsplit=1)

        if len(parts) < 2:
            print("Usage: trace <from entity> → <to entity>")
            return

        # Strip quotes from entity names
        start = parts[0].strip().strip('"\'')
        end = parts[1].strip().strip('"\'')

        conn = self._ensure_conn()
        paths = trace_causality(conn, start, end)

        if not paths:
            print(f"\nNo path found between '{start}' and '{end}'")
            return

        print(f"\n═══ Causality Trace: {start} → {end} ═══")
        print(f"Found {len(paths)} path(s)\n")

        for i, path in enumerate(paths, 1):
            print(f"─── Path {i} ({path.hops} hops, {path.evidence_score:.0f}% Tier 0/1 evidenced) ───\n")

            for j, edge in enumerate(path.path, 1):
                from_name = edge.get('from_name', edge['from_node'])
                to_name = edge.get('to_name', edge['to_node'])
                rel = edge['relationship']
                detail = f" ({edge['detail']})" if edge.get('detail') else ""

                tier = edge.get('best_tier')
                tier_str = f"Tier {tier}" if tier is not None else "No source"
                status = edge.get('status', 'UNKNOWN')

                print(f"  {j}. {from_name} --{rel}--> {to_name}{detail}")
                print(f"     Claim: {edge['claim_id']} [{status}, {tier_str}]")
                if edge.get('claim_text'):
                    text = edge['claim_text'][:70] + "..." if len(edge['claim_text']) > 70 else edge['claim_text']
                    print(f"     \"{text}\"")
                print()

            if path.weakest_link:
                wl = path.weakest_link
                print(f"  ⚠ Weakest link: {wl.get('from_name', wl['from_node'])} → {wl.get('to_name', wl['to_node'])}")
                print(f"    Tier: {wl.get('best_tier', 'No source')}")
            print()

    # ─────────────────────────────────────────────────────────────────
    # Status Command
    # ─────────────────────────────────────────────────────────────────

    def do_status(self, arg: str):
        """Show database status summary."""
        conn = self._ensure_conn()
        summary = get_status_summary(conn)

        print("\n═══ FGIP Database Status ═══\n")

        print(f"Total Claims: {summary['total_claims']}")
        print("  By status:")
        for status, count in summary.get('claims_by_status', {}).items():
            icon = {'VERIFIED': '✓', 'EVIDENCED': '◐', 'PARTIAL': '○', 'MISSING': '✗'}.get(status, '?')
            print(f"    {icon} {status}: {count}")

        print(f"\nTotal Edges: {summary['total_edges']}")
        print(f"  With Tier 0/1 sources: {summary['edges_with_tier01']}")
        print(f"\n  Evidence Coverage: {summary['evidence_coverage']}%")

        # Node counts
        cursor = conn.cursor()
        cursor.execute("SELECT node_type, COUNT(*) FROM nodes GROUP BY node_type")
        nodes_by_type = dict(cursor.fetchall())
        total_nodes = sum(nodes_by_type.values())

        print(f"\nTotal Nodes: {total_nodes}")
        print("  By type:")
        for ntype, count in sorted(nodes_by_type.items()):
            print(f"    {ntype}: {count}")

        print()

    # ─────────────────────────────────────────────────────────────────
    # Missing Command
    # ─────────────────────────────────────────────────────────────────

    def do_missing(self, arg: str):
        """List claims with status MISSING (need source URLs)."""
        conn = self._ensure_conn()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT claim_id, claim_text, topic, required_tier
            FROM claims
            WHERE status = 'MISSING'
            ORDER BY topic, claim_id
        """)

        rows = cursor.fetchall()
        if not rows:
            print("\nNo MISSING claims. All claims have at least one source URL.")
            return

        print(f"\n═══ MISSING Claims ({len(rows)} total) ═══\n")

        current_topic = None
        for row in rows:
            if row['topic'] != current_topic:
                current_topic = row['topic']
                print(f"─── {current_topic} ───")

            text = row['claim_text'][:60] + "..." if len(row['claim_text']) > 60 else row['claim_text']
            print(f"  {row['claim_id']} (req Tier {row['required_tier']})")
            print(f"    \"{text}\"")
        print()

    # ─────────────────────────────────────────────────────────────────
    # Upgrade Command
    # ─────────────────────────────────────────────────────────────────

    def do_upgrade(self, arg: str):
        """Upgrade a claim with artifact: upgrade <claim_id>"""
        claim_id = arg.strip()
        if not claim_id:
            print("Usage: upgrade <claim_id>")
            return

        conn = self._ensure_conn()
        status = get_claim_status(conn, claim_id)

        if not status:
            print(f"Claim not found: {claim_id}")
            return

        print(f"\n═══ Upgrade Claim: {claim_id} ═══")
        print(f"Claim: \"{status.claim_text}\"")
        print(f"Topic: {status.topic}")
        print(f"Current Status: {status.status}")
        print(f"Required Tier: {status.required_tier}")
        print(f"Best Source Tier: {status.best_tier if status.best_tier is not None else 'None'}")

        if status.sources:
            print(f"\nExisting Sources ({len(status.sources)}):")
            for src in status.sources:
                print(f"  - Tier {src['tier']}: {src['url'][:60]}...")

        print("\nTo upgrade, add a source with artifact:")
        print(f"  add-source {claim_id} --url <URL> --artifact <path>")
        print()

    # ─────────────────────────────────────────────────────────────────
    # Add Commands
    # ─────────────────────────────────────────────────────────────────

    def do_add_node(self, arg: str):
        """Add a new node: add-node <name> --type TYPE"""
        # Simple arg parsing
        match = re.match(r'"([^"]+)"\s+--type\s+(\w+)', arg)
        if not match:
            match = re.match(r'(\S+)\s+--type\s+(\w+)', arg)

        if not match:
            print("Usage: add-node <name> --type TYPE")
            print("       add-node \"Multi Word Name\" --type COMPANY")
            return

        name = match.group(1)
        node_type = match.group(2).upper()

        try:
            conn = self._ensure_conn()
            node_id = add_node(conn, name, node_type)
            print(f"Created node: {node_id} ({name}, {node_type})")
        except Exception as e:
            print(f"Error: {e}")

    # Alias for hyphenated command
    do_add_node.__name__ = 'do_add-node'

    def do_add_edge(self, arg: str):
        """Add a new edge: add-edge <from> → <to> --rel RELATIONSHIP --claim CLAIM_ID"""
        # Parse: "Entity A" → "Entity B" --rel REL --claim FGIP-XXX
        pattern = r'"?([^"→]+)"?\s*[→\->]+\s*"?([^"]+)"?\s+--rel\s+(\w+)\s+--claim\s+(FGIP-\d+)'
        match = re.match(pattern, arg)

        if not match:
            print("Usage: add-edge <from> → <to> --rel RELATIONSHIP --claim CLAIM_ID")
            print("       add-edge \"Entity A\" → \"Entity B\" --rel SUPPLIES --claim FGIP-000042")
            return

        from_entity = match.group(1).strip()
        to_entity = match.group(2).strip()
        relationship = match.group(3).upper()
        claim_id = match.group(4)

        try:
            conn = self._ensure_conn()
            cursor = conn.cursor()

            # Normalize node IDs
            from_node = normalize_node_id(cursor, from_entity)
            to_node = normalize_node_id(cursor, to_entity)

            if not from_node:
                print(f"From node not found: {from_entity}")
                return
            if not to_node:
                print(f"To node not found: {to_entity}")
                return

            edge_id = add_edge(conn, from_node, to_node, relationship, claim_id)
            print(f"Created edge {edge_id}: {from_node} --{relationship}--> {to_node}")
        except Exception as e:
            print(f"Error: {e}")

    do_add_edge.__name__ = 'do_add-edge'

    def do_add_claim(self, arg: str):
        """Add a new claim: add-claim <text> --topic TOPIC [--source URL]"""
        # Parse: "claim text" --topic Topic [--source URL]
        pattern = r'"([^"]+)"\s+--topic\s+(\w+)(?:\s+--source\s+(\S+))?'
        match = re.match(pattern, arg)

        if not match:
            print("Usage: add-claim \"<claim text>\" --topic TOPIC [--source URL]")
            return

        claim_text = match.group(1)
        topic = match.group(2)
        source_url = match.group(3)

        try:
            conn = self._ensure_conn()
            claim_id = add_claim(conn, claim_text, topic, source_url)
            status = "PARTIAL" if source_url else "MISSING"
            print(f"Created claim: {claim_id} [{status}]")
            print(f"  \"{claim_text[:60]}...\"" if len(claim_text) > 60 else f"  \"{claim_text}\"")
        except Exception as e:
            print(f"Error: {e}")

    do_add_claim.__name__ = 'do_add-claim'

    # ─────────────────────────────────────────────────────────────────
    # Analysis Commands
    # ─────────────────────────────────────────────────────────────────

    def do_ownership_loop(self, arg: str):
        """Detect ownership cycles: ownership-loop <entity>"""
        if not arg.strip():
            print("Usage: ownership-loop <entity>")
            return

        conn = self._ensure_conn()
        cycle = ownership_loop(conn, arg.strip())

        if not cycle:
            print(f"\nNo ownership cycle found involving: {arg}")
            return

        print(f"\n═══ Ownership Cycle Detected ═══\n")
        for i, edge in enumerate(cycle, 1):
            print(f"  {i}. {edge.get('from_name', edge['from_node'])} --{edge['relationship']}--> {edge.get('to_name', edge['to_node'])}")
            if edge.get('detail'):
                print(f"     Detail: {edge['detail']}")
        print()

    do_ownership_loop.__name__ = 'do_ownership-loop'

    def do_contradictions(self, arg: str):
        """Check for contradictions: contradictions <entity>"""
        if not arg.strip():
            print("Usage: contradictions <entity>")
            return

        conn = self._ensure_conn()
        results = contradiction_check(conn, arg.strip())

        if not results:
            print(f"\nNo contradictions found for: {arg}")
            return

        print(f"\n═══ Contradictions Found ═══\n")
        for c in results:
            print(f"Type: {c['type']}")
            print(f"  {c['description']}")
            print()

    def do_correction_score(self, arg: str):
        """Score correction benefit: correction-score <company>"""
        if not arg.strip():
            print("Usage: correction-score <company>")
            return

        conn = self._ensure_conn()
        result = correction_score(conn, arg.strip())

        if 'error' in result:
            print(f"\nError: {result['error']}")
            return

        print(f"\n═══ Correction Score: {result['company']} ═══\n")
        print(f"Total Score: {result['total_score']}")
        print(f"\nComponents:")
        for k, v in result['components'].items():
            sign = '+' if v >= 0 else ''
            print(f"  {k}: {sign}{v}")
        print(f"\nEdge count: {result['edge_count']}")
        print()

    do_correction_score.__name__ = 'do_correction-score'

    # ─────────────────────────────────────────────────────────────────
    # Signal Layer Commands
    # ─────────────────────────────────────────────────────────────────

    def do_signal(self, arg: str):
        """Signal layer commands: signal <list|convergence|who-covers> [args]"""
        parts = arg.strip().split(maxsplit=1)
        if not parts:
            print("Usage: signal <list|convergence|who-covers> [args]")
            return

        subcmd = parts[0].lower()
        subarg = parts[1] if len(parts) > 1 else ''

        if subcmd == 'list':
            self._signal_list()
        elif subcmd == 'convergence':
            self._signal_convergence(subarg)
        elif subcmd in ['who-covers', 'who_covers']:
            self._signal_who_covers(subarg)
        elif subcmd == 'load':
            self._signal_load()
        else:
            print("Usage: signal <list|convergence|who-covers|load> [args]")

    def _signal_list(self):
        """List all independent media/signal sources."""
        conn = self._ensure_conn()
        sources = get_signal_sources(conn)

        if not sources:
            print("\nNo signal sources found. Run 'signal load' to add signal layer.")
            return

        print(f"\n═══ Signal Sources ({len(sources)} total) ═══\n")

        by_type = {}
        for src in sources:
            stype = src.get('node_type', 'OTHER')
            if stype not in by_type:
                by_type[stype] = []
            by_type[stype].append(src)

        for stype, nodes in sorted(by_type.items()):
            print(f"─── {stype} ───")
            for node in nodes:
                import json
                meta = json.loads(node.get('metadata', '{}') or '{}')
                signal_type = meta.get('signal_type', 'unknown')
                print(f"  {node['name']}")
                print(f"    Signal type: {signal_type}")
                topics = meta.get('topics_covered', [])
                if topics:
                    print(f"    Topics: {', '.join(topics[:4])}")
            print()

    def _signal_convergence(self, topic: str):
        """Check signal convergence for a topic."""
        if not topic:
            print("Usage: signal convergence <topic>")
            print("Topics: reshoring, china_threat, defense_industrial_base, institutional_capture, correction")
            return

        conn = self._ensure_conn()
        result = signal_convergence(conn, topic)

        print(f"\n═══ Signal Convergence: {topic} ═══\n")
        print(f"Score: {result.score}/6 ({result.confidence_level.upper()} confidence)")
        print(f"\nCategories confirmed ({len(result.categories_confirmed)}):")

        for cat in SIGNAL_CATEGORIES:
            confirmed = '✓' if cat in result.categories_confirmed else '○'
            desc = SIGNAL_CATEGORIES[cat]
            print(f"  {confirmed} {cat}: {desc}")

            # Show specific signals
            signals = result.signals_by_category.get(cat, [])
            for sig in signals[:3]:
                print(f"      → {sig['name']}")

        print()

    def _signal_who_covers(self, entity: str):
        """Find which media covers an entity."""
        if not entity:
            print("Usage: signal who-covers <entity>")
            return

        conn = self._ensure_conn()
        cursor = conn.cursor()

        # Find entity node
        entity = entity.strip().strip('"\'')
        node_id = normalize_node_id(cursor, entity)
        if not node_id:
            print(f"Entity not found: {entity}")
            return

        # Find edges where signal sources report on this entity
        cursor.execute("""
            SELECT fn.name as source_name, fn.metadata as source_meta,
                   e.relationship, e.detail
            FROM edges e
            JOIN nodes fn ON e.from_node = fn.node_id
            WHERE e.to_node = ? AND e.relationship IN ('REPORTS_ON', 'VALIDATES')
        """, (node_id,))

        rows = cursor.fetchall()
        if not rows:
            print(f"\nNo signal sources covering: {entity}")
            return

        print(f"\n═══ Signal Sources Covering: {entity} ═══\n")
        for row in rows:
            print(f"  {row['source_name']}")
            print(f"    Relationship: {row['relationship']}")
            if row['detail']:
                print(f"    Detail: {row['detail']}")
            print()

    def _signal_load(self):
        """Load signal and accountability layer."""
        conn = self._ensure_conn()
        nodes, edges = load_signal_layer(conn)
        print(f"\nLoaded signal layer:")
        print(f"  Nodes created: {nodes}")
        print(f"  Edges created: {edges}")
        print()

    # ─────────────────────────────────────────────────────────────────
    # Crime/Accountability Commands
    # ─────────────────────────────────────────────────────────────────

    def do_crime(self, arg: str):
        """Crime/accountability commands: crime <list|trace|downstream> [args]"""
        parts = arg.strip().split(maxsplit=1)
        if not parts:
            print("Usage: crime <list|trace|downstream> [args]")
            return

        subcmd = parts[0].lower()
        subarg = parts[1] if len(parts) > 1 else ''

        if subcmd == 'list':
            self._crime_list()
        elif subcmd == 'trace':
            self._crime_trace(subarg)
        elif subcmd == 'downstream':
            self._crime_downstream(subarg)
        else:
            print("Usage: crime <list|trace|downstream> [args]")

    def _crime_list(self):
        """List all crime/fraud cases."""
        conn = self._ensure_conn()
        cases = get_accountability_cases(conn)

        if not cases:
            print("\nNo accountability cases found. Run 'signal load' first.")
            return

        print(f"\n═══ Accountability Cases ({len(cases)} total) ═══\n")

        for case in cases:
            import json
            meta = json.loads(case.get('metadata', '{}') or '{}')
            crime_type = meta.get('type', 'unknown')
            print(f"  {case['name']}")
            print(f"    Type: {crime_type}")
            if meta.get('amount_stolen'):
                print(f"    Amount: ${meta['amount_stolen']:,}")
            if meta.get('fine'):
                print(f"    Fine: ${meta['fine']:,}")
            if meta.get('deaths_per_year'):
                print(f"    Deaths/year: ~{meta['deaths_per_year']:,}")
            print()

    def _crime_trace(self, crime_node: str):
        """Trace what enabled a crime."""
        if not crime_node:
            print("Usage: crime trace <crime_node_id>")
            return

        conn = self._ensure_conn()
        enablers = trace_crime_enablers(conn, crime_node.strip())

        if not enablers:
            print(f"\nNo enablers found for: {crime_node}")
            return

        print(f"\n═══ What Enabled: {crime_node} ═══\n")
        for e in enablers:
            print(f"  {e['from_name']} --{e['relationship']}--> {crime_node}")
            if e.get('claim_text'):
                print(f"    Claim: \"{e['claim_text'][:70]}...\"")
            print()

    def _crime_downstream(self, legislation: str):
        """Find crimes enabled by legislation."""
        if not legislation:
            print("Usage: crime downstream <legislation_node>")
            return

        conn = self._ensure_conn()
        crimes = crime_downstream(conn, legislation.strip())

        if not crimes:
            print(f"\nNo downstream crimes found for: {legislation}")
            return

        print(f"\n═══ Crimes Enabled By: {legislation} ═══\n")
        for c in crimes:
            import json
            meta = json.loads(c.get('crime_metadata', '{}') or '{}')
            print(f"  → {c['to_name']}")
            print(f"    Type: {meta.get('type', 'unknown')}")
            if c.get('claim_text'):
                print(f"    Detail: \"{c['claim_text'][:60]}...\"")
            print()

    # ─────────────────────────────────────────────────────────────────
    # Risk Management Commands
    # ─────────────────────────────────────────────────────────────────

    def do_risk(self, arg: str):
        """Risk commands: risk <thesis|investment|portfolio|scotus-impact> [args]"""
        parts = arg.strip().split(maxsplit=1)
        if not parts:
            print("Usage: risk <thesis|investment|portfolio|scotus-impact> [args]")
            return

        subcmd = parts[0].lower().replace('-', '_')
        subarg = parts[1] if len(parts) > 1 else ''

        if subcmd == 'thesis':
            self._risk_thesis(subarg)
        elif subcmd == 'investment':
            self._risk_investment(subarg)
        elif subcmd == 'portfolio':
            self._risk_portfolio()
        elif subcmd == 'scotus_impact':
            self._risk_scotus()
        else:
            print("Usage: risk <thesis|investment|portfolio|scotus-impact> [args]")

    def _risk_thesis(self, claim_id: str):
        """Score thesis confidence for a claim."""
        if not claim_id:
            print("Usage: risk thesis <claim_id>")
            return

        conn = self._ensure_conn()
        result = thesis_risk_score(conn, claim_id=claim_id.strip())

        print(f"\n═══ Thesis Confidence: {claim_id} ═══\n")
        print(f"Score: {result.score}/100")
        print(f"\nBreakdown:")
        for k, v in result.breakdown.items():
            print(f"  {k}: +{v}")
        print(f"\nSource quality score: {result.source_quality_score}")
        print(f"Validation count: {result.validation_count}")
        print(f"Signal categories: {', '.join(result.signal_categories) if result.signal_categories else 'None'}")
        print(f"Accountability confirmations: {result.accountability_confirmations}")
        print(f"Contradictions (entities fighting): {result.contradictions_found}")
        print()

    def _risk_investment(self, company: str):
        """Score investment risk for a company."""
        if not company:
            print("Usage: risk investment <company>")
            return

        conn = self._ensure_conn()
        result = investment_risk_score(conn, company.strip().strip('"\''))

        print(f"\n═══ Investment Risk: {result.company} ═══\n")
        print(f"Risk Score: {result.score}/100 ({'HIGH' if result.score > 60 else 'MEDIUM' if result.score > 40 else 'LOW'})")
        print(f"SCOTUS Exposure: {result.scotus_exposure}")

        if result.risk_factors:
            print(f"\nRisk Factors (increase):")
            for factor, pts in result.risk_factors:
                print(f"  +{pts}: {factor}")

        if result.mitigating_factors:
            print(f"\nMitigating Factors (decrease):")
            for factor, pts in result.mitigating_factors:
                print(f"  {pts}: {factor}")

        print()

    def _risk_portfolio(self):
        """Score all correction companies."""
        conn = self._ensure_conn()
        results = portfolio_risk_summary(conn)

        if not results:
            print("\nNo correction companies found in database.")
            return

        print(f"\n═══ Portfolio Risk Summary ═══\n")
        print(f"{'Company':<30} {'Risk':<6} {'SCOTUS':<8}")
        print("-" * 50)

        for r in results:
            risk_bar = '█' * (r['risk_score'] // 10) + '░' * (10 - r['risk_score'] // 10)
            print(f"{r['company'][:28]:<30} {r['risk_score']:<6} {r['scotus_exposure']:<8}")

        print()

    def _risk_scotus(self):
        """Assess SCOTUS ruling impact on portfolio."""
        conn = self._ensure_conn()
        assessment = scotus_impact_assessment(conn)

        print(f"\n═══ SCOTUS Tariff Ruling Impact (Feb 20, 2026) ═══\n")
        print(f"Ruling: {assessment['ruling_summary']}")

        print(f"\n⚠ AT RISK (Executive authority):")
        for item in assessment['at_risk'][:5]:
            print(f"  - {item['name']}: {item['reason']}")

        print(f"\n✓ PROTECTED (Legislative):")
        for item in assessment['protected'][:5]:
            print(f"  - {item['name']}: {item['reason']}")

        print(f"\n🏭 IRREVERSIBLE (Physical assets):")
        for item in assessment['irreversible'][:5]:
            print(f"  - {item['name']}: {item['reason']}")

        print(f"\n📡 Confirmation Signals:")
        for sig in assessment['confirmation_signals']:
            print(f"  - {sig['signal']}")
            print(f"    → {sig['interpretation']}")

        print()

    # ─────────────────────────────────────────────────────────────────
    # Briefing Command
    # ─────────────────────────────────────────────────────────────────

    def do_briefing(self, arg: str):
        """Generate weekly thesis briefing: briefing [weekly]"""
        conn = self._ensure_conn()

        print("\n" + "═" * 60)
        print("  FGIP WEEKLY THESIS BRIEFING")
        print("═" * 60 + "\n")

        # Status summary
        summary = get_status_summary(conn)
        print("─── Evidence Status ───")
        print(f"Total Claims: {summary['total_claims']}")
        print(f"Evidence Coverage: {summary['evidence_coverage']}%")
        print(f"Claims by status: {summary['claims_by_status']}")

        # Signal convergence for key topics
        print("\n─── Signal Convergence ───")
        for topic in ['reshoring', 'china_threat', 'correction']:
            result = signal_convergence(conn, topic)
            print(f"  {topic}: {result.score}/6 ({result.confidence_level})")

        # Portfolio risk
        print("\n─── Portfolio Risk ───")
        portfolio = portfolio_risk_summary(conn)
        if portfolio:
            avg_risk = sum(p['risk_score'] for p in portfolio) / len(portfolio)
            print(f"  Average risk: {avg_risk:.0f}/100")
            print(f"  Companies tracked: {len(portfolio)}")
            high_risk = [p for p in portfolio if p['risk_score'] > 60]
            if high_risk:
                print(f"  ⚠ High risk: {', '.join(p['company'] for p in high_risk[:3])}")

        # SCOTUS impact summary
        print("\n─── SCOTUS Ruling Impact ───")
        scotus = scotus_impact_assessment(conn)
        print(f"  At risk items: {len(scotus['at_risk'])}")
        print(f"  Protected items: {len(scotus['protected'])}")
        print(f"  Irreversible: {len(scotus['irreversible'])}")

        # Accountability layer
        print("\n─── Accountability Layer ───")
        cases = get_accountability_cases(conn)
        print(f"  Criminal/fraud cases tracked: {len(cases)}")
        case_types = {}
        for c in cases:
            import json
            meta = json.loads(c.get('metadata', '{}') or '{}')
            ctype = meta.get('type', 'unknown')
            case_types[ctype] = case_types.get(ctype, 0) + 1
        for ctype, count in sorted(case_types.items()):
            print(f"    {ctype}: {count}")

        print("\n" + "═" * 60)
        print("  END BRIEFING")
        print("═" * 60 + "\n")

    # ─────────────────────────────────────────────────────────────────
    # Load Command
    # ─────────────────────────────────────────────────────────────────

    def do_load(self, arg: str):
        """Load data from source files: load [--sources FILE] [--citations FILE]"""
        # Default paths
        urls_file = Path('/home/voidstr3m33/fgip_all_source_urls.txt')
        citation_file = Path('/home/voidstr3m33/fgip_citation_database.md')

        # Parse args for custom paths
        if '--sources' in arg:
            match = re.search(r'--sources\s+(\S+)', arg)
            if match:
                urls_file = Path(match.group(1))

        if '--citations' in arg:
            match = re.search(r'--citations\s+(\S+)', arg)
            if match:
                citation_file = Path(match.group(1))

        if not urls_file.exists():
            print(f"Source URLs file not found: {urls_file}")
            return

        if not citation_file.exists():
            print(f"Citation database not found: {citation_file}")
            return

        print(f"\nLoading from:")
        print(f"  Sources: {urls_file}")
        print(f"  Citations: {citation_file}")
        print()

        try:
            conn = self._ensure_conn()
            result = load_all(conn, urls_file, citation_file)

            print("\n═══ Load Summary ═══")
            print(f"Sources loaded: {result['sources_loaded']}")
            print(f"Claims loaded: {result['claims_loaded']}")
            print(f"Links created: {result['links_created']}")
            print(f"\nTotal sources: {result['total_sources']}")
            print(f"  By tier: {result['sources_by_tier']}")
            print(f"Total claims: {result['total_claims']}")
            print(f"  By status: {result['claims_by_status']}")
            print()
        except Exception as e:
            print(f"Error loading: {e}")

    def do_build_graph(self, arg: str):
        """Build nodes and edges from loaded claims: build-graph"""
        try:
            conn = self._ensure_conn()
            result = build_graph(conn)

            print("\n═══ Graph Build Summary ═══")
            print(f"Nodes created: {result['nodes_created']}")
            print(f"  By type: {result['nodes_by_type']}")
            print(f"Edges created: {result['edges_created']}")
            print(f"  By relationship: {result['edges_by_relationship']}")
            print()
        except Exception as e:
            print(f"Error building graph: {e}")

    do_build_graph.__name__ = 'do_build-graph'

    # ─────────────────────────────────────────────────────────────────
    # Navigation
    # ─────────────────────────────────────────────────────────────────

    def do_help(self, arg: str):
        """Show help."""
        print("""
═══ FGIP Commands ═══

Query & Analysis:
  query <entity>              Show all edges connected to a node
  trace <from> → <to>         Find paths with evidence quality scoring
  status                      Database summary (claims, edges, coverage)
  missing                     List MISSING claims (need URLs)
  ownership-loop <entity>     Detect ownership cycles
  contradictions <entity>     Find logical contradictions
  correction-score <company>  Score reshoring benefit

Signal Layer:
  signal list                 Show all independent media nodes
  signal convergence <topic>  How many signal categories confirm (0-6)
  signal who-covers <entity>  Which media covers this entity
  signal load                 Load signal + accountability layer

Crime/Accountability:
  crime list                  Show all crime/fraud cases
  crime trace <crime_node>    Trace what enabled this crime
  crime downstream <leg>      What crimes did legislation enable

Risk Management:
  risk thesis <claim_id>      Thesis confidence score (0-100)
  risk investment <company>   Investment risk score (0-100)
  risk portfolio              Score all correction companies
  risk scotus-impact          How Feb 20 ruling affects portfolio
  briefing                    Generate weekly thesis briefing

Data Entry:
  add-node <name> --type TYPE
  add-edge <from> → <to> --rel REL --claim CLAIM_ID
  add-claim "text" --topic TOPIC [--source URL]
  upgrade <claim_id>          Add artifact to upgrade claim status

Loading:
  load [--sources FILE] [--citations FILE]   Load source URLs and claims
  build-graph                                Build nodes/edges from claims

System:
  help                        This help
  quit / exit                 Exit the CLI
""")

    def do_quit(self, arg: str):
        """Exit the CLI."""
        print("Goodbye.")
        return True

    def do_exit(self, arg: str):
        """Exit the CLI."""
        return self.do_quit(arg)

    def do_EOF(self, arg: str):
        """Handle Ctrl+D."""
        print()
        return self.do_quit(arg)

    def default(self, line: str):
        """Handle unknown commands or hyphenated commands."""
        # Try converting hyphenated commands
        parts = line.split(maxsplit=1)
        if parts:
            cmd_name = parts[0].replace('-', '_')
            method = getattr(self, f'do_{cmd_name}', None)
            if method:
                arg = parts[1] if len(parts) > 1 else ''
                return method(arg)

        print(f"Unknown command: {line}")
        print("Type 'help' for available commands.")

    def emptyline(self):
        """Do nothing on empty line."""
        pass


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='FGIP Causality Engine CLI')
    parser.add_argument('--db', default='fgip.db', help='Database path')
    parser.add_argument('--load', action='store_true', help='Load data on startup')
    args = parser.parse_args()

    shell = FGIPShell(db_path=args.db)

    if args.load:
        shell.do_load('')
        shell.do_build_graph('')

    try:
        shell.cmdloop()
    except KeyboardInterrupt:
        print("\nGoodbye.")
        sys.exit(0)


if __name__ == '__main__':
    main()
