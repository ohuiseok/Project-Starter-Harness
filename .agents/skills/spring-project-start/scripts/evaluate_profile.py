#!/usr/bin/env python3
"""Validate a project technology profile and evaluate catalog compatibility."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ALLOWED_STATUSES = {"NOW", "SOON", "DEFERRED", "NOT_USED", "UNKNOWN"}


def meaningful_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.strip().upper() != "UNKNOWN"


def load_object(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{path}: cannot load JSON: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{path}: root must be an object")
    return value


def evaluate(profile_path: Path) -> tuple[str, list[str], int, bool, list[str]]:
    skill_root = Path(__file__).resolve().parent.parent
    options_doc = load_object(skill_root / "references" / "technology-options.json")
    rules_doc = load_object(skill_root / "references" / "compatibility-rules.json")
    readiness_doc = load_object(skill_root / "references" / "generation-readiness.json")
    profile = load_object(profile_path)

    if profile.get("profileVersion") != 1:
        raise ValueError("profileVersion must be 1")
    decisions = profile.get("decisions")
    if not isinstance(decisions, dict):
        raise ValueError("decisions must be an object")

    option_axes: dict[str, str] = {}
    known_axes: set[str] = set()
    for axis in options_doc.get("axes", []):
        axis_id = axis["id"]
        known_axes.add(axis_id)
        for option in axis["options"]:
            option_axes[option["id"]] = axis_id

    selected: set[str] = set()
    selected_by_axis: dict[str, str] = {}
    decision_status: dict[str, str] = {}
    findings: list[str] = []
    blockers: list[str] = []
    review = profile.get("compatibilityReview", {})
    accepted_findings = review.get("acceptedFindings", []) if isinstance(review, dict) else []
    if not isinstance(accepted_findings, list) or not all(
        isinstance(item, str) and item for item in accepted_findings
    ):
        raise ValueError("compatibilityReview.acceptedFindings must be a string array")
    accepted_findings_set = set(accepted_findings)
    unresolved_reviews: set[str] = set()
    matched_reviews: set[str] = set()
    for axis_id, decision in decisions.items():
        if axis_id not in known_axes:
            raise ValueError(f"unknown decision axis: {axis_id}")
        if not isinstance(decision, dict):
            raise ValueError(f"decision {axis_id} must be an object")
        status = decision.get("status")
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"decision {axis_id} has invalid status: {status}")
        decision_status[axis_id] = status
        option = decision.get("option")
        custom = decision.get("custom")
        if bool(option) == bool(custom):
            raise ValueError(f"decision {axis_id} requires exactly one of option or custom")
        if option:
            if option not in option_axes:
                raise ValueError(f"decision {axis_id} uses unknown option: {option}")
            if option_axes[option] != axis_id:
                raise ValueError(f"option {option} does not belong to axis {axis_id}")
            selected.add(option)
            selected_by_axis[axis_id] = option
        else:
            if not isinstance(custom, str) or not custom.strip():
                raise ValueError(f"decision {axis_id} custom value must be non-empty text")
            findings.append(f"REVIEW_REQUIRED custom-{axis_id}: validate custom choice '{custom}'")
            unresolved_reviews.add(f"custom-{axis_id}")
            matched_reviews.add(f"custom-{axis_id}")
            if status == "NOW":
                blockers.append(f"NOW custom decision has no deterministic generation mapping: {axis_id}")

    for axis_id in readiness_doc.get("requiredAxes", []):
        if axis_id not in decisions:
            blockers.append(f"missing required decision: {axis_id}")
        elif decision_status.get(axis_id) != "NOW":
            blockers.append(f"required decision must be NOW: {axis_id}")
        elif axis_id not in selected_by_axis:
            blockers.append(f"required decision has no generation mapping: {axis_id}")

    for axis_id in readiness_doc.get("resolvedValueAxes", []):
        decision = decisions.get(axis_id)
        if isinstance(decision, dict):
            value = decision.get("resolvedValue")
            if not meaningful_text(value):
                blockers.append(f"exact resolvedValue is required: {axis_id}")

    for object_name, fields in readiness_doc.get("requiredObjectFields", {}).items():
        value = profile.get(object_name)
        if not isinstance(value, dict):
            blockers.append(f"required profile object is missing: {object_name}")
            continue
        for field in fields:
            field_value = value.get(field)
            if not meaningful_text(field_value):
                blockers.append(f"required profile field is missing: {object_name}.{field}")

    for rule in readiness_doc.get("conditionalRules", []):
        if not set(rule.get("whenAny", [])) & selected:
            continue
        for axis_id, allowed in rule.get("allowedOptions", {}).items():
            if selected_by_axis.get(axis_id) not in set(allowed):
                blockers.append(f"{rule['id']}: {rule['message']}")
                break
            if decision_status.get(axis_id) != "NOW":
                blockers.append(f"{rule['id']}: decision must be NOW: {axis_id}")
                break
        for field in rule.get("requiredNonEmptyArrays", []):
            value = profile.get(field)
            if not isinstance(value, list) or not value:
                blockers.append(f"{rule['id']}: {rule['message']}")
        for field, required_fields in rule.get("requiredArrayObjectFields", {}).items():
            value = profile.get(field)
            if not isinstance(value, list):
                continue
            for index, item in enumerate(value):
                if not isinstance(item, dict):
                    blockers.append(f"{rule['id']}: {field}[{index}] must be an object")
                    continue
                for required_field in required_fields:
                    if not meaningful_text(item.get(required_field)):
                        blockers.append(
                            f"{rule['id']}: missing {field}[{index}].{required_field}"
                        )

    confirmation = profile.get("confirmedBy")
    if not isinstance(confirmation, dict) or confirmation.get("user") is not True:
        blockers.append("user confirmation is required")
    elif not meaningful_text(confirmation.get("confirmedAt")):
        blockers.append("confirmation timestamp is required")

    overall = "SUPPORTED"
    for rule in rules_doc.get("rules", []):
        required = set(rule.get("when", {}).get("all", []))
        if required and required <= selected:
            result = rule["result"]
            findings.append(f"{result} {rule['id']}: {rule['message']}")
            if result == "CONFLICT":
                overall = "CONFLICT"
            elif result == "REVIEW_REQUIRED" and overall == "SUPPORTED":
                overall = "REVIEW_REQUIRED"
            if result == "REVIEW_REQUIRED" and rule["id"] not in accepted_findings_set:
                unresolved_reviews.add(rule["id"])
            if result == "REVIEW_REQUIRED":
                matched_reviews.add(rule["id"])
    if findings and overall == "SUPPORTED":
        overall = "REVIEW_REQUIRED"
    if overall == "CONFLICT":
        blockers.append("compatibility conflict must be resolved")
    for review_id in sorted(accepted_findings_set - matched_reviews):
        blockers.append(f"accepted compatibility finding is stale or unknown: {review_id}")
    for review_id in sorted(unresolved_reviews):
        blockers.append(f"compatibility review must be resolved: {review_id}")
    return overall, findings, len(unresolved_reviews), not blockers, blockers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    try:
        overall, findings, unresolved_reviews, ready, blockers = evaluate(args.profile)
    except ValueError as error:
        print(f"PROFILE_VALID: no\nERROR: {error}")
        return 2
    print("PROFILE_VALID: yes")
    print(f"COMPATIBILITY_RESULT: {overall}")
    print(f"GENERATION_READY: {'yes' if ready else 'no'}")
    print(f"FINDINGS: {len(findings)}")
    for finding in findings:
        print(f"FINDING: {finding}")
    print(f"UNRESOLVED_REVIEWS: {unresolved_reviews}")
    print(f"BLOCKERS: {len(blockers)}")
    for blocker in blockers:
        print(f"BLOCKER: {blocker}")
    if overall == "CONFLICT" or (args.require_ready and not ready):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
