#!/usr/bin/env python3
"""Evidence and compatibility assessment for HTTP API REUSE and EXTEND."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from http_api_contract import encoded, operations, validate_openapi
from validate_design_contract import inside, validate as validate_metadata
from validate_feature_specs import load_object, text


MAPPING = re.compile(r"@(Get|Post|Put|Delete|Patch)Mapping\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?[\"']([^\"']*)[\"']")
REQUEST_MAPPING = re.compile(
    r"@RequestMapping\s*\([^)]*(?:value|path)\s*=\s*[\"']([^\"']*)[\"'][^)]*method\s*=\s*RequestMethod\.(GET|POST|PUT|DELETE|PATCH)"
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def operation_map(document: dict[str, Any]) -> dict[str, tuple[str, str, dict[str, Any]]]:
    result = {}
    for path, method, operation in operations(document):
        operation_id = text(operation.get("operationId"), f"paths.{path}.{method}.operationId", False)
        if operation_id in result:
            raise ValueError(f"duplicate operationId in existing OpenAPI: {operation_id}")
        result[operation_id] = (path, method, operation)
    return result


def required_parameters(operation: dict[str, Any]) -> set[tuple[str, str]]:
    return {
        (item.get("in"), item.get("name")) for item in operation.get("parameters", [])
        if isinstance(item, dict) and item.get("required") is True
    }


def schema_signature(operation: dict[str, Any]) -> str:
    body = operation.get("requestBody", {})
    return json.dumps(body, sort_keys=True, separators=(",", ":"))


def request_schema(operation: dict[str, Any]) -> dict[str, Any]:
    content = operation.get("requestBody", {}).get("content", {})
    media = next(iter(content.values()), {}) if isinstance(content, dict) else {}
    return media.get("schema", {}) if isinstance(media, dict) else {}


def response_schemas(operation: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for code, response in operation.get("responses", {}).items():
        content = response.get("content", {}) if isinstance(response, dict) else {}
        media = next(iter(content.values()), {}) if isinstance(content, dict) else {}
        result[str(code)] = media.get("schema", {}) if isinstance(media, dict) else {}
    return result


def schema_breaks(old: Any, new: Any, request: bool) -> bool:
    if not isinstance(old, dict) or not isinstance(new, dict):
        return old != new
    if old.get("type") != new.get("type") and old.get("type") is not None:
        return True
    if set(old.get("enum", [])) - set(new.get("enum", [])):
        return True
    old_properties, new_properties = old.get("properties", {}), new.get("properties", {})
    if isinstance(old_properties, dict) and isinstance(new_properties, dict):
        if not request and set(old_properties) - set(new_properties):
            return True
        for name in set(old_properties) & set(new_properties):
            if schema_breaks(old_properties[name], new_properties[name], request):
                return True
    old_required, new_required = set(old.get("required", [])), set(new.get("required", []))
    if request and new_required - old_required:
        return True
    if not request and old_required - new_required:
        return True
    return False


def compare_openapi(baseline: dict[str, Any], proposed: dict[str, Any], contract_id: str) -> dict[str, Any]:
    before = operation_map(baseline)
    after = operation_map(proposed)
    changes: list[dict[str, str]] = []
    for operation_id in sorted(set(before) - set(after)):
        changes.append({"level": "BREAKING", "code": "OPERATION_REMOVED", "location": operation_id, "message": "Existing operation is removed."})
    for operation_id in sorted(set(after) - set(before)):
        changes.append({"level": "NON_BREAKING", "code": "OPERATION_ADDED", "location": operation_id, "message": "New operation is added."})
    for operation_id in sorted(set(before) & set(after)):
        old_path, old_method, old = before[operation_id]
        new_path, new_method, new = after[operation_id]
        if (old_path, old_method) != (new_path, new_method):
            changes.append({"level": "BREAKING", "code": "ENDPOINT_CHANGED", "location": operation_id, "message": "Path or method changes."})
        added_required = required_parameters(new) - required_parameters(old)
        if added_required:
            changes.append({"level": "BREAKING", "code": "REQUIRED_PARAMETER_ADDED", "location": operation_id, "message": "A required parameter is added."})
        removed_responses = set(old.get("responses", {})) - set(new.get("responses", {}))
        if removed_responses:
            changes.append({"level": "BREAKING", "code": "RESPONSE_REMOVED", "location": operation_id, "message": "An existing response is removed."})
        if not old.get("security", baseline.get("security")) and new.get("security", proposed.get("security")):
            changes.append({"level": "BREAKING", "code": "SECURITY_REQUIRED", "location": operation_id, "message": "Authentication becomes required."})
        if schema_signature(old) != schema_signature(new):
            level = "BREAKING" if schema_breaks(request_schema(old), request_schema(new), True) else "REVIEW"
            changes.append({"level": level, "code": "REQUEST_SCHEMA_CHANGED", "location": operation_id, "message": "Request schema changes."})
        old_responses, new_responses = response_schemas(old), response_schemas(new)
        for code in sorted(set(old_responses) & set(new_responses)):
            if old_responses[code] != new_responses[code]:
                level = "BREAKING" if schema_breaks(old_responses[code], new_responses[code], False) else "REVIEW"
                changes.append({"level": level, "code": "RESPONSE_SCHEMA_CHANGED", "location": f"{operation_id}:{code}", "message": "Response schema changes."})
    return {
        "reportVersion": 1, "contractId": contract_id,
        "baselineSha256": hashlib.sha256(encoded(baseline)).hexdigest(),
        "proposedSha256": hashlib.sha256(encoded(proposed)).hexdigest(),
        "summary": {
            "reused": len(set(before) & set(after)), "added": len(set(after) - set(before)),
            "removed": len(set(before) - set(after)),
            "breaking": sum(item["level"] == "BREAKING" for item in changes),
            "review": sum(item["level"] == "REVIEW" for item in changes),
        },
        "changes": changes,
    }


def controller_mappings(path: Path) -> set[tuple[str, str]]:
    source = path.read_text(encoding="utf-8")
    mappings = {(match.group(1).lower(), match.group(2) or "") for match in MAPPING.finditer(source)}
    mappings.update((match.group(2).lower(), match.group(1)) for match in REQUEST_MAPPING.finditer(source))
    return mappings


def decorated_for_feature(document: dict[str, Any], traceability: list[dict[str, Any]]) -> dict[str, Any]:
    result = copy.deepcopy(document)
    refs = {item["subjectRef"]: item["requirementRefs"] for item in traceability}
    for _, _, operation in operations(result):
        if operation.get("operationId") in refs:
            operation["x-harness-requirement-refs"] = refs[operation["operationId"]]
    return result


def validate_existing_contract(
    metadata: dict[str, Any], route: dict[str, Any], route_path: Path, target: Path,
    contract_path: Path, feature: dict[str, Any], profile: dict[str, Any],
) -> tuple[bool, list[str], dict[str, Any], dict[str, Any]]:
    approved, blockers = validate_metadata(metadata, route, route_path, target, contract_path)
    disposition = metadata.get("disposition")
    if metadata.get("kind") != "HTTP_API" or disposition not in {"REUSE", "EXTEND"}:
        blockers.append("existing HTTP API contract must be HTTP_API REUSE or EXTEND")
    root = target.resolve()
    baseline_ref = metadata.get("baselineArtifact")
    if not isinstance(baseline_ref, dict) or set(baseline_ref) != {"format", "path", "sha256"}:
        raise ValueError("baselineArtifact must contain format, path, and sha256")
    if baseline_ref["format"] != "OPENAPI":
        blockers.append("baseline artifact format must be OPENAPI")
    baseline_path = inside(root, text(baseline_ref["path"], "baselineArtifact.path", False), "baselineArtifact.path")
    if baseline_ref["path"] not in metadata.get("evidencePaths", []):
        blockers.append("baseline OpenAPI must be route evidence")
    if digest(baseline_path) != baseline_ref["sha256"]:
        blockers.append("baseline OpenAPI changed after assessment")
    baseline = load_object(baseline_path)
    artifact_path = inside(root, metadata["artifact"]["path"], "artifact.path")
    proposed = load_object(artifact_path)
    if disposition == "REUSE" and artifact_path != baseline_path:
        blockers.append("REUSE must reference the existing OpenAPI without copying it")
    decorated = decorated_for_feature(proposed, metadata["traceability"])
    validation_metadata = copy.deepcopy(metadata)
    validation_metadata["traceability"] = [
        {"subjectRef": op["operationId"], "requirementRefs": op.get("x-harness-requirement-refs", [])}
        for _, _, op in operations(decorated)
    ]
    blockers.extend(validate_openapi(decorated, feature, profile, validation_metadata))
    evidence = {item["path"]: item for item in route["inputs"]["codeEvidence"]}
    for evidence_path in metadata["evidencePaths"]:
        evidence_file = inside(root, evidence_path, "evidence path")
        recorded = evidence.get(evidence_path)
        if recorded is None:
            blockers.append(f"route evidence record is missing: {evidence_path}")
        elif digest(evidence_file) != recorded["sha256"]:
            blockers.append(f"route evidence changed after assessment: {evidence_path}")
    if evidence.get(baseline_ref["path"], {}).get("sha256") != baseline_ref["sha256"]:
        blockers.append("baseline hash does not match route evidence")
    controller_paths = [path for path in metadata["evidencePaths"] if evidence.get(path, {}).get("kind") == "SPRING_CONTROLLER"]
    if controller_paths:
        observed = set().union(*(controller_mappings(inside(root, path, "controller evidence")) for path in controller_paths))
        for path, method, operation in operations(baseline):
            if not any(found_method == method and (not found_path or found_path in path) for found_method, found_path in observed):
                blockers.append(f"controller evidence does not prove operation: {operation['operationId']}")
    comparison_ref = metadata.get("comparison")
    if not isinstance(comparison_ref, dict) or set(comparison_ref) != {"path", "sha256"}:
        raise ValueError("comparison must contain path and sha256")
    comparison_path = inside(root, comparison_ref["path"], "comparison.path")
    if digest(comparison_path) != comparison_ref["sha256"]:
        blockers.append("compatibility report changed after assessment")
    report = load_object(comparison_path)
    expected = compare_openapi(baseline, proposed, metadata["contractId"])
    if report != expected:
        blockers.append("compatibility report does not match current OpenAPI artifacts")
    if disposition == "REUSE" and report["changes"]:
        blockers.append("REUSE cannot contain interface changes")
    if disposition == "EXTEND" and report["summary"]["breaking"]:
        blockers.append("EXTEND contains breaking API changes")
    accepted = metadata.get("acceptedCompatibilityReviews", [])
    if not isinstance(accepted, list) or not all(isinstance(item, str) and item for item in accepted):
        raise ValueError("acceptedCompatibilityReviews must be a string array")
    review_ids = {f"{item['code']}:{item['location']}" for item in report["changes"] if item["level"] == "REVIEW"}
    if set(accepted) - review_ids:
        blockers.append("accepted compatibility review does not exist in current report")
    if disposition == "EXTEND" and review_ids - set(accepted):
        blockers.append("EXTEND has unresolved compatibility reviews")
    return approved, blockers, proposed, report
