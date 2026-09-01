#!/usr/bin/env python3
"""Validate PostgreSQL/Flyway physical designs without rendering or applying DDL."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from http_api_contract import reject_openapi_secrets
from relational_data_contract import STABLE_ID, derived_traceability as logical_traceability, validate_relational_contract
from validate_design_contract import inside
from validate_feature_specs import load_object, text, validate_approval


SQL_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
SQL_TYPE = re.compile(r"^(?:UUID|TEXT|BOOLEAN|DATE|TIME|TIMESTAMP WITH TIME ZONE|TIMESTAMP WITHOUT TIME ZONE|INTEGER|BIGINT|SMALLINT|BYTEA|JSONB|VARCHAR\([1-9][0-9]{0,4}\)|NUMERIC\([1-9][0-9]?,[0-9]{1,2}\))$")
RESERVED = {"all", "analyse", "analyze", "and", "any", "array", "as", "asc", "both", "case", "cast", "check", "collation", "column", "constraint", "create", "current_date", "current_time", "current_timestamp", "default", "desc", "distinct", "do", "else", "end", "except", "false", "for", "foreign", "from", "grant", "group", "having", "in", "initially", "intersect", "into", "lateral", "leading", "limit", "localtime", "localtimestamp", "new", "not", "null", "off", "offset", "old", "on", "only", "or", "order", "placing", "primary", "references", "returning", "select", "session_user", "some", "symmetric", "table", "then", "to", "trailing", "true", "union", "unique", "user", "using", "variadic", "when", "where", "window", "with"}
RECOVERY_REQUIREMENTS = {"TRANSACTIONAL_REQUIRED", "COMPENSATION_REQUIRED", "FORWARD_FIX_ACCEPTED", "MANUAL_REVIEW_REQUIRED"}
RISK = {"NONE", "LOW", "MEDIUM", "HIGH", "UNKNOWN"}
ON_ACTION = {"NO_ACTION", "RESTRICT", "CASCADE", "SET_NULL", "SET_DEFAULT"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value: object, location: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(item not in "0123456789abcdef" for item in value):
        raise ValueError(f"{location} must be lowercase SHA-256")
    return value


def stable(value: object, location: str) -> str:
    result = text(value, location, False)
    if not STABLE_ID.fullmatch(result): raise ValueError(f"{location} must be lowercase kebab-case")
    return result


def sql_name(value: object, location: str) -> str:
    result = text(value, location, False)
    if not SQL_NAME.fullmatch(result): raise ValueError(f"{location} must be unquoted snake_case")
    if len(result.encode()) > 63: raise ValueError(f"{location} exceeds PostgreSQL's 63-byte identifier limit")
    if result in RESERVED: raise ValueError(f"{location} uses a reserved PostgreSQL name: {result}")
    return result


def array(value: object, location: str) -> list:
    if not isinstance(value, list): raise ValueError(f"{location} must be an array")
    return value


def load_adapters() -> dict[str, dict]:
    path = Path(__file__).resolve().parent.parent / "references" / "relational-adapters.json"
    document = load_object(path)
    if document.get("registryVersion") != 1 or not isinstance(document.get("adapters"), list):
        raise ValueError("relational adapter registry is invalid")
    result = {item.get("id"): item for item in document["adapters"] if isinstance(item, dict)}
    if len(result) != len(document["adapters"]): raise ValueError("relational adapter registry has duplicate or missing IDs")
    return result


def type_compatible(logical_type: str, sql_type: str) -> bool:
    allowed = {
        "STRING": ("TEXT", "VARCHAR("), "INTEGER": ("INTEGER", "BIGINT", "SMALLINT"),
        "DECIMAL": ("NUMERIC(",), "BOOLEAN": ("BOOLEAN",), "DATE": ("DATE",), "TIME": ("TIME",),
        "DATETIME": ("TIMESTAMP WITH TIME ZONE", "TIMESTAMP WITHOUT TIME ZONE"), "UUID": ("UUID",),
        "BINARY": ("BYTEA",), "JSON": ("JSONB",),
    }
    return logical_type == "CUSTOM" or any(sql_type == item or sql_type.startswith(item) for item in allowed.get(logical_type, ()))


def derived_traceability(physical: dict, logical: dict) -> list[dict]:
    entity_refs = {item["entityId"]: item.get("requirementRefs", []) for item in logical["entities"]}
    field_refs = {field["fieldId"]: field.get("requirementRefs", []) for item in logical["entities"] for field in item["fields"]}
    relationship_refs = {item["relationshipId"]: item.get("requirementRefs", []) for item in logical["relationships"]}
    invariant_refs = {rule["invariantId"]: rule["requirementRefs"] for item in logical["entities"] for rule in item["invariants"]}
    result = []
    for table in physical.get("tables", []):
        if table.get("entityRef") and entity_refs.get(table["entityRef"]):
            result.append({"subjectRef": f"table:{table['tableId']}", "requirementRefs": entity_refs[table["entityRef"]]})
        for column in table.get("columns", []):
            if field_refs.get(column.get("fieldRef")):
                result.append({"subjectRef": f"column:{column['columnId']}", "requirementRefs": field_refs[column["fieldRef"]]})
    for item in physical.get("relationshipImplementations", []):
        if relationship_refs.get(item.get("relationshipRef")):
            result.append({"subjectRef": f"relationship-implementation:{item['relationshipRef']}", "requirementRefs": relationship_refs[item["relationshipRef"]]})
    for item in physical.get("invariantImplementations", []):
        if invariant_refs.get(item.get("invariantRef")):
            result.append({"subjectRef": f"invariant-implementation:{item['invariantRef']}", "requirementRefs": invariant_refs[item["invariantRef"]]})
    return result


def validate_physical_model(physical: dict, logical: dict, metadata: dict, target: Path) -> list[str]:
    reject_openapi_secrets(physical, location="physicalModel")
    keys = {"physicalModelVersion", "physicalModelId", "adapterId", "database", "migrationPlan", "provisioningPlan", "riskAssessment", "tables", "queryPatterns", "relationshipImplementations", "invariantImplementations"}
    if set(physical) != keys: raise ValueError("physical model has invalid top-level fields")
    if physical["physicalModelVersion"] != 1: raise ValueError("physicalModelVersion must be 1")
    stable(physical["physicalModelId"], "physicalModelId")
    adapters = load_adapters(); adapter = adapters.get(physical["adapterId"])
    if adapter is None: raise ValueError("physical model references an unknown adapter")
    blockers = []
    if adapter["status"] != "READY": blockers.append(f"physical adapter is not READY: {adapter['id']}")
    if metadata.get("adapter") != {"id": adapter["id"], "status": adapter["status"]}: blockers.append("metadata adapter assessment is stale")
    database = physical["database"]
    if not isinstance(database, dict) or set(database) != {"engine", "version", "schemaName"}: raise ValueError("database has invalid fields")
    if database["engine"] != adapter["engine"]: blockers.append("database engine does not match the selected adapter")
    text(database["version"], "database.version", False); sql_name(database["schemaName"], "database.schemaName")
    migration = physical["migrationPlan"]
    migration_keys = {"strategy", "plannedSourcePath", "sourceOfTruth", "requiredRecovery", "applyAuthorized"}
    if not isinstance(migration, dict) or set(migration) != migration_keys: raise ValueError("migrationPlan has invalid fields")
    if migration["strategy"] != adapter["migrationStrategy"] or migration["sourceOfTruth"] != "VERSIONED_MIGRATION": blockers.append("migration source strategy does not match the adapter")
    migration_path = inside(target.resolve(), text(migration["plannedSourcePath"], "migrationPlan.plannedSourcePath", False), "migrationPlan.plannedSourcePath")
    if not re.fullmatch(r"V[0-9][0-9._]*__[a-z0-9_]+\.sql", migration_path.name): blockers.append("planned Flyway migration name is invalid")
    if migration_path.exists(): blockers.append("planned Flyway migration path already exists")
    if migration["requiredRecovery"] not in RECOVERY_REQUIREMENTS: raise ValueError("migration requiredRecovery is invalid")
    if migration["applyAuthorized"] is not False: blockers.append("physical contract must not authorize migration execution")
    risk = physical["riskAssessment"]
    if not isinstance(risk, dict) or set(risk) != {"dataLoss", "locking", "downtime", "reason"}: raise ValueError("riskAssessment has invalid fields")
    if any(risk[item] not in RISK for item in ("dataLoss", "locking", "downtime")): raise ValueError("riskAssessment level is invalid")
    text(risk["reason"], "riskAssessment.reason", False)
    if "UNKNOWN" in {risk["dataLoss"], risk["locking"], risk["downtime"]}: blockers.append("physical database risk is UNKNOWN")
    logical_entities = {item["entityId"]: item for item in logical["entities"]}
    logical_fields = {field["fieldId"]: field for item in logical["entities"] for field in item["fields"]}
    tables = array(physical["tables"], "tables")
    if not tables: blockers.append("physical model has no tables")
    table_ids, table_names, column_ids, entity_coverage, field_coverage = set(), set(), set(), set(), set()
    table_columns: dict[str, set[str]] = {}
    constraint_ids: set[str] = set()
    foreign_key_ids: set[str] = set()
    check_invariants: dict[str, set[str]] = {}
    index_ids: set[str] = set()
    query_items = array(physical["queryPatterns"], "queryPatterns")
    if any(not isinstance(item, dict) for item in query_items): raise ValueError("queryPatterns entries must be objects")
    query_ids = {stable(item.get("queryPatternId"), f"queryPatterns[{index}].queryPatternId") for index, item in enumerate(query_items)}
    if len(query_ids) != len(physical["queryPatterns"]): raise ValueError("queryPatterns contains duplicate IDs")
    known_requirements = {ref for item in metadata.get("traceability", []) for ref in item.get("requirementRefs", [])}
    for index, query in enumerate(physical["queryPatterns"]):
        if set(query) != {"queryPatternId", "description", "tableId", "columnIds", "requirementRefs"}: raise ValueError(f"queryPatterns[{index}] has invalid fields")
        text(query["description"], f"queryPatterns[{index}].description", False)
        if not isinstance(query["columnIds"], list) or not query["columnIds"]: raise ValueError(f"queryPatterns[{index}].columnIds must not be empty")
        if not isinstance(query["requirementRefs"], list) or not query["requirementRefs"]: blockers.append(f"query pattern has no feature justification: {query['queryPatternId']}")
        elif set(query["requirementRefs"]) - known_requirements: blockers.append(f"query pattern references unknown requirements: {query['queryPatternId']}")
    for index, table in enumerate(tables):
        location = f"tables[{index}]"; table_keys = {"tableId", "name", "description", "entityRef", "changeIntent", "previousNames", "columns", "primaryKey", "foreignKeys", "checkConstraints", "indexes"}
        if not isinstance(table, dict) or set(table) != table_keys: raise ValueError(f"{location} has invalid fields")
        table_id = stable(table["tableId"], f"{location}.tableId"); name = sql_name(table["name"], f"{location}.name")
        if table_id in table_ids or name in table_names: raise ValueError("duplicate physical table ID or name")
        table_ids.add(table_id); table_names.add(name); text(table["description"], f"{location}.description", False)
        if table["changeIntent"] != "CREATE" or table["previousNames"] != []: blockers.append(f"CREATE table has invalid rename intent: {table_id}")
        entity_ref = table["entityRef"]
        if entity_ref is not None:
            if entity_ref not in logical_entities: blockers.append(f"table references unknown logical entity: {table_id}")
            elif entity_ref in entity_coverage: blockers.append(f"logical entity maps to more than one primary table: {entity_ref}")
            else: entity_coverage.add(entity_ref)
        columns = array(table["columns"], f"{location}.columns"); local_columns = set(); table_columns[table_id] = local_columns
        if not columns: blockers.append(f"table has no columns: {table_id}")
        for column_index, column in enumerate(columns):
            column_location = f"{location}.columns[{column_index}]"; column_keys = {"columnId", "name", "description", "fieldRef", "sqlType", "nullable", "unique", "defaultExpression", "changeIntent", "previousNames"}
            if not isinstance(column, dict) or set(column) != column_keys: raise ValueError(f"{column_location} has invalid fields")
            column_id = stable(column["columnId"], f"{column_location}.columnId"); sql_name(column["name"], f"{column_location}.name")
            if column_id in column_ids: raise ValueError(f"duplicate columnId: {column_id}")
            column_ids.add(column_id); local_columns.add(column_id); text(column["description"], f"{column_location}.description", False)
            if not isinstance(column["nullable"], bool) or not isinstance(column["unique"], bool): raise ValueError(f"{column_location} flags must be boolean")
            if not isinstance(column["sqlType"], str) or not SQL_TYPE.fullmatch(column["sqlType"]): blockers.append(f"unsupported PostgreSQL type: {column_id}")
            if column["defaultExpression"] is not None and column["defaultExpression"] not in {"CURRENT_TIMESTAMP", "true", "false", "0"}: blockers.append(f"unsupported default expression: {column_id}")
            if column["changeIntent"] != "CREATE" or column["previousNames"] != []: blockers.append(f"CREATE column has invalid rename intent: {column_id}")
            field_ref = column["fieldRef"]
            if field_ref is not None:
                field = logical_fields.get(field_ref)
                if field is None: blockers.append(f"column references unknown logical field: {column_id}")
                else:
                    if field_ref in field_coverage: blockers.append(f"logical field maps to more than one column: {field_ref}")
                    field_coverage.add(field_ref)
                    if column["nullable"] == field["required"]: blockers.append(f"column nullability does not match logical field: {column_id}")
                    if not type_compatible(field["logicalType"], column["sqlType"]): blockers.append(f"column type does not match logical field: {column_id}")
                    if column["sqlType"].startswith("NUMERIC("):
                        precision, scale = (int(item) for item in column["sqlType"][8:-1].split(","))
                        if scale > precision: blockers.append(f"numeric scale exceeds precision: {column_id}")
        primary = table["primaryKey"]
        if not isinstance(primary, dict) or set(primary) != {"constraintId", "name", "columnIds"}: raise ValueError(f"{location}.primaryKey has invalid fields")
        pk_id = stable(primary["constraintId"], f"{location}.primaryKey.constraintId"); sql_name(primary["name"], f"{location}.primaryKey.name")
        pk_columns = array(primary["columnIds"], f"{location}.primaryKey.columnIds")
        if not pk_columns or set(pk_columns) - local_columns: blockers.append(f"primary key columns are invalid: {table_id}")
        if pk_id in constraint_ids: raise ValueError(f"duplicate constraintId: {pk_id}")
        constraint_ids.add(pk_id)
        if entity_ref in logical_entities:
            expected_identifiers = {field["fieldId"] for field in logical_entities[entity_ref]["fields"] if field["identifier"]}
            actual_identifiers = {column["fieldRef"] for column in columns if column["columnId"] in pk_columns}
            if expected_identifiers != actual_identifiers: blockers.append(f"primary key does not match logical identifiers: {table_id}")
        for column in columns:
            field = logical_fields.get(column["fieldRef"])
            if field and field["unique"] and not column["unique"] and column["columnId"] not in pk_columns:
                blockers.append(f"column uniqueness does not match logical field: {column['columnId']}")
        for fk_index, fk in enumerate(array(table["foreignKeys"], f"{location}.foreignKeys")):
            fk_location = f"{location}.foreignKeys[{fk_index}]"; fk_keys = {"constraintId", "name", "columnIds", "referencedTableId", "referencedColumnIds", "relationshipRef", "onDelete", "onUpdate"}
            if not isinstance(fk, dict) or set(fk) != fk_keys: raise ValueError(f"{fk_location} has invalid fields")
            fk_id = stable(fk["constraintId"], f"{fk_location}.constraintId")
            if fk_id in constraint_ids: raise ValueError(f"duplicate constraintId: {fk_id}")
            constraint_ids.add(fk_id); foreign_key_ids.add(fk_id); sql_name(fk["name"], f"{fk_location}.name")
            if set(fk["columnIds"]) - local_columns: blockers.append(f"foreign key uses unknown source columns: {fk['constraintId']}")
            if fk["onDelete"] not in ON_ACTION or fk["onUpdate"] not in ON_ACTION: raise ValueError(f"{fk_location} action is invalid")
            if fk["relationshipRef"] not in {item["relationshipId"] for item in logical["relationships"]}: blockers.append(f"foreign key references an unknown logical relationship: {fk_id}")
        for check_index, check in enumerate(array(table["checkConstraints"], f"{location}.checkConstraints")):
            check_location = f"{location}.checkConstraints[{check_index}]"
            if not isinstance(check, dict) or set(check) != {"constraintId", "name", "expression", "invariantRefs"}: raise ValueError(f"{check_location} has invalid fields")
            check_id = stable(check["constraintId"], f"{check_location}.constraintId")
            if check_id in constraint_ids: raise ValueError(f"duplicate constraintId: {check_id}")
            constraint_ids.add(check_id); sql_name(check["name"], f"{check_location}.name")
            expression = text(check["expression"], f"{check_location}.expression", False)
            expression_names = set(re.findall(r"[a-z_][a-z0-9_]*", expression.lower()))
            column_names = {column["name"] for column in columns}
            if not re.fullmatch(r"[a-zA-Z0-9_ ()<>=!]+", expression) or expression_names - column_names - {"and", "or", "not", "true", "false", "null"}:
                blockers.append(f"unsafe or unresolved check expression: {check['constraintId']}")
            invariant_refs = set(check["invariantRefs"])
            if not invariant_refs or invariant_refs - {rule["invariantId"] for entity in logical["entities"] for rule in entity["invariants"]}: blockers.append(f"check constraint has invalid invariant links: {check_id}")
            check_invariants[check_id] = invariant_refs
        for index_index, item in enumerate(array(table["indexes"], f"{location}.indexes")):
            index_location = f"{location}.indexes[{index_index}]"
            if not isinstance(item, dict) or set(item) != {"indexId", "name", "columnIds", "unique", "queryPatternRefs"}: raise ValueError(f"{index_location} has invalid fields")
            index_id = stable(item["indexId"], f"{index_location}.indexId"); sql_name(item["name"], f"{index_location}.name")
            if index_id in index_ids: raise ValueError(f"duplicate indexId: {index_id}")
            index_ids.add(index_id)
            if set(item["columnIds"]) - local_columns or not item["columnIds"]: blockers.append(f"index columns are invalid: {index_id}")
            if not isinstance(item["unique"], bool): raise ValueError(f"{index_location}.unique must be boolean")
            if not item["queryPatternRefs"] or set(item["queryPatternRefs"]) - query_ids: blockers.append(f"index has no valid query justification: {index_id}")
    if entity_coverage != set(logical_entities): blockers.append("physical tables do not cover every logical entity exactly once")
    if field_coverage != set(logical_fields): blockers.append("physical columns do not cover every logical field exactly once")
    for query in physical["queryPatterns"]:
        if query["tableId"] not in table_ids: blockers.append(f"query pattern references an unknown table: {query['queryPatternId']}")
        elif set(query["columnIds"]) - table_columns[query["tableId"]]: blockers.append(f"query pattern references unknown columns: {query['queryPatternId']}")
    for table in tables:
        for fk in table["foreignKeys"]:
            referenced = fk["referencedTableId"]
            if referenced not in table_ids: blockers.append(f"foreign key references an unknown table: {fk['constraintId']}")
            elif set(fk["referencedColumnIds"]) - table_columns[referenced]: blockers.append(f"foreign key references unknown target columns: {fk['constraintId']}")
            if len(fk["columnIds"]) != len(fk["referencedColumnIds"]): blockers.append(f"foreign key column counts do not match: {fk['constraintId']}")
    logical_relationships = {item["relationshipId"] for item in logical["relationships"]}
    implementations = array(physical["relationshipImplementations"], "relationshipImplementations")
    implemented_relationships = set()
    for index, item in enumerate(implementations):
        if not isinstance(item, dict) or set(item) != {"relationshipRef", "enforcement", "constraintRefs", "reason"}: raise ValueError(f"relationshipImplementations[{index}] has invalid fields")
        relationship_ref = item["relationshipRef"]
        if relationship_ref in implemented_relationships: raise ValueError(f"duplicate relationship implementation: {relationship_ref}")
        implemented_relationships.add(relationship_ref); text(item["reason"], f"relationshipImplementations[{index}].reason", False)
        if item["enforcement"] not in {"FOREIGN_KEY", "JOIN_TABLE", "APPLICATION"}: raise ValueError("relationship enforcement is invalid")
        if item["enforcement"] in {"FOREIGN_KEY", "JOIN_TABLE"} and (not item["constraintRefs"] or set(item["constraintRefs"]) - foreign_key_ids): blockers.append(f"relationship implementation lacks valid foreign keys: {relationship_ref}")
        linked_relationships = {fk["relationshipRef"] for table in tables for fk in table["foreignKeys"] if fk["constraintId"] in item["constraintRefs"]}
        if item["enforcement"] in {"FOREIGN_KEY", "JOIN_TABLE"} and linked_relationships != {relationship_ref}: blockers.append(f"relationship constraints do not prove the selected relationship: {relationship_ref}")
    if implemented_relationships != logical_relationships: blockers.append("physical model does not implement every logical relationship exactly once")
    logical_invariants = {rule["invariantId"] for entity in logical["entities"] for rule in entity["invariants"]}
    implemented_invariants = set()
    for index, item in enumerate(array(physical["invariantImplementations"], "invariantImplementations")):
        if not isinstance(item, dict) or set(item) != {"invariantRef", "enforcement", "constraintRef", "reason"}: raise ValueError(f"invariantImplementations[{index}] has invalid fields")
        invariant_ref = item["invariantRef"]
        if invariant_ref in implemented_invariants: raise ValueError(f"duplicate invariant implementation: {invariant_ref}")
        implemented_invariants.add(invariant_ref); text(item["reason"], f"invariantImplementations[{index}].reason", False)
        if item["enforcement"] not in {"DATABASE_CHECK", "APPLICATION", "BOTH"}: raise ValueError("invariant enforcement is invalid")
        if item["enforcement"] in {"DATABASE_CHECK", "BOTH"} and invariant_ref not in check_invariants.get(item["constraintRef"], set()): blockers.append(f"invariant implementation lacks a matching check constraint: {invariant_ref}")
        if item["enforcement"] == "APPLICATION" and item["constraintRef"] is not None: blockers.append(f"application-only invariant must not reference a constraint: {invariant_ref}")
    if implemented_invariants != logical_invariants: blockers.append("physical model does not implement every logical invariant exactly once")
    provisioning = physical["provisioningPlan"]
    if not isinstance(provisioning, dict) or set(provisioning) != {"strategy", "compose", "testcontainers"}: raise ValueError("provisioningPlan has invalid fields")
    expected_strategy = logical["runtimeProvisioning"]["strategy"]
    if provisioning["strategy"] != expected_strategy: blockers.append("physical provisioning plan does not match the logical contract")
    compose_expected = expected_strategy in {"DOCKER_COMPOSE", "BOTH"}; test_expected = expected_strategy in {"TESTCONTAINERS", "BOTH"}
    compose = provisioning["compose"]
    if compose_expected:
        compose_keys = {"plannedPath", "serviceName", "volumeName", "imageReference", "hostPort", "checkPortAtExecution", "autoStart", "destructiveCleanupAllowed", "secretNames"}
        if not isinstance(compose, dict) or set(compose) != compose_keys: raise ValueError("Compose provisioning plan has invalid fields")
        inside(target.resolve(), compose["plannedPath"], "provisioningPlan.compose.plannedPath"); sql_name(compose["serviceName"], "compose.serviceName"); sql_name(compose["volumeName"], "compose.volumeName")
        if compose["imageReference"] != logical["runtimeProvisioning"]["imageReference"]: blockers.append("Compose image does not match the approved logical contract")
        if not isinstance(compose["hostPort"], int) or isinstance(compose["hostPort"], bool) or not 1 <= compose["hostPort"] <= 65535: raise ValueError("Compose hostPort is invalid")
        if compose["checkPortAtExecution"] is not True or compose["autoStart"] is not False or compose["destructiveCleanupAllowed"] is not False: blockers.append("Compose plan must defer execution and destructive cleanup")
        if compose["secretNames"] != logical["runtimeProvisioning"]["credentialSecretNames"]: blockers.append("Compose secret names do not match the logical contract")
    elif compose is not None: blockers.append("Compose plan exists when Compose is not selected")
    testcontainers = provisioning["testcontainers"]
    if test_expected:
        test_keys = {"imageReference", "reuse", "authPersistence", "startupAuthorized"}
        if not isinstance(testcontainers, dict) or set(testcontainers) != test_keys: raise ValueError("Testcontainers plan has invalid fields")
        if testcontainers["imageReference"] != logical["runtimeProvisioning"]["imageReference"]: blockers.append("Testcontainers image does not match the approved logical contract")
        if testcontainers["reuse"] is not False or testcontainers["authPersistence"] is not False or testcontainers["startupAuthorized"] is not False: blockers.append("Testcontainers plan must be isolated and not authorized to start")
    elif testcontainers is not None: blockers.append("Testcontainers plan exists when it is not selected")
    if metadata.get("traceability") != derived_traceability(physical, logical): blockers.append("physical contract traceability is stale")
    return blockers


def validate_physical_contract(metadata: dict, physical_path: Path, logical_metadata_path: Path, route: dict, route_path: Path, target: Path, feature: dict, profile: dict) -> tuple[bool, list[str], dict, dict]:
    required = {"physicalContractVersion", "contractId", "logicalContract", "logicalModel", "target", "artifact", "physicalModelSha256", "adapter", "traceability", "approval"}
    if not isinstance(metadata, dict) or set(metadata) != required or metadata["physicalContractVersion"] != 1: raise ValueError("physical contract metadata is invalid")
    stable(metadata["contractId"], "contractId"); root = target.resolve()
    logical_ref = metadata["logicalContract"]
    if not isinstance(logical_ref, dict) or set(logical_ref) != {"path", "sha256"}: raise ValueError("logicalContract reference is invalid")
    declared_logical = inside(root, logical_ref["path"], "logicalContract.path")
    if declared_logical != logical_metadata_path.resolve(): raise ValueError("logical contract path does not match")
    digest(logical_ref["sha256"], "logicalContract.sha256")
    blockers = []
    if sha256(declared_logical) != logical_ref["sha256"]: blockers.append("approved logical contract changed after physical design")
    logical_metadata = load_object(declared_logical)
    logical_approved, logical_blockers, logical = validate_relational_contract(logical_metadata, route, route_path, target, declared_logical, feature, profile)
    if not logical_approved or logical_blockers: blockers.append("logical relational contract is not approved and current")
    model_ref = metadata["logicalModel"]
    if not isinstance(model_ref, dict) or set(model_ref) != {"path", "sha256"}: raise ValueError("logicalModel reference is invalid")
    logical_path = inside(root, model_ref["path"], "logicalModel.path"); digest(model_ref["sha256"], "logicalModel.sha256")
    if sha256(logical_path) != model_ref["sha256"] or logical_path != root / logical_metadata["artifact"]["path"]: blockers.append("logical model reference is stale or mismatched")
    if metadata["target"] != logical_metadata["target"]: blockers.append("physical contract target does not match logical contract")
    artifact = metadata["artifact"]
    if not isinstance(artifact, dict) or set(artifact) != {"format", "path"} or artifact["format"] != "PHYSICAL_DATA_MODEL": raise ValueError("physical artifact reference is invalid")
    declared_physical = inside(root, artifact["path"], "artifact.path")
    if declared_physical != physical_path.resolve(): raise ValueError("physical artifact path does not match")
    digest(metadata["physicalModelSha256"], "physicalModelSha256")
    if sha256(declared_physical) != metadata["physicalModelSha256"]: blockers.append("physical model changed after assessment")
    physical = load_object(declared_physical); blockers.extend(validate_physical_model(physical, logical, metadata, target))
    approved = validate_approval(metadata["approval"], "approval", metadata)
    return approved, blockers, physical, logical
