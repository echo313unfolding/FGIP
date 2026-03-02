"""FGIP CLI - Command-line interface with Square-One compliance."""

import json
import sys
from pathlib import Path

import click

from .db import FGIPDatabase
from .loader import FGIPLoader, generate_node_id, generate_edge_id
from .query import FGIPQuery
from .schema import Node, Edge, NodeType, EdgeType, SourceType, Source, Claim, ClaimStatus
from .migrate import FGIPMigrator, load_sources_from_file, upgrade_claim
from .citation_loader import CitationLoader
from .causal_chain import CausalChainBuilder, parse_chain_spec
from . import staging as staging_module
from .verification import run_verification, quick_verify, EASTER_EGGS, get_eggs_for_agent
from .analysis.gap_detector import GapDetector, AgentRequest


DEFAULT_DB_PATH = "fgip.db"


def get_db(db_path: str = DEFAULT_DB_PATH) -> FGIPDatabase:
    return FGIPDatabase(db_path)


@click.group()
@click.option("--db", default=DEFAULT_DB_PATH, help="Database file path")
@click.pass_context
def cli(ctx, db):
    """FGIP Causality Engine - Square-One Compliant Knowledge Graph."""
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = db


# ============ Database Commands ============

@cli.command()
@click.pass_context
def init(ctx):
    """Initialize the database schema."""
    db = get_db(ctx.obj["db_path"])
    receipt = db.init_schema()

    if receipt.success:
        click.echo(f"✓ Database initialized: {ctx.obj['db_path']}")
        click.echo(f"  Receipt: {receipt.receipt_id}")
        click.echo("  Schema includes: nodes, edges, sources, claims, claim_sources")
    else:
        click.echo("✗ Failed to initialize database", err=True)
        sys.exit(1)


@cli.command()
@click.option("--nodes", type=click.Path(exists=True), help="Nodes JSON file")
@click.option("--edges", type=click.Path(exists=True), help="Edges JSON file")
@click.pass_context
def load(ctx, nodes, edges):
    """Load seed data from JSON files."""
    db = get_db(ctx.obj["db_path"])
    loader = FGIPLoader(db)

    if nodes:
        receipt = loader.load_nodes(nodes)
        click.echo(f"Nodes: loaded {receipt.details.get('loaded', 0)}, errors {len(receipt.details.get('errors', []))}")
        if receipt.details.get("is_synthetic"):
            click.echo("  WARNING: Data marked as SYNTHETIC")

    if edges:
        receipt = loader.load_edges(edges)
        click.echo(f"Edges: loaded {receipt.details.get('loaded', 0)}, errors {len(receipt.details.get('errors', []))}")


@cli.command("load-citations")
@click.option("--sources", type=click.Path(exists=True),
              default="/home/voidstr3m33/fgip_all_source_urls.txt",
              help="Source URLs file (fgip_all_source_urls.txt)")
@click.option("--citations", type=click.Path(exists=True),
              default="/home/voidstr3m33/fgip_citation_database.md",
              help="Citation database markdown file")
@click.pass_context
def load_citations(ctx, sources, citations):
    """Load sources and claims from citation database (Square-One compliant).

    This command loads:
    - ~698 source URLs with auto-tiering (T0=gov, T1=journalism, T2=other)
    - ~200+ claims from markdown tables
    - Creates claim_sources links
    - Extracts nodes from known entities
    - Creates edges backed by claims
    """
    db = get_db(ctx.obj["db_path"])
    loader = CitationLoader(db)

    click.echo("=== FGIP Citation Loader (Square-Two) ===\n")

    receipt = loader.load_all(sources, citations)

    # Print source loading results
    src = receipt.details.get("sources", {})
    click.echo(f"Sources: {src.get('loaded', 0)} loaded")
    click.echo(f"  Tier 0 (Primary): {src.get('tier_0', 0)}")
    click.echo(f"  Tier 1 (Journalism): {src.get('tier_1', 0)}")
    click.echo(f"  Tier 2 (Commentary): {src.get('tier_2', 0)}")

    # Print claims loading results
    clm = receipt.details.get("claims", {})
    click.echo(f"\nClaims: {clm.get('claims_loaded', 0)} loaded")
    click.echo(f"  Links created: {clm.get('links_created', 0)}")
    if clm.get("by_topic"):
        click.echo("  By topic:")
        for topic, count in sorted(clm["by_topic"].items()):
            click.echo(f"    {topic}: {count}")
    if clm.get("by_status"):
        click.echo("  By status:")
        for status, count in clm["by_status"].items():
            click.echo(f"    {status}: {count}")

    # Print node extraction results
    nodes = receipt.details.get("nodes", {})
    click.echo(f"\nNodes: {nodes.get('nodes_created', 0)} created")
    if nodes.get("by_type"):
        for ntype, count in sorted(nodes["by_type"].items()):
            click.echo(f"  {ntype}: {count}")

    # Print edge creation results
    edges = receipt.details.get("edges", {})
    click.echo(f"\nEdges: {edges.get('edges_created', 0)} created")
    if edges.get("by_type"):
        for etype, count in sorted(edges["by_type"].items()):
            click.echo(f"  {etype}: {count}")

    # Print final statistics
    final = receipt.details.get("final_stats", {})
    click.echo("\n=== Final Statistics ===")
    click.echo(f"Total Sources: {final.get('total_sources', 0)}")
    click.echo(f"Total Claims: {final.get('total_claims', 0)}")
    click.echo(f"Total Nodes: {final.get('total_nodes', 0)}")
    click.echo(f"Total Edges: {final.get('total_edges', 0)}")
    click.echo(f"Evidence Coverage: {final.get('evidence_coverage_pct', 0):.1f}%")
    click.echo(f"Tier 0/1 Coverage: {final.get('tier_01_coverage_pct', 0):.1f}%")

    click.echo(f"\nReceipt: {receipt.receipt_id}")


@cli.command()
@click.pass_context
def stats(ctx):
    """Show database statistics including evidence coverage."""
    db = get_db(ctx.obj["db_path"])
    stats = db.get_stats()
    evidence = db.get_evidence_status()

    click.echo("=== FGIP Database Statistics ===\n")
    click.echo(f"Nodes: {stats['nodes']}")
    click.echo(f"Edges: {stats['edges']}")
    click.echo(f"Sources: {stats['sources']}")
    click.echo(f"Claims: {stats['claims']}")

    click.echo("\n=== Square-One Evidence Status ===\n")
    click.echo(f"Total Claims: {evidence['total_claims']}")
    click.echo(f"  VERIFIED: {evidence['verified']}")
    click.echo(f"  EVIDENCED: {evidence['evidenced']}")
    click.echo(f"  PARTIAL: {evidence['partial']}")
    click.echo(f"  MISSING: {evidence['missing']}")

    click.echo(f"\nEdges with Claims: {evidence['edges_with_claims']}/{evidence['total_edges']}")
    click.echo(f"Orphan Edges (no claim): {evidence['orphan_edges']}")
    click.echo(f"\nEvidence Coverage: {evidence['evidence_coverage_pct']:.1f}%")
    click.echo(f"Tier 0/1 Coverage: {evidence['tier_01_coverage_pct']:.1f}%")

    if stats['source_tiers']:
        click.echo("\nSource Tiers:")
        for tier, count in sorted(stats['source_tiers'].items()):
            tier_name = {"tier_0": "Tier 0 (Primary)", "tier_1": "Tier 1 (Journalism)", "tier_2": "Tier 2 (Commentary)"}.get(tier, tier)
            click.echo(f"  {tier_name}: {count}")


@cli.command()
@click.pass_context
def status(ctx):
    """Show evidence status summary (Square-One)."""
    db = get_db(ctx.obj["db_path"])
    evidence = db.get_evidence_status()

    click.echo("=== Square-One Evidence Status ===\n")
    click.echo(f"Claims: {evidence['total_claims']} total")
    click.echo(f"  ✓ VERIFIED: {evidence['verified']}")
    click.echo(f"  ◐ EVIDENCED: {evidence['evidenced']}")
    click.echo(f"  ○ PARTIAL: {evidence['partial']}")
    click.echo(f"  ✗ MISSING: {evidence['missing']}")

    click.echo(f"\nEvidence Coverage: {evidence['evidence_coverage_pct']:.1f}%")
    click.echo(f"Tier 0/1 Coverage: {evidence['tier_01_coverage_pct']:.1f}%")

    if evidence['orphan_edges'] > 0:
        click.echo(f"\n⚠ Warning: {evidence['orphan_edges']} orphan edges without claims")


@cli.command()
@click.option("--limit", default=50, type=int)
@click.pass_context
def missing(ctx, limit):
    """List claims with MISSING status (need source URLs)."""
    db = get_db(ctx.obj["db_path"])
    claims = db.list_claims(status="MISSING", limit=limit)

    if not claims:
        click.echo("No MISSING claims found. All claims have sources.")
        return

    click.echo(f"=== MISSING Claims ({len(claims)}) ===\n")
    for claim in claims:
        click.echo(f"{claim.claim_id}: {claim.claim_text[:80]}...")
        click.echo(f"  Topic: {claim.topic}")
        if claim.notes:
            click.echo(f"  Notes: {claim.notes}")
        click.echo()


# ============ Migration Commands ============

@cli.command("migrate")
@click.pass_context
def migrate_cmd(ctx):
    """Migrate legacy edges to Square-One compliance."""
    db = get_db(ctx.obj["db_path"])
    migrator = FGIPMigrator(db)

    click.echo("Running Square-One migration...")
    result = migrator.migrate_all()

    click.echo(f"\n✓ Migration complete:")
    click.echo(f"  Sources created: {result['sources_created']}")
    click.echo(f"  Claims created: {result['claims_created']}")
    click.echo(f"  Edges updated: {result['edges_updated']}")

    if result['errors']:
        click.echo(f"  Errors: {len(result['errors'])}")
        for err in result['errors'][:5]:
            click.echo(f"    - {err['edge_id']}: {err['error']}")


@cli.command("upgrade")
@click.argument("claim_id")
@click.option("--artifact", required=True, type=click.Path(exists=True), help="Path to artifact file")
@click.pass_context
def upgrade_cmd(ctx, claim_id, artifact):
    """Upgrade a claim by attaching an artifact (PDF/HTML snapshot)."""
    db = get_db(ctx.obj["db_path"])

    claim = db.get_claim(claim_id)
    if not claim:
        click.echo(f"Claim not found: {claim_id}", err=True)
        sys.exit(1)

    click.echo(f"Claim: {claim.claim_text[:80]}...")
    click.echo(f"Current status: {claim.status.value}")

    if upgrade_claim(db, claim_id, artifact):
        new_claim = db.get_claim(claim_id)
        click.echo(f"✓ Upgraded to: {new_claim.status.value}")
    else:
        click.echo("✗ Failed to upgrade claim", err=True)
        sys.exit(1)


# ============ Source Commands ============

@cli.group()
def sources():
    """Source operations (Square-One)."""
    pass


@sources.command("load")
@click.argument("filepath", type=click.Path(exists=True))
@click.pass_context
def sources_load(ctx, filepath):
    """Load sources from URL list file."""
    db = get_db(ctx.obj["db_path"])
    result = load_sources_from_file(db, filepath)

    click.echo(f"✓ Loaded {result['created']} sources")
    if result['errors']:
        click.echo(f"  Errors: {len(result['errors'])}")


@sources.command("list")
@click.option("--tier", type=int, help="Filter by tier (0, 1, 2)")
@click.option("--limit", default=50, type=int)
@click.pass_context
def sources_list(ctx, tier, limit):
    """List sources."""
    db = get_db(ctx.obj["db_path"])
    sources_list = db.list_sources(tier=tier, limit=limit)

    tier_names = {0: "PRIMARY", 1: "JOURNALISM", 2: "COMMENTARY"}
    for source in sources_list:
        tier_name = tier_names.get(source.tier, str(source.tier))
        artifact = "✓" if source.artifact_path else "○"
        click.echo(f"[{artifact}] T{source.tier} {source.domain}: {source.url[:60]}...")


# ============ Claim Commands ============

@cli.group()
def claims():
    """Claim operations (Square-One)."""
    pass


@claims.command("list")
@click.option("--status", type=click.Choice(["MISSING", "PARTIAL", "EVIDENCED", "VERIFIED"]))
@click.option("--topic", help="Filter by topic")
@click.option("--limit", default=50, type=int)
@click.pass_context
def claims_list(ctx, status, topic, limit):
    """List claims."""
    db = get_db(ctx.obj["db_path"])
    claims_list = db.list_claims(status=status, topic=topic, limit=limit)

    status_icons = {"MISSING": "✗", "PARTIAL": "○", "EVIDENCED": "◐", "VERIFIED": "✓"}
    for claim in claims_list:
        icon = status_icons.get(claim.status.value, "?")
        click.echo(f"[{icon}] {claim.claim_id}: {claim.claim_text[:60]}...")
        click.echo(f"    Topic: {claim.topic}, Required: Tier {claim.required_tier}")


@claims.command("get")
@click.argument("claim_id")
@click.pass_context
def claims_get(ctx, claim_id):
    """Get claim details with sources."""
    db = get_db(ctx.obj["db_path"])
    claim = db.get_claim(claim_id)

    if not claim:
        click.echo(f"Claim not found: {claim_id}", err=True)
        sys.exit(1)

    click.echo(f"Claim ID: {claim.claim_id}")
    click.echo(f"Text: {claim.claim_text}")
    click.echo(f"Topic: {claim.topic}")
    click.echo(f"Status: {claim.status.value}")
    click.echo(f"Required Tier: {claim.required_tier}")

    sources = db.get_claim_sources(claim_id)
    if sources:
        click.echo(f"\nSources ({len(sources)}):")
        for src in sources:
            artifact = "✓" if src.artifact_path else "○"
            click.echo(f"  [{artifact}] Tier {src.tier}: {src.url}")


@claims.command("add")
@click.option("--text", required=True, help="Claim text")
@click.option("--topic", required=True, help="Topic category")
@click.option("--source-url", help="Source URL")
@click.option("--required-tier", default=1, type=int)
@click.pass_context
def claims_add(ctx, text, topic, source_url, required_tier):
    """Add a new claim."""
    db = get_db(ctx.obj["db_path"])

    claim_id = db.get_next_claim_id()
    status = ClaimStatus.PARTIAL if source_url else ClaimStatus.MISSING

    claim = Claim(
        claim_id=claim_id,
        claim_text=text,
        topic=topic,
        status=status,
        required_tier=required_tier,
    )

    if db.insert_claim(claim):
        click.echo(f"✓ Created claim: {claim_id}")

        if source_url:
            source = Source.from_url(source_url)
            db.insert_source(source)
            db.link_claim_source(claim_id, source.source_id)
            click.echo(f"  Linked to source: Tier {source.tier} ({source.domain})")
    else:
        click.echo("✗ Failed to create claim", err=True)
        sys.exit(1)


# ============ Node Commands ============

@cli.group()
def node():
    """Node operations."""
    pass


@node.command("add")
@click.option("--type", "node_type", required=True, type=click.Choice([t.value for t in NodeType]))
@click.option("--name", required=True)
@click.option("--description", default=None)
@click.option("--aliases", default=None, help="Comma-separated aliases")
@click.pass_context
def node_add(ctx, node_type, name, description, aliases):
    """Add a new node."""
    db = get_db(ctx.obj["db_path"])

    node_id = generate_node_id(NodeType(node_type), name)
    alias_list = [a.strip() for a in aliases.split(",")] if aliases else []

    node = Node(
        node_id=node_id,
        node_type=NodeType(node_type),
        name=name,
        aliases=alias_list,
        description=description,
    )

    receipt = db.insert_node(node)

    if receipt.success:
        click.echo(f"✓ Added node: {node_id}")
    else:
        click.echo("✗ Failed to add node", err=True)
        sys.exit(1)


@node.command("get")
@click.argument("node_id")
@click.pass_context
def node_get(ctx, node_id):
    """Get a node by ID."""
    db = get_db(ctx.obj["db_path"])
    node = db.get_node(node_id)

    if node:
        click.echo(json.dumps(node.to_dict(), indent=2))
    else:
        click.echo(f"Node not found: {node_id}", err=True)
        sys.exit(1)


@node.command("list")
@click.option("--type", "node_type", default=None, type=click.Choice([t.value for t in NodeType]))
@click.option("--limit", default=50, type=int)
@click.pass_context
def node_list(ctx, node_type, limit):
    """List nodes."""
    db = get_db(ctx.obj["db_path"])
    nodes = db.list_nodes(node_type=node_type, limit=limit)

    for node in nodes:
        click.echo(f"{node.node_id}: {node.name} ({node.node_type.value})")


@node.command("search")
@click.argument("query")
@click.option("--limit", default=20, type=int)
@click.pass_context
def node_search(ctx, query, limit):
    """Search nodes by name/description."""
    db = get_db(ctx.obj["db_path"])
    nodes = db.search_nodes(query, limit=limit)

    if nodes:
        for node in nodes:
            click.echo(f"{node.node_id}: {node.name}")
    else:
        click.echo("No results found")


# ============ Edge Commands ============

@cli.group()
def edge():
    """Edge operations."""
    pass


@edge.command("add")
@click.option("--type", "edge_type", required=True, type=click.Choice([t.value for t in EdgeType]))
@click.option("--from", "from_node", required=True, help="Source node ID")
@click.option("--to", "to_node", required=True, help="Target node ID")
@click.option("--claim", "claim_id", required=True, help="Claim ID (Square-One required)")
@click.option("--date-occurred", default=None)
@click.option("--notes", default=None)
@click.pass_context
def edge_add(ctx, edge_type, from_node, to_node, claim_id, date_occurred, notes):
    """Add a new edge (requires claim_id for Square-One compliance)."""
    db = get_db(ctx.obj["db_path"])

    # Verify claim exists
    claim = db.get_claim(claim_id)
    if not claim:
        click.echo(f"Claim not found: {claim_id}. Create claim first.", err=True)
        sys.exit(1)

    edge_id = generate_edge_id(EdgeType(edge_type), from_node, to_node)

    edge = Edge(
        edge_id=edge_id,
        edge_type=EdgeType(edge_type),
        from_node_id=from_node,
        to_node_id=to_node,
        claim_id=claim_id,
        date_occurred=date_occurred,
        notes=notes,
    )

    receipt = db.insert_edge(edge)

    if receipt.success:
        click.echo(f"✓ Added edge: {edge_id}")
        click.echo(f"  Backed by claim: {claim_id} [{claim.status.value}]")
    else:
        click.echo("✗ Failed to add edge", err=True)
        sys.exit(1)


@edge.command("list")
@click.option("--from", "from_node", default=None)
@click.option("--to", "to_node", default=None)
@click.option("--type", "edge_type", default=None, type=click.Choice([t.value for t in EdgeType]))
@click.option("--limit", default=50, type=int)
@click.pass_context
def edge_list(ctx, from_node, to_node, edge_type, limit):
    """List edges with claim status."""
    db = get_db(ctx.obj["db_path"])
    edges = db.list_edges(from_node_id=from_node, to_node_id=to_node, edge_type=edge_type, limit=limit)

    status_icons = {"MISSING": "✗", "PARTIAL": "○", "EVIDENCED": "◐", "VERIFIED": "✓"}
    assertion_icons = {"FACT": "F", "INFERENCE": "I", "HYPOTHESIS": "H"}

    for edge in edges:
        claim = db.get_claim(edge.claim_id) if edge.claim_id else None
        assertion = assertion_icons.get(edge.assertion_level, "?")
        if claim:
            icon = status_icons.get(claim.status.value, "?")
            click.echo(f"[{icon}|{assertion}] {edge.from_node_id} --{edge.edge_type.value}--> {edge.to_node_id}")
            click.echo(f"    Claim: {edge.claim_id} ({edge.assertion_level})")
        else:
            click.echo(f"[!|{assertion}] {edge.from_node_id} --{edge.edge_type.value}--> {edge.to_node_id}")
            click.echo(f"    WARNING: No claim (legacy edge)")


@edge.command("add-chain")
@click.option("--spec", help="Chain spec: 'A --(TYPE:LEVEL)--> B --(TYPE:LEVEL)--> C'")
@click.option("--interactive", "-i", is_flag=True, help="Interactive mode")
@click.pass_context
def add_causal_chain(ctx, spec, interactive):
    """Add a causal chain with explicit assertion levels.

    Enforces forensic discipline by requiring INFERENCE or HYPOTHESIS
    for causal edge types (ENABLED, CAUSED, etc.).

    \b
    Chain spec format:
        node1 --(EDGE_TYPE:ASSERTION)--> node2 --(EDGE_TYPE:ASSERTION)--> node3

    \b
    Assertion levels:
        FACT       - Direct Tier 0/1 evidence exists
        INFERENCE  - Reasonable conclusion from documented facts
        HYPOTHESIS - Speculative or contested causal link

    \b
    Examples:
        # Simple two-node chain
        fgip edge add-chain --spec "pntr-2000 --(ENABLED:INFERENCE)--> china-trade"

        # Multi-hop chain
        fgip edge add-chain --spec "chamber --(LOBBIED_FOR:FACT)--> pntr --(ENABLED:INFERENCE)--> trade"

        # Interactive mode
        fgip edge add-chain -i
    """
    db = get_db(ctx.obj["db_path"])
    builder = CausalChainBuilder(db)

    if interactive:
        click.echo("=== Causal Chain Builder (Interactive) ===\n")
        click.echo("Assertion levels: FACT | INFERENCE | HYPOTHESIS")
        click.echo("Edge types: ENABLED, CAUSED, LOBBIED_FOR, OWNS_SHARES, etc.\n")

        # Collect nodes first
        click.echo("Step 1: Define new nodes (if any)")
        while True:
            node_id = click.prompt("Node ID (or 'done' to continue)", default="done")
            if node_id.lower() == "done":
                break

            # Check if node exists
            existing = db.get_node(node_id)
            if existing:
                click.echo(f"  Node exists: {existing.name} ({existing.node_type.value})")
                continue

            name = click.prompt("  Name")
            node_type = click.prompt(
                "  Type",
                type=click.Choice([
                    "ORGANIZATION", "PERSON", "LEGISLATION", "COMPANY",
                    "ECONOMIC_EVENT", "POLICY", "COURT_CASE"
                ])
            )
            description = click.prompt("  Description (optional)", default="")
            builder.add_node(node_id, name, node_type, description or None)
            click.echo(f"  Registered: {node_id}")

        # Collect links
        click.echo("\nStep 2: Define chain links")
        link_num = 1
        while True:
            click.echo(f"\n--- Link {link_num} ---")
            from_node = click.prompt("From node ID (or 'done')", default="done")
            if from_node.lower() == "done":
                break

            to_node = click.prompt("To node ID")
            edge_type = click.prompt(
                "Edge type",
                type=click.Choice([
                    "ENABLED", "CAUSED", "LOBBIED_FOR", "LOBBIED_AGAINST",
                    "FILED_AMICUS", "OWNS_SHARES", "DONATED_TO", "CONTRIBUTED_TO"
                ])
            )
            assertion_level = click.prompt(
                "Assertion level",
                type=click.Choice(["FACT", "INFERENCE", "HYPOTHESIS"])
            )
            claim_text = click.prompt("Claim text (what does this link assert?)")
            source_url = click.prompt("Source URL (optional)", default="")
            topic = click.prompt("Topic", default="Causal")

            builder.add_link(
                from_node=from_node,
                to_node=to_node,
                edge_type=edge_type,
                assertion_level=assertion_level,
                claim_text=claim_text,
                source_url=source_url or None,
                topic=topic,
            )
            click.echo(f"  Added: {from_node} --({edge_type}:{assertion_level})--> {to_node}")
            link_num += 1

        if not builder.links:
            click.echo("No links defined. Aborting.")
            return

    elif spec:
        # Parse the chain spec
        links = parse_chain_spec(spec)
        if not links:
            click.echo("Could not parse chain spec. Use format:", err=True)
            click.echo("  'A --(TYPE:LEVEL)--> B --(TYPE:LEVEL)--> C'", err=True)
            sys.exit(1)

        click.echo(f"Parsed {len(links)} link(s) from spec:\n")

        for link in links:
            click.echo(f"  {link['from_node']} --({link['edge_type']}:{link['assertion_level']})--> {link['to_node']}")

            # Check if nodes exist
            for node_id in [link['from_node'], link['to_node']]:
                existing = db.get_node(node_id)
                if not existing:
                    click.echo(f"\n  Node '{node_id}' does not exist. Creating...")
                    name = click.prompt(f"    Name for {node_id}")
                    node_type = click.prompt(
                        f"    Type for {node_id}",
                        type=click.Choice([
                            "ORGANIZATION", "PERSON", "LEGISLATION", "COMPANY",
                            "ECONOMIC_EVENT", "POLICY", "COURT_CASE"
                        ])
                    )
                    builder.add_node(node_id, name, node_type)

            # Get claim text
            claim_text = click.prompt(f"\n  Claim text for this link")
            source_url = click.prompt("  Source URL (optional)", default="")

            builder.add_link(
                from_node=link['from_node'],
                to_node=link['to_node'],
                edge_type=link['edge_type'],
                assertion_level=link['assertion_level'],
                claim_text=claim_text,
                source_url=source_url or None,
            )

    else:
        click.echo("Provide --spec or use --interactive mode", err=True)
        sys.exit(1)

    # Validate and commit
    click.echo("\n=== Validating chain ===")
    errors = builder.validate()
    if errors:
        click.echo("Validation errors:", err=True)
        for err in errors:
            click.echo(f"  - {err}", err=True)
        sys.exit(1)

    click.echo("Validation passed. Committing...")
    receipt = builder.commit()

    if receipt.success:
        details = receipt.details
        click.echo("\n=== Chain Created ===")
        click.echo(f"Nodes created: {len(details.get('nodes_created', []))}")
        for node_id in details.get('nodes_created', []):
            click.echo(f"  + {node_id}")

        click.echo(f"\nClaims created: {len(details.get('claims_created', []))}")
        for claim_id in details.get('claims_created', []):
            click.echo(f"  + {claim_id}")

        click.echo(f"\nEdges created: {len(details.get('edges_created', []))}")
        for edge in details.get('edges_created', []):
            click.echo(f"  + [{edge['assertion']}] {edge['from']} --{edge['type']}--> {edge['to']}")
            click.echo(f"      Claim: {edge['claim_id']}")

        click.echo(f"\nReceipt: {receipt.receipt_id}")
    else:
        click.echo(f"Failed: {receipt.details.get('error', 'Unknown error')}", err=True)
        sys.exit(1)


# ============ Query Commands ============

@cli.group()
def query():
    """Analysis queries with evidence coverage."""
    pass


@query.command("trace-causality")
@click.option("--start", required=True, help="Starting node ID")
@click.option("--end", required=True, help="Target node ID")
@click.option("--max-depth", default=6, type=int)
@click.pass_context
def trace_causality_cmd(ctx, start, end, max_depth):
    """Trace causal paths with evidence coverage score."""
    from analysis.causality_chain import trace_causality

    db = get_db(ctx.obj["db_path"])
    paths = trace_causality(db, start, end, max_depth=max_depth)

    if not paths:
        click.echo("No paths found")
        return

    click.echo(f"Found {len(paths)} path(s):\n")

    status_icons = {"MISSING": "✗", "PARTIAL": "○", "EVIDENCED": "◐", "VERIFIED": "✓"}

    for i, path in enumerate(paths[:10]):
        # Calculate evidence coverage for this path
        tier_01_count = 0
        total_edges = len(path.edges)

        click.echo(f"Path {i+1}:")

        for j, (node, edge) in enumerate(zip(path.nodes[:-1], path.edges)):
            claim = db.get_claim(edge.claim_id) if edge.claim_id else None

            if claim:
                sources = db.get_claim_sources(claim.claim_id)
                best_tier = min((s.tier for s in sources), default=2)
                if best_tier <= 1:
                    tier_01_count += 1

                icon = status_icons.get(claim.status.value, "?")
                click.echo(f"  {j+1}. [{node.name}] --{edge.edge_type.value}--> [{path.nodes[j+1].name}]")
                click.echo(f"     Claim: {claim.claim_id} [{icon} {claim.status.value}]")
                if sources:
                    click.echo(f"     Source: {sources[0].url[:50]}...")
            else:
                click.echo(f"  {j+1}. [{node.name}] --{edge.edge_type.value}--> [{path.nodes[j+1].name}]")
                click.echo(f"     [!] No claim (legacy)")

        coverage = (tier_01_count / total_edges * 100) if total_edges > 0 else 0
        click.echo(f"\n  Evidence: {tier_01_count}/{total_edges} edges Tier 0/1 ({coverage:.0f}% coverage)")
        click.echo()


@query.command("ownership-loop")
@click.option("--entity", required=True, help="Entity node ID")
@click.option("--max-depth", default=10, type=int)
@click.pass_context
def ownership_loop_cmd(ctx, entity, max_depth):
    """Detect circular ownership structures with evidence."""
    from analysis.ownership_loop import detect_ownership_loops, map_ownership_structure

    db = get_db(ctx.obj["db_path"])
    loops = detect_ownership_loops(db, entity, max_depth=max_depth)

    if loops:
        click.echo(f"Found {len(loops)} ownership loop(s):\n")
        for i, loop in enumerate(loops):
            click.echo(f"Loop {i+1}: {loop.describe()}")
    else:
        click.echo("No ownership loops detected")

    structure = map_ownership_structure(db, entity, max_depth=max_depth)
    click.echo(f"\nOwnership structure for {structure['entity']['name']}:")
    click.echo(f"  Owners: {len(structure['owners'])}")
    click.echo(f"  Owned: {len(structure['owned'])}")


@query.command("contradiction-check")
@click.option("--entity", required=True, help="Entity node ID")
@click.pass_context
def contradiction_check_cmd(ctx, entity):
    """Check for contradictions with evidence status."""
    from analysis.contradiction_detector import full_contradiction_check

    db = get_db(ctx.obj["db_path"])
    result = full_contradiction_check(db, entity)

    click.echo(f"Contradiction check for: {result['entity']['name']}\n")
    click.echo(f"Summary:")
    click.echo(f"  Total contradictions: {result['summary']['total_contradictions']}")
    click.echo(f"  High severity: {result['summary']['high_severity']}")
    click.echo(f"  Position reversals: {result['summary']['position_reversals']}")


@query.command("correction-score")
@click.option("--company", required=True, help="Company node ID")
@click.pass_context
def correction_score_cmd(ctx, company):
    """Calculate correction alignment score with evidence breakdown."""
    from analysis.portfolio_scorer import calculate_correction_score

    db = get_db(ctx.obj["db_path"])
    score = calculate_correction_score(db, company)

    click.echo(f"Correction Score for: {score.company.name}")
    click.echo(f"  Total Score: {score.total_score:.1f}/100 (Grade: {score._get_grade()})\n")

    click.echo("Factors:")
    for factor, points in score.factors.items():
        max_pts = 25 if factor == "reshoring_actions" else 20 if factor in ["domestic_supply_chain", "no_anti_tariff_amicus", "us_manufacturing"] else 15
        click.echo(f"  {factor}: {points:.1f}/{max_pts}")

    if score.positive_signals:
        click.echo("\nPositive signals:")
        for sig in score.positive_signals:
            click.echo(f"  + {sig}")

    if score.negative_signals:
        click.echo("\nNegative signals:")
        for sig in score.negative_signals:
            click.echo(f"  - {sig}")


# ============ Export Commands ============

@cli.command()
@click.option("--format", "fmt", default="json", type=click.Choice(["json"]))
@click.option("--output", required=True, type=click.Path())
@click.pass_context
def export(ctx, fmt, output):
    """Export graph with evidence coverage."""
    db = get_db(ctx.obj["db_path"])
    query = FGIPQuery(db)

    data = query.export_graph(output_format=fmt)

    # Add evidence coverage to export
    evidence = db.get_evidence_status()
    data["evidence_status"] = evidence

    with open(output, "w") as f:
        json.dump(data, f, indent=2)

    click.echo(f"Exported {data['stats']['nodes']} nodes and {data['stats']['edges']} edges to {output}")
    click.echo(f"Evidence Coverage: {evidence['evidence_coverage_pct']:.1f}%")
    click.echo(f"Tier 0/1 Coverage: {evidence['tier_01_coverage_pct']:.1f}%")


# ============ Review Commands (Agent Staging) ============

@cli.command()
@click.option("--all", "show_all", is_flag=True, help="Show all proposals, not just pending")
@click.option("--agent", "agent_name", default=None, help="Filter by agent name")
@click.option("--status", type=click.Choice(["PENDING", "APPROVED", "REJECTED"]), default=None)
@click.option("--limit", default=50, type=int)
@click.pass_context
def review(ctx, show_all, agent_name, status, limit):
    """List proposals awaiting review.

    By default shows PENDING proposals. Use --all to see all.

    \b
    Examples:
        fgip review                    # Show pending proposals
        fgip review --all              # Show all proposals
        fgip review --agent edgar      # Show proposals from EDGAR agent
        fgip review --status REJECTED  # Show rejected proposals
    """
    db = get_db(ctx.obj["db_path"])
    conn = db.connect()

    if show_all or status:
        proposals = staging_module.get_all_proposals(conn, agent_name=agent_name, status=status)
    else:
        proposals = staging_module.get_pending_proposals(conn, agent_name=agent_name)

    claims = proposals.get("claims", [])[:limit]
    edges = proposals.get("edges", [])[:limit]

    status_icons = {"PENDING": "○", "APPROVED": "✓", "REJECTED": "✗"}

    if claims:
        click.echo(f"\n=== Proposed Claims ({len(claims)}) ===\n")
        for claim in claims:
            icon = status_icons.get(claim["status"], "?")
            click.echo(f"[{icon}] {claim['proposal_id']}")
            click.echo(f"    Claim: {claim['claim_text'][:70]}...")
            click.echo(f"    Topic: {claim['topic']} | Agent: {claim['agent_name']}")
            if claim.get("source_url"):
                click.echo(f"    Source: {claim['source_url'][:60]}...")
            if claim.get("promotion_requirement"):
                click.echo(f"    Upgrade requires: {claim['promotion_requirement']}")
            if claim.get("reasoning"):
                click.echo(f"    Reasoning: {claim['reasoning'][:60]}...")
            click.echo()
    else:
        click.echo("\nNo proposed claims found.")

    if edges:
        click.echo(f"\n=== Proposed Edges ({len(edges)}) ===\n")
        for edge in edges:
            icon = status_icons.get(edge["status"], "?")
            click.echo(f"[{icon}] {edge['proposal_id']}")
            click.echo(f"    {edge['from_node']} --{edge['relationship']}--> {edge['to_node']}")
            click.echo(f"    Agent: {edge['agent_name']} | Confidence: {edge['confidence']:.2f}")
            if edge.get("detail"):
                click.echo(f"    Detail: {edge['detail'][:60]}...")
            if edge.get("proposed_claim_id"):
                click.echo(f"    Backing claim: {edge['proposed_claim_id']}")
            if edge.get("promotion_requirement"):
                click.echo(f"    Upgrade requires: {edge['promotion_requirement']}")
            click.echo()
    else:
        click.echo("\nNo proposed edges found.")


@cli.command()
@click.argument("proposal_id")
@click.option("--notes", default=None, help="Reviewer notes")
@click.pass_context
def accept(ctx, proposal_id, notes):
    """Accept a proposal and promote to production.

    This promotes a HYPOTHESIS proposal to the production claims/edges tables.
    Edges are created with HYPOTHESIS assertion level by default.

    \b
    Examples:
        fgip accept FGIP-PROPOSED-EDGAR-20260222-abc123
        fgip accept FGIP-PROPOSED-000001 --notes "Verified in SEC filing"
    """
    db = get_db(ctx.obj["db_path"])
    conn = db.connect()

    proposal = staging_module.get_proposal_by_id(conn, proposal_id)
    if not proposal:
        click.echo(f"Proposal not found: {proposal_id}", err=True)
        sys.exit(1)

    if proposal["status"] != "PENDING":
        click.echo(f"Proposal is not pending (status: {proposal['status']})", err=True)
        sys.exit(1)

    if proposal["type"] == "claim":
        click.echo(f"Accepting claim: {proposal['claim_text'][:70]}...")
        new_id = staging_module.accept_claim(conn, proposal_id, notes, reviewer="cli_user")
        if new_id:
            click.echo(f"✓ Promoted to production claim: {new_id}")
        else:
            click.echo("✗ Failed to accept claim", err=True)
            sys.exit(1)

    elif proposal["type"] == "edge":
        click.echo(f"Accepting edge: {proposal['from_node']} --{proposal['relationship']}--> {proposal['to_node']}")
        new_id = staging_module.accept_edge(conn, proposal_id, notes, reviewer="cli_user")
        if new_id:
            click.echo(f"✓ Promoted to production edge (rowid: {new_id})")
        else:
            click.echo("✗ Failed to accept edge", err=True)
            sys.exit(1)


@cli.command()
@click.argument("proposal_id")
@click.option("--reason", required=True, help="Reason for rejection (required)")
@click.pass_context
def reject(ctx, proposal_id, reason):
    """Reject a proposal with explanation.

    \b
    Examples:
        fgip reject FGIP-PROPOSED-000001 --reason "Source is not authoritative"
        fgip reject FGIP-PROPOSED-EDGAR-20260222-abc123 --reason "Data is outdated"
    """
    db = get_db(ctx.obj["db_path"])
    conn = db.connect()

    proposal = staging_module.get_proposal_by_id(conn, proposal_id)
    if not proposal:
        click.echo(f"Proposal not found: {proposal_id}", err=True)
        sys.exit(1)

    if proposal["status"] != "PENDING":
        click.echo(f"Proposal is not pending (status: {proposal['status']})", err=True)
        sys.exit(1)

    if proposal["type"] == "claim":
        click.echo(f"Rejecting claim: {proposal['claim_text'][:70]}...")
    else:
        click.echo(f"Rejecting edge: {proposal['from_node']} --{proposal['relationship']}--> {proposal['to_node']}")

    if staging_module.reject_proposal(conn, proposal_id, reason, reviewer="cli_user"):
        click.echo(f"✗ Rejected: {reason}")
    else:
        click.echo("Failed to reject proposal", err=True)
        sys.exit(1)


@cli.group()
def agent():
    """Agent management commands."""
    pass


@agent.command("run")
@click.argument("agent_name")
@click.option("--file", "-f", "file_path", help="Input file path (for citation_loader agent)")
@click.pass_context
def agent_run(ctx, agent_name, file_path):
    """Run an agent to collect evidence and propose claims/edges.

    \b
    Available agents:
        edgar           - SEC EDGAR watcher (13F, 10-K, 8-K filings)
        scotus          - Supreme Court docket watcher
        gao             - GAO/Agency PDF watcher
        rss             - RSS signal layer feed
        citation_loader - Batch loader from citation database markdown
        fara            - Foreign Agents Registration Act monitor (Tier 0)

    \b
    Examples:
        fgip agent run edgar
        fgip agent run scotus
        fgip agent run citation_loader --file /path/to/fgip_citation_database.md
        fgip agent run fara
    """
    db = get_db(ctx.obj["db_path"])

    # Import agents dynamically
    agent_map = {}

    try:
        from .agents.edgar import EDGARAgent
        agent_map["edgar"] = EDGARAgent
    except ImportError:
        pass

    try:
        from .agents.scotus import SCOTUSAgent
        agent_map["scotus"] = SCOTUSAgent
    except ImportError:
        pass

    try:
        from .agents.gao import GAOAgent
        agent_map["gao"] = GAOAgent
    except ImportError:
        pass

    try:
        from .agents.rss_signal import RSSSignalAgent
        agent_map["rss"] = RSSSignalAgent
    except ImportError:
        pass

    try:
        from .agents.citation_loader import CitationLoaderAgent
        agent_map["citation_loader"] = CitationLoaderAgent
    except ImportError:
        pass

    try:
        from .agents.fara import FARAAgent
        agent_map["fara"] = FARAAgent
    except ImportError:
        pass

    try:
        from .agents.opensecrets import OpenSecretsAgent
        agent_map["opensecrets"] = OpenSecretsAgent
    except ImportError:
        pass

    try:
        from .agents.usaspending import USASpendingAgent
        agent_map["usaspending"] = USASpendingAgent
    except ImportError:
        pass

    try:
        from .agents.federal_register import FederalRegisterAgent
        agent_map["federal_register"] = FederalRegisterAgent
    except ImportError:
        pass

    try:
        from .agents.dark_money import DarkMoneyAgent
        agent_map["dark_money"] = DarkMoneyAgent
    except ImportError:
        pass

    try:
        from .agents.podcast import PodcastAgent
        agent_map["podcast"] = PodcastAgent
    except ImportError:
        pass

    try:
        from .agents.narrative import NarrativeAgent
        agent_map["narrative"] = NarrativeAgent
    except ImportError:
        pass

    try:
        from .agents.bias_auditor import BiasAuditorAgent
        agent_map["bias_auditor"] = BiasAuditorAgent
    except ImportError:
        pass

    if agent_name not in agent_map:
        available = ", ".join(agent_map.keys()) if agent_map else "none available"
        click.echo(f"Unknown agent: {agent_name}", err=True)
        click.echo(f"Available agents: {available}", err=True)
        sys.exit(1)

    click.echo(f"Running agent: {agent_name}")
    agent_cls = agent_map[agent_name]

    # Handle citation_loader special case with --file argument
    if agent_name == "citation_loader":
        if not file_path:
            click.echo("Error: citation_loader agent requires --file argument", err=True)
            click.echo("Usage: fgip agent run citation_loader --file /path/to/citation_database.md", err=True)
            sys.exit(1)
        agent_instance = agent_cls(db, citation_file=file_path)
    else:
        agent_instance = agent_cls(db)

    results = agent_instance.run()

    click.echo(f"\n=== Agent Results ===")
    click.echo(f"Artifacts collected: {results['artifacts_collected']}")
    click.echo(f"Facts extracted: {results['facts_extracted']}")
    click.echo(f"Claims proposed: {results['claims_proposed']}")
    click.echo(f"Edges proposed: {results['edges_proposed']}")
    if results.get('nodes_proposed', 0) > 0:
        click.echo(f"Nodes proposed: {results['nodes_proposed']}")

    if results.get("errors"):
        click.echo(f"\nErrors ({len(results['errors'])}):")
        for err in results["errors"][:5]:
            click.echo(f"  - {err}")


@agent.command("status")
@click.pass_context
def agent_status(ctx):
    """Show proposal counts by agent."""
    db = get_db(ctx.obj["db_path"])
    conn = db.connect()

    stats = staging_module.get_agent_stats(conn)

    if not stats:
        click.echo("No agent proposals found.")
        return

    click.echo("\n=== Agent Status ===\n")

    for agent_name, counts in sorted(stats.items()):
        total_pending = counts.get("pending_claims", 0) + counts.get("pending_edges", 0)
        total_approved = counts.get("approved_claims", 0) + counts.get("approved_edges", 0)
        total_rejected = counts.get("rejected_claims", 0) + counts.get("rejected_edges", 0)

        click.echo(f"{agent_name}:")
        click.echo(f"  Pending:  {total_pending} (claims: {counts.get('pending_claims', 0)}, edges: {counts.get('pending_edges', 0)})")
        click.echo(f"  Approved: {total_approved} (claims: {counts.get('approved_claims', 0)}, edges: {counts.get('approved_edges', 0)})")
        click.echo(f"  Rejected: {total_rejected} (claims: {counts.get('rejected_claims', 0)}, edges: {counts.get('rejected_edges', 0)})")
        click.echo()


@agent.command("list")
@click.pass_context
def agent_list(ctx):
    """List available agents."""
    agents = [
        ("edgar", "SEC EDGAR watcher - Tracks 13F/10-K/8-K filings (DI-1)"),
        ("scotus", "Supreme Court docket watcher - Opinions, orders, amicus briefs"),
        ("gao", "GAO/Agency PDF watcher - Government reports"),
        ("fara", "FARA monitor - Foreign Agents Registration Act (Tier 0)"),
        ("opensecrets", "Campaign finance/lobbying monitor - OpenSecrets.org (Tier 1)"),
        ("usaspending", "Federal spending/awards - USASpending.gov (Tier 0)"),
        ("federal_register", "Rulemaking monitor - FederalRegister.gov (Tier 0)"),
        ("dark_money", "Dark Money Monitor - 501(c)(4), PACs, 990s (DI-8)"),
        ("podcast", "Podcast Intelligence - Long-form interviews, reference chains"),
        ("narrative", "Narrative Divergence - Investigative vs lobby rhetoric"),
        ("bias_auditor", "AI Training Bias Auditor - Narrative Distortion Index"),
        ("rss", "RSS signal layer - News feeds from Reuters, AP, etc."),
        ("citation_loader", "Batch loader from citation database markdown"),
    ]

    click.echo("\n=== Available Agents ===\n")
    for name, desc in agents:
        click.echo(f"  {name:16} - {desc}")

    click.echo("\nUse 'fgip agent run <name>' to run an agent.")


# Agent priority for run-all (validates pipeline progressively)
AGENT_PRIORITY = [
    "rss",              # Easiest, validates pipeline
    "edgar",            # Tier 0, SEC data, highest value
    "federal_register", # Tier 0, rulemaking
    "usaspending",      # Tier 0, federal awards
    "dark_money",       # Tier 0/1, FEC + ProPublica
    "podcast",          # Tier 1/2, long-form content
    "narrative",        # Tier 1/2, divergence detection
]


def load_agent(agent_name: str, conn):
    """Load an agent by name.

    Args:
        agent_name: Name of the agent to load
        conn: Database connection

    Returns:
        Agent instance or None if not found
    """
    # Import agent classes
    from .agents import (
        RSSSignalAgent, EDGARAgent, FederalRegisterAgent,
        USASpendingAgent, FARAAgent, OpenSecretsAgent
    )
    from .agents.dark_money import DarkMoneyAgent
    from .agents.podcast import PodcastAgent
    from .agents.narrative import NarrativeAgent

    # Agent name to class mapping
    agent_map = {
        "rss": RSSSignalAgent,
        "edgar": EDGARAgent,
        "federal_register": FederalRegisterAgent,
        "usaspending": USASpendingAgent,
        "fara": FARAAgent,
        "opensecrets": OpenSecretsAgent,
        "dark_money": DarkMoneyAgent,
        "podcast": PodcastAgent,
        "narrative": NarrativeAgent,
    }

    agent_class = agent_map.get(agent_name)
    if agent_class is None:
        return None

    return agent_class(conn)


@agent.command("run-all")
@click.option("--dry-run", is_flag=True, help="Show what would run without executing")
@click.option("--verify-after", is_flag=True, default=True, help="Run easter egg verification after all agents")
@click.pass_context
def agent_run_all(ctx, dry_run, verify_after):
    """Run all agents in priority order.

    Priority order: rss -> edgar -> federal_register -> usaspending
                    -> dark_money -> podcast -> narrative

    This validates the pipeline progressively, starting with the
    easiest agent (RSS) and moving to more complex data sources.

    \b
    Examples:
        fgip agent run-all              # Run all agents
        fgip agent run-all --dry-run    # Show what would run
    """
    if dry_run:
        click.echo("=== Dry Run: Agent Execution Plan ===\n")
        for i, agent_name in enumerate(AGENT_PRIORITY, 1):
            click.echo(f"  {i}. Would run: {agent_name}")
        click.echo(f"\nTotal: {len(AGENT_PRIORITY)} agents would be executed")
        return

    db = get_db(ctx.obj["db_path"])
    conn = db.connect()

    click.echo("=== Running All Agents ===\n")
    results = {"success": [], "failed": [], "skipped": []}

    for i, agent_name in enumerate(AGENT_PRIORITY, 1):
        click.echo(f"[{i}/{len(AGENT_PRIORITY)}] Running {agent_name}...")

        try:
            agent_instance = load_agent(agent_name, conn)
            if agent_instance is None:
                click.echo(f"  ⚠ Agent not found or not implemented: {agent_name}")
                results["skipped"].append(agent_name)
                continue

            # Run the agent
            run_result = agent_instance.run()

            if run_result.get("error"):
                click.echo(f"  ✗ Error: {run_result['error']}")
                results["failed"].append(agent_name)
            else:
                claims = run_result.get("claims_proposed", 0)
                edges = run_result.get("edges_proposed", 0)
                click.echo(f"  ✓ Done: {claims} claims, {edges} edges proposed")
                results["success"].append(agent_name)

        except Exception as e:
            click.echo(f"  ✗ Exception: {str(e)}")
            results["failed"].append(agent_name)

        click.echo()

    # Summary
    click.echo("=== Run Summary ===\n")
    click.echo(f"  Success: {len(results['success'])} agents")
    click.echo(f"  Failed:  {len(results['failed'])} agents")
    click.echo(f"  Skipped: {len(results['skipped'])} agents")

    if results["failed"]:
        click.echo(f"\n  Failed agents: {', '.join(results['failed'])}")
    if results["skipped"]:
        click.echo(f"  Skipped agents: {', '.join(results['skipped'])}")

    # Run verification if requested
    if verify_after and results["success"]:
        click.echo("\n=== Easter Egg Verification ===\n")
        report = run_verification(conn)
        pct = (report.eggs_found / report.eggs_total * 100) if report.eggs_total > 0 else 0
        health_icon = {"healthy": "✓", "degraded": "⚠", "broken": "✗"}.get(report.pipeline_health, "?")
        click.echo(f"  [{health_icon}] Pipeline Health: {report.pipeline_health.upper()}")
        click.echo(f"  Easter Eggs: {report.eggs_found}/{report.eggs_total} ({pct:.0f}%)")
        if report.eggs_missing:
            click.echo(f"  Missing: {', '.join(report.eggs_missing)}")


# ============ Staging Commands (Human-in-the-Loop Review) ============

@cli.group("staging")
def staging_group():
    """Proposal staging queue (human review)."""
    pass


@staging_group.command("pending")
@click.option("--agent", "agent_name", default=None, help="Filter by agent name")
@click.option("--type", "proposal_type", type=click.Choice(["claim", "edge"]), default=None)
@click.option("--limit", default=50, type=int)
@click.pass_context
def staging_pending(ctx, agent_name, proposal_type, limit):
    """List pending proposals awaiting human review.

    \b
    Examples:
        fgip staging pending
        fgip staging pending --agent edgar
        fgip staging pending --type claim
    """
    db = get_db(ctx.obj["db_path"])
    conn = db.connect()

    proposals = staging_module.get_pending_proposals(conn, agent_name=agent_name, proposal_type=proposal_type)

    claims = proposals.get("claims", [])[:limit]
    edges = proposals.get("edges", [])[:limit]

    if not claims and not edges:
        click.echo("No pending proposals found.")
        return

    if claims:
        click.echo(f"\n=== Pending Claims ({len(claims)}) ===\n")
        for claim in claims:
            click.echo(f"○ {claim['proposal_id']}")
            click.echo(f"    {claim['claim_text'][:70]}...")
            click.echo(f"    Agent: {claim['agent_name']} | Topic: {claim['topic']}")
            if claim.get("source_url"):
                click.echo(f"    Source: {claim['source_url'][:60]}...")
            click.echo()

    if edges:
        click.echo(f"\n=== Pending Edges ({len(edges)}) ===\n")
        for edge in edges:
            click.echo(f"○ {edge['proposal_id']}")
            click.echo(f"    {edge['from_node']} --{edge['relationship']}--> {edge['to_node']}")
            click.echo(f"    Agent: {edge['agent_name']} | Confidence: {edge['confidence']:.2f}")
            click.echo()


@staging_group.command("accept")
@click.argument("proposal_id")
@click.option("--notes", default=None, help="Reviewer notes")
@click.pass_context
def staging_accept(ctx, proposal_id, notes):
    """Accept a proposal and promote to production.

    \b
    Examples:
        fgip staging accept FGIP-PROPOSED-000001
        fgip staging accept FGIP-PROPOSED-000001 --notes "Verified in SEC filing"
    """
    db = get_db(ctx.obj["db_path"])
    conn = db.connect()

    proposal = staging_module.get_proposal_by_id(conn, proposal_id)
    if not proposal:
        click.echo(f"Proposal not found: {proposal_id}", err=True)
        sys.exit(1)

    if proposal["status"] != "PENDING":
        click.echo(f"Proposal is not pending (status: {proposal['status']})", err=True)
        sys.exit(1)

    if proposal["type"] == "claim":
        click.echo(f"Accepting claim: {proposal['claim_text'][:70]}...")
        new_id = staging_module.accept_claim(conn, proposal_id, notes, reviewer="cli_user")
        if new_id:
            click.echo(f"✓ Promoted to production claim: {new_id}")
        else:
            click.echo("✗ Failed to accept claim", err=True)
            sys.exit(1)
    elif proposal["type"] == "edge":
        click.echo(f"Accepting edge: {proposal['from_node']} --{proposal['relationship']}--> {proposal['to_node']}")
        new_id = staging_module.accept_edge(conn, proposal_id, notes, reviewer="cli_user")
        if new_id:
            click.echo(f"✓ Promoted to production edge (rowid: {new_id})")
        else:
            click.echo("✗ Failed to accept edge", err=True)
            sys.exit(1)


@staging_group.command("reject")
@click.argument("proposal_id")
@click.option("--reason", required=True, help="Reason for rejection (required)")
@click.pass_context
def staging_reject(ctx, proposal_id, reason):
    """Reject a proposal with explanation.

    \b
    Examples:
        fgip staging reject FGIP-PROPOSED-000001 --reason "Source is not authoritative"
    """
    db = get_db(ctx.obj["db_path"])
    conn = db.connect()

    proposal = staging_module.get_proposal_by_id(conn, proposal_id)
    if not proposal:
        click.echo(f"Proposal not found: {proposal_id}", err=True)
        sys.exit(1)

    if proposal["status"] != "PENDING":
        click.echo(f"Proposal is not pending (status: {proposal['status']})", err=True)
        sys.exit(1)

    if proposal["type"] == "claim":
        click.echo(f"Rejecting claim: {proposal['claim_text'][:70]}...")
    else:
        click.echo(f"Rejecting edge: {proposal['from_node']} --{proposal['relationship']}--> {proposal['to_node']}")

    if staging_module.reject_proposal(conn, proposal_id, reason, reviewer="cli_user"):
        click.echo(f"✗ Rejected: {reason}")
    else:
        click.echo("Failed to reject proposal", err=True)
        sys.exit(1)


@staging_group.command("show")
@click.argument("proposal_id")
@click.pass_context
def staging_show(ctx, proposal_id):
    """Show proposal details with correlation metrics.

    \b
    Examples:
        fgip staging show FGIP-PROPOSED-000001
    """
    db = get_db(ctx.obj["db_path"])
    conn = db.connect()

    proposal = staging_module.get_proposal_by_id(conn, proposal_id)
    if not proposal:
        click.echo(f"Proposal not found: {proposal_id}", err=True)
        sys.exit(1)

    status_icons = {"PENDING": "○", "APPROVED": "✓", "REJECTED": "✗"}
    icon = status_icons.get(proposal["status"], "?")

    click.echo(f"\n=== Proposal: {proposal_id} ===\n")
    click.echo(f"Status: [{icon}] {proposal['status']}")
    click.echo(f"Type: {proposal['type']}")
    click.echo(f"Agent: {proposal['agent_name']}")
    click.echo(f"Created: {proposal['created_at']}")

    if proposal["type"] == "claim":
        click.echo(f"\nClaim Text:\n  {proposal['claim_text']}")
        click.echo(f"Topic: {proposal['topic']}")
        if proposal.get("source_url"):
            click.echo(f"Source URL: {proposal['source_url']}")
        if proposal.get("artifact_path"):
            click.echo(f"Artifact: {proposal['artifact_path']}")
            click.echo(f"Artifact Hash: {proposal.get('artifact_hash', 'N/A')}")
    else:
        click.echo(f"\nEdge: {proposal['from_node']} --{proposal['relationship']}--> {proposal['to_node']}")
        click.echo(f"Confidence: {proposal['confidence']:.3f}")
        if proposal.get("detail"):
            click.echo(f"Detail: {proposal['detail']}")
        if proposal.get("proposed_claim_id"):
            click.echo(f"Backing Claim: {proposal['proposed_claim_id']}")

    if proposal.get("reasoning"):
        click.echo(f"\nReasoning:\n  {proposal['reasoning']}")

    if proposal.get("promotion_requirement"):
        click.echo(f"\nUpgrade Requirement:\n  {proposal['promotion_requirement']}")

    # Compute and show correlation metrics
    click.echo("\n--- Correlation Metrics ---")
    metrics = staging_module.compute_correlation_metrics(conn, proposal_id)
    if "error" in metrics:
        click.echo(f"  Error: {metrics['error']}")
    else:
        for metric_name, value in metrics.get("metrics", {}).items():
            if metric_name == "source_overlap":
                click.echo(f"  Source Overlap: {value:.3f}")
            elif metric_name == "path_distance":
                if value == -1:
                    click.echo(f"  Path Distance: No path found")
                else:
                    click.echo(f"  Path Distance: {value} hops")
            elif metric_name == "convergence_score":
                click.echo(f"  Convergence Score: {value}")
            elif metric_name == "similar_claims":
                click.echo(f"  Similar Claims: {value}")
            else:
                click.echo(f"  {metric_name}: {value}")


@staging_group.command("stats")
@click.pass_context
def staging_stats(ctx):
    """Show agent proposal statistics.

    \b
    Examples:
        fgip staging stats
    """
    db = get_db(ctx.obj["db_path"])
    conn = db.connect()

    stats = staging_module.get_agent_stats(conn)

    if not stats:
        click.echo("No agent proposals found.")
        return

    click.echo("\n=== Agent Proposal Statistics ===\n")

    for agent_name, counts in sorted(stats.items()):
        total_pending = counts.get("pending_claims", 0) + counts.get("pending_edges", 0)
        total_approved = counts.get("approved_claims", 0) + counts.get("approved_edges", 0)
        total_rejected = counts.get("rejected_claims", 0) + counts.get("rejected_edges", 0)

        click.echo(f"{agent_name}:")
        click.echo(f"  ○ Pending:  {total_pending} (claims: {counts.get('pending_claims', 0)}, edges: {counts.get('pending_edges', 0)})")
        click.echo(f"  ✓ Approved: {total_approved} (claims: {counts.get('approved_claims', 0)}, edges: {counts.get('approved_edges', 0)})")
        click.echo(f"  ✗ Rejected: {total_rejected} (claims: {counts.get('rejected_claims', 0)}, edges: {counts.get('rejected_edges', 0)})")
        click.echo()


@staging_group.command("promote-edge")
@click.argument("edge_id")
@click.option("--to", "to_level", required=True,
              type=click.Choice(["INFERENCE", "FACT"]),
              help="Target assertion level")
@click.option("--claim", "claim_id", required=True,
              help="Claim ID that justifies promotion")
@click.option("--receipt", "receipt_hash", default=None,
              help="Receipt/artifact hash (required for FACT on inferential edges)")
@click.option("--notes", default=None, help="Justification notes")
@click.pass_context
def staging_promote_edge(ctx, edge_id, to_level, claim_id, receipt_hash, notes):
    """Promote an edge to a higher assertion level.

    This is a DELIBERATE action requiring explicit justification.
    "Accept" means safe-to-store. "Promote" means increasing confidence.

    Promotion path: HYPOTHESIS → INFERENCE → FACT

    \b
    Requirements:
      - INFERENCE: claim must exist
      - FACT: claim must be EVIDENCED/VERIFIED + artifact hash required
             for inferential edge types (ENABLED, CAUSED, etc.)

    \b
    Examples:
        fgip staging promote-edge edge_enabled_pntr_china --to INFERENCE --claim FGIP-000042
        fgip staging promote-edge edge_owns_vanguard_jpmorgan --to FACT --claim FGIP-000048 --receipt abc123
    """
    db = get_db(ctx.obj["db_path"])
    conn = db.connect()

    # Get current edge state
    edge = db.get_edge(edge_id)
    if not edge:
        click.echo(f"Edge not found: {edge_id}", err=True)
        sys.exit(1)

    click.echo(f"Edge: {edge.from_node_id} --{edge.edge_type.value}--> {edge.to_node_id}")
    click.echo(f"Current assertion: {edge.assertion_level}")
    click.echo(f"Target assertion: {to_level}")

    # Verify claim
    claim = db.get_claim(claim_id)
    if not claim:
        click.echo(f"Claim not found: {claim_id}", err=True)
        sys.exit(1)

    click.echo(f"Backing claim: {claim_id} [{claim.status.value}]")

    # Attempt promotion
    if staging_module.promote_edge(conn, edge_id, to_level, claim_id, receipt_hash, "cli_user", notes):
        click.echo(f"\n✓ Promoted: {edge.assertion_level} → {to_level}")
    else:
        click.echo("\n✗ Promotion failed. Check requirements:", err=True)
        click.echo("  - Cannot demote or stay at same level", err=True)
        click.echo("  - FACT requires claim status EVIDENCED/VERIFIED", err=True)
        click.echo("  - FACT on inferential edges requires --receipt", err=True)
        sys.exit(1)


@staging_group.command("prelint")
@click.option("--agent", "agent_name", default=None, help="Filter by agent name")
@click.option("--auto-reject", is_flag=True, help="Auto-reject proposals with ERROR-level issues")
@click.pass_context
def staging_prelint(ctx, agent_name, auto_reject):
    """Run prelint on pending proposals to catch garbage before review.

    Validates proposed edges and nodes against hygiene rules:
    - Garbage patterns (dollar amounts, date ranges, share counts)
    - Franken-nodes (multiple entities conjoined)
    - Invalid edge types
    - Node ID should use canonical form

    \b
    Examples:
        fgip staging prelint
        fgip staging prelint --agent citation_loader
        fgip staging prelint --auto-reject
    """
    from . import staging_prelint as prelint_module

    db = get_db(ctx.obj["db_path"])
    conn = db.connect()

    click.echo("\n=== Staging Prelint ===\n")

    results = prelint_module.run_prelint_on_staging(conn, agent_name)

    click.echo(f"Edges checked: {results['edges_checked']}")
    click.echo(f"  - With errors: {results['edges_with_errors']}")
    click.echo(f"  - With warnings: {results['edges_with_warnings']}")
    click.echo(f"Nodes checked: {results['nodes_checked']}")
    click.echo(f"  - With errors: {results['nodes_with_errors']}")
    click.echo(f"  - With warnings: {results['nodes_with_warnings']}")

    if results["issues"]:
        click.echo(f"\n=== Issues Found ({len(results['issues'])}) ===\n")

        auto_rejected = 0
        for item in results["issues"]:
            proposal_id = item["proposal_id"]
            proposal_type = item["type"]
            issues = item["issues"]

            has_error = any(i["severity"] == "ERROR" for i in issues)
            marker = "✗" if has_error else "⚠"

            click.echo(f"{marker} {proposal_id} ({proposal_type})")
            for issue in issues:
                sev = issue["severity"]
                icon = "✗" if sev == "ERROR" else ("⚠" if sev == "WARNING" else "ℹ")
                click.echo(f"    {icon} [{issue['field']}] {issue['message']}")

            # Auto-reject if requested and has errors
            if auto_reject and has_error:
                reason = "; ".join(f"{i['field']}: {i['message']}" for i in issues if i["severity"] == "ERROR")
                if proposal_type == "edge":
                    conn.execute(
                        "UPDATE proposed_edges SET status = 'REJECTED', reviewer_notes = ? WHERE proposal_id = ?",
                        (f"[AUTO-REJECT PRELINT] {reason}", proposal_id)
                    )
                elif proposal_type == "node":
                    conn.execute(
                        "UPDATE proposed_nodes SET status = 'REJECTED', reviewer_notes = ? WHERE proposal_id = ?",
                        (f"[AUTO-REJECT PRELINT] {reason}", proposal_id)
                    )
                auto_rejected += 1
                click.echo(f"    → Auto-rejected")

            click.echo()

        if auto_reject and auto_rejected > 0:
            conn.commit()
            click.echo(f"Auto-rejected {auto_rejected} proposals with ERROR-level issues.")
    else:
        click.echo("\n✓ No issues found. Staging queue is clean.")


# ============ Lint Command ============

@cli.command("lint")
@click.option("--fix", is_flag=True, help="Suggest fixes (doesn't modify)")
@click.pass_context
def lint_cmd(ctx, fix):
    """Lint the knowledge graph for epistemic integrity violations.

    Flags:
    - FACT edges without Tier 0/1 sources
    - VERIFIED claims without artifacts
    - Inferential edges marked FACT (requires explicit override)
    - Orphan edges without claims

    \b
    Examples:
        fgip lint
        fgip lint --fix
    """
    from .schema import INFERENTIAL_EDGE_TYPES

    db = get_db(ctx.obj["db_path"])
    conn = db.connect()

    issues = []

    click.echo("\n=== FGIP Epistemic Lint ===\n")

    # 1. FACT edges without Tier 0/1 sources
    click.echo("Checking FACT edges for Tier 0/1 sourcing...")
    rows = conn.execute(
        """SELECT e.edge_id, e.edge_type, e.from_node_id, e.to_node_id, e.claim_id
           FROM edges e
           WHERE e.assertion_level = 'FACT'"""
    ).fetchall()

    fact_without_tier01 = []
    for row in rows:
        if not row["claim_id"]:
            fact_without_tier01.append((row["edge_id"], "no claim"))
            continue

        sources = db.get_claim_sources(row["claim_id"])
        if not sources:
            fact_without_tier01.append((row["edge_id"], "claim has no sources"))
            continue

        best_tier = min(s.tier for s in sources)
        if best_tier > 1:
            fact_without_tier01.append((row["edge_id"], f"best source is Tier {best_tier}"))

    if fact_without_tier01:
        click.echo(f"  ✗ {len(fact_without_tier01)} FACT edge(s) without Tier 0/1 sources:")
        for edge_id, reason in fact_without_tier01[:10]:
            click.echo(f"    - {edge_id}: {reason}")
            if fix:
                click.echo(f"      FIX: Demote to INFERENCE or add Tier 0/1 source")
        issues.extend(fact_without_tier01)
    else:
        click.echo("  ✓ All FACT edges have Tier 0/1 sources")

    # 2. VERIFIED claims without artifacts
    click.echo("\nChecking VERIFIED claims for artifacts...")
    rows = conn.execute(
        "SELECT claim_id, claim_text FROM claims WHERE status = 'VERIFIED'"
    ).fetchall()

    verified_without_artifact = []
    for row in rows:
        sources = db.get_claim_sources(row["claim_id"])
        has_artifact = any(s.artifact_hash for s in sources)
        if not has_artifact:
            verified_without_artifact.append(row["claim_id"])

    if verified_without_artifact:
        click.echo(f"  ✗ {len(verified_without_artifact)} VERIFIED claim(s) without artifacts:")
        for claim_id in verified_without_artifact[:10]:
            click.echo(f"    - {claim_id}")
            if fix:
                click.echo(f"      FIX: Downgrade to EVIDENCED or attach artifact")
        issues.extend(verified_without_artifact)
    else:
        click.echo("  ✓ All VERIFIED claims have artifacts")

    # 3. Inferential edges marked FACT
    click.echo("\nChecking inferential edges for FACT assertion...")
    rows = conn.execute(
        """SELECT edge_id, edge_type, from_node_id, to_node_id, claim_id
           FROM edges
           WHERE assertion_level = 'FACT'"""
    ).fetchall()

    inferential_as_fact = []
    for row in rows:
        if row["edge_type"] in INFERENTIAL_EDGE_TYPES:
            # Check if it has explicit promotion in metadata
            inferential_as_fact.append((row["edge_id"], row["edge_type"]))

    if inferential_as_fact:
        click.echo(f"  ⚠ {len(inferential_as_fact)} inferential edge(s) marked FACT:")
        for edge_id, edge_type in inferential_as_fact[:10]:
            click.echo(f"    - {edge_id} ({edge_type})")
            if fix:
                click.echo(f"      FIX: Verify explicit promotion or demote to INFERENCE")
        # These are warnings, not hard errors if explicitly promoted
    else:
        click.echo("  ✓ No inferential edges marked FACT")

    # 4. Orphan edges without claims
    click.echo("\nChecking for orphan edges (no claims)...")
    orphan_count = conn.execute(
        "SELECT COUNT(*) FROM edges WHERE claim_id IS NULL"
    ).fetchone()[0]

    if orphan_count > 0:
        click.echo(f"  ✗ {orphan_count} edge(s) without claims (Square-One violation)")
        if fix:
            click.echo(f"      FIX: Run 'fgip migrate' to create claims for legacy edges")
        issues.append(f"{orphan_count} orphan edges")
    else:
        click.echo("  ✓ All edges have claims")

    # Summary
    click.echo("\n=== Summary ===")
    if issues:
        click.echo(f"Found {len(issues)} issue(s)")
        click.echo("Run 'fgip lint --fix' for suggested fixes")
        sys.exit(1)
    else:
        click.echo("✓ No epistemic integrity issues found")


# ============ Prove Command ============

@cli.command("prove")
@click.argument("claim_id")
@click.pass_context
def prove_cmd(ctx, claim_id):
    """Show artifact path, SHA256, and sources for a claim.

    Displays the full evidence chain for a claim including:
    - Claim text and status
    - All backing sources with tier info
    - Artifact paths and SHA256 hashes

    \b
    Examples:
        fgip prove FGIP-000001
        fgip prove FGIP-000042
    """
    db = get_db(ctx.obj["db_path"])

    claim = db.get_claim(claim_id)
    if not claim:
        click.echo(f"Claim not found: {claim_id}", err=True)
        sys.exit(1)

    status_icons = {"MISSING": "✗", "PARTIAL": "○", "EVIDENCED": "◐", "VERIFIED": "✓"}
    icon = status_icons.get(claim.status.value, "?")

    click.echo(f"\n=== Claim: {claim.claim_id} ===\n")
    click.echo(f"Text: {claim.claim_text}")
    click.echo(f"Topic: {claim.topic}")
    click.echo(f"Status: [{icon}] {claim.status.value}")
    click.echo(f"Required Tier: {claim.required_tier}")
    if claim.notes:
        click.echo(f"Notes: {claim.notes}")

    sources = db.get_claim_sources(claim_id)

    if not sources:
        click.echo("\n⚠ No sources linked to this claim")
        click.echo("  This claim needs source URLs to upgrade from MISSING status.")
        return

    tier_names = {0: "Primary (T0)", 1: "Journalism (T1)", 2: "Commentary (T2)"}

    click.echo(f"\n=== Sources ({len(sources)}) ===\n")

    for src in sources:
        tier_name = tier_names.get(src.tier, f"Tier {src.tier}")
        artifact_status = "✓" if src.artifact_path else "○"

        click.echo(f"[{artifact_status}] {tier_name}")
        click.echo(f"    URL: {src.url}")
        click.echo(f"    Domain: {src.domain}")

        if src.artifact_path:
            click.echo(f"    Artifact: {src.artifact_path}")
            if src.artifact_hash:
                click.echo(f"    SHA256: {src.artifact_hash}")
        else:
            click.echo("    Artifact: Not captured")

        if src.retrieved_at:
            click.echo(f"    Retrieved: {src.retrieved_at}")

        click.echo()

    # Show upgrade path
    best_tier = min(s.tier for s in sources)
    has_artifact = any(s.artifact_path for s in sources)

    click.echo("--- Upgrade Path ---")
    if claim.status.value == "MISSING":
        click.echo("  Current: MISSING → Add source URL to upgrade to PARTIAL")
    elif claim.status.value == "PARTIAL":
        click.echo("  Current: PARTIAL → Capture artifact (PDF/HTML) to upgrade to EVIDENCED")
    elif claim.status.value == "EVIDENCED":
        if best_tier > 1:
            click.echo("  Current: EVIDENCED → Add Tier 0/1 source to upgrade to VERIFIED")
        else:
            click.echo("  Current: EVIDENCED → Mark as VERIFIED (has Tier 0/1 source)")
    else:
        click.echo("  Current: VERIFIED ✓ (fully evidenced)")


# ============ Chain Command ============

@cli.command("chain")
@click.option("--start", required=True, help="Starting node ID")
@click.option("--end", required=True, help="Target node ID")
@click.option("--only", "only_level", type=click.Choice(["proven", "fact", "inference", "hypothesis"]),
              help="Only show edges at this assertion level")
@click.option("--include", "include_levels", multiple=True,
              type=click.Choice(["fact", "inference", "hypothesis"]),
              help="Include edges at these assertion levels (can specify multiple)")
@click.option("--max-depth", default=6, type=int, help="Maximum path depth")
@click.pass_context
def chain_cmd(ctx, start, end, only_level, include_levels, max_depth):
    """Show causal chain with assertion level filtering.

    Traces paths between two nodes and shows the assertion level
    (FACT, INFERENCE, HYPOTHESIS) for each edge.

    \b
    Filtering options:
      --only proven      STRICT: assertion=FACT + claim=VERIFIED + Tier≤1 + artifact
      --only fact        Only FACT assertion level (may be weakly sourced!)
      --only inference   Only INFERENCE assertion level
      --only hypothesis  Only HYPOTHESIS assertion level
      --include fact     Include FACT edges (can combine multiple)

    \b
    Examples:
        fgip chain --start us-chamber-of-commerce --end fentanyl-crisis
        fgip chain --start chamber --end fentanyl --only fact
        fgip chain --start chamber --end fentanyl --include fact --include inference
    """
    db = get_db(ctx.obj["db_path"])
    conn = db.connect()

    # Build level filter set
    level_filter = set()
    if only_level:
        if only_level == "proven":
            level_filter.add("FACT")  # Will also check for Tier 0/1 evidence
        else:
            level_filter.add(only_level.upper())
    elif include_levels:
        level_filter = {l.upper() for l in include_levels}

    # Find paths using BFS
    paths = _find_paths_bfs(conn, start, end, max_depth)

    if not paths:
        click.echo(f"No paths found from '{start}' to '{end}' within {max_depth} hops")
        return

    click.echo(f"\n=== Causal Chains: {start} → {end} ===\n")
    click.echo(f"Found {len(paths)} path(s)")

    if level_filter:
        filter_desc = " | ".join(sorted(level_filter))
        if only_level == "proven":
            filter_desc = "PROVEN (FACT + VERIFIED + Tier≤1 + artifact)"
        click.echo(f"Filter: {filter_desc}")

    status_icons = {"MISSING": "✗", "PARTIAL": "○", "EVIDENCED": "◐", "VERIFIED": "✓"}
    assertion_icons = {"FACT": "F", "INFERENCE": "I", "HYPOTHESIS": "H"}

    for path_num, path in enumerate(paths[:5], 1):
        click.echo(f"\n--- Path {path_num} ({len(path)} hop(s)) ---\n")

        path_valid = True
        tier_01_count = 0
        total_edges = 0

        for i, (from_node_id, edge_data, to_node_id) in enumerate(path):
            assertion = edge_data.get("assertion_level", "FACT")
            edge_type = edge_data.get("edge_type", "?")
            claim_id = edge_data.get("claim_id")

            # Check filter
            if level_filter:
                if only_level == "proven":
                    # STRICT "proven" filter per CLAUDE.md:
                    # 1. assertion_level == FACT
                    # 2. claim status == VERIFIED
                    # 3. best_source_tier <= 1
                    # 4. artifact_hash present
                    # If ANY missing, it's "asserted FACT" not "proven"
                    if assertion != "FACT":
                        path_valid = False
                        continue

                    if not claim_id:
                        path_valid = False
                        continue

                    claim = db.get_claim(claim_id)
                    if not claim or claim.status.value != "VERIFIED":
                        path_valid = False
                        continue

                    sources = db.get_claim_sources(claim_id)
                    if not sources:
                        path_valid = False
                        continue

                    best_tier = min((s.tier for s in sources), default=2)
                    has_artifact = any(s.artifact_hash for s in sources)

                    if best_tier > 1 or not has_artifact:
                        path_valid = False
                        continue
                elif assertion not in level_filter:
                    path_valid = False
                    continue

            total_edges += 1
            a_icon = assertion_icons.get(assertion, "?")

            # Get claim info
            claim_status = "?"
            if claim_id:
                claim = db.get_claim(claim_id)
                if claim:
                    claim_status = claim.status.value
                    sources = db.get_claim_sources(claim_id)
                    best_tier = min((s.tier for s in sources), default=2)
                    if best_tier <= 1:
                        tier_01_count += 1

            s_icon = status_icons.get(claim_status, "?")

            # Get node names
            from_node = db.get_node(from_node_id)
            to_node = db.get_node(to_node_id)
            from_name = from_node.name if from_node else from_node_id
            to_name = to_node.name if to_node else to_node_id

            click.echo(f"  {i+1}. [{a_icon}|{s_icon}] {from_name}")
            click.echo(f"         --({edge_type}:{assertion})-->")
            click.echo(f"      {to_name}")
            if claim_id:
                click.echo(f"      Claim: {claim_id}")
            click.echo()

        if path_valid and total_edges > 0:
            coverage = (tier_01_count / total_edges * 100)
            click.echo(f"  Evidence: {tier_01_count}/{total_edges} Tier 0/1 ({coverage:.0f}% coverage)")


def _find_paths_bfs(conn, start: str, end: str, max_depth: int = 6):
    """Find all paths between two nodes using BFS."""
    if start == end:
        return []

    # BFS with path tracking
    queue = [(start, [(start, None, start)])]  # (current_node, path)
    all_paths = []
    visited_states = set()

    while queue:
        current, path = queue.pop(0)

        if len(path) > max_depth + 1:
            continue

        # Get outgoing edges
        rows = conn.execute(
            """SELECT edge_id, edge_type, from_node_id, to_node_id,
                      claim_id, assertion_level
               FROM edges WHERE from_node_id = ?""",
            (current,)
        ).fetchall()

        for row in rows:
            next_node = row["to_node_id"]
            edge_data = {
                "edge_id": row["edge_id"],
                "edge_type": row["edge_type"],
                "claim_id": row["claim_id"],
                "assertion_level": row["assertion_level"] or "FACT",
            }

            # Create state for cycle detection
            state = (next_node, len(path))
            if state in visited_states:
                continue
            visited_states.add(state)

            new_path = path + [(current, edge_data, next_node)]

            if next_node == end:
                # Found a path - extract just the edges
                edges_only = [(p[0], p[1], p[2]) for p in new_path[1:]]
                all_paths.append(edges_only)
            else:
                queue.append((next_node, new_path))

    return all_paths


@cli.command()
@click.argument("proposal_id")
@click.pass_context
def correlate(ctx, proposal_id):
    """Compute correlation metrics for a proposal.

    Metrics computed:
    - source_overlap: Do entities repeatedly appear in same sources? (0-1)
    - path_distance: Graph distance between entities (hops)
    - convergence_score: How many signal categories confirm?
    - similar_claims: For claims, count of similar existing claims

    \b
    Examples:
        fgip correlate FGIP-PROPOSED-000001
    """
    db = get_db(ctx.obj["db_path"])
    conn = db.connect()

    proposal = staging_module.get_proposal_by_id(conn, proposal_id)
    if not proposal:
        click.echo(f"Proposal not found: {proposal_id}", err=True)
        sys.exit(1)

    click.echo(f"Computing correlation metrics for: {proposal_id}")
    click.echo(f"Type: {proposal['type']}")

    if proposal["type"] == "edge":
        click.echo(f"Edge: {proposal['from_node']} --{proposal['relationship']}--> {proposal['to_node']}")
    else:
        click.echo(f"Claim: {proposal['claim_text'][:60]}...")

    metrics = staging_module.compute_correlation_metrics(conn, proposal_id)

    if "error" in metrics:
        click.echo(f"\nError: {metrics['error']}", err=True)
        sys.exit(1)

    click.echo("\n=== Correlation Metrics ===\n")
    for metric_name, value in metrics.get("metrics", {}).items():
        if metric_name == "source_overlap":
            click.echo(f"  Source Overlap: {value:.3f} (0=none, 1=complete)")
        elif metric_name == "path_distance":
            if value == -1:
                click.echo(f"  Path Distance: No path found (max depth 6)")
            else:
                click.echo(f"  Path Distance: {value} hops")
        elif metric_name == "convergence_score":
            click.echo(f"  Convergence Score: {value} distinct relationship types")
        elif metric_name == "similar_claims":
            click.echo(f"  Similar Claims: {value} existing claims match pattern")
        else:
            click.echo(f"  {metric_name}: {value}")


# ============ Verification Commands ============

@cli.group()
def verify():
    """Easter egg verification and pipeline health."""
    pass


@verify.command("easter-eggs")
@click.option("--agent", default=None, help="Filter by agent name")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def verify_easter_eggs(ctx, agent, as_json):
    """Check which easter eggs have been discovered.

    Easter eggs are known-true facts that agents MUST discover.
    They validate the full pipeline: fetch -> extract -> propose -> stage.

    \b
    Examples:
        fgip verify easter-eggs              # Check all
        fgip verify easter-eggs --agent edgar  # Check one agent
        fgip verify easter-eggs --json       # JSON output
    """
    db = get_db(ctx.obj["db_path"])
    conn = db.connect()

    report = run_verification(conn, agent_name=agent)

    if as_json:
        click.echo(report.to_json())
    else:
        click.echo(report.to_text())


@verify.command("report")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]),
              default="text", help="Output format")
@click.option("--save", type=click.Path(), default=None,
              help="Save report to file")
@click.pass_context
def verify_report(ctx, output_format, save):
    """Generate full verification report.

    Shows pipeline health based on easter egg discovery rate:
    - healthy: 100% of easter eggs found
    - degraded: 60-99% found
    - broken: <60% found

    \b
    Examples:
        fgip verify report                   # Text report
        fgip verify report --format json     # JSON report
        fgip verify report --save report.json  # Save to file
    """
    db = get_db(ctx.obj["db_path"])
    conn = db.connect()

    report = run_verification(conn)

    if output_format == "json":
        output = report.to_json()
    else:
        output = report.to_text()

    if save:
        from .verification import save_verification_report
        save_verification_report(report, save)
        click.echo(f"Report saved to: {save}")
    else:
        click.echo(output)


@verify.command("quick")
@click.pass_context
def verify_quick(ctx):
    """Quick verification status one-liner.

    \b
    Output format: "Easter Eggs: X/Y (Z%) [status]"

    \b
    Examples:
        fgip verify quick
    """
    db = get_db(ctx.obj["db_path"])
    conn = db.connect()
    click.echo(quick_verify(conn))


# ============ Gap Detection Commands ============

@cli.group()
def gaps():
    """Gap detection and analysis."""
    pass


@gaps.command("report")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--save", type=click.Path(), default=None, help="Save report to file")
@click.pass_context
def gaps_report(ctx, as_json, save):
    """Generate full gap analysis report.

    Analyzes the knowledge graph for:
    - Orphan nodes (no edges)
    - Missing ownership data
    - Missing lobbying data
    - Missing rulemaking implementation
    - Source coverage gaps (only Tier 2)
    - Temporal gaps (stale nodes)
    - Missing reciprocal edges

    \b
    Examples:
        fgip gaps report              # Text report
        fgip gaps report --json       # JSON output
        fgip gaps report --save gaps.json
    """
    db = get_db(ctx.obj["db_path"])
    detector = GapDetector(db)
    report = detector.generate_report()

    if as_json or save:
        import json
        output = json.dumps(detector.to_dict(), indent=2)
        if save:
            with open(save, "w") as f:
                f.write(output)
            click.echo(f"Report saved to: {save}")
        else:
            click.echo(output)
    else:
        # Text output
        click.echo("=== FGIP Gap Analysis Report ===")
        click.echo(f"Timestamp: {report.timestamp}")
        click.echo(f"Total Nodes: {report.total_nodes}")
        click.echo(f"Total Edges: {report.total_edges}")
        click.echo(f"Total Gaps: {len(report.gaps)}")
        click.echo()

        click.echo("=== Gaps by Type ===")
        for gap_type, count in sorted(report.gap_by_type.items(), key=lambda x: -x[1]):
            click.echo(f"  {gap_type}: {count}")
        click.echo()

        click.echo("=== Top Agent Suggestions ===")
        for i, sug in enumerate(report.suggestions[:5], 1):
            click.echo(f"  {i}. {sug.agent} (priority {sug.priority})")
            click.echo(f"     Gaps: {sug.gap_count} | Reason: {sug.reason}")
            if sug.targets[:5]:
                click.echo(f"     Targets: {', '.join(sug.targets[:5])}")
            click.echo()

        click.echo("=== Coverage Stats ===")
        stats = report.coverage_stats
        click.echo(f"  Connectivity: {stats['connectivity_rate']:.1%}")
        click.echo(f"  Orphan nodes: {stats['orphan_nodes']}")
        click.echo(f"  Evidence rate: {stats['evidence_rate']:.1%}")


@gaps.command("orphans")
@click.option("--limit", default=50, type=int, help="Max results to show")
@click.pass_context
def gaps_orphans(ctx, limit):
    """List orphan nodes (nodes with no edges).

    \b
    Examples:
        fgip gaps orphans
        fgip gaps orphans --limit 20
    """
    db = get_db(ctx.obj["db_path"])
    detector = GapDetector(db)
    orphans = detector.detect_orphan_nodes()

    if not orphans:
        click.echo("No orphan nodes found.")
        return

    click.echo(f"=== Orphan Nodes ({len(orphans)} total) ===\n")
    for gap in orphans[:limit]:
        click.echo(f"  {gap.node_id}")
        click.echo(f"    Name: {gap.node_name}")
        click.echo(f"    Type: {gap.node_type}")
        if gap.suggested_agent:
            click.echo(f"    Suggested: {gap.suggested_agent}")
        click.echo()

    if len(orphans) > limit:
        click.echo(f"  ... and {len(orphans) - limit} more")


@gaps.command("sources")
@click.option("--limit", default=50, type=int, help="Max results to show")
@click.pass_context
def gaps_sources(ctx, limit):
    """List nodes/edges needing source tier upgrades.

    Shows edges backed only by Tier 2 sources that need
    Tier 0 (government) or Tier 1 (journalism) sources.

    \b
    Examples:
        fgip gaps sources
    """
    db = get_db(ctx.obj["db_path"])
    detector = GapDetector(db)
    source_gaps = detector.detect_source_coverage_gaps()

    if not source_gaps:
        click.echo("No source coverage gaps found.")
        return

    click.echo(f"=== Source Coverage Gaps ({len(source_gaps)} total) ===\n")
    for gap in source_gaps[:limit]:
        click.echo(f"  {gap.node_name}")
        click.echo(f"    Edge: {gap.expected_edge_type}")
        click.echo(f"    {gap.description}")
        if gap.suggested_agent:
            click.echo(f"    Suggested: {gap.suggested_agent}")
        click.echo()

    if len(source_gaps) > limit:
        click.echo(f"  ... and {len(source_gaps) - limit} more")


@gaps.command("temporal")
@click.option("--months", default=6, type=int, help="Months threshold for staleness")
@click.option("--limit", default=50, type=int, help="Max results to show")
@click.pass_context
def gaps_temporal(ctx, months, limit):
    """List nodes with no recent activity.

    Finds entities that haven't been updated in N months.

    \b
    Examples:
        fgip gaps temporal
        fgip gaps temporal --months 3
    """
    db = get_db(ctx.obj["db_path"])
    detector = GapDetector(db)
    temporal_gaps = detector.detect_temporal_gaps(months=months)

    if not temporal_gaps:
        click.echo(f"No nodes inactive for >{months} months.")
        return

    click.echo(f"=== Temporal Gaps (>{months} months inactive) ===\n")
    for gap in temporal_gaps[:limit]:
        click.echo(f"  {gap.node_name}")
        click.echo(f"    Type: {gap.node_type}")
        click.echo(f"    {gap.description}")
        click.echo()

    if len(temporal_gaps) > limit:
        click.echo(f"  ... and {len(temporal_gaps) - limit} more")


@gaps.command("agents")
@click.option("--generate-specs", is_flag=True, help="Generate agent request specs")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def gaps_agents(ctx, generate_specs, as_json):
    """Show agent coverage matrix and generate agent requests.

    Displays which node types each agent can cover and identifies
    blind spots where new agent capabilities are needed.

    \b
    Examples:
        fgip gaps agents              # Coverage matrix
        fgip gaps agents --generate-specs  # Generate agent request specs
    """
    db = get_db(ctx.obj["db_path"])
    detector = GapDetector(db)

    if generate_specs:
        requests = detector.generate_agent_requests()

        if as_json:
            import json
            output = [
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
            ]
            click.echo(json.dumps(output, indent=2))
        else:
            click.echo("=== Agent Requests (auto-generated) ===\n")
            for req in requests:
                click.echo(f"[PRIORITY {req.priority}] {req.request_id}")
                click.echo(f"  Gap: {req.description}")
                click.echo(f"  Would fill: {req.gap_type}")
                click.echo(f"  API: {req.suggested_api}")
                click.echo(f"  Estimated new edges: {req.estimated_edges}")
                click.echo()

    else:
        matrix = detector.get_agent_coverage_matrix()

        if as_json:
            import json
            click.echo(json.dumps(matrix, indent=2))
        else:
            click.echo("=== Agent Coverage Matrix ===\n")
            for node_type, data in sorted(matrix.items()):
                coverage_pct = data["coverage_rate"] * 100
                status = "✓" if coverage_pct == 100 else ("○" if coverage_pct > 50 else "✗")

                click.echo(f"[{status}] {node_type}")
                click.echo(f"    Nodes: {data['covered_nodes']}/{data['total_nodes']} ({coverage_pct:.0f}%)")
                click.echo(f"    Agents: {', '.join(data['expected_agents']) or 'none'}")
                click.echo(f"    Gaps: {data['gaps']}")
                click.echo()


# ============ Health Command ============

@cli.command()
@click.pass_context
def health(ctx):
    """System health overview: verification + gaps + stats.

    Combines easter egg verification, gap analysis, and basic stats
    into a single health check.

    \b
    Examples:
        fgip health
    """
    db = get_db(ctx.obj["db_path"])
    conn = db.connect()

    click.echo("=== FGIP System Health Check ===\n")

    # Basic stats
    nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    sources = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
    claims = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]

    click.echo("--- Graph Stats ---")
    click.echo(f"  Nodes:   {nodes}")
    click.echo(f"  Edges:   {edges}")
    click.echo(f"  Sources: {sources}")
    click.echo(f"  Claims:  {claims}")
    click.echo()

    # Easter egg verification
    click.echo("--- Easter Egg Verification ---")
    report = run_verification(conn)
    pct = (report.eggs_found / report.eggs_total * 100) if report.eggs_total > 0 else 0
    health_icon = {"healthy": "✓", "degraded": "⚠", "broken": "✗"}.get(report.pipeline_health, "?")
    click.echo(f"  [{health_icon}] Pipeline: {report.pipeline_health.upper()}")
    click.echo(f"  Easter Eggs: {report.eggs_found}/{report.eggs_total} ({pct:.0f}%)")
    if report.eggs_missing:
        click.echo(f"  Missing: {', '.join(report.eggs_missing[:5])}")
    click.echo()

    # Gap analysis summary
    click.echo("--- Gap Analysis ---")
    detector = GapDetector(db)
    gap_report = detector.generate_report()
    click.echo(f"  Total Gaps: {len(gap_report.gaps)}")
    for gap_type, count in sorted(gap_report.gap_by_type.items(), key=lambda x: -x[1])[:5]:
        click.echo(f"    {gap_type}: {count}")
    click.echo()

    # Coverage stats
    stats = gap_report.coverage_stats
    click.echo("--- Coverage ---")
    click.echo(f"  Connectivity: {stats['connectivity_rate']:.1%}")
    click.echo(f"  Evidence rate: {stats['evidence_rate']:.1%}")
    click.echo(f"  Orphan nodes: {stats['orphan_nodes']}")
    click.echo()

    # Overall health assessment
    click.echo("--- Overall Assessment ---")
    issues = []
    if report.pipeline_health == "broken":
        issues.append("Pipeline broken (easter eggs failing)")
    elif report.pipeline_health == "degraded":
        issues.append("Pipeline degraded (some easter eggs missing)")
    if stats["orphan_nodes"] > nodes * 0.2:
        issues.append(f"High orphan rate ({stats['orphan_nodes']} nodes)")
    if stats["evidence_rate"] < 0.5:
        issues.append(f"Low evidence rate ({stats['evidence_rate']:.0%})")

    if not issues:
        click.echo("  [✓] System healthy")
    else:
        for issue in issues:
            click.echo(f"  [!] {issue}")


def main():
    cli(obj={})


if __name__ == "__main__":
    main()
