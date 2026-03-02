"""
FGIP Reasoning Agent
====================
Traverses the existing knowledge graph to:
1. Find multi-hop causal paths (lobbying → policy → grants → ownership)
2. Identify "same actor both sides" patterns
3. Score causal chains by evidence strength
4. Propose new INFERENCE edges connecting existing nodes
5. Generate thesis confidence reports

Unlike collection agents (RSS, EDGAR, etc.), this agent doesn't scrape
external data. It reasons OVER the graph that already exists.
"""

import sqlite3
import hashlib
import json
from datetime import datetime, timezone
from typing import List, Tuple, Dict, Any, Optional, Set
from dataclasses import dataclass, field
from collections import defaultdict
from itertools import combinations

try:
    from .base import FGIPAgent, Artifact, StructuredFact, ProposedClaim, ProposedEdge
except ImportError:
    # Allow standalone execution for testing
    pass

# Import economic model for dynamic scenario modeling
try:
    from ..analysis.economic_model import (
        EconomicModel, CorrectionMechanism, DynamicScenario,
        DynamicThesisResult, KNOWN_MECHANISMS, get_baseline_model,
    )
    HAS_ECONOMIC_MODEL = True
except ImportError:
    HAS_ECONOMIC_MODEL = False

# Import compression pattern analyzer for chain validation
try:
    from ..analysis.compression_patterns import CompressionPatternAnalyzer
    HAS_COMPRESSION = True
except ImportError:
    HAS_COMPRESSION = False

# Maximum compression boost to chain confidence (bounded to prevent overfit)
COMPRESSION_MAX_BOOST = 0.10  # 10% max


# ─── Data Structures ───────────────────────────────────────────────────────

@dataclass
class CausalPath:
    """A multi-hop path through the graph with evidence scoring."""
    hops: List[Dict[str, str]]       # [{from, edge_type, to, edge_id}, ...]
    start_node: str
    end_node: str
    path_type: str                    # "lobbying_to_grant", "ownership_both_sides", etc.
    evidence_score: float             # 0.0 - 1.0
    tier_distribution: Dict[int, int] # {0: 3, 1: 2, 2: 5} count of sources by tier
    weakest_link: Optional[str]       # edge_id of lowest-evidence hop
    narrative: str                    # Human-readable description

@dataclass
class BothSidesPattern:
    """An actor that appears on both problem and correction sides."""
    actor_id: str
    actor_name: str
    problem_edges: List[Dict]    # edges connecting to problem layer
    correction_edges: List[Dict] # edges connecting to correction layer
    ownership_pct: Dict[str, float]  # {company_id: pct}
    confidence: float
    narrative: str

@dataclass
class ReasoningResult:
    """Complete output of a reasoning run."""
    causal_paths: List[CausalPath]
    both_sides_patterns: List[BothSidesPattern]
    convergence_nodes: List[Dict]   # nodes where 3+ paths intersect
    proposed_inferences: List[Dict] # new edges to propose
    thesis_score: float
    report: str


# ─── Edge Type Classification ──────────────────────────────────────────────

PROBLEM_EDGE_TYPES = {
    "LOBBIED_FOR", "DONATED_TO", "FUNDED_BY", "REGISTERED_AS_AGENT",
    "FILED_AMICUS", "EMPLOYED", "OWNS_MEDIA",
    # Foreign leverage edges (GENIUS Act problem layer)
    "HAS_LEVERAGE_OVER", "BLOCKS", "HOLDS_TREASURY",
}

CORRECTION_EDGE_TYPES = {
    "AWARDED_GRANT", "BUILT_IN", "FUNDED_PROJECT", "IMPLEMENTED_BY",
    "RULEMAKING_FOR", "AUTHORIZED_BY", "CORRECTS",
    # GENIUS Act mechanism edges
    "ENABLES", "REDUCES", "FUNDS", "CONTRIBUTES_TO",
}

OWNERSHIP_EDGE_TYPES = {
    "OWNS_SHARES", "SUBSIDIARY_OF", "MEMBER_OF",
}

INSTITUTIONAL_INVESTORS = {
    "vanguard-group", "blackrock-inc", "state-street-corporation",
    "fidelity", "capital-group", "t-rowe-price",
}

PROBLEM_POLICIES = {
    "pntr-2000", "pntr", "china-trade-policy", "china-trade",
}

CORRECTION_POLICIES = {
    "chips-act", "chips-act-2022", "inflation-reduction-act", "infrastructure-act",
    "genius-act-2025", "genius-act",
}

# Economic mechanism edge types for dynamic scenario modeling
MECHANISM_EDGE_TYPES = {
    "REDUCES", "BLOCKS", "REPLACES", "CORRELATES", "DERIVES_FROM",
}


# ─── Reasoning Agent ───────────────────────────────────────────────────────

class ReasoningAgent:
    """
    Reasons over the FGIP graph to find patterns, score chains,
    and propose inference edges.

    This is NOT a standard FGIPAgent (no collect/extract/propose cycle).
    It reads the production graph and writes to staging.
    """

    def __init__(self, db_path: str = "fgip.db"):
        self.db_path = db_path
        self.conn = None
        self.adjacency: Dict[str, List[Dict]] = defaultdict(list)  # node_id -> [edges]
        self.reverse_adj: Dict[str, List[Dict]] = defaultdict(list)  # target -> [edges]
        self.nodes: Dict[str, Dict] = {}
        self.edges: List[Dict] = []
        self.sources_by_edge: Dict[str, List[Dict]] = defaultdict(list)

    def connect(self):
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._load_graph()

    def _load_graph(self):
        """Load entire graph into memory for fast traversal."""
        # Load nodes
        for row in self.conn.execute("SELECT * FROM nodes"):
            d = dict(row)
            self.nodes[d["node_id"]] = d

        # Load edges - handle both column naming conventions
        for row in self.conn.execute("SELECT * FROM edges"):
            d = dict(row)
            # Normalize column names (some schemas use from_node_id, others source_node_id)
            if "from_node_id" in d:
                d["source_node_id"] = d["from_node_id"]
            if "to_node_id" in d:
                d["target_node_id"] = d["to_node_id"]

            self.edges.append(d)
            src = d.get("source_node_id") or d.get("from_node_id")
            tgt = d.get("target_node_id") or d.get("to_node_id")
            if src:
                self.adjacency[src].append(d)
            if tgt:
                self.reverse_adj[tgt].append(d)

        # Load source tiers for edges (via claims)
        try:
            query = """
                SELECT e.edge_id, s.tier, s.url
                FROM edges e
                LEFT JOIN claims c ON e.claim_id = c.claim_id
                LEFT JOIN claim_sources cs ON c.claim_id = cs.claim_id
                LEFT JOIN sources s ON cs.source_id = s.source_id
                WHERE s.tier IS NOT NULL
            """
            for row in self.conn.execute(query):
                self.sources_by_edge[row["edge_id"]].append({
                    "tier": row["tier"],
                    "url": row["url"],
                })
        except Exception:
            pass  # sources may not be linked yet

        print(f"Loaded: {len(self.nodes)} nodes, {len(self.edges)} edges")

    # ─── Path Finding ──────────────────────────────────────────────────

    def find_all_paths(self, start: str, end: str, max_depth: int = 5, bidirectional: bool = True) -> List[List[Dict]]:
        """BFS to find all paths from start to end, up to max_depth hops.

        Args:
            start: Starting node ID
            end: Ending node ID
            max_depth: Maximum number of hops
            bidirectional: If True, also traverse edges in reverse direction
        """
        paths = []
        queue = [(start, [])]
        visited_paths: Set[str] = set()

        while queue:
            current, path = queue.pop(0)
            if len(path) >= max_depth:
                continue

            # Forward edges (current is source)
            for edge in self.adjacency.get(current, []):
                target = edge.get("target_node_id") or edge.get("to_node_id")
                edge_id = edge.get("edge_id") or f"{current}-{edge['edge_type']}-{target}"
                hop = {
                    "from": current,
                    "edge_type": edge["edge_type"],
                    "to": target,
                    "edge_id": edge_id,
                    "direction": "forward",
                }
                new_path = path + [hop]
                path_key = "->".join(h["edge_id"] or "?" for h in new_path)

                if path_key in visited_paths:
                    continue
                visited_paths.add(path_key)

                if target == end:
                    paths.append(new_path)
                elif target not in [h["from"] for h in new_path] and target not in [h["to"] for h in new_path]:
                    queue.append((target, new_path))

            # Reverse edges (current is target) - enables traversal through vote edges
            if bidirectional:
                for edge in self.reverse_adj.get(current, []):
                    source = edge.get("source_node_id") or edge.get("from_node_id")
                    edge_id = edge.get("edge_id") or f"{source}-{edge['edge_type']}-{current}"
                    hop = {
                        "from": current,
                        "edge_type": f"<-{edge['edge_type']}",  # Mark as reverse
                        "to": source,
                        "edge_id": edge_id + "_rev",
                        "direction": "reverse",
                    }
                    new_path = path + [hop]
                    path_key = "->".join(h["edge_id"] or "?" for h in new_path)

                    if path_key in visited_paths:
                        continue
                    visited_paths.add(path_key)

                    if source == end:
                        paths.append(new_path)
                    elif source not in [h["from"] for h in new_path] and source not in [h["to"] for h in new_path]:
                        queue.append((source, new_path))

        return paths

    def find_causal_chains(self) -> List[CausalPath]:
        """
        Find paths from problem layer to correction layer.
        Pattern: lobbyist -> policy -> ... -> correction outcome
        """
        chains = []

        # Find all lobbying source nodes
        lobby_sources = set()
        for edge in self.edges:
            if edge["edge_type"] in PROBLEM_EDGE_TYPES:
                src = edge.get("source_node_id") or edge.get("from_node_id")
                if src:
                    lobby_sources.add(src)

        # Find all correction target nodes
        correction_targets = set()
        for edge in self.edges:
            if edge["edge_type"] in CORRECTION_EDGE_TYPES:
                tgt = edge.get("target_node_id") or edge.get("to_node_id")
                if tgt:
                    correction_targets.add(tgt)

        # Find paths from lobby sources to correction targets
        for source in list(lobby_sources)[:20]:  # limit for performance
            for target in list(correction_targets)[:20]:
                if source == target:
                    continue
                paths = self.find_all_paths(source, target, max_depth=4)
                for path in paths:
                    chain = self._score_path(path, "lobbying_to_correction")
                    if chain.evidence_score > 0.2:  # minimum threshold
                        chains.append(chain)

        # Sort by evidence score
        chains.sort(key=lambda c: c.evidence_score, reverse=True)
        return chains[:50]  # top 50

    def _score_path(self, hops: List[Dict], path_type: str) -> CausalPath:
        """Score a path based on evidence quality."""
        tier_dist = defaultdict(int)
        min_score = 1.0
        weakest = None

        for hop in hops:
            # Strip _rev suffix for reverse edges when looking up sources
            edge_id = hop["edge_id"]
            if edge_id.endswith("_rev"):
                edge_id = edge_id[:-4]  # Remove "_rev" suffix
            sources = self.sources_by_edge.get(edge_id, [])
            if not sources:
                hop_score = 0.1  # no sources = very weak
                tier_dist[3] += 1  # "unsourced"
            else:
                best_tier = min(s["tier"] for s in sources)
                tier_dist[best_tier] += 1
                tier_scores = {0: 1.0, 1: 0.8, 2: 0.5}
                hop_score = tier_scores.get(best_tier, 0.3)

            if hop_score < min_score:
                min_score = hop_score
                weakest = hop["edge_id"]

        # Overall score = geometric mean of hop scores weighted by tier
        n_hops = len(hops)
        tier0_count = tier_dist.get(0, 0)
        tier1_count = tier_dist.get(1, 0)

        evidence_score = min_score * (0.6 + 0.15 * tier0_count + 0.1 * tier1_count)
        evidence_score = min(1.0, evidence_score)

        # Build narrative
        hop_names = []
        for hop in hops:
            src_name = self.nodes.get(hop["from"], {}).get("name", hop["from"])
            tgt_name = self.nodes.get(hop["to"], {}).get("name", hop["to"])
            hop_names.append(f"{src_name} --{hop['edge_type']}--> {tgt_name}")

        narrative = " → ".join(hop_names)

        return CausalPath(
            hops=hops,
            start_node=hops[0]["from"],
            end_node=hops[-1]["to"],
            path_type=path_type,
            evidence_score=evidence_score,
            tier_distribution=dict(tier_dist),
            weakest_link=weakest,
            narrative=narrative,
        )

    # ─── Compression-Based Chain Validation ────────────────────────────

    def validate_chains_with_compression(self, chains: List[CausalPath]) -> List[CausalPath]:
        """
        Use surprisal analysis as primary signal for chain validation.

        Surprisal (information-theoretic) scoring measures structural
        predictability using abstract tokens (edge_type, node_types, tier)
        instead of verbose node ID strings.

        Low surprisal = chain follows common patterns = structurally regular
        High surprisal = unusual path = potential weak link

        Returns chains with adjusted evidence_score where applicable.
        """
        if not HAS_COMPRESSION or not chains:
            return chains

        try:
            analyzer = CompressionPatternAnalyzer(self.db_path)
            analyzer.connect()
        except Exception as e:
            print(f"  ⚠ Compression analyzer unavailable: {e}")
            return chains

        validated_chains = []
        boost_count = 0

        for chain in chains:
            # Extract node IDs and edge IDs from chain
            chain_nodes = [chain.start_node]
            chain_edges = []
            for hop in chain.hops:
                chain_nodes.append(hop["to"])
                edge_id = hop.get("edge_id", "")
                chain_edges.append(edge_id)

            # Check tier distribution
            tier0_count = chain.tier_distribution.get(0, 0)
            tier1_count = chain.tier_distribution.get(1, 0)
            has_quality_sources = (tier0_count + tier1_count) > 0

            try:
                # PRIMARY: Try surprisal scoring (better signal)
                surprisal_result = analyzer.chain_surprisal_score(
                    chain_nodes=chain_nodes,
                    chain_edges=chain_edges
                )

                if surprisal_result.is_structured and has_quality_sources:
                    # Boost proportional to how much better than baseline
                    # Lower surprisal = more structured = bigger boost
                    advantage = max(0, surprisal_result.baseline_mean - surprisal_result.mean_surprisal_bits)
                    boost = min(COMPRESSION_MAX_BOOST, advantage * 0.03)

                    if boost > 0.01:
                        chain.evidence_score = min(1.0, chain.evidence_score * (1 + boost))
                        boost_count += 1

            except Exception:
                # FALLBACK: Use compression ratio if surprisal fails
                try:
                    validation = analyzer.validate_causal_chain(
                        chain_nodes=chain_nodes,
                        chain_edges=[e.rstrip('_rev') if e.endswith('_rev') else e for e in chain_edges]
                    )

                    compression_ratio = validation.get("compression_ratio", 1.0)
                    is_compressible = validation.get("is_compressible", False)

                    if is_compressible and has_quality_sources:
                        compression_advantage = max(0, 1.0 - compression_ratio)
                        boost = min(COMPRESSION_MAX_BOOST, compression_advantage * 0.2)

                        if boost > 0.01:
                            chain.evidence_score = min(1.0, chain.evidence_score * (1 + boost))
                            boost_count += 1
                except Exception:
                    pass  # Keep original score

            validated_chains.append(chain)

        if boost_count > 0:
            print(f"  Surprisal boost applied to {boost_count}/{len(chains)} chains")

        return validated_chains

    # ─── Both Sides Detection ─────────────────────────────────────────

    def find_both_sides_patterns(self) -> List[BothSidesPattern]:
        """
        Find actors that connect to BOTH problem and correction layers.
        This is the core thesis test: same money, both sides.
        """
        patterns = []

        for node_id, node in self.nodes.items():
            outgoing = self.adjacency.get(node_id, [])
            incoming = self.reverse_adj.get(node_id, [])
            all_edges = outgoing + incoming

            # Classify edges
            problem_edges = []
            correction_edges = []
            ownership_edges = []

            for edge in all_edges:
                et = edge["edge_type"]
                if et in PROBLEM_EDGE_TYPES:
                    problem_edges.append(edge)
                elif et in CORRECTION_EDGE_TYPES:
                    correction_edges.append(edge)
                elif et in OWNERSHIP_EDGE_TYPES:
                    ownership_edges.append(edge)

            # Check for both-sides pattern
            if problem_edges and correction_edges:
                # Direct involvement on both sides
                pct = {}
                for e in ownership_edges:
                    detail = e.get("detail") or e.get("notes", "")
                    try:
                        if "%" in str(detail):
                            pct_val = float(str(detail).split("%")[0].split()[-1])
                            tgt = e.get("target_node_id") or e.get("to_node_id")
                            if tgt:
                                pct[tgt] = pct_val
                    except (ValueError, TypeError):
                        pass

                confidence = min(0.95, 0.3 + 0.15 * len(problem_edges) + 0.15 * len(correction_edges))

                pattern = BothSidesPattern(
                    actor_id=node_id,
                    actor_name=node.get("name", node_id),
                    problem_edges=[dict(e) for e in problem_edges],
                    correction_edges=[dict(e) for e in correction_edges],
                    ownership_pct=pct,
                    confidence=confidence,
                    narrative=self._build_both_sides_narrative(node, problem_edges, correction_edges),
                )
                patterns.append(pattern)

        # Now check OWNERSHIP both-sides:
        # Investor owns Company A (lobbied for problem) AND Company B (received correction)
        for investor_id in INSTITUTIONAL_INVESTORS:
            if investor_id not in self.nodes:
                continue

            owned_companies = set()
            for edge in self.adjacency.get(investor_id, []):
                if edge["edge_type"] == "OWNS_SHARES":
                    tgt = edge.get("target_node_id") or edge.get("to_node_id")
                    if tgt:
                        owned_companies.add(tgt)

            # Which owned companies are in problem layer?
            problem_companies = set()
            for company in owned_companies:
                for edge in self.adjacency.get(company, []):
                    if edge["edge_type"] in PROBLEM_EDGE_TYPES:
                        problem_companies.add(company)
                # Also check if company is target of problem edge
                for edge in self.reverse_adj.get(company, []):
                    if edge["edge_type"] in PROBLEM_EDGE_TYPES:
                        problem_companies.add(company)

            # Which owned companies are in correction layer?
            correction_companies = set()
            for company in owned_companies:
                for edge in self.reverse_adj.get(company, []):
                    if edge["edge_type"] in CORRECTION_EDGE_TYPES:
                        correction_companies.add(company)

            if problem_companies and correction_companies:
                investor = self.nodes.get(investor_id, {})

                # Extract ownership percentages
                pct = {}
                for edge in self.adjacency.get(investor_id, []):
                    if edge["edge_type"] == "OWNS_SHARES":
                        detail = edge.get("detail") or edge.get("notes", "")
                        tgt = edge.get("target_node_id") or edge.get("to_node_id")
                        try:
                            if detail and "%" in str(detail):
                                pct_val = float(str(detail).split("%")[0].split()[-1])
                                if tgt:
                                    pct[tgt] = pct_val
                        except (ValueError, TypeError):
                            pass

                confidence = min(0.95, 0.4 + 0.1 * len(problem_companies) + 0.1 * len(correction_companies))

                # Build narrative
                prob_names = [self.nodes.get(c, {}).get("name", c) for c in problem_companies]
                corr_names = [self.nodes.get(c, {}).get("name", c) for c in correction_companies]

                narrative = (
                    f"{investor.get('name', investor_id)} owns shares in "
                    f"PROBLEM-LAYER companies ({', '.join(prob_names[:5])}) "
                    f"AND CORRECTION-LAYER companies ({', '.join(corr_names[:5])}). "
                    f"Same institutional capital on both sides of the trade."
                )

                pattern = BothSidesPattern(
                    actor_id=investor_id,
                    actor_name=investor.get("name", investor_id),
                    problem_edges=[{"company": c, "side": "problem"} for c in problem_companies],
                    correction_edges=[{"company": c, "side": "correction"} for c in correction_companies],
                    ownership_pct=pct,
                    confidence=confidence,
                    narrative=narrative,
                )
                patterns.append(pattern)

        patterns.sort(key=lambda p: p.confidence, reverse=True)
        return patterns

    def _build_both_sides_narrative(self, node, problem_edges, correction_edges):
        name = node.get("name", node.get("node_id", "Unknown"))
        prob_targets = set()
        for e in problem_edges:
            tgt = e.get("target_node_id") or e.get("to_node_id") or e.get("source_node_id") or e.get("from_node_id", "")
            prob_targets.add(tgt)
        corr_targets = set()
        for e in correction_edges:
            tgt = e.get("target_node_id") or e.get("to_node_id") or e.get("source_node_id") or e.get("from_node_id", "")
            corr_targets.add(tgt)

        return (
            f"{name} has {len(problem_edges)} problem-layer connections "
            f"and {len(correction_edges)} correction-layer connections. "
            f"Problem targets: {', '.join(list(prob_targets)[:5])}. "
            f"Correction targets: {', '.join(list(corr_targets)[:5])}."
        )

    # ─── Convergence Detection ─────────────────────────────────────────

    def find_convergence_nodes(self) -> List[Dict]:
        """
        Find nodes where 3+ independent causal paths intersect.
        These are the "nexus points" of the thesis.
        """
        node_path_count: Dict[str, Dict] = defaultdict(lambda: {
            "problem_in": 0, "problem_out": 0,
            "correction_in": 0, "correction_out": 0,
            "ownership_in": 0, "ownership_out": 0,
            "total": 0,
        })

        for edge in self.edges:
            et = edge["edge_type"]
            src = edge.get("source_node_id") or edge.get("from_node_id")
            tgt = edge.get("target_node_id") or edge.get("to_node_id")

            if not src or not tgt:
                continue

            if et in PROBLEM_EDGE_TYPES:
                node_path_count[src]["problem_out"] += 1
                node_path_count[tgt]["problem_in"] += 1
            elif et in CORRECTION_EDGE_TYPES:
                node_path_count[src]["correction_out"] += 1
                node_path_count[tgt]["correction_in"] += 1
            elif et in OWNERSHIP_EDGE_TYPES:
                node_path_count[src]["ownership_out"] += 1
                node_path_count[tgt]["ownership_in"] += 1

            node_path_count[src]["total"] += 1
            node_path_count[tgt]["total"] += 1

        convergence = []
        for node_id, counts in node_path_count.items():
            # Count how many distinct layer types this node touches
            layers = 0
            if counts["problem_in"] + counts["problem_out"] > 0:
                layers += 1
            if counts["correction_in"] + counts["correction_out"] > 0:
                layers += 1
            if counts["ownership_in"] + counts["ownership_out"] > 0:
                layers += 1

            if layers >= 2 and counts["total"] >= 3:
                node = self.nodes.get(node_id, {})
                convergence.append({
                    "node_id": node_id,
                    "name": node.get("name", node_id),
                    "node_type": node.get("node_type", "UNKNOWN"),
                    "layers_touched": layers,
                    "total_connections": counts["total"],
                    "breakdown": counts,
                })

        convergence.sort(key=lambda c: (c["layers_touched"], c["total_connections"]), reverse=True)
        return convergence[:30]

    # ─── Inference Generation ──────────────────────────────────────────

    def generate_inferences(self, patterns: List[BothSidesPattern],
                            chains: List[CausalPath]) -> List[Dict]:
        """
        Propose new INFERENCE edges based on discovered patterns.
        These go to staging for human review.
        """
        inferences = []
        seen = set()

        # From both-sides patterns: propose BENEFITS_FROM edges
        for pattern in patterns:
            if pattern.confidence < 0.5:
                continue

            # For ownership both-sides: investor BENEFITS_FROM correction policy
            for corr_edge in pattern.correction_edges:
                company = corr_edge.get("company", corr_edge.get("target_node_id", corr_edge.get("to_node_id", "")))
                if not company:
                    continue

                # Find what correction policy benefits this company
                for edge in self.reverse_adj.get(company, []):
                    if edge["edge_type"] in CORRECTION_EDGE_TYPES:
                        policy = edge.get("source_node_id") or edge.get("from_node_id")
                        if not policy:
                            continue
                        key = f"{pattern.actor_id}->BENEFITS_FROM->{policy}"
                        if key not in seen:
                            seen.add(key)
                            inferences.append({
                                "source_node_id": pattern.actor_id,
                                "target_node_id": policy,
                                "edge_type": "BENEFITS_FROM",
                                "detail": (
                                    f"Owns shares in {self.nodes.get(company, {}).get('name', company)} "
                                    f"which received {edge['edge_type']} from {policy}"
                                ),
                                "confidence": pattern.confidence,
                                "evidence_path": f"{pattern.actor_id} --OWNS_SHARES--> {company} "
                                                 f"<--{edge['edge_type']}-- {policy}",
                                "assertion_type": "INFERENCE",
                                "reasoning": (
                                    f"Institutional investor {pattern.actor_name} owns shares in "
                                    f"{self.nodes.get(company, {}).get('name', company)}, which is a "
                                    f"recipient of {policy}. This creates financial benefit from the "
                                    f"correction layer policy."
                                ),
                            })

        # From causal chains: propose CAUSED_BY edges for long chains
        for chain in chains:
            if chain.evidence_score < 0.4 or len(chain.hops) < 2:
                continue

            key = f"{chain.start_node}->CAUSED_BY->{chain.end_node}"
            if key not in seen:
                seen.add(key)
                inferences.append({
                    "source_node_id": chain.end_node,
                    "target_node_id": chain.start_node,
                    "edge_type": "CAUSED_BY",
                    "detail": f"{len(chain.hops)}-hop chain: {chain.narrative}",
                    "confidence": chain.evidence_score,
                    "evidence_path": chain.narrative,
                    "assertion_type": "INFERENCE",
                    "reasoning": (
                        f"Multi-hop causal path detected with evidence score "
                        f"{chain.evidence_score:.0%}. Chain: {chain.narrative}"
                    ),
                })

        inferences.sort(key=lambda i: i["confidence"], reverse=True)
        return inferences[:100]  # top 100

    # ─── Thesis Scoring ────────────────────────────────────────────────

    def score_thesis(self, patterns: List[BothSidesPattern],
                     chains: List[CausalPath],
                     convergence: List[Dict]) -> Tuple[float, Dict]:
        """
        Score the overall thesis: "Same institutional capital profited
        from offshoring and is positioned to profit from reshoring."
        """
        score = 0.0
        breakdown = {}

        # 1. Do both-sides patterns exist? (max 25 points)
        both_sides_score = min(25, len(patterns) * 5)
        breakdown["both_sides_patterns"] = both_sides_score
        score += both_sides_score

        # 2. Are there high-confidence patterns? (max 20 points)
        high_conf = [p for p in patterns if p.confidence > 0.7]
        high_conf_score = min(20, len(high_conf) * 7)
        breakdown["high_confidence_patterns"] = high_conf_score
        score += high_conf_score

        # 3. Causal chain density (max 15 points)
        strong_chains = [c for c in chains if c.evidence_score > 0.4]
        chain_score = min(15, len(strong_chains) * 3)
        breakdown["causal_chains"] = chain_score
        score += chain_score

        # 4. Convergence nodes (max 15 points)
        multi_layer = [c for c in convergence if c["layers_touched"] >= 2]
        conv_score = min(15, len(multi_layer) * 3)
        breakdown["convergence_nodes"] = conv_score
        score += conv_score

        # 5. Source quality (max 15 points)
        tier0_edges = 0
        tier1_edges = 0
        for edge_id, sources in self.sources_by_edge.items():
            tiers = [s["tier"] for s in sources]
            if 0 in tiers:
                tier0_edges += 1
            elif 1 in tiers:
                tier1_edges += 1
        total_edges = len(self.edges) or 1
        tier_score = min(15, (tier0_edges / total_edges) * 30 + (tier1_edges / total_edges) * 15)
        breakdown["source_quality"] = round(tier_score, 1)
        score += tier_score

        # 6. Graph connectivity (max 10 points)
        connected = sum(1 for n in self.nodes if self.adjacency.get(n) or self.reverse_adj.get(n))
        connectivity = connected / max(len(self.nodes), 1)
        conn_score = min(10, connectivity * 12)
        breakdown["connectivity"] = round(conn_score, 1)
        score += conn_score

        return min(100, round(score, 1)), breakdown

    # ─── Dynamic Scenario Modeling ──────────────────────────────────────

    def find_correction_mechanisms(self) -> List[CorrectionMechanism]:
        """Find correction mechanisms from graph edges or known mechanisms.

        Looks for REDUCES/BLOCKS/REPLACES edges in the graph, and also
        includes pre-defined known mechanisms for policies like GENIUS Act.
        """
        if not HAS_ECONOMIC_MODEL:
            return []

        mechanisms = []

        # Check for mechanism edges in the graph
        for edge in self.edges:
            edge_type = edge.get("edge_type", "")
            if edge_type in MECHANISM_EDGE_TYPES:
                # Extract mechanism details from edge metadata
                metadata = edge.get("metadata", {})
                if isinstance(metadata, str):
                    try:
                        metadata = json.loads(metadata) if metadata else {}
                    except:
                        metadata = {}
                if metadata is None:
                    metadata = {}

                target_var = metadata.get("target_variable")
                delta = metadata.get("delta", 0)

                if target_var and delta:
                    mechanisms.append(CorrectionMechanism(
                        mechanism_id=edge.get("edge_id", f"{edge['from_node_id']}-{edge_type}"),
                        policy_node_id=edge.get("from_node_id"),
                        target_variable=target_var,
                        effect_type=edge_type,
                        expected_delta=delta,
                        confidence=edge.get("confidence", 0.5),
                        narrative=edge.get("notes") or f"{edge_type} edge from {edge['from_node_id']}",
                    ))

        # Also check for known mechanisms that match nodes in the graph
        for policy_id in CORRECTION_POLICIES:
            if policy_id in self.nodes:
                # Check if there's a matching known mechanism
                for mech_id, mech in KNOWN_MECHANISMS.items():
                    if mech.policy_node_id in policy_id or policy_id in mech.policy_node_id:
                        # Avoid duplicates
                        if not any(m.mechanism_id == mech_id for m in mechanisms):
                            mechanisms.append(mech)

        return mechanisms

    def model_dynamic_scenarios(self) -> List[DynamicScenario]:
        """Model all correction mechanisms and return scenarios."""
        if not HAS_ECONOMIC_MODEL:
            return []

        model = get_baseline_model()
        mechanisms = self.find_correction_mechanisms()

        scenarios = []
        for mech in mechanisms:
            try:
                scenario = model.model_scenario(mech)
                scenarios.append(scenario)
            except Exception as e:
                print(f"  ⚠ Could not model {mech.mechanism_id}: {e}")

        return scenarios

    def score_thesis_with_dynamics(
        self,
        patterns: List[BothSidesPattern],
        chains: List[CausalPath],
        convergence: List[Dict],
        scenarios: List[DynamicScenario]
    ) -> Tuple[float, Dict, float]:
        """Score thesis including dynamic mechanism effects.

        Returns:
            Tuple of (dynamic_score, breakdown, confidence_delta)
        """
        # Get static score first
        static_score, breakdown = self.score_thesis(patterns, chains, convergence)

        if not scenarios:
            return static_score, breakdown, 0.0

        # Add dynamic component (max 15 points)
        dynamic_bonus = 0.0
        for scenario in scenarios:
            if scenario.extraction_after < scenario.extraction_before:
                # Correction mechanism validated - adds confidence
                extraction_before = scenario.extraction_before
                if extraction_before > 0:
                    reduction_pct = (extraction_before - scenario.extraction_after) / extraction_before
                    dynamic_bonus += min(5, reduction_pct * 15) * scenario.mechanism.confidence

        dynamic_bonus = min(15, dynamic_bonus)
        breakdown["dynamic_mechanisms"] = round(dynamic_bonus, 1)

        dynamic_score = min(100, static_score + dynamic_bonus)
        confidence_delta = dynamic_score - static_score

        return round(dynamic_score, 1), breakdown, round(confidence_delta, 1)

    # ─── Stage Proposals ───────────────────────────────────────────────

    def stage_inferences(self, inferences: List[Dict]):
        """Write inference proposals to staging tables."""
        count = 0
        for inf in inferences:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            h = hashlib.md5(f"{inf['source_node_id']}{inf['target_node_id']}{inf['edge_type']}".encode()).hexdigest()[:8]
            proposal_id = f"FGIP-PROPOSED-REASONING-{ts}-{h}"

            # Check if edge already exists
            try:
                existing = self.conn.execute(
                    """SELECT edge_id FROM edges
                       WHERE from_node_id=? AND to_node_id=? AND edge_type=?""",
                    (inf["source_node_id"], inf["target_node_id"], inf["edge_type"])
                ).fetchone()
            except Exception:
                existing = None
            if existing:
                continue

            # Check if already proposed
            try:
                already = self.conn.execute(
                    """SELECT proposal_id FROM proposed_edges
                       WHERE from_node=? AND to_node=? AND relationship=? AND status='PENDING'""",
                    (inf["source_node_id"], inf["target_node_id"], inf["edge_type"])
                ).fetchone()
                if already:
                    continue
            except Exception:
                pass  # table may not exist or have different schema

            try:
                self.conn.execute("""
                    INSERT INTO proposed_edges (
                        proposal_id, from_node, to_node, relationship,
                        detail, agent_name, confidence, reasoning,
                        status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
                """, (
                    proposal_id,
                    inf["source_node_id"],
                    inf["target_node_id"],
                    inf["edge_type"],
                    inf["detail"],
                    "reasoning",
                    inf["confidence"],
                    inf["reasoning"],
                    datetime.now(timezone.utc).isoformat() + "Z",
                ))
                count += 1
            except Exception as e:
                print(f"  ⚠ Could not stage {proposal_id}: {e}")

        self.conn.commit()
        print(f"  Staged {count} inference proposals")
        return count

    # ─── Main Run ──────────────────────────────────────────────────────

    def run(self, stage: bool = True, dynamic: bool = False) -> ReasoningResult:
        """Execute full reasoning pass over the graph.

        Args:
            stage: Whether to stage inference proposals
            dynamic: Whether to include dynamic economic scenario modeling
        """
        if not self.conn:
            self.connect()

        # Calculate step count based on available features
        base_steps = 5
        if HAS_COMPRESSION:
            base_steps += 1
        if dynamic:
            base_steps += 1
        step_count = base_steps

        print("\n" + "=" * 60)
        print("  FGIP REASONING AGENT" + (" (DYNAMIC MODE)" if dynamic else ""))
        print("=" * 60)

        current_step = 1

        # 1. Find causal chains
        print(f"\n[{current_step}/{step_count}] Finding causal chains...")
        chains = self.find_causal_chains()
        print(f"  Found {len(chains)} causal paths")
        for c in chains[:5]:
            print(f"    {c.evidence_score:.0%} | {c.narrative[:80]}...")
        current_step += 1

        # 1b. Compression-based chain validation (if available)
        if HAS_COMPRESSION:
            print(f"\n[{current_step}/{step_count}] Validating chains with compression analysis...")
            chains = self.validate_chains_with_compression(chains)
            # Re-sort after compression boost
            chains.sort(key=lambda c: c.evidence_score, reverse=True)
            print(f"  Top chains after compression validation:")
            for c in chains[:3]:
                print(f"    {c.evidence_score:.0%} | {c.narrative[:80]}...")
            current_step += 1

        # 2. Find both-sides patterns
        print(f"\n[{current_step}/{step_count}] Detecting 'same actor both sides' patterns...")
        patterns = self.find_both_sides_patterns()
        print(f"  Found {len(patterns)} both-sides patterns")
        for p in patterns[:5]:
            print(f"    {p.confidence:.0%} | {p.actor_name}: {p.narrative[:60]}...")
        current_step += 1

        # 3. Find convergence nodes
        print(f"\n[{current_step}/{step_count}] Identifying convergence nodes...")
        convergence = self.find_convergence_nodes()
        print(f"  Found {len(convergence)} convergence points")
        for c in convergence[:5]:
            print(f"    {c['name']}: {c['layers_touched']} layers, {c['total_connections']} connections")
        current_step += 1

        # 4. Generate inferences
        print(f"\n[{current_step}/{step_count}] Generating inference proposals...")
        inferences = self.generate_inferences(patterns, chains)
        print(f"  Generated {len(inferences)} inference proposals")
        current_step += 1

        # 5. Score thesis (static)
        print(f"\n[{current_step}/{step_count}] Scoring thesis...")
        thesis_score, breakdown = self.score_thesis(patterns, chains, convergence)
        print(f"  Static thesis confidence: {thesis_score}%")
        for k, v in breakdown.items():
            print(f"    {k}: +{v}")
        current_step += 1

        # 6. Dynamic scenario modeling (optional)
        scenarios = []
        dynamic_score = thesis_score
        confidence_delta = 0.0
        if dynamic and HAS_ECONOMIC_MODEL:
            print(f"\n[{current_step}/{step_count}] Modeling dynamic scenarios...")
            scenarios = self.model_dynamic_scenarios()
            print(f"  Found {len(scenarios)} correction mechanisms")

            if scenarios:
                dynamic_score, breakdown, confidence_delta = self.score_thesis_with_dynamics(
                    patterns, chains, convergence, scenarios
                )
                print(f"\n  DYNAMIC THESIS SCORE: {dynamic_score}%")
                print(f"  Delta from static: +{confidence_delta}")

                for scenario in scenarios:
                    print(f"\n  Scenario: {scenario.mechanism.mechanism_id}")
                    print(f"    Extraction: {scenario.extraction_before:.1f}% -> {scenario.extraction_after:.1f}%")
                    print(f"    Thesis boost: +{scenario.thesis_delta:.1f}")
        elif dynamic and not HAS_ECONOMIC_MODEL:
            print(f"\n[{current_step}/{step_count}] Dynamic modeling skipped (economic_model not available)")

        # Stage if requested
        if stage and inferences:
            print("\n[STAGING] Writing proposals...")
            self.stage_inferences(inferences)

        # Build report
        final_score = dynamic_score if dynamic else thesis_score
        report = self._build_report(
            chains, patterns, convergence, inferences,
            final_score, breakdown, scenarios if dynamic else None
        )

        return ReasoningResult(
            causal_paths=chains,
            both_sides_patterns=patterns,
            convergence_nodes=convergence,
            proposed_inferences=inferences,
            thesis_score=final_score,
            report=report,
        )

    def _build_report(self, chains, patterns, convergence, inferences, score, breakdown, scenarios=None):
        lines = []
        lines.append("=" * 60)
        lines.append("  FGIP REASONING REPORT" + (" (DYNAMIC)" if scenarios else ""))
        lines.append(f"  Generated: {datetime.now(timezone.utc).isoformat()}Z")
        lines.append("=" * 60)

        lines.append(f"\n  THESIS SCORE: {score}%")
        lines.append(f"  Breakdown:")
        for k, v in breakdown.items():
            lines.append(f"    {k}: +{v}")

        # Include dynamic scenario summary if available
        if scenarios:
            lines.append(f"\n  DYNAMIC SCENARIOS ({len(scenarios)}):")
            for s in scenarios:
                lines.append(f"    {s.mechanism.mechanism_id}:")
                lines.append(f"      Effect: {s.mechanism.narrative}")
                lines.append(f"      Extraction: {s.extraction_before:.1f}% -> {s.extraction_after:.1f}%")
                lines.append(f"      Thesis boost: +{s.thesis_delta:.1f}")

            lines.append(f"\n  KEY INSIGHT:")
            lines.append(f"    The static extraction rate ({scenarios[0].extraction_before:.1f}%) includes")
            lines.append(f"    inflation CAUSED BY Fed printing. When correction mechanisms")
            lines.append(f"    reduce Fed printing, inflation drops, and extraction drops.")
            lines.append(f"    You can't use the disease as the argument against the cure.")

        lines.append(f"\n  BOTH-SIDES PATTERNS ({len(patterns)}):")
        for p in patterns:
            lines.append(f"    [{p.confidence:.0%}] {p.actor_name}")
            lines.append(f"         Problem edges: {len(p.problem_edges)}")
            lines.append(f"         Correction edges: {len(p.correction_edges)}")
            if p.ownership_pct:
                top_holdings = sorted(p.ownership_pct.items(), key=lambda x: x[1], reverse=True)[:5]
                for company, pct in top_holdings:
                    name = self.nodes.get(company, {}).get("name", company)
                    lines.append(f"         Owns {pct:.1f}% of {name}")

        lines.append(f"\n  TOP CAUSAL CHAINS ({len(chains)}):")
        for c in chains[:10]:
            lines.append(f"    [{c.evidence_score:.0%}] {c.narrative[:100]}")
            if c.weakest_link:
                lines.append(f"         Weakest: {c.weakest_link}")

        lines.append(f"\n  CONVERGENCE NODES ({len(convergence)}):")
        for c in convergence[:10]:
            lines.append(f"    {c['name']} ({c['node_type']}): "
                        f"{c['layers_touched']} layers, {c['total_connections']} connections")

        lines.append(f"\n  PROPOSED INFERENCES ({len(inferences)}):")
        for inf in inferences[:15]:
            src = self.nodes.get(inf["source_node_id"], {}).get("name", inf["source_node_id"])
            tgt = self.nodes.get(inf["target_node_id"], {}).get("name", inf["target_node_id"])
            lines.append(f"    [{inf['confidence']:.0%}] {src} --{inf['edge_type']}--> {tgt}")

        return "\n".join(lines)


# ─── CLI Entry Point ───────────────────────────────────────────────────────

def main():
    import sys
    import os
    db_path = sys.argv[1] if len(sys.argv) > 1 else "fgip.db"
    stage = "--no-stage" not in sys.argv
    dynamic = "--dynamic" in sys.argv

    agent = ReasoningAgent(db_path=db_path)
    result = agent.run(stage=stage, dynamic=dynamic)

    print("\n" + result.report)

    # Save report
    suffix = "_dynamic" if dynamic else ""
    report_path = f"data/artifacts/reasoning/reasoning_report{suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w") as f:
        f.write(result.report)
    print(f"\nReport saved: {report_path}")


if __name__ == "__main__":
    main()
