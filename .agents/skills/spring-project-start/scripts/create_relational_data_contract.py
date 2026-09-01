#!/usr/bin/env python3
"""Materialize a prepared logical relational model and derived metadata."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from http_api_contract import encoded
from record_spec_approval import atomic_write_bytes
from relational_data_contract import derived_traceability, validate_relational_contract
from validate_design_route import assess
from validate_feature_specs import load_object


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--route", required=True, type=Path); parser.add_argument("--feature", required=True, type=Path)
    parser.add_argument("--project-brief", required=True, type=Path); parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path); parser.add_argument("--contract-id", required=True)
    parser.add_argument("--model-source", required=True, type=Path); parser.add_argument("--contract-output", required=True, type=Path)
    parser.add_argument("--model-output", required=True, type=Path)
    args = parser.parse_args(); created: list[tuple[Path, bytes]] = []
    try:
        root = args.target.resolve(strict=True); contract_output, model_output = args.contract_output.resolve(), args.model_output.resolve()
        for path, label in ((contract_output, "contract output"), (model_output, "model output")):
            if root not in (path, *path.parents): raise ValueError(f"{label} escapes target")
            if path.exists(): raise ValueError(f"{label} already exists; implicit overwrite is not allowed")
        route, feature, project, profile = load_object(args.route), load_object(args.feature), load_object(args.project_brief), load_object(args.profile)
        route_approved, profile_ready, route_blockers = assess(route, feature, project, profile, args.feature, args.project_brief, args.profile, root)
        if not route_approved or not profile_ready or route_blockers: raise ValueError("design route is not ready: " + "; ".join(route_blockers))
        matches = [item for item in route["routes"] if item.get("contractId") == args.contract_id]
        if len(matches) != 1: raise ValueError("contract-id must match exactly one route instance")
        selected = matches[0]
        if selected["kind"] != "PERSISTENCE" or selected["disposition"] != "CREATE": raise ValueError("selected route instance must be PERSISTENCE CREATE")
        if selected.get("artifactPath") != contract_output.relative_to(root).as_posix(): raise ValueError("contract output does not match route artifactPath")
        if model_output.parent != contract_output.parent: raise ValueError("logical model must be a sibling of its metadata")
        model = load_object(args.model_source); model_content = encoded(model)
        metadata = {
            "contractVersion": 1, "contractId": args.contract_id, "kind": "PERSISTENCE", "featureId": route["featureId"],
            "route": {"path": args.route.resolve().relative_to(root).as_posix(), "sha256": hashlib.sha256(args.route.read_bytes()).hexdigest()},
            "disposition": "CREATE", "target": selected["target"],
            "artifact": {"format": "DATA_MODEL", "path": model_output.relative_to(root).as_posix()},
            "modelSha256": hashlib.sha256(model_content).hexdigest(), "traceability": derived_traceability(model),
            "evidencePaths": selected["evidencePaths"],
            "approval": {"status": "DRAFT", "approvedBy": None, "approvedAt": None, "approvedContentSha256": None},
        }
        metadata_content = encoded(metadata)
        for path, content in ((model_output, model_content), (contract_output, metadata_content)):
            path.parent.mkdir(parents=True, exist_ok=True); atomic_write_bytes(content, path); created.append((path, content))
        _, blockers, _ = validate_relational_contract(metadata, route, args.route, root, contract_output, feature, profile)
    except (OSError, ValueError) as error:
        rollback_errors = []
        for path, expected in reversed(created):
            try:
                if path.read_bytes() != expected: raise OSError("created artifact changed externally; refusing rollback deletion")
                path.unlink()
            except OSError as rollback_error: rollback_errors.append(f"{path}: {rollback_error}")
        suffix = f"; rollback incomplete: {rollback_errors}" if rollback_errors else ""
        print(f"RELATIONAL_DATA_CONTRACT_CREATED: no\nERROR: {error}{suffix}"); return 1
    print("RELATIONAL_DATA_CONTRACT_CREATED: yes")
    print(f"CONTRACT_DRAFT_READY: {'yes' if not blockers else 'no'}")
    for blocker in blockers: print(f"BLOCKER: {blocker}")
    print("TARGET_SOURCE_CHANGED: no")
    print("DATABASE_OR_CONTAINER_CHANGED: no")
    return 0


if __name__ == "__main__": sys.exit(main())
