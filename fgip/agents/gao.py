"""FGIP GAO Agent - GAO/Agency PDF Watcher.

Monitors gao.gov, state.gov, and other government agency reports.
PDF text extraction for topic keywords.
Proposes claims citing government reports.

Tier 0 agent - uses official government sources.

Safety rules:
- Uses official government websites only
- Stores only public documents
- Respects rate limits
- Artifacts saved locally with SHA256 hash
"""

import hashlib
import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any
import urllib.request
import urllib.error

from .base import FGIPAgent, Artifact, StructuredFact, ProposedClaim, ProposedEdge


# Government agency report sources
GAO_REPORTS_URL = "https://www.gao.gov/reports-testimonies"
GAO_SEARCH_URL = "https://www.gao.gov/search"
STATE_DEPT_URL = "https://www.state.gov/reports/"
TREASURY_URL = "https://home.treasury.gov/policy-issues/"
CRS_REPORTS_URL = "https://crsreports.congress.gov"

USER_AGENT = "FGIP Research Agent (contact@example.com)"

# Topics we're interested in
TRACKED_TOPICS = [
    "china", "trade", "tariff", "fentanyl", "supply chain",
    "manufacturing", "semiconductor", "national security",
    "foreign investment", "cfius", "sanctions",
]


class GAOAgent(FGIPAgent):
    """GAO/Agency PDF watcher agent.

    Monitors government reports for:
    - GAO reports and testimonies
    - State Department reports
    - Congressional Research Service reports

    Proposes claims from government findings.
    """

    def __init__(self, db, artifact_dir: str = "data/artifacts/gao"):
        super().__init__(
            db=db,
            name="gao",
            description="GAO/Agency PDF watcher - government reports"
        )
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self._rate_limit_delay = 2.0  # 2 seconds between requests
        self._last_request_time = 0

    def _rate_limit(self):
        """Enforce rate limiting."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._rate_limit_delay:
            time.sleep(self._rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    def _fetch_url(self, url: str) -> Optional[bytes]:
        """Fetch URL with proper headers and rate limiting."""
        self._rate_limit()

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html, application/pdf, */*",
            }
        )

        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError:
            return None
        except Exception:
            return None

    def _get_tracked_topics(self) -> List[str]:
        """Get topics from database claims or use defaults."""
        conn = self.db.connect()
        rows = conn.execute(
            "SELECT DISTINCT topic FROM claims LIMIT 50"
        ).fetchall()

        topics = [row["topic"].lower() for row in rows if row["topic"]]
        topics.extend(TRACKED_TOPICS)
        return list(set(topics))

    def _fetch_gao_reports_page(self) -> Optional[str]:
        """Fetch GAO reports listing page."""
        content = self._fetch_url(GAO_REPORTS_URL)
        if content:
            return content.decode("utf-8", errors="ignore")
        return None

    def _extract_gao_report_links(self, html: str) -> List[Dict[str, str]]:
        """Extract report links from GAO page."""
        reports = []

        # Look for report links
        # GAO URLs typically like: /products/gao-24-123
        pattern = re.compile(
            r'<a[^>]+href="(/products/gao-\d+-\d+)"[^>]*>([^<]+)</a>',
            re.IGNORECASE
        )

        for match in pattern.finditer(html):
            path = match.group(1)
            title = match.group(2).strip()

            # Filter by tracked topics
            title_lower = title.lower()
            for topic in TRACKED_TOPICS:
                if topic in title_lower:
                    reports.append({
                        "url": f"https://www.gao.gov{path}",
                        "title": title,
                        "matched_topic": topic,
                    })
                    break

        return reports[:20]  # Limit results

    def _fetch_pdf_content(self, url: str) -> Optional[bytes]:
        """Fetch PDF content."""
        return self._fetch_url(url)

    def _extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extract text from PDF using basic method.

        Note: In production, use PyPDF2, pdfplumber, or similar library.
        This is a basic extraction that looks for readable text.
        """
        try:
            with open(pdf_path, "rb") as f:
                content = f.read()

            # Basic text extraction - look for text streams
            # This is simplified; real implementation would use a PDF library
            text_parts = []

            # Find text between stream/endstream
            stream_pattern = re.compile(rb'stream\r?\n(.+?)\r?\nendstream', re.DOTALL)
            for match in stream_pattern.finditer(content):
                chunk = match.group(1)
                # Try to decode as text
                try:
                    decoded = chunk.decode("utf-8", errors="ignore")
                    # Filter to printable ASCII
                    printable = "".join(c for c in decoded if c.isprintable() or c.isspace())
                    if len(printable) > 50:
                        text_parts.append(printable)
                except Exception:
                    pass

            return "\n".join(text_parts)[:100000]  # Limit text length

        except Exception:
            return ""

    def collect(self) -> List[Artifact]:
        """Fetch government report documents."""
        artifacts = []

        # Fetch GAO reports page
        gao_html = self._fetch_gao_reports_page()
        if gao_html:
            # Save the index page
            content_hash = hashlib.sha256(gao_html.encode()).hexdigest()
            local_path = self.artifact_dir / "gao_reports_index.html"

            with open(local_path, "w", encoding="utf-8") as f:
                f.write(gao_html)

            artifacts.append(Artifact(
                url=GAO_REPORTS_URL,
                artifact_type="html",
                local_path=str(local_path),
                content_hash=content_hash,
                metadata={
                    "doc_type": "gao_index",
                    "source": "gao",
                }
            ))

            # Extract and fetch individual reports
            reports = self._extract_gao_report_links(gao_html)

            for report in reports[:5]:  # Limit per run
                report_page = self._fetch_url(report["url"])
                if not report_page:
                    continue

                report_html = report_page.decode("utf-8", errors="ignore")

                # Look for PDF link in report page
                pdf_pattern = re.compile(r'href="([^"]+\.pdf)"', re.IGNORECASE)
                pdf_match = pdf_pattern.search(report_html)

                if pdf_match:
                    pdf_url = pdf_match.group(1)
                    if not pdf_url.startswith("http"):
                        pdf_url = f"https://www.gao.gov{pdf_url}"

                    pdf_content = self._fetch_pdf_content(pdf_url)
                    if pdf_content:
                        pdf_hash = hashlib.sha256(pdf_content).hexdigest()
                        pdf_filename = pdf_url.split("/")[-1]
                        pdf_path = self.artifact_dir / pdf_filename

                        with open(pdf_path, "wb") as f:
                            f.write(pdf_content)

                        artifacts.append(Artifact(
                            url=pdf_url,
                            artifact_type="pdf",
                            local_path=str(pdf_path),
                            content_hash=pdf_hash,
                            metadata={
                                "doc_type": "gao_report",
                                "title": report["title"],
                                "matched_topic": report["matched_topic"],
                                "source": "gao",
                                "report_page": report["url"],
                            }
                        ))
                else:
                    # Save HTML version
                    html_hash = hashlib.sha256(report_html.encode()).hexdigest()
                    report_id = report["url"].split("/")[-1]
                    html_path = self.artifact_dir / f"{report_id}.html"

                    with open(html_path, "w", encoding="utf-8") as f:
                        f.write(report_html)

                    artifacts.append(Artifact(
                        url=report["url"],
                        artifact_type="html",
                        local_path=str(html_path),
                        content_hash=html_hash,
                        metadata={
                            "doc_type": "gao_report",
                            "title": report["title"],
                            "matched_topic": report["matched_topic"],
                            "source": "gao",
                        }
                    ))

        return artifacts

    def extract(self, artifacts: List[Artifact]) -> List[StructuredFact]:
        """Extract facts from government reports."""
        facts = []

        for artifact in artifacts:
            doc_type = artifact.metadata.get("doc_type")

            if doc_type == "gao_index":
                continue  # Skip index pages

            if doc_type == "gao_report":
                facts.extend(self._extract_gao_report_facts(artifact))

        return facts

    def _extract_gao_report_facts(self, artifact: Artifact) -> List[StructuredFact]:
        """Extract facts from a GAO report."""
        facts = []

        if not artifact.local_path:
            return facts

        # Get content
        if artifact.artifact_type == "pdf":
            content = self._extract_text_from_pdf(artifact.local_path)
        else:
            try:
                with open(artifact.local_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                return facts

        if not content or len(content) < 100:
            return facts

        title = artifact.metadata.get("title", "GAO Report")
        topic = artifact.metadata.get("matched_topic", "government")

        # Extract key findings patterns
        finding_patterns = [
            # "GAO found that..."
            (r"GAO\s+found\s+that\s+([^\.]+\.)", "finding"),
            # "We found..."
            (r"We\s+found\s+(?:that\s+)?([^\.]+\.)", "finding"),
            # "The report concludes..."
            (r"(?:report|study)\s+concludes\s+(?:that\s+)?([^\.]+\.)", "conclusion"),
            # Dollar amounts
            (r"\$(\d+(?:\.\d+)?)\s*(billion|million|trillion)", "financial"),
            # Recommendations
            (r"recommend(?:s|ation)?\s+(?:that\s+)?([^\.]+\.)", "recommendation"),
        ]

        content_lower = content.lower()

        for pattern, fact_type in finding_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches[:5]:  # Limit matches per pattern
                if isinstance(match, tuple):
                    text = " ".join(match)
                else:
                    text = match

                text = text.strip()[:500]  # Limit text length

                if len(text) < 20:
                    continue

                facts.append(StructuredFact(
                    fact_type=f"gao_{fact_type}",
                    subject="GAO",
                    predicate="REPORTS",
                    object=text,
                    source_artifact=artifact,
                    confidence=0.85,
                    raw_text=text,
                    metadata={
                        "report_title": title,
                        "topic": topic,
                        "finding_type": fact_type,
                    }
                ))

        # Extract entity mentions
        tracked_orgs = self._get_tracked_organizations()
        for org in tracked_orgs:
            org_name = org["name"]
            if org_name.lower() in content_lower:
                # Find context around mention
                idx = content_lower.find(org_name.lower())
                context_start = max(0, idx - 100)
                context_end = min(len(content), idx + len(org_name) + 200)
                context = content[context_start:context_end].strip()

                facts.append(StructuredFact(
                    fact_type="entity_mention",
                    subject=org_name,
                    predicate="MENTIONED_IN",
                    object=title,
                    source_artifact=artifact,
                    confidence=0.7,
                    raw_text=context,
                    metadata={
                        "org_node_id": org["node_id"],
                        "topic": topic,
                    }
                ))

        return facts

    def _get_tracked_organizations(self) -> List[Dict[str, Any]]:
        """Get organizations from nodes table."""
        conn = self.db.connect()
        rows = conn.execute(
            """SELECT node_id, name FROM nodes
               WHERE node_type IN ('ORGANIZATION', 'COMPANY')
               LIMIT 100"""
        ).fetchall()

        return [{"node_id": row["node_id"], "name": row["name"]} for row in rows]

    def propose(self, facts: List[StructuredFact]) -> tuple[List[ProposedClaim], List[ProposedEdge]]:
        """Generate HYPOTHESIS claims from extracted facts."""
        claims = []
        edges = []

        for fact in facts:
            proposal_id = self._generate_proposal_id()

            # Create claim based on fact type
            if fact.fact_type in ("gao_finding", "gao_conclusion"):
                claim_text = f"GAO report states: {fact.object[:200]}"
            elif fact.fact_type == "gao_recommendation":
                claim_text = f"GAO recommends: {fact.object[:200]}"
            elif fact.fact_type == "gao_financial":
                claim_text = f"GAO reports financial finding: ${fact.object}"
            elif fact.fact_type == "entity_mention":
                claim_text = f"{fact.subject} is mentioned in GAO report '{fact.object}'"
            else:
                claim_text = f"GAO: {fact.subject} {fact.predicate} {fact.object}"

            claim = ProposedClaim(
                proposal_id=proposal_id,
                claim_text=claim_text,
                topic=fact.metadata.get("topic", "GAO").upper(),
                agent_name=self.name,
                source_url=fact.source_artifact.url,
                artifact_path=fact.source_artifact.local_path,
                artifact_hash=fact.source_artifact.content_hash,
                reasoning=f"Extracted from GAO report: {fact.metadata.get('report_title', 'Unknown')}",
                promotion_requirement="Verify text exists in original GAO report PDF at gao.gov",
            )
            claims.append(claim)

            # Create edge for entity mentions
            if fact.fact_type == "entity_mention" and fact.metadata.get("org_node_id"):
                edge_proposal_id = self._generate_proposal_id()

                edge = ProposedEdge(
                    proposal_id=edge_proposal_id,
                    from_node="gao",
                    to_node=fact.metadata["org_node_id"],
                    relationship="REPORTS_ON",
                    agent_name=self.name,
                    detail=f"GAO report mentions {fact.subject}",
                    proposed_claim_id=proposal_id,
                    confidence=fact.confidence,
                    reasoning=f"Entity mentioned in GAO report '{fact.object}'",
                    promotion_requirement="Verify entity is substantively discussed (not just mentioned)",
                )
                edges.append(edge)

        return claims, edges
