#!/usr/bin/env python3
"""Prepare a safe design-route draft from a committed feature promotion."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from evaluate_profile import evaluate
from render_design_route import render
from spring_milestone_completion import sha, target_path
from validate_design_route import ROUTE_REQUIREMENTS, assess, technology_mismatch
from validate_feature_specs import load_object, validate_feature, validate_project


def ref(path: Path, root: Path) -> dict:
    return {"path": path.relative_to(root).as_posix(), "sha256": sha(path)}


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


def argument_path(root: Path, value: Path, label: str) -> Path:
    try:
        relative = value.absolute().relative_to(root).as_posix()
    except ValueError as error:
        raise ValueError(f"{label} must be inside the target") from error
    return target_path(root, relative, label)


def git_overlap(root: Path, paths: list[Path]) -> list[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root, capture_output=True, text=True, check=False,
    )
    if result.returncode:
        raise ValueError("target Git state cannot be verified")
    dirty = {line[3:].split(" -> ")[-1].strip('"') for line in result.stdout.splitlines() if len(line) > 3}
    wanted = {path.relative_to(root).as_posix() for path in paths}
    return sorted(dirty & wanted)


def exact_single_target(profile: dict) -> tuple[str, str] | None:
    projects = profile.get("projects", [])
    if projects:
        if len(projects) != 1 or not isinstance(projects[0], dict):
            return None
        project_id = projects[0].get("id")
        # A child profile identifies a project, but does not prove a module path.
        return (project_id, "UNKNOWN") if isinstance(project_id, str) and project_id else None
    project_id = profile.get("project", {}).get("artifactId")
    return (project_id, ".") if isinstance(project_id, str) and project_id not in {"", "UNKNOWN"} else None


def load_inputs(root: Path, completion_path: Path, project_path: Path, profile_path: Path) -> tuple[dict, dict, dict, dict, Path]:
    completion = load_object(completion_path)
    required = {"continuationCompletionVersion", "intake", "promotionPlan", "reservation", "featureId", "approvedBy", "approvedAt", "state"}
    if set(completion) != required or completion["continuationCompletionVersion"] != 1 or completion["state"] != "CONSUMED":
        raise ValueError("a committed continuation completion receipt is required")
    plan_ref = completion["promotionPlan"]
    if not isinstance(plan_ref, dict) or set(plan_ref) != {"path", "sha256"}:
        raise ValueError("completion promotion-plan reference is invalid")
    plan_path = target_path(root, plan_ref["path"], "promotion plan")
    if not plan_path.is_file() or sha(plan_path) != plan_ref["sha256"]:
        raise ValueError("promotion plan changed after completion")
    plan = load_object(plan_path)
    feature_id = completion["featureId"]
    if plan.get("featureSpecPromotionVersion") != 2 or plan.get("proposedFeature", {}).get("feature", {}).get("id") != feature_id:
        raise ValueError("completion does not match the promotion plan")
    expected_project = target_path(root, plan["projectBrief"]["path"], "project brief")
    expected_feature = target_path(root, plan["officialFeaturePath"], "official feature")
    if project_path != expected_project:
        raise ValueError("project brief does not match the completed promotion")
    project = load_object(project_path)
    feature = load_object(expected_feature)
    profile = load_object(profile_path)
    project_ready, project_blockers = validate_project(project)
    feature_ready, feature_blockers = validate_feature(feature, project)
    if not project_ready or project_blockers or not feature_ready or feature_blockers:
        raise ValueError("official project and feature contracts are not advancement-ready")
    return completion, project, feature, profile, expected_feature


def build(root: Path, completion_path: Path, project_path: Path, profile_path: Path, output: Path, view: Path) -> tuple[dict, dict, dict, dict, list[str]]:
    completion, project, feature, profile, feature_path = load_inputs(root, completion_path, project_path, profile_path)
    _, _, _, profile_ready, _ = evaluate(profile_path)
    target = exact_single_target(profile) if profile_ready else None
    stores = profile.get("dataStores", []) if isinstance(profile.get("dataStores", []), list) else []
    routes = []
    for kind, requirement_ref in ROUTE_REQUIREMENTS.items():
        requirement = feature["designRequirements"].get(requirement_ref) if kind not in {"SECURITY", "VERIFICATION"} else None
        required = kind == "VERIFICATION" or (kind == "SECURITY" and bool(feature["authorization"])) or (requirement and requirement["status"] == "REQUIRED")
        mismatch = technology_mismatch(kind, profile) if required and profile_ready else None
        if requirement and requirement["status"] == "NOT_USED":
            disposition, reason, source, confirmed = "NOT_NEEDED", requirement["reason"], "PROJECT_EVIDENCE", True
        elif requirement and requirement["status"] == "DEFERRED":
            disposition, reason, source, confirmed = "DEFERRED", requirement["reason"], "PROJECT_EVIDENCE", True
        elif not required:
            disposition, reason, source, confirmed = "NOT_NEEDED", "승인된 기능 범위에 별도 설계 요구가 없습니다.", "PROJECT_EVIDENCE", True
        elif mismatch:
            disposition, reason, source, confirmed = "UNKNOWN", mismatch, "UNKNOWN", False
        elif target is None or target[1] == "UNKNOWN" or (kind == "PERSISTENCE" and len(stores) > 1):
            disposition, reason, source, confirmed = "UNKNOWN", "대상 프로젝트·모듈 또는 데이터 저장소를 먼저 선택해야 합니다.", "UNKNOWN", False
        else:
            disposition, reason, source, confirmed = "CREATE", "승인된 기능 요구에 맞는 새 설계 계약을 준비합니다.", "RECOMMENDED", False
        active = disposition in {"CREATE", "EXTEND", "REUSE"}
        project_id, module_path = target if target else ("UNKNOWN", "UNKNOWN")
        store_ids = [stores[0]["id"]] if active and kind == "PERSISTENCE" and len(stores) == 1 and isinstance(stores[0], dict) and stores[0].get("id") else []
        contract_id = kind.lower().replace("_", "-")
        artifact = f"docs/features/{feature['feature']['id']}/contracts/{contract_id}/metadata.json" if active else None
        routes.append({"contractId": contract_id, "kind": kind, "requirementRef": requirement_ref, "disposition": disposition, "target": {"projectId": project_id, "modulePath": module_path, "dataStoreIds": store_ids}, "evidencePaths": [], "artifactPath": artifact, "reason": reason, "source": source, "confirmedByUser": confirmed})
    route = {"routeVersion": 2, "featureId": feature["feature"]["id"], "inputs": {"feature": ref(feature_path, root), "projectBrief": ref(project_path, root), "technologyProfile": ref(profile_path, root), "codeEvidence": []}, "routes": routes, "preparation": {"completion": ref(completion_path, root), "gitOverlap": git_overlap(root, [output, view])}, "approval": {"status": "DRAFT", "approvedBy": None, "approvedAt": None, "approvedContentSha256": None}}
    # Structural and runtime assessment must be possible even when choices remain unresolved.
    _, _, blockers = assess(route, feature, project, profile, target_path(root, route["inputs"]["feature"]["path"], "feature"), project_path, profile_path, root)
    return route, feature, project, profile, blockers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--completion", required=True, type=Path)
    parser.add_argument("--project-brief", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--view", required=True, type=Path)
    args = parser.parse_args()
    written = None
    try:
        root = args.target.resolve(strict=True)
        if args.target.is_symlink():
            raise ValueError("target is a symbolic link")
        completion = argument_path(root, args.completion, "completion")
        project = argument_path(root, args.project_brief, "project brief")
        profile = argument_path(root, args.profile, "technology profile")
        output = argument_path(root, args.output, "design route output")
        view = argument_path(root, args.view, "design route view")
        if view != output.with_suffix(".md"):
            raise ValueError("design route view must be the sibling Markdown path")
        if len({completion, project, profile, output, view}) != 5 or any(not path.is_file() for path in (completion, project, profile)):
            raise ValueError("design-route inputs are missing, duplicated, or unsafe")
        if output.exists() or view.exists():
            raise ValueError("design route or view already exists; refusing overwrite")
        overlap = git_overlap(root, [output, view])
        if overlap:
            raise ValueError("design route targets overlap current Git changes: " + ", ".join(overlap))
        route, feature, project_value, profile_value, blockers = build(root, completion, project, profile, output, view)
        route_bytes = (json.dumps(route, ensure_ascii=False, indent=2) + "\n").encode()
        view_bytes = render(route, feature, project_value, profile_value, runtime_blockers=blockers).encode()
        output.parent.mkdir(parents=True, exist_ok=True)
        view.parent.mkdir(parents=True, exist_ok=True)
        atomic_create_bytes(route_bytes, output)
        written = (output, route_bytes)
        atomic_create_bytes(view_bytes, view)
    except (OSError, ValueError, KeyError, TypeError) as error:
        if written and written[0].exists() and written[0].read_bytes() == written[1]:
            written[0].unlink()
        print(f"DESIGN_ROUTE_PREPARATION_VALID: no\nERROR: {error}")
        return 1
    print("DESIGN_ROUTE_PREPARATION_VALID: yes")
    print("SOURCE_OR_RUNTIME_CHANGED: no")
    print("NEXT_WORKFLOW: DESIGN_ROUTE_REVIEW")
    return 0


if __name__ == "__main__":
    sys.exit(main())
