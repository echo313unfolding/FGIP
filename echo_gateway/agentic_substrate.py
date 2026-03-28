"""
FibPi3D Substrate Integration for Agentic Reasoning.

WO-AGENTIC-SUBSTRATE-01

Bridges the FibPi3D lattice geometry into the agentic cognition system:
- Maps reasoning steps to nodes on golden-spiral lattice
- Uses wave propagation for "resonance" between thoughts
- Laplacian diffusion for coherence detection across scales

This creates a "wave memory" where:
- Nearby thoughts in concept space have stronger influence
- Contradictions create destructive interference
- Coherent chains create constructive resonance

Inspired by:
- Nature's scale-invariant self-organization
- Neural avalanche dynamics (criticality)
- The Se = H × C × D formula from regime_classifier
"""

import sys
import math
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Import FibPi3D from lattice_test
LATTICE_PATH = Path.home() / "lattice_test"
if str(LATTICE_PATH) not in sys.path:
    sys.path.insert(0, str(LATTICE_PATH))

try:
    from fibpi_lattice import (
        build_fibpi_graph,
        fibpi_laplacian,
        fibpi3d_coord,
        PHI,
        GOLDEN_ANGLE,
    )
    FIBPI_AVAILABLE = True
except ImportError:
    FIBPI_AVAILABLE = False
    PHI = 1.618033988749895
    GOLDEN_ANGLE = 2.39996322972865332


@dataclass
class ResonanceField:
    """
    Wave field over reasoning steps.

    Each reasoning step is a node with:
    - Position in FibPi3D space (based on content hash)
    - Amplitude (confidence contribution)
    - Phase (support vs contradiction)
    """
    n_nodes: int
    amplitudes: List[float] = field(default_factory=list)
    phases: List[float] = field(default_factory=list)  # 0 = support, π = contradict
    node_labels: List[str] = field(default_factory=list)
    graph: Optional[Dict] = None

    def total_energy(self) -> float:
        """Total energy in the field (sum of squared amplitudes)."""
        return sum(a * a for a in self.amplitudes)

    def coherence(self) -> float:
        """
        Measure coherence as constructive interference ratio.

        High coherence = phases aligned (all support or all contradict)
        Low coherence = phases mixed (interference)
        """
        if not self.phases:
            return 0.5

        # Compute resultant vector
        real_sum = sum(a * math.cos(p) for a, p in zip(self.amplitudes, self.phases))
        imag_sum = sum(a * math.sin(p) for a, p in zip(self.amplitudes, self.phases))
        resultant = math.sqrt(real_sum**2 + imag_sum**2)

        total_amp = sum(self.amplitudes)
        if total_amp == 0:
            return 0.5

        return resultant / total_amp

    def to_dict(self) -> Dict[str, Any]:
        return {
            "n_nodes": self.n_nodes,
            "total_energy": self.total_energy(),
            "coherence": self.coherence(),
            "node_labels": self.node_labels[:10],  # First 10 for brevity
        }


def content_to_lattice_index(content: str, max_nodes: int = 1000) -> int:
    """
    Map content to a lattice index using hash.

    Similar content will map to nearby indices due to
    the golden-angle spacing creating quasi-random but deterministic positions.
    """
    # Hash content
    h = hashlib.md5(content.encode()).hexdigest()
    # Convert to int and mod
    return int(h[:8], 16) % max_nodes


def content_to_phase(content: str) -> float:
    """
    Determine phase based on content sentiment.

    Returns:
        0 = strong support
        π/2 = neutral
        π = contradiction
    """
    # Simple keyword-based phase detection
    support_words = ["confirms", "supports", "shows", "proves", "evidence", "found", "yes", "correct"]
    contradict_words = ["contradicts", "however", "but", "unlike", "no", "wrong", "missing", "error"]

    content_lower = content.lower()

    support_count = sum(1 for w in support_words if w in content_lower)
    contradict_count = sum(1 for w in contradict_words if w in content_lower)

    if support_count > contradict_count:
        return 0.0  # In phase (constructive)
    elif contradict_count > support_count:
        return math.pi  # Out of phase (destructive)
    else:
        return math.pi / 2  # Neutral


class FibPiReasoningSubstrate:
    """
    FibPi3D substrate for reasoning wave dynamics.

    Maps reasoning steps to a golden-spiral lattice and uses
    wave propagation to find coherence and resonance patterns.
    """

    def __init__(self, n_nodes: int = 256, k_neighbors: int = 6):
        """
        Initialize the substrate.

        Args:
            n_nodes: Number of nodes in the FibPi3D lattice
            k_neighbors: Number of nearest neighbors per node
        """
        self.n_nodes = n_nodes
        self.k_neighbors = k_neighbors
        self.graph = None

        if FIBPI_AVAILABLE:
            self.graph = build_fibpi_graph(n_nodes, k_neighbors, mode="phi")

        # Initialize resonance field
        self.field = ResonanceField(n_nodes=n_nodes)
        self.field.amplitudes = [0.0] * n_nodes
        self.field.phases = [0.0] * n_nodes
        self.field.node_labels = [""] * n_nodes
        self.field.graph = self.graph

        # Track which nodes are active
        self.active_nodes: List[int] = []

    def inject_thought(
        self,
        content: str,
        amplitude: float = 1.0,
        label: str = "",
    ) -> int:
        """
        Inject a thought into the substrate as a wave excitation.

        Args:
            content: The thought content
            amplitude: Wave amplitude (confidence weight)
            label: Optional label for tracking

        Returns:
            Node index where thought was injected
        """
        # Map content to lattice position
        node_idx = content_to_lattice_index(content, self.n_nodes)

        # Determine phase from content sentiment
        phase = content_to_phase(content)

        # Inject into field (additive - waves superpose)
        self.field.amplitudes[node_idx] += amplitude

        # Phase blending (weighted by amplitude)
        old_amp = self.field.amplitudes[node_idx] - amplitude
        if old_amp > 0:
            # Blend phases weighted by amplitude
            old_phase = self.field.phases[node_idx]
            self.field.phases[node_idx] = (old_phase * old_amp + phase * amplitude) / self.field.amplitudes[node_idx]
        else:
            self.field.phases[node_idx] = phase

        # Track label
        if label:
            self.field.node_labels[node_idx] = label

        # Track active nodes
        if node_idx not in self.active_nodes:
            self.active_nodes.append(node_idx)

        return node_idx

    def propagate(self, steps: int = 1, diffusion_rate: float = 0.1) -> None:
        """
        Propagate waves through the lattice using Laplacian diffusion.

        This spreads influence from excited nodes to neighbors,
        creating resonance patterns.
        """
        if not FIBPI_AVAILABLE or self.graph is None:
            return

        for _ in range(steps):
            new_amplitudes = self.field.amplitudes.copy()

            for i in range(self.n_nodes):
                if self.field.amplitudes[i] > 0.01:  # Only propagate from active nodes
                    # Compute Laplacian
                    lap = fibpi_laplacian(self.graph, self.field.amplitudes, i)
                    # Diffuse
                    new_amplitudes[i] += diffusion_rate * lap

            # Normalize to prevent explosion
            max_amp = max(new_amplitudes) if new_amplitudes else 1.0
            if max_amp > 10.0:
                new_amplitudes = [a / max_amp * 10.0 for a in new_amplitudes]

            self.field.amplitudes = new_amplitudes

    def find_resonances(self, threshold: float = 0.5) -> List[Tuple[int, int, float]]:
        """
        Find resonating node pairs (nodes with correlated activity).

        Returns:
            List of (node_i, node_j, resonance_strength) tuples
        """
        if not FIBPI_AVAILABLE or self.graph is None:
            return []

        resonances = []

        for i in self.active_nodes:
            neighbors = self.graph["neighbors"][i]

            for j in neighbors:
                if j in self.active_nodes and j > i:  # Avoid duplicates
                    # Resonance = amplitude product * phase alignment
                    amp_product = self.field.amplitudes[i] * self.field.amplitudes[j]
                    phase_diff = abs(self.field.phases[i] - self.field.phases[j])
                    phase_alignment = math.cos(phase_diff)  # 1 = aligned, -1 = opposite

                    resonance = amp_product * phase_alignment

                    if resonance > threshold:
                        resonances.append((i, j, resonance))

        return sorted(resonances, key=lambda x: x[2], reverse=True)

    def compute_substrate_se(self) -> Dict[str, float]:
        """
        Compute Se-like metrics from substrate state.

        Returns:
            Dict with H, C, D, Se computed from wave dynamics
        """
        # H (Entropy): Based on amplitude distribution
        total_energy = self.field.total_energy()
        if total_energy > 0:
            # Normalized entropy of amplitude distribution
            probs = [(a*a) / total_energy for a in self.field.amplitudes if a > 0]
            if probs:
                H = -sum(p * math.log(p + 1e-10) for p in probs) / math.log(len(probs) + 1)
            else:
                H = 0.5
        else:
            H = 0.5

        # C (Coherence): From wave interference pattern
        C = self.field.coherence()

        # D (Depth): Fraction of lattice that's active
        active_count = sum(1 for a in self.field.amplitudes if a > 0.01)
        D = active_count / self.n_nodes

        # Se = H × C × D
        Se = H * C * D

        return {
            "H": round(H, 4),
            "C": round(C, 4),
            "D": round(D, 4),
            "Se": round(Se, 4),
            "active_nodes": active_count,
            "total_energy": round(total_energy, 4),
        }

    def get_dominant_mode(self) -> str:
        """
        Get the dominant reasoning mode from wave pattern.

        Returns:
            'coherent' - waves in phase (supporting evidence)
            'conflicted' - waves out of phase (contradictions)
            'diffuse' - low energy, spread out
            'focused' - high energy, localized
        """
        se = self.compute_substrate_se()
        coherence = self.field.coherence()
        energy = self.field.total_energy()

        if energy < 0.1:
            return "inactive"
        elif coherence > 0.8:
            return "coherent"
        elif coherence < 0.3:
            return "conflicted"
        elif se["D"] > 0.3:
            return "diffuse"
        else:
            return "focused"

    def reset(self) -> None:
        """Reset the substrate to initial state."""
        self.field.amplitudes = [0.0] * self.n_nodes
        self.field.phases = [0.0] * self.n_nodes
        self.field.node_labels = [""] * self.n_nodes
        self.active_nodes = []


class SubstrateIntegratedReasoning:
    """
    Integration layer between agentic reasoning and FibPi3D substrate.

    Injects reasoning steps into the substrate and uses wave dynamics
    to inform confidence and coherence computations.
    """

    def __init__(self, n_nodes: int = 256):
        self.substrate = FibPiReasoningSubstrate(n_nodes=n_nodes)

    def process_scratchpad(self, scratchpad: List[Dict]) -> Dict[str, Any]:
        """
        Process reasoning scratchpad through substrate.

        Args:
            scratchpad: List of ThoughtStep dicts

        Returns:
            Substrate analysis including Se state and resonances
        """
        self.substrate.reset()

        for step in scratchpad:
            content = step.get("content", "")
            step_type = step.get("step_type", "think")

            # Amplitude based on step type
            amplitude_map = {
                "think": 1.0,
                "observation": 1.5,  # Tool results are more concrete
                "reflection": 0.8,
                "error": 0.5,
            }
            amplitude = amplitude_map.get(step_type, 1.0)

            self.substrate.inject_thought(
                content=content,
                amplitude=amplitude,
                label=step_type,
            )

        # Propagate waves
        self.substrate.propagate(steps=3, diffusion_rate=0.15)

        # Analyze
        se_state = self.substrate.compute_substrate_se()
        resonances = self.substrate.find_resonances(threshold=0.3)
        mode = self.substrate.get_dominant_mode()

        return {
            "substrate_se": se_state,
            "resonances": resonances[:5],  # Top 5
            "dominant_mode": mode,
            "field_summary": self.substrate.field.to_dict(),
        }

    def get_confidence_modifier(self, substrate_result: Dict) -> float:
        """
        Get confidence modifier from substrate analysis.

        Returns:
            Float to add to confidence (-0.2 to +0.2)
        """
        mode = substrate_result.get("dominant_mode", "inactive")
        se = substrate_result.get("substrate_se", {}).get("Se", 0.25)

        # Coherent mode with good Se = boost
        if mode == "coherent" and se > 0.3:
            return 0.15
        elif mode == "coherent":
            return 0.08
        elif mode == "conflicted":
            return -0.15
        elif mode == "focused" and se > 0.2:
            return 0.05
        elif mode == "diffuse":
            return -0.05
        else:
            return 0.0


# Quick test
if __name__ == "__main__":
    print("Testing FibPi3D Reasoning Substrate...")
    print(f"FibPi available: {FIBPI_AVAILABLE}")
    print()

    # Create substrate
    substrate = FibPiReasoningSubstrate(n_nodes=64, k_neighbors=4)

    # Inject some thoughts
    thoughts = [
        ("Vanguard owns 8% of Intel according to SEC EDGAR", "observation"),
        ("BlackRock owns 7% of Intel from 13F filings", "observation"),
        ("Both are also investors in CHIPS Act recipients", "think"),
        ("This confirms the both-sides ownership pattern", "reflection"),
    ]

    for content, label in thoughts:
        idx = substrate.inject_thought(content, amplitude=1.0, label=label)
        print(f"Injected '{label}' at node {idx}")

    # Propagate
    substrate.propagate(steps=3)

    # Analyze
    se = substrate.compute_substrate_se()
    print(f"\nSubstrate Se State:")
    print(f"  H (Entropy):   {se['H']:.3f}")
    print(f"  C (Coherence): {se['C']:.3f}")
    print(f"  D (Depth):     {se['D']:.3f}")
    print(f"  Se:            {se['Se']:.3f}")
    print(f"  Mode:          {substrate.get_dominant_mode()}")

    # Find resonances
    resonances = substrate.find_resonances()
    if resonances:
        print(f"\nResonances found: {len(resonances)}")
        for i, j, strength in resonances[:3]:
            print(f"  Node {i} <-> Node {j}: {strength:.3f}")
