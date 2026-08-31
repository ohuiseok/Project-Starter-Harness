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
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


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
        project_source = load_object(args.project_brief)
        if approval_content_hash(project_source) != args.expected_project_hash:
            raise ValueError("project brief changed after it was shown to the user")
        project = approved_copy(project_source, args.approved_by, args.approved_at)
        project_approved, project_blockers = validate_project(project)
        if not project_approved or project_blockers:
            raise ValueError("project brief is not approvable: " + "; ".join(project_blockers))
        documents: list[tuple[Path, dict[str, Any]]] = [(args.project_brief, project)]
        if args.feature:
            if not args.expected_feature_hash:
                raise ValueError("expected-feature-hash is required with --feature")
            feature_source = load_object(args.feature)
            if approval_content_hash(feature_source) != args.expected_feature_hash:
                raise ValueError("feature spec changed after it was shown to the user")
            feature = approved_copy(feature_source, args.approved_by, args.approved_at)
            feature_approved, feature_blockers = validate_feature(feature, project)
            if not feature_approved or feature_blockers:
                raise ValueError("feature spec is not approvable: " + "; ".join(feature_blockers))
            documents.append((args.feature, feature))
        elif args.expected_feature_hash:
            raise ValueError("expected-feature-hash requires --feature")
        originals = {path: path.read_bytes() for path, _ in documents}
        written: list[Path] = []
        try:
            for path, document in documents:
                atomic_write(document, path)
                written.append(path)
        except OSError as error:
            rollback_errors: list[str] = []
            for path in reversed(written):
                try:
                    temporary = path.with_name(f".{path.name}.{os.getpid()}.rollback")
                    temporary.write_bytes(originals[path])
                    os.replace(temporary, path)
                except OSError as rollback_error:
                    rollback_errors.append(f"{path}: {rollback_error}")
            if rollback_errors:
                raise RuntimeError(f"approval write failed and rollback was incomplete: {rollback_errors}") from error
            raise ValueError(f"approval write failed and was rolled back: {error}") from error
    except (OSError, ValueError, RuntimeError) as error:
        print(f"SPEC_APPROVAL_VALID: no\nERROR: {error}")
        return 1
    print("SPEC_APPROVAL_VALID: yes")
    print(f"APPROVED_ARTIFACTS: {len(documents)}")
    print("CONTENT_HASH_VISIBLE_TO_USER: no")
    return 0


if __name__ == "__main__":
    sys.exit(main())
