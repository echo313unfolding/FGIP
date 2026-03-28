"""
JSONL export bridge for regime → graph ingestion.

v1.0 Outputs:
- receipts/regime/exports/<export_id>/regime_nodes.jsonl
- receipts/regime/exports/<export_id>/regime_edges.jsonl
- receipts/regime/exports/<export_id>/EXPORT_MANIFEST.json

v1.4 Full Graph Outputs:
- thesis_nodes.jsonl       THESIS nodes (canonical theses)
- regime_nodes.jsonl       REGIME_STATE nodes
- hypothesis_nodes.jsonl   HYPOTHESIS nodes (predictions)
- regime_edges.jsonl       MODULATES / INCREASES_RISK_FOR / AFFECTS_CONVICTION
- temporal_edges.jsonl     PRECEDES / LEADS
- belief_revision_edges.jsonl  SUPERSEDES
- hypothesis_edges.jsonl   PREDICTS / CONFIRMS / DID_NOT_MATERIALIZE
- EXPORT_MANIFEST.json     File SHA256s + input provenance

Design:
- Deterministic: given the same inputs + same regime receipt, produces same JSONL bytes
  (ordering is fixed, json dumps uses sort_keys=True, no random IDs).
- Receipt-linked: every node/edge carries receipt_id + calibration_hash for provenance.
- Safe ontology: edges are explicitly inferential.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from fgip.ontology.validator import validate_jsonl_export, ValidationResult


def _sha256_file(path: Path) -> str:
    """Compute SHA256 hash of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _json_line(obj: Any) -> str:
    """
    Serialize object to deterministic JSON line.

    - Dataclasses are converted to dicts
    - sort_keys=True for stable ordering
    - Compact separators (no extra whitespace)
    """
    if is_dataclass(obj):
        obj = asdict(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


# Timestamp fields that cause non-determinism if not normalized
TIMESTAMP_FIELDS = frozenset({
    "created_at", "timestamp", "exported_at", "generated_at", "evaluated_at",
    "evaluation_date",  # v1.4.1: EVALUATED_AT edge metadata
})


def _normalize_for_export(obj: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize object for deterministic export.

    Strips runtime timestamp fields from metadata to ensure
    identical inputs produce identical JSONL bytes.
    """
    result = dict(obj)

    # Normalize metadata if present
    if "metadata" in result:
        meta = result["metadata"]
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except json.JSONDecodeError:
                return result

        # Strip timestamp fields
        meta = {k: v for k, v in meta.items() if k not in TIMESTAMP_FIELDS}

        # Re-serialize with canonical formatting
        result["metadata"] = json.dumps(meta, sort_keys=True, separators=(",", ":"))

    return result


def write_jsonl(
    path: Path,
    rows: Iterable[Dict[str, Any]],
    *,
    normalize: bool = True,
) -> str:
    """
    Write rows to JSONL file.

    Args:
        path: Output file path
        rows: Iterable of dicts to write
        normalize: Strip timestamp fields for determinism (default True)

    Returns SHA256 hash of written file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            if normalize:
                r = _normalize_for_export(r)
            f.write(_json_line(r))
    return _sha256_file(path)


def export_regime_graph_jsonl(
    *,
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    output_root: str = "receipts/regime/exports",
    export_id: Optional[str] = None,
    regime_receipt_id: Optional[str] = None,
    calibration_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Write nodes/edges JSONL plus an export manifest with hashes.

    Args:
        nodes: Node dicts ready for insertion (already schema-compliant)
        edges: Edge dicts ready for insertion (already schema-compliant)
        output_root: Base directory for exports
        export_id: Optional fixed ID. If None, uses UTC timestamp
        regime_receipt_id: Should be the regime-run receipt id (for provenance)
        calibration_hash: Should match calibration receipt output

    Returns:
        Manifest dict with paths and hashes
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    export_id = export_id or f"regime-graph-export-{ts}"

    out_dir = Path(output_root) / export_id
    nodes_path = out_dir / "regime_nodes.jsonl"
    edges_path = out_dir / "regime_edges.jsonl"
    manifest_path = out_dir / "EXPORT_MANIFEST.json"

    # Ensure stable ordering for deterministic output
    nodes_sorted = sorted(
        nodes,
        key=lambda d: (d.get("node_type", ""), d.get("node_id", ""))
    )
    edges_sorted = sorted(
        edges,
        key=lambda d: (
            d.get("edge_type", ""),
            d.get("from_node_id", d.get("from_node", "")),
            d.get("to_node_id", d.get("to_node", "")),
        )
    )

    # Write JSONL files
    nodes_sha = write_jsonl(nodes_path, nodes_sorted)
    edges_sha = write_jsonl(edges_path, edges_sorted)

    # Build manifest
    manifest = {
        "export_id": export_id,
        "generated_at": ts,
        "inputs": {
            "regime_receipt_id": regime_receipt_id,
            "calibration_hash": calibration_hash,
            "nodes_count": len(nodes_sorted),
            "edges_count": len(edges_sorted),
        },
        "outputs": {
            "regime_nodes_jsonl": {
                "path": str(nodes_path),
                "sha256": nodes_sha,
            },
            "regime_edges_jsonl": {
                "path": str(edges_path),
                "sha256": edges_sha,
            },
        },
        "notes": [
            "All edges in this export are inferential by design.",
            "JSONL lines are deterministically serialized (sort_keys=True).",
            "Same inputs will produce identical JSONL bytes.",
        ],
    }

    # Write manifest
    out_dir.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n")

    manifest_sha = _sha256_file(manifest_path)
    manifest["outputs"]["export_manifest"] = {
        "path": str(manifest_path),
        "sha256": manifest_sha,
    }

    return manifest


def export_full_graph_jsonl(
    *,
    # Node categories
    thesis_nodes: List[Dict[str, Any]] = None,
    regime_nodes: List[Dict[str, Any]] = None,
    hypothesis_nodes: List[Dict[str, Any]] = None,
    # Edge categories
    regime_edges: List[Dict[str, Any]] = None,
    temporal_edges: List[Dict[str, Any]] = None,
    belief_revision_edges: List[Dict[str, Any]] = None,
    hypothesis_edges: List[Dict[str, Any]] = None,
    # Provenance
    output_root: str = "receipts/regime/exports",
    export_id: Optional[str] = None,
    regime_receipt_id: Optional[str] = None,
    calibration_hash: Optional[str] = None,
    negative_space_receipt_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Write full graph to categorized JSONL files plus manifest.

    Args:
        thesis_nodes: THESIS node dicts
        regime_nodes: REGIME_STATE node dicts
        hypothesis_nodes: HYPOTHESIS node dicts
        regime_edges: MODULATES / INCREASES_RISK_FOR / AFFECTS_CONVICTION edges
        temporal_edges: PRECEDES / LEADS edges
        belief_revision_edges: SUPERSEDES edges
        hypothesis_edges: PREDICTS / CONFIRMS / DID_NOT_MATERIALIZE edges
        output_root: Base directory for exports
        export_id: Optional fixed ID. If None, uses UTC timestamp
        regime_receipt_id: Regime-run receipt ID (for provenance)
        calibration_hash: Calibration receipt hash
        negative_space_receipt_id: Negative space receipt ID (for provenance)

    Returns:
        Manifest dict with paths and hashes
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    export_id = export_id or f"full-graph-export-{ts}"

    out_dir = Path(output_root) / export_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # Initialize empty lists if None
    thesis_nodes = thesis_nodes or []
    regime_nodes = regime_nodes or []
    hypothesis_nodes = hypothesis_nodes or []
    regime_edges = regime_edges or []
    temporal_edges = temporal_edges or []
    belief_revision_edges = belief_revision_edges or []
    hypothesis_edges = hypothesis_edges or []

    # Sort by (node_type, node_id) for deterministic output
    def sort_nodes(nodes: List[Dict]) -> List[Dict]:
        return sorted(nodes, key=lambda d: (d.get("node_type", ""), d.get("node_id", "")))

    # Sort by (edge_type, from_node_id, to_node_id) for deterministic output
    def sort_edges(edges: List[Dict]) -> List[Dict]:
        return sorted(edges, key=lambda d: (
            d.get("edge_type", ""),
            d.get("from_node_id", d.get("from_node", "")),
            d.get("to_node_id", d.get("to_node", "")),
        ))

    outputs = {}

    # Write node files
    node_files = [
        ("thesis_nodes.jsonl", thesis_nodes),
        ("regime_nodes.jsonl", regime_nodes),
        ("hypothesis_nodes.jsonl", hypothesis_nodes),
    ]

    total_nodes = 0
    for filename, nodes in node_files:
        if nodes:
            path = out_dir / filename
            sha = write_jsonl(path, sort_nodes(nodes))
            outputs[filename.replace(".jsonl", "")] = {
                "path": str(path),
                "sha256": sha,
                "count": len(nodes),
            }
            total_nodes += len(nodes)

    # Write edge files
    edge_files = [
        ("regime_edges.jsonl", regime_edges),
        ("temporal_edges.jsonl", temporal_edges),
        ("belief_revision_edges.jsonl", belief_revision_edges),
        ("hypothesis_edges.jsonl", hypothesis_edges),
    ]

    total_edges = 0
    for filename, edges in edge_files:
        if edges:
            path = out_dir / filename
            sha = write_jsonl(path, sort_edges(edges))
            outputs[filename.replace(".jsonl", "")] = {
                "path": str(path),
                "sha256": sha,
                "count": len(edges),
            }
            total_edges += len(edges)

    # Build manifest
    manifest = {
        "export_id": export_id,
        "generated_at": ts,
        "version": "1.4.0",
        "inputs": {
            "regime_receipt_id": regime_receipt_id,
            "calibration_hash": calibration_hash,
            "negative_space_receipt_id": negative_space_receipt_id,
        },
        "summary": {
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "thesis_nodes": len(thesis_nodes),
            "regime_nodes": len(regime_nodes),
            "hypothesis_nodes": len(hypothesis_nodes),
            "regime_edges": len(regime_edges),
            "temporal_edges": len(temporal_edges),
            "belief_revision_edges": len(belief_revision_edges),
            "hypothesis_edges": len(hypothesis_edges),
        },
        "outputs": outputs,
        "notes": [
            "Full graph export with categorized JSONL files.",
            "All edges are inferential by design.",
            "JSONL lines are deterministically serialized (sort_keys=True).",
            "Same inputs will produce identical JSONL bytes.",
            "hypothesis_edges includes PREDICTS, CONFIRMS, DID_NOT_MATERIALIZE.",
        ],
    }

    # Write manifest
    manifest_path = out_dir / "EXPORT_MANIFEST.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n")

    manifest_sha = _sha256_file(manifest_path)
    manifest["outputs"]["export_manifest"] = {
        "path": str(manifest_path),
        "sha256": manifest_sha,
    }

    return manifest


def run_full_export(
    *,
    receipts_dir: str = "THESIS_PACK/receipts/inflation",
    output_root: str = "receipts/regime/exports",
    start_date: str = "2020-01",
    include_hypotheses: bool = True,
    evaluation_date: Optional[str] = None,
    verbose: bool = True,
    validate: bool = True,
    strict: bool = False,
    max_warnings: Optional[int] = None,
) -> Dict[str, Any]:
    """
    High-level entry point: run full regime analysis and export all graph artifacts.

    This is the recommended way to generate a complete, graph-insertable export.

    Args:
        receipts_dir: Path to FRED CSV artifacts
        output_root: Base directory for exports
        start_date: Filter regime states to this date and later
        include_hypotheses: Include hypothesis generation and evaluation
        evaluation_date: Date to evaluate hypotheses against (default: latest)
        verbose: Print progress to stdout
        validate: Run ontology validation after export (default True)
        strict: Fail on warnings (default False)
        max_warnings: Maximum allowed warnings before failure (default None = unlimited)

    Returns:
        Export manifest dict
    """
    from .features_from_fred import extract_features
    from .regime_classifier import RegimeClassifier
    from .calibration import load_calibration
    from .graph_nodes import (
        generate_regime_nodes,
        generate_thesis_edges,
        generate_increases_risk_edges,
    )
    from .thesis_nodes import generate_thesis_nodes, CANONICAL_THESES, get_all_canonical_thesis_ids
    from .temporal_edges import (
        generate_regime_sequence_edges,
        generate_transition_edges,
        get_empirical_lead_edges,
    )
    from .belief_revision import apply_revision

    if verbose:
        print("Full Graph Export v1.4")
        print("=" * 50)

    # Step 1: Load calibration and extract features
    if verbose:
        print("\n[1/6] Loading calibration + features...")

    cal = load_calibration()
    if cal is None:
        from .calibration import calibrate
        cal = calibrate(receipts_dir, "receipts/regime")

    features, file_hashes = extract_features(receipts_dir)

    if verbose:
        print(f"      Features: {len(features)} months")
        print(f"      Calibration: {cal.calibration_hash[:16]}...")

    # Step 2: Classify regimes
    if verbose:
        print("\n[2/6] Classifying regimes...")

    classifier = RegimeClassifier(calibrated=cal)
    regimes = classifier.classify_series(features)
    filtered = [r for r in regimes if r.date >= start_date]

    if verbose:
        print(f"      Total: {len(regimes)}, filtered: {len(filtered)}")

    # Step 3: Generate thesis nodes
    if verbose:
        print("\n[3/6] Generating thesis nodes...")

    thesis_nodes = generate_thesis_nodes(CANONICAL_THESES)

    if verbose:
        print(f"      Thesis nodes: {len(thesis_nodes)}")

    # Step 4: Generate regime nodes and edges
    if verbose:
        print("\n[4/6] Generating regime nodes + edges...")

    regime_receipt_id = f"export-run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    regime_nodes = generate_regime_nodes(
        regimes,
        cal.calibration_hash,
        start_date=start_date,
        regime_receipt_id=regime_receipt_id,
    )

    # Apply belief revision to get versioned IDs + SUPERSEDES edges
    revision = apply_revision(
        regime_nodes + thesis_nodes,
        exports_root=output_root,
        reason="full_export",
    )

    # Use versioned nodes from revision
    all_versioned_nodes = revision.new_nodes + revision.unchanged_nodes + revision.superseded_nodes
    thesis_nodes_versioned = [n for n in all_versioned_nodes if n.get("node_type") == "THESIS"]
    regime_nodes_versioned = [n for n in all_versioned_nodes if n.get("node_type") == "REGIME_STATE"]

    # Generate regime → thesis edges (loop over each node)
    thesis_ids = get_all_canonical_thesis_ids()
    regime_edges = []
    for node, state in zip(regime_nodes_versioned, filtered):
        regime_edges.extend(generate_thesis_edges(node, thesis_ids, state))
        regime_edges.extend(generate_increases_risk_edges(node, thesis_ids, state))

    if verbose:
        print(f"      Regime nodes: {len(regime_nodes_versioned)}")
        print(f"      Regime edges: {len(regime_edges)}")
        print(f"      Belief revision: {revision.stats}")

    # Step 5: Generate temporal edges
    if verbose:
        print("\n[5/6] Generating temporal edges...")

    temporal_edges = generate_regime_sequence_edges(regime_nodes_versioned, filtered)
    temporal_edges += generate_transition_edges(regime_nodes_versioned, filtered)
    temporal_edges += get_empirical_lead_edges()

    if verbose:
        print(f"      Temporal edges: {len(temporal_edges)}")

    # Step 6: Generate hypothesis nodes + edges (optional)
    hypothesis_nodes = []
    hypothesis_edges = []
    negative_space_receipt_id = None

    if include_hypotheses:
        if verbose:
            print("\n[6/6] Generating hypothesis nodes + edges...")

        from .negative_space import (
            generate_all_v0_hypotheses,
            generate_hypothesis_nodes,
            generate_predicts_edges,
            run_hypothesis_evaluation,
        )

        # Generate hypotheses
        hypotheses = generate_all_v0_hypotheses(
            regime_states=filtered,
            regime_nodes=regime_nodes_versioned,
            target_thesis_ids=thesis_ids,
            calibration_hash=cal.calibration_hash,
            regime_receipt_id=regime_receipt_id,
        )

        # Generate hypothesis nodes
        hyp_nodes = generate_hypothesis_nodes(hypotheses)

        # Generate PREDICTS edges
        predicts_edges = []
        for hyp in hypotheses:
            node = {"node_id": hyp.hypothesis_id}  # Minimal for edge generation
            predicts_edges.extend(generate_predicts_edges(node, hyp))

        # Evaluate hypotheses and generate outcome + EVALUATED_AT edges
        eval_date = evaluation_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        outcome_edges, ns_receipt = run_hypothesis_evaluation(
            hypotheses=hypotheses,
            features=features,
            regime_states=regimes,
            current_date=eval_date,
            calibration_hash=cal.calibration_hash,
            regime_receipt_id=regime_receipt_id,
            regime_nodes=regime_nodes_versioned,  # For EVALUATED_AT edges
        )

        hypothesis_nodes = hyp_nodes
        hypothesis_edges = predicts_edges + outcome_edges
        negative_space_receipt_id = Path(ns_receipt).stem if ns_receipt else None

        if verbose:
            print(f"      Hypotheses generated: {len(hypotheses)}")
            print(f"      Hypothesis nodes: {len(hypothesis_nodes)}")
            print(f"      Hypothesis edges: {len(hypothesis_edges)}")
            print(f"      Receipt: {negative_space_receipt_id}")
    else:
        if verbose:
            print("\n[6/6] Skipping hypotheses (--include-hypotheses not set)")

    # Export to JSONL
    if verbose:
        print("\n" + "=" * 50)
        print("Writing JSONL files...")

    manifest = export_full_graph_jsonl(
        thesis_nodes=thesis_nodes_versioned,
        regime_nodes=regime_nodes_versioned,
        hypothesis_nodes=hypothesis_nodes,
        regime_edges=regime_edges,
        temporal_edges=temporal_edges,
        belief_revision_edges=revision.supersedes_edges,
        hypothesis_edges=hypothesis_edges,
        output_root=output_root,
        regime_receipt_id=regime_receipt_id,
        calibration_hash=cal.calibration_hash,
        negative_space_receipt_id=negative_space_receipt_id,
    )

    # Ontology validation (optional but recommended)
    if validate:
        if verbose:
            print("\n" + "=" * 50)
            print("Running ontology validation...")

        # Get export directory from manifest
        export_manifest_path = manifest["outputs"]["export_manifest"]["path"]
        export_dir = str(Path(export_manifest_path).parent)

        # Run validation
        validation_result = validate_jsonl_export(export_dir)

        # Build validation report
        validation_report = {
            "valid": validation_result.valid,
            "errors_count": len(validation_result.errors),
            "warnings_count": len(validation_result.warnings),
            "errors": validation_result.errors,
            "warnings": validation_result.warnings,
            "validated_at": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        }

        # Write validation report
        validation_path = Path(export_dir) / "VALIDATION_REPORT.json"
        with validation_path.open("w", encoding="utf-8") as f:
            f.write(json.dumps(validation_report, indent=2, sort_keys=True, ensure_ascii=False) + "\n")

        validation_sha = _sha256_file(validation_path)

        # Add validation to manifest
        manifest["outputs"]["validation_report"] = {
            "path": str(validation_path),
            "sha256": validation_sha,
            "valid": validation_result.valid,
            "errors": len(validation_result.errors),
            "warnings": len(validation_result.warnings),
        }

        # Rewrite manifest with validation info
        manifest_path = Path(export_manifest_path)
        with manifest_path.open("w", encoding="utf-8") as f:
            f.write(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n")

        # Update manifest hash (now includes validation)
        manifest["outputs"]["export_manifest"]["sha256"] = _sha256_file(manifest_path)

        if verbose:
            print(f"  Valid: {validation_result.valid}")
            print(f"  Errors: {len(validation_result.errors)}")
            print(f"  Warnings: {len(validation_result.warnings)}")
            print(f"  Report: {validation_path}")

        # Fail hard on errors
        if not validation_result.valid:
            raise RuntimeError(
                f"Ontology validation failed: {len(validation_result.errors)} errors. "
                f"See report: {validation_path}"
            )

        # Strict mode: fail on warnings
        if strict and len(validation_result.warnings) > 0:
            raise RuntimeError(
                f"Ontology validation strict mode: {len(validation_result.warnings)} warnings present. "
                f"See report: {validation_path}"
            )

        # Warning budget enforcement
        if max_warnings is not None and len(validation_result.warnings) > max_warnings:
            raise RuntimeError(
                f"Ontology validation warning budget exceeded: "
                f"{len(validation_result.warnings)} > {max_warnings}. "
                f"See report: {validation_path}"
            )

    if verbose:
        print(f"\nExport complete: {manifest['export_id']}")
        print(f"  Total nodes: {manifest['summary']['total_nodes']}")
        print(f"  Total edges: {manifest['summary']['total_edges']}")
        for name, info in manifest["outputs"].items():
            if name != "export_manifest" and isinstance(info, dict):
                print(f"  {name}: {info.get('count', 'N/A')} items, sha256={info['sha256'][:16]}...")

    return manifest


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="FGIP Graph Export (JSONL)"
    )
    parser.add_argument(
        "--receipts-dir",
        default="THESIS_PACK/receipts/inflation",
        help="Path to FRED CSV artifacts"
    )
    parser.add_argument(
        "--output-dir",
        default="receipts/regime/exports",
        help="Path to write exports"
    )
    parser.add_argument(
        "--start-date",
        default="2020-01",
        help="Filter regime states to this date and later"
    )
    parser.add_argument(
        "--include-hypotheses",
        action="store_true",
        help="Include hypothesis generation and evaluation"
    )
    parser.add_argument(
        "--evaluation-date",
        default=None,
        help="Date to evaluate hypotheses against (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress verbose output"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output manifest as JSON"
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip ontology validation"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on validation warnings (strict mode)"
    )
    parser.add_argument(
        "--max-warnings",
        type=int,
        default=None,
        help="Maximum allowed validation warnings before failure"
    )

    args = parser.parse_args()

    manifest = run_full_export(
        receipts_dir=args.receipts_dir,
        output_root=args.output_dir,
        start_date=args.start_date,
        include_hypotheses=args.include_hypotheses,
        evaluation_date=args.evaluation_date,
        verbose=not args.quiet and not args.json,
        validate=not args.no_validate,
        strict=args.strict,
        max_warnings=args.max_warnings,
    )

    if args.json:
        print(json.dumps(manifest, indent=2))
