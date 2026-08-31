#!/usr/bin/env python3
"""Validate project briefs and feature contracts without third-party packages."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


STATUSES = {"DRAFT", "REVIEW_REQUIRED", "APPROVED", "IMPLEMENTING", "VERIFIED", "DEFERRED"}
SOURCES = {"USER_STATED", "PROJECT_EVIDENCE", "RECOMMENDED", "INFERRED", "UNKNOWN"}
UNKNOWN_STATUSES = {"OPEN", "RESOLVED", "DEFERRED"}
FEATURE_ID = re.compile(r"^F\d{3}$")
RULE_ID = re.compile(r"^BR-(F\d{3})-\d{2}$")
CRITERION_ID = re.compile(r"^AC-(F\d{3})-\d{2}$")
UNKNOWN_ID = re.compile(r"^U-(?:PROJECT|F\d{3})-\d{2}$")
DESIGN_NEEDS = {
    "httpApi", "relationalData", "messaging", "scheduledJob",
    "serverRenderedUi", "separateClient", "externalIntegration",
}
SENSITIVE_KEYS = re.compile(r"(?:password|passwd|secret|credential|api[_-]?key|access[_-]?token|private[_-]?key)", re.I)
SENSITIVE_VALUES = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----|\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.I)


def load_object(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{path}: cannot load JSON: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{path}: root must be an object")
    return value


def text(value: Any, location: str, allow_unknown: bool = True) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{location}: non-empty string required")
    if not allow_unknown and value.strip() == "UNKNOWN":
        raise ValueError(f"{location}: resolved text required")
    return value.strip()


def string_list(value: Any, location: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{location}: string array required")
    return value


def unique_ids(items: list[Any], location: str, pattern: re.Pattern[str]) -> None:
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"{location}[{index}]: object required")
        item_id = text(item.get("id"), f"{location}[{index}].id")
        if not pattern.fullmatch(item_id):
            raise ValueError(f"{location}[{index}].id: invalid ID {item_id}")
        if item_id in seen:
            raise ValueError(f"{location}: duplicate ID {item_id}")
        seen.add(item_id)


def reject_secrets(value: Any, location: str = "root") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if SENSITIVE_KEYS.search(str(key)):
                raise ValueError(f"{location}.{key}: secret-bearing fields are not allowed")
            reject_secrets(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_secrets(child, f"{location}[{index}]")
    elif isinstance(value, str) and SENSITIVE_VALUES.search(value):
        raise ValueError(f"{location}: secret-like value is not allowed")


def approval_content_hash(document: dict[str, Any]) -> str:
    content = {key: value for key, value in document.items() if key != "approval"}
    encoded = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate_approval(value: Any, location: str, document: dict[str, Any]) -> bool:
    if not isinstance(value, dict):
        raise ValueError(f"{location}: object required")
    required = {"status", "approvedBy", "approvedAt", "approvedContentSha256"}
    if set(value) != required:
        raise ValueError(f"{location}: {sorted(required)} are required")
    status = text(value.get("status"), f"{location}.status")
    if status not in STATUSES:
        raise ValueError(f"{location}.status: invalid status {status}")
    approved = status in {"APPROVED", "IMPLEMENTING", "VERIFIED"}
    if approved:
        text(value.get("approvedBy"), f"{location}.approvedBy", False)
        approved_at = text(value.get("approvedAt"), f"{location}.approvedAt", False)
        try:
            dt.datetime.fromisoformat(approved_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError(f"{location}.approvedAt: ISO-8601 timestamp required") from error
        expected_hash = approval_content_hash(document)
        if value.get("approvedContentSha256") != expected_hash:
            raise ValueError(f"{location}.approvedContentSha256: approved content has changed")
    elif any(value.get(field) is not None for field in ("approvedBy", "approvedAt", "approvedContentSha256")):
        raise ValueError(f"{location}: unapproved artifact cannot contain approval identity")
    return approved


def validate_sources(value: Any, location: str) -> None:
    if not isinstance(value, list):
        raise ValueError(f"{location}: array required")
    seen: set[str] = set()
    for index, source in enumerate(value):
        if not isinstance(source, dict):
            raise ValueError(f"{location}[{index}]: object required")
        source_id = text(source.get("id"), f"{location}[{index}].id")
        if source_id in seen:
            raise ValueError(f"{location}: duplicate source ID {source_id}")
        seen.add(source_id)
        source_type = text(source.get("type"), f"{location}[{index}].type")
        if source_type not in SOURCES:
            raise ValueError(f"{location}[{index}].type: invalid source {source_type}")
        text(source.get("reference"), f"{location}[{index}].reference")


def validate_unknowns(value: Any, location: str, expected_feature: str | None = None) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{location}: array required")
    unique_ids(value, location, UNKNOWN_ID)
    blockers: list[str] = []
    for index, unknown in enumerate(value):
        unknown_id = unknown["id"]
        if expected_feature and not unknown_id.startswith(f"U-{expected_feature}-"):
            raise ValueError(f"{location}[{index}].id: must belong to {expected_feature}")
        text(unknown.get("question"), f"{location}[{index}].question")
        text(unknown.get("impact"), f"{location}[{index}].impact")
        if not isinstance(unknown.get("blocking"), bool):
            raise ValueError(f"{location}[{index}].blocking: boolean required")
        status = text(unknown.get("status"), f"{location}[{index}].status")
        if status not in UNKNOWN_STATUSES:
            raise ValueError(f"{location}[{index}].status: invalid status {status}")
        if unknown["blocking"] and status != "RESOLVED":
            blockers.append(f"blocking unknown is unresolved: {unknown_id}")
    return blockers


def validate_project(document: dict[str, Any]) -> tuple[bool, list[str]]:
    if document.get("schemaVersion") != 1:
        raise ValueError("schemaVersion must be 1")
    reject_secrets(document)
    project = document.get("project")
    if not isinstance(project, dict):
        raise ValueError("project: object required")
    for field in ("name", "goal"):
        text(project.get(field), f"project.{field}")
    for field in ("targetUsers", "successCriteria", "nonFunctionalRequirements"):
        string_list(project.get(field), f"project.{field}")
    scope = document.get("scope")
    if not isinstance(scope, dict):
        raise ValueError("scope: object required")
    string_list(scope.get("included"), "scope.included")
    string_list(scope.get("excluded"), "scope.excluded")
    candidates = document.get("featureCandidates")
    if not isinstance(candidates, list):
        raise ValueError("featureCandidates: array required")
    unique_ids(candidates, "featureCandidates", FEATURE_ID)
    orders: set[int] = set()
    for index, candidate in enumerate(candidates):
        text(candidate.get("name"), f"featureCandidates[{index}].name")
        text(candidate.get("userValue"), f"featureCandidates[{index}].userValue")
        text(candidate.get("recommendationReason"), f"featureCandidates[{index}].recommendationReason")
        dependencies = candidate.get("dependsOn")
        blocking_unknowns = candidate.get("blockingUnknownIds")
        if not isinstance(dependencies, list) or not all(
            isinstance(item, str) and FEATURE_ID.fullmatch(item) for item in dependencies
        ):
            raise ValueError(f"featureCandidates[{index}].dependsOn: feature ID array required")
        if not isinstance(blocking_unknowns, list) or not all(
            isinstance(item, str) and UNKNOWN_ID.fullmatch(item) for item in blocking_unknowns
        ):
            raise ValueError(f"featureCandidates[{index}].blockingUnknownIds: unknown ID array required")
        if len(dependencies) != len(set(dependencies)) or len(blocking_unknowns) != len(set(blocking_unknowns)):
            raise ValueError(f"featureCandidates[{index}]: dependency and unknown links must be unique")
        order = candidate.get("recommendedOrder")
        if not isinstance(order, int) or isinstance(order, bool) or order < 1:
            raise ValueError(f"featureCandidates[{index}].recommendedOrder: positive integer required")
        if order in orders:
            raise ValueError(f"featureCandidates: duplicate recommendedOrder {order}")
        orders.add(order)
        status = text(candidate.get("status"), f"featureCandidates[{index}].status")
        if status not in STATUSES:
            raise ValueError(f"featureCandidates[{index}].status: invalid status {status}")
    blockers = validate_unknowns(document.get("unknowns"), "unknowns")
    candidate_ids = {candidate["id"] for candidate in candidates}
    unknown_ids = {unknown["id"] for unknown in document["unknowns"]}
    for index, candidate in enumerate(candidates):
        invalid_dependencies = set(candidate["dependsOn"]) - candidate_ids
        if candidate["id"] in candidate["dependsOn"]:
            raise ValueError(f"featureCandidates[{index}].dependsOn: self dependency is not allowed")
        if invalid_dependencies:
            raise ValueError(f"featureCandidates[{index}].dependsOn: unknown features {sorted(invalid_dependencies)}")
        invalid_unknowns = set(candidate["blockingUnknownIds"]) - unknown_ids
        if invalid_unknowns:
            raise ValueError(f"featureCandidates[{index}].blockingUnknownIds: unknown IDs {sorted(invalid_unknowns)}")
    dependency_map = {candidate["id"]: candidate["dependsOn"] for candidate in candidates}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(feature_id: str) -> None:
        if feature_id in visiting:
            raise ValueError(f"featureCandidates: dependency cycle contains {feature_id}")
        if feature_id in visited:
            return
        visiting.add(feature_id)
        for dependency in dependency_map[feature_id]:
            visit(dependency)
        visiting.remove(feature_id)
        visited.add(feature_id)

    for candidate_id in dependency_map:
        visit(candidate_id)
    validate_sources(document.get("sources"), "sources")
    approved = validate_approval(document.get("approval"), "approval", document)
    if approved:
        for field in ("name", "goal"):
            if project[field] == "UNKNOWN":
                blockers.append(f"project.{field} is unresolved")
        if not project["targetUsers"]:
            blockers.append("targetUsers are required")
        elif "UNKNOWN" in project["targetUsers"]:
            blockers.append("targetUsers contain UNKNOWN")
        if not project["successCriteria"]:
            blockers.append("successCriteria are required")
        elif "UNKNOWN" in project["successCriteria"]:
            blockers.append("successCriteria contain UNKNOWN")
        if not candidates:
            blockers.append("at least one feature candidate is required")
    return approved, blockers


def validate_feature(document: dict[str, Any], project: dict[str, Any] | None) -> tuple[bool, list[str]]:
    if document.get("schemaVersion") != 1:
        raise ValueError("schemaVersion must be 1")
    reject_secrets(document)
    feature = document.get("feature")
    if not isinstance(feature, dict):
        raise ValueError("feature: object required")
    feature_id = text(feature.get("id"), "feature.id")
    if not FEATURE_ID.fullmatch(feature_id):
        raise ValueError(f"feature.id: invalid ID {feature_id}")
    for field in ("name", "goal", "userValue"):
        text(feature.get(field), f"feature.{field}")
    feature_status = text(feature.get("status"), "feature.status")
    if feature_status not in STATUSES:
        raise ValueError(f"feature.status: invalid status {feature_status}")
    string_list(document.get("actors"), "actors")
    scenario = document.get("scenario")
    if not isinstance(scenario, dict):
        raise ValueError("scenario: object required")
    for field in ("preconditions", "mainFlow", "alternateFlows", "postconditions"):
        string_list(scenario.get(field), f"scenario.{field}")
    text(scenario.get("trigger"), "scenario.trigger")

    rules = document.get("businessRules")
    if not isinstance(rules, list):
        raise ValueError("businessRules: array required")
    unique_ids(rules, "businessRules", RULE_ID)
    blockers: list[str] = []
    for index, rule in enumerate(rules):
        if RULE_ID.fullmatch(rule["id"]).group(1) != feature_id:
            raise ValueError(f"businessRules[{index}].id: must belong to {feature_id}")
        text(rule.get("description"), f"businessRules[{index}].description")
        source = text(rule.get("source"), f"businessRules[{index}].source")
        if source not in SOURCES:
            raise ValueError(f"businessRules[{index}].source: invalid source {source}")
        status = text(rule.get("status"), f"businessRules[{index}].status")
        if status not in STATUSES:
            raise ValueError(f"businessRules[{index}].status: invalid status {status}")
        confirmed = rule.get("confirmedByUser")
        if not isinstance(confirmed, bool):
            raise ValueError(f"businessRules[{index}].confirmedByUser: boolean required")
        if source in {"RECOMMENDED", "INFERRED"} and not confirmed:
            blockers.append(f"AI-proposed rule is not user-confirmed: {rule['id']}")
        if source == "UNKNOWN":
            blockers.append(f"business rule source is UNKNOWN: {rule['id']}")
    for field in ("authorization", "dataAndState", "failureCases", "dependencies"):
        string_list(document.get(field), field)

    criteria = document.get("acceptanceCriteria")
    if not isinstance(criteria, list):
        raise ValueError("acceptanceCriteria: array required")
    unique_ids(criteria, "acceptanceCriteria", CRITERION_ID)
    for index, criterion in enumerate(criteria):
        if CRITERION_ID.fullmatch(criterion["id"]).group(1) != feature_id:
            raise ValueError(f"acceptanceCriteria[{index}].id: must belong to {feature_id}")
        for field in ("given", "when", "then"):
            text(criterion.get(field), f"acceptanceCriteria[{index}].{field}", False)
    needs = document.get("designNeeds")
    if not isinstance(needs, dict) or set(needs) != DESIGN_NEEDS:
        raise ValueError(f"designNeeds must contain exactly {sorted(DESIGN_NEEDS)}")
    for field, value in needs.items():
        if not isinstance(value, bool):
            raise ValueError(f"designNeeds.{field}: boolean required")
    blockers.extend(validate_unknowns(document.get("unknowns"), "unknowns", feature_id))
    validate_sources(document.get("sources"), "sources")
    approved = validate_approval(document.get("approval"), "approval", document)
    if feature_status in {"APPROVED", "IMPLEMENTING", "VERIFIED"} and not approved:
        raise ValueError("approved feature status requires approved approval status")
    if approved and feature_status not in {"APPROVED", "IMPLEMENTING", "VERIFIED"}:
        raise ValueError("approved approval status requires an approved feature status")
    if approved:
        for field in ("name", "goal", "userValue"):
            if feature[field] == "UNKNOWN":
                blockers.append(f"feature.{field} is unresolved")
        if not document["actors"]:
            blockers.append("at least one actor is required")
        elif "UNKNOWN" in document["actors"]:
            blockers.append("actors contain UNKNOWN")
        if scenario["trigger"] == "UNKNOWN" or not scenario["mainFlow"]:
            blockers.append("a resolved trigger and main flow are required")
        elif "UNKNOWN" in scenario["mainFlow"]:
            blockers.append("main flow contains UNKNOWN")
        if not rules:
            blockers.append("at least one business rule is required")
        for rule in rules:
            if rule["description"] == "UNKNOWN":
                blockers.append(f"business rule description is unresolved: {rule['id']}")
            if rule["status"] not in {"APPROVED", "IMPLEMENTING", "VERIFIED"}:
                blockers.append(f"business rule is not approved: {rule['id']}")
        if not criteria:
            blockers.append("at least one acceptance criterion is required")
    if project is not None:
        project_approved, project_blockers = validate_project(project)
        if not project_approved:
            blockers.append("project brief is not approved")
        blockers.extend(f"project brief: {blocker}" for blocker in project_blockers)
        project_ids = {item["id"] for item in project.get("featureCandidates", []) if isinstance(item, dict) and "id" in item}
        if feature_id not in project_ids:
            blockers.append(f"feature is absent from project brief: {feature_id}")
    return approved, blockers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-brief", required=True, type=Path)
    parser.add_argument("--feature", type=Path)
    parser.add_argument("--require-approved", action="store_true")
    args = parser.parse_args()
    try:
        project = load_object(args.project_brief)
        if args.feature is None:
            approved, blockers = validate_project(project)
            kind = "PROJECT_BRIEF"
        else:
            approved, blockers = validate_feature(load_object(args.feature), project)
            kind = "FEATURE_SPEC"
    except ValueError as error:
        print(f"SPEC_VALID: no\nERROR: {error}")
        return 1
    advancement = approved and not blockers
    print("SPEC_VALID: yes")
    print(f"SPEC_KIND: {kind}")
    print(f"APPROVED: {'yes' if approved else 'no'}")
    print(f"ADVANCEMENT_READY: {'yes' if advancement else 'no'}")
    for blocker in blockers:
            print(f"BLOCKER: {blocker}")
    if args.require_approved and not advancement:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
