"""
FGIP Loader - Parse source URLs and citation database into the claims-first schema.

Build order:
1. Load all source URLs from fgip_all_source_urls.txt
2. Parse claims from fgip_citation_database.md
3. Link claims to sources via claim_sources
"""

import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional

from schema import source_id_from_url, get_domain, get_tier


def load_source_urls(conn: sqlite3.Connection, urls_file: Path) -> int:
    """
    Load all source URLs from the text file.

    Returns number of sources loaded.
    """
    cursor = conn.cursor()
    loaded = 0

    with open(urls_file) as f:
        for line in f:
            url = line.strip()
            if not url or url.startswith('#'):
                continue

            source_id = source_id_from_url(url)
            domain = get_domain(url)
            tier = get_tier(url)

            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO sources (source_id, url, domain, tier, retrieved_at)
                    VALUES (?, ?, ?, ?, datetime('now'))
                """, (source_id, url, domain, tier))
                if cursor.rowcount > 0:
                    loaded += 1
            except sqlite3.IntegrityError:
                pass  # URL already exists

    conn.commit()
    return loaded


def parse_citation_database(conn: sqlite3.Connection, md_file: Path) -> Tuple[int, int]:
    """
    Parse claims from the citation database markdown file.

    Returns (claims_loaded, claim_source_links_created).
    """
    cursor = conn.cursor()

    # Get next claim number
    cursor.execute("SELECT MAX(CAST(SUBSTR(claim_id, 6) AS INTEGER)) FROM claims")
    row = cursor.fetchone()
    next_num = (row[0] or 0) + 1

    content = md_file.read_text()

    # Topic mapping from section headers
    topic_map = {
        'I': 'Lobbying',
        'II': 'Judicial',
        'III': 'Ownership',
        'IV': 'Downstream',
        'V': 'Censorship',
        'VI': 'Reshoring',
        'VII': 'ThinkTank',
        'VIII': 'IndependentMedia',
        'IX': 'Fraud',
        'X': 'Stablecoin',
        'XI': 'ForeignPolicy',
    }

    claims_loaded = 0
    links_created = 0
    current_topic = 'General'

    # Split into lines
    lines = content.split('\n')
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        # Detect section headers like "# I. LOBBYING NETWORK"
        section_match = re.match(r'^#\s+(I+|IV|V|VI+|IX|X|XI)\.?\s+', line)
        if section_match:
            roman = section_match.group(1)
            current_topic = topic_map.get(roman, 'General')
            i += 1
            continue

        # Detect table rows: | Claim | Source |
        if line.startswith('|') and '|' in line[1:]:
            parts = [p.strip() for p in line.split('|')]
            parts = [p for p in parts if p]  # Remove empty parts

            # Skip header rows
            if len(parts) >= 2 and parts[0].lower() in ['claim', 'company', 'event', 'entity', 'from']:
                i += 1
                continue

            # Skip separator rows
            if len(parts) >= 1 and all(c in '-|:' for c in parts[0]):
                i += 1
                continue

            # Parse claim row
            if len(parts) >= 2:
                claim_text = parts[0]
                source_text = parts[-1]  # Last column is source

                # Handle 3-column tables (Company | Claim | Source)
                if len(parts) >= 3:
                    # Check if first column looks like a company name
                    if not any(c in parts[0].lower() for c in ['%', '$', 'billion', 'million', 'passed', 'signed']):
                        claim_text = f"{parts[0]}: {parts[1]}"
                        source_text = parts[-1]

                # Generate claim_id
                claim_id = f"FGIP-{next_num:06d}"
                next_num += 1

                # Determine status
                # MISSING if no URL in source text
                # PARTIAL if has URL
                urls = extract_urls(source_text)
                status = 'PARTIAL' if urls else 'MISSING'

                # Determine required_tier based on claim content
                required_tier = determine_required_tier(claim_text)

                # Insert claim
                try:
                    cursor.execute("""
                        INSERT INTO claims (claim_id, claim_text, topic, status, required_tier)
                        VALUES (?, ?, ?, ?, ?)
                    """, (claim_id, claim_text, current_topic, status, required_tier))
                    claims_loaded += 1

                    # Link to sources
                    for url in urls:
                        source_id = source_id_from_url(url)

                        # Ensure source exists
                        cursor.execute("""
                            INSERT OR IGNORE INTO sources (source_id, url, domain, tier, retrieved_at)
                            VALUES (?, ?, ?, ?, datetime('now'))
                        """, (source_id, url, get_domain(url), get_tier(url)))

                        # Create link
                        cursor.execute("""
                            INSERT OR IGNORE INTO claim_sources (claim_id, source_id)
                            VALUES (?, ?)
                        """, (claim_id, source_id))
                        links_created += 1

                except sqlite3.IntegrityError as e:
                    print(f"Error inserting claim: {e}")

        i += 1

    conn.commit()
    return claims_loaded, links_created


def extract_urls(text: str) -> List[str]:
    """Extract all URLs from text."""
    # Match http/https URLs
    url_pattern = r'https?://[^\s<>"\')\]]+[^\s<>"\')\],.]'
    urls = re.findall(url_pattern, text)

    # Clean up URLs (remove trailing punctuation that might have been caught)
    cleaned = []
    for url in urls:
        # Remove trailing punctuation
        while url and url[-1] in '.,;:)]':
            url = url[:-1]
        if url:
            cleaned.append(url)

    return cleaned


def determine_required_tier(claim_text: str) -> int:
    """
    Determine required source tier based on claim content.

    Tier 0 required for:
    - Ownership percentages
    - Dollar amounts (lobbying spend, fines)
    - Legislative outcomes
    - Court rulings

    Tier 1 required for:
    - Market performance claims

    Tier 2 acceptable for:
    - Interpretive/analytical claims
    """
    text_lower = claim_text.lower()

    # Tier 0 indicators
    tier_0_patterns = [
        r'\d+\.?\d*\s*%',  # Percentages
        r'\$[\d,]+[mb]?',  # Dollar amounts
        r'owns?\s+\d+',  # Ownership claims
        r'(passed|signed|enacted|ruled|decided)',  # Legislative/judicial
        r'(congress|senate|house|supreme court)',  # Government bodies
        r'(sec\s+fil|13f|edgar)',  # SEC filings
        r'(foia|gao|audit)',  # Government documents
    ]

    for pattern in tier_0_patterns:
        if re.search(pattern, text_lower):
            return 0

    # Tier 1 indicators
    tier_1_patterns = [
        r'\+\d+%\s+(ytd|yoy)',  # Market performance
        r'(backlog|revenue|earnings)',  # Financial claims
        r'(jobs? (lost|created|added))',  # Employment claims
    ]

    for pattern in tier_1_patterns:
        if re.search(pattern, text_lower):
            return 1

    # Default to Tier 2
    return 2


def load_all(conn: sqlite3.Connection, urls_file: Path, citation_file: Path) -> dict:
    """
    Load everything: sources, claims, and links.

    Returns summary dict.
    """
    print("Loading source URLs...")
    sources_loaded = load_source_urls(conn, urls_file)
    print(f"  Loaded {sources_loaded} sources")

    print("Parsing citation database...")
    claims_loaded, links_created = parse_citation_database(conn, citation_file)
    print(f"  Loaded {claims_loaded} claims")
    print(f"  Created {links_created} claim-source links")

    # Get stats
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM sources")
    total_sources = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM claims")
    total_claims = cursor.fetchone()[0]

    cursor.execute("SELECT status, COUNT(*) FROM claims GROUP BY status")
    status_counts = dict(cursor.fetchall())

    cursor.execute("SELECT tier, COUNT(*) FROM sources GROUP BY tier")
    tier_counts = dict(cursor.fetchall())

    return {
        'sources_loaded': sources_loaded,
        'claims_loaded': claims_loaded,
        'links_created': links_created,
        'total_sources': total_sources,
        'total_claims': total_claims,
        'claims_by_status': status_counts,
        'sources_by_tier': tier_counts,
    }


if __name__ == '__main__':
    from schema import init_db

    db_path = 'fgip.db'
    urls_file = Path('/home/voidstr3m33/fgip_all_source_urls.txt')
    citation_file = Path('/home/voidstr3m33/fgip_citation_database.md')

    print(f"Initializing database: {db_path}")
    conn = init_db(db_path)

    result = load_all(conn, urls_file, citation_file)

    print("\n=== Load Summary ===")
    print(f"Total sources: {result['total_sources']}")
    print(f"  By tier: {result['sources_by_tier']}")
    print(f"Total claims: {result['total_claims']}")
    print(f"  By status: {result['claims_by_status']}")

    conn.close()
