"""Staging Prelint - Catch garbage proposals before human review.

Validates proposed claims, edges, and nodes against hygiene rules.
Prevents review fatigue by auto-rejecting obvious garbage.

Usage:
    from fgip.staging_prelint import prelint_edge, prelint_node, prelint_claim

    issues = prelint_edge(from_node, to_node, relationship, detail)
    if issues:
        # Auto-reject or flag for review
"""

import re
from typing import List, Optional, Tuple
from pathlib import Path
import yaml


# Load node aliases for canonical matching
def load_aliases() -> dict:
    """Load node aliases from config file."""
    alias_path = Path(__file__).parent.parent / "config" / "node_aliases.yaml"
    if alias_path.exists():
        with open(alias_path) as f:
            content = f.read()
            # Parse YAML, ignoring comments
            aliases = {}
            for line in content.split('\n'):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if ':' in line:
                    parts = line.split(':', 1)
                    if len(parts) == 2:
                        key = parts[0].strip().lower()
                        value = parts[1].strip()
                        if key and value:
                            aliases[key] = value
            return aliases
    return {}


ALIASES = load_aliases()


# Garbage patterns that indicate a malformed node_id
GARBAGE_NODE_PATTERNS = [
    # Contains dollar amounts
    (r'\$[\d,.]+[BMK]?', "Contains dollar amount"),

    # Contains date ranges
    (r'\(\d{4}[-–]\d{4}\)', "Contains date range in parentheses"),
    (r'\d{4}[-–]\d{4}', "Contains year range"),

    # Contains percentage ownership text
    (r'largest\s+shareholder', "Contains 'largest shareholder' text"),
    (r'\d+\.?\d*%', "Contains percentage"),
    (r'[\d,]+\s*shares', "Contains share count"),

    # Sentence fragments (too many words)
    (r'^\S+(\s+\S+){6,}$', "Looks like sentence fragment (7+ words)"),

    # Contains "and" suggesting multi-entity
    (r'\band\b.*\b(and|,)\b', "Multiple conjunctions (likely multi-entity)"),

    # Contains action verbs suggesting it's a description not entity
    (r'\b(spent|lobbied|filed|owns|was|became|led|caused)\b', "Contains verb (likely description, not entity)"),

    # Contains parenthetical that looks like description
    (r'\([^)]{20,}\)', "Long parenthetical (likely description)"),
]


# Patterns for detecting multi-entity (Franken-nodes)
MULTI_ENTITY_PATTERNS = [
    (r'^[A-Z][a-z]+\s+[A-Z]?[a-z]*\s+and\s+[A-Z][a-z]+', "Two proper names joined by 'and'"),
    (r',\s*and\s+', "Oxford comma multi-entity"),
    (r'\bet\s+al\.?', "Academic citation style"),
]


# Valid edge types (from schema)
VALID_EDGE_TYPES = {
    # Problem layer - capture/lobbying
    'LOBBIED_FOR', 'LOBBIED_AGAINST', 'FILED_AMICUS', 'OWNS_SHARES',
    'EMPLOYS', 'EMPLOYED', 'MARRIED_TO', 'DONATED_TO', 'APPOINTED_BY',
    'RULED_ON', 'OWNS_MEDIA', 'REPORTS_ON', 'MEMBER_OF', 'INVESTED_IN',
    'SUPPLIES', 'CAUSED', 'ENABLED', 'CONTRIBUTED_TO', 'FACILITATED',
    'PROFITED_FROM', 'COORDINATED_WITH', 'CORRECTS', 'OPPOSES_CORRECTION',
    'REGISTERED_AS_AGENT',
    # Correction layer - legislation/regulation flow
    'AUTHORIZED_BY', 'IMPLEMENTED_BY', 'RULEMAKING_FOR',
    # Correction layer - money flow
    'AWARDED_GRANT', 'AWARDED_CONTRACT', 'FUNDED_PROJECT',
    # Correction layer - operational/outcome signals
    'BUILT_IN', 'EXPANDED_CAPACITY', 'RESHORING_SIGNAL',
}


class LintIssue:
    """A lint issue found during prelint."""

    SEVERITY_ERROR = "ERROR"      # Auto-reject
    SEVERITY_WARNING = "WARNING"  # Flag for manual review
    SEVERITY_INFO = "INFO"        # Informational only

    def __init__(self, field: str, message: str, severity: str = "WARNING"):
        self.field = field
        self.message = message
        self.severity = severity

    def __repr__(self):
        return f"[{self.severity}] {self.field}: {self.message}"

    def to_dict(self):
        return {
            "field": self.field,
            "message": self.message,
            "severity": self.severity,
        }


def prelint_node_id(node_id: str, field_name: str = "node_id") -> List[LintIssue]:
    """Check if a node_id is valid or looks like garbage.

    Args:
        node_id: The node ID to validate
        field_name: Name of the field for error reporting

    Returns:
        List of LintIssue objects (empty if valid)
    """
    issues = []

    if not node_id:
        issues.append(LintIssue(field_name, "Empty node_id", LintIssue.SEVERITY_ERROR))
        return issues

    # Check for garbage patterns
    for pattern, reason in GARBAGE_NODE_PATTERNS:
        if re.search(pattern, node_id, re.IGNORECASE):
            issues.append(LintIssue(field_name, f"Garbage pattern: {reason}", LintIssue.SEVERITY_ERROR))

    # Check for multi-entity patterns
    for pattern, reason in MULTI_ENTITY_PATTERNS:
        if re.search(pattern, node_id):
            issues.append(LintIssue(field_name, f"Multi-entity: {reason}", LintIssue.SEVERITY_ERROR))

    # Check length (slugified IDs shouldn't be too long)
    if len(node_id) > 80:
        issues.append(LintIssue(field_name, f"Node ID too long ({len(node_id)} chars)", LintIssue.SEVERITY_WARNING))

    # Check if it's a known alias that should be normalized
    node_lower = node_id.lower().replace('-', ' ')
    if node_lower in ALIASES:
        canonical = ALIASES[node_lower]
        if canonical != node_id:
            issues.append(LintIssue(
                field_name,
                f"Should use canonical ID '{canonical}' instead of '{node_id}'",
                LintIssue.SEVERITY_WARNING
            ))

    return issues


def prelint_edge(
    from_node: str,
    to_node: str,
    relationship: str,
    detail: Optional[str] = None
) -> List[LintIssue]:
    """Validate a proposed edge.

    Args:
        from_node: Source node ID
        to_node: Target node ID
        relationship: Edge type
        detail: Optional edge detail text

    Returns:
        List of LintIssue objects (empty if valid)
    """
    issues = []

    # Validate from_node
    issues.extend(prelint_node_id(from_node, "from_node"))

    # Validate to_node
    issues.extend(prelint_node_id(to_node, "to_node"))

    # Validate relationship type
    if relationship not in VALID_EDGE_TYPES:
        issues.append(LintIssue(
            "relationship",
            f"Invalid edge type '{relationship}'. Valid types: {', '.join(sorted(VALID_EDGE_TYPES))}",
            LintIssue.SEVERITY_ERROR
        ))

    # Check for self-loops
    if from_node and to_node and from_node == to_node:
        issues.append(LintIssue(
            "edge",
            f"Self-loop detected: {from_node} -> {to_node}",
            LintIssue.SEVERITY_WARNING
        ))

    return issues


def prelint_node(
    node_id: str,
    node_type: str,
    name: str
) -> List[LintIssue]:
    """Validate a proposed node.

    Args:
        node_id: Node ID
        node_type: Node type
        name: Display name

    Returns:
        List of LintIssue objects (empty if valid)
    """
    issues = []

    # Validate node_id
    issues.extend(prelint_node_id(node_id, "node_id"))

    # Validate node_type
    valid_types = {
        'ORGANIZATION', 'PERSON', 'LEGISLATION', 'COURT_CASE', 'POLICY',
        'COMPANY', 'MEDIA_OUTLET', 'FINANCIAL_INST', 'AMICUS_BRIEF',
        'ETF_FUND', 'ECONOMIC_EVENT',
        # Correction layer node types
        'AGENCY', 'FACILITY', 'LOCATION', 'PROJECT', 'PROGRAM',
    }
    if node_type not in valid_types:
        issues.append(LintIssue(
            "node_type",
            f"Invalid node type '{node_type}'",
            LintIssue.SEVERITY_ERROR
        ))

    # Check name for garbage
    if name:
        for pattern, reason in GARBAGE_NODE_PATTERNS:
            if re.search(pattern, name, re.IGNORECASE):
                issues.append(LintIssue("name", f"Garbage pattern in name: {reason}", LintIssue.SEVERITY_WARNING))

        for pattern, reason in MULTI_ENTITY_PATTERNS:
            if re.search(pattern, name):
                issues.append(LintIssue("name", f"Multi-entity in name: {reason}", LintIssue.SEVERITY_ERROR))

    return issues


def prelint_claim(
    claim_text: str,
    source_url: Optional[str] = None
) -> List[LintIssue]:
    """Validate a proposed claim.

    Args:
        claim_text: The claim text
        source_url: Optional source URL

    Returns:
        List of LintIssue objects (empty if valid)
    """
    issues = []

    if not claim_text:
        issues.append(LintIssue("claim_text", "Empty claim text", LintIssue.SEVERITY_ERROR))
        return issues

    # Very short claims are suspicious
    if len(claim_text) < 10:
        issues.append(LintIssue("claim_text", f"Claim too short ({len(claim_text)} chars)", LintIssue.SEVERITY_WARNING))

    # Check source URL
    if source_url:
        if not source_url.startswith(('http://', 'https://')):
            issues.append(LintIssue("source_url", "Invalid URL format", LintIssue.SEVERITY_WARNING))

    return issues


def normalize_to_canonical(entity_name: str) -> Optional[str]:
    """Attempt to normalize an entity name to its canonical node_id.

    Args:
        entity_name: Entity name to normalize

    Returns:
        Canonical node_id if found, None otherwise
    """
    if not entity_name:
        return None

    # Try exact match first
    entity_lower = entity_name.lower().strip()
    if entity_lower in ALIASES:
        return ALIASES[entity_lower]

    # Try with dashes replaced by spaces
    entity_normalized = entity_lower.replace('-', ' ')
    if entity_normalized in ALIASES:
        return ALIASES[entity_normalized]

    return None


def run_prelint_on_staging(conn, agent_name: Optional[str] = None) -> dict:
    """Run prelint on all pending proposals in staging.

    Args:
        conn: Database connection
        agent_name: Optional filter by agent

    Returns:
        Dict with counts and issues by proposal
    """
    results = {
        "edges_checked": 0,
        "edges_with_errors": 0,
        "edges_with_warnings": 0,
        "nodes_checked": 0,
        "nodes_with_errors": 0,
        "nodes_with_warnings": 0,
        "issues": [],
    }

    # Check pending edges
    query = "SELECT proposal_id, from_node, to_node, relationship, detail FROM proposed_edges WHERE status = 'PENDING'"
    params = []
    if agent_name:
        query += " AND agent_name = ?"
        params.append(agent_name)

    edges = conn.execute(query, params).fetchall()
    for e in edges:
        results["edges_checked"] += 1
        issues = prelint_edge(e[1], e[2], e[3], e[4])
        if issues:
            has_error = any(i.severity == LintIssue.SEVERITY_ERROR for i in issues)
            has_warning = any(i.severity == LintIssue.SEVERITY_WARNING for i in issues)
            if has_error:
                results["edges_with_errors"] += 1
            if has_warning:
                results["edges_with_warnings"] += 1
            results["issues"].append({
                "proposal_id": e[0],
                "type": "edge",
                "issues": [i.to_dict() for i in issues],
            })

    # Check pending nodes
    query = "SELECT proposal_id, node_id, node_type, name FROM proposed_nodes WHERE status = 'PENDING'"
    params = []
    if agent_name:
        query += " AND agent_name = ?"
        params.append(agent_name)

    nodes = conn.execute(query, params).fetchall()
    for n in nodes:
        results["nodes_checked"] += 1
        issues = prelint_node(n[1], n[2], n[3])
        if issues:
            has_error = any(i.severity == LintIssue.SEVERITY_ERROR for i in issues)
            has_warning = any(i.severity == LintIssue.SEVERITY_WARNING for i in issues)
            if has_error:
                results["nodes_with_errors"] += 1
            if has_warning:
                results["nodes_with_warnings"] += 1
            results["issues"].append({
                "proposal_id": n[0],
                "type": "node",
                "issues": [i.to_dict() for i in issues],
            })

    return results
