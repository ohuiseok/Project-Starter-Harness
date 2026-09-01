#!/usr/bin/env python3
"""Create REUSE/EXTEND metadata and a deterministic compatibility report."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from existing_http_api_contract import compare_openapi, digest, validate_existing_contract
from http_api_contract import derived_traceability, encoded
from record_spec_approval import atomic_write_bytes
from validate_design_contract import sha256
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
    parser.add_argument("--baseline-openapi", required=True, type=Path)
    parser.add_argument("--proposed-openapi", type=Path)
    parser.add_argument("--traceability-source", type=Path)
    parser.add_argument("--contract-output", required=True, type=Path)
    parser.add_argument("--proposed-output", type=Path)
    parser.add_argument("--comparison-output", required=True, type=Path)
    args = parser.parse_args()
    created: list[tuple[Path, bytes]] = []
    try:
        root = args.target.resolve(strict=True)
        contract_output = args.contract_output.resolve()
        comparison_output = args.comparison_output.resolve()
        for path, label in ((contract_output, "contract output"), (comparison_output, "comparison output")):
            if root not in (path, *path.parents):
                raise ValueError(f"{label} escapes target")
            if path.exists():
                raise ValueError(f"{label} already exists; implicit overwrite is not allowed")
        route, feature, project, profile = (
            load_object(args.route), load_object(args.feature), load_object(args.project_brief), load_object(args.profile)
        )
        approved, profile_ready, route_blockers = assess(
            route, feature, project, profile, args.feature, args.project_brief, args.profile, root,
        )
        if not approved or not profile_ready or route_blockers:
            raise ValueError("design route is not ready: " + "; ".join(route_blockers))
        matches = [item for item in route["routes"] if item.get("contractId") == args.contract_id]
        if len(matches) != 1:
            raise ValueError("contract-id must match exactly one route instance")
        selected = matches[0]
        disposition = selected["disposition"]
        if selected["kind"] != "HTTP_API" or disposition not in {"REUSE", "EXTEND"}:
            raise ValueError("selected route instance must be HTTP_API REUSE or EXTEND")
        if selected.get("artifactPath") != contract_output.relative_to(root).as_posix():
            raise ValueError("contract output does not match route artifactPath")
        baseline_path = args.baseline_openapi.resolve(strict=True)
        if root not in (baseline_path, *baseline_path.parents):
            raise ValueError("baseline OpenAPI escapes target")
        baseline_relative = baseline_path.relative_to(root).as_posix()
        if baseline_relative not in selected["evidencePaths"]:
            raise ValueError("baseline OpenAPI must be selected route evidence")
        baseline = load_object(baseline_path)
        if disposition == "REUSE":
            if args.proposed_openapi or args.proposed_output:
                raise ValueError("REUSE does not accept a proposed OpenAPI")
            proposed, artifact_path = baseline, baseline_path
        else:
            if not args.proposed_openapi or not args.proposed_output:
                raise ValueError("EXTEND requires proposed-openapi and proposed-output")
            proposed = load_object(args.proposed_openapi)
            artifact_path = args.proposed_output.resolve()
            if root not in (artifact_path, *artifact_path.parents) or artifact_path.exists():
                raise ValueError("proposed output must be a new path inside target")
        traceability = (
            load_object(args.traceability_source).get("traceability") if args.traceability_source
            else derived_traceability(proposed)
        )
        if not isinstance(traceability, list):
            raise ValueError("traceability source must contain a traceability array")
        selected_operations = [item.get("subjectRef") for item in traceability if isinstance(item, dict)]
        if not selected_operations or not all(isinstance(item, str) and item for item in selected_operations):
            raise ValueError("traceability must select at least one operation")
        report = compare_openapi(baseline, proposed, args.contract_id)
        report_content = encoded(report)
        metadata = {
            "contractVersion": 1, "contractId": args.contract_id, "kind": "HTTP_API",
            "featureId": route["featureId"],
            "route": {"path": args.route.resolve().relative_to(root).as_posix(), "sha256": sha256(args.route)},
            "disposition": disposition, "target": selected["target"],
            "artifact": {"format": "OPENAPI", "path": artifact_path.relative_to(root).as_posix()},
            "baselineArtifact": {"format": "OPENAPI", "path": baseline_relative, "sha256": digest(baseline_path)},
            "comparison": {"path": comparison_output.relative_to(root).as_posix(), "sha256": hashlib.sha256(report_content).hexdigest()},
            "selectedOperations": selected_operations,
            "compatibilityReviews": [
                {
                    "reviewId": f"{item['code']}:{item['location']}", "status": "PENDING",
                    "reason": "UNKNOWN", "source": "UNKNOWN", "confirmedByUser": False,
                }
                for item in report["changes"] if item["level"] == "REVIEW"
            ],
            "traceability": traceability, "evidencePaths": selected["evidencePaths"],
            "approval": {"status": "DRAFT", "approvedBy": None, "approvedAt": None, "approvedContentSha256": None},
        }
        writes: list[tuple[Path, bytes]] = []
        if disposition == "EXTEND":
            writes.append((artifact_path, encoded(proposed)))
        writes.extend(((comparison_output, report_content), (contract_output, encoded(metadata))))
        for path, content in writes:
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_bytes(content, path)
            created.append((path, content))
        _, blockers, _, _ = validate_existing_contract(
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
        suffix = f"; rollback incomplete: {rollback_errors}" if rollback_errors else ""
        print(f"EXISTING_HTTP_API_CONTRACT_CREATED: no\nERROR: {error}{suffix}")
        return 1
    print("EXISTING_HTTP_API_CONTRACT_CREATED: yes")
    print(f"CONTRACT_DRAFT_READY: {'yes' if not blockers else 'no'}")
    for blocker in blockers:
        print(f"BLOCKER: {blocker}")
    print("TARGET_SOURCE_CHANGED: no")
    return 0


if __name__ == "__main__":
    sys.exit(main())
