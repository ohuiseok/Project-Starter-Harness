#!/usr/bin/env python3
"""Validate a feature design-routing manifest and its current inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from evaluate_profile import evaluate
from validate_feature_specs import SOURCES, load_object, text, validate_approval, validate_feature, validate_project


ROUTE_REQUIREMENTS = {
    "HTTP_API": "httpApi", "PERSISTENCE": "persistentState", "MESSAGING": "messaging",
    "SCHEDULED_JOB": "scheduledJob", "SERVER_UI": "serverRenderedUi",
    "CLIENT_INTEGRATION": "separateClient", "EXTERNAL_INTEGRATION": "externalIntegration",
    "SECURITY": "authorization", "VERIFICATION": "acceptanceCriteria",
}
DISPOSITIONS = {"CREATE", "EXTEND", "REUSE", "NOT_NEEDED", "DEFERRED", "UNKNOWN"}
ACTIVE = {"CREATE", "EXTEND", "REUSE"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def string_list(value: Any, location: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{location}: string array required")
    if len(value) != len(set(value)):
        raise ValueError(f"{location}: values must be unique")
    return value


def validate(route: dict[str, Any], feature: dict[str, Any], project: dict[str, Any], profile: dict[str, Any]) -> tuple[bool, list[str]]:
    if route.get("routeVersion") != 1:
        raise ValueError("routeVersion must be 1")
    feature_approved, feature_blockers = validate_feature(feature, project)
    if not feature_approved or feature_blockers:
        raise ValueError("feature specification must be advancement-ready")
    if route.get("featureId") != feature["feature"]["id"]:
        raise ValueError("featureId does not match the feature specification")
    blockers: list[str] = []
    inputs = route.get("inputs")
    if not isinstance(inputs, dict) or set(inputs) != {"feature", "projectBrief", "technologyProfile", "codeEvidence"}:
        raise ValueError("inputs must contain feature, projectBrief, technologyProfile, and codeEvidence")
    for name in ("feature", "projectBrief", "technologyProfile"):
        ref = inputs[name]
        if not isinstance(ref, dict) or set(ref) != {"path", "sha256"}:
            raise ValueError(f"inputs.{name}: path and sha256 required")
        text(ref["path"], f"inputs.{name}.path", False)
        digest = text(ref["sha256"], f"inputs.{name}.sha256")
        if digest == "UNKNOWN":
            blockers.append(f"input hash is UNKNOWN: {name}")
        elif len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError(f"inputs.{name}.sha256: lowercase SHA-256 required")
    evidence = inputs["codeEvidence"]
    if not isinstance(evidence, list):
        raise ValueError("inputs.codeEvidence: array required")
    evidence_paths: set[str] = set()
    for index, item in enumerate(evidence):
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "kind"}:
            raise ValueError(f"inputs.codeEvidence[{index}]: path, sha256, and kind required")
        path = text(item["path"], f"inputs.codeEvidence[{index}].path", False)
        if path in evidence_paths:
            raise ValueError(f"inputs.codeEvidence: duplicate path {path}")
        evidence_paths.add(path)
        text(item["kind"], f"inputs.codeEvidence[{index}].kind", False)
        digest = text(item["sha256"], f"inputs.codeEvidence[{index}].sha256", False)
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError(f"inputs.codeEvidence[{index}].sha256: lowercase SHA-256 required")
    routes = route.get("routes")
    if not isinstance(routes, list) or len(routes) != len(ROUTE_REQUIREMENTS):
        raise ValueError("routes must contain every routing kind exactly once")
    kinds = [item.get("kind") for item in routes if isinstance(item, dict)]
    if set(kinds) != set(ROUTE_REQUIREMENTS) or len(kinds) != len(set(kinds)):
        raise ValueError("routes must contain every routing kind exactly once")
    project_ids = {item.get("id") for item in profile.get("projects", []) if isinstance(item, dict)}
    if not project_ids:
        project_ids = {profile.get("project", {}).get("artifactId")}
    store_ids = {item.get("id") for item in profile.get("dataStores", []) if isinstance(item, dict)}
    requirements = feature["designRequirements"]
    artifact_paths: set[str] = set()
    for index, item in enumerate(routes):
        kind = item["kind"]
        location = f"routes[{index}]"
        if item.get("requirementRef") != ROUTE_REQUIREMENTS[kind]:
            raise ValueError(f"{location}.requirementRef does not match {kind}")
        disposition = text(item.get("disposition"), f"{location}.disposition")
        if disposition not in DISPOSITIONS:
            raise ValueError(f"{location}.disposition: invalid value {disposition}")
        reason = text(item.get("reason"), f"{location}.reason")
        source = text(item.get("source"), f"{location}.source")
        if source not in SOURCES:
            raise ValueError(f"{location}.source: invalid source {source}")
        confirmed = item.get("confirmedByUser")
        if not isinstance(confirmed, bool):
            raise ValueError(f"{location}.confirmedByUser: boolean required")
        target = item.get("target")
        if not isinstance(target, dict) or set(target) != {"projectId", "modulePath", "dataStoreIds"}:
            raise ValueError(f"{location}.target: projectId, modulePath, and dataStoreIds required")
        data_store_refs = string_list(target["dataStoreIds"], f"{location}.target.dataStoreIds")
        evidence_refs = string_list(item.get("evidencePaths"), f"{location}.evidencePaths")
        invalid_evidence = set(evidence_refs) - evidence_paths
        if invalid_evidence:
            raise ValueError(f"{location}.evidencePaths: unknown paths {sorted(invalid_evidence)}")
        artifact = item.get("artifactPath")
        if artifact is not None:
            text(artifact, f"{location}.artifactPath", False)
        if disposition in ACTIVE:
            project_id = text(target.get("projectId"), f"{location}.target.projectId", False)
            text(target.get("modulePath"), f"{location}.target.modulePath", False)
            if project_id not in project_ids:
                blockers.append(f"route target project is not in technology profile: {kind}")
            if disposition in {"EXTEND", "REUSE"} and not evidence_refs:
                blockers.append(f"{disposition} requires code evidence: {kind}")
            if disposition in {"CREATE", "EXTEND"} and artifact is None:
                blockers.append(f"{disposition} requires artifactPath: {kind}")
            if artifact is not None:
                if artifact in artifact_paths:
                    blockers.append(f"active routes share artifactPath: {artifact}")
                artifact_paths.add(artifact)
        if set(data_store_refs) - store_ids:
            blockers.append(f"route references unknown data store: {kind}")
        if kind == "PERSISTENCE" and disposition in ACTIVE and len(store_ids) > 1 and not data_store_refs:
            blockers.append("active persistence route must select data stores")
        if kind in {"SECURITY", "VERIFICATION"}:
            expected = None
        else:
            expected = requirements[ROUTE_REQUIREMENTS[kind]]["status"]
        if expected == "REQUIRED" and disposition not in ACTIVE | {"UNKNOWN"}:
            blockers.append(f"required design cannot be {disposition}: {kind}")
        if expected == "NOT_USED" and disposition != "NOT_NEEDED":
            blockers.append(f"unused design must be NOT_NEEDED: {kind}")
        if expected == "DEFERRED" and disposition != "DEFERRED":
            blockers.append(f"deferred design must remain DEFERRED: {kind}")
        if disposition == "UNKNOWN":
            blockers.append(f"route disposition is UNKNOWN: {kind}")
        if reason == "UNKNOWN" or source == "UNKNOWN":
            blockers.append(f"route reason or source is UNKNOWN: {kind}")
        if source in {"RECOMMENDED", "INFERRED"} and not confirmed:
            blockers.append(f"AI-proposed route is not user-confirmed: {kind}")
        if kind == "VERIFICATION" and disposition not in ACTIVE | {"UNKNOWN"}:
            blockers.append("verification route must be CREATE, EXTEND, or REUSE")
        if kind == "SECURITY" and feature["authorization"] and disposition not in ACTIVE | {"UNKNOWN"}:
            blockers.append("authorized feature requires an active security route")
    approved = validate_approval(route.get("approval"), "approval", route)
    return approved, blockers


def verify_inputs(route: dict[str, Any], feature_path: Path, project_path: Path, profile_path: Path, target: Path) -> list[str]:
    blockers: list[str] = []
    root = target.resolve()
    for name, actual in (("feature", feature_path), ("projectBrief", project_path), ("technologyProfile", profile_path)):
        try:
            resolved = actual.resolve(strict=True)
        except OSError:
            blockers.append(f"{name} input is missing")
            continue
        if root not in (resolved, *resolved.parents):
            blockers.append(f"{name} input escapes target")
        else:
            declared = route["inputs"][name]["path"]
            if resolved.relative_to(root).as_posix() != declared:
                blockers.append(f"{name} input path does not match the manifest")
    if route["inputs"]["feature"]["sha256"] != "UNKNOWN" and sha256(feature_path) != route["inputs"]["feature"]["sha256"]:
        blockers.append("feature input hash is stale")
    if route["inputs"]["projectBrief"]["sha256"] != "UNKNOWN" and sha256(project_path) != route["inputs"]["projectBrief"]["sha256"]:
        blockers.append("project brief input hash is stale")
    if route["inputs"]["technologyProfile"]["sha256"] != "UNKNOWN" and sha256(profile_path) != route["inputs"]["technologyProfile"]["sha256"]:
        blockers.append("technology profile input hash is stale")
    for item in route["inputs"]["codeEvidence"]:
        evidence_path = target / item["path"]
        try:
            resolved = evidence_path.resolve(strict=True)
        except OSError:
            blockers.append(f"code evidence is missing: {item['path']}")
            continue
        if root not in (resolved, *resolved.parents):
            blockers.append(f"code evidence escapes target: {item['path']}")
        elif not resolved.is_file() or sha256(resolved) != item["sha256"]:
            blockers.append(f"code evidence is stale: {item['path']}")
    for item in route["routes"]:
        if item["disposition"] not in ACTIVE:
            continue
        for label, value in (("modulePath", item["target"]["modulePath"]), ("artifactPath", item["artifactPath"])):
            if value is None or value == "UNKNOWN":
                continue
            resolved = (root / value).resolve()
            if root not in (resolved, *resolved.parents):
                blockers.append(f"route {label} escapes target: {item['kind']}")
    return blockers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--route", required=True, type=Path)
    parser.add_argument("--feature", required=True, type=Path)
    parser.add_argument("--project-brief", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    try:
        route = load_object(args.route)
        feature = load_object(args.feature)
        project = load_object(args.project_brief)
        profile = load_object(args.profile)
        _, _, _, profile_ready, profile_blockers = evaluate(args.profile)
        approved, blockers = validate(route, feature, project, profile)
        blockers.extend(f"technology profile: {item}" for item in profile_blockers)
        blockers.extend(verify_inputs(route, args.feature, args.project_brief, args.profile, args.target))
        ready = approved and profile_ready and not blockers
    except (OSError, ValueError) as error:
        print(f"DESIGN_ROUTE_VALID: no\nERROR: {error}")
        return 1
    print("DESIGN_ROUTE_VALID: yes")
    print(f"APPROVED: {'yes' if approved else 'no'}")
    print(f"DESIGN_READY: {'yes' if ready else 'no'}")
    for blocker in blockers:
        print(f"BLOCKER: {blocker}")
    return 1 if args.require_ready and not ready else 0


if __name__ == "__main__":
    sys.exit(main())
