#!/usr/bin/env python3
"""Extract GENIUS Act Section 4(a) from GovInfo.

Fetches the official GPO/GovInfo HTML for S.394 and extracts
Section 4(a) "Standards for the Issuance of Payment Stablecoins"
for use as Tier-0 evidence in FGIP.

Usage:
    python3 tools/extract_genius_4a.py [output_path]

Default output: docs/genius_s394_section_4a.txt
"""

import re
import sys
import textwrap
import urllib.request
import urllib.error

URL = "https://www.govinfo.gov/content/pkg/BILLS-119s394is/html/BILLS-119s394is.htm"

START_PAT = r"SEC\.\s*4\.\s*REQUIREMENTS\s+FOR\s+ISSUING\s+PAYMENT\s+STABLECOINS\."
END_PAT = r"\(b\)\s*State-Level\s+Regulatory\s+Regimes\.\s*--"


def fetch_url(url: str) -> str:
    """Fetch URL with proper headers."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "FGIP Research Agent (verification@fgip.local)",
            "Accept": "text/html, */*",
        }
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="ignore")


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "docs/genius_s394_section_4a.txt"

    print(f"Fetching: {URL}")
    html = fetch_url(URL)
    print(f"Fetched {len(html)} bytes")

    # GovInfo HTML is mostly plain text with tags; strip tags
    text = re.sub(r"<[^>]+>", "", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    m_start = re.search(START_PAT, text, flags=re.IGNORECASE)
    if not m_start:
        print("ERROR: Start pattern not found. GovInfo markup may have changed.")
        print("Dumping first 5000 chars of cleaned text for debugging:")
        print(text[:5000])
        raise SystemExit(1)

    # Find the "(a) Standards..." section and extract 4(a) until 4(b)
    after_sec4 = text[m_start.start():]
    m_a = re.search(
        r"\(a\)\s*Standards\s+for\s+the\s+Issuance\s+of\s+Payment\s+Stablecoins\.\s*--",
        after_sec4,
        flags=re.IGNORECASE
    )
    if not m_a:
        print("ERROR: (a) header not found after SEC.4.")
        print("Text after SEC.4 (first 2000 chars):")
        print(after_sec4[:2000])
        raise SystemExit(1)

    after_a = after_sec4[m_a.start():]
    m_end = re.search(END_PAT, after_a, flags=re.IGNORECASE)
    if not m_end:
        print("ERROR: End pattern '(b) State-Level Regulatory Regimes' not found.")
        print("Text after (a) (first 3000 chars):")
        print(after_a[:3000])
        raise SystemExit(1)

    section_4a = after_a[:m_end.start()].strip()

    # Light cleanup
    section_4a = textwrap.dedent(section_4a)
    section_4a = re.sub(r"[ \t]+", " ", section_4a)
    section_4a = re.sub(r"\n ?", "\n", section_4a)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# GENIUS Act S.394 Section 4(a) - Extracted Text\n")
        f.write(f"# SOURCE: {URL}\n")
        f.write(f"# TIER: 0 (Official GPO/GovInfo)\n")
        f.write(f"# EXTRACTED: {__import__('datetime').datetime.utcnow().isoformat()}Z\n")
        f.write(f"# LENGTH: {len(section_4a)} chars\n")
        f.write(f"\n{'='*70}\n\n")
        f.write(section_4a + "\n")

    print(f"SUCCESS: Wrote {out_path} ({len(section_4a)} chars)")

    # Print summary of key provisions found
    print("\n" + "="*60)
    print("KEY PROVISIONS DETECTED:")
    print("="*60)

    if "1-to-1" in section_4a.lower() or "one-to-one" in section_4a.lower():
        print("✓ 1:1 reserve requirement found")

    if "93 day" in section_4a or "93-day" in section_4a:
        print("✓ Short-term Treasury requirement (≤93 days) found")

    if "rehypothecate" in section_4a.lower() or "pledge" in section_4a.lower():
        print("✓ Rehypothecation provisions found")

    if "monthly" in section_4a.lower():
        print("✓ Monthly reporting requirement found")

    if "accounting firm" in section_4a.lower() or "registered public" in section_4a.lower():
        print("✓ Accounting firm examination requirement found")

    if "ceo" in section_4a.lower() or "chief executive" in section_4a.lower():
        print("✓ CEO/CFO certification requirement found")


if __name__ == "__main__":
    main()
