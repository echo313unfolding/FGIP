"""FGIP Agent Factory - Proposes new agent specifications for capability gaps.

When GapDetector finds a hole that no existing agent can fill, AgentFactory:
1. Checks if an existing agent can address the gap
2. If not, writes an agent specification to agents/proposed/
3. Generates implementation template for Claude Code

Workflow:
1. GapDetector identifies structural hole
2. AgentFactory checks AGENT_CAPABILITIES mapping
3. If no agent can fill gap → write spec to agents/proposed/
4. User reviews and approves spec
5. Claude Code implements the agent
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional


@dataclass
class AgentSpec:
    """Specification for a proposed new agent."""
    spec_id: str
    name: str
    description: str
    gap_type: str           # What gap this addresses
    target_edge_types: List[str]
    data_sources: List[str]
    expected_artifacts: List[str]
    expected_output: Dict[str, int]  # edge_type -> expected count
    priority: int           # 1-5 (1 = highest)
    complexity: str         # 'simple', 'moderate', 'complex'
    dependencies: List[str] # Other agents or APIs needed
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AgentFactory:
    """Proposes new agent specifications when gaps cannot be filled by existing agents.

    This is NOT an FGIPAgent - it's a factory that generates agent specs.

    Usage:
        factory = AgentFactory()
        gap = {'edge_type': 'SITS_ON_BOARD', 'severity': 8, 'category': 'governance'}
        spec = factory.generate_spec_from_gap(gap)
        if spec:
            path = factory.write_spec(spec)
    """

    # Known agent capabilities - which agents can produce which edge types
    AGENT_CAPABILITIES = {
        'edgar': [
            'OWNS_SHARES', 'COMPETES_WITH', 'SUPPLIES_TO', 'CUSTOMER_OF',
            'SITS_ON_BOARD', 'RELATED_PARTY_TXN', 'ACQUIRED', 'SUBSIDIARY_OF',
        ],
        'supply_chain_extractor': [
            'SUPPLIES_TO', 'DEPENDS_ON', 'CUSTOMER_OF', 'BOTTLENECK_AT',
        ],
        'usaspending': [
            'AWARDED_GRANT', 'AWARDED_CONTRACT', 'FUNDED_PROJECT', 'BUILT_IN',
        ],
        'opensecrets': [
            'LOBBIED_FOR', 'LOBBIED_AGAINST', 'DONATED_TO',
        ],
        'fec': [
            'DONATED_TO', 'RECEIVED_FROM',
        ],
        'fara': [
            'REGISTERED_AS_AGENT', 'REPRESENTS',
        ],
        'federal_register': [
            'RULEMAKING_FOR', 'IMPLEMENTED_BY', 'COMMENTED_ON',
        ],
        'congress': [
            'VOTED_FOR', 'VOTED_AGAINST', 'SPONSORED', 'COSPONSORED',
        ],
        'scotus': [
            'FILED_AMICUS', 'RULED_ON', 'ARGUED',
        ],
        'chips_facility': [
            'CAPACITY_AT', 'BUILT_IN', 'OPENED_FACILITY',
        ],
        'tic': [
            'HOLDS_TREASURY', 'FOREIGN_HOLDINGS',
        ],
        'gao': [
            'AUDITED', 'RECOMMENDED',
        ],
    }

    # Gap type to suggested data source mapping
    GAP_SOURCE_MAP = {
        'supply_chain': [
            'SEC 10-K filings (Item 1, 1A)',
            'Company investor relations',
            'Industry reports (IBISWorld)',
        ],
        'governance': [
            'SEC DEF 14A proxy statements',
            'Board announcements',
            'OpenCorporates API',
        ],
        'causal': [
            'Academic papers',
            'Congressional testimony',
            'GAO reports',
        ],
        'court_records': [
            'CourtListener API',
            'PACER',
            'State court records',
        ],
        'foreign_influence': [
            'FARA.gov',
            'Department of State',
            'Treasury OFAC',
        ],
        'state_level': [
            'FollowTheMoney.org',
            'State campaign finance APIs',
            'State legislature APIs',
        ],
        'financial': [
            'SEC EDGAR 13F',
            'Bloomberg Terminal',
            'FINRA BrokerCheck',
        ],
    }

    # Complexity estimation by gap category
    COMPLEXITY_MAP = {
        'supply_chain': 'moderate',
        'governance': 'moderate',
        'causal': 'complex',
        'court_records': 'complex',
        'foreign_influence': 'moderate',
        'state_level': 'complex',
        'financial': 'moderate',
    }

    # Dependencies by gap category
    DEPENDENCIES_MAP = {
        'supply_chain': ['edgar', 'SEC API access'],
        'governance': ['edgar', 'company_name_resolution'],
        'causal': ['reasoning_agent', 'academic_paper_access'],
        'court_records': ['CourtListener API key', 'PACER credentials'],
        'foreign_influence': ['fara', 'treasury_api'],
        'state_level': ['state_api_keys'],
        'financial': ['edgar', 'sec_api'],
    }

    def __init__(self, output_dir: str = "agents/proposed"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def can_existing_agent_fill(self, edge_type: str) -> Optional[str]:
        """Check if an existing agent can produce this edge type.

        Args:
            edge_type: The edge type to check

        Returns:
            Agent name if one can fill it, None otherwise
        """
        for agent, capabilities in self.AGENT_CAPABILITIES.items():
            if edge_type in capabilities:
                return agent
        return None

    def get_agents_for_edge_type(self, edge_type: str) -> List[str]:
        """Get all agents that can produce this edge type."""
        agents = []
        for agent, capabilities in self.AGENT_CAPABILITIES.items():
            if edge_type in capabilities:
                agents.append(agent)
        return agents

    def categorize_gap(self, edge_type: str) -> str:
        """Determine the category of an edge type gap."""
        categories = {
            'supply_chain': [
                'SUPPLIES_TO', 'DEPENDS_ON', 'CUSTOMER_OF', 'BOTTLENECK_AT',
                'COMPETES_WITH',
            ],
            'governance': [
                'SITS_ON_BOARD', 'APPOINTED_BY', 'RELATED_PARTY_TXN',
                'MEMBER_OF',
            ],
            'causal': [
                'CAUSED', 'ENABLED', 'CONTRIBUTED_TO', 'BLOCKED',
                'REPLACED', 'REDUCED',
            ],
            'financial': [
                'OWNS_SHARES', 'ACQUIRED', 'SUBSIDIARY_OF',
                'INVESTED_IN', 'FUNDED',
            ],
            'court_records': [
                'FILED_AMICUS', 'RULED_ON', 'ARGUED', 'SUED',
            ],
            'foreign_influence': [
                'REGISTERED_AS_AGENT', 'REPRESENTS', 'LOBBIED_FOR',
            ],
        }

        for category, types in categories.items():
            if edge_type in types:
                return category

        return 'unknown'

    def generate_spec_from_gap(self, gap: Dict[str, Any]) -> Optional[AgentSpec]:
        """Generate an agent specification from a gap finding.

        Args:
            gap: Gap finding dict with keys: edge_type, severity, category, etc.

        Returns:
            AgentSpec if a new agent is needed, None if existing agent can fill
        """
        edge_type = gap.get('edge_type') or gap.get('subject')
        if not edge_type:
            return None

        # Check if existing agent can fill
        existing_agent = self.can_existing_agent_fill(edge_type)
        if existing_agent:
            print(f"Existing agent '{existing_agent}' can produce {edge_type}")
            return None

        # Determine gap category
        gap_category = gap.get('category') or self.categorize_gap(edge_type)

        # Generate spec ID
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d')
        edge_slug = edge_type.lower().replace('_', '-')[:20]
        spec_id = f"AGENT-SPEC-{timestamp}-{edge_slug}"

        # Determine agent name
        agent_name = f"{gap_category.replace('_', '-')}-{edge_slug}-agent"

        # Get suggested data sources
        data_sources = self.GAP_SOURCE_MAP.get(gap_category, ['TBD - research needed'])

        # Estimate complexity
        complexity = self.COMPLEXITY_MAP.get(gap_category, 'moderate')

        # Get dependencies
        dependencies = self.DEPENDENCIES_MAP.get(gap_category, [])

        # Estimate expected output
        expected_output = {edge_type: 50}  # Conservative estimate

        # Determine priority from severity
        severity = gap.get('severity', 5)
        priority = max(1, min(5, (11 - severity) // 2))

        return AgentSpec(
            spec_id=spec_id,
            name=agent_name,
            description=f"Agent to produce {edge_type} edges for {gap_category} gap",
            gap_type=gap_category,
            target_edge_types=[edge_type],
            data_sources=data_sources,
            expected_artifacts=[f'{gap_category}_data_*.json', f'{gap_category}_raw_*.html'],
            expected_output=expected_output,
            priority=priority,
            complexity=complexity,
            dependencies=dependencies,
        )

    def generate_spec_from_gaps_report(self, gaps_json_path: str) -> List[AgentSpec]:
        """Generate agent specs from a GapDetector report.

        Args:
            gaps_json_path: Path to gaps_*.json file

        Returns:
            List of AgentSpec for gaps that need new agents
        """
        gaps_path = Path(gaps_json_path)
        if not gaps_path.exists():
            print(f"Warning: Gaps file not found: {gaps_path}")
            return []

        report = json.loads(gaps_path.read_text())
        specs = []

        # Process unused edge types
        for finding in report.get('findings', []):
            if finding.get('gap_type') in ('unused_edge_type', 'extraction_gap', 'missing_edge_type'):
                edge_type = finding.get('entity_id')
                if edge_type:
                    gap = {
                        'edge_type': edge_type,
                        'severity': finding.get('severity', 5),
                        'category': finding.get('metadata', {}).get('category'),
                    }
                    spec = self.generate_spec_from_gap(gap)
                    if spec:
                        specs.append(spec)

        return specs

    def write_spec(self, spec: AgentSpec) -> str:
        """Write specification to proposed directory.

        Args:
            spec: AgentSpec to write

        Returns:
            Path to written spec file
        """
        spec_path = self.output_dir / f"{spec.spec_id}.json"
        spec_path.write_text(json.dumps(spec.to_dict(), indent=2))

        # Also write markdown template for Claude Code
        template_path = self.output_dir / f"{spec.spec_id}_template.md"
        template = self._generate_implementation_template(spec)
        template_path.write_text(template)

        print(f"Wrote spec: {spec_path}")
        print(f"Wrote template: {template_path}")

        return str(spec_path)

    def _generate_implementation_template(self, spec: AgentSpec) -> str:
        """Generate implementation template for Claude Code."""
        edge_types_list = '\n'.join(f'- `{et}`' for et in spec.target_edge_types)
        data_sources_list = '\n'.join(f'- {ds}' for ds in spec.data_sources)
        dependencies_list = '\n'.join(f'- {dep}' for dep in spec.dependencies) or 'None'

        return f'''# Agent Implementation: {spec.name}

## Specification

| Field | Value |
|-------|-------|
| **ID** | {spec.spec_id} |
| **Priority** | {spec.priority}/5 |
| **Complexity** | {spec.complexity} |
| **Gap Type** | {spec.gap_type} |
| **Created** | {spec.created_at} |

## Gap Being Addressed

{spec.description}

## Target Edge Types

{edge_types_list}

## Data Sources

{data_sources_list}

## Expected Artifacts

- `data/artifacts/{spec.name.replace('-agent', '')}/`
- File patterns: {', '.join(spec.expected_artifacts)}

## Expected Output

```json
{json.dumps(spec.expected_output, indent=2)}
```

## Dependencies

{dependencies_list}

---

## Implementation Checklist

### 1. Create Agent File
- [ ] Create `fgip/agents/{spec.name.replace('-', '_')}.py`

### 2. Implement Required Methods
```python
class {spec.name.replace('-', '_').title().replace('_', '')}Agent(FGIPAgent):
    def __init__(self, db):
        super().__init__(db=db, name="{spec.name.replace('-agent', '')}", description="...")

    def collect(self) -> List[Artifact]:
        """Fetch data from: {', '.join(spec.data_sources[:2])}"""
        pass

    def extract(self, artifacts: List[Artifact]) -> List[StructuredFact]:
        """Parse artifacts into structured facts"""
        pass

    def propose(self, facts: List[StructuredFact]) -> Tuple[List[ProposedClaim], List[ProposedEdge]]:
        """Generate {', '.join(spec.target_edge_types)} edges"""
        pass
```

### 3. Register Agent
- [ ] Add to `fgip/agents/__init__.py`:
  ```python
  from .{spec.name.replace('-', '_')} import {spec.name.replace('-', '_').title().replace('_', '')}Agent
  ```

- [ ] Add to `tools/schedule_runner.py` AGENT_REGISTRY:
  ```python
  "{spec.name.replace('-agent', '')}": {{"tier": 3, "module": "fgip.agents.{spec.name.replace('-', '_')}", "class": "{spec.name.replace('-', '_').title().replace('_', '')}Agent"}},
  ```

### 4. Create Artifact Directory
```bash
mkdir -p data/artifacts/{spec.name.replace('-agent', '')}
```

### 5. Write Tests
- [ ] Create `tests/test_{spec.name.replace('-', '_')}.py`
- [ ] Test collect() returns valid artifacts
- [ ] Test extract() parses correctly
- [ ] Test propose() generates expected edge types

### 6. Verify
```bash
PYTHONPATH=. python3 -c "
from fgip.agents.{spec.name.replace('-', '_')} import {spec.name.replace('-', '_').title().replace('_', '')}Agent
from fgip.db import FGIPDatabase
db = FGIPDatabase('fgip.db')
agent = {spec.name.replace('-', '_').title().replace('_', '')}Agent(db)
result = agent.run()
print(result)
"
```

---

## Notes

- This spec was generated by AgentFactory based on GapDetector findings
- Review data sources before implementation - some may require API keys
- Consider rate limiting for external API calls
- All proposals go to staging tables for human review
'''

    def list_proposed_specs(self) -> List[Dict[str, Any]]:
        """List all proposed agent specifications."""
        specs = []
        for spec_path in self.output_dir.glob("AGENT-SPEC-*.json"):
            if not spec_path.name.endswith('_template.md'):
                spec_data = json.loads(spec_path.read_text())
                spec_data['_path'] = str(spec_path)
                specs.append(spec_data)
        return sorted(specs, key=lambda x: x.get('priority', 5))

    def get_capability_matrix(self) -> Dict[str, List[str]]:
        """Get the full capability matrix."""
        return self.AGENT_CAPABILITIES.copy()

    def suggest_agent_for_edge_type(self, edge_type: str) -> Dict[str, Any]:
        """Suggest how to fill an edge type gap.

        Returns:
            Dict with 'existing_agent' (if any) and 'new_spec' (if needed)
        """
        result = {
            'edge_type': edge_type,
            'existing_agent': None,
            'new_spec_needed': False,
            'suggestion': '',
        }

        existing = self.can_existing_agent_fill(edge_type)
        if existing:
            result['existing_agent'] = existing
            result['suggestion'] = f"Run '{existing}' agent to produce {edge_type} edges"
        else:
            result['new_spec_needed'] = True
            category = self.categorize_gap(edge_type)
            result['suggestion'] = f"New agent needed for {category} category. Use generate_spec_from_gap()"

        return result


if __name__ == "__main__":
    import sys

    factory = AgentFactory()

    if len(sys.argv) > 1:
        if sys.argv[1] == '--list':
            # List proposed specs
            specs = factory.list_proposed_specs()
            print(f"Proposed agent specs: {len(specs)}")
            for spec in specs:
                print(f"  [{spec.get('priority', '?')}] {spec.get('name', 'unknown')}: {spec.get('description', '')[:60]}")

        elif sys.argv[1] == '--from-gaps':
            # Generate specs from gaps report
            gaps_path = sys.argv[2] if len(sys.argv) > 2 else "receipts/gaps/gaps_*.json"
            from glob import glob
            latest = sorted(glob(gaps_path))[-1] if glob(gaps_path) else None
            if latest:
                print(f"Processing: {latest}")
                specs = factory.generate_spec_from_gaps_report(latest)
                print(f"Generated {len(specs)} new agent specs")
                for spec in specs:
                    factory.write_spec(spec)
            else:
                print(f"No gaps files found matching: {gaps_path}")

        elif sys.argv[1] == '--suggest':
            # Suggest for specific edge type
            edge_type = sys.argv[2] if len(sys.argv) > 2 else 'SITS_ON_BOARD'
            suggestion = factory.suggest_agent_for_edge_type(edge_type)
            print(json.dumps(suggestion, indent=2))

        else:
            # Test with a specific edge type
            edge_type = sys.argv[1]
            gap = {'edge_type': edge_type, 'severity': 8}
            spec = factory.generate_spec_from_gap(gap)
            if spec:
                path = factory.write_spec(spec)
                print(f"Spec written to: {path}")
            else:
                print(f"Existing agent can handle {edge_type}")
    else:
        # Default: list capability matrix
        print("Agent Capability Matrix:")
        print("=" * 60)
        for agent, capabilities in factory.AGENT_CAPABILITIES.items():
            print(f"{agent}: {', '.join(capabilities[:5])}{'...' if len(capabilities) > 5 else ''}")
