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

import create_relational_physical_contract  # noqa: E402
import record_relational_physical_contract_approval  # noqa: E402
from relational_physical_contract import derived_traceability, load_adapters, validate_physical_contract  # noqa: E402
from render_relational_physical_contract import render  # noqa: E402
from tests.test_feature_specs import feature_spec  # noqa: E402
import tests.test_relational_data_contract as logical_tests  # noqa: E402
from validate_feature_specs import approval_content_hash  # noqa: E402


def physical_model() -> dict:
    return {
        "physicalModelVersion": 1, "physicalModelId": "leave-requests-postgresql", "adapterId": "postgresql-flyway",
        "database": {"engine": "POSTGRESQL", "version": "17", "schemaName": "public"},
        "migrationPlan": {"strategy": "FLYWAY_SQL", "plannedSourcePath": "src/main/resources/db/migration/V1__create_leave_requests.sql", "sourceOfTruth": "VERSIONED_MIGRATION", "requiredRecovery": "TRANSACTIONAL_REQUIRED", "applyAuthorized": False},
        "provisioningPlan": {
            "strategy": "BOTH",
            "compose": {"plannedPath": "compose.yaml", "serviceName": "leave_db", "volumeName": "leave_db_data", "imageReference": "postgres:17.6", "hostPort": 5432, "checkPortAtExecution": True, "autoStart": False, "destructiveCleanupAllowed": False, "secretNames": ["DB_USERNAME", "DB_PASSWORD"]},
            "testcontainers": {"imageReference": "postgres:17.6", "reuse": False, "authPersistence": False, "startupAuthorized": False},
        },
        "riskAssessment": {"dataLoss": "NONE", "locking": "NONE", "downtime": "NONE", "reason": "Creates a new empty schema only."},
        "tables": [{
            "tableId": "leave-requests-table", "name": "leave_requests", "description": "Stores employee leave requests.", "entityRef": "leave-request", "changeIntent": "CREATE", "previousNames": [],
            "columns": [
                {"columnId": "leave-request-id-column", "name": "leave_request_id", "description": "Stable request identity.", "fieldRef": "leave-request-id", "sqlType": "UUID", "nullable": False, "unique": False, "defaultExpression": None, "changeIntent": "CREATE", "previousNames": []},
                {"columnId": "leave-start-date-column", "name": "start_date", "description": "First leave date.", "fieldRef": "leave-start-date", "sqlType": "DATE", "nullable": False, "unique": False, "defaultExpression": None, "changeIntent": "CREATE", "previousNames": []},
                {"columnId": "leave-end-date-column", "name": "end_date", "description": "Last leave date.", "fieldRef": "leave-end-date", "sqlType": "DATE", "nullable": False, "unique": False, "defaultExpression": None, "changeIntent": "CREATE", "previousNames": []},
            ],
            "primaryKey": {"constraintId": "leave-requests-pk", "name": "pk_leave_requests", "columnIds": ["leave-request-id-column"]},
            "foreignKeys": [],
            "checkConstraints": [{"constraintId": "leave-date-range-check", "name": "ck_leave_requests_date_range", "expression": "end_date >= start_date", "invariantRefs": ["valid-leave-date-range"]}],
            "indexes": [],
        }],
        "queryPatterns": [], "relationshipImplementations": [],
        "invariantImplementations": [{"invariantRef": "valid-leave-date-range", "enforcement": "DATABASE_CHECK", "constraintRef": "leave-date-range-check", "reason": "The invariant only depends on columns in one row."}],
    }


class RelationalPhysicalContractTests(unittest.TestCase):
    def fixture(self, root: Path, approved: bool = True):
        logical_test = logical_tests.RelationalDataContractTests(); logical_metadata, logical, route, route_path, logical_contract, logical_path = logical_test.fixture(root, True)
        physical = physical_model(); directory = logical_contract.parent / "physical"; directory.mkdir()
        physical_path = directory / "physical-model.json"; physical_path.write_text(json.dumps(physical))
        adapter = load_adapters()[physical["adapterId"]]
        metadata = {
            "physicalContractVersion": 1, "contractId": "persistence-physical",
            "logicalContract": {"path": logical_contract.relative_to(root).as_posix(), "sha256": hashlib.sha256(logical_contract.read_bytes()).hexdigest()},
            "logicalModel": {"path": logical_path.relative_to(root).as_posix(), "sha256": hashlib.sha256(logical_path.read_bytes()).hexdigest()},
            "target": copy.deepcopy(logical_metadata["target"]), "artifact": {"format": "PHYSICAL_DATA_MODEL", "path": physical_path.relative_to(root).as_posix()},
            "physicalModelSha256": hashlib.sha256(physical_path.read_bytes()).hexdigest(), "adapter": {"id": adapter["id"], "status": adapter["status"]},
            "traceability": derived_traceability(physical, logical),
            "approval": {"status": "APPROVED" if approved else "DRAFT", "approvedBy": "test-user" if approved else None, "approvedAt": "2026-09-01T00:00:00Z" if approved else None, "approvedContentSha256": None},
        }
        if approved: metadata["approval"]["approvedContentSha256"] = approval_content_hash(metadata)
        contract_path = directory / "metadata.json"; contract_path.write_text(json.dumps(metadata))
        return metadata, physical, logical, route, route_path, logical_contract, physical_path, contract_path

    def validate(self, root: Path, fixture):
        metadata, _, _, route, route_path, logical_contract, physical_path, _ = fixture
        return validate_physical_contract(metadata, physical_path, logical_contract, route, route_path, root, feature_spec(), {})

    def test_complete_postgresql_flyway_contract_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); fixture = self.fixture(root)
            self.assertEqual((True, []), self.validate(root, fixture)[:2])

    def test_physical_model_drift_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); fixture = self.fixture(root); fixture[6].write_text(fixture[6].read_text() + "\n")
            self.assertIn("physical model changed after assessment", self.validate(root, fixture)[1])

    def test_logical_contract_drift_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); fixture = self.fixture(root); fixture[5].write_text(fixture[5].read_text() + "\n")
            self.assertIn("approved logical contract changed after physical design", self.validate(root, fixture)[1])

    def test_every_logical_field_must_be_mapped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); fixture = self.fixture(root); physical = json.loads(fixture[6].read_text()); physical["tables"][0]["columns"].pop(); fixture[6].write_text(json.dumps(physical))
            self.assertIn("physical columns do not cover every logical field exactly once", self.validate(root, fixture)[1])

    def test_incompatible_postgresql_type_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); fixture = self.fixture(root); physical = json.loads(fixture[6].read_text()); physical["tables"][0]["columns"][1]["sqlType"] = "UUID"; fixture[6].write_text(json.dumps(physical))
            self.assertTrue(any("type does not match" in item for item in self.validate(root, fixture)[1]))

    def test_reserved_postgresql_table_name_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); fixture = self.fixture(root); physical = json.loads(fixture[6].read_text()); physical["tables"][0]["name"] = "user"; fixture[6].write_text(json.dumps(physical))
            with self.assertRaisesRegex(ValueError, "reserved PostgreSQL name"): self.validate(root, fixture)

    def test_non_ready_adapter_is_visible_and_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); fixture = self.fixture(root); physical = json.loads(fixture[6].read_text()); physical["adapterId"] = "postgresql-liquibase"; physical["migrationPlan"]["strategy"] = "LIQUIBASE"; fixture[6].write_text(json.dumps(physical)); fixture[0]["adapter"] = {"id": "postgresql-liquibase", "status": "PLANNED"}; fixture[0]["approval"]["approvedContentSha256"] = approval_content_hash(fixture[0])
            self.assertIn("physical adapter is not READY: postgresql-liquibase", self.validate(root, fixture)[1])

    def test_contract_cannot_authorize_migration_or_container_start(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); fixture = self.fixture(root); physical = json.loads(fixture[6].read_text()); physical["migrationPlan"]["applyAuthorized"] = True; physical["provisioningPlan"]["compose"]["autoStart"] = True; fixture[6].write_text(json.dumps(physical))
            blockers = self.validate(root, fixture)[1]; self.assertTrue(any("must not authorize" in item for item in blockers)); self.assertTrue(any("must defer execution" in item for item in blockers))

    def test_query_pattern_must_reference_real_columns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); fixture = self.fixture(root); physical = json.loads(fixture[6].read_text())
            physical["queryPatterns"] = [{"queryPatternId": "leave-by-owner", "description": "Find an owner's requests.", "tableId": "leave-requests-table", "columnIds": ["missing-owner-column"], "requirementRefs": ["requirement-leave-request"]}]
            fixture[6].write_text(json.dumps(physical))
            self.assertTrue(any("unknown columns" in item for item in self.validate(root, fixture)[1]))

    def test_duplicate_constraint_ids_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); fixture = self.fixture(root); physical = json.loads(fixture[6].read_text())
            physical["tables"][0]["checkConstraints"][0]["constraintId"] = "leave-requests-pk"
            fixture[6].write_text(json.dumps(physical))
            with self.assertRaisesRegex(ValueError, "duplicate constraintId"): self.validate(root, fixture)

    def test_invariant_must_link_to_its_own_check_constraint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); fixture = self.fixture(root); physical = json.loads(fixture[6].read_text())
            physical["tables"][0]["checkConstraints"][0]["invariantRefs"] = []
            fixture[6].write_text(json.dumps(physical))
            self.assertTrue(any("matching check constraint" in item for item in self.validate(root, fixture)[1]))

    def test_user_view_separates_design_from_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            metadata, physical, logical, *_ = self.fixture(Path(directory))
            markdown = render(metadata, physical, logical, [])
            self.assertIn("migration 파일을 생성하거나 실행하지 않음", markdown); self.assertIn("자동 시작 안 함", markdown); self.assertIn("실제 복구 가능성", markdown)

    def test_creator_materializes_only_contract_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); logical_fixture = logical_tests.RelationalDataContractTests().fixture(root, True); logical_contract = logical_fixture[4]
            source = root / "physical-draft.json"; source.write_text(json.dumps(physical_model())); output_dir = logical_contract.parent / "physical"; contract_output, model_output = output_dir / "metadata.json", output_dir / "physical-model.json"
            feature_path, profile_path = root / "feature.json", root / "profile.json"; feature_path.write_text(json.dumps(feature_spec())); profile_path.write_text("{}")
            arguments = ["create_relational_physical_contract.py", "--logical-contract", str(logical_contract), "--physical-model-source", str(source), "--physical-contract-output", str(contract_output), "--physical-model-output", str(model_output), "--route", str(logical_fixture[3]), "--feature", str(feature_path), "--profile", str(profile_path), "--target", str(root)]
            output = io.StringIO()
            with mock.patch.object(sys, "argv", arguments), contextlib.redirect_stdout(output): self.assertEqual(0, create_relational_physical_contract.main())
            self.assertIn("MIGRATION_RENDERED: no", output.getvalue()); self.assertFalse((root / "compose.yaml").exists()); self.assertFalse((root / "src").exists())

    def test_approval_is_atomic_and_leaves_models_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); fixture = self.fixture(root, False); metadata, physical, logical, route, route_path, logical_contract, physical_path, contract_path = fixture
            contract_path.with_suffix(".md").write_text(render(metadata, physical, logical, []))
            feature_path, project_path, profile_path = root / "feature.json", root / "project.json", root / "profile.json"; feature_path.write_text(json.dumps(feature_spec())); project_path.write_text("{}"); profile_path.write_text("{}")
            physical_before, logical_before = physical_path.read_bytes(), logical_contract.read_bytes()
            arguments = ["record_relational_physical_contract_approval.py", "--contract", str(contract_path), "--physical-model", str(physical_path), "--logical-contract", str(logical_contract), "--route", str(route_path), "--feature", str(feature_path), "--project-brief", str(project_path), "--profile", str(profile_path), "--target", str(root), "--expected-contract-hash", approval_content_hash(metadata), "--expected-physical-model-hash", hashlib.sha256(physical_before).hexdigest(), "--expected-logical-contract-hash", hashlib.sha256(logical_before).hexdigest(), "--approved-by", "test-user", "--approved-at", "2026-09-01T00:00:00Z"]
            with mock.patch.object(sys, "argv", arguments), mock.patch.object(record_relational_physical_contract_approval, "assess", return_value=(True, True, [])), mock.patch.object(record_relational_physical_contract_approval, "verify_inputs", return_value=[]), contextlib.redirect_stdout(io.StringIO()): self.assertEqual(0, record_relational_physical_contract_approval.main())
            self.assertEqual("APPROVED", json.loads(contract_path.read_text())["approval"]["status"]); self.assertEqual(physical_before, physical_path.read_bytes()); self.assertEqual(logical_before, logical_contract.read_bytes())


if __name__ == "__main__": unittest.main(verbosity=2)
