#!/usr/bin/env python3
"""Atomically approve current HTTP API metadata after revalidating every input."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import sys
from pathlib import Path

from http_api_contract import encoded, validate_http_contract
from record_spec_approval import approved_copy, atomic_write_bytes, read_expected
from render_http_api_contract import render
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
    parser.add_argument("--expected-openapi-hash", required=True)
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--approved-at", required=True)
    args = parser.parse_args()
    try:
        if not args.approved_by.strip() or args.approved_by == "UNKNOWN":
            raise ValueError("approved-by must identify the approving user")
        try:
            dt.datetime.fromisoformat(args.approved_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("approved-at must be an ISO-8601 timestamp") from error
        original = args.contract.read_bytes()
        metadata = load_object(args.contract)
        read_expected(args.contract, original, "HTTP API contract metadata")
        if approval_content_hash(metadata) != args.expected_contract_hash:
            raise ValueError("HTTP API contract changed after it was shown to the user")
        route = load_object(args.route)
        feature = load_object(args.feature)
        project = load_object(args.project_brief)
        profile = load_object(args.profile)
        route_approved, profile_ready, route_blockers = assess(
            route, feature, project, profile,
            args.feature, args.project_brief, args.profile, args.target,
        )
        if not route_approved or not profile_ready or route_blockers:
            raise ValueError("design route is not ready: " + "; ".join(route_blockers))
        _, blockers, openapi = validate_http_contract(
            metadata, route, args.route, args.target, args.contract, feature, profile,
        )
        if blockers:
            raise ValueError("HTTP API contract is not approvable: " + "; ".join(blockers))
        openapi_path = args.target.resolve() / metadata["artifact"]["path"]
        openapi_original = openapi_path.read_bytes()
        if hashlib.sha256(openapi_original).hexdigest() != args.expected_openapi_hash:
            raise ValueError("OpenAPI changed after it was shown to the user")
        markdown_path = args.contract.with_suffix(".md")
        markdown_original = render(metadata, openapi, blockers).encode()
        read_expected(markdown_path, markdown_original, "HTTP API contract Markdown")
        approved_metadata = approved_copy(metadata, args.approved_by, args.approved_at)
        approved_state, approved_blockers, approved_openapi = validate_http_contract(
            approved_metadata, route, args.route, args.target, args.contract, feature, profile,
        )
        if not approved_state or approved_blockers:
            raise ValueError("approved HTTP API contract is invalid: " + "; ".join(approved_blockers))
        approved_markdown = render(approved_metadata, approved_openapi, []).encode()
        artifacts = [(args.contract, original, encoded(approved_metadata)), (markdown_path, markdown_original, approved_markdown)]
        written: list[tuple[Path, bytes, bytes]] = []
        try:
            final_blockers = verify_inputs(route, args.feature, args.project_brief, args.profile, args.target)
            if final_blockers:
                raise ValueError("design inputs changed before approval: " + "; ".join(final_blockers))
            if openapi_path.read_bytes() != openapi_original:
                raise ValueError("OpenAPI changed before approval")
            for path, before, after in artifacts:
                read_expected(path, before, str(path))
                atomic_write_bytes(after, path)
                written.append((path, before, after))
        except (OSError, ValueError) as error:
            rollback_errors: list[str] = []
            for path, before, after in reversed(written):
                try:
                    if path.read_bytes() != after:
                        raise OSError("approved artifact changed externally; refusing rollback overwrite")
                    atomic_write_bytes(before, path)
                except OSError as rollback_error:
                    rollback_errors.append(f"{path}: {rollback_error}")
            if rollback_errors:
                raise RuntimeError(f"approval failed and rollback was incomplete: {rollback_errors}") from error
            raise ValueError(f"approval failed and was rolled back: {error}") from error
    except (OSError, ValueError, RuntimeError) as error:
        print(f"HTTP_API_APPROVAL_VALID: no\nERROR: {error}")
        return 1
    print("HTTP_API_APPROVAL_VALID: yes")
    print("APPROVED_ARTIFACTS: 2")
    print("OPENAPI_CHANGED: no")
    return 0


if __name__ == "__main__":
    sys.exit(main())
