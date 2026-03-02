#!/usr/bin/env python3
"""Generalized bill section extractor for FGIP.

Extracts sections from GovInfo/US Code HTML sources.

Usage:
    python3 tools/extract_section.py --url <URL> --start <regex> --end <regex> --output <path>

Examples:
    # S.394 Introduced (Section 4a)
    python3 tools/extract_section.py \
        --url "https://www.govinfo.gov/content/pkg/BILLS-119s394is/html/BILLS-119s394is.htm" \
        --start "SEC.*4.*REQUIREMENTS.*ISSUING.*PAYMENT.*STABLECOINS" \
        --end "\(b\).*State-Level.*Regulatory" \
        --output docs/genius_s394_section_4a.txt

    # Enacted (12 USC 5903)
    python3 tools/extract_section.py \
        --url "https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title12-section5903&edition=prelim" \
        --start "§.*5903.*Requirements.*issuing.*payment.*stablecoins" \
        --end "\(b\).*State" \
        --output docs/genius_enacted_5903_4a.txt
"""

import argparse
import hashlib
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def fetch_url(url: str) -> str:
    """Fetch URL with proper headers."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "FGIP Research Agent (verification@fgip.local)",
            "Accept": "text/html, application/xhtml+xml, */*",
        }
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", errors="ignore")


def clean_html(html: str) -> str:
    """Strip HTML tags and normalize whitespace."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&#\d+;", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    return text


def extract_section(text: str, start_pattern: str, end_pattern: str) -> str:
    """Extract section between start and end patterns."""
    m_start = re.search(start_pattern, text, flags=re.IGNORECASE)
    if not m_start:
        raise ValueError(f"Start pattern not found: {start_pattern}")

    after_start = text[m_start.start():]

    # Look for (a) Standards header
    m_a = re.search(r"\(a\)\s*Standards", after_start, flags=re.IGNORECASE)
    if m_a:
        after_start = after_start[m_a.start():]

    m_end = re.search(end_pattern, after_start, flags=re.IGNORECASE)
    if not m_end:
        # If end not found, take first 15000 chars
        return after_start[:15000].strip()

    return after_start[:m_end.start()].strip()


def normalize_reserve_list(text: str) -> list:
    """Extract and normalize the reserve asset list for comparison."""
    reserves = []

    # Look for enumerated items (i), (ii), (iii), etc.
    pattern = r'\((?:i{1,3}|iv|v|vi{1,3}|viii?|ix|x)\)\s*([^(]+?)(?=\((?:i{1,3}|iv|v|vi{1,3}|viii?|ix|x|[A-Z])\)|$)'
    matches = re.findall(pattern, text, flags=re.IGNORECASE | re.DOTALL)

    for match in matches:
        # Clean up the text
        clean = re.sub(r'\s+', ' ', match).strip()
        clean = re.sub(r';$', '', clean).strip()
        if len(clean) > 10:  # Filter out noise
            reserves.append(clean)

    return reserves


def main():
    parser = argparse.ArgumentParser(description="Extract bill sections for FGIP")
    parser.add_argument("--url", required=True, help="Source URL")
    parser.add_argument("--start", required=True, help="Start pattern (regex)")
    parser.add_argument("--end", required=True, help="End pattern (regex)")
    parser.add_argument("--output", required=True, help="Output file path")
    parser.add_argument("--version", default="unknown", help="Version identifier (e.g., s394_is, enacted)")
    args = parser.parse_args()

    print(f"Fetching: {args.url}")
    html = fetch_url(args.url)
    print(f"Fetched {len(html)} bytes")

    text = clean_html(html)
    print(f"Cleaned to {len(text)} chars")

    try:
        section = extract_section(text, args.start, args.end)
    except ValueError as e:
        print(f"ERROR: {e}")
        print("First 3000 chars of cleaned text:")
        print(text[:3000])
        raise SystemExit(1)

    # Compute hash
    content_hash = hashlib.sha256(section.encode()).hexdigest()[:16]

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# GENIUS Act Section 4(a) - {args.version}\n")
        f.write(f"# SOURCE: {args.url}\n")
        f.write(f"# TIER: 0 (Official Government Source)\n")
        f.write(f"# EXTRACTED: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"# HASH: {content_hash}\n")
        f.write(f"# LENGTH: {len(section)} chars\n")
        f.write(f"\n{'='*70}\n\n")
        f.write(section + "\n")

    print(f"SUCCESS: Wrote {output_path} ({len(section)} chars)")
    print(f"Hash: {content_hash}")

    # Extract and print reserve list
    reserves = normalize_reserve_list(section)
    if reserves:
        print(f"\n{'='*60}")
        print("RESERVE ASSETS ENUMERATED:")
        print("="*60)
        for i, r in enumerate(reserves, 1):
            print(f"  ({i}) {r[:80]}{'...' if len(r) > 80 else ''}")


if __name__ == "__main__":
    main()
