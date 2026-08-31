#!/usr/bin/env python3
"""Validate a generation plan before a dry-run renderer consumes it."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ALLOWED_PLAN_STATUSES = {"READY_FOR_DRY_RUN", "REVIEW_REQUIRED"}


def load_object(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{path}: cannot load JSON: {error}") from error
    if not isinstance(value, dict):
        raise ValueError("plan root must be an object")
    return value


def non_empty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate(plan: dict[str, Any]) -> None:
    if plan.get("planVersion") != 1:
        raise ValueError("planVersion must be 1")
    if plan.get("planStatus") not in ALLOWED_PLAN_STATUSES:
        raise ValueError("planStatus is invalid")
    initializr = plan.get("initializr")
    if not isinstance(initializr, dict) or not non_empty_text(initializr.get("service")):
        raise ValueError("initializr.service is required")
    service = urlparse(initializr["service"])
    if service.scheme != "https" or not service.netloc or service.username or service.password:
        raise ValueError("initializr.service must be an HTTPS URL without credentials")
    request = initializr.get("request")
    structure = plan.get("projectStructure")
    if not isinstance(structure, dict):
        raise ValueError("projectStructure is required")
    if structure.get("shape") == "multi-project":
        if request is not None or initializr.get("childPlansRequired") is not True:
            raise ValueError("multi-project plan must require child Initializr plans")
        if not isinstance(structure.get("childProjects"), list) or not structure["childProjects"]:
            raise ValueError("multi-project plan requires childProjects")
        request = initializr.get("defaultRequest")
    if not isinstance(request, dict):
        raise ValueError("an Initializr request or multi-project defaultRequest is required")
    for field in ("type", "language", "bootVersion", "javaVersion", "packaging", "groupId", "artifactId", "name", "packageName"):
        if not non_empty_text(request.get(field)):
            raise ValueError(f"Initializr request field is required: {field}")
    dependencies = request.get("dependencies")
    if not isinstance(dependencies, list) or not all(
        non_empty_text(item) for item in dependencies
    ):
        raise ValueError("initializr.request.dependencies must be a string array")
    if dependencies != sorted(set(dependencies)):
        raise ValueError("initializr.request.dependencies must be sorted and unique")
    secrets = plan.get("secrets")
    if not isinstance(secrets, dict) or secrets.get("valuesStored") is not False:
        raise ValueError("generation plans must never store secret values")
    if set(secrets) != {"requiredNames", "valuesStored"}:
        raise ValueError("secrets may contain requiredNames and valuesStored only")
    required_names = secrets.get("requiredNames")
    if not isinstance(required_names, list) or not all(
        non_empty_text(item) for item in required_names
    ):
        raise ValueError("secrets.requiredNames must be a string array")
    if required_names != sorted(set(required_names)):
        raise ValueError("secrets.requiredNames must be sorted and unique")
    reviews = plan.get("reviews")
    if not isinstance(reviews, list) or not all(non_empty_text(item) for item in reviews):
        raise ValueError("reviews must be a string array")
    if reviews and plan.get("planStatus") != "REVIEW_REQUIRED":
        raise ValueError("a plan with reviews must be REVIEW_REQUIRED")
    for field in ("capabilities", "externalPrerequisites", "verification"):
        values = plan.get(field)
        if not isinstance(values, list) or not all(non_empty_text(item) for item in values):
            raise ValueError(f"{field} must be a string array")
        if values != sorted(set(values)):
            raise ValueError(f"{field} must be sorted and unique")
    changes = plan.get("plannedChanges")
    if not isinstance(changes, dict) or changes.get("state") != "NOT_COMPUTED":
        raise ValueError("plannedChanges must remain NOT_COMPUTED before dry run")
    for field in ("creates", "updates", "conflicts"):
        if changes.get(field) != []:
            raise ValueError(f"plannedChanges.{field} must be empty before dry run")
    if plan.get("executionReady") is not False:
        raise ValueError("executionReady must be false before dry run and approval")
    deferred = plan.get("deferredValidations")
    if not isinstance(deferred, list) or not deferred or not all(
        non_empty_text(item) for item in deferred
    ):
        raise ValueError("deferredValidations must name dry-run checks")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    args = parser.parse_args()
    try:
        validate(load_object(args.plan))
    except ValueError as error:
        print(f"GENERATION_PLAN_VALID: no\nERROR: {error}")
        return 1
    print("GENERATION_PLAN_VALID: yes")
    print("DRY_RUN_READY: yes")
    print("EXECUTION_READY: no")
    return 0


if __name__ == "__main__":
    sys.exit(main())
