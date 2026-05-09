#!/usr/bin/env python3
"""Populate FGIP graph with digital asset rails layer.

Adds nodes and edges for:
- GENIUS Act and stablecoin regulatory framework
- OCC, FDIC, Fed, SEC, Treasury regulatory nodes
- Payment stablecoin issuers and reserves
- Tokenized securities infrastructure
- Treasury market structure (primary dealers, auctions, foreign holders)
- Dollar resilience thesis edges

Usage:
    python3 tools/populate_digital_asset_rails.py
"""

import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "fgip.db"


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def upsert_node(conn, node_id, name, node_type, metadata=None):
    node_hash = sha256(f"{node_id}-{name}-{node_type}")
    meta_json = json.dumps(metadata) if metadata else "{}"
    ts = now_iso()
    conn.execute(
        """INSERT INTO nodes (node_id, name, node_type, metadata, sha256, created_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(node_id) DO UPDATE SET
               name = excluded.name,
               metadata = excluded.metadata,
               sha256 = excluded.sha256""",
        (node_id, name, node_type, meta_json, node_hash, ts),
    )


def upsert_edge(conn, from_id, to_id, edge_type, confidence=0.95, notes="", source="populate_digital_asset_rails"):
    edge_id = sha256(f"{from_id}-{to_id}-{edge_type}")[:16]
    edge_hash = sha256(f"{from_id}-{to_id}-{edge_type}-{confidence}-{notes}")
    ts = now_iso()
    conn.execute(
        """INSERT INTO edges (edge_id, from_node_id, to_node_id, edge_type, confidence, notes, source, sha256, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(edge_id) DO UPDATE SET
               confidence = excluded.confidence,
               notes = excluded.notes""",
        (edge_id, from_id, to_id, edge_type, confidence, notes, source, edge_hash, ts),
    )


def add_regulatory_nodes(conn):
    """Add regulatory bodies and legal framework nodes."""
    nodes = [
        ("genius-act", "GENIUS Act", "legislation", {"enacted": "2025-07-18", "description": "Permitted payment stablecoin issuer framework"}),
        ("occ", "Office of the Comptroller of the Currency", "regulator", {"jurisdiction": "national banks, federal savings associations"}),
        ("fdic", "Federal Deposit Insurance Corporation", "regulator", {"jurisdiction": "deposit insurance, bank supervision"}),
        ("federal-reserve", "Federal Reserve System", "regulator", {"note": "Federal agency accountable to Congress. Not owned by asset managers."}),
        ("sec", "Securities and Exchange Commission", "regulator", {"jurisdiction": "securities, exchanges, transfer agents"}),
        ("us-treasury", "U.S. Department of the Treasury", "government_agency", {"jurisdiction": "debt management, sanctions, AML"}),
        ("fincen", "Financial Crimes Enforcement Network", "regulator", {"jurisdiction": "AML/CFT, Bank Secrecy Act"}),
    ]
    for node_id, name, ntype, meta in nodes:
        upsert_node(conn, node_id, name, ntype, meta)
    print(f"  Added {len(nodes)} regulatory nodes")


def add_market_structure_nodes(conn):
    """Add Treasury market structure nodes."""
    nodes = [
        ("treasury-auctions", "Treasury Auctions", "market_mechanism", {"description": "Primary market for U.S. government debt"}),
        ("primary-dealers", "Primary Dealers", "market_participant", {"description": "Designated counterparties of NY Fed, bid in Treasury auctions"}),
        ("new-york-fed", "Federal Reserve Bank of New York", "central_bank", {"role": "Open market operations, monetary policy implementation"}),
        ("treasury-secondary-market", "Treasury Secondary Market", "market", {"description": "Secondary trading of U.S. Treasury securities"}),
        ("foreign-treasury-holders", "Foreign Treasury Holders", "market_participant", {"note": "Japan ~$1.239T, UK ~$897B, China ~$693B (Feb 2026)"}),
        ("us-dollar-reserve-status", "U.S. Dollar Reserve Currency Status", "concept", {}),
    ]
    for node_id, name, ntype, meta in nodes:
        upsert_node(conn, node_id, name, ntype, meta)
    print(f"  Added {len(nodes)} market structure nodes")


def add_stablecoin_nodes(conn):
    """Add stablecoin and digital asset rail nodes."""
    nodes = [
        ("permitted-payment-stablecoin-issuers", "Permitted Payment Stablecoin Issuers", "regulatory_category", {"framework": "GENIUS Act"}),
        ("stablecoin-reserves", "Stablecoin Reserves", "asset_class", {"composition": "cash, Treasury bills, repo"}),
        ("short-term-treasuries", "Short-Term Treasury Securities", "asset_class", {"includes": "T-bills, short-term T-notes"}),
        ("payment-stablecoins", "Payment Stablecoins", "asset_class", {"description": "Dollar-denominated blockchain settlement tokens"}),
        ("programmable-dollar-settlement", "Programmable Dollar Settlement", "infrastructure", {}),
        ("legacy-bank-settlement", "Legacy Bank Settlement", "infrastructure", {"includes": "ACH, wire, card networks"}),
        ("banking-system", "Banking System", "infrastructure", {"role": "Reserves, custody, redemption, compliance"}),
        ("aml-sanctions-compliance", "AML/Sanctions Compliance", "regulatory_requirement", {"law": "Bank Secrecy Act"}),
        ("tokenized-securities", "Tokenized Securities", "asset_class", {"note": "SEC: remain securities under federal law"}),
        ("tokenized-treasuries", "Tokenized Treasuries", "asset_class", {}),
        ("financial-stability-risk", "Financial Stability Risk", "risk", {"type": "run risk, convertibility risk"}),
    ]
    for node_id, name, ntype, meta in nodes:
        upsert_node(conn, node_id, name, ntype, meta)
    print(f"  Added {len(nodes)} stablecoin/digital asset nodes")


def add_company_nodes(conn):
    """Add companies in the digital asset rails space."""
    nodes = [
        ("dtcc", "DTCC", "company", {"role": "Market infrastructure, tokenization"}),
        ("bullish", "Bullish", "company", {"type": "crypto exchange"}),
        ("equiniti", "Equiniti", "company", {"type": "transfer agent", "clients": "~3,000 public companies"}),
        ("circle", "Circle", "company", {"product": "USDC stablecoin"}),
        ("paypal", "PayPal", "company", {"product": "PYUSD stablecoin", "ticker": "PYPL"}),
        ("coinbase", "Coinbase", "company", {"type": "exchange, custody", "ticker": "COIN"}),
    ]
    for node_id, name, ntype, meta in nodes:
        upsert_node(conn, node_id, name, ntype, meta)
    print(f"  Added {len(nodes)} company nodes")


def add_regulatory_edges(conn):
    """Add edges for GENIUS Act regulatory framework."""
    edges = [
        ("genius-act", "permitted-payment-stablecoin-issuers", "AUTHORIZES_FRAMEWORK_FOR", 1.0,
         "GENIUS Act creates permitted payment stablecoin issuer framework"),
        ("permitted-payment-stablecoin-issuers", "stablecoin-reserves", "REQUIRES_RESERVES", 1.0,
         "100% reserve backing with dollars, short-term Treasuries, or equivalent liquid assets"),
        ("stablecoin-reserves", "short-term-treasuries", "BACKED_BY", 0.90,
         "Reserve assets include cash, Treasury bills, repo secured by Treasuries"),
        ("stablecoin-reserves", "short-term-treasuries", "CREATES_DEMAND_FOR", 0.85,
         "Richmond Fed: stablecoin adoption raises demand for Treasuries"),
        ("genius-act", "us-dollar-reserve-status", "SUPPORTS_DEMAND_FOR", 0.90,
         "White House: Act intended to cement dollar reserve-currency status"),
        ("occ", "genius-act", "IMPLEMENTS", 0.95,
         "OCC proposed rulemaking for GENIUS Act implementation"),
        ("us-treasury", "permitted-payment-stablecoin-issuers", "REGULATES", 0.95,
         "Treasury/FinCEN AML/CFT rulemaking for PPSIs"),
        ("permitted-payment-stablecoin-issuers", "aml-sanctions-compliance", "SUBJECT_TO", 0.95,
         "PPSIs treated as financial institutions under BSA"),
        ("sec", "tokenized-securities", "REGULATES", 1.0,
         "SEC: tokenized securities remain securities under federal law"),
        ("fdic", "payment-stablecoins", "DOES_NOT_INSURE", 1.0,
         "Payment stablecoins NOT FDIC insured per GENIUS Act"),
    ]
    for from_id, to_id, etype, conf, note in edges:
        upsert_edge(conn, from_id, to_id, etype, conf, note)
    print(f"  Added {len(edges)} regulatory edges")


def add_market_structure_edges(conn):
    """Add edges for Treasury market structure."""
    edges = [
        ("us-treasury", "treasury-auctions", "ISSUES_DEBT", 1.0,
         "Treasury issues debt through auction process"),
        ("primary-dealers", "treasury-auctions", "BIDS_AT_AUCTION", 1.0,
         "Primary dealers are designated counterparties, expected to bid competitively"),
        ("new-york-fed", "treasury-secondary-market", "CONDUCTS_OPERATIONS", 1.0,
         "NY Fed buys/sells Treasuries for monetary policy implementation"),
        ("foreign-treasury-holders", "treasury-secondary-market", "HOLDS_AND_TRADES", 0.95,
         "Japan ~$1.239T, UK ~$897B, China ~$693B. Record aggregate highs Feb 2026"),
        ("foreign-treasury-holders", "treasury-secondary-market", "CAN_RAISE_YIELD_PRESSURE", 0.80,
         "Foreign selling is pressure vector, not instant kill switch"),
        ("federal-reserve", "congress", "ACCOUNTABLE_TO", 1.0,
         "Fed Board is federal agency accountable to Congress. Not privately owned."),
    ]
    for from_id, to_id, etype, conf, note in edges:
        upsert_edge(conn, from_id, to_id, etype, conf, note)
    print(f"  Added {len(edges)} market structure edges")


def add_settlement_rail_edges(conn):
    """Add edges for settlement rail dynamics."""
    edges = [
        ("payment-stablecoins", "programmable-dollar-settlement", "ENABLES", 0.85,
         "Stablecoins allow blockchain-based dollar transfer and settlement"),
        ("payment-stablecoins", "banking-system", "DEPENDS_ON", 0.90,
         "Redemption, reserves, and compliance still require banks"),
        ("payment-stablecoins", "legacy-bank-settlement", "PARTIALLY_BYPASSES", 0.75,
         "Faster than legacy ACH/wire timing but does not escape banking system"),
        ("payment-stablecoins", "financial-stability-risk", "EXPOSES_TO", 0.80,
         "BoE Governor Bailey warns of convertibility risk during stress"),
    ]
    for from_id, to_id, etype, conf, note in edges:
        upsert_edge(conn, from_id, to_id, etype, conf, note)
    print(f"  Added {len(edges)} settlement rail edges")


def add_tokenization_edges(conn):
    """Add edges for tokenized asset infrastructure."""
    edges = [
        ("dtcc", "tokenized-securities", "TOKENIZES", 0.85,
         "DTCC extending market infrastructure into digital assets"),
        ("bullish", "equiniti", "ACQUIRES", 0.90,
         "$4.2B acquisition. Transfer agent for ~3,000 public companies"),
        ("equiniti", "tokenized-securities", "SERVES_AS_TRANSFER_AGENT_FOR", 0.85,
         "Transfer agent infrastructure bridges public-company records to blockchain"),
    ]
    for from_id, to_id, etype, conf, note in edges:
        upsert_edge(conn, from_id, to_id, etype, conf, note)
    print(f"  Added {len(edges)} tokenization edges")


def main():
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}", file=sys.stderr)
        print("Run: python3 -m fgip.cli init", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))

    print("Populating digital asset rails layer...")
    add_regulatory_nodes(conn)
    add_market_structure_nodes(conn)
    add_stablecoin_nodes(conn)
    add_company_nodes(conn)
    add_regulatory_edges(conn)
    add_market_structure_edges(conn)
    add_settlement_rail_edges(conn)
    add_tokenization_edges(conn)

    conn.commit()

    # Count totals
    nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    print(f"\nGraph totals: {nodes} nodes, {edges} edges")

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
