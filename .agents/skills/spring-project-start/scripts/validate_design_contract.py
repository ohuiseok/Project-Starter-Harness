#!/usr/bin/env python3
"""Validate minimal design-contract metadata against an approved route instance."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

from validate_design_route import ACTIVE, ROUTE_REQUIREMENTS
from validate_feature_specs import load_object, text, validate_approval


CONTRACT_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FORMATS = {"OPENAPI", "JSON_SCHEMA", "ASYNCAPI", "MARKDOWN", "MERMAID", "OTHER", "UNKNOWN"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inside(root: Path, value: str, location: str) -> Path:
    resolved = (root / value).resolve()
    if root not in (resolved, *resolved.parents):
        raise ValueError(f"{location} escapes target")
    return resolved


def validate(
    contract: dict, route: dict, route_path: Path, target: Path, contract_path: Path | None = None,
) -> tuple[bool, list[str]]:
    if contract.get("contractVersion") != 1:
        raise ValueError("contractVersion must be 1")
    if route.get("routeVersion") != 2:
        raise ValueError("design contracts require routeVersion 2")
    contract_id = text(contract.get("contractId"), "contractId", False)
    if not CONTRACT_ID.fullmatch(contract_id):
        raise ValueError("contractId must be lowercase kebab-case")
    kind = text(contract.get("kind"), "kind", False)
    if kind not in ROUTE_REQUIREMENTS:
        raise ValueError(f"kind is invalid: {kind}")
    matches = [item for item in route["routes"] if item.get("contractId") == contract_id]
    if len(matches) != 1:
        raise ValueError("contractId must match exactly one route instance")
    selected = matches[0]
    blockers: list[str] = []
    route_approved = validate_approval(route.get("approval"), "route.approval", route)
    if selected["kind"] != kind:
        blockers.append("contract kind does not match its route instance")
    if selected["disposition"] not in ACTIVE:
        blockers.append("contract route instance is not active")
    if contract.get("featureId") != route.get("featureId"):
        blockers.append("featureId does not match the design route")
    route_ref = contract.get("route")
    if not isinstance(route_ref, dict) or set(route_ref) != {"path", "sha256"}:
        raise ValueError("route must contain path and sha256")
    root = target.resolve()
    declared_route = inside(root, text(route_ref["path"], "route.path", False), "route.path")
    if declared_route != route_path.resolve():
        blockers.append("route path does not match the validated route")
    digest = text(route_ref["sha256"], "route.sha256")
    if digest == "UNKNOWN":
        blockers.append("route hash is UNKNOWN")
    elif len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("route.sha256 must be lowercase SHA-256")
    elif digest != sha256(route_path):
        blockers.append("design route changed after contract drafting")
    target_value = contract.get("target")
    if not isinstance(target_value, dict) or set(target_value) != {"projectId", "modulePath", "dataStoreIds"}:
        raise ValueError("target must contain projectId, modulePath, and dataStoreIds")
    if not isinstance(contract.get("evidencePaths"), list) or not all(
        isinstance(item, str) and item for item in contract["evidencePaths"]
    ):
        raise ValueError("evidencePaths must be a string array")
    for field in ("disposition", "target", "evidencePaths"):
        if contract.get(field) != selected.get(field):
            blockers.append(f"{field} does not match the route instance")
    if contract_path is not None:
        resolved_contract = contract_path.resolve()
        if root not in (resolved_contract, *resolved_contract.parents):
            raise ValueError("contract path escapes target")
        relative_contract = resolved_contract.relative_to(root).as_posix()
        if selected.get("artifactPath") != relative_contract:
            blockers.append("contract file path does not match route artifactPath")
    artifact = contract.get("artifact")
    if not isinstance(artifact, dict) or set(artifact) != {"format", "path"}:
        raise ValueError("artifact must contain format and path")
    artifact_format = text(artifact["format"], "artifact.format")
    if artifact_format not in FORMATS:
        raise ValueError(f"artifact.format is invalid: {artifact_format}")
    artifact_path = text(artifact["path"], "artifact.path")
    if artifact_format == "UNKNOWN" or artifact_path == "UNKNOWN":
        blockers.append("contract artifact is not selected")
    else:
        inside(root, artifact_path, "artifact.path")
    traceability = contract.get("traceability")
    if not isinstance(traceability, list):
        raise ValueError("traceability must be an array")
    for index, item in enumerate(traceability):
        if not isinstance(item, dict) or set(item) != {"subjectRef", "requirementRefs"}:
            raise ValueError(f"traceability[{index}] must contain subjectRef and requirementRefs")
        text(item["subjectRef"], f"traceability[{index}].subjectRef", False)
        refs = item["requirementRefs"]
        if not isinstance(refs, list) or not refs or not all(isinstance(ref, str) and ref for ref in refs):
            raise ValueError(f"traceability[{index}].requirementRefs must be a non-empty string array")
    if not traceability:
        blockers.append("contract has no feature traceability")
    approved = validate_approval(contract.get("approval"), "approval", contract)
    if not route_approved:
        blockers.append("design route is not approved")
    return approved, blockers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--route", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    try:
        approved, blockers = validate(
            load_object(args.contract), load_object(args.route), args.route, args.target, args.contract
        )
        ready = approved and not blockers
    except (OSError, ValueError) as error:
        print(f"DESIGN_CONTRACT_VALID: no\nERROR: {error}")
        return 1
    print("DESIGN_CONTRACT_VALID: yes")
    print(f"APPROVED: {'yes' if approved else 'no'}")
    print(f"CONTRACT_READY: {'yes' if ready else 'no'}")
    for blocker in blockers:
        print(f"BLOCKER: {blocker}")
    return 1 if args.require_ready and not ready else 0


if __name__ == "__main__":
    sys.exit(main())
