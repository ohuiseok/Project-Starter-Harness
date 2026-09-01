#!/usr/bin/env python3
"""Approve current REUSE/EXTEND assessment without applying interface changes."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import sys
from pathlib import Path

from existing_http_api_contract import validate_existing_contract
from http_api_contract import encoded
from record_spec_approval import approved_copy, atomic_write_bytes, read_expected
from render_existing_http_api_contract import render
from validate_design_route import assess, verify_inputs
from validate_feature_specs import approval_content_hash, load_object


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--route", required=True, type=Path)
    parser.add_argument("--feature", required=True, type=Path)
    parser.add_argument("--project-brief", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--expected-contract-hash", required=True)
    parser.add_argument("--expected-artifact-hash", required=True)
    parser.add_argument("--expected-comparison-hash", required=True)
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--approved-at", required=True)
    args = parser.parse_args()
    try:
        if not args.approved_by.strip() or args.approved_by == "UNKNOWN":
            raise ValueError("approved-by must identify the approving user")
        dt.datetime.fromisoformat(args.approved_at.replace("Z", "+00:00"))
        root = args.target.resolve()
        original = args.contract.read_bytes()
        metadata = load_object(args.contract)
        if approval_content_hash(metadata) != args.expected_contract_hash:
            raise ValueError("contract changed after it was shown")
        route, feature, project, profile = (
            load_object(args.route), load_object(args.feature), load_object(args.project_brief), load_object(args.profile)
        )
        route_approved, profile_ready, route_blockers = assess(
            route, feature, project, profile, args.feature, args.project_brief, args.profile, root,
        )
        if not route_approved or not profile_ready or route_blockers:
            raise ValueError("design route is not ready: " + "; ".join(route_blockers))
        _, blockers, openapi, report = validate_existing_contract(
            metadata, route, args.route, root, args.contract, feature, profile,
        )
        if blockers:
            raise ValueError("existing HTTP API contract is not approvable: " + "; ".join(blockers))
        artifact_path = root / metadata["artifact"]["path"]
        comparison_path = root / metadata["comparison"]["path"]
        artifact_original, comparison_original = artifact_path.read_bytes(), comparison_path.read_bytes()
        if hashlib.sha256(artifact_original).hexdigest() != args.expected_artifact_hash:
            raise ValueError("API artifact changed after it was shown")
        if hashlib.sha256(comparison_original).hexdigest() != args.expected_comparison_hash:
            raise ValueError("compatibility report changed after it was shown")
        markdown_path = args.contract.with_suffix(".md")
        markdown_original = render(metadata, openapi, report, []).encode()
        read_expected(markdown_path, markdown_original, "existing HTTP API Markdown")
        approved = approved_copy(metadata, args.approved_by, args.approved_at)
        approved_state, approved_blockers, approved_api, approved_report = validate_existing_contract(
            approved, route, args.route, root, args.contract, feature, profile,
        )
        if not approved_state or approved_blockers:
            raise ValueError("approved contract is invalid: " + "; ".join(approved_blockers))
        writes = [
            (args.contract, original, encoded(approved)),
            (markdown_path, markdown_original, render(approved, approved_api, approved_report, []).encode()),
        ]
        written: list[tuple[Path, bytes, bytes]] = []
        try:
            final_blockers = verify_inputs(route, args.feature, args.project_brief, args.profile, root)
            if final_blockers:
                raise ValueError("design inputs changed before approval: " + "; ".join(final_blockers))
            if artifact_path.read_bytes() != artifact_original or comparison_path.read_bytes() != comparison_original:
                raise ValueError("API evidence changed before approval")
            for path, before, after in writes:
                read_expected(path, before, str(path))
                atomic_write_bytes(after, path)
                written.append((path, before, after))
        except (OSError, ValueError) as error:
            rollback_errors = []
            for path, before, after in reversed(written):
                try:
                    if path.read_bytes() != after:
                        raise OSError("artifact changed externally; refusing rollback overwrite")
                    atomic_write_bytes(before, path)
                except OSError as rollback_error:
                    rollback_errors.append(f"{path}: {rollback_error}")
            if rollback_errors:
                raise RuntimeError(f"approval rollback incomplete: {rollback_errors}") from error
            raise ValueError(f"approval failed and was rolled back: {error}") from error
    except (OSError, ValueError, RuntimeError) as error:
        print(f"EXISTING_HTTP_API_APPROVAL_VALID: no\nERROR: {error}")
        return 1
    print("EXISTING_HTTP_API_APPROVAL_VALID: yes")
    print("INTERFACE_APPLIED: no")
    return 0


if __name__ == "__main__":
    sys.exit(main())
