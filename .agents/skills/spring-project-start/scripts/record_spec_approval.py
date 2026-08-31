#!/usr/bin/env python3
"""Record user approval without exposing content hashes to the user."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any

from validate_feature_specs import (
    approval_content_hash,
    load_object,
    validate_feature,
    validate_project,
)
from render_spec_markdown import render_feature, render_project


def approved_copy(document: dict[str, Any], approved_by: str, approved_at: str) -> dict[str, Any]:
    clone = json.loads(json.dumps(document))
    if "feature" in clone:
        clone["feature"]["status"] = "APPROVED"
    clone["approval"] = {
        "status": "APPROVED",
        "approvedBy": approved_by,
        "approvedAt": approved_at,
        "approvedContentSha256": None,
    }
    clone["approval"]["approvedContentSha256"] = approval_content_hash(clone)
    return clone


def atomic_write(document: dict[str, Any], destination: Path) -> None:
    atomic_write_bytes((json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode(), destination)


def atomic_write_bytes(content: bytes, destination: Path) -> None:
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def encoded_json(document: dict[str, Any]) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode()


def read_expected(path: Path, expected: bytes, description: str) -> None:
    try:
        current = path.read_bytes()
    except OSError as error:
        raise ValueError(f"cannot read {description}: {error}") from error
    if current != expected:
        raise ValueError(f"{description} changed during approval")


def synchronize_candidate(project: dict[str, Any], feature: dict[str, Any]) -> None:
    feature_id = feature["feature"]["id"]
    matches = [item for item in project["featureCandidates"] if item["id"] == feature_id]
    if len(matches) != 1:
        raise ValueError(f"feature candidate must exist exactly once: {feature_id}")
    matches[0]["status"] = "APPROVED"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-brief", required=True, type=Path)
    parser.add_argument("--feature", type=Path)
    parser.add_argument("--expected-project-hash", required=True)
    parser.add_argument("--expected-feature-hash")
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
        project_original = args.project_brief.read_bytes()
        project_source = load_object(args.project_brief)
        read_expected(args.project_brief, project_original, "project brief")
        if approval_content_hash(project_source) != args.expected_project_hash:
            raise ValueError("project brief changed after it was shown to the user")
        project_markdown_path = args.project_brief.with_suffix(".md")
        project_markdown_source = render_project(project_source).encode()
        read_expected(project_markdown_path, project_markdown_source, "project Markdown view")
        project = approved_copy(project_source, args.approved_by, args.approved_at)
        artifacts: list[tuple[Path, bytes, bytes]] = []
        if args.feature:
            if not args.expected_feature_hash:
                raise ValueError("expected-feature-hash is required with --feature")
            feature_original = args.feature.read_bytes()
            feature_source = load_object(args.feature)
            read_expected(args.feature, feature_original, "feature spec")
            if approval_content_hash(feature_source) != args.expected_feature_hash:
                raise ValueError("feature spec changed after it was shown to the user")
            feature_markdown_path = args.feature.with_suffix(".md")
            feature_markdown_source = render_feature(feature_source, project_source).encode()
            read_expected(feature_markdown_path, feature_markdown_source, "feature Markdown view")
            feature = approved_copy(feature_source, args.approved_by, args.approved_at)
            synchronize_candidate(project, feature)
            project = approved_copy(project, args.approved_by, args.approved_at)
            feature_approved, feature_blockers = validate_feature(feature, project)
            if not feature_approved or feature_blockers:
                raise ValueError("feature spec is not approvable: " + "; ".join(feature_blockers))
            artifacts.extend([
                (args.feature, feature_original, encoded_json(feature)),
                (feature_markdown_path, feature_markdown_source, render_feature(feature, project).encode()),
            ])
        elif args.expected_feature_hash:
            raise ValueError("expected-feature-hash requires --feature")
        project_approved, project_blockers = validate_project(project)
        if not project_approved or project_blockers:
            raise ValueError("project brief is not approvable: " + "; ".join(project_blockers))
        artifacts[0:0] = [
            (args.project_brief, project_original, encoded_json(project)),
            (project_markdown_path, project_markdown_source, render_project(project).encode()),
        ]
        written: list[tuple[Path, bytes, bytes]] = []
        try:
            for path, original, approved_content in artifacts:
                read_expected(path, original, str(path))
                atomic_write_bytes(approved_content, path)
                written.append((path, original, approved_content))
        except (OSError, ValueError) as error:
            rollback_errors: list[str] = []
            for path, original, approved_content in reversed(written):
                try:
                    if path.read_bytes() != approved_content:
                        raise OSError("approved artifact changed externally; refusing to overwrite during rollback")
                    atomic_write_bytes(original, path)
                except OSError as rollback_error:
                    rollback_errors.append(f"{path}: {rollback_error}")
            if rollback_errors:
                raise RuntimeError(f"approval write failed and rollback was incomplete: {rollback_errors}") from error
            raise ValueError(f"approval write failed and was rolled back: {error}") from error
    except (OSError, ValueError, RuntimeError) as error:
        print(f"SPEC_APPROVAL_VALID: no\nERROR: {error}")
        return 1
    print("SPEC_APPROVAL_VALID: yes")
    print(f"APPROVED_ARTIFACTS: {len(artifacts)}")
    print("CONTENT_HASH_VISIBLE_TO_USER: no")
    return 0


if __name__ == "__main__":
    sys.exit(main())
