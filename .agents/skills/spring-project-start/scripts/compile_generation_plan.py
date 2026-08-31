#!/usr/bin/env python3
"""Compile a generation plan without creating or modifying target source files."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from evaluate_profile import evaluate


JAVA_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)+$")
ARTIFACT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def load_object(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{path}: cannot load JSON: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{path}: root must be an object")
    return value


def metadata_ids(metadata: dict[str, Any], field: str) -> set[str]:
    value = metadata.get(field, {})
    values = value.get("values", []) if isinstance(value, dict) else []
    return {
        item["id"]
        for item in values
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def dependency_ids(metadata: dict[str, Any]) -> set[str]:
    dependencies = metadata.get("dependencies", {})
    groups = dependencies.get("values", []) if isinstance(dependencies, dict) else []
    result: set[str] = set()
    for group in groups:
        if not isinstance(group, dict):
            continue
        for item in group.get("values", []):
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                result.add(item["id"])
    return result


def compile_plan(
    profile_path: Path, metadata_path: Path
) -> dict[str, Any]:
    compatibility, findings, unresolved, ready, blockers = evaluate(profile_path)
    if not ready:
        details = "; ".join(blockers)
        raise ValueError(f"profile is not generation-ready: {details}")

    skill_root = Path(__file__).resolve().parent.parent
    mappings_doc = load_object(skill_root / "references" / "generation-mappings.json")
    profile = load_object(profile_path)
    metadata = load_object(metadata_path)
    decisions = profile["decisions"]

    dependencies: set[str] = set()
    contributors: set[str] = set()
    capabilities: set[str] = set()
    prerequisites: set[str] = set()
    required_secrets: set[str] = set()
    verification: set[str] = set()
    reviews: set[str] = set()
    initializr: dict[str, Any] = {}
    project_shape = "single-project"
    selected_options: dict[str, str] = {}

    mappings = mappings_doc["optionMappings"]
    for axis_id, decision in decisions.items():
        if decision.get("status") != "NOW" or not decision.get("option"):
            continue
        option_id = decision["option"]
        selected_options[axis_id] = option_id
        mapping = mappings.get(option_id, {})
        initializr_mapping = mapping.get("initializr", {})
        for key in ("language", "type", "packaging"):
            value = initializr_mapping.get(key)
            if value:
                existing = initializr.get(key)
                if existing and existing != value:
                    raise ValueError(f"conflicting Initializr {key}: {existing} vs {value}")
                initializr[key] = value
        dependencies.update(initializr_mapping.get("dependencies", []))
        contributors.update(mapping.get("contributors", []))
        capabilities.update(mapping.get("capabilities", []))
        prerequisites.update(mapping.get("externalPrerequisites", []))
        required_secrets.update(mapping.get("requiredSecrets", []))
        verification.update(mapping.get("verification", []))
        reviews.update(mapping.get("reviews", []))
        if mapping.get("projectShape"):
            project_shape = mapping["projectShape"]

    initializr["bootVersion"] = decisions["spring-boot-version"]["resolvedValue"]
    initializr["javaVersion"] = decisions["java-version"]["option"].split(".", 1)[1]
    initializr["dependencies"] = sorted(dependencies)
    project = profile["project"]
    if not JAVA_NAME.fullmatch(project["groupId"]):
        raise ValueError(f"invalid Java groupId: {project['groupId']}")
    if not JAVA_NAME.fullmatch(project["packageName"]):
        raise ValueError(f"invalid Java packageName: {project['packageName']}")
    if not ARTIFACT_NAME.fullmatch(project["artifactId"]):
        raise ValueError(f"invalid artifactId: {project['artifactId']}")
    initializr.update(
        {
            "groupId": project["groupId"],
            "artifactId": project["artifactId"],
            "name": project["name"],
            "description": project.get("description", ""),
            "packageName": project["packageName"],
        }
    )

    checks = {
        "type": metadata_ids(metadata, "type"),
        "language": metadata_ids(metadata, "language"),
        "packaging": metadata_ids(metadata, "packaging"),
        "bootVersion": metadata_ids(metadata, "bootVersion"),
        "javaVersion": metadata_ids(metadata, "javaVersion"),
    }
    for field, supported in checks.items():
        if supported and initializr.get(field) not in supported:
            raise ValueError(
                f"Initializr metadata does not support {field}={initializr.get(field)}"
            )
    unsupported_dependencies = dependencies - dependency_ids(metadata)
    if unsupported_dependencies:
        raise ValueError(
            "Initializr metadata does not support dependencies: "
            f"{sorted(unsupported_dependencies)}"
        )

    multi_project = project_shape == "multi-project"
    if multi_project and not profile.get("projects"):
        raise ValueError("multi-project plan requires child project definitions")
    plan_status = "REVIEW_REQUIRED" if reviews else "READY_FOR_DRY_RUN"
    initializr_section: dict[str, Any] = {
        "service": mappings_doc["initializrService"],
        "request": None if multi_project else initializr,
    }
    if multi_project:
        initializr_section["childPlansRequired"] = True
        initializr_section["defaultRequest"] = initializr
    return {
        "planVersion": 1,
        "planStatus": plan_status,
        "source": {
            "profile": str(profile_path),
            "metadata": str(metadata_path),
            "compatibilityResult": compatibility,
            "acceptedCompatibilityFindings": profile.get("compatibilityReview", {}).get(
                "acceptedFindings", []
            ),
        },
        "selectedOptions": dict(sorted(selected_options.items())),
        "initializr": initializr_section,
        "projectStructure": {
            "shape": project_shape,
            "contributors": sorted(contributors),
            "childProjects": profile.get("projects", []),
            "dataStores": profile.get("dataStores", []),
        },
        "capabilities": sorted(capabilities),
        "externalPrerequisites": sorted(prerequisites),
        "secrets": {
            "requiredNames": sorted(required_secrets),
            "valuesStored": False,
        },
        "verification": sorted(verification),
        "reviews": sorted(reviews),
        "deferredValidations": [
            "Spring Initializr dependency version ranges and generated build compatibility must be verified during dry run."
        ],
        "plannedChanges": {
            "state": "NOT_COMPUTED",
            "creates": [],
            "updates": [],
            "conflicts": [],
            "nextStep": "Run a separate dry-run renderer before applying files."
        },
        "executionReady": False,
    }


def write_plan(plan: dict[str, Any], output: Path, force: bool) -> None:
    if output.exists() and not force:
        raise ValueError(f"output already exists; use --force to replace it: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(plan, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        temporary.replace(output)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        plan = compile_plan(args.profile, args.metadata)
        if args.output:
            write_plan(plan, args.output, args.force)
            print(f"GENERATION_PLAN: {args.output}")
        else:
            json.dump(plan, sys.stdout, ensure_ascii=False, indent=2)
            print()
    except ValueError as error:
        print(f"GENERATION_PLAN_VALID: no\nERROR: {error}", file=sys.stderr)
        return 1
    print("GENERATION_PLAN_VALID: yes", file=sys.stderr)
    print(f"PLAN_STATUS: {plan['planStatus']}", file=sys.stderr)
    print("TARGET_SOURCE_CHANGED: no", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
