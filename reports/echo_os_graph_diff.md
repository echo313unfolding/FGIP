========================================================================
ECHO OS IMPORT CRAWLER — Architecture vs Code Diff Report
========================================================================

Repos crawled:     7
Python files:      6611
Total imports:     40619
Total calls:       470794
Resolved edges:    34
Graph edges:       95

------------------------------------------------------------------------
1. ARCHITECTURE-YES / CODE-NO  (19 edges)
   Graph says dependency exists, but no import/call found in code
------------------------------------------------------------------------
  HXQ Codec --[FEEDS_SIGNAL]--> Ghost Bridge
    graph: comp_hxq_codec -> comp_ghost_bridge
    notes: Ghost reads encoded bytes from HXQ output

  Ghost Bridge --[FEEDS_SIGNAL]--> Hydra Router
    graph: comp_ghost_bridge -> comp_hydra_router
    notes: Ghost pre-screens, clears 53.8%

  Residual Contract --[FEEDS_SIGNAL]--> Residual Router
    graph: comp_residual_contract -> comp_residual_router
    notes: Damage profile → routing decision

  Crystal Vault Invariant Basis --[FEEDS_SIGNAL]--> Ghost Classifier
    graph: comp_crystal_vault -> comp_ghost_classifier
    notes: Invariant basis feeds classifier

  Ghost Classifier --[FEEDS_SIGNAL]--> Ghost Bridge
    graph: comp_ghost_classifier -> comp_ghost_bridge
    notes: Classifier results inform bridge features

  Hydra Router --[ROUTES_TO]--> HXQ Codec
    graph: comp_hydra_router -> comp_hxq_codec
    notes: Routes to codec head selection (affine4/5/6, VQ, sidecar)

  Residual Router --[ROUTES_TO]--> Hydra Router
    graph: comp_residual_router -> comp_hydra_router
    notes: Post-reconstruction verification feeds back

  Se Depth Router --[ROUTES_TO]--> Qwen-Coder Backend
    graph: comp_se_depth_router -> comp_qwen_backend
    notes: Se routes prompt complexity to model tier

  KRISPER MorphSAT Gate --[GATES]--> KRISPER Engine
    graph: comp_krisper_gate -> comp_krisper
    notes: Every op checked before dispatch. Fail-closed.

  MorphSAT --[GATES]--> Agent Substrate
    graph: comp_morphsat -> comp_agent_substrate
    notes: MorphSAT gates agent decisions

  Ghost Bridge --[DEPENDS_ON]--> HXQ Codec
    graph: comp_ghost_bridge -> comp_hxq_codec
    notes: Needs encoded tensor bytes as input

  Hydra Router --[DEPENDS_ON]--> Ghost Bridge
    graph: comp_hydra_router -> comp_ghost_bridge
    notes: Uses Ghost pre-screening for efficiency

  Residual Router --[DEPENDS_ON]--> Residual Contract
    graph: comp_residual_router -> comp_residual_contract
    notes: Needs damage profile to decide correction type

  GGML_TYPE_HXQ --[DEPENDS_ON]--> HXQ Codec
    graph: comp_ggml_hxq -> comp_hxq_codec
    notes: Native kernel implements HXQ codec in C/CUDA

  Specialist Compute Pool --[DEPENDS_ON]--> cell-runtime
    graph: comp_specialist_pool -> comp_cell_runtime
    notes: Pool runs inside cell-runtime

  Gauge-Only Routing --[DEPENDS_ON]--> Residual Contract
    graph: comp_gauge_routing -> comp_residual_contract
    notes: Gauge features derived from residual analysis

  echo_nav MCP --[DEPENDS_ON]--> EchoMemory
    graph: comp_echo_nav -> comp_echo_memory
    notes: MCP server reads/searches memory files

  GeometryRouter v0.1 --[DEPENDS_ON]--> Ghost Bridge
    graph: comp_geometry_router -> comp_ghost_bridge
    notes: Uses ghost_features_from_bytes() from helix_substrate.ghost_bridge

  GeometryRouter v0.1 --[FEEDS_SIGNAL]--> Hydra Router
    graph: comp_geometry_router -> comp_hydra_router
    notes: PLANNED: GeometryRouter route decisions feed Hydra Router. Not wired yet.


------------------------------------------------------------------------
2. CODE-YES / ARCHITECTURE-NO  (6 edges)
   Code imports/calls exist but graph has no edge
------------------------------------------------------------------------
  HXQ Codec --[CODE_IMPORTS]--> GeometryRouter v0.1
    file: /home/voidstr3m33/helix-substrate/build/lib/helix_substrate/route_inheritance.py:27
    code: import route_decision (RetrievalMode, RouteDecision)

  HXQ Codec --[CODE_IMPORTS]--> FGIP Knowledge Graph
    file: /home/voidstr3m33/helix-substrate/build/lib/helix_substrate/trading_executors.py:134
    code: import fgip.db (FGIPDatabase)

  FGIP Knowledge Graph --[CODE_IMPORTS]--> GeometryRouter v0.1
    file: /home/voidstr3m33/fgip-engine/fgip/regime/__init__.py:35
    code: import features_from_fred (FREDFeatures, extract_features, features_to_dict)

  GeometryRouter v0.1 --[CODE_IMPORTS]--> HXQ Codec
    file: /home/voidstr3m33/echo-origin-gold/geometry_router/features.py:15
    code: import helix_substrate.ghost_bridge (ghost_features_from_bytes)

  HXQ Codec --[CODE_INSTANTIATES]--> GeometryRouter v0.1
    file: /home/voidstr3m33/helix-substrate/build/lib/helix_substrate/route_decision.py:186
    code: RouteDecision()

  HXQ Codec --[CODE_INSTANTIATES]--> FGIP Knowledge Graph
    file: /home/voidstr3m33/helix-substrate/build/lib/helix_substrate/trading_executors.py:135
    code: FGIPDatabase()


------------------------------------------------------------------------
3. UNTESTED DEPENDENCIES  (34 edges)
   Import exists but no TESTED_WITH edge in graph
------------------------------------------------------------------------
  HXQ Codec -> Se Depth Router
    file: /home/voidstr3m33/helix-substrate/build/lib/helix_substrate/cdna_reader.py:1225

  HXQ Codec -> GeometryRouter v0.1
    file: /home/voidstr3m33/helix-substrate/build/lib/helix_substrate/route_inheritance.py:27

  HXQ Codec -> FGIP Knowledge Graph
    file: /home/voidstr3m33/helix-substrate/build/lib/helix_substrate/trading_executors.py:134

  basin_server -> Quant Router
    file: /home/voidstr3m33/helix-cdc/api/basin_server.py:74

  basin_server -> Se Depth Router
    file: /home/voidstr3m33/helix-cdc/api/basin_server.py:528

  basin_server -> HXQ Codec
    file: /home/voidstr3m33/helix-cdc/api/basin_server.py:745

  basin_server -> Qwen-Coder Backend
    file: /home/voidstr3m33/helix-cdc/api/basin_server.py:837

  KRISPER Engine -> BioPoetica Compiler
    file: /home/voidstr3m33/helix-cdc/gitforest-repo/forest/krisper/__init__.py:7

  Se Depth Router -> HXQ Codec
    file: /home/voidstr3m33/helix-cdc/helix_cdc/regrow/cdna_reader.py:17

  cell-runtime -> BioPoetica Compiler
    file: /home/voidstr3m33/cell-runtime/examples/biopoetica_krisper/demo_allow.py:20

  cell-runtime -> KRISPER Engine
    file: /home/voidstr3m33/cell-runtime/examples/biopoetica_krisper/demo_allow.py:21

  cell-runtime -> Quant Router
    file: /home/voidstr3m33/cell-runtime/src/cell/orchestrator.py:24

  cell-runtime -> echo-sentry
    file: /home/voidstr3m33/cell-runtime/src/cell/specialists.py:117

  cell-runtime -> HXQ Codec
    file: /home/voidstr3m33/cell-runtime/src/cell/vault_shard.py:1404

  cell-runtime -> Crystal Vault Invariant Basis
    file: /home/voidstr3m33/cell-runtime/tests/test_cross_model_shadows.py:34

  cell-runtime -> Weight Page Library
    file: /home/voidstr3m33/cell-runtime/tests/test_weight_page_manifest.py:75

  FGIP Knowledge Graph -> Se Depth Router
    file: /home/voidstr3m33/fgip-engine/cdna_server/app.py:503

  FGIP Knowledge Graph -> GeometryRouter v0.1
    file: /home/voidstr3m33/fgip-engine/fgip/regime/__init__.py:35

  FGIP Web UI -> FGIP Knowledge Graph
    file: /home/voidstr3m33/fgip-engine/web/app.py:20

  MorphSAT -> HXQ Codec
    file: /home/voidstr3m33/morphsat/tools/bridge_mamba_test.py:88

  GeometryRouter v0.1 -> HXQ Codec
    file: /home/voidstr3m33/echo-origin-gold/geometry_router/features.py:15

  HXQ Codec -> MorphSAT
    file: /home/voidstr3m33/helix-substrate/build/lib/helix_substrate/lobe_scheduler.py:469

  HXQ Codec -> GeometryRouter v0.1
    file: /home/voidstr3m33/helix-substrate/build/lib/helix_substrate/route_decision.py:186

  HXQ Codec -> FGIP Knowledge Graph
    file: /home/voidstr3m33/helix-substrate/build/lib/helix_substrate/trading_executors.py:135

  HXQ Codec -> Residual Contract
    file: /home/voidstr3m33/helix-substrate/helix_substrate/residual_contract.py:179

  basin_server -> Quant Router
    file: /home/voidstr3m33/helix-cdc/api/basin_server.py:1542

  KRISPER Engine -> BioPoetica Compiler
    file: /home/voidstr3m33/helix-cdc/gitforest-repo/forest/krisper/bio_executor.py:19

  cell-runtime -> BioPoetica Compiler
    file: /home/voidstr3m33/cell-runtime/examples/biopoetica_krisper/demo_allow.py:48

  cell-runtime -> MorphSAT
    file: /home/voidstr3m33/cell-runtime/examples/biopoetica_krisper/demo_allow.py:60

  cell-runtime -> KRISPER Engine
    file: /home/voidstr3m33/cell-runtime/examples/biopoetica_krisper/demo_allow.py:65

  cell-runtime -> Agent Substrate
    file: /home/voidstr3m33/cell-runtime/src/cell/cli_chat.py:47

  cell-runtime -> Crystal Vault Invariant Basis
    file: /home/voidstr3m33/cell-runtime/tests/test_cross_model_shadows.py:264

  cell-runtime -> Weight Page Library
    file: /home/voidstr3m33/cell-runtime/tests/test_weight_page_manifest.py:76

  FGIP Web UI -> FGIP Knowledge Graph
    file: /home/voidstr3m33/fgip-engine/web/app.py:34


------------------------------------------------------------------------
4. CROSS-REPO CLASS USAGE  (17 classes)
   Same class used across multiple repos (may indicate duplication or shared dependency)
------------------------------------------------------------------------
  HelixLinear: 'HelixLinear' used across 4 repos: echo-origin-gold, helix-cdc, helix-substrate, morphsat
  MorphSATGate: 'MorphSATGate' used across 3 repos: cell-runtime, helix-substrate, morphsat
  RouteDecision: 'RouteDecision' used across 2 repos: echo-origin-gold, helix-substrate
  FGIPDatabase: 'FGIPDatabase' used across 2 repos: fgip-engine, helix-substrate
  RouterDecision: 'RouterDecision' used across 2 repos: echo-origin-gold, helix-cdc
  Node: 'Node' used across 3 repos: echo-origin-gold, fgip-engine, helix-cdc
  SeRouter: 'SeRouter' used across 2 repos: echo-origin-gold, helix-cdc
  BioPoeticaCompiler: 'BioPoeticaCompiler' used across 3 repos: cell-runtime, echo-origin-gold, helix-cdc
  SeedStore: 'SeedStore' used across 2 repos: echo-origin-gold, helix-cdc
  Genotype: 'Genotype' used across 2 repos: echo-origin-gold, helix-cdc
  BloodType: 'BloodType' used across 2 repos: echo-origin-gold, helix-cdc
  CapsuleManifest: 'CapsuleManifest' used across 2 repos: echo-origin-gold, helix-cdc
  Edge: 'Edge' used across 3 repos: echo-origin-gold, fgip-engine, helix-cdc
  Claim: 'Claim' used across 3 repos: echo-origin-gold, fgip-engine, helix-cdc
  FibPiAnchor: 'FibPiAnchor' used across 2 repos: echo-origin-gold, helix-cdc
  VaultClient: 'VaultClient' used across 2 repos: echo-origin-gold, helix-cdc
  KrisperEngine: 'KrisperEngine' used across 2 repos: cell-runtime, echo-origin-gold

------------------------------------------------------------------------
5. CONFIRMED EDGES  (24 edges)
   Both code and architecture graph agree
------------------------------------------------------------------------
  HXQ Codec --[CODE_IMPORTS]--> Se Depth Router
    code: import helix_cdc.regrow.cdna_stream (CDNAStreamReader)
  basin_server --[CODE_IMPORTS]--> Quant Router
    code: import helix_cdc.echo.ops.models (EchoLoopReceipt, RouterDecision, SeMetrics, UncertaintyDispatchReceipt, AgentResultModel, ROUTER_SCHEMA_VERSION)
  basin_server --[CODE_IMPORTS]--> Se Depth Router
    code: import helix_cdc.regrow.stream_transformer_block (stream_transformer_block_forward)
  basin_server --[CODE_IMPORTS]--> HXQ Codec
    code: import helix_substrate.basin_runtime (validate_receipt)
  basin_server --[CODE_IMPORTS]--> Qwen-Coder Backend
    code: import echo_cog.backend_llama_cpp (run_llama_cpp_timed)
  KRISPER Engine --[CODE_IMPORTS]--> BioPoetica Compiler
    code: import bio_poetica (BioPoeticaParser, BioPoeticaCompiler)
  Se Depth Router --[CODE_IMPORTS]--> HXQ Codec
    code: import helix_substrate.cdna_reader (CDNAv2Reader)
  cell-runtime --[CODE_IMPORTS]--> BioPoetica Compiler
    code: import cell.biopoetica (BioPoeticaCompiler, BioPoeticaEmitter)
  cell-runtime --[CODE_IMPORTS]--> Quant Router
    code: import cell.router (classify, route_model)
  cell-runtime --[CODE_IMPORTS]--> HXQ Codec
    code: import helix_substrate.stream_matmul (stream_xw_from_cdna)
  cell-runtime --[CODE_IMPORTS]--> Crystal Vault Invariant Basis
    code: import cell.vault_shard (Ghost, GlyphDAR, LatentShape, MemoryEntry, Outcome, Shadow, ShadowMemory, _entropy_band, _hamming64, _structural_key)
  cell-runtime --[CODE_IMPORTS]--> Weight Page Library
    code: import cell.weight_pages (WeightPageLibrary)
  FGIP Knowledge Graph --[CODE_IMPORTS]--> Se Depth Router
    code: import helix_cdc.regrow.stream_transformer_block (stream_multi_block_forward, rms_norm, load_norm_weights_from_gguf)
  FGIP Web UI --[CODE_IMPORTS]--> FGIP Knowledge Graph
    code: import fgip.db (FGIPDatabase)
  MorphSAT --[CODE_IMPORTS]--> HXQ Codec
    code: import helix_substrate.helix_linear (HelixLinear, load_cdna_factors, swap_to_helix, swap_summary)
  HXQ Codec --[CODE_INSTANTIATES]--> MorphSAT
    code: MorphSATGate()
  HXQ Codec --[CODE_INSTANTIATES]--> Residual Contract
    code: ResidualProfile()
  basin_server --[CODE_INSTANTIATES]--> Quant Router
    code: RouterDecision()
  KRISPER Engine --[CODE_INSTANTIATES]--> BioPoetica Compiler
    code: BioPoeticaCompiler()
  cell-runtime --[CODE_INSTANTIATES]--> BioPoetica Compiler
    code: BioPoeticaCompiler()
  cell-runtime --[CODE_INSTANTIATES]--> Agent Substrate
    code: Orchestrator()
  cell-runtime --[CODE_INSTANTIATES]--> Crystal Vault Invariant Basis
    code: ShadowMemory()
  cell-runtime --[CODE_INSTANTIATES]--> Weight Page Library
    code: WeightPageLibrary()
  FGIP Web UI --[CODE_INSTANTIATES]--> FGIP Knowledge Graph
    code: FGIPDatabase()

========================================================================
SUMMARY
========================================================================
  Confirmed integrations:       24
  Graph-only (missing code):     19
  Code-only (undocumented):      6
  Untested dependencies:         34
  Cross-repo class usage:        17

  PRIORITY: Wire these missing integrations first:
    - HXQ Codec -> Ghost Bridge [FEEDS_SIGNAL]
    - Ghost Bridge -> Hydra Router [FEEDS_SIGNAL]
    - Residual Contract -> Residual Router [FEEDS_SIGNAL]
    - Crystal Vault Invariant Basis -> Ghost Classifier [FEEDS_SIGNAL]
    - Ghost Classifier -> Ghost Bridge [FEEDS_SIGNAL]
