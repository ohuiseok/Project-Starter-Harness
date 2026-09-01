#!/usr/bin/env python3
"""Approve physical DB planning without generating or executing artifacts."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import sys
from pathlib import Path

from http_api_contract import encoded
from record_spec_approval import approved_copy, atomic_write_bytes, read_expected
from relational_physical_contract import validate_physical_contract
from render_relational_physical_contract import render
from validate_design_route import assess, verify_inputs
from validate_feature_specs import approval_content_hash, load_object


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, type=Path); parser.add_argument("--physical-model", required=True, type=Path)
    parser.add_argument("--logical-contract", required=True, type=Path); parser.add_argument("--route", required=True, type=Path)
    parser.add_argument("--feature", required=True, type=Path); parser.add_argument("--project-brief", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path); parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--expected-contract-hash", required=True); parser.add_argument("--expected-physical-model-hash", required=True)
    parser.add_argument("--expected-logical-contract-hash", required=True); parser.add_argument("--approved-by", required=True); parser.add_argument("--approved-at", required=True)
    args = parser.parse_args()
    try:
        root = args.target.resolve(strict=True)
        for path, label in ((args.contract, "physical contract"), (args.physical_model, "physical model"), (args.logical_contract, "logical contract")):
            resolved = path.resolve(strict=True)
            if root not in (resolved, *resolved.parents): raise ValueError(f"{label} escapes target")
        if not args.approved_by.strip() or args.approved_by == "UNKNOWN": raise ValueError("approved-by must identify the approving user")
        try: dt.datetime.fromisoformat(args.approved_at.replace("Z", "+00:00"))
        except ValueError as error: raise ValueError("approved-at must be an ISO-8601 timestamp") from error
        original = args.contract.read_bytes(); metadata = load_object(args.contract); read_expected(args.contract, original, "physical relational metadata")
        if approval_content_hash(metadata) != args.expected_contract_hash: raise ValueError("physical contract changed after it was shown to the user")
        physical_original, logical_original = args.physical_model.read_bytes(), args.logical_contract.read_bytes()
        if hashlib.sha256(physical_original).hexdigest() != args.expected_physical_model_hash: raise ValueError("physical model changed after it was shown to the user")
        if hashlib.sha256(logical_original).hexdigest() != args.expected_logical_contract_hash: raise ValueError("logical contract changed after physical review")
        route, feature, project, profile = load_object(args.route), load_object(args.feature), load_object(args.project_brief), load_object(args.profile)
        route_approved, profile_ready, route_blockers = assess(route, feature, project, profile, args.feature, args.project_brief, args.profile, root)
        if not route_approved or not profile_ready or route_blockers: raise ValueError("design route is not ready: " + "; ".join(route_blockers))
        _, blockers, physical, logical = validate_physical_contract(metadata, args.physical_model, args.logical_contract, route, args.route, root, feature, profile)
        if blockers: raise ValueError("physical relational contract is not approvable: " + "; ".join(blockers))
        markdown_path = args.contract.with_suffix(".md"); markdown_original = render(metadata, physical, logical, blockers).encode(); read_expected(markdown_path, markdown_original, "physical relational Markdown")
        approved_metadata = approved_copy(metadata, args.approved_by, args.approved_at)
        approved_state, approved_blockers, approved_physical, approved_logical = validate_physical_contract(approved_metadata, args.physical_model, args.logical_contract, route, args.route, root, feature, profile)
        if not approved_state or approved_blockers: raise ValueError("approved physical contract is invalid: " + "; ".join(approved_blockers))
        approved_markdown = render(approved_metadata, approved_physical, approved_logical, []).encode()
        written = []
        try:
            final_blockers = verify_inputs(route, args.feature, args.project_brief, args.profile, root)
            if final_blockers: raise ValueError("design inputs changed before approval: " + "; ".join(final_blockers))
            if args.physical_model.read_bytes() != physical_original or args.logical_contract.read_bytes() != logical_original: raise ValueError("data contract artifacts changed before approval")
            for path, before, after in ((args.contract, original, encoded(approved_metadata)), (markdown_path, markdown_original, approved_markdown)):
                read_expected(path, before, str(path)); atomic_write_bytes(after, path); written.append((path, before, after))
        except (OSError, ValueError) as error:
            rollback_errors = []
            for path, before, after in reversed(written):
                try:
                    if path.read_bytes() != after: raise OSError("approved artifact changed externally; refusing rollback overwrite")
                    atomic_write_bytes(before, path)
                except OSError as rollback_error: rollback_errors.append(f"{path}: {rollback_error}")
            if rollback_errors: raise RuntimeError(f"approval failed and rollback was incomplete: {rollback_errors}") from error
            raise ValueError(f"approval failed and was rolled back: {error}") from error
    except (OSError, ValueError, RuntimeError) as error: print(f"RELATIONAL_PHYSICAL_APPROVAL_VALID: no\nERROR: {error}"); return 1
    print("RELATIONAL_PHYSICAL_APPROVAL_VALID: yes"); print("APPROVED_ARTIFACTS: 2")
    print("PHYSICAL_MODEL_CHANGED: no"); print("MIGRATION_RENDERED_OR_APPLIED: no"); print("DATABASE_OR_CONTAINER_CHANGED: no")
    return 0


if __name__ == "__main__": sys.exit(main())
