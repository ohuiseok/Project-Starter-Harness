#!/usr/bin/env python3

from __future__ import annotations

import contextlib
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

import render_relational_artifact_dry_run as dry_run  # noqa: E402
from render_relational_artifact_dry_run_markdown import render  # noqa: E402
from tests.test_feature_specs import feature_spec  # noqa: E402
import tests.test_relational_physical_contract as physical_tests  # noqa: E402


class RelationalArtifactDryRunTests(unittest.TestCase):
    def fixture(self, root: Path):
        physical_fixture = physical_tests.RelationalPhysicalContractTests().fixture(root)
        metadata, physical, _, route, route_path, logical_contract, physical_path, contract_path = physical_fixture
        feature_path, profile_path = root / "feature.json", root / "profile.json"
        profile = {"project": {"packageName": "com.example"}, "decisions": {"verification": {"option": "verification.testcontainers"}}}
        feature_path.write_text(json.dumps(feature_spec())); profile_path.write_text(json.dumps(profile))
        plan = {"artifactPlanVersion": 1, "planId": "leave-db-files", "physicalContractSha256": hashlib.sha256(contract_path.read_bytes()).hexdigest(), "physicalModelSha256": hashlib.sha256(physical_path.read_bytes()).hexdigest(), "profileSha256": hashlib.sha256(profile_path.read_bytes()).hexdigest(), "databaseName": "leave_service", "credentialBindings": {"username": "DB_USERNAME", "password": "DB_PASSWORD"}, "testcontainers": {"plannedPath": "src/test/java/com/example/LeaveDatabaseTestConfiguration.java", "packageName": "com.example", "className": "LeaveDatabaseTestConfiguration"}}
        plan_path = root / "artifact-plan.json"; plan_path.write_text(json.dumps(plan)); output = root / "dry-run.json"
        arguments = ["render_relational_artifact_dry_run.py", "--physical-contract", str(contract_path), "--physical-model", str(physical_path), "--logical-contract", str(logical_contract), "--route", str(route_path), "--feature", str(feature_path), "--profile", str(profile_path), "--artifact-plan", str(plan_path), "--target", str(root), "--output", str(output)]
        return physical, plan, plan_path, output, arguments

    def run_dry(self, arguments: list[str]) -> tuple[int, str]:
        stream = io.StringIO()
        with mock.patch.object(sys, "argv", arguments), contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream): return dry_run.main(), stream.getvalue()

    def test_clear_dry_run_plans_three_files_without_writing_them(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); _, _, _, output, arguments = self.fixture(root)
            self.assertEqual(0, self.run_dry(arguments)[0]); report = json.loads(output.read_text())
            paths = {item["path"] for item in report["plannedChanges"]["creates"]}
            self.assertEqual({"src/main/resources/db/migration/V1__create_leave_requests.sql", "compose.yaml", "src/test/java/com/example/LeaveDatabaseTestConfiguration.java"}, paths)
            self.assertEqual(report["plannedChanges"]["desiredManifest"]["files"], {item["path"]: item["sha256"] for item in report["generatedArtifacts"]})
            self.assertFalse((root / "compose.yaml").exists()); self.assertFalse((root / "src").exists()); self.assertFalse(report["databaseOrContainerChanged"])

    def test_existing_unowned_file_is_a_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); _, _, _, output, arguments = self.fixture(root); (root / "compose.yaml").write_text("user owned\n")
            self.assertEqual(0, self.run_dry(arguments)[0]); report = json.loads(output.read_text())
            self.assertFalse(report["readyForApproval"]); self.assertEqual("CONFLICT", report["plannedChanges"]["state"])

    def test_artifact_plan_hash_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); _, plan, plan_path, _, arguments = self.fixture(root); plan["profileSha256"] = "0" * 64; plan_path.write_text(json.dumps(plan))
            code, output = self.run_dry(arguments); self.assertEqual(1, code); self.assertIn("technology profile changed", output)

    def test_credential_roles_must_match_approved_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); _, plan, plan_path, _, arguments = self.fixture(root); plan["credentialBindings"] = {"username": "DB_PASSWORD", "password": "DB_PASSWORD"}; plan_path.write_text(json.dumps(plan))
            code, output = self.run_dry(arguments); self.assertEqual(1, code); self.assertIn("map the approved secret names exactly", output)

    def test_testcontainers_requires_matching_technology_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); _, plan, plan_path, _, arguments = self.fixture(root); profile_path = root / "profile.json"
            profile_path.write_text(json.dumps({"project": {"packageName": "com.example"}, "decisions": {"verification": {"option": "verification.unit-only"}}})); plan["profileSha256"] = hashlib.sha256(profile_path.read_bytes()).hexdigest(); plan_path.write_text(json.dumps(plan))
            code, output = self.run_dry(arguments); self.assertEqual(1, code); self.assertIn("does not enable Testcontainers", output)

    def test_harness_repository_cannot_be_the_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, _, _, _, arguments = self.fixture(Path(directory)); target_index = arguments.index("--target") + 1; arguments[target_index] = str(ROOT)
            code, output = self.run_dry(arguments); self.assertEqual(1, code); self.assertIn("external non-symlink repository", output)

    def test_rendered_sources_contain_no_credential_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); model, plan, *_ = self.fixture(root)
            generated = dry_run.compose(model, plan) + dry_run.testcontainers_java(model, plan)
            self.assertIn("${DB_PASSWORD:?set DB_PASSWORD}", generated); self.assertIn('System.getenv(name)', generated); self.assertNotIn("password123", generated)

    def test_markdown_separates_file_review_from_execution(self) -> None:
        report = {"readyForApproval": True, "generatedArtifacts": [{"kind": "DOCKER_COMPOSE", "path": "compose.yaml", "sha256": "a" * 64, "content": "services: {}\n"}], "plannedChanges": {"creates": [{"path": "compose.yaml"}], "updates": [], "unchanged": [], "conflicts": []}, "recoveryAssessment": {"required": "TRANSACTIONAL_REQUIRED", "renderedDdlClass": "TRANSACTIONAL_CREATE_ONLY"}}
        view = render(report); self.assertIn("실제 프로젝트 파일 변경: 없음", view); self.assertIn("DB 연결·migration 실행: 없음", view); self.assertIn("별도 적용 승인", view)
        self.assertIn("```yaml\nservices: {}", view)


if __name__ == "__main__": unittest.main(verbosity=2)
