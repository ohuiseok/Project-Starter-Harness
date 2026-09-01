#!/usr/bin/env python3
"""Evidence and compatibility assessment for HTTP API REUSE and EXTEND."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from http_api_contract import encoded, operations, validate_openapi
from validate_design_contract import inside, validate as validate_metadata
from validate_feature_specs import SOURCES, load_object, text


ANNOTATION = re.compile(r"@(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)\s*(\([^)]*\))?", re.S)
CLASS_DECLARATION = re.compile(r"\b(?:class|interface)\s+\w+")
CUSTOM_MAPPING = re.compile(r"@(\w*Mapping)\b")
QUOTED = re.compile(r"[\"']([^\"']*)[\"']")


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


def parameter_map(document: dict[str, Any], path: str, operation: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    items = []
    path_item = document.get("paths", {}).get(path, {})
    for owner in (path_item, operation):
        if isinstance(owner, dict) and isinstance(owner.get("parameters"), list):
            items.extend(owner["parameters"])
    result = {}
    for raw in items:
        item = resolve_schema(document, raw)
        if isinstance(item, dict) and isinstance(item.get("in"), str) and isinstance(item.get("name"), str):
            result[(item["in"], item["name"])] = item
    return result


def json_pointer(document: dict[str, Any], reference: str) -> Any:
    if not reference.startswith("#/"):
        return {"$externalRef": reference}
    current: Any = document
    for raw in reference[2:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or token not in current:
            raise ValueError(f"unresolved local OpenAPI reference: {reference}")
        current = current[token]
    return current


def resolve_schema(document: dict[str, Any], value: Any, stack: tuple[str, ...] = ()) -> Any:
    if isinstance(value, dict):
        if "$ref" in value:
            reference = text(value["$ref"], "$ref", False)
            if reference in stack:
                return {"$recursiveRef": reference}
            resolved = resolve_schema(document, json_pointer(document, reference), stack + (reference,))
            siblings = {key: child for key, child in value.items() if key != "$ref"}
            if siblings and isinstance(resolved, dict):
                return {**resolved, **resolve_schema(document, siblings, stack)}
            return resolved
        return {key: resolve_schema(document, child, stack) for key, child in value.items()}
    if isinstance(value, list):
        return [resolve_schema(document, child, stack) for child in value]
    return value


def external_references(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        reference = value.get("$ref")
        if isinstance(reference, str) and not reference.startswith("#/"):
            found.add(reference)
        for child in value.values():
            found.update(external_references(child))
    elif isinstance(value, list):
        for child in value:
            found.update(external_references(child))
    return found


def request_schemas(document: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    content = operation.get("requestBody", {}).get("content", {})
    return {
        media_type: resolve_schema(document, media.get("schema", {}))
        for media_type, media in content.items() if isinstance(media, dict)
    } if isinstance(content, dict) else {}


def response_schemas(document: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for code, response in operation.get("responses", {}).items():
        content = response.get("content", {}) if isinstance(response, dict) else {}
        result[str(code)] = {
            media_type: resolve_schema(document, media.get("schema", {}))
            for media_type, media in content.items() if isinstance(media, dict)
        } if isinstance(content, dict) else {}
    return result


def effective_security(document: dict[str, Any], operation: dict[str, Any]) -> list[Any]:
    value = operation["security"] if "security" in operation else document.get("security", [])
    return value if isinstance(value, list) else []


def security_state(document: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    requirements = effective_security(document, operation)
    names = {name for item in requirements if isinstance(item, dict) for name in item}
    definitions = document.get("components", {}).get("securitySchemes", {})
    return {
        "requirements": requirements,
        "schemes": {name: definitions.get(name) for name in sorted(names)} if isinstance(definitions, dict) else {},
    }


def change(level: str, code: str, location: str, before: Any, after: Any, impact: str, recommendation: str) -> dict[str, Any]:
    return {
        "level": level, "code": code, "location": location,
        "before": before, "after": after, "impact": impact, "recommendation": recommendation,
    }


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
    old_required_value, new_required_value = old.get("required", []), new.get("required", [])
    old_required = set(old_required_value) if isinstance(old_required_value, list) else set()
    new_required = set(new_required_value) if isinstance(new_required_value, list) else set()
    if request and new_required - old_required:
        return True
    if not request and old_required - new_required:
        return True
    handled = {"type", "enum", "properties", "required"}
    for key in set(old) & set(new) - handled:
        if schema_breaks(old[key], new[key], request):
            return True
    return False


def compare_openapi(baseline: dict[str, Any], proposed: dict[str, Any], contract_id: str) -> dict[str, Any]:
    before = operation_map(baseline)
    after = operation_map(proposed)
    changes: list[dict[str, Any]] = []
    for reference in sorted(external_references(baseline) | external_references(proposed)):
        changes.append(change("UNKNOWN", "EXTERNAL_REF_UNRESOLVED", reference, reference, reference,
                              "External schema content cannot be verified from current evidence.",
                              "Provide a local immutable schema or record the external artifact as evidence."))
    for operation_id in sorted(set(before) - set(after)):
        path, method, _ = before[operation_id]
        changes.append(change("BREAKING", "OPERATION_REMOVED", operation_id, f"{method.upper()} {path}", None,
                              "Existing clients lose an operation.", "Keep it or introduce a versioned replacement."))
    for operation_id in sorted(set(after) - set(before)):
        path, method, _ = after[operation_id]
        changes.append(change("NON_BREAKING", "OPERATION_ADDED", operation_id, None, f"{method.upper()} {path}",
                              "Existing clients can continue unchanged.", "Add tests for the new operation."))
    for operation_id in sorted(set(before) & set(after)):
        old_path, old_method, old = before[operation_id]
        new_path, new_method, new = after[operation_id]
        if (old_path, old_method) != (new_path, new_method):
            changes.append(change("BREAKING", "ENDPOINT_CHANGED", operation_id,
                                  f"{old_method.upper()} {old_path}", f"{new_method.upper()} {new_path}",
                                  "Existing calls no longer reach the same endpoint.", "Keep the endpoint or create a new version."))
        old_parameters = parameter_map(baseline, old_path, old)
        new_parameters = parameter_map(proposed, new_path, new)
        removed_parameters = set(old_parameters) - set(new_parameters)
        if removed_parameters:
            changes.append(change("BREAKING", "PARAMETER_REMOVED", operation_id, sorted(removed_parameters), [],
                                  "Existing clients may send parameters that are no longer accepted.", "Keep the parameter or version the API."))
        added_required = {
            key for key in set(new_parameters) - set(old_parameters) if new_parameters[key].get("required") is True
        }
        if added_required:
            changes.append(change("BREAKING", "REQUIRED_PARAMETER_ADDED", operation_id, [], sorted(added_required),
                                  "Existing requests may be rejected.", "Make the parameter optional or version the API."))
        for parameter in sorted(set(old_parameters) & set(new_parameters)):
            if old_parameters[parameter] != new_parameters[parameter]:
                newly_required = old_parameters[parameter].get("required") is not True and new_parameters[parameter].get("required") is True
                level = "BREAKING" if newly_required or schema_breaks(old_parameters[parameter], new_parameters[parameter], True) else "REVIEW"
                changes.append(change(level, "PARAMETER_CHANGED", f"{operation_id}:{parameter[0]}:{parameter[1]}",
                                      old_parameters[parameter], new_parameters[parameter], "Parameter compatibility may change.",
                                      "Preserve the existing parameter contract or version the API."))
        removed_responses = set(old.get("responses", {})) - set(new.get("responses", {}))
        if removed_responses:
            changes.append(change("BREAKING", "RESPONSE_REMOVED", operation_id, sorted(removed_responses), [],
                                  "Clients can no longer handle the documented response contract.", "Keep existing responses or version the API."))
        old_body, new_body = old.get("requestBody", {}), new.get("requestBody", {})
        if old_body.get("required") is not True and new_body.get("required") is True:
            changes.append(change("BREAKING", "REQUEST_BODY_REQUIRED", operation_id, False, True,
                                  "Existing calls without a body will fail.", "Keep the body optional or version the API."))
        old_request_media = set(old_body.get("content", {})) if isinstance(old_body.get("content", {}), dict) else set()
        new_request_media = set(new_body.get("content", {})) if isinstance(new_body.get("content", {}), dict) else set()
        if old_request_media - new_request_media:
            changes.append(change("BREAKING", "REQUEST_CONTENT_TYPE_REMOVED", operation_id,
                                  sorted(old_request_media), sorted(new_request_media), "Some existing request formats are no longer accepted.",
                                  "Keep existing content types or version the API."))
        old_security, new_security = security_state(baseline, old), security_state(proposed, new)
        old_requirements, new_requirements = old_security["requirements"], new_security["requirements"]
        if old_security != new_security:
            if old_requirements and not new_requirements:
                level, code, impact = "SECURITY", "SECURITY_REMOVED", "The operation becomes public or less protected."
            elif not old_requirements and new_requirements:
                level, code, impact = "BREAKING", "SECURITY_REQUIRED", "Existing unauthenticated clients will fail."
            else:
                old_scopes = {name: set(scopes) for item in old_requirements if isinstance(item, dict) for name, scopes in item.items()}
                new_scopes = {name: set(scopes) for item in new_requirements if isinstance(item, dict) for name, scopes in item.items()}
                strengthened = any(new_scopes.get(name, set()) - old_scopes.get(name, set()) for name in new_scopes)
                level, code = ("BREAKING", "SECURITY_SCOPE_ADDED") if strengthened else ("SECURITY", "SECURITY_CHANGED")
                impact = "Authentication scheme or required scopes change."
            changes.append(change(level, code, operation_id, old_security, new_security, impact,
                                  "Review authorization explicitly; do not accept it as a schema-only change."))
        old_requests, new_requests = request_schemas(baseline, old), request_schemas(proposed, new)
        if old_requests != new_requests:
            level = "BREAKING" if schema_breaks(old_requests, new_requests, True) else "REVIEW"
            changes.append(change(level, "REQUEST_SCHEMA_CHANGED", operation_id, old_requests, new_requests,
                                  "Request compatibility may change.", "Keep old accepted inputs or document why the change is safe."))
        old_responses, new_responses = response_schemas(baseline, old), response_schemas(proposed, new)
        for code in sorted(set(old_responses) & set(new_responses)):
            removed_media = set(old_responses[code]) - set(new_responses[code])
            if removed_media:
                changes.append(change("BREAKING", "RESPONSE_CONTENT_TYPE_REMOVED", f"{operation_id}:{code}",
                                      sorted(old_responses[code]), sorted(new_responses[code]),
                                      "Clients lose a documented response format.", "Keep the content type or version the API."))
            if old_responses[code] != new_responses[code]:
                level = "BREAKING" if schema_breaks(old_responses[code], new_responses[code], False) else "REVIEW"
                changes.append(change(level, "RESPONSE_SCHEMA_CHANGED", f"{operation_id}:{code}",
                                      old_responses[code], new_responses[code], "Client response handling may change.",
                                      "Preserve existing fields and types or version the response."))
            old_response = old.get("responses", {}).get(code, {})
            new_response = new.get("responses", {}).get(code, {})
            old_headers = old_response.get("headers", {}) if isinstance(old_response, dict) else {}
            new_headers = new_response.get("headers", {}) if isinstance(new_response, dict) else {}
            removed_headers = set(old_headers) - set(new_headers)
            if removed_headers:
                changes.append(change("BREAKING", "RESPONSE_HEADER_REMOVED", f"{operation_id}:{code}",
                                      sorted(removed_headers), [], "Clients may depend on a removed response header.",
                                      "Keep the response header or version the API."))
    return {
        "reportVersion": 1, "contractId": contract_id,
        "baselineSha256": hashlib.sha256(encoded(baseline)).hexdigest(),
        "proposedSha256": hashlib.sha256(encoded(proposed)).hexdigest(),
        "summary": {
            "reused": len(set(before) & set(after)), "added": len(set(after) - set(before)),
            "removed": len(set(before) - set(after)),
            "breaking": sum(item["level"] == "BREAKING" for item in changes),
            "security": sum(item["level"] == "SECURITY" for item in changes),
            "unknown": sum(item["level"] == "UNKNOWN" for item in changes),
            "review": sum(item["level"] == "REVIEW" for item in changes),
        },
        "changes": changes,
    }


@dataclass(frozen=True)
class ControllerMappings:
    mappings: set[tuple[str, str]]
    unknowns: tuple[str, ...]


def normalize_path(value: str) -> str:
    if not value or value == "/":
        return ""
    return "/" + value.strip("/")


def join_path(base: str, child: str) -> str:
    combined = normalize_path(base) + normalize_path(child)
    return combined or "/"


def annotation_paths(arguments: str | None) -> tuple[list[str], bool]:
    if not arguments:
        return [""], False
    paths = QUOTED.findall(arguments)
    content = arguments[1:-1].strip()
    unresolved = bool(content and not paths)
    return (paths or [""]), unresolved


def controller_mappings(path: Path) -> ControllerMappings:
    source = path.read_text(encoding="utf-8")
    class_matches = list(CLASS_DECLARATION.finditer(source))
    class_match = class_matches[0] if class_matches else None
    class_position = class_match.start() if class_match else len(source)
    annotations = list(ANNOTATION.finditer(source))
    class_annotation = next((
        item for item in reversed(annotations)
        if item.start() < class_position and item.group(1) == "RequestMapping" and "RequestMethod." not in (item.group(2) or "")
    ), None)
    bases, base_unknown = annotation_paths(class_annotation.group(2) if class_annotation else None)
    mappings: set[tuple[str, str]] = set()
    unknowns: list[str] = []
    if len(class_matches) > 1:
        return ControllerMappings(set(), ("multiple class or interface boundaries cannot be resolved safely",))
    if base_unknown:
        return ControllerMappings(set(), ("class-level RequestMapping uses a non-literal path",))
    method_names = {"GetMapping": "get", "PostMapping": "post", "PutMapping": "put", "DeleteMapping": "delete", "PatchMapping": "patch"}
    for annotation in annotations:
        if annotation is class_annotation or annotation.start() < class_position:
            continue
        name, arguments = annotation.group(1), annotation.group(2)
        paths, unresolved = annotation_paths(arguments)
        if name == "RequestMapping":
            methods = [item.lower() for item in re.findall(r"RequestMethod\.(GET|POST|PUT|DELETE|PATCH)", arguments or "")]
            if not methods:
                unknowns.append("method RequestMapping has no literal HTTP method")
                continue
        else:
            methods = [method_names[name]]
        if unresolved:
            unknowns.append(f"{name} uses a non-literal path")
            continue
        for method in methods:
            for base in bases:
                for child in paths:
                    mappings.add((method, join_path(base, child)))
    known_names = {"GetMapping", "PostMapping", "PutMapping", "DeleteMapping", "PatchMapping", "RequestMapping"}
    for custom in CUSTOM_MAPPING.findall(source):
        if custom not in known_names:
            unknowns.append(f"custom mapping annotation cannot be resolved: {custom}")
    return ControllerMappings(mappings, tuple(dict.fromkeys(unknowns)))


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
    selected = metadata.get("selectedOperations")
    if not isinstance(selected, list) or not selected or not all(isinstance(item, str) and item for item in selected):
        raise ValueError("selectedOperations must be a non-empty string array")
    if len(selected) != len(set(selected)):
        raise ValueError("selectedOperations must be unique")
    trace_subjects = {item.get("subjectRef") for item in metadata["traceability"] if isinstance(item, dict)}
    if trace_subjects != set(selected):
        blockers.append("traceability must cover exactly the selected operations")
    decorated = decorated_for_feature(proposed, metadata["traceability"])
    validation_metadata = copy.deepcopy(metadata)
    validation_metadata["traceability"] = [
        {"subjectRef": op["operationId"], "requirementRefs": op.get("x-harness-requirement-refs", [])}
        for _, _, op in operations(decorated) if op["operationId"] in set(selected)
    ]
    blockers.extend(validate_openapi(decorated, feature, profile, validation_metadata, set(selected)))
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
        controller_results = [controller_mappings(inside(root, path, "controller evidence")) for path in controller_paths]
        observed = set().union(*(item.mappings for item in controller_results))
        unknown_mapping_reasons = [reason for item in controller_results for reason in item.unknowns]
        for path, method, operation in operations(baseline):
            if operation["operationId"] not in set(selected):
                continue
            normalized_openapi_path = normalize_path(path) or "/"
            if (method, normalized_openapi_path) in observed:
                continue
            if unknown_mapping_reasons:
                blockers.append(f"controller mapping is UNKNOWN for operation: {operation['operationId']}")
            else:
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
    if report["summary"].get("security"):
        blockers.append("EXTEND contains a security regression or unresolved security change")
    if report["summary"].get("unknown"):
        blockers.append("API compatibility is UNKNOWN because external references cannot be verified")
    review_ids = {f"{item['code']}:{item['location']}" for item in report["changes"] if item["level"] == "REVIEW"}
    reviews = metadata.get("compatibilityReviews")
    if not isinstance(reviews, list):
        raise ValueError("compatibilityReviews must be an array")
    review_records: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(reviews):
        if not isinstance(item, dict) or set(item) != {"reviewId", "status", "reason", "source", "confirmedByUser"}:
            raise ValueError(f"compatibilityReviews[{index}] has invalid fields")
        review_id = text(item["reviewId"], f"compatibilityReviews[{index}].reviewId", False)
        if review_id in review_records:
            raise ValueError("compatibilityReviews contains duplicate reviewId")
        if item["status"] not in {"PENDING", "ACCEPTED"} or item["source"] not in SOURCES or not isinstance(item["confirmedByUser"], bool):
            raise ValueError(f"compatibilityReviews[{index}] has invalid decision values")
        text(item["reason"], f"compatibilityReviews[{index}].reason")
        if item["status"] == "ACCEPTED" and (
            item["reason"] == "UNKNOWN" or item["source"] == "UNKNOWN" or not item["confirmedByUser"]
        ):
            blockers.append(f"accepted compatibility review lacks user-confirmed reason: {review_id}")
        review_records[review_id] = item
    if set(review_records) - review_ids:
        blockers.append("accepted compatibility review does not exist in current report")
    if review_ids - set(review_records):
        blockers.append("compatibility report reviews are missing decision records")
    pending = {review_id for review_id, item in review_records.items() if item["status"] != "ACCEPTED"}
    if disposition == "EXTEND" and pending:
        blockers.append("EXTEND has unresolved compatibility reviews")
    return approved, blockers, proposed, report
