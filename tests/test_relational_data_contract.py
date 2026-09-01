#!/usr/bin/env python3

from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / ".agents/skills/spring-project-start/scripts"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(SCRIPTS))

from relational_data_contract import derived_traceability, validate_relational_contract  # noqa: E402
from render_relational_data_contract import render  # noqa: E402
import create_relational_data_contract  # noqa: E402
import record_relational_data_contract_approval  # noqa: E402
from tests.test_design_route import route  # noqa: E402
from tests.test_feature_specs import feature_spec  # noqa: E402
from validate_feature_specs import approval_content_hash  # noqa: E402


def model() -> dict:
    return {
        "modelVersion": 1, "modelId": "leave-requests", "storeKind": "RELATIONAL", "storeId": "default",
        "purpose": "Keep approved leave-request state across application restarts.", "physicalArtifactStrategy": "FLYWAY_SQL", "physicalArtifactCustom": None,
        "runtimeProvisioning": {"strategy": "BOTH", "databaseEngine": "POSTGRESQL", "customDatabaseEngine": None, "customDescription": None, "imageReference": "postgres:17.6", "composePath": "compose.yaml", "credentialSecretNames": ["DB_USERNAME", "DB_PASSWORD"]},
        "entities": [{
            "entityId": "leave-request", "name": "Leave request", "description": "A request for employee leave.",
            "owner": {"projectId": "leave-service", "modulePath": "."},
            "lifecycle": {"creation": "Created after valid submission.", "deletion": "Removed by an approved retention job.", "retention": "Retained for the configured HR policy period."},
            "sensitivity": "PII", "requirementRefs": ["AC-F001-01"],
            "fields": [
                {"fieldId": "leave-request-id", "name": "Request ID", "description": "Stable request identity.", "logicalType": "UUID", "required": True, "identifier": True, "unique": True, "sensitivity": "NONE", "requirementRefs": []},
                {"fieldId": "leave-start-date", "name": "Start date", "description": "First leave date.", "logicalType": "DATE", "required": True, "identifier": False, "unique": False, "sensitivity": "PII", "requirementRefs": ["BR-F001-01"]},
                {"fieldId": "leave-end-date", "name": "End date", "description": "Last leave date.", "logicalType": "DATE", "required": True, "identifier": False, "unique": False, "sensitivity": "PII", "requirementRefs": ["BR-F001-01"]},
            ],
            "invariants": [{"invariantId": "valid-leave-date-range", "description": "End date cannot precede start date.", "requirementRefs": ["BR-F001-01"]}],
        }], "relationships": [],
    }


class RelationalDataContractTests(unittest.TestCase):
    def fixture(self, root: Path, approved: bool = True):
        design_route = route(); selected = next(item for item in design_route["routes"] if item["kind"] == "PERSISTENCE")
        route_path = root / "docs/features/F001/design-route.json"; route_path.parent.mkdir(parents=True); route_path.write_text(json.dumps(design_route))
        contract_path = root / selected["artifactPath"]; contract_path.parent.mkdir(parents=True, exist_ok=True)
        model_path = contract_path.parent / "data-model.json"; data_model = model(); model_path.write_text(json.dumps(data_model))
        metadata = {"contractVersion": 1, "contractId": selected["contractId"], "kind": "PERSISTENCE", "featureId": "F001", "route": {"path": route_path.relative_to(root).as_posix(), "sha256": hashlib.sha256(route_path.read_bytes()).hexdigest()}, "disposition": "CREATE", "target": copy.deepcopy(selected["target"]), "artifact": {"format": "DATA_MODEL", "path": model_path.relative_to(root).as_posix()}, "modelSha256": hashlib.sha256(model_path.read_bytes()).hexdigest(), "traceability": derived_traceability(data_model), "evidencePaths": [], "approval": {"status": "APPROVED" if approved else "DRAFT", "approvedBy": "test-user" if approved else None, "approvedAt": "2026-09-01T00:00:00Z" if approved else None, "approvedContentSha256": None}}
        if approved: metadata["approval"]["approvedContentSha256"] = approval_content_hash(metadata)
        contract_path.write_text(json.dumps(metadata))
        return metadata, data_model, design_route, route_path, contract_path, model_path

    def test_complete_logical_contract_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); metadata, data_model, design_route, route_path, contract_path, _ = self.fixture(root)
            self.assertEqual((True, [], data_model), validate_relational_contract(metadata, design_route, route_path, root, contract_path, feature_spec()))

    def test_every_entity_requires_stable_identifier(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); metadata, _, design_route, route_path, contract_path, model_path = self.fixture(root)
            data_model = json.loads(model_path.read_text()); data_model["entities"][0]["fields"][0]["identifier"] = False; model_path.write_text(json.dumps(data_model)); metadata["traceability"] = derived_traceability(data_model)
            self.assertIn("entity has no identifier: leave-request", validate_relational_contract(metadata, design_route, route_path, root, contract_path, feature_spec())[1])

    def test_relationship_must_reference_known_entities(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); metadata, _, design_route, route_path, contract_path, model_path = self.fixture(root)
            data_model = json.loads(model_path.read_text()); data_model["relationships"] = [{"relationshipId": "unknown-owner", "fromEntityId": "leave-request", "toEntityId": "employee", "fromCardinality": "ZERO_OR_MORE", "toCardinality": "ONE", "description": "Owner", "requirementRefs": ["AC-F001-01"]}]; model_path.write_text(json.dumps(data_model)); metadata["traceability"] = derived_traceability(data_model); metadata["approval"]["approvedContentSha256"] = approval_content_hash(metadata)
            self.assertTrue(any("unknown entity" in item for item in validate_relational_contract(metadata, design_route, route_path, root, contract_path, feature_spec())[1]))

    def test_container_image_must_be_pinned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); metadata, _, design_route, route_path, contract_path, model_path = self.fixture(root)
            data_model = json.loads(model_path.read_text()); data_model["runtimeProvisioning"]["imageReference"] = "postgres:latest"; model_path.write_text(json.dumps(data_model))
            self.assertTrue(any("pinned non-latest image" in item for item in validate_relational_contract(metadata, design_route, route_path, root, contract_path, feature_spec())[1]))

    def test_approved_model_drift_is_detected_even_when_traceability_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); metadata, _, design_route, route_path, contract_path, model_path = self.fixture(root)
            data_model = json.loads(model_path.read_text()); data_model["purpose"] = "Changed purpose with the same requirement links."; model_path.write_text(json.dumps(data_model))
            self.assertIn("relational data model changed after assessment", validate_relational_contract(metadata, design_route, route_path, root, contract_path, feature_spec())[1])

    def test_custom_database_can_use_a_pinned_container_image(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); metadata, _, design_route, route_path, contract_path, model_path = self.fixture(root)
            data_model = json.loads(model_path.read_text()); runtime = data_model["runtimeProvisioning"]
            runtime.update({"databaseEngine": "CUSTOM", "customDatabaseEngine": "CockroachDB", "imageReference": "cockroachdb/cockroach:v26.2.0"})
            model_path.write_text(json.dumps(data_model)); metadata["modelSha256"] = hashlib.sha256(model_path.read_bytes()).hexdigest(); metadata["approval"]["approvedContentSha256"] = approval_content_hash(metadata)
            blockers = validate_relational_contract(metadata, design_route, route_path, root, contract_path, feature_spec())[1]
            self.assertFalse(any("container provisioning requires a resolved" in item for item in blockers))

    def test_dynamic_container_image_reference_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); metadata, _, design_route, route_path, contract_path, model_path = self.fixture(root)
            data_model = json.loads(model_path.read_text()); data_model["runtimeProvisioning"]["imageReference"] = "${POSTGRES_IMAGE:-postgres:17.6}"; model_path.write_text(json.dumps(data_model))
            self.assertTrue(any("pinned non-latest image" in item for item in validate_relational_contract(metadata, design_route, route_path, root, contract_path, feature_spec())[1]))

    def test_contract_choices_must_match_technology_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); metadata, _, design_route, route_path, contract_path, _ = self.fixture(root)
            technology = {"decisions": {"migration": {"option": "migration.liquibase"}, "database": {"option": "database.mysql"}}}
            blockers = validate_relational_contract(metadata, design_route, route_path, root, contract_path, feature_spec(), technology)[1]
            self.assertTrue(any("physical artifact strategy" in item for item in blockers)); self.assertTrue(any("database engine" in item for item in blockers))

    def test_compose_path_cannot_escape_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); metadata, _, design_route, route_path, contract_path, model_path = self.fixture(root)
            data_model = json.loads(model_path.read_text()); data_model["runtimeProvisioning"]["composePath"] = "../compose.yaml"; model_path.write_text(json.dumps(data_model))
            with self.assertRaisesRegex(ValueError, "composePath escapes target"): validate_relational_contract(metadata, design_route, route_path, root, contract_path, feature_spec())

    def test_secret_value_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); metadata, _, design_route, route_path, contract_path, model_path = self.fixture(root)
            data_model = json.loads(model_path.read_text()); data_model["purpose"] = "Bearer abcdefghijklmnop"; model_path.write_text(json.dumps(data_model))
            with self.assertRaisesRegex(ValueError, "secret-like value"): validate_relational_contract(metadata, design_route, route_path, root, contract_path, feature_spec())

    def test_user_view_explains_model_erd_and_deferred_execution(self) -> None:
        data_model = model(); metadata = {"approval": {"status": "DRAFT"}, "traceability": derived_traceability(data_model)}
        markdown = render(metadata, data_model, [], feature_spec())
        self.assertIn("```mermaid", markdown); self.assertIn("Docker Compose와 Testcontainers", markdown); self.assertIn("컨테이너나 DB를 설치·실행하지 않음", markdown); self.assertIn("승인 대기", markdown)

    def test_user_view_translates_internal_blockers(self) -> None:
        data_model = model(); metadata = {"approval": {"status": "DRAFT"}, "traceability": derived_traceability(data_model)}
        markdown = render(metadata, data_model, ["entity has no identifier: leave-request"], feature_spec())
        self.assertIn("각 데이터 객체를 구별할 식별자", markdown); self.assertNotIn("entity has no identifier", markdown)

    def test_approval_is_atomic_and_does_not_change_model(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); metadata, data_model, _, route_path, contract_path, model_path = self.fixture(root, False)
            contract_path.with_suffix(".md").write_text(render(metadata, data_model, [], feature_spec()))
            feature_path, project_path, profile_path = root / "feature.json", root / "project.json", root / "profile.json"
            feature_path.write_text(json.dumps(feature_spec())); project_path.write_text("{}"); profile_path.write_text("{}")
            model_before = model_path.read_bytes(); arguments = ["record_relational_data_contract_approval.py", "--contract", str(contract_path), "--route", str(route_path), "--feature", str(feature_path), "--project-brief", str(project_path), "--profile", str(profile_path), "--target", str(root), "--expected-contract-hash", approval_content_hash(metadata), "--expected-model-hash", hashlib.sha256(model_before).hexdigest(), "--approved-by", "test-user", "--approved-at", "2026-09-01T00:00:00Z"]
            with mock.patch.object(sys, "argv", arguments), mock.patch.object(record_relational_data_contract_approval, "assess", return_value=(True, True, [])), mock.patch.object(record_relational_data_contract_approval, "verify_inputs", return_value=[]), contextlib.redirect_stdout(io.StringIO()): self.assertEqual(0, record_relational_data_contract_approval.main())
            self.assertEqual("APPROVED", json.loads(contract_path.read_text())["approval"]["status"]); self.assertEqual(model_before, model_path.read_bytes())

    def test_creator_materializes_model_and_metadata_without_source_or_database_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); design_route = route(); selected = next(item for item in design_route["routes"] if item["kind"] == "PERSISTENCE")
            route_path = root / "docs/features/F001/design-route.json"; route_path.parent.mkdir(parents=True); route_path.write_text(json.dumps(design_route))
            feature_path, project_path, profile_path, source_path = root / "feature.json", root / "project.json", root / "profile.json", root / "draft-model.json"
            feature_path.write_text(json.dumps(feature_spec())); project_path.write_text("{}"); profile_path.write_text("{}"); source_path.write_text(json.dumps(model()))
            contract_output = root / selected["artifactPath"]; model_output = contract_output.parent / "data-model.json"
            arguments = ["create_relational_data_contract.py", "--route", str(route_path), "--feature", str(feature_path), "--project-brief", str(project_path), "--profile", str(profile_path), "--target", str(root), "--contract-id", selected["contractId"], "--model-source", str(source_path), "--contract-output", str(contract_output), "--model-output", str(model_output)]
            output = io.StringIO()
            with mock.patch.object(sys, "argv", arguments), mock.patch.object(create_relational_data_contract, "assess", return_value=(True, True, [])), contextlib.redirect_stdout(output): self.assertEqual(0, create_relational_data_contract.main())
            metadata = json.loads(contract_output.read_text()); self.assertEqual(derived_traceability(model()), metadata["traceability"])
            self.assertEqual(hashlib.sha256(model_output.read_bytes()).hexdigest(), metadata["modelSha256"])
            self.assertIn("DATABASE_OR_CONTAINER_CHANGED: no", output.getvalue()); self.assertFalse((root / "src").exists())


if __name__ == "__main__": unittest.main(verbosity=2)
