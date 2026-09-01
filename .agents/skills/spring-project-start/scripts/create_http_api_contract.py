#!/usr/bin/env python3
"""Materialize a reviewed OpenAPI draft and derived HTTP contract metadata safely."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from http_api_contract import derived_traceability, encoded, validate_http_contract
from record_spec_approval import atomic_write_bytes
from validate_design_contract import inside, sha256
from validate_design_route import assess
from validate_feature_specs import load_object


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--route", required=True, type=Path)
    parser.add_argument("--feature", required=True, type=Path)
    parser.add_argument("--project-brief", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--contract-id", required=True)
    parser.add_argument("--openapi-source", required=True, type=Path)
    parser.add_argument("--contract-output", required=True, type=Path)
    parser.add_argument("--openapi-output", required=True, type=Path)
    args = parser.parse_args()
    created: list[tuple[Path, bytes]] = []
    try:
        root = args.target.resolve(strict=True)
        contract_output = inside(root, args.contract_output.resolve().relative_to(root).as_posix(), "contract output")
        openapi_output = inside(root, args.openapi_output.resolve().relative_to(root).as_posix(), "OpenAPI output")
        if contract_output.exists() or openapi_output.exists():
            raise ValueError("contract outputs already exist; implicit overwrite is not allowed")
        route = load_object(args.route)
        feature = load_object(args.feature)
        project = load_object(args.project_brief)
        profile = load_object(args.profile)
        approved, profile_ready, route_blockers = assess(
            route, feature, project, profile,
            args.feature, args.project_brief, args.profile, root,
        )
        if not approved or not profile_ready or route_blockers:
            raise ValueError("design route is not ready: " + "; ".join(route_blockers))
        matches = [item for item in route["routes"] if item.get("contractId") == args.contract_id]
        if len(matches) != 1:
            raise ValueError("contract-id must match exactly one route instance")
        selected = matches[0]
        if selected["kind"] != "HTTP_API" or selected["disposition"] != "CREATE":
            raise ValueError("selected route instance must be HTTP_API CREATE")
        if selected.get("artifactPath") != contract_output.relative_to(root).as_posix():
            raise ValueError("contract output does not match route artifactPath")
        openapi = load_object(args.openapi_source)
        metadata = {
            "contractVersion": 1, "contractId": args.contract_id, "kind": "HTTP_API",
            "featureId": route["featureId"],
            "route": {"path": args.route.resolve().relative_to(root).as_posix(), "sha256": sha256(args.route)},
            "disposition": "CREATE", "target": selected["target"],
            "artifact": {"format": "OPENAPI", "path": openapi_output.relative_to(root).as_posix()},
            "traceability": derived_traceability(openapi), "evidencePaths": selected["evidencePaths"],
            "approval": {"status": "DRAFT", "approvedBy": None, "approvedAt": None, "approvedContentSha256": None},
        }
        openapi_content = encoded(openapi)
        metadata_content = encoded(metadata)
        openapi_output.parent.mkdir(parents=True, exist_ok=True)
        contract_output.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(openapi_content, openapi_output)
        created.append((openapi_output, openapi_content))
        atomic_write_bytes(metadata_content, contract_output)
        created.append((contract_output, metadata_content))
        _, blockers, _ = validate_http_contract(
            metadata, route, args.route, root, contract_output, feature, profile,
        )
    except (OSError, ValueError) as error:
        rollback_errors: list[str] = []
        for path, expected in reversed(created):
            try:
                if path.read_bytes() != expected:
                    raise OSError("created artifact changed externally; refusing rollback deletion")
                path.unlink()
            except OSError as rollback_error:
                rollback_errors.append(f"{path}: {rollback_error}")
        if rollback_errors:
            print(f"HTTP_API_CONTRACT_CREATED: no\nERROR: {error}; rollback incomplete: {rollback_errors}")
        else:
            print(f"HTTP_API_CONTRACT_CREATED: no\nERROR: {error}")
        return 1
    print("HTTP_API_CONTRACT_CREATED: yes")
    print(f"HTTP_API_DRAFT_READY: {'yes' if not blockers else 'no'}")
    for blocker in blockers:
        print(f"BLOCKER: {blocker}")
    print("APPROVAL_REQUIRED: yes")
    print("TARGET_SOURCE_CHANGED: no")
    return 0


if __name__ == "__main__":
    sys.exit(main())
