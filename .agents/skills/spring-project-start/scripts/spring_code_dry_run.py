#!/usr/bin/env python3
"""Validate exact Java candidates against an approved implementation plan."""

from __future__ import annotations

import hashlib
import re
import tempfile
from pathlib import Path, PurePosixPath

from render_generation_dry_run import files_under, load_baseline
from spring_implementation_plan import validate as validate_plan
from validate_feature_specs import load_object


BASELINE = ".starter-harness-implementation.json"
MAX_FILE_BYTES = 1024 * 1024
PACKAGE = re.compile(r"(?m)^package\s+([a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*)\s*;")
PUBLIC_TYPE = re.compile(r"(?m)^public\s+(?:final\s+)?(?:class|interface|record|enum)\s+([A-Z][A-Za-z0-9]*)\b")
SECRET_LITERAL = re.compile(r'(?i)\b(password|secret|api[_-]?key|access[_-]?token)\b\s*=\s*"(?!\$\{)[^"\n]+"')
ASSERTION = re.compile(r"\b(?:assertThat|assertEquals|assertTrue|assertFalse|andExpect|verify)\s*\(")
REQUIRED_MARKERS = {
    "JPA_ENTITY": ("@Entity",),
    "REPOSITORY": ("JpaRepository",),
    "APPLICATION_SERVICE": ("@Service", "@Transactional"),
    "CONTROLLER": ("@RestController", "@PostMapping"),
    "EXCEPTION_HANDLER": ("@RestControllerAdvice", "@ExceptionHandler"),
    "UNIT_TEST": ("@Test",),
    "REPOSITORY_INTEGRATION_TEST": ("@DataJpaTest", "@Test"),
    "API_INTEGRATION_TEST": ("@SpringBootTest", "@Test"),
}


def camel(value: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", value)
    return parts[0].lower() + "".join(item[:1].upper() + item[1:] for item in parts[1:] if item)


def contract_expectations(plan: dict, target: Path) -> dict:
    openapi = load_object(target / plan["inputs"]["openApi"]["path"])
    physical = load_object(target / plan["inputs"]["physicalModel"]["path"])
    operations = [(path, operation) for path, item in openapi.get("paths", {}).items() for method, operation in item.items() if method.lower() == "post" and isinstance(operation, dict)]
    if len(operations) != 1 or len(physical.get("tables", [])) != 1:
        raise ValueError("first code dry-run needs one POST operation and one physical table")
    api_path, operation = operations[0]
    table = physical["tables"][0]
    columns = table.get("columns", [])
    if not columns:
        raise ValueError("physical model has no columns")
    primary_ids = set(table["primaryKey"]["columnIds"])
    fields = [camel(item["fieldRef"]) for item in columns]
    request_fields = [camel(item["fieldRef"]) for item in columns if item["columnId"] not in primary_ids]
    return {"apiPath": api_path, "table": table["name"], "columns": [item["name"] for item in columns], "fields": fields, "requestFields": request_fields}


def semantic_reasons(component: dict, content: str, expectations: dict, plan: dict) -> list[str]:
    kind = component["kind"]
    component_by_kind = {item["kind"]: item["target"]["typeName"] for item in plan["components"]}
    required: list[str] = []
    if kind == "REQUEST_DTO": required = expectations["requestFields"]
    elif kind == "RESPONSE_DTO": required = expectations["fields"]
    elif kind == "JPA_ENTITY": required = [f'@Table(name = "{expectations["table"]}")'] + [f'@Column(name = "{name}")' for name in expectations["columns"]] + ["@Id"]
    elif kind == "REPOSITORY": required = [component_by_kind["JPA_ENTITY"], "JpaRepository<"]
    elif kind == "APPLICATION_SERVICE": required = [component_by_kind["REPOSITORY"], component_by_kind["REQUEST_DTO"], component_by_kind["RESPONSE_DTO"], ".save("]
    elif kind == "CONTROLLER": required = [f'"{expectations["apiPath"]}"', component_by_kind["REQUEST_DTO"], component_by_kind["RESPONSE_DTO"], "ResponseEntity"]
    elif kind == "EXCEPTION_HANDLER": required = ["ResponseEntity"]
    missing = [item for item in required if item not in content]
    reasons = ["contract-semantics-missing:" + ",".join(missing)] if missing else []
    if kind.endswith("TEST") and not ASSERTION.search(content):
        reasons.append("test-has-no-executable-assertion")
    return reasons


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def target_file(root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or pure.suffix != ".java":
        raise ValueError(f"unsafe Java candidate path: {relative}")
    result = root.joinpath(*pure.parts)
    if root.resolve() not in result.resolve().parents:
        raise ValueError(f"Java candidate escapes rendered source: {relative}")
    return result


def validate_candidate(plan: dict, rendered: Path, target: Path | None = None) -> tuple[list[dict], list[dict]]:
    if rendered.is_symlink() or not rendered.is_dir():
        raise ValueError("rendered source must be a non-symlink directory")
    found = files_under(rendered)
    expected = {item["target"]["plannedPath"]: item for item in plan["components"]}
    conflicts: list[dict] = []
    checks: list[dict] = []
    for path in sorted(set(expected) - set(found)):
        conflicts.append({"path": path, "reason": "planned-component-is-missing"})
    for path in sorted(set(found) - set(expected)):
        conflicts.append({"path": path, "reason": "file-is-not-in-approved-plan"})
    entity_names = {item["target"]["typeName"] for item in plan["components"] if item["kind"] == "JPA_ENTITY"}
    coverage = {item["requirementRef"]: item for item in plan["coverage"]}
    expectations = contract_expectations(plan, target) if target is not None else None
    for relative in sorted(set(found) & set(expected)):
        component = expected[relative]
        path = target_file(rendered, relative)
        if path.stat().st_size > MAX_FILE_BYTES:
            conflicts.append({"path": relative, "reason": "candidate-file-exceeds-size-limit"})
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            conflicts.append({"path": relative, "reason": "candidate-is-not-utf8-text"})
            continue
        package = PACKAGE.search(content)
        public_type = PUBLIC_TYPE.search(content)
        identity_ok = bool(package and package.group(1) == component["target"]["packageName"] and public_type and public_type.group(1) == component["target"]["typeName"])
        checks.append({"check": "JAVA_IDENTITY", "componentRef": component["componentId"], "state": "PASSED" if identity_ok else "FAILED"})
        if not identity_ok:
            conflicts.append({"path": relative, "reason": "package-or-public-type-does-not-match-plan"})
        missing_markers = [marker for marker in REQUIRED_MARKERS.get(component["kind"], ()) if marker not in content]
        checks.append({"check": "SPRING_ROLE", "componentRef": component["componentId"], "state": "PASSED" if not missing_markers else "FAILED"})
        if missing_markers:
            conflicts.append({"path": relative, "reason": "missing-required-marker:" + ",".join(missing_markers)})
        if SECRET_LITERAL.search(content):
            conflicts.append({"path": relative, "reason": "hardcoded-secret-like-literal"})
        if expectations is not None:
            semantic = semantic_reasons(component, content, expectations, plan)
            checks.append({"check": "CONTRACT_SEMANTICS", "componentRef": component["componentId"], "state": "PASSED" if not semantic else "FAILED"})
            conflicts.extend({"path": relative, "reason": reason} for reason in semantic)
        if component["kind"] in {"CONTROLLER", "REQUEST_DTO", "RESPONSE_DTO"} and any(re.search(rf"\b{re.escape(name)}\b", content) for name in entity_names):
            conflicts.append({"path": relative, "reason": "jpa-entity-crosses-api-boundary"})
        if component["kind"].endswith("TEST"):
            required = [requirement for requirement, item in coverage.items() if any(entry["componentRef"] == component["componentId"] for entry in item["verifiedBy"])]
            missing = [requirement for requirement in required if requirement not in content]
            checks.append({"check": "REQUIREMENT_TRACEABILITY", "componentRef": component["componentId"], "state": "PASSED" if not missing else "FAILED"})
            if missing:
                conflicts.append({"path": relative, "reason": "test-misses-requirement-refs:" + ",".join(missing)})
    return checks, conflicts


def load_approved_plan(plan_path: Path, target: Path) -> dict:
    if plan_path.is_symlink() or not plan_path.is_file() or target.resolve() not in plan_path.resolve().parents:
        raise ValueError("implementation plan must be a target-owned regular file")
    plan = load_object(plan_path)
    blockers = validate_plan(plan, target)
    if blockers or plan["status"] != "APPROVED":
        raise ValueError("implementation plan is not approved and current" + (": " + "; ".join(blockers) if blockers else ""))
    return plan


def canonical_baseline(target: Path) -> tuple[Path, dict | None, dict, dict]:
    path = target / BASELINE
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("canonical implementation baseline is unsafe")
    if not path.exists():
        return path, None, {}, {}
    document = load_object(path)
    if document.get("manifestVersion") != 1 or document.get("artifactKind") != "SPRING_IMPLEMENTATION":
        raise ValueError("canonical implementation baseline has an unsupported identity")
    files, modes = load_baseline(path)
    return path, {"path": BASELINE, "sha256": sha(path)}, files, modes


def validate_report(report: dict, target: Path) -> None:
    required = {"springCodeDryRunVersion", "implementationPlan", "target", "baseline", "userFlow", "contractSummary", "qualityChecks", "generatedFiles", "plannedChanges", "verification", "targetSourceChanged", "readyForApproval", "executionReady"}
    if not isinstance(report, dict) or set(report) != required or report["springCodeDryRunVersion"] != 1:
        raise ValueError("Spring code dry-run report is invalid")
    if Path(report["target"]).resolve() != target.resolve() or report["targetSourceChanged"] is not False or report["executionReady"] is not False:
        raise ValueError("Spring code dry-run safety claims are invalid")
    plan_ref = report["implementationPlan"]
    if not isinstance(plan_ref, dict) or set(plan_ref) != {"path", "sha256"}:
        raise ValueError("implementation plan evidence is invalid")
    plan_path = target / plan_ref["path"]
    if not plan_path.is_file() or plan_path.is_symlink() or sha(plan_path) != plan_ref["sha256"]:
        raise ValueError("implementation plan evidence changed")
    plan = load_approved_plan(plan_path, target)
    expectations = contract_expectations(plan, target)
    expected_summary = {"httpMethod": "POST", "httpPath": expectations["apiPath"], "table": expectations["table"], "requirements": [item["requirementRef"] for item in plan["coverage"]]}
    if report["contractSummary"] != expected_summary:
        raise ValueError("contract summary changed")
    _, current_baseline, _, _ = canonical_baseline(target)
    if report["baseline"] != current_baseline:
        raise ValueError("implementation baseline evidence changed")
    expected = {item["target"]["plannedPath"]: item for item in plan["components"]}
    generated_paths = set()
    for item in report["generatedFiles"]:
        if not isinstance(item, dict) or set(item) != {"componentRef", "kind", "path", "sha256", "content"}:
            raise ValueError("generated file evidence is invalid")
        component = expected.get(item["path"])
        if component is None or component["componentId"] != item["componentRef"] or component["kind"] != item["kind"] or item["path"] in generated_paths:
            raise ValueError("generated file does not match the approved component graph")
        if hashlib.sha256(item["content"].encode()).hexdigest() != item["sha256"]:
            raise ValueError("generated file content hash changed")
        generated_paths.add(item["path"])
    with tempfile.TemporaryDirectory(prefix="spring-code-report-recheck-") as temporary:
        rendered = Path(temporary)
        for item in report["generatedFiles"]:
            destination = rendered / item["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(item["content"], encoding="utf-8")
        recomputed_checks, recomputed_conflicts = validate_candidate(plan, rendered, target)
    changes = report["plannedChanges"]
    if not isinstance(changes, dict) or set(changes) != {"state", "creates", "updates", "conflicts", "unchanged", "desiredManifest"} or changes["state"] not in {"COMPUTED", "CONFLICT"}:
        raise ValueError("planned changes are invalid")
    manifest = changes["desiredManifest"]
    if not isinstance(manifest, dict) or manifest.get("manifestVersion") != 1 or not isinstance(manifest.get("files"), dict) or not isinstance(manifest.get("modes"), dict) or set(manifest["files"]) != set(manifest["modes"]):
        raise ValueError("desired manifest is invalid")
    for item in report["generatedFiles"]:
        if manifest["files"].get(item["path"]) != item["sha256"]:
            raise ValueError("generated evidence disagrees with desired manifest")
    categorized: set[str] = set()
    for field in ("creates", "updates"):
        if not isinstance(changes[field], list):
            raise ValueError(f"plannedChanges.{field} is invalid")
        for item in changes[field]:
            expected_keys = {"path", "sha256"} if field == "creates" else {"path", "beforeSha256", "afterSha256", "beforeMode", "afterMode"}
            if not isinstance(item, dict) or set(item) != expected_keys or item["path"] in categorized:
                raise ValueError(f"plannedChanges.{field} entry is invalid")
            path = PurePosixPath(item["path"])
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("planned change path is unsafe")
            desired_hash = item["sha256"] if field == "creates" else item["afterSha256"]
            if manifest["files"].get(item["path"]) != desired_hash:
                raise ValueError("planned change disagrees with desired manifest")
            categorized.add(item["path"])
    if not isinstance(changes["unchanged"], list) or any(not isinstance(item, str) or item in categorized for item in changes["unchanged"]):
        raise ValueError("plannedChanges.unchanged is invalid")
    categorized.update(changes["unchanged"])
    if categorized != set(manifest["files"]):
        raise ValueError("change categories do not cover the desired manifest")
    if not isinstance(changes["conflicts"], list) or not all(isinstance(item, dict) and set(item) == {"path", "reason"} for item in changes["conflicts"]):
        raise ValueError("plannedChanges.conflicts is invalid")
    if changes["state"] == "COMPUTED" and changes["conflicts"]:
        raise ValueError("COMPUTED report contains conflicts")
    checks = report["qualityChecks"]
    if not isinstance(checks, list) or not all(isinstance(item, dict) and set(item) == {"check", "componentRef", "state"} and item["state"] in {"PASSED", "FAILED"} for item in checks):
        raise ValueError("quality check evidence is invalid")
    if checks != recomputed_checks:
        raise ValueError("quality checks do not match regenerated code")
    if any(item not in changes["conflicts"] for item in recomputed_conflicts):
        raise ValueError("candidate conflicts do not match regenerated code")
    computed_ready = changes["state"] == "COMPUTED" and not changes["conflicts"] and all(item["state"] == "PASSED" for item in checks)
    if computed_ready and (generated_paths != set(expected) or set(manifest["files"]) != set(expected)):
        raise ValueError("reviewable report does not exactly cover the approved component graph")
    if report["readyForApproval"] is not computed_ready:
        raise ValueError("readyForApproval does not match dry-run evidence")
    if report["verification"] != {"compilation": "NOT_RUN", "automatedTests": "NOT_RUN", "reason": "Dry run does not execute target code."}:
        raise ValueError("dry-run verification claim is invalid")
