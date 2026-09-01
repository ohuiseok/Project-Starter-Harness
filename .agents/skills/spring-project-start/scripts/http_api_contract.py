#!/usr/bin/env python3
"""Shared validation and rendering support for HTTP API design contracts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from validate_design_contract import inside, validate as validate_metadata
from validate_feature_specs import SENSITIVE_KEYS, SENSITIVE_VALUES, load_object, text


METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
STATUS = re.compile(r"^[1-5](?:\d\d|XX)$")
SUPPORTED_OPENAPI = re.compile(r"^3\.(?:0|1)\.\d+$")


def reject_openapi_secrets(value: Any, sensitive_parent: bool = False, location: str = "openapi") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            sensitive_key = bool(SENSITIVE_KEYS.search(str(key)))
            if sensitive_key and isinstance(child, (str, int, float, bool)):
                raise ValueError(f"{location}.{key}: secret-bearing value is not allowed")
            if sensitive_parent and key in {"example", "default", "value"} and isinstance(child, str):
                raise ValueError(f"{location}.{key}: sensitive example value is not allowed")
            reject_openapi_secrets(child, sensitive_key, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_openapi_secrets(child, sensitive_parent, f"{location}[{index}]")
    elif isinstance(value, str) and SENSITIVE_VALUES.search(value):
        raise ValueError(f"{location}: secret-like value is not allowed")


def security_option(profile: dict[str, Any]) -> str:
    decision = profile.get("decisions", {}).get("security", {})
    return decision.get("option", "UNKNOWN") if isinstance(decision, dict) else "UNKNOWN"


def operations(document: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    result: list[tuple[str, str, dict[str, Any]]] = []
    for path, path_item in document.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method in METHODS and isinstance(operation, dict):
                result.append((path, method, operation))
    return result


def resolve_local_ref(
    document: dict[str, Any], value: Any, location: str, stack: tuple[str, ...] = (),
) -> Any:
    """Resolve one local OpenAPI component reference for semantic validation."""
    if not isinstance(value, dict) or "$ref" not in value:
        return value
    reference = text(value["$ref"], f"{location}.$ref", False)
    if not reference.startswith("#/"):
        return value
    if reference in stack:
        raise ValueError(f"{location} contains a cyclic local OpenAPI reference: {reference}")
    current: Any = document
    for raw in reference[2:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or token not in current:
            raise ValueError(f"{location} has an unresolved local OpenAPI reference: {reference}")
        current = current[token]
    if not isinstance(current, dict):
        raise ValueError(f"{location} local OpenAPI reference must resolve to an object: {reference}")
    resolved = resolve_local_ref(document, current, location, stack + (reference,))
    siblings = {key: child for key, child in value.items() if key != "$ref"}
    return {**resolved, **siblings} if siblings else resolved


def derived_traceability(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "subjectRef": operation["operationId"],
            "requirementRefs": operation.get("x-harness-requirement-refs", []),
        }
        for _, _, operation in operations(document)
        if isinstance(operation.get("operationId"), str)
    ]


def validate_openapi(
    document: dict[str, Any], feature: dict[str, Any], profile: dict[str, Any], metadata: dict[str, Any],
    selected_operation_ids: set[str] | None = None,
) -> list[str]:
    reject_openapi_secrets(document)
    version = text(document.get("openapi"), "openapi", False)
    if not SUPPORTED_OPENAPI.fullmatch(version):
        raise ValueError("openapi must be a supported 3.0.x or 3.1.x version")
    info = document.get("info")
    if not isinstance(info, dict):
        raise ValueError("info must be an object")
    text(info.get("title"), "info.title", False)
    text(info.get("version"), "info.version", False)
    paths = document.get("paths")
    if not isinstance(paths, dict) or not paths:
        raise ValueError("paths must be a non-empty object")
    blockers: list[str] = []
    seen_ids: set[str] = set()
    available_refs = {
        item["id"] for item in feature.get("acceptanceCriteria", []) + feature.get("businessRules", [])
    }
    acceptance_refs = {item["id"] for item in feature.get("acceptanceCriteria", [])}
    business_refs = {item["id"] for item in feature.get("businessRules", [])}
    covered_acceptance: set[str] = set()
    covered_business: set[str] = set()
    has_error_response = False
    secured_operations = 0
    document_operations = operations(document)
    if not document_operations:
        raise ValueError("paths must contain at least one HTTP operation")
    all_ids: list[str] = []
    for path, method, operation in document_operations:
        operation_id = text(operation.get("operationId"), f"paths.{path}.{method}.operationId", False)
        if operation_id in all_ids:
            raise ValueError(f"duplicate operationId: {operation_id}")
        all_ids.append(operation_id)
    if selected_operation_ids is not None:
        missing_selected = selected_operation_ids - set(all_ids)
        if missing_selected:
            blockers.append("selected operations are missing from OpenAPI: " + ", ".join(sorted(missing_selected)))
        all_operations = [item for item in document_operations if item[2]["operationId"] in selected_operation_ids]
        if not all_operations:
            blockers.append("no selected API operation can be validated")
    else:
        all_operations = document_operations
    global_security = document.get("security")
    schemes = document.get("components", {}).get("securitySchemes", {})
    if not isinstance(schemes, dict):
        raise ValueError("components.securitySchemes must be an object")
    for path, method, operation in all_operations:
        location = f"paths.{path}.{method}"
        if not path.startswith("/"):
            raise ValueError(f"OpenAPI path must start with '/': {path}")
        operation_id = text(operation.get("operationId"), f"{location}.operationId", False)
        seen_ids.add(operation_id)
        text(operation.get("summary"), f"{location}.summary", False)
        refs = operation.get("x-harness-requirement-refs")
        if not isinstance(refs, list) or not refs or not all(isinstance(ref, str) and ref for ref in refs):
            blockers.append(f"operation has no requirement traceability: {operation_id}")
            refs = []
        unknown_refs = set(refs) - available_refs
        if unknown_refs:
            blockers.append(f"operation references unknown feature requirements: {operation_id}")
        covered_acceptance.update(set(refs) & acceptance_refs)
        covered_business.update(set(refs) & business_refs)
        responses = operation.get("responses")
        if not isinstance(responses, dict) or not responses:
            raise ValueError(f"{location}.responses must be a non-empty object")
        if not any(str(code).startswith("2") for code in responses):
            blockers.append(f"operation has no success response: {operation_id}")
        for code, response_value in responses.items():
            if code != "default" and not STATUS.fullmatch(str(code)):
                raise ValueError(f"{location}.responses has invalid status code: {code}")
            response = resolve_local_ref(document, response_value, f"{location}.responses.{code}")
            if not isinstance(response, dict) or (
                "$ref" not in response and not isinstance(response.get("description"), str)
            ):
                raise ValueError(f"{location}.responses.{code} requires a description")
            for media_type, media in response.get("content", {}).items():
                if not isinstance(media, dict) or "schema" not in media:
                    raise ValueError(f"{location}.responses.{code}.content.{media_type} requires schema")
            if str(code).startswith("4") or str(code).startswith("5") or code == "default":
                has_error_response = True
        request_body = operation.get("requestBody")
        if request_body is not None:
            if not isinstance(request_body, dict):
                raise ValueError(f"{location}.requestBody must be an object")
            request_body = resolve_local_ref(document, request_body, f"{location}.requestBody")
            external_request_body = isinstance(request_body.get("$ref"), str) and not request_body["$ref"].startswith("#/")
            if not external_request_body and not isinstance(request_body.get("content"), dict):
                raise ValueError(f"{location}.requestBody requires content")
            for media_type, media in request_body.get("content", {}).items():
                if not isinstance(media, dict) or "schema" not in media:
                    raise ValueError(f"{location}.requestBody.content.{media_type} requires schema")
        effective_security = operation.get("security", global_security)
        if effective_security:
            secured_operations += 1
            if not isinstance(effective_security, list):
                raise ValueError(f"{location}.security must be an array")
            referenced_schemes = {
                name for requirement in effective_security if isinstance(requirement, dict) for name in requirement
            }
            if referenced_schemes - set(schemes):
                blockers.append(f"operation references an unknown security scheme: {operation_id}")
            if feature.get("authorization") and not {"401", "403"}.issubset({str(code) for code in responses}):
                blockers.append(f"authorized operation must describe both 401 and 403 responses: {operation_id}")
        placeholders = set(re.findall(r"\{([^{}]+)\}", path))
        parameters = []
        path_item = paths[path]
        for owner in (path_item, operation):
            if isinstance(owner.get("parameters"), list):
                parameters.extend(owner["parameters"])
        resolved_parameters = [
            resolve_local_ref(document, item, f"{location}.parameters") for item in parameters
        ]
        declared = {
            item.get("name") for item in resolved_parameters
            if isinstance(item, dict) and item.get("in") == "path" and item.get("required") is True
        }
        if placeholders != declared:
            blockers.append(f"path parameters do not match path template: {operation_id}")
    missing_acceptance = acceptance_refs - covered_acceptance
    if missing_acceptance:
        blockers.append("acceptance criteria are not covered by API operations: " + ", ".join(sorted(missing_acceptance)))
    missing_business = business_refs - covered_business
    if missing_business:
        blockers.append("business rules are not covered by API operations: " + ", ".join(sorted(missing_business)))
    if feature.get("failureCases") and not has_error_response:
        blockers.append("feature failure cases have no API error response")
    expected_security = security_option(profile)
    if expected_security == "security.none":
        if schemes or secured_operations:
            blockers.append("security.none profile cannot define secured API operations")
    elif expected_security in {"security.session", "security.token", "security.oidc", "security.mixed"}:
        if not schemes or not secured_operations:
            blockers.append(f"{expected_security} profile requires secured API operations")
        if expected_security == "security.session" and not any(
            item.get("type") == "apiKey" and item.get("in") == "cookie" for item in schemes.values()
            if isinstance(item, dict)
        ):
            blockers.append("session security requires a cookie apiKey security scheme")
        if expected_security == "security.token" and not any(
            item.get("type") == "http" and item.get("scheme", "").lower() == "bearer" for item in schemes.values()
            if isinstance(item, dict)
        ):
            blockers.append("token security requires an HTTP bearer security scheme")
        if expected_security == "security.oidc" and not any(
            item.get("type") in {"openIdConnect", "oauth2"} for item in schemes.values() if isinstance(item, dict)
        ):
            blockers.append("OIDC security requires an OpenID Connect or OAuth2 security scheme")
    else:
        blockers.append("technology profile security decision is unresolved")
    if feature.get("authorization") and secured_operations == 0:
        blockers.append("authorized feature has no secured API operation")
    expected_traceability = derived_traceability(document)
    if selected_operation_ids is not None:
        expected_traceability = [item for item in expected_traceability if item["subjectRef"] in selected_operation_ids]
    if metadata.get("traceability") != expected_traceability:
        blockers.append("contract traceability does not match OpenAPI operations")
    return blockers


def validate_http_contract(
    metadata: dict[str, Any], route: dict[str, Any], route_path: Path, target: Path,
    contract_path: Path, feature: dict[str, Any], profile: dict[str, Any],
) -> tuple[bool, list[str], dict[str, Any]]:
    approved, blockers = validate_metadata(metadata, route, route_path, target, contract_path)
    if metadata.get("kind") != "HTTP_API":
        blockers.append("HTTP API contract kind must be HTTP_API")
    if metadata.get("disposition") != "CREATE":
        blockers.append("this milestone supports HTTP_API CREATE only")
    if metadata.get("artifact", {}).get("format") != "OPENAPI":
        blockers.append("HTTP API contract artifact format must be OPENAPI")
    artifact_path = inside(target.resolve(), metadata["artifact"]["path"], "artifact.path")
    try:
        openapi = load_object(artifact_path)
    except OSError as error:
        raise ValueError(f"cannot read OpenAPI artifact: {error}") from error
    blockers.extend(validate_openapi(openapi, feature, profile, metadata))
    return approved, blockers, openapi


def encoded(document: dict[str, Any]) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode()
