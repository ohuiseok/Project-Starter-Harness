#!/usr/bin/env python3
"""Validate the spring-project-start technology catalog with stdlib only."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ALLOWED_STATUSES = {"NOW", "SOON", "DEFERRED", "NOT_USED", "UNKNOWN"}
ALLOWED_RESULTS = {"SUPPORTED", "REVIEW_REQUIRED", "CONFLICT"}


def fail(message: str) -> None:
    raise ValueError(message)


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        fail(f"{path.name}: cannot load JSON: {error}")
    if not isinstance(value, dict):
        fail(f"{path.name}: root must be an object")
    if value.get("schemaVersion") != 1:
        fail(f"{path.name}: schemaVersion must be 1")
    return value


def require_text(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        fail(f"{location}: non-empty string required")
    return value


def validate() -> tuple[int, int, int, list[str]]:
    root = Path(__file__).resolve().parent.parent / "references"
    options_doc = load_json(root / "technology-options.json")
    rules_doc = load_json(root / "compatibility-rules.json")
    profiles_doc = load_json(root / "profiles.json")
    readiness_doc = load_json(root / "generation-readiness.json")
    mappings_doc = load_json(root / "generation-mappings.json")

    axes = options_doc.get("axes")
    if not isinstance(axes, list) or not axes:
        fail("technology-options.json: axes must be a non-empty array")

    axis_options: dict[str, set[str]] = {}
    all_options: set[str] = set()
    for index, axis in enumerate(axes):
        location = f"technology-options.json axes[{index}]"
        if not isinstance(axis, dict):
            fail(f"{location}: object required")
        axis_id = require_text(axis.get("id"), f"{location}.id")
        require_text(axis.get("label"), f"{location}.label")
        stage = require_text(axis.get("decisionStage"), f"{location}.decisionStage")
        if stage not in ALLOWED_STATUSES:
            fail(f"{location}.decisionStage: invalid status {stage}")
        if axis_id in axis_options:
            fail(f"{location}: duplicate axis id {axis_id}")
        if axis.get("customAllowed") is not True:
            fail(f"{location}: customAllowed must be true")
        options = axis.get("options")
        if not isinstance(options, list) or len(options) < 2:
            fail(f"{location}.options: at least two representative options required")
        axis_options[axis_id] = set()
        for option_index, option in enumerate(options):
            option_location = f"{location}.options[{option_index}]"
            if not isinstance(option, dict):
                fail(f"{option_location}: object required")
            option_id = require_text(option.get("id"), f"{option_location}.id")
            require_text(option.get("label"), f"{option_location}.label")
            require_text(option.get("description"), f"{option_location}.description")
            if not option_id.startswith(f"{axis_id}."):
                fail(f"{option_location}.id: must start with {axis_id}.")
            if option_id in all_options:
                fail(f"{option_location}: duplicate option id {option_id}")
            axis_options[axis_id].add(option_id)
            all_options.add(option_id)

    rules = rules_doc.get("rules")
    if not isinstance(rules, list):
        fail("compatibility-rules.json: rules must be an array")
    rule_ids: set[str] = set()
    normalized_rules: list[tuple[str, set[str], str]] = []
    for index, rule in enumerate(rules):
        location = f"compatibility-rules.json rules[{index}]"
        if not isinstance(rule, dict):
            fail(f"{location}: object required")
        rule_id = require_text(rule.get("id"), f"{location}.id")
        if rule_id in rule_ids:
            fail(f"{location}: duplicate rule id {rule_id}")
        rule_ids.add(rule_id)
        result = require_text(rule.get("result"), f"{location}.result")
        if result not in ALLOWED_RESULTS:
            fail(f"{location}.result: invalid result {result}")
        require_text(rule.get("message"), f"{location}.message")
        when = rule.get("when")
        selected = when.get("all") if isinstance(when, dict) else None
        if not isinstance(selected, list) or len(selected) < 2:
            fail(f"{location}.when.all: at least two option ids required")
        selected_set = set(selected)
        if len(selected_set) != len(selected):
            fail(f"{location}.when.all: duplicate option id")
        unknown = selected_set - all_options
        if unknown:
            fail(f"{location}.when.all: unknown options {sorted(unknown)}")
        normalized_rules.append((rule_id, selected_set, result))

    profiles = profiles_doc.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        fail("profiles.json: profiles must be a non-empty array")
    profile_ids: set[str] = set()
    warnings: list[str] = []
    for index, profile in enumerate(profiles):
        location = f"profiles.json profiles[{index}]"
        if not isinstance(profile, dict):
            fail(f"{location}: object required")
        profile_id = require_text(profile.get("id"), f"{location}.id")
        require_text(profile.get("label"), f"{location}.label")
        require_text(profile.get("useWhen"), f"{location}.useWhen")
        if profile_id in profile_ids:
            fail(f"{location}: duplicate profile id {profile_id}")
        profile_ids.add(profile_id)
        selections = profile.get("selections")
        if not isinstance(selections, dict):
            fail(f"{location}.selections: object required")
        unknown_axes = set(selections) - set(axis_options)
        if unknown_axes:
            fail(f"{location}.selections: unknown axes {sorted(unknown_axes)}")
        selected_options: set[str] = set()
        for axis_id, decision in selections.items():
            decision_location = f"{location}.selections.{axis_id}"
            if not isinstance(decision, dict):
                fail(f"{decision_location}: object required")
            option_id = require_text(decision.get("option"), f"{decision_location}.option")
            if option_id not in axis_options[axis_id]:
                fail(f"{decision_location}.option: {option_id} does not belong to {axis_id}")
            status = require_text(decision.get("status"), f"{decision_location}.status")
            if status not in ALLOWED_STATUSES:
                fail(f"{decision_location}.status: invalid status {status}")
            selected_options.add(option_id)
        for rule_id, required_options, result in normalized_rules:
            if required_options <= selected_options:
                if result == "CONFLICT":
                    fail(f"profiles.json profile {profile_id}: triggers conflict {rule_id}")
                warnings.append(f"profile {profile_id}: {result} {rule_id}")

    required_axes = readiness_doc.get("requiredAxes")
    if not isinstance(required_axes, list) or not required_axes:
        fail("generation-readiness.json: requiredAxes must be a non-empty array")
    unknown_required_axes = set(required_axes) - set(axis_options)
    if unknown_required_axes:
        fail(f"generation-readiness.json: unknown required axes {sorted(unknown_required_axes)}")
    for index, profile in enumerate(profiles):
        missing_axes = set(required_axes) - set(profile["selections"])
        if missing_axes:
            fail(
                f"profiles.json profiles[{index}]: missing generation-required axes "
                f"{sorted(missing_axes)}"
            )
    resolved_axes = readiness_doc.get("resolvedValueAxes")
    if not isinstance(resolved_axes, list):
        fail("generation-readiness.json: resolvedValueAxes must be an array")
    unknown_resolved_axes = set(resolved_axes) - set(axis_options)
    if unknown_resolved_axes:
        fail(f"generation-readiness.json: unknown resolved axes {sorted(unknown_resolved_axes)}")
    required_object_fields = readiness_doc.get("requiredObjectFields", {})
    if not isinstance(required_object_fields, dict):
        fail("generation-readiness.json: requiredObjectFields must be an object")
    for object_name, fields in required_object_fields.items():
        if not isinstance(object_name, str) or not object_name:
            fail("generation-readiness.json: required object name must be non-empty")
        if not isinstance(fields, list) or not fields or not all(
            isinstance(field, str) and field for field in fields
        ):
            fail(
                f"generation-readiness.json requiredObjectFields.{object_name}: "
                "non-empty string array required"
            )
    conditional_rules = readiness_doc.get("conditionalRules")
    if not isinstance(conditional_rules, list):
        fail("generation-readiness.json: conditionalRules must be an array")
    readiness_rule_ids: set[str] = set()
    for index, rule in enumerate(conditional_rules):
        location = f"generation-readiness.json conditionalRules[{index}]"
        if not isinstance(rule, dict):
            fail(f"{location}: object required")
        rule_id = require_text(rule.get("id"), f"{location}.id")
        if rule_id in readiness_rule_ids:
            fail(f"{location}: duplicate rule id {rule_id}")
        readiness_rule_ids.add(rule_id)
        require_text(rule.get("message"), f"{location}.message")
        when_any = rule.get("whenAny")
        if not isinstance(when_any, list) or not when_any:
            fail(f"{location}.whenAny: non-empty option array required")
        unknown_when = set(when_any) - all_options
        if unknown_when:
            fail(f"{location}.whenAny: unknown options {sorted(unknown_when)}")
        allowed_options = rule.get("allowedOptions", {})
        if not isinstance(allowed_options, dict):
            fail(f"{location}.allowedOptions: object required")
        for axis_id, option_ids in allowed_options.items():
            if axis_id not in axis_options:
                fail(f"{location}.allowedOptions: unknown axis {axis_id}")
            if not isinstance(option_ids, list) or not option_ids:
                fail(f"{location}.allowedOptions.{axis_id}: non-empty array required")
            invalid_options = set(option_ids) - axis_options[axis_id]
            if invalid_options:
                fail(f"{location}.allowedOptions.{axis_id}: invalid options {sorted(invalid_options)}")
        required_arrays = rule.get("requiredNonEmptyArrays", [])
        if not isinstance(required_arrays, list) or not all(
            isinstance(item, str) and item for item in required_arrays
        ):
            fail(f"{location}.requiredNonEmptyArrays: string array required")
        array_fields = rule.get("requiredArrayObjectFields", {})
        if not isinstance(array_fields, dict):
            fail(f"{location}.requiredArrayObjectFields: object required")
        for field, required_fields in array_fields.items():
            if field not in required_arrays:
                fail(
                    f"{location}.requiredArrayObjectFields.{field}: field must also be "
                    "listed in requiredNonEmptyArrays"
                )
            if not isinstance(required_fields, list) or not required_fields or not all(
                isinstance(item, str) and item for item in required_fields
            ):
                fail(
                    f"{location}.requiredArrayObjectFields.{field}: "
                    "non-empty string array required"
                )
        if not allowed_options and not required_arrays and not array_fields:
            fail(f"{location}: at least one readiness requirement is required")

    mappings = mappings_doc.get("optionMappings")
    if not isinstance(mappings, dict):
        fail("generation-mappings.json: optionMappings must be an object")
    unknown_mapping_options = set(mappings) - all_options
    if unknown_mapping_options:
        fail(
            "generation-mappings.json: mappings reference unknown options "
            f"{sorted(unknown_mapping_options)}"
        )
    for option_id, mapping in mappings.items():
        location = f"generation-mappings.json optionMappings.{option_id}"
        if not isinstance(mapping, dict):
            fail(f"{location}: object required")
        initializr = mapping.get("initializr", {})
        if not isinstance(initializr, dict):
            fail(f"{location}.initializr: object required")
        dependencies = initializr.get("dependencies", [])
        if not isinstance(dependencies, list) or not all(
            isinstance(item, str) and item for item in dependencies
        ):
            fail(f"{location}.initializr.dependencies: string array required")
        for field in (
            "contributors",
            "capabilities",
            "externalPrerequisites",
            "requiredSecrets",
            "verification",
            "reviews",
        ):
            values = mapping.get(field, [])
            if not isinstance(values, list) or not all(
                isinstance(item, str) and item for item in values
            ):
                fail(f"{location}.{field}: string array required")
    strategies = mappings_doc.get("contributorStrategies")
    if not isinstance(strategies, dict):
        fail("generation-mappings.json: contributorStrategies must be an object")
    referenced_contributors = {
        contributor
        for mapping in mappings.values()
        for contributor in mapping.get("contributors", [])
    }
    if set(strategies) != referenced_contributors:
        fail(
            "generation-mappings.json: contributorStrategies must exactly cover "
            f"contributors; missing={sorted(referenced_contributors - set(strategies))}, "
            f"unknown={sorted(set(strategies) - referenced_contributors)}"
        )
    invalid_strategies = {
        name: strategy
        for name, strategy in strategies.items()
        if strategy not in {"initializr-covered", "manual-conflict"}
    }
    if invalid_strategies:
        fail(f"generation-mappings.json: invalid contributor strategies {invalid_strategies}")
    algorithmic_axes = {"java-version", "spring-boot-version"}
    for axis_id in required_axes:
        if axis_id in algorithmic_axes:
            continue
        missing_mappings = axis_options[axis_id] - set(mappings)
        if missing_mappings:
            fail(
                f"generation-mappings.json: required axis {axis_id} has unmapped "
                f"options {sorted(missing_mappings)}"
            )

    return len(axes), len(all_options), len(profiles), warnings


def main() -> int:
    try:
        axes, options, profiles, warnings = validate()
    except ValueError as error:
        print(f"CATALOG_VALID: no\nERROR: {error}")
        return 1
    print("CATALOG_VALID: yes")
    print(f"AXES: {axes}")
    print(f"OPTIONS: {options}")
    print(f"PROFILES: {profiles}")
    print(f"REVIEW_WARNINGS: {len(warnings)}")
    for warning in warnings:
        print(f"WARNING: {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
