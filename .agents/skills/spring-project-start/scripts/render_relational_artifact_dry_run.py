#!/usr/bin/env python3
"""Render DB artifacts temporarily and compare them without executing anything."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

from http_api_contract import encoded
from relational_physical_contract import validate_physical_contract
from render_generation_dry_run import compare, load_baseline, write_report
from validate_feature_specs import load_object


JAVA_PACKAGE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$")
JAVA_CLASS = re.compile(r"^[A-Z][A-Za-z0-9]*$")
DB_NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
SECRET = re.compile(r"^[A-Z][A-Z0-9_]*$")
RELATIONAL_BASELINE = ".starter-harness-relational.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pinned(value: object, expected: str, location: str) -> None:
    if value != expected: raise ValueError(f"{location} changed after artifact planning")


def artifact_plan(plan: dict, physical: dict, contract_path: Path, model_path: Path, profile_path: Path, profile: dict, target: Path) -> None:
    common = {"artifactPlanVersion", "planId", "physicalContractSha256", "physicalModelSha256", "profileSha256", "databaseName", "testcontainers"}
    version = plan.get("artifactPlanVersion") if isinstance(plan, dict) else None
    expected = common | ({"credentialBindings"} if version == 1 else {"schemaManagement", "composeCredentialBindings"})
    if version not in {1, 2} or set(plan) != expected: raise ValueError("relational artifact plan is invalid")
    if not isinstance(plan["planId"], str) or not re.fullmatch(r"[a-z][a-z0-9-]*", plan["planId"]): raise ValueError("artifact planId must be kebab-case")
    pinned(plan["physicalContractSha256"], sha(contract_path), "physical contract")
    pinned(plan["physicalModelSha256"], sha(model_path), "physical model")
    pinned(plan["profileSha256"], sha(profile_path), "technology profile")
    if not isinstance(plan["databaseName"], str) or not DB_NAME.fullmatch(plan["databaseName"]): raise ValueError("databaseName must be safe lowercase snake_case")
    schema_management = "EXISTING" if version == 1 and physical["database"]["schemaName"] == "public" else plan.get("schemaManagement")
    if schema_management not in {"EXISTING", "CREATE_IF_MISSING"}: raise ValueError("schemaManagement must explicitly assign schema responsibility")
    bindings = plan.get("credentialBindings") if version == 1 else plan["composeCredentialBindings"]
    compose_selected = physical["provisioningPlan"]["compose"] is not None
    if compose_selected:
        if not isinstance(bindings, dict) or set(bindings) != {"username", "password"}: raise ValueError("Compose credential bindings must identify username and password")
        names = physical["provisioningPlan"]["compose"]["secretNames"]
        if any(not isinstance(value, str) or not SECRET.fullmatch(value) for value in bindings.values()): raise ValueError("Compose credential bindings must be secret names")
        if bindings["username"] == bindings["password"] or set(bindings.values()) != set(names): raise ValueError("Compose credential bindings must map the approved secret names exactly")
    elif bindings is not None: raise ValueError("Compose credential bindings exist when Compose is not selected")
    selected = physical["provisioningPlan"]["strategy"] in {"TESTCONTAINERS", "BOTH"}
    test = plan["testcontainers"]
    if selected:
        if not isinstance(test, dict) or set(test) != {"plannedPath", "packageName", "className"}: raise ValueError("Testcontainers rendering details are required")
        path = Path(test["plannedPath"])
        if path.is_absolute() or ".." in path.parts or path.suffix != ".java": raise ValueError("Testcontainers plannedPath is unsafe")
        resolved = (target / path).resolve()
        if target.resolve() not in resolved.parents: raise ValueError("Testcontainers plannedPath escapes target")
        if not JAVA_PACKAGE.fullmatch(test["packageName"]) or not JAVA_CLASS.fullmatch(test["className"]): raise ValueError("Testcontainers Java package or class is invalid")
        if profile.get("decisions", {}).get("verification", {}).get("option") != "verification.testcontainers": raise ValueError("technology profile does not enable Testcontainers verification")
        if profile.get("project", {}).get("packageName") != test["packageName"]: raise ValueError("Testcontainers package does not match the target project profile")
        suffix = Path(*test["packageName"].split("."), test["className"] + ".java")
        if path.parts[:3] != ("src", "test", "java") or not path.as_posix().endswith(suffix.as_posix()): raise ValueError("Testcontainers path does not match src/test/java, package, and class")
    elif test is not None: raise ValueError("Testcontainers details exist when it is not selected")


def sql(physical: dict, plan: dict) -> str:
    lines = ["-- Generated from an approved physical data contract.", "-- Review in an isolated PostgreSQL dry run before execution.", ""]
    schema_management = "EXISTING" if plan.get("artifactPlanVersion") == 1 else plan["schemaManagement"]
    if schema_management == "CREATE_IF_MISSING": lines.extend([f"CREATE SCHEMA IF NOT EXISTS {physical['database']['schemaName']};", ""])
    for table in physical["tables"]:
        by_id = {column["columnId"]: column for column in table["columns"]}
        definitions = []
        for column in table["columns"]:
            value = f"    {column['name']} {column['sqlType']}"
            if column["defaultExpression"] is not None: value += f" DEFAULT {column['defaultExpression']}"
            if not column["nullable"]: value += " NOT NULL"
            if column["unique"]: value += " UNIQUE"
            definitions.append(value)
        primary = table["primaryKey"]
        definitions.append(f"    CONSTRAINT {primary['name']} PRIMARY KEY ({', '.join(by_id[item]['name'] for item in primary['columnIds'])})")
        definitions.extend(f"    CONSTRAINT {item['name']} CHECK ({item['expression']})" for item in table["checkConstraints"])
        lines.extend([f"CREATE TABLE {physical['database']['schemaName']}.{table['name']} (", ",\n".join(definitions), ");", ""])
    tables = {table["tableId"]: table for table in physical["tables"]}
    for table in physical["tables"]:
        columns = {item["columnId"]: item["name"] for item in table["columns"]}
        for fk in table["foreignKeys"]:
            target = tables[fk["referencedTableId"]]; target_columns = {item["columnId"]: item["name"] for item in target["columns"]}
            lines.extend([f"ALTER TABLE {physical['database']['schemaName']}.{table['name']}", f"    ADD CONSTRAINT {fk['name']} FOREIGN KEY ({', '.join(columns[item] for item in fk['columnIds'])})", f"    REFERENCES {physical['database']['schemaName']}.{target['name']} ({', '.join(target_columns[item] for item in fk['referencedColumnIds'])})", f"    ON DELETE {fk['onDelete'].replace('_', ' ')} ON UPDATE {fk['onUpdate'].replace('_', ' ')};", ""])
        for index in table["indexes"]:
            unique = "UNIQUE " if index["unique"] else ""
            lines.extend([f"CREATE {unique}INDEX {index['name']} ON {physical['database']['schemaName']}.{table['name']} ({', '.join(columns[item] for item in index['columnIds'])});", ""])
    return "\n".join(lines)


def compose(physical: dict, plan: dict) -> str:
    item = physical["provisioningPlan"]["compose"]; bindings = plan.get("credentialBindings") if plan["artifactPlanVersion"] == 1 else plan["composeCredentialBindings"]
    return "\n".join(["services:", f"  {item['serviceName']}:", f"    image: {item['imageReference']}", "    environment:", f"      POSTGRES_DB: {plan['databaseName']}", f"      POSTGRES_USER: ${{{bindings['username']}:?set {bindings['username']}}}", f"      POSTGRES_PASSWORD: ${{{bindings['password']}:?set {bindings['password']}}}", "    ports:", f"      - \"{item['hostPort']}:5432\"", "    volumes:", f"      - {item['volumeName']}:/var/lib/postgresql/data", "", "volumes:", f"  {item['volumeName']}: {{}}", ""])


def testcontainers_java(physical: dict, plan: dict) -> str:
    test = plan["testcontainers"]; image = physical["provisioningPlan"]["testcontainers"]["imageReference"]
    return "\n".join([f"package {test['packageName']};", "", "import org.springframework.boot.test.context.TestConfiguration;", "import org.springframework.boot.testcontainers.service.connection.ServiceConnection;", "import org.springframework.context.annotation.Bean;", "import org.testcontainers.containers.PostgreSQLContainer;", "", "@TestConfiguration(proxyBeanMethods = false)", f"public class {test['className']} {{", "    @Bean", "    @ServiceConnection", "    PostgreSQLContainer<?> postgresContainer() {", f"        return new PostgreSQLContainer<>(\"{image}\")", f"                .withDatabaseName(\"{plan['databaseName']}\");", "    }", "}", ""])


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("physical-contract", "physical-model", "logical-contract", "route", "feature", "profile", "artifact-plan", "target", "output"): parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--baseline-manifest", type=Path); parser.add_argument("--force", action="store_true"); args = parser.parse_args()
    try:
        root = args.target.resolve(strict=True)
        harness_root = Path(__file__).resolve().parents[4]
        if args.target.is_symlink() or root == harness_root: raise ValueError("target must be an external non-symlink repository")
        for path, label in ((args.physical_contract, "physical contract"), (args.physical_model, "physical model"), (args.logical_contract, "logical contract"), (args.route, "route"), (args.feature, "feature"), (args.profile, "profile"), (args.artifact_plan, "artifact plan"), (args.output, "output")):
            resolved = path.resolve()
            if root not in (resolved, *resolved.parents): raise ValueError(f"{label} escapes target")
        metadata, physical, route, feature, profile = (load_object(args.physical_contract), load_object(args.physical_model), load_object(args.route), load_object(args.feature), load_object(args.profile))
        approved, blockers, validated_physical, _ = validate_physical_contract(metadata, args.physical_model, args.logical_contract, route, args.route, root, feature, profile)
        if not approved or blockers: raise ValueError("physical contract is not approved and current: " + "; ".join(blockers))
        if validated_physical["adapterId"] != "postgresql-flyway": raise ValueError("artifact renderer supports only postgresql-flyway")
        plan = load_object(args.artifact_plan); artifact_plan(plan, physical, args.physical_contract, args.physical_model, args.profile, profile, root)
        canonical_baseline = root / RELATIONAL_BASELINE
        if args.baseline_manifest and args.baseline_manifest.resolve() != canonical_baseline: raise ValueError("only the canonical relational baseline may authorize updates")
        if canonical_baseline.is_symlink(): raise ValueError("canonical relational baseline must not be a symbolic link")
        if canonical_baseline.exists():
            baseline_document = load_object(canonical_baseline)
            if baseline_document.get("manifestVersion") != 1 or baseline_document.get("artifactKind") != "RELATIONAL": raise ValueError("canonical relational baseline has an unsupported identity")
        baseline_evidence = {"path": RELATIONAL_BASELINE, "sha256": sha(canonical_baseline)} if canonical_baseline.exists() else None
        with tempfile.TemporaryDirectory(prefix="relational-artifact-dry-run-") as temporary:
            rendered = Path(temporary)
            artifacts = [("FLYWAY_SQL", physical["migrationPlan"]["plannedSourcePath"], sql(physical, plan))]
            if physical["provisioningPlan"]["compose"]: artifacts.append(("DOCKER_COMPOSE", physical["provisioningPlan"]["compose"]["plannedPath"], compose(physical, plan)))
            if plan["testcontainers"]: artifacts.append(("TESTCONTAINERS_JAVA", plan["testcontainers"]["plannedPath"], testcontainers_java(physical, plan)))
            for _, relative, content in artifacts:
                destination = rendered / relative; destination.parent.mkdir(parents=True, exist_ok=True); destination.write_text(content, encoding="utf-8")
            baseline, modes = load_baseline(canonical_baseline if canonical_baseline.exists() else None); changes = compare(rendered, root, baseline, modes)
        previews = [{"kind": kind, "path": path, "sha256": hashlib.sha256(content.encode()).hexdigest(), "content": content} for kind, path, content in artifacts]
        report = {"relationalArtifactDryRunVersion": 1, "physicalContract": {"path": str(args.physical_contract), "sha256": sha(args.physical_contract)}, "physicalModelSha256": sha(args.physical_model), "artifactPlan": {"path": str(args.artifact_plan), "sha256": sha(args.artifact_plan)}, "baseline": baseline_evidence, "target": str(root), "generatedArtifacts": previews, "plannedChanges": changes, "recoveryAssessment": {"required": physical["migrationPlan"]["requiredRecovery"], "renderedDdlClass": "TRANSACTIONAL_CREATE_ONLY", "isolatedDatabaseVerified": False}, "targetSourceChanged": False, "databaseOrContainerChanged": False, "readyForApproval": changes["state"] == "COMPUTED", "executionReady": False}
        write_report(report, args.output, args.force)
    except (OSError, ValueError) as error:
        print(f"RELATIONAL_ARTIFACT_DRY_RUN_VALID: no\nERROR: {error}", file=sys.stderr); return 1
    print("RELATIONAL_ARTIFACT_DRY_RUN_VALID: yes"); print(f"CHANGE_RESULT: {report['plannedChanges']['state']}"); print("TARGET_SOURCE_CHANGED: no"); print("DATABASE_OR_CONTAINER_CHANGED: no"); print(f"READY_FOR_APPROVAL: {'yes' if report['readyForApproval'] else 'no'}"); print("EXECUTION_READY: no"); return 0


if __name__ == "__main__": sys.exit(main())
