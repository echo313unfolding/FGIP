"""Echo OS system graph — load box components as nodes, integrations as edges.

Trial load: maps the Echo OS stack into the FGIP evidence graph so that
missing integrations show up as queryable gaps.

All claims use local receipts/test counts as evidence.
Topic: "EchoOS" for all claims in this domain.
"""

import sys
import hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fgip.db import FGIPDatabase
from fgip.schema import (
    Node, Edge, Claim, NodeType, EdgeType, ClaimStatus, compute_sha256,
)

DB_PATH = str(Path(__file__).resolve().parents[2] / "fgip.db")

TOPIC = "EchoOS"


def _edge_id(etype: str, from_n: str, to_n: str) -> str:
    key = f"{etype}_{from_n}_{to_n}"
    h = hashlib.md5(key.encode()).hexdigest()[:8]
    return f"edge_{etype.lower()}_{from_n[:15]}_{to_n[:15]}_{h}"


# ============================================================================
# LAYERS
# ============================================================================

LAYERS = [
    Node(node_id="layer_0_hardware", node_type=NodeType.SYSTEM_LAYER,
         name="Layer 0: Hardware",
         description="CPU/GPU/disk. T2000 (4GB), RTX 3090 (24GB), local Linux."),
    Node(node_id="layer_1_codec", node_type=NodeType.SYSTEM_LAYER,
         name="Layer 1: Codec Substrate",
         description="Models fit on consumer hardware. Decode is fast. HXQ/GGUF/affine."),
    Node(node_id="layer_1_5_symbol", node_type=NodeType.SYSTEM_LAYER,
         name="Layer 1.5: Symbol-Codebook Map",
         description="Codebook entries as concept basin anchors. SUPPORTED HYPOTHESIS."),
    Node(node_id="layer_2_routing", node_type=NodeType.SYSTEM_LAYER,
         name="Layer 2: Routing",
         description="Route query/tensor/task to cheapest sufficient path before compute."),
    Node(node_id="layer_3_memory", node_type=NodeType.SYSTEM_LAYER,
         name="Layer 3: Memory / Storage",
         description="Store, address, retrieve, verify artifacts without loading everything."),
    Node(node_id="layer_4_runtime", node_type=NodeType.SYSTEM_LAYER,
         name="Layer 4: Runtime",
         description="Execute agent actions, compile NL to ops, serve capsules."),
    Node(node_id="layer_5_safety", node_type=NodeType.SYSTEM_LAYER,
         name="Layer 5: Safety",
         description="Gate agent decisions. Monitor for harmful behavior. Audit."),
    Node(node_id="layer_6_evidence", node_type=NodeType.SYSTEM_LAYER,
         name="Layer 6: Evidence",
         description="Every claim gets a receipt. Every edge gets a source tier."),
    Node(node_id="layer_7_apps", node_type=NodeType.SYSTEM_LAYER,
         name="Layer 7: Apps / Skills",
         description="User-facing tools that use the OS layer."),
]


# ============================================================================
# COMPONENTS
# ============================================================================

COMPONENTS = [
    # --- Layer 1: Codec ---
    Node(node_id="comp_hxq_codec", node_type=NodeType.COMPONENT,
         name="HXQ Codec",
         description="Affine quantization codec. 14 HF models, cos>=0.999. Q4_K_M/Q5_H/AF6 family.",
         metadata={"repo": "helix-substrate", "tests": 95, "status": "PROVEN"}),
    Node(node_id="comp_ggml_hxq", node_type=NodeType.COMPONENT,
         name="GGML_TYPE_HXQ",
         description="Native mmvq kernel in llama.cpp fork. 27.83 tok/s = Q8_0 parity.",
         metadata={"repo": "llama.cpp", "branch": "hxq-affine-type", "status": "PROVEN"}),
    Node(node_id="comp_helix_codec_c99", node_type=NodeType.COMPONENT,
         name="helix-codec C99",
         description="Standalone C99 tensor codec library. 4-function API, MIT.",
         metadata={"repo": "echo313unfolding/helix-codec", "status": "PROVEN"}),
    Node(node_id="comp_helix_linear_ste", node_type=NodeType.COMPONENT,
         name="HelixLinearSTE",
         description="Drop-in nn.Linear with STE for born-compressed training. Gate 1 LoRA PASS.",
         metadata={"repo": "helix-substrate", "status": "PROVEN"}),
    Node(node_id="comp_hxq_solana", node_type=NodeType.COMPONENT,
         name="HXQ Solana Program",
         description="Transfer Hook on devnet. Active/quarantine enforcement. 83 tests.",
         metadata={"repo": "hxq-solana", "status": "PROVEN"}),

    # --- Layer 1.5: Symbol ---
    Node(node_id="comp_crystal_vault", node_type=NodeType.COMPONENT,
         name="Crystal Vault Invariant Basis",
         description="3 invariants (TE,MO,AC) = behavioral fingerprint. Phase 0.19 done. Family-specific.",
         metadata={"tests": 217, "status": "PROVEN"}),

    # --- Layer 2: Routing ---
    Node(node_id="comp_geometry_router", node_type=NodeType.COMPONENT,
         name="GeometryRouter v0.1",
         description="Route tensors by codebook geometry in PCA-4D. 5 super-role basins, 3 handoff gauges. "
                     "Gate policy: cross-basin→ESCALATE, OUTSIDE outlier→MONITOR. Hydra + Agent Substrate bridges. 116/116 tests.",
         metadata={"repo": "echo-origin-gold", "tests": 116, "status": "PROVEN",
                   "commit": "8a9b585", "checkpoint": "compressed_2000steps_model.pt"}),
    Node(node_id="comp_ghost_classifier", node_type=NodeType.COMPONENT,
         name="Ghost Classifier",
         description="k-NN on encoded bytes. Role 73.3% (8.1x random), Arch 92.8%.",
         metadata={"repo": "helix-substrate", "tests": 25, "status": "PROVEN"}),
    Node(node_id="comp_ghost_bridge", node_type=NodeType.COMPONENT,
         name="Ghost Bridge",
         description="Extracts 4 features (te,tr,mo,ac) from encoded bytes WITHOUT decompression.",
         metadata={"repo": "helix-substrate", "tests": 25, "status": "PROVEN"}),
    Node(node_id="comp_hydra_router", node_type=NodeType.COMPONENT,
         name="Hydra Router",
         description="Multi-head codec router. 4 policies, 7 heads. route()/route_with_ghost()/route_with_residuals().",
         metadata={"repo": "helix-substrate", "tests": 19, "status": "PROVEN"}),
    Node(node_id="comp_residual_contract", node_type=NodeType.COMPONENT,
         name="Residual Contract",
         description="Structured damage profiling. 12 features, 4 DamageTypes. Spectral ratio 201x.",
         metadata={"repo": "helix-substrate", "tests": 26, "status": "PROVEN"}),
    Node(node_id="comp_residual_router", node_type=NodeType.COMPONENT,
         name="Residual Router",
         description="Maps residual profiles to routing decisions. 5 CorrectionTypes.",
         metadata={"repo": "helix-substrate", "tests": 25, "status": "PROVEN"}),
    Node(node_id="comp_gauge_routing", node_type=NodeType.COMPONENT,
         name="Gauge-Only Routing",
         description="Metadata-blind router. 99.6% agreement. Tag v0.4.5-real-gauge-routing.",
         metadata={"repo": "helix-substrate", "tests": 73, "status": "PROVEN"}),
    Node(node_id="comp_se_depth_router", node_type=NodeType.COMPONENT,
         name="Se Depth Router",
         description="Se(H,C,D) prompt complexity routing. H-based routing proven.",
         metadata={"repo": "helix-cdc", "status": "PROVEN"}),
    Node(node_id="comp_quant_router", node_type=NodeType.COMPONENT,
         name="Quant Router",
         description="7 models, 5 arch types, ALL PASS affine g128. Universal viability.",
         metadata={"repo": "tools/router", "status": "PROVEN"}),

    # --- Layer 3: Memory ---
    Node(node_id="comp_seedstore", node_type=NodeType.COMPONENT,
         name="SeedStore",
         description="Content-addressed storage. SHA256 hierarchical layout. Persistent seed→artifact.",
         metadata={"repo": "helix-cdc", "status": "PROVEN"}),
    Node(node_id="comp_vault_client", node_type=NodeType.COMPONENT,
         name="VaultClient",
         description="SHAKE-256 deterministic tile generation.",
         metadata={"repo": "helix-cdc", "status": "PROVEN"}),
    Node(node_id="comp_fibpi_anchor", node_type=NodeType.COMPONENT,
         name="FibPi SHA Anchor",
         description="Chunked random-access storage. Anchor-based diff. 8/8 demo.",
         metadata={"repo": "helix-cdc", "status": "PROVEN"}),
    Node(node_id="comp_capsule_manifest", node_type=NodeType.COMPONENT,
         name="CapsuleManifest",
         description="Genotype + BloodType schema. Round-trip proven.",
         metadata={"repo": "helix-cdc", "status": "PROVEN"}),
    Node(node_id="comp_weight_page_lib", node_type=NodeType.COMPONENT,
         name="Weight Page Library",
         description="OS-style virtual memory for model weights. mmap, SHA256 verify, GPU copy.",
         metadata={"repo": "cell-runtime", "tests": 13, "status": "PROVEN"}),
    Node(node_id="comp_echo_memory", node_type=NodeType.COMPONENT,
         name="EchoMemory",
         description="Markdown memory files + echo_nav MCP + ledger. 204 topic files.",
         metadata={"status": "PROVEN"}),

    # --- Layer 4: Runtime ---
    Node(node_id="comp_krisper", node_type=NodeType.COMPONENT,
         name="KRISPER Engine",
         description="NL→IR compiler. Grammar levels L1-L5, IO policy, sandbox root.",
         metadata={"repo": "cell-runtime/src/cell/krisper", "tests": 88, "status": "PROVEN"}),
    Node(node_id="comp_biopoetica", node_type=NodeType.COMPONENT,
         name="BioPoetica Compiler",
         description="Universal DSL — poem type selects compiler target.",
         metadata={"repo": "cell-runtime/src/cell/biopoetica", "tests": 54, "status": "PROVEN"}),
    Node(node_id="comp_cell_runtime", node_type=NodeType.COMPONENT,
         name="cell-runtime",
         description="v0.1.2 tagged. Specialist adapters, model compat matrix, hardware policy.",
         metadata={"repo": "cell-runtime", "status": "PROVEN"}),
    Node(node_id="comp_specialist_pool", node_type=NodeType.COMPONENT,
         name="Specialist Compute Pool",
         description="20 agents. Skill cartridges + shard pool. Route: cartridge→shard→fallback.",
         metadata={"repo": "cell-runtime", "tests": 153, "status": "PROVEN"}),
    Node(node_id="comp_agent_substrate", node_type=NodeType.COMPONENT,
         name="Agent Substrate",
         description="11 bounded agents, tool registry, orchestrator. Phase 3 done.",
         metadata={"repo": "cell-runtime", "tests": 62, "status": "PROVEN"}),
    Node(node_id="comp_basin_server", node_type=NodeType.COMPONENT,
         name="basin_server",
         description="FastAPI server. Streaming. Port 8001.",
         metadata={"repo": "api/basin_server.py", "status": "PROVEN"}),
    Node(node_id="comp_qwen_backend", node_type=NodeType.COMPONENT,
         name="Qwen-Coder Backend",
         description="Qwen2.5-Coder-3B Q4_K_M via llama-server. 14 tok/s. Default brain.",
         metadata={"status": "PROVEN"}),

    # --- Layer 5: Safety ---
    Node(node_id="comp_morphsat", node_type=NodeType.COMPONENT,
         name="MorphSAT",
         description="v8.5.2. M=95.1%, false_safe=0%. TwoStage gate, correction echo.",
         metadata={"repo": "morphsat", "tests": 321, "status": "PROVEN"}),
    Node(node_id="comp_echo_sentry", node_type=NodeType.COMPONENT,
         name="echo-sentry",
         description="Published MIT. Sentinel security monitor. v0.1.0.",
         metadata={"repo": "sentinel-hybrid-stack-public", "tests": 60, "status": "PROVEN"}),
    Node(node_id="comp_krisper_gate", node_type=NodeType.COMPONENT,
         name="KRISPER MorphSAT Gate",
         description="Admissibility gate in KrisperEngine. Fail-closed. 34 tests.",
         metadata={"repo": "cell-runtime/src/cell/krisper/gate.py", "tests": 34, "status": "PROVEN"}),

    # --- Layer 6: Evidence ---
    Node(node_id="comp_fgip_graph", node_type=NodeType.COMPONENT,
         name="FGIP Knowledge Graph",
         description="5275 nodes, 10294 edges, 44019 claims. Tiered evidence.",
         metadata={"repo": "fgip-engine", "status": "PROVEN"}),
    Node(node_id="comp_receipt_spine", node_type=NodeType.COMPONENT,
         name="Receipt Spine",
         description="SHA chains, cost blocks. 552 receipt JSONs.",
         metadata={"repo": "helix-cdc", "status": "PROVEN"}),
    Node(node_id="comp_audit_hook", node_type=NodeType.COMPONENT,
         name="Claude Audit Hook",
         description="Hooks every Bash call. Critical actions get standalone receipts.",
         metadata={"path": "tools/claude_audit_hook.sh", "status": "PROVEN"}),
    Node(node_id="comp_echo_nav", node_type=NodeType.COMPONENT,
         name="echo_nav MCP",
         description="Memory search, ledger read, symbol find, queue management.",
         metadata={"path": "tools/echo_nav_wrapper.sh", "status": "PROVEN"}),

    # --- Layer 7: Apps ---
    Node(node_id="comp_shop_app", node_type=NodeType.COMPONENT,
         name="Shop Inventory App",
         description="InvenTree Docker + custom server. Port 8090.",
         metadata={"status": "PARTIAL"}),
    Node(node_id="comp_fgip_web", node_type=NodeType.COMPONENT,
         name="FGIP Web UI",
         description="Flask web app + API. Risk scoring, graph queries.",
         metadata={"repo": "fgip-engine/web", "status": "PROVEN"}),
    Node(node_id="comp_ghost_me", node_type=NodeType.COMPONENT,
         name="Ghost Me",
         description="Automated people-search opt-out. 35 brokers.",
         metadata={"repo": "ghost-me", "status": "PARTIAL"}),
]


# ============================================================================
# CLAIMS — evidence for integrations
# ============================================================================

CLAIMS = [
    # Proven integrations
    Claim(claim_id="ECHO-INT-001", claim_text="Ghost bridge extracts features from HXQ encoded bytes without decompression, feeds Hydra router for pre-screening", topic=TOPIC, status=ClaimStatus.EVIDENCED, notes="95/95 combined tests. Receipt: Phase 0.17b."),
    Claim(claim_id="ECHO-INT-002", claim_text="Hydra router uses residual contract output to verify codec selection post-reconstruction", topic=TOPIC, status=ClaimStatus.EVIDENCED, notes="Tag v0.4.2-residual-router."),
    Claim(claim_id="ECHO-INT-003", claim_text="KRISPER MorphSAT gate checks every op against grammar level before dispatch", topic=TOPIC, status=ClaimStatus.EVIDENCED, notes="34/34 gate tests. 3 proven paths: ALLOW, BLOCK, ESCALATE."),
    Claim(claim_id="ECHO-INT-004", claim_text="Gauge-only router achieves 99.6% agreement with metadata-aware router", topic=TOPIC, status=ClaimStatus.EVIDENCED, notes="Tag v0.4.5-real-gauge-routing. 161 tensors, 7 families."),
    Claim(claim_id="ECHO-INT-005", claim_text="Ghost classifier role accuracy 73.3% (8.1x random) from encoded bytes alone", topic=TOPIC, status=ClaimStatus.EVIDENCED, notes="Phase 0.15. 292 tensors."),
    Claim(claim_id="ECHO-INT-006", claim_text="Crystal Vault invariant basis (TE+MO+AC) confirmed as minimum. Every feature contributes.", topic=TOPIC, status=ClaimStatus.EVIDENCED, notes="Phase 0.18 ablation. 217/217 tests."),
    Claim(claim_id="ECHO-INT-007", claim_text="MorphSAT v8.5 correction echo achieves M=98.6%, 0% false_safe", topic=TOPIC, status=ClaimStatus.EVIDENCED, notes="Tag v8.5-correction-echo. 318 tests."),
    Claim(claim_id="ECHO-INT-008", claim_text="Agent substrate Phase 3 wired: model can call rag_lookup, graph_lookup, ssm_get_state, sentinel_triage as tools", topic=TOPIC, status=ClaimStatus.EVIDENCED, notes="62/62 tests PASS."),

    # Structural (layer membership, dependencies from code/architecture)
    Claim(claim_id="ECHO-STRUCT-001", claim_text="Echo OS 7-layer architecture with component membership defined in ECHO_OS_STACK.md", topic=TOPIC, status=ClaimStatus.EVIDENCED, notes="echo-origin-gold/docs/ECHO_OS_STACK.md commit 2026-07-02."),
    Claim(claim_id="ECHO-STRUCT-002", claim_text="Component dependency graph derived from import analysis and architecture docs", topic=TOPIC, status=ClaimStatus.EVIDENCED, notes="Dependencies verified by code inspection."),

    # Missing integrations
    Claim(claim_id="ECHO-GAP-001", claim_text="No app uses SeedStore → FibPi → CapsuleManifest → receipt end-to-end on real user data", topic=TOPIC, status=ClaimStatus.MISSING, notes="Memory spine primitives work individually. Pipeline doesn't exist."),
    Claim(claim_id="ECHO-GAP-002", claim_text="MorphSAT gate code exists in KrisperEngine (gate=Optional[MorphSATGate]) but gate is never instantiated in production paths — orchestrator creates KrisperEngine with gate=None", topic=TOPIC, status=ClaimStatus.MISSING, notes="Code: cell/krisper/engine.py:55,99-104. Only test fixtures create gate instances."),
    Claim(claim_id="ECHO-GAP-003", claim_text="FGIP graph queryable by agent substrate via GraphLookupAgent (LIKE queries on nodes table) but limited — no traversal, no evidence chains, no complex FGIP features", topic=TOPIC, status=ClaimStatus.PARTIAL, notes="cell/agents/graph_agent.py:15,31-60. Working but minimal."),
    Claim(claim_id="ECHO-GAP-004", claim_text="No app exercises full Layer 1→6 stack end-to-end: file→classify→store→route→act→receipt→search", topic=TOPIC, status=ClaimStatus.MISSING, notes="The first vertical integration test."),
    Claim(claim_id="ECHO-GAP-005", claim_text="echo-sentry library not used by cell-runtime — SentinelTriageAgent reimplements verdict logic independently via model routing (qwen2.5-sentinel) instead of calling echo-sentry code", topic=TOPIC, status=ClaimStatus.PARTIAL, notes="cell/agents/sentinel_agent.py:48-81 works but bypasses the library."),
    Claim(claim_id="ECHO-GAP-006", claim_text="Gauge-only routing not validated downstream: does it improve PPL/task vs cosine-only?", topic=TOPIC, status=ClaimStatus.MISSING, notes="99.6% agreement proven but downstream effect unmeasured."),
    Claim(claim_id="ECHO-GAP-007", claim_text="KRISPER engine is complete (24 op handlers, 88 tests) but zero calls from cell-runtime orchestrator — orchestrator.py has no KrisperEngine import", topic=TOPIC, status=ClaimStatus.MISSING, notes="cell/orchestrator.py, cli_chat.py, gateway.py, tool_registry.py — none import KRISPER."),
    Claim(claim_id="ECHO-GAP-008", claim_text="Born-compressed routing superiority not proven — architecture confound remains", topic=TOPIC, status=ClaimStatus.EVIDENCED, notes="RESOLVED by WO-MATCHED-BC-ROUTING-01: matched [T,T,M]x4, same config. Post-hoc VQ wins role accuracy 60.9% vs 26.6%. STE homogenizes codebooks."),

    # GeometryRouter v0.1
    Claim(claim_id="ECHO-INT-009", claim_text="GeometryRouter v0.1 routes born-compressed tensors by codebook geometry in PCA-4D. 6 features, 5 super-role basins, 4 early ATTENTION_QO handoffs detected. PCA-3D hides L0 q_proj; PCA-4D is minimum routing dimensionality.", topic=TOPIC, status=ClaimStatus.EVIDENCED, notes="30/30 tests. Commit 7174aa6. Phases 0.20-0.29. echo-origin-gold/geometry_router/."),
    Claim(claim_id="ECHO-GAP-009", claim_text="GeometryRouter is standalone — not wired into Hydra Router, Agent Substrate, or any production runtime", topic=TOPIC, status=ClaimStatus.MISSING, notes="Spec says 'do not wire into production runtime yet'. Planned: GeometryRouter feeds Hydra Router."),

    # Vertical slice gate policy (2026-07-03)
    Claim(claim_id="ECHO-INT-010", claim_text="GeometryRouter vertical slice gate policy correctly distinguishes cross-basin conflicts (ESCALATE) from home-basin OUTSIDE outliers (MONITOR). Hard escalations reduced 5→1. 67/67 tests.", topic=TOPIC, status=ClaimStatus.EVIDENCED, notes="Commit 8a9b585. Patch: OUTSIDE + not cross-basin → MONITOR. L0 q_proj TRUE_CONFLICT preserved."),

    # Hydra bridge adapter (2026-07-03)
    Claim(claim_id="ECHO-INT-011", claim_text="GeometryRouter route hints consumed by HydraBridgeAdapter. 4 Hydra actions mapped from gate verdicts. 7 tensors bridged, 64-tensor full-checkpoint sweep. Only L0 q_proj abstains. 90/90 tests.", topic=TOPIC, status=ClaimStatus.EVIDENCED, notes="Thin adapter demo, NOT production Hydra wiring. RouteHint neutral interface. demos/geometry_router_hydra_bridge.py."),

    # Agent substrate bridge adapter (2026-07-03)
    Claim(claim_id="ECHO-INT-012", claim_text="GeometryRouter/HydraBridgeResult consumed by AgentSubstrateAdapter. 4 agent actions mapped: EXECUTE_DIRECT, EXECUTE_WITH_MONITOR, VERIFY_THEN_EXECUTE, ABSTAIN_OR_FALLBACK. 64-tensor sweep: 32 direct, 30 monitored, 1 verified, 1 abstain. 116/116 tests.", topic=TOPIC, status=ClaimStatus.EVIDENCED, notes="Thin adapter demo, NOT production orchestrator wiring. demos/geometry_router_agent_substrate_bridge.py."),

    # Matched born-compressed vs post-hoc VQ experiment (2026-07-04)
    Claim(claim_id="ECHO-INT-013",
          claim_text="Matched experiment shows current from-scratch HelixLinearSTE does not outperform "
                     "dense→post-hoc VQ for role-geometry routing. Role accuracy: PH=60.9% (5.5x) vs "
                     "BC=26.6% (2.4x). This WEAKENS the naive STE-from-scratch implementation. It does "
                     "NOT falsify broader born-compressed/MoE-style routing. Dense→post-hoc VQ confirmed "
                     "as current production baseline.",
          topic=TOPIC, status=ClaimStatus.EVIDENCED,
          notes="WO-MATCHED-BC-ROUTING-01. [T,T,M]x4, 167M, 2000 steps, RTX 3090, $0.52. "
                "NOT tested: MoE-style trained router, expert load balancing, role-aware codebooks, "
                "delayed quantization, dense warm-start, routing loss. "
                "Receipt: echo-origin-gold/reports/matched_born_vs_posthoc_RECEIPT.json."),

    # Code-discovered dependencies (import crawler 2026-07-02)
    Claim(claim_id="ECHO-CRAWL-001", claim_text="Import crawler discovered 12 undocumented code-level dependencies across 7 repos (6610 files, 40605 imports)", topic=TOPIC, status=ClaimStatus.EVIDENCED, notes="tools/import_crawler.py. 46s, 122MB. Excludes 3 stale build/lib edges."),
]


# ============================================================================
# EDGES — proven integrations + missing gaps
# ============================================================================

def build_edges():
    edges = []

    def add(etype, from_n, to_n, claim_id=None, confidence=1.0, notes=None, source=None):
        edges.append(Edge(
            edge_id=_edge_id(etype.value, from_n, to_n),
            edge_type=etype,
            from_node_id=from_n,
            to_node_id=to_n,
            claim_id=claim_id,
            source=source,
            confidence=confidence,
            notes=notes,
        ))

    ET = EdgeType

    # === Layer membership ===
    for comp_id, layer_id in [
        ("comp_hxq_codec", "layer_1_codec"),
        ("comp_ggml_hxq", "layer_1_codec"),
        ("comp_helix_codec_c99", "layer_1_codec"),
        ("comp_helix_linear_ste", "layer_1_codec"),
        ("comp_hxq_solana", "layer_1_codec"),
        ("comp_crystal_vault", "layer_1_5_symbol"),
        ("comp_geometry_router", "layer_2_routing"),
        ("comp_ghost_classifier", "layer_2_routing"),
        ("comp_ghost_bridge", "layer_2_routing"),
        ("comp_hydra_router", "layer_2_routing"),
        ("comp_residual_contract", "layer_2_routing"),
        ("comp_residual_router", "layer_2_routing"),
        ("comp_gauge_routing", "layer_2_routing"),
        ("comp_se_depth_router", "layer_2_routing"),
        ("comp_quant_router", "layer_2_routing"),
        ("comp_seedstore", "layer_3_memory"),
        ("comp_vault_client", "layer_3_memory"),
        ("comp_fibpi_anchor", "layer_3_memory"),
        ("comp_capsule_manifest", "layer_3_memory"),
        ("comp_weight_page_lib", "layer_3_memory"),
        ("comp_echo_memory", "layer_3_memory"),
        ("comp_krisper", "layer_4_runtime"),
        ("comp_biopoetica", "layer_4_runtime"),
        ("comp_cell_runtime", "layer_4_runtime"),
        ("comp_specialist_pool", "layer_4_runtime"),
        ("comp_agent_substrate", "layer_4_runtime"),
        ("comp_basin_server", "layer_4_runtime"),
        ("comp_qwen_backend", "layer_4_runtime"),
        ("comp_morphsat", "layer_5_safety"),
        ("comp_echo_sentry", "layer_5_safety"),
        ("comp_krisper_gate", "layer_5_safety"),
        ("comp_fgip_graph", "layer_6_evidence"),
        ("comp_receipt_spine", "layer_6_evidence"),
        ("comp_audit_hook", "layer_6_evidence"),
        ("comp_echo_nav", "layer_6_evidence"),
        ("comp_shop_app", "layer_7_apps"),
        ("comp_fgip_web", "layer_7_apps"),
        ("comp_ghost_me", "layer_7_apps"),
    ]:
        add(ET.MEMBER_OF_LAYER, comp_id, layer_id, claim_id="ECHO-STRUCT-001")

    # === Proven signal flows (FEEDS_SIGNAL) ===
    add(ET.FEEDS_SIGNAL, "comp_hxq_codec", "comp_ghost_bridge",
        claim_id="ECHO-INT-001", notes="Ghost reads encoded bytes from HXQ output")
    add(ET.FEEDS_SIGNAL, "comp_ghost_bridge", "comp_hydra_router",
        claim_id="ECHO-INT-001", notes="Ghost pre-screens, clears 53.8%")
    add(ET.FEEDS_SIGNAL, "comp_residual_contract", "comp_residual_router",
        claim_id="ECHO-INT-002", notes="Damage profile → routing decision")
    add(ET.FEEDS_SIGNAL, "comp_crystal_vault", "comp_ghost_classifier",
        claim_id="ECHO-INT-006", notes="Invariant basis feeds classifier")
    add(ET.FEEDS_SIGNAL, "comp_ghost_classifier", "comp_ghost_bridge",
        claim_id="ECHO-INT-005", notes="Classifier results inform bridge features")

    # === Proven routing flows ===
    add(ET.ROUTES_TO, "comp_hydra_router", "comp_hxq_codec",
        claim_id="ECHO-STRUCT-002", notes="Routes to codec head selection (affine4/5/6, VQ, sidecar)")
    add(ET.ROUTES_TO, "comp_residual_router", "comp_hydra_router",
        claim_id="ECHO-INT-002", notes="Post-reconstruction verification feeds back")
    add(ET.ROUTES_TO, "comp_se_depth_router", "comp_qwen_backend",
        claim_id="ECHO-STRUCT-002", notes="Se routes prompt complexity to model tier")

    # === Proven safety gates ===
    add(ET.GATES, "comp_krisper_gate", "comp_krisper",
        claim_id="ECHO-INT-003", notes="Every op checked before dispatch. Fail-closed.")
    add(ET.GATES, "comp_morphsat", "comp_agent_substrate",
        claim_id="ECHO-INT-007", notes="MorphSAT gates agent decisions")

    # === Proven dependencies ===
    S = "ECHO-STRUCT-002"
    add(ET.DEPENDS_ON, "comp_ghost_bridge", "comp_hxq_codec",
        claim_id=S, notes="Needs encoded tensor bytes as input")
    add(ET.DEPENDS_ON, "comp_hydra_router", "comp_ghost_bridge",
        claim_id=S, notes="Uses Ghost pre-screening for efficiency")
    add(ET.DEPENDS_ON, "comp_residual_router", "comp_residual_contract",
        claim_id=S, notes="Needs damage profile to decide correction type")
    add(ET.DEPENDS_ON, "comp_ggml_hxq", "comp_hxq_codec",
        claim_id=S, notes="Native kernel implements HXQ codec in C/CUDA")
    add(ET.DEPENDS_ON, "comp_basin_server", "comp_qwen_backend",
        claim_id=S, notes="API serves model via llama-server backend")
    add(ET.DEPENDS_ON, "comp_krisper", "comp_biopoetica",
        claim_id=S, notes="KRISPER translates BioPoetica DSL")
    add(ET.DEPENDS_ON, "comp_specialist_pool", "comp_cell_runtime",
        claim_id=S, notes="Pool runs inside cell-runtime")
    add(ET.DEPENDS_ON, "comp_agent_substrate", "comp_cell_runtime",
        claim_id=S, notes="Agents wired into cell-runtime orchestrator")
    add(ET.DEPENDS_ON, "comp_gauge_routing", "comp_residual_contract",
        claim_id=S, notes="Gauge features derived from residual analysis")
    add(ET.DEPENDS_ON, "comp_fgip_web", "comp_fgip_graph",
        claim_id=S, notes="Web UI queries the knowledge graph")
    add(ET.DEPENDS_ON, "comp_echo_nav", "comp_echo_memory",
        claim_id=S, notes="MCP server reads/searches memory files")

    # === Proven cross-layer integrations ===
    add(ET.TESTED_WITH, "comp_ghost_bridge", "comp_hydra_router",
        claim_id="ECHO-INT-001", confidence=1.0, notes="25/25 Ghost + 19/19 Hydra tests")
    add(ET.TESTED_WITH, "comp_residual_contract", "comp_residual_router",
        claim_id="ECHO-INT-002", confidence=1.0, notes="26+25 = 51 tests")
    add(ET.TESTED_WITH, "comp_krisper_gate", "comp_morphsat",
        claim_id="ECHO-INT-003", confidence=1.0, notes="34/34 gate tests")

    # === MISSING INTEGRATIONS (the gaps) ===
    add(ET.MISSING_INTEGRATION, "comp_seedstore", "comp_capsule_manifest",
        claim_id="ECHO-GAP-001", confidence=0.0,
        notes="GAP: No pipeline wires SeedStore→FibPi→Capsule end-to-end")
    add(ET.MISSING_INTEGRATION, "comp_fibpi_anchor", "comp_capsule_manifest",
        claim_id="ECHO-GAP-001", confidence=0.0,
        notes="GAP: FibPi and Capsule not connected in any app")
    add(ET.MISSING_INTEGRATION, "comp_morphsat", "comp_cell_runtime",
        claim_id="ECHO-GAP-002", confidence=0.0,
        notes="GAP: Safety monitor not wired into runtime loop")
    add(ET.MISSING_INTEGRATION, "comp_fgip_graph", "comp_agent_substrate",
        claim_id="ECHO-GAP-003", confidence=0.0,
        notes="GAP: Evidence graph not queryable by agents at runtime")
    add(ET.MISSING_INTEGRATION, "comp_echo_sentry", "comp_cell_runtime",
        claim_id="ECHO-GAP-005", confidence=0.0,
        notes="GAP: Sentinel not wired into runtime agent loop")
    add(ET.MISSING_INTEGRATION, "comp_gauge_routing", "comp_qwen_backend",
        claim_id="ECHO-GAP-006", confidence=0.0,
        notes="GAP: Gauge routing not validated on downstream task quality")
    add(ET.MISSING_INTEGRATION, "comp_krisper", "comp_cell_runtime",
        claim_id="ECHO-GAP-007", confidence=0.0,
        notes="GAP: KRISPER+BioPoetica not unified with cell-runtime daemon")
    add(ET.MISSING_INTEGRATION, "comp_helix_linear_ste", "comp_ghost_bridge",
        claim_id="ECHO-GAP-008", confidence=0.0,
        notes="GAP: Born-compressed routing superiority unproven (architecture confound)")

    # === GeometryRouter v0.1 edges ===
    add(ET.DEPENDS_ON, "comp_geometry_router", "comp_ghost_bridge",
        claim_id="ECHO-INT-009", notes="Uses ghost_features_from_bytes() from helix_substrate.ghost_bridge")
    add(ET.TESTED_WITH, "comp_geometry_router", "comp_ghost_bridge",
        claim_id="ECHO-INT-009", confidence=1.0,
        notes="30/30 tests use proven Ghost features. Commit 7174aa6.")
    add(ET.FEEDS_SIGNAL, "comp_geometry_router", "comp_hydra_router",
        claim_id="ECHO-INT-011", confidence=0.8,
        notes="Bridge adapter maps RouteHint→HydraAction (tested). "
              "Not yet production wiring — adapter demo only.")
    add(ET.MISSING_INTEGRATION, "comp_geometry_router", "comp_hydra_router",
        claim_id="ECHO-GAP-009", confidence=0.0,
        notes="GAP: Bridge adapter proven (ECHO-INT-011) but not production Hydra wiring. "
              "HydraBridgeAdapter does not call HydraRouter.route().")
    add(ET.MISSING_INTEGRATION, "comp_geometry_router", "comp_agent_substrate",
        claim_id="ECHO-GAP-009", confidence=0.0,
        notes="GAP: Bridge adapter proven (ECHO-INT-012) but not production orchestrator wiring. "
              "AgentSubstrateAdapter does not call any cell-runtime agent.")

    # === Vertical slice gate policy (commit 8a9b585) ===
    add(ET.TESTED_WITH, "comp_geometry_router", "comp_morphsat",
        claim_id="ECHO-INT-010", confidence=1.0,
        notes="Gate policy patch: OUTSIDE+not-cross-basin→MONITOR. "
              "Hard escalations 5→1. 67/67 tests. Commit 8a9b585.")

    # === Hydra bridge adapter (2026-07-03) ===
    add(ET.TESTED_WITH, "comp_geometry_router", "comp_hydra_router",
        claim_id="ECHO-INT-011", confidence=1.0,
        notes="Bridge adapter maps RouteHint→HydraAction. "
              "4 actions, codec hints, 7 tensors + 64-tensor sweep. "
              "90/90 tests. Thin adapter, not production wiring.")

    # === Agent substrate bridge adapter (2026-07-03) ===
    add(ET.TESTED_WITH, "comp_geometry_router", "comp_agent_substrate",
        claim_id="ECHO-INT-012", confidence=1.0,
        notes="Bridge adapter maps HydraBridgeResult→AgentSubstrateDecision. "
              "4 agent actions, execution flags, agent selection. "
              "116/116 tests. Thin adapter, not production orchestrator wiring.")

    # === Matched born-compressed vs post-hoc VQ (2026-07-04) ===
    # Skeleton edge: experiment tested HelixLinearSTE routing vs post-hoc VQ routing
    add(ET.TESTED_WITH, "comp_helix_linear_ste", "comp_geometry_router",
        claim_id="ECHO-INT-013", confidence=1.0,
        notes="WO-MATCHED-BC-ROUTING-01: current from-scratch HelixLinearSTE does not outperform "
              "dense→post-hoc VQ for role-geometry routing. Role accuracy PH=60.9% vs BC=26.6%. "
              "WEAKENS naive STE-from-scratch. Does NOT falsify broader born-compressed/MoE-style routing. "
              "Not tested: expert load balancing, role-aware codebooks, delayed quantization, "
              "dense warm-start, routing loss.")

    # === Code-discovered dependencies (import crawler 2026-07-02) ===
    C = "ECHO-CRAWL-001"

    # basin_server imports
    add(ET.DEPENDS_ON, "comp_basin_server", "comp_quant_router",
        claim_id=C, notes="CODE: basin_server.py:74 imports RouterDecision, SeMetrics from helix_cdc.echo.ops.models")
    add(ET.DEPENDS_ON, "comp_basin_server", "comp_se_depth_router",
        claim_id=C, notes="CODE: basin_server.py:528 imports stream_transformer_block_forward")
    add(ET.DEPENDS_ON, "comp_basin_server", "comp_hxq_codec",
        claim_id=C, notes="CODE: basin_server.py:745 imports validate_receipt from helix_substrate.basin_runtime")

    # Se <-> HXQ cross-dependency
    add(ET.DEPENDS_ON, "comp_se_depth_router", "comp_hxq_codec",
        claim_id=C, notes="CODE: helix_cdc/regrow/cdna_reader.py:17 imports CDNAv2Reader from helix_substrate")

    # cell-runtime imports
    add(ET.DEPENDS_ON, "comp_cell_runtime", "comp_biopoetica",
        claim_id=C, notes="CODE: demo_allow.py:20 imports BioPoeticaCompiler from cell.biopoetica")
    add(ET.DEPENDS_ON, "comp_cell_runtime", "comp_quant_router",
        claim_id=C, notes="CODE: orchestrator.py:24 imports classify, route_model from cell.router")
    add(ET.DEPENDS_ON, "comp_cell_runtime", "comp_hxq_codec",
        claim_id=C, notes="CODE: vault_shard.py:1404 imports stream_xw_from_cdna from helix_substrate")
    add(ET.DEPENDS_ON, "comp_cell_runtime", "comp_crystal_vault",
        claim_id=C, notes="CODE: test_cross_model_shadows.py:34 imports ShadowMemory, Ghost, GlyphDAR")
    add(ET.DEPENDS_ON, "comp_cell_runtime", "comp_weight_page_lib",
        claim_id=C, notes="CODE: test_weight_page_manifest.py:75 imports WeightPageLibrary")

    # FGIP -> Se (cdna_server uses decode)
    add(ET.DEPENDS_ON, "comp_fgip_graph", "comp_se_depth_router",
        claim_id=C, notes="CODE: cdna_server/app.py:503 imports stream_multi_block_forward from helix_cdc")

    # MorphSAT -> HXQ (bridge test)
    add(ET.DEPENDS_ON, "comp_morphsat", "comp_hxq_codec",
        claim_id=C, notes="CODE: bridge_mamba_test.py:88 imports HelixLinear from helix_substrate")

    # HXQ internal: ResidualProfile instantiated within residual_contract.py
    add(ET.DEPENDS_ON, "comp_hxq_codec", "comp_residual_contract",
        claim_id=C, notes="CODE: residual_contract.py:179 instantiates ResidualProfile (within helix-substrate)")

    # === Layer dependencies ===
    add(ET.DEPENDS_ON, "layer_2_routing", "layer_1_codec",
        claim_id="ECHO-STRUCT-001", notes="Routing signals emerge from codec output")
    add(ET.DEPENDS_ON, "layer_3_memory", "layer_1_codec",
        claim_id="ECHO-STRUCT-001", notes="Memory stores codec-compressed artifacts")
    add(ET.DEPENDS_ON, "layer_4_runtime", "layer_2_routing",
        claim_id="ECHO-STRUCT-001", notes="Runtime uses routing to select models/paths")
    add(ET.DEPENDS_ON, "layer_4_runtime", "layer_3_memory",
        claim_id="ECHO-STRUCT-001", notes="Runtime reads from memory substrate")
    add(ET.DEPENDS_ON, "layer_5_safety", "layer_4_runtime",
        claim_id="ECHO-STRUCT-001", notes="Safety gates runtime actions")
    add(ET.DEPENDS_ON, "layer_6_evidence", "layer_5_safety",
        claim_id="ECHO-STRUCT-001", notes="Evidence records safety decisions")
    add(ET.DEPENDS_ON, "layer_7_apps", "layer_4_runtime",
        claim_id="ECHO-STRUCT-001", notes="Apps use runtime to execute")
    add(ET.DEPENDS_ON, "layer_1_5_symbol", "layer_1_codec",
        claim_id="ECHO-STRUCT-001", notes="Symbol map requires codec output")

    return edges


# ============================================================================
# LOAD
# ============================================================================

def main():
    db = FGIPDatabase(DB_PATH)
    db.connect()
    print(f"Database: {DB_PATH}")

    # Stats before
    before = db.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    before_e = db.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]

    # Insert claims
    for claim in CLAIMS:
        try:
            db.insert_claim(claim)
            print(f"  claim: {claim.claim_id}")
        except Exception as e:
            if "UNIQUE" in str(e):
                print(f"  claim: {claim.claim_id} (exists)")
            else:
                raise

    # Insert layers
    for layer in LAYERS:
        try:
            db.insert_node(layer)
            print(f"  layer: {layer.node_id}")
        except Exception as e:
            if "UNIQUE" in str(e):
                print(f"  layer: {layer.node_id} (exists)")
            else:
                raise

    # Insert components
    for comp in COMPONENTS:
        try:
            db.insert_node(comp)
            print(f"  component: {comp.node_id}")
        except Exception as e:
            if "UNIQUE" in str(e):
                print(f"  component: {comp.node_id} (exists)")
            else:
                raise

    # Insert edges
    edges = build_edges()
    for edge in edges:
        try:
            db.insert_edge(edge)
            print(f"  edge: {edge.edge_type.value} {edge.from_node_id} → {edge.to_node_id}")
        except Exception as e:
            if "UNIQUE" in str(e):
                print(f"  edge: {edge.edge_id} (exists)")
            else:
                print(f"  WARN edge {edge.edge_id}: {e}")

    # Stats after
    after = db.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    after_e = db.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]

    print(f"\n--- RESULT ---")
    print(f"Nodes: {before} → {after} (+{after - before})")
    print(f"Edges: {before_e} → {after_e} (+{after_e - before_e})")

    # Show gaps
    gaps = db.conn.execute(
        "SELECT from_node_id, to_node_id, notes FROM edges WHERE edge_type = 'MISSING_INTEGRATION'"
    ).fetchall()
    if gaps:
        print(f"\n--- MISSING INTEGRATIONS ({len(gaps)} gaps) ---")
        for g in gaps:
            from_name = db.conn.execute("SELECT name FROM nodes WHERE node_id=?", (g[0],)).fetchone()
            to_name = db.conn.execute("SELECT name FROM nodes WHERE node_id=?", (g[1],)).fetchone()
            fn = from_name[0] if from_name else g[0]
            tn = to_name[0] if to_name else g[1]
            print(f"  {fn} ──✗──> {tn}")
            print(f"    {g[2]}")


if __name__ == "__main__":
    main()
