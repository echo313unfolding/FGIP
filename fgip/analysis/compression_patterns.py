"""
FGIP Compression Pattern Detection Module

Information-theoretic pattern detector using SHAKE256 fingerprinting and
compression-based similarity to find graph patterns.

Key Insight: Real causal chains compress better than random paths because
they have structural regularity. This validates chain candidates even if
they don't meet explicit edge-type gating rules.

Constraints (per ChatGPT review):
1. Deterministic: All operations reproducible from seed
2. Baseline-corrected: Compare against degree-matched random baselines
3. Auditable: JSON receipts with determinism seals
4. Scalable: Cache results, avoid O(n²) where possible
5. Hypothesis generator: NOT proof - mark as HYPOTHESIS unless Tier-0/1 edges

Usage:
    python3 -m fgip.analysis.compression_patterns fgip.db
"""

import hashlib
import json
import math
import os
import random
import sqlite3
import statistics
import tempfile
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional, Any


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class MotifTemplate:
    """Definition of a known graph pattern to detect."""
    motif_id: str
    name: str
    edge_sequence: List[str]
    node_type_sequence: List[str]
    min_nodes: int
    max_nodes: int
    description: str


@dataclass
class MotifMatch:
    """A detected instance of a motif pattern."""
    pattern_id: str                      # SHAKE256 fingerprint (hex)
    pattern_name: str                    # Motif name or "unknown"
    nodes_involved: List[str]
    edges_involved: List[str]
    supporting_evidence: Dict[int, int]  # tier -> count
    confidence: float                    # tier-weighted + rarity vs baseline
    description_length: int              # bytes to describe
    baseline_length: float               # expected random baseline
    compression_ratio: float             # description_length / baseline_length

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class NeighborhoodSketch:
    """Locality-sensitive hash of a node's neighborhood."""
    node_id: str
    depth: int
    shingles: Set[int]
    edge_type_counts: Dict[str, int]
    sketch_hash: str                     # SHAKE256 of sketch

    def to_dict(self) -> Dict:
        return {
            'node_id': self.node_id,
            'depth': self.depth,
            'shingle_count': len(self.shingles),
            'edge_type_counts': self.edge_type_counts,
            'sketch_hash': self.sketch_hash,
        }


@dataclass
class AnomalyResult:
    """Result of anomaly detection for a single node."""
    node_id: str
    node_name: str
    node_type: str
    anomaly_score: float                 # 0.0 = typical, 1.0 = unusual
    cohort_size: int
    cohort_similarity_mean: float
    cohort_similarity_std: float
    unusual_edges: List[str]

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class SimilarPair:
    """A pair of similar entities detected via compression."""
    node_a: str
    node_b: str
    similarity: float
    shared_edge_types: List[str]
    assertion_level: str = "HYPOTHESIS"  # Always HYPOTHESIS unless proven

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class CompressionReceipt:
    """Verification receipt per CLAUDE.md."""
    receipt_id: str
    operation: str
    timestamp: str
    seed: int
    impl_sha256: str
    input_hash: str
    output_hash: str
    evidence_level: str                  # "DEMONSTRATED" (not PROVEN)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class CompressionReport:
    """Full compression analysis report."""
    timestamp: str
    seed: int
    impl_sha256: str
    total_nodes: int
    total_edges: int
    evidence_level: str
    motif_matches: List[MotifMatch]
    similar_entities: List[SimilarPair]
    anomalies: List[AnomalyResult]
    random_baseline_stats: Dict[str, Dict[str, float]]
    receipt: CompressionReceipt

    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp,
            'seed': self.seed,
            'impl_sha256': self.impl_sha256,
            'total_nodes': self.total_nodes,
            'total_edges': self.total_edges,
            'evidence_level': self.evidence_level,
            'motif_matches': [m.to_dict() for m in self.motif_matches],
            'similar_entities': [s.to_dict() for s in self.similar_entities],
            'anomalies': [a.to_dict() for a in self.anomalies],
            'random_baseline_stats': self.random_baseline_stats,
            'receipt': self.receipt.to_dict(),
        }


# =============================================================================
# SURPRISAL-BASED CHAIN SCORING
# =============================================================================

@dataclass
class ChainToken:
    """
    A single token in a chain sequence for surprisal scoring.

    Uses abstract features (edge_type, node_types, tier) instead of
    verbose node IDs to avoid string-length dominating the signal.
    """
    edge_type: str          # "ENABLES", "REDUCES", etc.
    from_node_type: str     # "POLICY", "COMPANY", etc.
    to_node_type: str       # "ECONOMIC_EVENT", etc.
    tier: int               # 0, 1, 2, 3 (source quality)
    direction: str          # "FWD" or "REV"

    def to_symbol(self) -> str:
        """Convert to string symbol for counting."""
        return f"{self.edge_type}|{self.from_node_type}>{self.to_node_type}|T{self.tier}|{self.direction}"


@dataclass
class SurprisalResult:
    """Result of surprisal analysis on a chain."""
    mean_surprisal_bits: float      # Average surprisal per hop
    max_surprisal_bits: float       # Highest surprisal (weakest hop)
    weakest_hop_index: int          # Index of most surprising hop
    total_surprisal_bits: float     # Sum of all surprisals
    is_structured: bool             # Below baseline threshold
    baseline_mean: float            # Expected surprisal for random chains
    tokens: List[str]               # The token sequence

    def to_dict(self) -> Dict:
        return asdict(self)


class TransitionModel:
    """
    Markov transition model over chain tokens for surprisal scoring.

    Learns P(next_token | context) from the graph's existing paths,
    then uses surprisal = -log2(P) to measure structural regularity.
    """

    def __init__(self, order: int = 2, smoothing: float = 1.0):
        """
        Args:
            order: Context length (1=bigram, 2=trigram)
            smoothing: Laplace smoothing constant
        """
        self.order = order
        self.smoothing = smoothing
        # counts[context_tuple][next_symbol] = count
        self.counts: Dict[Tuple[str, ...], Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        # total_counts[context_tuple] = total count
        self.total_counts: Dict[Tuple[str, ...], int] = defaultdict(int)
        # vocabulary of all seen symbols
        self.vocabulary: Set[str] = set()
        self.trained = False

    def train(self, chains: List[List[str]]):
        """
        Train on sequences of token symbols.

        Args:
            chains: List of token sequences (each chain is List[str])
        """
        # Add START/END markers
        START = "<START>"
        END = "<END>"

        for chain in chains:
            # Pad with START markers
            padded = [START] * self.order + chain + [END]

            # Build vocabulary
            self.vocabulary.update(chain)

            # Count n-grams
            for i in range(self.order, len(padded)):
                context = tuple(padded[i - self.order : i])
                symbol = padded[i]

                self.counts[context][symbol] += 1
                self.total_counts[context] += 1

        self.vocabulary.add(START)
        self.vocabulary.add(END)
        self.trained = True

    def probability(self, context: Tuple[str, ...], symbol: str) -> float:
        """
        P(symbol | context) with Laplace smoothing.

        Args:
            context: Tuple of previous symbols
            symbol: Next symbol to predict

        Returns:
            Probability in [0, 1]
        """
        if not self.trained:
            return 1.0 / max(1, len(self.vocabulary))

        # Laplace smoothing
        count = self.counts[context][symbol] + self.smoothing
        total = self.total_counts[context] + self.smoothing * len(self.vocabulary)

        return count / total if total > 0 else 1.0 / max(1, len(self.vocabulary))

    def surprisal(self, context: Tuple[str, ...], symbol: str) -> float:
        """
        Surprisal = -log2(P(symbol | context)) in bits.

        High surprisal = unexpected/unusual
        Low surprisal = predictable/regular
        """
        prob = self.probability(context, symbol)
        # Clamp to avoid log(0)
        prob = max(prob, 1e-10)
        return -math.log2(prob)

    def score_chain(self, tokens: List[str]) -> Tuple[List[float], float, float]:
        """
        Score a chain by computing surprisal for each token.

        Args:
            tokens: List of token symbols

        Returns:
            Tuple of (per_token_surprisals, mean_surprisal, max_surprisal)
        """
        START = "<START>"
        padded = [START] * self.order + tokens

        surprisals = []
        for i in range(self.order, len(padded)):
            context = tuple(padded[i - self.order : i])
            symbol = padded[i]
            s = self.surprisal(context, symbol)
            surprisals.append(s)

        if not surprisals:
            return [], 0.0, 0.0

        return surprisals, statistics.mean(surprisals), max(surprisals)


# =============================================================================
# MOTIF TEMPLATES
# =============================================================================

MOTIF_TEMPLATES = {
    'revolving_door': MotifTemplate(
        motif_id='revolving_door',
        name='Revolving Door',
        edge_sequence=['EMPLOYED', 'LOBBIED_FOR'],
        node_type_sequence=['PERSON', 'AGENCY', 'ORGANIZATION'],
        min_nodes=3,
        max_nodes=4,
        description='Person moves from government to lobbying for same sector'
    ),
    'lobbying_triangle': MotifTemplate(
        motif_id='lobbying_triangle',
        name='Lobbying Triangle',
        edge_sequence=['LOBBIED_FOR', 'DONATED_TO', 'VOTED_FOR'],
        node_type_sequence=['ORGANIZATION', 'LEGISLATION', 'PERSON'],
        min_nodes=3,
        max_nodes=5,
        description='Organization lobbies, donates to legislators who vote for it'
    ),
    'both_sides_ownership': MotifTemplate(
        motif_id='both_sides_ownership',
        name='Both Sides Ownership',
        edge_sequence=['OWNS_SHARES', 'OWNS_SHARES'],
        node_type_sequence=['FINANCIAL_INST', 'COMPANY', 'COMPANY'],
        min_nodes=3,
        max_nodes=10,
        description='Same investor owns shares in problem and correction layers'
    ),
    'grant_to_ownership': MotifTemplate(
        motif_id='grant_to_ownership',
        name='Grant-to-Ownership Loop',
        edge_sequence=['AWARDED_GRANT', 'OWNS_SHARES'],
        node_type_sequence=['PROGRAM', 'COMPANY', 'FINANCIAL_INST'],
        min_nodes=3,
        max_nodes=5,
        description='Government grant flows to company owned by institutional investor'
    ),
    'amicus_to_benefit': MotifTemplate(
        motif_id='amicus_to_benefit',
        name='Amicus-to-Benefit',
        edge_sequence=['FILED_AMICUS', 'BENEFITS_FROM'],
        node_type_sequence=['ORGANIZATION', 'CASE', 'ORGANIZATION'],
        min_nodes=3,
        max_nodes=4,
        description='Organization files amicus brief in case that benefits them'
    ),
}


# =============================================================================
# CORE FUNCTIONS
# =============================================================================

def compute_file_sha256(filepath: str) -> str:
    """Compute SHA256 of a file."""
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def compute_data_sha256(data: Any) -> str:
    """Compute SHA256 of JSON-serializable data."""
    canonical = json.dumps(data, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def canonical_subgraph_bytes(nodes: List[str], edges: List[Dict]) -> bytes:
    """
    Create stable, reproducible serialization of a subgraph.

    Ensures identical subgraphs produce identical bytes regardless of
    input order.
    """
    # Sort nodes
    sorted_nodes = sorted(nodes)

    # Sort edges by (type, from, to)
    edge_tuples = sorted([
        (e.get('edge_type', ''), e.get('from_node_id', ''), e.get('to_node_id', ''))
        for e in edges
    ])

    canonical = {
        'n': sorted_nodes,
        'e': edge_tuples,
    }

    return json.dumps(
        canonical,
        sort_keys=True,
        separators=(',', ':')
    ).encode('utf-8')


def fingerprint_subgraph(
    nodes: List[str],
    edges: List[Dict],
    digest_size: int = 20
) -> str:
    """
    Generate SHAKE256 fingerprint of canonical subgraph.

    Returns hex string for JSON compatibility.
    """
    canonical = canonical_subgraph_bytes(nodes, edges)
    shake = hashlib.shake_256(canonical)
    return shake.digest(digest_size).hex()


def jaccard_similarity(set_a: Set, set_b: Set) -> float:
    """Compute Jaccard similarity between two sets."""
    if not set_a and not set_b:
        return 1.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


# =============================================================================
# NEIGHBORHOOD SKETCHING
# =============================================================================

def node_neighborhood_sketch(
    node_id: str,
    adjacency: Dict[str, List[Dict]],
    reverse_adj: Dict[str, List[Dict]],
    depth: int = 2,
    num_shingles: int = 64
) -> NeighborhoodSketch:
    """
    Create locality-sensitive hash of node's neighborhood.

    Uses BFS to collect edge patterns, then creates MinHash-style shingles.
    """
    # BFS to collect edge patterns
    visited = {node_id}
    patterns = []  # (hop, direction, edge_type) tuples
    edge_type_counts = defaultdict(int)

    queue = deque([(node_id, 0)])

    while queue:
        current, hop = queue.popleft()
        if hop >= depth:
            continue

        # Outgoing edges
        for edge in adjacency.get(current, []):
            edge_type = edge.get('edge_type', 'UNKNOWN')
            target = edge.get('to_node_id', '')

            patterns.append((hop, 'out', edge_type))
            edge_type_counts[edge_type] += 1

            if target not in visited:
                visited.add(target)
                queue.append((target, hop + 1))

        # Incoming edges
        for edge in reverse_adj.get(current, []):
            edge_type = edge.get('edge_type', 'UNKNOWN')
            source = edge.get('from_node_id', '')

            patterns.append((hop, 'in', edge_type))
            edge_type_counts[edge_type] += 1

            if source not in visited:
                visited.add(source)
                queue.append((source, hop + 1))

    # Create shingles (hash of pattern sequences)
    shingles = set()
    patterns_sorted = sorted(patterns)

    for i in range(len(patterns_sorted)):
        # Single patterns
        shingle = hash(patterns_sorted[i])
        shingles.add(shingle % (2**31))

        # Pairs
        if i + 1 < len(patterns_sorted):
            pair = (patterns_sorted[i], patterns_sorted[i+1])
            shingles.add(hash(pair) % (2**31))

    # Limit to num_shingles (keep smallest for MinHash approximation)
    if len(shingles) > num_shingles:
        shingles = set(sorted(shingles)[:num_shingles])

    # Create sketch hash
    sketch_data = json.dumps({
        'patterns': patterns_sorted,
        'counts': dict(edge_type_counts),
    }, sort_keys=True)
    sketch_hash = hashlib.shake_256(sketch_data.encode()).hexdigest(16)

    return NeighborhoodSketch(
        node_id=node_id,
        depth=depth,
        shingles=shingles,
        edge_type_counts=dict(edge_type_counts),
        sketch_hash=sketch_hash,
    )


def similarity_search(
    sketches: Dict[str, NeighborhoodSketch],
    topk: int = 20,
    similarity_threshold: float = 0.3
) -> List[SimilarPair]:
    """
    Find node pairs with similar neighborhoods using shingle comparison.

    Returns pairs above threshold, sorted by similarity.
    """
    pairs = []
    nodes = list(sketches.keys())

    # O(n²) but with early pruning
    for i, node_a in enumerate(nodes):
        sketch_a = sketches[node_a]

        for node_b in nodes[i+1:]:
            sketch_b = sketches[node_b]

            # Quick reject: no shared shingles
            if not sketch_a.shingles & sketch_b.shingles:
                continue

            similarity = jaccard_similarity(sketch_a.shingles, sketch_b.shingles)

            if similarity >= similarity_threshold:
                # Find shared edge types
                shared = set(sketch_a.edge_type_counts.keys()) & set(sketch_b.edge_type_counts.keys())

                pairs.append(SimilarPair(
                    node_a=node_a,
                    node_b=node_b,
                    similarity=similarity,
                    shared_edge_types=list(shared),
                    assertion_level="HYPOTHESIS",  # Always hypothesis
                ))

    # Sort by similarity, take top-k
    pairs.sort(key=lambda p: p.similarity, reverse=True)
    return pairs[:topk]


# =============================================================================
# BASELINE COMPUTATION
# =============================================================================

def random_walk(
    adjacency: Dict[str, List[Dict]],
    start: str,
    length: int,
    rng: random.Random
) -> Tuple[List[str], List[Dict]]:
    """Perform random walk from start node."""
    nodes = [start]
    edges = []
    current = start

    for _ in range(length):
        neighbors = adjacency.get(current, [])
        if not neighbors:
            break

        edge = rng.choice(neighbors)
        edges.append(edge)
        current = edge.get('to_node_id', '')
        nodes.append(current)

    return nodes, edges


def compute_random_baseline(
    adjacency: Dict[str, List[Dict]],
    all_nodes: List[str],
    path_length: int,
    samples: int = 500,
    seed: int = 42
) -> Dict[str, float]:
    """
    Compute baseline description length for random paths.

    Real causal chains should compress BETTER (lower length) than these.
    """
    rng = random.Random(seed)
    lengths = []

    for _ in range(samples):
        start = rng.choice(all_nodes)
        nodes, edges = random_walk(adjacency, start, path_length, rng)

        if len(nodes) >= 2:
            canonical = canonical_subgraph_bytes(nodes, edges)
            lengths.append(len(canonical))

    if not lengths:
        return {'mean': 0, 'std': 0, 'p25': 0, 'p50': 0, 'p75': 0}

    return {
        'mean': statistics.mean(lengths),
        'std': statistics.stdev(lengths) if len(lengths) > 1 else 0,
        'p25': statistics.quantiles(lengths, n=4)[0] if len(lengths) >= 4 else min(lengths),
        'p50': statistics.median(lengths),
        'p75': statistics.quantiles(lengths, n=4)[2] if len(lengths) >= 4 else max(lengths),
    }


# =============================================================================
# ANOMALY DETECTION
# =============================================================================

def compute_anomaly_score(
    node_id: str,
    sketch: NeighborhoodSketch,
    cohort_sketches: List[NeighborhoodSketch],
    nodes: Dict[str, Dict]
) -> AnomalyResult:
    """
    Score how anomalous a node's neighborhood is vs its cohort.

    Cohort = nodes of same type with similar degree.
    """
    if not cohort_sketches:
        return AnomalyResult(
            node_id=node_id,
            node_name=nodes.get(node_id, {}).get('name', node_id),
            node_type=nodes.get(node_id, {}).get('node_type', 'UNKNOWN'),
            anomaly_score=0.0,
            cohort_size=0,
            cohort_similarity_mean=0.0,
            cohort_similarity_std=0.0,
            unusual_edges=[],
        )

    # Compute similarity to each cohort member
    similarities = []
    for cohort_sketch in cohort_sketches:
        if cohort_sketch.node_id != node_id:
            sim = jaccard_similarity(sketch.shingles, cohort_sketch.shingles)
            similarities.append(sim)

    if not similarities:
        return AnomalyResult(
            node_id=node_id,
            node_name=nodes.get(node_id, {}).get('name', node_id),
            node_type=nodes.get(node_id, {}).get('node_type', 'UNKNOWN'),
            anomaly_score=0.0,
            cohort_size=0,
            cohort_similarity_mean=0.0,
            cohort_similarity_std=0.0,
            unusual_edges=[],
        )

    mean_sim = statistics.mean(similarities)
    std_sim = statistics.stdev(similarities) if len(similarities) > 1 else 0.01

    # Anomaly = low similarity to cohort = high anomaly score
    # Normalize: 0 = average, 1 = very unusual
    anomaly = max(0, 1 - mean_sim)

    # Find unusual edge types (present in this node but rare in cohort)
    cohort_edge_types = defaultdict(int)
    for cs in cohort_sketches:
        for et in cs.edge_type_counts:
            cohort_edge_types[et] += 1

    unusual = []
    cohort_size = len(cohort_sketches)
    for et in sketch.edge_type_counts:
        if cohort_edge_types[et] < cohort_size * 0.2:  # Less than 20% have this
            unusual.append(et)

    return AnomalyResult(
        node_id=node_id,
        node_name=nodes.get(node_id, {}).get('name', node_id),
        node_type=nodes.get(node_id, {}).get('node_type', 'UNKNOWN'),
        anomaly_score=anomaly,
        cohort_size=cohort_size,
        cohort_similarity_mean=mean_sim,
        cohort_similarity_std=std_sim,
        unusual_edges=unusual,
    )


# =============================================================================
# MOTIF SCANNING
# =============================================================================

def scan_for_motif(
    template: MotifTemplate,
    adjacency: Dict[str, List[Dict]],
    nodes: Dict[str, Dict],
    sources_by_edge: Dict[str, List[Dict]],
    baseline_stats: Dict[str, float],
    max_matches: int = 50
) -> List[MotifMatch]:
    """
    Scan graph for instances of a specific motif template.
    """
    matches = []
    edge_seq = template.edge_sequence

    if not edge_seq:
        return matches

    # Find candidate start nodes
    for node_id, node in nodes.items():
        # Check outgoing edges for first edge type in sequence
        for edge in adjacency.get(node_id, []):
            if edge.get('edge_type') != edge_seq[0]:
                continue

            # Try to complete the sequence via DFS
            path_nodes = [node_id]
            path_edges = [edge]
            current = edge.get('to_node_id', '')
            path_nodes.append(current)

            # Continue matching sequence
            matched = True
            for i, next_edge_type in enumerate(edge_seq[1:], 1):
                found_next = False
                for next_edge in adjacency.get(current, []):
                    if next_edge.get('edge_type') == next_edge_type:
                        path_edges.append(next_edge)
                        current = next_edge.get('to_node_id', '')
                        path_nodes.append(current)
                        found_next = True
                        break

                if not found_next:
                    matched = False
                    break

            if matched and len(path_nodes) >= template.min_nodes:
                # Compute evidence tier distribution
                evidence = defaultdict(int)
                for e in path_edges:
                    edge_id = e.get('edge_id', '')
                    sources = sources_by_edge.get(edge_id, [])
                    for src in sources:
                        tier = src.get('tier', 2)
                        evidence[tier] += 1

                # Compute fingerprint
                fp = fingerprint_subgraph(path_nodes, path_edges)

                # Compute description length
                canonical = canonical_subgraph_bytes(path_nodes, path_edges)
                desc_len = len(canonical)

                # Compare to baseline
                baseline_key = f"path_{len(path_edges)}"
                baseline = baseline_stats.get(baseline_key, {'p50': desc_len})
                baseline_len = baseline.get('p50', desc_len)

                compression_ratio = desc_len / baseline_len if baseline_len > 0 else 1.0

                # Confidence: tier-weighted + compression bonus
                tier_score = evidence.get(0, 0) * 0.4 + evidence.get(1, 0) * 0.3 + evidence.get(2, 0) * 0.1
                compression_bonus = max(0, (1 - compression_ratio) * 0.3)
                confidence = min(0.95, 0.5 + tier_score * 0.1 + compression_bonus)

                matches.append(MotifMatch(
                    pattern_id=fp,
                    pattern_name=template.name,
                    nodes_involved=path_nodes,
                    edges_involved=[e.get('edge_id', '') for e in path_edges],
                    supporting_evidence=dict(evidence),
                    confidence=confidence,
                    description_length=desc_len,
                    baseline_length=baseline_len,
                    compression_ratio=compression_ratio,
                ))

                if len(matches) >= max_matches:
                    return matches

    return matches


# =============================================================================
# MAIN ANALYZER CLASS
# =============================================================================

class CompressionPatternAnalyzer:
    """
    Information-theoretic pattern detector for FGIP graph.

    Key insight: Real causal chains compress better than random paths
    because they have structural regularity.
    """

    def __init__(self, db_path: str = 'fgip.db', seed: int = 42):
        self.db_path = db_path
        self.seed = seed
        self.conn = None
        self.nodes = {}
        self.edges = []
        self.adjacency = {}
        self.reverse_adj = {}
        self.sources_by_edge = {}
        self.baseline_cache = {}
        # Surprisal scoring
        self.transition_model: Optional[TransitionModel] = None
        self.surprisal_baseline: Optional[Dict[str, float]] = None

    def connect(self):
        """Connect to database and load graph."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._load_graph()

    def _load_graph(self):
        """Load graph into memory for fast access."""
        # Load nodes
        rows = self.conn.execute("SELECT * FROM nodes").fetchall()
        self.nodes = {r['node_id']: dict(r) for r in rows}

        # Load edges
        rows = self.conn.execute("SELECT * FROM edges").fetchall()
        self.edges = [dict(r) for r in rows]

        # Build adjacency lists
        self.adjacency = defaultdict(list)
        self.reverse_adj = defaultdict(list)

        for edge in self.edges:
            from_n = edge.get('from_node_id', '')
            to_n = edge.get('to_node_id', '')
            self.adjacency[from_n].append(edge)
            self.reverse_adj[to_n].append(edge)

        # Load sources by edge
        try:
            rows = self.conn.execute("""
                SELECT e.edge_id, s.tier, s.url
                FROM edges e
                LEFT JOIN claims c ON e.claim_id = c.claim_id
                LEFT JOIN claim_sources cs ON c.claim_id = cs.claim_id
                LEFT JOIN sources s ON cs.source_id = s.source_id
            """).fetchall()

            for r in rows:
                edge_id = r['edge_id']
                if edge_id not in self.sources_by_edge:
                    self.sources_by_edge[edge_id] = []
                if r['tier'] is not None:
                    self.sources_by_edge[edge_id].append({
                        'tier': r['tier'],
                        'url': r['url'],
                    })
        except Exception:
            pass  # Sources table may not have all columns

    def _compute_baselines(self):
        """Compute random baselines for various path lengths."""
        all_nodes = list(self.nodes.keys())

        for length in [2, 3, 4, 5]:
            key = f"path_{length}"
            if key not in self.baseline_cache:
                self.baseline_cache[key] = compute_random_baseline(
                    self.adjacency,
                    all_nodes,
                    length,
                    samples=500,
                    seed=self.seed,
                )

    def run_full_analysis(
        self,
        include_sketches: bool = True,
        include_anomalies: bool = True,
        include_similarity: bool = True,
    ) -> CompressionReport:
        """Run complete compression pattern analysis."""
        timestamp = datetime.utcnow().isoformat() + 'Z'
        impl_sha = compute_file_sha256(__file__) if os.path.exists(__file__) else 'unknown'

        # Compute baselines
        self._compute_baselines()

        # Scan for motifs
        all_motif_matches = []
        for template in MOTIF_TEMPLATES.values():
            matches = scan_for_motif(
                template,
                self.adjacency,
                self.nodes,
                self.sources_by_edge,
                self.baseline_cache,
                max_matches=50,
            )
            all_motif_matches.extend(matches)

        # Deduplicate by fingerprint
        seen_fps = set()
        unique_matches = []
        for m in all_motif_matches:
            if m.pattern_id not in seen_fps:
                seen_fps.add(m.pattern_id)
                unique_matches.append(m)

        # Sort by confidence
        unique_matches.sort(key=lambda m: m.confidence, reverse=True)

        # Compute neighborhood sketches
        sketches = {}
        if include_sketches or include_anomalies or include_similarity:
            for node_id in self.nodes:
                sketches[node_id] = node_neighborhood_sketch(
                    node_id,
                    self.adjacency,
                    self.reverse_adj,
                    depth=2,
                )

        # Find similar entities
        similar = []
        if include_similarity and sketches:
            similar = similarity_search(sketches, topk=30, similarity_threshold=0.3)

        # Compute anomalies
        anomalies = []
        if include_anomalies and sketches:
            # Group by node type for cohort comparison
            by_type = defaultdict(list)
            for node_id, sketch in sketches.items():
                node_type = self.nodes.get(node_id, {}).get('node_type', 'UNKNOWN')
                by_type[node_type].append(sketch)

            # Score each node against its cohort
            for node_id, sketch in sketches.items():
                node_type = self.nodes.get(node_id, {}).get('node_type', 'UNKNOWN')
                cohort = by_type.get(node_type, [])

                if len(cohort) >= 5:  # Only score if cohort is meaningful
                    result = compute_anomaly_score(node_id, sketch, cohort, self.nodes)
                    if result.anomaly_score > 0.5:  # Only report significant anomalies
                        anomalies.append(result)

            # Sort by anomaly score
            anomalies.sort(key=lambda a: a.anomaly_score, reverse=True)
            anomalies = anomalies[:20]  # Top 20

        # Create receipt
        input_hash = compute_data_sha256({
            'nodes': len(self.nodes),
            'edges': len(self.edges),
            'seed': self.seed,
        })

        output_hash = compute_data_sha256({
            'motifs': len(unique_matches),
            'similar': len(similar),
            'anomalies': len(anomalies),
        })

        receipt = CompressionReceipt(
            receipt_id=str(uuid.uuid4()),
            operation='compression_analysis',
            timestamp=timestamp,
            seed=self.seed,
            impl_sha256=impl_sha,
            input_hash=input_hash,
            output_hash=output_hash,
            evidence_level='DEMONSTRATED',  # Not PROVEN until verified
        )

        return CompressionReport(
            timestamp=timestamp,
            seed=self.seed,
            impl_sha256=impl_sha,
            total_nodes=len(self.nodes),
            total_edges=len(self.edges),
            evidence_level='DEMONSTRATED',
            motif_matches=unique_matches,
            similar_entities=similar,
            anomalies=anomalies,
            random_baseline_stats=self.baseline_cache,
            receipt=receipt,
        )

    def validate_causal_chain(
        self,
        chain_nodes: List[str],
        chain_edges: List[str]
    ) -> Dict[str, Any]:
        """
        Validate a causal chain using compression.

        Returns dict with compression metrics and validation result.
        """
        # Get edge data
        edges = []
        for edge_id in chain_edges:
            for e in self.edges:
                if e.get('edge_id') == edge_id:
                    edges.append(e)
                    break

        if not edges:
            return {
                'compression_ratio': 1.0,
                'is_compressible': False,
                'compression_bonus': 0.0,
                'description_length': 0,
                'baseline_p50': 0,
            }

        # Compute description length
        canonical = canonical_subgraph_bytes(chain_nodes, edges)
        desc_len = len(canonical)

        # Get baseline for this path length
        path_len = len(edges)
        baseline_key = f"path_{path_len}"

        if baseline_key not in self.baseline_cache:
            self._compute_baselines()

        baseline = self.baseline_cache.get(baseline_key, {'p50': desc_len})
        baseline_p50 = baseline.get('p50', desc_len)

        compression_ratio = desc_len / baseline_p50 if baseline_p50 > 0 else 1.0
        is_compressible = compression_ratio < 1.0
        compression_bonus = max(0, (1 - compression_ratio) * 0.2)

        return {
            'compression_ratio': compression_ratio,
            'is_compressible': is_compressible,
            'compression_bonus': compression_bonus,
            'description_length': desc_len,
            'baseline_p50': baseline_p50,
        }

    # ─── Surprisal-Based Scoring ────────────────────────────────────────

    def _edge_to_token(
        self,
        edge: Dict,
        direction: str = "FWD"
    ) -> ChainToken:
        """Convert a single edge to a ChainToken."""
        from_id = edge.get('from_node_id', '')
        to_id = edge.get('to_node_id', '')

        from_type = self.nodes.get(from_id, {}).get('node_type', 'UNKNOWN')
        to_type = self.nodes.get(to_id, {}).get('node_type', 'UNKNOWN')

        edge_type = edge.get('edge_type', 'UNKNOWN')

        # Get best tier from sources
        edge_id = edge.get('edge_id', '')
        sources = self.sources_by_edge.get(edge_id, [])
        tier = min((s.get('tier', 3) for s in sources), default=3)

        return ChainToken(
            edge_type=edge_type,
            from_node_type=from_type,
            to_node_type=to_type,
            tier=tier,
            direction=direction,
        )

    def _chain_to_tokens(
        self,
        chain_nodes: List[str],
        chain_edges: List[str]
    ) -> List[ChainToken]:
        """
        Convert a chain (node IDs + edge IDs) into a sequence of tokens.

        Each token captures structural features without verbose IDs.
        """
        tokens = []

        for edge_id in chain_edges:
            # Find edge data
            edge = None
            for e in self.edges:
                if e.get('edge_id') == edge_id:
                    edge = e
                    break

            if edge is None:
                # Try without _rev suffix (for reverse edges)
                clean_id = edge_id.rstrip('_rev') if edge_id.endswith('_rev') else edge_id
                for e in self.edges:
                    if e.get('edge_id') == clean_id:
                        edge = e
                        break

            if edge:
                direction = "REV" if edge_id.endswith('_rev') else "FWD"
                tokens.append(self._edge_to_token(edge, direction))

        return tokens

    def _extract_training_chains(self, max_chains: int = 1000) -> List[List[str]]:
        """
        Extract token sequences from existing graph paths for training.

        Uses random walks and known good patterns.
        """
        rng = random.Random(self.seed)
        chains = []
        all_node_ids = list(self.nodes.keys())

        if not all_node_ids:
            return chains

        # Random walks of various lengths
        for _ in range(max_chains):
            start = rng.choice(all_node_ids)
            length = rng.randint(2, 5)

            nodes, edges = random_walk(
                self.adjacency,
                start,
                length,
                rng
            )

            if len(edges) >= 1:
                # Convert to tokens
                tokens = []
                for edge in edges:
                    token = self._edge_to_token(edge, "FWD")
                    tokens.append(token.to_symbol())

                if tokens:
                    chains.append(tokens)

        return chains

    def _train_transition_model(self):
        """Train the transition model on graph paths."""
        chains = self._extract_training_chains(max_chains=1000)

        if not chains:
            # Fallback: create minimal model
            self.transition_model = TransitionModel(order=2)
            self.transition_model.trained = True
            return

        self.transition_model = TransitionModel(order=2, smoothing=1.0)
        self.transition_model.train(chains)

        # Compute baseline surprisal from training chains
        if chains:
            surprisals = []
            for chain in chains[:200]:  # Sample for baseline
                _, mean_s, _ = self.transition_model.score_chain(chain)
                surprisals.append(mean_s)

            self.surprisal_baseline = {
                'mean': statistics.mean(surprisals) if surprisals else 5.0,
                'std': statistics.stdev(surprisals) if len(surprisals) > 1 else 1.0,
                'p50': statistics.median(surprisals) if surprisals else 5.0,
            }
        else:
            self.surprisal_baseline = {'mean': 5.0, 'std': 1.0, 'p50': 5.0}

    def chain_surprisal_score(
        self,
        chain_nodes: List[str],
        chain_edges: List[str]
    ) -> SurprisalResult:
        """
        Score a chain using surprisal (information-theoretic regularity).

        Low surprisal = chain follows common patterns = structurally regular
        High surprisal = unusual path = potential weak link or anomaly

        This avoids the verbose node ID problem because we use abstract
        tokens (edge_type, node_types, tier) instead of string lengths.

        Args:
            chain_nodes: List of node IDs in the chain
            chain_edges: List of edge IDs in the chain

        Returns:
            SurprisalResult with scoring metrics
        """
        # Ensure model is trained
        if self.transition_model is None:
            self._train_transition_model()

        # Convert chain to tokens
        tokens = self._chain_to_tokens(chain_nodes, chain_edges)
        token_symbols = [t.to_symbol() for t in tokens]

        if not token_symbols:
            return SurprisalResult(
                mean_surprisal_bits=float('inf'),
                max_surprisal_bits=float('inf'),
                weakest_hop_index=0,
                total_surprisal_bits=float('inf'),
                is_structured=False,
                baseline_mean=self.surprisal_baseline.get('mean', 5.0) if self.surprisal_baseline else 5.0,
                tokens=[],
            )

        # Score chain
        per_token, mean_s, max_s = self.transition_model.score_chain(token_symbols)

        # Find weakest hop (highest surprisal)
        weakest_idx = per_token.index(max_s) if per_token else 0

        # Compare to baseline
        baseline_mean = self.surprisal_baseline.get('mean', 5.0) if self.surprisal_baseline else 5.0

        # Structured = mean surprisal below baseline
        is_structured = mean_s < baseline_mean

        return SurprisalResult(
            mean_surprisal_bits=mean_s,
            max_surprisal_bits=max_s,
            weakest_hop_index=weakest_idx,
            total_surprisal_bits=sum(per_token),
            is_structured=is_structured,
            baseline_mean=baseline_mean,
            tokens=token_symbols,
        )


# =============================================================================
# FILE I/O
# =============================================================================

def atomic_write_report(report: CompressionReport, path: str) -> None:
    """Atomic file write: temp -> fsync -> rename."""
    dir_path = os.path.dirname(path) or '.'
    os.makedirs(dir_path, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode='w',
        dir=dir_path,
        delete=False,
        suffix='.tmp'
    ) as f:
        json.dump(report.to_dict(), f, indent=2)
        f.flush()
        os.fsync(f.fileno())
        temp_path = f.name

    os.rename(temp_path, path)


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

def main():
    """CLI: python3 -m fgip.analysis.compression_patterns fgip.db"""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description='FGIP Compression Pattern Analysis'
    )
    parser.add_argument('db_path', nargs='?', default='fgip.db')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--output', default='data/reports/compression_report.json')
    parser.add_argument('--no-sketches', action='store_true', help='Skip neighborhood sketching')
    parser.add_argument('--no-anomalies', action='store_true', help='Skip anomaly detection')
    parser.add_argument('--no-similarity', action='store_true', help='Skip similarity search')

    args = parser.parse_args()

    print(f"FGIP Compression Pattern Analysis")
    print(f"=" * 50)
    print(f"Database: {args.db_path}")
    print(f"Seed: {args.seed}")
    print()

    analyzer = CompressionPatternAnalyzer(
        db_path=args.db_path,
        seed=args.seed,
    )
    analyzer.connect()

    print(f"Loaded: {len(analyzer.nodes)} nodes, {len(analyzer.edges)} edges")
    print()

    print("Running analysis...")
    report = analyzer.run_full_analysis(
        include_sketches=not args.no_sketches,
        include_anomalies=not args.no_anomalies,
        include_similarity=not args.no_similarity,
    )

    # Save report
    atomic_write_report(report, args.output)

    print()
    print(f"Results:")
    print(f"  Motif matches: {len(report.motif_matches)}")
    print(f"  Similar entity pairs: {len(report.similar_entities)}")
    print(f"  Anomalies detected: {len(report.anomalies)}")
    print()

    # Show top motifs
    if report.motif_matches:
        print("Top Motif Matches:")
        for m in report.motif_matches[:5]:
            print(f"  [{m.confidence:.0%}] {m.pattern_name}")
            print(f"       Nodes: {' → '.join(m.nodes_involved[:4])}")
            print(f"       Compression: {m.compression_ratio:.2f}")

    # Show top similar pairs
    if report.similar_entities:
        print()
        print("Top Similar Entity Pairs:")
        for s in report.similar_entities[:5]:
            print(f"  [{s.similarity:.0%}] {s.node_a} ~ {s.node_b}")
            print(f"       Shared: {', '.join(s.shared_edge_types[:3])}")

    # Show top anomalies
    if report.anomalies:
        print()
        print("Top Anomalies:")
        for a in report.anomalies[:5]:
            print(f"  [{a.anomaly_score:.0%}] {a.node_name} ({a.node_type})")
            if a.unusual_edges:
                print(f"       Unusual: {', '.join(a.unusual_edges[:3])}")

    print()
    print(f"Report saved: {args.output}")
    print(f"Evidence level: {report.evidence_level}")

    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
