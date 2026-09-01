#!/usr/bin/env python3
"""Safely approve a displayed design route and its Markdown view."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from record_spec_approval import approved_copy, atomic_write_bytes, encoded_json, read_expected
from render_design_route import render
from validate_design_route import assess, load_object, validate, verify_inputs
from validate_feature_specs import approval_content_hash


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--route", required=True, type=Path)
    parser.add_argument("--feature", required=True, type=Path)
    parser.add_argument("--project-brief", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--expected-route-hash", required=True)
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
        route_original = args.route.read_bytes()
        route_source = load_object(args.route)
        read_expected(args.route, route_original, "design route")
        if approval_content_hash(route_source) != args.expected_route_hash:
            raise ValueError("design route changed after it was shown to the user")
        feature = load_object(args.feature)
        project = load_object(args.project_brief)
        profile = load_object(args.profile)
        _, profile_ready, route_blockers = assess(
            route_source, feature, project, profile,
            args.feature, args.project_brief, args.profile, args.target,
        )
        if not profile_ready:
            raise ValueError("technology profile is not ready")
        if route_blockers:
            raise ValueError("design route is not approvable: " + "; ".join(route_blockers))
        markdown_path = args.route.with_suffix(".md")
        markdown_original = render(route_source, feature, project, profile).encode()
        read_expected(markdown_path, markdown_original, "design route Markdown")
        approved = approved_copy(route_source, args.approved_by, args.approved_at)
        approved_state, approved_blockers = validate(approved, feature, project, profile)
        if not approved_state or approved_blockers:
            raise ValueError("approved design route is invalid: " + "; ".join(approved_blockers))
        artifacts = [
            (args.route, route_original, encoded_json(approved)),
            (markdown_path, markdown_original, render(approved, feature, project, profile).encode()),
        ]
        written: list[tuple[Path, bytes, bytes]] = []
        try:
            final_input_blockers = verify_inputs(
                route_source, args.feature, args.project_brief, args.profile, args.target
            )
            if final_input_blockers:
                raise ValueError("design route inputs changed before approval: " + "; ".join(final_input_blockers))
            for path, original, content in artifacts:
                read_expected(path, original, str(path))
                atomic_write_bytes(content, path)
                written.append((path, original, content))
        except (OSError, ValueError) as error:
            rollback_errors: list[str] = []
            for path, original, content in reversed(written):
                try:
                    if path.read_bytes() != content:
                        raise OSError("approved artifact changed externally; refusing rollback overwrite")
                    atomic_write_bytes(original, path)
                except OSError as rollback_error:
                    rollback_errors.append(f"{path}: {rollback_error}")
            if rollback_errors:
                raise RuntimeError(f"approval failed and rollback was incomplete: {rollback_errors}") from error
            raise ValueError(f"approval failed and was rolled back: {error}") from error
    except (OSError, ValueError, RuntimeError) as error:
        print(f"DESIGN_ROUTE_APPROVAL_VALID: no\nERROR: {error}")
        return 1
    print("DESIGN_ROUTE_APPROVAL_VALID: yes")
    print("APPROVED_ARTIFACTS: 2")
    print("CONTENT_HASH_VISIBLE_TO_USER: no")
    return 0


if __name__ == "__main__":
    sys.exit(main())
