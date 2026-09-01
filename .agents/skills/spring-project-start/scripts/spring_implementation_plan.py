#!/usr/bin/env python3
"""Build and validate a CREATE-only Spring implementation component plan."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path, PurePosixPath

from validate_feature_specs import approval_content_hash, load_object, validate_approval


ID = re.compile(r"^[a-z][a-z0-9-]*$"); PACKAGE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
COMPONENT_KINDS = {"REQUEST_DTO", "RESPONSE_DTO", "JPA_ENTITY", "REPOSITORY", "APPLICATION_SERVICE", "CONTROLLER", "EXCEPTION_HANDLER", "UNIT_TEST", "REPOSITORY_INTEGRATION_TEST", "API_INTEGRATION_TEST"}
DISPOSITIONS = {"CREATE", "REUSE", "REUSE_CANDIDATE", "CONFLICT", "DEFER"}
CONFLICT_CODES = {"PATH_OCCUPIED", "SOURCE_DRIFT", "CONTRACT_COLLISION", "STRUCTURE_AMBIGUOUS", "UNSUPPORTED_STACK", "DIRTY_OVERLAP", "MISSING_CONTRACT", "TRACEABILITY_GAP", "DEPENDENCY_CYCLE", "ENTITY_API_EXPOSURE", "TRANSACTION_UNRESOLVED"}


def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path: Path, root: Path) -> dict:
    resolved = path.resolve(strict=True)
    if path.is_symlink() or root not in resolved.parents or not resolved.is_file(): raise ValueError("implementation input must be a target-owned regular file")
    return {"path": resolved.relative_to(root).as_posix(), "sha256": sha(resolved)}


def options(profile: dict) -> set[str]:
    result = set()
    def walk(value):
        if isinstance(value, dict):
            if isinstance(value.get("option"), str): result.add(value["option"])
            for item in value.values(): walk(item)
        elif isinstance(value, list):
            for item in value: walk(item)
    walk(profile.get("decisions", {})); return result


def pascal(value: str) -> str: return "".join(part[:1].upper() + part[1:] for part in re.split(r"[^A-Za-z0-9]+", value) if part)
def kebab(value: str) -> str: return re.sub(r"[^a-z0-9]+", "-", re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", value).lower()).strip("-")


def source_path(package: str, layer: str, name: str, test: bool = False) -> str:
    root = "src/test/java" if test else "src/main/java"
    return f"{root}/{package.replace('.', '/')}/{layer}/{name}.java"


def dirty_paths(root: Path) -> set[str]:
    result = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root, capture_output=True, text=True, check=False)
    if result.returncode: return set()
    return {line[3:].split(" -> ")[-1] for line in result.stdout.splitlines() if len(line) > 3}


def build(feature: dict, profile: dict, route: dict, openapi: dict, physical: dict | None, migration_report: dict | None, root: Path, package: str, input_refs: dict) -> dict:
    feature_id = feature["feature"]["id"]; operations = [(path, method, operation) for path, item in openapi.get("paths", {}).items() for method, operation in item.items() if method.lower() == "post" and isinstance(operation, dict)]
    conflicts = []
    selected = options(profile); required = {"language.java", "application.rest-api"}; supported_build = selected & {"build.gradle-kotlin", "build.gradle-groovy", "build.maven"}
    if physical is not None: required |= {"persistence.jpa", "database.postgresql"}
    missing = sorted(required - selected)
    if missing or not supported_build: conflicts.append({"code": "UNSUPPORTED_STACK", "severity": "BLOCKING", "subject": "technology-profile", "message": "첫 구현 계획 지원 범위를 벗어난 기술 조합입니다.", "recommendedActions": ["지원 프로필로 조정", "직접 구현 계획으로 보류"], "evidencePaths": [input_refs["technologyProfile"]["path"]]})
    if len(operations) != 1: conflicts.append({"code": "MISSING_CONTRACT" if not operations else "STRUCTURE_AMBIGUOUS", "severity": "BLOCKING", "subject": "HTTP POST CREATE", "message": "첫 마일스톤은 POST operation 하나가 필요합니다.", "recommendedActions": ["기능 slice를 POST 하나로 축소"], "evidencePaths": [input_refs["openApi"]["path"]]})
    path, _, operation = operations[0] if operations else ("UNKNOWN", "post", {"operationId": "unknown", "responses": {}})
    operation_id = operation.get("operationId", "unknown"); base = pascal(operation_id); stem = kebab(operation_id); main_package = package + ".feature." + stem.replace("-", "")
    definitions = [
        ("request", "REQUEST_DTO", "api", f"{base}Request", []), ("response", "RESPONSE_DTO", "api", f"{base}Response", []),
        ("entity", "JPA_ENTITY", "persistence", f"{base}Entity", []), ("repository", "REPOSITORY", "persistence", f"{base}Repository", [f"{stem}-entity"]),
        ("service", "APPLICATION_SERVICE", "application", f"{base}Service", [f"{stem}-repository", f"{stem}-request", f"{stem}-response"]),
        ("controller", "CONTROLLER", "api", f"{base}Controller", [f"{stem}-service", f"{stem}-request", f"{stem}-response"]),
        ("error-handler", "EXCEPTION_HANDLER", "api", f"{base}ExceptionHandler", []),
        ("service-test", "UNIT_TEST", "application", f"{base}ServiceTest", [f"{stem}-service"]),
        ("repository-test", "REPOSITORY_INTEGRATION_TEST", "persistence", f"{base}RepositoryTest", [f"{stem}-repository"]),
        ("api-test", "API_INTEGRATION_TEST", "api", f"{base}ApiTest", [f"{stem}-controller"]),
    ]
    dirty = dirty_paths(root); components = []
    for suffix, kind, layer, type_name, dependencies in definitions:
        component_id = f"{stem}-{suffix}"; planned = source_path(main_package, layer, type_name, kind.endswith("TEST"))
        occupied = (root / planned).exists(); disposition = "CONFLICT" if occupied else "CREATE"
        component = {"componentId": component_id, "kind": kind, "disposition": disposition, "target": {"modulePath": ".", "packageName": f"{main_package}.{layer}", "plannedPath": planned, "typeName": type_name}, "responsibilities": [f"{operation_id} 기능의 {kind.lower()} 책임"], "publicContract": {"operationRefs": [f"openapi:{operation_id}"] if kind in {"CONTROLLER", "APPLICATION_SERVICE"} else [], "inputTypeRefs": [f"{stem}-request"] if kind in {"CONTROLLER", "APPLICATION_SERVICE"} else [], "outputTypeRefs": [f"{stem}-response"] if kind in {"CONTROLLER", "APPLICATION_SERVICE"} else []}, "transaction": {"required": kind == "APPLICATION_SERVICE" and physical is not None, "readOnly": False, "reason": "CREATE 저장 경계" if kind == "APPLICATION_SERVICE" and physical is not None else "transaction 소유 component 아님"}, "dependsOn": dependencies, "requirementRefs": list(operation.get("x-harness-requirement-refs", [])), "contractRefs": [f"openapi:{operation_id}"]}
        components.append(component)
        if occupied: conflicts.append({"code": "DIRTY_OVERLAP" if planned in dirty else "PATH_OCCUPIED", "severity": "BLOCKING", "subject": planned, "message": "생성 예정 경로에 사용자 소유 파일이 있습니다. 자동 수정하지 않습니다.", "recommendedActions": ["기존 구조 확장 분석", "다른 package 선택", "기능 보류"], "evidencePaths": [planned]})
    responses = operation.get("responses", {}); error_mappings = [{"errorId": f"http-{code}", "source": "BEAN_VALIDATION" if code == "400" else "SECURITY" if code in {"401", "403"} else "BUSINESS_RULE", "httpStatus": int(code), "responseRef": f"openapi:{operation_id}:response:{code}", "handlerComponentRef": f"{stem}-error-handler"} for code in responses if str(code).isdigit() and int(code) >= 400]
    requirements = [item["id"] for item in feature.get("acceptanceCriteria", [])] + [item["id"] for item in feature.get("businessRules", [])]
    coverage = [{"requirementRef": requirement, "enforcedBy": [{"kind": "IMPLEMENTATION", "componentRef": f"{stem}-service"}], "verifiedBy": [{"kind": "AUTOMATED_TEST", "componentRef": f"{stem}-api-test"}]} for requirement in requirements]
    operation_refs = set(operation.get("x-harness-requirement-refs", [])); uncovered = sorted(set(requirements) - operation_refs)
    for requirement in uncovered: conflicts.append({"code": "TRACEABILITY_GAP", "severity": "BLOCKING", "subject": requirement, "message": "OpenAPI operation이 요구사항을 추적하지 않습니다.", "recommendedActions": ["API contract traceability 보완"], "evidencePaths": [input_refs["openApi"]["path"]]})
    blocking = any(item["severity"] == "BLOCKING" for item in conflicts); create_count = sum(item["disposition"] == "CREATE" for item in components)
    routes = route.get("routes", [])
    if not routes:
        raise ValueError("design route has no active route")
    return {"implementationPlanVersion": 1, "planId": f"{feature_id.lower()}-{stem}-implementation", "featureId": feature_id, "target": {"path": str(root), "projectId": routes[0]["target"]["projectId"], "modulePath": ".", "packageName": package, "language": "JAVA", "architecture": "LAYERED"}, "inputs": input_refs, "capability": {"status": "UNSUPPORTED" if missing or not supported_build else "SUPPORTED", "reasons": ["첫 마일스톤: Java + REST + 단일 모듈" + (" + JPA + PostgreSQL" if physical is not None else "")]}, "userFlow": {"name": feature["feature"]["name"], "trigger": feature["scenario"]["trigger"], "steps": feature["scenario"]["mainFlow"], "outcome": feature["scenario"]["postconditions"][0]}, "components": components, "errorMappings": error_mappings, "coverage": coverage, "conflicts": conflicts, "summary": {"create": create_count, "reuse": 0, "defer": 0, "conflict": len(components) - create_count, "automatedTests": sum(item["kind"].endswith("TEST") for item in components)}, "status": "BLOCKED" if blocking else "REVIEW_READY", "approval": {"status": "DRAFT", "approvedBy": None, "approvedAt": None, "approvedContentSha256": None}}


def validate(plan: dict, root: Path, verify_evidence: bool = True) -> list[str]:
    required = {"implementationPlanVersion", "planId", "featureId", "target", "inputs", "capability", "userFlow", "components", "errorMappings", "coverage", "conflicts", "summary", "status", "approval"}; blockers = []
    if not isinstance(plan, dict) or set(plan) != required or plan.get("implementationPlanVersion") != 1: raise ValueError("implementation plan is invalid")
    if plan["status"] not in {"BLOCKED", "REVIEW_READY", "APPROVED"}: raise ValueError("implementation plan status is invalid")
    if not ID.fullmatch(plan["planId"]): raise ValueError("planId must be kebab-case")
    if Path(plan["target"]["path"]).resolve() != root.resolve() or plan["target"]["language"] != "JAVA" or plan["target"]["architecture"] != "LAYERED" or not PACKAGE.fullmatch(plan["target"]["packageName"]): raise ValueError("implementation target is invalid")
    inputs = plan["inputs"]
    if set(inputs) != {"featureSpec", "technologyProfile", "designRoute", "httpApiContract", "openApi", "physicalContract", "physicalModel", "migrationVerification"}: raise ValueError("implementation inputs are invalid")
    if verify_evidence:
        for name, item in inputs.items():
            if not isinstance(item, dict) or set(item) != {"path", "sha256"}: raise ValueError(f"implementation input reference is invalid: {name}")
            path = root / item["path"]
            pure = PurePosixPath(item["path"])
            if pure.is_absolute() or ".." in pure.parts or path.is_symlink() or not path.is_file() or sha(path) != item["sha256"]: blockers.append(f"input changed: {name}")
    component_ids = set(); paths = set(); graph = {}
    entity_ids = {item["componentId"] for item in plan["components"] if item.get("kind") == "JPA_ENTITY"}
    for component in plan["components"]:
        keys = {"componentId", "kind", "disposition", "target", "responsibilities", "publicContract", "transaction", "dependsOn", "requirementRefs", "contractRefs"}
        if not isinstance(component, dict) or set(component) != keys or component["kind"] not in COMPONENT_KINDS or component["disposition"] not in DISPOSITIONS: raise ValueError("implementation component is invalid")
        identity = component["componentId"]; path = component["target"]["plannedPath"]
        if identity in component_ids or path in paths: raise ValueError("component IDs and paths must be unique")
        component_ids.add(identity); paths.add(path); graph[identity] = component["dependsOn"]
        pure = PurePosixPath(path)
        if pure.is_absolute() or ".." in pure.parts: raise ValueError("component path is unsafe")
        if component["kind"] == "JPA_ENTITY" and any("response" in ref or "request" in ref for ref in component["dependsOn"]): blockers.append("JPA entity must not depend on API DTOs")
        if component["kind"] in {"CONTROLLER", "REQUEST_DTO", "RESPONSE_DTO"}:
            exposed = set(component["publicContract"]["inputTypeRefs"] + component["publicContract"]["outputTypeRefs"])
            if exposed & entity_ids: blockers.append("JPA entity must not be exposed by the API boundary")
        if component["kind"] == "APPLICATION_SERVICE" and component["transaction"]["required"] and component["transaction"]["readOnly"]: blockers.append("CREATE service transaction cannot be read-only")
    if any(set(deps) - component_ids for deps in graph.values()): blockers.append("component dependency references are unresolved")
    visiting = set(); visited = set()
    def visit(node):
        if node in visiting: return True
        if node in visited: return False
        visiting.add(node)
        if any(visit(dep) for dep in graph.get(node, [])): return True
        visiting.remove(node); visited.add(node); return False
    if any(visit(node) for node in graph): blockers.append("component dependency cycle exists")
    write_transactions = [item for item in plan["components"] if item["transaction"]["required"] and not item["transaction"]["readOnly"]]
    if len(write_transactions) != 1 or write_transactions[0]["kind"] != "APPLICATION_SERVICE": blockers.append("CREATE plan needs exactly one service-owned write transaction")
    for conflict in plan["conflicts"]:
        if not isinstance(conflict, dict) or set(conflict) != {"code", "severity", "subject", "message", "recommendedActions", "evidencePaths"} or conflict["code"] not in CONFLICT_CODES: raise ValueError("implementation conflict is invalid")
        if conflict["severity"] == "BLOCKING": blockers.append(f"{conflict['code']}: {conflict['subject']}")
    requirement_refs = {item["requirementRef"] for item in plan["coverage"]}
    for item in plan["coverage"]:
        references = {entry["componentRef"] for entry in item["enforcedBy"] + item["verifiedBy"]}
        if references - component_ids: blockers.append(f"coverage references are unresolved: {item['requirementRef']}")
    if any(not item["enforcedBy"] or not item["verifiedBy"] for item in plan["coverage"]): blockers.append("requirement coverage is incomplete")
    if not requirement_refs: blockers.append("requirement coverage is empty")
    expected_summary = {
        "create": sum(item["disposition"] == "CREATE" for item in plan["components"]),
        "reuse": sum(item["disposition"] in {"REUSE", "REUSE_CANDIDATE"} for item in plan["components"]),
        "defer": sum(item["disposition"] == "DEFER" for item in plan["components"]),
        "conflict": sum(item["disposition"] == "CONFLICT" for item in plan["components"]),
        "automatedTests": sum(item["kind"].endswith("TEST") for item in plan["components"]),
    }
    if plan["summary"] != expected_summary: raise ValueError("implementation summary does not match components")
    approved = validate_approval(plan["approval"], "approval", plan)
    if plan["status"] == "APPROVED" and not approved: blockers.append("approved status lacks exact approval")
    if plan["status"] == "REVIEW_READY" and blockers: blockers.append("REVIEW_READY plan has blockers")
    return blockers
