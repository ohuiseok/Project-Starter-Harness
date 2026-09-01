#!/usr/bin/env python3
"""Atomically approve a logical relational data contract."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import sys
from pathlib import Path

from http_api_contract import encoded
from record_spec_approval import approved_copy, atomic_write_bytes, read_expected
from relational_data_contract import validate_relational_contract
from render_relational_data_contract import render
from validate_design_route import assess, verify_inputs
from validate_feature_specs import approval_content_hash, load_object


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, type=Path); parser.add_argument("--route", required=True, type=Path)
    parser.add_argument("--feature", required=True, type=Path); parser.add_argument("--project-brief", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path); parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--expected-contract-hash", required=True); parser.add_argument("--expected-model-hash", required=True)
    parser.add_argument("--approved-by", required=True); parser.add_argument("--approved-at", required=True)
    args = parser.parse_args()
    try:
        if not args.approved_by.strip() or args.approved_by == "UNKNOWN": raise ValueError("approved-by must identify the approving user")
        try: dt.datetime.fromisoformat(args.approved_at.replace("Z", "+00:00"))
        except ValueError as error: raise ValueError("approved-at must be an ISO-8601 timestamp") from error
        original = args.contract.read_bytes(); metadata = load_object(args.contract)
        read_expected(args.contract, original, "relational data contract metadata")
        if approval_content_hash(metadata) != args.expected_contract_hash: raise ValueError("relational data contract changed after it was shown to the user")
        route, feature, project, profile = load_object(args.route), load_object(args.feature), load_object(args.project_brief), load_object(args.profile)
        route_approved, profile_ready, route_blockers = assess(route, feature, project, profile, args.feature, args.project_brief, args.profile, args.target)
        if not route_approved or not profile_ready or route_blockers: raise ValueError("design route is not ready: " + "; ".join(route_blockers))
        _, blockers, model = validate_relational_contract(metadata, route, args.route, args.target, args.contract, feature, profile)
        if blockers: raise ValueError("relational data contract is not approvable: " + "; ".join(blockers))
        model_path = args.target.resolve() / metadata["artifact"]["path"]
        model_original = model_path.read_bytes()
        if hashlib.sha256(model_original).hexdigest() != args.expected_model_hash: raise ValueError("relational data model changed after it was shown to the user")
        markdown_path = args.contract.with_suffix(".md"); markdown_original = render(metadata, model, blockers, feature).encode()
        read_expected(markdown_path, markdown_original, "relational data Markdown")
        approved_metadata = approved_copy(metadata, args.approved_by, args.approved_at)
        approved_state, approved_blockers, approved_model = validate_relational_contract(approved_metadata, route, args.route, args.target, args.contract, feature, profile)
        if not approved_state or approved_blockers: raise ValueError("approved relational data contract is invalid: " + "; ".join(approved_blockers))
        approved_markdown = render(approved_metadata, approved_model, [], feature).encode()
        artifacts = [(args.contract, original, encoded(approved_metadata)), (markdown_path, markdown_original, approved_markdown)]
        written: list[tuple[Path, bytes, bytes]] = []
        try:
            final_blockers = verify_inputs(route, args.feature, args.project_brief, args.profile, args.target)
            if final_blockers: raise ValueError("design inputs changed before approval: " + "; ".join(final_blockers))
            if model_path.read_bytes() != model_original: raise ValueError("relational data model changed before approval")
            for path, before, after in artifacts:
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
    except (OSError, ValueError, RuntimeError) as error:
        print(f"RELATIONAL_DATA_APPROVAL_VALID: no\nERROR: {error}"); return 1
    print("RELATIONAL_DATA_APPROVAL_VALID: yes")
    print("APPROVED_ARTIFACTS: 2")
    print("DATA_MODEL_CHANGED: no")
    print("DATABASE_OR_CONTAINER_CHANGED: no")
    return 0


if __name__ == "__main__":
    sys.exit(main())
