#!/usr/bin/env python3
"""Append one immutable, natural-language-backed design-route revision."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from continuation_route import sanitize
from record_spec_approval import atomic_write_bytes
from render_design_route import render
from spring_milestone_completion import sha, target_path
from validate_design_route import assess
from validate_feature_specs import load_object


def encoded(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def atomic_create_bytes(content: bytes, destination: Path) -> None:
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content); stream.flush(); os.fsync(stream.fileno())
        os.link(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def ref(path: Path, root: Path, digest: str | None = None) -> dict:
    return {"path": path.relative_to(root).as_posix(), "sha256": digest or sha(path)}


def argument_path(root: Path, value: Path, label: str) -> Path:
    try:
        relative = value.absolute().relative_to(root).as_posix()
    except ValueError as error:
        raise ValueError(f"{label} must be inside the target") from error
    return target_path(root, relative, label)


def route_changes(old: dict, new: dict) -> list[dict]:
    old_routes = {item["contractId"]: item for item in old["routes"]}
    new_routes = {item["contractId"]: item for item in new["routes"]}
    if set(old_routes) != set(new_routes):
        raise ValueError("proposal cannot add, remove, or rename contract identities in this revision")
    changes = []
    for contract_id in old_routes:
        before, after = old_routes[contract_id], new_routes[contract_id]
        if before != after:
            changes.append({"contractId": contract_id, "beforeSha256": hashlib.sha256(encoded(before)).hexdigest(), "afterSha256": hashlib.sha256(encoded(after)).hexdigest()})
    return changes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", required=True, type=Path)
    parser.add_argument("--proposal", required=True, type=Path)
    parser.add_argument("--answer", required=True)
    parser.add_argument("--feature", required=True, type=Path)
    parser.add_argument("--project-brief", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--view", required=True, type=Path)
    args = parser.parse_args()
    written: list[tuple[Path, bytes]] = []
    try:
        root = args.target.resolve(strict=True)
        if args.target.is_symlink():
            raise ValueError("target is a symbolic link")
        current_path = argument_path(root, args.current, "current route")
        proposal_path = argument_path(root, args.proposal, "route proposal")
        feature_path = argument_path(root, args.feature, "feature")
        project_path = argument_path(root, args.project_brief, "project brief")
        profile_path = argument_path(root, args.profile, "technology profile")
        output = argument_path(root, args.output, "route revision")
        view = argument_path(root, args.view, "route revision view")
        if view != output.with_suffix(".md") or len({current_path, proposal_path, feature_path, project_path, profile_path, output, view}) != 7:
            raise ValueError("route revision paths are duplicated or the view is not sibling Markdown")
        if any(not path.is_file() for path in (current_path, proposal_path, feature_path, project_path, profile_path)) or output.exists() or view.exists():
            raise ValueError("route revision inputs are missing or outputs already exist")
        answer = sanitize(args.answer)
        if answer != args.answer.strip():
            raise ValueError("answer must already be PII-minimized")
        old = load_object(current_path)
        new = load_object(proposal_path)
        if old.get("approval", {}).get("status") == "APPROVED" or new.get("approval") != {"status": "DRAFT", "approvedBy": None, "approvedAt": None, "approvedContentSha256": None}:
            raise ValueError("only an unapproved route may be revised and a proposal cannot approve itself")
        if old.get("featureId") != new.get("featureId") or old.get("preparation") != new.get("preparation"):
            raise ValueError("proposal must preserve feature and completion identity")
        for name in ("feature", "projectBrief"):
            if old["inputs"][name] != new["inputs"][name]:
                raise ValueError(f"proposal cannot change {name} identity")
        if old["inputs"]["technologyProfile"]["path"] != new["inputs"]["technologyProfile"]["path"] or new["inputs"]["technologyProfile"]["sha256"] != sha(profile_path):
            raise ValueError("proposal must bind the current technology profile")
        changes = route_changes(old, new)
        if not changes:
            raise ValueError("proposal has no routing change")
        previous = ref(current_path, root)
        new["revision"] = {"previous": previous, "answerSummary": answer, "changedContractIds": [item["contractId"] for item in changes]}
        feature = load_object(feature_path); project = load_object(project_path); profile = load_object(profile_path)
        _, _, blockers = assess(new, feature, project, profile, feature_path, project_path, profile_path, root)
        output_bytes = encoded(new)
        view_bytes = render(new, feature, project, profile, runtime_blockers=blockers).encode()
        next_ref = ref(output, root, hashlib.sha256(output_bytes).hexdigest()); view_ref = ref(view, root, hashlib.sha256(view_bytes).hexdigest())
        edge = {"designRouteDraftUpdateVersion": 1, "previous": previous, "next": next_ref, "view": view_ref, "answerSummary": answer, "changes": changes, "state": "COMMITTED"}
        edge_path = target_path(root, f".starter-harness/design-route-draft-updates/{previous['sha256']}.json", "route update journal")
        if edge_path.exists():
            raise ValueError("current route already has a newer immutable revision")
        edge_path.parent.mkdir(parents=True, exist_ok=True)
        prepared = encoded({**edge, "state": "PREPARED"})
        fd = os.open(edge_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(prepared); stream.flush(); os.fsync(stream.fileno())
        written.append((edge_path, prepared))
        if sha(current_path) != previous["sha256"] or output.exists() or view.exists():
            raise ValueError("route inputs changed immediately before revision write")
        output.parent.mkdir(parents=True, exist_ok=True)
        atomic_create_bytes(output_bytes, output); written.append((output, output_bytes))
        if view.exists():
            raise ValueError("route view appeared immediately before revision write")
        atomic_create_bytes(view_bytes, view); written.append((view, view_bytes))
        atomic_write_bytes(encoded(edge), edge_path); written[0] = (edge_path, encoded(edge))
    except (OSError, ValueError, KeyError, TypeError) as error:
        rollback_errors = []
        for path, payload in reversed(written):
            try:
                if path.exists() and path.read_bytes() == payload:
                    path.unlink()
                elif path.exists():
                    rollback_errors.append(f"{path}: changed externally")
            except OSError as rollback_error:
                rollback_errors.append(f"{path}: {rollback_error}")
        suffix = f"; rollback incomplete: {rollback_errors}" if rollback_errors else ""
        print(f"DESIGN_ROUTE_DRAFT_UPDATE_VALID: no\nERROR: {error}{suffix}")
        return 1
    print("DESIGN_ROUTE_DRAFT_UPDATE_VALID: yes")
    print("OFFICIAL_ROUTE_CHANGED: no")
    return 0


if __name__ == "__main__":
    sys.exit(main())
