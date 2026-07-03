"""Echo OS Import/Call Crawler — diff code reality against architecture graph.

Crawls Python files across Echo OS repos, extracts imports and class
instantiations, maps them to known FGIP component IDs, then diffs
against the architecture graph edges to find:

1. architecture-yes / code-no  (graph says edge exists, code doesn't wire it)
2. code-yes / architecture-no  (code wires things the graph doesn't know about)
3. untested dependencies       (import exists, no TESTED_WITH edge)
4. duplicate functionality     (same class reimplemented in multiple repos)
5. highest-priority missing    (ranked by how many downstream things break)

Usage:
    python3 tools/import_crawler.py                    # full report
    python3 tools/import_crawler.py --json             # JSON output
    python3 tools/import_crawler.py --update-graph     # also insert discovered edges
"""

import ast
import json
import sys
import hashlib
import time
import resource
import platform
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# REPOS — directories to crawl
# ---------------------------------------------------------------------------

HOME = Path.home()

REPOS = {
    "helix-substrate": HOME / "helix-substrate",
    "helix-cdc":       HOME / "helix-cdc",
    "cell-runtime":    HOME / "cell-runtime",
    "fgip-engine":     HOME / "fgip-engine",
    "morphsat":        HOME / "morphsat",
    "sentinel":        HOME / "sentinel-hybrid-stack-public",
    "echo-origin-gold": HOME / "echo-origin-gold",
}

# ---------------------------------------------------------------------------
# COMPONENT REGISTRY — maps FGIP node_id to identifiable code patterns
# ---------------------------------------------------------------------------
# Each entry: node_id -> {
#   "classes": [class names that represent this component],
#   "modules": [module import paths],
#   "functions": [top-level functions],
#   "files": [canonical file globs],
# }

COMPONENT_REGISTRY = {
    # Layer 1: Codec
    "comp_hxq_codec": {
        "classes": ["HelixHfQuantizer", "HelixLinear", "HelixConfig"],
        "modules": ["helix_substrate", "helix_substrate.quantizer", "helix_substrate.helix_linear"],
        "functions": ["quantize_model", "dequantize_tensor"],
        "files": ["helix_substrate/quantizer.py", "helix_substrate/helix_linear.py"],
    },
    "comp_ggml_hxq": {
        "classes": [],
        "modules": [],
        "functions": [],
        "files": ["ggml-hxq.cu", "ggml-hxq.h"],  # C/CUDA, not Python-crawlable
    },
    "comp_helix_codec_c99": {
        "classes": [],
        "modules": ["helix_codec"],
        "functions": ["helix_quantize_6bit", "helix_dequantize_6bit"],
        "files": ["helix_codec.h", "helix_codec.c"],
    },
    "comp_helix_linear_ste": {
        "classes": ["HelixLinearSTE"],
        "modules": ["helix_substrate.ste", "helix_substrate.helix_linear_ste"],
        "functions": [],
        "files": ["helix_substrate/helix_linear_ste.py", "helix_substrate/ste.py"],
    },
    "comp_hxq_solana": {
        "classes": [],
        "modules": [],
        "functions": [],
        "files": ["programs/hxq-transfer-hook/**/*.rs"],  # Rust, not Python
    },

    # Layer 1.5: Symbol
    "comp_crystal_vault": {
        "classes": ["CrystalVault", "GlyphPacket", "ShadowMemory", "GhostFeatureExtractor"],
        "modules": ["crystal_vault", "helix_cdc.crystal_vault", "helix_substrate.ghost_bridge"],
        "functions": ["extract_ghost_features", "compute_invariants"],
        "files": ["crystal_vault/*.py", "helix_substrate/ghost_bridge.py"],
    },

    # Layer 2: Routing
    "comp_geometry_router": {
        "classes": ["GeometryRouter", "RouteDecision", "ProjectionSpace", "BasinMap",
                     "HandoffGauges", "Basin"],
        "modules": ["geometry_router", "geometry_router.decisions", "geometry_router.features",
                     "geometry_router.projection", "geometry_router.basins", "geometry_router.gauges",
                     "geometry_router.receipts"],
        "functions": ["extract_features", "features_to_vector", "route_tensor",
                       "classify_super_role", "classify_fine_role", "write_receipt"],
        "files": ["geometry_router/*.py", "echo-origin-gold/geometry_router/*.py"],
    },
    "comp_ghost_classifier": {
        "classes": ["GhostClassifier"],
        "modules": ["helix_substrate.ghost_classifier"],
        "functions": [],
        "files": ["helix_substrate/ghost_classifier.py"],
    },
    "comp_ghost_bridge": {
        "classes": ["GhostBridge"],
        "modules": ["helix_substrate.ghost_bridge"],
        "functions": ["ghost_pre_route", "extract_ghost_features"],
        "files": ["helix_substrate/ghost_bridge.py"],
    },
    "comp_hydra_router": {
        "classes": ["HydraRouter", "HydraPolicy", "HydraHead"],
        "modules": ["helix_substrate.hydra_router"],
        "functions": ["route", "route_with_ghost", "route_with_residuals"],
        "files": ["helix_substrate/hydra_router.py"],
    },
    "comp_residual_contract": {
        "classes": ["ResidualProfile", "DamageType"],
        "modules": ["helix_substrate.residual_contract"],
        "functions": ["compare_codecs", "residual_routing_signal"],
        "files": ["helix_substrate/residual_contract.py"],
    },
    "comp_residual_router": {
        "classes": ["ResidualRouter", "CorrectionType"],
        "modules": ["helix_substrate.residual_router"],
        "functions": ["decide_from_residual", "decide_from_candidates"],
        "files": ["helix_substrate/residual_router.py"],
    },
    "comp_gauge_routing": {
        "classes": ["GaugeRouter", "GaugeOnlyRouter"],
        "modules": ["helix_substrate.gauge_router", "helix_substrate.gauge_only_router"],
        "functions": [],
        "files": ["helix_substrate/gauge_router.py", "helix_substrate/gauge_only_router.py"],
    },
    "comp_se_depth_router": {
        "classes": ["SeDepthRouter", "SeRouter"],
        "modules": ["helix_cdc.se_router", "helix_cdc.regrow"],
        "functions": ["compute_se", "se_route"],
        "files": ["helix_cdc/se_router.py"],
    },
    "comp_quant_router": {
        "classes": ["QuantRouter", "RouterDecision"],
        "modules": ["tools.router", "router"],
        "functions": ["route_model", "profile_model"],
        "files": ["tools/router/*.py"],
    },

    # Layer 3: Memory
    "comp_seedstore": {
        "classes": ["SeedStore"],
        "modules": ["helix_cdc.seedstore", "helix_cdc.seed_store"],
        "functions": [],
        "files": ["helix_cdc/seedstore.py", "helix_cdc/seed_store.py"],
    },
    "comp_vault_client": {
        "classes": ["VaultClient"],
        "modules": ["helix_cdc.vault_client"],
        "functions": [],
        "files": ["helix_cdc/vault_client.py"],
    },
    "comp_fibpi_anchor": {
        "classes": ["FibPiAnchor", "FibPiSHA"],
        "modules": ["helix_cdc.fibpi", "helix_cdc.fibpi_anchor"],
        "functions": ["fibpi_sha256"],
        "files": ["helix_cdc/fibpi*.py"],
    },
    "comp_capsule_manifest": {
        "classes": ["CapsuleManifest", "Capsule", "Genotype", "BloodType"],
        "modules": ["helix_cdc.capsule", "helix_cdc.capsule_manifest"],
        "functions": [],
        "files": ["helix_cdc/capsule*.py"],
    },
    "comp_weight_page_lib": {
        "classes": ["WeightPageLibrary", "TensorPage"],
        "modules": ["cell_runtime.weight_page", "weight_page_library"],
        "functions": [],
        "files": ["cell-runtime/**/weight_page*.py"],
    },
    "comp_echo_memory": {
        "classes": [],
        "modules": ["echo_nav"],
        "functions": ["search_memory", "ledger_read"],
        "files": ["tools/echo_nav*.py"],
    },

    # Layer 4: Runtime
    "comp_krisper": {
        "classes": ["KrisperEngine", "KrisperOp"],
        "modules": ["cell.krisper", "cell.krisper.engine", "krisper"],
        "functions": ["dispatch", "execute_op"],
        "files": ["cell/krisper/engine.py", "cell/krisper/*.py"],
    },
    "comp_biopoetica": {
        "classes": ["BioPoeticaCompiler", "PoemCompiler"],
        "modules": ["cell.biopoetica", "cell.biopoetica.compiler", "biopoetica"],
        "functions": ["compile_poem", "emit"],
        "files": ["cell/biopoetica/*.py"],
    },
    "comp_cell_runtime": {
        "classes": ["CellRuntime"],
        "modules": ["cell_runtime", "cell"],
        "functions": [],
        "files": ["cell-runtime/src/cell/*.py"],
    },
    "comp_specialist_pool": {
        "classes": ["SpecialistPool", "SkillCartridge", "ShardConfig"],
        "modules": ["cell.specialist_pool", "cell.agents"],
        "functions": [],
        "files": ["cell/specialist_pool.py", "cell/agents/*.py"],
    },
    "comp_agent_substrate": {
        "classes": ["Orchestrator", "ToolRegistry", "AgentBase"],
        "modules": ["cell.orchestrator", "cell.tool_registry"],
        "functions": [],
        "files": ["cell/orchestrator.py", "cell/tool_registry.py"],
    },
    "comp_basin_server": {
        "classes": [],
        "modules": ["basin_server"],
        "functions": [],
        "files": ["api/basin_server.py"],
    },
    "comp_qwen_backend": {
        "classes": ["LlamaServerBackend", "QwenBackend"],
        "modules": ["echo_cog.backend_llama_cpp", "cell.backends"],
        "functions": [],
        "files": ["echo_cog/backend_llama_cpp.py"],
    },

    # Layer 5: Safety
    "comp_morphsat": {
        "classes": ["ShadowMonitor", "MorphSATGate", "TwoStageGate", "ReceiptChain",
                     "ReceiptGraph", "CorrectionEcho", "EchoMarker"],
        "modules": ["morphsat", "morphsat.shadow_monitor", "morphsat.receipt_chain",
                     "morphsat.receipt_graph"],
        "functions": [],
        "files": ["morphsat/*.py", "morphsat/**/*.py"],
    },
    "comp_echo_sentry": {
        "classes": ["SentinelMonitor", "Sentinel", "SentinelEngine"],
        "modules": ["sentinel", "sentinel.monitor", "echo_sentry"],
        "functions": [],
        "files": ["sentinel/*.py", "echo_sentry/*.py"],
    },
    "comp_krisper_gate": {
        "classes": ["MorphSATGate", "GateVerdict"],
        "modules": ["cell.krisper.gate"],
        "functions": ["check_gate", "gate_check"],
        "files": ["cell/krisper/gate.py"],
    },

    # Layer 6: Evidence
    "comp_fgip_graph": {
        "classes": ["FGIPDatabase", "Node", "Edge", "Claim"],
        "modules": ["fgip", "fgip.db", "fgip.schema"],
        "functions": [],
        "files": ["fgip/db.py", "fgip/schema.py"],
    },
    "comp_receipt_spine": {
        "classes": [],
        "modules": [],
        "functions": [],
        "files": ["receipts/*.json"],  # not Python
    },
    "comp_audit_hook": {
        "classes": [],
        "modules": [],
        "functions": [],
        "files": ["tools/claude_audit_hook.sh"],  # bash, not Python
    },
    "comp_echo_nav": {
        "classes": [],
        "modules": ["echo_nav"],
        "functions": ["box_orient", "search_memory", "ledger_read", "find_symbol"],
        "files": ["tools/echo_nav*.py", "tools/echo_nav_wrapper.sh"],
    },

    # Layer 7: Apps
    "comp_shop_app": {
        "classes": [],
        "modules": [],
        "functions": [],
        "files": ["mcelroy-inventory/*.py"],
    },
    "comp_fgip_web": {
        "classes": [],
        "modules": ["web.app"],
        "functions": [],
        "files": ["fgip-engine/web/*.py"],
    },
    "comp_ghost_me": {
        "classes": [],
        "modules": [],
        "functions": [],
        "files": ["ghost-me/*.py"],
    },
}


# ---------------------------------------------------------------------------
# DATA STRUCTURES
# ---------------------------------------------------------------------------

@dataclass
class ImportRecord:
    """A single import found in a Python file."""
    source_file: str          # absolute path of the importing file
    source_repo: str          # which repo it belongs to
    import_module: str        # the module being imported
    imported_names: list      # specific names imported (from X import Y,Z)
    line_number: int

@dataclass
class InstantiationRecord:
    """A class instantiation found in a Python file."""
    source_file: str
    source_repo: str
    class_name: str
    line_number: int
    context: str = ""         # surrounding code snippet

@dataclass
class CodeEdge:
    """A discovered code-level dependency between two components."""
    from_component: str       # FGIP node_id of the importing component
    to_component: str         # FGIP node_id of the imported component
    edge_type: str            # CODE_IMPORTS, CODE_CALLS, CODE_INSTANTIATES
    source_file: str
    line_number: int
    detail: str = ""

@dataclass
class DiffResult:
    """Result of diffing code edges against architecture graph."""
    arch_yes_code_no: list = field(default_factory=list)    # graph has edge, code doesn't
    code_yes_arch_no: list = field(default_factory=list)    # code has edge, graph doesn't
    untested: list = field(default_factory=list)            # import exists, no TESTED_WITH
    duplicates: list = field(default_factory=list)          # same class in multiple repos
    confirmed: list = field(default_factory=list)           # both agree


# ---------------------------------------------------------------------------
# AST CRAWLER
# ---------------------------------------------------------------------------

def crawl_file(filepath: Path, repo_name: str) -> tuple[list[ImportRecord], list[InstantiationRecord]]:
    """Parse a single Python file for imports and class instantiations."""
    imports = []
    instantiations = []

    try:
        source = filepath.read_text(errors="replace")
        tree = ast.parse(source, filename=str(filepath))
    except (SyntaxError, UnicodeDecodeError, FileNotFoundError, OSError):
        return imports, instantiations

    for node in ast.walk(tree):
        # import X
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(ImportRecord(
                    source_file=str(filepath),
                    source_repo=repo_name,
                    import_module=alias.name,
                    imported_names=[],
                    line_number=node.lineno,
                ))

        # from X import Y, Z
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names = [a.name for a in (node.names or [])]
                imports.append(ImportRecord(
                    source_file=str(filepath),
                    source_repo=repo_name,
                    import_module=node.module,
                    imported_names=names,
                    line_number=node.lineno,
                ))

        # X() — class instantiation
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                instantiations.append(InstantiationRecord(
                    source_file=str(filepath),
                    source_repo=repo_name,
                    class_name=node.func.id,
                    line_number=node.lineno,
                ))
            elif isinstance(node.func, ast.Attribute):
                instantiations.append(InstantiationRecord(
                    source_file=str(filepath),
                    source_repo=repo_name,
                    class_name=node.func.attr,
                    line_number=node.lineno,
                ))

    return imports, instantiations


def crawl_repo(repo_path: Path, repo_name: str) -> tuple[list[ImportRecord], list[InstantiationRecord]]:
    """Crawl all Python files in a repo."""
    all_imports = []
    all_instantiations = []

    if not repo_path.exists():
        return all_imports, all_instantiations

    for py_file in sorted(repo_path.rglob("*.py")):
        # Skip __pycache__, .git, venv, etc.
        parts = py_file.parts
        if any(p.startswith(".") or p == "__pycache__" or p in ("venv", ".venv", "node_modules") for p in parts):
            continue

        imps, insts = crawl_file(py_file, repo_name)
        all_imports.extend(imps)
        all_instantiations.extend(insts)

    return all_imports, all_instantiations


# ---------------------------------------------------------------------------
# COMPONENT RESOLUTION — map imports/calls to FGIP component IDs
# ---------------------------------------------------------------------------

def _file_belongs_to_component(filepath: str) -> Optional[str]:
    """Determine which component a source file itself belongs to."""
    fp = Path(filepath)
    for comp_id, registry in COMPONENT_REGISTRY.items():
        for cls in registry.get("classes", []):
            # Check if the file defines this class
            pass  # handled by import matching
        for mod in registry.get("modules", []):
            # Convert module path to file path pattern
            mod_path = mod.replace(".", "/")
            if mod_path in str(fp) or str(fp).endswith(f"{mod_path}.py"):
                return comp_id
    return None


def resolve_import_to_component(imp: ImportRecord) -> Optional[str]:
    """Map an import to a FGIP component ID."""
    mod = imp.import_module
    names = imp.imported_names

    for comp_id, registry in COMPONENT_REGISTRY.items():
        # Check module match
        for reg_mod in registry.get("modules", []):
            if mod == reg_mod or mod.startswith(reg_mod + "."):
                return comp_id

        # Check imported class names
        for cls in registry.get("classes", []):
            if cls in names:
                return comp_id

        # Check imported function names
        for func in registry.get("functions", []):
            if func in names:
                return comp_id

    return None


def resolve_instantiation_to_component(inst: InstantiationRecord) -> Optional[str]:
    """Map a class instantiation to a FGIP component ID."""
    for comp_id, registry in COMPONENT_REGISTRY.items():
        if inst.class_name in registry.get("classes", []):
            return comp_id
    return None


def identify_source_component(filepath: str, repo_name: str) -> Optional[str]:
    """Identify which component the source file belongs to (the 'from' side)."""
    fp = Path(filepath)
    rel = str(fp)

    for comp_id, registry in COMPONENT_REGISTRY.items():
        for mod in registry.get("modules", []):
            mod_path = mod.replace(".", "/")
            if f"/{mod_path}/" in rel or rel.endswith(f"/{mod_path}.py") or f"/{mod_path.split('.')[-1]}/" in rel:
                return comp_id

        for fpattern in registry.get("files", []):
            # Simple substring match on the canonical file paths
            clean = fpattern.replace("**/", "").replace("*.py", "")
            if clean and clean in rel:
                return comp_id

    # Fallback: try to match by repo + directory structure
    repo_component_map = {
        "helix-substrate": None,  # too many components
        "helix-cdc": None,
        "cell-runtime": "comp_cell_runtime",
        "fgip-engine": "comp_fgip_graph",
        "morphsat": "comp_morphsat",
        "sentinel": "comp_echo_sentry",
    }

    if repo_name in repo_component_map:
        fallback = repo_component_map[repo_name]
        if fallback:
            return fallback

    return None


# ---------------------------------------------------------------------------
# GRAPH LOADER — read edges from FGIP database
# ---------------------------------------------------------------------------

def load_graph_edges(db_path: str) -> list[dict]:
    """Load all EchoOS-domain edges from the FGIP database."""
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get all edges involving comp_ or layer_ nodes
    rows = conn.execute("""
        SELECT edge_id, edge_type, from_node_id, to_node_id, claim_id, confidence, notes
        FROM edges
        WHERE from_node_id LIKE 'comp_%' OR from_node_id LIKE 'layer_%'
           OR to_node_id LIKE 'comp_%' OR to_node_id LIKE 'layer_%'
    """).fetchall()

    edges = [dict(r) for r in rows]
    conn.close()
    return edges


def load_graph_nodes(db_path: str) -> dict:
    """Load all component/layer nodes."""
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT node_id, name, node_type, description
        FROM nodes
        WHERE node_id LIKE 'comp_%' OR node_id LIKE 'layer_%'
    """).fetchall()

    nodes = {r["node_id"]: dict(r) for r in rows}
    conn.close()
    return nodes


# ---------------------------------------------------------------------------
# DIFF ENGINE
# ---------------------------------------------------------------------------

def build_code_edges(all_imports: list[ImportRecord],
                     all_instantiations: list[InstantiationRecord]) -> list[CodeEdge]:
    """Convert raw imports/instantiations into component-level edges."""
    edges = []
    seen = set()

    for imp in all_imports:
        from_comp = identify_source_component(imp.source_file, imp.source_repo)
        to_comp = resolve_import_to_component(imp)

        if from_comp and to_comp and from_comp != to_comp:
            key = (from_comp, to_comp, "CODE_IMPORTS")
            if key not in seen:
                seen.add(key)
                edges.append(CodeEdge(
                    from_component=from_comp,
                    to_component=to_comp,
                    edge_type="CODE_IMPORTS",
                    source_file=imp.source_file,
                    line_number=imp.line_number,
                    detail=f"import {imp.import_module}" + (f" ({', '.join(imp.imported_names)})" if imp.imported_names else ""),
                ))

    for inst in all_instantiations:
        from_comp = identify_source_component(inst.source_file, inst.source_repo)
        to_comp = resolve_instantiation_to_component(inst)

        if from_comp and to_comp and from_comp != to_comp:
            key = (from_comp, to_comp, "CODE_INSTANTIATES")
            if key not in seen:
                seen.add(key)
                edges.append(CodeEdge(
                    from_component=from_comp,
                    to_component=to_comp,
                    edge_type="CODE_INSTANTIATES",
                    source_file=inst.source_file,
                    line_number=inst.line_number,
                    detail=f"{inst.class_name}()",
                ))

    return edges


def find_duplicates(all_instantiations: list[InstantiationRecord],
                    all_imports: list[ImportRecord]) -> list[dict]:
    """Find classes that appear in multiple repos (potential reimplementation)."""
    # Track which class names are defined vs imported across repos
    all_known_classes = set()
    for reg in COMPONENT_REGISTRY.values():
        all_known_classes.update(reg.get("classes", []))

    # Track which repos import which known classes
    class_repos = defaultdict(set)
    for imp in all_imports:
        for name in imp.imported_names:
            if name in all_known_classes:
                class_repos[name].add(imp.source_repo)

    for inst in all_instantiations:
        if inst.class_name in all_known_classes:
            class_repos[inst.class_name].add(inst.source_repo)

    duplicates = []
    for cls, repos in class_repos.items():
        if len(repos) > 1:
            duplicates.append({
                "class": cls,
                "repos": sorted(repos),
                "note": f"'{cls}' used across {len(repos)} repos: {', '.join(sorted(repos))}",
            })

    return duplicates


def diff_edges(code_edges: list[CodeEdge], graph_edges: list[dict],
               graph_nodes: dict) -> DiffResult:
    """Compare code-discovered edges against architecture graph."""
    result = DiffResult()

    # Normalize graph edges into (from, to, type) tuples
    graph_pairs = set()
    graph_tested = set()
    graph_missing = set()
    graph_depends = set()
    graph_feeds = set()

    for ge in graph_edges:
        f, t = ge["from_node_id"], ge["to_node_id"]
        etype = ge["edge_type"]

        if etype == "TESTED_WITH":
            graph_tested.add((f, t))
            graph_tested.add((t, f))  # bidirectional
        elif etype == "MISSING_INTEGRATION":
            graph_missing.add((f, t))
        elif etype == "DEPENDS_ON":
            graph_depends.add((f, t))
        elif etype == "FEEDS_SIGNAL":
            graph_feeds.add((f, t))

        graph_pairs.add((f, t, etype))

    code_pairs = set()
    for ce in code_edges:
        code_pairs.add((ce.from_component, ce.to_component))

    # 1. Architecture-yes, code-no
    for ge in graph_edges:
        f, t = ge["from_node_id"], ge["to_node_id"]
        etype = ge["edge_type"]

        # Only check dependency/signal/routing edges (not MEMBER_OF_LAYER)
        if etype in ("DEPENDS_ON", "FEEDS_SIGNAL", "GATES", "ROUTES_TO"):
            if (f, t) not in code_pairs and (t, f) not in code_pairs:
                # Check if these are both comp_ nodes (not layer_ nodes)
                if f.startswith("comp_") and t.startswith("comp_"):
                    f_name = graph_nodes.get(f, {}).get("name", f)
                    t_name = graph_nodes.get(t, {}).get("name", t)
                    result.arch_yes_code_no.append({
                        "from": f, "to": t, "type": etype,
                        "from_name": f_name, "to_name": t_name,
                        "notes": ge.get("notes", ""),
                    })

    # 2. Code-yes, architecture-no
    for ce in code_edges:
        f, t = ce.from_component, ce.to_component
        # Check if any graph edge exists between these components
        has_graph_edge = any(
            (ge["from_node_id"] == f and ge["to_node_id"] == t) or
            (ge["from_node_id"] == t and ge["to_node_id"] == f)
            for ge in graph_edges
        )
        if not has_graph_edge:
            f_name = graph_nodes.get(f, {}).get("name", f)
            t_name = graph_nodes.get(t, {}).get("name", t)
            result.code_yes_arch_no.append({
                "from": f, "to": t,
                "from_name": f_name, "to_name": t_name,
                "code_type": ce.edge_type,
                "source_file": ce.source_file,
                "line": ce.line_number,
                "detail": ce.detail,
            })

    # 3. Untested: code imports exist but no TESTED_WITH edge
    for ce in code_edges:
        f, t = ce.from_component, ce.to_component
        if (f, t) not in graph_tested:
            f_name = graph_nodes.get(f, {}).get("name", f)
            t_name = graph_nodes.get(t, {}).get("name", t)
            result.untested.append({
                "from": f, "to": t,
                "from_name": f_name, "to_name": t_name,
                "source_file": ce.source_file,
                "line": ce.line_number,
            })

    # 4. Confirmed: both code and graph agree
    for ce in code_edges:
        f, t = ce.from_component, ce.to_component
        has_graph_edge = any(
            (ge["from_node_id"] == f and ge["to_node_id"] == t) or
            (ge["from_node_id"] == t and ge["to_node_id"] == f)
            for ge in graph_edges
            if ge["edge_type"] in ("DEPENDS_ON", "FEEDS_SIGNAL", "GATES", "ROUTES_TO", "TESTED_WITH")
        )
        if has_graph_edge:
            f_name = graph_nodes.get(f, {}).get("name", f)
            t_name = graph_nodes.get(t, {}).get("name", t)
            result.confirmed.append({
                "from": f, "to": t,
                "from_name": f_name, "to_name": t_name,
                "code_type": ce.edge_type,
                "detail": ce.detail,
            })

    return result


# ---------------------------------------------------------------------------
# REPORT
# ---------------------------------------------------------------------------

def format_report(result: DiffResult, duplicates: list, code_edges: list,
                  stats: dict) -> str:
    """Format the diff result as a readable report."""
    lines = []
    lines.append("=" * 72)
    lines.append("ECHO OS IMPORT CRAWLER — Architecture vs Code Diff Report")
    lines.append("=" * 72)
    lines.append("")

    # Stats
    lines.append(f"Repos crawled:     {stats['repos_crawled']}")
    lines.append(f"Python files:      {stats['files_crawled']}")
    lines.append(f"Total imports:     {stats['total_imports']}")
    lines.append(f"Total calls:       {stats['total_instantiations']}")
    lines.append(f"Resolved edges:    {stats['resolved_edges']}")
    lines.append(f"Graph edges:       {stats['graph_edges']}")
    lines.append("")

    # Section 1: Architecture says yes, code says no
    lines.append("-" * 72)
    lines.append(f"1. ARCHITECTURE-YES / CODE-NO  ({len(result.arch_yes_code_no)} edges)")
    lines.append("   Graph says dependency exists, but no import/call found in code")
    lines.append("-" * 72)
    if result.arch_yes_code_no:
        for item in result.arch_yes_code_no:
            lines.append(f"  {item['from_name']} --[{item['type']}]--> {item['to_name']}")
            lines.append(f"    graph: {item['from']} -> {item['to']}")
            if item.get("notes"):
                lines.append(f"    notes: {item['notes']}")
            lines.append("")
    else:
        lines.append("  (none)")
    lines.append("")

    # Section 2: Code says yes, architecture says no
    lines.append("-" * 72)
    lines.append(f"2. CODE-YES / ARCHITECTURE-NO  ({len(result.code_yes_arch_no)} edges)")
    lines.append("   Code imports/calls exist but graph has no edge")
    lines.append("-" * 72)
    if result.code_yes_arch_no:
        for item in result.code_yes_arch_no:
            lines.append(f"  {item['from_name']} --[{item['code_type']}]--> {item['to_name']}")
            lines.append(f"    file: {item['source_file']}:{item['line']}")
            lines.append(f"    code: {item['detail']}")
            lines.append("")
    else:
        lines.append("  (none)")
    lines.append("")

    # Section 3: Untested dependencies
    lines.append("-" * 72)
    lines.append(f"3. UNTESTED DEPENDENCIES  ({len(result.untested)} edges)")
    lines.append("   Import exists but no TESTED_WITH edge in graph")
    lines.append("-" * 72)
    if result.untested:
        for item in result.untested:
            lines.append(f"  {item['from_name']} -> {item['to_name']}")
            lines.append(f"    file: {item['source_file']}:{item['line']}")
            lines.append("")
    else:
        lines.append("  (none)")
    lines.append("")

    # Section 4: Duplicate functionality
    lines.append("-" * 72)
    lines.append(f"4. CROSS-REPO CLASS USAGE  ({len(duplicates)} classes)")
    lines.append("   Same class used across multiple repos (may indicate duplication or shared dependency)")
    lines.append("-" * 72)
    if duplicates:
        for d in duplicates:
            lines.append(f"  {d['class']}: {d['note']}")
    else:
        lines.append("  (none)")
    lines.append("")

    # Section 5: Confirmed (both agree)
    lines.append("-" * 72)
    lines.append(f"5. CONFIRMED EDGES  ({len(result.confirmed)} edges)")
    lines.append("   Both code and architecture graph agree")
    lines.append("-" * 72)
    if result.confirmed:
        for item in result.confirmed:
            lines.append(f"  {item['from_name']} --[{item['code_type']}]--> {item['to_name']}")
            lines.append(f"    code: {item['detail']}")
    else:
        lines.append("  (none)")
    lines.append("")

    # Summary
    lines.append("=" * 72)
    lines.append("SUMMARY")
    lines.append("=" * 72)
    total_gaps = len(result.arch_yes_code_no)
    total_undoc = len(result.code_yes_arch_no)
    total_untested = len(result.untested)
    total_confirmed = len(result.confirmed)

    lines.append(f"  Confirmed integrations:       {total_confirmed}")
    lines.append(f"  Graph-only (missing code):     {total_gaps}")
    lines.append(f"  Code-only (undocumented):      {total_undoc}")
    lines.append(f"  Untested dependencies:         {total_untested}")
    lines.append(f"  Cross-repo class usage:        {len(duplicates)}")

    if total_gaps > 0:
        lines.append("")
        lines.append("  PRIORITY: Wire these missing integrations first:")
        for item in result.arch_yes_code_no[:5]:
            lines.append(f"    - {item['from_name']} -> {item['to_name']} [{item['type']}]")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    t_start = time.time()
    cpu_start = time.process_time()

    json_mode = "--json" in sys.argv
    update_graph = "--update-graph" in sys.argv

    db_path = str(Path(__file__).resolve().parents[1] / "fgip.db")

    # ---- Crawl all repos ----
    all_imports = []
    all_instantiations = []
    files_crawled = 0
    repos_crawled = 0

    for repo_name, repo_path in REPOS.items():
        if not repo_path.exists():
            print(f"  SKIP {repo_name}: {repo_path} not found")
            continue
        repos_crawled += 1
        imps, insts = crawl_repo(repo_path, repo_name)
        py_count = sum(1 for _ in repo_path.rglob("*.py")
                       if not any(p.startswith(".") or p == "__pycache__" for p in _.parts))
        files_crawled += py_count
        all_imports.extend(imps)
        all_instantiations.extend(insts)
        print(f"  {repo_name}: {py_count} files, {len(imps)} imports, {len(insts)} calls")

    # ---- Resolve to component edges ----
    code_edges = build_code_edges(all_imports, all_instantiations)
    print(f"\nResolved {len(code_edges)} component-level edges from code")

    # ---- Find duplicates ----
    duplicates = find_duplicates(all_instantiations, all_imports)

    # ---- Load graph ----
    graph_edges = load_graph_edges(db_path)
    graph_nodes = load_graph_nodes(db_path)
    print(f"Loaded {len(graph_edges)} graph edges, {len(graph_nodes)} nodes")

    # ---- Diff ----
    result = diff_edges(code_edges, graph_edges, graph_nodes)

    # ---- Stats ----
    cost = {
        "wall_time_s": round(time.time() - t_start, 3),
        "cpu_time_s": round(time.process_time() - cpu_start, 3),
        "peak_memory_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        "python_version": platform.python_version(),
        "hostname": platform.node(),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    stats = {
        "repos_crawled": repos_crawled,
        "files_crawled": files_crawled,
        "total_imports": len(all_imports),
        "total_instantiations": len(all_instantiations),
        "resolved_edges": len(code_edges),
        "graph_edges": len(graph_edges),
        "confirmed": len(result.confirmed),
        "arch_yes_code_no": len(result.arch_yes_code_no),
        "code_yes_arch_no": len(result.code_yes_arch_no),
        "untested": len(result.untested),
        "duplicates": len(duplicates),
    }

    if json_mode:
        output = {
            "stats": stats,
            "cost": cost,
            "arch_yes_code_no": result.arch_yes_code_no,
            "code_yes_arch_no": result.code_yes_arch_no,
            "untested": result.untested,
            "duplicates": duplicates,
            "confirmed": result.confirmed,
            "code_edges": [asdict(e) for e in code_edges],
        }
        out_path = Path(__file__).resolve().parents[1] / "reports" / "echo_os_import_graph.json"
        out_path.parent.mkdir(exist_ok=True)
        out_path.write_text(json.dumps(output, indent=2))
        print(f"\nJSON written to {out_path}")
    else:
        report = format_report(result, duplicates, code_edges, stats)
        print(report)

        # Also write the report
        out_path = Path(__file__).resolve().parents[1] / "reports" / "echo_os_graph_diff.md"
        out_path.parent.mkdir(exist_ok=True)
        out_path.write_text(report)
        print(f"Report written to {out_path}")

    print(f"\nCost: {cost['wall_time_s']}s wall, {cost['cpu_time_s']}s CPU, {cost['peak_memory_mb']} MB peak")


if __name__ == "__main__":
    main()
