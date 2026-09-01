#!/usr/bin/env python3
"""Validation and user-view support for logical relational data contracts."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from http_api_contract import reject_openapi_secrets
from validate_design_contract import inside, validate as validate_metadata
from validate_feature_specs import load_object, text


STABLE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SECRET_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
LOGICAL_TYPES = {"STRING", "INTEGER", "DECIMAL", "BOOLEAN", "DATE", "TIME", "DATETIME", "UUID", "BINARY", "JSON", "CUSTOM"}
SENSITIVITY = {"NONE", "PII", "SENSITIVE"}
CARDINALITIES = {"ONE", "ZERO_OR_ONE", "ONE_OR_MORE", "ZERO_OR_MORE"}
PHYSICAL_STRATEGIES = {"FLYWAY_SQL", "LIQUIBASE", "DECLARATIVE_SQL", "EXTERNALLY_MANAGED", "CUSTOM", "DEFERRED"}
PROVISIONING = {"DOCKER_COMPOSE", "TESTCONTAINERS", "BOTH", "EXTERNAL", "CUSTOM", "DEFERRED"}
ENGINES = {"H2", "POSTGRESQL", "MYSQL", "MARIADB", "ORACLE", "SQL_SERVER", "CUSTOM", "UNKNOWN"}


def string_array(value: Any, location: str, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{location} must be a string array")
    if not allow_empty and not value:
        raise ValueError(f"{location} must not be empty")
    if len(value) != len(set(value)):
        raise ValueError(f"{location} must not contain duplicates")
    return value


def stable_id(value: Any, location: str) -> str:
    result = text(value, location, False)
    if not STABLE_ID.fullmatch(result):
        raise ValueError(f"{location} must be lowercase kebab-case")
    return result


def derived_traceability(model: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for entity in model.get("entities", []):
        subjects = [(f"entity:{entity.get('entityId')}", entity.get("requirementRefs", []))]
        subjects.extend(
            (f"field:{field.get('fieldId')}", field.get("requirementRefs", []))
            for field in entity.get("fields", [])
        )
        subjects.extend(
            (f"invariant:{rule.get('invariantId')}", rule.get("requirementRefs", []))
            for rule in entity.get("invariants", [])
        )
        result.extend({"subjectRef": subject, "requirementRefs": refs} for subject, refs in subjects if refs)
    for relationship in model.get("relationships", []):
        refs = relationship.get("requirementRefs", [])
        if refs:
            result.append({"subjectRef": f"relationship:{relationship.get('relationshipId')}", "requirementRefs": refs})
    return result


def validate_model(model: dict[str, Any], feature: dict[str, Any], metadata: dict[str, Any], target: Path) -> list[str]:
    reject_openapi_secrets(model, location="dataModel")
    expected_keys = {"modelVersion", "modelId", "storeKind", "storeId", "purpose", "physicalArtifactStrategy", "physicalArtifactCustom", "runtimeProvisioning", "entities", "relationships"}
    if set(model) != expected_keys:
        raise ValueError("relational data model has invalid top-level fields")
    if model["modelVersion"] != 1 or model["storeKind"] != "RELATIONAL":
        raise ValueError("modelVersion must be 1 and storeKind must be RELATIONAL")
    model_id = stable_id(model["modelId"], "modelId")
    store_id = text(model["storeId"], "storeId", False)
    text(model["purpose"], "purpose")
    blockers: list[str] = []
    if model_id == "unknown": blockers.append("data model ID is UNKNOWN")
    if model["purpose"] == "UNKNOWN":
        blockers.append("data model purpose is UNKNOWN")
    if model["physicalArtifactStrategy"] not in PHYSICAL_STRATEGIES:
        raise ValueError("physicalArtifactStrategy is invalid")
    physical_custom = model["physicalArtifactCustom"]
    if model["physicalArtifactStrategy"] == "CUSTOM":
        if not isinstance(physical_custom, str) or not physical_custom.strip(): blockers.append("custom physical artifact strategy requires a description")
    elif physical_custom is not None:
        blockers.append("non-custom physical artifact strategy must not declare a custom description")
    selected_stores = metadata["target"]["dataStoreIds"]
    if selected_stores and store_id not in selected_stores:
        blockers.append("data model store does not match the routed data stores")
    runtime = model["runtimeProvisioning"]
    runtime_keys = {"strategy", "databaseEngine", "customDatabaseEngine", "customDescription", "imageReference", "composePath", "credentialSecretNames"}
    if not isinstance(runtime, dict) or set(runtime) != runtime_keys:
        raise ValueError("runtimeProvisioning has invalid fields")
    strategy, engine = runtime["strategy"], runtime["databaseEngine"]
    if strategy not in PROVISIONING or engine not in ENGINES:
        raise ValueError("runtime provisioning strategy or database engine is invalid")
    if engine == "CUSTOM":
        if not isinstance(runtime["customDatabaseEngine"], str) or not runtime["customDatabaseEngine"].strip(): blockers.append("custom database engine requires a description")
    elif runtime["customDatabaseEngine"] is not None:
        blockers.append("standard database engine must not declare a custom engine description")
    if strategy == "CUSTOM":
        if not isinstance(runtime["customDescription"], str) or not runtime["customDescription"].strip(): blockers.append("custom provisioning requires a description")
    elif runtime["customDescription"] is not None:
        blockers.append("standard provisioning must not declare a custom description")
    secret_names = string_array(runtime["credentialSecretNames"], "runtimeProvisioning.credentialSecretNames")
    if any(not SECRET_NAME.fullmatch(item) for item in secret_names):
        raise ValueError("credential secret names must use uppercase environment-variable names")
    if strategy in {"DOCKER_COMPOSE", "TESTCONTAINERS", "BOTH"}:
        if engine == "UNKNOWN":
            blockers.append("container provisioning requires a resolved relational database engine")
        image = runtime["imageReference"]
        if not isinstance(image, str) or ":" not in image or image.endswith(":latest") or any(item in image for item in ("$", "{", "}", " ")):
            blockers.append("container provisioning requires an explicitly pinned non-latest image")
        if engine == "H2":
            blockers.append("H2 is embedded and must not use container provisioning")
    elif runtime["imageReference"] is not None:
        blockers.append("non-container provisioning must not declare a container image")
    if strategy in {"DOCKER_COMPOSE", "BOTH"}:
        if not isinstance(runtime["composePath"], str):
            blockers.append("Docker Compose provisioning requires a future compose path")
        else:
            inside(target.resolve(), runtime["composePath"], "runtimeProvisioning.composePath")
        if not secret_names:
            blockers.append("Docker Compose provisioning requires credential secret names")
    elif runtime["composePath"] is not None:
        blockers.append("non-Compose provisioning must not declare a compose path")
    entities = model["entities"]
    if not isinstance(entities, list):
        raise ValueError("entities must be an array")
    if not entities: blockers.append("data model has no entities")
    entity_ids: set[str] = set()
    field_ids: set[str] = set()
    invariant_ids: set[str] = set()
    known_requirements = {item["id"] for item in feature.get("acceptanceCriteria", []) + feature.get("businessRules", [])}
    linked_requirements: set[str] = set()
    for index, entity in enumerate(entities):
        location = f"entities[{index}]"
        required = {"entityId", "name", "description", "owner", "lifecycle", "sensitivity", "requirementRefs", "fields", "invariants"}
        if not isinstance(entity, dict) or set(entity) != required:
            raise ValueError(f"{location} has invalid fields")
        entity_id = stable_id(entity["entityId"], f"{location}.entityId")
        if entity_id in entity_ids:
            raise ValueError(f"duplicate entityId: {entity_id}")
        entity_ids.add(entity_id)
        text(entity["name"], f"{location}.name", False); text(entity["description"], f"{location}.description", False)
        owner = entity["owner"]
        if not isinstance(owner, dict) or set(owner) != {"projectId", "modulePath"}:
            raise ValueError(f"{location}.owner has invalid fields")
        if owner["projectId"] != metadata["target"]["projectId"] or owner["modulePath"] != metadata["target"]["modulePath"]:
            blockers.append(f"entity owner does not match routed target: {entity_id}")
        lifecycle = entity["lifecycle"]
        if not isinstance(lifecycle, dict) or set(lifecycle) != {"creation", "deletion", "retention"}:
            raise ValueError(f"{location}.lifecycle has invalid fields")
        for key, value in lifecycle.items():
            text(value, f"{location}.lifecycle.{key}")
            if value == "UNKNOWN": blockers.append(f"entity lifecycle is UNKNOWN: {entity_id}.{key}")
        if entity["sensitivity"] not in SENSITIVITY:
            raise ValueError(f"{location}.sensitivity is invalid")
        refs = string_array(entity["requirementRefs"], f"{location}.requirementRefs")
        linked_requirements.update(refs)
        fields = entity["fields"]
        if not isinstance(fields, list) or not fields:
            raise ValueError(f"{location}.fields must be a non-empty array")
        identifiers = 0
        for field_index, field in enumerate(fields):
            field_location = f"{location}.fields[{field_index}]"
            field_keys = {"fieldId", "name", "description", "logicalType", "required", "identifier", "unique", "sensitivity", "requirementRefs"}
            if not isinstance(field, dict) or set(field) != field_keys:
                raise ValueError(f"{field_location} has invalid fields")
            field_id = stable_id(field["fieldId"], f"{field_location}.fieldId")
            if field_id in field_ids: raise ValueError(f"duplicate fieldId: {field_id}")
            field_ids.add(field_id)
            text(field["name"], f"{field_location}.name", False); text(field["description"], f"{field_location}.description", False)
            if field["logicalType"] not in LOGICAL_TYPES: raise ValueError(f"{field_location}.logicalType is invalid")
            if not all(isinstance(field[key], bool) for key in ("required", "identifier", "unique")):
                raise ValueError(f"{field_location} flags must be boolean")
            if field["identifier"]:
                identifiers += 1
                if not field["required"] or not field["unique"]: blockers.append(f"identifier must be required and unique: {field_id}")
            if field["sensitivity"] not in SENSITIVITY: raise ValueError(f"{field_location}.sensitivity is invalid")
            refs = string_array(field["requirementRefs"], f"{field_location}.requirementRefs")
            linked_requirements.update(refs)
        if identifiers == 0: blockers.append(f"entity has no identifier: {entity_id}")
        invariants = entity["invariants"]
        if not isinstance(invariants, list): raise ValueError(f"{location}.invariants must be an array")
        for rule_index, rule in enumerate(invariants):
            rule_location = f"{location}.invariants[{rule_index}]"
            if not isinstance(rule, dict) or set(rule) != {"invariantId", "description", "requirementRefs"}:
                raise ValueError(f"{rule_location} has invalid fields")
            rule_id = stable_id(rule["invariantId"], f"{rule_location}.invariantId")
            if rule_id in invariant_ids: raise ValueError(f"duplicate invariantId: {rule_id}")
            invariant_ids.add(rule_id); text(rule["description"], f"{rule_location}.description", False)
            refs = string_array(rule["requirementRefs"], f"{rule_location}.requirementRefs", False)
            linked_requirements.update(refs)
    relationships = model["relationships"]
    if not isinstance(relationships, list): raise ValueError("relationships must be an array")
    relationship_ids: set[str] = set()
    for index, relationship in enumerate(relationships):
        location = f"relationships[{index}]"
        keys = {"relationshipId", "fromEntityId", "toEntityId", "fromCardinality", "toCardinality", "description", "requirementRefs"}
        if not isinstance(relationship, dict) or set(relationship) != keys: raise ValueError(f"{location} has invalid fields")
        relationship_id = stable_id(relationship["relationshipId"], f"{location}.relationshipId")
        if relationship_id in relationship_ids: raise ValueError(f"duplicate relationshipId: {relationship_id}")
        relationship_ids.add(relationship_id)
        if relationship["fromEntityId"] not in entity_ids or relationship["toEntityId"] not in entity_ids:
            blockers.append(f"relationship references an unknown entity: {relationship_id}")
        if relationship["fromCardinality"] not in CARDINALITIES or relationship["toCardinality"] not in CARDINALITIES:
            raise ValueError(f"{location} cardinality is invalid")
        text(relationship["description"], f"{location}.description", False)
        refs = string_array(relationship["requirementRefs"], f"{location}.requirementRefs")
        linked_requirements.update(refs)
    unknown_refs = linked_requirements - known_requirements
    if unknown_refs: blockers.append("data model references unknown feature requirements: " + ", ".join(sorted(unknown_refs)))
    if not linked_requirements: blockers.append("data model has no feature traceability")
    expected_traceability = derived_traceability(model)
    if metadata.get("traceability") != expected_traceability:
        blockers.append("contract traceability does not match the relational data model")
    return blockers


def validate_relational_contract(metadata: dict[str, Any], route: dict[str, Any], route_path: Path, target: Path, contract_path: Path, feature: dict[str, Any], profile: dict[str, Any] | None = None) -> tuple[bool, list[str], dict[str, Any]]:
    approved, blockers = validate_metadata(metadata, route, route_path, target, contract_path)
    if metadata.get("kind") != "PERSISTENCE" or metadata.get("disposition") != "CREATE":
        blockers.append("this milestone supports PERSISTENCE CREATE only")
    if metadata.get("artifact", {}).get("format") != "DATA_MODEL":
        blockers.append("relational logical contract artifact format must be DATA_MODEL")
    model_path = inside(target.resolve(), metadata["artifact"]["path"], "artifact.path")
    model_digest = metadata.get("modelSha256")
    if not isinstance(model_digest, str) or len(model_digest) != 64 or any(item not in "0123456789abcdef" for item in model_digest):
        raise ValueError("modelSha256 must be lowercase SHA-256")
    if hashlib.sha256(model_path.read_bytes()).hexdigest() != model_digest:
        blockers.append("relational data model changed after assessment")
    model = load_object(model_path)
    blockers.extend(validate_model(model, feature, metadata, target))
    if profile is not None:
        decisions = profile.get("decisions", {})
        migration = decisions.get("migration", {}).get("option") if isinstance(decisions.get("migration"), dict) else None
        expected_physical = {"migration.flyway": "FLYWAY_SQL", "migration.liquibase": "LIQUIBASE", "migration.external": "EXTERNALLY_MANAGED", "migration.none": "DEFERRED"}.get(migration)
        if expected_physical and model["physicalArtifactStrategy"] != expected_physical:
            blockers.append("physical artifact strategy does not match the technology profile")
        database = decisions.get("database", {}).get("option") if isinstance(decisions.get("database"), dict) else None
        allowed_engines = {"database.h2": {"H2"}, "database.postgresql": {"POSTGRESQL"}, "database.mysql": {"MYSQL", "MARIADB"}, "database.oracle": {"ORACLE"}}.get(database)
        if allowed_engines and model["runtimeProvisioning"]["databaseEngine"] not in allowed_engines:
            blockers.append("runtime database engine does not match the technology profile")
    return approved, blockers, model
